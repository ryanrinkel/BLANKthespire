"""Phase AE — card tags + tag_cards_owned scalar (VOCABULARY_GAPS #25) — offline, no API key.

Run:  uv run python -m tests.test_phase_ae       (from generation/)
Exits nonzero on any failure. Exercises the mod-contract validator (a tagged card + a tag_cards_owned payoff
accept; >2 tags / uppercase tag / tag_cards_owned without a tag / a stray tag reject), cardgen text/emit
(byte-matching the C# ForgedCards.Describe + the Tag: named EffectSpec arg), the census scale tally, the
class-level tag_synergy_warnings (payoff tag on <2 cards), and the catalog strike_synergy + featured entries.
Mirrors the C# CardSpec / DataCard / EffectRunner / ForgedCards changes (vocab v35).
"""
from __future__ import annotations

import sys

from btsgen.class_forge import point_btsgen_at_mod_contract

point_btsgen_at_mod_contract()

from btsgen import bts1, cardgen, census                       # noqa: E402
from btsgen.validator import CardValidator                     # noqa: E402
from btsgen.character_validator import tag_synergy_warnings    # noqa: E402
from btsgen.frontend import catalog as C                       # noqa: E402
from btsgen import featured                                    # noqa: E402

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
    base = {"id": "ae_test", "name": "AE Test", "type": "attack", "rarity": "uncommon",
            "cost": 1, "target": "enemy", "source": "llm", "effects": effects}
    base["upgrade"] = {"effects": up if up is not None else effects}
    base.update(kw)
    return base


def test_version() -> None:
    print("Phase AE vocab stamp is at least v35:")
    check(bts1.VOCAB_VERSION >= 35, f"bts1.VOCAB_VERSION must be >= 35 (Phase AE), got {bts1.VOCAB_VERSION}")


def test_accepts(v: CardValidator) -> None:
    print("valid tagged / tag_cards_owned cards validate:")
    tagged = _card([{"op": "damage", "amount": 9}, {"op": "block", "amount": 4}], tags=["strike"])
    check(v.validate(tagged).ok, f"a tagged attack should validate: {v.validate(tagged).errors}")
    payoff = _card([{"op": "damage", "amount": 6, "scale": "tag_cards_owned", "tag": "strike"}], tags=["strike"])
    check(v.validate(payoff).ok, f"a tag_cards_owned payoff should validate: {v.validate(payoff).errors}")
    blk = _card([{"op": "block", "amount": 5, "scale": "tag_cards_owned", "tag": "guard"}],
                **{"type": "skill", "target": "self"})
    check(v.validate(blk).ok, f"a tag_cards_owned block payoff should validate: {v.validate(blk).errors}")


def test_rejects(v: CardValidator) -> None:
    print("invalid tags / tag_cards_owned are rejected:")

    def bad(card, why):
        check(not v.validate(card).ok, why)

    bad(_card([{"op": "damage", "amount": 6}], tags=["a", "b", "c"]), ">2 tags must reject")
    bad(_card([{"op": "damage", "amount": 6}], tags=["Strike"]), "uppercase tag must reject")
    bad(_card([{"op": "damage", "amount": 6, "scale": "tag_cards_owned"}]),
        "tag_cards_owned without a tag must reject")
    bad(_card([{"op": "damage", "amount": 6, "tag": "strike"}]),
        "a stray tag (no tag_cards_owned scale) must reject")
    bad(_card([{"op": "draw", "amount": 1, "scale": "tag_cards_owned", "tag": "strike"}]),
        "tag_cards_owned on draw must reject (damage/block only)")


def test_text_bytematch() -> None:
    print("tag_cards_owned text byte-matches the C# ForgedCards.Describe:")
    d = cardgen.describe([{"op": "damage", "amount": 6, "scale": "tag_cards_owned", "tag": "strike"}], "enemy")
    check(d == "Deal 6 damage, plus 1 per 'strike' card you own.", f"tag damage describe mismatch: {d!r}")
    b = cardgen.describe([{"op": "block", "amount": 5, "scale": "tag_cards_owned", "tag": "guard"}], "self")
    check(b == "Gain 5 Block, plus 1 per 'guard' card you own.", f"tag block describe mismatch: {b!r}")


def test_emit() -> None:
    print("tag_cards_owned emits the scaled EffectSpec with a Tag: named arg:")
    lit = cardgen.effect_literal({"op": "damage", "amount": 6, "scale": "tag_cards_owned", "tag": "strike"})
    check(lit == 'new EffectSpec("damage", 6, null, 1, "tag_cards_owned", Tag: "strike")',
          f"tag_cards_owned emit mismatch: {lit!r}")


def test_census() -> None:
    print("census tallies the tag_cards_owned scale:")
    cc = census.walk_card(_card([{"op": "damage", "amount": 6, "scale": "tag_cards_owned", "tag": "strike"}]))
    check("tag_cards_owned" in cc.scales, "census should count the tag_cards_owned scale")
    check(not cc.plain, "a tag_cards_owned card must be non-plain")


def test_class_warnings() -> None:
    print("tag_synergy_warnings flags a payoff tag present on <2 cards:")
    payoff = {"id": "p", "effects": [{"op": "damage", "amount": 6, "scale": "tag_cards_owned", "tag": "strike"}]}
    one_tagged = {"id": "s1", "effects": [{"op": "damage", "amount": 6}], "tags": ["strike"]}
    two_tagged = {"id": "s2", "effects": [{"op": "damage", "amount": 6}], "tags": ["strike"]}
    check(len(tag_synergy_warnings([payoff, one_tagged])) == 1, "payoff + 1 tagged card should warn")
    check(tag_synergy_warnings([payoff, one_tagged, two_tagged]) == [], "payoff + 2 tagged cards should NOT warn")


def test_catalog_and_featured() -> None:
    print("catalog strike_synergy (BUILDABLE) + featured entry exist:")
    cat = C.load_catalog()
    check("strike_synergy" in cat.by_id, "strike_synergy archetype must exist")
    e = cat.by_id["strike_synergy"]
    check("tag_cards_owned" in e.ops, "strike_synergy must declare the tag_cards_owned token")
    check(e.buildable, f"strike_synergy must be BUILDABLE (gap #25 done): {e.block_reasons}")
    check("tag_cards_owned" in C.live_vocab_tokens(), "tag_cards_owned must be a live token")
    check("strike_synergy" in featured._BY_ID, "strike_synergy featured entry must exist")
    cc = census.walk_card(_card([{"op": "damage", "amount": 6, "scale": "tag_cards_owned", "tag": "strike"}]))
    check(featured._BY_ID["strike_synergy"].detect(cc), "featured detect fires on a tag_cards_owned card")


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
