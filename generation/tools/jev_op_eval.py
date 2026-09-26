"""Phase 0b of docs/plans/JEV_EVALUATION_PLAN.md: per-OP gating. Section gating (jev_gate_eval.py) leaves the
Effect-ops table (~4.25k tokens) and the schema's effect definition (~6.8k tokens) in every card prompt. Can
Jev read a brief and say which of the 41 ops the card will need, so the prompt keeps only those rows?

Question text per op = that op's own row in VOCABULARY.md's Effect-ops table (our vocabulary's words).
Ground truth = ops in the finished card. Baseline = a frequency prior (always include the top-N ops).

    uv run python tools/jev_op_eval.py [--batch 12] [--limit N]

Cached in scratch/jev_op_cache.jsonl. ~576 briefs x 41 questions: a few cents.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.request
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import jev_gate_eval as G  # noqa: E402

CACHE = G.GEN / "scratch" / "jev_op_cache.jsonl"
OUT = G.GEN / "scratch" / "jev_op_eval.json"
VOCAB = G.GEN.parent / "mod" / "contract" / "VOCABULARY.md"
SCHEMA = G.GEN.parent / "mod" / "contract" / "card.schema.json"
ALWAYS = {"damage", "block", "apply_status"}  # the core three: never gated


def op_rows() -> dict[str, str]:
    """op -> its Effect-ops table row text (fields + description), from VOCABULARY.md."""
    text = VOCAB.read_text(encoding="utf-8")
    sec = re.split(r"^(?=## )", text, flags=re.M)
    eff = next(s for s in sec if s.startswith("## Effect ops"))
    rows = {}
    for line in eff.splitlines():
        m = re.match(r"^\|\s*`([a-z_]+)`\s*\|(.*)$", line)
        if m:
            rows[m.group(1)] = re.sub(r"\s+", " ", m.group(2)).strip(" |")[:600]
    return rows


def schema_ops() -> set[str]:
    ops = set()

    def walk(o):
        if isinstance(o, dict):
            op = o.get("op")
            if isinstance(op, dict):
                if "const" in op:
                    ops.add(op["const"])
                ops.update(op.get("enum", []))
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)

    walk(json.loads(SCHEMA.read_text(encoding="utf-8")))
    return ops


def card_ops(card: dict) -> set[str]:
    ops = set()

    def walk(o):
        if isinstance(o, dict):
            if isinstance(o.get("op"), str):
                ops.add(o["op"])
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)

    walk(card)
    return ops


def load_cases(limit):
    cases = []
    for mf in sorted(G.SCRATCH.glob("*.meta.json")):
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
        cases.append({"id": mf.name[: -len(".meta.json")], "brief": m["brief"], "ops": sorted(card_ops(card))})
    return cases[:limit] if limit else cases


def _cache():
    out = {}
    if CACHE.exists():
        for line in CACHE.read_text(encoding="utf-8").splitlines():
            try:
                r = json.loads(line)
                out[r["id"]] = r
            except Exception:
                pass
    return out


def ask(key, batch, ops, rows, stats):
    state = {"context": "Card briefs for a Slay-the-Spire-like deckbuilder mod. Each card will be coded as JSON "
                        "from a closed effect vocabulary of named ops. For each card and op: will coding the card "
                        "as briefed use that op? Answer from the brief line only.",
             "cards": [{"card": i, "brief": c["brief"]} for i, c in enumerate(batch)]}
    q = {}
    for i, _ in enumerate(batch):
        for op in ops:
            q[f"c{i}_{op}"] = {"type": "noul", "instructions": f"Card {i}: will it use the op `{op}`? ({rows.get(op, '')})"}
    body = json.dumps({"model": G.MODEL, "state": state, "questions": q}).encode()
    req = urllib.request.Request(G.ENDPOINT, data=body, method="POST",
                                 headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
    t0 = time.time()
    resp = json.load(urllib.request.urlopen(req, timeout=180))
    u = resp.get("usage", {})
    stats["calls"] += 1
    stats["input_tokens"] += int(u.get("input_tokens", 0))
    stats["cost"] += float(u.get("cost", 0) or 0)
    stats["secs"] += time.time() - t0
    stats["max_questions"] = max(stats["max_questions"], len(q))
    ans = resp.get("answers", {})
    return [{"id": c["id"], "probs": {op: float(ans.get(f"c{i}_{op}", {}).get("noul", -1)) for op in ops}}
            for i, c in enumerate(batch)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--batch", type=int, default=12)
    ap.add_argument("--limit", type=int, default=None)
    a = ap.parse_args()
    rows = op_rows()
    ops = sorted(schema_ops() - ALWAYS)
    print(f"ops gated: {len(ops)} (always-on: {sorted(ALWAYS)}); rows found for {sum(o in rows for o in ops)}")
    cases = load_cases(a.limit)
    print("cases:", len(cases))
    freq = Counter(o for c in cases for o in c["ops"])

    key = G._key()
    cache = _cache()
    todo = [c for c in cases if c["id"] not in cache]
    stats = {"calls": 0, "input_tokens": 0, "cost": 0.0, "secs": 0.0, "max_questions": 0, "429s": 0}
    bs = a.batch
    i = 0
    with CACHE.open("a", encoding="utf-8") as fh:
        while i < len(todo):
            batch = todo[i:i + bs]
            try:
                rs = ask(key, batch, ops, rows, stats)
            except urllib.error.HTTPError as e:
                body = e.read()[:200].decode("utf-8", "replace")
                if e.code == 422 and bs > 1:
                    stats["422_at"] = stats.get("422_at") or len(batch) * len(ops)
                    bs = max(1, bs // 2)
                    print(f"  422 at {len(batch) * len(ops)} questions -> batch {bs}: {body[:100]}")
                    continue
                if e.code in (429, 529):
                    stats["429s"] += 1
                    time.sleep(min(60, 2 ** stats["429s"]))
                    continue
                raise
            for r in rs:
                cache[r["id"]] = r
                fh.write(json.dumps(r) + "\n")
            i += len(batch)
            print(f"  {i}/{len(todo)} calls={stats['calls']} cost=${stats['cost']:.4f}")

    # tokens per op row: Effect-ops section / 41 + schema effect def / 41 (chars/4)
    per_op_tokens = (17021 / 4 + 27000 / 4) / 41
    result = {"n": len(cases), "stats": stats, "thresholds": {}}
    print(f"\n~{per_op_tokens:.0f} prompt tokens per op row (vocab row + schema branch)")
    for th in (0.05, 0.10, 0.15, 0.25, 0.50):
        n = complete = inc_sum = 0
        tp = Counter(); fn = Counter(); fp = Counter()
        for c in cases:
            pr = cache.get(c["id"], {}).get("probs")
            if not pr:
                continue
            n += 1
            need = set(c["ops"]) - ALWAYS
            on = {o for o in ops if pr.get(o, -1) >= th}
            inc_sum += len(on)
            complete += need <= on
            for o in need & on: tp[o] += 1
            for o in need - on: fn[o] += 1
            for o in on - need: fp[o] += 1
        inc = inc_sum / n
        saved = (len(ops) - inc) * per_op_tokens
        worst = sorted(((fn[o] / (fn[o] + tp[o]), o, fn[o] + tp[o]) for o in ops if fn[o] + tp[o] >= 5), reverse=True)[:6]
        result["thresholds"][str(th)] = {"cards_complete": complete / n, "avg_ops_included": inc,
                                         "avg_tokens_saved": saved, "worst_recall": worst}
        print(f" th {th:.2f}: every needed op included {100 * complete / n:5.1f}%  avg ops kept {inc:4.1f}/{len(ops)}  "
              f"~{saved:,.0f} tokens saved   worst recall: " +
              ", ".join(f"{o} {100 * (1 - r):.0f}% (n={k})" for r, o, k in worst))
    # frequency prior baseline
    print("\nfrequency-prior baseline (always include the top-N ops):")
    ranked = [o for o, _ in freq.most_common() if o not in ALWAYS]
    for N in (6, 10, 15, 20):
        keep = set(ranked[:N])
        comp = sum((set(c["ops"]) - ALWAYS) <= keep for c in cases) / len(cases)
        print(f"  top {N:2d}: every needed op included {100 * comp:5.1f}%  ~{(len(ops) - N) * per_op_tokens:,.0f} tokens saved")
    OUT.write_text(json.dumps(result, indent=1), encoding="utf-8")
    print("wrote", OUT)


if __name__ == "__main__":
    main()
