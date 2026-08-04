"""Offline tests for btsgen/bridges.py — the O-1 fusion enforcer. No API key needed.

Run:  uv run python -m tests.test_bridges     (from generation/)
Exits nonzero on any failure. Covers: card_tokens over effects/payloads/when/scale, witness math (disjoint
pair, overlapping-pair fallback, orb-vs-normal), the _validate_blueprint tag-count + rare rule, the fake
path emitting valid bridge tags (_fake_blueprint / _topup_blueprint_briefs), _resolve_bridge_ctx catalog
resolution, and the enforce_coverage bridge repair-in-place targeting. Per the plan we assert PLUMBING +
witness math, not real-generator outcomes.
"""
from __future__ import annotations

import sys

from btsgen.class_forge import point_btsgen_at_mod_contract

point_btsgen_at_mod_contract()

from btsgen import bridges, coverage  # noqa: E402
from btsgen.class_forge import (ClassBrief, MIN_BRIDGES, _ensure_bridge_tags, _fake_blueprint,  # noqa: E402
                                _resolve_bridge_ctx, _topup_blueprint_briefs, _validate_blueprint)

_PASS = 0
_FAIL = 0


def check(cond: bool, msg: str) -> None:
    global _PASS, _FAIL
    if cond:
        _PASS += 1
    else:
        _FAIL += 1
        print(f"  FAIL: {msg}")


def _card(effects, cost=1):
    return {"id": "t", "name": "T", "type": "attack", "cost": cost, "target": "enemy", "effects": effects}


# --------------------------------------------------------------- card_tokens
def test_card_tokens() -> None:
    print("card_tokens(): flat token set over ops / statuses / triggers / when / scale:")
    c = _card([
        {"op": "damage", "amount": 6},
        {"op": "apply_status", "status": "thorns", "amount": 3},
        {"op": "add_trigger", "trigger": "attacked", "effects": [{"op": "damage", "amount": 4}]},
        {"op": "block", "amount": 5, "when": {"kind": "hp_below_half"}},
        {"op": "draw", "amount": 1, "scale": "cards_retained"},
    ])
    toks = bridges.card_tokens(c)
    for want in ("damage", "block", "draw", "thorns", "add_trigger", "attacked", "hp_below_half",
                 "scale", "cards_retained"):
        check(want in toks, f"card_tokens must surface '{want}': {sorted(toks)}")
    check("x" not in toks, "a non-X card must not carry the 'x' token")
    check("x" in bridges.card_tokens(_card([{"op": "damage", "amount": 5}], cost="x")),
          "an X-cost card carries the 'x' token")
    check(bridges.card_tokens({}) == set(), "an empty card yields no tokens")


# --------------------------------------------------------------- witness math
def test_witness_disjoint() -> None:
    print("is_witnessed(): a DISJOINT pair needs >=1 witness token of EACH side:")
    # forge_ramp-ish vs counter_riposte-ish (fully disjoint witness sets)
    ops_a = {"forge", "forged_ge", "scale", "add_trigger"}
    ops_b = {"thorns", "attacked", "on_hp_lost", "add_trigger"}
    wit_a, wit_b = bridges.witness_sets(ops_a, ops_b)
    check(wit_a == {"forge", "forged_ge", "scale"} and wit_b == {"thorns", "attacked", "on_hp_lost"},
          f"witness sets drop the shared token: {wit_a} / {wit_b}")
    fused = _card([{"op": "forge", "amount": 2},
                   {"op": "apply_status", "status": "thorns", "amount": 3}])
    check(bridges.is_witnessed(fused, ops_a, ops_b), "forge + thorns fuses both engines")
    one_side = _card([{"op": "forge", "amount": 2}])
    check(not bridges.is_witnessed(one_side, ops_a, ops_b), "forge alone does not fuse (misses side B)")
    shared_only = _card([{"op": "add_trigger", "trigger": "turn_start", "effects": [{"op": "block", "amount": 2}]}])
    check(not bridges.is_witnessed(shared_only, ops_a, ops_b),
          "touching only the SHARED token does not fuse either side")


def test_witness_overlapping_fallback() -> None:
    print("is_witnessed(): an OVERLAPPING pair (a witness set empty) falls back to >=2 union tokens:")
    ops_a = {"damage", "block"}
    ops_b = {"damage", "block", "draw"}  # a is a subset -> witness_a empty
    wit_a, wit_b = bridges.witness_sets(ops_a, ops_b)
    check(wit_a == set(), "the subset side has an empty witness set")
    two_union = _card([{"op": "damage", "amount": 6}, {"op": "block", "amount": 5}])
    check(bridges.is_witnessed(two_union, ops_a, ops_b), "2 union tokens satisfy the overlap fallback")
    one_union = _card([{"op": "damage", "amount": 6}])
    check(not bridges.is_witnessed(one_union, ops_a, ops_b), "1 union token is not enough under the fallback")


def test_witness_orb_vs_normal() -> None:
    print("is_witnessed(): an orb archetype fused with a normal one:")
    ops_orb = {"channel_orb", "evoke", "gain_orb_slot", "focus"}
    ops_norm = {"block", "apply_status", "add_trigger"}
    fused = _card([{"op": "channel_orb", "orb": "lightning", "amount": 1}, {"op": "block", "amount": 5}])
    check(bridges.is_witnessed(fused, ops_orb, ops_norm), "channel + block fuses orb x normal")
    orb_only = _card([{"op": "channel_orb", "orb": "lightning", "amount": 1}])
    check(not bridges.is_witnessed(orb_only, ops_orb, ops_norm), "channel alone does not fuse")


def test_repair_directive() -> None:
    print("repair_directive(): names both engines + concrete witness tokens:")
    d = bridges.repair_directive("Forge", "Riposte", {"forge", "scale"}, {"thorns", "attacked"})
    check("BRIDGE" in d and "Forge" in d and "Riposte" in d, f"directive names both engines: {d}")
    check("forge" in d and "thorns" in d, f"directive anchors concrete witness tokens: {d}")
    # overlapping pair -> the union-fallback phrasing
    d2 = bridges.repair_directive("A", "B", {"damage", "block"}, {"damage", "block", "draw"})
    check("TWO" in d2 or "two" in d2.lower(), f"overlapping directive asks for >=2 union tokens: {d2}")


# --------------------------------------------------------------- blueprint rule
def _valid_bp():
    """A topped-up fake bp that passes _validate_blueprint clean (bridges + strategy satisfied)."""
    return _topup_blueprint_briefs(_fake_blueprint(ClassBrief(concept="plain")), strategies=["aggro", "control"])


def test_validate_blueprint_bridge_rule() -> None:
    print("_validate_blueprint(): >=MIN_BRIDGES tagged bridges incl >=1 rare:")
    bp = _valid_bp()
    check(_validate_blueprint(bp) == [], f"the topped-up fake must validate clean: {_validate_blueprint(bp)}")
    # strip every bridge tag -> the tag-count rule fires
    for c in bp["cards"]:
        c.pop("bridge", None)
    errs = _validate_blueprint(bp)
    check(any("bridge" in e for e in errs), f"an untagged pool must fail the bridge rule: {errs}")
    # tag exactly MIN_BRIDGES commons (no rare) -> the rare-poster rule fires, tag-count satisfied
    commons = [c for c in bp["cards"] if c.get("role") == "pool"
               and str(c.get("rarity", "")).lower() == "common"][:MIN_BRIDGES]
    check(len(commons) >= MIN_BRIDGES, "fixture must have >=MIN_BRIDGES common pool cards to tag")
    for c in commons:
        c["bridge"] = True
    errs = _validate_blueprint(bp)
    check(any("rare" in e and "bridge" in e for e in errs),
          f"{MIN_BRIDGES} non-rare bridges must fail the rare-poster rule: {errs}")
    check(not any("need at least" in e and "bridge cards" in e for e in errs),
          "the tag-COUNT rule must be satisfied once MIN_BRIDGES are tagged")


def test_fake_path_bridge_tags() -> None:
    print("fake path: _fake_blueprint / _ensure_bridge_tags emit >=MIN_BRIDGES tags incl a rare:")
    for concept in ["a smith with a growing blade", "an orb storm channeler", "a razor-focus duelist status",
                    "a necromancer summon commander", "a plain toxin brawler"]:
        bp = _fake_blueprint(ClassBrief(concept=concept))
        br = [c for c in bp["cards"] if c.get("role") == "pool" and c.get("bridge")]
        check(len(br) >= MIN_BRIDGES, f"'{concept}': fake must tag >=MIN_BRIDGES bridges, got {len(br)}")
        check(any(str(c.get("rarity", "")).lower() == "rare" for c in br),
              f"'{concept}': a fake bridge must be rare")
    # idempotent + adds fillers when the pool is too small
    tiny = {"cards": [{"role": "pool", "name_hint": "Only", "type": "skill", "rarity": "common",
                       "cost": 1, "deck_count": 0, "archetype": None, "theme": "x"}]}
    _ensure_bridge_tags(tiny)
    br = [c for c in tiny["cards"] if c.get("bridge")]
    check(len(br) >= MIN_BRIDGES and any(str(c.get("rarity", "")).lower() == "rare" for c in br),
          f"_ensure_bridge_tags backfills fillers incl a rare on a tiny pool: {len(br)}")


# --------------------------------------------------------------- ctx resolution
def test_resolve_bridge_ctx() -> None:
    print("_resolve_bridge_ctx(): resolves catalog ops, None on unknown ids:")
    good = {"archetypes": [{"id": "forge_ramp", "name": "Forge"},
                           {"id": "counter_riposte", "name": "Riposte"}]}
    ctx = _resolve_bridge_ctx(good)
    check(ctx is not None and "forge" in ctx["ops_a"] and "thorns" in ctx["ops_b"],
          f"a catalog pair resolves to its ops: {ctx}")
    unknown = {"archetypes": [{"id": "forge_ramp", "name": "Forge"},
                              {"id": "made_up_id", "name": "Nope"}]}
    check(_resolve_bridge_ctx(unknown) is None, "an unknown archetype id yields None (detector skipped)")
    check(_resolve_bridge_ctx({"archetypes": [{"id": "forge_ramp"}]}) is None, "need exactly 2 archetypes")


# --------------------------------------------------------------- enforce_coverage bridge targeting
def _m(role, effects, *, rarity="common", name=None, bridge=False):
    plan = {"role": role, "rarity": rarity, "type": "attack", "cost": 1}
    if bridge:
        plan["bridge"] = True
    return {"plan": plan, "card": {"id": f"c_{name or role}", "name": name or role, "type": "attack",
                                   "rarity": rarity, "cost": 1, "target": "enemy", "effects": effects}}


def test_enforce_bridge_repair_in_place() -> None:
    print("enforce_coverage(): a non-fusing bridge is repaired IN PLACE, first, and re-witnessed:")
    ctx = {"ops_a": {"forge", "forged_ge", "scale"}, "ops_b": {"thorns", "attacked", "on_hp_lost"},
           "name_a": "Forge", "name_b": "Riposte"}
    # a bridge that touches only side A (forge) -> fails witness; plus filler pool cards
    made = [
        _m("basic_attack", [{"op": "damage", "amount": 6}], rarity="basic", name="Strike"),
        _m("basic_skill", [{"op": "block", "amount": 5}], rarity="basic", name="Defend"),
        _m("rare", [{"op": "forge", "amount": 2}], rarity="rare", name="HalfBridge", bridge=True),
        _m("common", [{"op": "damage", "amount": 6}], name="Filler1"),
        _m("common", [{"op": "damage", "amount": 6}], name="Filler2"),
    ]

    def regen(plan, old, directive):
        # only the bridge directive gets a (witnessing) replacement; generic quota directives are left alone
        if "BRIDGE" in directive:
            return {"id": "fused", "name": "Fused", "type": "attack", "cost": 1, "target": "enemy",
                    "effects": [{"op": "forge", "amount": 2}, {"op": "apply_status", "status": "thorns", "amount": 3}]}
        return None

    log: list[str] = []
    summary = coverage.enforce_coverage(made, regen, log.append, bridge_ctx=ctx)
    check(summary["bridge_fail_before"] and not summary["bridge_fail_after"],
          f"the bridge fails before, fuses after: {summary['bridge_fail_before']} -> {summary['bridge_fail_after']}")
    fused = next(m["card"] for m in made if m["plan"].get("bridge"))
    check(bridges.is_witnessed(fused, ctx["ops_a"], ctx["ops_b"]), "the repaired bridge witnesses both engines")
    check(any("coverage bridges:" in l for l in log), "a bridge status line is streamed")
    # a bridge that already fuses is NOT flagged
    made2 = [_m("rare", [{"op": "forge", "amount": 2}, {"op": "apply_status", "status": "thorns", "amount": 3}],
                rarity="rare", name="GoodBridge", bridge=True),
             _m("common", [{"op": "damage", "amount": 6}], name="F1")]
    s2 = coverage.enforce_coverage(made2, lambda p, o, d: None, [].append, bridge_ctx=ctx)
    check(not s2["bridge_fail_before"], "a fusing bridge is never flagged")


def main() -> int:
    test_card_tokens()
    test_witness_disjoint()
    test_witness_overlapping_fallback()
    test_witness_orb_vs_normal()
    test_repair_directive()
    test_validate_blueprint_bridge_rule()
    test_fake_path_bridge_tags()
    test_resolve_bridge_ctx()
    test_enforce_bridge_repair_in_place()
    print(f"\n{_PASS} passed, {_FAIL} failed")
    return 1 if _FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
