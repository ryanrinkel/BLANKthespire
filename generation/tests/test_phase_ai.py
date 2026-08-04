"""Phase AI — op `graft_card` (VOCABULARY_GAPS #7, graft) — offline, no API key.

Run:  uv run python -m tests.test_phase_ai       (from generation/)
Exits nonzero on any failure. Exercises the mod-contract validator (a graft card with a valid same-class target +
a graft + when-condition ACCEPT; unknown card_id / basic / in-payload / graft+purge / graft+purge_card / over-cap
REJECT), the describe byte-match, the C# emit (CardId), census/catalog (metamorph BUILDABLE + graft featured),
and the transform-family cap (graft counts toward the ≤3 shared with transform_card). Mirrors the C# ForgedCards /
EffectRunner (GraftCard) / ForgedCharacters changes (vocab v39).

graft_card = the CHOOSE form of transform_card (as purge_card is the choose form of purge): when the card is
played, YOU pick a card in HAND and THAT picked card permanently becomes card_id for the rest of the run.
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

# A real card id that exists in the known corpus (a resolvable graft target for the per-card ref-integrity
# ACCEPT). Must live in the committed authored pool (mod/content/cards), not in local scratch quarantine.
_KNOWN_TARGET = "reckoning"


def check(cond: bool, msg: str) -> None:
    global _PASS, _FAIL
    if cond:
        _PASS += 1
    else:
        _FAIL += 1
        print(f"  FAIL: {msg}")


def _card(cid, effects, *, rarity="uncommon", ctype="skill", cost=1, target="self", upgrade=None):
    c = {"id": cid, "name": cid.replace("_", " ").title(), "type": ctype, "rarity": rarity,
         "cost": cost, "target": target, "source": "llm", "effects": effects}
    if upgrade is not None:
        c["upgrade"] = {"effects": upgrade}
    return c


def _graft(cid, target_id, **kw):
    """A card whose effects: a plain attack + a graft_card into target_id."""
    return _card(cid, [{"op": "damage", "amount": 6}, {"op": "graft_card", "card_id": target_id}],
                 ctype="attack", target="enemy", **kw)


def test_version() -> None:
    print("Phase AI vocab stamp is at least v39:")
    check(bts1.VOCAB_VERSION >= 39, f"bts1.VOCAB_VERSION must be >= 39 (Phase AI), got {bts1.VOCAB_VERSION}")


def test_accepts(v: CardValidator) -> None:
    print("a graft_card into a known same-class card validates:")
    # plain graft: pick a card, it becomes a strong known card.
    plain = _graft("ai_grafter", _KNOWN_TARGET)
    r = v.validate(plain)
    check(r.ok, f"a graft_card into a known same-class card should validate: {r.errors}")

    # graft + when-condition on the graft effect (a conditional prune-and-graft).
    gated = _card("ai_gated_graft", [
        {"op": "damage", "amount": 5},
        {"op": "graft_card", "card_id": _KNOWN_TARGET, "when": {"kind": "forged_ge", "value": 5}},
    ], ctype="attack", target="enemy")
    rg = v.validate(gated)
    check(rg.ok, f"a graft_card behind a when-condition should validate: {rg.errors}")

    # a lone graft card doesn't trip the transform-family cap.
    check(transform_warnings([plain]) == [], "a single graft card must NOT warn (well under the ≤3 cap)")


def test_rejects(v: CardValidator) -> None:
    print("invalid graft_card cards / sets are rejected:")

    def bad(card, why):
        check(not v.validate(card).ok, why)

    # unknown target
    bad(_card("ai_unknown", [{"op": "damage", "amount": 6},
                             {"op": "graft_card", "card_id": "definitely_not_a_real_card_xyz"}],
              ctype="attack", target="enemy"),
        "graft_card into an unknown card must reject")
    # basic card
    bad(_card("ai_basic", [{"op": "damage", "amount": 6},
                           {"op": "graft_card", "card_id": _KNOWN_TARGET}],
              ctype="attack", rarity="basic", target="enemy"),
        "graft_card on a BASIC card must reject")
    # graft + purge on one card
    bad(_card("ai_purge_conflict", [{"op": "damage", "amount": 6},
                                    {"op": "graft_card", "card_id": _KNOWN_TARGET},
                                    {"op": "purge"}], ctype="attack", target="enemy"),
        "graft_card + purge on one card must reject")
    # graft + purge_card on one card
    bad(_card("ai_purgecard_conflict", [{"op": "damage", "amount": 6},
                                        {"op": "graft_card", "card_id": _KNOWN_TARGET},
                                        {"op": "purge_card"}], ctype="attack", target="enemy"),
        "graft_card + purge_card on one card must reject")
    # two graft_card on one card
    bad(_card("ai_double", [{"op": "graft_card", "card_id": _KNOWN_TARGET},
                            {"op": "graft_card", "card_id": _KNOWN_TARGET}]),
        "two graft_card effects on one card must reject")
    # in a trigger payload (schema triggerEffect op enum excludes graft_card)
    bad(_card("ai_payload", [{"op": "add_trigger", "trigger": "turn_start",
                              "effects": [{"op": "graft_card", "card_id": _KNOWN_TARGET}]}]),
        "graft_card inside a trigger payload must reject")
    # card_id on a non-graft/non-transform/non-add_card op still rejects
    bad(_card("ai_strayid", [{"op": "block", "amount": 5, "card_id": _KNOWN_TARGET}]),
        "card_id on a stray op must reject")


def test_family_cap() -> None:
    print("graft_card counts toward the transform-family <=3-per-class cap (shared with transform_card):")
    # 4 transform-family cards (mix of graft + transform) → over-cap warning.
    g1 = _graft("ai_cap_g1", _KNOWN_TARGET)
    g2 = _graft("ai_cap_g2", _KNOWN_TARGET)
    t1 = _card("ai_cap_t1", [{"op": "damage", "amount": 6}, {"op": "transform_card", "card_id": _KNOWN_TARGET}],
               ctype="attack", target="enemy")
    t2 = _card("ai_cap_t2", [{"op": "damage", "amount": 6}, {"op": "transform_card", "card_id": _KNOWN_TARGET}],
               ctype="attack", target="enemy")
    check(any("too many transform" in w for w in transform_warnings([g1, g2, t1, t2])),
          "4 transform-family cards (graft + transform) in a class must warn (>3 cap)")
    # 3 graft cards alone → no over-cap warning (at the limit).
    g3 = _graft("ai_cap_g3", _KNOWN_TARGET)
    check(not any("too many transform" in w for w in transform_warnings([g1, g2, g3])),
          "3 graft cards must NOT warn (at the <=3 limit)")


def test_text_bytematch() -> None:
    print("describe() graft_card sentence byte-matches the C# ForgedCards.Describe wording:")
    got = cardgen.describe([{"op": "graft_card", "card_id": "molten_edge"}], "self")
    check(got == "Choose a card in your hand. It transforms into Molten Edge for the rest of the run.",
          f"graft_card describe mismatch: {got!r}")


def test_emit() -> None:
    print("effect_literal emits a named CardId arg:")
    lit = cardgen.effect_literal({"op": "graft_card", "card_id": "molten_edge"})
    check(lit == 'new EffectSpec("graft_card", CardId: "molten_edge")', f"emit mismatch: {lit!r}")


def test_census() -> None:
    print("census tallies graft_card + marks the card non-plain:")
    cc = census.walk_card(_graft("ai_c", _KNOWN_TARGET))
    check(cc.ops.get("graft_card", 0) == 1, "graft_card should be tallied in cc.ops")
    check(not cc.plain, "a graft_card card is a build-around, not plain")


def test_catalog_and_featured() -> None:
    print("catalog metamorph (BUILDABLE, declares graft_card) + graft featured entry exist:")
    cat = C.load_catalog()
    check("metamorph" in cat.by_id, "metamorph archetype must exist")
    e = cat.by_id["metamorph"]
    check("graft_card" in e.ops, "metamorph must declare the graft_card token")
    check(e.buildable, f"metamorph must be BUILDABLE (gap #7 done): {e.block_reasons}")
    check("graft_card" in C.live_vocab_tokens(), "graft_card must be a live token (VOCABULARY.md)")
    check("graft" in featured._BY_ID, "graft featured entry must exist")
    cc = census.walk_card(_graft("ai_feat", _KNOWN_TARGET))
    check(featured._BY_ID["graft"].detect(cc), "featured detect fires on a graft_card card")


def main() -> int:
    v = CardValidator()
    test_version()
    test_accepts(v)
    test_rejects(v)
    test_family_cap()
    test_text_bytematch()
    test_emit()
    test_census()
    test_catalog_and_featured()
    print(f"\n{_PASS} passed, {_FAIL} failed")
    return 1 if _FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
