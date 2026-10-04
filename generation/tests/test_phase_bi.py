"""Phase BI — CARD TRIGGER FILTERS: the relic v48 hook filters ported to card `add_trigger` — `card_type`, `every_n`,
`scope:"this_turn"` and the payload target `random_enemy` (VOCAB_EXPANSION_6_PLAN, gap #62, vocab v61) — offline.
Run:  uv run python -m tests.test_phase_bi  (from generation/)

Pins: the stamp; the engine wiring (ForgedTriggerPower filter + per-combat counter + this_turn self-removal, the
random-enemy roll, the `status` hand kind, the EveryN parse); the validator rules on both sides; the describe
byte-match (Python literals asserted, the C# fragments grepped); the contract surfaces (schema, VOCABULARY, gate
FIELD_UNITS, census, bridges, archetypes, exemplars, heuristics, gap log, render.js, the TRIGGERS pitch); the saved
AutoSlay tag greps under tests/gaptest-bi/; and prints the rule-0.9 readings (informational).
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

from btsgen import bridges, bts1, cardgen, census, gate, paths  # noqa: E402
from btsgen import class_forge as cf  # noqa: E402
from btsgen.validator import CardValidator  # noqa: E402

_PASS = 0
_FAIL = 0
MOD_CODE = paths.VOCABULARY.parents[1] / "BlankTheSpireCode"
CARD_SCHEMA = paths.VOCABULARY.parent / "card.schema.json"
REPO = paths.VOCABULARY.parents[2]
DATA = pathlib.Path(cf.__file__).parent / "data"
TESTER_DIR = pathlib.Path(__file__).parent / "gaptest-bi"
SMOKE_SEEDS = ("GAPTESTBI1", "GAPTESTBI2")
BI_TAGS = ("[BI] card_type", "[BI] every_n count", "[BI] this_turn trigger removed", "[BI] random_enemy payload ->")


def check(cond: bool, msg: str) -> None:
    global _PASS, _FAIL
    if cond:
        _PASS += 1
    else:
        _FAIL += 1
        print(f"  FAIL: {msg}")


def _cs(*parts: str) -> str:
    return (MOD_CODE.joinpath(*parts)).read_text(encoding="utf-8")


def _card(effects, rarity="uncommon", cost=1, ctype="power"):
    return {"id": "bi_t", "name": "BI", "type": ctype, "rarity": rarity, "cost": cost, "target": "self", "effects": effects}


def _trig(trigger, payload, **flags):
    t = {"op": "add_trigger", "trigger": trigger, "effects": payload}
    t.update(flags)
    return t


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


RAGE = _trig("on_card_played", [{"op": "block", "amount": 3}], card_type="attack", scope="this_turn")
JUGGLE = _trig("on_card_played", [{"op": "damage", "amount": 4, "target": "random_enemy"}], card_type="attack", every_n=3)
PANACHE = _trig("on_card_played", [{"op": "draw", "amount": 1}], every_n=5)
ITERATION = _trig("on_card_drawn", [{"op": "draw", "amount": 1}], card_type="status", once_per_turn=True)


def test_version() -> None:
    print("Phase BI vocab stamp is at least 61 (Python + C#):")
    check(bts1.VOCAB_VERSION >= 61, f"bts1.VOCAB_VERSION >= 61, got {bts1.VOCAB_VERSION}")
    fc = _cs("Engine", "ForgedCards.cs")
    m = re.search(r"public const int VocabVersion = (\d+);", fc)
    check(m is not None and int(m.group(1)) >= 61, f"ForgedCards.VocabVersion >= 61, got {m and m.group(1)}")
    check(m is not None and bts1.VOCAB_VERSION <= int(m.group(1)), "bts1.VOCAB_VERSION <= ForgedCards.VocabVersion")
    check("Phase BI" in fc and "`every_n`" in fc and "`random_enemy`" in fc, "ForgedCards.cs comment names Phase BI + the filters")
    check("61: Phase BI" in pathlib.Path(bts1.__file__).read_text(encoding="utf-8"), "bts1.py records the v61 entry")


def _t_engine() -> None:
    print("the engine: filter + counter + this_turn removal on the trigger power, the random roll, the parse:")
    tp = _cs("Powers", "ForgedTriggerPower.cs")
    check("EffectRunner.HandKindMatches(cardFilter, t.CardKind)" in tp, "FireReactive filters on the card's type (HandKindMatches)")
    check('[BI] card_type {t.CardKind} matched' in tp, "the [BI] card_type tag")
    check("await FireReactive(kind, ctx, cardFilter: cardPlay.Card);" in tp, "AfterCardPlayed hands in the played card")
    check('await FireReactive("on_card_drawn", ctx, cardFilter: card);' in tp, "AfterCardDrawn hands in the drawn card")
    check("private int _everyNCount;" in tp and "int n = ++_everyNCount;" in tp, "the every_n counter is a per-combat instance field")
    check('[BI] every_n count {n}/{t.EveryN} — {(fires ? "FIRES" : "waiting")}' in tp, "the [BI] every_n tag")
    check(tp.count("EveryNFires(t,") == 2, "both reactive paths (FireReactive + on_hp_lost) count every_n")
    check('(Trigger?.EveryN ?? 0) > 1 ? PowerStackType.Counter' in tp, "an every_n power is Counter-stacked (the icon draws the count)")
    check('t?.Scope == "this_turn" && side == Owner.Side' in tp and "await PowerCmd.Remove(this);" in tp,
          "this_turn removes the power at the owner's turn end (RagePower recipe)")
    check("[BI] this_turn trigger removed at turn end" in tp, "the [BI] this_turn tag")
    tr = _cs("Engine", "TriggerRunner.cs")
    check('if (target == "random_enemy")' in tr and "player.RunState.Rng.CombatTargets.NextItem(hittable)" in tr,
          "ResolveEnemies rolls random_enemy on Rng.CombatTargets")
    check("[BI] random_enemy payload ->" in tr, "the [BI] random_enemy tag")
    check('"status"     => c.Type == CardType.Status' in _cs("Engine", "EffectRunner.cs"), "HandKindMatches knows `status`")
    check("int EveryN = 0" in _cs("Engine", "CardSpec.cs"), "EffectSpec.EveryN")  # Phase BK (v63) appended HitsScale after it
    fc = _cs("Engine", "ForgedCards.cs")
    check('int everyN = e.ContainsKey("every_n") ? Int(e, "every_n") : 0;' in fc and "EveryN: everyN" in fc, "ParseEffects reads every_n")
    check('TriggerCardKinds = ["attack", "skill", "power", "non_attack", "status"]' in fc, "the trigger card-kind set")
    check('HandKindFilters = ["attack", "skill", "power", "non_attack"]' in fc, "... and the hand ops' filter stays status-free")
    check("MinEveryN = 2, MaxEveryN = 9" in fc, "the every_n band")
    check("'every_n' can't be combined with 'once_per_combat'" in fc, "every_n + once_per_combat is rejected")
    check('t.Target != "random_enemy"' in fc, "ValidateTrigger allows random_enemy")
    check("e.Op is not (\"exhaust_card\" or \"draw_until\" or \"add_trigger\")" in fc, "the stray card_type rule admits add_trigger")


def _t_rules_and_describe() -> None:
    print("validator + describe (Python literal == the C# fragment written by hand):")
    for name, t, ct in (("rage", RAGE, "skill"), ("juggle", JUGGLE, "power"), ("panache", PANACHE, "power"),
                        ("iteration", ITERATION, "power")):
        check(not _errs(_card([t], ctype=ct)), f"{name} validates: {_errs(_card([t], ctype=ct))}")
    bad = [
        (_trig("on_card_played", [{"op": "block", "amount": 3}], card_type="status"), "on_card_drawn"),
        (_trig("turn_start", [{"op": "block", "amount": 3}], card_type="attack"), "on_card_played/on_card_drawn"),
        (_trig("on_card_played", [{"op": "block", "amount": 3}], every_n=1), "2..9"),
        (_trig("on_card_played", [{"op": "block", "amount": 3}], every_n=10), "2..9"),
        (_trig("turn_end", [{"op": "block", "amount": 3}], every_n=3), "power-hosted multi-fire"),
        (_trig("on_discard", [{"op": "block", "amount": 3}], every_n=3), "power-hosted multi-fire"),
        (_trig("on_card_played", [{"op": "block", "amount": 3}], every_n=3, once_per_combat=True), "once_per_combat"),
        (_trig("turn_start", [{"op": "block", "amount": 3}], scope="this_turn"), "power-hosted reactive"),
        (_trig("ripen", [{"op": "block", "amount": 3}], scope="this_turn", amount=2), "power-hosted reactive"),
        (_trig("on_card_played", [{"op": "block", "amount": 3}], scope="combat"), "this_turn"),
        (_trig("on_card_played", [{"op": "block", "amount": 3, "every_n": 2}]), "every_n"),
    ]
    for t, frag in bad:
        e = _errs(_card([t]))
        check(any(frag in x for x in e), f"rejected ({frag}): {json.dumps(t)} -> {e}")
    e = _errs(_card([{"op": "block", "amount": 5, "every_n": 3}], ctype="skill"))
    check(any("only applies to add_trigger" in x for x in e), f"every_n on a block is a stray field: {e}")
    e = _errs(_card([{"op": "block", "amount": 5, "scope": "this_turn"}], ctype="skill"))
    check(any("only apply to cost_shift" in x for x in e), f"scope on a block stays a stray field: {e}")
    # pricing: an every-N payload is worth amount / n
    v = _V
    base = v._score_effect(_trig("on_card_played", [{"op": "block", "amount": 6}]))
    check(abs(v._score_effect(_trig("on_card_played", [{"op": "block", "amount": 6}], every_n=3)) - base / 3) < 1e-9,
          "every_n prices the payload at amount / n")
    # describe — the literals (byte-match with ForgedCards.TriggerSentence / TriggerFragment)
    cases = [
        (RAGE, "This turn, whenever you play an Attack, gain 3 Block."),
        (JUGGLE, "Every 3rd time you play an Attack, deal 4 damage to a random enemy."),
        (PANACHE, "Every 5th card you play, draw 1 card(s)."),
        (ITERATION, "Whenever you draw a Status, draw 1 card(s) (once per turn)."),
        (_trig("on_card_played", [{"op": "block", "amount": 2}], card_type="skill"), "Whenever you play a Skill, gain 2 Block."),
        (_trig("on_card_played", [{"op": "block", "amount": 2}], card_type="power"), "Whenever you play a Power, gain 2 Block."),
        (_trig("on_card_played", [{"op": "block", "amount": 2}], card_type="non_attack"),
         "Whenever you play a non-Attack card, gain 2 Block."),
        (_trig("on_exhaust", [{"op": "block", "amount": 9}], every_n=2), "Every 2nd time a card is Exhausted, gain 9 Block."),
        (_trig("on_card_drawn", [{"op": "block", "amount": 9}], every_n=4), "Every 4th card you draw, gain 9 Block."),
    ]
    for t, want in cases:
        got = cardgen.describe([t], "self")
        check(got == want, f"describe {got!r} == {want!r}")
    fc = _cs("Engine", "ForgedCards.cs")
    for frag in ('when = $"Whenever you {(t.Trigger == "on_card_drawn" ? "draw" : "play")} {TriggerKindWord(t.CardKind)}";',
                 'when = $"Every {nth} card you play";', 'when = $"Every {nth} card you draw";',
                 'when = $"Every {nth} time {when["Whenever ".Length..]}";',
                 'when = $"This turn, {char.ToLowerInvariant(when[0])}{when[1..]}";',
                 '"attack" => "an Attack", "skill" => "a Skill", "power" => "a Power",',
                 '"non_attack" => "a non-Attack card", "status" => "a Status", _ => "a card",',
                 'n + (n == 2 ? "nd" : n == 3 ? "rd" : "th")',
                 'e.Target == "random_enemy" ? " to a random enemy" : ""'):
        check(frag in fc, f"C# fragment present: {frag}")
    lit = cardgen.effect_literal(JUGGLE)
    check(lit.endswith(', CardKind: "attack", EveryN: 3)') and 'Target: "random_enemy"' in lit, f"effect_literal named args: {lit}")
    check(cardgen.effect_literal(RAGE).endswith(', CardKind: "attack", Scope: "this_turn")'), "effect_literal carries Scope")


def _t_contract() -> None:
    print("contract surfaces:")
    schema = json.loads(CARD_SCHEMA.read_text(encoding="utf-8"))
    eff = schema["$defs"]["effect"]
    check(eff["properties"].get("every_n", {}).get("minimum") == 2 and eff["properties"]["every_n"].get("maximum") == 9,
          "schema: every_n 2..9 on the effect")
    check("status" in eff["properties"]["card_type"]["enum"], "schema: card_type admits status")
    check("random_enemy" in schema["$defs"]["triggerEffect"]["properties"]["target"]["enum"], "schema: payload target random_enemy")
    rules = json.dumps(eff.get("allOf", []))
    check('"enum": ["cost_shift", "exhaust_card", "draw_until", "add_trigger"' in rules, "schema: card_type admits add_trigger")  # BM appends replay_next
    check('"required": ["every_n"]' in rules and '"scope": {"const": "this_turn"}' in rules, "schema: every_n + this_turn clauses")
    vocab = paths.VOCABULARY.read_text(encoding="utf-8")
    check('optional filters `card_type` / `every_n` / `scope:"this_turn"` (v61' in vocab, "VOCABULARY add_trigger row names the filters")
    check("**Filters (v61" in vocab and '"Every 3rd time you play an Attack"' in vocab, "VOCABULARY Triggers prose")
    check('`"random_enemy"` (v61)' in vocab, "VOCABULARY payload targets list random_enemy")
    check(gate.FIELD_UNITS.get("every_n") == ("add_trigger",) and "add_trigger" in gate.FIELD_UNITS["card_type"]
          and "add_trigger" in gate.FIELD_UNITS["scope"], "gate.FIELD_UNITS gates the filter fields with add_trigger")
    cc = census.walk_card(_card([JUGGLE]))
    check(cc.every_n == 1 and cc.trigger_card_types == {"attack": 1} and cc.this_turn_triggers == 0, "census counts every_n / card_type")
    check(census.walk_card(_card([RAGE], ctype="skill")).this_turn_triggers == 1, "census counts this_turn")
    check("trigger filters (BI, v61)" in census.format_report([("bi", census.census_cards([_card([JUGGLE])]))]), "census report line")
    check({"card_type", "every_n"} <= bridges.card_tokens(_card([JUGGLE])), "bridges.card_tokens surfaces the filters")
    arch = {a["id"]: a for a in json.loads((DATA / "archetypes.json").read_text(encoding="utf-8"))["archetypes"]}
    for aid in ("power_ramp", "strike_tempo"):
        a = arch[aid]
        check({"card_type", "every_n"} <= set(a["vocabulary"]["ops"]), f"{aid} claims card_type + every_n")
        check("VOCABULARY_GAPS#62" in a["gap_refs"] and a["buildable"] is True, f"{aid} refs gap #62 and stays buildable")
    pool = {e["card"]["id"]: e for e in json.loads((DATA / "exemplar_pool.json").read_text(encoding="utf-8"))["exemplars"]}
    for eid, needle in (("ex_battle_fury", '"scope": "this_turn"'), ("ex_knife_juggler", '"every_n": 3'),
                        ("ex_static_loop", '"card_type": "status"')):
        check(eid in pool and needle in json.dumps(pool[eid]["card"]), f"exemplar {eid} uses {needle}")
        if eid in pool:
            check(not _errs(dict(pool[eid]["card"], id="bi_ex")), f"exemplar {eid} validates: {_errs(dict(pool[eid]['card'], id='bi_ex'))}")
    check("Trigger filters (v61)" in (paths.VOCABULARY.parent / "DESIGN_HEURISTICS.md").read_text(encoding="utf-8"),
          "DESIGN_HEURISTICS prices the filters")
    gaps = (REPO / "VOCABULARY_GAPS.md").read_text(encoding="utf-8")
    entry = gaps.split("### 62.", 1)[1].split("### 63.", 1)[0]
    check("**Status:** **done (2026-10-02, vocab v61, Phase BI)**" in entry, "gap #62 is done")
    js = (REPO / "web" / "static" / "render.js").read_text(encoding="utf-8")
    check("function trigHead(e)" in js and "`${trigHead(e)}: `" in js, "render.js renders the filtered trigger heads")
    check('`Every ${ordinal(n)} time ${when.slice(9)}`' in js and '`This turn, ${when[0].toLowerCase()}${when.slice(1)}`' in js,
          "render.js every-N + this-turn wording matches the describe heads")
    check('x.target === "random_enemy" ? " to a random enemy"' in js, "render.js payload random_enemy suffix")
    src = pathlib.Path(cf.__file__).read_text(encoding="utf-8")
    check('Filters (v61): card_type ("whenever you play an Attack"), every_n ("every 3rd")' in src, "the TRIGGERS pitch names the filters")


def _t_smoke_record() -> None:
    print("the saved AutoSlay tag greps (TEST_AUDIT_2026-10 §7):")
    seen = ""
    for seed in SMOKE_SEEDS:
        p = TESTER_DIR / f"godot_BI_tags_{seed}.txt"
        assert p.exists(), f"missing smoke record {p}"
        txt = p.read_text(encoding="utf-8")
        check("[BI]" in txt, f"{p.name} holds [BI] tags")
        check("mod exceptions: 0" in txt and "Localization formatting errors: 0" in txt, f"{p.name} records a clean run")
        seen += txt
    for tag in BI_TAGS:
        check(tag in seen, f"the smoke fired '{tag}'")
    check((TESTER_DIR / "build_tester.py").exists(), "the tester is committed next to the phase test")


def _t_budget() -> None:
    print("rule 0.9 (informational) — readings on the real path:")
    from tests.test_harness_v2 import rule_0_9_readings
    with _env(BTS_HARNESS_V2="1", BTS_BLUEPRINT_VOCAB="tree"):
        r = rule_0_9_readings()
    print(f"  (reading) index                  {r['index']:>8,}")
    print(f"  (reading) per-archetype max      {r['archetype_max']:>8,}  ({r['archetype_max_id']})")
    print(f"  (reading) all-ops path           {r['all_ops']:>8,}")
    print(f"  (reading) scaffold (all-ops)     {r['scaffold']:>8,}")


def main() -> int:
    test_version()
    _t_engine()
    _t_rules_and_describe()
    _t_contract()
    _t_smoke_record()
    _t_budget()
    print(f"\n{_PASS} passed, {_FAIL} failed")
    return 1 if _FAIL else 0


def test_phase_bi_all() -> None:
    global _PASS, _FAIL
    _PASS = _FAIL = 0
    assert main() == 0, f"{_FAIL} Phase BI check(s) failed - see the FAIL lines above"


if __name__ == "__main__":
    sys.exit(main())
