"""Phase AD — hp_lost_ge condition (VOCABULARY_GAPS #12, Ice Shatter) — offline, no API key.

Run:  uv run python -m tests.test_phase_ad       (from generation/)
Exits nonzero on any failure. Exercises the mod-contract validator (a damage effect gated on
when:hp_lost_ge accepts; value 0 / missing / >15 reject), cardgen.cond_phrase byte-match, condition_literal
emit, and the composed gap-#12 "Ice Shatter" card (self lose_hp fuel + gated payoff). Mirrors the C#
Conditions / HpLossTracker changes (vocab v34).
"""
from __future__ import annotations

import sys

from btsgen.class_forge import point_btsgen_at_mod_contract

point_btsgen_at_mod_contract()

from btsgen import bts1, cardgen        # noqa: E402
from btsgen.validator import CardValidator  # noqa: E402

_PASS = 0
_FAIL = 0


def check(cond: bool, msg: str) -> None:
    global _PASS, _FAIL
    if cond:
        _PASS += 1
    else:
        _FAIL += 1
        print(f"  FAIL: {msg}")


def _card(effects, up=None, **kw):
    base = {"id": "ad_test", "name": "AD Test", "type": "attack", "rarity": "uncommon",
            "cost": 1, "target": "enemy", "source": "llm", "effects": effects}
    base["upgrade"] = {"effects": up if up is not None else effects}
    base.update(kw)
    return base


def test_version() -> None:
    print("Phase AD vocab stamp is at least v34:")
    check(bts1.VOCAB_VERSION >= 34, f"bts1.VOCAB_VERSION must be >= 34 (Phase AD), got {bts1.VOCAB_VERSION}")


def test_accepts(v: CardValidator) -> None:
    print("valid hp_lost_ge-gated cards validate:")
    c = _card([{"op": "damage", "amount": 10, "when": {"kind": "hp_lost_ge", "value": 3}}])
    check(v.validate(c).ok, f"damage when hp_lost_ge should validate: {v.validate(c).errors}")
    # the gap-#12 "Ice Shatter" shape: self-fuel then gated payoff
    ice = _card([{"op": "lose_hp", "amount": 3},
                 {"op": "damage", "amount": 18, "when": {"kind": "hp_lost_ge", "value": 3}}])
    check(v.validate(ice).ok, f"Ice Shatter card should validate: {v.validate(ice).errors}")


def test_rejects(v: CardValidator) -> None:
    print("invalid hp_lost_ge conditions are rejected:")

    def bad(card, why):
        check(not v.validate(card).ok, why)

    bad(_card([{"op": "damage", "amount": 10, "when": {"kind": "hp_lost_ge", "value": 0}}]),
        "hp_lost_ge value 0 must reject")
    bad(_card([{"op": "damage", "amount": 10, "when": {"kind": "hp_lost_ge"}}]),
        "hp_lost_ge with no value must reject")
    bad(_card([{"op": "damage", "amount": 10, "when": {"kind": "hp_lost_ge", "value": 16}}]),
        "hp_lost_ge value 16 (>15) must reject")


def test_cond_phrase_bytematch() -> None:
    print("hp_lost_ge phrase byte-matches the C# Conditions.Phrase:")
    p = cardgen.cond_phrase({"kind": "hp_lost_ge", "value": 3})
    check(p == "you have lost 3 or more HP this turn", f"hp_lost_ge cond_phrase mismatch: {p!r}")
    # woven into a card sentence (the "if …" prefix, matching the C# When-weave)
    d = cardgen.describe([{"op": "damage", "amount": 18, "when": {"kind": "hp_lost_ge", "value": 3}}], "enemy")
    check(d == "Deal {Damage} damage if you have lost 3 or more HP this turn.", f"woven describe mismatch: {d!r}")


def test_condition_literal() -> None:
    print("hp_lost_ge emits the positional Condition literal:")
    lit = cardgen.condition_literal({"kind": "hp_lost_ge", "value": 3})
    check(lit == 'new Condition("hp_lost_ge", 3, null, false)', f"hp_lost_ge condition_literal mismatch: {lit!r}")


def main() -> int:
    v = CardValidator()
    test_version()
    test_accepts(v)
    test_rejects(v)
    test_cond_phrase_bytematch()
    test_condition_literal()
    print(f"\n{_PASS} passed, {_FAIL} failed")
    return 1 if _FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
