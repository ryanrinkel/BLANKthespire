"""Phase BB — TEMPO KEYWORDS: `sly` + `turn_at_most` (VOCAB_EXPANSION_5_PLAN, gaps #55/#59, vocab v56) — offline.

Run:  uv run python -m tests.test_phase_bb       (from generation/)
Exits nonzero on any failure. Covers the v56 change in lockstep with the C#:
  1. the vocab stamp is >= 56 on both sides (bts1.VOCAB_VERSION <= ForgedCards.VocabVersion);
  2. `sly` is a keyword flag-op the C# DECLARES (CardKeyword.Sly) and never re-implements: the game's own
     CardCmd.DiscardAndDraw does the free play; the mod's discard ops are batch calls through it; DataCard does NOT
     route Sly through AfterCardDiscarded (that would double-play);
  3. sly ⊥ retain and never on a Power, on both sides; an upgrade may append it like the other four keywords;
  4. `turn_at_most` is in Conditions.Kinds / Validate / Eval / Phrase and the schema, needs a value, and is legal as
     a trigger gate and inside a custom-orb effect (a player read, like its mirror);
  5. describe is a byte-match contract: cardgen.describe() == the C# sentences ("Sly." / "... if it is turn 2 or earlier");
  6. the contract surfaces — VOCABULARY rows, schema, exemplars, featured/coverage/harness menus, the census keyword
     set, the class-level outlet warning, the archetype catalog and render.js.

No private rule-0.9 ceiling lives here — the one budget is in tests/test_harness_v2.py.
"""
from __future__ import annotations

import json
import pathlib
import re
import sys

from btsgen.class_forge import point_btsgen_at_mod_contract

point_btsgen_at_mod_contract()

from btsgen import bts1, cardgen, census, coverage, featured, harness_v2, paths  # noqa: E402
from btsgen import class_forge as cf  # noqa: E402
from btsgen.character_validator import sly_warnings  # noqa: E402
from btsgen.validator import CardValidator  # noqa: E402

_PASS = 0
_FAIL = 0

MOD_CODE = paths.VOCABULARY.parents[1] / "BlankTheSpireCode"   # mod/contract/.. -> mod/BlankTheSpireCode
CARD_SCHEMA = paths.VOCABULARY.parent / "card.schema.json"
REPO = paths.VOCABULARY.parents[2]
RENDER_JS = REPO / "web" / "static" / "render.js"
EXEMPLAR_POOL = pathlib.Path(cf.__file__).parent / "data" / "exemplar_pool.json"
ARCHETYPES = pathlib.Path(cf.__file__).parent / "data" / "archetypes.json"


def check(cond: bool, msg: str) -> None:
    global _PASS, _FAIL
    if cond:
        _PASS += 1
    else:
        _FAIL += 1
        print(f"  FAIL: {msg}")


def _cs(*parts: str) -> str:
    return (MOD_CODE.joinpath(*parts)).read_text(encoding="utf-8")


def _card(effects, ctype="attack", rarity="common", target="enemy", cost=1, upgrade=None, **extra):
    c = {"id": "bb_t", "name": "BB", "type": ctype, "rarity": rarity, "cost": cost, "target": target,
         "effects": effects}
    if upgrade is not None:
        c["upgrade"] = upgrade if isinstance(upgrade, dict) else {"effects": upgrade}
    c.update(extra)
    return c


_V = None


def _v() -> CardValidator:
    global _V
    if _V is None:
        _V = CardValidator()
    return _V


def _errs(card) -> list[str]:
    return _v().validate(card).errors


def _ok(card) -> bool:
    return not _errs(card)


DMG = {"op": "damage", "amount": 6}


# --------------------------------------------------------------------------- 1. stamps
def test_version() -> None:
    print("Phase BB vocab stamp is at least 56 (Python + C#):")
    check(bts1.VOCAB_VERSION >= 56, f"bts1.VOCAB_VERSION >= 56, got {bts1.VOCAB_VERSION}")
    fc = _cs("Engine", "ForgedCards.cs")
    m = re.search(r"public const int VocabVersion = (\d+);", fc)
    check(m is not None and int(m.group(1)) >= 56, f"ForgedCards.VocabVersion >= 56, got {m and m.group(1)}")
    check(m is not None and bts1.VOCAB_VERSION <= int(m.group(1)), "bts1.VOCAB_VERSION <= ForgedCards.VocabVersion")
    check("Phase BB" in fc and '"sly"' in fc and "turn_at_most" in fc,
          "ForgedCards.cs VocabVersion comment names Phase BB + both tokens")
    src = pathlib.Path(bts1.__file__).read_text(encoding="utf-8")
    check("56: Phase BB" in src, "bts1.py's VOCAB_VERSION comment records the v56 (Phase BB) entry")


# --------------------------------------------------------------------------- 2. sly in the engine
def _t_sly_engine() -> None:
    print("sly: the C# declares the base-game keyword and never re-implements the free play:")
    dc = _cs("Engine", "DataCard.cs")
    check('case "sly":         WithKeyword(CardKeyword.Sly, KeywordUpgrade("sly")); break;' in dc,
          "DataCard declares CardKeyword.Sly for the sly flag-op")
    check('case "sly":      WithKeyword(CardKeyword.Sly, UpgradeType.Add); break;' in dc,
          "DataCard's upgrade-adds-keyword switch knows sly")
    check("AutoPlayType.SlyDiscard" in dc and "[BB] sly" in dc,
          "DataCard logs the [BB] tag off the game's BeforeCardAutoPlayed(SlyDiscard) hook")
    disc = dc.split("public override Task AfterCardDiscarded", 1)[1].split("internal async Task FireOnDiscard", 1)[0]
    check("Sly" not in disc, "AfterCardDiscarded does NOT route Sly (the game's DiscardAndDraw already plays it)")
    er = _cs("Engine", "EffectRunner.cs")
    check('case "sly":' in er.split('case "ethereal":', 1)[1].split("break;", 1)[0],
          "EffectRunner treats sly as a declare-time keyword (no-op at play)")
    # every mod discard is a BATCH call (the Sly timing the game warns about)
    for site in ("DiscardRandom", "DiscardChoose", "Scry"):
        body = er.split(f"internal static async Task {site}(", 1)[1].split("internal static", 1)[0]
        check("CardCmd.Discard(ctx, " in body, f"{site} discards through the batch CardCmd.Discard (Sly-safe)")
    fc = _cs("Engine", "ForgedCards.cs")
    for lst in ("SupportedOps", "UpgradeAddableKeywords", "KeywordOps"):
        block = fc.split(f"{lst} =", 1)[1].split("];", 1)[0]
        check('"sly"' in block, f"ForgedCards.{lst} carries sly")
    check('case "sly":         parts.Add("Sly."); break;' in fc, "C# Describe renders 'Sly.'")
    check("a card can't be both 'sly' and 'retain'" in fc, "C# rejects sly + retain")
    check("'sly' is not allowed on a Power" in fc, "C# rejects sly on a Power")


# --------------------------------------------------------------------------- 3. sly rules (Python)
def _t_sly_rules() -> None:
    print("sly: the validator mirrors the C# rules:")
    check(_ok(_card([{"op": "sly"}, DMG])), f"a Sly attack validates: {_errs(_card([{'op': 'sly'}, DMG]))}")
    check(_ok(_card([{"op": "sly"}, {"op": "block", "amount": 5}], ctype="skill", target="self")),
          "a Sly skill validates")
    errs = _errs(_card([{"op": "sly"}, {"op": "retain"}, DMG]))
    check(any("'sly' and 'retain'" in e for e in errs), f"sly + retain is rejected: {errs}")
    errs = _errs(_card([{"op": "sly"}, {"op": "apply_status", "status": "strength", "amount": 1}],
                       ctype="power", target="self"))
    check(any("not allowed on a Power" in e for e in errs), f"sly on a Power is rejected: {errs}")
    # an upgrade may APPEND sly (the AX one-keyword rule)
    check(_ok(_card([DMG], upgrade=[{"op": "damage", "amount": 9}, {"op": "sly"}])),
          "an upgrade may append sly")
    errs = _errs(_card([{"op": "retain"}, DMG], upgrade=[{"op": "retain"}, {"op": "damage", "amount": 9}, {"op": "sly"}]))
    check(any("'sly' and 'retain'" in e for e in errs), "an upgrade appending sly onto a retain card is rejected")
    # pricing: the free replay is worth something
    v = _v()
    check(v.score_card(_card([{"op": "sly"}, DMG])) > v.score_card(_card([DMG])), "sly carries a price premium")
    # class-level: a Sly card needs an outlet
    check(sly_warnings([_card([{"op": "sly"}, DMG])]) != [], "sly with no discard/scry outlet warns")
    check(sly_warnings([_card([{"op": "sly"}, DMG]), _card([{"op": "discard", "amount": 1}], ctype="skill", target="self")]) == [],
          "sly with a discard outlet is fine")
    check(sly_warnings([_card([{"op": "sly"}, DMG]),
                        _card([{"op": "add_trigger", "trigger": "turn_start", "effects": [{"op": "discard", "amount": 1}]}],
                              ctype="power", target="self")]) == [],
          "a payload discard counts as an outlet")


# --------------------------------------------------------------------------- 4. turn_at_most
def _t_turn_at_most() -> None:
    print("turn_at_most: Conditions + schema + validator:")
    cond = _cs("Engine", "Conditions.cs")
    m = re.search(r"Kinds =\s*\[(.*?)\];", cond, re.S)
    check(m is not None and '"turn_at_most"' in m.group(1), "Conditions.Kinds carries turn_at_most")
    check('case "turn_at_most":' in cond and "RoundNumber <= c.Value" in cond, "Eval: RoundNumber <= value")
    check('"turn_at_most"       => $"it is turn {c.Value} or earlier"' in cond, "Phrase: 'it is turn N or earlier'")
    check('|| c.Kind == "turn_at_most" // Phase BB (v56)' in cond and "&& c.Value < 1)" in cond,
          "Validate: needs value >= 1")  # Phase BJ (v62) appended played_cards_last_turn_ge to the same list
    schema = json.loads(CARD_SCHEMA.read_text(encoding="utf-8"))
    kinds = set(schema["$defs"]["condition"]["properties"]["kind"]["enum"])
    check("turn_at_most" in kinds, "schema condition enum carries turn_at_most")
    check(any(r.get("if", {}).get("properties", {}).get("kind", {}).get("const") == "turn_at_most"
              for r in schema["$defs"]["condition"]["allOf"]), "schema requires a value on turn_at_most")
    gated = _card([DMG, {"op": "gain_energy", "amount": 1, "when": {"kind": "turn_at_most", "value": 2}}])
    check(_ok(gated), f"a turn_at_most-gated card validates: {_errs(gated)}")
    check(not _ok(_card([DMG, {"op": "gain_energy", "amount": 1, "when": {"kind": "turn_at_most"}}])),
          "turn_at_most without a value is rejected")
    trig = _card([{"op": "add_trigger", "trigger": "turn_start", "when": {"kind": "turn_at_most", "value": 2},
                   "effects": [{"op": "draw", "amount": 1}]}], ctype="power", target="self")
    check(_ok(trig), f"turn_at_most is a legal trigger gate (a player read): {_errs(trig)}")
    check("turn_at_most" in cf._ORB_CONDITION_KINDS and "turn_at_most" in cf._ORB_CONDITION_VALUE_KINDS,
          "turn_at_most is legal inside a custom-orb effect (with a value), like its mirror")
    # the blueprint's uptime heuristic knows the mirror
    src = pathlib.Path(cf.__file__).read_text(encoding="utf-8")
    check('elif kind == "turn_at_most":' in src, "class_forge's condition-uptime heuristic has a turn_at_most branch")


# --------------------------------------------------------------------------- 5. describe byte-match
def _t_describe() -> None:
    print("describe: Python == C# byte for byte:")
    check(cardgen.describe([{"op": "sly"}, {"op": "damage", "amount": 5}], "enemy") == "Sly.\nDeal {Damage} damage.",
          f"sly sentence: {cardgen.describe([{'op': 'sly'}, {'op': 'damage', 'amount': 5}], 'enemy')!r}")
    txt = cardgen.describe([{"op": "damage", "amount": 8},
                            {"op": "gain_energy", "amount": 1, "when": {"kind": "turn_at_most", "value": 2}}], "enemy")
    check(txt == "Deal {Damage} damage.\nGain {Energy} energy if it is turn 2 or earlier.", f"turn_at_most weave: {txt!r}")
    txt = cardgen.describe([{"op": "block", "amount": 5, "when": {"kind": "turn_at_most", "value": 1, "negate": True}}], "self")
    check(txt == "Gain {Block} Block unless it is turn 1 or earlier.", f"negated: {txt!r}")


# --------------------------------------------------------------------------- 6. the contract surfaces
def _t_contract() -> None:
    print("contract surfaces (vocabulary / schema / exemplars / menus / census / catalog / render.js):")
    vocab = paths.VOCABULARY.read_text(encoding="utf-8")
    check("| `sly`" in vocab, "VOCABULARY has a sly op row")
    check("| `turn_at_most`" in vocab, "VOCABULARY has a turn_at_most condition row")
    check("`ethereal` / `sly`" in vocab, "VOCABULARY's card-shape rule lists sly as an appendable keyword")
    schema = json.loads(CARD_SCHEMA.read_text(encoding="utf-8"))
    ops = set(schema["$defs"]["effect"]["properties"]["op"]["enum"])
    check("sly" in ops, "the card op enum carries sly")
    check("sly" not in set(schema["$defs"]["triggerEffect"]["properties"]["op"]["enum"]),
          "sly is not a trigger-payload op (a keyword has no payload meaning)")

    pool = json.loads(EXEMPLAR_POOL.read_text(encoding="utf-8"))["exemplars"]
    by_id = {e["card"]["id"]: e for e in pool}
    for eid, tok in (("ex_pocket_dagger", '"sly"'), ("ex_first_light", "turn_at_most")):
        check(eid in by_id, f"exemplar {eid} exists")
        if eid in by_id:
            check(_ok(dict(by_id[eid]["card"], id="bb_ex")), f"exemplar {eid} validates: {_errs(dict(by_id[eid]['card'], id='bb_ex'))}")
            check(tok in json.dumps(by_id[eid]["card"]), f"exemplar {eid} uses {tok}")

    check("sly" in census.KEYWORD_OPS, "census counts sly as a keyword kind")
    cc = census.walk_card(_card([{"op": "sly"}, DMG]))
    check("sly" in cc.keyword_kinds and not cc.plain, "a Sly card is a keyword shape, not a plain stat line")
    check(any(k == "turn_at_most" for k, _ in coverage.WHEN_MENU_V2), "WHEN_MENU_V2 carries turn_at_most")
    check("turn_at_most" in coverage.CENSUS_DETECTOR, "turn_at_most has a census detector")
    check(any(f.id == "first_blood" for f in featured.FEATURED_MENU), "featured menu has first_blood (turn_at_most)")
    check(any(f.id == "sly_fuel" for f in featured.FEATURED_CLASS_KIND["discard"]),
          "the discard class-kind menu has sly_fuel")
    check(not any(k == "sly" for k, _ in coverage.KEYWORD_MENU), "sly is deliberately NOT on the keyword quota menu")
    check("sly" in harness_v2._PREFERRED_OPS and "turn_at_most" in harness_v2._PREFERRED_CONDITIONS,
          "the harness names both tokens in its compositional clause lists")
    clause = harness_v2.compositional_clause()
    check("`sly`" in clause and "turn_at_most" in clause, "... and the live clause mentions them")

    arch = json.loads(ARCHETYPES.read_text(encoding="utf-8"))["archetypes"]
    by_a = {a["id"]: a for a in arch}
    check("sly" in by_a["madness_discard"]["vocabulary"]["ops"], "madness_discard lists sly")
    check("turn_at_most" in by_a["ambush_alpha"]["vocabulary"]["ops"], "ambush_alpha lists turn_at_most")
    check("`sly`" in by_a["madness_discard"]["build_notes"] and "`turn_at_most`" in by_a["ambush_alpha"]["build_notes"],
          "both build_notes name the new token")
    heur = (paths.VOCABULARY.parent / "DESIGN_HEURISTICS.md").read_text(encoding="utf-8")
    check("`sly` (v56)" in heur and "turn_at_most gate (v56)" in heur, "DESIGN_HEURISTICS prices both")

    js = RENDER_JS.read_text(encoding="utf-8")
    check('case "sly": return "Sly";' in js, "render.js renders sly")
    check('case "turn_at_most":' in js, "render.js renders turn_at_most")

    bp = cf._BlueprintContract(mode="dossier", triad=True, seed=1).system_prompt()
    print(f"  (rule 0.9) blueprint prompt: {len(bp):,} chars "
          f"(scaffolding {len(bp) - len(vocab):,}; the ONE ceiling lives in tests/test_harness_v2.py)")


def main() -> int:
    test_version()
    _t_sly_engine()
    _t_sly_rules()
    _t_turn_at_most()
    _t_describe()
    _t_contract()
    print(f"\n{_PASS} passed, {_FAIL} failed")
    return 1 if _FAIL else 0


def test_phase_bb_all() -> None:
    """The pytest entry point: run every section and FAIL the run if any check did (the BA idiom)."""
    global _PASS, _FAIL
    _PASS = _FAIL = 0
    rc = main()
    assert rc == 0, f"{_FAIL} Phase BB check(s) failed - see the FAIL lines above"


if __name__ == "__main__":
    sys.exit(main())
