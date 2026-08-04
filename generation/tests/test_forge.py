"""Phase M Forge tests (VOCABULARY_GAPS #36) — offline, no API key.

Run:  uv run python -m tests.test_forge     (from generation/)
Exits nonzero on any failure. Exercises the mod-contract validator, the set-level forge⇔forged pairing
rule, the relic-side forge op, the C#-emit literals, and the synthesized card text for the `forge` op /
scale:"forged" additive payoff / `forged_ge` condition. Mirrors the C# ForgedCards validation + Describe
(vocab v19).
"""
from __future__ import annotations

import sys

# MUST repoint at the constrained mod contract BEFORE importing the btsgen modules that read paths.
from btsgen.class_forge import (point_btsgen_at_mod_contract, _validate_relic,  # noqa: E402
                                _synthesize_blade)

point_btsgen_at_mod_contract()

from btsgen import cardgen                                  # noqa: E402
from btsgen.character_validator import forge_manipulation_warnings, forge_pairing_warnings  # noqa: E402
from btsgen.validator import CardValidator                  # noqa: E402

_PASS = 0
_FAIL = 0


def check(cond: bool, msg: str) -> None:
    global _PASS, _FAIL
    if cond:
        _PASS += 1
    else:
        _FAIL += 1
        print(f"  FAIL: {msg}")


def _card(effects: list[dict], **kw) -> dict:
    base = {"id": "forge_test", "name": "Forge Test", "type": "attack", "rarity": "uncommon",
            "cost": 1, "target": "enemy", "source": "llm", "effects": effects}
    base.update(kw)
    return base


def test_accepts(v: CardValidator) -> None:
    print("forge income + forged payoffs validate:")
    # plain forge income (a skill that stokes the counter)
    income = _card([{"op": "forge", "amount": 3}], type="skill", target="self")
    res = v.validate(income)
    check(res.ok, f"forge income should validate: {res.errors}")
    # the forged-scaled damage payoff (additive: printed 6 + Forge)
    payoff = _card([{"op": "damage", "amount": 6, "scale": "forged"}])
    res = v.validate(payoff)
    check(res.ok, f"forged damage payoff should validate: {res.errors}")
    # forged block payoff
    blk = _card([{"op": "block", "amount": 5, "scale": "forged"}], type="skill", target="self")
    res = v.validate(blk)
    check(res.ok, f"forged block payoff should validate: {res.errors}")
    # trigger income: the per-turn engine power
    engine = _card([{"op": "add_trigger", "trigger": "turn_start",
                     "effects": [{"op": "forge", "amount": 2}]}], type="power", target="self")
    res = v.validate(engine)
    check(res.ok, f"turn_start forge trigger should validate: {res.errors}")
    # forged_ge gated payoff ("if your Forge is 10+")
    gated = _card([{"op": "damage", "amount": 8},
                   {"op": "apply_status", "status": "vulnerable", "amount": 2,
                    "when": {"kind": "forged_ge", "value": 10}}])
    res = v.validate(gated)
    check(res.ok, f"forged_ge-gated effect should validate: {res.errors}")
    # forged payoff with an upgrade (printed base grows; still one scaled damage)
    up = _card([{"op": "damage", "amount": 6, "scale": "forged"}],
               upgrade={"effects": [{"op": "damage", "amount": 9, "scale": "forged"}]})
    res = v.validate(up)
    check(res.ok, f"upgraded forged payoff should validate: {res.errors}")


def test_rejects(v: CardValidator) -> None:
    print("forge misuse is rejected:")

    def bad(card: dict, why: str) -> None:
        check(not v.validate(card).ok, why)

    # forged on draw (no printed base to add to)
    bad(_card([{"op": "draw", "amount": 2, "scale": "forged"}], type="skill", target="self"),
        "scale:forged on draw must be rejected")
    # forge op without an amount (schema requires it)
    bad(_card([{"op": "forge"}], type="skill", target="self"),
        "forge without amount must be rejected")
    # scale:"forged" inside a trigger payload (only cards_retained is allowed there)
    bad(_card([{"op": "add_trigger", "trigger": "turn_end",
                "effects": [{"op": "block", "amount": 3, "scale": "forged"}]}], type="power", target="self"),
        "scale:forged inside a trigger payload must be rejected")
    # a scaled trigger forge (income is fixed-amount only)
    bad(_card([{"op": "add_trigger", "trigger": "turn_end",
                "effects": [{"op": "forge", "amount": 1, "scale": "cards_retained"}]}], type="power", target="self"),
        "scaled trigger forge must be rejected")
    # two scaled damage/block on one card (one calculated var)
    bad(_card([{"op": "damage", "amount": 6, "scale": "forged"},
               {"op": "block", "amount": 4, "scale": "cards_in_hand"}]),
        "two scaled damage/block effects must be rejected")
    # forged is NOT the X-cost scalar: an X-cost card still needs scale:x
    bad(_card([{"op": "damage", "amount": 6, "scale": "forged"}], cost="X"),
        "X-cost with only a forged scale must be rejected")
    # forged_ge needs a value (schema)
    bad(_card([{"op": "damage", "amount": 8, "when": {"kind": "forged_ge"}}]),
        "forged_ge without value must be rejected")
    # forge can't be multi-hit (hits only on damage/summon_attack)
    bad(_card([{"op": "forge", "amount": 2, "hits": 3}], type="skill", target="self"),
        "forge with hits must be rejected")


def test_text(_v: CardValidator) -> None:
    print("synthesized card text matches the C# Describe/TriggerSentence:")

    def desc(effects: list[dict], target: str = "enemy") -> str:
        return cardgen.describe(effects, target)

    check(desc([{"op": "forge", "amount": 3}], "self") == "Forge 3.",
          "forge keyword sentence")
    check(desc([{"op": "damage", "amount": 6, "scale": "forged"}])
          == "Deal 6 damage, plus your Forge.",
          "forged damage sentence")
    check(desc([{"op": "damage", "amount": 6, "scale": "forged"}], "all_enemies")
          == "Deal 6 damage to ALL enemies, plus your Forge.",
          "forged AoE damage sentence")
    check(desc([{"op": "block", "amount": 5, "scale": "forged"}], "self")
          == "Gain 5 Block, plus your Forge.",
          "forged block sentence")
    check(desc([{"op": "add_trigger", "trigger": "turn_start",
                 "effects": [{"op": "forge", "amount": 2}]}], "self")
          == "At the start of your turn, Forge 2.",
          "trigger forge income sentence")
    check(desc([{"op": "damage", "amount": 8, "when": {"kind": "forged_ge", "value": 10}}])
          == "Deal {Damage} damage if your Forge is 10+.",
          "forged_ge condition weave")


def test_literals() -> None:
    print("C#-emit literals carry forge/forged/forged_ge:")
    check(cardgen.effect_literal({"op": "forge", "amount": 3})
          == 'new EffectSpec("forge", 3)',
          "forge literal")
    check(cardgen.effect_literal({"op": "damage", "amount": 6, "scale": "forged"})
          == 'new EffectSpec("damage", 6, null, 1, "forged")',
          "forged damage literal")
    trig = cardgen.effect_literal({"op": "add_trigger", "trigger": "turn_start",
                                   "effects": [{"op": "forge", "amount": 2}]})
    check('Trigger: "turn_start"' in trig and 'new EffectSpec("forge", 2)' in trig,
          f"trigger forge literal: {trig}")
    gated = cardgen.effect_literal({"op": "damage", "amount": 8,
                                    "when": {"kind": "forged_ge", "value": 10}})
    check('When: new Condition("forged_ge", 10, null, false)' in gated,
          f"forged_ge condition literal: {gated}")


def test_pairing() -> None:
    print("set-level forge pairing (income <-> payoff):")
    income = _card([{"op": "forge", "amount": 3}], id="smith", type="skill", target="self")
    trigger_income = _card([{"op": "add_trigger", "trigger": "turn_start",
                             "effects": [{"op": "forge", "amount": 2}]}],
                           id="furnace", type="power", target="self")
    payoff = _card([{"op": "damage", "amount": 6, "scale": "forged"}], id="blade")
    plain = _card([{"op": "damage", "amount": 6}], id="strike2")
    check(forge_pairing_warnings([income, payoff]) == [], "income + payoff pairs cleanly")
    check(forge_pairing_warnings([trigger_income, payoff]) == [], "trigger income counts as income")
    check(forge_pairing_warnings([plain]) == [], "a forge-free set is silent")
    w = forge_pairing_warnings([income, plain])
    check(len(w) == 1 and "no payoff" in w[0], f"income with no payoff warns: {w}")
    w = forge_pairing_warnings([payoff, plain])
    check(len(w) == 1 and "no income" in w[0], f"payoff with no income warns: {w}")


def test_scoring(v: CardValidator) -> None:
    print("balance scoring prices forge income and forged payoffs:")
    check(v.score_card(_card([{"op": "forge", "amount": 3}])) == 6.0,
          "forge 3 scores 6.0 (2.0/stack)")
    check(v.score_card(_card([{"op": "damage", "amount": 6, "scale": "forged"}])) == 12.0,
          "forged 6 damage scores 12.0 (printed + 6 premium)")


def test_blade(v: CardValidator) -> None:
    print("the Sovereign Blade (Phase T — summoned-on-first-Forge token):")
    blade = _synthesize_blade({"name_hint": "Emberfang"})
    # shape (Phase T): a TOKEN, 2-cost attack that is retained + damage scale:"forged" — NO innate (summoned).
    check(blade["id"] == "emberfang", f"blade id slugs the name: {blade['id']}")
    check(blade["name"] == "Emberfang", "blade uses the blueprint name")
    check(blade["type"] == "attack" and blade["rarity"] == "token" and blade["cost"] == 2,
          f"blade is a 2-cost token attack: {blade['rarity']}/{blade['cost']}")
    check(blade.get("token") is True, "blade is marked token:true (non-drafted)")
    ops = [(e["op"], e.get("scale")) for e in blade["effects"]]
    check(ops == [("damage", "forged"), ("retain", None)],
          f"blade effects are forged damage + retain, NO innate: {ops}")
    check(blade["effects"][0]["amount"] == 10, f"blade base damage is 10: {blade['effects'][0]['amount']}")
    up = [(e["op"], e.get("scale")) for e in blade["upgrade"]["effects"]]
    check(up == [("damage", "forged"), ("retain", None)],
          "blade upgrade keeps the same shape (grows the printed base)")
    check(blade["upgrade"]["effects"][0]["amount"] == 13, "blade upgrade damage is 13")
    # it must pass the live mod-contract validator (token rarity + token:true blade)
    res = v.validate(blade)
    check(res.ok, f"synthesized blade should validate: {res.errors}")
    # text mirrors the C# Describe: forged damage + the ONE keyword line (Retain), no Innate
    text = cardgen.describe(blade["effects"], blade["target"])
    check(text == "Deal 10 damage, plus your Forge.\nRetain.", f"blade card text: {text!r}")
    # a default (safety-net) blade with no name falls back cleanly
    default = _synthesize_blade(None)
    check(default["id"] == "sovereign_blade" and default["token"] is True, "default blade falls back to Sovereign Blade")
    # the blade is a forged PAYOFF: income + blade pairs cleanly; a blade with no income warns.
    income = _card([{"op": "forge", "amount": 2}], id="stoke", type="skill", target="self")
    check(forge_pairing_warnings([income, blade]) == [], "forge income + the blade pair cleanly")
    w = forge_pairing_warnings([blade])
    check(len(w) == 1 and "no income" in w[0], f"a blade with no income warns (dead blade): {w}")


def test_blade_manipulation(v: CardValidator) -> None:
    print("Phase T — blade manipulation (summon_blade / on_blade_played) + the decision-#9 rule:")
    blade = _synthesize_blade({"name_hint": "Emberfang"})
    income = _card([{"op": "forge", "amount": 2}], id="stoke", type="skill", target="self")
    # summon_blade text (card-level + trigger fragment) byte-matches the C# ForgedCards.
    sb_card = _card([{"op": "summon_blade"}], id="summon_forth", type="skill", target="self")
    check(cardgen.describe(sb_card["effects"], "self") == "Put your blade into your hand from anywhere.",
          f"summon_blade text: {cardgen.describe(sb_card['effects'], 'self')!r}")
    # on_blade_played trigger sentence byte-matches.
    parry = _card([{"op": "add_trigger", "trigger": "on_blade_played",
                    "effects": [{"op": "block", "amount": 8}]}], id="riposte", type="power", target="self")
    sent = cardgen.trigger_sentence(parry["effects"][0])
    check(sent == "Whenever you play your blade, gain 8 Block.", f"on_blade_played sentence: {sent!r}")
    # decision #9: a forge class (income + blade) with NO manipulation card warns; with one, it's clean.
    mw = forge_manipulation_warnings([income, blade])
    check(len(mw) == 1 and "blade-manipulation" in mw[0], f"forge class w/o manipulation warns: {mw}")
    check(forge_manipulation_warnings([income, blade, sb_card]) == [],
          "a summon_blade card satisfies the manipulation rule")
    check(forge_manipulation_warnings([income, blade, parry]) == [],
          "an on_blade_played rider satisfies the manipulation rule")
    # a non-forge class (no income, no blade) is never asked for a manipulation card.
    plain = _card([{"op": "damage", "amount": 6}], id="plain", type="attack", target="enemy")
    check(forge_manipulation_warnings([plain]) == [], "a non-forge set never triggers the manipulation rule")


def test_vocab_version() -> None:
    print("Phase AI — the vocab stamp is v39:")
    from btsgen import bts1
    check(bts1.VOCAB_VERSION == 39, f"bts1.VOCAB_VERSION == 39: {bts1.VOCAB_VERSION}")


def test_relic() -> None:
    print("relic-side forge income validates:")
    relic = {"name": "Smoldering Heirloom", "tier": "starter",
             "hooks": [{"trigger": "turn_start", "effects": [{"op": "forge", "amount": 1}]}]}
    errs = _validate_relic(relic)
    check(errs == [], f"forge relic hook should validate: {errs}")
    bad = {"name": "Cold Heirloom", "tier": "starter",
           "hooks": [{"trigger": "turn_start", "effects": [{"op": "forge", "amount": 0}]}]}
    check(_validate_relic(bad) != [], "forge relic hook with amount 0 must be rejected")


def main() -> int:
    v = CardValidator()
    test_accepts(v)
    test_rejects(v)
    test_text(v)
    test_literals()
    test_pairing()
    test_scoring(v)
    test_blade(v)
    test_blade_manipulation(v)
    test_vocab_version()
    test_relic()
    print(f"\n{_PASS} passed, {_FAIL} failed")
    return 1 if _FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
