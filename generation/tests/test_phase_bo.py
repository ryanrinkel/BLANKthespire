"""Phase BO — self-routing recursion, put-back, draw-pile tutor, on_shuffle, grant_keyword (VOCAB_EXPANSION_6_PLAN,
gaps #74 / #75, vocab v66) — offline. Run:  uv run python -m tests.test_phase_bo  (from generation/)

Pins: the stamp; verify-first against the game sources (Bolas / Particle Wall / ReboundPower / the AbstractModel hook
signatures / CardPileCmd.Shuffle -> AfterShuffle / CardSelectCmd.FromCombatPile on the draw pile / CardCmd.ApplyKeyword +
ApplySingleTurnSly); the engine wiring (the three DataCard pile overrides with their guards + tags, the custom picker
prompts via CardLoc ExtraLoc, EffectRunner put_back / shuffle_hand / grant_keyword / the draw-pile tutor / exhaust from
the draw pile, ForgedTriggerPower.AfterShuffle); the validator rules on both sides; the describe byte-match (Python
literals asserted, the C# fragments grepped); the contract surfaces (schema, VOCABULARY rows, gate order + field units,
census, coverage, featured, harness_v2, archetypes, exemplars, heuristics, gap log, render.js, the pitch sentences); the
tester's validate-only path; the saved AutoSlay tag greps under tests/gaptest-bo/ when present ("smoke pending"
otherwise); and prints the rule-0.9 readings.
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
TESTER_DIR = pathlib.Path(__file__).parent / "gaptest-bo"
SMOKE_SEEDS = ("GAPTESTBO1", "GAPTESTBO2")
MODREF = pathlib.Path(r"C:/Users/ryanr/Desktop/NOVOGODOT/BLANKthespire/_modref")

FLAG_OPS = ("return_to_hand", "to_draw_top", "return_next_turn")
NEW_OPS = FLAG_OPS + ("put_back", "shuffle_hand", "grant_keyword")
NEW_TOKENS = NEW_OPS + ("on_shuffle",)
TAGS = ("[BO] return_to_hand '", "[BO] to_draw_top '", "[BO] return_next_turn '", "[BO] put_back hand '",
        "[BO] put_back discard '", "[BO] retrieve draw [attack] '", "[BO] retrieve draw [skill] '",
        "[BO] exhaust_card draw '", "[BO] on_shuffle fired", "[BO] grant_keyword sly -> '",
        "[BO] grant_keyword retain -> '", "[BO] grant_keyword ethereal -> '", "[BO] shuffle_hand ")


def check(cond: bool, msg: str) -> None:
    global _PASS, _FAIL
    if cond:
        _PASS += 1
    else:
        _FAIL += 1
        print(f"  FAIL: {msg}")


def _cs(*parts: str) -> str:
    return (MOD_CODE.joinpath(*parts)).read_text(encoding="utf-8").replace("\r\n", "\n")


def _card(effects, rarity="uncommon", cost=1, ctype="skill", target="self", upgrade=None, up_cost=None):
    c = {"id": "bo_t", "name": "BO", "type": ctype, "rarity": rarity, "cost": cost, "target": target, "effects": effects}
    if upgrade is not None or up_cost is not None:
        c["upgrade"] = {"effects": upgrade if upgrade is not None else effects}
        if up_cost is not None:
            c["upgrade"]["cost"] = up_cost
    return c


def _atk(effects, **kw):
    kw.setdefault("ctype", "attack")
    kw.setdefault("target", "enemy")
    return _card(effects, **kw)


def _gk(kw, ck=None, **extra):
    e = {"op": "grant_keyword", "keyword": kw, "cards": "choose"}
    if ck:
        e["card_type"] = ck
    e.update(extra)
    return e


def _pb(frm, **extra):
    e = {"op": "put_back", "from": frm, "cards": "choose"}
    e.update(extra)
    return e


def _tut(cards, ck=None, **extra):
    e = {"op": "retrieve_card", "pile": "draw", "cards": cards}
    if ck:
        e["card_type"] = ck
    e.update(extra)
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


def _set(src: str, name: str) -> set[str]:
    m = re.search(name + r"\s*=\s*\[(.*?)\];", src, re.S)
    return set(re.findall(r'"(\w+)"', m.group(1))) if m else set()


def test_version() -> None:
    print("Phase BO vocab stamp is at least 66 (Python + C#):")
    check(bts1.VOCAB_VERSION >= 66, f"bts1.VOCAB_VERSION >= 66, got {bts1.VOCAB_VERSION}")
    fc = _cs("Engine", "ForgedCards.cs")
    m = re.search(r"public const int VocabVersion = (\d+);", fc)
    check(m is not None and int(m.group(1)) >= 66, f"ForgedCards.VocabVersion >= 66, got {m and m.group(1)}")
    check(m is not None and bts1.VOCAB_VERSION <= int(m.group(1)), "bts1.VOCAB_VERSION <= ForgedCards.VocabVersion")
    check("66: Phase BO" in fc and all(f"`{t}`" in fc for t in ("return_to_hand", "to_draw_top", "return_next_turn",
                                                                  "shuffle_hand", "on_shuffle")),
          "ForgedCards.cs comment names Phase BO + the tokens")
    check("66: Phase BO" in pathlib.Path(bts1.__file__).read_text(encoding="utf-8"), "bts1.py records the v66 entry")


def _t_verify_first() -> None:
    print("verify-first against the game sources (rule 0.6):")
    root = MODREF / "decomp_full"
    if not root.exists():
        print("  (decomp not on this machine — skipped, informational)")
        return
    am = (root / "MegaCrit.Sts2.Core.Models" / "AbstractModel.cs").read_text(encoding="utf-8")
    for sig in ("public virtual (PileType, CardPilePosition) ModifyCardPlayResultPileTypeAndPosition(CardModel card, "
                "bool isAutoPlay, ResourceInfo resources, PileType pileType, CardPilePosition position)",
                "public virtual Task BeforeHandDraw(Player player, PlayerChoiceContext choiceContext, ICombatState combatState)",
                "public virtual Task AfterShuffle(PlayerChoiceContext choiceContext, Player shuffler)"):
        check(sig in am, f"DECOMP AbstractModel: {sig[:70]}")
    cm = (root / "MegaCrit.Sts2.Core.Models" / "CardModel.cs").read_text(encoding="utf-8")
    check("protected virtual PileType GetResultPileTypeForCardPlay()" in cm, "DECOMP: GetResultPileTypeForCardPlay is protected virtual")
    check("Hook.ModifyCardPlayResultPileTypeAndPosition(combatState, this, isAutoPlay, resources, GetResultPileTypeForCardPlay(), "
          "CardPilePosition.Bottom" in cm, "DECOMP: OnPlayWrapper runs the result pile through the listener hook")
    cards = root / "MegaCrit.Sts2.Core.Models.Cards"
    bolas = (cards / "Bolas.cs").read_text(encoding="utf-8")
    check("e.HappenedLastPlayerTurn(base.Owner) && e.CardPlay.Card == this" in bolas
          and "await CardPileCmd.Add(this, PileType.Hand);" in bolas, "DECOMP: Bolas.BeforeHandDraw (the copied recipe)")
    pw = (cards / "ParticleWall.cs").read_text(encoding="utf-8")
    check("resultPileTypeForCardPlay != PileType.Discard" in pw and "return PileType.Hand;" in pw,
          "DECOMP: ParticleWall turns only a Discard result into Hand")
    rb = (root / "MegaCrit.Sts2.Core.Models.Powers" / "ReboundPower.cs").read_text(encoding="utf-8")
    check("return (PileType.Draw, CardPilePosition.Top);" in rb, "DECOMP: ReboundPower's (Draw, Top)")
    cmds = root / "MegaCrit.Sts2.Core.Commands"
    pc = (cmds / "CardPileCmd.cs").read_text(encoding="utf-8")
    check("await Hook.AfterShuffle(player.Creature.CombatState, choiceContext, player);" in pc,
          "DECOMP: CardPileCmd.Shuffle raises AfterShuffle")
    sc = (cmds / "CardSelectCmd.cs").read_text(encoding="utf-8")
    check("public static async Task<IEnumerable<CardModel>> FromCombatPile(PlayerChoiceContext context, CardPile pile, "
          "Player player, CardSelectorPrefs prefs, Func<CardModel, bool> filter)" in sc
          and "if (pile.Type == PileType.Draw)" in sc, "DECOMP: FromCombatPile takes the DRAW pile (+ a filter)")
    cc = (cmds / "CardCmd.cs").read_text(encoding="utf-8")
    check("public static void ApplyKeyword(CardModel card, params CardKeyword[] keywords)" in cc
          and "public static void ApplySingleTurnSly(CardModel card)" in cc, "DECOMP: ApplyKeyword / ApplySingleTurnSly")
    check("await CardPileCmd.Add(card, PileType.Exhaust" in cc, "DECOMP: CardCmd.Exhaust moves from ANY pile")


def _t_engine() -> None:
    print("the engine: the pile overrides + guards, the pickers, AfterShuffle, the tags:")
    dc = _cs("Engine", "DataCard.cs")
    for frag, why in (
            ("if (Spec.HasPurge) return PileType.None;", "purge's None keeps precedence"),
            ("if (Spec.HasReturnToHand && pile == PileType.Discard)", "return_to_hand: only a Discard result -> Hand"),
            ("$\"[BO] return_to_hand '{Spec.Title ?? Spec.Id}' (Discard -> Hand).\"", "the [BO] return_to_hand tag"),
            ("public override (PileType, CardPilePosition) ModifyCardPlayResultPileTypeAndPosition(CardModel card, bool isAutoPlay,",
             "the to_draw_top override (card-level hook)"),
            ("if (card == this && Spec.HasToDrawTop && pileType == PileType.Discard)", "to_draw_top: this card, Discard only"),
            ("return (PileType.Draw, CardPilePosition.Top);", "to_draw_top -> (Draw, Top)"),
            ("$\"[BO] to_draw_top '{Spec.Title ?? Spec.Id}'", "the [BO] to_draw_top tag"),
            ("public override async Task BeforeHandDraw(Player player, PlayerChoiceContext choiceContext, ICombatState combatState)",
             "the return_next_turn override (Bolas)"),
            ("CombatManager.Instance.History.CardPlaysFinished.Any(e => e.HappenedLastPlayerTurn(Owner) && e.CardPlay.Card == this)",
             "return_next_turn: the Bolas history read"),
            ("if (from is not (PileType.Discard or PileType.Draw))", "return_next_turn: never from Exhaust / purged / removed"),
            ("await CardPileCmd.Add(this, PileType.Hand);", "return_next_turn -> Hand"),
            ("$\"[BO] return_next_turn '{Spec.Title ?? Spec.Id}' <- {from}.\"", "the [BO] return_next_turn tag"),
            ("new CardLoc(Spec.Title, Spec.Description ?? \"\", PickPrompts())", "the custom prompts ride CardLoc ExtraLoc"),
            ("list.Insert(0, (\"selectionScreenPrompt\", list[0].Item2));", "the first prompt also fills selectionScreenPrompt")):
        check(frag in dc, f"DataCard: {why}")
    spec = _cs("Engine", "CardSpec.cs")
    check("string? From = null," in spec and "string? Keyword = null)" in spec, "EffectSpec.From / Keyword")
    check('public bool HasReturnToHand => Effects.Any(e => e.Op == "return_to_hand");' in spec, "CardSpec.HasReturnToHand")
    er = _cs("Engine", "EffectRunner.cs")
    for frag, why in (
            ('PileType pileType = e.Pile switch { "exhaust" => PileType.Exhaust, "draw" => PileType.Draw, _ => PileType.Discard };',
             "retrieve_card reads the DRAW pile"),
            ("Func<CardModel, bool> ok = c => Retrievable(c) && HandKindMatches(c, e.CardKind);",
             "the tutor keeps Retrievable AND HandKindMatches"),
            ("$\"[BO] retrieve draw [{e.CardKind ?? \"any\"}] '{c.Title}' ({e.Cards ?? \"random\"}).\"", "the [BO] retrieve tag"),
            ("await CardPileCmd.Add(chosen, PileType.Draw, CardPilePosition.Top);", "put_back -> draw TOP"),
            ("$\"[BO] put_back {from} '{chosen.Title}' -> draw top.\"", "the [BO] put_back tag"),
            ("await CardPileCmd.Shuffle(ctx, owner);", "shuffle_hand uses the game's Shuffle (AfterShuffle fires)"),
            ("$\"[BO] shuffle_hand {hand.Count} cards", "the [BO] shuffle_hand tag"),
            ('"sly"      => !c.IsSlyThisTurn && !c.Keywords.Contains(CardKeyword.Sly),', "grant_keyword skips cards that already have it"),
            ("case \"sly\":      CardCmd.ApplySingleTurnSly(chosen); break;", "sly = ApplySingleTurnSly"),
            ("case \"ethereal\": CardCmd.ApplyKeyword(chosen, CardKeyword.Ethereal); break;", "ethereal = ApplyKeyword"),
            ("default:         CardCmd.ApplyKeyword(chosen, CardKeyword.Retain); break;", "retain = ApplyKeyword"),
            ("$\"[BO] grant_keyword {kw} -> '{chosen.Title}'.\"", "the [BO] grant_keyword tag"),
            ('if (e.Pile == "draw") { await ExhaustFromDraw(e, n, ctx, owner); return; }', "exhaust_card pile draw"),
            ("await CardCmd.Exhaust(ctx, c);   // one at a time (the game's own rule) -> Hook.AfterCardExhausted per card",
             "exhaust from the draw pile through CardCmd.Exhaust"),
            ("$\"[BO] exhaust_card draw '{c.Title}'", "the [BO] exhaust_card draw tag"),
            ("var ls = new LocString(\"cards\", card.Id.Entry + \".\" + key);", "BoPrompt reads the ExtraLoc key"),
            ("return ls.Exists() ? ls : fallback;", "BoPrompt falls back (never the throwing SelectionScreenPrompt)")):
        check(frag in er, f"EffectRunner: {why}")
    tp = _cs("Powers", "ForgedTriggerPower.cs")
    check("public override async Task AfterShuffle(PlayerChoiceContext ctx, Player shuffler)" in tp
          and 'await FireReactive("on_shuffle", ctx);' in tp, "ForgedTriggerPower.AfterShuffle -> FireReactive")
    check("[BO] on_shuffle fired" in tp and '"on_shuffle" => "On Shuffle"' in tp, "the [BO] on_shuffle tag + power title")
    body = tp.split("public override async Task AfterShuffle", 1)[1].split("\n    }\n", 1)[0]
    check("_combatCtx = ctx" not in body, "AfterShuffle never stores its (possibly hand-draw) ctx")
    fc = _cs("Engine", "ForgedCards.cs")
    check(set(NEW_OPS) <= _set(fc, "SupportedOps"), "SupportedOps += the six ops")
    check(not (set(NEW_OPS) & _set(fc, "TriggerOps")), "the six ops are card-only (not in TriggerOps)")
    check("on_shuffle" in _set(fc, "SupportedTriggers") and "on_shuffle" in _set(fc, "MultiFireTriggers")
          and "on_shuffle" in _set(fc, "OncePerCombatTriggers"),
          "on_shuffle: supported, multi-fire, once_per_* (and so every_n / this_turn) eligible")
    check(_set(fc, "RetrievePiles") == {"discard", "exhaust", "draw"}, "RetrievePiles += draw")
    check(not (_set(fc, "KeywordOps") & set(NEW_OPS)), "C# KeywordOps unchanged (the flags are not CardKeywords)")
    for frag in ('"a card routes itself ONE way: \'{flags[0]}\' and \'{flags[1]}\' can\'t share a card."',
                 "can't share a card with 'exhaust' / 'purge'",
                 "'return_to_hand' can't share a card with 'draw' / 'gain_energy'",
                 "'to_draw_top' can't share a card with 'corruption'",
                 "are not allowed on a Power (it never reaches a pile)",
                 "'return_to_hand' needs a card that costs 1+ energy",
                 "put_back needs a 'from' pile", "grant_keyword needs a 'keyword'",
                 "exhaust_card from the draw pile takes 'cards' choose or random only"):
        check(frag in fc, f"ForgedCards.Validate: {frag[:70]}")


CASES = [([{"op": "block", "amount": 9}, {"op": "return_to_hand"}], "self",
          "Gain {Block} Block.\nReturns to your hand after you play it."),
         ([{"op": "damage", "amount": 6}, {"op": "to_draw_top"}], "enemy",
          "Deal {Damage} damage.\nGoes on top of your draw pile after you play it."),
         ([{"op": "damage", "amount": 3}, {"op": "return_next_turn"}], "enemy",
          "Deal {Damage} damage.\nAt the start of your next turn, return this to your hand."),
         ([{"op": "draw", "amount": 2}, _pb("hand")], "self",
          "Draw {Cards} card(s).\nPut a card from your hand on top of your draw pile."),
         ([{"op": "damage", "amount": 9}, _pb("discard")], "enemy",
          "Deal {Damage} damage.\nPut a card from your discard pile on top of your draw pile."),
         ([{"op": "shuffle_hand"}, {"op": "draw", "amount": 3}], "self",
          "Shuffle your hand and discard pile into your draw pile.\nDraw {Cards} card(s)."),
         ([_tut("choose", "attack")], "self", "Put an Attack from your draw pile into your hand."),
         ([_tut("random", "skill")], "self", "Put a random Skill from your draw pile into your hand."),
         ([_tut("choose")], "self", "Put a card from your draw pile into your hand."),
         ([_tut("random", None, amount=2)], "self", "Put 2 random cards from your draw pile into your hand."),
         ([{"op": "retrieve_card", "pile": "discard", "cards": "choose", "card_type": "attack"}], "self",
          "Return an Attack of your choice from your discard pile to your hand."),
         ([{"op": "retrieve_card", "pile": "discard", "cards": "random"}], "self",
          "Return a random card from your discard pile to your hand."),
         ([{"op": "exhaust_card", "pile": "draw", "cards": "choose", "amount": 1}], "self", "Exhaust a card in your draw pile."),
         ([{"op": "exhaust_card", "pile": "draw", "cards": "random", "amount": 1}], "self",
          "Exhaust a random card in your draw pile."),
         ([_gk("retain")], "self", "Choose a card in your hand. It gains Retain."),
         ([_gk("sly", "skill")], "self", "Choose a Skill in your hand. It is Sly this turn."),
         ([_gk("ethereal")], "self", "Choose a card in your hand. It gains Ethereal."),
         ([{"op": "add_trigger", "trigger": "on_shuffle", "effects": [{"op": "block", "amount": 4}]}], "self",
          "Whenever you shuffle your draw pile, gain 4 Block.")]
C_FRAGMENTS = ('case "return_to_hand":   parts.Add("Returns to your hand after you play it."); break;',
               'case "to_draw_top":      parts.Add("Goes on top of your draw pile after you play it."); break;',
               'case "return_next_turn": parts.Add("At the start of your next turn, return this to your hand."); break;',
               'case "put_back":         parts.Add(e.From == "discard" ? "Put a card from your discard pile on top of your draw pile."',
               ': "Put a card from your hand on top of your draw pile."); break;',
               'case "shuffle_hand":     parts.Add("Shuffle your hand and discard pile into your draw pile."); break;',
               'return $"Put {pick} from your draw pile into your hand.";',
               'string pick = e.Cards == "choose" ? (n > 1 ? $"{n} {many}" : one) : (n > 1 ? $"{n} random {many}" : $"a random {noun}");',
               '? (n > 1 ? $"{n} {many} of your choice" : $"{one} of your choice")',
               'string gains = e.Keyword switch { "sly" => "is Sly this turn", "ethereal" => "gains Ethereal", _ => "gains Retain" };',
               'return $"Choose {HandKindWords(e.CardKind).One} in your hand. It {gains}.";',
               'return $"Exhaust {what} in your {(e.Pile == "draw" ? "draw pile" : "hand")}.";',
               '"on_shuffle"      => "Whenever you shuffle your draw pile",')


def _t_rules_and_describe() -> None:
    print("validator + describe (Python literal == the C# fragment written by hand):")
    ok = [_card([{"op": "block", "amount": 9}, {"op": "return_to_hand"}]),
          _atk([{"op": "damage", "amount": 6}, {"op": "to_draw_top"}], rarity="rare"),
          _atk([{"op": "damage", "amount": 3}, {"op": "return_next_turn"}], rarity="rare", cost=0),
          _atk([{"op": "damage", "amount": 9}, _pb("discard")], rarity="common"),
          _card([{"op": "draw", "amount": 2}, _pb("hand"), {"op": "exhaust"}], cost=0),
          _card([{"op": "shuffle_hand"}, {"op": "draw", "amount": 4}, {"op": "exhaust"}], rarity="rare", cost=0),
          _card([_tut("choose", "attack"), {"op": "exhaust"}], rarity="rare", cost=0),
          _card([{"op": "block", "amount": 5}, _tut("random", "skill")]),
          _card([{"op": "block", "amount": 8}, {"op": "exhaust_card", "pile": "draw", "cards": "choose", "amount": 1}]),
          _atk([{"op": "damage", "amount": 7}, _gk("retain")], rarity="common"),
          _card([{"op": "block", "amount": 7}, _gk("sly", "skill")]),
          _card([{"op": "draw", "amount": 1}, _gk("ethereal")], cost=0, rarity="common"),
          _card([{"op": "add_trigger", "trigger": "on_shuffle", "effects": [{"op": "block", "amount": 4}]}], ctype="power"),
          # BI's filters on the new kind (decision recorded in the plan): every_n / this_turn / once_per_turn are legal
          _card([{"op": "add_trigger", "trigger": "on_shuffle", "every_n": 2, "effects": [{"op": "draw", "amount": 1}]}],
                ctype="power", rarity="rare"),
          _card([{"op": "add_trigger", "trigger": "on_shuffle", "once_per_turn": True, "effects": [{"op": "block", "amount": 3}]}],
                ctype="power"),
          # a replayed (BM) return_to_hand card is fine: the result pile is decided once per play series
          _card([{"op": "block", "amount": 9}, {"op": "return_to_hand"}], upgrade=[{"op": "block", "amount": 12}, {"op": "return_to_hand"}]),
          # retrieve_card keeps its old discard / exhaust shapes
          _atk([{"op": "damage", "amount": 9}, {"op": "retrieve_card", "pile": "discard", "cards": "choose"}])]
    for c in ok:
        check(not _errs(c), f"validates: {json.dumps(c['effects'])} -> {_errs(c)}")
    bad = [(_card([{"op": "block", "amount": 9}, {"op": "return_to_hand"}], cost=0), "costs 1+"),
           (_card([{"op": "block", "amount": 9}, {"op": "return_to_hand"}], up_cost=0), "costs 1+"),
           (_card([{"op": "draw", "amount": 1}, {"op": "return_to_hand"}]), "infinite loop"),
           (_card([{"op": "gain_energy", "amount": 1}, {"op": "return_to_hand"}]), "infinite loop"),
           (_card([{"op": "block", "amount": 5}, {"op": "return_to_hand"}, {"op": "to_draw_top"}]), "ONE way"),
           (_card([{"op": "block", "amount": 5}, {"op": "to_draw_top"}, {"op": "exhaust"}]), "'exhaust' / 'purge'"),
           (_card([{"op": "block", "amount": 5}, {"op": "return_next_turn"}, {"op": "purge"}]), "'exhaust' / 'purge'"),
           (_card([{"op": "block", "amount": 5}, {"op": "to_draw_top"}], ctype="power"), "not allowed on a Power"),
           (_card([{"op": "to_draw_top"}, {"op": "corruption"}]), "corruption"),
           (_card([{"op": "return_to_hand", "amount": 1}, {"op": "block", "amount": 5}]), ""),
           (_card([_pb("draw")]), "from"),
           (_card([{"op": "put_back", "from": "hand", "cards": "random"}]), "choose"),
           (_card([_pb("hand", amount=2)]), ""),
           (_card([_pb("hand"), _pb("discard")]), "at most one 'put_back'"),
           (_card([_gk("exhaust")]), "keyword"),
           (_card([{"op": "grant_keyword", "keyword": "retain", "cards": "random"}]), "choose"),
           (_card([_gk("retain", "status")]), ""),
           (_card([_gk("retain", amount=1)]), ""),
           (_card([{"op": "block", "amount": 5, "keyword": "retain"}]), "keyword"),
           (_card([{"op": "block", "amount": 5, "from": "hand"}]), "from"),
           (_card([{"op": "exhaust_card", "pile": "draw", "cards": "all"}]), "choose or random"),
           (_card([{"op": "exhaust_card", "pile": "exhaust", "cards": "choose", "amount": 1}]), "pile"),
           (_card([{"op": "shuffle_hand"}, {"op": "shuffle_hand"}]), "at most one 'shuffle_hand'"),
           (_card([{"op": "add_trigger", "trigger": "turn_start", "effects": [_pb("hand")]}], ctype="power"), ""),
           (_card([{"op": "add_trigger", "trigger": "turn_start", "effects": [{"op": "shuffle_hand"}]}], ctype="power"), ""),
           (_card([{"op": "add_trigger", "trigger": "turn_start", "effects": [_gk("retain")]}], ctype="power"), "")]
    for c, frag in bad:
        e = _errs(c)
        check(bool(e) and any(frag in x for x in e), f"rejected ({frag or 'any'}): {json.dumps(c['effects'])} -> {e}")
    v = _V
    check(v._score_effect({"op": "return_to_hand"}) == 5.0 and v._score_effect({"op": "to_draw_top"}) == 2.0
          and v._score_effect({"op": "return_next_turn"}) == 3.0, "the flag-ops are priced (card-flow value)")
    check(v._score_effect(_pb("hand")) == 2.0 and v._score_effect({"op": "shuffle_hand"}) == 2.0, "put_back / shuffle_hand priced")
    check(v._score_effect(_gk("retain")) == 3.0 and v._score_effect(_gk("ethereal")) == 1.0, "grant_keyword priced per keyword")
    for effects, target, want in CASES:
        got = cardgen.describe(effects, target)
        check(got == want, f"describe {got!r} == {want!r}")
    src = _cs("Engine", "ForgedCards.cs")
    for frag in C_FRAGMENTS:
        check(frag in src, f"C# Describe fragment: {frag}")
    check(cardgen.effect_literal(_pb("discard")) == 'new EffectSpec("put_back", 0, Cards: "choose", From: "discard")',
          "effect_literal: put_back carries Cards + From")
    check(cardgen.effect_literal(_gk("sly", "skill")) == 'new EffectSpec("grant_keyword", 0, Cards: "choose", Keyword: "sly", CardKind: "skill")',
          "effect_literal: grant_keyword carries Cards + Keyword (+ CardKind)")
    check(cardgen.effect_literal(_tut("choose", "attack")) == 'new EffectSpec("retrieve_card", 1, Pile: "draw", Cards: "choose", CardKind: "attack")',
          "effect_literal: the tutor's CardKind")
    check(cardgen.effect_literal({"op": "exhaust_card", "pile": "draw", "cards": "random", "amount": 1})
          == 'new EffectSpec("exhaust_card", 1, Cards: "random", Pile: "draw")', "effect_literal: exhaust_card Pile draw")
    for op in FLAG_OPS + ("shuffle_hand",):
        check(cardgen.effect_literal({"op": op}) == f'new EffectSpec("{op}", 0)', f"effect_literal: {op}")


def _t_contract() -> None:
    print("contract surfaces:")
    schema = json.loads(CARD_SCHEMA.read_text(encoding="utf-8"))
    eff = schema["$defs"]["effect"]
    check(set(NEW_OPS) <= set(eff["properties"]["op"]["enum"]), "schema: op enum += the six ops")
    check(eff["properties"]["from"]["enum"] == ["hand", "discard"], "schema: the `from` field")
    check(eff["properties"]["keyword"]["enum"] == ["retain", "ethereal", "sly"], "schema: the `keyword` field")
    check("on_shuffle" in eff["properties"]["trigger"]["enum"], "schema: trigger enum += on_shuffle")
    te = schema["$defs"]["triggerEffect"]
    check(not (set(NEW_OPS) & set(te["properties"]["op"]["enum"])), "schema: the six ops are never payload ops")
    rules = json.dumps(eff.get("allOf", []))
    check('"pile": {"enum": ["discard", "exhaust", "draw"]}' in rules, "schema: retrieve_card pile += draw")
    check('"pile": {"enum": ["hand", "draw"]}' in rules, "schema: exhaust_card pile hand/draw")
    check('"required": ["from", "cards"]' in rules and '"required": ["keyword", "cards"]' in rules,
          "schema: put_back / grant_keyword required fields")
    check('"op": {"enum": ["return_to_hand", "to_draw_top", "return_next_turn", "shuffle_hand"]}' in rules,
          "schema: the flag-op rule")
    check('"retrieve_card", "grant_keyword"]' in rules, "schema: card_type belongs to retrieve_card + grant_keyword too")
    vocab = paths.VOCABULARY.read_text(encoding="utf-8")
    idx = gate.vocab_index(vocab)
    for t in NEW_OPS:
        check(vocab.count(f"| `{t}`") == 1, f"VOCABULARY: ONE `{t}` row")
        check(f"`{t}` —" in idx, f"the index carries a {t} line")
    check("`on_shuffle`" in idx, "the index names on_shuffle")
    row = next(l for l in vocab.splitlines() if l.startswith("| `retrieve_card`"))
    check("`pile:\"draw\"` is a TUTOR" in row and "reverses the old never-the-draw-pile rule on purpose" in row,
          "VOCABULARY: the retrieve_card row says the draw-pile rule is reversed on purpose")
    check("`pile:\"draw\"` (v66" in next(l for l in vocab.splitlines() if l.startswith("| `exhaust_card`")),
          "VOCABULARY: exhaust_card row names the draw pile")
    check("`on_shuffle` (v66" in vocab and "on_poison_damage/on_shuffle)" in vocab, "VOCABULARY: Triggers prose + add_trigger row")
    for op in NEW_OPS:
        check(op in gate.GATED_OP_ORDER, f"gate.GATED_OP_ORDER carries {op} (no card core cost)")
    check(gate.FIELD_UNITS["from"] == ("put_back",) and gate.FIELD_UNITS["keyword"] == ("grant_keyword",)
          and "exhaust_card" in gate.FIELD_UNITS["pile"], "gate.FIELD_UNITS: from / keyword / exhaust_card pile")
    check(set(FLAG_OPS) <= census.KEYWORD_OPS, "census.KEYWORD_OPS += the three flag-ops")
    check("on_shuffle" in {k for k, _ in coverage.REACTIVE_MENU_V2} and "on_shuffle" in coverage.CENSUS_DETECTOR,
          "coverage: REACTIVE_MENU_V2 + detector for on_shuffle")
    cc = census.walk_card(_card([{"op": "add_trigger", "trigger": "on_shuffle", "effects": [{"op": "block", "amount": 4}]}],
                                ctype="power"))
    check(coverage.CENSUS_DETECTOR["on_shuffle"](cc), "the on_shuffle detector fires on an on_shuffle power")
    fe = next((f for f in featured.FEATURED_MENU if f.id == "recursion"), None)
    check(fe is not None and fe.detect(census.walk_card(_card([{"op": "block", "amount": 9}, {"op": "return_to_hand"}])))
          and fe.detect(census.walk_card(_atk([{"op": "damage", "amount": 9}, _pb("discard")])))
          and not fe.detect(census.walk_card(_atk([{"op": "damage", "amount": 6}]))), "featured: the recursion entry + detector")
    check({"put_back", "grant_keyword"} <= set(harness_v2._PREFERRED_OPS), "harness_v2: put_back / grant_keyword preferred")
    arch = {a["id"]: a for a in json.loads((DATA / "archetypes.json").read_text(encoding="utf-8"))["archetypes"]}
    claims = {"madness_discard": ({"put_back", "grant_keyword", "return_next_turn"}, {"#74", "#75"}),
              "retain_hold": ({"grant_keyword", "put_back", "return_to_hand"}, {"#74", "#75"}),
              "ascetic_purge": ({"retrieve_card", "to_draw_top", "shuffle_hand", "on_shuffle"}, {"#74"}),
              "exhaust_pyre": ({"exhaust_card"}, {"#74"}),
              "fleeting_flux": ({"grant_keyword"}, {"#75"})}
    for aid, (toks, gaps) in claims.items():
        a = arch[aid]
        check(toks <= set(a["vocabulary"]["ops"]), f"{aid} claims {sorted(toks)}")
        check({f"VOCABULARY_GAPS{g}" for g in gaps} <= set(a["gap_refs"]) and a["buildable"] is True, f"{aid} refs {sorted(gaps)}")
        check("(v66" in a.get("build_notes", ""), f"{aid} build_notes name the v66 shape")
    pool = json.loads((DATA / "exemplar_pool.json").read_text(encoding="utf-8"))["exemplars"]
    v = harness_v2.exemplar_validator()
    used = set()
    tutor = exdraw = False
    for e in pool:
        hit = set(NEW_TOKENS) & bridges.card_tokens(e["card"])
        effs = e["card"]["effects"]
        tutor |= any(x.get("op") == "retrieve_card" and x.get("pile") == "draw" for x in effs)
        exdraw |= any(x.get("op") == "exhaust_card" and x.get("pile") == "draw" for x in effs)
        if hit or any(x.get("pile") == "draw" and x.get("op") in ("retrieve_card", "exhaust_card") for x in effs):
            used |= hit
            r = v.validate(dict(e["card"]))
            check(r.ok, f"exemplar {e['card']['id']} validates: {r.errors}")
    check(set(NEW_TOKENS) <= used, f"exemplars cover every new token (got {sorted(used)})")
    check(tutor and exdraw, "exemplars show the draw-pile tutor and exhaust from the draw pile")
    heur = (paths.VOCABULARY.parent / "DESIGN_HEURISTICS.md").read_text(encoding="utf-8")
    check(heur.count("(v66") >= 5, "DESIGN_HEURISTICS: the v66 notes on all five archetypes")
    gaps_md = (REPO / "VOCABULARY_GAPS.md").read_text(encoding="utf-8")
    for n, nxt in (("74", "75"), ("75", "76")):
        entry = gaps_md.split(f"### {n}.", 1)[1].split(f"### {nxt}.", 1)[0]
        check("**Status:** **done (2026-10-04, vocab v66, Phase BO)**" in entry, f"gap #{n} is done (v66)")
        check("vocab v67" not in entry, f"gap #{n} no longer names v67")
    js = (REPO / "web" / "static" / "render.js").read_text(encoding="utf-8")
    for frag in ('case "return_to_hand": return "Returns to your hand after you play it";',
                 'case "to_draw_top": return "Goes on top of your draw pile after you play it";',
                 'case "return_next_turn": return "At the start of your next turn, return this to your hand";',
                 'case "put_back": return e.from === "discard"', 'case "shuffle_hand":', 'case "grant_keyword": {',
                 'on_shuffle: "Whenever you shuffle your draw pile"', 'from your draw pile into your hand',
                 'const where = e.pile === "draw" ? "draw pile" : "hand";'):
        check(frag in js, f"render.js: {frag[:60]}")
    src = pathlib.Path(cf.__file__).read_text(encoding="utf-8")
    check("(5) v66: `put_back`" in src and "A thin deck digs (v66)" in src and "v66: `grant_keyword` gives a hand card Retain" in src,
          "class_forge: one pitch sentence per touched section")
    plan = (REPO / "docs" / "plans" / "VOCAB_EXPANSION_6_PLAN.md").read_text(encoding="utf-8")
    check("**Findings (BO" in plan and "**Phase BO" in plan, "the plan records the BO findings + status line")


def _t_tester() -> None:
    print("the tester (validate-only path; staging waits for Ryan):")
    p = TESTER_DIR / "build_tester.py"
    check(p.exists(), "tests/gaptest-bo/build_tester.py exists")
    spec = importlib.util.spec_from_file_location("bo_tester", p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    check(mod.validate(verbose=True) == 0, "every tester card validates")
    types = [c["type"] for c in mod.CARDS if c["rarity"] != "basic"]
    check(types.count("attack") >= 3 and types.count("skill") >= 3 and types.count("power") >= 1,
          "pool: >= 3 non-basic Attacks + Skills and >= 1 Power (the merchant stall)")
    deck = sum(s["count"] for s in mod.CHARACTER["starting_deck"])
    check(deck <= 18, f"a THIN starting deck so the draw pile reshuffles often (got {deck})")
    flat = json.dumps(mod.CARDS)
    for need in ('"return_to_hand"', '"to_draw_top"', '"return_next_turn"', '"from": "discard"', '"from": "hand"',
                 '"pile": "draw", "cards": "choose", "card_type": "attack"', '"pile": "draw", "cards": "random", "card_type": "skill"',
                 '"op": "exhaust_card", "pile": "draw"', '"keyword": "sly"', '"keyword": "retain"', '"keyword": "ethereal"',
                 '"trigger": "on_shuffle"', '"shuffle_hand"'):
        check(need in flat, f"the tester exercises {need}")
    names = {c["name"] for c in mod.CARDS}
    for base in ("Particle Wall", "Bolas", "Make It So", "Headbutt", "Secret Weapon", "Snap", "Reboot"):
        check(base in names, f"the tester carries the plan's {base}")
    text = p.read_text(encoding="utf-8")
    check("--validate-only" in text and "Auto-selected" in text, "the tester has --validate-only and names the picker grep")


def _t_smoke_record() -> None:
    print("the saved AutoSlay tag greps (TEST_AUDIT_2026-10 §7):")
    files = [TESTER_DIR / f"godot_BO_tags_{s}.txt" for s in SMOKE_SEEDS]
    if not any(p.exists() for p in files):
        print("  smoke pending (no godot_BO_tags_<SEED>.txt yet — the BO smoke runs with BP's, after Ryan's go-ahead)")
        return
    seen = ""
    for p in files:
        assert p.exists(), f"missing smoke record {p}"
        txt = p.read_text(encoding="utf-8")
        check("Run completed" in txt, f"{p.name}: the run completed")
        check("[BO]" in txt, f"{p.name} holds [BO] tags")
        check("mod exceptions: 0" in txt and "Localization formatting errors: 0" in txt
              and "BlankTheSpire stack frames: 0" in txt, f"{p.name} records a clean run")
        seen += txt
    for t in TAGS:
        check(t in seen, f"the smoke fired '{t}'")
    check("Auto-selected" in seen, "a BO picker resolved through the AutoSlay selector")


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


def test_phase_bo_all() -> None:
    global _PASS, _FAIL
    _PASS = _FAIL = 0
    assert main() == 0, f"{_FAIL} Phase BO check(s) failed - see the FAIL lines above"


if __name__ == "__main__":
    sys.exit(main())
