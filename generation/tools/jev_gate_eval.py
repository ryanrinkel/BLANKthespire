"""Phase 0 of docs/plans/JEV_EVALUATION_PLAN.md: can Jev (TypeSafe System One, via OpenRouter's Decisions
API) read a card BRIEF and say which VOCABULARY.md families the finished card will need?

Ground truth = the real-model cards in generation/scratch/_class_gen (their .meta.json carries the brief
line and the model). For each card we know which families its final JSON used. We ask Jev the same
questions from the brief alone, and a keyword heuristic as the no-vendor baseline, then report recall /
precision per family at several include thresholds plus the prompt tokens a gate would save.

    uv run python tools/jev_gate_eval.py [--batch 12] [--limit N] [--no-jev]

Jev answers are cached in scratch/jev_gate_cache.jsonl so re-runs cost nothing. Needs OPENROUTER_API_KEY
in generation/.env. A full run is ~576 briefs at a few hundred tokens each: well under $0.05.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

GEN = Path(__file__).resolve().parents[1]
SCRATCH = GEN / "scratch" / "_class_gen"
CACHE = GEN / "scratch" / "jev_gate_cache.jsonl"
OUT = GEN / "scratch" / "jev_gate_eval.json"
ENDPOINT = "https://openrouter.ai/api/alpha/decisions"
MODEL = "typesafe/jev-1.13"

# ---- families: what a gate would switch on/off, and the tokens each costs in the card prompt ----
# tokens = VOCABULARY.md section (~chars/4) + the matching card.schema.json branch (approx, see plan doc).
FAMILIES = {
    "triggers": {
        "tokens": 2160 + 2400,
        "ops": {"add_trigger"},
        "q": "Will coding this card need an `add_trigger` ongoing engine: a power/effect that fires every "
             "turn (turn_start / turn_end), fires ONCE after N turns (ripen: 'plant', 'after N turns', "
             "'matures'), or fires reactively whenever an event happens (whenever you play/draw/exhaust/"
             "discard a card, gain Block, lose HP, deal damage, or are attacked)?",
        "kw": r"whenever|at the (start|end) of (your|each|every) turn|each turn|every turn|after \d+ turns?|"
              r"ripen|matur|\bpower\b|when(ever)? you (play|draw|exhaust|discard|gain block|lose hp|are attacked)|"
              r"thorns|reflex|plant|engine|ongoing|for the rest of (the )?combat",
    },
    "conditions": {
        "tokens": 1270 + 1150,
        "keys": {"when"},
        "q": "Will coding this card need a conditional `when` gate that checks combat state before an effect "
             "fires: e.g. if the target has a status / block, if you have no block, if HP is below half, if "
             "you hold at least N cards, if it is turn N or later, if you retained this card, if enemies "
             "number at least N, if the draw pile is empty?",
        "kw": r"\bif\b|\bunless\b|\bwhile\b|only when|when (you|your|the target|the enemy|an enemy) (have|has|"
              r"hold|are|is)|below half|at least \d+|no block|has block|retained|held|debuffed|"
              r"vulnerable target|target (is|has)",
    },
    "scaling": {
        "tokens": 1500,
        "keys": {"scale", "hits", "times"},
        "q": "Will coding this card need multi-hit (deal X damage N times) or a SCALED amount: an amount "
             "that grows with a counter such as cards in hand, cards retained, cards played this turn, "
             "your Strength, your Forge, orbs, unspent energy, enemy count, or an X-cost?",
        "kw": r"\d+ times|twice|thrice|x times|multi[- ]?hit|\bhits?\b|per (card|enemy|orb|stack|turn|"
              r"forge|point)|for each|for every|equal to|scal|grows|plus your|based on|x-cost|\bx\b",
    },
    "orbs": {
        "tokens": 707,
        "ops": {"channel_orb", "evoke", "gain_orb_slot"},
        "q": "Will coding this card need orb ops (channel an orb, evoke, gain an orb slot: lightning / "
             "frost / dark / a custom orb)?",
        "kw": r"\borbs?\b|channel|evoke|lightning|frost|\bdark\b|orb slot|focus",
    },
    "summons": {
        "tokens": 979,
        "ops": {"summon", "summon_attack", "buff_summon", "shield_summon", "heal_summon", "sacrifice_summon"},
        "q": "Will coding this card need summon ops (summon a minion/companion, make it attack, buff, shield, "
             "heal or sacrifice it)?",
        "kw": r"summon|minion|companion|familiar|ally|creature|beast|spirit|golem|wolf|pet",
    },
    "custom_status": {
        "tokens": 746,
        "ops": {"apply_status_custom"},
        "q": "Will coding this card need this class's own FORGED custom status (a class-specific named "
             "stack such as Embers, Rust, Bloom, Chill: not the base statuses Vulnerable / Weak / Poison / "
             "Strength / Dexterity / Frail / Thorns / Artifact / Plated Armor / Metallicize / Regen)?",
        "kw": r"stacks? of|counter|custom|class status|\b(apply|gain|give|add)s? \d+ (?!strength|dexterity|"
              r"block|vulnerable|weak|poison|frail|thorns|artifact|plated|metallicize|regen|temp|damage|"
              r"energy)[a-z]+",
    },
    "forge": {
        "tokens": 183,
        "ops": {"forge", "spend_forge", "summon_blade", "blade_empower"},
        "q": "Will coding this card need Forge ops (forge N, spend Forge, summon or empower the signature "
             "blade)?",
        "kw": r"forge|blade|anvil|temper|ember|smith",
    },
}


# ---------------------------------------------------------------- ground truth
def truth(card: dict) -> dict[str, bool]:
    ops, keys = set(), set()

    def walk(o):
        if isinstance(o, dict):
            if isinstance(o.get("op"), str):
                ops.add(o["op"])
            keys.update(k for k in o.keys() if k in ("when", "scale", "hits", "times"))
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)

    walk(card)
    return {f: bool((spec.get("ops", set()) & ops) or (spec.get("keys", set()) & keys))
            for f, spec in FAMILIES.items()}


def load_cases(limit: int | None) -> list[dict]:
    cases = []
    for mf in sorted(SCRATCH.glob("*.meta.json")):
        try:
            m = json.loads(mf.read_text(encoding="utf-8"))
        except Exception:
            continue
        if m.get("model") in ("fake-offline", "stub") or not isinstance(m.get("brief"), str):
            continue
        cf = mf.with_name(mf.name[: -len(".meta.json")] + ".json")
        if not cf.exists():
            continue
        try:
            card = json.loads(cf.read_text(encoding="utf-8"))
        except Exception:
            continue
        if "effects" not in card:
            continue
        cases.append({"id": mf.name[: -len(".meta.json")], "brief": m["brief"], "model": m.get("model"),
                      "truth": truth(card)})
    return cases[:limit] if limit else cases


# ---------------------------------------------------------------- heuristic
def heuristic(brief: str) -> dict[str, float]:
    b = brief.lower()
    return {f: (1.0 if re.search(spec["kw"], b) else 0.0) for f, spec in FAMILIES.items()}


# ---------------------------------------------------------------- jev
def _key() -> str:
    env = (GEN / ".env").read_text(encoding="utf-8")
    m = re.search(r"^OPENROUTER_API_KEY=(.+)$", env, re.M)
    if not m:
        sys.exit("OPENROUTER_API_KEY missing from generation/.env")
    return m.group(1).strip().strip('"')


def _cache() -> dict[str, dict]:
    if not CACHE.exists():
        return {}
    out = {}
    for line in CACHE.read_text(encoding="utf-8").splitlines():
        try:
            r = json.loads(line)
            out[r["id"]] = r
        except Exception:
            pass
    return out


def jev_batch(key: str, batch: list[dict], stats: dict) -> list[dict]:
    """One Decisions request for a batch of briefs. Returns [{id, probs, ...}] or raises."""
    state = {"context": "Card briefs for a Slay-the-Spire-like deckbuilder mod. Each card will be coded as "
                        "JSON from a closed effect vocabulary. Answer per card, from its brief line only.",
             "cards": [{"card": i, "brief": c["brief"]} for i, c in enumerate(batch)]}
    questions = {}
    for i, _ in enumerate(batch):
        for f, spec in FAMILIES.items():
            questions[f"c{i}_{f}"] = {"type": "noul", "instructions": f"Card {i}: {spec['q']}"}
    body = json.dumps({"model": MODEL, "state": state, "questions": questions}).encode()
    req = urllib.request.Request(ENDPOINT, data=body, method="POST",
                                 headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
    t0 = time.time()
    resp = json.load(urllib.request.urlopen(req, timeout=120))
    dt = time.time() - t0
    usage = resp.get("usage", {})
    stats["calls"] += 1
    stats["input_tokens"] += int(usage.get("input_tokens", 0))
    stats["cost"] += float(usage.get("cost", 0) or 0)
    stats["secs"] += dt
    stats["max_questions"] = max(stats["max_questions"], len(questions))
    ans = resp.get("answers", {})
    out = []
    for i, c in enumerate(batch):
        probs = {f: float(ans.get(f"c{i}_{f}", {}).get("noul", -1)) for f in FAMILIES}
        out.append({"id": c["id"], "probs": probs, "model": resp.get("model"), "secs": dt / len(batch)})
    return out


def run_jev(cases: list[dict], batch_size: int, stats: dict) -> dict[str, dict]:
    key = _key()
    cache = _cache()
    todo = [c for c in cases if c["id"] not in cache]
    print(f"jev: {len(cache)} cached, {len(todo)} to ask, batch {batch_size}")
    i = 0
    with CACHE.open("a", encoding="utf-8") as fh:
        while i < len(todo):
            batch = todo[i:i + batch_size]
            try:
                rows = jev_batch(key, batch, stats)
            except urllib.error.HTTPError as e:
                body = e.read()[:300].decode("utf-8", "replace")
                if e.code == 422 and batch_size > 1:
                    batch_size = max(1, batch_size // 2)
                    print(f"  422 at {len(batch)} briefs ({len(batch) * len(FAMILIES)} questions): {body[:120]} "
                          f"-> batch {batch_size}")
                    stats["422_at"] = stats.get("422_at") or len(batch) * len(FAMILIES)
                    continue
                if e.code in (429, 529):
                    stats["429s"] += 1
                    wait = min(60, 2 ** stats["429s"])
                    print(f"  {e.code}, sleeping {wait}s: {body[:120]}")
                    time.sleep(wait)
                    continue
                print(f"  HTTP {e.code}: {body}")
                raise
            for r in rows:
                cache[r["id"]] = r
                fh.write(json.dumps(r) + "\n")
            i += len(batch)
            print(f"  {i}/{len(todo)}  calls={stats['calls']} cost=${stats['cost']:.4f}")
    return cache


# ---------------------------------------------------------------- scoring
def score(cases: list[dict], preds: dict[str, dict], thresholds: list[float]) -> dict:
    """Per family and threshold: recall (needed & included / needed), precision, include rate.
    Per card: 'complete' = every needed family included; tokens saved vs. always-include."""
    total_tokens = sum(s["tokens"] for s in FAMILIES.values())
    report = {}
    for th in thresholds:
        fam = {}
        for f in FAMILIES:
            tp = fp = fn = inc = 0
            for c in cases:
                p = preds.get(c["id"], {}).get("probs", {}).get(f, -1)
                if p < 0:
                    continue
                need, on = c["truth"][f], p >= th
                inc += on
                tp += need and on
                fp += (not need) and on
                fn += need and (not on)
            fam[f] = {"recall": tp / (tp + fn) if tp + fn else None, "precision": tp / (tp + fp) if tp + fp else None,
                      "include_rate": inc / len(cases), "needed": tp + fn}
        complete = saved = n = 0
        for c in cases:
            pr = preds.get(c["id"], {}).get("probs")
            if not pr or min(pr.values()) < 0:
                continue
            n += 1
            ok = all((pr[f] >= th) or (not c["truth"][f]) for f in FAMILIES)
            complete += ok
            saved += sum(FAMILIES[f]["tokens"] for f in FAMILIES if pr[f] < th)
        report[str(th)] = {"families": fam, "cards_complete": complete / n if n else None,
                           "avg_tokens_saved": saved / n if n else None, "gateable_tokens": total_tokens, "n": n}
    return report


def print_report(name: str, rep: dict) -> None:
    print(f"\n== {name} ==")
    for th, r in rep.items():
        print(f" threshold {th}: cards with every needed family included {100 * (r['cards_complete'] or 0):.1f}%, "
              f"avg tokens saved {r['avg_tokens_saved'] or 0:,.0f} of {r['gateable_tokens']:,} gateable  (n={r['n']})")
        for f, s in r["families"].items():
            rc = "  -  " if s["recall"] is None else f"{100 * s['recall']:5.1f}"
            pc = "  -  " if s["precision"] is None else f"{100 * s['precision']:5.1f}"
            print(f"    {f:14s} needed {s['needed']:3d}  recall {rc}%  precision {pc}%  included {100 * s['include_rate']:5.1f}%")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--batch", type=int, default=12)
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--no-jev", action="store_true")
    args = ap.parse_args()
    cases = load_cases(args.limit)
    print(f"cases: {len(cases)} real-model cards with briefs")
    need = {f: sum(c["truth"][f] for c in cases) for f in FAMILIES}
    print("ground truth (cards needing each family):", need)

    heur = {c["id"]: {"probs": heuristic(c["brief"])} for c in cases}
    rep_h = score(cases, heur, [0.5])
    print_report("keyword heuristic", rep_h)

    result = {"n": len(cases), "need": need, "heuristic": rep_h}
    if not args.no_jev:
        stats = {"calls": 0, "input_tokens": 0, "cost": 0.0, "secs": 0.0, "429s": 0, "max_questions": 0}
        preds = run_jev(cases, args.batch, stats)
        rep_j = score(cases, preds, [0.05, 0.10, 0.15, 0.25, 0.50])
        print_report("jev", rep_j)
        print(f"\njev usage this run: {stats}")
        result["jev"] = rep_j
        result["jev_stats"] = stats
        # the misses at 0.15, for reading
        misses = []
        for c in cases:
            pr = preds.get(c["id"], {}).get("probs", {})
            for f in FAMILIES:
                if c["truth"][f] and 0 <= pr.get(f, -1) < 0.15:
                    misses.append({"id": c["id"], "family": f, "p": pr[f], "brief": c["brief"][:160]})
        result["jev_misses_at_0.15"] = misses
        print(f"\njev misses at 0.15: {len(misses)} (first 12)")
        for m in misses[:12]:
            print(f"  {m['family']:14s} p={m['p']:.2f}  {m['brief']}")
    OUT.write_text(json.dumps(result, indent=1), encoding="utf-8")
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()
