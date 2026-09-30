"""Phase BD — HELD-CARD PAYOFFS: `grow_held` + `held_discount` (VOCAB_EXPANSION_5_PLAN, gaps #57/#58, vocab v58) — offline.

Run:  uv run python -m tests.test_phase_bd       (from generation/)
Pins, in lockstep with the C#: the stamp; the engine rides the GAME's retain hook (DataCard.AfterFlush reads
retainedCards, bumps a per-instance counter, and lowers the cost with the THIS-COMBAT modifier — a this-turn one is
wiped by EndOfTurnCleanup right after the hook); grow_held is a calc-var on damage/block that needs retain, is ⊥
scale/grow, 1..9, <= amount, joins the one-calc-var budget and is never a payload; held_discount needs retain and a
cost of 1+, amount 1..2, one per card; describe byte-match; the contract surfaces.
"""
from __future__ import annotations

import json
import pathlib
import re
import sys

from btsgen.class_forge import point_btsgen_at_mod_contract

point_btsgen_at_mod_contract()

from btsgen import bridges, bts1, cardgen, census, featured, harness_v2, paths  # noqa: E402
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


def _card(effects, ctype="attack", rarity="uncommon", target="enemy", cost=2, upgrade=None, **extra):
    c = {"id": "bd_t", "name": "BD", "type": ctype, "rarity": rarity, "cost": cost, "target": target, "effects": effects}
    if upgrade is not None:
        c["upgrade"] = {"effects": upgrade}
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


RET = {"op": "retain"}
WINDMILL = [RET, {"op": "damage", "amount": 7, "grow_held": 4}]
SANDS = [RET, {"op": "damage", "amount": 20}, {"op": "held_discount", "amount": 1}]


def test_version() -> None:
    print("Phase BD vocab stamp is at least 58 (Python + C#):")
    check(bts1.VOCAB_VERSION >= 58, f"bts1.VOCAB_VERSION >= 58, got {bts1.VOCAB_VERSION}")
    fc = _cs("Engine", "ForgedCards.cs")
    m = re.search(r"public const int VocabVersion = (\d+);", fc)
    check(m is not None and int(m.group(1)) >= 58, f"ForgedCards.VocabVersion >= 58, got {m and m.group(1)}")
    check(m is not None and bts1.VOCAB_VERSION <= int(m.group(1)), "bts1.VOCAB_VERSION <= ForgedCards.VocabVersion")
    check("Phase BD" in fc and "grow_held" in fc and "held_discount" in fc, "ForgedCards.cs comment names Phase BD + both tokens")
    check("58: Phase BD" in pathlib.Path(bts1.__file__).read_text(encoding="utf-8"), "bts1.py records the v58 entry")


def _t_engine() -> None:
    print("the engine: the game's retain hook, a per-instance counter, a this-combat cost modifier:")
    dc = _cs("Engine", "DataCard.cs")
    check("public override Task AfterFlush(PlayerChoiceContext choiceContext, Player player," in dc, "DataCard overrides the game's AfterFlush hook")
    fl = dc.split("public override Task AfterFlush(", 1)[1].split("/// <summary>", 1)[0]
    check("retainedCards.Contains(this)" in fl and "_turnsHeld++" in fl, "... counts only when THIS card was retained")
    check("EnergyCost.AddThisCombat(-n)" in fl, "held_discount uses the THIS-COMBAT modifier (EndOfTurnCleanup runs right after the hook)")
    check("AddThisTurn" not in fl and "AddUntilPlayed" not in fl, "... and never a this-turn / until-played one")
    check("[BD] grow_held" in fl and "[BD] held_discount" in fl, "[BD] tags on both paths")
    check("private int _turnsHeld;" in dc and "HeldBonusFor(EffectSpec e, int up)" in dc, "the held-turn counter + its calc-var lambda exist")
    check("else if (e.HasGrowHeld) WithCalculatedDamage(0, HeldBonusFor(e, up), dprops);" in dc, "damage grow_held is a CalculatedDamage var")
    check("else if (e.HasGrowHeld) WithCalculatedBlock(0, HeldBonusFor(e, up));" in dc, "block grow_held is a CalculatedBlock var")
    cs = _cs("Engine", "CardSpec.cs")
    check("int GrowHeld = 0)" in cs and "public bool HasGrowHeld => GrowHeld != 0;" in cs, "EffectSpec carries GrowHeld")
    fc = _cs("Engine", "ForgedCards.cs")
    check('int growHeld = e.ContainsKey("grow_held") ? Int(e, "grow_held") : 0;' in fc and "GrowHeld: growHeld" in fc, "the importer parses grow_held")
    check('"held_discount"' in fc.split("SupportedOps =", 1)[1].split("];", 1)[0], "SupportedOps carries held_discount")
    check("held_discount" not in fc.split("TriggerOps =", 1)[1].split("];", 1)[0], "held_discount is card-only")
    check("'grow_held' / 'held_discount' need 'retain' on the same card" in fc, "C# requires retain")
    check("'held_discount' needs a card that costs 1+ energy" in fc, "C# rejects held_discount on 0/X-cost")
    check("(e.HasGrowHeld && e.Op is \"damage\" or \"block\")" in fc, "grow_held joins the one-calc-var budget")
    check("'grow_held' is not allowed in a trigger payload" in fc, "C# rejects a payload grow_held")


def _t_rules() -> None:
    print("validator: the shape rules mirror the C#:")
    check(_ok(_card(WINDMILL)), f"Windmill Strike validates: {_errs(_card(WINDMILL))}")
    check(_ok(_card([RET, {"op": "block", "amount": 5, "grow_held": 3}], ctype="skill", target="self")), "block grow_held validates")
    check(_ok(_card(SANDS, cost=3)), f"Sands of Time validates: {_errs(_card(SANDS, cost=3))}")
    check(_ok(_card([{"op": "damage", "amount": 7}], upgrade=[{"op": "damage", "amount": 7, "grow_held": 3}, RET])),
          "an upgrade that appends retain may carry grow_held")
    bad = [
        ("no retain (grow_held)", _card([{"op": "damage", "amount": 7, "grow_held": 4}])),
        ("no retain (held_discount)", _card([{"op": "damage", "amount": 20}, {"op": "held_discount"}])),
        ("grow_held > amount", _card([RET, {"op": "damage", "amount": 3, "grow_held": 4}])),
        ("grow_held 10", _card([RET, {"op": "damage", "amount": 12, "grow_held": 10}])),
        ("grow_held + scale", _card([RET, {"op": "damage", "amount": 7, "grow_held": 2, "scale": "block"}])),
        ("grow_held + grow", _card([RET, {"op": "damage", "amount": 7, "grow_held": 2, "grow": 2}])),
        ("grow_held on draw", _card([RET, {"op": "draw", "amount": 2, "grow_held": 1}], ctype="skill", target="self")),
        ("two calc-vars", _card([RET, {"op": "damage", "amount": 7, "grow_held": 2}, {"op": "block", "amount": 5, "grow_held": 2}])),
        ("held_discount on 0-cost", _card(SANDS, cost=0)),
        ("held_discount on X-cost", _card([RET, {"op": "damage", "amount": 5, "scale": "x"}, {"op": "held_discount"}], cost="X")),
        ("held_discount 3", _card([RET, {"op": "damage", "amount": 20}, {"op": "held_discount", "amount": 3}])),
        ("two held_discount", _card([RET, {"op": "damage", "amount": 20}, {"op": "held_discount"}, {"op": "held_discount"}])),
        ("payload grow_held", _card([{"op": "add_trigger", "trigger": "turn_start", "effects": [{"op": "block", "amount": 3, "grow_held": 1}]}], ctype="power", target="self")),
    ]
    for label, c in bad:
        check(not _ok(c), f"rejected: {label}")
    v = _V
    check(v.score_card(_card(WINDMILL)) > v.score_card(_card([RET, {"op": "damage", "amount": 7}])), "grow_held carries a premium")
    check(v.score_card(_card(SANDS, cost=3)) > v.score_card(_card(SANDS[:2], cost=3)), "held_discount carries a premium")


def _t_describe() -> None:
    print("describe: Python == C# byte for byte:")
    got = cardgen.describe(WINDMILL, "enemy")
    check(got == "Retain.\nDeal {CalculatedDamage} damage. Grows by 4 each turn it is retained.", f"windmill: {got!r}")
    got = cardgen.describe([RET, {"op": "block", "amount": 5, "grow_held": 3}], "self")
    check(got == "Retain.\nGain {CalculatedBlock} Block. Grows by 3 each turn it is retained.", f"block: {got!r}")
    got = cardgen.describe(SANDS, "enemy")
    check(got == "Retain.\nDeal {Damage} damage.\nCosts 1 less for each turn it is retained.", f"sands: {got!r}")
    fc = _cs("Engine", "ForgedCards.cs")
    for frag in ('damage{dmgSuffix}{ub}. Grows by {e.GrowHeld} each turn it is retained."',
                 '$"Gain {{CalculatedBlock}} Block. Grows by {e.GrowHeld} each turn it is retained."',
                 '$"Costs {Math.Max(1, e.Amount)} less for each turn it is retained."'):
        check(frag in fc, f"C# Describe carries {frag!r}")
    check(cardgen.effect_literal({"op": "damage", "amount": 7, "grow_held": 4}) == 'new EffectSpec("damage", 7, GrowHeld: 4)', "damage literal")
    check(cardgen.effect_literal({"op": "block", "amount": 5, "grow_held": 2}) == 'new EffectSpec("block", 5, GrowHeld: 2)', "block literal")


def _t_contract() -> None:
    print("contract surfaces:")
    vocab = paths.VOCABULARY.read_text(encoding="utf-8")
    check("| `held_discount`" in vocab and "**Windmill Strike (`grow_held`, v58):**" in vocab, "VOCABULARY documents both")
    schema = json.loads(CARD_SCHEMA.read_text(encoding="utf-8"))
    eff = schema["$defs"]["effect"]["properties"]
    check("grow_held" in eff and "held_discount" in eff["op"]["enum"], "schema carries the field + the op")
    check("held_discount" not in schema["$defs"]["triggerEffect"]["properties"]["op"]["enum"]
          and "grow_held" not in schema["$defs"]["triggerEffect"]["properties"], "neither is payload-legal")
    pool = {e["card"]["id"]: e for e in json.loads(EXEMPLAR_POOL.read_text(encoding="utf-8"))["exemplars"]}
    for eid, tok in (("ex_windmill_cut", "grow_held"), ("ex_hourglass_edge", "held_discount")):
        check(eid in pool and tok in json.dumps(pool[eid]["card"]), f"exemplar {eid} uses {tok}")
        if eid in pool:
            check(_ok(dict(pool[eid]["card"], id="bd_ex")), f"exemplar {eid} validates: {_errs(dict(pool[eid]['card'], id='bd_ex'))}")
    cc = census.walk_card(_card(WINDMILL))
    check(cc.grow_held == 1 and not cc.plain, "census counts grow_held and it is not plain")
    check("grow_held" in bridges.card_tokens(_card(WINDMILL)), "bridges surfaces grow_held as a token")
    check(any(f.id == "patience_payoff" for f in featured.FEATURED_MENU), "featured menu has patience_payoff")
    check("held_discount" in harness_v2._PREFERRED_OPS, "held_discount is a preferred compositional op")
    arch = {a["id"]: a for a in json.loads(ARCHETYPES.read_text(encoding="utf-8"))["archetypes"]}
    check({"grow_held", "held_discount"} <= set(arch["retain_hold"]["vocabulary"]["ops"]), "retain_hold lists both")
    js = RENDER_JS.read_text(encoding="utf-8")
    check('case "held_discount":' in js and "per turn held" in js, "render.js renders both")
    heur = (paths.VOCABULARY.parent / "DESIGN_HEURISTICS.md").read_text(encoding="utf-8")
    check("`grow_held` card prints BELOW" in heur, "DESIGN_HEURISTICS prices the held payoffs")
    bp = cf._BlueprintContract(mode="dossier", triad=True, seed=1).system_prompt()
    print(f"  (rule 0.9) blueprint prompt: {len(bp):,} chars (scaffolding {len(bp) - len(vocab):,})")


def main() -> int:
    test_version()
    _t_engine()
    _t_rules()
    _t_describe()
    _t_contract()
    print(f"\n{_PASS} passed, {_FAIL} failed")
    return 1 if _FAIL else 0


def test_phase_bd_all() -> None:
    global _PASS, _FAIL
    _PASS = _FAIL = 0
    assert main() == 0, f"{_FAIL} Phase BD check(s) failed - see the FAIL lines above"


if __name__ == "__main__":
    sys.exit(main())
