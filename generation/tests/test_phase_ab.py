"""Phase AB — Corruption power (VOCABULARY_GAPS #20) — offline, no API key.

Run:  uv run python -m tests.test_phase_ab       (from generation/)
Exits nonzero on any failure. Exercises the mod-contract validator (the `corruption` flag-op accepts on a
power/skill; rejects on an attack, with an amount, twice on one card, and inside a trigger payload), cardgen
text/emit for `corruption` (byte-matching the C# ForgedCards.Describe two-sentence case + the generic flag-op
EffectSpec literal), the census tally + non-plain classification, the class-level `corruption_warnings`
(>1-per-class), and the catalog `exhaust_pyre` (corruption token, BUILDABLE) + featured entry.
Mirrors the C# ForgedCorruptionPower / ForgedCards / EffectRunner / DataCard changes (vocab v32).
"""
from __future__ import annotations

import sys

# MUST repoint at the constrained mod contract BEFORE importing the btsgen modules that read paths.
from btsgen.class_forge import point_btsgen_at_mod_contract

point_btsgen_at_mod_contract()

from btsgen import bts1, cardgen, census                      # noqa: E402
from btsgen.validator import CardValidator                    # noqa: E402
from btsgen.character_validator import corruption_warnings    # noqa: E402
from btsgen.frontend import catalog as C                      # noqa: E402
from btsgen import featured                                   # noqa: E402

_PASS = 0
_FAIL = 0

_CORRUPTION_TEXT = "Your Skills cost 0.\nYour Skills Exhaust when played."


def check(cond: bool, msg: str) -> None:
    global _PASS, _FAIL
    if cond:
        _PASS += 1
    else:
        _FAIL += 1
        print(f"  FAIL: {msg}")


def _card(effects, up=None, **kw):
    base = {"id": "ab_test", "name": "AB Test", "type": "power", "rarity": "uncommon",
            "cost": 1, "target": "self", "source": "llm", "effects": effects}
    base["upgrade"] = {"effects": up if up is not None else effects}
    base.update(kw)
    return base


def test_version() -> None:
    print("Phase AB vocab stamp is at least v32:")
    check(bts1.VOCAB_VERSION >= 32, f"bts1.VOCAB_VERSION must be >= 32 (Phase AB), got {bts1.VOCAB_VERSION}")


def test_accepts(v: CardValidator) -> None:
    print("valid corruption cards validate:")
    # a bare power card that just grants Corruption
    pw = _card([{"op": "corruption"}])
    check(v.validate(pw).ok, f"corruption power should validate: {v.validate(pw).errors}")
    # a skill that grants Corruption alongside a block effect
    sk = _card([{"op": "block", "amount": 8}, {"op": "corruption"}], **{"type": "skill"})
    check(v.validate(sk).ok, f"block + corruption skill should validate: {v.validate(sk).errors}")


def test_rejects(v: CardValidator) -> None:
    print("invalid corruption cards are rejected:")

    def bad(card, why):
        check(not v.validate(card).ok, why)

    # corruption on an attack card (the fantasy is "your Skills are free")
    bad(_card([{"op": "damage", "amount": 10}, {"op": "corruption"}], **{"type": "attack", "target": "enemy"}),
        "corruption on an attack card must reject")
    # corruption carrying an amount (it's a flag-op)
    bad(_card([{"op": "corruption", "amount": 2}]),
        "corruption with an amount must reject")
    # two corruption effects on one card
    bad(_card([{"op": "corruption"}, {"op": "corruption"}]),
        "two corruption effects on one card must reject")
    # corruption inside a trigger payload (a repeating binary-power grant is noise; card-only)
    bad(_card([{"op": "add_trigger", "trigger": "turn_start", "effects": [{"op": "corruption"}]}]),
        "corruption inside a trigger payload must reject")


def test_text_bytematch() -> None:
    print("corruption card text byte-matches the C# ForgedCards.Describe corruption case:")
    solo = cardgen.describe([{"op": "corruption"}], "self")
    check(solo == _CORRUPTION_TEXT, f"corruption-only describe mismatch: {solo!r}")
    combo = cardgen.describe([{"op": "block", "amount": 8}, {"op": "corruption"}], "self")
    check(combo == f"Gain {{Block}} Block.\n{_CORRUPTION_TEXT}", f"block + corruption describe mismatch: {combo!r}")


def test_emit() -> None:
    print("corruption emits a plain flag-op EffectSpec literal (no amount):")
    lit = cardgen.effect_literal({"op": "corruption"})
    check(lit == 'new EffectSpec("corruption", 0)', f"corruption emit mismatch: {lit!r}")


def test_census() -> None:
    print("census tallies the corruption op and classifies the card non-plain:")
    cc = census.walk_card(_card([{"op": "corruption"}]))
    check("corruption" in cc.ops, "census should count the corruption op")
    check(not cc.plain, "a corruption card must be classified non-plain")


def test_class_warnings() -> None:
    print("corruption_warnings flags a class with more than one corruption card:")
    def cc(i):
        return {"id": f"corrupt_{i}", "effects": [{"op": "corruption"}]}
    check(corruption_warnings([cc(0)]) == [], "1 corruption card should NOT warn")
    check(len(corruption_warnings([cc(0), cc(1)])) == 1, "2 corruption cards should warn")


def test_catalog_and_featured() -> None:
    print("catalog exhaust_pyre carries the corruption token (BUILDABLE) + featured entry exists:")
    cat = C.load_catalog()
    check("exhaust_pyre" in cat.by_id, "exhaust_pyre archetype must exist in the catalog")
    e = cat.by_id["exhaust_pyre"]
    check("corruption" in e.ops, "exhaust_pyre must declare the corruption op/token")
    check(e.buildable, f"exhaust_pyre must be BUILDABLE (gap #20 done + corruption live): {e.block_reasons}")
    check("corruption" in C.live_vocab_tokens(), "corruption must appear in live_vocab_tokens()")
    check("corruption_engine" in featured._BY_ID, "corruption_engine featured menu entry must exist")
    cc = census.walk_card(_card([{"op": "corruption"}]))
    check(featured._BY_ID["corruption_engine"].detect(cc), "featured detect fires on a corruption card")
    plain = census.walk_card(_card([{"op": "block", "amount": 5}], **{"type": "skill"}))
    check(not featured._BY_ID["corruption_engine"].detect(plain), "featured detect does NOT fire on a plain card")


def main() -> int:
    v = CardValidator()
    test_version()
    test_accepts(v)
    test_rejects(v)
    test_text_bytematch()
    test_emit()
    test_census()
    test_class_warnings()
    test_catalog_and_featured()
    print(f"\n{_PASS} passed, {_FAIL} failed")
    return 1 if _FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
