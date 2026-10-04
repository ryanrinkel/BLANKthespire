"""Phase BJ — COMBAT-HISTORY SCALES + CONDITIONS: twelve scale forms read off the combat History / piles (verbatim base-
game recipes, replace-semantics) and three `when` kinds (VOCAB_EXPANSION_6_PLAN, gaps #63/#64, vocab v62) — offline.
Run:  uv run python -m tests.test_phase_bj  (from generation/)

Pins: the stamp; the engine wiring (one EffectRunner.ScaleValue case + helper per scale, each carrying its base recipe
line; the per-target target_status_stacks calc-var; Expertise / Double Energy executors; the three Conditions cases);
the validator rules on both sides; the describe byte-match (Python literals asserted, the C# fragments grepped); the
contract surfaces (schema, VOCABULARY, coverage menus, archetypes, exemplars, heuristics, gap log, render.js, the
pitch sentences, the orb-condition lockstep); the saved AutoSlay tag greps under tests/gaptest-bj/; and prints the
rule-0.9 readings (informational).
"""
from __future__ import annotations

import contextlib
import json
import os
import pathlib
import re
import sys

from btsgen.class_forge import point_btsgen_at_mod_contract

point_btsgen_at_mod_contract()

from btsgen import bts1, cardgen, census, coverage, gate, harness_v2, paths  # noqa: E402
from btsgen import class_forge as cf  # noqa: E402
from btsgen.validator import CardValidator  # noqa: E402

_PASS = 0
_FAIL = 0
MOD_CODE = paths.VOCABULARY.parents[1] / "BlankTheSpireCode"
CARD_SCHEMA = paths.VOCABULARY.parent / "card.schema.json"
REPO = paths.VOCABULARY.parents[2]
DATA = pathlib.Path(cf.__file__).parent / "data"
TESTER_DIR = pathlib.Path(__file__).parent / "gaptest-bj"
SMOKE_SEEDS = ("GAPTESTBJ1", "GAPTESTBJ2")

# The eleven new scale tokens (the twelfth form is `energy` on gain_energy — an existing token on a new op).
HISTORY_SCALES = ("exhaust_pile_size", "discard_pile_size", "discards_this_turn", "cards_drawn_this_turn",
                  "cards_drawn_this_combat", "energy_spent_this_turn", "hp_loss_events_this_combat",
                  "cards_generated_this_combat", "total_enemy_poison", "target_status_stacks")
NEW_SCALES = HISTORY_SCALES + ("to_hand_size",)
NEW_CONDS = ("exhausted_this_turn", "played_cards_last_turn_ge", "target_intends_attack")


def check(cond: bool, msg: str) -> None:
    global _PASS, _FAIL
    if cond:
        _PASS += 1
    else:
        _FAIL += 1
        print(f"  FAIL: {msg}")


def _cs(*parts: str) -> str:
    return (MOD_CODE.joinpath(*parts)).read_text(encoding="utf-8")


def _card(effects, rarity="uncommon", cost=1, ctype="attack", target="enemy"):
    return {"id": "bj_t", "name": "BJ", "type": ctype, "rarity": rarity, "cost": cost, "target": target, "effects": effects}


def _sc(op, scale, amount=1, **kw):
    e = {"op": op, "amount": amount, "scale": scale}
    e.update(kw)
    return e


_V = None


def _errs(card) -> list[str]:
    global _V
    if _V is None:
        _V = CardValidator()
    return _V.validate(card).errors


@contextlib.contextmanager
def _env(**kv):
    old = {k: os.environ.get(k) for k in kv}
    os.environ.update(kv)
    try:
        yield
    finally:
        for k, v in old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def test_version() -> None:
    print("Phase BJ vocab stamp is at least 62 (Python + C#):")
    check(bts1.VOCAB_VERSION >= 62, f"bts1.VOCAB_VERSION >= 62, got {bts1.VOCAB_VERSION}")
    fc = _cs("Engine", "ForgedCards.cs")
    m = re.search(r"public const int VocabVersion = (\d+);", fc)
    check(m is not None and int(m.group(1)) >= 62, f"ForgedCards.VocabVersion >= 62, got {m and m.group(1)}")
    check(m is not None and bts1.VOCAB_VERSION <= int(m.group(1)), "bts1.VOCAB_VERSION <= ForgedCards.VocabVersion")
    check("Phase BJ" in fc and "`exhaust_pile_size`" in fc and "`target_intends_attack`" in fc,
          "ForgedCards.cs comment names Phase BJ + the tokens")
    check("62: Phase BJ" in pathlib.Path(bts1.__file__).read_text(encoding="utf-8"), "bts1.py records the v62 entry")


def _t_engine() -> None:
    print("the engine: one ScaleValue case + base recipe per scale, the per-target read, Expertise / Double Energy, conditions:")
    er = _cs("Engine", "EffectRunner.cs")
    # one ScaleValue branch per player-level scale, each pointing at its helper
    for frag in ('"exhaust_pile_size"          => ExhaustPileSize(card.Owner),',
                 '"discard_pile_size"          => card.Owner?.PlayerCombatState?.DiscardPile?.Cards?.Count ?? 0,',
                 '"discards_this_turn"         => DiscardsThisTurn(card.Owner),',
                 '"cards_drawn_this_turn"      => CardsDrawnThisTurn(card.Owner),',
                 '"cards_drawn_this_combat"    => CardsDrawnThisCombat(card.Owner),',
                 '"energy_spent_this_turn"     => EnergySpentThisTurn(card),',
                 '"hp_loss_events_this_combat" => HpLossEventsThisCombat(card.Owner),',
                 '"cards_generated_this_combat" => CardsGeneratedThisCombat(card.Owner),',
                 '"total_enemy_poison"         => TotalEnemyPoison(card.Owner),'):
        check(frag in er, f"ScaleValue branch: {frag}")
    # the verbatim base recipes (AshenStrike / MementoMori / DeathMarch / Murder / HelixDrill / TearAsunder /
    # Supermassive / Mirage / Bully)
    for frag, base in (("player?.PlayerCombatState?.ExhaustPile?.Cards?.Count ?? 0", "AshenStrike"),
                       ("CardDiscardedEntry>()\n            .Count(e => e.HappenedThisTurn(cs) && e.Card.Owner == player)", "MementoMori"),
                       ("e.HappenedThisTurn(cs) && e.Actor == player.Creature && !e.FromHandDraw", "DeathMarch"),
                       ("CardDrawnEntry>().Count(e => e.Actor == player.Creature)", "Murder"),
                       ("EnergySpentEntry>()\n            .Where(e => e.HappenedThisTurn(cs) && e.Actor.Player == owner).Sum(e => e.Amount)", "HelixDrill"),
                       ("if (card.Pile.Type == PileType.Play)\n            n -= card.EnergyCost.GetWithModifiers(CostModifiers.All);", "HelixDrill own cost"),
                       ("e.Receiver == player.Creature && e.Result.UnblockedDamage > 0", "TearAsunder"),
                       ("CardGeneratedEntry>().Count(e => e.Creator == player)", "Supermassive"),
                       ("cs.Enemies.Where(c => c.IsAlive).Sum(c => c.GetPowerAmount<PoisonPower>())", "Mirage"),
                       ('"vulnerable" => target.GetPowerAmount<VulnerablePower>(),', "Bully"),
                       ("CardExhaustedEntry>()\n            .Any(e => e.HappenedThisTurn(cs) && e.Card.Owner == player)", "EvilEye"),
                       ("c.HappenedLastPlayerTurn(player) && c.CardPlay.Card.Owner == player", "PaleBlueDotPower")):
        check(frag.replace("\n", "\r\n") in er or frag in er, f"{base} recipe: {frag!r}")
    check("return Math.Max(0, n);" in er, "energy_spent_this_turn clamps at 0 (an auto-played card spent nothing)")
    dc = _cs("Engine", "DataCard.cs")
    check(': e.Scale == "target_status_stacks"\n                    ? (_, tgt) => EffectRunner.StatusStacks(tgt, e.Status)'
          .replace("\n", "\r\n") in dc or ': e.Scale == "target_status_stacks"\n                    ? (_, tgt) => '
          'EffectRunner.StatusStacks(tgt, e.Status)' in dc, "BonusFor: target_status_stacks reads the calc-var target")
    check('if (!e.IsScaled || e.Scale == "to_hand_size") WithCards(e.Amount, up);' in dc, "to_hand_size keeps the Cards var")
    check("if (!e.IsScaled) WithEnergy(e.Amount, up);" in dc, "Double Energy declares no Energy var")
    check("int n = Math.Max(0, amt - h);" in er, "Expertise: draw max(0, N - hand)")
    check("await PlayerCmd.GainEnergy(cur, card.Owner);" in er, "Double Energy: gain your current energy")
    # tags
    for tag in ('[BJ] scale {e.Scale} -> {BjScaleRead(e, card, play)} (damage)', '[BJ] scale {e.Scale} -> {BjScaleRead(e, card, play)} (block)',
                '[BJ] draw to_hand_size: hand {h} -> draw {n}', '[BJ] gain_energy x energy: {cur} -> {cur * 2}',
                '[BJ] cond {e.When.Kind} -> {(gateOpen ? "true" : "false")}'):
        check(tag in er, f"tag: {tag}")
    m = re.search(r"PhaseBjScales =\s*\[(.*?)\];", er, re.S)
    check(m is not None and set(re.findall(r'"(\w+)"', m.group(1))) == set(HISTORY_SCALES), "PhaseBjScales == the ten history scales")
    tr = _cs("Engine", "TriggerRunner.cs")
    check('case "exhaust_pile_size":' in tr and 'case "total_enemy_poison":' in tr and "EffectRunner.TotalEnemyPoison(player)" in tr,
          "TriggerRunner.ResolveAmount resolves the two payload-legal reads")
    cond = _cs("Engine", "Conditions.cs")
    check("return EffectRunner.ExhaustedThisTurn(player);" in cond, "Eval: exhausted_this_turn")
    check("return EffectRunner.CardsPlayedLastTurn(player) >= c.Value;" in cond, "Eval: played_cards_last_turn_ge")
    check("return target?.Monster?.IntendsToAttack ?? false;" in cond, "Eval: target_intends_attack (GoForTheEyes)")
    tk = re.search(r"TargetKinds =\s*\[(.*?)\];", cond, re.S)
    check(tk is not None and '"target_intends_attack"' in tk.group(1), "target_intends_attack is a TargetKinds read")
    check('c.Kind == "played_cards_last_turn_ge" && c.Value > CardsPlayedGeMax' in cond, "played_cards_last_turn_ge capped at 10")
    fc = _cs("Engine", "ForgedCards.cs")
    m = re.search(r"TriggerScales =\s*\[(.*?)\];", fc, re.S)
    check(m is not None and {"exhaust_pile_size", "total_enemy_poison"} <= set(re.findall(r'"(\w+)"', m.group(1))),
          "TriggerScales += exhaust_pile_size / total_enemy_poison")
    check('DamageOnlyScales =\n        ["cards_drawn_this_combat", "hp_loss_events_this_combat", "total_enemy_poison"];'.replace("\n", "\r\n") in fc
          or 'DamageOnlyScales =\n        ["cards_drawn_this_combat", "hp_loss_events_this_combat", "total_enemy_poison"];' in fc,
          "DamageOnlyScales")
    check('e.Scale == "energy" && e.Op is "damage" or "block" or "draw"' in fc, "the cost-0 energy rule is narrowed to damage/block/draw")
    check('"draw"         => e.IsScaled && e.Scale != "to_hand_size" ? null : "Cards"' in fc and
          '"gain_energy"  => e.IsScaled ? null : "Energy"' in fc, "VarKey: to_hand_size -> Cards, scaled gain_energy -> none")


CASES = [
    ([_sc("damage", "exhaust_pile_size")], "enemy", "Deal damage equal to the cards in your exhaust pile."),
    ([_sc("block", "discard_pile_size")], "self", "Gain Block equal to the cards in your discard pile."),
    ([_sc("damage", "discards_this_turn")], "enemy", "Deal damage equal to the cards you have discarded this turn."),
    ([_sc("damage", "cards_drawn_this_turn")], "enemy", "Deal damage equal to the cards you have drawn this turn."),
    ([_sc("damage", "cards_drawn_this_combat")], "enemy", "Deal damage equal to the cards you have drawn this combat."),
    ([_sc("block", "energy_spent_this_turn")], "self", "Gain Block equal to the energy you have spent this turn."),
    ([_sc("damage", "hp_loss_events_this_combat")], "enemy", "Deal damage equal to the times you have lost HP this combat."),
    ([_sc("damage", "cards_generated_this_combat")], "enemy", "Deal damage equal to the cards you have created this combat."),
    ([_sc("damage", "total_enemy_poison")], "all_enemies", "Deal damage equal to the total Poison on ALL enemies to ALL enemies."),
    ([_sc("damage", "target_status_stacks", status="vulnerable")], "enemy", "Deal damage equal to the enemy's Vulnerable."),
    ([_sc("block", "target_status_stacks", status="weak")], "enemy", "Gain Block equal to the enemy's Weak."),
    ([_sc("damage", "target_status_stacks", status="poison")], "enemy", "Deal damage equal to the enemy's Poison."),
    ([_sc("gain_energy", "energy"), {"op": "exhaust"}], "self", "Double your energy.\nExhaust."),
    ([_sc("draw", "to_hand_size", amount=6)], "self", "Draw cards until you have {Cards} in hand."),
    ([{"op": "block", "amount": 6}, {"op": "draw", "amount": 1, "when": {"kind": "exhausted_this_turn"}}], "self",
     "Gain {Block} Block.\nDraw {Cards} card(s) if you have Exhausted a card this turn."),
    ([{"op": "block", "amount": 6}, {"op": "draw", "amount": 2, "when": {"kind": "played_cards_last_turn_ge", "value": 4}}], "self",
     "Gain {Block} Block.\nDraw {Cards} card(s) if you played 4+ cards last turn."),
    ([{"op": "damage", "amount": 3}, {"op": "apply_status", "status": "weak", "amount": 1, "when": {"kind": "target_intends_attack"}}],
     "enemy", "Deal {Damage} damage.\nApply Weak if the enemy intends to attack."),
    ([{"op": "add_trigger", "trigger": "turn_start", "effects": [_sc("damage", "total_enemy_poison", target="all_enemies")]}], "self",
     "At the start of your turn, deal damage equal to the total Poison on ALL enemies to ALL enemies."),
    ([{"op": "add_trigger", "trigger": "turn_end", "effects": [_sc("block", "exhaust_pile_size")]}], "self",
     "At the end of your turn, gain Block equal to the cards in your exhaust pile."),
]


def _t_rules_and_describe() -> None:
    print("validator + describe (Python literal == the C# fragment written by hand):")
    ok = [
        _card([_sc("damage", "exhaust_pile_size")]), _card([_sc("block", "exhaust_pile_size")], ctype="skill", target="self"),
        _card([_sc("draw", "exhaust_pile_size")], ctype="skill", target="self"),
        _card([_sc("block", "discard_pile_size")], ctype="skill", target="self"),
        _card([{"op": "discard", "amount": 2}, _sc("damage", "discards_this_turn")], cost=0),
        _card([{"op": "draw", "amount": 2}, _sc("damage", "cards_drawn_this_turn")]),
        _card([_sc("damage", "cards_drawn_this_combat")], rarity="rare", cost=2),
        _card([_sc("damage", "energy_spent_this_turn")], cost=0), _card([_sc("block", "energy_spent_this_turn")], ctype="skill", target="self"),
        _card([_sc("damage", "hp_loss_events_this_combat")], rarity="rare", cost=2),
        _card([_sc("damage", "cards_generated_this_combat")]),
        _card([_sc("damage", "total_enemy_poison")]), _card([_sc("damage", "total_enemy_poison")], target="all_enemies"),
        _card([_sc("damage", "target_status_stacks", status="vulnerable")]),
        _card([_sc("block", "target_status_stacks", status="weak")], ctype="skill"),
        _card([_sc("gain_energy", "energy"), {"op": "exhaust"}], cost=1, ctype="skill", target="self"),
        _card([_sc("draw", "to_hand_size", amount=6)], ctype="skill", target="self"),
        _card([{"op": "damage", "amount": 9, "when": {"kind": "target_intends_attack"}}]),
        _card([{"op": "damage", "amount": 9, "when": {"kind": "exhausted_this_turn"}}], target="all_enemies"),
        _card([{"op": "damage", "amount": 9, "when": {"kind": "played_cards_last_turn_ge", "value": 3}}]),
        _card([{"op": "add_trigger", "trigger": "turn_start", "when": {"kind": "exhausted_this_turn"},
                "effects": [{"op": "block", "amount": 3}]}], ctype="power", target="self"),
        _card([{"op": "add_trigger", "trigger": "turn_start", "effects": [_sc("damage", "total_enemy_poison", target="all_enemies")]}],
              ctype="power", target="self", rarity="rare"),
    ]
    for c in ok:
        check(not _errs(c), f"validates: {json.dumps(c['effects'])} -> {_errs(c)}")
    bad = [
        (_card([_sc("block", "cards_drawn_this_combat")], ctype="skill", target="self"), "only applies to damage"),
        (_card([_sc("block", "total_enemy_poison")], ctype="skill", target="self"), "only applies to damage"),
        (_card([_sc("draw", "discards_this_turn")], ctype="skill", target="self"), "only applies to damage/block"),
        (_card([_sc("damage", "target_status_stacks")]), "needs a 'status'"),
        (_card([_sc("damage", "target_status_stacks", status="frail")]), "needs a 'status'"),
        (_card([_sc("damage", "target_status_stacks", status="weak")], target="all_enemies"), "single-enemy"),
        (_card([_sc("damage", "target_status_stacks", status="weak")], target="random_enemy"), "single-enemy"),
        (_card([_sc("draw", "to_hand_size", amount=1)], ctype="skill", target="self"), "target hand size"),
        (_card([_sc("draw", "to_hand_size", amount=11)], ctype="skill", target="self"), "target hand size"),
        (_card([_sc("damage", "to_hand_size")]), "only applies to draw"),
        (_card([_sc("heal", "energy")], ctype="skill", target="self"), "damage/block/draw/gain_energy"),
        (_card([_sc("damage", "energy")], cost=1), "cost-0"),
        (_card([{"op": "damage", "amount": 6, "status": "weak"}]), "only applies with 'scale:target_status_stacks'"),
        (_card([{"op": "damage", "amount": 9, "when": {"kind": "target_intends_attack"}}], target="all_enemies"), "single-enemy"),
        (_card([{"op": "add_trigger", "trigger": "turn_start", "when": {"kind": "target_intends_attack"},
                 "effects": [{"op": "block", "amount": 3}]}], ctype="power", target="self"), "trigger's 'when'"),
        (_card([{"op": "add_trigger", "trigger": "turn_start", "effects": [_sc("block", "total_enemy_poison")]}],
               ctype="power", target="self"), "inside a trigger only applies to damage"),
        (_card([{"op": "add_trigger", "trigger": "turn_start", "effects": [_sc("block", "discard_pile_size")]}],
               ctype="power", target="self"), "inside a trigger 'scale' must be one of"),
    ]
    for c, frag in bad:
        e = _errs(c)
        check(any(frag in x for x in e), f"rejected ({frag}): {json.dumps(c['effects'])} -> {e}")
    e = _errs(_card([{"op": "damage", "amount": 9, "when": {"kind": "played_cards_last_turn_ge", "value": 11}}]))
    check(any("maximum of 10" in x for x in e), f"played_cards_last_turn_ge capped at 10: {e}")
    # pricing: the two unbounded counts are late-game payoffs
    v = _V
    check(v._score_effect(_sc("damage", "cards_drawn_this_combat")) >= 18 and v._score_effect(_sc("damage", "hp_loss_events_this_combat")) >= 8,
          "the unbounded combat counts are priced at their late-game expected value")
    check(cf._cond_uptime({"kind": "exhausted_this_turn"}, {"share": 0}) == 0.4
          and cf._cond_uptime({"kind": "played_cards_last_turn_ge", "value": 4}, {"share": 0}) == 0.3, "_cond_uptime knows the new kinds")
    # describe — the literals (byte-match with ForgedCards.Describe / ScalePhrase / Conditions.Phrase)
    for effects, target, want in CASES:
        got = cardgen.describe(effects, target)
        check(got == want, f"describe {got!r} == {want!r}")
    fc = _cs("Engine", "ForgedCards.cs")
    for scale in NEW_SCALES:
        if scale in ("target_status_stacks", "to_hand_size"):
            continue
        noun = cardgen._scale_phrase(scale)
        check(re.search(r'"' + scale + r'"\s+=> "' + re.escape(noun) + '",', fc) is not None, f"C# ScalePhrase: {scale} => {noun!r}")
    for frag in ('e.Scale == "target_status_stacks" ? $"the enemy\'s {StatusDisplay(e.Status)}" : ScalePhrase(e.Scale);',
                 ': e.Scale == "to_hand_size" ? "Draw cards until you have {Cards} in hand."',
                 'parts.Add(e.Scale == "energy" ? "Double your energy." : "Gain {Energy} energy.");',
                 '"exhaust_pile_size"        => "the cards in your exhaust pile",   // Phase BJ (v62)',
                 '"total_enemy_poison"       => "the total Poison on ALL enemies",  // Phase BJ (v62)'):
        check(frag in fc, f"C# fragment present: {frag}")
    cond = _cs("Engine", "Conditions.cs")
    for frag in ('"exhausted_this_turn"       => "you have Exhausted a card this turn",',
                 '"played_cards_last_turn_ge" => $"you played {c.Value}+ cards last turn",',
                 '"target_intends_attack"     => "the enemy intends to attack",'):
        check(frag in cond, f"C# Phrase present: {frag}")
    lit = cardgen.effect_literal(_sc("damage", "target_status_stacks", status="vulnerable"))
    check(lit == 'new EffectSpec("damage", 1, "vulnerable", 1, "target_status_stacks")', f"effect_literal carries the status: {lit}")
    check(cardgen.effect_literal(_sc("draw", "to_hand_size", amount=6)) == 'new EffectSpec("draw", 6, null, 1, "to_hand_size")',
          "effect_literal: to_hand_size")


def _t_contract() -> None:
    print("contract surfaces:")
    schema = json.loads(CARD_SCHEMA.read_text(encoding="utf-8"))
    eff = schema["$defs"]["effect"]
    check(set(NEW_SCALES) <= set(eff["properties"]["scale"]["enum"]), "schema: effect scale enum carries the new sources")
    check({"exhaust_pile_size", "total_enemy_poison"} <= set(schema["$defs"]["triggerEffect"]["properties"]["scale"]["enum"]),
          "schema: payload scale enum += exhaust_pile_size / total_enemy_poison")
    check(set(NEW_CONDS) <= set(schema["$defs"]["condition"]["properties"]["kind"]["enum"]), "schema: condition kinds")
    rules = json.dumps(eff.get("allOf", []))
    check('"scale": {"const": "target_status_stacks"}' in rules and '"status": {"enum": ["vulnerable", "weak", "poison"]}' in rules,
          "schema: target_status_stacks requires its status")
    crules = json.dumps(schema["$defs"]["condition"].get("allOf", []))
    check('"kind": {"const": "played_cards_last_turn_ge"}' in crules, "schema: played_cards_last_turn_ge requires value 1..10")
    vocab = paths.VOCABULARY.read_text(encoding="utf-8")
    check("**Combat-history reads (v62, replace-semantics):**" in vocab, "VOCABULARY: the one history-reads row group")
    live = set(re.findall(r"`([a-z][a-z0-9_]*)`", vocab))
    check(set(NEW_SCALES) <= live and set(NEW_CONDS) <= live, f"VOCABULARY backticks every token (missing {set(NEW_SCALES + NEW_CONDS) - live})")
    for k in NEW_CONDS:
        check(f"| `{k}` |" in vocab, f"VOCABULARY Conditions row: {k}")
    check(set(harness_v2.vocabulary_conditions(vocab)) >= set(NEW_CONDS), "the Conditions table parser sees the rows")
    check(set(gate.vocab_tokens(vocab)) >= set(NEW_SCALES + NEW_CONDS), "the vocabulary tree knows the tokens")
    idx = gate.vocab_index(vocab)
    check(all(f"`{t}`" in idx for t in NEW_SCALES + NEW_CONDS), "the index lists every new token")
    # coverage menus + census detectors
    scale_keys = {k for k, _ in coverage.SCALE_MENU}
    check(set(NEW_SCALES) <= scale_keys, "coverage.SCALE_MENU carries the new scales")
    check(set(NEW_CONDS) <= {k for k, _ in coverage.WHEN_MENU_V2}, "coverage.WHEN_MENU_V2 carries the new kinds")
    cc = census.walk_card(_card([_sc("damage", "target_status_stacks", status="weak"),
                                 {"op": "draw", "amount": 1, "when": {"kind": "target_intends_attack"}}]))
    check(cc.scales.get("target_status_stacks") == 1 and cc.whens.get("target_intends_attack") == 1, "census counts the scale + kind")
    # orb-condition lockstep (test_phase_ar asserts the set equality; spot-check here)
    check({"exhausted_this_turn", "played_cards_last_turn_ge"} <= cf._ORB_CONDITION_KINDS
          and "target_intends_attack" in cf._ORB_FORBIDDEN_CONDITION_KINDS, "class_forge orb-condition sets")
    # archetypes
    arch = {a["id"]: a for a in json.loads((DATA / "archetypes.json").read_text(encoding="utf-8"))["archetypes"]}
    for aid, toks, gap in (("exhaust_pyre", {"exhaust_pile_size", "exhausted_this_turn"}, "#63"),
                           ("madness_discard", {"discards_this_turn", "discard_pile_size"}, "#63"),
                           ("tempo_draw", {"cards_drawn_this_turn", "cards_drawn_this_combat", "to_hand_size"}, "#63"),
                           ("big_energy", {"energy_spent_this_turn", "energy"}, "#63"),
                           ("poison_attrition", {"total_enemy_poison"}, "#63"),
                           ("debuff_expose", {"target_status_stacks"}, "#63"),
                           ("countdown_ripen", {"target_intends_attack"}, "#64"),
                           ("ambush_alpha", {"target_intends_attack"}, "#64")):
        a = arch[aid]
        check(toks <= set(a["vocabulary"]["ops"]), f"{aid} claims {sorted(toks)}")
        check(f"VOCABULARY_GAPS{gap}" in a["gap_refs"] and a["buildable"] is True, f"{aid} refs gap {gap} and stays buildable")
    # exemplars: every new scale / kind is used by an exemplar that validates
    pool = json.loads((DATA / "exemplar_pool.json").read_text(encoding="utf-8"))["exemplars"]
    v = harness_v2.exemplar_validator()
    for tok in NEW_SCALES + NEW_CONDS:
        hits = [e for e in pool if f'"{tok}"' in json.dumps(e["card"])]
        check(bool(hits), f"an exemplar uses {tok}")
        for e in hits:
            r = v.validate(dict(e["card"]))
            check(r.ok, f"exemplar {e['card']['id']} validates: {r.errors}")
    check(any('"scale": "energy"' in json.dumps(e["card"]) and '"gain_energy"' in json.dumps(e["card"]) for e in pool),
          "a Double Energy exemplar")
    heur = (paths.VOCABULARY.parent / "DESIGN_HEURISTICS.md").read_text(encoding="utf-8")
    check("History scales (v62)" in heur and "`target_status_stacks` (v62)" in heur and "`target_intends_attack` (v62)" in heur,
          "DESIGN_HEURISTICS prices the history scales / the intent gate")
    gaps = (REPO / "VOCABULARY_GAPS.md").read_text(encoding="utf-8")
    for n, nxt in ((63, 64), (64, 65)):
        entry = gaps.split(f"### {n}.", 1)[1].split(f"### {nxt}.", 1)[0]
        check("**Status:** **done (2026-10-04, vocab v62, Phase BJ)**" in entry, f"gap #{n} is done")
    js = (REPO / "web" / "static" / "render.js").read_text(encoding="utf-8")
    for scale in HISTORY_SCALES[:-1]:
        check(f'{scale}: "{cardgen._scale_phrase(scale)}"' in js, f"render.js SCALE_NOUN: {scale}")
    check("`the enemy's ${statusName(e.status)}`" in js, "render.js: the enemy's <Status>")
    check('"Double your energy"' in js and "`Draw cards until you have ${a ?? \"?\"} in hand`" in js, "render.js: Double Energy / Expertise")
    for k in NEW_CONDS:
        check(f'case "{k}": return' in js, f"render.js condCore: {k}")
    check('return `you played ${v ?? "enough"}+ cards last turn`' in js and '"the enemy intends to attack"' in js
          and '"you have Exhausted a card this turn"' in js, "render.js condCore phrases match cond_phrase")
    src = pathlib.Path(cf.__file__).read_text(encoding="utf-8")
    check('History reads (v62): "exhaust_pile_size", "discards_this_turn"' in src, "the SCALED AMOUNTS pitch names the history reads")
    check("`exhausted_this_turn`, \"\n    \"`target_intends_attack`" in src.replace("\r\n", "\n"), "the conditions pitch names the new kinds")
    check("intends? to attack" in gate.FAMILY_KW["conditions"] and "double your energy" in gate.FAMILY_KW["scaling"],
          "the card gate's keyword rules route the new wording to their families")


def _t_smoke_record() -> None:
    print("the saved AutoSlay tag greps (TEST_AUDIT_2026-10 §7):")
    seen = ""
    for seed in SMOKE_SEEDS:
        p = TESTER_DIR / f"godot_BJ_tags_{seed}.txt"
        assert p.exists(), f"missing smoke record {p}"
        txt = p.read_text(encoding="utf-8")
        check("[BJ]" in txt, f"{p.name} holds [BJ] tags")
        check("mod exceptions: 0" in txt and "Localization formatting errors: 0" in txt, f"{p.name} records a clean run")
        seen += txt
    for scale in HISTORY_SCALES:
        check(f"[BJ] scale {scale} -> " in seen, f"the smoke fired '[BJ] scale {scale}'")
    for tag in ("[BJ] draw to_hand_size: hand", "[BJ] gain_energy x energy:"):
        check(tag in seen, f"the smoke fired '{tag}'")
    for k in NEW_CONDS:
        check(f"[BJ] cond {k} -> true" in seen, f"the smoke opened the '{k}' gate")
    check((TESTER_DIR / "build_tester.py").exists(), "the tester is committed next to the phase test")


def _t_budget() -> None:
    print("rule 0.9 (informational) — readings on the real path:")
    from tests.test_harness_v2 import rule_0_9_readings
    with _env(BTS_HARNESS_V2="1", BTS_BLUEPRINT_VOCAB="tree"):
        r = rule_0_9_readings()
    print(f"  (reading) index                  {r['index']:>8,}  (clause cap {r['index_clause_cap']})")
    print(f"  (reading) per-archetype max      {r['archetype_max']:>8,}  ({r['archetype_max_id']})")
    print(f"  (reading) per-archetype scaffold {r['archetype_scaffold_max']:>8,}  ({r['archetype_scaffold_max_id']})")
    print(f"  (reading) triads                 {', '.join(f'{k} {v:,}' for k, v in r['triads'].items())}")
    print(f"  (reading) all-ops path           {r['all_ops']:>8,}")
    print(f"  (reading) scaffold (all-ops)     {r['scaffold']:>8,}")
    print(f"  (reading) full path (untrimmed)  {r['untrimmed']:>8,}  (scaffold {r['untrimmed_scaffold']:,})")


def main() -> int:
    test_version()
    _t_engine()
    _t_rules_and_describe()
    _t_contract()
    _t_smoke_record()
    _t_budget()
    print(f"\n{_PASS} passed, {_FAIL} failed")
    return 1 if _FAIL else 0


def test_phase_bj_all() -> None:
    global _PASS, _FAIL
    _PASS = _FAIL = 0
    assert main() == 0, f"{_FAIL} Phase BJ check(s) failed - see the FAIL lines above"


if __name__ == "__main__":
    sys.exit(main())
