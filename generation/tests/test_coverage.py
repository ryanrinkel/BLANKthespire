"""Offline tests for btsgen/coverage.py — set-level breadth quotas + bounded repair. No API key needed.

Run:  uv run python -m tests.test_coverage     (from generation/)
Exits nonzero on any failure. Covers: measure() census math over the non-basic pool (reprint exempt from
plain-share), quota-violation detection, plan_repairs directive selection (deficit-driven, budget-capped),
victim selection (protected roles NEVER picked, plain-first), and the enforce_coverage repair plumbing with
a controlled stub generator. Per the plan, we assert PLUMBING, not quota outcomes under a real generator.
"""
from __future__ import annotations

import sys

from btsgen.class_forge import point_btsgen_at_mod_contract

point_btsgen_at_mod_contract()

from btsgen import coverage  # noqa: E402
from btsgen.class_forge import _BASIC_ROLES, _BLADE_ROLE  # noqa: E402

_PASS = 0
_FAIL = 0


def check(cond: bool, msg: str) -> None:
    global _PASS, _FAIL
    if cond:
        _PASS += 1
    else:
        _FAIL += 1
        print(f"  FAIL: {msg}")


def _m(role, effects, *, rarity="common", theme="", token=False, card_id=None, name=None, cost=1, bridge=False):
    plan = {"role": role, "rarity": rarity, "theme": theme, "type": "skill", "cost": cost}
    if bridge:
        plan["bridge"] = True
    card = {"id": card_id or f"c_{name or role}", "name": name or role, "type": "skill",
            "rarity": rarity, "cost": cost, "target": "self", "effects": effects}
    if token:
        card["token"] = True
    return {"plan": plan, "card": card}


def _pool():
    """A deterministic mixed pool (2 basics + a blade token excluded; 6 pool cards + 1 reprint)."""
    return [
        _m("basic_attack", [{"op": "damage", "amount": 6}], rarity="basic", name="Strike"),
        _m("basic_skill", [{"op": "block", "amount": 5}], rarity="basic", name="Defend"),
        _m(_BLADE_ROLE, [{"op": "damage", "amount": 6, "scale": "forged"}], rarity="basic", token=True, name="Blade"),
        _m("common", [{"op": "damage", "amount": 6}], name="A_plain"),                                  # plain
        _m("common", [{"op": "damage", "amount": 5}, {"op": "apply_status", "status": "vulnerable", "amount": 1}], name="B_debuff"),  # plain+debuff
        _m("uncommon", [{"op": "add_trigger", "trigger": "attacked", "effects": [{"op": "damage", "amount": 4}]}], name="C_reactive"),  # reactive
        _m("uncommon", [{"op": "damage", "amount": 8, "when": {"kind": "hp_below_half"}}], name="D_when"),  # when
        _m("common", [{"op": "apply_status", "status": "thorns", "amount": 3}], name="E_exotic"),         # plain + exotic
        _m("rare", [{"op": "damage", "amount": 1, "scale": "cards_in_hand"}], rarity="rare", name="F_scaled"),  # scaled
        _m("common", [{"op": "damage", "amount": 8}, {"op": "apply_status", "status": "vulnerable", "amount": 2}],
           theme="Reprint of Bash (base game): a heavy hit that exposes", name="R_reprint"),              # reprint (exempt)
    ]


def test_measure_math() -> None:
    print("measure(): census math + violations over the non-basic pool:")
    rep = coverage.measure(_pool())
    check(rep.pool_size == 7, f"7 measurable cards (basics+blade excluded), got {rep.pool_size}")
    check(rep.plain_denom == 6, f"plain denom excludes the reprint -> 6, got {rep.plain_denom}")
    check(rep.plain == 3, f"3 plain among denom (A,B,E), got {rep.plain}")
    check(abs(rep.plain_share - 0.5) < 1e-9, f"plain share 0.5, got {rep.plain_share}")
    check(rep.reactive_kinds == {"attacked"}, f"reactive {rep.reactive_kinds}")
    check(rep.when_kinds == {"hp_below_half"}, f"when {rep.when_kinds}")
    check(rep.exotic_kinds == {"thorns"}, f"exotic {rep.exotic_kinds}")
    check(rep.generic_debuff_cards == 2, f"debuff cards B+reprint = 2, got {rep.generic_debuff_cards}")
    check(rep.scaled_or_x == 1, f"one scaled card (F), got {rep.scaled_or_x}")
    # violations: plain, reactive, when, exotic, debuff all short; scaled OK
    joined = " | ".join(rep.violations)
    check("plain share" in joined, f"plain-share violation present: {joined}")
    check("reactive" in joined and "when" in joined and "exotic" in joined, f"kind violations present: {joined}")
    check("generic-debuff" in joined, f"debuff violation present: {joined}")
    check(not any("scaled/X" in v for v in rep.violations), f"scaled quota met (no violation): {rep.violations}")


def test_measure_clean_pool() -> None:
    print("measure(): a rich pool trips no violations:")
    made = [
        _m("common", [{"op": "add_trigger", "trigger": "attacked", "effects": [{"op": "damage", "amount": 4}]}], name="r1"),
        _m("common", [{"op": "add_trigger", "trigger": "on_hp_lost", "effects": [{"op": "block", "amount": 3}]}], name="r2"),
        _m("common", [{"op": "damage", "amount": 6, "when": {"kind": "hp_below_half"}}], name="w1"),
        _m("common", [{"op": "block", "amount": 6, "when": {"kind": "turn_at_least"}}], name="w2"),
        _m("common", [{"op": "damage", "amount": 6, "when": {"kind": "enemy_count_ge"}, "target": "all_enemies"}], name="w3"),
        _m("common", [{"op": "apply_status", "status": "thorns", "amount": 3, "when": {"kind": "no_block"}}], name="x1"),
        _m("common", [{"op": "apply_status", "status": "metallicize", "amount": 3, "when": {"kind": "has_block"}}], name="x2"),
        _m("common", [{"op": "damage", "amount": 1, "scale": "cards_in_hand"}], name="s1"),
    ]
    rep = coverage.measure(made)
    check(not rep.violations, f"a rich pool has no violations, got {rep.violations}")


def test_plan_repairs() -> None:
    print("plan_repairs(): deficit-driven, budget-capped directive list:")
    rep = coverage.measure(_pool())
    directives = coverage.plan_repairs(rep)
    # reactive needs +1, when needs +2, exotic needs +1  => 4 directives; plain resolves via those
    check(len(directives) == 4, f"4 directives (1 reactive, 2 when, 1 exotic), got {len(directives)}: {directives}")
    joined = " ".join(directives)
    check("on_hp_lost" in joined, "a reactive directive was added")
    check("turn_at_least" in joined and "enemy_count_ge" in joined, "two new when directives added")
    check("metallicize" in joined or "regen" in joined or "temp_strength" in joined, "an exotic directive added")
    check(not any("attacked" in d for d in directives), "does not re-request a reactive kind already present")

    # budget clamps the list
    tiny = coverage.plan_repairs(rep, budget=2)
    check(len(tiny) == 2, f"budget=2 clamps directives to 2, got {len(tiny)}")


def test_victim_selection() -> None:
    print("victim_indices(): protected roles never picked, plain-first:")
    made = _pool()
    victims = coverage.victim_indices(made)
    names = [made[i]["card"]["name"] for i in victims]
    # protected: the 2 basics, the blade token, and the reprint must never appear
    for forbidden in ("Strike", "Defend", "Blade", "R_reprint"):
        check(forbidden not in names, f"protected card '{forbidden}' never a victim; victims={names}")
    # plain cards come first; the plain+debuff card (B) sorts ahead of the other plain cards
    check(names and names[0] == "B_debuff", f"plain+debuff victim first, got {names}")
    check(set(names[:3]) == {"A_plain", "B_debuff", "E_exotic"}, f"the 3 plain cards lead: {names}")

    # a bridge-tagged card is protected too
    made2 = _pool() + [_m("common", [{"op": "damage", "amount": 6}], name="Br", bridge=True)]
    check("Br" not in [made2[i]["card"]["name"] for i in coverage.victim_indices(made2)],
          "a bridge-tagged card is protected from unrelated repairs")


def test_enforce_plumbing() -> None:
    print("enforce_coverage(): repair plumbing with a controlled stub generator:")
    made = _pool()
    log: list[str] = []

    calls: list[tuple] = []

    def stub_regen(plan, old_card, directive):
        # a controlled "good" repair: a distinctive non-plain card carrying a reactive engine
        calls.append((old_card.get("name"), directive))
        return {"id": f"fixed_{len(calls)}", "name": f"Fixed{len(calls)}", "type": "skill", "rarity": "common",
                "cost": 1, "target": "self",
                "effects": [{"op": "add_trigger", "trigger": "on_card_played", "once_per_turn": True,
                             "effects": [{"op": "block", "amount": 3}]}]}

    summary = coverage.enforce_coverage(made, stub_regen, log.append)
    check(summary["repaired"] == 4, f"4 victims repaired (min of directives, victims), got {summary['repaired']}")
    check(len(calls) == 4, f"regen called once per repair, got {len(calls)}")
    # the victims that changed are the plain-first ones; the reprint/basics/blade are untouched
    for m in made:
        if m["plan"].get("role") in _BASIC_ROLES or m["card"].get("token"):
            check(not m["card"]["id"].startswith("fixed_"), "a basic/blade was never swapped")
    check(any("coverage: pool" in l for l in log), "a before-summary line was streamed")
    check(any(l.startswith("coverage repair:") for l in log), "per-repair lines were streamed")

    # a stub that always fails: 0 repaired, graceful notes, no crash
    made2 = _pool()
    log2: list[str] = []
    s2 = coverage.enforce_coverage(made2, lambda p, o, d: None, log2.append)
    check(s2["repaired"] == 0, f"no repairs when the generator fails, got {s2['repaired']}")
    check(any("could not be improved" in l for l in log2), "failed repairs are noted, not fatal")

    # a clean pool: no repair attempted
    clean = [
        _m("common", [{"op": "add_trigger", "trigger": "attacked", "effects": [{"op": "damage", "amount": 4}]}], name="r1"),
        _m("common", [{"op": "add_trigger", "trigger": "on_hp_lost", "effects": [{"op": "block", "amount": 3}]}], name="r2"),
        _m("common", [{"op": "damage", "amount": 6, "when": {"kind": "hp_below_half"}}], name="w1"),
        _m("common", [{"op": "block", "amount": 6, "when": {"kind": "turn_at_least"}}], name="w2"),
        _m("common", [{"op": "damage", "amount": 6, "when": {"kind": "no_block"}}], name="w3"),
        _m("common", [{"op": "apply_status", "status": "thorns", "amount": 3}], name="x1"),
        _m("common", [{"op": "apply_status", "status": "metallicize", "amount": 3, "when": {"kind": "has_block"}}], name="x2"),
        _m("common", [{"op": "damage", "amount": 1, "scale": "cards_in_hand"}], name="s1"),
    ]
    log3: list[str] = []
    s3 = coverage.enforce_coverage(clean, lambda p, o, d: None, log3.append)
    check(s3["attempted"] == 0 and any("quotas met" in l for l in log3), "a clean pool skips repair")


def main() -> int:
    test_measure_math()
    test_measure_clean_pool()
    test_plan_repairs()
    test_victim_selection()
    test_enforce_plumbing()
    print(f"\n{_PASS} passed, {_FAIL} failed")
    return 1 if _FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
