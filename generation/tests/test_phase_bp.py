"""Phase BP — `cost_delta` + the small reactive triggers on_card_generated / on_debuff_applied (+ payload target
`that_enemy`) / on_evoke (VOCAB_EXPANSION_6_PLAN, gaps #76 / #77, vocab v67) — offline. Run:
uv run python -m tests.test_phase_bp  (from generation/)

Pins: the stamp; verify-first against the game sources (CardEnergyCost's Add/Set calls + GetWithModifiers, the energy-cost
hook passes, the base Stomp / Momentum Strike / Kingly Kick / Modded recipes, Arsenal / Sleight of Flesh / Vicious, the
AfterCardGeneratedForCombat / AfterPowerAmountChanged / AfterOrbEvoked signatures, CardPlayFinished recorded before
AfterCardPlayed, BaseLib's temporary shell is an ITemporaryPower); the engine wiring (the DataCard cost hooks + tags, the
three ForgedTriggerPower overrides + the re-entry tag, TriggerRunner's that_enemy); the validator rules on both sides;
the describe byte-match (Python literals asserted, the C# fragments grepped); the contract surfaces (schema, VOCABULARY
rows, gate order + field units, coverage + the orb gate, featured, harness_v2, bridges, archetypes, exemplars,
heuristics, gap log, render.js, the pitch sentences); the tester's validate-only path; the saved AutoSlay tag greps
under tests/gaptest-bp/ (smokes GAPTESTBP1/BP2, 2026-10-04); and prints the rule-0.9 readings.
"""
from __future__ import annotations

import contextlib
import importlib.util
import json
import os
import pathlib
import re
import sys

from btsgen.class_forge import point_btsgen_at_mod_contract

point_btsgen_at_mod_contract()

from btsgen import bridges, bts1, cardgen, census, coverage, featured, gate, harness_v2, paths  # noqa: E402
from btsgen import class_forge as cf  # noqa: E402
from btsgen.validator import CardValidator  # noqa: E402

_PASS = 0
_FAIL = 0
MOD_CODE = paths.VOCABULARY.parents[1] / "BlankTheSpireCode"
CARD_SCHEMA = paths.VOCABULARY.parent / "card.schema.json"
REPO = paths.VOCABULARY.parents[2]
DATA = pathlib.Path(cf.__file__).parent / "data"
TESTER_DIR = pathlib.Path(__file__).parent / "gaptest-bp"
SMOKE_SEEDS = ("GAPTESTBP1", "GAPTESTBP2")
MODREF = pathlib.Path(r"C:/Users/ryanr/Desktop/NOVOGODOT/BLANKthespire/_modref")

NEW_TRIGGERS = ("on_card_generated", "on_debuff_applied", "on_evoke")
NEW_TOKENS = ("cost_delta",) + NEW_TRIGGERS
TAGS = ("[BP] cost_delta 'Stomp' on attack_played: ", "[BP] cost_delta 'Quick Study' on skill_played: ",
        "[BP] cost_delta 'Crescendo' on card_played: ", "[BP] cost_delta 'Momentum Strike' on played: 1 -> 0 (combat, set_zero)",
        "[BP] cost_delta 'Modded' on played: 0 -> 1 (combat, +1)", "[BP] cost_delta 'Up My Sleeve' on played: 2 -> 1 (combat, -1)",
        "[BP] cost_delta 'Kingly Kick' on drawn: 4 -> 3 (combat, -1)", "[BP] cost_delta 'Ash Hunger' on card_exhausted: ",
        "[BP] on_card_generated fired", "[BP] on_debuff_applied fired", "filter vulnerable", "[BP] that_enemy -> '",
        "[BP] re-entry blocked (on_debuff_applied)")


def check(cond: bool, msg: str) -> None:
    global _PASS, _FAIL
    if cond:
        _PASS += 1
    else:
        _FAIL += 1
        print(f"  FAIL: {msg}")


def _cs(*parts: str) -> str:
    return (MOD_CODE.joinpath(*parts)).read_text(encoding="utf-8").replace("\r\n", "\n")


def _card(effects, rarity="uncommon", cost=2, ctype="skill", target="self", upgrade=None, up_cost=None):
    c = {"id": "bp_t", "name": "BP", "type": ctype, "rarity": rarity, "cost": cost, "target": target, "effects": effects}
    if upgrade is not None or up_cost is not None:
        c["upgrade"] = {"effects": upgrade if upgrade is not None else effects}
        if up_cost is not None:
            c["upgrade"]["cost"] = up_cost
    return c


def _atk(effects, **kw):
    kw.setdefault("ctype", "attack")
    kw.setdefault("target", "enemy")
    return _card(effects, **kw)


def _cd(on, scope, amount=None, set_zero=False, **extra):
    e = {"op": "cost_delta", "on": on, "scope": scope}
    if set_zero:
        e["set_zero"] = True
    if amount is not None:
        e["amount"] = amount
    e.update(extra)
    return e


def _pow(trigger, payload, **kw):
    t = {"op": "add_trigger", "trigger": trigger}
    t.update(kw)
    t["effects"] = payload
    return _card([t], ctype="power", cost=1)


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


def _set(src: str, name: str) -> set[str]:
    m = re.search(name + r"\s*=\s*\[(.*?)\];", src, re.S)
    return set(re.findall(r'"(\w+)"', m.group(1))) if m else set()


def test_version() -> None:
    print("Phase BP vocab stamp is at least 67 (Python + C#):")
    check(bts1.VOCAB_VERSION >= 67, f"bts1.VOCAB_VERSION >= 67, got {bts1.VOCAB_VERSION}")
    fc = _cs("Engine", "ForgedCards.cs")
    m = re.search(r"public const int VocabVersion = (\d+);", fc)
    check(m is not None and int(m.group(1)) >= 67, f"ForgedCards.VocabVersion >= 67, got {m and m.group(1)}")
    check(m is not None and bts1.VOCAB_VERSION <= int(m.group(1)), "bts1.VOCAB_VERSION <= ForgedCards.VocabVersion")
    check("67: Phase BP" in fc and all(f"`{t}`" in fc for t in ("on_card_generated", "on_debuff_applied", "on_evoke", "that_enemy")),
          "ForgedCards.cs comment names Phase BP + the tokens")
    check("`cost_delta {on, amount -2..+1, scope, set_zero?}`" in fc, "ForgedCards.cs comment names cost_delta's shape")
    check("67: Phase BP" in pathlib.Path(bts1.__file__).read_text(encoding="utf-8"), "bts1.py records the v67 entry")


def _t_verify_first() -> None:
    print("verify-first against the game sources (rule 0.6):")
    root = MODREF / "decomp_full"
    if not root.exists():
        print("  (decomp not on this machine — skipped, informational)")
        return
    am = (root / "MegaCrit.Sts2.Core.Models" / "AbstractModel.cs").read_text(encoding="utf-8")
    for sig in ("public virtual bool TryModifyEnergyCostInCombat(CardModel card, decimal originalCost, out decimal modifiedCost)",
                "public virtual Task AfterCardGeneratedForCombat(CardModel card, Player? creator)",
                "public virtual Task AfterPowerAmountChanged(PlayerChoiceContext choiceContext, PowerModel power, decimal amount, "
                "Creature? applier, CardModel? cardSource)",
                "public virtual Task AfterOrbEvoked(PlayerChoiceContext choiceContext, OrbModel orb, IEnumerable<Creature> targets)",
                "public virtual Task AfterCardDrawn(PlayerChoiceContext choiceContext, CardModel card, bool fromHandDraw)",
                "public virtual Task AfterCardExhausted(PlayerChoiceContext choiceContext, CardModel card, bool causedByEthereal)",
                "public virtual Task AfterCardPlayed(PlayerChoiceContext choiceContext, CardPlay cardPlay)"):
        check(sig in am, f"DECOMP AbstractModel: {sig[:72]}")
    ec = (root / "MegaCrit.Sts2.Core.Entities.Cards" / "CardEnergyCost.cs").read_text(encoding="utf-8")
    for m in ("public void SetThisCombat(int cost, bool reduceOnly = false)", "public void AddThisTurn(int amount, bool reduceOnly = false)",
              "public void AddThisCombat(int amount, bool reduceOnly = false)", "public int GetWithModifiers(CostModifiers modifiers)",
              "num = (int)Hook.ModifyEnergyCostInCombat(_card.CombatState, _card, num);", "return Math.Max(0, num);"):
        check(m in ec, f"DECOMP CardEnergyCost: {m[:60]}")
    hk = (root / "MegaCrit.Sts2.Core.Hooks" / "Hook.cs").read_text(encoding="utf-8")
    early = hk.find("item.TryModifyEnergyCostInCombat(card, modifiedCost, out modifiedCost);")
    late = hk.find("item2.TryModifyEnergyCostInCombatLate(card, modifiedCost, out modifiedCost);")
    check(0 <= early < late, "DECOMP Hook.ModifyEnergyCostInCombat: the EARLY pass runs before the LATE pass (Corruption wins)")
    cards = root / "MegaCrit.Sts2.Core.Models.Cards"
    check("base.EnergyCost.SetThisCombat(0);" in (cards / "MomentumStrike.cs").read_text(encoding="utf-8"), "DECOMP: Momentum Strike")
    kk = (cards / "KinglyKick.cs").read_text(encoding="utf-8")
    check("base.EnergyCost.AddThisCombat(-1);" in kk and "if (card != this)" in kk, "DECOMP: Kingly Kick (AfterCardDrawn, card == this)")
    check("base.EnergyCost.AddThisCombat(1);" in (cards / "Modded.cs").read_text(encoding="utf-8"), "DECOMP: Modded (+1 this combat)")
    st = (cards / "Stomp.cs").read_text(encoding="utf-8")
    check("base.EnergyCost.AddThisTurn(-amount);" in st and "e.HappenedThisTurn(base.CombatState)" in st,
          "DECOMP: Stomp (this-turn count, the back-fill our stateless form makes unnecessary)")
    pw = root / "MegaCrit.Sts2.Core.Models.Powers"
    sof = (pw / "SleightOfFleshPower.cs").read_text(encoding="utf-8")
    check("power.GetTypeForAmount(amount) == PowerType.Debuff && power.Owner.IsEnemy && applier == base.Owner && "
          "!(power is ITemporaryPower)" in sof, "DECOMP: the Sleight of Flesh filter (copied verbatim)")
    check("power is VulnerablePower" in (pw / "ViciousPower.cs").read_text(encoding="utf-8"), "DECOMP: Vicious (Vulnerable)")
    ars = (pw / "ArsenalPower.cs").read_text(encoding="utf-8")
    check("creator.Creature == base.Owner" in ars and "new ThrowingPlayerChoiceContext()" in ars,
          "DECOMP: Arsenal (creator filter, no ctx -> a throwing one)")
    cm = (root / "MegaCrit.Sts2.Core.Models" / "CardModel.cs").read_text(encoding="utf-8")
    fin = cm.find("CombatManager.Instance.History.CardPlayFinished(combatState, cardPlay);")
    aft = cm.find("await Hook.AfterCardPlayed(combatState, choiceContext, cardPlay);")
    check(0 <= fin < aft, "DECOMP: the play is recorded FINISHED before AfterCardPlayed (the counted tag reads it)")
    bl = MODREF / "BaseLib-StS2" / "Abstracts" / "CustomTemporaryPowerModel.cs"
    if bl.exists():
        check("CustomTemporaryPowerModel : CustomPowerModel, ITemporaryPower" in bl.read_text(encoding="utf-8"),
              "BaseLib: the temporary shell (Strength Down) is an ITemporaryPower (excluded from on_debuff_applied)")


def _t_engine() -> None:
    print("the engine: the cost hooks, the three trigger overrides, that_enemy, the tags:")
    dc = _cs("Engine", "DataCard.cs")
    for frag, why in (
            ("public override bool TryModifyEnergyCostInCombat(CardModel card, decimal originalCost, out decimal modifiedCost)",
             "the stateless cost hook"),
            ("if (card != this) return base.TryModifyEnergyCostInCombat(card, originalCost, out modifiedCost);", "only this card"),
            ("if (cd == null || !cd.IsCountedCostDelta || originalCost <= 0 || EnergyCost.CostsX) return false;",
             "counted forms only; X / free / unplayable skipped"),
            ("modifiedCost = Math.Max(0, originalCost + CostDeltaAmount(cd) * n);", "the count x amount, floored at 0"),
            ("&& (cd.Scope != \"this_turn\" || en.HappenedThisTurn(cs))", "this_turn counts only this turn's plays"),
            ("if (cd.SetZero) EnergyCost.SetThisCombat(0);", "set_zero = SetThisCombat(0) (Momentum Strike)"),
            ("else if (cd.Scope == \"combat\") EnergyCost.AddThisCombat(amt);", "combat = AddThisCombat"),
            ("else EnergyCost.AddThisTurn(amt);", "this_turn = AddThisTurn"),
            ("if (EnergyCost.CostsX) return;", "X-cost skipped (the held_discount rule)"),
            ("public override async Task AfterCardPlayed(PlayerChoiceContext choiceContext, CardPlay cardPlay)", "AfterCardPlayed"),
            ("if (cardPlay.Card == this) ApplyCostDelta(cd, \"played\");", "on played: this card"),
            ("public override async Task AfterCardDrawn(PlayerChoiceContext choiceContext, CardModel card, bool fromHandDraw)",
             "AfterCardDrawn (Kingly Kick)"),
            ("if (card == this && Spec.CostDelta is { On: \"drawn\" } cd) ApplyCostDelta(cd, \"drawn\");", "on drawn: this card"),
            ("public override async Task AfterCardExhausted(PlayerChoiceContext choiceContext, CardModel card, bool causedByEthereal)",
             "AfterCardExhausted"),
            ("Spec.CostDelta is { On: \"card_exhausted\" } cd", "on card_exhausted"),
            ("$\"[BP] cost_delta '{Spec.Title ?? Spec.Id}' on {evt}: {before} -> \"", "the mutating [BP] tag (old -> new)"),
            ("$\"[BP] cost_delta '{Spec.Title ?? Spec.Id}' on {cd.On}: {Math.Max(0, local + amt * (n - 1))} -> \"",
             "the stateless [BP] tag (old -> new)"),
            ("EnergyCost.GetWithModifiers(CostModifiers.Local)", "the tags log the cost READ"),
            ("case \"cost_delta\":            // Phase BP (v67, gap #76)", "DeclareEffects: cost_delta declares no var")):
        check(frag in dc, f"DataCard: {why}")
    spec = _cs("Engine", "CardSpec.cs")
    check("string? On = null," in spec and "bool SetZero = false)" in spec, "EffectSpec.On / SetZero")
    check('public bool IsCountedCostDelta => Op == "cost_delta" && On is "attack_played" or "skill_played" or "card_played";' in spec,
          "EffectSpec.IsCountedCostDelta")
    check("public EffectSpec? CostDelta => Effects.FirstOrDefault(e => e.Op == \"cost_delta\");" in spec, "CardSpec.CostDelta")
    er = _cs("Engine", "EffectRunner.cs")
    check('case "cost_delta":    // Phase BP (v67, gap #76)' in er, "EffectRunner: cost_delta is a no-op at play time")
    tp = _cs("Powers", "ForgedTriggerPower.cs")
    for frag, why in (
            ("public override async Task AfterCardGeneratedForCombat(CardModel card, Player? creator)", "AfterCardGeneratedForCombat"),
            ("creator == null || creator.Creature != Owner", "on_card_generated: the creator filter (Arsenal)"),
            ('await FireReactive("on_card_generated", _combatCtx ?? new ThrowingPlayerChoiceContext());',
             "no ctx: the captured one or a throwing one"),
            ("public override async Task AfterPowerAmountChanged(PlayerChoiceContext ctx, PowerModel power, decimal amount,",
             "AfterPowerAmountChanged"),
            ("if (amount == 0m || power.GetTypeForAmount(amount) != PowerType.Debuff || power.Owner == null || !power.Owner.IsEnemy",
             "the Sleight of Flesh filter (debuff, enemy)"),
            ("|| applier != Owner || power is ITemporaryPower) return;", "the Sleight of Flesh filter (applier, temporary)"),
            ("if (t.Status != null && !DebuffMatches(power, t.Status)) return;", "the Vicious status filter"),
            ('"vulnerable" => power is VulnerablePower,', "status filter maps to the base power type"),
            ('await FireReactive("on_debuff_applied", ctx, attacker: power.Owner);', "the debuffed enemy rides the attacker slot"),
            ("public override async Task AfterOrbEvoked(PlayerChoiceContext ctx, OrbModel orb, IEnumerable<Creature> targets)",
             "AfterOrbEvoked"),
            ("orb.Owner != Owner.Player", "on_evoke: the owner's orbs"),
            ("[BP] on_card_generated fired", "the [BP] on_card_generated tag"),
            ("[BP] on_debuff_applied fired", "the [BP] on_debuff_applied tag"),
            ("[BP] on_evoke fired", "the [BP] on_evoke tag"),
            ('MainFile.Logger.Info($"[BP] re-entry blocked ({kind}).");', "the [BP] re-entry tag (the _firing guard held)"),
            ('"on_card_generated" => "On Card Created", "on_debuff_applied" => "On Debuff Applied"', "the power titles")):
        check(frag in tp, f"ForgedTriggerPower: {why}")
    for hook in ("AfterCardGeneratedForCombat", "AfterPowerAmountChanged", "AfterOrbEvoked"):
        body = tp.split(f"public override async Task {hook}", 1)[1].split("\n    }\n", 1)[0]
        check("_combatCtx = ctx" not in body, f"{hook} never stores its ctx (a throwing one may arrive)")
    tr = _cs("Engine", "TriggerRunner.cs")
    check('if (target == "that_enemy")' in tr and "[BP] that_enemy -> '" in tr and "return alive ? [attacker!] : [];" in tr,
          "TriggerRunner.ResolveEnemies: that_enemy (+ its tag)")
    fc = _cs("Engine", "ForgedCards.cs")
    check("cost_delta" in _set(fc, "SupportedOps") and "cost_delta" not in _set(fc, "TriggerOps"), "cost_delta: supported, card-only")
    for k in NEW_TRIGGERS:
        check(k in _set(fc, "SupportedTriggers") and k in _set(fc, "MultiFireTriggers") and k in _set(fc, "OncePerCombatTriggers"),
              f"{k}: supported, multi-fire, power-hosted (every_n / this_turn / once_per_* legal)")
    check(_set(fc, "DebuffTriggerStatuses") == {"vulnerable", "weak", "frail", "poison", "doom"}, "the status-filter set")
    for frag in ("cost_delta needs an 'on' event", "cost_delta 'set_zero' is on:'played' + scope 'combat' with no amount",
                 "cost_delta +1 (a card that costs more each play — Modded) needs on:'played' + scope 'combat'.",
                 "cost_delta on:'card_played' is this_turn only", "a 'cost_delta' discount needs a card that costs 1+ energy",
                 "'cost_delta' is not allowed on an X-cost card", "cost_delta on:'played' is not allowed on a Power",
                 "an upgrade can't change a cost_delta's 'on' / 'scope' / 'set_zero'",
                 "'cost_delta' and 'held_discount' can't share a card", "an add_trigger 'status' filter only applies to on_debuff_applied",
                 "a trigger effect target 'that_enemy' is only valid on the 'on_debuff_applied' trigger",
                 "'on' / 'set_zero' only apply to cost_delta"):
        check(frag in fc, f"ForgedCards.Validate: {frag[:70]}")


CASES = [([{"op": "block", "amount": 10}, _cd("skill_played", "this_turn", -1)], "self",
          "Gain {Block} Block.\nCosts 1 less this turn for each Skill you play."),
         ([{"op": "damage", "amount": 12}, _cd("attack_played", "this_turn", -1)], "all_enemies",
          "Deal {Damage} damage to ALL enemies.\nCosts 1 less this turn for each Attack you play."),
         ([{"op": "damage", "amount": 10}, _cd("card_played", "this_turn", -2)], "enemy",
          "Deal {Damage} damage.\nCosts 2 less this turn for each card you play."),
         ([{"op": "damage", "amount": 9}, _cd("attack_played", "combat", -1)], "enemy",
          "Deal {Damage} damage.\nCosts 1 less this combat for each Attack you play."),
         ([{"op": "damage", "amount": 10}, _cd("played", "combat", set_zero=True)], "enemy",
          "Deal {Damage} damage.\nAfter you play this, it costs 0 for the rest of combat."),
         ([{"op": "damage", "amount": 27}, _cd("drawn", "combat", -1)], "enemy",
          "Deal {Damage} damage.\nWhenever you draw this, it costs 1 less this combat."),
         ([{"op": "draw", "amount": 1}, _cd("played", "combat", 1)], "self",
          "Draw {Cards} card(s).\nCosts 1 more each time you play it."),
         ([{"op": "draw", "amount": 2}, _cd("played", "combat", -1)], "self",
          "Draw {Cards} card(s).\nCosts 1 less this combat each time you play it."),
         ([{"op": "draw", "amount": 2}, _cd("played", "this_turn", -1)], "self",
          "Draw {Cards} card(s).\nCosts 1 less this turn each time you play it."),
         ([{"op": "damage", "amount": 16}, _cd("card_exhausted", "combat", -1)], "enemy",
          "Deal {Damage} damage.\nCosts 1 less this combat for each card you Exhaust."),
         ([{"op": "damage", "amount": 6}, _cd("drawn", "this_turn", -2)], "enemy",
          "Deal {Damage} damage.\nWhenever you draw this, it costs 2 less this turn."),
         ([{"op": "add_trigger", "trigger": "on_card_generated", "effects": [{"op": "apply_status", "status": "strength", "amount": 1}]}],
          "self", "Whenever you create a card, gain 1 Strength."),
         ([{"op": "add_trigger", "trigger": "on_debuff_applied", "effects": [{"op": "damage", "amount": 3, "target": "that_enemy"}]}],
          "self", "Whenever you apply a debuff, deal 3 damage to that enemy."),
         ([{"op": "add_trigger", "trigger": "on_debuff_applied", "status": "vulnerable", "effects": [{"op": "draw", "amount": 1}]}],
          "self", "Whenever you apply Vulnerable, draw 1 card(s)."),
         ([{"op": "add_trigger", "trigger": "on_evoke", "effects": [{"op": "block", "amount": 3}]}], "self",
          "Whenever you Evoke an orb, gain 3 Block."),
         ([{"op": "add_trigger", "trigger": "on_debuff_applied", "every_n": 3, "status": "poison",
            "effects": [{"op": "block", "amount": 4}]}], "self", "Every 3rd time you apply Poison, gain 4 Block."),
         ([{"op": "add_trigger", "trigger": "on_card_generated", "scope": "this_turn", "effects": [{"op": "block", "amount": 2}]}],
          "self", "This turn, whenever you create a card, gain 2 Block.")]
C_FRAGMENTS = ('if (e.SetZero) return "After you play this, it costs 0 for the rest of combat.";',
               'if (e.Amount > 0) return $"Costs {e.Amount} more each time you play it.";',
               'string life = e.Scope == "combat" ? "this combat" : "this turn";',
               '"played"         => $"Costs {n} less {life} each time you play it.",',
               '"drawn"          => $"Whenever you draw this, it costs {n} less {life}.",',
               '"attack_played"  => $"Costs {n} less {life} for each Attack you play.",',
               '"skill_played"   => $"Costs {n} less {life} for each Skill you play.",',
               '"card_exhausted" => $"Costs {n} less {life} for each card you Exhaust.",',
               '_                => $"Costs {n} less {life} for each card you play.",',
               'case "cost_delta":    parts.Add(CostDeltaSentence(e)); break;',
               '"on_card_generated" => "Whenever you create a card",',
               '"on_debuff_applied" => t.Status != null ? $"Whenever you apply {StatusName(t.Status)}" : "Whenever you apply a debuff",',
               '"on_evoke"        => "Whenever you Evoke an orb",',
               ': e.Target == "that_enemy" ? " to that enemy" : "";')


def _t_rules_and_describe() -> None:
    print("validator + describe (Python literal == the C# fragment written by hand):")
    ok = [_atk([{"op": "damage", "amount": 12}, _cd("attack_played", "this_turn", -1)], cost=3, target="all_enemies"),
          _card([{"op": "block", "amount": 10}, _cd("skill_played", "this_turn", -1)]),
          _atk([{"op": "damage", "amount": 10}, _cd("card_played", "this_turn", -1)]),
          _atk([{"op": "damage", "amount": 9}, _cd("skill_played", "combat", -1)], rarity="rare"),
          _atk([{"op": "damage", "amount": 10}, _cd("played", "combat", set_zero=True)], cost=1, rarity="common"),
          _atk([{"op": "damage", "amount": 27}, _cd("drawn", "combat", -1)], cost=4, rarity="rare"),
          _atk([{"op": "damage", "amount": 8}, _cd("drawn", "this_turn", -2)], cost=3),
          _card([{"op": "draw", "amount": 1}, _cd("played", "combat", 1)], cost=0, rarity="rare"),
          _card([{"op": "draw", "amount": 2}, _cd("played", "combat", -1)]),
          _card([{"op": "draw", "amount": 2}, _cd("played", "this_turn", -2)], cost=3),
          _atk([{"op": "damage", "amount": 16}, _cd("card_exhausted", "combat", -1)], cost=3),
          # the upgrade may move the amount, never the event
          _atk([{"op": "damage", "amount": 9}, _cd("drawn", "combat", -1)], cost=3,
               upgrade=[{"op": "damage", "amount": 12}, _cd("drawn", "combat", -2)]),
          # a Power may take a counted / drawn cost_delta (it is played once, but its cost moves before that)
          _card([{"op": "apply_status", "status": "strength", "amount": 2}, _cd("drawn", "combat", -1)], ctype="power", cost=3),
          _pow("on_card_generated", [{"op": "block", "amount": 2}]),
          _pow("on_debuff_applied", [{"op": "damage", "amount": 3, "target": "that_enemy"}]),
          _pow("on_debuff_applied", [{"op": "apply_status", "status": "weak", "amount": 1, "target": "that_enemy"}]),
          _pow("on_debuff_applied", [{"op": "draw", "amount": 1}], status="vulnerable"),
          _pow("on_debuff_applied", [{"op": "block", "amount": 2}], status="doom"),
          # BI's filters on the new kinds (decision recorded in the plan): every_n / this_turn / once_per_* are legal
          _pow("on_card_generated", [{"op": "draw", "amount": 1}], every_n=3),
          _pow("on_debuff_applied", [{"op": "block", "amount": 3}], scope="this_turn"),
          _pow("on_evoke", [{"op": "block", "amount": 3}], once_per_turn=True)]
    for c in ok:
        check(not _errs(c), f"validates: {json.dumps(c['effects'])} -> {_errs(c)}")
    bad = [(_card([{"op": "block", "amount": 5}, _cd("skill_played", "this_turn", -1)], cost=0), "costs 1+"),
           (_card([{"op": "block", "amount": 5}, _cd("played", "combat", set_zero=True)], cost=0), "costs 1+"),
           (_card([{"op": "block", "amount": 5, "scale": "x"}, _cd("played", "combat", 1)], cost="X"), "X-cost"),
           (_card([{"op": "block", "amount": 5}, _cd("played", "combat", -1)], ctype="power"), "not allowed on a Power"),
           (_card([{"op": "block", "amount": 5}, _cd("played", "combat", -3)]), "amount"),
           (_card([{"op": "block", "amount": 5}, _cd("played", "combat", 2)]), ""),
           (_card([{"op": "block", "amount": 5}, _cd("played", "combat", 0)]), ""),
           (_card([{"op": "block", "amount": 5}, _cd("drawn", "combat", 1)]), "+1"),
           (_card([{"op": "block", "amount": 5}, _cd("played", "this_turn", 1)]), "+1"),
           (_card([{"op": "block", "amount": 5}, _cd("attack_played", "combat", -2)]), "moves the cost by 1"),
           (_card([{"op": "block", "amount": 5}, _cd("card_played", "combat", -1)]), "this_turn only"),
           (_card([{"op": "block", "amount": 5}, _cd("drawn", "combat", set_zero=True)]), "set_zero"),
           (_card([{"op": "block", "amount": 5}, _cd("played", "this_turn", set_zero=True)]), "set_zero"),
           (_card([{"op": "block", "amount": 5}, _cd("discarded", "combat", -1)]), ""),
           (_card([{"op": "block", "amount": 5}, {"op": "cost_delta", "on": "played", "amount": -1}]), ""),
           (_card([{"op": "block", "amount": 5}, _cd("played", "combat", -1, card_type="attack")]), ""),
           (_card([{"op": "block", "amount": 5}, _cd("played", "combat", -1), _cd("drawn", "combat", -1)]), "at most one 'cost_delta'"),
           (_card([{"op": "block", "amount": 5}, _cd("drawn", "combat", -1), {"op": "retain"}, {"op": "held_discount"}]),
            "held_discount"),
           (_atk([{"op": "damage", "amount": 9}, _cd("drawn", "combat", -1)], cost=3,
                 upgrade=[{"op": "damage", "amount": 12}, _cd("played", "combat", -1)]), "only its amount"),
           (_card([{"op": "block", "amount": 5, "on": "played"}]), ""),
           (_pow("turn_start", [{"op": "block", "amount": 2}], status="vulnerable"), ""),
           (_pow("on_debuff_applied", [{"op": "block", "amount": 2}], status="strength"), ""),
           (_pow("attacked", [{"op": "damage", "amount": 3, "target": "that_enemy"}]), "that_enemy"),
           (_pow("turn_start", [_cd("played", "combat", -1)]), "")]
    for c, frag in bad:
        e = _errs(c)
        check(bool(e) and any(frag in x for x in e), f"rejected ({frag or 'any'}): {json.dumps(c['effects'])} -> {e}")
    v = _V
    check(v._score_effect(_cd("played", "combat", set_zero=True)) == 4.0 and v._score_effect(_cd("played", "combat", 1)) == -2.0,
          "cost_delta priced: set_zero 4, the +1 tax -2")
    check(v._score_effect(_cd("drawn", "combat", -1)) == 3.0 and v._score_effect(_cd("skill_played", "this_turn", -1)) == 2.0,
          "cost_delta priced: whole-combat step 3, counted this-turn step 2")
    for effects, target, want in CASES:
        got = cardgen.describe(effects, target)
        check(got == want, f"describe {got!r} == {want!r}")
    src = _cs("Engine", "ForgedCards.cs")
    for frag in C_FRAGMENTS:
        check(frag in src, f"C# Describe fragment: {frag}")
    check(cardgen.effect_literal(_cd("skill_played", "this_turn", -1))
          == 'new EffectSpec("cost_delta", -1, Scope: "this_turn", On: "skill_played")', "effect_literal: cost_delta")
    check(cardgen.effect_literal(_cd("played", "combat", set_zero=True))
          == 'new EffectSpec("cost_delta", 0, Scope: "combat", On: "played", SetZero: true)', "effect_literal: set_zero")
    lit = cardgen.effect_literal({"op": "add_trigger", "trigger": "on_debuff_applied", "status": "vulnerable",
                                  "effects": [{"op": "damage", "amount": 3, "target": "that_enemy"}]})
    check(lit == 'new EffectSpec("add_trigger", 0, Trigger: "on_debuff_applied", Triggered: '
                 '[new EffectSpec("damage", 3, Target: "that_enemy")], Status: "vulnerable")', f"effect_literal: the filter + target: {lit}")
    check("string? on = e.ContainsKey(\"on\")" in src and "bool setZero = e.ContainsKey(\"set_zero\") && e[\"set_zero\"].AsBool();" in src,
          "ForgedCards.ParseEffects reads on / set_zero")


def _t_contract() -> None:
    print("contract surfaces:")
    schema = json.loads(CARD_SCHEMA.read_text(encoding="utf-8"))
    eff = schema["$defs"]["effect"]
    check("cost_delta" in eff["properties"]["op"]["enum"], "schema: op enum += cost_delta")
    check(eff["properties"]["on"]["enum"] == ["played", "drawn", "attack_played", "skill_played", "card_played", "card_exhausted"],
          "schema: the `on` field")
    check(eff["properties"]["set_zero"]["type"] == "boolean", "schema: the `set_zero` field")
    check(eff["properties"]["amount"]["minimum"] == -2, "schema: amount is signed (cost_delta) ...")
    rules = json.dumps(eff.get("allOf", []))
    check('"not": {"properties": {"op": {"const": "cost_delta"}}}' in rules and '"then": {"properties": {"amount": {"minimum": 1}}}' in rules,
          "schema: ... and >= 1 on every other op")
    check('"required": ["on", "scope"]' in rules and '"maximum": 1, "not": {"const": 0}' in rules, "schema: the cost_delta clause")
    check('"op": {"enum": ["cost_shift", "add_trigger", "cost_delta"]}' in rules, "schema: scope belongs to cost_delta too")
    check('"trigger": {"const": "on_debuff_applied"}, "status": {"enum": ["vulnerable", "weak", "frail", "poison", "doom"]}' in rules,
          "schema: the add_trigger status filter")
    check(set(NEW_TRIGGERS) <= set(eff["properties"]["trigger"]["enum"]), "schema: trigger enum += the three kinds")
    te = schema["$defs"]["triggerEffect"]
    check("cost_delta" not in te["properties"]["op"]["enum"], "schema: cost_delta is never a payload op")
    check("that_enemy" in te["properties"]["target"]["enum"], "schema: payload target += that_enemy")
    vocab = paths.VOCABULARY.read_text(encoding="utf-8")
    idx = gate.vocab_index(vocab)
    check(vocab.count("| `cost_delta`") == 1 and "`cost_delta` —" in idx, "VOCABULARY: ONE cost_delta row (+ its index line)")
    for t in NEW_TRIGGERS:
        check(f"`{t}` (v67" in vocab and f"`{t}`" in idx, f"VOCABULARY: Triggers prose + the index name {t}")
    check("on_shuffle/on_card_generated/on_debuff_applied/on_evoke)" in vocab and "`status` (v67, on_debuff_applied" in vocab,
          "VOCABULARY: the add_trigger row")
    check('`"that_enemy"` (v67, the enemy you just debuffed' in vocab, "VOCABULARY: the that_enemy target")
    check("cost_delta" in gate.GATED_OP_ORDER, "gate.GATED_OP_ORDER carries cost_delta (no card core cost)")
    check(gate.FIELD_UNITS["on"] == ("cost_delta",) and gate.FIELD_UNITS["set_zero"] == ("cost_delta",)
          and "cost_delta" in gate.FIELD_UNITS["scope"], "gate.FIELD_UNITS: on / set_zero / scope")
    react = {k for k, _ in coverage.REACTIVE_MENU_V2}
    check(set(NEW_TRIGGERS) <= react and all(k in coverage.CENSUS_DETECTOR for k in NEW_TRIGGERS),
          "coverage: REACTIVE_MENU_V2 + detectors for the three kinds")
    samples = {"on_card_generated": _pow("on_card_generated", [{"op": "block", "amount": 2}]),
               "on_debuff_applied": _pow("on_debuff_applied", [{"op": "damage", "amount": 3, "target": "that_enemy"}]),
               "on_evoke": _pow("on_evoke", [{"op": "block", "amount": 3}])}
    plain = census.walk_card(_atk([{"op": "damage", "amount": 6}]))
    for k, c in samples.items():
        check(coverage.CENSUS_DETECTOR[k](census.walk_card(c)) and not coverage.CENSUS_DETECTOR[k](plain), f"the {k} detector")
        check(coverage.directive_key(coverage.DIRECTIVE_BY_KEY[k]) == k, f"directive_key round-trips {k}")
    check(coverage.KEY_KIND.get("on_evoke") == "orb", "coverage: on_evoke is orb-gated")
    with _env(BTS_HARNESS_V2="1"):
        normal = {k for k, _ in coverage._menus(None, 5, kinds={""})[0]}
        orb = {k for k, _ in coverage._menus(None, 5, kinds={"", "orb"})[0]}
        nom = [k for k, _ in coverage._menus({"reactive": ["on_evoke", "on_debuff_applied"]}, 5, kinds={""})[0]]
    check("on_evoke" not in normal and {"on_card_generated", "on_debuff_applied"} <= normal, "a normal class is never dealt on_evoke")
    check("on_evoke" in orb, "an orb class is dealt on_evoke")
    check(nom == ["on_debuff_applied"], f"a nominated on_evoke is dropped on a normal class: {nom}")
    fe = next((f for f in featured.FEATURED_MENU if f.id == "self_discount"), None)
    check(fe is not None and fe.detect(census.walk_card(_atk([{"op": "damage", "amount": 9}, _cd("drawn", "combat", -1)])))
          and not fe.detect(plain), "featured: the self_discount entry + detector")
    check("cost_delta" in harness_v2._PREFERRED_OPS and {"on_card_generated", "on_debuff_applied"} <= set(harness_v2._PREFERRED_TRIGGERS)
          and "on_evoke" in harness_v2._CLASS_ONLY_TOKENS, "harness_v2: preferred op / triggers, on_evoke class-only")
    check(cf._card_uses_orbs(samples["on_evoke"]) and not cf._card_uses_orbs(samples["on_debuff_applied"]),
          "class_forge: an on_evoke card is orb-class only (dropped off a slotless class)")
    toks = bridges.card_tokens(_pow("on_debuff_applied", [{"op": "draw", "amount": 1}], status="vulnerable"))
    check({"on_debuff_applied", "vulnerable"} <= toks, "bridges: the status filter surfaces its status")
    check("cost_delta" in bridges.card_tokens(_card([{"op": "block", "amount": 5}, _cd("played", "combat", -1)])),
          "bridges: cost_delta surfaces as a token")
    arch = {a["id"]: a for a in json.loads((DATA / "archetypes.json").read_text(encoding="utf-8"))["archetypes"]}
    claims = {"tempo_draw": ("cost_delta", "#76"), "big_energy": ("cost_delta", "#76"), "retain_hold": ("cost_delta", "#76"),
              "strike_tempo": ("cost_delta", "#76"), "token_conjurer": ("on_card_generated", "#77"),
              "debuff_expose": ("on_debuff_applied", "#77"), "poison_attrition": ("on_debuff_applied", "#77"),
              "orb_channel": ("on_evoke", "#77")}
    for aid, (tok, gap) in claims.items():
        a = arch[aid]
        check(tok in a["vocabulary"]["ops"], f"{aid} claims {tok}")
        check(f"VOCABULARY_GAPS{gap}" in a["gap_refs"] and a["buildable"] is True, f"{aid} refs {gap}")
        check("(v67)" in a.get("build_notes", ""), f"{aid} build_notes name the v67 shape")
    pool = json.loads((DATA / "exemplar_pool.json").read_text(encoding="utf-8"))["exemplars"]
    v = harness_v2.exemplar_validator()
    used, ons, zero, tax, target = set(), set(), False, False, False
    for e in pool:
        hit = set(NEW_TOKENS) & bridges.card_tokens(e["card"])
        if not hit:
            continue
        used |= hit
        r = v.validate(dict(e["card"]))
        check(r.ok, f"exemplar {e['card']['id']} validates: {r.errors}")
        check((e.get("needs") == "orb") == ("on_evoke" in hit), f"exemplar {e['card']['id']} needs orb iff on_evoke")
        for x in e["card"]["effects"]:
            if x.get("op") == "cost_delta":
                ons.add(x.get("on"))
                zero |= x.get("set_zero") is True
                tax |= isinstance(x.get("amount"), int) and x["amount"] > 0
            for y in x.get("effects") or []:
                target |= y.get("target") == "that_enemy"
    check(set(NEW_TOKENS) <= used, f"exemplars cover every new token (got {sorted(used)})")
    check(ons == {"played", "drawn", "attack_played", "skill_played", "card_exhausted"} or
          ons >= {"played", "drawn", "attack_played", "skill_played", "card_exhausted"}, f"exemplars show the cost_delta forms: {ons}")
    check(zero and tax and target, "exemplars show set_zero, the +1 tax and the that_enemy target")
    heur = (paths.VOCABULARY.parent / "DESIGN_HEURISTICS.md").read_text(encoding="utf-8")
    check(heur.count("(v67") >= 8, "DESIGN_HEURISTICS: the v67 notes on all eight archetypes")
    gaps_md = (REPO / "VOCABULARY_GAPS.md").read_text(encoding="utf-8")
    for n, nxt in (("76", "77"), ("77", "78")):
        entry = gaps_md.split(f"### {n}.", 1)[1].split(f"### {nxt}.", 1)[0]
        check("**Status:** **done (2026-10-04, vocab v67, Phase BP)**" in entry, f"gap #{n} is done (v67)")
        check("vocab v68" not in entry, f"gap #{n} no longer names v68")
    js = (REPO / "web" / "static" / "render.js").read_text(encoding="utf-8")
    for frag in ('case "cost_delta": return costDeltaPhrase(e);', 'if (e.set_zero) return "After you play this, it costs 0 for the rest of combat";',
                 'on_card_generated: "Whenever you create a card", on_debuff_applied: "Whenever you apply a debuff",',
                 'on_evoke: "Whenever you Evoke an orb"', '`Whenever you apply ${statusName(e.status)}`', '" to that enemy"'):
        check(frag in js, f"render.js: {frag[:60]}")
    src = pathlib.Path(cf.__file__).read_text(encoding="utf-8")
    check("a `cost_delta` card that cheapens itself (v67: Stomp, Momentum Strike)" in src
          and "v67: on_card_generated (Arsenal), on_debuff_applied (+ status filter; payload target that_enemy), on_evoke (orb only)." in src,
          "class_forge: the translation clause + the TRIGGERS sentence")
    plan = (REPO / "docs" / "plans" / "VOCAB_EXPANSION_6_PLAN.md").read_text(encoding="utf-8")
    check("**Findings (BP" in plan and "**Phase BP" in plan, "the plan records the BP findings + status line")


def _t_tester() -> None:
    print("the tester (validate-only path):")
    p = TESTER_DIR / "build_tester.py"
    check(p.exists(), "tests/gaptest-bp/build_tester.py exists")
    spec = importlib.util.spec_from_file_location("bp_tester", p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    check(mod.validate(verbose=True) == 0, "every tester card validates")
    types = [c["type"] for c in mod.CARDS if c["rarity"] != "basic"]
    check(types.count("attack") >= 3 and types.count("skill") >= 3 and types.count("power") >= 1,
          "pool: >= 3 non-basic Attacks + Skills and >= 1 Power (the merchant stall)")
    flat = json.dumps(mod.CARDS)
    for need in ('"on": "attack_played"', '"on": "skill_played"', '"on": "card_played"', '"on": "drawn"', '"on": "card_exhausted"',
                 '"set_zero": true', '"on": "played", "scope": "combat", "amount": 1', '"on": "played", "scope": "combat", "amount": -1',
                 '"trigger": "on_card_generated"', '"trigger": "on_debuff_applied", "status": "vulnerable"',
                 '"target": "that_enemy"', '"op": "add_status_card"', '"op": "add_card"', '"op": "exhaust_card"', '"status": "vulnerable"'):
        check(need in flat, f"the tester exercises {need}")
    names = {c["name"] for c in mod.CARDS}
    for base in ("Stomp", "Momentum Strike", "Kingly Kick", "Arsenal", "Vicious", "Sleight of Flesh"):
        check(base in names, f"the tester carries the plan's {base}")
    text = p.read_text(encoding="utf-8")
    check("--validate-only" in text and "on_evoke` is orb-class only" in text and "re-entry blocked" in text,
          "the tester has --validate-only, says on_evoke is not proven here, and names the re-entry tag")


def _t_smoke_record() -> None:
    print("the saved AutoSlay tag greps (TEST_AUDIT_2026-10 §7):")
    files = [TESTER_DIR / f"godot_BP_tags_{s}.txt" for s in SMOKE_SEEDS]
    seen = ""
    for p in files:
        assert p.exists(), f"missing smoke record {p}"
        txt = p.read_text(encoding="utf-8")
        check("Run completed" in txt, f"{p.name}: the run completed")
        check("[BP]" in txt, f"{p.name} holds [BP] tags")
        check("mod exceptions: 0" in txt and "Localization formatting errors: 0" in txt
              and "BlankTheSpire stack frames: 0" in txt, f"{p.name} records a clean run")
        seen += txt
    for t in TAGS:
        check(t in seen, f"the smoke fired '{t}'")
    check("Auto-selected" in seen, "Burning Pact's picker resolved through the AutoSlay selector")
    check("Strength Down" not in seen and "ForgedTempStrengthDownPower" not in seen,
          "no temporary wrapper ever fired on_debuff_applied")


def _t_budget() -> None:
    print("rule 0.9 — readings on the real path:")
    from tests.test_harness_v2 import (BP_ARCHETYPE_CEILING, BP_INDEX_CEILING, BP_SCAFFOLD_BUDGET_PER_ARCHETYPE,
                                       BP_TOTAL_TRIPWIRE, BP_TRIAD_BUDGET, rule_0_9_readings)
    with _env(BTS_HARNESS_V2="1", BTS_BLUEPRINT_VOCAB="tree"):
        r = rule_0_9_readings()
    print(f"  (reading) index                  {r['index']:>8,}  (clause cap {r['index_clause_cap']}; budget {BP_INDEX_CEILING:,})")
    print(f"  (reading) per-archetype max      {r['archetype_max']:>8,}  ({r['archetype_max_id']}; ceiling {BP_ARCHETYPE_CEILING:,})")
    print(f"  (reading) per-archetype scaffold {r['archetype_scaffold_max']:>8,}  ({r['archetype_scaffold_max_id']}; "
          f"budget {BP_SCAFFOLD_BUDGET_PER_ARCHETYPE:,})")
    print(f"  (reading) triads                 {', '.join(f'{k} {v:,}' for k, v in r['triads'].items())}  (budget {BP_TRIAD_BUDGET:,})")
    print(f"  (reading) all-ops path           {r['all_ops']:>8,}  (tripwire {BP_TOTAL_TRIPWIRE:,})")
    print(f"  (reading) scaffold (all-ops)     {r['scaffold']:>8,}")
    print(f"  (reading) full path (untrimmed)  {r['untrimmed']:>8,}  (scaffold {r['untrimmed_scaffold']:,})")
    check(BP_INDEX_CEILING == gate.INDEX_BUDGET == 11_000, "rule 0.9 (2026-10-04): index budget 11,000 for the stretch phases")
    check(r["index"] <= BP_INDEX_CEILING, "index within budget")
    check(r["archetype_max"] <= BP_ARCHETYPE_CEILING, "every archetype alone within its ceiling")
    check(r["archetype_scaffold_max"] <= BP_SCAFFOLD_BUDGET_PER_ARCHETYPE, "per-archetype scaffold within budget")
    check(all(n <= BP_TRIAD_BUDGET for n in r["triads"].values()), "the sample triads within their ceiling")
    check(r["all_ops"] <= BP_TOTAL_TRIPWIRE, "the all-ops path under the tripwire")


def main() -> int:
    test_version()
    _t_verify_first()
    _t_engine()
    _t_rules_and_describe()
    _t_contract()
    _t_tester()
    _t_smoke_record()
    _t_budget()
    print(f"\n{_PASS} passed, {_FAIL} failed")
    return 1 if _FAIL else 0


def test_phase_bp_all() -> None:
    global _PASS, _FAIL
    _PASS = _FAIL = 0
    assert main() == 0, f"{_FAIL} Phase BP check(s) failed - see the FAIL lines above"


if __name__ == "__main__":
    sys.exit(main())
