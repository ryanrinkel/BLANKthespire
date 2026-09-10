"""Phase AO — CARD-TYPE-SCOPED COST MODIFIERS (VOCAB_GAP_REMEDIATION_PLAN Wave 3, vocab v45) — offline, no API key.

Run:  uv run python -m tests.test_phase_ao       (from generation/)
Exits nonzero on any failure. Covers the v45 `cost_shift` op on the generation side, in lockstep with the C#:
  1. shape: `cost_shift {card_type: attack|skill|power|all, amount: 1..2, scope: this_turn|combat, count?: 1..3}` validates;
     a missing/bad card_type or scope, amount 0 / 3, count 0 / 4, scope:combat with amount 2, the three fields on another
     op, two on one card, a BASIC carrier, and a non-rare combat scope all REJECT; a trigger-payload cost_shift is rejected;
  2. describe byte-matches ForgedCards.CostShiftSentence in every shape (flat / count 1 / count N × attack/skill/power/all ×
     this_turn/combat);
  3. emit carries the named CardKind / Scope (+ Count) args; census / card_tokens / the cost_trick detector see the op;
     the validator prices it (build-around) and the combat scope higher than the turn scope;
  4. the relic side: a turn_start `cost_shift` hook (this_turn, count 1) validates through both the relic validator (schema)
     and the class_forge relic gate; scope:combat on a relic rejects in both;
  5. the set-level warning fires only for >1 whole-combat cost_shift cards.
Plus: the vocab stamp is >= v45; the schema / vocabulary / relic contract / exemplars / archetypes / featured menu /
blueprint prompt carry the token.
"""
from __future__ import annotations

import json
import pathlib
import sys

from btsgen.class_forge import point_btsgen_at_mod_contract

point_btsgen_at_mod_contract()

from btsgen import bts1, cardgen, census, class_forge, featured, paths  # noqa: E402
from btsgen.bridges import card_tokens  # noqa: E402
from btsgen.character_validator import cost_shift_warnings  # noqa: E402
from btsgen.relic_validator import RelicValidator  # noqa: E402
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


def _card(effects, up=None, **kw):
    base = {"id": "ao_test", "name": "AO Test", "type": "skill", "rarity": "uncommon",
            "cost": 1, "target": "self", "source": "llm", "effects": effects}
    base["upgrade"] = {"effects": up if up is not None else effects}
    base.update(kw)
    return base


def _cs(card_type="attack", amount=1, scope="this_turn", count=None, **extra):
    e = {"op": "cost_shift", "card_type": card_type, "amount": amount, "scope": scope}
    if count is not None:
        e["count"] = count
    e.update(extra)
    return e


def _power(trigger, payload):
    return _card([{"op": "add_trigger", "trigger": trigger, "effects": payload}], type="power")


def test_version() -> None:
    print("Phase AO vocab stamp is at least v45:")
    check(bts1.VOCAB_VERSION >= 45, f"bts1.VOCAB_VERSION must be >= 45 (Phase AO), got {bts1.VOCAB_VERSION}")


def _t_shape(v: CardValidator) -> None:
    print("cost_shift: the legal shapes validate; every malformed / out-of-band shape rejects:")
    throttle = _card([_cs("attack", 1, "this_turn"), {"op": "draw", "amount": 1}])
    r = v.validate(throttle)
    check(r.ok, f"'Your Attacks cost 1 less this turn' + draw validates: {r.errors}")
    for ct in ("attack", "skill", "power", "all"):
        for sc in ("this_turn",):
            for amt in (1, 2):
                check(v.validate(_card([_cs(ct, amt, sc)])).ok, f"cost_shift {ct} -{amt} {sc} validates")
    check(v.validate(_card([_cs("skill", 2, "this_turn", count=1)], cost=0, rarity="common")).ok, "the count-1 form validates on a common")
    check(v.validate(_card([_cs("all", 1, "this_turn", count=3)])).ok, "count 3 validates")
    war = _card([_cs("attack", 1, "combat")], type="power", rarity="rare", cost=2)
    check(v.validate(war).ok, f"a rare whole-combat discount validates: {v.validate(war).errors}")
    check(v.validate(_card([_cs("attack", 1, "combat", count=2)], rarity="rare")).ok, "combat scope + count validates at rare")
    bad = [
        (_card([{"op": "cost_shift", "amount": 1, "scope": "this_turn"}]), "card_type", "missing card_type"),
        (_card([_cs("curse", 1, "this_turn")]), "card_type", "card_type curse"),
        (_card([{"op": "cost_shift", "card_type": "attack", "amount": 1}]), "scope", "missing scope"),
        (_card([_cs("attack", 1, "next_turn")]), "scope", "scope next_turn"),
        (_card([_cs("attack", 0, "this_turn")]), "amount", "amount 0"),
        (_card([_cs("attack", 3, "this_turn")]), "amount", "amount 3"),
        (_card([_cs("attack", 1, "this_turn", count=0)]), "count", "count 0"),
        (_card([_cs("attack", 1, "this_turn", count=4)]), "count", "count 4"),
        (_card([_cs("attack", 2, "combat")], rarity="rare"), "amount 1", "combat scope with amount 2"),
        (_card([_cs("attack", 1, "combat")], rarity="uncommon"), "RARE-ONLY", "combat scope on an uncommon"),
        (_card([_cs("attack", 1, "this_turn")], rarity="basic", cost=1), "BASIC", "cost_shift on a basic"),
        (_card([_cs("attack", 1, "this_turn"), _cs("skill", 1, "this_turn")]), "at most one", "two cost_shift on one card"),
        (_card([{"op": "block", "amount": 5, "card_type": "attack"}]), "only apply to cost_shift", "card_type on block"),
        (_card([{"op": "block", "amount": 5, "scope": "this_turn"}]), "only apply to cost_shift", "scope on block"),
        (_card([{"op": "block", "amount": 5, "count": 1}]), "only apply to cost_shift", "count on block"),
        (_power("turn_start", [_cs("attack", 1, "this_turn")]), "", "cost_shift inside a trigger payload (card-only)"),
    ]
    for card, needle, label in bad:
        r = v.validate(card)
        check(not r.ok and any(needle.lower() in e.lower() for e in r.errors), f"{label} is rejected: {r.errors}")


def _t_describe() -> None:
    print("describe byte-matches ForgedCards.CostShiftSentence in every shape:")
    want = [
        (_cs("attack", 1, "this_turn"), "Your Attacks cost 1 less this turn."),
        (_cs("skill", 2, "this_turn"), "Your Skills cost 2 less this turn."),
        (_cs("power", 1, "this_turn"), "Your Powers cost 1 less this turn."),
        (_cs("all", 1, "this_turn"), "Your cards cost 1 less this turn."),
        (_cs("attack", 1, "combat"), "Your Attacks cost 1 less this combat."),
        (_cs("all", 1, "combat"), "Your cards cost 1 less this combat."),
        (_cs("skill", 1, "this_turn", count=1), "Your next Skill costs 1 less this turn."),
        (_cs("attack", 2, "this_turn", count=1), "Your next Attack costs 2 less this turn."),
        (_cs("power", 1, "this_turn", count=1), "Your next Power costs 1 less this turn."),
        (_cs("all", 1, "this_turn", count=1), "Your next card costs 1 less this turn."),
        (_cs("attack", 1, "this_turn", count=2), "Your next 2 Attacks cost 1 less this turn."),
        (_cs("all", 1, "combat", count=3), "Your next 3 cards cost 1 less this combat."),
    ]
    for eff, text in want:
        d = cardgen.describe([eff], "self")
        check(d == text, f"describe {eff}: {d!r} != {text!r}")
    d = cardgen.describe([_cs("attack", 1, "this_turn"), {"op": "draw", "amount": 1}], "self")
    check(d == "Your Attacks cost 1 less this turn.\nDraw {Cards} card(s).", f"the sentence composes with a draw: {d!r}")
    d = cardgen.describe([{"op": "damage", "amount": 6}, _cs("attack", 1, "this_turn")], "all_enemies")
    check(d == "Deal {Damage} damage to ALL enemies.\nYour Attacks cost 1 less this turn.", f"rides an AoE attack without the suffix: {d!r}")


def _t_emit_and_scoring(v: CardValidator) -> None:
    print("emit carries the named args; census / tokens / detector see the op; pricing is ordered:")
    throttle = _card([_cs("attack", 1, "this_turn"), {"op": "draw", "amount": 1}])
    _, src = cardgen.gen_class(throttle)
    check('new EffectSpec("cost_shift", 1, CardKind: "attack", Scope: "this_turn")' in src, f"emit (flat form): {src[src.find('cost_shift') - 20: src.find('cost_shift') + 80]!r}")
    _, src = cardgen.gen_class(_card([_cs("skill", 2, "this_turn", count=1)]))
    check('new EffectSpec("cost_shift", 2, CardKind: "skill", Scope: "this_turn", Count: 1)' in src, "emit (count form)")
    _, src = cardgen.gen_class(_card([_cs("all", 1, "combat")], rarity="rare", type="power"))
    check('new EffectSpec("cost_shift", 1, CardKind: "all", Scope: "combat")' in src, "emit (combat scope)")
    cc = census.walk_card(throttle)
    check(cc.ops["cost_shift"] == 2 and "cost_shift" in card_tokens(throttle), "census / card_tokens see the op (base + upgrade)")
    ct = next(f for f in featured.FEATURED_MENU if f.id == "cost_trick")
    check(ct.detect(cc) and not ct.detect(census.walk_card(_card([{"op": "block", "amount": 5}]))), "cost_trick detector keys off the op")
    turn = v._score_effect(_cs("attack", 1, "this_turn"))
    turn_all = v._score_effect(_cs("all", 1, "this_turn"))
    nxt = v._score_effect(_cs("attack", 1, "this_turn", count=1))
    combat = v._score_effect(_cs("attack", 1, "combat"))
    energy = v._score_effect({"op": "gain_energy", "amount": 1})
    check(0 < nxt < turn < turn_all <= energy < combat, f"pricing order next({nxt}) < turn({turn}) < all({turn_all}) <= energy({energy}) < combat({combat})")
    from btsgen import validator as _val
    check("cost_shift" in _val._BUILD_AROUND_OPS, "cost_shift is a build-around op (not a blank stat line)")


def _t_relic() -> None:
    print("relic side: a this-turn cost_shift hook validates (schema + class_forge gate); combat scope rejects:")
    rv = RelicValidator()
    relic = {"name": "Apprentice's Patience", "id": "apprentices_patience", "description": "Your first card each turn costs 1 less.",
             "tier": "starter", "icon_emoji": "🏷️",
             "hooks": [{"trigger": "turn_start", "target": "self",
                        "effects": [{"op": "cost_shift", "card_type": "all", "amount": 1, "scope": "this_turn", "count": 1}]}]}
    r = rv.validate(relic)
    check(r.ok, f"the patient-apprentice relic validates: {r.errors}")
    check(class_forge._validate_relic(relic) == [], f"class_forge relic gate accepts it: {class_forge._validate_relic(relic)}")
    bad = json.loads(json.dumps(relic))
    bad["hooks"][0]["effects"][0]["scope"] = "combat"
    check(not rv.validate(bad).ok, "scope:combat on a relic is rejected by the schema (const this_turn)")
    check(any("this_turn" in e for e in class_forge._validate_relic(bad)), "scope:combat on a relic is rejected by the class_forge gate")
    bad2 = json.loads(json.dumps(relic))
    del bad2["hooks"][0]["effects"][0]["card_type"]
    check(not rv.validate(bad2).ok and any("card_type" in e for e in class_forge._validate_relic(bad2)), "a relic cost_shift needs card_type (both gates)")
    check(rv.score_relic(relic) > 0, "the relic scorer prices the hook")


def _t_set_warning() -> None:
    print("set-level: >1 whole-combat cost_shift cards warn; one (or turn-scoped ones) do not:")
    a = _card([_cs("attack", 1, "combat")], id="a", rarity="rare", type="power")
    b = _card([_cs("skill", 1, "combat")], id="b", rarity="rare", type="power")
    c = _card([_cs("skill", 1, "this_turn")], id="c")
    check(cost_shift_warnings([a, c]) == [], "one combat + one turn: no warning")
    w = cost_shift_warnings([a, b, c])
    check(len(w) == 1 and "a, b" in w[0], f"two combat-scoped: one warning naming both: {w}")


def _t_contract() -> None:
    print("schema / vocabulary / relic contract / exemplars / archetypes / featured menu / blueprint prompt carry the token:")
    schema = json.loads(paths.CARD_SCHEMA.read_text(encoding="utf-8"))
    eff = schema["$defs"]["effect"]["properties"]
    trig = schema["$defs"]["triggerEffect"]["properties"]
    check("cost_shift" in eff["op"]["enum"] and "cost_shift" not in trig["op"]["enum"], "schema: cost_shift is a card-level op only")
    check(set(eff["card_type"]["enum"]) == {"attack", "skill", "power", "all"} and set(eff["scope"]["enum"]) == {"this_turn", "combat"}
          and eff["count"]["maximum"] == 3, "schema: card_type / scope / count properties")
    check(all(k not in trig for k in ("card_type", "scope", "count")), "schema: the three fields are not on triggerEffect")
    vocab = paths.VOCABULARY.read_text(encoding="utf-8")
    check("`cost_shift`" in vocab and "Your Attacks cost 1 less this turn." in vocab and "rare-only" in vocab, "VOCABULARY.md names cost_shift with the wording + the rare rule")
    rschema = json.loads(paths.RELIC_SCHEMA.read_text(encoding="utf-8"))
    reff = rschema["$defs"]["effect"]["properties"]
    check("cost_shift" in reff["op"]["enum"] and reff["scope"]["const"] == "this_turn", "relic schema: cost_shift op + scope const this_turn")
    check("`cost_shift`" in paths.RELIC_VOCABULARY.read_text(encoding="utf-8"), "RELIC_VOCABULARY.md lists cost_shift")
    check("cost_shift" in (paths.VOCABULARY.parent / "DESIGN_HEURISTICS.md").read_text(encoding="utf-8"), "DESIGN_HEURISTICS.md prices it")
    data = pathlib.Path(paths.__file__).parent / "data"
    pool = json.loads((data / "exemplar_pool.json").read_text(encoding="utf-8"))
    by_id = {e["card"]["id"]: e for e in pool["exemplars"]}
    v = CardValidator()
    for cid in ("ex_open_throttle", "ex_quiet_step", "ex_war_economy"):
        check(cid in by_id and by_id[cid]["needs"] == "", f"exemplar {cid} present (needs '')")
        if cid in by_id:
            r = v.validate(dict(by_id[cid]["card"]))
            check(r.ok, f"exemplar {cid} validates: {r.errors}")
    arch = json.loads((data / "archetypes.json").read_text(encoding="utf-8"))
    ops = {a["id"]: a["vocabulary"]["ops"] for a in arch["archetypes"]}
    check("cost_shift" in ops["tempo_draw"] and "cost_shift" in ops["big_energy"], "archetypes list the token")
    check("cost_trick" in {f.id for f in featured.FEATURED_MENU}, "featured menu carries cost_trick")
    from btsgen.class_forge import _BlueprintContract
    prompt = _BlueprintContract(mode="dossier", triad=True, seed=1).system_prompt()
    check("cost_shift" in prompt, "the blueprint prompt points at cost_shift")


def main() -> int:
    v = CardValidator()
    test_version()
    _t_shape(v)
    _t_describe()
    _t_emit_and_scoring(v)
    _t_relic()
    _t_set_warning()
    _t_contract()
    print(f"\n{_PASS} passed, {_FAIL} failed")
    return 1 if _FAIL else 0


# pytest entry point (re-runs main's checks in isolation for a clear failure name)
def test_phase_ao_all() -> None:
    assert main() == 0


if __name__ == "__main__":
    sys.exit(main())
