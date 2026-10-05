"""Phase BR — stun (re-opened gap #11), `discard cards:"all"` + `cards_removed`, growing turn-start damage (gap #79), vocab v70
— offline. Run: uv run python -m tests.test_phase_br  (from generation/)

Pins: the stamp; verify-first against the game sources (CreatureCmd.Stun + its stunMove overload, Creature.StunInternal throws
for a player and reads StateLog.Last(), SetMoveImmediate only replaces a move that CanTransitionAway, STUNNED is
MustPerformOnceBeforeTransitioning, Whistle; the batch CardCmd.Discard; Fiend Fire / Calculated Gamble; RollingBoulderPower
awaits a VFX Finished signal outside TestMode); the engine wiring (the stun op + its guards and tags, the per-play
cards_removed stash, discard all, the AfterSideTurnStart Rolling Boulder tick with a ThrowingPlayerChoiceContext, NO base
RollingBoulderPower anywhere in the mod, the class-level stun rails in the importer); the validator rules on both sides (every
stun guard rail, the cards_removed ordering rule, the payload-grow rule); the describe byte-match (Python literals asserted, the
C# fragments grepped); the contract surfaces (schema, VOCABULARY rows, gate, census, coverage, featured, harness_v2,
class_forge, bridges, archetypes, exemplars, heuristics, gap log, render.js, the plan); the tester's validate-only path; the
saved AutoSlay tag greps under tests/gaptest-br/ when they exist ("smoke pending" until then); and prints the rule-0.9
readings.
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
TESTER_DIR = pathlib.Path(__file__).parent / "gaptest-br"
SMOKE_SEEDS = ("GAPTESTBR1", "GAPTESTBR2")
MODREF = pathlib.Path(r"C:/Users/ryanr/Desktop/NOVOGODOT/BLANKthespire/_modref")

NEW_OPS = ("stun",)
NEW_TOKENS = NEW_OPS + ("cards_removed",)
TAGS = ("[BR] stun '", "(applied=True)", "[BR] stunned turn performed '", "[BR] discard all x",
        "[BR] cards_removed -> ", "(hits)", "(draw)", "[BK] hits_scale cards_removed -> ", "[BR] turn_start grow: 5+5x")
REMOVED_DRAW = [{"op": "discard", "cards": "all"}, {"op": "draw", "amount": 1, "scale": "cards_removed"}, {"op": "exhaust"}]
FIEND_FIRE = [{"op": "exhaust_card", "cards": "all"}, {"op": "damage", "amount": 7, "hits_scale": "cards_removed"}, {"op": "exhaust"}]
WHISTLE = [{"op": "damage", "amount": 20}, {"op": "stun"}, {"op": "exhaust"}]
BOULDER = [{"op": "add_trigger", "trigger": "turn_start",
            "effects": [{"op": "damage", "amount": 5, "grow": 5, "target": "all_enemies"}]}]


def check(cond: bool, msg: str) -> None:
    global _PASS, _FAIL
    if cond:
        _PASS += 1
    else:
        _FAIL += 1
        print(f"  FAIL: {msg}")


def _cs(*parts: str) -> str:
    return (MOD_CODE.joinpath(*parts)).read_text(encoding="utf-8-sig").replace("\r\n", "\n")


def _card(effects, rarity="uncommon", cost=1, ctype="skill", target="self", upgrade=None, up_cost=None, cid="br_t"):
    c = {"id": cid, "name": "BR", "type": ctype, "rarity": rarity, "cost": cost, "target": target, "effects": effects}
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


def _trig(trigger, payload, **extra):
    return [dict({"op": "add_trigger", "trigger": trigger, "effects": payload}, **extra)]


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


def _code(src: str) -> str:
    """The C# source with // and /// comments stripped (the pins below are about CODE, not the explanatory comments)."""
    return re.sub(r"//.*", "", src)


def _set(src: str, name: str) -> set[str]:
    m = re.search(name + r"\s*=\s*\[(.*?)\];", src, re.S)
    return set(re.findall(r'"(\w+)"', m.group(1))) if m else set()


def test_version() -> None:
    print("Phase BR vocab stamp is at least 70 (Python + C#):")
    check(bts1.VOCAB_VERSION >= 70, f"bts1.VOCAB_VERSION >= 70, got {bts1.VOCAB_VERSION}")
    fc = _cs("Engine", "ForgedCards.cs")
    m = re.search(r"public const int VocabVersion = (\d+);", fc)
    check(m is not None and int(m.group(1)) >= 70, f"ForgedCards.VocabVersion >= 70, got {m and m.group(1)}")
    check(m is not None and bts1.VOCAB_VERSION <= int(m.group(1)), "bts1.VOCAB_VERSION <= ForgedCards.VocabVersion")
    check("70: Phase BR" in fc and all(f"`{t}`" in fc for t in NEW_TOKENS), "ForgedCards.cs comment names Phase BR + the tokens")
    check("70: Phase BR" in pathlib.Path(bts1.__file__).read_text(encoding="utf-8"), "bts1.py records the v70 entry")


def _t_verify_first() -> None:
    print("verify-first against the game sources (rule 0.6):")
    root = MODREF / "decomp_full"
    if not root.exists():
        print("  (decomp not on this machine — skipped, informational)")
        return
    cc = (root / "MegaCrit.Sts2.Core.Commands" / "CreatureCmd.cs").read_text(encoding="utf-8")
    check("public static async Task Stun(Creature creature, string? nextMoveId = null)" in cc
          and "public static Task Stun(Creature creature, Func<IReadOnlyList<Creature>, Task> stunMove, string? nextMoveId = null)" in cc,
          "DECOMP CreatureCmd.Stun + the stunMove overload (the stunned-turn observation point)")
    cr = (root / "MegaCrit.Sts2.Core.Entities.Creatures" / "Creature.cs").read_text(encoding="utf-8")
    si = cr.split("public void StunInternal(", 1)[1].split("public void PrepareForNextTurn", 1)[0]
    check('throw new InvalidOperationException("Can\'t stun a player.");' in si and "stateLog.Last().Id" in si
          and 'new MoveState("STUNNED", stunMove, new StunIntent())' in si and "MustPerformOnceBeforeTransitioning = true" in si
          and "Monster.SetMoveImmediate(state);" in si, "DECOMP StunInternal: throws for a player, reads StateLog.Last(), STUNNED is must-perform")
    mm = (root / "MegaCrit.Sts2.Core.Models" / "MonsterModel.cs").read_text(encoding="utf-8")
    check("if (NextMove.CanTransitionAway || forceTransition)" in mm, "DECOMP SetMoveImmediate only replaces a CanTransitionAway move")
    ms = (root / "MegaCrit.Sts2.Core.MonsterMoves.MonsterMoveStateMachine" / "MoveState.cs").read_text(encoding="utf-8")
    check("if (MustPerformOnceBeforeTransitioning)" in ms and "return _performedAtLeastOnce;" in ms,
          "DECOMP MoveState.CanTransitionAway (a second stun the same turn is a no-op)")
    cards = root / "MegaCrit.Sts2.Core.Models.Cards"
    check("await CreatureCmd.Stun(cardPlay.Target);" in (cards / "Whistle.cs").read_text(encoding="utf-8")
          and "CardKeyword.Exhaust" in (cards / "Whistle.cs").read_text(encoding="utf-8"), "DECOMP Whistle: Exhaust + CreatureCmd.Stun")
    ff = (cards / "FiendFire.cs").read_text(encoding="utf-8")
    check("await CardCmd.Exhaust(choiceContext, item);" in ff and ".WithHitCount(cardCount)" in ff,
          "DECOMP Fiend Fire: exhausts the hand one at a time, one hit per card")
    check("CardCmd.DiscardAndDraw(choiceContext, cards, cardsToDraw)" in (cards / "CalculatedGamble.cs").read_text(encoding="utf-8"),
          "DECOMP Calculated Gamble: discard the hand, draw that many")
    rb = (root / "MegaCrit.Sts2.Core.Models.Powers" / "RollingBoulderPower.cs").read_text(encoding="utf-8")
    check("if (TestMode.IsOn)" in rb and "NRollingBoulderVfx.SignalName.Finished" in rb and "await signalAwaiter;" in rb,
          "DECOMP RollingBoulderPower awaits a VFX Finished signal outside TestMode (why it is never applied)")
    cmd = (root / "MegaCrit.Sts2.Core.Commands" / "CardCmd.cs").read_text(encoding="utf-8")
    check("public static async Task Discard(PlayerChoiceContext choiceContext, IEnumerable<CardModel> cards)" in cmd,
          "DECOMP the batch CardCmd.Discard (Sly-safe)")
    cm = (root / "MegaCrit.Sts2.Core.Combat" / "CombatManager.cs").read_text(encoding="utf-8")
    st = cm.split("await Hook.BeforeSideTurnStart(", 1)[1]
    check(st.index("item3.AfterTurnStart(") < st.index("await Hook.AfterSideTurnStart("),
          "DECOMP StartTurn: the per-creature AfterTurnStart (ClearBlock) runs BEFORE Hook.AfterSideTurnStart")


def _t_engine() -> None:
    print("the engine: stun, the cards_removed stash, discard all, the Rolling Boulder tick, the class rails, the tags:")
    er = _cs("Engine", "EffectRunner.cs")
    for frag, why in (
            ('case "stun":\n                    // Phase BR (v70, gap #11)', "the stun op"),
            ("await StunTarget(play?.Target, spec.Title ?? spec.Id);", "stuns the CHOSEN target"),
            ("if (m.MoveStateMachine == null || m.MoveStateMachine.StateLog.Count == 0)", "guards the empty StateLog (StunInternal throws)"),
            ("if (t?.Monster == null)", "a player / no target is never stunned (StunInternal throws)"),
            ("await CreatureCmd.Stun(t, _ =>", "the stunMove overload (observes the stunned turn)"),
            ("catch (Exception ex)", "the call is in a try/catch"),
            ('bool applied = now == "STUNNED" && old != "STUNNED";', "applied = NextMove became STUNNED"),
            ("[BR] stun '{name}': next move {old} -> {now} (applied={applied})", "the stun tag"),
            ("[BR] stun skipped: already stunned", "the already-stunned tag"),
            ("[BR] stun skipped: cannot transition", "the locked-move tag"),
            ("[BR] stun skipped: empty move log", "the empty-log tag"),
            ("[BR] stunned turn performed '{name}'", "the stunned-turn tag (from the stunMove)"),
            ("if (brCard != null) brCard.RemovedThisPlay = null;", "the stash resets every play (a replay too)"),
            ("removedN = await DiscardRandom(hand, card.Owner, ctx);", "discard all = the whole hand through the batch path"),
            ("[BR] discard all x{removedN}", "the discard-all tag"),
            ("int removedN = await ExhaustCards(e, amt, ctx, card.Owner, card);", "exhaust_card records its count"),
            ('"cards_removed"              => (card as DataCard)?.RemovedThisPlay ?? OtherCardsInHand(card),',
             "ScaleValue: the stash, the preview falls back to OtherCardsInHand"),
            ("[BR] cards_removed -> {ScaleValue(e.HitsScale, card)} ('{spec.Title ?? spec.Id}') (hits).", "the hits tag"),
            ("[BR] cards_removed -> {n} ('{spec.Title ?? spec.Id}') (draw).", "the draw tag"),
            ('&& !(c is DataCard sdc && sdc.HasOp("stun"))', "add_random_card never generates a stun card"),
            ("internal static async Task<int> DiscardRandom(", "DiscardRandom returns the count"),
            ("try { await CardCmd.Discard(ctx, chosen); }", "the batch CardCmd.Discard (Sly still fires)")):
        check(frag in er, f"EffectRunner: {why}")
    dc = _cs("Engine", "DataCard.cs")
    check("internal int? RemovedThisPlay;" in dc and 'case "stun":' in dc
          and 'if (e.Cards != "all") WithVar("Discard", e.Amount, up);' in dc, "DataCard: the stash, stun declares no var, discard all no var")
    tr = _cs("Engine", "TriggerRunner.cs")
    check("Creature? attacker = null, int growFires = 0)" in tr and "int grown = amt + e.Grow * Math.Max(0, growFires);" in tr
          and "[BR] turn_start grow: {amt}+{e.Grow}x{growFires} = {grown}" in tr, "TriggerRunner: amt + grow x fires + the tag")
    tp = _cs("Powers", "ForgedTriggerPower.cs")
    side = tp.split("public override async Task AfterSideTurnStart(CombatSide side, IReadOnlyList<Creature> participants, ICombatState combatState)", 1)
    check(len(side) == 2 and "await TriggerRunner.Run(t, Owner.Player, new ThrowingPlayerChoiceContext(), growFires: _growFires);" in side[1].split("\n    }", 1)[0]
          and "_growFires++;" in side[1].split("\n    }", 1)[0], "ForgedTriggerPower: the tick is on AfterSideTurnStart + a ThrowingPlayerChoiceContext")
    check("if (Grows(t)) return;" in tp and "private int _growFires;" in tp and "private static bool Grows(EffectSpec t)" in tp,
          "a growing payload skips AfterPlayerTurnStart; the per-power fire counter sits beside _ripenLeft")
    check("BeforeSideTurnStart" not in _code(tp), "ForgedTriggerPower never ticks on BeforeSideTurnStart (the turn-start pitfall)")
    mod_src = "\n".join(_code(p.read_text(encoding="utf-8-sig")) for p in MOD_CODE.rglob("*.cs"))
    check(re.search(r"\bRollingBoulderPower\b", mod_src) is None, "the base RollingBoulderPower is referenced NOWHERE in the mod")
    fc = _cs("Engine", "ForgedCards.cs")
    check(set(NEW_OPS) <= _set(fc, "SupportedOps") and not (set(NEW_OPS) & _set(fc, "TriggerOps")),
          "stun: supported, never a payload op")
    check("cards_removed" in _set(fc, "SupportedScales") and "cards_removed" in _set(fc, "HitsScaleSources")
          and _set(fc, "DiscardPickModes") == {"random", "choose", "all"}, "the scale + hits_scale source, discard's pick modes")
    for frag in ("internal const int StunMinCost = 2;", "'stun' belongs on an UNCOMMON or RARE card",
                 "'stun' needs 'exhaust' on the card (base and upgrade)", "'stun' needs a card that costs {StunMinCost}+ energy",
                 "'stun' can't share a card with return_to_hand / to_draw_top / return_next_turn",
                 "'stun' is not allowed on a Power", "stun needs a single-enemy card", "stun is a flag-op",
                 "at most one 'stun' effect per card.", "discard 'cards':'all' takes no amount",
                 "a 'cards_removed' read needs a 'discard' or 'exhaust_card' op earlier",
                 "'grow' in a trigger payload is only allowed on a targeted 'damage' of a turn_start trigger (Rolling Boulder).",
                 "a growing turn_start damage must be the trigger's ONLY payload effect.",
                 "a growing turn_start trigger can't carry a 'when'",
                 "a class may carry at most ONE stun card",
                 "returns cards from the exhaust pile — a class with a stun card may not re-buy it.",
                 "makes a copy of the stun card"):
        check(frag in fc, f"ForgedCards: {frag[:70]}")
    ch = _cs("Engine", "ForgedCharacters.cs")
    check("var stunErr = ForgedCards.StunClassError(parsedCards);" in ch, "the importer enforces the class-level stun rails")


CASES = [(WHISTLE, "enemy", "Deal {Damage} damage.\nStun the enemy.\nExhaust."),
         (FIEND_FIRE, "enemy", "Exhaust your hand.\nDeal {Damage} damage for each card Exhausted.\nExhaust."),
         (REMOVED_DRAW, "self", "Discard your hand.\nDraw cards equal to the cards Discarded.\nExhaust."),
         ([{"op": "discard", "cards": "all"}, {"op": "damage", "amount": 4, "hits_scale": "cards_removed"}], "enemy",
          "Discard your hand.\nDeal {Damage} damage for each card Discarded."),
         ([{"op": "exhaust_card", "cards": "all"}, {"op": "damage", "amount": 1, "scale": "cards_removed"}], "all_enemies",
          "Exhaust your hand.\nDeal damage equal to the cards Exhausted to ALL enemies."),
         ([{"op": "exhaust_card", "cards": "random", "amount": 2}, {"op": "block", "amount": 1, "scale": "cards_removed"}], "self",
          "Exhaust 2 random cards in your hand.\nGain Block equal to the cards Exhausted."),
         ([{"op": "exhaust_card", "cards": "all", "card_type": "skill"}], "self", "Exhaust all Skills in your hand."),
         (BOULDER, "self", "At the start of your turn, deal 5 damage to ALL enemies. Increases by 5 each turn.")]
C_FRAGMENTS = ('case "stun":             parts.Add("Stun the enemy."); break;',
               'case "discard":     parts.Add(e.Cards == "all" ? "Discard your hand."',
               'string removed = "Discarded";',
               'string Sp(EffectSpec x) => x.Scale == "cards_removed" ? $"the cards {removed}" : ScalePhrase(x);',
               ': e.HitsScale == "cards_removed" ? $"Deal {{Damage}} damage for each card {removed}{dmgSuffix}{ub}."',
               'case "exhaust_card":    parts.Add(ExhaustCardSentence(e)); removed = "Exhausted"; break;',
               'if (e.Cards == "all" && e.CardKind == null && e.Pile != "draw") return "Exhaust your hand.";',
               ': e.HasGrow ? $"deal {e.Amount} damage{to}. Increases by {e.Grow} each turn"',
               '$"Deal damage equal to {Sp(e)}{dmgSuffix}{ub}."', '$"Gain Block equal to {Sp(e)}."', '$"Draw cards equal to {Sp(e)}."')


def _t_rules_and_describe() -> None:
    print("validator + describe (Python literal == the C# fragment written by hand):")
    ok = [_atk(WHISTLE, cost=3), _atk(WHISTLE, cost=2, rarity="rare", upgrade=[{"op": "damage", "amount": 26}, {"op": "stun"}, {"op": "exhaust"}]),
          _card([{"op": "block", "amount": 8}, {"op": "stun"}, {"op": "exhaust"}], cost=2, target="enemy"),
          _atk(FIEND_FIRE, rarity="rare", cost=2), _card(REMOVED_DRAW, cost=0),
          _atk([{"op": "discard", "cards": "all"}, {"op": "damage", "amount": 4, "hits_scale": "cards_removed"}], rarity="rare"),
          _card([{"op": "discard", "cards": "choose", "amount": 2}, {"op": "draw", "amount": 1, "scale": "cards_removed"}]),
          _card([{"op": "exhaust_card", "cards": "random", "amount": 2}, {"op": "block", "amount": 1, "scale": "cards_removed"}]),
          _pow(BOULDER, cost=3), _pow(_trig("turn_start", [{"op": "damage", "amount": 3, "grow": 3, "target": "random_enemy"}]), cost=2)]
    for c in ok:
        check(not _errs(c), f"validates: {json.dumps(c['effects'])} -> {_errs(c)}")
    bad = [(_atk([{"op": "damage", "amount": 20}, {"op": "stun"}], cost=3), "exhaust"),
           (_atk(WHISTLE, cost=3, upgrade=[{"op": "damage", "amount": 26}, {"op": "stun"}]), "exhaust"),
           (_atk(WHISTLE, cost=1), "costs 2+"), (_atk(WHISTLE, cost=3, up_cost=1), "costs 2+"), (_atk(WHISTLE, cost="X"), ""),
           (_atk(WHISTLE, cost=3, rarity="common"), "UNCOMMON or RARE"),
           (_atk(WHISTLE, cost=3, target="all_enemies"), "single-enemy"), (_atk(WHISTLE, cost=3, target="random_enemy"), "single-enemy"),
           (_atk([{"op": "damage", "amount": 20}, {"op": "stun"}, {"op": "stun"}, {"op": "exhaust"}], cost=3), "at most one 'stun'"),
           (_atk([{"op": "damage", "amount": 20}, {"op": "stun", "amount": 1}, {"op": "exhaust"}], cost=3), ""),
           (_atk([{"op": "damage", "amount": 20}, {"op": "stun"}, {"op": "return_to_hand"}], cost=3), ""),
           (_pow(_trig("turn_start", [{"op": "stun", "target": "enemy"}]), cost=3), ""),
           (_pow(_trig("attacked", [{"op": "stun"}]), cost=3), ""),
           (_card([{"op": "discard", "cards": "all", "amount": 2}]), "no amount"),
           (_card([{"op": "draw", "amount": 1, "scale": "cards_removed"}, {"op": "discard", "cards": "all"}]), "earlier"),
           (_atk([{"op": "damage", "amount": 4, "hits_scale": "cards_removed"}]), "earlier"),
           (_card([{"op": "discard", "cards": "all"}, {"op": "draw", "amount": 1, "scale": "cards_removed"}],
                  upgrade=[{"op": "draw", "amount": 1, "scale": "cards_removed"}, {"op": "discard", "cards": "all"}]), "earlier"),
           (_pow(_trig("turn_start", [{"op": "discard", "cards": "all"}])), ""),
           (_pow(_trig("turn_end", [{"op": "damage", "amount": 5, "grow": 5, "target": "all_enemies"}])), "turn_start"),
           (_pow(_trig("turn_start", [{"op": "damage", "amount": 5, "grow": 5, "target": "all_enemies"}, {"op": "block", "amount": 3}])), "ONLY"),
           (_pow(_trig("turn_start", [{"op": "damage", "amount": 5, "grow": 5, "target": "all_enemies"}], when={"kind": "hp_below_half"})), "'when'"),
           (_pow(_trig("turn_start", [{"op": "damage", "amount": 3, "grow": 5, "target": "all_enemies"}])), "exceed"),
           (_pow(_trig("turn_start", [{"op": "block", "amount": 5, "grow": 5}])), ""),
           (_pow(_trig("turn_start", [{"op": "damage", "amount": 5, "grow": 5, "hits": 2, "target": "all_enemies"}])), "")]
    for c, frag in bad:
        e = _errs(c)
        check(bool(e) and any(frag in x for x in e), f"rejected ({frag or 'any'}): {json.dumps(c['effects'])} {c.get('cost')} -> {e}")
    v = _V
    check(v._score_effect({"op": "stun"}) == 10.0, "priced: stun ~ an enemy turn skipped (10)")
    check(v._score_effect({"op": "damage", "amount": 7, "hits_scale": "cards_removed"}) == 28.0
          and v._score_effect({"op": "damage", "amount": 1, "scale": "cards_removed"}) == 4.0,
          "priced: cards_removed at ~4 cards (Fiend Fire 7 x 4; a scaled damage 4)")
    for effects, target, want in CASES:
        got = cardgen.describe(effects, target)
        check(got == want, f"describe {got!r} == {want!r}")
    src = _cs("Engine", "ForgedCards.cs")
    for frag in C_FRAGMENTS:
        check(frag in src, f"C# Describe fragment: {frag}")
    for e, want in (({"op": "stun"}, 'new EffectSpec("stun", 0)'),
                    ({"op": "discard", "cards": "all"}, 'new EffectSpec("discard", 0, Cards: "all")'),
                    ({"op": "damage", "amount": 7, "hits_scale": "cards_removed"}, 'new EffectSpec("damage", 7, HitsScale: "cards_removed")'),
                    ({"op": "draw", "amount": 1, "scale": "cards_removed"}, 'new EffectSpec("draw", 1, null, 1, "cards_removed")'),
                    (BOULDER[0], 'new EffectSpec("add_trigger", 0, Trigger: "turn_start", Triggered: '
                                 '[new EffectSpec("damage", 5, Grow: 5, Target: "all_enemies")])')):
        got = cardgen.effect_literal(e)
        check(got == want, f"effect_literal {got!r} == {want!r}")
    # the class-level rails (class_forge mirrors ForgedCards.StunClassError)
    stun = _atk(WHISTLE, cost=3, cid="whistle")
    exhume = _card([{"op": "retrieve_card", "pile": "exhaust", "cards": "choose"}, {"op": "exhaust"}], cid="exhume")
    copier = _card([{"op": "add_card", "card_id": "whistle", "pile": "hand"}], cid="copier")
    check(cf._stun_class_conflict([], stun) is None, "class rail: the first stun card is fine")
    check(cf._stun_class_conflict([stun], _atk(WHISTLE, cost=3, cid="whistle2")) is not None, "class rail: a second stun card drops")
    check(cf._stun_class_conflict([stun], exhume) is not None and cf._stun_class_conflict([exhume], stun) is not None,
          "class rail: exhaust-pile recursion and a stun card never share a class (either order)")
    check(cf._stun_class_conflict([stun], copier) is not None, "class rail: add_card naming the stun card drops")
    check(cf._stun_class_conflict([stun], _card([{"op": "retrieve_card", "pile": "discard", "cards": "choose"}], cid="r")) is None,
          "class rail: discard-pile recursion is fine (the stun card exhausts)")


def _t_contract() -> None:
    print("contract surfaces:")
    schema = json.loads(CARD_SCHEMA.read_text(encoding="utf-8"))
    eff = schema["$defs"]["effect"]
    check(set(NEW_OPS) <= set(eff["properties"]["op"]["enum"]), "schema: op enum += stun")
    check("cards_removed" in eff["properties"]["scale"]["enum"] and "cards_removed" in eff["properties"]["hits_scale"]["enum"],
          "schema: scale + hits_scale += cards_removed")
    rules = json.dumps(eff["allOf"])
    check('"cards": {"enum": ["random", "choose", "all"]}' in rules and '"op": {"const": "stun"}' in rules
          and '"cards": {"const": "all"}' in rules, "schema: discard cards all (no amount) + the stun flag-op rule")
    te = schema["$defs"]["triggerEffect"]
    check("stun" not in te["properties"]["op"]["enum"] and te["properties"]["grow"]["maximum"] == 9
          and '"required": ["grow"]' in json.dumps(te["allOf"]), "schema: stun never a payload; payload grow declared + ruled")
    vocab = paths.VOCABULARY.read_text(encoding="utf-8")
    idx = gate.vocab_index(vocab)
    check(vocab.count("| `stun`") == 1 and "`stun`" in idx, "VOCABULARY: ONE stun row (+ its index name)")
    check("`cards_removed`" in idx and "`cards_removed` (v70)" in vocab and '(random/choose/all)' in vocab
          and "may `grow`" in vocab, "VOCABULARY: cards_removed (scale + hits_scale), discard all, the payload grow")
    check(set(NEW_OPS) <= set(gate.GATED_OP_ORDER), "gate: stun gated (no card-core cost)")
    check("stun" in census.KEYWORD_OPS, "census: the nullary stun flag-op is a card-shape keyword")
    check("cards_removed" in {k for k, _ in coverage.SCALE_MENU}, "coverage: SCALE_MENU += cards_removed")
    ff = census.walk_card(_atk(FIEND_FIRE, rarity="rare", cost=2))
    cg = census.walk_card(_card(REMOVED_DRAW, cost=0))
    plain = census.walk_card(_atk([{"op": "damage", "amount": 6}]))
    check(coverage.CENSUS_DETECTOR["cards_removed"](ff) and coverage.CENSUS_DETECTOR["cards_removed"](cg)
          and not coverage.CENSUS_DETECTOR["cards_removed"](plain), "coverage: the cards_removed detector (scale OR hits_scale)")
    feats = {f.id: f for f in featured.FEATURED_MENU}
    check("hand_dump" in feats and feats["hand_dump"].detect(ff) and feats["hand_dump"].detect(cg)
          and not feats["hand_dump"].detect(plain), "featured: hand_dump")
    check("cards_removed" in harness_v2._PREFERRED_SCALES and "stun" not in harness_v2._PREFERRED_OPS,
          "harness_v2: cards_removed preferred; stun NOT (one stun card per class)")
    src = pathlib.Path(cf.__file__).read_text(encoding="utf-8")
    check("(7) v70: `discard` `\"cards\":\"all\"` discards \\\nyour hand" in src
          and 'v70: Fiend Fire = `exhaust_card` `cards:"all"` + a damage `hits_scale:"cards_removed"`.' in src
          and "v70: a turn_start payload \\\ndamage may `grow` each turn (Rolling Boulder)." in src
          and "STUN (v70) — `stun` on ONE uncommon/rare Exhaust card per class (cost 2+, single enemy); nothing re-buys it." in src,
          "class_forge: one short pitch sentence per touched section (DISCARD / DECK-THINNING / RAMPAGE / PRECISION READS)")
    check("_stun_why = _stun_class_conflict([m[\"card\"] for m in made], pres.card)" in src
          and "if _stun_class_conflict([m[\"card\"] for m in made if m.get(\"card\") is not old_card], new):" in src,
          "class_forge: the class rails drop a conflicting card (main loop + the coverage repair)")
    check({"stun", "cards_removed"} <= bridges.card_tokens(_atk(WHISTLE + [], cost=3)) | bridges.card_tokens(_atk(FIEND_FIRE, rarity="rare", cost=2))
          and "grow" in bridges.card_tokens(_pow(BOULDER, cost=3)), "bridges: stun / cards_removed (hits too) / grow surface")
    arch = {a["id"]: a for a in json.loads((DATA / "archetypes.json").read_text(encoding="utf-8"))["archetypes"]}
    for aid, tok, gap in (("ambush_alpha", "stun", 11), ("block_bulwark", "stun", 11), ("madness_discard", "cards_removed", 79),
                          ("exhaust_pyre", "cards_removed", 79), ("power_ramp", "grow", 79), ("countdown_ripen", "grow", 79)):
        a = arch[aid]
        check(tok in a["vocabulary"]["ops"] and f"VOCABULARY_GAPS#{gap}" in a["gap_refs"] and a["buildable"] is True
              and "(v70" in a.get("build_notes", ""), f"{aid} claims {tok} (#{gap}, v70 note)")
        check(f"`{tok}`" in vocab, f"'{tok}' is backticked in VOCABULARY.md (test_archetypes)")
    pool = json.loads((DATA / "exemplar_pool.json").read_text(encoding="utf-8"))["exemplars"]
    v = harness_v2.exemplar_validator()
    forms = set()
    for e in pool:
        flat = json.dumps(e["card"])
        for name, frag in (("stun", '"op": "stun"'), ("fiend_fire", '"hits_scale": "cards_removed"'),
                           ("calc_gamble", '"scale": "cards_removed"'), ("discard_all", '"op": "discard", "cards": "all"'),
                           ("boulder", '"grow": ')):
            if frag in flat and (name != "boulder" or '"trigger": "turn_start"' in flat):
                forms.add(name)
                r = v.validate(dict(e["card"]))
                check(r.ok, f"exemplar {e['card']['id']} validates: {r.errors}")
                check("needs" not in e, f"exemplar {e['card']['id']} is not class-only")
    check(forms == {"stun", "fiend_fire", "calc_gamble", "discard_all", "boulder"}, f"exemplars show every form: {sorted(forms)}")
    heur = (paths.VOCABULARY.parent / "DESIGN_HEURISTICS.md").read_text(encoding="utf-8")
    amb = heur.split("archetype-note: ambush_alpha", 1)[1].split("archetype-note:", 1)[0]
    check(heur.count("(v70") >= 6 and "ONE stun card per class" in amb and "re-buy it" in amb,
          "DESIGN_HEURISTICS: the v70 notes (the stun guard rails on ambush_alpha)")
    gaps_md = (REPO / "VOCABULARY_GAPS.md").read_text(encoding="utf-8")
    g11 = gaps_md.split("### 11.", 1)[1].split("### 12.", 1)[0]
    check("**Status:** **done (2026-10-04, vocab v70, Phase BR)**" in g11 and "re-opened 2026-10-01" in g11
          and "was rejected 2026-07-14" in g11 and "Triage (2026-07-14" in g11, "gap #11 is done (v70), history kept")
    g79 = gaps_md.split("### 79.", 1)[1].split("### 80.", 1)[0]
    check("**Status:** **done (2026-10-04, vocab v70, Phase BR)**" in g79, "gap #79 is done (v70)")
    js = (REPO / "web" / "static" / "render.js").read_text(encoding="utf-8")
    for frag in ('case "stun": return "Stun the enemy";', 'e.cards === "all" ? "Discard your hand"',
                 'return "Exhaust your hand";', 'cards_removed: "the cards removed"', 'cards_removed: "card removed"',
                 '${e.grow ? ` (grows by ${e.grow})` : ""}'):
        check(frag in js, f"render.js: {frag[:60]}")
    plan = (REPO / "docs" / "plans" / "VOCAB_EXPANSION_6_PLAN.md").read_text(encoding="utf-8")
    check("**Findings (BR" in plan and "**Phase BR" in plan and "| BR | #11, #79 | v70 |" in plan,
          "the plan records the BR findings + status line (v70)")


def _t_tester() -> None:
    print("the tester (validate-only path):")
    p = TESTER_DIR / "build_tester.py"
    check(p.exists(), "tests/gaptest-br/build_tester.py exists")
    spec = importlib.util.spec_from_file_location("br_tester", p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    check(mod.validate(verbose=True) == 0, "every tester card validates (+ the class-level stun rails)")
    types = [c["type"] for c in mod.CARDS if c["rarity"] != "basic"]
    check(types.count("attack") >= 3 and types.count("skill") >= 3 and types.count("power") >= 1,
          "pool: >= 3 non-basic Attacks + Skills and >= 1 Power (the merchant stall)")
    check(90 <= mod.CHARACTER["max_hp"] <= 110, "max HP ~100")
    check(sum(1 for c in mod.CARDS if any(e.get("op") == "stun" for e in c["effects"])) == 1 and mod.DECK.get("br_whistle") == 2,
          "ONE stun card (two copies in the deck: the already-STUNNED no-op)")
    flat = json.dumps(mod.CARDS)
    for need in ('"op": "stun"', '"cost": 3', '"amount": 20}, {"op": "stun"}', '"exhaust_card", "cards": "all"}, {"op": "damage", "amount": 7, "hits_scale": "cards_removed"}',
                 '"op": "discard", "cards": "all"}, {"op": "draw", "amount": 1, "scale": "cards_removed"}',
                 '"op": "discard", "cards": "all"}, {"op": "damage", "amount": 4, "hits_scale": "cards_removed"}',
                 '{"op": "damage", "amount": 5, "grow": 5, "target": "all_enemies"}', '"op": "sly"', '"status": "strength"'):
        check(need in flat, f"the tester exercises {need}")
    text = p.read_text(encoding="utf-8")
    check("--validate-only" in text and "--character class4" in text and "GAPTESTBR1 GAPTESTBR2" in text
          and "[BR] turn_start grow: 5+5x<fires>" in text and "Combat turn N" in text,
          "the docstring is the complete smoke recipe")


def _t_smoke_record() -> None:
    print("the saved AutoSlay tag greps (TEST_AUDIT_2026-10 §7):")
    files = [TESTER_DIR / f"godot_BR_tags_{s}.txt" for s in SMOKE_SEEDS]
    if not any(p.exists() for p in files):
        print("  smoke pending (no godot_BR_tags_<SEED>.txt yet)")
        return
    seen = ""
    for p in files:
        assert p.exists(), f"missing smoke record {p}"
        txt = p.read_text(encoding="utf-8")
        check("[BR]" in txt, f"{p.name} holds [BR] tags")
        check("mod exceptions: 0" in txt and "Localization formatting errors: 0" in txt
              and "BlankTheSpire stack frames: 0" in txt, f"{p.name} records a clean run")
        seen += txt
    for t in TAGS:
        check(t in seen, f"the smoke fired '{t}'")
    check("(applied=False)" in seen or "[BR] stun skipped:" in seen, "the smoke saw a stun that did NOT land (locked / already stunned)")
    fires = [int(m) for m in re.findall(r"turn_start grow: 5\+5x(\d+)", seen)]
    check(fires and max(fires) >= 2, f"the boulder grew (max fires {max(fires) if fires else None})")
    nz = re.findall(r"\[BR\] cards_removed -> ([1-9]\d*) \('([^']+)'\)", seen)
    check(any(c.startswith("Fiend Fire") for _n, c in nz), "cards_removed non-zero on the exhaust form (Fiend Fire)")
    check(any(c.startswith(("Scatter Volley", "Calculated Gamble")) for _n, c in nz), "cards_removed non-zero on a discard form")


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


def test_phase_br_all() -> None:
    global _PASS, _FAIL
    _PASS = _FAIL = 0
    assert main() == 0, f"{_FAIL} Phase BR check(s) failed - see the FAIL lines above"


if __name__ == "__main__":
    sys.exit(main())
