"""Offline tests for btsgen/census.py — the Phase N creative-breadth metric. No API key needed.

Run:  uv run python -m tests.test_census     (from generation/)
Exits nonzero on any failure. Covers: walk_card ops/statuses/triggers/whens/scales tallying across base +
upgrade + nested add_trigger payloads, the plain-flag edges (a `when` guard or a `scale` makes a card
NOT plain), X-cost detection, aggregate Counters + plain_share, and decode_bundle round-tripping a real
BTSC code.
"""
from __future__ import annotations

import json
import sys

from btsgen import bts1, census

_PASS = 0
_FAIL = 0


def check(cond: bool, msg: str) -> None:
    global _PASS, _FAIL
    if cond:
        _PASS += 1
    else:
        _FAIL += 1
        print(f"  FAIL: {msg}")


def _card(id_, effects, upgrade=None, cost=1):
    c = {"id": id_, "name": id_, "type": "skill", "rarity": "common", "cost": cost,
         "target": "self", "effects": effects}
    if upgrade is not None:
        c["upgrade"] = {"effects": upgrade}
    return c


# --------------------------------------------------------------- walk_card basics + plain edges
def test_plain_flag() -> None:
    print("plain-flag: only damage/block/apply_status/draw with no when/scale/X is plain:")
    plain = _card("plain", [{"op": "damage", "amount": 6}], [{"op": "damage", "amount": 9}])
    check(census.walk_card(plain).plain, "a bare damage card is plain")

    # apply_status vulnerable/weak is still a "plain" op set (breadth measures the debuff share separately)
    dbf = _card("dbf", [{"op": "damage", "amount": 5}, {"op": "apply_status", "status": "vulnerable", "amount": 1}])
    cc = census.walk_card(dbf)
    check(cc.plain, "damage + apply_status(vulnerable) is plain (op set ⊆ base)")
    check(cc.uses_generic_debuff, "vulnerable flags uses_generic_debuff")

    # a `when` guard removes plainness even though ops stay in the base set
    guarded = _card("guarded", [{"op": "damage", "amount": 8, "when": {"kind": "hp_below_half"}}])
    gc = census.walk_card(guarded)
    check(not gc.plain, "a when-guarded card is NOT plain")
    check(gc.whens.get("hp_below_half") == 1, "when kind recorded")

    # a scaled amount removes plainness
    scaled = _card("scaled", [{"op": "damage", "amount": 1, "scale": "cards_in_hand"}])
    sc = census.walk_card(scaled)
    check(not sc.plain, "a scaled card is NOT plain")
    check(sc.scales.get("cards_in_hand") == 1, "scale source recorded")

    # a non-base op (retain) removes plainness
    ret = _card("ret", [{"op": "draw", "amount": 1}, {"op": "retain"}])
    check(not census.walk_card(ret).plain, "a card with retain is NOT plain")

    # X-cost removes plainness
    xc = _card("xc", [{"op": "damage", "amount": 1, "scale": "x"}], cost="x")
    xcc = census.walk_card(xc)
    check(not xcc.plain, "an X-cost card is NOT plain")
    check(xcc.x_cost, "x_cost flag set for cost:'x'")

    # an empty/malformed card is not plain (no ops)
    check(not census.walk_card({"id": "empty", "effects": []}).plain, "an effectless card is not plain")


def test_nested_and_upgrade_walk() -> None:
    print("walk covers base + upgrade + nested add_trigger payloads:")
    card = _card(
        "engine",
        [{"op": "add_trigger", "trigger": "on_hp_lost",
          "effects": [{"op": "apply_status", "status": "thorns", "amount": 2}]}],
        upgrade=[{"op": "add_trigger", "trigger": "on_hp_lost",
                  "effects": [{"op": "apply_status", "status": "thorns", "amount": 3}]}],
    )
    cc = census.walk_card(card)
    check(cc.triggers.get("on_hp_lost") == 2, f"trigger counted in base+upgrade, got {cc.triggers}")
    check(cc.statuses.get("thorns") == 2, f"nested payload status counted twice, got {cc.statuses}")
    check("on_hp_lost" in cc.reactive_trigger_kinds, "on_hp_lost is a reactive trigger kind")
    check(cc.exotic_status_kinds == {"thorns"}, f"thorns is exotic, got {cc.exotic_status_kinds}")

    # turn_start/turn_end are NOT reactive
    tt = _card("tt", [{"op": "add_trigger", "trigger": "turn_start",
                       "effects": [{"op": "block", "amount": 3}]}])
    check(not census.walk_card(tt).reactive_trigger_kinds, "turn_start is not a reactive kind")


def test_innate_ethereal_ops() -> None:
    print("innate / ethereal are nullary ops:")
    card = _card("opener", [{"op": "innate"}, {"op": "damage", "amount": 7}])
    cc = census.walk_card(card)
    check(cc.ops.get("innate") == 1, "innate counted as an op")
    check(not cc.plain, "innate makes it non-plain (op ∉ base set)")
    eth = _card("fleeting", [{"op": "ethereal"}, {"op": "draw", "amount": 2}])
    check(census.walk_card(eth).ops.get("ethereal") == 1, "ethereal counted as an op")


# --------------------------------------------------------------- aggregation
def test_aggregate() -> None:
    print("census_cards aggregates plain count, share, and occurrence Counters:")
    cards = [
        _card("p1", [{"op": "damage", "amount": 6}]),
        _card("p2", [{"op": "block", "amount": 5}]),
        _card("v", [{"op": "apply_status", "status": "vulnerable", "amount": 1}],
              upgrade=[{"op": "apply_status", "status": "vulnerable", "amount": 2}]),
        _card("x", [{"op": "damage", "amount": 1, "scale": "x"}], cost="x"),
    ]
    cen = census.census_cards(cards)
    check(cen.total == 4, "total cards")
    check(cen.plain == 3, f"3 plain (p1, p2, v), got {cen.plain}")
    check(abs(cen.plain_share - 0.75) < 1e-9, f"plain_share 0.75, got {cen.plain_share}")
    check(cen.generic_debuff_count == 2, f"vulnerable counted base+upgrade = 2, got {cen.generic_debuff_count}")
    check(cen.x_cost == 1, "one X-cost card")
    check(len(cen.per_card) == 4, "per_card retains each reading")


def test_bundle_and_decode() -> None:
    print("census_bundle + decode_bundle round-trip a BTSC code:")
    bundle = {"kind": "class", "character": {"name": "Testy"},
              "cards": [_card("d", [{"op": "damage", "amount": 6}])]}
    cen = census.census_bundle(bundle)
    check(cen.total == 1 and cen.plain == 1, "bundle census walks bundle['cards']")

    code = bts1.encode_class(json.dumps(bundle, separators=(",", ":")))
    decoded = census.decode_bundle(code)
    check(decoded.get("character", {}).get("name") == "Testy", "decode_bundle recovers the class bundle")
    check(census.census_bundle(decoded).total == 1, "decoded bundle censuses identically")

    # a bare card code decodes to a one-card bundle
    card_code = bts1.encode_card(json.dumps(_card("solo", [{"op": "block", "amount": 4}]), separators=(",", ":")))
    solo = census.decode_bundle(card_code)
    check(len(solo.get("cards", [])) == 1, "a BTS1 card code becomes a one-card bundle")



# --------------------------------------------------------------- W2.1: count what exists
def test_w2_counters() -> None:
    print("W2.1: multi-hit, keywords, custom statuses, summon buffs, specialty bucket, tags, upgrade.cost, "
          "once_per_turn, ripen amounts, targeted payloads:")
    # multi-hit is NON-plain and a keyword KIND
    mh = _card("mh", [{"op": "damage", "amount": 4, "hits": 3}])
    cc = census.walk_card(mh)
    check(cc.multi_hit == 1, f"hits>=2 on damage counts as multi_hit, got {cc.multi_hit}")
    check(not cc.plain, "a multi-hit card is NOT plain (W2.1)")
    check(census.MULTI_HIT_KIND in cc.keyword_kinds, "multi_hit is a keyword kind")
    check(census.walk_card(_card("h1", [{"op": "damage", "amount": 4, "hits": 1}])).multi_hit == 0,
          "hits:1 is not multi-hit")
    sa = _card("sa", [{"op": "summon_attack", "amount": 3, "hits": 2}])
    check(census.walk_card(sa).multi_hit == 1, "summon_attack with hits counts as multi-hit (Phase AJ)")

    # the four keywords
    kw = _card("kw", [{"op": "exhaust"}, {"op": "retain"}, {"op": "damage", "amount": 6}],
               upgrade=[{"op": "innate"}, {"op": "ethereal"}, {"op": "damage", "amount": 9}])
    cc = census.walk_card(kw)
    check(cc.keywords == {"exhaust": 1, "retain": 1, "innate": 1, "ethereal": 1},
          f"all four keywords counted across base+upgrade, got {dict(cc.keywords)}")
    check(cc.keyword_kinds == {"exhaust", "retain", "innate", "ethereal"}, f"keyword_kinds, got {cc.keyword_kinds}")

    # apply_status_custom statuses + buff_summon statuses (default strength)
    cs = _card("cs", [{"op": "apply_status_custom", "status_name": "Rust", "amount": 2},
                      {"op": "buff_summon", "amount": 2},
                      {"op": "buff_summon", "amount": 1, "status": "dexterity"}])
    cc = census.walk_card(cs)
    check(cc.custom_statuses == {"rust": 1}, f"custom status counted (lowercased), got {dict(cc.custom_statuses)}")
    check(cc.summon_buffs == {"strength": 1, "dexterity": 1},
          f"buff_summon statuses counted (default strength), got {dict(cc.summon_buffs)}")

    # poison / frail / focus: their own bucket, neither generic nor exotic
    sp = _card("sp", [{"op": "apply_status", "status": "poison", "amount": 3},
                      {"op": "apply_status", "status": "frail", "amount": 1},
                      {"op": "apply_status", "status": "focus", "amount": 1}])
    cc = census.walk_card(sp)
    check(cc.specialty_status_kinds == {"poison", "frail", "focus"}, f"specialty bucket, got {cc.specialty_status_kinds}")
    check(not cc.uses_generic_debuff and not cc.exotic_status_kinds, "specialty statuses are neither generic nor exotic")
    check(census.SPECIALTY_STATUSES.isdisjoint(census.EXOTIC_STATUSES)
          and census.SPECIALTY_STATUSES.isdisjoint(census.GENERIC_DEBUFFS), "the three buckets are disjoint")

    # tags, upgrade.cost, once_per_turn, ripen amounts, targeted payloads
    rich = _card("rich", [{"op": "add_trigger", "trigger": "ripen", "amount": 2,
                           "effects": [{"op": "damage", "amount": 12, "target": "enemy"}]},
                          {"op": "add_trigger", "trigger": "on_card_played", "once_per_turn": True,
                           "effects": [{"op": "block", "amount": 2}]}],
                 upgrade=[{"op": "add_trigger", "trigger": "ripen", "amount": 3,
                           "effects": [{"op": "damage", "amount": 16, "target": "all_enemies"}]}])
    rich["tags"] = ["fuse"]
    rich["upgrade"]["cost"] = 0
    cc = census.walk_card(rich)
    check(cc.tagged, "a card with tags is tagged")
    check(cc.upgrade_cost, "an upgrade with an absolute cost is counted")
    check(cc.once_per_turn == 1, f"once_per_turn triggers counted, got {cc.once_per_turn}")
    check(cc.ripen_amounts == {2: 1, 3: 1}, f"ripen amounts counted, got {dict(cc.ripen_amounts)}")
    check(cc.targeted_payloads == 2, f"targeted payload effects counted, got {cc.targeted_payloads}")
    # a top-level targeted effect is NOT a targeted payload
    top = _card("top", [{"op": "damage", "amount": 6, "target": "enemy"}])
    check(census.walk_card(top).targeted_payloads == 0, "a top-level target is not a payload target")
    check(not census.walk_card(_card("nt", [{"op": "damage", "amount": 6}])).tagged, "no tags -> not tagged")
    check(not census.walk_card(_card("nu", [{"op": "damage", "amount": 6}], [{"op": "damage", "amount": 9}])).upgrade_cost,
          "no upgrade.cost -> not counted")

    # aggregate carries every counter + merge folds them
    cen = census.census_cards([mh, kw, cs, sp, rich])
    check(cen.multi_hit == 1 and cen.keywords["retain"] == 1 and cen.custom_statuses["rust"] == 1
          and cen.summon_buffs["strength"] == 1 and cen.tagged_cards == 1 and cen.upgrade_cost_cards == 1
          and cen.once_per_turn == 1 and cen.ripen_amounts[2] == 1 and cen.targeted_payloads == 2,
          "census_cards aggregates every W2.1 counter")
    check(cen.keyword_kinds == {"exhaust", "retain", "innate", "ethereal", census.MULTI_HIT_KIND},
          f"aggregate keyword_kinds, got {cen.keyword_kinds}")
    check(cen.specialty_status_kinds == {"poison", "frail", "focus"}, "aggregate specialty kinds")
    agg = census.Census()
    agg.merge(cen)
    agg.merge(census.census_cards([mh]))
    check(agg.total == 6 and agg.multi_hit == 2 and agg.tagged_cards == 1, "merge sums counters")


def test_w2_report_prints_every_counter() -> None:
    print("W2.1: format_report prints every counter, not a fixed subset:")
    cards = [
        _card("a", [{"op": "damage", "amount": 4, "hits": 2}, {"op": "retain"}]),
        _card("b", [{"op": "apply_status", "status": "poison", "amount": 3},
                    {"op": "apply_status_custom", "status_name": "Rust", "amount": 1},
                    {"op": "buff_summon", "amount": 2}]),
        _card("c", [{"op": "add_trigger", "trigger": "ripen", "amount": 2, "once_per_turn": True,
                     "effects": [{"op": "damage", "amount": 9, "target": "enemy"}]},
                    {"op": "scry", "amount": 2}]),
        _card("d", [{"op": "block", "amount": 3, "scale": "cards_retained", "when": {"kind": "draw_pile_empty"}}]),
    ]
    cards[0]["tags"] = ["fuse"]
    cards[3]["upgrade"] = {"cost": 0, "effects": [{"op": "block", "amount": 5}]}
    rep = census.format_report([("Klass", census.census_cards(cards))])
    for needle in ("multi_hit=1", "retain=1", "poison=1", "rust=1", "strength=1", "once_per_turn=1",
                   "targeted_payloads=1", "2=1", "draw_pile_empty=1", "cards_retained=1", "tagged_cards=1",
                   "upgrade_cost_cards=1", "scry=1", "keywords=2"):
        check(needle in rep, f"report carries '{needle}'")
    # the untouched-vocabulary columns still print as zeros (the N-0 baseline table stays readable)
    check("vulnerable=0" in rep and "turn_at_least=0" in rep, "fixed baseline columns still print")


def main() -> int:
    test_plain_flag()
    test_nested_and_upgrade_walk()
    test_innate_ethereal_ops()
    test_aggregate()
    test_bundle_and_decode()
    test_w2_counters()
    test_w2_report_prints_every_counter()
    print(f"\n{_PASS} passed, {_FAIL} failed")
    return 1 if _FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
