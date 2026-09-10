"""Phase AR — CONDITIONS INSIDE CUSTOM ORB EFFECTS (VOCAB_GAP_REMEDIATION_PLAN Wave 3, vocab v49) — offline, no API key.

Run:  uv run python -m tests.test_phase_ar       (from generation/)
Exits nonzero on any failure. Covers the v49 additions on the generation side, in lockstep with the C#:
  1. a custom orb's passive/evoke effect may carry a `when` gate — every card condition kind EXCEPT the card-instance and
     chosen-target reads (target_has_status / retained_last_turn / target_hp_below_half / target_has_block: an orb fires
     with no card and no chosen target, the trigger rule) — with the C# Conditions.Validate value bounds (value >= 1 on
     the threshold kinds; energy_ge <= 6, cards_played_this_turn_ge <= 10, hp_lost_ge <= 15) and a boolean `negate`;
     class_forge._validate_orb_pool accepts every legal shape and rejects every illegal one with the C# wording family;
  2. a custom orb gains `passive_timing` (turn_end default / turn_start) and a passive `gain_energy` / `draw` MUST be
     turn_start (dead at the end-of-turn tick — the Plasma finding); the VOCABULARY.md Plasma / Glass recipes validate;
  3. the condition-kind sets stay in lockstep three ways: card.schema.json's enum, the C# Conditions.Kinds list, and the
     Python orb set (+ its forbidden set);
  4. the C# mirror: OrbSpec carries When/PassiveTiming, ForgedCharacters' sets + parser carry the tokens and call the
     shared Conditions.Validate, OrbRunner gates at fire time (+ [AR] tag, tooltip clause), ForgedOrb overrides
     AfterTurnStartOrbTrigger (the game's Plasma hook) and the VocabVersion stamp is 49;
  5. the contract carries the tokens: VOCABULARY.md bullets + recipes, the Conditions cross-reference, DESIGN_HEURISTICS
     orb_channel note, app.js labels (turn_start passive + the later condition kinds), the PHASE_I plan deferrals marked
     LANDED, the offline fake orb blueprint validates, the blueprint prompt carries the sentence; rule-0.9 budget printed.
"""
from __future__ import annotations

import json
import pathlib
import re
import sys

from btsgen.class_forge import point_btsgen_at_mod_contract

point_btsgen_at_mod_contract()

from btsgen import bts1, paths  # noqa: E402
from btsgen import class_forge as cf  # noqa: E402
from btsgen.class_forge import ClassBrief, _BlueprintContract, _fake_blueprint, _validate_orb_pool  # noqa: E402

_PASS = 0
_FAIL = 0

MOD_CODE = paths.VOCABULARY.parents[1] / "BlankTheSpireCode"   # mod/contract/.. -> mod/BlankTheSpireCode
WEB_APP = paths.VOCABULARY.parents[2] / "web" / "static" / "app.js"
CARD_SCHEMA = paths.VOCABULARY.parent / "card.schema.json"
PHASE_I_PLAN = paths.VOCABULARY.parents[2] / "docs" / "plans" / "PHASE_I_FORGED_ORBS_PLAN.md"

FORBIDDEN = {"target_has_status", "retained_last_turn", "target_hp_below_half", "target_has_block"}


def check(cond: bool, msg: str) -> None:
    global _PASS, _FAIL
    if cond:
        _PASS += 1
    else:
        _FAIL += 1
        print(f"  FAIL: {msg}")


def _orb(passive=None, evoke=None, timing=None, name="Test") -> dict:
    o = {"name": name, "passive_val": 2, "evoke_val": 8,
         "passive": passive if passive is not None else [],
         "evoke": evoke if evoke is not None else []}
    if timing is not None:
        o["passive_timing"] = timing
    return o


def _errs(*orbs) -> list[str]:
    return _validate_orb_pool(list(orbs), 3)


def _accepts(orb, label):
    e = _errs(orb)
    check(not e, f"{label} should validate: {e}")


def _rejects(orb, needle, label):
    e = _errs(orb)
    check(any(needle in x for x in e), f"{label} should be rejected with '{needle}': {e}")


def _when(kind, value=None, negate=None, status=None) -> dict:
    w = {"kind": kind}
    if value is not None:
        w["value"] = value
    if negate is not None:
        w["negate"] = negate
    if status is not None:
        w["status"] = status
    return w


def test_version() -> None:
    print("vocab v49 stamps:")
    check(bts1.VOCAB_VERSION == 49, f"bts1.VOCAB_VERSION == 49 (got {bts1.VOCAB_VERSION})")
    fc = (MOD_CODE / "Engine" / "ForgedCards.cs").read_text(encoding="utf-8")
    check("public const int VocabVersion = 49;" in fc, "ForgedCards.VocabVersion == 49")
    check("49: Phase AR" in fc, "the v49 comment names Phase AR")


def _t_when_accepts() -> None:
    print("orb-effect `when` accepts every legal kind on a passive and an evoke, negate, and the caps:")
    sample_value = {"has_block": 2, "energy_ge": 6, "cards_played_this_turn_ge": 10, "hp_lost_ge": 15}
    for kind in sorted(cf._ORB_CONDITION_KINDS):
        v = sample_value.get(kind, 1 if kind in cf._ORB_CONDITION_VALUE_KINDS else None)
        dmg = {"op": "damage", "amount": 3, "target": "enemy", "when": _when(kind, v)}
        _accepts(_orb(passive=[dmg]), f"passive damage gated on {kind}")
        blk = {"op": "block", "amount": 4, "when": _when(kind, v, negate=True)}
        _accepts(_orb(evoke=[blk]), f"evoke block gated on negated {kind}")
    # a gate on every op modality
    for eff in ({"op": "apply_status", "status": "vulnerable", "amount": 1, "target": "all_enemies"},
                {"op": "apply_status", "status": "strength", "amount": 1},
                {"op": "heal", "amount": 2}, {"op": "gain_orb_slot", "amount": 1},
                {"op": "channel_orb", "orb": "lightning"}):
        _accepts(_orb(evoke=[dict(eff, when=_when("orbs_match"))]), f"evoke {eff['op']} gated on orbs_match")
    # the has_block default (no value) is legal, like on cards
    _accepts(_orb(evoke=[{"op": "draw", "amount": 1, "when": _when("has_block")}]), "has_block with no value")
    # an ungated effect next to a gated one
    _accepts(_orb(evoke=[{"op": "damage", "amount": 8, "target": "all_enemies"},
                         {"op": "draw", "amount": 1, "when": _when("orb_count_ge", 2)}]), "mixed gated + ungated evoke")


def _t_when_rejects() -> None:
    print("orb-effect `when` rejects the no-card/no-target reads, unknown kinds, and bad values:")
    for kind in sorted(FORBIDDEN):
        _rejects(_orb(evoke=[{"op": "damage", "amount": 3, "target": "enemy", "when": _when(kind, 1, status="poison")}]),
                 "can't use", f"orb gate on {kind}")
    _rejects(_orb(passive=[{"op": "block", "amount": 2, "when": _when("moon_phase")}]), "unknown condition kind", "an unknown kind")
    _rejects(_orb(passive=[{"op": "block", "amount": 2, "when": _when("orb_count_ge", 0)}]), "needs value >= 1", "orb_count_ge 0")
    _rejects(_orb(passive=[{"op": "block", "amount": 2, "when": _when("turn_at_least")}]), "needs value >= 1", "turn_at_least without a value")
    _rejects(_orb(passive=[{"op": "block", "amount": 2, "when": _when("energy_ge", 7)}]), "at most 6", "energy_ge 7")
    _rejects(_orb(passive=[{"op": "block", "amount": 2, "when": _when("cards_played_this_turn_ge", 11)}]), "at most 10", "cards_played 11")
    _rejects(_orb(passive=[{"op": "block", "amount": 2, "when": _when("hp_lost_ge", 16)}]), "at most 15", "hp_lost_ge 16")
    _rejects(_orb(passive=[{"op": "block", "amount": 2, "when": "orbs_match"}]), "must be an object", "a string when")
    _rejects(_orb(passive=[{"op": "block", "amount": 2, "when": _when("no_block", negate="yes")}]), "must be true/false", "a string negate")
    # the pre-AR orb rules still hold
    _rejects(_orb(passive=[{"op": "lose_hp", "amount": 2}]), "not allowed in an orb", "lose_hp in an orb")
    _rejects(_orb(passive=[{"op": "damage", "amount": 2, "target": "self"}]), "can't target self", "damage self")


def _t_timing() -> None:
    print("passive_timing: turn_end default, turn_start for the Plasma shape, energy/draw passives must be turn_start:")
    plasma = _orb(passive=[{"op": "gain_energy", "amount": 1}], evoke=[{"op": "gain_energy", "amount": 2}],
                  timing="turn_start", name="Plasma")
    _accepts(plasma, "the Plasma shape (turn_start gain_energy passive)")
    _accepts(_orb(passive=[{"op": "draw", "amount": 1}], timing="turn_start"), "a turn_start draw passive")
    _accepts(_orb(passive=[{"op": "damage", "amount": 2, "target": "enemy"}], timing="turn_start"), "a turn_start damage passive")
    _accepts(_orb(passive=[{"op": "damage", "amount": 2, "target": "enemy"}], timing="turn_end"), "an explicit turn_end")
    _accepts(_orb(evoke=[{"op": "gain_energy", "amount": 2}, {"op": "draw", "amount": 1}]), "energy/draw on an EVOKE need no timing")
    _rejects(_orb(passive=[{"op": "gain_energy", "amount": 1}]), 'needs passive_timing "turn_start"', "a gain_energy passive with the default timing")
    _rejects(_orb(passive=[{"op": "draw", "amount": 1}], timing="turn_end"), 'needs passive_timing "turn_start"', "a draw passive at turn_end")
    _rejects(_orb(passive=[{"op": "block", "amount": 2}], timing="combat_start"), "is not one of turn_end/turn_start", "an unknown timing")
    check(cf._ORB_TURN_START_ONLY_OPS == {"gain_energy", "draw"}, "the turn-start-only ops are exactly gain_energy + draw")
    check(cf._ORB_PASSIVE_TIMINGS == {"turn_end", "turn_start"}, "the timings are exactly turn_end + turn_start")


def _t_recipes() -> None:
    print("the VOCABULARY.md Plasma / Glass recipes parse and validate as a pool:")
    vocab = paths.VOCABULARY.read_text(encoding="utf-8")
    orbs_sec = vocab.split("## Orbs", 1)[1].split("\n## ", 1)[0]
    snippets = re.findall(r"`(\{\"name\":\"(?:Plasma|Glass)\".*?\})`", orbs_sec)
    check(len(snippets) == 2, f"two backticked recipe objects in the Orbs section (got {len(snippets)})")
    recipes = []
    for s in snippets:
        try:
            recipes.append(json.loads(s))
        except json.JSONDecodeError as ex:
            check(False, f"recipe is valid JSON: {ex}: {s[:60]}")
    if len(recipes) == 2:
        by = {r["name"]: r for r in recipes}
        check(set(by) == {"Plasma", "Glass"}, f"recipes are Plasma + Glass: {sorted(by)}")
        e = _validate_orb_pool(recipes, 3)
        check(not e, f"both recipes validate together as a pool: {e}")
        p, g = by.get("Plasma", {}), by.get("Glass", {})
        check(p.get("passive_timing") == "turn_start" and p.get("passive") == [{"op": "gain_energy", "amount": 1}],
              "Plasma = turn_start passive gain_energy 1")
        check(any(x.get("op") == "gain_energy" for x in p.get("evoke", [])), "Plasma evokes for energy")
        check(g.get("passive") == [] and len(g.get("evoke", [])) == 1
              and g["evoke"][0].get("op") == "damage" and g["evoke"][0].get("target") == "all_enemies",
              "Glass = evoke-only AoE damage")
        # the recipe with the documented gate example
        gated = dict(g, evoke=[dict(g["evoke"][0], when={"kind": "orb_count_ge", "value": 3})])
        check(not _validate_orb_pool([gated], 3), "the documented gated Glass (orb_count_ge 3) validates")
    check('"when":{"kind":"orb_count_ge","value":3}' in orbs_sec, "the Orbs section shows the gate example")


def _t_kind_lockstep() -> None:
    print("condition-kind lockstep: card.schema.json enum == C# Conditions.Kinds == Python orb kinds + forbidden:")
    schema = json.loads(CARD_SCHEMA.read_text(encoding="utf-8"))
    enum = set(schema["$defs"]["condition"]["properties"]["kind"]["enum"]) if "$defs" in schema \
        else set(schema["definitions"]["condition"]["properties"]["kind"]["enum"])
    check(FORBIDDEN <= enum, "the forbidden kinds are card kinds")
    check(cf._ORB_CONDITION_KINDS == enum - FORBIDDEN, f"Python orb kinds == schema enum minus forbidden "
                                                       f"(missing {sorted(enum - FORBIDDEN - cf._ORB_CONDITION_KINDS)}, "
                                                       f"extra {sorted(cf._ORB_CONDITION_KINDS - enum)})")
    check(cf._ORB_FORBIDDEN_CONDITION_KINDS == FORBIDDEN, "Python forbidden set is the four no-card/no-target reads")
    cond = (MOD_CODE / "Engine" / "Conditions.cs").read_text(encoding="utf-8")
    m = re.search(r"Kinds =\s*\[(.*?)\];", cond, re.S)
    cs_kinds = set(re.findall(r'"(\w+)"', m.group(1))) if m else set()
    check(cs_kinds == enum, f"C# Conditions.Kinds == schema enum (diff {sorted(cs_kinds ^ enum)})")
    tk = re.search(r"TargetKinds =\s*\[(.*?)\];", cond, re.S)
    cs_target = set(re.findall(r'"(\w+)"', tk.group(1))) if tk else set()
    check(cs_target | {"target_has_status", "retained_last_turn"} == FORBIDDEN,
          "C# TargetKinds + target_has_status + retained_last_turn == the forbidden set")
    check(cf._ORB_CONDITION_VALUE_MAX == {"energy_ge": 6, "cards_played_this_turn_ge": 10, "hp_lost_ge": 15},
          "value caps mirror Conditions.EnergyGeMax / CardsPlayedGeMax / the hp_lost_ge 15 cap")
    check("EnergyGeMax = 6" in cond and "CardsPlayedGeMax = 10" in cond and 'c.Kind == "hp_lost_ge" && c.Value > 15' in cond,
          "the C# caps are still 6 / 10 / 15")


def _t_csharp_mirror() -> None:
    print("C# mirror: OrbSpec / ForgedCharacters / OrbRunner / ForgedOrb carry the v49 shapes:")
    spec = (MOD_CODE / "Engine" / "OrbSpec.cs").read_text(encoding="utf-8")
    check("public Condition? When => Effect.When;" in spec, "OrbEffect exposes When (rides on EffectSpec.When)")
    check('string PassiveTiming = "turn_end"' in spec, "OrbSpec.PassiveTiming defaults to turn_end")
    check('public bool PassiveAtTurnStart => PassiveTiming == "turn_start";' in spec, "OrbSpec.PassiveAtTurnStart")
    fch = (MOD_CODE / "Engine" / "ForgedCharacters.cs").read_text(encoding="utf-8")
    pt = re.search(r"OrbPassiveTimings =\s*\[([^\]]*)\]", fch)
    check(pt is not None and set(re.findall(r'"(\w+)"', pt.group(1))) == {"turn_end", "turn_start"},
          "ForgedCharacters.OrbPassiveTimings = turn_end + turn_start")
    ts = re.search(r"OrbTurnStartOnlyOps =\s*\[([^\]]*)\]", fch)
    check(ts is not None and set(re.findall(r'"(\w+)"', ts.group(1))) == {"gain_energy", "draw"},
          "ForgedCharacters.OrbTurnStartOnlyOps = gain_energy + draw")
    fk = re.search(r"OrbForbiddenConditionKinds =\s*\[([^\]]*)\]", fch)
    check(fk is not None and set(re.findall(r'"(\w+)"', fk.group(1))) == {"target_has_status", "retained_last_turn"}
          and "Conditions.TargetKinds" in fk.group(1),
          "ForgedCharacters.OrbForbiddenConditionKinds = target_has_status + retained_last_turn + ..Conditions.TargetKinds")
    check('e.ContainsKey("when")' in fch and "var cerr = Conditions.Validate(when);" in fch
          and "OrbForbiddenConditionKinds.Contains(when.Kind)" in fch,
          "TryParseOrbEffects parses `when`, runs the shared Conditions.Validate, then the orb rule")
    check("Orb: orb, When: when), target)" in fch, "the parsed gate lands on the orb effect's EffectSpec")
    check('Str(d, "passive_timing")' in fch and "OrbPassiveTimings.Contains(timing)" in fch
          and "OrbTurnStartOnlyOps.Contains(pe.Effect.Op) && timing != \"turn_start\"" in fch,
          "TryParseCustomOrb parses passive_timing and enforces the energy/draw rule")
    check("passive, evoke, timing);" in fch, "the timing reaches the OrbSpec")
    run = (MOD_CODE / "Engine" / "OrbRunner.cs").read_text(encoding="utf-8")
    check("bool open = Conditions.Evaluate(e.When, player, null);" in run and "if (!open) return;" in run,
          "OrbRunner.RunEffect gates on Conditions.Evaluate (player-state overload, no target)")
    check('"[AR] orb' in run, "OrbRunner logs the [AR] tag (gate + turn-start tick)")
    check("spec.PassiveAtTurnStart" in run and "Passive (turn start):" in run, "Describe names a turn_start passive")
    check("Conditions.Phrase(oe.When)" in run and '"unless " : "if "' in run, "the tooltip fragment carries the if/unless clause")
    orb = (MOD_CODE / "Powers" / "ForgedOrb.cs").read_text(encoding="utf-8")
    check("public override Task AfterTurnStartOrbTrigger(PlayerChoiceContext ctx)" in orb,
          "ForgedOrb overrides AfterTurnStartOrbTrigger (the game's Plasma hook)")
    check("s == null || s.PassiveAtTurnStart ? Task.CompletedTask" in orb
          and "s == null || !s.PassiveAtTurnStart ? Task.CompletedTask" in orb,
          "each orb ticks on exactly one of the two hooks")


def _t_fake_and_prompt() -> None:
    print("the offline fake orb blueprint + the blueprint prompt carry the v49 shapes:")
    bp = _fake_blueprint(ClassBrief(concept="a storm elementalist"))
    pool = bp.get("orb_pool") or []
    check(any(isinstance(o, dict) and o.get("name") == "Plasma" and o.get("passive_timing") == "turn_start" for o in pool),
          "the fake orb class carries a turn_start Plasma orb")
    check(any(isinstance(o, dict) and any("when" in e for e in o.get("evoke", [])) for o in pool),
          "the fake orb class carries a when-gated orb effect")
    e = _validate_orb_pool(pool, bp.get("orb_slots", 0))
    check(not e, f"the fake orb pool validates: {e}")
    check(cf._orb_pool_custom_names(bp) >= {"ember", "plasma"}, "custom names include ember + plasma")
    prompt = _BlueprintContract(mode="dossier", triad=True, seed=1).system_prompt()
    for tok in ('Any orb-effect may carry a "when" gate (v49', '"passive_timing": "turn_start"',
                "a Plasma orb = passive_timing turn_start", "a Glass orb = no passive"):
        check(tok in prompt, f"the blueprint prompt carries {tok!r}")
    print(f"  (rule 0.9) blueprint prompt: {len(prompt):,} chars (Phase AS baseline 91,949)")


def _t_contract() -> None:
    print("contract / heuristics / web / plans carry the tokens:")
    vocab = paths.VOCABULARY.read_text(encoding="utf-8")
    check("- **Orb-effect `when` (v49):**" in vocab, "VOCABULARY.md Orbs: the when bullet")
    check("- **`passive_timing` (v49):**" in vocab and '`"passive_timing": "turn_start"`' in vocab,
          "VOCABULARY.md Orbs: the passive_timing bullet + rule")
    check("**Plasma** =" in vocab and "**Glass** (evoke-only" in vocab, "VOCABULARY.md Orbs: both recipes")
    check("legal inside a custom orb's `passive` / `evoke` effects" in vocab, "VOCABULARY.md Conditions cross-references orbs")
    heur = (paths.VOCABULARY.parent / "DESIGN_HEURISTICS.md").read_text(encoding="utf-8")
    note = heur.split("<!-- archetype-note: orb_channel -->", 1)[1].split("<!--", 1)[0]
    check("`when`-gated" in note and "passive_timing" in note and "never stack it with `max_energy`" in note,
          "DESIGN_HEURISTICS orb_channel note prices the gated orb + the Plasma passive")
    app = WEB_APP.read_text(encoding="utf-8")
    check('passive_turn_start: "At the start of each turn while channeled"' in app
          and 'orb.passive_timing === "turn_start"' in app, "app.js labels a turn_start passive")
    for kind in ("draw_pile_empty", "hp_lost_ge", "dark_ge", "light_ge", "centered", "target_hp_below_half",
                 "target_has_block", "energy_ge", "cards_played_this_turn_ge"):
        check(f'case "{kind}":' in app, f"app.js condCore renders {kind}")
    check("e.when && e.when.kind ? condText(e.when)" in app, "app.js fmtEffect appends the gate (orb chips inherit it)")
    plan = PHASE_I_PLAN.read_text(encoding="utf-8")
    check("**LANDED — Phase AR (2026-09-10, vocab v49)**" in plan and "LANDED in Phase AR (v49" in plan,
          "PHASE_I plan deferrals (:95, :118) marked LANDED")


def main() -> int:
    test_version()
    _t_when_accepts()
    _t_when_rejects()
    _t_timing()
    _t_recipes()
    _t_kind_lockstep()
    _t_csharp_mirror()
    _t_fake_and_prompt()
    _t_contract()
    print(f"\n{_PASS} passed, {_FAIL} failed")
    return 1 if _FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
