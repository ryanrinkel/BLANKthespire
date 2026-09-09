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



# --------------------------------------------------------------- W2.2: widen the menus, gate by class kind
class _V2:
    """Toggle BTS_HARNESS_V2 for one block (the flag is read at call time)."""

    def __init__(self, on: bool) -> None:
        self.on = on
        self.saved = None

    def __enter__(self):
        import os
        self.saved = os.environ.get("BTS_HARNESS_V2")
        if self.on:
            os.environ["BTS_HARNESS_V2"] = "1"
        else:
            os.environ.pop("BTS_HARNESS_V2", None)
        return self

    def __exit__(self, *a):
        import os
        if self.saved is None:
            os.environ.pop("BTS_HARNESS_V2", None)
        else:
            os.environ["BTS_HARNESS_V2"] = self.saved


def _w2_keys() -> list[str]:
    """The keys W2.2 ADDED (the v1 when keys + hand_size_ge pre-date it)."""
    old_when = {k for k, _ in coverage.WHEN_MENU} | {"hand_size_ge"}
    return ([k for k, _ in coverage.WHEN_MENU_V2 if k not in old_when] + [k for k, _d, _k in coverage.WHEN_MENU_KIND]
            + [k for k, _ in coverage.SCALE_MENU] + [k for k, _d, _k in coverage.SCALE_MENU_KIND]
            + [k for k, _ in coverage.EXOTIC_NOMINATE_ONLY] + [k for k, _ in coverage.KEYWORD_MENU])


def test_w2_menu_keys_wired() -> None:
    print("W2.2: every new menu key has a directive, a census detector, and a DIRECTIVE_BY_KEY entry:")
    from btsgen import census
    when_keys = {k for k, _ in coverage.WHEN_MENU_V2}
    for need in ("retained_last_turn", "draw_pile_empty", "hp_lost_ge", "target_has_status"):
        check(need in when_keys, f"WHEN_MENU_V2 carries {need}")
    check({k for k, _d, _k in coverage.WHEN_MENU_KIND} == {"forged_ge", "dark_ge", "light_ge", "centered",
                                                           "orbs_match", "orb_count_ge"}, "the gated when keys")
    check({k for k, _ in coverage.SCALE_MENU} == {"cards_in_hand", "cards_retained", "unspent_energy_last_turn",
                                                  "target_debuff_count", "damage_dealt_unblocked"}, "the scale menu")
    check({k for k, _d, _k in coverage.SCALE_MENU_KIND} == {"tag_cards_owned", "forged"}, "the gated scale keys")
    check({k for k, _ in coverage.EXOTIC_NOMINATE_ONLY} == {"ritual", "barricade", "intangible"}, "nominate-only exotics")
    check({k for k, _ in coverage.KEYWORD_MENU} == {"retain", "innate", "ethereal", "hits"}, "the keyword menu")
    check(coverage.MIN_KEYWORD_KINDS == 2, "MIN_KEYWORD_KINDS = 2")
    check(coverage.KEY_KIND == {"forged_ge": "forge", "dark_ge": "balance", "light_ge": "balance",
                                "centered": "balance", "orbs_match": "orb", "orb_count_ge": "orb",
                                "tag_cards_owned": "tags", "forged": "forge"}, f"KEY_KIND, got {coverage.KEY_KIND}")
    for key in _w2_keys():
        d = coverage.DIRECTIVE_BY_KEY.get(key)
        check(isinstance(d, str) and d.startswith("REQUIRED:") and key in d,
              f"'{key}' has a REQUIRED directive naming the key")
        check(key in coverage.CENSUS_DETECTOR, f"'{key}' has a census detector")
        check(coverage.directive_key(d) == key, f"directive_key round-trips '{key}'")
    # the detectors fire on the right census shape and not on a plain card
    plain = census.walk_card({"id": "p", "cost": 1, "effects": [{"op": "damage", "amount": 6}]})
    samples = {
        "retained_last_turn": {"op": "damage", "amount": 6, "when": {"kind": "retained_last_turn"}},
        "draw_pile_empty": {"op": "damage", "amount": 30, "when": {"kind": "draw_pile_empty"}},
        "hp_lost_ge": {"op": "damage", "amount": 18, "when": {"kind": "hp_lost_ge", "value": 3}},
        "target_has_status": {"op": "damage", "amount": 9, "when": {"kind": "target_has_status", "status": "vulnerable"}},
        "forged_ge": {"op": "damage", "amount": 9, "when": {"kind": "forged_ge", "value": 5}},
        "dark_ge": {"op": "damage", "amount": 9, "when": {"kind": "dark_ge", "value": 3}},
        "light_ge": {"op": "block", "amount": 9, "when": {"kind": "light_ge", "value": 3}},
        "centered": {"op": "draw", "amount": 2, "when": {"kind": "centered", "value": 1}},
        "orbs_match": {"op": "damage", "amount": 9, "when": {"kind": "orbs_match"}},
        "orb_count_ge": {"op": "damage", "amount": 9, "when": {"kind": "orb_count_ge", "value": 2}},
        "cards_in_hand": {"op": "damage", "amount": 1, "scale": "cards_in_hand"},
        "cards_retained": {"op": "block", "amount": 1, "scale": "cards_retained"},
        "unspent_energy_last_turn": {"op": "draw", "amount": 1, "scale": "unspent_energy_last_turn"},
        "target_debuff_count": {"op": "damage", "amount": 1, "scale": "target_debuff_count"},
        "damage_dealt_unblocked": {"op": "heal", "amount": 1, "scale": "damage_dealt_unblocked"},
        "tag_cards_owned": {"op": "damage", "amount": 6, "scale": "tag_cards_owned", "tag": "strike"},
        "forged": {"op": "damage", "amount": 6, "scale": "forged"},
        "ritual": {"op": "apply_status", "status": "ritual", "amount": 1},
        "barricade": {"op": "apply_status", "status": "barricade", "amount": 1},
        "intangible": {"op": "apply_status", "status": "intangible", "amount": 1},
        "retain": {"op": "retain"}, "innate": {"op": "innate"}, "ethereal": {"op": "ethereal"},
        "hits": {"op": "damage", "amount": 4, "hits": 3},
    }
    check(set(samples) == set(_w2_keys()), "a sample exists for every W2.2 key")
    for key, eff in samples.items():
        cc = census.walk_card({"id": key, "cost": 1, "effects": [eff]})
        check(coverage.CENSUS_DETECTOR[key](cc), f"detector '{key}' fires on its shape")
        check(not coverage.CENSUS_DETECTOR[key](plain), f"detector '{key}' is silent on a plain card")


def test_w2_nominations_and_gating() -> None:
    print("W2.2: sanitize_nominations knows scale/keyword; gated keys need the class kind:")
    got = coverage.sanitize_nominations({"scale": ["forged", "bogus", "cards_in_hand", "target_debuff_count"],
                                         "keyword": ["hits", "retain", "innate"],
                                         "exotic": ["ritual", "intangible"], "when": ["forged_ge", "orbs_match"]})
    check(got["scale"] == ["forged", "cards_in_hand"], f"scale nominations capped at 2, unknown dropped: {got}")
    check(got["keyword"] == ["hits", "retain"], f"keyword nominations capped at 2: {got}")
    check(got["exotic"] == ["ritual", "intangible"], "nominate-only exotics are nominatable")
    check(got["when"] == ["forged_ge", "orbs_match"], "gated when keys are nominatable")
    check(coverage.NOMINATION_CATEGORIES == ("reactive", "when", "exotic", "scale", "keyword", "sections"),
          "nomination categories")
    with _V2(True):
        # shuffled default: gated entries appear ONLY for the matching kind set
        _r, when_normal, _x = coverage._menus(None, 7, kinds={""})
        _r, when_forge, _x = coverage._menus(None, 7, kinds={"", "forge"})
        _r, when_none, _x = coverage._menus(None, 7, kinds=None)
        keys_normal = {k for k, _ in when_normal}
        keys_forge = {k for k, _ in when_forge}
        check("forged_ge" not in keys_normal and "orbs_match" not in keys_normal, "a normal class gets no gated when")
        check("forged_ge" in keys_forge and "dark_ge" not in keys_forge, "a forge class gets forged_ge only")
        check(not ({k for k, _ in when_none} & set(coverage.KEY_KIND)), "kinds=None deals no gated entry")
        scale_tags, kw = coverage._menus_w2(None, 7, kinds={"", "tags"})
        check({k for k, _ in scale_tags} == {k for k, _ in coverage.SCALE_MENU} | {"tag_cards_owned"},
              "a tags class gets tag_cards_owned on the scale menu")
        check({k for k, _ in kw} == {k for k, _ in coverage.KEYWORD_MENU}, "the keyword menu is dealt whole")
        # a nominated gated key on the WRONG class kind is dropped
        _r, when_nom, _x = coverage._menus({"when": ["forged_ge", "no_block"]}, 7, kinds={""})
        check([k for k, _ in when_nom] == ["no_block"], f"forged_ge dropped on a normal class: {when_nom}")
        _r, when_nom2, _x = coverage._menus({"when": ["forged_ge", "no_block"]}, 7, kinds={"", "forge"})
        check([k for k, _ in when_nom2] == ["forged_ge", "no_block"], "forged_ge kept on a forge class")
        # the shuffled exotic menu NEVER deals a nominate-only exotic; nominations can
        for seed in range(20):
            _r, _w, ex = coverage._menus(None, seed, kinds={""})
            check(not ({k for k, _ in ex} & {"ritual", "barricade", "intangible"}), "shuffle never deals ritual/barricade/intangible")
        _r, _w, ex_nom = coverage._menus({"exotic": ["ritual"]}, 1, kinds={""})
        check([k for k, _ in ex_nom] == ["ritual"], "a nominated ritual is reachable")
    with _V2(False):
        check(coverage._menus_w2(None, 1, kinds={"", "forge"}) == ([("scale", coverage.SCALE_DIRECTIVE)], []),
              "v1: the one fixed scale directive and NO keyword menu (byte-for-byte baseline)")
        check(coverage._menus(None, 1, kinds={"", "forge"}) == (coverage.REACTIVE_MENU, coverage.WHEN_MENU, coverage.EXOTIC_MENU),
              "v1: the fixed menus ignore kinds")


def test_w2_repair_walks_new_menus() -> None:
    print("W2.2: plan_repairs walks the scale + keyword menus (v2) and the keyword quota is v2-only:")
    from btsgen import census
    rep = coverage.measure(_pool())
    with _V2(False):
        check(not any("keyword" in v for v in rep.violations), "v1: no keyword violation")
        d1 = coverage.plan_repairs(rep)
        check(len(d1) == 4, f"v1 plan unchanged (4 directives), got {len(d1)}")
    with _V2(True):
        rep2 = coverage.measure(_pool())
        check(rep2.keyword_kinds == set() and any("keyword kind(s) < 2" in v for v in rep2.violations),
              f"v2: the keyword quota is measured + violated on the plain pool: {rep2.violations}")
        check(rep2.scale_kinds == {"cards_in_hand"}, f"scale kinds measured: {rep2.scale_kinds}")
        # nominate scale + keyword: the plan honors them, in order, and projects the keyword kinds forward
        nom = coverage.sanitize_nominations({"reactive": ["on_hp_lost"], "when": ["no_block", "has_block"],
                                             "exotic": ["regen"], "scale": ["target_debuff_count"],
                                             "keyword": ["hits", "ethereal"]})
        d2 = coverage.plan_repairs(rep2, budget=12, nominated=nom, seed=3, kinds={""})
        keys = [coverage.directive_key(d) for d in d2]
        check("hits" in keys and "ethereal" in keys, f"both nominated keywords requested: {keys}")
        check("target_debuff_count" not in keys, f"scale quota already met (F_scaled) -> no scale directive: {keys}")
        # a pool with one keyword already: only ONE more keyword directive
        made = _pool() + [_m("common", [{"op": "damage", "amount": 4, "hits": 3}], name="MH")]
        rep3 = coverage.measure(made)
        check(rep3.keyword_kinds == {census.MULTI_HIT_KIND}, "multi-hit counted as a keyword kind")
        d3 = coverage.plan_repairs(rep3, budget=12, nominated=nom, seed=3, kinds={""})
        keys3 = [coverage.directive_key(d) for d in d3]
        check(keys3.count("hits") == 0 and keys3.count("ethereal") == 1,
              f"a present keyword kind is not re-requested; one more fills the quota: {keys3}")
        # scale quota short + no nomination: the shuffled scale menu supplies a real source (never the v1 "scale")
        no_scale = [m for m in _pool() if m["card"]["name"] != "F_scaled"]
        rep4 = coverage.measure(no_scale)
        d4 = coverage.plan_repairs(rep4, budget=12, seed=5, kinds={"", "forge"})
        keys4 = [coverage.directive_key(d) for d in d4]
        scale_keys = {k for k, _ in coverage.SCALE_MENU} | {"forged"}
        check(len(set(keys4) & scale_keys) == 1 and "scale" not in keys4, f"one scale-menu source requested: {keys4}")
        # enforce_coverage plumbs `kinds` through and streams the keyword count
        log: list[str] = []
        s = coverage.enforce_coverage(_pool(), lambda p, o, d: None, log.append, seed=5, kinds={""})
        check(any("keywords 0 (min 2)" in l for l in log), "the v2 summary line carries the keyword count")
        check(s["attempted"] > 0, "repairs attempted")


def main() -> int:
    test_measure_math()
    test_measure_clean_pool()
    test_plan_repairs()
    test_victim_selection()
    test_enforce_plumbing()
    test_w2_menu_keys_wired()
    test_w2_nominations_and_gating()
    test_w2_repair_walks_new_menus()
    print(f"\n{_PASS} passed, {_FAIL} failed")
    return 1 if _FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
