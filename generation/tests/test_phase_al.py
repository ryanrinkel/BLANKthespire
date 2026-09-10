"""Phase AL — RICHER TRIGGER PAYLOADS (VOCAB_GAP_REMEDIATION_PLAN Wave 3, vocab v42) — offline, no API key.

Run:  uv run python -m tests.test_phase_al       (from generation/)
Exits nonzero on any failure. Covers the v42 payload mechanics on the generation side, in lockstep with the C#:
  1. the class engines as payloads — `apply_status_custom` (status class), `summon_attack` / `buff_summon` (summon
     class) inside an add_trigger: validate under the right class context, describe byte-identically, emit; and are
     REJECTED without the class context / with a bad status / with a stray status_name;
  2. `hits` on a payload damage (targeted) / summon_attack — validates, describes "… N times …", emits the positional
     Hits; REJECTED on any other payload op and together with a scale;
  3. payload `scale` += cards_in_hand / unspent_energy_last_turn / forged (additive, damage/block only, amount >= 1),
     a TARGETED damage may be scaled; REJECTED on channel_orb/evoke/forge/balance_step/summon ops, on a targeted
     non-damage, and for the card-only scalars (x / target_debuff_count / damage_dealt_unblocked / tag_cards_owned).
Plus: the vocab stamp is v42; the census counts payload ops / scaled + multi-hit payloads; the schema / vocabulary /
exemplars / archetypes / featured menu carry the tokens.
"""
from __future__ import annotations

import json
import re
import sys

from btsgen.class_forge import point_btsgen_at_mod_contract

point_btsgen_at_mod_contract()

from btsgen import bts1, cardgen, census, featured, paths  # noqa: E402
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


def _power(cid, trigger, payload, **flags):
    trig = {"op": "add_trigger", "trigger": trigger, "effects": payload}
    trig.update(flags)
    return {"id": cid, "name": cid.replace("_", " ").title(), "type": "power", "rarity": "uncommon",
            "cost": 1, "target": "self", "source": "llm", "effects": [trig]}


def _desc(card) -> str:
    return cardgen.describe(card["effects"], "self")


def test_version() -> None:
    print("Phase AL vocab stamp is at least v42:")
    check(bts1.VOCAB_VERSION >= 42, f"bts1.VOCAB_VERSION must be >= 42 (Phase AL), got {bts1.VOCAB_VERSION}")


def _t_class_engines(vc: CardValidator, vn: CardValidator) -> None:
    print("class engines inside a payload: apply_status_custom / summon_attack / buff_summon validate, describe, emit:")
    # --- status class: the signature status as a per-turn engine
    hone = _power("al_hone", "turn_start", [{"op": "apply_status_custom", "status_name": "Razor Focus", "amount": 1}])
    r = vc.validate(hone)
    check(r.ok, f"turn_start -> apply_status_custom (status class) validates: {r.errors}")
    check(_desc(hone) == "At the start of your turn, gain 1 Razor Focus.", f"describe: {_desc(hone)!r}")
    _, src = cardgen.gen_class(hone)
    check('new EffectSpec("apply_status_custom", 1, StatusName: "Razor Focus")' in src, "emit carries the nested StatusName arg")
    # a custom DEBUFF form takes a target and reads "apply … to ALL enemies"
    brand = _power("al_brand", "turn_start", [{"op": "apply_status_custom", "status_name": "Razor Focus", "amount": 2, "target": "all_enemies"}])
    r = vc.validate(brand)
    check(r.ok, f"targeted apply_status_custom validates: {r.errors}")
    check(_desc(brand) == "At the start of your turn, apply 2 Razor Focus to ALL enemies.", f"targeted describe: {_desc(brand)!r}")
    check('Target: "all_enemies"' in cardgen.gen_class(brand)[1], "targeted custom status emits the Target arg")
    # attacker form on the attacked trigger
    sting = _power("al_sting", "attacked", [{"op": "apply_status_custom", "status_name": "Razor Focus", "amount": 1, "target": "attacker"}])
    check(vc.validate(sting).ok, f"attacked -> custom status to the attacker validates: {vc.validate(sting).errors}")
    check(_desc(sting) == "Whenever you are attacked, apply 1 Razor Focus to the attacker.", f"attacker describe: {_desc(sting)!r}")
    # rejections: no class context / unknown status / missing status_name / stray status_name
    r = vn.validate(hone)
    check(not r.ok and any("status_pool" in e for e in r.errors), f"no status context -> rejected naming the pool: {r.errors}")
    bad = _power("al_bad_name", "turn_start", [{"op": "apply_status_custom", "status_name": "Nope", "amount": 1}])
    check(not vc.validate(bad).ok, "an unknown status_name is rejected")
    stray = _power("al_stray", "turn_start", [{"op": "block", "amount": 3, "status_name": "Razor Focus"}])
    check(not vc.validate(stray).ok, "a stray status_name on a block payload is rejected (schema + validator)")
    # --- summon class: the minion acting on its own
    hour = _power("al_hour", "turn_end", [{"op": "summon_attack", "amount": 4, "hits": 2}])
    r = vc.validate(hour)
    check(r.ok, f"turn_end -> summon_attack x2 validates: {r.errors}")
    check(_desc(hour) == "At the end of your turn, deal 4 damage 2 times with your summon.", f"describe: {_desc(hour)!r}")
    check('new EffectSpec("summon_attack", 4, null, 2)' in cardgen.gen_class(hour)[1], "emit carries the positional Hits on the nested summon_attack")
    single = _power("al_single", "turn_end", [{"op": "summon_attack", "amount": 5}])
    check(_desc(single) == "At the end of your turn, deal 5 damage with your summon.", f"single-hit describe: {_desc(single)!r}")
    aoe = _power("al_aoe", "turn_end", [{"op": "summon_attack", "amount": 3, "target": "all_enemies"}])
    check(vc.validate(aoe).ok, f"targeted summon_attack validates: {vc.validate(aoe).errors}")
    check(_desc(aoe) == "At the end of your turn, deal 3 damage with your summon to ALL enemies.", f"aoe describe: {_desc(aoe)!r}")
    drill = _power("al_drill", "turn_start", [{"op": "buff_summon", "amount": 1, "status": "strength"}])
    r = vc.validate(drill)
    check(r.ok, f"turn_start -> buff_summon validates: {r.errors}")
    check(_desc(drill) == "At the start of your turn, your summon gains 1 Strength.", f"describe: {_desc(drill)!r}")
    check('new EffectSpec("buff_summon", 1, "strength")' in cardgen.gen_class(drill)[1], "emit carries the nested buff_summon status")
    dflt = _power("al_dflt", "turn_start", [{"op": "buff_summon", "amount": 2}])
    check(vc.validate(dflt).ok and _desc(dflt) == "At the start of your turn, your summon gains 2 Strength.",
          f"buff_summon defaults to Strength: {_desc(dflt)!r}")
    # rejections: no summon context / a debuff on buff_summon / a targeted buff_summon
    r = vn.validate(hour)
    check(not r.ok and any("summon class" in e for e in r.errors), f"no summon context -> summon_attack rejected: {r.errors}")
    check(not vn.validate(drill).ok, "no summon context -> buff_summon rejected")
    weak = _power("al_weak_drill", "turn_start", [{"op": "buff_summon", "amount": 1, "status": "weak"}])
    check(not vc.validate(weak).ok, "buff_summon with a debuff status is rejected")
    tb = _power("al_tgt_drill", "turn_start", [{"op": "buff_summon", "amount": 1, "target": "enemy"}])
    check(not vc.validate(tb).ok, "a targeted buff_summon is rejected (schema target/op coupling)")
    # the full plan-tester shape: once_per_turn + when + a multi-hit summon strike
    full = _power("al_full", "on_card_played", [{"op": "summon_attack", "amount": 2, "hits": 2}],
                  once_per_turn=True, when={"kind": "turn_at_least", "value": 2})
    check(vc.validate(full).ok, f"reactive multi-hit summon strike validates: {vc.validate(full).errors}")
    check(_desc(full) == "Whenever you play a card, deal 2 damage 2 times with your summon (once per turn) if it is turn 2+.",
          f"full describe: {_desc(full)!r}")


def _t_hits(v: CardValidator) -> None:
    print("payload hits: legal on a targeted damage / summon_attack, rejected elsewhere and with a scale:")
    flurry = _power("al_flurry", "attacked", [{"op": "damage", "amount": 2, "hits": 3, "target": "attacker"}], once_per_turn=True)
    r = v.validate(flurry)
    check(r.ok, f"attacked -> deal 2 damage 3 times to the attacker validates: {r.errors}")
    check(_desc(flurry) == "Whenever you are attacked, deal 2 damage 3 times to the attacker (once per turn).", f"describe: {_desc(flurry)!r}")
    check('new EffectSpec("damage", 2, null, 3, Target: "attacker")' in cardgen.gen_class(flurry)[1], "emit carries Hits + Target on the payload damage")
    aoe = _power("al_aoe_hits", "turn_start", [{"op": "damage", "amount": 1, "hits": 4, "target": "all_enemies"}])
    check(v.validate(aoe).ok and _desc(aoe) == "At the start of your turn, deal 1 damage 4 times to ALL enemies.", f"aoe hits: {_desc(aoe)!r}")
    for op, extra in (("block", {}), ("draw", {}), ("heal", {}), ("apply_status", {"status": "strength"}),
                      ("apply_status", {"status": "weak", "target": "enemy"})):
        bad = _power(f"al_bad_hits_{op}_{len(extra)}", "turn_start", [dict({"op": op, "amount": 2, "hits": 2}, **extra)])
        check(not v.validate(bad).ok, f"hits on a payload '{op}' is rejected")
    both = _power("al_hits_scale", "turn_start", [{"op": "damage", "amount": 1, "hits": 2, "scale": "cards_in_hand", "target": "enemy"}])
    r = v.validate(both)
    check(not r.ok, f"hits + scale on one payload effect is rejected: {r.errors}")
    check(not v.validate(_power("al_hits1", "turn_start", [{"op": "damage", "amount": 3, "hits": 1, "target": "enemy"}])).ok,
          "hits:1 is rejected by the schema minimum (2)")


def _t_scales(v: CardValidator, vc: CardValidator) -> None:
    print("payload scales: the four player-level reads validate + describe; card-only scalars and bad ops are rejected:")
    thrift = _power("al_thrift", "turn_start", [{"op": "block", "amount": 1, "scale": "unspent_energy_last_turn"}])
    check(v.validate(thrift).ok, f"block scale unspent_energy_last_turn validates: {v.validate(thrift).errors}")
    check(_desc(thrift) == "At the start of your turn, gain Block equal to your unspent energy last turn.", f"describe: {_desc(thrift)!r}")
    check('new EffectSpec("block", 1, null, 1, "unspent_energy_last_turn")' in cardgen.gen_class(thrift)[1], "emit carries the payload scale")
    crowd = _power("al_crowd", "turn_start", [{"op": "damage", "amount": 1, "scale": "cards_in_hand", "target": "all_enemies"}])
    check(v.validate(crowd).ok, f"a TARGETED damage may be scaled (cards_in_hand): {v.validate(crowd).errors}")
    check(_desc(crowd) == "At the start of your turn, deal damage equal to the cards in your hand to ALL enemies.", f"describe: {_desc(crowd)!r}")
    # AutoSlay finding (GAPTESTAL1): the turn_end hook fires after the discard, so cards_in_hand on turn_end reads 0 → rejected
    late = _power("al_late", "turn_end", [{"op": "block", "amount": 1, "scale": "cards_in_hand"}])
    r = v.validate(late)
    check(not r.ok and any("turn_end" in e and "cards_in_hand" in e for e in r.errors), f"cards_in_hand on turn_end is rejected: {r.errors}")
    check(v.validate(_power("al_react_cih", "on_card_played", [{"op": "block", "amount": 1, "scale": "cards_in_hand"}], once_per_turn=True)).ok,
          "cards_in_hand on a reactive trigger stays legal")
    draw = _power("al_draw", "turn_start", [{"op": "draw", "amount": 1, "scale": "cards_retained"}])
    check(v.validate(draw).ok and _desc(draw) == "At the start of your turn, draw cards equal to cards retained.",
          f"cards_retained keeps its F5 wording: {_desc(draw)!r}")
    en = _power("al_en", "turn_start", [{"op": "gain_energy", "amount": 1, "scale": "cards_in_hand"}])
    check(v.validate(en).ok and _desc(en) == "At the start of your turn, gain energy equal to the cards in your hand.", f"energy: {_desc(en)!r}")
    st = _power("al_st", "turn_end", [{"op": "apply_status", "status": "strength", "amount": 1, "scale": "unspent_energy_last_turn"}])
    check(v.validate(st).ok and _desc(st) == "At the end of your turn, gain Strength equal to your unspent energy last turn.", f"status: {_desc(st)!r}")
    # forged: ADDITIVE, damage/block only, amount >= 1 (the card-level rule)
    tithe = _power("al_tithe", "turn_end", [{"op": "block", "amount": 2, "scale": "forged"}])
    check(v.validate(tithe).ok, f"block scale forged validates: {v.validate(tithe).errors}")
    check(_desc(tithe) == "At the end of your turn, gain 2 Block, plus your Forge.", f"forged describe: {_desc(tithe)!r}")
    fd = _power("al_fd", "attacked", [{"op": "damage", "amount": 3, "scale": "forged", "target": "attacker"}])
    check(v.validate(fd).ok and _desc(fd) == "Whenever you are attacked, deal 3 damage to the attacker, plus your Forge.",
          f"forged damage describe: {_desc(fd)!r}")
    check(not v.validate(_power("al_fdraw", "turn_start", [{"op": "draw", "amount": 1, "scale": "forged"}])).ok, "forged on a draw payload is rejected")
    # rejections: card-only scalars, targeted non-damage, non-scalable ops, the fixed-income ops
    for sc in ("x", "target_debuff_count", "damage_dealt_unblocked", "tag_cards_owned"):
        bad = _power(f"al_bad_scale_{sc}", "turn_start", [{"op": "block", "amount": 1, "scale": sc}])
        check(not v.validate(bad).ok, f"card-only scale '{sc}' is rejected inside a payload")
    tgt_st = _power("al_tgt_st", "turn_start", [{"op": "apply_status", "status": "weak", "amount": 1, "scale": "cards_in_hand", "target": "enemy"}])
    r = v.validate(tgt_st)
    check(not r.ok and any("only a targeted trigger 'damage' may be scaled" in e for e in r.errors), f"a targeted debuff can't be scaled: {r.errors}")
    tgt_sa = _power("al_tgt_sa", "turn_end", [{"op": "summon_attack", "amount": 2, "scale": "cards_in_hand", "target": "enemy"}])
    check(not vc.validate(tgt_sa).ok, "a scaled summon_attack payload is rejected")
    self_sa = _power("al_self_sa", "turn_end", [{"op": "summon_attack", "amount": 2, "scale": "forged"}])
    check(not vc.validate(self_sa).ok, "a scaled untargeted summon_attack payload is rejected")
    for op, extra in (("channel_orb", {"orb": "lightning"}), ("evoke", {}), ("forge", {}), ("balance_step", {"pole": "dark"}),
                      ("discard", {}), ("heal_summon", {}), ("shield_summon", {})):
        bad = _power(f"al_bad_sop_{op}", "turn_start", [dict({"op": op, "amount": 2, "scale": "cards_in_hand"}, **extra)])
        check(not vc.validate(bad).ok, f"scale on a payload '{op}' is rejected")


def _t_census_and_contract() -> None:
    print("census counts payload ops / scaled + multi-hit payloads; schema / vocabulary / exemplars / archetypes / featured carry the tokens:")
    c = _power("al_c1", "turn_end", [{"op": "summon_attack", "amount": 4, "hits": 2},
                                     {"op": "block", "amount": 1, "scale": "cards_in_hand"}])
    cc = census.walk_card(c)
    check(cc.payload_ops["summon_attack"] == 1 and cc.payload_ops["block"] == 1, f"payload_ops: {dict(cc.payload_ops)}")
    check(cc.scaled_payloads == 1 and cc.multi_hit_payloads == 1 and cc.multi_hit == 1,
          f"scaled={cc.scaled_payloads} mh_payload={cc.multi_hit_payloads} mh={cc.multi_hit}")
    agg = census.census_cards([c, c])
    check(agg.payload_ops["summon_attack"] == 2 and agg.scaled_payloads == 2 and agg.multi_hit_payloads == 2, "aggregate payload counters")
    rep = census.format_report([("X", agg)])
    check("scaled_payloads=2" in rep and "multi_hit_payloads=2" in rep and "summon_attack" in rep, "report prints the AL counters")
    merged = census.Census()
    merged.merge(agg)
    check(merged.payload_ops["summon_attack"] == 2 and merged.scaled_payloads == 2, "merge folds the AL counters")
    schema = json.loads(paths.CARD_SCHEMA.read_text(encoding="utf-8"))
    te = schema["$defs"]["triggerEffect"]["properties"]
    check({"apply_status_custom", "summon_attack", "buff_summon"} <= set(te["op"]["enum"]), "schema payload op enum has the class engines")
    check(set(te["scale"]["enum"]) == {"cards_retained", "cards_in_hand", "unspent_energy_last_turn", "forged"}, "schema payload scale enum")
    check("hits" in te and "status_name" in te, "schema payload declares hits + status_name")
    vocab = paths.VOCABULARY.read_text(encoding="utf-8")
    check("deal 4 damage 2 times with your summon" in vocab and "gain 1 Razor Focus" in vocab
          and "plus your Forge" in vocab and "cards in your hand to ALL enemies" in vocab, "VOCABULARY.md shows the new payload wordings")
    pool = json.loads((__import__("pathlib").Path(paths.__file__).parent / "data" / "exemplar_pool.json").read_text(encoding="utf-8"))
    by_id = {e["card"]["id"]: e for e in pool["exemplars"]}
    for cid, needs in (("ex_honing_ritual", "status"), ("ex_thralls_hour", "summon"), ("ex_drill_cadence", "summon"),
                       ("ex_flurry_ward", ""), ("ex_ember_tithe", "forge"), ("ex_thrift_bulwark", ""), ("ex_crowded_mind", "")):
        check(cid in by_id and by_id[cid]["needs"] == needs, f"exemplar {cid} present with needs='{needs}'")
    arch = json.loads((__import__("pathlib").Path(paths.__file__).parent / "data" / "archetypes.json").read_text(encoding="utf-8"))
    ops = {a["id"]: a["vocabulary"]["ops"] for a in arch["archetypes"]}
    check("add_trigger" in ops["summon_swarm"] and "add_trigger" in ops["status_signature"], "archetypes: the two class kinds list add_trigger")
    ids = {f.id for f in featured.CLASS_KIND_MENU}
    check({"custom_status_engine", "summon_engine"} <= ids, "featured class-kind menu has the two engine entries")
    eng = next(f for f in featured.CLASS_KIND_MENU if f.id == "summon_engine")
    check(eng.detect(cc) and not eng.detect(census.walk_card(_power("al_plain", "turn_end", [{"op": "block", "amount": 3}]))),
          "summon_engine detector keys off payload_ops")
    seng = next(f for f in featured.CLASS_KIND_MENU if f.id == "custom_status_engine")
    hone = census.walk_card(_power("al_hone2", "turn_start", [{"op": "apply_status_custom", "status_name": "Razor Focus", "amount": 1}]))
    card_level = census.walk_card({"id": "x", "name": "X", "type": "skill", "rarity": "common", "cost": 1, "target": "self",
                                   "effects": [{"op": "apply_status_custom", "status_name": "Razor Focus", "amount": 1}]})
    check(seng.detect(hone) and not seng.detect(card_level), "custom_status_engine fires on a payload, not a card-level apply")


def main() -> int:
    v = CardValidator()
    vc = CardValidator(extra_statuses={"Razor Focus"}, extra_summons={"Bone Thrall"})
    test_version()
    _t_class_engines(vc, v)
    _t_hits(v)
    _t_scales(v, vc)
    _t_census_and_contract()
    print(f"\n{_PASS} passed, {_FAIL} failed")
    return 1 if _FAIL else 0


# pytest entry point (re-runs main's checks in isolation for a clear failure name)
def test_phase_al_all() -> None:
    assert main() == 0


if __name__ == "__main__":
    sys.exit(main())
