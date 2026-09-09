"""Phase AJ — HIDDEN CAPACITY (VOCAB_GAP_REMEDIATION_PLAN Wave 1, vocab v40) — offline, no API key.

Run:  uv run python -m tests.test_phase_aj       (from generation/)
Exits nonzero on any failure. Covers the four contract catch-ups (no new runtime mechanic):
  1. card target `random_enemy` validates + describes byte-identically (damage AND status suffix), and the
     target-reading condition/scale (`when:target_has_status`, `scale:target_debuff_count`) are REJECTED on it;
  2. `hits` on `summon_attack` validates (the vocabulary/schema/engine allowed it; the validator didn't);
  3. a trigger-payload `channel_orb` may name a custom pool orb (class context) and is rejected for an unknown
     name / on a class with no such orb;
  4. `once_per_turn` on an `on_blade_played` trigger validates (C# parity).
Plus: the vocab stamp is v40 and the C# emit for a random_enemy card names TargetType.RandomEnemy.
"""
from __future__ import annotations

import sys

from btsgen.class_forge import point_btsgen_at_mod_contract

point_btsgen_at_mod_contract()

from btsgen import bts1, cardgen, census  # noqa: E402
from btsgen.validator import CardValidator  # noqa: E402

_PASS = 0
_FAIL = 0


def check(cond: bool, msg: str) -> None:
    global _PASS, _FAIL
    if cond:
        _PASS += 1
    else:
        _FAIL += 1
        print(f"  FAIL: {msg}")


def _card(cid, effects, *, rarity="uncommon", ctype="attack", cost=1, target="enemy", upgrade=None):
    c = {"id": cid, "name": cid.replace("_", " ").title(), "type": ctype, "rarity": rarity,
         "cost": cost, "target": target, "source": "llm", "effects": effects}
    if upgrade is not None:
        c["upgrade"] = {"effects": upgrade}
    return c


def test_version() -> None:
    print("Phase AJ vocab stamp is v40:")
    check(bts1.VOCAB_VERSION >= 40, f"bts1.VOCAB_VERSION must be >= 40 (Phase AJ), got {bts1.VOCAB_VERSION}")


def _t_random_enemy(v: CardValidator) -> None:
    print("random_enemy target validates, describes, and emits:")
    scatter = _card("aj_scatter", [{"op": "damage", "amount": 4, "hits": 3}], target="random_enemy")
    r = v.validate(scatter)
    check(r.ok, f"a random_enemy multi-hit attack should validate: {r.errors}")
    # describe() emits the DynamicVar templates ({Damage}/{Hits}) the game fills in — byte-match with C# Describe.
    check(cardgen.describe(scatter["effects"], "random_enemy") == "Deal {Damage} damage {Hits} times to a random enemy.",
          f"describe: {cardgen.describe(scatter['effects'], 'random_enemy')!r}")
    # a status rider on a random_enemy card reads "... to a random enemy" (lockstep with ForgedCards.Describe)
    flask = _card("aj_flask", [{"op": "damage", "amount": 6}, {"op": "apply_status", "status": "weak", "amount": 2}],
                  target="random_enemy")
    r = v.validate(flask)
    check(r.ok, f"random_enemy damage + debuff should validate: {r.errors}")
    d = cardgen.describe(flask["effects"], "random_enemy")
    check(d == "Deal {Damage} damage to a random enemy.\nApply Weak to a random enemy.", f"describe: {d!r}")
    # a self-buff on a random_enemy card still reads "Gain ..." (buffs land on you)
    d2 = cardgen.describe([{"op": "damage", "amount": 6}, {"op": "apply_status", "status": "strength", "amount": 1}],
                          "random_enemy")
    check(d2 == "Deal {Damage} damage to a random enemy.\nGain Strength.", f"describe (buff): {d2!r}")
    # C# emit names the RandomEnemy TargetType
    _, src = cardgen.gen_class(scatter)
    check("TargetType.RandomEnemy" in src, "emitted C# should carry TargetType.RandomEnemy")
    # the target-reading condition / scale are rejected on a random_enemy card
    bad_when = _card("aj_bad_when", [{"op": "damage", "amount": 6},
                                     {"op": "draw", "amount": 1, "when": {"kind": "target_has_status", "status": "weak"}}],
                     target="random_enemy")
    r = v.validate(bad_when)
    check(not r.ok and any("target_has_status" in e for e in r.errors),
          f"when:target_has_status on a random_enemy card must be rejected: {r.errors}")
    bad_scale = _card("aj_bad_scale", [{"op": "damage", "amount": 1, "scale": "target_debuff_count"}], target="random_enemy")
    r = v.validate(bad_scale)
    check(not r.ok and any("target_debuff_count" in e for e in r.errors),
          f"scale:target_debuff_count on a random_enemy card must be rejected: {r.errors}")
    # the same shapes stay legal on a chosen-enemy card
    ok_when = dict(bad_when, target="enemy")
    check(v.validate(ok_when).ok, f"when:target_has_status on an enemy card stays legal: {v.validate(ok_when).errors}")
    # the census sees the card as a normal attack (no crash on the new target)
    cc = census.walk_card(scatter)
    check(cc is not None, "census walks a random_enemy card")


def _t_summon_attack_hits(v_summon: CardValidator, v_plain: CardValidator) -> None:
    print("multi-hit summon_attack validates on a summon class:")
    card = _card("aj_thrall_flurry", [{"op": "summon_attack", "amount": 3, "hits": 3}])
    r = v_summon.validate(card)
    check(r.ok, f"summon_attack with hits should validate on a summon class: {r.errors}")
    d = cardgen.describe(card["effects"], "enemy")
    check(d == "Deal 3 damage 3 times with your summon.", f"describe: {d!r}")
    # hits still only on damage / summon_attack
    bad = _card("aj_bad_hits", [{"op": "block", "amount": 3, "hits": 2}], ctype="skill", target="self")
    r = v_plain.validate(bad)
    check(not r.ok, "hits on block must still be rejected")
    # one multi-hit per card: summon_attack hits + damage hits on one card is two Hits vars
    two = _card("aj_two_hits", [{"op": "damage", "amount": 3, "hits": 2}, {"op": "summon_attack", "amount": 3, "hits": 2}])
    r = v_summon.validate(two)
    check(not r.ok, "two multi-hit effects on one card must be rejected")


def _t_trigger_custom_orb(v_orb: CardValidator, v_plain: CardValidator) -> None:
    print("trigger-payload channel_orb accepts a custom pool orb (class context only):")
    ember = _card("aj_ember_engine", [{"op": "add_trigger", "trigger": "turn_start",
                                       "effects": [{"op": "channel_orb", "orb": "ember", "amount": 1}]}],
                  ctype="power", target="self")
    r = v_orb.validate(ember)
    check(r.ok, f"turn_start channel_orb ember should validate for a class whose pool has Ember: {r.errors}")
    r = v_plain.validate(ember)
    check(not r.ok and any("ember" in e for e in r.errors),
          f"channel_orb ember must be rejected without that pool orb: {r.errors}")
    unknown = _card("aj_typo_engine", [{"op": "add_trigger", "trigger": "turn_start",
                                        "effects": [{"op": "channel_orb", "orb": "embr", "amount": 1}]}],
                    ctype="power", target="self")
    r = v_orb.validate(unknown)
    check(not r.ok, "a typo'd pool orb name in a trigger payload must be rejected")
    base = _card("aj_frost_engine", [{"op": "add_trigger", "trigger": "turn_end",
                                      "effects": [{"op": "channel_orb", "orb": "frost", "amount": 1}]}],
                 ctype="power", target="self")
    check(v_plain.validate(base).ok, "base orbs in a trigger payload stay legal everywhere")
    d = cardgen.describe(ember["effects"], "self")
    check("Ember" in d and "start of your turn" in d, f"trigger describe names the custom orb: {d!r}")


def _t_blade_once_per_turn(v_plain: CardValidator) -> None:
    print("once_per_turn on an on_blade_played trigger validates:")
    parry = _card("aj_parry", [{"op": "add_trigger", "trigger": "on_blade_played", "once_per_turn": True,
                                "effects": [{"op": "block", "amount": 6}]}], ctype="power", target="self")
    r = v_plain.validate(parry)
    check(r.ok, f"on_blade_played + once_per_turn should validate: {r.errors}")
    still = _card("aj_no_opt", [{"op": "add_trigger", "trigger": "turn_start", "once_per_turn": True,
                                 "effects": [{"op": "block", "amount": 6}]}], ctype="power", target="self")
    check(not v_plain.validate(still).ok, "once_per_turn on turn_start must still be rejected")


def main() -> int:
    v_plain = CardValidator()
    v_orb = CardValidator(extra_orbs={"ember"})
    v_summon = CardValidator(extra_summons={"Bone Thrall"})
    test_version()
    _t_random_enemy(v_plain)
    _t_summon_attack_hits(v_summon, v_plain)
    _t_trigger_custom_orb(v_orb, v_plain)
    _t_blade_once_per_turn(v_plain)
    print(f"\n{_PASS} passed, {_FAIL} failed")
    return 1 if _FAIL else 0


# pytest entry points (each re-runs main's checks in isolation for a clear failure name)
def test_phase_aj_all() -> None:
    assert main() == 0


if __name__ == "__main__":
    sys.exit(main())
