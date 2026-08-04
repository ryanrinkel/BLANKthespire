"""Phase AH — op `transform_card` (VOCABULARY_GAPS #35/#38) — offline, no API key.

Run:  uv run python -m tests.test_phase_ah       (from generation/)
Exits nonzero on any failure. Exercises the mod-contract validator (a two-card mode-swap pair + a conditional
rank-up transform ACCEPT; a chain / unknown card_id / basic / in-payload / transform+purge / >3-per-class
REJECT), the describe byte-match, the C# emit (CardId), census/catalog (metamorph BUILDABLE), and the featured
detect. Mirrors the C# ForgedCards / EffectRunner / ForgedCharacters changes (vocab v38).
"""
from __future__ import annotations

import sys

from btsgen.class_forge import point_btsgen_at_mod_contract

point_btsgen_at_mod_contract()

from btsgen import bts1, cardgen, census                        # noqa: E402
from btsgen.validator import CardValidator                      # noqa: E402
from btsgen.character_validator import transform_warnings       # noqa: E402
from btsgen.frontend import catalog as C                        # noqa: E402
from btsgen import featured                                     # noqa: E402

_PASS = 0
_FAIL = 0

# A real card id that exists in the known corpus (used as a resolvable transform target for the per-card
# ref-integrity ACCEPT). The target's OWN effects don't matter to the per-card validator (it checks existence
# only); the chain/mode-swap discrimination is set-level (transform_warnings), tested separately.
_KNOWN_TARGET = "reckoning"  # must live in the committed authored pool (mod/content/cards), not scratch


def check(cond: bool, msg: str) -> None:
    global _PASS, _FAIL
    if cond:
        _PASS += 1
    else:
        _FAIL += 1
        print(f"  FAIL: {msg}")


def _card(cid, effects, *, rarity="uncommon", ctype="skill", cost=1, target="self", upgrade=None, tags=None):
    c = {"id": cid, "name": cid.replace("_", " ").title(), "type": ctype, "rarity": rarity,
         "cost": cost, "target": target, "source": "llm", "effects": effects}
    if upgrade is not None:
        c["upgrade"] = {"effects": upgrade}
    if tags is not None:
        c["tags"] = tags
    return c


def _xform(cid, target_id, **kw):
    """A card whose effects: a plain attack + a transform_card into target_id."""
    return _card(cid, [{"op": "damage", "amount": 6}, {"op": "transform_card", "card_id": target_id}],
                 ctype="attack", target="enemy", **kw)


def test_version() -> None:
    print("Phase AH vocab stamp is at least v38:")
    check(bts1.VOCAB_VERSION >= 38, f"bts1.VOCAB_VERSION must be >= 38 (Phase AH), got {bts1.VOCAB_VERSION}")


def test_accepts(v: CardValidator) -> None:
    print("a transform_card into a known same-class card validates:")
    # rank-up: a weak attack that transforms into a strong known card once a condition holds.
    rankup = _card("ah_caterpillar", [
        {"op": "damage", "amount": 4},
        {"op": "transform_card", "card_id": _KNOWN_TARGET, "when": {"kind": "forged_ge", "value": 5}},
    ], ctype="attack", target="enemy")
    r = v.validate(rankup)
    check(r.ok, f"conditional rank-up transform should validate: {r.errors}")

    # mode-swap pair: two cards each transform into the OTHER. Each references the other's id (both known via
    # self_id + the corpus is irrelevant — we validate each with the other id present as a REAL known card is
    # not required for the pair's SET-level acceptance; per-card ref-integrity is checked against known_cards, so
    # use ids that resolve). We assert the SET-level transform_warnings accepts the pair (no chain).
    a = _xform("ah_mode_a", "ah_mode_b")
    b = _xform("ah_mode_b", "ah_mode_a")
    check(transform_warnings([a, b]) == [], "a two-card mode-swap pair A<->B must NOT warn (it's not a chain)")


def test_rejects(v: CardValidator) -> None:
    print("invalid transform_card cards / sets are rejected:")

    def bad(card, why):
        check(not v.validate(card).ok, why)

    # unknown target
    bad(_card("ah_unknown", [{"op": "damage", "amount": 6},
                             {"op": "transform_card", "card_id": "definitely_not_a_real_card_xyz"}],
              ctype="attack", target="enemy"),
        "transform_card into an unknown card must reject")
    # self-transform (card becomes itself)
    bad(_card("ah_selfie", [{"op": "damage", "amount": 6},
                            {"op": "transform_card", "card_id": "ah_selfie"}],
              ctype="attack", target="enemy"),
        "transform_card into itself must reject")
    # basic card
    bad(_card("ah_basic", [{"op": "damage", "amount": 6},
                           {"op": "transform_card", "card_id": _KNOWN_TARGET}],
              ctype="attack", rarity="basic", target="enemy"),
        "transform_card on a BASIC card must reject")
    # transform + purge on one card
    bad(_card("ah_conflict", [{"op": "damage", "amount": 6},
                              {"op": "transform_card", "card_id": _KNOWN_TARGET},
                              {"op": "purge"}], ctype="attack", target="enemy"),
        "transform_card + purge on one card must reject")
    # in a trigger payload (schema triggerEffect op enum excludes transform_card)
    bad(_card("ah_payload", [{"op": "add_trigger", "trigger": "turn_start",
                              "effects": [{"op": "transform_card", "card_id": _KNOWN_TARGET}]}]),
        "transform_card inside a trigger payload must reject")
    # card_id on a non-transform/non-add_card op
    bad(_card("ah_strayid", [{"op": "block", "amount": 5, "card_id": _KNOWN_TARGET}]),
        "card_id on a stray op must reject")

    # set-level: a CHAIN A->B->C is flagged (B transforms into C != A).
    a = _xform("ah_chain_a", "ah_chain_b")
    b = _xform("ah_chain_b", "ah_chain_c")
    c = _xform("ah_chain_c", "ah_chain_a")
    check(len(transform_warnings([a, b, c])) >= 1, "a transform chain A->B->C must warn (dead op at runtime)")

    # set-level: >3 transform cards per class warns.
    many = [_xform(f"ah_many_{i}", _KNOWN_TARGET) for i in range(4)]
    check(any("too many transform" in w for w in transform_warnings(many)),
          "4 transform cards in a class must warn (>3 cap)")


def test_text_bytematch() -> None:
    print("describe() transform_card sentence byte-matches the C# ForgedCards.Describe wording:")
    got = cardgen.describe([{"op": "transform_card", "card_id": "molten_edge"}], "self")
    check(got == "Transforms into Molten Edge for the rest of the run.",
          f"transform_card describe mismatch: {got!r}")


def test_emit() -> None:
    print("effect_literal emits a named CardId arg:")
    lit = cardgen.effect_literal({"op": "transform_card", "card_id": "molten_edge"})
    check(lit == 'new EffectSpec("transform_card", CardId: "molten_edge")', f"emit mismatch: {lit!r}")


def test_census() -> None:
    print("census tallies transform_card + marks the card non-plain:")
    cc = census.walk_card(_xform("ah_c", _KNOWN_TARGET))
    check(cc.ops.get("transform_card", 0) == 1, "transform_card should be tallied in cc.ops")
    check(not cc.plain, "a transform_card card is a build-around, not plain")


def test_catalog_and_featured() -> None:
    print("catalog metamorph (BUILDABLE) + featured entry exist:")
    cat = C.load_catalog()
    check("metamorph" in cat.by_id, "metamorph archetype must exist")
    e = cat.by_id["metamorph"]
    check("transform_card" in e.ops, "metamorph must declare the transform_card token")
    check(e.buildable, f"metamorph must be BUILDABLE (gaps #35/#38 done): {e.block_reasons}")
    check("transform_card" in C.live_vocab_tokens(), "transform_card must be a live token (VOCABULARY.md)")
    check("metamorph" in featured._BY_ID, "metamorph featured entry must exist")
    cc = census.walk_card(_xform("ah_feat", _KNOWN_TARGET))
    check(featured._BY_ID["metamorph"].detect(cc), "featured detect fires on a transform_card card")


def main() -> int:
    v = CardValidator()
    test_version()
    test_accepts(v)
    test_rejects(v)
    test_text_bytematch()
    test_emit()
    test_census()
    test_catalog_and_featured()
    print(f"\n{_PASS} passed, {_FAIL} failed")
    return 1 if _FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
