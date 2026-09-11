"""Offline tests for btsgen/featured.py — the featured-mechanic roulette (Phase N-2). No API key needed.

Run:  uv run python -m tests.test_featured     (from generation/)
Exits nonzero on any failure. Covers: seeded-roll reproducibility (per concept, never `random`), both
blueprint brief modes carrying the REQUIRED featured block, every detector round-tripping its own mechanic
(and NOT firing on a plain card), the rare-tier exclusion note, and the coverage round targeting a missing
featured mechanic with its own directive + WARNING.
"""
from __future__ import annotations

import sys

from btsgen.class_forge import point_btsgen_at_mod_contract

point_btsgen_at_mod_contract()

from btsgen import census, coverage, featured  # noqa: E402
from btsgen.class_forge import ClassBrief, _BlueprintContract  # noqa: E402

_PASS = 0
_FAIL = 0


def check(cond: bool, msg: str) -> None:
    global _PASS, _FAIL
    if cond:
        _PASS += 1
    else:
        _FAIL += 1
        print(f"  FAIL: {msg}")


def test_roll_reproducible() -> None:
    print("roll_featured(): deterministic per concept, N distinct, ids on the menu:")
    ids = {f.id for f in featured.FEATURED_MENU}
    a = featured.roll_featured("a storm-calling gambler")
    b = featured.roll_featured("a storm-calling gambler")
    check([f.id for f in a] == [f.id for f in b], f"same concept -> same picks: {[f.id for f in a]} vs {[f.id for f in b]}")
    check(len(a) == featured.N_FEATURED, f"rolls N_FEATURED={featured.N_FEATURED}, got {len(a)}")
    check(len({f.id for f in a}) == len(a), f"picks are distinct: {[f.id for f in a]}")
    check(all(f.id in ids for f in a), "picks are menu entries")
    # case/space-insensitive seeding
    c = featured.roll_featured("  A Storm-Calling Gambler  ")
    check([f.id for f in a] == [f.id for f in c], "seed ignores case + surrounding whitespace")
    # different concepts usually differ (sample a few; at least one pair differs)
    rolls = [tuple(f.id for f in featured.roll_featured(s)) for s in
             ("venom alchemist", "block turtle", "orb channeler", "berserker rage", "patient duelist")]
    check(len(set(rolls)) >= 3, f"different concepts spread across picks: {rolls}")


def test_themed_roll() -> None:
    print("themed_roll(): slot 1 resonant + wild rest, deterministic, order-proof, recency-damped:")
    concept = "a beekeeper who commands the swarm"
    short = ["token_conjure", "x_dump", "scry_filter"]
    menu_ids = {f.id for f in featured.FEATURED_MENU}
    a = featured.themed_roll(concept, short)
    b = featured.themed_roll(concept, short)
    check([f.id for f in a] == [f.id for f in b], "same concept + shortlist -> same picks")
    check(len(a) == featured.N_FEATURED and len({f.id for f in a}) == len(a),
          f"N distinct picks, got {[f.id for f in a]}")
    check(a[0].id in short, f"slot 1 comes from the resonant shortlist: {a[0].id}")
    check(all(f.id in menu_ids for f in a), "every pick is a menu entry")
    # the model re-ordering its nominations cannot change the draw (canonical menu order)
    c = featured.themed_roll(concept, list(reversed(short)))
    check([f.id for f in a] == [f.id for f in c], "shortlist ordering does not change the picks")
    # empty / unknown shortlist -> all-wild fallback, still N picks off the menu
    d = featured.themed_roll(concept, ["not_a_mechanic"])
    check(len(d) == featured.N_FEATURED and all(f.id in menu_ids for f in d),
          "unknown shortlist -> wild fallback still rolls N menu picks")
    check(len(featured.themed_roll(concept, [])) == featured.N_FEATURED, "empty shortlist -> wild fallback")
    # recency damping: a heavily-used shortlist favorite gets displaced (weight 1000 -> ~9), never banned
    heavy = {a[0].id: 100.0}
    e = featured.themed_roll(concept, short, recent=heavy)
    check(e[0].id != a[0].id and e[0].id in short,
          f"recency-damped favorite displaced within the shortlist: {a[0].id} -> {e[0].id}")
    # different concepts spread the resonant pick across the same shortlist
    rolls = {featured.themed_roll(s, short)[0].id for s in
             ("a beekeeper", "a hive tyrant", "a honey merchant", "a wasp queen", "a pollen shaman")}
    check(len(rolls) >= 2, f"the lottery spreads slot 1 across the shortlist: {rolls}")
    # menu_block lists every id (the cloud stage's rating surface)
    mb = featured.menu_block()
    check(all(f"- {i}:" in mb for i in menu_ids), "menu_block carries every menu id")


def test_brief_blocks() -> None:
    print("both brief modes carry the REQUIRED featured block:")
    feats = featured.roll_featured("a tidal warden")
    ids = [f.id for f in feats]
    # concept mode
    c = _BlueprintContract(triad=False)  # concept mode, pinned to the legacy 2-arch prompt shape
    cb = ClassBrief(concept="a tidal warden", featured=ids)
    concept_brief = c.user_brief(cb)
    check("FEATURED MECHANICS (REQUIRED)" in concept_brief, "concept brief carries the featured block")
    check(all(f.injection.split("(")[0].strip()[:20] in concept_brief for f in feats),
          "concept brief renders each rolled injection line")

    # dossier mode
    from btsgen.frontend.dossier import Candidate, DossierBrief
    cand = Candidate(name="The Warden", fantasy="turn the tide", archetype_ids=["block_bulwark", "counter_riposte"],
                     archetype_descs=["turtle", "riposte"], class_kind="normal", suggested_max_hp=74,
                     strategic_lines=[{"strategy": "control", "line": "hold", "win_condition": "counter"}])
    db = DossierBrief(candidate=cand, concept="a tidal warden", featured=ids)
    dossier_brief = _BlueprintContract(mode="dossier", triad=False).user_brief(db)
    check("FEATURED MECHANICS (REQUIRED)" in dossier_brief, "dossier brief carries the featured block")

    # no featured -> no block, no crash
    check("FEATURED MECHANICS" not in c.user_brief(ClassBrief(concept="x")), "no featured -> no block")
    check(featured.injection_block(None) == "" and featured.injection_block([]) == "", "empty ids -> empty block")


def _card(effects, cost=1):
    return {"id": "t", "name": "T", "type": "skill", "rarity": "common", "cost": cost, "target": "self",
            "effects": effects}


def test_detectors_round_trip() -> None:
    print("every detector fires on its own mechanic and NOT on a plain card:")
    samples = {
        "reactive_played": _card([{"op": "add_trigger", "trigger": "on_card_played", "once_per_turn": True,
                                   "effects": [{"op": "block", "amount": 3}]}]),
        "reactive_drawn": _card([{"op": "add_trigger", "trigger": "on_card_drawn", "effects": [{"op": "block", "amount": 2}]}]),
        "reactive_damage": _card([{"op": "add_trigger", "trigger": "on_damage_dealt", "effects": [{"op": "block", "amount": 2}]}]),
        "reactive_block": _card([{"op": "add_trigger", "trigger": "on_block_gained", "effects": [{"op": "draw", "amount": 1}]}]),
        "counterattack": _card([{"op": "add_trigger", "trigger": "attacked", "effects": [{"op": "damage", "amount": 4, "target": "enemy"}]}]),
        "blood_engine": _card([{"op": "add_trigger", "trigger": "on_hp_lost", "effects": [{"op": "block", "amount": 3}]}]),
        "long_fuse": _card([{"op": "add_trigger", "trigger": "ripen", "amount": 2, "effects": [{"op": "damage", "amount": 20}]}]),
        "late_game": _card([{"op": "damage", "amount": 8, "when": {"kind": "turn_at_least", "value": 3}}]),
        "horde_payoff": _card([{"op": "damage", "amount": 6, "target": "all_enemies", "when": {"kind": "enemy_count_ge", "value": 2}}]),
        "desperation": _card([{"op": "damage", "amount": 10, "when": {"kind": "hp_below_half"}}]),
        "patient_reserve": _card([{"op": "damage", "amount": 1, "scale": "unspent_energy_last_turn"}]),
        # Phase AN (v44)
        "devourer": _card([{"op": "damage", "amount": 10}, {"op": "gain_max_hp", "amount": 3}, {"op": "exhaust"}]),
        "piercing_strike": _card([{"op": "damage", "amount": 7, "unblockable": True}]),
        # Phase AO (v45)
        "cost_trick": _card([{"op": "cost_shift", "card_type": "attack", "amount": 1, "scope": "this_turn"}, {"op": "draw", "amount": 1}]),
        # Phase AM (v43)
        "body_slam": _card([{"op": "damage", "amount": 1, "scale": "block"}]),
        "executioner": _card([{"op": "damage", "amount": 7}, {"op": "gain_energy", "amount": 1, "when": {"kind": "target_hp_below_half"}}]),
        "combo_finisher": _card([{"op": "damage", "amount": 9}, {"op": "apply_status", "status": "weak", "amount": 1,
                                                                  "when": {"kind": "cards_played_this_turn_ge", "value": 2}}]),
        "x_dump": _card([{"op": "damage", "amount": 1, "scale": "x"}], cost="x"),
        "opening_gambit": _card([{"op": "innate"}, {"op": "damage", "amount": 6}]),
        "fleeting_power": _card([{"op": "ethereal"}, {"op": "damage", "amount": 12}]),
        "untouchable": _card([{"op": "apply_status", "status": "buffer", "amount": 1}]),
        "burst_window": _card([{"op": "apply_status", "status": "temp_strength", "amount": 3}]),
        "token_conjure": _card([{"op": "add_card", "card_id": "ember", "pile": "hand", "amount": 2}]),
        "discard_reflex": _card([{"op": "add_trigger", "trigger": "on_discard", "effects": [{"op": "block", "amount": 5}]}]),
        "balance_shift": _card([{"op": "balance_step", "pole": "dark", "amount": 2}]),
        "rampage_grow": _card([{"op": "damage", "amount": 8, "grow": 5}]),
        "battle_smith": _card([{"op": "upgrade_card", "cards": "random"}]),
        "ascetic_purge": _card([{"op": "damage", "amount": 14}, {"op": "purge"}]),
        "scry_filter": _card([{"op": "scry", "amount": 3}]),
        "corruption_engine": _card([{"op": "corruption"}]),
        "strike_synergy": _card([{"op": "damage", "amount": 6, "scale": "tag_cards_owned", "tag": "strike"}]),
        "metamorph": _card([{"op": "transform_card", "card_id": "ember"}]),
        "graft": _card([{"op": "graft_card", "card_id": "ember"}]),
        # Phase AP (v46)
        "grave_recall": _card([{"op": "retrieve_card", "pile": "discard", "cards": "choose", "amount": 1}]),
        "tainted_power": _card([{"op": "damage", "amount": 12}, {"op": "add_status_card", "card": "wound", "pile": "discard"}]),
    }
    plain = census.walk_card(_card([{"op": "damage", "amount": 6}]))
    check(set(samples) == {f.id for f in featured.FEATURED_MENU}, "a sample exists for every menu entry")
    for f in featured.FEATURED_MENU:
        cc = census.walk_card(samples[f.id])
        check(f.detect(cc), f"detector '{f.id}' fires on its own mechanic")
        check(not f.detect(plain), f"detector '{f.id}' does NOT fire on a plain damage card")


def test_exclusion_and_presence() -> None:
    print("exclusion note + presence() over a made-list:")
    unt = next(f for f in featured.FEATURED_MENU if f.id == "untouchable")
    check(unt.exclusion == "rare-tier", f"untouchable is rare-tier gated, got {unt.exclusion!r}")

    made = [
        {"plan": {"role": "common"}, "card": _card([{"op": "add_trigger", "trigger": "attacked",
                                                     "effects": [{"op": "damage", "amount": 4, "target": "enemy"}]}])},
        {"plan": {"role": "common"}, "card": _card([{"op": "damage", "amount": 6}])},
    ]
    feats = featured.resolve(["counterattack", "desperation"])
    pres = featured.presence(made, feats)
    check(pres["counterattack"] is True, "counterattack present (a card carries `attacked`)")
    check(pres["desperation"] is False, "desperation absent")


def test_coverage_targets_featured() -> None:
    print("a missing featured mechanic joins the coverage repair round with its own directive + WARNING:")
    # a small pool with plenty of variety so the ONLY shortfall is the featured mechanic
    def m(effects, name):
        return {"plan": {"role": "common", "rarity": "common", "theme": "", "type": "skill"},
                "card": {"id": f"c_{name}", "name": name, "type": "skill", "rarity": "common", "cost": 1,
                         "target": "self", "effects": effects}}
    made = [
        m([{"op": "add_trigger", "trigger": "attacked", "effects": [{"op": "damage", "amount": 4}]}], "r1"),
        m([{"op": "add_trigger", "trigger": "on_hp_lost", "effects": [{"op": "block", "amount": 3}]}], "r2"),
        m([{"op": "damage", "amount": 6, "when": {"kind": "hp_below_half"}}], "w1"),
        m([{"op": "block", "amount": 6, "when": {"kind": "turn_at_least"}}], "w2"),
        m([{"op": "damage", "amount": 6, "when": {"kind": "no_block"}}], "w3"),
        # exotic cards carry a `when` too, so they are NOT plain (keeps plain-share under quota)
        m([{"op": "apply_status", "status": "thorns", "amount": 3, "when": {"kind": "has_block"}}], "x1"),
        m([{"op": "damage", "amount": 5}, {"op": "apply_status", "status": "metallicize", "amount": 3, "when": {"kind": "hp_below_half"}}], "x2"),
        m([{"op": "damage", "amount": 1, "scale": "cards_in_hand"}], "s1"),
        m([{"op": "damage", "amount": 6}], "plainvictim"),
    ]
    rep = coverage.measure(made)
    check(not rep.violations, f"the base pool meets every quota (so only featured can be short): {rep.violations}")

    feats = featured.resolve(["burst_window"])  # not present -> must be requested
    seen_directives: list[str] = []
    log: list[str] = []

    def stub(plan, old, directive):
        seen_directives.append(directive)
        return None  # fail the repair so we can assert the WARNING path

    summary = coverage.enforce_coverage(made, stub, log.append, featured=feats)
    check(summary["featured_missing_before"] == ["burst_window"], f"featured miss detected up front: {summary}")
    check(any("temp_strength" in d for d in seen_directives), f"the burst_window directive was targeted: {seen_directives}")
    check(any("featured 'burst_window' not woven in" in l for l in log), "a WARNING names the missing featured mechanic")

    # when the mechanic IS present, no featured shortfall
    made2 = made + [m([{"op": "apply_status", "status": "temp_strength", "amount": 3}], "burst")]
    log2: list[str] = []
    s2 = coverage.enforce_coverage(made2, lambda p, o, d: None, log2.append, featured=feats)
    check(s2["featured_missing_before"] == [], "present featured mechanic -> no shortfall")
    check(any("burst_window=present" in l for l in log2), "featured status line reports it present")



# --------------------------------------------------------------- W2.3: class-kind-aware roulette
def test_class_kind_roulette() -> None:
    print("W2.3: roll_class_kind deals only from the menus matching the class's kind set:")
    base_ids = {f.id for f in featured.FEATURED_MENU}
    kind_ids = {f.id for f in featured.CLASS_KIND_MENU}
    check(not (base_ids & kind_ids), "class-kind ids never collide with the base menu")
    check(set(featured.FEATURED_CLASS_KIND) == {"orb", "status", "summon", "forge", "balance", "discard", "transform"},
          f"the seven class-kind menus, got {sorted(featured.FEATURED_CLASS_KIND)}")
    for kind, entries in featured.FEATURED_CLASS_KIND.items():
        check(len(entries) >= 1, f"menu '{kind}' is non-empty")
    # a summon-kind class rolls a summon entry; a normal class rolls NOTHING
    summon_ids = {f.id for f in featured.FEATURED_CLASS_KIND["summon"]}
    for concept in ("a necromancer and her bone thrall", "a beast tamer", "a puppeteer"):
        picks = featured.roll_class_kind(concept, {"", "summon"})
        check(len(picks) == featured.N_CLASS_KIND and picks[0].id in summon_ids,
              f"summon class rolls a summon entry: {[f.id for f in picks]}")
        check(featured.roll_class_kind(concept, {""}) == [], "a normal class rolls no class-kind entry")
        check(featured.roll_class_kind(concept, None) == [], "no kind set -> nothing")
    # deterministic per concept, order-proof over the kind set, and the two rolls don't move in lockstep
    a = featured.roll_class_kind("a storm-forger", {"", "orb", "forge"})
    b = featured.roll_class_kind("a storm-forger", {"forge", "orb", ""})
    check([f.id for f in a] == [f.id for f in b] and a[0].id in {f.id for f in featured.FEATURED_CLASS_KIND["orb"]}
          | {f.id for f in featured.FEATURED_CLASS_KIND["forge"]}, "deterministic and kind-order-proof")
    spread = {featured.roll_class_kind(c, {"", "forge"})[0].id for c in
              ("an anvil priest", "a molten duelist", "a sovereign smith", "a furnace knight", "a hammer saint",
               "a blacksmith", "a forge witch", "an ember warden")}
    check(len(spread) >= 2, f"different concepts spread across the forge menu: {spread}")
    # the base roll never picks a class-kind entry; resolve knows both menus
    check(all(f.id in base_ids for f in featured.roll_featured("a summoner")), "roll_featured stays on the base menu")
    check([f.id for f in featured.resolve(["summon_medic", "x_dump", "nope"])] == ["summon_medic", "x_dump"],
          "resolve() knows class-kind ids")
    check("summon_medic" not in featured.menu_block(), "menu_block (the cloud rating surface) lists the base menu only")


def test_class_kind_detectors_and_presence() -> None:
    print("W2.3: every class-kind detector round-trips; min_cards + detect_pool presence:")
    samples = {
        "orb_evoke_burst": _card([{"op": "evoke", "amount": 2}]),
        "orb_flash_focus": _card([{"op": "apply_status", "status": "temp_focus", "amount": 2}]),  # Phase AN (v44)
        "orb_slot_growth": _card([{"op": "gain_orb_slot", "amount": 1}]),
        "orb_focus_power": _card([{"op": "apply_status", "status": "focus", "amount": 1}]),
        "custom_status_spread": _card([{"op": "apply_status_custom", "status_name": "Rust", "amount": 2}]),
        "summon_medic": _card([{"op": "heal_summon", "amount": 4}]),
        "summon_drill": _card([{"op": "buff_summon", "amount": 2}]),
        # Phase AL (v42): the class engines as payloads
        "custom_status_engine": _card([{"op": "add_trigger", "trigger": "turn_start", "effects": [{"op": "apply_status_custom", "status_name": "Rust", "amount": 1}]}]),
        "summon_engine": _card([{"op": "add_trigger", "trigger": "turn_end", "effects": [{"op": "summon_attack", "amount": 4, "hits": 2}]}]),
        "blade_empower_burst": _card([{"op": "blade_empower", "amount": 2}]),
        "blade_recall": _card([{"op": "summon_blade"}]),
        "blade_rider": _card([{"op": "add_trigger", "trigger": "on_blade_played", "effects": [{"op": "block", "amount": 3}]}]),
        "knife_edge": _card([{"op": "damage", "amount": 12, "when": {"kind": "centered", "value": 1}}]),
        "discard_loop": _card([{"op": "scry", "amount": 2}]),
        "transform_graft": _card([{"op": "graft_card", "card_id": "ember"}]),
        # Phase AV (v52): spend the minion for a payoff
        "summon_sacrifice": _card([{"op": "sacrifice_summon"}, {"op": "block", "amount": 12}]),
    }
    check(set(samples) == {f.id for f in featured.CLASS_KIND_MENU}, "a sample exists for every class-kind entry")
    plain = census.walk_card(_card([{"op": "damage", "amount": 6}]))
    for f in featured.CLASS_KIND_MENU:
        check(f.detect(census.walk_card(samples[f.id])), f"detector '{f.id}' fires")
        check(not f.detect(plain), f"detector '{f.id}' silent on a plain card")
        check(f.directive.startswith("REQUIRED:"), f"'{f.id}' carries a REQUIRED directive")
    # min_cards: the status spread needs THREE carriers
    spread = next(f for f in featured.CLASS_KIND_MENU if f.id == "custom_status_spread")
    one = [census.walk_card(samples["custom_status_spread"])]
    check(not spread.carried_by(one), "one apply_status_custom card is not a spread")
    check(spread.carried_by(one * 3), "three carriers satisfy the spread")
    # detect_pool: the discard loop needs BOTH halves
    loop = next(f for f in featured.CLASS_KIND_MENU if f.id == "discard_loop")
    scry = census.walk_card(samples["discard_loop"])
    reflex = census.walk_card(_card([{"op": "add_trigger", "trigger": "on_discard", "effects": [{"op": "block", "amount": 5}]}]))
    check(not loop.carried_by([scry, scry]) and not loop.carried_by([reflex]), "half a loop is not carried")
    check(loop.carried_by([scry, reflex]), "scry + on_discard together carry the loop")
    # presence() + the coverage round use carried_by (so a missing spread is repaired)
    made = [{"plan": {"role": "common"}, "card": samples["custom_status_spread"]}]
    check(featured.presence(made, [spread]) == {"custom_status_spread": False}, "presence honors min_cards")
    log: list[str] = []
    asked: list[str] = []

    def stub(plan, old, directive):
        asked.append(directive)
        return None
    good = [{"plan": {"role": "common", "rarity": "common"}, "card": c} for c in (
        _card([{"op": "add_trigger", "trigger": "attacked", "effects": [{"op": "damage", "amount": 4}]}]),
        _card([{"op": "add_trigger", "trigger": "on_hp_lost", "effects": [{"op": "block", "amount": 3}]}]),
        _card([{"op": "damage", "amount": 6, "when": {"kind": "hp_below_half"}}]),
        _card([{"op": "block", "amount": 6, "when": {"kind": "turn_at_least"}}]),
        _card([{"op": "damage", "amount": 6, "when": {"kind": "no_block"}}]),
        _card([{"op": "apply_status", "status": "thorns", "amount": 3, "when": {"kind": "has_block"}}]),
        _card([{"op": "apply_status", "status": "regen", "amount": 3, "when": {"kind": "has_block"}}]),
        _card([{"op": "damage", "amount": 1, "scale": "cards_in_hand"}]),
        _card([{"op": "damage", "amount": 6}]),
    )]
    for i, m in enumerate(good):
        m["card"]["id"] = f"g{i}"
        m["card"]["name"] = f"G{i}"
    s = coverage.enforce_coverage(good, stub, log.append, featured=[loop])
    check("discard_loop" in s["featured_missing_before"], "a missing class-kind pick is a quota item")
    check(any(d == loop.directive for d in asked), "its directive is injected")
    check(any("featured 'discard_loop' not woven in" in l for l in log), "and the WARNING names it")


def main() -> int:
    test_roll_reproducible()
    test_themed_roll()
    test_brief_blocks()
    test_detectors_round_trip()
    test_exclusion_and_presence()
    test_coverage_targets_featured()
    test_class_kind_roulette()
    test_class_kind_detectors_and_presence()
    print(f"\n{_PASS} passed, {_FAIL} failed")
    return 1 if _FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
