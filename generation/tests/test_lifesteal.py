"""Self-healing discipline lint (Suck-U-Lator post-mortem, 2026-08-12) — offline, no API key.

Run:  uv run python -m tests.test_lifesteal       (from generation/)
Exits nonzero on any failure. Exercises the class-level `lifesteal_warnings`: the rarity floor
(a damage_dealt_unblocked heal on a basic/common), the sustain-density cap (>2 cards carrying
lifesteal or a per-turn heal engine), and the relic-stacking check (the starter relic also heals
in combat while the cards already sustain; a combat_end victory heal is exempt). The archetype
notes for reaper_lifesteal / iron_regrowth in DESIGN_HEURISTICS.md are the generative-side fix —
their presence is checked here too (contract.archetype_balance_note).
"""
from __future__ import annotations

import sys

# MUST repoint at the constrained mod contract BEFORE importing the btsgen modules that read paths.
from btsgen.class_forge import point_btsgen_at_mod_contract

point_btsgen_at_mod_contract()

from btsgen import contract                                   # noqa: E402
from btsgen.character_validator import lifesteal_warnings     # noqa: E402

_PASS = 0
_FAIL = 0


def check(cond: bool, msg: str) -> None:
    global _PASS, _FAIL
    if cond:
        _PASS += 1
    else:
        _FAIL += 1
        print(f"  FAIL: {msg}")


def _steal(i: int, rarity: str = "uncommon"):
    """A lifesteal attack: damage, then heal scaled by the unblocked damage (the Reaper pattern)."""
    return {"id": f"steal_{i}", "rarity": rarity, "type": "attack",
            "effects": [{"op": "damage", "amount": 8},
                        {"op": "heal", "amount": 1, "scale": "damage_dealt_unblocked"}]}


def _engine(i: int):
    """A per-turn heal power: add_trigger turn_end -> heal (the Industrial Intake pattern)."""
    return {"id": f"engine_{i}", "rarity": "rare", "type": "power",
            "effects": [{"op": "add_trigger", "trigger": "turn_end",
                         "effects": [{"op": "damage", "amount": 5}, {"op": "heal", "amount": 3}]}]}


def _plain(i: int):
    return {"id": f"plain_{i}", "rarity": "common", "type": "attack",
            "effects": [{"op": "damage", "amount": 6}]}


def _relic(trigger: str = "on_damage_dealt", heals: bool = True):
    effects = [{"op": "heal", "amount": 1}] if heals else [{"op": "draw", "amount": 1}]
    return {"id": "test_relic", "hooks": [{"trigger": trigger, "effects": effects}]}


def test_rarity_floor() -> None:
    print("lifesteal_warnings flags a damage_dealt_unblocked heal below uncommon:")
    check(len(lifesteal_warnings([_steal(0, "basic")])) == 1, "lifesteal on a basic should warn")
    check(len(lifesteal_warnings([_steal(0, "common")])) == 1, "lifesteal on a common should warn")
    check(lifesteal_warnings([_steal(0, "uncommon")]) == [], "lifesteal on an uncommon should NOT warn")
    check(lifesteal_warnings([_steal(0, "rare")]) == [], "lifesteal on a rare should NOT warn")
    # a flat (unscaled) heal is not lifesteal — no rarity floor
    flat = {"id": "flat", "rarity": "common", "type": "skill",
            "effects": [{"op": "heal", "amount": 3}]}
    check(lifesteal_warnings([flat]) == [], "a flat heal on a common should NOT trip the lifesteal floor")


def test_sustain_density() -> None:
    print("lifesteal_warnings flags >2 sustain cards (lifesteal + per-turn heal engines):")
    check(lifesteal_warnings([_steal(0), _steal(1), _plain(0)]) == [],
          "2 lifesteal cards should NOT warn")
    check(len(lifesteal_warnings([_steal(0), _steal(1), _steal(2)])) == 1,
          "3 lifesteal cards should warn")
    check(len(lifesteal_warnings([_steal(0), _steal(1), _engine(0)])) == 1,
          "2 lifesteal + a per-turn heal power (=3 sustain) should warn")
    check(lifesteal_warnings([_engine(0), _plain(0)]) == [],
          "a lone per-turn heal power should NOT warn")


def test_relic_stacking() -> None:
    print("lifesteal_warnings flags a relic that also heals in combat on top of card sustain:")
    check(len(lifesteal_warnings([_steal(0)], _relic("on_damage_dealt"))) == 1,
          "sustain cards + an on_damage_dealt heal relic should warn")
    check(lifesteal_warnings([_steal(0)], _relic("combat_end")) == [],
          "a combat_end victory-heal relic should NOT warn (the Burning Blood form)")
    check(lifesteal_warnings([_steal(0)], _relic("on_damage_dealt", heals=False)) == [],
          "a non-healing relic should NOT warn")
    check(lifesteal_warnings([_plain(0)], _relic("on_damage_dealt")) == [],
          "a heal relic with NO card sustain should NOT warn (nothing to stack on)")


def test_suck_u_lator_shape() -> None:
    print("the Suck-U-Lator shape (basic lifesteal, 8 sustain cards, heal relic) trips all three:")
    cards = [_steal(0, "basic")] + [_steal(i) for i in range(1, 7)] + [_engine(0)]
    ws = lifesteal_warnings(cards, _relic("on_damage_dealt"))
    check(len(ws) == 3, f"expected 3 warnings (floor + density + relic), got {len(ws)}: {ws}")


def test_archetype_notes() -> None:
    print("DESIGN_HEURISTICS carries the reaper_lifesteal / iron_regrowth archetype notes:")
    for aid in ("reaper_lifesteal", "iron_regrowth"):
        note = contract.archetype_balance_note(aid)
        check(bool(note), f"archetype-note for {aid} must exist")
        check("heal" in note.lower(), f"archetype-note for {aid} should talk about healing")


def main() -> int:
    test_rarity_floor()
    test_sustain_density()
    test_relic_stacking()
    test_suck_u_lator_shape()
    test_archetype_notes()
    print(f"\n{_PASS} passed, {_FAIL} failed")
    return 1 if _FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
