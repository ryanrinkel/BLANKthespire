"""Phase BK — `hits_scale`: a damage op's HIT COUNT from a live read (Whirlwind / Finisher / Flechettes …)
(VOCAB_EXPANSION_6_PLAN, gap #65, vocab v63) — offline.
Run:  uv run python -m tests.test_phase_bk  (from generation/)

Pins: the stamp; the engine wiring (the BaseLib NAMED calc-var "CalculatedHits" in DataCard, the capped read + the two
[BK] tags in EffectRunner, the three new ScaleValue reads, the X coupling, the one-multi-hit / upgrade / payload rules
in ForgedCards); the validator rules on both sides; the describe byte-match (Python literals asserted, the C# fragments
grepped, one case per source noun); the contract surfaces (schema, VOCABULARY row, gate field unit, census, bridges,
coverage, archetypes, exemplars, heuristics, gap log, render.js, the pitch sentence, orb-class gating); the saved
AutoSlay tag greps under tests/gaptest-bk/; and prints the rule-0.9 readings (informational).
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

from btsgen import bridges, bts1, cardgen, census, coverage, gate, harness_v2, paths  # noqa: E402
from btsgen import class_forge as cf  # noqa: E402
from btsgen.validator import CardValidator  # noqa: E402

_PASS = 0
_FAIL = 0
MOD_CODE = paths.VOCABULARY.parents[1] / "BlankTheSpireCode"
CARD_SCHEMA = paths.VOCABULARY.parent / "card.schema.json"
REPO = paths.VOCABULARY.parents[2]
DATA = pathlib.Path(cf.__file__).parent / "data"
TESTER_DIR = pathlib.Path(__file__).parent / "gaptest-bk"
SMOKE_SEEDS = ("GAPTESTBK1", "GAPTESTBK2")

SOURCES = ("x", "attacks_played_this_turn", "cards_in_hand", "skills_in_hand", "plays_this_combat",
           "exhaust_pile_size", "hp_loss_events_this_combat", "energy_spent_this_turn", "orb_count")
NOUNS = {
    "attacks_played_this_turn": "Attack you played this turn",
    "cards_in_hand": "other card in your hand",
    "skills_in_hand": "Skill in your hand",
    "plays_this_combat": "card you have played this combat",
    "exhaust_pile_size": "card in your exhaust pile",
    "hp_loss_events_this_combat": "time you have lost HP this combat",
    "energy_spent_this_turn": "energy you have spent this turn",
    "orb_count": "orb you have channeled",
}
# AutoSlay never pays energy, so the energy-spent read is the one source the smoke can only prove as a READ (0 hits ->
# the skip tag); every other source must reach a non-zero hit count on the saved seeds.
SMOKE_ZERO_OK = {"energy_spent_this_turn"}


def check(cond: bool, msg: str) -> None:
    global _PASS, _FAIL
    if cond:
        _PASS += 1
    else:
        _FAIL += 1
        print(f"  FAIL: {msg}")


def _cs(*parts: str) -> str:
    return (MOD_CODE.joinpath(*parts)).read_text(encoding="utf-8").replace("\r\n", "\n")


def _card(effects, rarity="uncommon", cost=1, ctype="attack", target="enemy", upgrade=None):
    c = {"id": "bk_t", "name": "BK", "type": ctype, "rarity": rarity, "cost": cost, "target": target, "effects": effects}
    if upgrade is not None:
        c["upgrade"] = {"effects": upgrade}
    return c


def _hs(src, amount=4, **kw):
    e = {"op": "damage", "amount": amount, "hits_scale": src}
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
    print("Phase BK vocab stamp is at least 63 (Python + C#):")
    check(bts1.VOCAB_VERSION >= 63, f"bts1.VOCAB_VERSION >= 63, got {bts1.VOCAB_VERSION}")
    fc = _cs("Engine", "ForgedCards.cs")
    m = re.search(r"public const int VocabVersion = (\d+);", fc)
    check(m is not None and int(m.group(1)) >= 63, f"ForgedCards.VocabVersion >= 63, got {m and m.group(1)}")
    check(m is not None and bts1.VOCAB_VERSION <= int(m.group(1)), "bts1.VOCAB_VERSION <= ForgedCards.VocabVersion")
    check("Phase BK" in fc and "`hits_scale`" in fc and "`attacks_played_this_turn`" in fc,
          "ForgedCards.cs comment names Phase BK + the tokens")
    check("63: Phase BK" in pathlib.Path(bts1.__file__).read_text(encoding="utf-8"), "bts1.py records the v63 entry")


def _t_engine() -> None:
    print("the engine: the named calc-var, the capped read + tags, the new reads, the X coupling, the card rules:")
    dc = _cs("Engine", "DataCard.cs")
    check("WithCalculatedVar(EffectRunner.CalculatedHitsKey, 0, (c, _) => EffectRunner.ScaleValue(e.HitsScale, c));" in dc,
          "DataCard declares the BaseLib NAMED calc-var (coexists with CalculatedDamage)")
    er = _cs("Engine", "EffectRunner.cs")
    check('internal const int HitsScaleCap = 10;' in er, "HitsScaleCap = 10 (plan §7 decision 3)")
    check('internal const string CalculatedHitsKey = "CalculatedHits";' in er, "the base Finisher var name")
    check("hits = Math.Min(HitsScaleCap, raw);" in er, "the runtime cap")
    check("? (int)cv.Calculate(play?.Target)" in er, "the count is read off the calc-var (preview == resolve)")
    check('[BK] hits_scale {e.HitsScale} -> {hits} hits (raw {raw}, cap {HitsScaleCap}) x ' in er, "the [BK] hit tag")
    check('[BK] hits_scale {e.HitsScale} -> 0 hits, skipped (raw {raw})' in er, "the [BK] 0-hit skip tag")
    i = er.index("[BK] hits_scale {e.HitsScale} -> 0 hits, skipped")
    check("break;" in er[i:i + 200], "0 hits skips the swing (no empty attack)")
    for frag, base in (('"attacks_played_this_turn"   => AttacksPlayedThisTurn(card.Owner),', "Finisher"),
                       ('"skills_in_hand"             => SkillsInHand(card.Owner),', "Flechettes"),
                       ('"orb_count"                  => card.Owner?.PlayerCombatState?.OrbQueue?.Orbs?.Count ?? 0,', "orbs"),
                       ("entry.HappenedThisTurn(cs) && entry.CardPlay.Card.Type == CardType.Attack", "Finisher recipe"),
                       ("Hand?.Cards?.Count(c => c.Type == CardType.Skill)", "Flechettes recipe"),
                       ('"x"                        => card.ResolveEnergyXValue(),', "X = ResolveEnergyXValue")):
        check(frag in er, f"{base}: {frag}")
    fc = _cs("Engine", "ForgedCards.cs")
    m = re.search(r"HitsScaleSources =\s*\[(.*?)\];", fc, re.S)
    check(m is not None and set(re.findall(r'"(\w+)"', m.group(1))) == set(SOURCES), "HitsScaleSources == the nine sources")
    m = re.search(r"SupportedScales =\s*\[(.*?)\];", fc, re.S)
    check(m is not None and not ({"attacks_played_this_turn", "skills_in_hand", "orb_count"} & set(re.findall(r'"(\w+)"', m.group(1)))),
          "the three new reads are hits_scale-only (not `scale` sources)")
    for frag in ('bool anyX = effects.Any(e => e.ScaleX || e.HitsScale == "x");',
                 "if (effects.Count(e => e.Hits > 1 || e.HitsScale != null) > 1)",
                 "if (effects[i].HitsScale != upgrade[i].HitsScale)",
                 "if (t.HitsScale != null) // Phase BK",
                 "HitsScale: hitsScale));",
                 "return \"'hits_scale' and 'scale' can't combine on one effect (the per-hit damage is the printed amount).\";"):
        check(frag in fc, f"ForgedCards: {frag}")
    check("string? HitsScale = null)" in _cs("Engine", "CardSpec.cs"), "EffectSpec.HitsScale")
    # BaseLib: the named overload never touches the one-basegame-calc-var guard (the verify-first finding)
    bl = pathlib.Path(r"C:/Users/ryanr/Desktop/NOVOGODOT/BLANKthespire/_modref/BaseLib-StS2/Abstracts/ConstructedCardModel.cs")
    if bl.exists():
        src = bl.read_text(encoding="utf-8")
        body = src[src.index("protected ConstructedCardModel WithCalculatedVar(string name, int baseVal,"):]
        body = body[:body.index("protected ConstructedCardModel WithCalculatedBlock(")]
        check("_hasBasegameCalculatedVar" not in body, "BaseLib WithCalculatedVar(name, …) never sets _hasBasegameCalculatedVar")


CASES = [([_hs("x", 5)], "all_enemies", "Deal {Damage} damage X times to ALL enemies."),
         ([_hs("x", 5)], "random_enemy", "Deal {Damage} damage X times to a random enemy."),
         ([_hs("attacks_played_this_turn", 6, unblockable=True)], "enemy",
          "Deal {Damage} damage for each Attack you played this turn, ignoring Block."),
         ([{"op": "channel_orb", "orb": "lightning", "amount": 1}, _hs("orb_count", 3)], "enemy",
          "Channel a Lightning orb.\nDeal {Damage} damage for each orb you have channeled.")]
CASES += [([_hs(src)], "enemy", f"Deal {{Damage}} damage for each {noun}.") for src, noun in NOUNS.items()]


def _t_rules_and_describe() -> None:
    print("validator + describe (Python literal == the C# fragment written by hand):")
    ok = [_card([_hs("x", 5)], cost="X", target="all_enemies"),
          _card([_hs("attacks_played_this_turn", 6)], upgrade=[_hs("attacks_played_this_turn", 8)]),
          _card([_hs("skills_in_hand", 4)]), _card([_hs("cards_in_hand", 3)], target="random_enemy"),
          _card([_hs("plays_this_combat", 2)], rarity="rare"), _card([_hs("exhaust_pile_size", 4)]),
          _card([_hs("hp_loss_events_this_combat", 3)]), _card([_hs("energy_spent_this_turn", 3)], cost=0),
          _card([{"op": "channel_orb", "orb": "lightning", "amount": 1}, _hs("orb_count", 3)]),
          _card([_hs("cards_in_hand", 3, unblockable=True)], rarity="rare"),
          # coexists with a scaled block (CalculatedBlock) on the same card — the named var is outside that budget
          _card([{"op": "block", "amount": 1, "scale": "cards_in_hand"}, _hs("skills_in_hand", 3)])]
    for c in ok:
        check(not _errs(c), f"validates: {json.dumps(c['effects'])} -> {_errs(c)}")
    bad = [(_card([_hs("x", 5)]), "requires the card cost to be"),
           (_card([_hs("cards_in_hand")], cost="X"), "needs a 'scale:x' or 'hits_scale:x' effect"),
           (_card([_hs("cards_in_hand", hits=2)]), "can't combine on one effect (hits_scale IS the hit count)"),
           (_card([_hs("cards_in_hand", scale="block")]), "'hits_scale' and 'scale' can't combine"),
           (_card([_hs("cards_in_hand", grow=2)]), "'hits_scale' can't combine with 'grow'"),
           (_card([{"op": "block", "amount": 4, "hits_scale": "cards_in_hand"}], ctype="skill", target="self"),
            "'hits_scale' only applies to damage"),
           (_card([_hs("block_count")]), "unsupported hits_scale"),
           (_card([_hs("cards_in_hand"), _hs("skills_in_hand")]), "at most one multi-hit"),
           (_card([_hs("cards_in_hand"), {"op": "damage", "amount": 2, "hits": 3}]), "at most one multi-hit"),
           (_card([_hs("cards_in_hand", 4)], upgrade=[_hs("skills_in_hand", 6)]), "an upgrade can't change 'hits_scale'"),
           (_card([{"op": "add_trigger", "trigger": "turn_start",
                    "effects": [{"op": "damage", "amount": 3, "target": "enemy", "hits_scale": "cards_in_hand"}]}],
                  ctype="power", target="self"), "hits_scale")]
    for c, frag in bad:
        e = _errs(c)
        check(any(frag in x for x in e), f"rejected ({frag}): {json.dumps(c['effects'])} -> {e}")
    # pricing: per-hit damage × the expected count
    v = _V
    check(v._score_effect(_hs("x", 5)) == 12.5, "x is priced at ~2.5 hits")
    check(v._score_effect(_hs("attacks_played_this_turn", 6)) == 12.0, "Finisher is priced at ~2 hits")
    check(v._score_effect(_hs("cards_in_hand", 3)) == 9.0, "cards_in_hand is priced at ~3 hits")
    check(v._score_effect(_hs("plays_this_combat", 2)) >= 12.0, "plays_this_combat is a late-game count")
    # orb_count is orb-class only (dropped off a slotless class like every orb-reading card)
    check(cf._card_uses_orbs(_card([_hs("orb_count", 3)])) and not cf._card_uses_orbs(_card([_hs("cards_in_hand", 3)])),
          "class_forge._card_uses_orbs knows the orb_count hit count")
    for effects, target, want in CASES:
        got = cardgen.describe(effects, target)
        check(got == want, f"describe {got!r} == {want!r}")
    fc = _cs("Engine", "ForgedCards.cs")
    for src, noun in NOUNS.items():
        check(cardgen._hits_phrase(src) == noun, f"cardgen._hits_phrase({src}) == {noun!r}")
        check(re.search(r'"' + src + r'"\s+=> "' + re.escape(noun) + '",', fc) is not None, f"C# HitsPhrase: {src} => {noun!r}")
    for frag in ('? $"Deal {{Damage}} damage X times{dmgSuffix}{ub}."',
                 ': $"Deal {{Damage}} damage for each {HitsPhrase(e.HitsScale)}{dmgSuffix}{ub}.");'):
        check(frag in fc, f"C# Describe fragment: {frag}")
    check(cardgen.effect_literal(_hs("x", 5)) == 'new EffectSpec("damage", 5, HitsScale: "x")', "effect_literal: HitsScale")
    check(cardgen.effect_literal(_hs("cards_in_hand", 3, unblockable=True))
          == 'new EffectSpec("damage", 3, HitsScale: "cards_in_hand", Unblockable: true)', "effect_literal: + Unblockable")


def _t_contract() -> None:
    print("contract surfaces:")
    schema = json.loads(CARD_SCHEMA.read_text(encoding="utf-8"))
    eff = schema["$defs"]["effect"]
    check(eff["additionalProperties"] is False and set(eff["properties"]["hits_scale"]["enum"]) == set(SOURCES),
          "schema: the effect object declares hits_scale with the nine sources")
    check("hits_scale" not in schema["$defs"]["triggerEffect"]["properties"]
          and schema["$defs"]["triggerEffect"].get("additionalProperties") is False, "schema: never on a payload effect")
    rules = json.dumps(eff.get("allOf", []))
    check('"if": {"required": ["hits_scale"]}' in rules and '{"required": ["grow_held"]}' in rules,
          "schema: hits_scale is damage-only and excludes hits/scale/grow/grow_held")
    vocab = paths.VOCABULARY.read_text(encoding="utf-8")
    check(vocab.count("- `hits_scale` (v63):") == 1, "VOCABULARY: ONE hits_scale row")
    live = set(re.findall(r"`([a-z][a-z0-9_]*)`", vocab))
    check(set(SOURCES) - {"x"} <= live and "hits_scale" in live, f"VOCABULARY backticks the tokens (missing {set(SOURCES) - {'x'} - live})")
    check("hits_scale" in gate.vocab_tokens(vocab) and "`hits_scale` —" in gate.vocab_index(vocab), "the index carries a hits_scale line")
    check(gate.FIELD_UNITS.get("hits_scale") == ("fam:scaling",), "gate.FIELD_UNITS: hits_scale rides the scaling family")
    cc = census.walk_card(_card([_hs("skills_in_hand", 4)]))
    check(cc.hits_scale.get("skills_in_hand") == 1 and cc.multi_hit == 1 and cc.scaled_or_x and not cc.plain,
          "census: the hits_scale counter (+ multi-hit, scaled, not plain)")
    check("hits_scale (BK, v63):" in census.format_report([("bk", census.Census())]), "census.format_report line")
    check("hits_scale" in bridges.card_tokens(_card([_hs("cards_in_hand")])), "bridges.card_tokens surfaces hits_scale")
    check(("hits_scale" in dict(coverage.SCALE_MENU)) and coverage.CENSUS_DETECTOR["hits_scale"](cc),
          "coverage.SCALE_MENU line + its detector")
    arch = {a["id"]: a for a in json.loads((DATA / "archetypes.json").read_text(encoding="utf-8"))["archetypes"]}
    for aid in ("strike_tempo", "big_energy", "horde_breaker"):
        a = arch[aid]
        check("hits_scale" in a["vocabulary"]["ops"], f"{aid} claims hits_scale")
        check("VOCABULARY_GAPS#65" in a["gap_refs"] and a["buildable"] is True, f"{aid} refs gap #65 and stays buildable")
        check("(v63)" in a.get("build_notes", ""), f"{aid} build_notes name the v63 shape")
    pool = json.loads((DATA / "exemplar_pool.json").read_text(encoding="utf-8"))["exemplars"]
    v = harness_v2.exemplar_validator()
    used = set()
    for e in pool:
        for eff_ in e["card"].get("effects", []):
            if eff_.get("hits_scale"):
                used.add(eff_["hits_scale"])
                r = v.validate(dict(e["card"]))
                check(r.ok, f"exemplar {e['card']['id']} validates: {r.errors}")
                if eff_["hits_scale"] == "orb_count":
                    check(e.get("needs") == "orb", f"{e['card']['id']} (orb_count) needs orb")
    check({"x", "attacks_played_this_turn", "skills_in_hand", "exhaust_pile_size", "orb_count"} <= used,
          f"exemplars: Whirlwind / Finisher / Flechettes / exhaust ripper / orb_count (got {sorted(used)})")
    heur = (paths.VOCABULARY.parent / "DESIGN_HEURISTICS.md").read_text(encoding="utf-8")
    check(heur.count("v63)") >= 3 and "`hits_scale`" in heur, "DESIGN_HEURISTICS prices hits_scale on the three archetypes")
    gaps = (REPO / "VOCABULARY_GAPS.md").read_text(encoding="utf-8")
    entry = gaps.split("### 65.", 1)[1].split("### 66.", 1)[0]
    check("**Status:** **done (2026-10-04, vocab v63, Phase BK)**" in entry, "gap #65 is done")
    js = (REPO / "web" / "static" / "render.js").read_text(encoding="utf-8")
    for src, noun in NOUNS.items():
        check(f'{src}: "{noun}"' in js, f"render.js HITS_NOUN: {src}")
    check('e.hits_scale === "x" ? "X times"' in js, "render.js: the X-times form")
    src = pathlib.Path(cf.__file__).read_text(encoding="utf-8")
    check('Hit counts (v63): "hits_scale" on a damage = one hit per unit' in src, "the SCALED AMOUNTS pitch sentence")


def _t_smoke_record() -> None:
    print("the saved AutoSlay tag greps (TEST_AUDIT_2026-10 §7):")
    seen = ""
    for seed in SMOKE_SEEDS:
        p = TESTER_DIR / f"godot_BK_tags_{seed}.txt"
        assert p.exists(), f"missing smoke record {p}"
        txt = p.read_text(encoding="utf-8")
        check("[BK]" in txt, f"{p.name} holds [BK] tags")
        check("mod exceptions: 0" in txt and "Localization formatting errors: 0" in txt
              and "BlankTheSpire stack frames: 0" in txt, f"{p.name} records a clean run")
        seen += txt
    for s in SOURCES:
        check(f"[BK] hits_scale {s} -> " in seen, f"the smoke fired '[BK] hits_scale {s}'")
        if s not in SMOKE_ZERO_OK:
            check(re.search(r"\[BK\] hits_scale " + s + r" -> [1-9]\d* hits", seen) is not None, f"'{s}' reached a non-zero hit count")
    check(re.search(r"-> 10 hits \(raw (1[1-9]|[2-9]\d), cap 10\)", seen) is not None, "the 10-hit cap was observed (raw > 10)")
    check("-> 0 hits, skipped" in seen, "the 0-hit skip tag fired")
    check((TESTER_DIR / "build_tester.py").exists(), "the tester is committed next to the phase test")


def _t_budget() -> None:
    print("rule 0.9 (informational) — readings on the real path:")
    from tests.test_harness_v2 import rule_0_9_readings
    with _env(BTS_HARNESS_V2="1", BTS_BLUEPRINT_VOCAB="tree"):
        r = rule_0_9_readings()
    print(f"  (reading) index                  {r['index']:>8,}  (clause cap {r['index_clause_cap']}; budget 8,500)")
    print(f"  (reading) per-archetype max      {r['archetype_max']:>8,}  ({r['archetype_max_id']}; ceiling 70,000)")
    print(f"  (reading) per-archetype scaffold {r['archetype_scaffold_max']:>8,}  ({r['archetype_scaffold_max_id']}; budget 32,000)")
    print(f"  (reading) triads                 {', '.join(f'{k} {v:,}' for k, v in r['triads'].items())}  (budget 80,000)")
    print(f"  (reading) all-ops path           {r['all_ops']:>8,}  (tripwire 140,000)")
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


def test_phase_bk_all() -> None:
    global _PASS, _FAIL
    _PASS = _FAIL = 0
    assert main() == 0, f"{_FAIL} Phase BK check(s) failed - see the FAIL lines above"


if __name__ == "__main__":
    sys.exit(main())
