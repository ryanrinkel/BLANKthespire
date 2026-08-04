"""Phase AF — op blade_empower (VOCABULARY_GAPS #41) — offline, no API key.

Run:  uv run python -m tests.test_phase_af       (from generation/)
Exits nonzero on any failure. Exercises the mod-contract validator (blade_empower on a skill accepts;
amount 1 / 4+ / on an attack / in a trigger payload reject), cardgen text/emit (byte-matching the C#
ForgedCards.Describe + the flag-amount EffectSpec literal), the census tally, the class-level
blade_empower_warnings (no forge income), the catalog forge_ramp token, and the scoring premium (empower >
plain forge income). Mirrors the C# ForgedBladeEmpowerPower / EffectRunner / DataCard / ForgedCards (v36).
"""
from __future__ import annotations

import sys

from btsgen.class_forge import point_btsgen_at_mod_contract

point_btsgen_at_mod_contract()

from btsgen import bts1, cardgen, census                       # noqa: E402
from btsgen.validator import CardValidator                     # noqa: E402
from btsgen.character_validator import blade_empower_warnings   # noqa: E402
from btsgen.frontend import catalog as C                       # noqa: E402

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
    base = {"id": "af_test", "name": "AF Test", "type": "skill", "rarity": "uncommon",
            "cost": 1, "target": "self", "source": "llm", "effects": effects}
    base["upgrade"] = {"effects": up if up is not None else effects}
    base.update(kw)
    return base


def test_version() -> None:
    print("Phase AF vocab stamp is at least v36:")
    check(bts1.VOCAB_VERSION >= 36, f"bts1.VOCAB_VERSION must be >= 36 (Phase AF), got {bts1.VOCAB_VERSION}")


def test_accepts(v: CardValidator) -> None:
    print("valid blade_empower cards validate:")
    x2 = _card([{"op": "blade_empower", "amount": 2}])
    check(v.validate(x2).ok, f"blade_empower x2 skill should validate: {v.validate(x2).errors}")
    x3 = _card([{"op": "blade_empower", "amount": 3}], **{"type": "power"})
    check(v.validate(x3).ok, f"blade_empower x3 power should validate: {v.validate(x3).errors}")


def test_rejects(v: CardValidator) -> None:
    print("invalid blade_empower cards are rejected:")

    def bad(card, why):
        check(not v.validate(card).ok, why)

    bad(_card([{"op": "blade_empower", "amount": 1}]), "blade_empower amount 1 must reject")
    bad(_card([{"op": "blade_empower", "amount": 4}]), "blade_empower amount 4 must reject")
    bad(_card([{"op": "blade_empower", "amount": 2}], **{"type": "attack", "target": "enemy"}),
        "blade_empower on an attack must reject")
    bad(_card([{"op": "add_trigger", "trigger": "turn_start", "effects": [{"op": "blade_empower", "amount": 2}]}],
              **{"type": "power"}),
        "blade_empower inside a trigger payload must reject")


def test_text_bytematch() -> None:
    print("blade_empower text byte-matches the C# ForgedCards.Describe:")
    d = cardgen.describe([{"op": "blade_empower", "amount": 2}], "self")
    check(d == "Your blade deals 2x damage this turn.", f"blade_empower describe mismatch: {d!r}")


def test_emit() -> None:
    print("blade_empower emits the plain amount EffectSpec literal:")
    lit = cardgen.effect_literal({"op": "blade_empower", "amount": 2})
    check(lit == 'new EffectSpec("blade_empower", 2)', f"blade_empower emit mismatch: {lit!r}")


def test_census() -> None:
    print("census tallies the blade_empower op (non-plain):")
    cc = census.walk_card(_card([{"op": "blade_empower", "amount": 2}]))
    check("blade_empower" in cc.ops, "census should count blade_empower")
    check(not cc.plain, "a blade_empower card must be non-plain")


def test_class_warnings() -> None:
    print("blade_empower_warnings flags a class with no forge income:")
    empower = {"id": "spike", "effects": [{"op": "blade_empower", "amount": 2}]}
    forger = {"id": "stoke", "effects": [{"op": "damage", "amount": 5}, {"op": "forge", "amount": 3}]}
    check(len(blade_empower_warnings([empower])) == 1, "blade_empower with no forge should warn")
    check(blade_empower_warnings([empower, forger]) == [], "blade_empower + forge income should NOT warn")


def test_scoring(v: CardValidator) -> None:
    print("blade_empower prices above plain forge income:")
    emp = v._score_effect({"op": "blade_empower", "amount": 2})
    frg = v._score_effect({"op": "forge", "amount": 2})
    check(emp > frg, f"blade_empower({emp}) should price above forge({frg})")


def test_catalog() -> None:
    print("catalog forge_ramp carries the blade_empower token (BUILDABLE):")
    cat = C.load_catalog()
    e = cat.by_id["forge_ramp"]
    check("blade_empower" in e.ops, "forge_ramp must declare the blade_empower token")
    check(e.buildable, f"forge_ramp must be BUILDABLE: {e.block_reasons}")
    check("blade_empower" in C.live_vocab_tokens(), "blade_empower must be a live token")


def main() -> int:
    v = CardValidator()
    test_version()
    test_accepts(v)
    test_rejects(v)
    test_text_bytematch()
    test_emit()
    test_census()
    test_class_warnings()
    test_scoring(v)
    test_catalog()
    print(f"\n{_PASS} passed, {_FAIL} failed")
    return 1 if _FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
