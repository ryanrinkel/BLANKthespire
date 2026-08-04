"""Phase AA — scry, the `scry` op (VOCABULARY_GAPS #17 R-2) — offline, no API key.

Run:  uv run python -m tests.test_phase_aa       (from generation/)
Exits nonzero on any failure. Exercises the mod-contract validator (the `scry` op accepts on a skill/attack
with an amount; requires amount; capped at 7; NOT a trigger-payload op — the schema triggerEffect enum
excludes it), cardgen text/emit for `scry` (byte-matching the C# ForgedCards.Describe scry case via the
{Scry} var + the EffectSpec literal), the census tally, pricing (a modest build-around value), and the
catalog `madness_discard` (now BUILDABLE, scry-aware) + featured `scry_filter`. Mirrors the C# ForgedCards
/ EffectRunner (Scry → CardSelectCmd.FromSimpleGrid → CardCmd.Discard → on_discard) / DataCard changes
(vocab v31).
"""
from __future__ import annotations

import sys

# MUST repoint at the constrained mod contract BEFORE importing the btsgen modules that read paths.
from btsgen.class_forge import point_btsgen_at_mod_contract

point_btsgen_at_mod_contract()

from btsgen import bts1, cardgen, census                 # noqa: E402
from btsgen.validator import CardValidator               # noqa: E402
from btsgen.frontend import catalog as C                 # noqa: E402
from btsgen import featured                              # noqa: E402

_PASS = 0
_FAIL = 0

_SCRY_TEXT = "Scry {Scry}. (Look at that many cards from the top of your draw pile and discard any.)"


def check(cond: bool, msg: str) -> None:
    global _PASS, _FAIL
    if cond:
        _PASS += 1
    else:
        _FAIL += 1
        print(f"  FAIL: {msg}")


def _card(effects, up=None, **kw):
    base = {"id": "aa_test", "name": "AA Test", "type": "skill", "rarity": "uncommon",
            "cost": 1, "target": "self", "source": "llm", "effects": effects}
    base["upgrade"] = {"effects": up if up is not None else effects}
    base.update(kw)
    return base


def test_version() -> None:
    print("Phase AA vocab stamp is at least v31:")
    check(bts1.VOCAB_VERSION >= 31, f"bts1.VOCAB_VERSION must be >= 31 (Phase AA), got {bts1.VOCAB_VERSION}")


def test_accepts(v: CardValidator) -> None:
    print("valid scry cards validate:")
    sc = _card([{"op": "scry", "amount": 3}])
    check(v.validate(sc).ok, f"scry 3 skill should validate: {v.validate(sc).errors}")
    # scry riding alongside a stat line (a cantrip that also filters)
    combo = _card([{"op": "block", "amount": 5}, {"op": "scry", "amount": 2}])
    check(v.validate(combo).ok, f"block + scry should validate: {v.validate(combo).errors}")
    # scry on an attack
    atk = _card([{"op": "damage", "amount": 6}, {"op": "scry", "amount": 2}], **{"type": "attack", "target": "enemy"})
    check(v.validate(atk).ok, f"damage + scry attack should validate: {v.validate(atk).errors}")
    # scry as discard fuel on a discard/on_discard card (the intended synergy)
    fuel = _card([{"op": "scry", "amount": 3},
                  {"op": "add_trigger", "trigger": "on_discard", "effects": [{"op": "block", "amount": 6}]}])
    check(v.validate(fuel).ok, f"scry + on_discard should validate: {v.validate(fuel).errors}")


def test_rejects(v: CardValidator) -> None:
    print("invalid scry cards are rejected:")

    def bad(card, why):
        check(not v.validate(card).ok, why)

    # scry needs an amount
    bad(_card([{"op": "scry"}]), "scry with no amount must reject")
    # scry amount capped at 7
    bad(_card([{"op": "scry", "amount": 8}]), "scry amount > 7 must reject")
    # scry is not a trigger-payload op (a repeating scry-UI every turn — card-only)
    bad(_card([{"op": "add_trigger", "trigger": "turn_start", "effects": [{"op": "scry", "amount": 2}]}],
              **{"type": "power"}),
        "scry inside a trigger payload must reject")


def test_text_bytematch() -> None:
    print("scry card text byte-matches the C# ForgedCards.Describe scry case:")
    solo = cardgen.describe([{"op": "scry", "amount": 3}], "self")
    check(solo == _SCRY_TEXT, f"scry-only describe mismatch: {solo!r}")
    combo = cardgen.describe([{"op": "block", "amount": 5}, {"op": "scry", "amount": 2}], "self")
    check(combo == f"Gain {{Block}} Block.\n{_SCRY_TEXT}", f"block + scry describe mismatch: {combo!r}")


def test_emit() -> None:
    print("scry emits an EffectSpec literal carrying its amount:")
    lit = cardgen.effect_literal({"op": "scry", "amount": 3})
    check(lit == 'new EffectSpec("scry", 3)', f"scry emit mismatch: {lit!r}")


def test_census() -> None:
    print("census tallies the scry op as a non-plain build-around:")
    cc = census.walk_card(_card([{"op": "block", "amount": 5}, {"op": "scry", "amount": 3}]))
    check("scry" in cc.ops, "census should count the scry op")
    check(not cc.plain, "a scry card is NOT a plain stat line")


def test_pricing(v: CardValidator) -> None:
    print("scry carries a modest build-around value that grows with N:")
    s2 = v.score_card(_card([{"op": "scry", "amount": 2}]))
    s5 = v.score_card(_card([{"op": "scry", "amount": 5}]))
    check(s2 > 0, f"scry should carry non-zero value (got {s2})")
    check(s5 > s2, f"scry 5 ({s5}) should price above scry 2 ({s2})")


def test_catalog_and_featured() -> None:
    print("catalog madness_discard is now BUILDABLE + scry-aware; featured scry_filter fires:")
    cat = C.load_catalog()
    e = cat.by_id["madness_discard"]
    check("scry" in e.ops, "madness_discard must declare the scry op/token")
    check(e.buildable, f"madness_discard must be BUILDABLE now (#17 done). block_reasons={e.block_reasons}")
    check("scry_filter" in featured._BY_ID, "scry_filter featured menu entry must exist")
    cc = census.walk_card(_card([{"op": "scry", "amount": 3}]))
    check(featured._BY_ID["scry_filter"].detect(cc), "featured detect fires on a scry card")


def main() -> int:
    v = CardValidator()
    test_version()
    test_accepts(v)
    test_rejects(v)
    test_text_bytematch()
    test_emit()
    test_census()
    test_pricing(v)
    test_catalog_and_featured()
    print(f"\n{_PASS} passed, {_FAIL} failed")
    return 1 if _FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
