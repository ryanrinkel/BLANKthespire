"""Phase X — player-pick upgrade, the CHOOSE scope on upgrade_card (VOCABULARY_GAPS #18 player-pick) — offline.

Run:  uv run python -m tests.test_phase_x       (from generation/)
Exits nonzero on any failure. Exercises the mod-contract validator (the new `choose` scope accepted at card
level, rejected inside a repeating trigger payload), cardgen text/emit for `upgrade_card cards:choose`
(byte-matching the C# ForgedCards.UpgradeSentence "a card of your choice"), pricing (choose between random
and all), the census tally, and the refreshed catalog/featured guidance. Mirrors the C# ForgedCards /
EffectRunner (UpgradeChoose → CardSelectCmd.FromHandForUpgrade) / DataCard / CardSpec changes (vocab v29).
"""
from __future__ import annotations

import sys

# MUST repoint at the constrained mod contract BEFORE importing the btsgen modules that read paths.
from btsgen.class_forge import point_btsgen_at_mod_contract

point_btsgen_at_mod_contract()

from btsgen import bts1, cardgen, census                # noqa: E402
from btsgen.validator import CardValidator              # noqa: E402
from btsgen.frontend import catalog as C                # noqa: E402
from btsgen import featured                             # noqa: E402

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
    base = {"id": "x_test", "name": "X Test", "type": "skill", "rarity": "uncommon",
            "cost": 1, "target": "self", "source": "llm", "effects": effects}
    base["upgrade"] = {"effects": up if up is not None else effects}
    base.update(kw)
    return base


def test_version() -> None:
    print("Phase X vocab stamp is at least v29:")
    check(bts1.VOCAB_VERSION >= 29, f"bts1.VOCAB_VERSION must be >= 29 (Phase X), got {bts1.VOCAB_VERSION}")


def test_accepts(v: CardValidator) -> None:
    print("upgrade_card cards:choose validates at card level:")
    ch = _card([{"op": "upgrade_card", "cards": "choose"}])
    check(v.validate(ch).ok, f"upgrade_card choose should validate: {v.validate(ch).errors}")
    # choose riding alongside another effect on the same card
    combo = _card([{"op": "block", "amount": 5}, {"op": "upgrade_card", "cards": "choose"}])
    check(v.validate(combo).ok, f"block + upgrade_card choose should validate: {v.validate(combo).errors}")


def test_rejects(v: CardValidator) -> None:
    print("upgrade_card cards:choose is rejected inside a repeating trigger payload:")

    def bad(card, why):
        check(not v.validate(card).ok, why)

    # `choose` inside a repeating trigger payload would spam the pick UI — random ONLY there
    bad(_card([{"op": "add_trigger", "trigger": "turn_start",
                "effects": [{"op": "upgrade_card", "cards": "choose"}]}], **{"type": "power"}),
        "upgrade_card 'choose' inside a trigger payload must reject")


def test_text_bytematch() -> None:
    print("upgrade_card choose card text byte-matches the C# ForgedCards.UpgradeSentence:")
    ch = cardgen.describe([{"op": "upgrade_card", "cards": "choose"}], "self")
    check(ch == "Upgrade a card of your choice in your hand for the rest of this combat.",
          f"upgrade_card choose describe mismatch: {ch!r}")


def test_emit() -> None:
    print("upgrade_card choose emits a Cards: named arg in the C# EffectSpec literal:")
    lit = cardgen.effect_literal({"op": "upgrade_card", "cards": "choose"})
    check(lit == 'new EffectSpec("upgrade_card", Cards: "choose")', f"upgrade_card choose emit mismatch: {lit!r}")


def test_census() -> None:
    print("census tallies an upgrade_card choose card as a non-plain upgrade card:")
    cc = census.walk_card(_card([{"op": "upgrade_card", "cards": "choose"}]))
    check("upgrade_card" in cc.ops, "census should count the upgrade_card op")
    check(not cc.plain, "an upgrade_card choose card is NOT a plain stat line")


def test_pricing(v: CardValidator) -> None:
    print("upgrade_card 'choose' scores between 'random' and 'all':")
    rnd = v.score_card(_card([{"op": "upgrade_card", "cards": "random"}]))
    ch = v.score_card(_card([{"op": "upgrade_card", "cards": "choose"}]))
    allc = v.score_card(_card([{"op": "upgrade_card", "cards": "all"}]))
    check(rnd < ch < allc, f"choose ({ch}) should price between random ({rnd}) and all ({allc})")


def test_catalog_and_featured() -> None:
    print("catalog battle_smith invites choose + featured detect fires on a choose card:")
    cat = C.load_catalog()
    e = cat.by_id["battle_smith"]
    check("choose" in e.description, "battle_smith description should mention the choose scope")
    cc = census.walk_card(_card([{"op": "upgrade_card", "cards": "choose"}]))
    check(featured._BY_ID["battle_smith"].detect(cc), "featured detect fires on an upgrade_card choose card")


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
