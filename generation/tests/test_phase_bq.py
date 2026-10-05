"""Phase BQ — orb extras (VOCAB_EXPANSION_6_PLAN, gap #78, vocab v68) — offline. Run:
uv run python -m tests.test_phase_bq  (from generation/)

Pins: the stamp; verify-first against the game sources (OrbModel.Passive is an empty virtual only OrbCmd.Passive calls,
OrbCmd.EvokeNext / EvokeLast / Passive / RemoveSlots, LoopPower, the base Dualcast / Darkness / Tesla Coil / Chill / Compile
Driver / Bulk Up recipes); the engine wiring (the ForgedOrb.Passive override FIRST, the evoke keep / newest, trigger_passive,
lose_orb_slot, per_enemy and orb-scale branches + their [BQ] tags, the orb_count_ge orb filter, the Loop status pipe and its
log-only tick patch, the importer's 3-slot rule); the validator rules on both sides; the describe byte-match (Python literals
asserted, the C# fragments grepped); the contract surfaces (schema, VOCABULARY rows, the loop status file, gate family + field
units, coverage, featured, harness_v2, class_forge, archetypes, exemplars, heuristics, gap log, render.js, the pitch sentence);
the tester's validate-only path (an ORB class with custom orbs, every BQ shape + the BP on_evoke proof); the saved AutoSlay tag
greps under tests/gaptest-bq/ when they exist ("smoke pending" until then); and prints the rule-0.9 readings.
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
TESTER_DIR = pathlib.Path(__file__).parent / "gaptest-bq"
SMOKE_SEEDS = ("GAPTESTBQ1", "GAPTESTBQ2")
MODREF = pathlib.Path(r"C:/Users/ryanr/Desktop/NOVOGODOT/BLANKthespire/_modref")

NEW_OPS = ("trigger_passive", "lose_orb_slot")
NEW_SCALES = ("orb_count", "orb_types")
NEW_TOKENS = NEW_OPS + ("loop",) + NEW_SCALES
TAGS = ("[BQ] passive override: '", "[BQ] evoke next keep=true -> '", "[BQ] evoke newest keep=false -> '",
        "(orbs=first)", "(orbs=all)", "[BQ] trigger_passive x", "[BQ] loop applied by 'Feedback Loop'", "[BQ] loop tick -> '",
        "[BQ] lose_orb_slot -> ", "[BQ] orb_types -> ", "[BQ] orb_count -> ", "[BQ] orb_count_ge[frost] -> ",
        "[BQ] orb_count_ge[ember] -> ", "[BQ] channel per_enemy x", "[BP] on_evoke fired")


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
    c = {"id": "bq_t", "name": "BQ", "type": ctype, "rarity": rarity, "cost": cost, "target": target, "effects": effects}
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
    return _card(effects, **kw)


_V = None


def _errs(card) -> list[str]:
    global _V
    if _V is None:
        _V = CardValidator(extra_orbs={"ember"})
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
    print("Phase BQ vocab stamp is at least 68 (Python + C#):")
    check(bts1.VOCAB_VERSION >= 68, f"bts1.VOCAB_VERSION >= 68, got {bts1.VOCAB_VERSION}")
    fc = _cs("Engine", "ForgedCards.cs")
    m = re.search(r"public const int VocabVersion = (\d+);", fc)
    check(m is not None and int(m.group(1)) >= 68, f"ForgedCards.VocabVersion >= 68, got {m and m.group(1)}")
    check(m is not None and bts1.VOCAB_VERSION <= int(m.group(1)), "bts1.VOCAB_VERSION <= ForgedCards.VocabVersion")
    check("68: Phase BQ" in fc and all(f"`{t}`" in fc for t in ("keep", "trigger_passive", "lose_orb_slot", "loop",
                                                                 "orb_count", "orb_types", "per_enemy")),
          "ForgedCards.cs comment names Phase BQ + the tokens")
    check("68: Phase BQ" in pathlib.Path(bts1.__file__).read_text(encoding="utf-8"), "bts1.py records the v68 entry")


def _t_verify_first() -> None:
    print("verify-first against the game sources (rule 0.6):")
    root = MODREF / "decomp_full"
    if not root.exists():
        print("  (decomp not on this machine — skipped, informational)")
        return
    om = (root / "MegaCrit.Sts2.Core.Models" / "OrbModel.cs").read_text(encoding="utf-8")
    check("public virtual Task Passive(PlayerChoiceContext choiceContext, Creature? target)\n\t{\n\t\treturn Task.CompletedTask;"
          in om.replace("\r\n", "\n"), "DECOMP OrbModel.Passive is an EMPTY virtual (the blocker)")
    oc = (root / "MegaCrit.Sts2.Core.Commands" / "OrbCmd.cs").read_text(encoding="utf-8")
    for sig in ("public static void RemoveSlots(Player player, int amount)",
                "public static async Task EvokeNext(PlayerChoiceContext choiceContext, Player player, bool dequeue = true)",
                "public static async Task EvokeLast(PlayerChoiceContext choiceContext, Player player, bool dequeue = true)",
                "public static async Task Passive(PlayerChoiceContext choiceContext, OrbModel orb, Creature? target)",
                "OrbModel orb = orbQueue.Orbs.Last();", "await orb.Passive(choiceContext, target);",
                "if (player.Character.BaseOrbSlotCount == 0 && orbQueue.Capacity == 0)"):
        check(sig in oc, f"DECOMP OrbCmd: {sig[:70]}")
    # Only OrbCmd.Passive calls OrbModel.Passive — so the ForgedOrb override cannot double-fire with the per-turn tick.
    callers = [p for p in root.rglob("*.cs") if "orb.Passive(" in p.read_text(encoding="utf-8", errors="ignore")]
    check([p.name for p in callers] == ["OrbCmd.cs"], f"DECOMP: only OrbCmd calls orb.Passive (got {[p.name for p in callers]})")
    lp = (root / "MegaCrit.Sts2.Core.Models.Powers" / "LoopPower.cs").read_text(encoding="utf-8")
    check("public override async Task AfterPlayerTurnStart(PlayerChoiceContext choiceContext, Player player)" in lp
          and "await OrbCmd.Passive(choiceContext, player.PlayerCombatState.OrbQueue.Orbs[0], null);" in lp
          and "PowerStackType.Counter" in lp, "DECOMP LoopPower: Counter, OrbCmd.Passive on Orbs[0] x Amount at turn start")
    cards = root / "MegaCrit.Sts2.Core.Models.Cards"
    dc = (cards / "Dualcast.cs").read_text(encoding="utf-8")
    check("OrbCmd.EvokeNext(choiceContext, base.Owner, dequeue: false);" in dc and "await OrbCmd.EvokeNext(choiceContext, base.Owner);" in dc,
          "DECOMP Dualcast: keep pass then normal pass")
    check("OrbCmd.Passive(choiceContext, darknessOrb, null)" in (cards / "Darkness.cs").read_text(encoding="utf-8"), "DECOMP Darkness")
    check("OrbCmd.Passive(choiceContext, lightningOrb, cardPlay.Target)" in (cards / "TeslaCoil.cs").read_text(encoding="utf-8"),
          "DECOMP Tesla Coil (the played target)")
    check("base.CombatState.HittableEnemies" in (cards / "Chill.cs").read_text(encoding="utf-8"), "DECOMP Chill (per hittable enemy)")
    check("group orb by orb.Id" in (cards / "CompileDriver.cs").read_text(encoding="utf-8"), "DECOMP Compile Driver (distinct orbs)")
    check("OrbCmd.RemoveSlots(base.Owner" in (cards / "BulkUp.cs").read_text(encoding="utf-8"), "DECOMP Bulk Up (RemoveSlots)")


def _t_engine() -> None:
    print("the engine: the Passive override, the orb-extras branches, the Loop pipe, the tags:")
    fo = _cs("Powers", "ForgedOrb.cs")
    check("public override Task Passive(PlayerChoiceContext choiceContext, Creature? target)" in fo
          and "return OrbRunner.RunPassive(s, this, choiceContext, target);" in fo and "if (s == null) return Task.CompletedTask;" in fo,
          "ForgedOrb overrides OrbModel.Passive -> OrbRunner.RunPassive (null Source = no-op)")
    check("[BQ] passive override: '{s.Name}' passive via OrbRunner" in fo, "the [BQ] passive override tag")
    tick = fo.split("public override Task BeforeTurnEndOrbTrigger", 1)[1].split("public override Task Passive", 1)[0]
    check("Passive(" not in tick.replace("RunPassive(", ""), "the per-turn tick never calls Passive (no double-fire)")
    er = _cs("Engine", "EffectRunner.cs")
    for frag, why in (
            ("await OrbCmd.EvokeNext(ctx, card.Owner, dequeue: false);\n                            await OrbCmd.EvokeNext(ctx, card.Owner, dequeue: true);",
             "evoke keep = Dualcast (keep pass + normal pass)"),
            ("await OrbCmd.EvokeLast(ctx, card.Owner, dequeue: true);", "evoke which newest = EvokeLast"),
            ("[BQ] evoke next keep=true -> '", "the keep tag"), ("[BQ] evoke newest keep=false -> '", "the newest tag"),
            ('case "trigger_passive":', "trigger_passive branch"),
            ('var orbs = e.Orbs == "all" ? pq.Orbs.ToList() : pq.Orbs.Take(1).ToList();', "first | all (snapshotted)"),
            ("await OrbCmd.Passive(ctx, o, play?.Target);", "OrbCmd.Passive at the played target (Tesla Coil)"),
            ("[BQ] trigger_passive x{times} on '{OrbName(o)}' (orbs={e.Orbs ?? \"first\"})", "the trigger_passive tag"),
            ('case "lose_orb_slot":', "lose_orb_slot branch"), ("OrbCmd.RemoveSlots(card.Owner, 1);", "RemoveSlots(1)"),
            ("if (capBefore <= 1)", "never below 1 slot"), ("[BQ] lose_orb_slot -> {sq.Capacity}", "the lose_orb_slot tag"),
            ("count = card.Owner.Creature.CombatState.HittableEnemies.Count;", "per_enemy = HittableEnemies.Count (Chill)"),
            ("[BQ] channel per_enemy x{count}", "the per_enemy tag"),
            ('"orb_types"                  => card.Owner?.PlayerCombatState?.OrbQueue?.Orbs?.Select(o => o.GetType()).Distinct().Count() ?? 0,',
             "scale orb_types = distinct GetType()"),
            ('if (e.Scale is "orb_count" or "orb_types")', "the scale tags"),
            ("[BQ] {e.Scale} -> {n} ('{spec.Title ?? spec.Id}') (draw).", "the draw scale tag"),
            ('internal static readonly HashSet<string> BmSelfStatuses = new(SelfDebuffStatuses) { "echo_form",\n        "loop" };',
             "loop rides the card-only self-status pipe"),
            ('"loop"           => RelicApplyT<LoopPower>(ctx, target, source, amount),', "loop = the base LoopPower"),
            ("[BQ] loop applied by '{src}'", "the loop applied tag")):
        check(frag in er, f"EffectRunner: {why}")
    lt = _cs("Engine", "LoopTickTagPatch.cs")
    check("[HarmonyPatch(typeof(LoopPower), nameof(LoopPower.AfterPlayerTurnStart))]" in lt and "private static void Prefix(" in lt
          and "[BQ] loop tick -> '" in lt and "return false" not in lt, "LoopTickTagPatch: a log-only prefix (never skips the original)")
    co = _cs("Engine", "Conditions.cs")
    for frag in ("if (c.Orb != null) return OrbsOfType(player, c.Orb, c.Value);",
                 "System.Type? type = k > 0 ? ForgedCharacters.ResolveOrbType(k, orb) : null;",
                 'if (type == null && orb is "lightning" or "frost" or "dark") type = EffectRunner.OrbTypeFor(orb);',
                 "[BQ] orb_count_ge[{orb}] -> ", 'c.Orb != null ? $"you have {c.Value}+ {ForgedCards.OrbDisplay(c.Orb)} orbs"'):
        check(frag in co, f"Conditions: {frag[:70]}")
    spec = _cs("Engine", "CardSpec.cs")
    check("bool Keep = false," in spec and "string? Which = null," in spec and "string? Orbs = null," in spec
          and "bool PerEnemy = false" in spec and "string? Orb = null);" in spec, "EffectSpec Keep / Which / Orbs / PerEnemy + Condition.Orb")
    dc = _cs("Engine", "DataCard.cs")
    check('case "trigger_passive":' in dc and 'case "lose_orb_slot":' in dc
          and 'case "loop":           Power<LoopPower>(vname, e.Amount, up); break;' in dc, "DataCard declares the new ops + Loop's hover tip")
    fc = _cs("Engine", "ForgedCards.cs")
    check(set(NEW_OPS) <= _set(fc, "SupportedOps") and not (set(NEW_OPS) & _set(fc, "TriggerOps")), "the two ops: supported, card-only")
    check("loop" in _set(fc, "SupportedStatuses") and set(NEW_SCALES) <= _set(fc, "SupportedScales"), "loop status + the two scales")
    for frag in ("bool keep = e.ContainsKey(\"keep\") && e[\"keep\"].AsBool();", "string? which = e.ContainsKey(\"which\")",
                 "string? orbs = e.ContainsKey(\"orbs\")", "bool perEnemy = e.ContainsKey(\"per_enemy\")",
                 'w.ContainsKey("orb") ? Str(w, "orb").Trim().ToLowerInvariant() : null);',
                 "'keep' / 'which' only apply to evoke", "evoke 'keep' evokes your NEXT orb twice", "trigger_passive 'amount' (times) must be 1..",
                 "lose_orb_slot loses ONE orb slot", "channel_orb 'per_enemy' channels ONE orb per enemy",
                 "a condition 'orb' filter only applies to orb_count_ge", "'loop' belongs on a POWER card",
                 "lose_orb_slot needs a Power or an Exhaust card", "are not allowed in a trigger payload (card-only orb extras)",
                 "internal const int LoseOrbSlotMinSlots = 3;"):
        check(frag in fc, f"ForgedCards: {frag[:70]}")
    ch = _cs("Engine", "ForgedCharacters.cs")
    check("cspec.OrbSlots < ForgedCards.LoseOrbSlotMinSlots" in ch, "the importer rejects lose_orb_slot on a class with < 3 slots")


CASES = [([{"op": "evoke", "keep": True}], "self", "Evoke your next orb twice."),
         ([{"op": "evoke", "which": "newest"}, {"op": "block", "amount": 5}], "self", "Evoke your newest orb.\nGain {Block} Block."),
         ([{"op": "evoke", "which": "newest", "amount": 2}], "self", "Evoke your 2 newest orbs."),
         ([{"op": "evoke", "amount": 2}], "self", "Evoke 2 times."),
         ([{"op": "channel_orb", "orb": "dark"}, {"op": "trigger_passive", "amount": 2}], "self",
          "Channel a Dark orb.\nTrigger the passive of your next orb 2 times."),
         ([{"op": "trigger_passive"}], "self", "Trigger the passive of your next orb."),
         ([{"op": "damage", "amount": 3}, {"op": "trigger_passive", "orbs": "all", "amount": 1}], "enemy",
          "Deal {Damage} damage.\nTrigger the passive of all your orbs."),
         ([{"op": "trigger_passive", "orbs": "all", "amount": 2}], "self", "Trigger the passive of all your orbs 2 times."),
         ([{"op": "apply_status", "status": "loop", "amount": 1}], "self", "At the start of your turn, trigger your next orb's passive."),
         ([{"op": "lose_orb_slot"}, {"op": "apply_status", "status": "strength", "amount": 2}], "self",
          "Lose 1 Orb Slot.\nGain Strength."),
         ([{"op": "damage", "amount": 7}, {"op": "draw", "amount": 1, "scale": "orb_types"}], "enemy",
          "Deal {Damage} damage.\nDraw cards equal to the different orbs you have channeled."),
         ([{"op": "damage", "amount": 1, "scale": "orb_count"}], "all_enemies", "Deal damage equal to the orbs you have channeled to ALL enemies."),
         ([{"op": "block", "amount": 1, "scale": "orb_count"}], "self", "Gain Block equal to the orbs you have channeled."),
         ([{"op": "block", "amount": 6}, {"op": "draw", "amount": 1, "when": {"kind": "orb_count_ge", "value": 2, "orb": "frost"}}], "self",
          "Gain {Block} Block.\nDraw {Cards} card(s) if you have 2+ Frost orbs."),
         ([{"op": "damage", "amount": 6, "when": {"kind": "orb_count_ge", "value": 1, "orb": "ember"}}], "enemy",
          "Deal {Damage} damage if you have 1+ Ember orbs."),
         ([{"op": "channel_orb", "orb": "frost", "per_enemy": True}, {"op": "exhaust"}], "self", "Channel a Frost orb for each enemy.\nExhaust.")]
C_FRAGMENTS = ('parts.Add(e.PerEnemy ? $"Channel a {orbName} orb for each enemy."',
               'parts.Add(e.Keep ? "Evoke your next orb twice."',
               ': e.Which == "newest" ? (ec > 1 ? $"Evoke your {ec} newest orbs." : "Evoke your newest orb.")',
               'case "trigger_passive": parts.Add(TriggerPassiveSentence(e)); break;',
               'string whose = e.Orbs == "all" ? "all your orbs" : "your next orb";',
               'return n > 1 ? $"Trigger the passive of {whose} {n} times." : $"Trigger the passive of {whose}.";',
               'case "lose_orb_slot":   parts.Add("Lose 1 Orb Slot."); break;',
               '"loop"           => "At the start of your turn, trigger your next orb\'s passive.",',
               '"orb_count"                   => "the orbs you have channeled",',
               '"orb_types"                   => "the different orbs you have channeled",')


def _t_rules_and_describe() -> None:
    print("validator + describe (Python literal == the C# fragment written by hand):")
    ok = [_card([{"op": "evoke", "keep": True}], up_cost=0),
          _card([{"op": "evoke", "which": "newest", "amount": 2}]),
          _card([{"op": "evoke", "which": "next"}]),
          _card([{"op": "channel_orb", "orb": "dark"}, {"op": "trigger_passive", "amount": 3}]),
          _atk([{"op": "damage", "amount": 3}, {"op": "trigger_passive", "orbs": "all", "amount": 2}], cost=0),
          _pow([{"op": "apply_status", "status": "loop", "amount": 1}], up_cost=0),
          _pow([{"op": "lose_orb_slot"}, {"op": "apply_status", "status": "strength", "amount": 2}], cost=2),
          _card([{"op": "lose_orb_slot", "amount": 1}, {"op": "draw", "amount": 3}, {"op": "exhaust"}]),
          _atk([{"op": "damage", "amount": 7}, {"op": "draw", "amount": 1, "scale": "orb_types"}]),
          _atk([{"op": "damage", "amount": 1, "scale": "orb_count"}]),
          _card([{"op": "block", "amount": 1, "scale": "orb_types"}]),
          _card([{"op": "block", "amount": 6}, {"op": "draw", "amount": 1, "when": {"kind": "orb_count_ge", "value": 2, "orb": "frost"}}]),
          _card([{"op": "block", "amount": 6}, {"op": "draw", "amount": 1, "when": {"kind": "orb_count_ge", "value": 1, "orb": "ember"}}]),
          _card([{"op": "channel_orb", "orb": "frost", "per_enemy": True}, {"op": "exhaust"}], cost=0)]
    for c in ok:
        check(not _errs(c), f"validates: {json.dumps(c['effects'])} -> {_errs(c)}")
    bad = [(_card([{"op": "evoke", "keep": True, "amount": 2}]), ""),
           (_card([{"op": "evoke", "keep": True, "which": "newest"}]), "never with which 'newest'"),
           (_card([{"op": "evoke", "which": "oldest"}]), ""),
           (_card([{"op": "draw", "amount": 1, "keep": True}]), ""),
           (_card([{"op": "trigger_passive", "amount": 4}]), ""),
           (_card([{"op": "trigger_passive", "orbs": "all", "amount": 3}]), "1..2"),
           (_card([{"op": "trigger_passive", "orbs": "some"}]), ""),
           (_card([{"op": "draw", "amount": 1, "orbs": "all"}]), ""),
           (_card([{"op": "apply_status", "status": "loop", "amount": 1}]), "POWER"),
           (_pow([{"op": "apply_status", "status": "loop", "amount": 2}]), "loop"),
           (_pow([{"op": "apply_status", "status": "loop", "amount": 1}], rarity="basic"), ""),
           (_card([{"op": "lose_orb_slot"}, {"op": "draw", "amount": 3}]), "Power or an Exhaust card"),
           (_card([{"op": "lose_orb_slot"}, {"op": "draw", "amount": 3}, {"op": "exhaust"}],
                  upgrade=[{"op": "lose_orb_slot"}, {"op": "draw", "amount": 4}]), "Power or an Exhaust card"),
           (_pow([{"op": "lose_orb_slot", "amount": 2}]), ""),
           (_pow([{"op": "lose_orb_slot"}, {"op": "lose_orb_slot"}, {"op": "draw", "amount": 4}]), "at most one lose_orb_slot"),
           (_pow([{"op": "lose_orb_slot"}], rarity="basic"), ""),
           (_card([{"op": "channel_orb", "orb": "frost", "per_enemy": True, "amount": 2}]), ""),
           (_card([{"op": "block", "amount": 5, "per_enemy": True}]), ""),
           (_card([{"op": "block", "amount": 6, "when": {"kind": "hand_size_ge", "value": 2, "orb": "frost"}}]), ""),
           (_card([{"op": "block", "amount": 6, "when": {"kind": "orb_count_ge", "value": 2, "orb": "random"}}]), ""),
           (_card([{"op": "block", "amount": 6, "when": {"kind": "orb_count_ge", "value": 2, "orb": "plasma"}}]), "not a valid orb"),
           (_card([{"op": "draw", "amount": 1, "scale": "orb_count"}, {"op": "apply_status", "status": "weak", "amount": 1, "scale": "orb_types"}]), ""),
           (_pow([{"op": "add_trigger", "trigger": "turn_start", "effects": [{"op": "trigger_passive", "amount": 1}]}]), ""),
           (_pow([{"op": "add_trigger", "trigger": "turn_start", "effects": [{"op": "evoke", "keep": True}]}]), ""),
           (_pow([{"op": "add_trigger", "trigger": "turn_start", "effects": [{"op": "block", "amount": 2, "scale": "orb_count"}]}]), "")]
    for c, frag in bad:
        e = _errs(c)
        check(bool(e) and any(frag in x for x in e), f"rejected ({frag or 'any'}): {json.dumps(c['effects'])} -> {e}")
    v = _V
    check(v._score_effect({"op": "trigger_passive", "amount": 2}) == 6.0 and v._score_effect({"op": "trigger_passive", "orbs": "all"}) == 7.0
          and v._score_effect({"op": "lose_orb_slot"}) == -5.0, "priced: trigger_passive 3 / 7 per time, lose_orb_slot -5")
    for effects, target, want in CASES:
        got = cardgen.describe(effects, target)
        check(got == want, f"describe {got!r} == {want!r}")
    src = _cs("Engine", "ForgedCards.cs")
    for frag in C_FRAGMENTS:
        check(frag in src, f"C# Describe fragment: {frag}")
    for e, want in (({"op": "evoke", "keep": True}, 'new EffectSpec("evoke", 0, Keep: true)'),
                    ({"op": "evoke", "which": "newest", "amount": 2}, 'new EffectSpec("evoke", 2, Which: "newest")'),
                    ({"op": "trigger_passive", "amount": 2}, 'new EffectSpec("trigger_passive", 2)'),
                    ({"op": "trigger_passive", "orbs": "all", "amount": 1}, 'new EffectSpec("trigger_passive", 1, Orbs: "all")'),
                    ({"op": "lose_orb_slot"}, 'new EffectSpec("lose_orb_slot", 0)'),
                    ({"op": "channel_orb", "orb": "frost", "per_enemy": True},
                     'new EffectSpec("channel_orb", 0, null, 1, null, "frost", PerEnemy: true)'),
                    ({"op": "draw", "amount": 1, "scale": "orb_types"}, 'new EffectSpec("draw", 1, null, 1, "orb_types")'),
                    ({"op": "draw", "amount": 1, "when": {"kind": "orb_count_ge", "value": 2, "orb": "frost"}},
                     'new EffectSpec("draw", 1, When: new Condition("orb_count_ge", 2, null, false, Orb: "frost"))')):
        got = cardgen.effect_literal(e)
        check(got == want, f"effect_literal {got!r} == {want!r}")
    check(cardgen.cond_phrase({"kind": "orb_count_ge", "value": 3}) == "you have 3+ orbs", "the unfiltered phrase is unchanged")


def _t_contract() -> None:
    print("contract surfaces:")
    schema = json.loads(CARD_SCHEMA.read_text(encoding="utf-8"))
    eff = schema["$defs"]["effect"]
    check(set(NEW_OPS) <= set(eff["properties"]["op"]["enum"]), "schema: op enum += trigger_passive / lose_orb_slot")
    check(eff["properties"]["keep"]["type"] == "boolean" and eff["properties"]["which"]["enum"] == ["next", "newest"]
          and eff["properties"]["orbs"]["enum"] == ["first", "all"] and eff["properties"]["per_enemy"]["type"] == "boolean",
          "schema: the keep / which / orbs / per_enemy fields")
    check(set(NEW_SCALES) <= set(eff["properties"]["scale"]["enum"]) and "loop" in eff["properties"]["status"]["enum"],
          "schema: scale enum += orb_count / orb_types, status enum += loop")
    te = schema["$defs"]["triggerEffect"]
    check(not (set(NEW_OPS) & set(te["properties"]["op"]["enum"])) and "loop" not in te["properties"]["status"]["enum"]
          and not ({"keep", "which", "orbs", "per_enemy"} & set(te["properties"])), "schema: nothing new reaches a payload")
    cond = schema["$defs"]["condition"]
    check("orb" in cond["properties"] and '"kind": {"const": "orb_count_ge"}' in json.dumps(cond["allOf"]), "schema: the condition orb filter")
    check((paths.VOCABULARY.parent / "statuses" / "loop.json").exists(), "mod/contract/statuses/loop.json")
    vocab = paths.VOCABULARY.read_text(encoding="utf-8")
    idx = gate.vocab_index(vocab)
    for t in NEW_OPS:
        check(vocab.count(f"| `{t}`") == 1 and f"`{t}`" in idx, f"VOCABULARY: ONE {t} row (+ its index name)")
    for t in ("`loop`", "`orb_count` / `orb_types`", '`orb:"frost"`', "`keep:true`", '`which:"newest"`', "`per_enemy:true`",
              "optional `orb` (v68)"):
        check(t in vocab, f"VOCABULARY names {t}")
    orbs_sec = vocab.split("## Orbs", 1)[1].split("\n## ", 1)[0]
    check("**Orb extras (v68):**" in orbs_sec and "`loop`" in orbs_sec, "VOCABULARY: the orb extras live in the Orbs section")
    stat_sec = vocab.split("## Statuses", 1)[1].split("\n## ", 1)[0]
    check("`loop`" not in stat_sec, "VOCABULARY: loop is NOT a core Statuses row (orb forges only)")
    check(set(NEW_OPS) <= set(gate.FAMILY_OPS["orbs"]) and not (set(NEW_OPS) & set(gate.GATED_OP_ORDER)),
          "gate: the two ops ride the orb family (normal classes never pay)")
    check(gate.FIELD_UNITS["keep"] == ("evoke",) and gate.FIELD_UNITS["which"] == ("evoke",)
          and gate.FIELD_UNITS["orbs"] == ("trigger_passive",) and gate.FIELD_UNITS["per_enemy"] == ("channel_orb",),
          "gate.FIELD_UNITS: keep / which / orbs / per_enemy")
    kinds = {k: kind for k, _d, kind in coverage.SCALE_MENU_KIND}
    check(kinds.get("orb_count") == "orb" and kinds.get("orb_types") == "orb", "coverage: SCALE_MENU_KIND orb entries")
    plain = census.walk_card(_atk([{"op": "damage", "amount": 6}]))
    for k, c in (("orb_count", _atk([{"op": "damage", "amount": 1, "scale": "orb_count"}])),
                 ("orb_types", _card([{"op": "draw", "amount": 1, "scale": "orb_types"}]))):
        check(coverage.CENSUS_DETECTOR[k](census.walk_card(c)) and not coverage.CENSUS_DETECTOR[k](plain), f"the {k} detector")
    check(coverage.KEY_KIND.get("orb_count") == "orb" and coverage.KEY_KIND.get("orb_types") == "orb", "coverage: the orb scales are orb-gated")
    orb_feats = {f.id: f for f in featured.FEATURED_CLASS_KIND["orb"]}
    check({"orb_passive_pump", "orb_census"} <= set(orb_feats), "featured: the two orb entries")
    check(orb_feats["orb_passive_pump"].detect(census.walk_card(_card([{"op": "trigger_passive", "amount": 2}])))
          and orb_feats["orb_passive_pump"].detect(census.walk_card(_pow([{"op": "apply_status", "status": "loop", "amount": 1}])))
          and orb_feats["orb_census"].detect(census.walk_card(_atk([{"op": "damage", "amount": 1, "scale": "orb_count"}])))
          and not orb_feats["orb_census"].detect(plain), "featured: the detectors")
    check({"trigger_passive", "lose_orb_slot", "loop", "orb_types"} <= harness_v2._CLASS_ONLY_TOKENS, "harness_v2: class-only tokens")
    for c in (_card([{"op": "trigger_passive"}]), _pow([{"op": "apply_status", "status": "loop", "amount": 1}]),
              _pow([{"op": "lose_orb_slot"}]), _atk([{"op": "damage", "amount": 1, "scale": "orb_types"}]),
              _atk([{"op": "damage", "amount": 1, "scale": "orb_count"}])):
        check(cf._card_uses_orbs(c), f"class_forge: orb-class only ({c['effects'][0]})")
    check(cf._LOSE_ORB_SLOT_MIN_SLOTS == 3 and cf._card_loses_orb_slot(_pow([{"op": "lose_orb_slot"}])), "class_forge: the 3-slot rule")
    src = pathlib.Path(cf.__file__).read_text(encoding="utf-8")
    check("v68 extras: evoke `keep` (Dualcast) / `which` newest, \\\n`trigger_passive`, `loop`, `lose_orb_slot`, scales `orb_count` / "
          "`orb_types`, `per_enemy` channel (Chill)." in src, "class_forge: ONE short ORB pitch sentence")
    toks = bridges.card_tokens(_pow([{"op": "lose_orb_slot"}, {"op": "apply_status", "status": "loop", "amount": 1}]))
    check({"lose_orb_slot", "loop"} <= toks, "bridges: the new tokens surface")
    arch = {a["id"]: a for a in json.loads((DATA / "archetypes.json").read_text(encoding="utf-8"))["archetypes"]}
    for aid, toks_want in (("orb_channel", {"trigger_passive", "loop", "lose_orb_slot", "orb_types"}), ("slot_machine", {"orb_count"})):
        a = arch[aid]
        check(toks_want <= set(a["vocabulary"]["ops"]), f"{aid} claims {sorted(toks_want)}")
        check("VOCABULARY_GAPS#78" in a["gap_refs"] and a["buildable"] is True, f"{aid} refs #78")
        check("(v68)" in a.get("build_notes", ""), f"{aid} build_notes name the v68 shapes")
    pool = json.loads((DATA / "exemplar_pool.json").read_text(encoding="utf-8"))["exemplars"]
    v = harness_v2.exemplar_validator()
    used, fields = set(), set()
    for e in pool:
        flat = json.dumps(e["card"])
        hit = set(NEW_TOKENS) & bridges.card_tokens(e["card"])
        for f in ('"keep": true', '"which": "newest"', '"per_enemy": true', '"orb": "frost"}', '"orbs": "all"'):
            if f in flat:
                fields.add(f)
                hit.add(f)
        if not hit:
            continue
        used |= hit
        r = v.validate(dict(e["card"]))
        check(r.ok, f"exemplar {e['card']['id']} validates: {r.errors}")
        check(e.get("needs") == "orb", f"exemplar {e['card']['id']} needs orb")
    check(set(NEW_TOKENS) <= used, f"exemplars cover every new token (got {sorted(used)})")
    check(len(fields) == 5, f"exemplars show keep / which newest / per_enemy / the orb filter / orbs all: {sorted(fields)}")
    heur = (paths.VOCABULARY.parent / "DESIGN_HEURISTICS.md").read_text(encoding="utf-8")
    check(heur.count("(v68") >= 2, "DESIGN_HEURISTICS: the v68 notes on orb_channel + slot_machine")
    gaps_md = (REPO / "VOCABULARY_GAPS.md").read_text(encoding="utf-8")
    entry = gaps_md.split("### 78.", 1)[1].split("### 79.", 1)[0]
    check("**Status:** **done (2026-10-04, vocab v68, Phase BQ)**" in entry and "v69" not in entry, "gap #78 is done (v68)")
    js = (REPO / "web" / "static" / "render.js").read_text(encoding="utf-8")
    for frag in ('if (e.keep) return "Evoke your next orb twice";', 'case "trigger_passive":', 'case "lose_orb_slot": return "Lose 1 Orb Slot";',
                 'for each enemy`', 'orb_types: "the different orbs you have channeled"', "c.orb ? `you have",
                 "loop: () => \"At the start of your turn, trigger your next orb's passive\""):
        check(frag in js, f"render.js: {frag[:60]}")
    plan = (REPO / "docs" / "plans" / "VOCAB_EXPANSION_6_PLAN.md").read_text(encoding="utf-8")
    check("**Findings (BQ" in plan and "**Phase BQ" in plan and "### Phase BQ — Orb extras (v68" in plan,
          "the plan records the BQ findings + status line (v68)")


def _t_tester() -> None:
    print("the tester (validate-only path):")
    p = TESTER_DIR / "build_tester.py"
    check(p.exists(), "tests/gaptest-bq/build_tester.py exists")
    spec = importlib.util.spec_from_file_location("bq_tester", p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    check(mod.validate(verbose=True) == 0, "every tester card + the orb pool validates")
    check(mod.CHARACTER["orb_slots"] >= 3 and any(isinstance(o, dict) for o in mod.ORB_POOL),
          "an ORB class (3+ slots) with custom orbs (the Passive override needs one)")
    types = [c["type"] for c in mod.CARDS if c["rarity"] != "basic"]
    check(types.count("attack") >= 3 and types.count("skill") >= 3 and types.count("power") >= 1,
          "pool: >= 3 non-basic Attacks + Skills and >= 1 Power (the merchant stall)")
    check(90 <= mod.CHARACTER["max_hp"] <= 110, "max HP ~100")
    flat = json.dumps(mod.CARDS)
    for need in ('"keep": true', '"which": "newest"', '"op": "trigger_passive", "amount": 2', '"orbs": "all"',
                 '"status": "loop"', '"op": "lose_orb_slot"', '"scale": "orb_types"', '"scale": "orb_count"',
                 '"orb": "frost"}', '"orb": "ember"}', '"per_enemy": true', '"trigger": "on_evoke"', '"status": "strength"'):
        check(need in flat, f"the tester exercises {need}")
    text = p.read_text(encoding="utf-8")
    check("--validate-only" in text and "--character class4" in text and "GAPTESTBQ1 GAPTESTBQ2" in text
          and "[BP] on_evoke fired" in text and "NO DOUBLE-FIRE" in text, "the docstring is the complete smoke recipe")


def _t_smoke_record() -> None:
    print("the saved AutoSlay tag greps (TEST_AUDIT_2026-10 §7):")
    files = [TESTER_DIR / f"godot_BQ_tags_{s}.txt" for s in SMOKE_SEEDS]
    if not any(p.exists() for p in files):
        print("  smoke pending (no godot_BQ_tags_<SEED>.txt yet — the BN agent runs BQ's smoke with BN's)")
        return
    seen = ""
    for p in files:
        assert p.exists(), f"missing smoke record {p}"
        txt = p.read_text(encoding="utf-8")
        check("[BQ]" in txt, f"{p.name} holds [BQ] tags")
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


def test_phase_bq_all() -> None:
    global _PASS, _FAIL
    _PASS = _FAIL = 0
    assert main() == 0, f"{_FAIL} Phase BQ check(s) failed - see the FAIL lines above"


if __name__ == "__main__":
    sys.exit(main())
