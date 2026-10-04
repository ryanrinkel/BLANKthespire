"""Phase BM — base-power statuses: self-drawbacks, replay, next-turn Block, retain hand (VOCAB_EXPANSION_6_PLAN,
gaps #68 / #69 / #70, vocab v65) — offline. Run:  uv run python -m tests.test_phase_bm  (from generation/)

Pins: the stamp; the engine wiring (EffectRunner.SelfDebuffStatuses routed to the player through ONE literal path —
the lose_* trio as NEGATIVE applies under named vars — the base powers behind every status / op, the replay +
decay-tick hooks on DataCard, the ForgedCostShiftPower replay skip, the [BM] tags); the validator rules on both sides;
the describe byte-match (Python literals asserted, the C# fragments grepped); the contract surfaces (schema, VOCABULARY
rows, statuses/*.json, gate order, census, featured, archetypes, exemplars, heuristics, gap log, render.js, the pitch
sentence); the tester's validate-only path; the saved AutoSlay tag greps under tests/gaptest-bm/ when present
(GAPTESTBM1 / BM2 — "smoke pending" until Ryan approves the run); and prints the rule-0.9 readings.
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

from btsgen import bridges, bts1, cardgen, census, featured, gate, harness_v2, paths  # noqa: E402
from btsgen import class_forge as cf  # noqa: E402
from btsgen.validator import CardValidator  # noqa: E402

_PASS = 0
_FAIL = 0
MOD_CODE = paths.VOCABULARY.parents[1] / "BlankTheSpireCode"
CARD_SCHEMA = paths.VOCABULARY.parent / "card.schema.json"
REPO = paths.VOCABULARY.parents[2]
DATA = pathlib.Path(cf.__file__).parent / "data"
TESTER_DIR = pathlib.Path(__file__).parent / "gaptest-bm"
SMOKE_SEEDS = ("GAPTESTBM1", "GAPTESTBM2")
MODREF = pathlib.Path(r"C:/Users/ryanr/Desktop/NOVOGODOT/BLANKthespire/_modref")

SELF_DEBUFFS = ("no_draw", "no_energy_gain", "no_block_gain", "dex_decay", "focus_decay",
                "lose_strength", "lose_dexterity", "lose_focus")
NEW_STATUSES = SELF_DEBUFFS + ("echo_form",)
NEW_OPS = ("replay_next", "block_next_turn", "retain_hand")
TAGS = ("[BM] self-debuff no_draw +1 on player (Artifact ", "[BM] self-debuff no_energy_gain +1 on player (Artifact ",
        "[BM] self-debuff no_block_gain +", "[BM] self-debuff dex_decay +", "[BM] self-debuff lose_strength +",
        "[BM] self-debuff lose_dexterity +", "[BM] replay_next skill x", "[BM] replay_next attack x",
        "[BM] replay_next power x", "[BM] replay_next all x", "[BM] replay play #2 of '", "[BM] echo_form applied",
        "(scale=fixed)", "(scale=block)", "[BM] retain_hand", "[BM] decay tick dex_decay -")


def check(cond: bool, msg: str) -> None:
    global _PASS, _FAIL
    if cond:
        _PASS += 1
    else:
        _FAIL += 1
        print(f"  FAIL: {msg}")


def _cs(*parts: str) -> str:
    return (MOD_CODE.joinpath(*parts)).read_text(encoding="utf-8").replace("\r\n", "\n")


def _card(effects, rarity="uncommon", cost=1, ctype="skill", target="self", upgrade=None):
    c = {"id": "bm_t", "name": "BM", "type": ctype, "rarity": rarity, "cost": cost, "target": target, "effects": effects}
    if upgrade is not None:
        c["upgrade"] = {"effects": upgrade}
    return c


def _st(status, amount, **kw):
    e = {"op": "apply_status", "status": status, "amount": amount}
    e.update(kw)
    return e


def _rp(kind, n, **kw):
    e = {"op": "replay_next", "card_type": kind, "count": n}
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


def _set(src: str, name: str) -> set[str]:
    m = re.search(name + r"\s*=\s*\[(.*?)\];", src, re.S)
    return set(re.findall(r'"(\w+)"', m.group(1))) if m else set()


def test_version() -> None:
    print("Phase BM vocab stamp is at least 65 (Python + C#):")
    check(bts1.VOCAB_VERSION >= 65, f"bts1.VOCAB_VERSION >= 65, got {bts1.VOCAB_VERSION}")
    fc = _cs("Engine", "ForgedCards.cs")
    m = re.search(r"public const int VocabVersion = (\d+);", fc)
    check(m is not None and int(m.group(1)) >= 65, f"ForgedCards.VocabVersion >= 65, got {m and m.group(1)}")
    check(m is not None and bts1.VOCAB_VERSION <= int(m.group(1)), "bts1.VOCAB_VERSION <= ForgedCards.VocabVersion")
    check("65: Phase BM" in fc and "`no_draw`" in fc and "`replay_next" in fc and "`echo_form`" in fc,
          "ForgedCards.cs comment names Phase BM + the tokens")
    check("65: Phase BM" in pathlib.Path(bts1.__file__).read_text(encoding="utf-8"), "bts1.py records the v65 entry")


def _t_engine() -> None:
    print("the engine: the self route, the base powers, the replay + decay hooks, the tags:")
    # verify-first: every base power is sealed + generic (no character state), with the semantics the spec relies on
    pw = MODREF / "decomp_full" / "MegaCrit.Sts2.Core.Models.Powers"
    if pw.exists():
        for cls in ("NoDrawPower", "NoEnergyGainPower", "NoBlockPower", "WraithFormPower", "BiasedCognitionPower",
                    "BurstPower", "OneTwoPunchPower", "SignalBoostPower", "DuplicationPower", "EchoFormPower",
                    "BlockNextTurnPower", "RetainHandPower"):
            src = (pw / f"{cls}.cs").read_text(encoding="utf-8")
            check(f"public sealed class {cls} : PowerModel" in src, f"DECOMP: {cls} is sealed + concrete")
        check("cardSource == null" in (pw / "NoBlockPower.cs").read_text(encoding="utf-8"),
              "DECOMP: NoBlockPower zeroes CARD Block only (payload / relic Block still lands)")
        check("AfterSideTurnStart" in (pw / "WraithFormPower.cs").read_text(encoding="utf-8"),
              "DECOMP: WraithFormPower owns its tick (AfterSideTurnStart)")
        art = (pw / "ArtifactPower.cs").read_text(encoding="utf-8")
        check("GetTypeForAmount(amount) != PowerType.Debuff" in art and "if (target != base.Owner)" in art,
              "DECOMP: Artifact eats ANY debuff on its owner (your own drawbacks included)")
    er = _cs("Engine", "EffectRunner.cs")
    check(set(SELF_DEBUFFS) == _set(er, "SelfDebuffStatuses"), "EffectRunner.SelfDebuffStatuses = the eight")
    check(not (set(NEW_STATUSES) & _set(er, "SelfBuffStatuses")),
          "none of them is in SelfBuffStatuses (relics / potions / orbs / summons / payloads never accept them)")
    for frag, why in (
            ('internal static readonly HashSet<string> BmSelfStatuses = new(SelfDebuffStatuses) { "echo_form" };',
             "self = SelfBuffStatuses ∪ SelfDebuffStatuses (+ the card-only echo_form)"),
            ("SelfBuffStatuses.Contains(status) || BmSelfStatuses.Contains(status)", "IsSelfStatus"),
            ("await ApplyBmSelfStatus(e.Status!, ctx, card.Owner.Creature, Math.Max(1, amt), spec.Title ?? spec.Id);",
             "cards apply the self statuses literally to the PLAYER"),
            ('"lose_strength"  => RelicApplyT<StrengthPower>(ctx, target, source, -amount),', "lose_strength = the -amt literal"),
            ('"lose_dexterity" => RelicApplyT<DexterityPower>(ctx, target, source, -amount),', "lose_dexterity = the -amt literal"),
            ('"lose_focus"     => RelicApplyT<FocusPower>(ctx, target, source, -amount),', "lose_focus = the -amt literal"),
            ('"no_draw"        => RelicApplyT<NoDrawPower>(ctx, target, source, amount),', "no_draw = NoDrawPower"),
            ('"no_energy_gain" => RelicApplyT<NoEnergyGainPower>(ctx, target, source, amount),', "no_energy_gain = NoEnergyGainPower"),
            ('"no_block_gain"       => RelicApplyT<NoBlockPower>(ctx, target, source, amount),', "no_block_gain = NoBlockPower"),
            ('"dex_decay"      => RelicApplyT<WraithFormPower>(ctx, target, source, amount),', "dex_decay = WraithFormPower"),
            ('"focus_decay"    => RelicApplyT<BiasedCognitionPower>(ctx, target, source, amount),', "focus_decay = BiasedCognitionPower"),
            ('"echo_form"      => RelicApplyT<EchoFormPower>(ctx, target, source, amount),', "echo_form = EchoFormPower"),
            ('"attack" => RelicApplyT<OneTwoPunchPower>(ctx, me, me, n),', "replay_next attack = OneTwoPunchPower"),
            ('"power"  => RelicApplyT<SignalBoostPower>(ctx, me, me, n),', "replay_next power = SignalBoostPower"),
            ('"all"    => RelicApplyT<DuplicationPower>(ctx, me, me, n),', "replay_next all = DuplicationPower"),
            ('_        => RelicApplyT<BurstPower>(ctx, me, me, n),', "replay_next skill = BurstPower"),
            ("int n = scaled ? (int)me.Block : Math.Max(1, amt);", "block_next_turn: scale block = your current Block"),
            ("if (n > 0) await RelicApplyT<BlockNextTurnPower>(ctx, me, me, n);", "block_next_turn = BlockNextTurnPower"),
            ("await RelicApplyT<RetainHandPower>(ctx, me, me, 1);", "retain_hand = RetainHandPower amount 1"),
            ('$"[BM] self-debuff {status} +{n} on player (Artifact {art0}"', "the [BM] self-debuff tag"),
            ('$"[BM] echo_form applied by \'{src}\'', "the [BM] echo_form tag"),
            ('$"[BM] replay_next {kind} x{n}', "the [BM] replay_next tag"),
            ('$"[BM] block_next_turn +{n} (scale={(scaled ? "block" : "fixed")})', "the [BM] block_next_turn tag"),
            ('$"[BM] retain_hand (', "the [BM] retain_hand tag")):
        check(frag in er, f"EffectRunner: {why}")
    dc = _cs("Engine", "DataCard.cs")
    for frag, why in (
            ('case "lose_strength":  WithVar("SelfStrengthLoss", e.Amount, up); break;', "lose_strength declares a NAMED var"),
            ('case "lose_dexterity": WithVar("SelfDexterityLoss", e.Amount, up); break;', "lose_dexterity declares a NAMED var"),
            ('case "lose_focus":     WithVar("SelfFocusLoss", e.Amount, up); break;', "lose_focus declares a NAMED var"),
            ('Power<NoBlockPower>(vname ?? "NoBlockTurns", e.Amount, up)', "no_block_gain's {NoBlockTurns} var"),
            ('Power<WraithFormPower>(vname ?? "DexDecay", e.Amount, up)', "dex_decay's {DexDecay} var"),
            ('Power<BiasedCognitionPower>(vname ?? "FocusDecay", e.Amount, up)', "focus_decay's {FocusDecay} var"),
            ('if (!e.IsScaled) WithPower<BlockNextTurnPower>("NextTurnBlock", e.Amount, up);', "block_next_turn's {NextTurnBlock} var"),
            ("if (cardPlay.Card == this && cardPlay.PlayIndex > 0)", "BeforeCardPlayed logs only THIS card's replays"),
            ('$"[BM] replay play #{cardPlay.PlayIndex + 1} of \'{Spec.Title ?? Spec.Id}\'', "the [BM] replay play tag"),
            ('$"[BM] decay tick dex_decay -{me.GetPowerAmount<WraithFormPower>()} "', "the [BM] decay tick tag (dex)"),
            ('$"[BM] decay tick focus_decay -{me.GetPowerAmount<BiasedCognitionPower>()} "', "the [BM] decay tick tag (focus)")):
        check(frag in dc, f"DataCard: {why}")
    check(dc.count("Power<StrengthPower>(") == 1, "Power<StrengthPower> stays the self-buff `strength` only")
    cs = _cs("Powers", "ForgedCostShiftPower.cs")
    check("if (!cardPlay!.IsFirstInSeries)" in cs and "burns no discount use" in cs,
          "ForgedCostShiftPower: a replay (PlayIndex > 0) burns no budgeted discount use (the BM decision)")
    fc = _cs("Engine", "ForgedCards.cs")
    check(set(NEW_STATUSES) <= _set(fc, "SupportedStatuses"), "ForgedCards.SupportedStatuses += the nine")
    check(set(NEW_OPS) <= _set(fc, "SupportedOps"), "SupportedOps += the three ops")
    check(not (set(NEW_OPS) & _set(fc, "TriggerOps")), "the three ops are card-only (not in TriggerOps)")
    check(not (set(NEW_STATUSES) & _set(fc, "EnemyDebuffStatuses")), "no self status is payload-legal")
    check('["no_draw"] = 1, ["no_energy_gain"] = 1, ["no_block_gain"] = 3, ["dex_decay"] = 2, ["focus_decay"] = 2,' in fc
          and '["lose_strength"] = 5, ["lose_dexterity"] = 5, ["lose_focus"] = 5, ["echo_form"] = 1,' in fc
          and 'BmStatusMin = new() { ["no_block_gain"] = 2 };' in fc, "the self-status bands")
    for frag in ('"\'no_draw\' is a price: the same card needs a \'draw\' or \'gain_energy\' payoff',
                 '"\'echo_form\' belongs on a RARE POWER card (the base Echo Form)."',
                 '"replay_next card_type \'all\' (your next card of ANY type plays twice) is RARE-only."',
                 '"an upgrade can\'t change replay_next\'s \'card_type\' / \'count\'',
                 "block_next_turn may only scale by 'block'",
                 '"retain_hand is a flag-op (no amount / status / scale / hits)."',
                 "&& !EffectRunner.IsSelfStatus(q.Status)"):
        check(frag in fc, f"ForgedCards.Validate: {frag[:70]}")


CASES = [([{"op": "draw", "amount": 3}, _st("no_draw", 1)], "self",
          "Draw {Cards} card(s).\nYou cannot draw additional cards this turn."),
         ([{"op": "gain_energy", "amount": 2}, _st("no_energy_gain", 1)], "self",
          "Gain {Energy} energy.\nYou cannot gain energy this turn."),
         ([_st("no_block_gain", 2)], "self", "You cannot gain Block from cards for {NoBlockTurns} turns."),
         ([_st("dex_decay", 1)], "self", "At the start of your turn, lose {DexDecay} Dexterity."),
         ([_st("focus_decay", 1)], "self", "At the start of your turn, lose {FocusDecay} Focus."),
         ([_st("lose_strength", 2)], "enemy", "Lose {SelfStrengthLoss} Strength."),
         ([_st("lose_dexterity", 1)], "self", "Lose {SelfDexterityLoss} Dexterity."),
         ([_st("lose_focus", 3)], "all_enemies", "Lose {SelfFocusLoss} Focus."),
         ([_st("echo_form", 1)], "self", "The first card you play each turn is played twice."),
         ([_rp("skill", 2)], "self", "This turn, your next 2 Skills are played twice."),
         ([_rp("skill", 1)], "self", "This turn, your next Skill is played twice."),
         ([_rp("attack", 1)], "self", "This turn, your next Attack is played twice."),
         ([_rp("power", 1)], "self", "Your next Power is played twice."),
         ([_rp("all", 1)], "self", "This turn, your next card is played twice."),
         ([{"op": "block_next_turn", "amount": 8}], "self", "Next turn, gain {NextTurnBlock} Block."),
         ([{"op": "block", "amount": 5}, {"op": "block_next_turn", "amount": 1, "scale": "block"}], "self",
          "Gain {Block} Block.\nNext turn, gain Block equal to your current Block."),
         ([{"op": "block", "amount": 12}, {"op": "retain_hand"}], "self", "Gain {Block} Block.\nRetain your hand this turn.")]
C_FRAGMENTS = ('"no_draw"        => "You cannot draw additional cards this turn.",',
               '"no_energy_gain" => "You cannot gain energy this turn.",',
               '"no_block_gain"       => "You cannot gain Block from cards for {NoBlockTurns} turns.",',
               '"dex_decay"      => "At the start of your turn, lose {DexDecay} Dexterity.",',
               '"focus_decay"    => "At the start of your turn, lose {FocusDecay} Focus.",',
               '"lose_strength"  => "Lose {SelfStrengthLoss} Strength.",',
               '"lose_dexterity" => "Lose {SelfDexterityLoss} Dexterity.",',
               '"lose_focus"     => "Lose {SelfFocusLoss} Focus.",',
               '"echo_form"      => "The first card you play each turn is played twice.",',
               'string what = n > 1 ? $"your next {n} {single}s are" : $"your next {single} is";',
               '? $"{char.ToUpperInvariant(what[0])}{what[1..]} played twice."',
               ': $"This turn, {what} played twice.";',
               'parts.Add(e.Scale == "block" ? "Next turn, gain Block equal to your current Block." : "Next turn, gain {NextTurnBlock} Block.");',
               'case "retain_hand":    parts.Add("Retain your hand this turn."); break;')


def _t_rules_and_describe() -> None:
    print("validator + describe (Python literal == the C# fragment written by hand):")
    ok = [_card([{"op": "draw", "amount": 3}, _st("no_draw", 1)], cost=0),
          _card([{"op": "gain_energy", "amount": 2}, _st("no_energy_gain", 1)]),
          _card([{"op": "block", "amount": 16}, _st("no_block_gain", 2), {"op": "exhaust"}], cost=0),
          _card([_st("intangible", 2), _st("dex_decay", 1)], rarity="rare", cost=3, ctype="power"),
          _card([_st("focus", 4), _st("focus_decay", 1)], ctype="power"),
          # an enemy Strength loss AND your own on one card (distinct vars: StrengthLoss vs SelfStrengthLoss)
          _card([_st("strength_down", 2), _st("lose_strength", 2), {"op": "exhaust"}], cost=0, target="enemy"),
          _card([{"op": "damage", "amount": 11}, _st("lose_dexterity", 1)], rarity="common", ctype="attack", target="enemy"),
          _card([{"op": "damage", "amount": 26}, _st("lose_focus", 3)], rarity="rare", cost=2, ctype="attack", target="all_enemies"),
          _card([_st("echo_form", 1)], rarity="rare", cost=3, ctype="power"),
          _card([_rp("skill", 2)]), _card([_rp("attack", 1), {"op": "draw", "amount": 1}]),
          _card([_rp("power", 1)]), _card([_rp("all", 1)], rarity="rare"),
          _card([{"op": "block", "amount": 5}, {"op": "block_next_turn", "amount": 6}], rarity="common"),
          _card([{"op": "block", "amount": 5}, {"op": "block_next_turn", "amount": 1, "scale": "block"}]),
          _card([{"op": "block", "amount": 12}, {"op": "retain_hand"}], cost=2),
          # a self status on a strip card does not break the Expose order (it is not an enemy debuff)
          _card([_st("lose_strength", 1), {"op": "strip_artifact"}, _st("weak", 1)], target="enemy")]
    for c in ok:
        check(not _errs(c), f"validates: {json.dumps(c['effects'])} -> {_errs(c)}")
    bad = [(_card([_st("no_draw", 1)]), "'no_draw' is a price"),
           (_card([{"op": "draw", "amount": 2}, _st("no_draw", 2)]), "must use amount 1"),
           (_card([_st("no_block_gain", 1)]), "amount must be 2..3"),
           (_card([_st("no_block_gain", 4)]), "amount must be 2..3"),
           (_card([_st("dex_decay", 3)], ctype="power", rarity="rare"), "amount must be 1..2"),
           (_card([_st("lose_strength", 6)]), "amount must be 1..5"),
           (_card([_st("lose_strength", 1), _st("lose_strength", 1, when={"kind": "hp_below_half"})]),
            "at most one 'lose_strength'"),
           (_card([_st("echo_form", 1)], rarity="uncommon", ctype="power"), "RARE POWER"),
           (_card([_st("echo_form", 1)], rarity="rare", ctype="skill"), "RARE POWER"),
           (_card([_rp("all", 1)]), "RARE-only"),
           (_card([_rp("skill", 3)]), "must be 1..2"),
           (_card([_rp("curse", 1)]), "needs a 'card_type'"),
           (_card([_rp("skill", 1, amount=2)]), "carries only 'card_type' + 'count'"),
           (_card([_rp("skill", 1)], rarity="basic"), "BASIC"),
           (_card([_rp("skill", 1)], upgrade=[_rp("skill", 2)]), "can't change replay_next"),
           (_card([_rp("skill", 1), _rp("attack", 1)]), "at most one 'replay_next'"),
           (_card([{"op": "block_next_turn", "amount": 1, "scale": "cards_in_hand"}]), "may only scale by 'block'"),
           (_card([{"op": "block_next_turn", "amount": 21}]), "1..20"),
           (_card([{"op": "retain_hand", "amount": 1}]), "flag-op"),
           (_card([{"op": "add_trigger", "trigger": "turn_start", "effects": [_st("no_draw", 1)]}],
                  ctype="power", rarity="rare"), "no_draw"),
           (_card([{"op": "add_trigger", "trigger": "turn_start", "effects": [_st("echo_form", 1)]}],
                  ctype="power", rarity="rare"), "echo_form"),
           (_card([{"op": "add_trigger", "trigger": "turn_start", "effects": [_rp("skill", 1)]}],
                  ctype="power", rarity="rare"), "replay_next")]
    for c, frag in bad:
        e = _errs(c)
        check(any(frag in x for x in e), f"rejected ({frag}): {json.dumps(c['effects'])} -> {e}")
    v = _V
    check(v._score_effect(_st("no_draw", 1)) < 0 and v._score_effect(_st("lose_strength", 2)) == -8.0
          and v._score_effect(_st("no_block_gain", 2)) == -10.0, "the self-drawbacks are priced NEGATIVE (like lose_hp)")
    check(v._score_effect(_st("echo_form", 1)) == 26.0, "Echo Form is priced as a rare Power engine")
    check(v._score_effect(_rp("skill", 2)) == 12.0 and v._score_effect(_rp("all", 1)) == 10.0, "replay_next is priced per replay")
    check(v._score_effect({"op": "block_next_turn", "amount": 10}) == 7.0
          and v._score_effect({"op": "retain_hand"}) == 4.0, "block_next_turn / retain_hand are priced")
    for effects, target, want in CASES:
        got = cardgen.describe(effects, target)
        check(got == want, f"describe {got!r} == {want!r}")
    src = _cs("Engine", "ForgedCards.cs")
    for frag in C_FRAGMENTS:
        check(frag in src, f"C# Describe fragment: {frag}")
    check(cardgen.effect_literal(_rp("skill", 2)) == 'new EffectSpec("replay_next", 0, CardKind: "skill", Count: 2)',
          "effect_literal: replay_next carries CardKind + Count")
    check(cardgen.effect_literal({"op": "block_next_turn", "amount": 1, "scale": "block"})
          == 'new EffectSpec("block_next_turn", 1, null, 1, "block")', "effect_literal: Prolong's scale")
    check(cardgen.effect_literal({"op": "retain_hand"}) == 'new EffectSpec("retain_hand", 0)', "effect_literal: retain_hand")
    check(cardgen.STATUS_NAME["echo_form"] == "Echo Form" and cardgen.STATUS_NAME["no_block_gain"] == "No Block",
          "cardgen.STATUS_NAME (lockstep with StatusDisplay)")


def _t_contract() -> None:
    print("contract surfaces:")
    schema = json.loads(CARD_SCHEMA.read_text(encoding="utf-8"))
    eff = schema["$defs"]["effect"]
    check(set(NEW_OPS) <= set(eff["properties"]["op"]["enum"]), "schema: op enum += the three ops")
    check(set(NEW_STATUSES) <= set(eff["properties"]["status"]["enum"]), "schema: status enum += the nine")
    te = schema["$defs"]["triggerEffect"]
    check(not (set(NEW_STATUSES) & set(te["properties"]["status"]["enum"])), "schema: no self status in a payload")
    check(not (set(NEW_OPS) & set(te["properties"]["op"]["enum"])), "schema: the three ops are never payload ops")
    rules = json.dumps(eff.get("allOf", []))
    check('"card_type": {"enum": ["skill", "attack", "power", "all"]}, "count": {"type": "integer", "minimum": 1, "maximum": 2}'
          in rules, "schema: replay_next's card_type + count rule")
    check('"scale": {"const": "block"}' in rules and '"amount": {"type": "integer", "minimum": 1, "maximum": 20}' in rules,
          "schema: block_next_turn's amount / scale block rule")
    check('"op": {"const": "retain_hand"}' in rules, "schema: the retain_hand flag-op rule")
    check('"op": {"enum": ["cost_shift", "replay_next"]}' in rules, "schema: count belongs to cost_shift + replay_next")
    for s in NEW_STATUSES:
        j = json.loads((paths.VOCABULARY.parent / "statuses" / f"{s}.json").read_text(encoding="utf-8"))
        check(j["id"] == s and j["kind"] == ("buff" if s == "echo_form" else "debuff"), f"statuses/{s}.json")
    vocab = paths.VOCABULARY.read_text(encoding="utf-8")
    idx = gate.vocab_index(vocab)
    for t in NEW_STATUSES + NEW_OPS:
        check(vocab.count(f"| `{t}`") == 1, f"VOCABULARY: ONE `{t}` row")
        check(f"`{t}` —" in idx, f"the index carries a {t} line")
    check("`focus_decay` —" in idx and "[orb]" in idx.split("`focus_decay` —", 1)[1].splitlines()[0],
          "the Focus drawbacks are tagged [orb] in the index")
    check("SELF-DEBUFFS (v65) also land on you" in vocab and "your own Artifact negates them" in vocab,
          "VOCABULARY: the Statuses intro routes self-debuffs to you (and names Artifact)")
    check(vocab.count("| `no_block`") == 1, "the `no_block` CONDITION row is untouched (the status is no_block_gain)")
    for op in NEW_OPS:
        check(op in gate.GATED_OP_ORDER, f"gate.GATED_OP_ORDER carries {op} (no card core cost)")
    check(set(NEW_STATUSES) <= census.EXOTIC_STATUSES, "census.EXOTIC_STATUSES += the nine")
    fe = next((f for f in featured.FEATURED_MENU if f.id == "replay_window"), None)
    check(fe is not None and fe.detect(census.walk_card(_card([_rp("skill", 1)])))
          and fe.detect(census.walk_card(_card([_st("echo_form", 1)], rarity="rare", ctype="power"))),
          "featured: the replay_window entry + detector")
    check(cf._card_uses_orbs(_card([_st("focus_decay", 1)])) and cf._card_uses_orbs(_card([_st("lose_focus", 1)])),
          "class_forge: the Focus drawbacks are orb-class cards")
    arch = {a["id"]: a for a in json.loads((DATA / "archetypes.json").read_text(encoding="utf-8"))["archetypes"]}
    claims = {"self_sacrifice": ({"lose_strength", "no_block_gain", "dex_decay"}, {"#68"}),
              "big_energy": ({"no_draw", "no_energy_gain"}, {"#68"}),
              "burst_window": ({"no_draw", "replay_next"}, {"#68", "#69"}),
              "power_ramp": ({"echo_form", "replay_next"}, {"#69"}),
              "block_bulwark": ({"block_next_turn"}, {"#70"}),
              "retain_hold": ({"retain_hand"}, {"#70"}),
              "orb_channel": ({"focus_decay", "lose_focus"}, {"#68"})}
    for aid, (toks, gaps) in claims.items():
        a = arch[aid]
        check(toks <= set(a["vocabulary"]["ops"]), f"{aid} claims {sorted(toks)}")
        check({f"VOCABULARY_GAPS{g}" for g in gaps} <= set(a["gap_refs"]) and a["buildable"] is True, f"{aid} refs {sorted(gaps)}")
        check("(v65" in a.get("build_notes", ""), f"{aid} build_notes name the v65 shape")
    check("no_block" in arch["threshold_duelist"]["vocabulary"]["ops"], "threshold_duelist keeps the no_block CONDITION")
    pool = json.loads((DATA / "exemplar_pool.json").read_text(encoding="utf-8"))["exemplars"]
    v = harness_v2.exemplar_validator()
    used = set()
    for e in pool:
        hit = (set(NEW_STATUSES) | set(NEW_OPS)) & bridges.card_tokens(e["card"])
        if hit:
            used |= hit
            r = v.validate(dict(e["card"]))
            check(r.ok, f"exemplar {e['card']['id']} validates: {r.errors}")
            if hit & {"focus_decay", "lose_focus"}:
                check(e.get("needs") == "orb", f"exemplar {e['card']['id']} carries needs:orb")
    check(set(NEW_STATUSES) | set(NEW_OPS) <= used, f"exemplars cover every new token (got {sorted(used)})")
    heur = (paths.VOCABULARY.parent / "DESIGN_HEURISTICS.md").read_text(encoding="utf-8")
    check(heur.count("(v65") >= 6 and "Your own Artifact eats these" in heur, "DESIGN_HEURISTICS: the v65 notes + Artifact")
    gaps = (REPO / "VOCABULARY_GAPS.md").read_text(encoding="utf-8")
    for n, nxt in (("68", "69"), ("69", "70"), ("70", "71")):
        entry = gaps.split(f"### {n}.", 1)[1].split(f"### {nxt}.", 1)[0]
        check("**Status:** **done (2026-10-04, vocab v65, Phase BM)**" in entry, f"gap #{n} is done")
    js = (REPO / "web" / "static" / "render.js").read_text(encoding="utf-8")
    for frag in ('case "replay_next": {', 'case "block_next_turn":', 'case "retain_hand": return "Retain your hand this turn";',
                 'no_draw: () => "You cannot draw additional cards this turn"', 'echo_form: "Echo Form"',
                 'if (BM_PHRASES[e.status]) return BM_PHRASES[e.status](a);'):
        check(frag in js, f"render.js: {frag[:60]}")
    src = pathlib.Path(cf.__file__).read_text(encoding="utf-8")
    check("PRICES / REPLAYS (v65)" in src, "the PRECISION READS pitch sentence")
    plan = (REPO / "docs" / "plans" / "VOCAB_EXPANSION_6_PLAN.md").read_text(encoding="utf-8")
    check("**Findings (BM" in plan and "**Phase BM" in plan, "the plan records the BM findings + status line")


def _t_tester() -> None:
    print("the tester (validate-only path; staging waits for Ryan):")
    p = TESTER_DIR / "build_tester.py"
    check(p.exists(), "tests/gaptest-bm/build_tester.py exists")
    spec = importlib.util.spec_from_file_location("bm_tester", p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    check(mod.validate(verbose=True) == 0, "every tester card validates")
    types = [c["type"] for c in mod.CARDS if c["rarity"] != "basic"]
    check(types.count("attack") >= 3 and types.count("skill") >= 3 and types.count("power") >= 1,
          "pool: >= 3 non-basic Attacks + Skills and >= 1 Power (the merchant stall)")
    flat = json.dumps(mod.CARDS)
    for need in ('"no_draw"', '"no_energy_gain"', '"no_block_gain"', '"dex_decay"', '"lose_strength"', '"lose_dexterity"',
                 '"echo_form"', '"card_type": "skill", "count": 2', '"card_type": "attack"', '"card_type": "power"',
                 '"card_type": "all"', '"op": "block_next_turn", "amount": 6', '"scale": "block"', '"retain_hand"',
                 '"cost_shift"'):
        check(need in flat, f"the tester exercises {need}")
    names = {c["name"] for c in mod.CARDS}
    for base in ("Battle Trance", "Panic Button", "Wraith Form", "Burst", "Echo Form", "Prolong", "Equilibrium"):
        check(base in names, f"the tester carries the plan's {base}")
    check("--validate-only" in p.read_text(encoding="utf-8"), "the tester has a --validate-only flag")


def _t_smoke_record() -> None:
    print("the saved AutoSlay tag greps (TEST_AUDIT_2026-10 §7):")
    recs = [TESTER_DIR / f"godot_BM_tags_{s}.txt" for s in SMOKE_SEEDS]
    if not any(p.exists() for p in recs):
        print("  smoke pending (no godot_BM_tags_*.txt yet — the smoke runs after Ryan's go-ahead)")
        return
    seen = ""
    for p in recs:
        if not p.exists():
            print(f"  smoke pending for {p.name}")
            continue
        txt = p.read_text(encoding="utf-8")
        check("[BM]" in txt, f"{p.name} holds [BM] tags")
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
    check(r["index"] <= BP_INDEX_CEILING, "index within budget")
    check(r["archetype_max"] <= BP_ARCHETYPE_CEILING, "every archetype alone within its ceiling")
    check(r["archetype_scaffold_max"] <= BP_SCAFFOLD_BUDGET_PER_ARCHETYPE, "per-archetype scaffold within budget")
    check(all(n <= BP_TRIAD_BUDGET for n in r["triads"].values()), "the sample triads within their ceiling")
    check(r["all_ops"] <= BP_TOTAL_TRIPWIRE, "the all-ops path under the tripwire")


def main() -> int:
    test_version()
    _t_engine()
    _t_rules_and_describe()
    _t_contract()
    _t_tester()
    _t_smoke_record()
    _t_budget()
    print(f"\n{_PASS} passed, {_FAIL} failed")
    return 1 if _FAIL else 0


def test_phase_bm_all() -> None:
    global _PASS, _FAIL
    _PASS = _FAIL = 0
    assert main() == 0, f"{_FAIL} Phase BM check(s) failed - see the FAIL lines above"


if __name__ == "__main__":
    sys.exit(main())
