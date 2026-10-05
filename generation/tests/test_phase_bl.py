"""Phase BL — enemy Strength loss, strip Block / Artifact, Doom (VOCAB_EXPANSION_6_PLAN, gaps #66 / #67, vocab v64)
— offline. Run:  uv run python -m tests.test_phase_bl  (from generation/)

Pins: the stamp; the engine wiring (the Debuff-typed ForgedTempStrengthDownPower shell — the Artifact sign-flip fix —
the NEGATIVE literal apply of the permanent strength_down, the Expose LoseBlock / Remove<ArtifactPower> calls, every
Doom site copied from poison, the Blight Strike widening of damage_dealt_unblocked, the [BL] tags, the decision-12
debuff count); the validator rules on both sides; the describe byte-match (Python literals asserted, the C# fragments
grepped); the contract surfaces (schema, VOCABULARY rows, statuses/*.json, gate order, census, coverage, featured,
archetypes, exemplars, heuristics, gap log, render.js, the pitch sentence, the per-class Doom warning); the tester's
validate-only path; the saved AutoSlay tag greps under tests/gaptest-bl/ (GAPTESTBL1 / BL2); and prints the rule-0.9
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
from btsgen.character_validator import doom_warnings  # noqa: E402
from btsgen.validator import CardValidator  # noqa: E402

_PASS = 0
_FAIL = 0
MOD_CODE = paths.VOCABULARY.parents[1] / "BlankTheSpireCode"
CARD_SCHEMA = paths.VOCABULARY.parent / "card.schema.json"
REPO = paths.VOCABULARY.parents[2]
DATA = pathlib.Path(cf.__file__).parent / "data"
TESTER_DIR = pathlib.Path(__file__).parent / "gaptest-bl"
SMOKE_SEEDS = ("GAPTESTBL1", "GAPTESTBL2")
MODREF = pathlib.Path(r"C:/Users/ryanr/Desktop/NOVOGODOT/BLANKthespire/_modref")

NEW_STATUSES = ("temp_strength_down", "strength_down", "doom")
NEW_OPS = ("strip_block", "strip_artifact")
TAGS = ("[BL] temp_strength_down +", "[BL] temp_strength_down expired (Str now ", "[BL] strength_down -",
        "[BL] strip_block ", "[BL] strip_artifact (had ", "[BL] doom +", "[BL] doom from unblocked ",
        "[BL] artifact check: ")


def check(cond: bool, msg: str) -> None:
    global _PASS, _FAIL
    if cond:
        _PASS += 1
    else:
        _FAIL += 1
        print(f"  FAIL: {msg}")


def _cs(*parts: str) -> str:
    return (MOD_CODE.joinpath(*parts)).read_text(encoding="utf-8").replace("\r\n", "\n")


def _card(effects, rarity="uncommon", cost=1, ctype="skill", target="enemy", upgrade=None):
    c = {"id": "bl_t", "name": "BL", "type": ctype, "rarity": rarity, "cost": cost, "target": target, "effects": effects}
    if upgrade is not None:
        c["upgrade"] = {"effects": upgrade}
    return c


def _st(status, amount, **kw):
    e = {"op": "apply_status", "status": status, "amount": amount}
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
    print("Phase BL vocab stamp is at least 64 (Python + C#):")
    check(bts1.VOCAB_VERSION >= 64, f"bts1.VOCAB_VERSION >= 64, got {bts1.VOCAB_VERSION}")
    fc = _cs("Engine", "ForgedCards.cs")
    m = re.search(r"public const int VocabVersion = (\d+);", fc)
    check(m is not None and int(m.group(1)) >= 64, f"ForgedCards.VocabVersion >= 64, got {m and m.group(1)}")
    check(m is not None and bts1.VOCAB_VERSION <= int(m.group(1)), "bts1.VOCAB_VERSION <= ForgedCards.VocabVersion")
    check("64: Phase BL" in fc and "`temp_strength_down`" in fc and "`strip_block`" in fc and "`doom`" in fc,
          "ForgedCards.cs comment names Phase BL + the tokens")
    check("64: Phase BL" in pathlib.Path(bts1.__file__).read_text(encoding="utf-8"), "bts1.py records the v64 entry")


def _t_engine() -> None:
    print("the engine: the Debuff shell, the negative literal, Expose, every Doom site, the tags:")
    tp = _cs("Powers", "ForgedTempStatPowers.cs")
    body = tp[tp.index("public sealed class ForgedTempStrengthDownPower : ForgedTempStatPower"):]
    check("public override PowerType Type => PowerType.Debuff;" in body,
          "ForgedTempStrengthDownPower overrides Type => PowerType.Debuff (MANDATORY: the Artifact sign-flip fix)")
    check("public override PowerModel InternallyAppliedPower => ModelDb.Power<StrengthPower>();" in body,
          "the shell's internal power is StrengthPower")
    check("protected override bool InvertInternalPowerAmount => true;" in body, "InvertInternalPowerAmount => true")
    check('$"[BL] temp_strength_down expired (Str now {owner!.GetPowerAmount<StrengthPower>()}) on "' in body,
          "the [BL] expiry tag (at the OWNER's side-turn end)")
    check("Loses {Amount} Strength until the end of its turn." in body, "the tooltip (smartDescription, Amount)")
    # verify-first: why the override is needed (BaseLib) + the base twin it copies (DECOMP)
    bl = MODREF / "BaseLib-StS2" / "Abstracts" / "CustomTemporaryPowerModel.cs"
    if bl.exists():
        src = bl.read_text(encoding="utf-8")
        check("public override PowerType Type => InternallyAppliedPower.Type;" in src,
              "BaseLib: the shell's Type is the INTERNAL power's (Buff for Strength) — hence the override")
        check("InvertInternalPowerAmount ? Amount : -Amount" in src, "BaseLib: the restore re-applies +Amount at expiry")
    pw = MODREF / "decomp_full" / "MegaCrit.Sts2.Core.Models.Powers" / "PiercingWailPower.cs"
    if pw.exists():
        check("protected override bool IsPositive => false;" in pw.read_text(encoding="utf-8"),
              "DECOMP: PiercingWailPower is a non-positive (Debuff) TemporaryStrengthPower")
    dp = MODREF / "decomp_full" / "MegaCrit.Sts2.Core.Models.Powers" / "DoomPower.cs"
    if dp.exists():
        dsrc = dp.read_text(encoding="utf-8")
        check("public sealed class DoomPower : PowerModel" in dsrc and "base.Owner.CurrentHp <= base.Amount" in dsrc,
              "DECOMP: DoomPower is sealed, concrete, and kills at HP <= Doom")

    er = _cs("Engine", "EffectRunner.cs")
    for frag, why in (
            ('"strength_down"  => RelicApplyT<StrengthPower>(ctx, target, source, -amount),', "the permanent loss is the -amt literal"),
            ('"temp_strength_down" => RelicApplyT<ForgedTempStrengthDownPower>(ctx, target, source, amount),', "temp via the literal path"),
            ('"doom"           => RelicApplyT<DoomPower>(ctx, target, source, amount),', "Doom: RelicApply"),
            ('"doom"           => ApplyPower<DoomPower>(self, card, ctx, play),', "Doom: ApplyStatus"),
            ('Take<DoomPower>("doom");', "Doom: SpreadDebuffs"),
            ('if (target.HasPower<DoomPower>()) n++;', "Doom: DebuffCount"),
            ('if (target.HasPower<ForgedTempStrengthDownPower>() || target.GetPowerAmount<StrengthPower>() < 0) n++;',
             "Strength Down counts as a debuff (decision 12)"),
            ('"doom"       => target.GetPowerAmount<DoomPower>(),', "Doom: StatusStacks (Time's Up)"),
            ("await CreatureCmd.LoseBlock(t, t.Block);", "strip_block = the Expose LoseBlock"),
            ("if (t.HasPower<ArtifactPower>()) await PowerCmd.Remove<ArtifactPower>(t);", "strip_artifact = guarded Remove<ArtifactPower>"),
            ('if (e.Status == "doom" && e.Scale == "damage_dealt_unblocked")', "Blight Strike reads unblockedDealt"),
            ("n = unblockedDealt;", "the Doom amount IS the unblocked damage dealt"),
            ('internal static readonly HashSet<string> BlStatuses = ["temp_strength_down", "strength_down", "doom"];', "the BL trio"),
            ("await ApplyBlStatus(e.Status!, ctx, t, card.Owner.Creature, n);", "cards apply the trio literally per target"),
            ('$"[BL] doom +{n} on \'{m}\' (HP {t.CurrentHp}, Doom {d}, doomed={t.CurrentHp <= d})"', "the [BL] doom tag"),
            ('$"[BL] artifact check: \'{m}\' Artifact {art0} blocked {status}, Str now {str1} "', "the [BL] artifact-check tag"),
            ('$"[BL] temp_strength_down +{n} on \'{m}\' (Str now {str1})."', "the [BL] temp tag"),
            ('$"[BL] strength_down -{n} on \'{m}\' (Str now {str1})."', "the [BL] strength_down tag"),
            ('$"[BL] strip_block {had}->{(int)t.Block} on \'{MonsterName(t)}\'', "the [BL] strip_block tag"),
            ('$"[BL] strip_artifact (had {had}) on \'{MonsterName(t)}\'', "the [BL] strip_artifact tag"),
            ('$"[BL] doom from unblocked {n}', "the [BL] Blight Strike tag")):
        check(frag in er, f"EffectRunner: {why}")
    # v0.4.0 release prep (2026-10-05): the GAPTEST-only Artifact injection op is STRIPPED from the engine; the
    # sign-flip proof it enabled lives in the saved BL tag files (_t_smoke_record below).
    engine = pathlib.Path(__file__).resolve().parents[2] / "mod" / "BlankTheSpireCode"
    left = [p.name for p in engine.rglob("*.cs") if "gaptest_enemy_artifact" in p.read_text(encoding="utf-8-sig")]
    check(not left, f"the gaptest_enemy_artifact op is GONE from the C# (still in: {left})")
    dc = _cs("Engine", "DataCard.cs")
    check('case "doom":           if (!e.IsScaled) Power<DoomPower>(vname, e.Amount, up); break;' in dc, "DataCard: Power<DoomPower>")
    check('case "temp_strength_down": Power<ForgedTempStrengthDownPower>(vname, e.Amount, up); break;' in dc, "DataCard: the temp shell var")
    check('case "strength_down":  WithVar("StrengthLoss", e.Amount, up); break;' in dc,
          "DataCard: the permanent form declares StrengthLoss (NOT Power<StrengthPower>)")
    check("Power<StrengthPower>(vname, e.Amount, up); break;" in dc and dc.count("Power<StrengthPower>(") == 1,
          "Power<StrengthPower> stays the self-buff `strength` only")
    for d in ('case "strip_block":', 'case "strip_artifact":'):
        check(d in dc, f"DataCard declares nothing for {d}")
    co = _cs("Engine", "Conditions.cs")
    check("doom" in _set(co, "StatusChecks") and '"doom"       => t.HasPower<DoomPower>(),' in co,
          "Conditions: StatusChecks + TargetHasStatus know doom")
    tr = _cs("Engine", "TriggerRunner.cs")
    check('"doom"               => EffectRunner.ApplyBlStatus("doom", ctx, target, source, amount),' in tr
          and '"temp_strength_down" => EffectRunner.ApplyBlStatus("temp_strength_down", ctx, target, source, amount),' in tr,
          "TriggerRunner.ApplyDebuff: Doom + temp Strength Down payloads")
    fc = _cs("Engine", "ForgedCards.cs")
    check(set(NEW_STATUSES) <= _set(fc, "SupportedStatuses"), "ForgedCards.SupportedStatuses += the three")
    check({"temp_strength_down", "doom"} <= _set(fc, "EnemyDebuffStatuses") and "strength_down" not in _set(fc, "EnemyDebuffStatuses"),
          "EnemyDebuffStatuses += temp_strength_down / doom (strength_down is card-only)")
    check("doom" in _set(fc, "StatusStackStatuses"), "StatusStackStatuses += doom (BJ's target_status_stacks)")
    check(set(NEW_OPS) <= _set(fc, "SupportedOps") and "gaptest_enemy_artifact" not in _set(fc, "SupportedOps"),
          "SupportedOps += the strip ops (the gaptest op is stripped for v0.4.0)")
    check(not (set(NEW_OPS) & _set(fc, "TriggerOps")), "the strip ops are card-only (not in TriggerOps)")
    check('new() { ["temp_strength_down"] = 9, ["strength_down"] = 3, ["doom"] = 12 };' in fc and "PayloadDoomMax = 5;" in fc,
          "the caps (temp 9 / permanent 3 / Doom 12, payload Doom 5)")
    check('"temp_strength_down" => "Strength Down", "strength_down" => "Strength Down", "doom" => "Doom",' in fc
          and fc.count('"doom" => "Doom"') == 2, "StatusDisplay + StatusName")
    for frag in ("return $\"'{list[i].Op}' must come BEFORE the card's debuffs (the Expose order: strip, then debuff).\";",
                 "if (e.Op != \"heal\" && !(e.Op == \"apply_status\" && e.Status == \"doom\"))",
                 'return "at most one \'strength_down\' effect per card (raise the amount instead).";',
                 "needs a single-enemy card (target \\\"enemy\\\") — it strips the CHOSEN enemy.\";"):
        check(frag in fc, f"ForgedCards.Validate: {frag[:70]}")


CASES = [([_st("temp_strength_down", 6)], "all_enemies", "Apply Strength Down to ALL enemies."),
         ([_st("temp_strength_down", 9)], "enemy", "Apply Strength Down."),
         ([_st("strength_down", 2)], "enemy", "The enemy loses {StrengthLoss} Strength."),
         ([_st("strength_down", 1)], "all_enemies", "ALL enemies lose {StrengthLoss} Strength."),
         ([_st("strength_down", 1)], "random_enemy", "A random enemy loses {StrengthLoss} Strength."),
         ([{"op": "strip_block"}, {"op": "strip_artifact"}, _st("vulnerable", 2)], "enemy",
          "Remove all of the enemy's Block.\nRemove the enemy's Artifact.\nApply Vulnerable."),
         ([_st("doom", 7)], "enemy", "Apply Doom."),
         ([{"op": "damage", "amount": 6}, _st("doom", 1, scale="damage_dealt_unblocked")], "enemy",
          "Deal {Damage} damage.\nApply Doom equal to the unblocked damage dealt."),
         ([{"op": "damage", "amount": 1, "scale": "target_status_stacks", "status": "doom"}], "enemy",
          "Deal damage equal to the enemy's Doom."),
         ([{"op": "damage", "amount": 8, "when": {"kind": "target_has_status", "status": "doom"}}], "enemy",
          "Deal {Damage} damage if the enemy has doom.")]
C_FRAGMENTS = ('case "strip_block":    parts.Add("Remove all of the enemy\'s Block."); break;',
               'case "strip_artifact": parts.Add("Remove the enemy\'s Artifact."); break;',
               'TargetType.AllEnemies => "ALL enemies lose {StrengthLoss} Strength.",',
               'TargetType.RandomEnemy => "A random enemy loses {StrengthLoss} Strength.",',
               '_ => "The enemy loses {StrengthLoss} Strength.",',
               'parts.Add("Apply Doom equal to the unblocked damage dealt.");',
               '"target_has_status"  => $"the enemy has {c.Status}",')


def _t_rules_and_describe() -> None:
    print("validator + describe (Python literal == the C# fragment written by hand):")
    pay = lambda st_, n: _card([{"op": "add_trigger", "trigger": "turn_start",  # noqa: E731
                                 "effects": [_st(st_, n, target="all_enemies")]}], rarity="rare", ctype="power", target="self")
    ok = [_card([_st("temp_strength_down", 6)], target="all_enemies", rarity="common"),
          _card([_st("temp_strength_down", 9), {"op": "exhaust"}]),
          _card([_st("strength_down", 3), {"op": "exhaust"}], rarity="rare"),
          _card([{"op": "strip_block"}, {"op": "strip_artifact"}, _st("vulnerable", 2)]),
          _card([{"op": "strip_artifact"}, _st("strength_down", 2)]),
          _card([_st("doom", 9)]), _card([_st("doom", 12)], rarity="rare"),
          _card([{"op": "damage", "amount": 6}, _st("doom", 1, scale="damage_dealt_unblocked")], ctype="attack"),
          _card([{"op": "damage", "amount": 1, "scale": "target_status_stacks", "status": "doom"}], ctype="attack", rarity="rare"),
          _card([{"op": "damage", "amount": 8, "when": {"kind": "target_has_status", "status": "doom"}}], ctype="attack"),
          _card([_st("doom", 3), {"op": "spread_debuffs"}]),
          # a self Strength buff and an enemy Strength loss on one card (distinct vars: StrengthPower vs StrengthLoss)
          _card([_st("strength", 1), _st("strength_down", 1)], rarity="rare"),
          pay("doom", 3), pay("temp_strength_down", 4)]
    for c in ok:
        check(not _errs(c), f"validates: {json.dumps(c['effects'])} -> {_errs(c)}")
    bad = [(_card([_st("temp_strength_down", 10)]), "amount may be at most 9"),
           (_card([_st("strength_down", 4)], rarity="rare"), "amount may be at most 3"),
           (_card([_st("doom", 13)], rarity="rare"), "amount may be at most 12"),
           (_card([_st("doom", 10)]), "RARE-only"),
           (_card([_st("strength_down", 1)], target="self"), "is an enemy debuff"),
           (_card([_st("doom", 2)], target="self"), "is an enemy debuff"),
           (_card([_st("vulnerable", 2), {"op": "strip_artifact"}]), "must come BEFORE the card's debuffs"),
           (_card([{"op": "strip_block"}], target="all_enemies"), "needs a single-enemy card"),
           (_card([{"op": "strip_block", "amount": 2}]), "flag-op"),
           (_card([{"op": "strip_block"}, {"op": "strip_block"}]), "at most one 'strip_block'"),
           (_card([_st("strength_down", 1), _st("strength_down", 1, when={"kind": "hp_below_half"})], rarity="rare"),
            "at most one 'strength_down'"),
           (_card([_st("doom", 1, scale="damage_dealt_unblocked")]), "needs a 'damage' op earlier"),
           (_card([{"op": "damage", "amount": 6}, _st("doom", 1, scale="damage_dealt_unblocked")], ctype="attack",
                  target="all_enemies"), "needs a single-enemy card"),
           (_card([{"op": "damage", "amount": 6}, _st("weak", 1, scale="damage_dealt_unblocked")], ctype="attack"),
            "only applies to heal (lifesteal) or apply_status doom"),
           (pay("doom", 6), "at most 5 per fire"),
           (pay("strength_down", 1), "strength_down"),
           (_card([{"op": "add_trigger", "trigger": "turn_start", "effects": [{"op": "strip_block"}]}],
                  ctype="power", target="self"), "strip_block")]
    for c, frag in bad:
        e = _errs(c)
        check(any(frag in x for x in e), f"rejected ({frag}): {json.dumps(c['effects'])} -> {e}")
    v = _V
    check(abs(v._score_effect(_st("temp_strength_down", 6)) - 3.6) < 1e-9, "temp Strength Down is priced at 0.6/stack")
    check(v._score_effect(_st("strength_down", 2)) == 6.0, "permanent Strength loss is priced at 3/stack")
    check(abs(v._score_effect(_st("doom", 10)) - 8.0) < 1e-9, "Doom is priced at 0.8/stack")
    check(v._score_effect(_st("doom", 1, scale="damage_dealt_unblocked")) > 0, "Blight Strike's Doom is priced (not the nominal 1)")
    check(v._score_effect({"op": "strip_block"}) == 3.0 and v._score_effect({"op": "strip_artifact"}) == 2.0, "the strips are priced")
    for effects, target, want in CASES:
        got = cardgen.describe(effects, target)
        check(got == want, f"describe {got!r} == {want!r}")
    src = _cs("Engine", "ForgedCards.cs") + _cs("Engine", "Conditions.cs")
    for frag in C_FRAGMENTS:
        check(frag in src, f"C# Describe fragment: {frag}")
    check(cardgen.STATUS_NAME["temp_strength_down"] == "Strength Down" and cardgen.STATUS_NAME["doom"] == "Doom",
          "cardgen.STATUS_NAME (lockstep with StatusDisplay)")
    trig = cardgen.describe([{"op": "add_trigger", "trigger": "turn_start",
                              "effects": [_st("doom", 3, target="all_enemies")]}], "self")
    check(trig == "At the start of your turn, apply 3 Doom to ALL enemies.", f"payload fragment: {trig!r}")
    check(cardgen.effect_literal(_st("doom", 1, scale="damage_dealt_unblocked"))
          == 'new EffectSpec("apply_status", 1, "doom", 1, "damage_dealt_unblocked")', "effect_literal: the Blight Strike scale")
    check(cardgen.effect_literal({"op": "strip_block"}) == 'new EffectSpec("strip_block", 0)', "effect_literal: strip_block")
    # plan §7 decision 6: <= 4 Doom cards per class (advisory, set-level)
    dc = [dict(_card([_st("doom", 3)]), id=f"d{i}") for i in range(5)]
    check(doom_warnings(dc[:4]) == [] and len(doom_warnings(dc)) == 1, "character_validator.doom_warnings: >4 Doom cards warns")


def _t_contract() -> None:
    print("contract surfaces:")
    schema = json.loads(CARD_SCHEMA.read_text(encoding="utf-8"))
    eff = schema["$defs"]["effect"]
    check(set(NEW_OPS) <= set(eff["properties"]["op"]["enum"]), "schema: op enum += strip_block / strip_artifact")
    check(set(NEW_STATUSES) <= set(eff["properties"]["status"]["enum"]), "schema: status enum += the three")
    te = schema["$defs"]["triggerEffect"]
    check({"temp_strength_down", "doom"} <= set(te["properties"]["status"]["enum"])
          and "strength_down" not in te["properties"]["status"]["enum"], "schema: payload status enum (strength_down card-only)")
    check(not (set(NEW_OPS) & set(te["properties"]["op"]["enum"])), "schema: the strip ops are never payload ops")
    rules = json.dumps(eff.get("allOf", []))
    check('"status": {"enum": ["vulnerable", "weak", "poison", "doom"]}' in rules, "schema: target_status_stacks reads doom")
    check('"op": {"enum": ["strip_block", "strip_artifact"]}' in rules, "schema: the strip flag-op rule")
    check("doom" in schema["$defs"]["condition"]["properties"]["status"]["enum"], "schema: target_has_status doom")
    for s in NEW_STATUSES:
        j = json.loads((paths.VOCABULARY.parent / "statuses" / f"{s}.json").read_text(encoding="utf-8"))
        check(j["id"] == s and j["kind"] == "debuff", f"statuses/{s}.json (a debuff)")
    vocab = paths.VOCABULARY.read_text(encoding="utf-8")
    check("| `doom`          | debuff | If the target's HP is at or below its Doom at the end of ITS turn, it dies. Doom never decays." in vocab,
          "VOCABULARY: the doom row (the plan's wording)")
    for t in NEW_STATUSES + NEW_OPS:
        check(vocab.count(f"| `{t}`") == 1, f"VOCABULARY: ONE `{t}` row")
        check(f"`{t}` —" in gate.vocab_index(vocab), f"the index carries a {t} line")
    check("(poison/vulnerable/weak/frail/doom)" in vocab and "Doom / Strength Down" in vocab, "VOCABULARY: condition + spread rows")
    for op in NEW_OPS:
        check(op in gate.GATED_OP_ORDER, f"gate.GATED_OP_ORDER carries {op} (no card core cost)")
    check(set(NEW_STATUSES) <= census.EXOTIC_STATUSES, "census.EXOTIC_STATUSES += the three")
    check(not (set(NEW_OPS) & census.KEYWORD_OPS), "the strip ops are NOT card-shape keywords (spread_debuffs precedent)")
    check("temp_strength_down" in {k for k, _ in coverage.EXOTIC_MENU_V2}
          and coverage.CENSUS_DETECTOR["temp_strength_down"](census.walk_card(_card([_st("temp_strength_down", 6)]))),
          "coverage: EXOTIC_MENU_V2 + detector for Piercing Wail")
    fe = next((f for f in featured.FEATURED_MENU if f.id == "expose_strip"), None)
    check(fe is not None and fe.detect(census.walk_card(_card([{"op": "strip_block"}, _st("weak", 1)]))),
          "featured: the expose_strip entry + detector")
    check("doom" in bridges.card_tokens(_card([{"op": "damage", "amount": 1, "scale": "target_status_stacks", "status": "doom"}],
                                              ctype="attack")), "bridges: Time's Up touches doom")
    arch = {a["id"]: a for a in json.loads((DATA / "archetypes.json").read_text(encoding="utf-8"))["archetypes"]}
    claims = {"block_bulwark": ({"temp_strength_down", "strength_down"}, {"#66"}),
              "untouchable_ward": ({"temp_strength_down"}, {"#66"}),
              "debuff_expose": ({"temp_strength_down", "strength_down", "strip_block", "strip_artifact", "doom"}, {"#66", "#67"}),
              "reaper_lifesteal": ({"doom"}, {"#67"}), "countdown_ripen": ({"doom"}, {"#67"})}
    for aid, (toks, gaps) in claims.items():
        a = arch[aid]
        check(toks <= set(a["vocabulary"]["ops"]), f"{aid} claims {sorted(toks)}")
        check({f"VOCABULARY_GAPS{g}" for g in gaps} <= set(a["gap_refs"]) and a["buildable"] is True, f"{aid} refs {sorted(gaps)}")
        check("(v64" in a.get("build_notes", ""), f"{aid} build_notes name the v64 shape")
    check("doom_reaper" not in arch, "no new doom_reaper archetype this phase")
    pool = json.loads((DATA / "exemplar_pool.json").read_text(encoding="utf-8"))["exemplars"]
    v = harness_v2.exemplar_validator()
    used, forms = set(), set()
    for e in pool:
        toks = bridges.card_tokens(e["card"])
        hit = (set(NEW_STATUSES) | set(NEW_OPS)) & toks
        if hit:
            used |= hit
            r = v.validate(dict(e["card"]))
            check(r.ok, f"exemplar {e['card']['id']} validates: {r.errors}")
        for eff_ in e["card"].get("effects", []):
            if eff_.get("status") == "doom" and eff_.get("scale") == "damage_dealt_unblocked":
                forms.add("blight_strike")
            if eff_.get("scale") == "target_status_stacks" and eff_.get("status") == "doom":
                forms.add("times_up")
    check(set(NEW_STATUSES) | set(NEW_OPS) <= used, f"exemplars cover every new token (got {sorted(used)})")
    check(forms == {"blight_strike", "times_up"}, f"exemplars: the Blight Strike + Time's Up forms (got {sorted(forms)})")
    heur = (paths.VOCABULARY.parent / "DESIGN_HEURISTICS.md").read_text(encoding="utf-8")
    check(heur.count("(v64") >= 5 and "at most 4 Doom cards per class" in heur and "Artifact eats Strength Down" in heur,
          "DESIGN_HEURISTICS: the Doom band + Artifact eats Strength Down")
    gaps = (REPO / "VOCABULARY_GAPS.md").read_text(encoding="utf-8")
    for n, nxt in (("66", "67"), ("67", "68")):
        entry = gaps.split(f"### {n}.", 1)[1].split(f"### {nxt}.", 1)[0]
        check("**Status:** **done (2026-10-04, vocab v64, Phase BL)**" in entry, f"gap #{n} is done")
    js = (REPO / "web" / "static" / "render.js").read_text(encoding="utf-8")
    for frag in ('case "strip_block": return "Remove all of the enemy\'s Block";', 'case "strip_artifact": return "Remove the enemy\'s Artifact";',
                 'temp_strength_down: "Strength Down (this turn)"', 'doom: "Doom"',
                 'return "Apply Doom equal to the unblocked damage dealt";', '`The enemy loses ${a ?? ""} Strength`'):
        check(frag in js, f"render.js: {frag[:60]}")
    src = pathlib.Path(cf.__file__).read_text(encoding="utf-8")
    check("ENEMY STRENGTH / EXPOSE / DOOM (v64)" in src, "the PRECISION READS pitch sentence")
    plan = (REPO / "docs" / "plans" / "VOCAB_EXPANSION_6_PLAN.md").read_text(encoding="utf-8")
    check("`doom` joins vulnerable / weak / poison (Phase BL, done)" in plan, "the BJ Findings bullet records that doom joined target_status_stacks")


def _t_tester() -> None:
    print("the tester (validate-only path; staging waits for Ryan):")
    p = TESTER_DIR / "build_tester.py"
    check(p.exists(), "tests/gaptest-bl/build_tester.py exists")
    spec = importlib.util.spec_from_file_location("bl_tester", p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    check(mod.validate(verbose=True) == 0, "every non-gaptest tester card validates")
    ids = {c["id"] for c in mod.CARDS}
    types = [c["type"] for c in mod.CARDS if c["rarity"] != "basic"]
    check(types.count("attack") >= 3 and types.count("skill") >= 3 and types.count("power") >= 1,
          "pool: >= 3 non-basic Attacks + Skills and >= 1 Power (the merchant stall)")
    check(mod.GAPTEST_ONLY == {"bl_warding_gift"} and "bl_warding_gift" not in ids,
          "the Artifact injection card is the one gaptest card, OFF by default (the op is stripped from the engine)")
    gift = mod.ARTIFACT_OP_CARD
    check({"op": "innate"} in gift["effects"] and gift["effects"][0]["op"] == "gaptest_enemy_artifact"
          and gift in mod.cards_for(with_artifact_op=True) and "--with-artifact-op" in p.read_text(encoding="utf-8"),
          "--with-artifact-op still stages the Innate injection (for a pre-v0.4.0 DLL)")
    flat = json.dumps(mod.CARDS)
    for need in ('"temp_strength_down"', '"strength_down"', '"strip_block"', '"strip_artifact"', '"damage_dealt_unblocked"',
                 '"target_status_stacks", "status": "doom"', '"spread_debuffs"', '"target": "all_enemies"'):
        check(need in flat, f"the tester exercises {need}")
    check("--validate-only" in p.read_text(encoding="utf-8"), "the tester has a --validate-only flag")


def _t_smoke_record() -> None:
    print("the saved AutoSlay tag greps (TEST_AUDIT_2026-10 §7):")
    seen = ""
    for s in SMOKE_SEEDS:
        p = TESTER_DIR / f"godot_BL_tags_{s}.txt"
        assert p.exists(), f"missing smoke record {p}"
        txt = p.read_text(encoding="utf-8")
        check("Run completed" in txt, f"{p.name}: the run completed")
        check("[BL]" in txt, f"{p.name} holds [BL] tags")
        check("mod exceptions: 0" in txt and "Localization formatting errors: 0" in txt
              and "BlankTheSpire stack frames: 0" in txt, f"{p.name} records a clean run")
        seen += txt
    for t in TAGS:
        check(t in seen, f"the smoke fired '{t}'")
    check(re.search(r"\[BL\] artifact check: '[^']+' Artifact \d+ blocked temp_strength_down, Str now -?\d+ \(shell 0->0\)", seen)
          is not None, "the sign-flip proof: an Artifact enemy's temp Strength Down was negated WHOLE (shell 0->0)")
    # every blocked Strength Down left the shell exactly as it was (0->0 = nothing to restore; N->N = a shell applied
    # BEFORE the Artifact arrived, untouched by the blocked apply) — Artifact never grows a shell
    shells = re.findall(r"\[BL\] artifact check: .*\(shell (\d+)->(\d+)\)", seen)
    check(shells and all(a == b for a, b in shells), f"no blocked Strength Down ever grew a shell ({len(shells)} checks)")
    check(re.search(r"\[BL\] strip_artifact \(had [1-9]", seen) is not None, "strip_artifact removed a real Artifact stack")
    check("doomed=True" in seen, "a Doom stack reached the enemy's HP")


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


def test_phase_bl_all() -> None:
    global _PASS, _FAIL
    _PASS = _FAIL = 0
    assert main() == 0, f"{_FAIL} Phase BL check(s) failed - see the FAIL lines above"


if __name__ == "__main__":
    sys.exit(main())
