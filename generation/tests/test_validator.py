"""Offline validator tests — no API key needed.

Run:  uv run python -m tests.test_validator     (from generation/)
Exits nonzero on any failure. Confirms the harness gate mirrors the engine's
ContentValidator.gd: shape/vocab/recursion via schema, ref-integrity, and an
identical balance score.
"""
from __future__ import annotations

import copy
import json
import sys

from btsgen import paths
from btsgen.validator import CardValidator

_PASS = 0
_FAIL = 0


def check(cond: bool, msg: str) -> None:
    global _PASS, _FAIL
    if cond:
        _PASS += 1
    else:
        _FAIL += 1
        print(f"  FAIL: {msg}")


def _strike() -> dict:
    return json.loads((paths.CARDS_DIR / "strike.json").read_text())


def test_all_authored_cards_validate(v: CardValidator) -> None:
    print("authored cards validate clean:")
    files = sorted(paths.CARDS_DIR.glob("*.json"))
    check(len(files) >= 17, f"expected >=17 authored cards, found {len(files)}")
    for f in files:
        card = json.loads(f.read_text())
        res = v.validate(card)
        check(res.ok, f"{f.name} should be valid: {res.errors}")
        # score is a real number (may be negative for debuff cards like Disarm)
        check(isinstance(res.score, float), f"{f.name} score not numeric")


def test_scores_match_engine(v: CardValidator) -> None:
    print("balance scores match ContentValidator.gd:")
    cases = {
        "strike": 6.0,          # damage 6
        "bash": 12.0,           # damage 8 + vuln 2*2
        "twin_strike": 10.0,    # multi x2 of (damage 5)
        "body_slam": 6.0,       # from_state -> flat 6
        "bloodletting": 10.5,   # lose_hp 3*-0.5 + gain_energy 2*6
        "disarm": -8.0,         # apply_status strength -2 * 4
        "battle_trance": 15.0,  # draw 3*5 (+ set_flag 0)
    }
    for cid, expected in cases.items():
        card = json.loads((paths.CARDS_DIR / f"{cid}.json").read_text())
        got = v.score_card(card)
        check(abs(got - expected) < 1e-6, f"{cid} score {got} != {expected}")


def test_hard_rejects(v: CardValidator) -> None:
    print("known-bad cards are rejected:")

    def bad(mutate, label) -> None:
        c = _strike()
        mutate(c)
        res = v.validate(c)
        check(not res.ok, f"{label} should reject")

    bad(lambda c: c.update(effects=[{"op": "nuke", "amount": 5}]), "unknown op")
    bad(lambda c: c.update(effects=[{"op": "apply_status", "status": "poison", "amount": 1}]), "unknown status")
    bad(lambda c: c.pop("cost"), "missing cost")
    bad(lambda c: c.update(cost=7), "cost out of range")
    bad(lambda c: c.update(effects=[{"op": "add_card", "card_id": "zzz_nope", "pile": "hand"}]), "bad card ref")
    bad(lambda c: c.update(rarity="legendary"), "bad rarity enum")
    bad(lambda c: c.update(wizardry=True), "extra property")
    bad(lambda c: c.update(effects=[]), "empty effects")


def test_overpowered_warns_not_rejects(v: CardValidator) -> None:
    print("overpowered card warns but is not rejected:")
    c = _strike()
    c.update(id="overkill", name="Overkill", cost=1, rarity="common",
             effects=[{"op": "damage", "amount": 100}])
    c.pop("upgrade", None)
    res = v.validate(c)
    check(res.ok, "overpowered card should still validate (warn, not reject)")
    check(any("power score" in w for w in res.warnings), f"expected a balance-score warning, got {res.warnings}")
    # power_ceiling is the same line the warning fires over (and what the balance-repair pass targets)
    check(abs(v.power_ceiling(c) - (5.0 + 1 * 7.0) * 1.25) < 1e-6, "common cost-1 ceiling should be 15.0")
    check(abs(v.power_ceiling({**c, "rarity": "rare"}) - 12.0 * 1.6) < 1e-6, "rare cost-1 ceiling should be 19.2")
    check(abs(v.power_ceiling({**c, "cost": "X"}) - (5.0 + 3 * 7.0) * 1.25) < 1e-6, "X-cost ~ 3 energy")
    check(res.score > v.power_ceiling(c), "the warned card scores above its ceiling")


def test_self_reference_allowed(v: CardValidator) -> None:
    print("a card may reference its own id (add_card self-copy):")
    c = _strike()
    c.update(id="echo_strike", name="Echo Strike",
             effects=[{"op": "damage", "amount": 6},
                      {"op": "add_card", "card_id": "echo_strike", "pile": "discard"}])
    c.pop("upgrade", None)
    res = v.validate(c)
    check(res.ok, f"self-referencing card should validate: {res.errors}")


def test_dominance_check(v: CardValidator) -> None:
    print("dominance check flags power-creep vs the corpus:")
    # War Footing redux: Inflame's +2 Strength PLUS 6 Block, same cost & rarity -> dominates inflame
    wf = {"id": "wf_test", "name": "WF", "type": "skill", "rarity": "uncommon", "cost": 1,
          "target": "self", "effects": [{"op": "apply_status", "status": "strength", "amount": 2},
                                          {"op": "block", "amount": 6}]}
    res = v.validate(wf)
    check(res.ok, f"war-footing-like validates (warn, not reject): {res.errors}")
    check(any("inflame" in w for w in res.warnings), f"should flag dominance over inflame: {res.warnings}")
    # the strength_temp fix is a DIFFERENT status key, so it does not dominate inflame
    wflex = {"id": "wflex_test", "name": "WFlex", "type": "skill", "rarity": "uncommon", "cost": 1,
             "target": "self", "effects": [{"op": "apply_status", "status": "strength_temp", "amount": 3},
                                            {"op": "block", "amount": 5}]}
    check(not any("inflame" in w for w in v.validate(wflex).warnings),
          "temp-Strength version must NOT dominate inflame")
    # target-aware: a single-target attack must NOT be judged to dominate an AoE attack
    st = {"id": "st_test", "name": "ST", "type": "attack", "rarity": "common", "cost": 1,
          "target": "enemy", "effects": [{"op": "damage", "amount": 20}]}
    check(not any("cleave" in w for w in v.validate(st).warnings),
          "single-target attack must not dominate AoE cleave")


def test_permanence_tripwire(v: CardValidator) -> None:
    print("permanence tripwire flags cheap permanent buffs on non-powers:")
    base = {"id": "perm_test", "name": "PT", "type": "skill", "rarity": "uncommon", "cost": 1,
            "target": "self", "effects": [{"op": "apply_status", "status": "strength", "amount": 2}]}
    check(any("permanent" in w for w in v.validate(base).warnings), "permanent-Str skill should warn")
    check(not any("permanent" in w for w in v.validate({**base, "id": "p_pow", "type": "power"}).warnings),
          "power is exempt")
    check(not any("permanent" in w for w in v.validate({**base, "id": "p_exh", "exhaust": True}).warnings),
          "exhaust is exempt")
    temp = {**base, "id": "p_temp",
            "effects": [{"op": "apply_status", "status": "strength_temp", "amount": 2}]}
    check(not any("permanent" in w for w in v.validate(temp).warnings), "strength_temp is exempt")


def test_rarity_floor(v: CardValidator) -> None:
    print("flat-rare floor warns, payoff rares don't:")
    flat = {"id": "t_flat_rare", "name": "Flat", "type": "attack", "rarity": "rare",
            "cost": 2, "target": "enemy", "effects": [{"op": "damage", "amount": 12}]}
    res = v.validate(flat)
    check(res.ok and any("flat rare" in w for w in res.warnings),
          f"plain 12-damage 2-cost rare should warn: {res.warnings}")
    big = {**flat, "id": "t_big_rare", "cost": 3, "effects": [{"op": "damage", "amount": 32}]}
    check(not any("flat rare" in w for w in v.validate(big).warnings),
          "Bludgeon-style simple-but-huge rare is fine")
    engine = {**flat, "id": "t_engine_rare",
              "effects": [{"op": "from_state", "emit": "damage", "value": {"state": "block"}}]}
    check(not any("flat rare" in w for w in v.validate(engine).warnings),
          "build-around (composite-op) rare is exempt")
    xcost = {**flat, "id": "t_x_rare", "cost": -1}
    check(not any("flat rare" in w for w in v.validate(xcost).warnings), "X-cost rare is exempt")
    common = {**flat, "id": "t_flat_common", "rarity": "common"}
    check(not any("flat rare" in w for w in v.validate(common).warnings),
          "the floor only applies to rares")


def test_reprint_gate(v: CardValidator) -> None:
    print("functional-reprint gate (the Inflame-clone fix):")
    clone = {"id": "hot_yoga", "name": "Hot Yoga", "type": "power", "rarity": "uncommon",
             "cost": 1, "target": "self", "source": "llm",
             "effects": [{"op": "apply_status", "status": "strength", "amount": 2}]}
    res = v.validate(clone)
    check(not res.ok and any("inflame" in e for e in res.errors),
          f"an uncommon Inflame clone must reject and name inflame: {res.errors}")

    nudged = dict(clone, id="hot_yoga_2",
                  effects=[{"op": "apply_status", "status": "strength", "amount": 3}])
    check(not v.validate(nudged).ok, "a +3-Strength nudge of Inflame must still reject")

    common = dict(clone, id="hot_yoga_3", rarity="common")
    res = v.validate(common)
    check(res.ok and any("reprint" in w for w in res.warnings),
          f"a common clone warns, not rejects: {res.errors or res.warnings}")

    check(v.validate(dict(clone, id="hot_yoga_4", rarity="basic")).ok,
          "basics are exempt (every class reprints its starters by rule)")

    authored = dict(clone, id="hot_yoga_5")
    authored.pop("source")
    check(v.validate(authored).ok, "authored provenance is never judged for reprints")

    # effect ORDER is not identity: iron_wave with its two effects swapped is still iron_wave
    swapped = {"id": "wave_iron", "name": "Wave Iron", "type": "attack", "rarity": "uncommon",
               "cost": 1, "target": "enemy", "source": "llm",
               "effects": [{"op": "damage", "amount": 5}, {"op": "block", "amount": 5}]}
    res = v.validate(swapped)
    check(not res.ok and any("iron_wave" in e for e in res.errors),
          f"reordered iron_wave must still read as a reprint: {res.errors}")

    # same skeleton with genuinely different numbers is allowed, with a review note
    scaled = {"id": "mega_flurry", "name": "Mega Flurry", "type": "attack", "rarity": "rare",
              "cost": 2, "target": "enemy", "source": "llm",
              "effects": [{"op": "multi", "times": 6, "effects": [{"op": "damage", "amount": 8}]}]}
    res = v.validate(scaled)
    check(res.ok and any("skeleton" in w for w in res.warnings),
          f"a scaled-up multi rare passes with a skeleton note: {res.errors or res.warnings}")


def test_loop_tripwire(v: CardValidator) -> None:
    print("loop discipline flags one-card engines (warn, not reject):")
    base = {"id": "rose_loop", "name": "RL", "type": "skill", "rarity": "basic", "cost": 0,
            "target": "none", "source": "llm",
            "effects": [{"op": "add_card", "card_id": "rose_loop", "pile": "hand", "amount": 2}]}
    res = v.validate(base)
    check(res.ok, f"self-copy card still validates (warn, never reject): {res.errors}")
    check(any("one-card engine" in w for w in res.warnings),
          f"free self-copy to hand should warn: {res.warnings}")

    anger_style = dict(base, id="rl_discard",
                       effects=[{"op": "add_card", "card_id": "rl_discard", "pile": "discard"}])
    check(not any("one-card engine" in w for w in v.validate(anger_style).warnings),
          "the Anger pattern (copy to discard) is sanctioned")

    exhausting = dict(base, id="rl_exhaust", exhaust=True,
                      effects=[{"op": "add_card", "card_id": "rl_exhaust", "pile": "hand"}])
    check(not any("one-card engine" in w for w in v.validate(exhausting).warnings),
          "exhaust prices the loop")

    expensive = dict(base, id="rl_pricey", cost=2,
                     effects=[{"op": "add_card", "card_id": "rl_pricey", "pile": "hand"}])
    check(not any("one-card engine" in w for w in v.validate(expensive).warnings),
          "a 2-energy iteration is expensive enough")

    refund = dict(base, id="rl_refund", cost=2,
                  effects=[{"op": "add_card", "card_id": "rl_refund", "pile": "hand"},
                           {"op": "gain_energy", "amount": 2}])
    check(any("one-card engine" in w for w in v.validate(refund).warnings),
          "an energy refund makes the loop free again")


def main() -> int:
    v = CardValidator()
    for t in (test_all_authored_cards_validate, test_scores_match_engine,
              test_hard_rejects, test_overpowered_warns_not_rejects,
              test_self_reference_allowed, test_dominance_check, test_permanence_tripwire,
              test_rarity_floor, test_reprint_gate, test_loop_tripwire):
        t(v)
    print(f"\n{_PASS} passed, {_FAIL} failed")
    return 1 if _FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
