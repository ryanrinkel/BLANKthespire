"""Phase BN — on-kill payoff, random card generation, autoplay (VOCAB_EXPANSION_6_PLAN, gaps #71-#73, vocab v69) — offline.
Run: uv run python -m tests.test_phase_bn  (from generation/)

Pins: the stamp; verify-first against the game sources (Feed snapshots ShouldOwnerDeathTriggerFatal BEFORE its attack and
the powers are removed after death; Sunder's any-kill read; the Discovery / Infernal Blade / Creative AI recipes;
CardFactory.GetDistinctForCombat; FromChooseACardScreen throws above 3 and ReportSoftlocks on 0; SetToFreeThisTurn; Havoc /
Uproar / Mayhem and AutoPlayFromDrawPile's forced exhaust; CardCmd.AutoPlay's random target; AfterAutoPrePlayPhaseEntered);
the engine wiring (the play-local kill flags + the gate, add_random_card's pool filters + empty-pool guard + choose screen,
autoplay's two forms + depth guard + candidate rule, the Mayhem fire point, the [BN] tags); the validator rules on both
sides; the describe byte-match (Python literals asserted, the C# fragments grepped); the contract surfaces (schema,
VOCABULARY rows, gate, coverage, featured, harness_v2, class_forge, archetypes, exemplars, heuristics, gap log, render.js,
the plan); the tester's validate-only path; the saved AutoSlay tag greps under tests/gaptest-bn/ when they exist ("smoke
pending" until then); and prints the rule-0.9 readings.
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
TESTER_DIR = pathlib.Path(__file__).parent / "gaptest-bn"
SMOKE_SEEDS = ("GAPTESTBN1", "GAPTESTBN2")
MODREF = pathlib.Path(r"C:/Users/ryanr/Desktop/NOVOGODOT/BLANKthespire/_modref")

NEW_OPS = ("add_random_card", "autoplay")
NEW_TOKENS = NEW_OPS + ("target_killed",)
TAGS = ("[BN] target_killed gate OPEN", "[BN] target_killed gate closed", "(negated)", "fatal=True",
        "choose_of=3", "[BN] add_random_card attack x1 -> Hand", "-> Discard", "('payload')", "Auto-selected 1 card(s)",
        "[BN] autoplay draw_top '", "[BN] autoplay draw_random '", "[BN] mayhem payload from AfterAutoPrePlayPhaseEntered",
        "[BP] on_card_generated fired")
KILLED = {"kind": "target_killed"}


def check(cond: bool, msg: str) -> None:
    global _PASS, _FAIL
    if cond:
        _PASS += 1
    else:
        _FAIL += 1
        print(f"  FAIL: {msg}")


def _cs(*parts: str) -> str:
    return (MOD_CODE.joinpath(*parts)).read_text(encoding="utf-8-sig").replace("\r\n", "\n")


def _card(effects, rarity="uncommon", cost=1, ctype="skill", target="self", upgrade=None, up_cost=None):
    c = {"id": "bn_t", "name": "BN", "type": ctype, "rarity": rarity, "cost": cost, "target": target, "effects": effects}
    if upgrade is not None or up_cost is not None:
        c["upgrade"] = {"effects": upgrade if upgrade is not None else effects}
        if up_cost is not None:
            c["upgrade"]["cost"] = up_cost
    return c


def _atk(effects, **kw):
    kw.setdefault("ctype", "attack")
    kw.setdefault("target", "enemy")
    return _card(effects, **kw)


def _pow(effects, **kw):
    kw.setdefault("ctype", "power")
    kw.setdefault("rarity", "rare")
    return _card(effects, **kw)


def _trig(trigger, payload):
    return [{"op": "add_trigger", "trigger": trigger, "effects": payload}]


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
    print("Phase BN vocab stamp is at least 69 (Python + C#):")
    check(bts1.VOCAB_VERSION >= 69, f"bts1.VOCAB_VERSION >= 69, got {bts1.VOCAB_VERSION}")
    fc = _cs("Engine", "ForgedCards.cs")
    m = re.search(r"public const int VocabVersion = (\d+);", fc)
    check(m is not None and int(m.group(1)) >= 69, f"ForgedCards.VocabVersion >= 69, got {m and m.group(1)}")
    check(m is not None and bts1.VOCAB_VERSION <= int(m.group(1)), "bts1.VOCAB_VERSION <= ForgedCards.VocabVersion")
    check("69: Phase BN" in fc and all(f"`{t}`" in fc for t in NEW_TOKENS), "ForgedCards.cs comment names Phase BN + the tokens")
    check("69: Phase BN" in pathlib.Path(bts1.__file__).read_text(encoding="utf-8"), "bts1.py records the v69 entry")


def _t_verify_first() -> None:
    print("verify-first against the game sources (rule 0.6):")
    root = MODREF / "decomp_full"
    if not root.exists():
        print("  (decomp not on this machine — skipped, informational)")
        return
    cards = root / "MegaCrit.Sts2.Core.Models.Cards"
    feed = (cards / "Feed.cs").read_text(encoding="utf-8")
    check(feed.index("ShouldOwnerDeathTriggerFatal") < feed.index("DamageCmd.Attack") and "r.WasTargetKilled" in feed,
          "DECOMP Feed: the fatal read is taken BEFORE the attack, then WasTargetKilled")
    cc = (root / "MegaCrit.Sts2.Core.Commands" / "CreatureCmd.cs").read_text(encoding="utf-8")
    check("RemoveAllPowersAfterDeath()" in cc, "DECOMP: powers are removed after death (why the engine snapshots first)")
    check(".Any((DamageResult r) => r.WasTargetKilled)" in (cards / "Sunder.cs").read_text(encoding="utf-8"),
          "DECOMP Sunder: any kill in the results (no fatal filter)")
    disc = (cards / "Discovery.cs").read_text(encoding="utf-8")
    for frag in ("base.Owner.Character.CardPool.GetUnlockedCards(base.Owner.UnlockState, base.Owner.RunState.CardMultiplayerConstraint)",
                 "base.Owner.RunState.Rng.CombatCardGeneration", "CardSelectCmd.FromChooseACardScreen(choiceContext, cards, base.Owner",
                 "cardModel.SetToFreeThisTurn();", "CardPileCmd.AddGeneratedCardToCombat(cardModel, PileType.Hand, base.Owner)"):
        check(frag in disc, f"DECOMP Discovery: {frag[:60]}")
    check("c.Type == CardType.Attack" in (cards / "InfernalBlade.cs").read_text(encoding="utf-8"), "DECOMP Infernal Blade (attack filter)")
    pw = root / "MegaCrit.Sts2.Core.Models.Powers"
    check("c.Type == CardType.Power" in (pw / "CreativeAiPower.cs").read_text(encoding="utf-8"), "DECOMP Creative AI (power filter)")
    may = (pw / "MayhemPower.cs").read_text(encoding="utf-8")
    check("AfterAutoPrePlayPhaseEntered" in may and "AutoPlayFromDrawPile" in may, "DECOMP Mayhem fires from AfterAutoPrePlayPhaseEntered")
    check("forceExhaust: true" in (cards / "Havoc.cs").read_text(encoding="utf-8"), "DECOMP Havoc: forced exhaust")
    up = (cards / "Uproar.cs").read_text(encoding="utf-8")
    check("StableShuffle(base.Owner.RunState.Rng.Shuffle)" in up and "CardCmd.AutoPlay(choiceContext, cardModel, null)" in up,
          "DECOMP Uproar: StableShuffle + AutoPlay(null)")
    pc = (root / "MegaCrit.Sts2.Core.Commands" / "CardPileCmd.cs").read_text(encoding="utf-8")
    check("item.ExhaustOnNextPlay = forceExhaust;" in pc and "public static async Task ShuffleIfNecessary(" in pc,
          "DECOMP AutoPlayFromDrawPile: ExhaustOnNextPlay per card; ShuffleIfNecessary is public")
    cs = (root / "MegaCrit.Sts2.Core.Commands" / "CardSelectCmd.cs").read_text(encoding="utf-8")
    check("if (cards.Count > 3)" in cs and "ReportSoftlock();" in cs, "DECOMP FromChooseACardScreen: throws above 3, ReportSoftlock on 0")
    cmd = (root / "MegaCrit.Sts2.Core.Commands" / "CardCmd.cs").read_text(encoding="utf-8")
    check("target = card2.Owner.RunState.Rng.CombatTargets.NextItem(combatState.HittableEnemies);" in cmd,
          "DECOMP CardCmd.AutoPlay: a null AnyEnemy target rolls a random hittable enemy")
    am = (root / "MegaCrit.Sts2.Core.Models" / "AbstractModel.cs").read_text(encoding="utf-8")
    check("public virtual Task AfterAutoPrePlayPhaseEntered(PlayerChoiceContext choiceContext, Player player)" in am,
          "DECOMP AbstractModel.AfterAutoPrePlayPhaseEntered")
    check("public void SetToFreeThisTurn()" in (root / "MegaCrit.Sts2.Core.Models" / "CardModel.cs").read_text(encoding="utf-8"),
          "DECOMP CardModel.SetToFreeThisTurn")


def _t_engine() -> None:
    print("the engine: the kill flags, add_random_card, autoplay, the Mayhem fire point, the tags:")
    er = _cs("Engine", "EffectRunner.cs")
    for frag, why in (
            ("bool killedAny = false, killedThisPlay = false;", "the play-local kill flags beside unblockedDealt"),
            ('if (e.When.Kind == "target_killed")', "the gate special-cases the kind"),
            ("gateOpen = killedThisPlay ^ e.When.Negate;", "negate flips it"),
            ("[BN] target_killed gate {(gateOpen ? \"OPEN\" : \"closed\")}", "the gate tag"),
            ("(killed={killedAny}, fatal={killedThisPlay})", "the killed / fatal read in the tag"),
            (".Where(c => c.Powers.All(p => p.ShouldOwnerDeathTriggerFatal())).ToHashSet();", "the Feed snapshot BEFORE the hit"),
            ("if (fatalBefore.Contains(r.Receiver)) killedThisPlay = true;", "any fatal kill in the results (AoE = any)"),
            ("owner.Character.CardPool.GetUnlockedCards(owner.UnlockState, owner.RunState.CardMultiplayerConstraint)", "the class pool"),
            ('!(c is DataCard dc && dc.HasOp("add_random_card"))', "depth-1: never generate an add_random_card card"),
            ("c.CanBeGeneratedInCombat", "CanBeGeneratedInCombat"),
            ("[BN] add_random_card: empty pool, skipped", "the empty-pool guard (never ReportSoftlock)"),
            ("CardFactory.GetDistinctForCombat(owner, pool, chooseOf, rng)", "choose_of offers distinct cards"),
            ("int chooseOf = Math.Min(e.ChooseOf, ForgedCards.ChooseOfMax);", "clamped to 3 (the screen throws above)"),
            ("await CardSelectCmd.FromChooseACardScreen(ctx, offer, owner);", "the choose-a-card screen"),
            ("if (e.FreeThisTurn) c.SetToFreeThisTurn();", "free this turn"),
            ("await AddGenerated(c, pile, owner);", "the shared generate-into-combat path"),
            ("=> CardPileCmd.AddGeneratedCardToCombat(model, pile, owner, CardPilePosition.Random);", "AddGenerated (add_card shares it)"),
            ("[BN] add_random_card {type} x{picked.Count} -> {pile}", "the add_random_card tag"),
            ("free={e.FreeThisTurn}; choose_of={e.ChooseOf}", "free / choose_of in the tag"),
            ("internal const int AutoplayDepthMax = 3;", "the static depth guard (3)"),
            ("[BN] autoplay depth guard hit", "the depth-guard tag"),
            ('!(c is DataCard dc && dc.HasOp("autoplay"))', "draw_random never picks an autoplay card"),
            ('if (top is DataCard dc && dc.HasOp("autoplay"))', "draw_top never auto-plays an autoplay card"),
            (".ToList().StableShuffle(owner.RunState.Rng.Shuffle).FirstOrDefault();", "Uproar's StableShuffle"),
            ("await CardPileCmd.ShuffleIfNecessary(ctx, owner);", "Havoc: ShuffleIfNecessary per card"),
            ("await CardPileCmd.Add(top, PileType.Play);", "Havoc: the top card to the Play pile first"),
            ("c.ExhaustOnNextPlay = true;", "the FORCED exhaust (mandatory)"),
            ("await CardCmd.AutoPlay(ctx, card, target);", "CardCmd.AutoPlay"),
            ("[BN] autoplay {from} '{card.Title}' -> {(target != null ? MonsterName(target) : \"none\")}", "the autoplay tag"),
            ("(depth {AutoplayDepth})", "the depth in the tag")):
        check(frag in er, f"EffectRunner: {why}")
    tr = _cs("Engine", "TriggerRunner.cs")
    check('case "add_random_card":' in tr and 'await EffectRunner.AddRandomCards(e, Math.Max(1, e.Amount), player, ctx, "payload");' in tr
          and 'await EffectRunner.Autoplay(e, Math.Max(1, e.Amount), player, ctx, "payload");' in tr, "TriggerRunner: the payload forms")
    tp = _cs("Powers", "ForgedTriggerPower.cs")
    check("public override async Task AfterAutoPrePlayPhaseEntered(PlayerChoiceContext ctx, Player player)" in tp
          and "if (PlaysCards(t)) return;" in tp and "[BN] mayhem payload from AfterAutoPrePlayPhaseEntered" in tp,
          "ForgedTriggerPower: an autoplay turn_start payload fires from AfterAutoPrePlayPhaseEntered (not AfterPlayerTurnStart)")
    co = _cs("Engine", "Conditions.cs")
    check("target_killed" in _set(co, "public static readonly HashSet<string> Kinds")
          and _set(co, "PlayLocalKinds") == {"target_killed"} and '"target_killed"             => "this kills the enemy",' in co,
          "Conditions: Kinds + PlayLocalKinds + the phrase")
    ch = _cs("Engine", "ForgedCharacters.cs")
    check(".. Conditions.PlayLocalKinds]" in ch, "orb gates reject target_killed (OrbForbiddenConditionKinds)")
    spec = _cs("Engine", "CardSpec.cs")
    check("int ChooseOf = 0," in spec and "bool FreeThisTurn = false)" in spec and "public bool HasOp(string op) =>" in spec,
          "EffectSpec ChooseOf / FreeThisTurn + CardSpec.HasOp")
    dc = _cs("Engine", "DataCard.cs")
    check('case "add_random_card":' in dc and 'case "autoplay":' in dc and "internal bool HasOp(string op) => Spec.HasOp(op);" in dc,
          "DataCard declares the two ops (no var) + HasOp")
    fc = _cs("Engine", "ForgedCards.cs")
    check(set(NEW_OPS) <= _set(fc, "SupportedOps") and set(NEW_OPS) <= _set(fc, "TriggerOps"), "the two ops: supported + payload-legal")
    for frag in ('int chooseOf = e.ContainsKey("choose_of") ? Int(e, "choose_of") : 0;',
                 'bool freeThisTurn = e.ContainsKey("free_this_turn") && e["free_this_turn"].AsBool();',
                 "'choose_of' / 'free_this_turn' only apply to add_random_card", "add_random_card needs a 'pile'",
                 "add_random_card with 'choose_of' adds the ONE card you pick", "add_random_card 'free_this_turn' needs pile 'hand'",
                 "a trigger add_random_card can't use 'choose_of'", "autoplay needs a 'from'",
                 "autoplay 'card_type' only applies with from 'draw_random'",
                 "is only allowed on a turn_start trigger (Creative AI / Mayhem)",
                 "'when:target_killed' can't gate an add_trigger", "a 'when:target_killed' effect needs a 'damage' op earlier",
                 "|| Conditions.PlayLocalKinds.Contains(e.When.Kind)", "'from' only applies to put_back / autoplay",
                 "internal const int AddRandomCardMaxAmount = 2, ChooseOfMin = 2, ChooseOfMax = 3;"):
        check(frag in fc, f"ForgedCards: {frag[:70]}")


CASES = [([{"op": "damage", "amount": 10}, {"op": "gain_max_hp", "amount": 3, "when": KILLED}, {"op": "exhaust"}], "enemy",
          "Deal {Damage} damage.\nGain {MaxHp} Max HP if this kills the enemy.\nExhaust."),
         ([{"op": "damage", "amount": 12}, {"op": "gain_energy", "amount": 2, "when": KILLED}], "all_enemies",
          "Deal {Damage} damage to ALL enemies.\nGain {Energy} energy if this kills an enemy."),
         ([{"op": "damage", "amount": 8}, {"op": "apply_status", "status": "weak", "amount": 2, "when": dict(KILLED, negate=True)}],
          "enemy", "Deal {Damage} damage.\nApply Weak unless this kills the enemy."),
         ([{"op": "add_random_card", "card_type": "attack", "pile": "hand", "free_this_turn": True}, {"op": "exhaust"}], "self",
          "Add a random Attack to your hand. It costs 0 this turn.\nExhaust."),
         ([{"op": "add_random_card", "pile": "discard", "amount": 2}], "self", "Add 2 random cards to your discard pile."),
         ([{"op": "add_random_card", "card_type": "skill", "pile": "hand", "choose_of": 3, "free_this_turn": True}], "self",
          "Choose 1 of 3 random Skills to add to your hand. It costs 0 this turn."),
         ([{"op": "add_random_card", "card_type": "non_attack", "pile": "hand", "amount": 2, "free_this_turn": True}], "self",
          "Add 2 random non-Attack cards to your hand. They cost 0 this turn."),
         ([{"op": "autoplay", "from": "draw_top"}], "self", "Play the top card of your draw pile and Exhaust it."),
         ([{"op": "autoplay", "from": "draw_top", "amount": 2}], "self", "Play the top 2 cards of your draw pile and Exhaust them."),
         ([{"op": "autoplay", "from": "draw_random", "card_type": "attack"}], "self", "Play a random Attack from your draw pile."),
         ([{"op": "autoplay", "from": "draw_random", "amount": 2}], "self", "Play 2 random cards from your draw pile."),
         (_trig("turn_start", [{"op": "add_random_card", "card_type": "power", "pile": "hand"}]), "self",
          "At the start of your turn, add a random Power to your hand."),
         (_trig("turn_start", [{"op": "autoplay", "from": "draw_top"}]), "self",
          "At the start of your turn, play the top card of your draw pile and Exhaust it.")]
C_FRAGMENTS = ('string phrase = e.When.Kind == "target_killed" && target != TargetType.AnyEnemy\n                    ? "this kills an enemy" : Conditions.Phrase(e.When);',
               'case "add_random_card":  parts.Add(AddRandomCardSentence(e, capitalize: true)); break;',
               'case "autoplay":         parts.Add(AutoplaySentence(e, capitalize: true)); break;',
               '"add_random_card" => AddRandomCardSentence(e, capitalize: false),',
               '"autoplay"      => AutoplaySentence(e, capitalize: false),',
               'string body = choose ? $"{(capitalize ? "Choose" : "choose")} 1 of {e.ChooseOf} random {RandomCardNoun(e.CardKind, true)} to add to your {pile}"',
               ': n > 1 ? $"{(capitalize ? "Add" : "add")} {n} random {RandomCardNoun(e.CardKind, true)} to your {pile}"',
               ': $"{(capitalize ? "Add" : "add")} a random {RandomCardNoun(e.CardKind, false)} to your {pile}";',
               'if (e.FreeThisTurn) body += !choose && n > 1 ? ". They cost 0 this turn" : ". It costs 0 this turn";',
               '? (n > 1 ? $"{verb} {n} random {RandomCardNoun(e.CardKind, true)} from your draw pile"',
               ': $"{verb} a random {RandomCardNoun(e.CardKind, false)} from your draw pile")',
               ': (n > 1 ? $"{verb} the top {n} cards of your draw pile and Exhaust them"',
               ': $"{verb} the top card of your draw pile and Exhaust it");',
               '"non_attack" => plural ? "non-Attack cards" : "non-Attack card",')


def _t_rules_and_describe() -> None:
    print("validator + describe (Python literal == the C# fragment written by hand):")
    ok = [_atk([{"op": "damage", "amount": 10}, {"op": "gain_max_hp", "amount": 3, "when": KILLED}, {"op": "exhaust"}], rarity="rare"),
          _atk([{"op": "damage", "amount": 12}, {"op": "gain_energy", "amount": 2, "when": KILLED}], target="all_enemies", cost=3),
          _atk([{"op": "damage", "amount": 6}, {"op": "draw", "amount": 1, "when": KILLED}], target="random_enemy"),
          _atk([{"op": "damage", "amount": 8}, {"op": "apply_status", "status": "weak", "amount": 2, "when": dict(KILLED, negate=True)}]),
          _card([{"op": "add_random_card", "card_type": "skill", "pile": "hand", "choose_of": 3, "free_this_turn": True}, {"op": "exhaust"}]),
          _card([{"op": "add_random_card", "card_type": "attack", "pile": "hand", "free_this_turn": True}, {"op": "exhaust"}]),
          _card([{"op": "block", "amount": 4}, {"op": "add_random_card", "pile": "discard", "amount": 2}], rarity="common"),
          _card([{"op": "add_random_card", "pile": "draw", "card_type": "non_attack"}]),
          _card([{"op": "autoplay", "from": "draw_top"}], rarity="common"),
          _card([{"op": "autoplay", "from": "draw_top", "amount": 2}], cost=2),
          _atk([{"op": "damage", "amount": 5, "hits": 2}, {"op": "autoplay", "from": "draw_random", "card_type": "attack"}], cost=2),
          _pow(_trig("turn_start", [{"op": "add_random_card", "card_type": "power", "pile": "hand"}]), cost=3),
          _pow(_trig("turn_start", [{"op": "add_random_card", "card_type": "attack", "pile": "hand", "free_this_turn": True}]), cost=3),
          _pow(_trig("turn_start", [{"op": "autoplay", "from": "draw_top"}]), cost=2),
          _pow(_trig("turn_start", [{"op": "autoplay", "from": "draw_random", "card_type": "attack"}]), cost=2)]
    for c in ok:
        check(not _errs(c), f"validates: {json.dumps(c['effects'])} -> {_errs(c)}")
    bad = [(_atk([{"op": "gain_max_hp", "amount": 3, "when": KILLED}, {"op": "damage", "amount": 10}]), "earlier"),
           (_card([{"op": "block", "amount": 5, "when": KILLED}]), "earlier"),
           (_upgrade_order_bad(), "earlier"),
           (_pow([{"op": "add_trigger", "trigger": "turn_start", "when": KILLED, "effects": [{"op": "block", "amount": 2}]}]), ""),
           (_pow(_trig("on_card_played", [{"op": "block", "amount": 2}]) + [{"op": "draw", "amount": 1, "when": KILLED}]), ""),
           (_card([{"op": "add_random_card"}]), "pile"),
           (_card([{"op": "add_random_card", "pile": "exhaust"}]), ""),
           (_card([{"op": "add_random_card", "pile": "hand", "amount": 3}]), ""),
           (_card([{"op": "add_random_card", "pile": "hand", "choose_of": 4}]), ""),
           (_card([{"op": "add_random_card", "pile": "hand", "choose_of": 3, "amount": 2}]), ""),
           (_card([{"op": "add_random_card", "pile": "discard", "free_this_turn": True}]), ""),
           (_card([{"op": "add_random_card", "pile": "hand", "card_type": "status"}]), ""),
           (_card([{"op": "add_random_card", "pile": "hand"}, {"op": "add_random_card", "pile": "discard"}]), "at most one"),
           (_card([{"op": "draw", "amount": 1, "choose_of": 3}]), ""),
           (_card([{"op": "draw", "amount": 1, "free_this_turn": True}]), ""),
           (_card([{"op": "autoplay"}]), ""),
           (_card([{"op": "autoplay", "from": "hand"}]), ""),
           (_card([{"op": "autoplay", "from": "draw_top", "card_type": "attack"}]), ""),
           (_card([{"op": "autoplay", "from": "draw_top", "amount": 3}]), ""),
           (_card([{"op": "autoplay", "from": "draw_top"}, {"op": "autoplay", "from": "draw_random"}]), "at most one"),
           (_card([{"op": "draw", "amount": 1, "from": "draw_top"}]), ""),
           (_pow(_trig("on_exhaust", [{"op": "autoplay", "from": "draw_top"}])), "turn_start"),
           (_pow(_trig("on_card_played", [{"op": "add_random_card", "pile": "hand"}])), "turn_start"),
           (_pow(_trig("turn_start", [{"op": "add_random_card", "pile": "hand", "choose_of": 3}])), ""),
           (_pow(_trig("turn_start", [{"op": "block", "amount": 2, "card_type": "attack"}])), "")]
    for c, frag in bad:
        e = _errs(c)
        check(bool(e) and any(frag in x for x in e), f"rejected ({frag or 'any'}): {json.dumps(c['effects'])} -> {e}")
    v = _V
    feed = v._score_effect({"op": "gain_max_hp", "amount": 3, "when": KILLED})
    sunder = v._score_effect({"op": "gain_energy", "amount": 2, "when": KILLED})
    check(abs(feed - 3 * 4.0 * 0.75) < 1e-9 and abs(sunder - 2 * 6.0 * 0.5) < 1e-9,
          f"priced: a kill-gated gain_max_hp is Feed-exact (0.75), other kill payoffs 0.5 (got {feed}, {sunder})")
    check(v._score_effect({"op": "add_random_card", "pile": "hand", "choose_of": 3, "free_this_turn": True}) == 4.0 + 2.0 + 4.0
          and v._score_effect({"op": "add_random_card", "pile": "discard", "amount": 2}) == 4.0
          and v._score_effect({"op": "autoplay", "from": "draw_top"}) == 4.0
          and v._score_effect({"op": "autoplay", "from": "draw_random", "card_type": "attack"}) == 5.0,
          "priced: add_random_card 4 / card in hand (+1 per extra option, +4 free), autoplay 4 (top) / 5 (typed random)")
    for effects, target, want in CASES:
        got = cardgen.describe(effects, target)
        check(got == want, f"describe {got!r} == {want!r}")
    src = _cs("Engine", "ForgedCards.cs")
    for frag in C_FRAGMENTS:
        check(frag in src, f"C# Describe fragment: {frag}")
    for e, want in (({"op": "add_random_card", "card_type": "skill", "pile": "hand", "choose_of": 3, "free_this_turn": True},
                     'new EffectSpec("add_random_card", 0, Pile: "hand", CardKind: "skill", ChooseOf: 3, FreeThisTurn: true)'),
                    ({"op": "add_random_card", "pile": "discard", "amount": 2}, 'new EffectSpec("add_random_card", 2, Pile: "discard")'),
                    ({"op": "autoplay", "from": "draw_top"}, 'new EffectSpec("autoplay", 0, From: "draw_top")'),
                    ({"op": "autoplay", "from": "draw_random", "card_type": "attack", "amount": 1},
                     'new EffectSpec("autoplay", 1, From: "draw_random", CardKind: "attack")'),
                    ({"op": "gain_max_hp", "amount": 3, "when": KILLED},
                     'new EffectSpec("gain_max_hp", 3, When: new Condition("target_killed", 0, null, false))')):
        got = cardgen.effect_literal(e)
        check(got == want, f"effect_literal {got!r} == {want!r}")
    check(cardgen.cond_phrase(KILLED) == "this kills the enemy", "cond_phrase target_killed")


def _upgrade_order_bad():
    return _atk([{"op": "damage", "amount": 10}, {"op": "gain_energy", "amount": 1, "when": KILLED}],
                upgrade=[{"op": "gain_energy", "amount": 1, "when": KILLED}, {"op": "damage", "amount": 13}])


def _t_contract() -> None:
    print("contract surfaces:")
    schema = json.loads(CARD_SCHEMA.read_text(encoding="utf-8"))
    eff = schema["$defs"]["effect"]
    check(set(NEW_OPS) <= set(eff["properties"]["op"]["enum"]), "schema: op enum += add_random_card / autoplay")
    check(eff["properties"]["choose_of"]["minimum"] == 2 and eff["properties"]["choose_of"]["maximum"] == 3
          and eff["properties"]["free_this_turn"]["type"] == "boolean"
          and {"draw_top", "draw_random"} <= set(eff["properties"]["from"]["enum"]), "schema: choose_of / free_this_turn / from")
    rules = json.dumps(eff["allOf"])
    check('"op": {"const": "add_random_card"}' in rules and '"op": {"const": "autoplay"}' in rules
          and '"op": {"enum": ["put_back", "autoplay"]}' in rules, "schema: the two op rules + from's owners")
    te = schema["$defs"]["triggerEffect"]
    check(set(NEW_OPS) <= set(te["properties"]["op"]["enum"]) and "choose_of" not in te["properties"]
          and {"card_type", "free_this_turn", "from"} <= set(te["properties"]), "schema: the payload forms (no choose_of)")
    check("target_killed" in schema["$defs"]["condition"]["properties"]["kind"]["enum"], "schema: condition kind target_killed")
    vocab = paths.VOCABULARY.read_text(encoding="utf-8")
    idx = gate.vocab_index(vocab)
    for t in NEW_TOKENS:
        check(vocab.count(f"| `{t}`") == 1 and f"`{t}`" in idx, f"VOCABULARY: ONE {t} row (+ its index name)")
    check("v69, `turn_start`\n  only: `add_random_card` (Creative AI) and `autoplay` (Mayhem)" in vocab, "VOCABULARY: the payload prose")
    check(set(NEW_OPS) <= set(gate.GATED_OP_ORDER), "gate: both ops gated (no card core cost)")
    check(gate.FIELD_UNITS["choose_of"] == ("add_random_card",) and gate.FIELD_UNITS["free_this_turn"] == ("add_random_card",)
          and "autoplay" in gate.FIELD_UNITS["from"] and "add_random_card" in gate.FIELD_UNITS["pile"]
          and {"add_random_card", "autoplay"} <= set(gate.FIELD_UNITS["card_type"]), "gate.FIELD_UNITS: the new fields")
    check("target_killed" in {k for k, _ in coverage.WHEN_MENU_V2}, "coverage: WHEN_MENU_V2 += target_killed")
    plain = census.walk_card(_atk([{"op": "damage", "amount": 6}]))
    kc = census.walk_card(_atk([{"op": "damage", "amount": 6}, {"op": "gain_energy", "amount": 1, "when": KILLED}]))
    check(coverage.CENSUS_DETECTOR["target_killed"](kc) and not coverage.CENSUS_DETECTOR["target_killed"](plain), "the target_killed detector")
    feats = {f.id: f for f in featured.FEATURED_MENU}
    check({"kill_payoff", "discovery", "havoc_play"} <= set(feats), "featured: the three entries")
    check(feats["kill_payoff"].detect(kc) and feats["discovery"].detect(census.walk_card(_card([{"op": "add_random_card", "pile": "hand"}])))
          and feats["havoc_play"].detect(census.walk_card(_pow(_trig("turn_start", [{"op": "autoplay", "from": "draw_top"}]))))
          and not any(feats[k].detect(plain) for k in ("kill_payoff", "discovery", "havoc_play")),
          "featured: the detectors (a Mayhem payload counts)")
    check(set(NEW_OPS) <= set(harness_v2._PREFERRED_OPS) and "target_killed" in harness_v2._PREFERRED_CONDITIONS,
          "harness_v2: preferred ops + condition")
    check("target_killed" in cf._ORB_FORBIDDEN_CONDITION_KINDS and "target_killed" not in cf._ORB_CONDITION_KINDS,
          "class_forge: orb gates never read target_killed")
    check(cf._cond_uptime(KILLED, {"share": 0.0, "start": 0, "pool": 0}) == 0.35, "class_forge: _cond_uptime target_killed")
    src = pathlib.Path(cf.__file__).read_text(encoding="utf-8")
    check("v69: `add_random_card` adds RANDOM cards from your own pool \\\n(Discovery: choose 1 of 3, free this turn)." in src
          and "(6) v69: `autoplay` plays the top card of your \\\ndraw pile (Havoc; it Exhausts) or a random Attack from it (Uproar)." in src
          and '`target_killed` (after the damage: \\"if this kills the enemy\\")' in src, "class_forge: the three short pitch sentences")
    sec = {k: toks for _h, toks, _kind, k, _p in cf._PRUNABLE_SECTIONS}
    check("add_random_card" in sec["tokens"] and "autoplay" in sec["discard"], "class_forge: the pitch sections keep for the new tokens")
    toks = bridges.card_tokens(_atk([{"op": "damage", "amount": 6}, {"op": "gain_energy", "amount": 1, "when": KILLED},
                                     {"op": "autoplay", "from": "draw_top"}]))
    check({"target_killed", "autoplay"} <= toks, "bridges: the new tokens surface")
    arch = {a["id"]: a for a in json.loads((DATA / "archetypes.json").read_text(encoding="utf-8"))["archetypes"]}
    for aid, tok, gap in (("reaper_lifesteal", "target_killed", 71), ("horde_breaker", "target_killed", 71),
                          ("iron_regrowth", "target_killed", 71), ("token_conjurer", "add_random_card", 72),
                          ("fleeting_flux", "add_random_card", 72), ("madness_discard", "autoplay", 73), ("big_energy", "autoplay", 73)):
        a = arch[aid]
        check(tok in a["vocabulary"]["ops"] and f"VOCABULARY_GAPS#{gap}" in a["gap_refs"] and a["buildable"] is True
              and "(v69)" in a.get("build_notes", ""), f"{aid} claims {tok} (#{gap}, v69 note)")
    check("chaos_havoc" not in arch, "no new chaos_havoc archetype this phase")
    pool = json.loads((DATA / "exemplar_pool.json").read_text(encoding="utf-8"))["exemplars"]
    v = harness_v2.exemplar_validator()
    used, forms = set(), set()
    for e in pool:
        flat = json.dumps(e["card"])
        hit = set(NEW_TOKENS) & bridges.card_tokens(e["card"])
        for f in ('"choose_of": 3', '"free_this_turn": true', '"pile": "discard", "amount": 2', '"from": "draw_top"',
                  '"from": "draw_random"', '"negate": true', '"target": "all_enemies"'):
            if f in flat and hit:
                forms.add(f)
        if '"trigger": "turn_start"' in flat and hit:
            forms.add("payload:" + ",".join(sorted(hit)))
        if not hit:
            continue
        used |= hit
        r = v.validate(dict(e["card"]))
        check(r.ok, f"exemplar {e['card']['id']} validates: {r.errors}")
        check("needs" not in e, f"exemplar {e['card']['id']} is not class-only")
    check(set(NEW_TOKENS) <= used, f"exemplars cover every new token (got {sorted(used)})")
    check(len(forms) >= 9, f"exemplars show every form (choose_of / free / discard x2 / top / random / negated / AoE / both payloads): {sorted(forms)}")
    heur = (paths.VOCABULARY.parent / "DESIGN_HEURISTICS.md").read_text(encoding="utf-8")
    check(heur.count("(v69") >= 7 and "gap #37" in heur.split("archetype-note: madness_discard", 1)[1].split("archetype-note:", 1)[0],
          "DESIGN_HEURISTICS: the v69 notes (autoplay policy vs gap #37 on madness_discard)")
    gaps_md = (REPO / "VOCABULARY_GAPS.md").read_text(encoding="utf-8")
    for n, nxt in ((71, 72), (72, 73), (73, 74)):
        entry = gaps_md.split(f"### {n}.", 1)[1].split(f"### {nxt}.", 1)[0]
        check("**Status:** **done (2026-10-04, vocab v69, Phase BN)**" in entry, f"gap #{n} is done (v69)")
    js = (REPO / "web" / "static" / "render.js").read_text(encoding="utf-8")
    for frag in ('case "target_killed": return "this kills the enemy";', 'case "add_random_card": {', 'case "autoplay": {',
                 '"Play the top card of your draw pile and Exhaust it"', 'function randomNoun(kind, plural)'):
        check(frag in js, f"render.js: {frag[:60]}")
    plan = (REPO / "docs" / "plans" / "VOCAB_EXPANSION_6_PLAN.md").read_text(encoding="utf-8")
    check("**Findings (BN" in plan and "**Phase BN" in plan and "### Phase BN — On-kill, random generation, auto-play (v69" in plan
          and "| BN | #71–#73 | v69 |" in plan, "the plan records the BN findings + status line (v69)")


def _t_tester() -> None:
    print("the tester (validate-only path):")
    p = TESTER_DIR / "build_tester.py"
    check(p.exists(), "tests/gaptest-bn/build_tester.py exists")
    spec = importlib.util.spec_from_file_location("bn_tester", p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    check(mod.validate(verbose=True) == 0, "every tester card validates")
    types = [c["type"] for c in mod.CARDS if c["rarity"] != "basic"]
    check(types.count("attack") >= 3 and types.count("skill") >= 3 and types.count("power") >= 1,
          "pool: >= 3 non-basic Attacks + Skills and >= 1 Power (the merchant stall)")
    check(90 <= mod.CHARACTER["max_hp"] <= 110, "max HP ~100")
    flat = json.dumps(mod.CARDS)
    for need in ('"gain_max_hp", "amount": 3, "when": {"kind": "target_killed"}', '"target": "all_enemies"',
                 '"negate": true', '"choose_of": 3', '"card_type": "attack", "pile": "hand", "free_this_turn": true',
                 '"pile": "discard", "amount": 2', '"from": "draw_top"', '"from": "draw_random", "card_type": "attack"',
                 '"trigger": "turn_start", "effects": [{"op": "add_random_card", "card_type": "power"',
                 '"trigger": "turn_start", "effects": [{"op": "autoplay"', '"trigger": "on_card_generated"', '"status": "strength"'):
        check(need in flat, f"the tester exercises {need}")
    text = p.read_text(encoding="utf-8")
    check("--validate-only" in text and "--character class4" in text and "GAPTESTBN1 GAPTESTBN2" in text
          and "Auto-selected 1 card(s)" in text and "[BN] mayhem payload from AfterAutoPrePlayPhaseEntered" in text,
          "the docstring is the complete smoke recipe")


def _t_smoke_record() -> None:
    print("the saved AutoSlay tag greps (TEST_AUDIT_2026-10 §7):")
    files = [TESTER_DIR / f"godot_BN_tags_{s}.txt" for s in SMOKE_SEEDS]
    seen = ""
    for p in files:
        assert p.exists(), f"missing smoke record {p}"
        txt = p.read_text(encoding="utf-8")
        check("[BN]" in txt, f"{p.name} holds [BN] tags")
        check("mod exceptions: 0" in txt and "Localization formatting errors: 0" in txt
              and "BlankTheSpire stack frames: 0" in txt, f"{p.name} records a clean run")
        seen += txt
    for t in TAGS:
        check(t in seen, f"the smoke fired '{t}'")


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


def test_phase_bn_all() -> None:
    global _PASS, _FAIL
    _PASS = _FAIL = 0
    assert main() == 0, f"{_FAIL} Phase BN check(s) failed - see the FAIL lines above"


if __name__ == "__main__":
    sys.exit(main())
