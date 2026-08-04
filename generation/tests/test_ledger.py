"""Offline tests for btsgen/ledger.py — the cross-forge usage ledger + recency signals (Phase N-4).

Run:  uv run python -m tests.test_ledger     (from generation/)
Exits nonzero on any failure. Covers: record_forge/read_window round-trip (census-derived fields), window
trimming, novelty-penalty math (empty/no-overlap/pair-repeat/recency-weighted/capped), corrupt + missing +
unwritable ledger tolerance (never raises, never breaks a forge), and the map/blueprint injection lines.
"""
from __future__ import annotations

import os
import sys
import tempfile

from btsgen.class_forge import point_btsgen_at_mod_contract

point_btsgen_at_mod_contract()

_TMP = tempfile.mkdtemp(prefix="bts_ledger_")
os.environ["BTS_FORGE_LEDGER"] = os.path.join(_TMP, "ledger.jsonl")

from btsgen import ledger  # noqa: E402  (import AFTER the env is set)

_PASS = 0
_FAIL = 0


def check(cond: bool, msg: str) -> None:
    global _PASS, _FAIL
    if cond:
        _PASS += 1
    else:
        _FAIL += 1
        print(f"  FAIL: {msg}")


def _bundle(name, effects):
    return {"kind": "class", "character": {"name": name},
            "cards": [{"id": "a", "name": "A", "type": "skill", "rarity": "common", "cost": 1,
                       "target": "self", "effects": effects}]}


def _bp(ids, orb_slots=0):
    return {"name": "BP", "archetypes": [{"id": i} for i in ids], "orb_slots": orb_slots}


def _fresh():
    p = ledger.ledger_path()
    if p.exists():
        p.unlink()


def test_round_trip() -> None:
    print("record_forge -> read_window round-trip with census-derived fields:")
    _fresh()
    bundle = _bundle("Venom Ma'am", [
        {"op": "damage", "amount": 6},
        {"op": "apply_status", "status": "poison", "amount": 3},
        {"op": "add_trigger", "trigger": "on_hp_lost", "effects": [{"op": "block", "amount": 3}]},
    ])
    ok = ledger.record_forge(bundle, _bp(["poison_attrition", "self_sacrifice"]))
    check(ok, "record_forge returns True on success")
    w = ledger.read_window()
    check(len(w) == 1, f"one entry read back, got {len(w)}")
    e = w[0]
    check(e["name"] == "Venom Ma'am", f"name recorded, got {e.get('name')}")
    check(e["archetype_ids"] == ["poison_attrition", "self_sacrifice"], f"ids recorded: {e.get('archetype_ids')}")
    check(e["class_kind"] == "normal", f"class_kind normal, got {e.get('class_kind')}")
    check("damage" in e["top_ops"] and "apply_status" in e["top_ops"], f"top_ops: {e.get('top_ops')}")
    check("poison" in e["statuses_used"], f"statuses: {e.get('statuses_used')}")
    check("on_hp_lost" in e["trigger_kinds"], f"triggers: {e.get('trigger_kinds')}")
    check(isinstance(e["ts"], float), "ts is a float")

    # orb class_kind derives from orb_slots
    ledger.record_forge(_bundle("Orbo", [{"op": "channel_orb", "orb": "lightning"}]), _bp(["orb_channel"], orb_slots=3))
    check(ledger.read_window()[-1]["class_kind"] == "orb", "orb_slots>0 -> class_kind orb")

    # the AUTHORITATIVE bp["archetype_ids"] (catalog ids) wins over bp["archetypes"][*].id (7B may echo names)
    bp = {"name": "X", "archetype_ids": ["counter_riposte", "debuff_expose"],
          "archetypes": [{"id": "Riposte"}, {"id": "Expose"}]}
    check(ledger._archetype_ids(bp) == ["counter_riposte", "debuff_expose"],
          f"canonical archetype_ids win over display-name ids: {ledger._archetype_ids(bp)}")
    # fallback to bp["archetypes"] when no canonical list is present
    check(ledger._archetype_ids({"archetypes": [{"id": "a"}, {"id": "b"}]}) == ["a", "b"],
          "falls back to bp['archetypes'] ids when no canonical list")


def test_window_trim() -> None:
    print("read_window trims to the last N entries:")
    _fresh()
    for i in range(15):
        ledger.record_forge(_bundle(f"C{i}", [{"op": "damage", "amount": 6}]), _bp([f"arch{i}", "block_bulwark"]))
    w = ledger.read_window(ledger.LEDGER_WINDOW)
    check(len(w) == ledger.LEDGER_WINDOW, f"trimmed to {ledger.LEDGER_WINDOW}, got {len(w)}")
    check(w[-1]["name"] == "C14", f"newest is last, got {w[-1]['name']}")
    check(w[0]["name"] == "C3", f"window starts at C3 (15-12), got {w[0]['name']}")


def test_penalty_math() -> None:
    print("pair_penalty: empty/no-overlap/repeat/recency-weighted/capped:")
    check(ledger.pair_penalty(["a", "b"], []) == 0.0, "empty window -> 0 penalty")

    win = [{"archetype_ids": ["poison_attrition", "self_sacrifice"]},
           {"archetype_ids": ["block_bulwark", "power_ramp"]}]
    check(ledger.pair_penalty(["orb_channel", "slot_machine"], win) == 0.0, "no overlap -> 0")
    p_pair = ledger.pair_penalty(["poison_attrition", "self_sacrifice"], win)
    check(p_pair > 0, f"an overused pair is penalized, got {p_pair}")
    p_one = ledger.pair_penalty(["poison_attrition", "orb_channel"], win)
    check(0 < p_one < p_pair, f"one shared archetype < full pair repeat: {p_one} vs {p_pair}")
    check(ledger.pair_penalty(["a", "b"], win) <= ledger._NOVELTY_MAX, "penalty never exceeds the cap")

    # recency: the SAME pair weighs more when it is the NEWEST entry than the oldest
    pair = ["poison_attrition", "self_sacrifice"]
    newest = [{"archetype_ids": ["x", "y"]}] * 3 + [{"archetype_ids": pair}]
    oldest = [{"archetype_ids": pair}] + [{"archetype_ids": ["x", "y"]}] * 3
    check(ledger.pair_penalty(pair, newest) > ledger.pair_penalty(pair, oldest),
          "a recent repeat penalizes more than an old one")

    # a pair repeated across MANY recent entries saturates at the cap
    many = [{"archetype_ids": pair}] * 12
    check(abs(ledger.pair_penalty(pair, many) - ledger._NOVELTY_MAX) < 1e-9, "heavy repetition hits the cap")


def test_corrupt_and_missing() -> None:
    print("corrupt / missing / unwritable ledger never raises:")
    # missing file
    _fresh()
    check(ledger.read_window() == [], "missing ledger -> empty window")

    # corrupt lines mixed with valid ones
    p = ledger.ledger_path()
    p.write_text('{"archetype_ids":["a","b"],"name":"good"}\nnot json at all\n{bad\n'
                 '{"archetype_ids":["c","d"],"name":"good2"}\n', encoding="utf-8")
    w = ledger.read_window()
    check(len(w) == 2 and [e["name"] for e in w] == ["good", "good2"], f"corrupt lines skipped: {w}")

    # totally corrupt file -> [] (no raise)
    p.write_text("\x00\x01 not text\n@@@@\n", encoding="utf-8")
    check(ledger.read_window() == [], "an all-garbage ledger -> empty window")

    # unwritable path -> record_forge returns False, never raises. Use a path whose PARENT is a regular file
    # (so record_forge's `path.parent.mkdir(...)` fails) — unwritable on both Linux and Windows (the old
    # hardcoded '/proc/...' path is only unwritable on Linux; Windows happily creates 'C:\proc\...').
    saved = os.environ.get("BTS_FORGE_LEDGER")
    blocker = os.path.join(_TMP, "blocker_file")
    with open(blocker, "w", encoding="utf-8") as _bf:
        _bf.write("not a directory")
    os.environ["BTS_FORGE_LEDGER"] = os.path.join(blocker, "child", "ledger.jsonl")
    try:
        check(ledger.record_forge(_bundle("X", [{"op": "damage", "amount": 6}]), _bp(["a", "b"])) is False,
              "unwritable ledger -> record_forge False, no crash")
    finally:
        os.environ["BTS_FORGE_LEDGER"] = saved


def test_injection_lines() -> None:
    print("map/blueprint injection lines summarize the overused window:")
    check(ledger.payload_line([]) == "", "empty window -> empty payload line")
    check(ledger.blueprint_status_line([]) == "", "empty window -> empty status line")

    win = [
        {"archetype_ids": ["poison_attrition", "self_sacrifice"], "top_ops": ["damage", "apply_status"],
         "statuses_used": ["vulnerable", "poison"]},
        {"archetype_ids": ["poison_attrition", "debuff_expose"], "top_ops": ["damage", "apply_status"],
         "statuses_used": ["vulnerable", "weak"]},
    ]
    pl = ledger.payload_line(win)
    check("RECENTLY OVERUSED" in pl and "poison_attrition" in pl, f"payload line names an overused pair: {pl}")
    check("damage" in pl and "ops" in pl, f"payload line names overused ops: {pl}")
    sl = ledger.blueprint_status_line(win)
    check("vulnerable" in sl, f"status line names the overused status: {sl}")
    check(all(ord(ch) < 128 for ch in pl + sl), "injection lines are ASCII (Windows console)")


def test_picker_novelty_term() -> None:
    print("the picker's _score drops by exactly the novelty penalty:")
    from btsgen.frontend import BlueprintBuilder, load_catalog
    from btsgen.frontend.dossier import Candidate, Dossier
    from btsgen.frontend.fakes import _StageFake

    b = BlueprintBuilder(lambda cm, *, max_tokens: _StageFake(cm), catalog=load_catalog(),
                         auto=True, gap_log_append=None)
    over = Candidate(name="Over", fantasy="rot", archetype_ids=["poison_attrition", "self_sacrifice"],
                     archetype_descs=["", ""], class_kind="normal", buildable=True)
    dossier = Dossier(theme="t")
    score_no_window = b._score(over, dossier, [over])  # default window is empty -> no penalty
    b._recency_window = [{"archetype_ids": ["poison_attrition", "self_sacrifice"]}] * 4
    score_with_window = b._score(over, dossier, [over])
    pen = b._novelty_penalty(over)
    check(pen > 0, f"an overused candidate gets a positive penalty, got {pen}")
    check(score_with_window < score_no_window, "recency lowers the score of an overused candidate")
    check(abs((score_no_window - score_with_window) - pen) < 1e-9,
          f"score drop equals the penalty ({score_no_window - score_with_window} vs {pen})")
    # a novel candidate is untouched
    novel = Candidate(name="Novel", fantasy="spin", archetype_ids=["orb_channel", "slot_machine"],
                      archetype_descs=["", ""], class_kind="orb", buildable=True)
    check(b._novelty_penalty(novel) == 0.0, "a candidate absent from the window has no penalty")
    # the penalty stays strictly below the fidelity weight (only ever a tie-breaker)
    from btsgen.frontend.builder import _FIDELITY_WEIGHT
    check(ledger._NOVELTY_MAX < _FIDELITY_WEIGHT, "novelty cap is strictly below the fidelity weight")


def main() -> int:
    test_round_trip()
    test_window_trim()
    test_penalty_math()
    test_corrupt_and_missing()
    test_injection_lines()
    test_picker_novelty_term()
    print(f"\n{_PASS} passed, {_FAIL} failed")
    return 1 if _FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
