"""Phase BC — HAND OPS: `exhaust_card` + `draw_until` (VOCAB_EXPANSION_5_PLAN, gaps #52/#53, vocab v57) — offline.

Run:  uv run python -m tests.test_phase_bc       (from generation/)
Exits nonzero on any failure. Covers the v57 change in lockstep with the C#:
  1. the vocab stamp is >= 57 on both sides;
  2. exhaust_card: four pick modes (choose / random / up_to / all), amount 1..3 on the counted modes and none on `all`,
     an optional hand filter (attack/skill/power/non_attack), card-only, one per card — on both sides; the engine
     exhausts ONE card at a time through CardCmd.Exhaust (the game's rule) via the game's own exhaust prompt;
  3. draw_until: a required hand filter, no amount, card-only, one per card; the engine is the Pillage loop;
  4. `card_type` is shared (cost_shift keeps attack/skill/power/all; the hand ops take non_attack) and `up_to` is an
     exhaust_card-only pick mode;
  5. describe is a byte-match contract for every sentence shape;
  6. the contract surfaces — VOCABULARY rows, schema, exemplars, featured/harness menus, the catalog, render.js.
"""
from __future__ import annotations

import json
import pathlib
import re
import sys

from btsgen.class_forge import point_btsgen_at_mod_contract

point_btsgen_at_mod_contract()

from btsgen import bts1, cardgen, featured, harness_v2, paths  # noqa: E402
from btsgen import class_forge as cf  # noqa: E402
from btsgen.validator import CardValidator  # noqa: E402

_PASS = 0
_FAIL = 0
MOD_CODE = paths.VOCABULARY.parents[1] / "BlankTheSpireCode"
CARD_SCHEMA = paths.VOCABULARY.parent / "card.schema.json"
RENDER_JS = paths.VOCABULARY.parents[2] / "web" / "static" / "render.js"
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


def _card(effects, ctype="skill", rarity="common", target="self", cost=1, upgrade=None, **extra):
    c = {"id": "bc_t", "name": "BC", "type": ctype, "rarity": rarity, "cost": cost, "target": target, "effects": effects}
    if upgrade is not None:
        c["upgrade"] = upgrade if isinstance(upgrade, dict) else {"effects": upgrade}
    c.update(extra)
    return c


_V = None


def _errs(card) -> list[str]:
    global _V
    if _V is None:
        _V = CardValidator()
    return _V.validate(card).errors


def _ok(card) -> bool:
    return not _errs(card)


def test_version() -> None:
    print("Phase BC vocab stamp is at least 57 (Python + C#):")
    check(bts1.VOCAB_VERSION >= 57, f"bts1.VOCAB_VERSION >= 57, got {bts1.VOCAB_VERSION}")
    fc = _cs("Engine", "ForgedCards.cs")
    m = re.search(r"public const int VocabVersion = (\d+);", fc)
    check(m is not None and int(m.group(1)) >= 57, f"ForgedCards.VocabVersion >= 57, got {m and m.group(1)}")
    check(m is not None and bts1.VOCAB_VERSION <= int(m.group(1)), "bts1.VOCAB_VERSION <= ForgedCards.VocabVersion")
    check("Phase BC" in fc and "exhaust_card" in fc and "draw_until" in fc, "ForgedCards.cs comment names Phase BC + both ops")
    check("57: Phase BC" in pathlib.Path(bts1.__file__).read_text(encoding="utf-8"), "bts1.py records the v57 entry")


def _t_engine() -> None:
    print("the engine: base-game recipes, one exhaust at a time, the Pillage loop:")
    er = _cs("Engine", "EffectRunner.cs")
    ex = er.split("internal static async Task ExhaustCards(", 1)[1].split("internal static", 1)[0]
    check("CardSelectorPrefs.ExhaustSelectionPrompt" in ex, "exhaust_card uses the game's own exhaust prompt (no invented loc key)")
    check("new CardSelectorPrefs(CardSelectorPrefs.ExhaustSelectionPrompt, 0, max)" in ex, "up_to = min 0 (Purity)")
    check("Rng.CombatCardSelection" in ex, "random rolls off the seeded CombatCardSelection stream (True Grit)")
    check("foreach (var c in chosen)\n            await CardCmd.Exhaust(ctx, c);" in ex, "exhausts ONE card at a time (the game's rule)")
    check("[BC] exhaust_card" in ex, "[BC] tag on the exhaust path")
    du = er.split("internal static async Task DrawUntil(", 1)[1].split("/// <summary>", 1)[0]
    check("CardPileCmd.Draw(ctx, owner)" in du and "CardPile.MaxCardsInHand" in du, "draw_until is the single-card Pillage loop with the hand cap")
    check("HandKindMatches(last, e.CardKind)" in du and "[BC] draw_until" in du, "... stops on a match and logs [BC]")
    check('"non_attack" => c.Type != CardType.Attack' in er, "non_attack = anything but an Attack")
    fc = _cs("Engine", "ForgedCards.cs")
    ops = fc.split("SupportedOps =", 1)[1].split("];", 1)[0]
    check('"exhaust_card"' in ops and '"draw_until"' in ops, "SupportedOps carries both")
    tops = fc.split("TriggerOps =", 1)[1].split("];", 1)[0]
    check("exhaust_card" not in tops and "draw_until" not in tops, "neither is a trigger-payload op (card-only)")
    check('ExhaustPickModes = ["choose", "random", "up_to", "all"]' in fc and 'HandKindFilters = ["attack", "skill", "power", "non_attack"]' in fc
          and "ExhaustCardMaxAmount = 3" in fc, "the C# tables match the Python ones")
    check("at most one '{hop}' effect per card" in fc, "C# enforces one exhaust_card / draw_until per list")


def _t_rules() -> None:
    print("validator: the shape rules mirror the C#:")
    ok_cards = [
        _card([{"op": "exhaust_card", "cards": "choose", "amount": 1}, {"op": "draw", "amount": 2}]),
        _card([{"op": "exhaust_card", "cards": "random", "amount": 2}, {"op": "block", "amount": 7}]),
        _card([{"op": "exhaust_card", "cards": "up_to", "amount": 3}]),
        _card([{"op": "exhaust_card", "cards": "all", "card_type": "non_attack"}, {"op": "block", "amount": 10}]),
        _card([{"op": "exhaust_card", "cards": "choose", "amount": 1, "card_type": "skill"}, {"op": "gain_energy", "amount": 1}]),
        _card([{"op": "damage", "amount": 6}, {"op": "draw_until", "card_type": "non_attack"}], ctype="attack", target="enemy"),
        _card([{"op": "draw_until", "card_type": "skill"}]),
    ]
    for c in ok_cards:
        check(_ok(c), f"validates: {json.dumps(c['effects'])} -> {_errs(c)}")
    bad = [
        ("no pick mode", _card([{"op": "exhaust_card", "amount": 1}])),
        ("bad pick mode", _card([{"op": "exhaust_card", "cards": "some", "amount": 1}])),
        ("amount 0", _card([{"op": "exhaust_card", "cards": "choose", "amount": 0}])),
        ("amount 4", _card([{"op": "exhaust_card", "cards": "random", "amount": 4}])),
        ("all with an amount", _card([{"op": "exhaust_card", "cards": "all", "amount": 2}])),
        ("cost_shift's 'all' filter", _card([{"op": "exhaust_card", "cards": "choose", "amount": 1, "card_type": "all"}])),
        ("two per list", _card([{"op": "exhaust_card", "cards": "choose", "amount": 1}, {"op": "exhaust_card", "cards": "random", "amount": 1}])),
        ("draw_until without a type", _card([{"op": "draw_until"}])),
        ("draw_until with an amount", _card([{"op": "draw_until", "card_type": "skill", "amount": 2}])),
        ("draw_until 'all'", _card([{"op": "draw_until", "card_type": "all"}])),
        ("up_to on upgrade_card", _card([{"op": "upgrade_card", "cards": "up_to"}])),
        ("non_attack on cost_shift", _card([{"op": "cost_shift", "card_type": "non_attack", "amount": 1, "scope": "this_turn"}])),
        ("card_type on damage", _card([{"op": "damage", "amount": 6, "card_type": "attack"}], ctype="attack", target="enemy")),
        ("payload exhaust_card", _card([{"op": "add_trigger", "trigger": "turn_start", "effects": [{"op": "exhaust_card", "cards": "random", "amount": 1}]}], ctype="power")),
    ]
    for label, c in bad:
        check(not _ok(c), f"rejected: {label}")
    v = _V
    check(v.score_card(_card([{"op": "exhaust_card", "cards": "random", "amount": 2}])) < 0, "random exhaust is priced as a cost")
    check(v.score_card(_card([{"op": "draw_until", "card_type": "non_attack"}])) == 10.0, "draw_until is priced as draw 2")


def _t_describe() -> None:
    print("describe: Python == C# byte for byte:")
    cases = [
        ([{"op": "exhaust_card", "cards": "choose", "amount": 1}], "Exhaust a card in your hand."),
        ([{"op": "exhaust_card", "cards": "choose", "amount": 2}], "Exhaust 2 cards in your hand."),
        ([{"op": "exhaust_card", "cards": "random", "amount": 1}], "Exhaust a random card in your hand."),
        ([{"op": "exhaust_card", "cards": "random", "amount": 2, "card_type": "attack"}], "Exhaust 2 random Attacks in your hand."),
        ([{"op": "exhaust_card", "cards": "random", "amount": 1, "card_type": "non_attack"}], "Exhaust a random non-Attack card in your hand."),
        ([{"op": "exhaust_card", "cards": "up_to", "amount": 3}], "Exhaust up to 3 cards in your hand."),
        ([{"op": "exhaust_card", "cards": "all", "card_type": "non_attack"}], "Exhaust all non-Attack cards in your hand."),
        ([{"op": "exhaust_card", "cards": "all"}], "Exhaust all cards in your hand."),
        ([{"op": "exhaust_card", "cards": "choose", "amount": 1, "card_type": "skill"}], "Exhaust a Skill in your hand."),
        ([{"op": "draw_until", "card_type": "non_attack"}], "Draw cards until you draw a non-Attack card."),
        ([{"op": "draw_until", "card_type": "power"}], "Draw cards until you draw a Power."),
    ]
    for fx, want in cases:
        got = cardgen.describe(fx, "self")
        check(got == want, f"{fx[0]} -> {got!r} (want {want!r})")
    fc = _cs("Engine", "ForgedCards.cs")
    for frag in ('"all"    => $"all {many}"', '"up_to"  => $"up to {n} {many}"', 'return $"Exhaust {what} in your hand.";',
                 '$"Draw cards until you draw {HandKindWords(e.CardKind).One}."', '"non_attack" => ("a non-Attack card", "non-Attack cards")'):
        check(frag in fc, f"C# Describe carries {frag!r}")
    lit = cardgen.effect_literal({"op": "exhaust_card", "cards": "up_to", "amount": 2, "card_type": "skill"})
    check(lit == 'new EffectSpec("exhaust_card", 2, Cards: "up_to", CardKind: "skill")', f"C# literal: {lit}")
    check(cardgen.effect_literal({"op": "draw_until", "card_type": "non_attack"}) == 'new EffectSpec("draw_until", CardKind: "non_attack")',
          "draw_until literal")


def _t_contract() -> None:
    print("contract surfaces:")
    vocab = paths.VOCABULARY.read_text(encoding="utf-8")
    check("| `exhaust_card`" in vocab and "| `draw_until`" in vocab, "VOCABULARY has both op rows")
    schema = json.loads(CARD_SCHEMA.read_text(encoding="utf-8"))
    eff = schema["$defs"]["effect"]["properties"]
    check({"exhaust_card", "draw_until"} <= set(eff["op"]["enum"]), "schema op enum carries both")
    check("up_to" in eff["cards"]["enum"] and "non_attack" in eff["card_type"]["enum"], "schema widened cards + card_type")
    check(not ({"exhaust_card", "draw_until"} & set(schema["$defs"]["triggerEffect"]["properties"]["op"]["enum"])), "not payload ops")
    pool = json.loads(EXEMPLAR_POOL.read_text(encoding="utf-8"))["exemplars"]
    by_id = {e["card"]["id"]: e for e in pool}
    for eid, tok in (("ex_burning_oath", "exhaust_card"), ("ex_clearing_breath", "non_attack"), ("ex_press_the_line", "draw_until")):
        check(eid in by_id and tok in json.dumps(by_id[eid]["card"]), f"exemplar {eid} uses {tok}")
        if eid in by_id:
            check(_ok(dict(by_id[eid]["card"], id="bc_ex")), f"exemplar {eid} validates: {_errs(dict(by_id[eid]['card'], id='bc_ex'))}")
    check(any(f.id == "exhaust_fuel" for f in featured.FEATURED_MENU), "featured menu has exhaust_fuel")
    check({"exhaust_card", "draw_until"} <= set(harness_v2._PREFERRED_OPS), "both are preferred compositional ops")
    arch = {a["id"]: a for a in json.loads(ARCHETYPES.read_text(encoding="utf-8"))["archetypes"]}
    check("exhaust_card" in arch["exhaust_pyre"]["vocabulary"]["ops"], "exhaust_pyre lists exhaust_card")
    check({"exhaust_card", "draw_until"} <= set(arch["ascetic_purge"]["vocabulary"]["ops"]), "ascetic_purge lists both")
    check("draw_until" in arch["strike_tempo"]["vocabulary"]["ops"], "strike_tempo lists draw_until")
    js = RENDER_JS.read_text(encoding="utf-8")
    check('case "exhaust_card":' in js and 'case "draw_until":' in js, "render.js renders both")
    heur = (paths.VOCABULARY.parent / "DESIGN_HEURISTICS.md").read_text(encoding="utf-8")
    check("`exhaust_card` (v57)" in heur and "`draw_until` (v57" in heur, "DESIGN_HEURISTICS prices both")
    bp = cf._BlueprintContract(mode="dossier", triad=True, seed=1).system_prompt()
    print(f"  (rule 0.9) blueprint prompt: {len(bp):,} chars (scaffolding {len(bp) - len(vocab):,}; the ONE ceiling lives in tests/test_harness_v2.py)")


def main() -> int:
    test_version()
    _t_engine()
    _t_rules()
    _t_describe()
    _t_contract()
    print(f"\n{_PASS} passed, {_FAIL} failed")
    return 1 if _FAIL else 0


def test_phase_bc_all() -> None:
    global _PASS, _FAIL
    _PASS = _FAIL = 0
    assert main() == 0, f"{_FAIL} Phase BC check(s) failed - see the FAIL lines above"


if __name__ == "__main__":
    sys.exit(main())
