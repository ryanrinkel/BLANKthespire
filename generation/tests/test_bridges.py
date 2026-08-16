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
from btsgen.class_forge import (ClassBrief, MIN_BRIDGES, _archetype_ids, _bridge_pair,  # noqa: E402
                                _ensure_bridge_tags, _fake_blueprint, _resolve_bridge_ctx,
                                _topup_blueprint_briefs, _validate_blueprint)

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


# --------------------------------------------------------------- O-2 per-card context
def test_card_context() -> None:
    print("_card_context(): class block + archetype assignment + PROACTIVE bridge fusion directive:")
    from btsgen.bridges import TARGET_BRIDGES
    from btsgen.class_forge import _card_context, _class_context
    check(TARGET_BRIDGES >= MIN_BRIDGES, "the prompt ask is at least the validation floor")
    bp = {"name": "Testclass", "description": "a test fantasy",
          "archetypes": [{"id": "forge_ramp", "name": "Forge", "description": "stoke the forge"},
                         {"id": "counter_riposte", "name": "Riposte", "description": "punish attackers"}]}
    cls = _class_context(bp)
    check("Testclass" in cls and "stoke the forge" in cls and "punish attackers" in cls,
          f"the class block names the class and BOTH engines: {cls}")
    plain = {"role": "pool", "archetype": "forge_ramp", "strategy": "aggro", "theme": "x"}
    ctx = _card_context(bp, plain)
    check("PRIMARILY serves the Forge" in ctx, f"the card's own archetype is named (by display name): {ctx}")
    check("Strategic line: aggro" in ctx, "the strategy tag rides along")
    check("BRIDGE" not in ctx, "a non-bridge card gets no fusion directive")
    bctx = {"ops_a": {"forge", "forged_ge"}, "ops_b": {"thorns", "attacked"},
            "name_a": "Forge", "name_b": "Riposte"}
    bridge = {"role": "pool", "archetype": None, "bridge": True}
    ctx2 = _card_context(bp, bridge, bctx)
    check("BRIDGE" in ctx2 and "forge" in ctx2 and "thorns" in ctx2,
          f"a bridge gets the witness-token fusion directive at FIRST generation: {ctx2}")
    ctx3 = _card_context(bp, bridge, None)
    check("BRIDGE" in ctx3 and "Forge" in ctx3 and "Riposte" in ctx3,
          f"unresolvable ctx -> generic fusion directive still naming both engines: {ctx3}")
    # the precomputed class_ctx shortcut is honored (forge_class builds it once per class)
    check(_card_context(bp, plain, None, "PRECOMPUTED").startswith("PRECOMPUTED"),
          "a precomputed class block is reused, not rebuilt")


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


# --------------------------------------------------------------- Phase 1: triad plumbing
# forge_ramp x counter_riposte x poison_attrition — three real catalog archetypes with resolvable, mostly
# disjoint ops (so the witness + third-wheel math is meaningful).
_TRIAD_IDS = ("forge_ramp", "counter_riposte", "poison_attrition")


def _triad_bp():
    """A topped-up fake TRIAD blueprint that passes _validate_blueprint clean (three archetypes, three
    distinct pair->strategy lines, per-pair bridge floors, the rare poster)."""
    import copy
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


def test_third_wheel_and_pair_key() -> None:
    print("third_wheel_tokens() + pair_key(): the anti-blend token set + the sorted normalizer:")
    tw = bridges.third_wheel_tokens({"forge", "scale"}, {"thorns", "attacked"}, {"poison", "forge", "damage"})
    check(tw == {"poison", "damage"}, f"third-wheel = ops(Z) - ops(X) - ops(Y): {tw}")
    check(bridges.pair_key("z", "a") == ("a", "z") == bridges.pair_key("a", "z"),
          "pair_key sorts, so AB and BA hash the same")


def test_bridge_pair_parsing() -> None:
    print("_bridge_pair(): schema parsing + 2-arch boolean back-compat + triad rejections:")
    two = _archetype_ids({"archetypes": [{"id": "a"}, {"id": "b"}]})
    tri = _archetype_ids({"archetypes": [{"id": "a"}, {"id": "b"}, {"id": "c"}]})
    check(_bridge_pair({}, two) is None, "a non-bridge card yields None")
    check(_bridge_pair({"bridge": True}, two) == ("a", "b"),
          "a 2-archetype boolean bridge normalizes to the ONLY pair")
    check(_bridge_pair({"bridge": ["b", "a"]}, two) == ("a", "b"),
          "an explicit pair normalizes (sorted) regardless of order")
    check(_bridge_pair({"bridge": True}, tri) == "invalid",
          "a boolean bridge on a THREE-archetype class is invalid (must declare its pair)")
    check(_bridge_pair({"bridge": ["a", "b", "c"]}, tri) == "invalid",
          "a 3-id bridge is invalid (trinity cards are banned)")
    check(_bridge_pair({"bridge": ["a", "a"]}, tri) == "invalid", "a same-id pair is invalid")
    check(_bridge_pair({"bridge": ["a", "z"]}, tri) == "invalid", "an unknown archetype id is invalid")


def test_validate_triad_bridges() -> None:
    print("_validate_blueprint(): triad accepts 3 archetypes; pairwise bridge + trinity + boolean rules:")
    import copy
    bp = _triad_bp()
    check(_validate_blueprint(bp) == [], f"a clean triad bp validates: {_validate_blueprint(bp)}")
    # a 3-id trinity bridge is an ERROR
    t = copy.deepcopy(bp)
    next(c for c in t["cards"] if c.get("bridge"))["bridge"] = list(_TRIAD_IDS)
    check(any("trinity" in e.lower() for e in _validate_blueprint(t)),
          "a 3-id (trinity) bridge is rejected")
    # a boolean bridge on a triad is an ERROR
    t2 = copy.deepcopy(bp)
    next(c for c in t2["cards"] if c.get("bridge"))["bridge"] = True
    check(any("declare its pair" in e for e in _validate_blueprint(t2)),
          "a boolean bridge on a triad is rejected")
    # collapse every bridge onto ONE pair -> the per-pair floor fires for the two starved pairs
    t3 = copy.deepcopy(bp)
    for c in t3["cards"]:
        if c.get("bridge"):
            c["bridge"] = [_TRIAD_IDS[0], _TRIAD_IDS[1]]
            c["strategy"] = t3["pair_lines"][0]["strategy"] \
                if bridges.pair_key(_TRIAD_IDS[0], _TRIAD_IDS[1]) == \
                bridges.pair_key(*t3["pair_lines"][0]["pair"]) else c.get("strategy")
    check(any("each of the three pairs" in e for e in _validate_blueprint(t3)),
          "the per-pair floor (>=1 bridge per pair) fires when a pair has none")


def test_validate_triad_strategy_mapping() -> None:
    print("_validate_blueprint(): triad requires ALL THREE distinct pair->strategy lines (D3):")
    import copy
    bp = _triad_bp()
    # two pairs sharing a strategy -> not distinct
    t = copy.deepcopy(bp)
    t["pair_lines"][1]["strategy"] = t["pair_lines"][0]["strategy"]
    check(any("DISTINCT" in e for e in _validate_blueprint(t)),
          "two pairs on the same strategy is rejected")
    # drop a pair_lines entry -> a pair is unmapped
    t2 = copy.deepcopy(bp)
    t2["pair_lines"] = t2["pair_lines"][:2]
    check(any("ALL THREE pairs" in e for e in _validate_blueprint(t2)),
          "an unmapped pair is rejected")
    # a bridge tagged off its pair's declared line -> error
    t3 = copy.deepcopy(bp)
    line0 = t3["pair_lines"][0]
    other = next(s for s in ("aggro", "control", "combo") if s != line0["strategy"])
    br = next(c for c in t3["cards"]
              if _bridge_pair(c, _archetype_ids(t3)) == bridges.pair_key(*line0["pair"]))
    br["strategy"] = other
    check(any("declared strategy" in e for e in _validate_blueprint(t3)),
          "a bridge whose strategy tag isn't its pair's line is rejected")


def test_third_wheel_is_soft() -> None:
    print("no-third-wheel: a warn + repair-directive line, never a validation error:")
    from btsgen.class_forge import _card_context
    bp = _triad_bp()
    ctx = _resolve_bridge_ctx(bp)
    check(ctx is not None and set(ctx["pairs"]) and all("name_third" in v for v in ctx["pairs"].values()),
          "every triad pair context carries the excluded (third) engine")
    plan = {"role": "pool", "bridge": [_TRIAD_IDS[0], _TRIAD_IDS[1]], "strategy": "aggro"}
    cc = _card_context(bp, plan, ctx)
    check("Keep it a PAIR bridge" in cc and "do NOT touch" in cc,
          f"the bridge card context appends the no-third-wheel line: {cc}")
    # a bridge that DOES touch the third engine still VALIDATES (soft check — no error path)
    check(_validate_blueprint(bp) == [], "the third-wheel guard never adds a blueprint error")


def test_triad_ctx_resolution() -> None:
    print("_resolve_bridge_ctx(): resolves 3 archetypes into per-pair contexts + by_id:")
    bp = _triad_bp()
    ctx = _resolve_bridge_ctx(bp)
    check(ctx is not None and len(ctx["by_id"]) == 3, "by_id carries all three archetypes")
    check(len(ctx["pairs"]) == 3, f"a triad resolves all C(3,2)=3 pairs: {sorted(ctx['pairs'])}")
    check("ops_a" not in ctx, "a triad has no single top-level pair (only per-pair contexts)")
    # a 2-archetype bp keeps the legacy top-level pair for the old callers
    two = {"archetypes": [{"id": "forge_ramp", "name": "F"}, {"id": "counter_riposte", "name": "R"}]}
    c2 = _resolve_bridge_ctx(two)
    check(c2 is not None and "ops_a" in c2 and len(c2["pairs"]) == 1,
          "a 2-archetype bp exposes the single pair top-level (back-compat)")


def test_triad_fake_bridge_tags() -> None:
    print("_ensure_bridge_tags(): a triad tags declared PAIRS (never booleans) meeting per-pair floors:")
    bp = _triad_bp()
    arch = _archetype_ids(bp)
    br = [c for c in bp["cards"] if c.get("role") == "pool" and c.get("bridge")]
    check(all(isinstance(c["bridge"], list) for c in br), "every triad bridge tag is a declared [id1, id2] pair")
    from collections import Counter
    per = Counter(_bridge_pair(c, arch) for c in br)
    check(all(isinstance(k, tuple) for k in per), "every tagged pair resolves (no invalid tags)")
    check(len(per) == 3 and all(v >= bridges.MIN_BRIDGES_PER_PAIR for v in per.values()),
          f"all three pairs clear the per-pair floor: {dict(per)}")
    check(any(str(c.get("rarity", "")).lower() == "rare" for c in br), "a triad fake still has a rare poster")


def main() -> int:
    test_card_tokens()
    test_witness_disjoint()
    test_witness_overlapping_fallback()
    test_witness_orb_vs_normal()
    test_repair_directive()
    test_validate_blueprint_bridge_rule()
    test_fake_path_bridge_tags()
    test_card_context()
    test_resolve_bridge_ctx()
    test_enforce_bridge_repair_in_place()
    test_third_wheel_and_pair_key()
    test_bridge_pair_parsing()
    test_validate_triad_bridges()
    test_validate_triad_strategy_mapping()
    test_third_wheel_is_soft()
    test_triad_ctx_resolution()
    test_triad_fake_bridge_tags()
    print(f"\n{_PASS} passed, {_FAIL} failed")
    return 1 if _FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
