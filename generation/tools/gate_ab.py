"""Offline A/B for docs/plans/JEV_EVALUATION_PLAN.md Phase 1a: does a GATED card prompt (vocabulary sections
and op rows chosen per brief by heuristic-OR-Jev, schema kept whole) produce cards as good as the FULL prompt?

Paired design: the same briefs (real ones from scratch/_class_gen), the same card model and settings as the
production `cards` role on the OpenRouter tier, the same validator and repair loop (`pipeline.generate_card`).
Arm A = full `contract.system_prompt()`. Arm B = the same text with unselected vocab sections and op rows cut.

Measured per arm: validator pass on attempt 1, pass after repair, drop rate, first-attempt error count,
balance score vs ceiling, type/rarity fidelity to the brief, ops used, input tokens. Then two blind pairwise
judges on the pairs where both arms produced a card: an LLM judge (position-swapped, twice) and Jev.

    uv run python tools/gate_ab.py --n 40 [--seed 7] [--workers 6] [--judge openai/gpt-5.4-mini]

Results are appended to scratch/gate_ab/results.jsonl (resumable) and summarised to scratch/gate_ab/report.md.
Quarantine writes go to scratch/gate_ab/quarantine, NOT to _class_gen (the ground-truth set).
"""
from __future__ import annotations

import argparse
import json
import os
import random
import re
import sys
import threading
import time
import urllib.request
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

GEN = Path(__file__).resolve().parents[1]
ABDIR = GEN / "scratch" / "gate_ab"
ABDIR.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("BTS_HARNESS_V2", "1")
os.environ["BTSGEN_GENERATED_DIR"] = str(ABDIR / "quarantine")  # never pollute _class_gen

sys.path.insert(0, str(GEN))
sys.path.insert(0, str(GEN / "tools"))
import jev_gate_eval as G  # noqa: E402
import jev_op_eval as O  # noqa: E402
from btsgen import contract, ollama_mix, paths, pipeline  # noqa: E402
from btsgen.generator import OpenAICompatGenerator  # noqa: E402
from btsgen.validator import CardValidator  # noqa: E402

RESULTS = ABDIR / "results.jsonl"
REPORT = ABDIR / "report.md"
OR_BASE = "https://openrouter.ai/api/v1"
CARD_MODEL = "z-ai/glm-5.3"
FAMILY_SECTION = {"triggers": "## Triggers", "conditions": "## Conditions", "scaling": "## Structural mechanics",
                  "orbs": "## Orbs", "summons": "## Forged summons", "custom_status": "## Forged statuses",
                  "forge": "## Run-persistent Forge"}
ALWAYS_DROP = ("## The signature potion", "## Hybrid classes")  # class knobs, never a card's business
FAMILY_OPS = {"triggers": {"add_trigger"}, "orbs": {"channel_orb", "evoke", "gain_orb_slot"},
              "summons": {"summon", "summon_attack", "buff_summon", "shield_summon", "heal_summon", "sacrifice_summon"},
              "custom_status": {"apply_status_custom"}, "forge": {"forge", "spend_forge", "summon_blade", "blade_empower"}}
TOP_OPS_N = 8
_lock = threading.Lock()


# ------------------------------------------------------------------ briefs
def parse_brief(line: str) -> contract.Brief:
    m = re.match(r"type: (\w+), rarity: (\w+)(?:, target cost: (\d+) energy)?, theme: (.*)$", line.strip(), re.S)
    if not m:
        raise ValueError(line)
    return contract.Brief(card_type=m.group(1), rarity=m.group(2),
                          target_cost=int(m.group(3)) if m.group(3) else None, theme=m.group(4).strip())


def sample_cases(n: int, seed: int) -> list[dict]:
    cases = [c for c in G.load_cases(None) if "Reprint of" not in c["brief"] and "signature blade" not in c["brief"].lower()]
    rnd = random.Random(seed)
    rnd.shuffle(cases)
    # stratify a little: make sure the engine-heavy families are represented
    picked, seen = [], set()
    for fam, want in (("triggers", n // 4), ("conditions", n // 6), ("scaling", n // 6)):
        for c in cases:
            if len([p for p in picked if p["truth"][fam]]) >= want:
                break
            if c["truth"][fam] and c["id"] not in seen:
                picked.append(c)
                seen.add(c["id"])
    for c in cases:
        if len(picked) >= n:
            break
        if c["id"] not in seen:
            picked.append(c)
            seen.add(c["id"])
    return picked[:n]


# ------------------------------------------------------------------ gating decisions (from the Phase 0 caches)
def decisions(case: dict, sec_cache: dict, op_cache: dict, top_ops: list[str]) -> tuple[set[str], set[str]]:
    h = G.heuristic(case["brief"])
    j = sec_cache.get(case["id"], {}).get("probs", {})
    fams = {f for f in G.FAMILIES if h[f] >= 0.5 or j.get(f, -1) >= 0.15}
    jo = op_cache.get(case["id"], {}).get("probs", {})
    ops = set(O.ALWAYS) | set(top_ops[:TOP_OPS_N]) | {o for o, p in jo.items() if p >= 0.05}
    for f in fams:
        ops |= FAMILY_OPS.get(f, set())
    return fams, ops


def gated_prompt(full: str, fams: set[str], ops: set[str]) -> str:
    head, rest = full.split("# THE VOCABULARY (authoring reference)\n", 1)
    vocab, tail = rest.split("\n# THE JSON SCHEMA", 1)
    out_secs = []
    for sec in re.split(r"^(?=## )", vocab, flags=re.M):
        title = sec.splitlines()[0] if sec.strip() else ""
        if any(title.startswith(d) for d in ALWAYS_DROP):
            continue
        gated_fam = next((f for f, t in FAMILY_SECTION.items() if title.startswith(t)), None)
        if gated_fam and gated_fam not in fams:
            continue
        if title.startswith("## Effect ops"):
            keep = []
            for line in sec.splitlines():
                m = re.match(r"^\|\s*`([a-z_]+)`\s*\|", line)
                if m and m.group(1) not in ops:
                    continue
                keep.append(line)
            sec = "\n".join(keep) + "\n"
        out_secs.append(sec)
    return head + "# THE VOCABULARY (authoring reference)\n" + "".join(out_secs) + "\n# THE JSON SCHEMA" + tail


class _Shim:
    """contract_mod duck type with a fixed system prompt; everything else defers to btsgen.contract."""

    def __init__(self, system: str):
        self._system = system

    def system_prompt(self):
        return self._system

    def __getattr__(self, name):
        return getattr(contract, name)


# ------------------------------------------------------------------ one job
def _key() -> str:
    return G._key()


def cards_role_settings() -> dict:
    spec = ollama_mix.effective_role_map()["roles"]["cards"]
    fb = next(f for f in ollama_mix.DEFAULT_ROLE_MAP["fallbacks"] if f["name"] == "openrouter-glm53")
    return {"temperature": spec.get("temperature"), "response_format": spec.get("response_format"),
            "extra_body": ollama_mix._tier_extra_body(fb, "cards", spec), "model": fb["models"]["cards"]}


def run_job(arm: str, case: dict, system: str, settings: dict) -> dict:
    usage = {"input": 0, "output": 0, "cached": 0, "calls": 0}

    def on_usage(u):
        usage["calls"] += 1
        usage["input"] += int(u.get("prompt_tokens", 0) or 0)
        usage["output"] += int(u.get("completion_tokens", 0) or 0)
        det = u.get("prompt_tokens_details") or {}
        usage["cached"] += int(det.get("cached_tokens", 0) or 0)

    gen = OpenAICompatGenerator(OR_BASE, _key(), settings["model"], contract_mod=_Shim(system), max_tokens=4000,
                                timeout=180, response_format=settings["response_format"],
                                temperature=settings["temperature"], on_usage=on_usage,
                                extra_body=settings["extra_body"])
    validator = CardValidator()
    brief = parse_brief(case["brief"])
    t0 = time.time()
    try:
        res = pipeline.generate_card(brief, gen=gen, validator=validator)
    except Exception as e:  # transport etc.: record, don't kill the run
        return {"arm": arm, "id": case["id"], "brief": case["brief"], "ok": False, "error": f"{type(e).__name__}: {e}"[:300],
                "usage": usage, "secs": time.time() - t0, "system_chars": len(system)}
    card = res.card
    out = {"arm": arm, "id": case["id"], "brief": case["brief"], "ok": bool(res.ok), "attempts": res.attempts,
           "repaired": bool(res.repaired), "first_errors": len(res.all_errors) if res.attempts >= 2 or not res.ok else 0,
           "all_errors": res.all_errors[:6], "log": res.log, "usage": usage, "secs": time.time() - t0,
           "system_chars": len(system), "balance_repair": res.balance_repair}
    if card is not None:
        ops = O.card_ops(card)
        out.update({"card": card, "ops": sorted(ops), "score": getattr(res.result, "score", None),
                    "ceiling": validator.power_ceiling(card) if hasattr(validator, "power_ceiling") else None,
                    "warnings": list(getattr(res.result, "warnings", []) or [])[:6],
                    "type_match": str(card.get("type")) == brief.card_type,
                    "rarity_match": str(card.get("rarity")) == brief.rarity,
                    "cost_match": brief.target_cost is None or card.get("cost") == brief.target_cost})
    return out


# ------------------------------------------------------------------ judges
def _chat(model: str, system: str, user: str, key: str) -> str:
    body = json.dumps({"model": model, "temperature": 0, "response_format": {"type": "json_object"},
                       "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}).encode()
    req = urllib.request.Request(f"{OR_BASE}/chat/completions", data=body, method="POST",
                                 headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
    r = json.load(urllib.request.urlopen(req, timeout=120))
    return r["choices"][0]["message"]["content"]


def card_text(card: dict) -> str:
    keep = {k: card.get(k) for k in ("name", "type", "rarity", "cost", "target", "description", "effects", "upgrade",
                                     "exhaust", "retain", "innate", "ethereal") if card.get(k) not in (None, False, "")}
    return json.dumps(keep, separators=(",", ":"))


JUDGE_SYS = ("You are a senior Slay the Spire card designer reviewing two candidate implementations of the SAME "
             "card brief for a deckbuilder mod. Judge ONLY: (1) fidelity to the brief, (2) mechanical clarity and "
             "coherence, (3) reasonable balance for the stated cost and rarity, (4) how fun/distinct the design is. "
             "Do not reward length. Answer as JSON: {\"better\": \"1\"|\"2\"|\"tie\", \"fidelity_1\": 1-5, "
             "\"fidelity_2\": 1-5, \"quality_1\": 1-5, \"quality_2\": 1-5, \"reason\": \"<one sentence>\"}")


def llm_judge(model: str, brief: str, a: dict, b: dict, key: str) -> dict:
    """Two calls with swapped positions; a win only counts if both orders agree."""
    votes, scores = [], {"A": [], "B": []}
    for first, second, lab in ((a, b, ("A", "B")), (b, a, ("B", "A"))):
        user = f"BRIEF: {brief}\n\nCARD 1: {card_text(first)}\n\nCARD 2: {card_text(second)}"
        try:
            j = json.loads(_chat(model, JUDGE_SYS, user, key))
        except Exception as e:
            return {"error": str(e)[:200]}
        v = str(j.get("better", "tie"))
        votes.append(lab[0] if v == "1" else lab[1] if v == "2" else "tie")
        scores[lab[0]].append((j.get("fidelity_1"), j.get("quality_1")))
        scores[lab[1]].append((j.get("fidelity_2"), j.get("quality_2")))
    win = votes[0] if votes[0] == votes[1] else "tie"
    return {"votes": votes, "win": win, "scores": scores, "reason": j.get("reason", "")[:200]}


def jev_judge(brief: str, a: dict, b: dict, key: str) -> dict:
    state = {"brief": brief, "card_A": card_text(a), "card_B": card_text(b)}
    q = {"better": {"type": "choice", "instructions": "Which card is the better implementation of the brief for a "
                                                     "Slay-the-Spire-like game (fidelity, clarity, balance, fun)?",
                    "criteria": {"A": "card_A is better", "B": "card_B is better", "tie": "equal"}},
         "fidelity_A": {"type": "score", "instructions": "How faithfully does card_A implement the brief?",
                        "criteria": ["ignores the brief", "loosely related", "mostly faithful", "faithful", "exact"]},
         "fidelity_B": {"type": "score", "instructions": "How faithfully does card_B implement the brief?",
                        "criteria": ["ignores the brief", "loosely related", "mostly faithful", "faithful", "exact"]}}
    body = json.dumps({"model": G.MODEL, "state": state, "questions": q}).encode()
    req = urllib.request.Request(G.ENDPOINT, data=body, method="POST",
                                 headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
    try:
        r = json.load(urllib.request.urlopen(req, timeout=60))["answers"]
    except Exception as e:
        return {"error": str(e)[:200]}
    return {"win": r["better"]["choice"], "conf": r["better"].get("confidence"),
            "fid_A": r["fidelity_A"].get("score"), "fid_B": r["fidelity_B"].get("score")}


# ------------------------------------------------------------------ main
def summarise(rows: list[dict]) -> dict:
    by = {"A": [r for r in rows if r["arm"] == "A"], "B": [r for r in rows if r["arm"] == "B"]}
    out = {}
    for arm, rs in by.items():
        n = len(rs)
        ok = [r for r in rs if r.get("ok")]
        first = [r for r in ok if r.get("attempts") == 1]
        with_card = [r for r in rs if r.get("card")]
        over = [r for r in with_card if r.get("score") and r.get("ceiling") and r["score"] > r["ceiling"]]
        out[arm] = {
            "n": n, "ok": len(ok) / n if n else None, "valid_first_try": len(first) / n if n else None,
            "repaired": sum(1 for r in rs if r.get("repaired")) / n if n else None,
            "transport_errors": sum(1 for r in rs if r.get("error")),
            "type_match": sum(1 for r in with_card if r.get("type_match")) / len(with_card) if with_card else None,
            "rarity_match": sum(1 for r in with_card if r.get("rarity_match")) / len(with_card) if with_card else None,
            "cost_match": sum(1 for r in with_card if r.get("cost_match")) / len(with_card) if with_card else None,
            "over_ceiling_after_repair": len(over) / len(with_card) if with_card else None,
            "avg_ops": sum(len(r["ops"]) for r in with_card) / len(with_card) if with_card else None,
            "distinct_ops": len({o for r in with_card for o in r["ops"]}),
            "avg_input_tokens": sum(r["usage"]["input"] for r in rs) / n if n else None,
            "avg_cached_tokens": sum(r["usage"]["cached"] for r in rs) / n if n else None,
            "avg_calls": sum(r["usage"]["calls"] for r in rs) / n if n else None,
            "avg_system_chars": sum(r["system_chars"] for r in rs) / n if n else None,
            "avg_secs": sum(r["secs"] for r in rs) / n if n else None,
        }
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=40)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--judge", default="openai/gpt-5.4-mini")
    ap.add_argument("--no-judge", action="store_true")
    a = ap.parse_args()

    cases = sample_cases(a.n, a.seed)
    sec_cache, op_cache = G._cache(), O._cache()
    all_cases = O.load_cases(None)
    freq = Counter(o for c in all_cases for o in c["ops"])
    top_ops = [o for o, _ in freq.most_common() if o not in O.ALWAYS]
    full = contract.system_prompt()
    settings = cards_role_settings()
    print(f"cases {len(cases)}  model {settings['model']}  settings {settings}")
    print(f"full system prompt {len(full):,} chars")

    done = {}
    if RESULTS.exists():
        for line in RESULTS.read_text(encoding="utf-8").splitlines():
            try:
                r = json.loads(line)
                done[(r["arm"], r["id"])] = r
            except Exception:
                pass
    jobs = []
    gated_sizes = []
    for c in cases:
        fams, ops = decisions(c, sec_cache, op_cache, top_ops)
        gated = gated_prompt(full, fams, ops)
        gated_sizes.append(len(gated))
        c["gate"] = {"families": sorted(fams), "ops": sorted(ops), "gated_chars": len(gated)}
        for arm, system in (("A", full), ("B", gated)):
            if (arm, c["id"]) not in done:
                jobs.append((arm, c, system))
    print(f"gated prompt avg {sum(gated_sizes) / len(gated_sizes):,.0f} chars "
          f"({100 * (1 - sum(gated_sizes) / len(gated_sizes) / len(full)):.0f}% smaller); {len(jobs)} jobs to run")

    with ThreadPoolExecutor(max_workers=a.workers) as ex, RESULTS.open("a", encoding="utf-8") as fh:
        futs = {ex.submit(run_job, arm, c, system, settings): (arm, c["id"]) for arm, c, system in jobs}
        for i, f in enumerate(as_completed(futs), 1):
            r = f.result()
            with _lock:
                fh.write(json.dumps(r) + "\n")
                fh.flush()
            done[(r["arm"], r["id"])] = r
            print(f"  {i}/{len(jobs)} {r['arm']} {r['id'][:28]:28s} ok={r.get('ok')} attempts={r.get('attempts')} "
                  f"in={r['usage']['input']} cached={r['usage']['cached']} {r.get('error', '')[:60]}")

    rows = [done[(arm, c["id"])] for c in cases for arm in ("A", "B") if (arm, c["id"]) in done]
    summ = summarise(rows)
    print("\n== per-arm summary (A = full prompt, B = gated) ==")
    for k in summ["A"]:
        va, vb = summ["A"][k], summ["B"][k]
        fmt = lambda v: f"{v:,.3f}" if isinstance(v, float) else str(v)
        print(f"  {k:28s} A {fmt(va):>12s}   B {fmt(vb):>12s}")

    judge = {}
    if not a.no_judge:
        key = _key()
        pairs = [c for c in cases if done.get(("A", c["id"]), {}).get("card") and done.get(("B", c["id"]), {}).get("card")]
        print(f"\njudging {len(pairs)} pairs with {a.judge} (position-swapped x2) and Jev")
        llm_wins, jev_wins = Counter(), Counter()
        fid = {"A": [], "B": []}
        jfid = {"A": [], "B": []}
        for c in pairs:
            A, B = done[("A", c["id"])]["card"], done[("B", c["id"])]["card"]
            lj = llm_judge(a.judge, c["brief"], A, B, key)
            jj = jev_judge(c["brief"], A, B, key)
            judge[c["id"]] = {"llm": lj, "jev": jj}
            if "win" in lj:
                llm_wins[lj["win"]] += 1
                for arm in ("A", "B"):
                    fid[arm] += [s[0] for s in lj["scores"][arm] if isinstance(s[0], (int, float))]
            if "win" in jj:
                jev_wins[jj["win"]] += 1
                jfid["A"].append(jj.get("fid_A"))
                jfid["B"].append(jj.get("fid_B"))
        avg = lambda xs: sum(x for x in xs if x is not None) / max(1, len([x for x in xs if x is not None]))
        print(f"  LLM judge wins: {dict(llm_wins)}   avg fidelity A {avg(fid['A']):.2f}  B {avg(fid['B']):.2f}")
        print(f"  Jev judge wins: {dict(jev_wins)}   avg fidelity A {avg(jfid['A']):.2f}  B {avg(jfid['B']):.2f}")
        summ["judge"] = {"llm_wins": dict(llm_wins), "jev_wins": dict(jev_wins),
                         "llm_fidelity": {k: avg(v) for k, v in fid.items()}, "jev_fidelity": {k: avg(v) for k, v in jfid.items()}}

    # report for a human read
    lines = [f"# Gate A/B: full vs gated card prompt ({settings['model']}, n={len(cases)}, seed={a.seed})\n",
             "A = full prompt, B = gated (heuristic OR Jev sections, Jev OR top-8 op rows, schema whole).\n",
             "```json", json.dumps(summ, indent=1), "```\n"]
    for c in cases:
        ra, rb = done.get(("A", c["id"])), done.get(("B", c["id"]))
        lines.append(f"## {c['id']}\n**Brief:** {c['brief']}\n\n**Gate:** families {c['gate']['families']}, "
                     f"{len(c['gate']['ops'])} op rows, {c['gate']['gated_chars']:,} chars\n")
        for arm, r in (("A", ra), ("B", rb)):
            if not r:
                lines.append(f"- **{arm}:** (not run)")
                continue
            if r.get("card"):
                lines.append(f"- **{arm}** ok={r['ok']} attempts={r.get('attempts')} score={r.get('score')} "
                             f"ceiling={r.get('ceiling')} in={r['usage']['input']}: `{card_text(r['card'])}`")
            else:
                lines.append(f"- **{arm}** FAILED: {r.get('error') or '; '.join(r.get('all_errors', []))[:300]}")
        j = judge.get(c["id"])
        if j:
            lines.append(f"- judge: LLM {j['llm'].get('win')} ({j['llm'].get('reason', '')}); Jev {j['jev'].get('win')} "
                         f"conf={j['jev'].get('conf')}")
        lines.append("")
    REPORT.write_text("\n".join(lines), encoding="utf-8")
    (ABDIR / "summary.json").write_text(json.dumps(summ, indent=1), encoding="utf-8")
    print(f"\nwrote {REPORT}")


if __name__ == "__main__":
    main()
