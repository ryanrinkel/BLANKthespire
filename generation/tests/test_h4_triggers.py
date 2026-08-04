"""Phase H4 reactive-trigger tests (VOCABULARY_GAPS #13 + #14) — offline, no API key.

Run:  uv run python -m tests.test_h4_triggers     (from generation/)
Exits nonzero on any failure. Exercises the mod-contract validator + cardgen text for the six
reactive triggers, the once_per_turn gate, and enemy-targeted payloads. Mirrors the C# ForgedCards
validation + TriggerSentence/TriggerFragment (vocab v18).
"""
from __future__ import annotations

import sys

# MUST repoint at the constrained mod contract BEFORE importing the btsgen modules that read paths.
from btsgen.class_forge import point_btsgen_at_mod_contract

point_btsgen_at_mod_contract()

from btsgen import cardgen                      # noqa: E402
from btsgen.validator import CardValidator      # noqa: E402

_PASS = 0
_FAIL = 0


def check(cond: bool, msg: str) -> None:
    global _PASS, _FAIL
    if cond:
        _PASS += 1
    else:
        _FAIL += 1
        print(f"  FAIL: {msg}")


def _card(effects: list[dict], **kw) -> dict:
    base = {"id": "h4_test", "name": "H4 Test", "type": "power", "rarity": "uncommon",
            "cost": 1, "target": "self", "source": "llm", "effects": effects}
    base.update(kw)
    return base


def _trig(trigger: str, payload: list[dict], **kw) -> dict:
    e = {"op": "add_trigger", "trigger": trigger, "effects": payload}
    e.update(kw)
    return e


def test_reactive_accepts(v: CardValidator) -> None:
    print("reactive triggers with valid payloads validate:")
    # each reactive kind with a self/orb payload
    for kind in ("on_exhaust", "on_card_played", "on_card_drawn", "on_damage_dealt",
                 "on_block_gained", "attacked"):
        card = _card([_trig(kind, [{"op": "block", "amount": 3}])])
        res = v.validate(card)
        check(res.ok, f"{kind} + self block should validate: {res.errors}")
    # once_per_turn on a reactive kind
    card = _card([_trig("on_card_drawn", [{"op": "draw", "amount": 1}], once_per_turn=True)])
    check(v.validate(card).ok, f"once_per_turn on on_card_drawn should validate: {v.validate(card).errors}")


def test_targeted_accepts(v: CardValidator) -> None:
    print("enemy-targeted payloads validate:")
    # Noxious Fumes: poison all enemies each turn
    fumes = _card([_trig("turn_start", [{"op": "apply_status", "status": "poison", "amount": 3,
                                         "target": "all_enemies"}])])
    check(v.validate(fumes).ok, f"turn_start poison-all should validate: {v.validate(fumes).errors}")
    # Combust: AoE damage each turn
    combust = _card([_trig("turn_end", [{"op": "damage", "amount": 5, "target": "all_enemies"}])])
    check(v.validate(combust).ok, f"turn_end AoE damage should validate: {v.validate(combust).errors}")
    # single-enemy targeted damage
    choke = _card([_trig("on_card_played", [{"op": "damage", "amount": 2, "target": "enemy"}],
                         once_per_turn=True)])
    check(v.validate(choke).ok, f"targeted single-enemy damage should validate: {v.validate(choke).errors}")


def test_rejects(v: CardValidator) -> None:
    print("H4 misuse is rejected:")

    def bad(card: dict, why: str) -> None:
        check(not v.validate(card).ok, why)

    # once_per_turn on a non-multi-fire trigger
    bad(_card([_trig("turn_start", [{"op": "block", "amount": 3}], once_per_turn=True)]),
        "once_per_turn on turn_start must be rejected")
    bad(_card([_trig("ripen", [{"op": "block", "amount": 3}], amount=2, once_per_turn=True)]),
        "once_per_turn on ripen must be rejected")
    # damage payload WITHOUT a target (schema requires target on damage)
    bad(_card([_trig("turn_end", [{"op": "damage", "amount": 5}])]),
        "untargeted trigger damage must be rejected")
    # self (untargeted) apply_status with a DEBUFF
    bad(_card([_trig("turn_end", [{"op": "apply_status", "status": "poison", "amount": 3}])]),
        "untargeted debuff apply_status must be rejected")
    # targeted apply_status with a SELF-BUFF
    bad(_card([_trig("turn_end", [{"op": "apply_status", "status": "strength", "amount": 2,
                                   "target": "enemy"}])]),
        "targeted self-buff apply_status must be rejected")
    # targeted effect that is also scaled
    bad(_card([_trig("turn_end", [{"op": "damage", "amount": 5, "target": "all_enemies",
                                   "scale": "cards_retained"}])]),
        "scaled targeted effect must be rejected")
    # unknown trigger kind (schema enum)
    bad(_card([_trig("on_potion_used", [{"op": "block", "amount": 3}])]),
        "unknown trigger kind must be rejected")
    # target on a card-level (non-trigger) effect (schema additionalProperties:false)
    bad(_card([{"op": "block", "amount": 3, "target": "enemy"}], type="skill"),
        "target on a card-level effect must be rejected")


def test_text(_v: CardValidator) -> None:
    print("synthesized card text matches the C# TriggerSentence/TriggerFragment:")

    def desc(effects: list[dict], target: str = "self") -> str:
        return cardgen.describe(effects, target)

    check(desc([_trig("on_exhaust", [{"op": "block", "amount": 3}])])
          == "Whenever a card is Exhausted, gain 3 Block.",
          "on_exhaust block sentence")
    check(desc([_trig("on_card_drawn", [{"op": "draw", "amount": 1}], once_per_turn=True)])
          == "Whenever you draw a card, draw 1 card(s) (once per turn).",
          "once_per_turn suffix")
    check(desc([_trig("turn_start", [{"op": "apply_status", "status": "poison", "amount": 3,
                                      "target": "all_enemies"}])])
          == "At the start of your turn, apply 3 Poison to ALL enemies.",
          "targeted AoE debuff sentence")
    check(desc([_trig("turn_end", [{"op": "damage", "amount": 2, "target": "enemy"}])])
          == "At the end of your turn, deal 2 damage.",
          "single-enemy targeted damage sentence")


def main() -> int:
    v = CardValidator()
    for t in (test_reactive_accepts, test_targeted_accepts, test_rejects, test_text):
        t(v)
    print(f"\n{_PASS} passed, {_FAIL} failed")
    return 1 if _FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
