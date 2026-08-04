"""Phase V — in-run upgrade, no-choice form (VOCABULARY_GAPS #18) — offline, no API key.

Run:  uv run python -m tests.test_phase_v       (from generation/)
Exits nonzero on any failure. Exercises the mod-contract validator (upgrade_card `cards` scope + the
`cards`-only-on-upgrade_card guard + the trigger-payload `random`-only rule), cardgen text/emit for the
`upgrade_card` op (card level + trigger fragment, byte-matching the C# ForgedCards.UpgradeSentence), the
census tally, pricing (all > random), and the catalog `battle_smith` + featured entries. Mirrors the C#
ForgedCards / EffectRunner / DataCard / CardSpec / TriggerRunner changes (vocab v27).
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
    base = {"id": "v_test", "name": "V Test", "type": "skill", "rarity": "uncommon",
            "cost": 1, "target": "self", "source": "llm", "effects": effects}
    base["upgrade"] = {"effects": up if up is not None else effects}
    base.update(kw)
    return base


def test_version() -> None:
    print("Phase V vocab stamp is at least v27:")
    check(bts1.VOCAB_VERSION >= 27, f"bts1.VOCAB_VERSION must be >= 27 (Phase V), got {bts1.VOCAB_VERSION}")


def test_accepts(v: CardValidator) -> None:
    print("valid upgrade_card cards validate:")
    rnd = _card([{"op": "upgrade_card", "cards": "random"}])
    check(v.validate(rnd).ok, f"upgrade_card random should validate: {v.validate(rnd).errors}")
    allc = _card([{"op": "upgrade_card", "cards": "all"}])
    check(v.validate(allc).ok, f"upgrade_card all should validate: {v.validate(allc).errors}")
    # upgrade_card riding alongside another effect on the same card (no calc-var conflict — it declares none)
    combo = _card([{"op": "block", "amount": 5}, {"op": "upgrade_card", "cards": "random"}])
    check(v.validate(combo).ok, f"block + upgrade_card should validate: {v.validate(combo).errors}")
    # a rare power whose turn_start payload upgrades a random card (the slow-burn engine — random ONLY)
    trig = _card([{"op": "add_trigger", "trigger": "turn_start",
                   "effects": [{"op": "upgrade_card", "cards": "random"}]}],
                 **{"type": "power", "rarity": "rare"})
    check(v.validate(trig).ok, f"turn_start -> upgrade_card random should validate: {v.validate(trig).errors}")


def test_rejects(v: CardValidator) -> None:
    print("invalid upgrade_card cards are rejected:")

    def bad(card, why):
        check(not v.validate(card).ok, why)

    bad(_card([{"op": "upgrade_card"}]),
        "upgrade_card with no 'cards' scope must reject")
    bad(_card([{"op": "upgrade_card", "cards": "zzz"}]),
        "upgrade_card with an unknown 'cards' scope must reject")
    bad(_card([{"op": "damage", "amount": 6, "cards": "all"}], **{"type": "attack", "target": "enemy"}),
        "'cards' on a non-upgrade_card op must reject")
    # `all` inside a repeating trigger payload is degenerate — random ONLY there
    bad(_card([{"op": "add_trigger", "trigger": "turn_start",
                "effects": [{"op": "upgrade_card", "cards": "all"}]}], **{"type": "power"}),
        "upgrade_card 'all' inside a trigger payload must reject")
    # a trigger payload upgrade_card with no scope must reject too
    bad(_card([{"op": "add_trigger", "trigger": "turn_start",
                "effects": [{"op": "upgrade_card"}]}], **{"type": "power"}),
        "a payload upgrade_card with no 'cards' must reject")


def test_text_bytematch() -> None:
    print("upgrade_card card text byte-matches the C# ForgedCards.UpgradeSentence:")
    rnd = cardgen.describe([{"op": "upgrade_card", "cards": "random"}], "self")
    check(rnd == "Upgrade a random card in your hand for the rest of this combat.",
          f"upgrade_card random describe mismatch: {rnd!r}")
    allc = cardgen.describe([{"op": "upgrade_card", "cards": "all"}], "self")
    check(allc == "Upgrade ALL cards in your hand for the rest of this combat.",
          f"upgrade_card all describe mismatch: {allc!r}")
    # the trigger fragment (lowercase verb, no trailing period inside the sentence) — random only
    trig = cardgen.describe([{"op": "add_trigger", "trigger": "turn_start",
                              "effects": [{"op": "upgrade_card", "cards": "random"}]}], "self")
    check(trig == "At the start of your turn, upgrade a random card in your hand for the rest of this combat.",
          f"upgrade_card trigger sentence mismatch: {trig!r}")


def test_emit() -> None:
    print("upgrade_card emits a Cards: named arg in the C# EffectSpec literal:")
    lit = cardgen.effect_literal({"op": "upgrade_card", "cards": "random"})
    check(lit == 'new EffectSpec("upgrade_card", Cards: "random")', f"upgrade_card emit mismatch: {lit!r}")
    lita = cardgen.effect_literal({"op": "upgrade_card", "cards": "all"})
    check(lita == 'new EffectSpec("upgrade_card", Cards: "all")', f"upgrade_card all emit mismatch: {lita!r}")
    # a payload upgrade_card nests inside the add_trigger literal
    litt = cardgen.effect_literal({"op": "add_trigger", "trigger": "turn_start",
                                   "effects": [{"op": "upgrade_card", "cards": "random"}]})
    check('new EffectSpec("upgrade_card", Cards: "random")' in litt, f"payload upgrade_card emit mismatch: {litt!r}")


def test_census() -> None:
    print("census tallies upgrade_card and un-plains an upgrade card:")
    cc = census.walk_card(_card([{"op": "upgrade_card", "cards": "random"}]))
    check("upgrade_card" in cc.ops, "census should count the upgrade_card op")
    check(not cc.plain, "an upgrade_card card is NOT a plain stat line")


def test_pricing(v: CardValidator) -> None:
    print("upgrade_card 'all' scores above 'random':")
    rnd = v.score_card(_card([{"op": "upgrade_card", "cards": "random"}]))
    allc = v.score_card(_card([{"op": "upgrade_card", "cards": "all"}]))
    check(allc > rnd, f"upgrade_card all ({allc}) should price above random ({rnd})")
    check(rnd > 0, f"upgrade_card random should carry non-zero value (got {rnd})")


def test_catalog_and_featured() -> None:
    print("catalog battle_smith entry + featured menu entry exist:")
    cat = C.load_catalog()
    check("battle_smith" in cat.by_id, "battle_smith archetype must exist in the catalog")
    e = cat.by_id["battle_smith"]
    check("upgrade_card" in e.ops, "battle_smith must declare the upgrade_card op/token")
    check(any("VOCABULARY_GAPS#18" in r for r in e.gap_refs), "battle_smith must gap_ref #18")
    check("battle_smith" in featured._BY_ID, "battle_smith featured menu entry must exist")
    cc = census.walk_card(_card([{"op": "upgrade_card", "cards": "all"}]))
    check(featured._BY_ID["battle_smith"].detect(cc), "featured detect fires on an upgrade_card card")
    plain = census.walk_card(_card([{"op": "block", "amount": 5}]))
    check(not featured._BY_ID["battle_smith"].detect(plain), "featured detect does NOT fire on a plain card")


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
