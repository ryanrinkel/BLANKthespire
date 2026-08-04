"""Phase Z — choose-a-card purge, the `purge_card` op (VOCABULARY_GAPS #19 choose) — offline, no API key.

Run:  uv run python -m tests.test_phase_z       (from generation/)
Exits nonzero on any failure. Exercises the mod-contract validator (the `purge_card` op accepts on a
skill/attack; forbidden on a BASIC card; NOT a trigger-payload op — the schema triggerEffect enum excludes
it), cardgen text/emit for `purge_card` (byte-matching the C# ForgedCards.Describe purge_card case + the
flag-op EffectSpec literal), the census tally, pricing (a modest build-around value), the class-level
`purge_warnings` counting purge_card toward the 1-3 limit, and the catalog `ascetic_purge` + featured
entries. Mirrors the C# ForgedCards / EffectRunner (PurgeChoose → CardSelectCmd.FromHand) / DataCard
changes (vocab v30).
"""
from __future__ import annotations

import sys

# MUST repoint at the constrained mod contract BEFORE importing the btsgen modules that read paths.
from btsgen.class_forge import point_btsgen_at_mod_contract

point_btsgen_at_mod_contract()

from btsgen import bts1, cardgen, census                 # noqa: E402
from btsgen.validator import CardValidator               # noqa: E402
from btsgen.character_validator import purge_warnings     # noqa: E402
from btsgen.frontend import catalog as C                 # noqa: E402
from btsgen import featured                              # noqa: E402

_PASS = 0
_FAIL = 0

_PURGE_CARD_TEXT = "Choose a card in your hand and Purge it. (Removed from your deck for the rest of the run.)"


def check(cond: bool, msg: str) -> None:
    global _PASS, _FAIL
    if cond:
        _PASS += 1
    else:
        _FAIL += 1
        print(f"  FAIL: {msg}")


def _card(effects, up=None, **kw):
    base = {"id": "z_test", "name": "Z Test", "type": "skill", "rarity": "uncommon",
            "cost": 1, "target": "self", "source": "llm", "effects": effects}
    base["upgrade"] = {"effects": up if up is not None else effects}
    base.update(kw)
    return base


def test_version() -> None:
    print("Phase Z vocab stamp is at least v30:")
    check(bts1.VOCAB_VERSION >= 30, f"bts1.VOCAB_VERSION must be >= 30 (Phase Z), got {bts1.VOCAB_VERSION}")


def test_accepts(v: CardValidator) -> None:
    print("valid purge_card cards validate:")
    # a skill whose whole point is to purge a chosen card
    sk = _card([{"op": "purge_card"}])
    check(v.validate(sk).ok, f"purge_card skill should validate: {v.validate(sk).errors}")
    # purge_card riding alongside a stat line (the card itself stays, so it can carry normal value)
    combo = _card([{"op": "block", "amount": 6}, {"op": "purge_card"}])
    check(v.validate(combo).ok, f"block + purge_card should validate: {v.validate(combo).errors}")
    # on an attack too
    atk = _card([{"op": "damage", "amount": 8}, {"op": "purge_card"}], **{"type": "attack", "target": "enemy"})
    check(v.validate(atk).ok, f"damage + purge_card attack should validate: {v.validate(atk).errors}")
    # purge_card + exhaust is allowed (they act on different cards — the played card exhausts, a chosen card purges)
    ex = _card([{"op": "block", "amount": 6}, {"op": "purge_card"}, {"op": "exhaust"}])
    check(v.validate(ex).ok, f"purge_card + exhaust should validate (different cards): {v.validate(ex).errors}")


def test_rejects(v: CardValidator) -> None:
    print("invalid purge_card cards are rejected:")

    def bad(card, why):
        check(not v.validate(card).ok, why)

    # purge_card on a BASIC card (deck-editing shouldn't be in the starting deck)
    bad(_card([{"op": "block", "amount": 6}, {"op": "purge_card"}], **{"rarity": "basic"}),
        "purge_card on a basic card must reject")
    # purge_card is not a trigger-payload op (a repeating pick would spam the UI / shred the deck)
    bad(_card([{"op": "add_trigger", "trigger": "turn_start", "effects": [{"op": "purge_card"}]}],
              **{"type": "power"}),
        "purge_card inside a trigger payload must reject")


def test_text_bytematch() -> None:
    print("purge_card card text byte-matches the C# ForgedCards.Describe purge_card case:")
    solo = cardgen.describe([{"op": "purge_card"}], "self")
    check(solo == _PURGE_CARD_TEXT, f"purge_card-only describe mismatch: {solo!r}")
    combo = cardgen.describe([{"op": "block", "amount": 6}, {"op": "purge_card"}], "self")
    check(combo == f"Gain {{Block}} Block.\n{_PURGE_CARD_TEXT}", f"block + purge_card describe mismatch: {combo!r}")


def test_emit() -> None:
    print("purge_card emits a plain flag-op EffectSpec literal (no amount):")
    lit = cardgen.effect_literal({"op": "purge_card"})
    check(lit == 'new EffectSpec("purge_card", 0)', f"purge_card emit mismatch: {lit!r}")


def test_census() -> None:
    print("census tallies the purge_card op as a non-plain build-around:")
    cc = census.walk_card(_card([{"op": "block", "amount": 6}, {"op": "purge_card"}]))
    check("purge_card" in cc.ops, "census should count the purge_card op")
    check(not cc.plain, "a purge_card card is NOT a plain stat line")


def test_pricing(v: CardValidator) -> None:
    print("purge_card carries a modest build-around value:")
    s = v.score_card(_card([{"op": "purge_card"}]))
    check(s > 0, f"purge_card should carry non-zero value (got {s})")


def test_class_warnings() -> None:
    print("purge_warnings counts purge_card toward the >3 deck-thinning limit:")
    def pc(i):
        return {"id": f"purgec_{i}", "effects": [{"op": "block", "amount": 6}, {"op": "purge_card"}]}
    check(purge_warnings([pc(i) for i in range(3)]) == [], "3 purge_card cards should NOT warn")
    check(len(purge_warnings([pc(i) for i in range(4)])) == 1, "4 purge_card cards should warn")
    # mixing purge + purge_card counts together toward the limit
    mixed = [{"id": "p1", "effects": [{"op": "damage", "amount": 9}, {"op": "purge"}]},
             {"id": "p2", "effects": [{"op": "damage", "amount": 9}, {"op": "purge"}]},
             {"id": "pc1", "effects": [{"op": "block", "amount": 6}, {"op": "purge_card"}]},
             {"id": "pc2", "effects": [{"op": "block", "amount": 6}, {"op": "purge_card"}]}]
    check(len(purge_warnings(mixed)) == 1, "2 purge + 2 purge_card (=4) should warn")


def test_catalog_and_featured() -> None:
    print("catalog ascetic_purge invites purge_card + featured detect fires on a purge_card card:")
    cat = C.load_catalog()
    e = cat.by_id["ascetic_purge"]
    check("purge_card" in e.ops, "ascetic_purge must declare the purge_card op/token")
    check("purge_card" in e.description, "ascetic_purge description should mention purge_card")
    cc = census.walk_card(_card([{"op": "block", "amount": 6}, {"op": "purge_card"}]))
    check(featured._BY_ID["ascetic_purge"].detect(cc), "featured detect fires on a purge_card card")


def main() -> int:
    v = CardValidator()
    test_version()
    test_accepts(v)
    test_rejects(v)
    test_text_bytematch()
    test_emit()
    test_census()
    test_pricing(v)
    test_class_warnings()
    test_catalog_and_featured()
    print(f"\n{_PASS} passed, {_FAIL} failed")
    return 1 if _FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
