"""Offline tests for the Phase 1 TRIAD experiment — the three-archetype creative path. No API key needed.

Run:  uv run python -m tests.test_triad     (from generation/)
Exits nonzero on any failure. Covers: the triad_enabled() mode switch (env + override), the mode-dependent
pool targets (9/16/7 vs 7/12/4), the harness-version stamp, the triad prompt (system-prompt override block +
pool ask), _strategy_coverage's all-three-lines floor, the forge-class one-signature cap rule at the 32-pool
target, and the coverage round routing bridge repairs per DECLARED pair. Per the plan we assert PLUMBING, not
real-generator outcomes; the legacy (2-archetype) path stays byte-for-byte unchanged (asserted here too).
"""
from __future__ import annotations

import copy
import os
import sys

from btsgen.class_forge import point_btsgen_at_mod_contract

point_btsgen_at_mod_contract()

from btsgen import bridges, coverage  # noqa: E402
from btsgen.class_forge import (HARNESS_VERSION, HARNESS_VERSION_TRIAD, MIN_BRIDGES_PER_PAIR,  # noqa: E402
                                TARGET_COMMONS, TARGET_COMMONS_TRIAD, TARGET_RARES, TARGET_RARES_TRIAD,
                                TARGET_UNCOMMONS, TARGET_UNCOMMONS_TRIAD, _BlueprintContract, _archetype_ids,
                                _bridge_pair, _pool_targets, _resolve_bridge_ctx, _strategy_coverage,
                                _topup_blueprint_briefs, _validate_blueprint, triad_enabled)

_PASS = 0
_FAIL = 0


def check(cond: bool, msg: str) -> None:
    global _PASS, _FAIL
    if cond:
        _PASS += 1
    else:
        _FAIL += 1
        print(f"  FAIL: {msg}")


_TRIAD_IDS = ("forge_ramp", "counter_riposte", "poison_attrition")


def _triad_bp():
    seed = {
        "name": "Triforge", "description": "a three-engine test class", "max_hp": 72, "orb_slots": 0,
        "archetypes": [{"id": _TRIAD_IDS[0], "name": "Forge", "description": "stoke the forge"},
                       {"id": _TRIAD_IDS[1], "name": "Riposte", "description": "punish attackers"},
                       {"id": _TRIAD_IDS[2], "name": "Venom", "description": "stack poison"}],
        "cards": [
            {"role": "basic_attack", "name_hint": "Strike", "type": "attack", "rarity": "basic", "cost": 1,
             "deck_count": 5, "archetype": None, "theme": "Strike"},
            {"role": "basic_skill", "name_hint": "Defend", "type": "skill", "rarity": "basic", "cost": 1,
             "deck_count": 4, "archetype": None, "theme": "Defend"},
            {"role": "signature", "name_hint": "Core", "type": "attack", "rarity": "basic", "cost": 1,
             "deck_count": 1, "archetype": _TRIAD_IDS[0], "theme": "core"},
        ],
    }
    return _topup_blueprint_briefs(copy.deepcopy(seed), strategies=["aggro", "control", "combo"])


# --------------------------------------------------------------- the mode switch
def test_triad_enabled() -> None:
    print("triad_enabled(): env-driven default, explicit override wins:")
    saved = os.environ.pop("BTS_TRIAD", None)
    try:
        check(triad_enabled() is False, "no BTS_TRIAD -> off")
        check(triad_enabled(True) is True and triad_enabled(False) is False, "an override wins over the env")
        for on in ("1", "true", "TRUE", "yes", "on"):
            os.environ["BTS_TRIAD"] = on
            check(triad_enabled() is True, f"BTS_TRIAD={on!r} -> on")
        os.environ["BTS_TRIAD"] = "0"
        check(triad_enabled() is False, "BTS_TRIAD=0 -> off")
        check(triad_enabled(False) is False, "an override still wins when the env is set")
    finally:
        if saved is None:
            os.environ.pop("BTS_TRIAD", None)
        else:
            os.environ["BTS_TRIAD"] = saved


def test_harness_versions() -> None:
    print("the triad path stamps its own attributable harness version:")
    check(HARNESS_VERSION == "1.6-synergy-weave", "legacy version unchanged")
    check(HARNESS_VERSION_TRIAD == "1.7-triad-exp", "the triad experiment stamps 1.7-triad-exp")


# --------------------------------------------------------------- mode-dependent targets
def test_pool_targets() -> None:
    print("_pool_targets(): keyed off the archetype COUNT, not the flag (9/16/7 triad, 7/12/4 legacy):")
    c2, u2, r2, p2 = _pool_targets(2)
    check((c2, u2, r2) == (TARGET_COMMONS, TARGET_UNCOMMONS, TARGET_RARES) == (7, 12, 4),
          f"2 archetypes -> legacy 7/12/4: {(c2, u2, r2)}")
    c3, u3, r3, p3 = _pool_targets(3)
    check((c3, u3, r3) == (TARGET_COMMONS_TRIAD, TARGET_UNCOMMONS_TRIAD, TARGET_RARES_TRIAD) == (9, 16, 7),
          f"3 archetypes -> triad 9/16/7: {(c3, u3, r3)}")
    check(p3 == 32, f"the triad pool totals 32: {p3}")


def test_prompt_mode() -> None:
    print("the blueprint contract flexes with self.triad — legacy prompt is untouched, triad appends a block:")
    off = _BlueprintContract(triad=False)
    on = _BlueprintContract(triad=True)
    p_off, p_on = off.system_prompt(), on.system_prompt()
    check("TRIAD OVERRIDE" not in p_off, "the flag-off system prompt is exactly today's (no triad block)")
    check(p_on.startswith(p_off), "the triad system prompt is the legacy prompt PLUS an appended override")
    check("TRIAD OVERRIDE" in p_on and "trinity" in p_on.lower() and "pair_lines" in p_on,
          "the triad block states the pairwise-bridge/trinity-ban/pair->strategy rules")
    check("9 commons" in on._pool_ask() and "16 uncommons" in on._pool_ask() and "7 rares" in on._pool_ask(),
          f"the triad pool ask carries 9/16/7: {on._pool_ask()}")
    check("7 commons" in off._pool_ask() and "12 uncommons" in off._pool_ask(),
          "the legacy pool ask keeps 7/12/4")
    # default (no arg) reads the env — off by default in the suite
    saved = os.environ.pop("BTS_TRIAD", None)
    try:
        check("TRIAD OVERRIDE" not in _BlueprintContract().system_prompt(), "env-off default -> legacy prompt")
    finally:
        if saved is not None:
            os.environ["BTS_TRIAD"] = saved


# --------------------------------------------------------------- validation (count + coverage + cap)
def test_triad_validates_and_targets() -> None:
    print("_validate_blueprint(): accepts 2 OR 3 archetypes regardless of the flag; a clean triad passes:")
    bp = _triad_bp()
    check(len(bp["archetypes"]) == 3 and _validate_blueprint(bp) == [],
          f"a three-archetype blueprint validates: {_validate_blueprint(bp)}")
    # a one-archetype bp is still rejected (2 or 3 only)
    solo = copy.deepcopy(bp)
    solo["archetypes"] = solo["archetypes"][:1]
    check(any("2 or 3 archetypes" in e for e in _validate_blueprint(solo)), "1 archetype is rejected")


def test_all_three_lines_required() -> None:
    print("_strategy_coverage(): triad requires ALL THREE lines (min_lines=3), legacy two:")
    cards = [{"role": "pool", "strategy": "aggro", "rarity": "rare"},
             {"role": "pool", "strategy": "aggro", "rarity": "common"},
             {"role": "pool", "strategy": "aggro", "rarity": "common"},
             {"role": "pool", "strategy": "control", "rarity": "rare"},
             {"role": "pool", "strategy": "control", "rarity": "common"},
             {"role": "pool", "strategy": "control", "rarity": "common"}]
    check(_strategy_coverage(cards, min_lines=2)[0] == [], "two full lines satisfy the legacy floor")
    errs = _strategy_coverage(cards, min_lines=3)[0]
    check(any("at least 3 strategic lines" in e for e in errs),
          f"two lines fail the triad (3-line) floor: {errs}")
    # a real triad bp (three full lines) passes the 3-line floor
    bp = _triad_bp()
    check(_strategy_coverage(bp["cards"], min_lines=3)[0] == [],
          "a topped-up triad covers all three lines")


def test_forge_class_signature_cap() -> None:
    print("D4: a FORGE class at the 32-pool target takes ONE signature (blade + 2 sigs overflows the cap):")
    from btsgen.class_forge import _BLUEPRINT_CARD_CAP
    bp = _triad_bp()
    f = copy.deepcopy(bp)
    f["cards"].append({"role": "signature_blade", "name_hint": "Blade", "type": "attack", "rarity": "token",
                       "cost": 2, "deck_count": 0, "archetype": _TRIAD_IDS[0], "theme": "blade"})
    f["cards"].append({"role": "signature", "name_hint": "Core2", "type": "skill", "rarity": "basic",
                       "cost": 1, "deck_count": 1, "archetype": _TRIAD_IDS[1], "theme": "c2"})
    while len(f["cards"]) <= _BLUEPRINT_CARD_CAP:
        f["cards"].append({"role": "pool", "name_hint": "Pad", "type": "skill", "rarity": "common", "cost": 1,
                           "deck_count": 0, "archetype": None, "strategy": None, "theme": "pad"})
    errs = _validate_blueprint(f)
    check(any("forge class at 32-pool target" in e and "one signature" in e for e in errs),
          f"the forge-class cap rule names the fix: {[e for e in errs if 'forge class' in e]}")


# --------------------------------------------------------------- coverage per-pair routing
def _m(pair, effects, name, *, rarity="common"):
    return {"plan": {"role": rarity, "rarity": rarity, "type": "attack", "cost": 1, "bridge": pair},
            "card": {"id": "c_" + name, "name": name, "type": "attack", "rarity": rarity, "cost": 1,
                     "target": "enemy", "effects": effects}}


def test_coverage_routes_per_pair() -> None:
    print("enforce_coverage(): each triad bridge is witnessed + repaired against ITS OWN declared pair:")
    bp = {"name": "T", "description": "d",
          "archetypes": [{"id": _TRIAD_IDS[0], "name": "Forge"},
                         {"id": _TRIAD_IDS[1], "name": "Riposte"},
                         {"id": _TRIAD_IDS[2], "name": "Venom"}]}
    ctx = _resolve_bridge_ctx(bp)
    made = [
        {"plan": {"role": "basic_attack"}, "card": {"id": "s", "name": "Strike",
                                                    "effects": [{"op": "damage", "amount": 6}]}},
        {"plan": {"role": "basic_skill"}, "card": {"id": "d", "name": "Defend",
                                                   "effects": [{"op": "block", "amount": 5}]}},
        # a forge x riposte bridge touching only forge -> fails ITS pair
        _m([_TRIAD_IDS[0], _TRIAD_IDS[1]], [{"op": "forge", "amount": 2}], "ABhalf", rarity="rare"),
        # a forge x venom bridge fusing forge + poison -> passes ITS pair
        _m([_TRIAD_IDS[0], _TRIAD_IDS[2]],
           [{"op": "forge", "amount": 2}, {"op": "apply_status", "status": "poison", "amount": 3}], "ACok"),
    ]

    def regen(plan, old, directive):
        # only the Riposte-pair directive (the failing AB bridge) gets a witnessing replacement
        if "BRIDGE" in directive and "Riposte" in directive:
            return {"id": "fixed", "name": "Fixed", "type": "attack", "cost": 1, "target": "enemy",
                    "effects": [{"op": "forge", "amount": 2}, {"op": "apply_status", "status": "thorns", "amount": 3}]}
        return None

    log: list[str] = []
    summary = coverage.enforce_coverage(made, regen, log.append, bridge_ctx=ctx)
    check(summary["bridge_fail_before"] and not summary["bridge_fail_after"],
          f"the AB bridge fails against its OWN pair, then fuses: "
          f"{summary['bridge_fail_before']} -> {summary['bridge_fail_after']}")
    check(any("3 pair-lanes" in l for l in log), "the status line names the three pair-lanes")


def main() -> int:
    for t in (test_triad_enabled, test_harness_versions, test_pool_targets, test_prompt_mode,
              test_triad_validates_and_targets, test_all_three_lines_required,
              test_forge_class_signature_cap, test_coverage_routes_per_pair):
        t()
    print(f"\n{_PASS} passed, {_FAIL} failed")
    return 1 if _FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
