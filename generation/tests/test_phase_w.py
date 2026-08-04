"""Phase W — self-purge, run-permanent deck-thinning (VOCABULARY_GAPS #19) — offline, no API key.

Run:  uv run python -m tests.test_phase_w       (from generation/)
Exits nonzero on any failure. Exercises the mod-contract validator (the `purge` flag-op accepts; purge ⊥
exhaust; purge forbidden on a BASIC card; purge is NOT a trigger-payload op), cardgen text/emit for `purge`
(byte-matching the C# ForgedCards.Describe purge case + the flag-op EffectSpec literal), the census tally,
the class-level `purge_warnings` (>3-per-class), and the catalog `ascetic_purge` + featured entries.
Mirrors the C# ForgedCards / EffectRunner / DataCard / CardSpec changes (vocab v28).
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

_PURGE_TEXT = "Purge. (Removed from your deck for the rest of the run.)"


def check(cond: bool, msg: str) -> None:
    global _PASS, _FAIL
    if cond:
        _PASS += 1
    else:
        _FAIL += 1
        print(f"  FAIL: {msg}")


def _card(effects, up=None, **kw):
    base = {"id": "w_test", "name": "W Test", "type": "attack", "rarity": "uncommon",
            "cost": 1, "target": "enemy", "source": "llm", "effects": effects}
    base["upgrade"] = {"effects": up if up is not None else effects}
    base.update(kw)
    return base


def test_version() -> None:
    print("Phase W vocab stamp is at least v28:")
    check(bts1.VOCAB_VERSION >= 28, f"bts1.VOCAB_VERSION must be >= 28 (Phase W), got {bts1.VOCAB_VERSION}")


def test_accepts(v: CardValidator) -> None:
    print("valid purge cards validate:")
    # a strong one-shot attack that purges itself
    atk = _card([{"op": "damage", "amount": 14}, {"op": "purge"}])
    check(v.validate(atk).ok, f"damage + purge attack should validate: {v.validate(atk).errors}")
    # a skill that purges itself
    sk = _card([{"op": "block", "amount": 10}, {"op": "purge"}], **{"type": "skill", "target": "self"})
    check(v.validate(sk).ok, f"block + purge skill should validate: {v.validate(sk).errors}")
    # purge that only appears in the upgrade list (the base doesn't purge, the upgraded card does). The upgrade
    # effect count must match the base's, so the base carries a placeholder second effect (draw).
    up = _card([{"op": "damage", "amount": 7}, {"op": "block", "amount": 7}],
               up=[{"op": "damage", "amount": 7}, {"op": "purge"}])
    check(v.validate(up).ok, f"purge only in upgrade should validate: {v.validate(up).errors}")


def test_rejects(v: CardValidator) -> None:
    print("invalid purge cards are rejected:")

    def bad(card, why):
        check(not v.validate(card).ok, why)

    # purge ⊥ exhaust on one card
    bad(_card([{"op": "damage", "amount": 10}, {"op": "purge"}, {"op": "exhaust"}]),
        "purge + exhaust on one card must reject")
    # exhaust living only in the upgrade still collides with a base purge
    bad(_card([{"op": "damage", "amount": 10}, {"op": "purge"}],
              up=[{"op": "damage", "amount": 10}, {"op": "purge"}, {"op": "exhaust"}]),
        "purge (base) + exhaust (upgrade) must reject")
    # purge on a BASIC card (would thin the class's starting deck / floors)
    bad(_card([{"op": "damage", "amount": 6}, {"op": "purge"}], **{"rarity": "basic"}),
        "purge on a basic card must reject")
    # purge is not a trigger-payload op (a trigger has no card to purge)
    bad(_card([{"op": "add_trigger", "trigger": "turn_start", "effects": [{"op": "purge"}]}],
              **{"type": "power", "target": "self"}),
        "purge inside a trigger payload must reject")


def test_text_bytematch() -> None:
    print("purge card text byte-matches the C# ForgedCards.Describe purge case:")
    d = cardgen.describe([{"op": "damage", "amount": 14}, {"op": "purge"}], "enemy")
    check(d == f"Deal {{Damage}} damage.\n{_PURGE_TEXT}", f"purge describe mismatch: {d!r}")
    solo = cardgen.describe([{"op": "purge"}], "self")
    check(solo == _PURGE_TEXT, f"purge-only describe mismatch: {solo!r}")


def test_emit() -> None:
    print("purge emits a plain flag-op EffectSpec literal (no amount):")
    lit = cardgen.effect_literal({"op": "purge"})
    check(lit == 'new EffectSpec("purge", 0)', f"purge emit mismatch: {lit!r}")


def test_census() -> None:
    print("census tallies the purge op:")
    cc = census.walk_card(_card([{"op": "damage", "amount": 14}, {"op": "purge"}]))
    check("purge" in cc.ops, "census should count the purge op")


def test_class_warnings() -> None:
    print("purge_warnings flags a class that over-uses purge (>3):")
    def pc(i):
        return {"id": f"purge_{i}", "effects": [{"op": "damage", "amount": 9}, {"op": "purge"}]}
    check(purge_warnings([pc(i) for i in range(3)]) == [], "3 purge cards should NOT warn")
    check(len(purge_warnings([pc(i) for i in range(4)])) == 1, "4 purge cards should warn")


def test_catalog_and_featured() -> None:
    print("catalog ascetic_purge entry + featured menu entry exist:")
    cat = C.load_catalog()
    check("ascetic_purge" in cat.by_id, "ascetic_purge archetype must exist in the catalog")
    e = cat.by_id["ascetic_purge"]
    check("purge" in e.ops, "ascetic_purge must declare the purge op/token")
    check(any("VOCABULARY_GAPS#19" in r for r in e.gap_refs), "ascetic_purge must gap_ref #19")
    check("ascetic_purge" in featured._BY_ID, "ascetic_purge featured menu entry must exist")
    cc = census.walk_card(_card([{"op": "damage", "amount": 14}, {"op": "purge"}]))
    check(featured._BY_ID["ascetic_purge"].detect(cc), "featured detect fires on a purge card")
    plain = census.walk_card(_card([{"op": "block", "amount": 5}], **{"type": "skill", "target": "self"}))
    check(not featured._BY_ID["ascetic_purge"].detect(plain), "featured detect does NOT fire on a plain card")


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
