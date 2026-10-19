"""LIVE probe for the Jev Phase 2 quality slots (docs/plans/JEV_EVALUATION_PLAN.md 3b). Costs a few hundredths of
a cent. Needs OPENROUTER_API_KEY (generation/.env is read via generator.load_env).

Fires ONE real request per built slot through the PRODUCTION code paths (so the questions are exactly what a forge
sends) and prints the RAW response next to what the parser made of it:
  1. nominate  coverage.sanitize_nominations: a misspelled key (`on_exhasut`) + a nonsense key (`zzz_quux`)
  2. nominate  BlueprintBuilder._snap_featured: a misspelled featured id (`reactive_playd`) + a nonsense one
  3. vocab     class_forge.triage_vocab_misses: op `apply_posion` (expect near:apply_status) + op `time_rewind`
  4. relic     class_forge.jev_relic_form: a canned Counter relic (every 3rd Attack -> 4 Block); expect Counter relic
  5. qa        class_forge.jev_card_qa: a canned card (2 nouls + the 5-level `score` question "power")
  6. stub      generator._jev_stub_verdict: an obvious stub `{"name": "", "effects": []}` (expect p high) and a real
               card reply (expect p low)

What to confirm (jev.py _parse_choice TODO): each choice answer carries `choice` + `probabilities` (+ `confidence`);
probabilities[choice] is the number the slots gate on.
What to confirm (jev.py parse_score TODO, request [5]): the `power` answer is {"type": "score", "score": <0-BASED
probability-weighted level index>, "legend", "probabilities": {"0".."4": p}}; parse_score reports score + 1.

Run:  uv run python tools/jev_slots_probe.py      (from generation/)
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from btsgen.class_forge import point_btsgen_at_mod_contract  # noqa: E402

point_btsgen_at_mod_contract()

from btsgen import class_forge, coverage, featured, jev  # noqa: E402
from btsgen.frontend.builder import BlueprintBuilder  # noqa: E402
from btsgen.generator import load_env  # noqa: E402

_real_post = jev.post
_total = {"cost": 0.0, "requests": 0}


def _recording_post(key, state, questions):
    t0 = time.time()
    resp = _real_post(key, state, questions)
    dt = time.time() - t0
    u = resp.get("usage") or {}
    _total["requests"] += 1
    _total["cost"] += float(u.get("cost") or 0)
    print(f"  request: {len(questions)} question(s), {len(json.dumps(state)) + len(json.dumps(questions))} chars "
          f"sent, {dt:.2f}s, input_tokens={u.get('input_tokens')}, cost=${u.get('cost')}")
    print(f"  model: {resp.get('model')}")
    for name, a in (resp.get("answers") or {}).items():
        probs = a.get("probabilities") if isinstance(a, dict) else None
        top = sorted(probs.items(), key=lambda kv: -kv[1])[:3] if isinstance(probs, dict) else None
        keys = sorted(a) if isinstance(a, dict) else type(a).__name__
        print(f"  raw[{name}]: keys={keys} choice={a.get('choice') if isinstance(a, dict) else None!r} "
              f"confidence={a.get('confidence') if isinstance(a, dict) else None} top3={top}"
              + (f" noul={a.get('noul')}" if isinstance(a, dict) and "noul" in a else "")
              + (f" score={a.get('score')} legend={a.get('legend')}" if isinstance(a, dict) and "score" in a
                 else ""))
    return resp


def main() -> int:
    load_env()
    if not jev.key():
        print("OPENROUTER_API_KEY is not set (env or generation/.env)")
        return 1
    os.environ["BTS_JEV_SLOTS"] = "nominate,vocab,relic,qa,stub"
    jev.post = _recording_post
    usage: list = []

    print("\n[1] nominate: coverage.sanitize_nominations")
    raw = {"reactive": ["on_exhasut", "attacked", "zzz_quux"]}
    out = coverage.sanitize_nominations(raw, on_usage=usage.append, log=lambda m: print("  log:", m))
    print(f"  in:  {raw}\n  out: {out}")

    print("\n[2] nominate: BlueprintBuilder._snap_featured")
    b = BlueprintBuilder(lambda *a, **k: None, catalog=None, on_event=lambda m: print("  log:", m.strip()), triad=False)
    b._usage_sink = usage.append
    fr = [{"id": "reactive_playd", "why": "probe"}, {"id": "quantum_tax"}]
    known = {f.id for f in featured.resolve([e["id"] for e in fr])}
    print(f"  in:  {fr}\n  out: {b._snap_featured(fr, known, featured)}")

    print("\n[3] vocab: class_forge.triage_vocab_misses")
    misses = [("op", "apply_posion"), ("op", "time_rewind")]
    t = class_forge.triage_vocab_misses(misses, "a card that poisons every enemy", on_usage=usage.append)
    for m in misses:
        print(f"  {m}: {t.get(m)}{class_forge._triage_suffix(t.get(m))}")

    print("\n[4] relic: class_forge.jev_relic_form")
    relic = {"id": "tally_stone", "name": "Tally Stone", "icon_emoji": "*",
             "description": "Every 3rd Attack you play, gain 4 Block.",
             "hooks": [{"trigger": "on_card_played", "card_type": "attack", "every_n": 3,
                        "effects": [{"op": "block", "amount": 4}]}]}
    print(f"  names parsed: {class_forge.relic_form_names()}")
    print(f"  out: {class_forge.jev_relic_form(relic, on_usage=usage.append)}")

    print("\n[5] qa: class_forge.jev_card_qa")
    card = {"id": "iron_hail", "name": "Iron Hail", "type": "attack", "rarity": "common", "cost": 1,
            "target": "enemy", "effects": [{"op": "damage", "amount": 4, "times": 2},
                                           {"op": "apply_status", "status": "vulnerable", "amount": 1}]}
    print(f"  text: {class_forge._card_text(card)!r}")
    print(f"  out: {class_forge.jev_card_qa(card, 'a hail of iron shards', on_usage=usage.append)}")

    print("\n[6] stub: generator._jev_stub_verdict")
    from btsgen.generator import _jev_stub_verdict, looks_like_stub
    for reply in ('{"name": "", "effects": []}', json.dumps(card)):
        print(f"  reply {reply[:60]!r}: {_jev_stub_verdict(reply, looks_like_stub(reply), usage.append)}")

    print(f"\nusage rows: {[(u['_role'], u['input_tokens'], u.get('cost')) for u in usage]}")
    print(f"total: {_total['requests']} request(s), ${_total['cost']:.6f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
