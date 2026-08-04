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


def main() -> int:
    test_plain_flag()
    test_nested_and_upgrade_walk()
    test_innate_ethereal_ops()
    test_aggregate()
    test_bundle_and_decode()
    print(f"\n{_PASS} passed, {_FAIL} failed")
    return 1 if _FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
