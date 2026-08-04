"""Phase AC — summon heal/shield ops (VOCABULARY_GAPS #2) — offline, no API key.

Run:  uv run python -m tests.test_phase_ac       (from generation/)
Exits nonzero on any failure. Exercises the mod-contract validator (heal_summon/shield_summon accept on a
summon-class skill + in a turn_start payload; reject amount 0/missing/over-cap and on a NON-summon class),
cardgen text/emit + trigger fragment (byte-matching the C# ForgedCards.Describe / TriggerFragment), the
census tally, and the class-level summon_support_warnings (medic-without-summon). Mirrors the C#
EffectRunner / TriggerRunner / ForgedCards changes (vocab v33).
"""
from __future__ import annotations

import sys

# MUST repoint at the constrained mod contract BEFORE importing the btsgen modules that read paths.
from btsgen.class_forge import point_btsgen_at_mod_contract

point_btsgen_at_mod_contract()

from btsgen import bts1, cardgen, census                          # noqa: E402
from btsgen.validator import CardValidator                        # noqa: E402
from btsgen.character_validator import summon_support_warnings    # noqa: E402
from btsgen.frontend import catalog as C                          # noqa: E402

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
    base = {"id": "ac_test", "name": "AC Test", "type": "skill", "rarity": "uncommon",
            "cost": 1, "target": "self", "source": "llm", "effects": effects}
    base["upgrade"] = {"effects": up if up is not None else effects}
    base.update(kw)
    return base


def test_version() -> None:
    print("Phase AC vocab stamp is at least v33:")
    check(bts1.VOCAB_VERSION >= 33, f"bts1.VOCAB_VERSION must be >= 33 (Phase AC), got {bts1.VOCAB_VERSION}")


def test_accepts(vs: CardValidator) -> None:
    print("valid summon heal/shield cards validate on a summon class:")
    heal = _card([{"op": "heal_summon", "amount": 5}])
    check(vs.validate(heal).ok, f"heal_summon skill should validate: {vs.validate(heal).errors}")
    shield = _card([{"op": "shield_summon", "amount": 8}])
    check(vs.validate(shield).ok, f"shield_summon skill should validate: {vs.validate(shield).errors}")
    # in a turn_start payload (the medic engine)
    eng = _card([{"op": "add_trigger", "trigger": "turn_start",
                  "effects": [{"op": "heal_summon", "amount": 3}]}], **{"type": "power"})
    check(vs.validate(eng).ok, f"turn_start heal_summon engine should validate: {vs.validate(eng).errors}")


def test_rejects(vs: CardValidator, vn: CardValidator) -> None:
    print("invalid summon heal/shield cards are rejected:")

    def bad(v, card, why):
        check(not v.validate(card).ok, why)

    # amount 0 / missing (schema minimum 1 / required)
    bad(vs, _card([{"op": "heal_summon", "amount": 0}]), "heal_summon amount 0 must reject")
    bad(vs, _card([{"op": "heal_summon"}]), "heal_summon amount missing must reject")
    # over the caps (heal 9, shield 12)
    bad(vs, _card([{"op": "heal_summon", "amount": 10}]), "heal_summon amount 10 (>9) must reject")
    bad(vs, _card([{"op": "shield_summon", "amount": 13}]), "shield_summon amount 13 (>12) must reject")
    # on a NON-summon class (no summon_pool context) — class-only
    bad(vn, _card([{"op": "heal_summon", "amount": 5}]), "heal_summon on a non-summon class must reject")
    bad(vn, _card([{"op": "shield_summon", "amount": 5}]), "shield_summon on a non-summon class must reject")


def test_text_bytematch() -> None:
    print("summon heal/shield text byte-matches the C# ForgedCards.Describe:")
    h = cardgen.describe([{"op": "heal_summon", "amount": 5}], "self")
    check(h == "Heal your summon 5 HP.", f"heal_summon describe mismatch: {h!r}")
    s = cardgen.describe([{"op": "shield_summon", "amount": 8}], "self")
    check(s == "Your summon gains 8 Block.", f"shield_summon describe mismatch: {s!r}")
    # trigger sentence (payload fragment) — byte-match ForgedCards.TriggerFragment
    eng = {"op": "add_trigger", "trigger": "turn_start", "effects": [{"op": "heal_summon", "amount": 3}]}
    ts = cardgen.trigger_sentence(eng)
    check(ts == "At the start of your turn, heal your summon 3 HP.", f"heal_summon trigger sentence mismatch: {ts!r}")


def test_emit() -> None:
    print("summon heal/shield emit the plain amount EffectSpec literal:")
    check(cardgen.effect_literal({"op": "heal_summon", "amount": 5}) == 'new EffectSpec("heal_summon", 5)',
          f"heal_summon emit mismatch: {cardgen.effect_literal({'op': 'heal_summon', 'amount': 5})!r}")
    check(cardgen.effect_literal({"op": "shield_summon", "amount": 8}) == 'new EffectSpec("shield_summon", 8)',
          f"shield_summon emit mismatch: {cardgen.effect_literal({'op': 'shield_summon', 'amount': 8})!r}")


def test_census() -> None:
    print("census tallies the summon heal/shield ops:")
    cc = census.walk_card(_card([{"op": "heal_summon", "amount": 5}, {"op": "shield_summon", "amount": 4}]))
    check("heal_summon" in cc.ops, "census should count heal_summon")
    check("shield_summon" in cc.ops, "census should count shield_summon")


def test_class_warnings() -> None:
    print("summon_support_warnings flags a medic card with no summon in the class:")
    medic = {"id": "medic", "effects": [{"op": "heal_summon", "amount": 4}]}
    summoner = {"id": "raise", "effects": [{"op": "summon", "summon_name": "wolf", "amount": 8}]}
    check(len(summon_support_warnings([medic])) == 1, "medic with no summon should warn")
    check(summon_support_warnings([medic, summoner]) == [], "medic + summon should NOT warn")


def test_catalog() -> None:
    print("catalog summon_swarm carries the heal/shield tokens (BUILDABLE):")
    cat = C.load_catalog()
    e = cat.by_id["summon_swarm"]
    check("heal_summon" in e.ops and "shield_summon" in e.ops, "summon_swarm must declare both medic tokens")
    check(e.buildable, f"summon_swarm must be BUILDABLE (gap #2 done): {e.block_reasons}")
    check("heal_summon" in C.live_vocab_tokens(), "heal_summon must appear in live_vocab_tokens()")


def main() -> int:
    vs = CardValidator(extra_summons={"wolf"})  # a summon-class context (declared a summon_pool)
    vn = CardValidator()                         # a non-summon class (no summon_pool)
    test_version()
    test_accepts(vs)
    test_rejects(vs, vn)
    test_text_bytematch()
    test_emit()
    test_census()
    test_class_warnings()
    test_catalog()
    print(f"\n{_PASS} passed, {_FAIL} failed")
    return 1 if _FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
