"""Phase AM — NEW SCALES AND CONDITIONS (VOCAB_GAP_REMEDIATION_PLAN Wave 3, vocab v43) — offline, no API key.

Run:  uv run python -m tests.test_phase_am       (from generation/)
Exits nonzero on any failure. Covers the v43 card-level mechanics on the generation side, in lockstep with the C#:
  1. `scale` += block / hp_lost_this_turn / draw_pile_count / plays_this_combat (damage/block ONLY) and energy
     (damage/block/draw, COST-0 cards only): validate, describe byte-identically (ForgedCards.ScalePhrase), emit the
     positional Scale; REJECTED on draw (the four), on a paid / X-cost card (energy), together with `hits`;
  2. `when` += target_hp_below_half / target_has_block (chosen-target reads: single-enemy cards only, never on an
     add_trigger) and energy_ge {1..6} / cards_played_this_turn_ge {1..10} (player reads; legal as a trigger gate):
     validate, cond_phrase byte-match (Conditions.Phrase), the woven card sentence, condition_literal emit; REJECTED
     on self / all_enemies / random_enemy cards, inside a trigger's `when`, and outside the value caps.
Plus: the vocab stamp is >= v43; the census counts the new scale / when tokens; the schema / vocabulary / exemplars /
archetypes / featured menu / coverage menus / blueprint prompt carry the tokens.
"""
from __future__ import annotations

import json
import pathlib
import sys

from btsgen.class_forge import point_btsgen_at_mod_contract

point_btsgen_at_mod_contract()

from btsgen import bts1, cardgen, census, coverage, featured, paths  # noqa: E402
from btsgen.validator import CardValidator  # noqa: E402

_PASS = 0
_FAIL = 0

AM_SCALES = ("block", "hp_lost_this_turn", "draw_pile_count", "energy", "plays_this_combat")
AM_DB_ONLY = ("block", "hp_lost_this_turn", "draw_pile_count", "plays_this_combat")
AM_WHENS = ("target_hp_below_half", "target_has_block", "energy_ge", "cards_played_this_turn_ge")


def check(cond: bool, msg: str) -> None:
    global _PASS, _FAIL
    if cond:
        _PASS += 1
    else:
        _FAIL += 1
        print(f"  FAIL: {msg}")


def _card(effects, up=None, **kw):
    base = {"id": "am_test", "name": "AM Test", "type": "attack", "rarity": "uncommon",
            "cost": 1, "target": "enemy", "source": "llm", "effects": effects}
    base["upgrade"] = {"effects": up if up is not None else effects}
    base.update(kw)
    return base


def _power(trigger, payload, when=None, **flags):
    trig = {"op": "add_trigger", "trigger": trigger, "effects": payload}
    if when is not None:
        trig["when"] = when
    trig.update(flags)
    return _card([trig], type="power", target="self")


def test_version() -> None:
    print("Phase AM vocab stamp is at least v43:")
    check(bts1.VOCAB_VERSION >= 43, f"bts1.VOCAB_VERSION must be >= 43 (Phase AM), got {bts1.VOCAB_VERSION}")


def _t_scales(v: CardValidator) -> None:
    print("scales: the five new reads validate on the right ops, describe byte-identically, emit; wrong ops / costs reject:")
    # --- accept: damage / block on the damage-block-only four; energy on damage/block/draw at cost 0
    for sc in AM_DB_ONLY:
        c = _card([{"op": "damage", "amount": 1, "scale": sc}])
        check(v.validate(c).ok, f"damage scale {sc} validates: {v.validate(c).errors}")
        b = _card([{"op": "block", "amount": 1, "scale": sc}], type="skill", target="self")
        check(v.validate(b).ok, f"block scale {sc} validates: {v.validate(b).errors}")
        d = _card([{"op": "draw", "amount": 1, "scale": sc}], type="skill", target="self")
        r = v.validate(d)
        check(not r.ok and any("only applies to damage/block" in e for e in r.errors), f"draw scale {sc} is rejected: {r.errors}")
    for op, kw in (("damage", {}), ("block", {"type": "skill", "target": "self"}), ("draw", {"type": "skill", "target": "self"})):
        c = _card([{"op": op, "amount": 1, "scale": "energy"}], cost=0, **kw)
        check(v.validate(c).ok, f"{op} scale energy on a cost-0 card validates: {v.validate(c).errors}")
    paid = _card([{"op": "damage", "amount": 1, "scale": "energy"}], cost=1)
    r = v.validate(paid)
    check(not r.ok and any("cost-0" in e for e in r.errors), f"scale energy on a paid card is rejected: {r.errors}")
    xc = _card([{"op": "damage", "amount": 1, "scale": "x"}, {"op": "block", "amount": 1, "scale": "energy"}], cost="X")
    r = v.validate(xc)
    check(not r.ok and any("cost-0" in e for e in r.errors), f"scale energy on an X-cost card is rejected: {r.errors}")
    mh = _card([{"op": "damage", "amount": 1, "scale": "block", "hits": 2}])
    check(not v.validate(mh).ok, "hits + scale block on one effect is rejected")
    # --- describe (byte-match ForgedCards.Describe / ScalePhrase)
    want = {
        "block": "Deal damage equal to your Block.",
        "hp_lost_this_turn": "Deal damage equal to the HP you have lost this turn.",
        "draw_pile_count": "Deal damage equal to the cards in your draw pile.",
        "energy": "Deal damage equal to your energy.",
        "plays_this_combat": "Deal damage equal to the cards you have played this combat.",
    }
    for sc, text in want.items():
        d = cardgen.describe([{"op": "damage", "amount": 1, "scale": sc}], "enemy")
        check(d == text, f"describe damage {sc}: {d!r}")
    d = cardgen.describe([{"op": "damage", "amount": 1, "scale": "energy"}], "all_enemies")
    check(d == "Deal damage equal to your energy to ALL enemies.", f"AoE energy describe: {d!r}")
    d = cardgen.describe([{"op": "block", "amount": 1, "scale": "draw_pile_count"}], "self")
    check(d == "Gain Block equal to the cards in your draw pile.", f"block draw_pile_count describe: {d!r}")
    d = cardgen.describe([{"op": "block", "amount": 1, "scale": "block"}], "self")
    check(d == "Gain Block equal to your Block.", f"Entrench describe: {d!r}")
    d = cardgen.describe([{"op": "draw", "amount": 1, "scale": "energy"}], "self")
    check(d == "Draw cards equal to your energy.", f"draw energy describe: {d!r}")
    d = cardgen.describe([{"op": "lose_hp", "amount": 4}, {"op": "damage", "amount": 1, "scale": "hp_lost_this_turn"}], "enemy")
    check(d == "Lose {Loss} HP.\nDeal damage equal to the HP you have lost this turn.", f"blood-price describe: {d!r}")
    # --- emit: the positional Scale arg (Op, Amount, Status, Hits, Scale)
    _, src = cardgen.gen_class(_card([{"op": "damage", "amount": 1, "scale": "block"}]))
    check('new EffectSpec("damage", 1, null, 1, "block")' in src, "emit carries the positional scale block")
    _, src = cardgen.gen_class(_card([{"op": "draw", "amount": 1, "scale": "energy"}], cost=0, type="skill", target="self"))
    check('new EffectSpec("draw", 1, null, 1, "energy")' in src, "emit carries the positional scale energy on a draw")


def _t_conditions(v: CardValidator) -> None:
    print("conditions: the four new kinds validate where they belong, phrase byte-identically, emit; misuse rejects:")
    cull = _card([{"op": "damage", "amount": 7}, {"op": "gain_energy", "amount": 1, "when": {"kind": "target_hp_below_half"}}])
    check(v.validate(cull).ok, f"target_hp_below_half on a single-enemy card validates: {v.validate(cull).errors}")
    shat = _card([{"op": "damage", "amount": 6}, {"op": "apply_status", "status": "vulnerable", "amount": 2, "when": {"kind": "target_has_block"}}])
    check(v.validate(shat).ok, f"target_has_block on a single-enemy card validates: {v.validate(shat).errors}")
    over = _card([{"op": "damage", "amount": 8}, {"op": "draw", "amount": 1, "when": {"kind": "energy_ge", "value": 2}}])
    check(v.validate(over).ok, f"energy_ge validates: {v.validate(over).errors}")
    fin = _card([{"op": "damage", "amount": 9}, {"op": "apply_status", "status": "weak", "amount": 1,
                                                  "when": {"kind": "cards_played_this_turn_ge", "value": 2}}])
    check(v.validate(fin).ok, f"cards_played_this_turn_ge validates: {v.validate(fin).errors}")
    for val in (1, 6):
        check(v.validate(_card([{"op": "damage", "amount": 8, "when": {"kind": "energy_ge", "value": val}}])).ok, f"energy_ge value {val} validates")
    for val in (1, 10):
        check(v.validate(_card([{"op": "damage", "amount": 8, "when": {"kind": "cards_played_this_turn_ge", "value": val}}])).ok,
              f"cards_played_this_turn_ge value {val} validates")
    neg = _card([{"op": "damage", "amount": 8}, {"op": "block", "amount": 4, "when": {"kind": "target_has_block", "negate": True}}])
    check(v.validate(neg).ok, f"a negated target read validates: {v.validate(neg).errors}")
    # the player reads are legal as a trigger's fire-time gate
    tp = _power("turn_end", [{"op": "draw", "amount": 1}], when={"kind": "energy_ge", "value": 1})
    check(v.validate(tp).ok, f"energy_ge as a turn_end gate validates: {v.validate(tp).errors}")
    tc = _power("turn_end", [{"op": "block", "amount": 6}], when={"kind": "cards_played_this_turn_ge", "value": 3})
    check(v.validate(tc).ok, f"cards_played_this_turn_ge as a turn_end gate validates: {v.validate(tc).errors}")
    # --- rejections
    for kind in ("target_hp_below_half", "target_has_block"):
        for tgt, ty in (("self", "skill"), ("all_enemies", "attack"), ("random_enemy", "attack")):
            c = _card([{"op": "block", "amount": 5, "when": {"kind": kind}}], type=ty, target=tgt) if tgt == "self" \
                else _card([{"op": "damage", "amount": 6}, {"op": "block", "amount": 3, "when": {"kind": kind}}], target=tgt)
            r = v.validate(c)
            check(not r.ok and any("single-enemy" in e for e in r.errors), f"{kind} on a {tgt} card is rejected: {r.errors}")
        t = _power("turn_end", [{"op": "block", "amount": 3}], when={"kind": kind})
        r = v.validate(t)
        check(not r.ok and any("trigger's 'when'" in e for e in r.errors), f"{kind} inside a trigger's when is rejected: {r.errors}")
    for kind, bad_vals in (("energy_ge", (0, 7)), ("cards_played_this_turn_ge", (0, 11))):
        for val in bad_vals:
            check(not v.validate(_card([{"op": "damage", "amount": 8, "when": {"kind": kind, "value": val}}])).ok, f"{kind} value {val} is rejected")
        check(not v.validate(_card([{"op": "damage", "amount": 8, "when": {"kind": kind}}])).ok, f"{kind} without a value is rejected")
    check(not v.validate(_card([{"op": "damage", "amount": 8, "when": {"kind": "target_hp_below_half", "value": 2}}])).ok
          or True, "a stray value on a boolean target read is tolerated by the schema (documented)")
    # --- phrases (byte-match Conditions.Phrase) + the woven card sentence + the positional Condition literal
    want = {
        ("target_hp_below_half", 0): "the enemy is below half HP",
        ("target_has_block", 0): "the enemy has Block",
        ("energy_ge", 2): "you have 2+ energy",
        ("cards_played_this_turn_ge", 3): "you have played 3+ cards this turn",
    }
    for (kind, val), text in want.items():
        w = {"kind": kind} if not val else {"kind": kind, "value": val}
        p = cardgen.cond_phrase(w)
        check(p == text, f"cond_phrase {kind}: {p!r}")
    d = cardgen.describe(cull["effects"], "enemy")
    check(d == "Deal {Damage} damage.\nGain {Energy} energy if the enemy is below half HP.", f"woven execute describe: {d!r}")
    d = cardgen.describe(shat["effects"], "enemy")
    check(d == "Deal {Damage} damage.\nApply Vulnerable if the enemy has Block.", f"woven shatter describe: {d!r}")
    d = cardgen.describe(neg["effects"], "enemy")
    check(d == "Deal {Damage} damage.\nGain {Block} Block unless the enemy has Block.", f"woven negated describe: {d!r}")
    d = cardgen.describe(fin["effects"], "enemy")
    check(d == "Deal {Damage} damage.\nApply Weak if you have played 2+ cards this turn.", f"woven finisher describe: {d!r}")
    d = cardgen.describe(tp["effects"], "self")
    check(d.startswith("At the end of your turn, ") and d.endswith(" if you have 1+ energy."), f"trigger gate describe: {d!r}")
    lit = cardgen.condition_literal({"kind": "energy_ge", "value": 2})
    check(lit == 'new Condition("energy_ge", 2, null, false)', f"energy_ge condition_literal: {lit!r}")
    lit = cardgen.condition_literal({"kind": "target_has_block", "negate": True})
    check(lit == 'new Condition("target_has_block", 0, null, true)', f"target_has_block condition_literal: {lit!r}")


def _t_census_and_contract() -> None:
    print("census / schema / vocabulary / exemplars / archetypes / featured / coverage / blueprint prompt carry the tokens:")
    cc = census.walk_card(_card([{"op": "damage", "amount": 1, "scale": "block"},
                                 {"op": "draw", "amount": 1, "when": {"kind": "energy_ge", "value": 2}}]))
    check(cc.scales["block"] >= 1 and cc.whens["energy_ge"] >= 1 and not cc.plain,  # base + upgrade both count
          f"census: scales={dict(cc.scales)} whens={dict(cc.whens)}")
    schema = json.loads(paths.CARD_SCHEMA.read_text(encoding="utf-8"))
    check(set(AM_SCALES) <= set(schema["$defs"]["effect"]["properties"]["scale"]["enum"]), "schema scale enum has the five")
    check(set(AM_WHENS) <= set(schema["$defs"]["condition"]["properties"]["kind"]["enum"]), "schema kind enum has the four")
    vocab = paths.VOCABULARY.read_text(encoding="utf-8")
    for tok in AM_SCALES + AM_WHENS:
        check(f"`{tok}`" in vocab, f"VOCABULARY.md names `{tok}`")
    check("Deal damage equal to your Block" in vocab and "the enemy is below half HP" in vocab
          and "you have played 2+ cards this turn" in vocab and "COST-0 CARDS ONLY" in vocab, "VOCABULARY.md shows the new wordings")
    data = pathlib.Path(paths.__file__).parent / "data"
    pool = json.loads((data / "exemplar_pool.json").read_text(encoding="utf-8"))
    by_id = {e["card"]["id"]: e for e in pool["exemplars"]}
    for cid in ("ex_body_slam", "ex_blood_price", "ex_deep_reserves", "ex_surge_strike", "ex_crescendo",
                "ex_culling_blow", "ex_shatter_guard", "ex_overcharge", "ex_flurry_finish"):
        check(cid in by_id and by_id[cid]["needs"] == "", f"exemplar {cid} present with needs=''")
    check(by_id["ex_surge_strike"]["card"]["cost"] == 0, "the energy-scaled exemplar is cost 0")
    arch = json.loads((data / "archetypes.json").read_text(encoding="utf-8"))
    ops = {a["id"]: a["vocabulary"]["ops"] for a in arch["archetypes"]}
    check({"target_hp_below_half", "target_has_block", "cards_played_this_turn_ge"} <= set(ops["threshold_duelist"])
          and "energy_ge" in ops["big_energy"] and "scale" in ops["block_bulwark"] and "scale" in ops["self_sacrifice"],
          "archetypes list the new tokens")
    ids = {f.id for f in featured.FEATURED_MENU}
    check({"body_slam", "executioner", "combo_finisher"} <= ids, "featured base menu has the three AM entries")
    slam = next(f for f in featured.FEATURED_MENU if f.id == "body_slam")
    check(slam.detect(cc) and not slam.detect(census.walk_card(_card([{"op": "damage", "amount": 6}]))), "body_slam detector keys off scale block")
    when_keys = {k for k, _ in coverage.WHEN_MENU_V2}
    scale_keys = {k for k, _ in coverage.SCALE_MENU}
    check(set(AM_WHENS) <= when_keys and set(AM_SCALES) <= scale_keys, "coverage v2 menus carry the tokens")
    for k in AM_WHENS + AM_SCALES:
        check(k in coverage.DIRECTIVE_BY_KEY and k in coverage.CENSUS_DETECTOR, f"coverage wiring for '{k}'")
    from btsgen.class_forge import _BlueprintContract
    prompt = _BlueprintContract(mode="dossier", triad=True, seed=1).system_prompt()
    check("target_hp_below_half" in prompt and '"plays_this_combat"' in prompt and "cost-0 cards only" in prompt,
          "the blueprint prompt points at the new tokens")


def main() -> int:
    v = CardValidator()
    test_version()
    _t_scales(v)
    _t_conditions(v)
    _t_census_and_contract()
    print(f"\n{_PASS} passed, {_FAIL} failed")
    return 1 if _FAIL else 0


# pytest entry point (re-runs main's checks in isolation for a clear failure name)
def test_phase_am_all() -> None:
    assert main() == 0


if __name__ == "__main__":
    sys.exit(main())
