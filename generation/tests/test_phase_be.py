"""Phase BE — ON_POISON_DAMAGE (VOCAB_EXPANSION_5_PLAN, gap #56, vocab v59) — offline.

Run:  uv run python -m tests.test_phase_be       (from generation/)
Pins, in lockstep with the C#: the stamp; the detector lives in AfterDamageGiven (the hook that fires on a LETHAL
tick — AfterDamageReceived is skipped then), keys on the base game's Poison-tick shape (no dealer, no card,
Unblockable|Unpowered, an enemy still carrying PoisonPower), excludes the mod's own damage_over_time tick, and never
stores its ThrowingPlayerChoiceContext; the kind is multi-fire (once_per_turn / once_per_combat legal); describe
byte-match; the contract surfaces (the featured entry is pool-level and NOT on the reactive quota menu).
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


def _power(trigger_extra=None, payload=None):
    t = {"op": "add_trigger", "trigger": "on_poison_damage", "effects": payload or [{"op": "block", "amount": 3}]}
    t.update(trigger_extra or {})
    return {"id": "be_t", "name": "BE", "type": "power", "rarity": "uncommon", "cost": 1, "target": "self", "effects": [t]}


_V = None


def _errs(card) -> list[str]:
    global _V
    if _V is None:
        _V = CardValidator()
    return _V.validate(card).errors


def test_version() -> None:
    print("Phase BE vocab stamp is at least 59 (Python + C#):")
    check(bts1.VOCAB_VERSION >= 59, f"bts1.VOCAB_VERSION >= 59, got {bts1.VOCAB_VERSION}")
    fc = _cs("Engine", "ForgedCards.cs")
    m = re.search(r"public const int VocabVersion = (\d+);", fc)
    check(m is not None and int(m.group(1)) >= 59, f"ForgedCards.VocabVersion >= 59, got {m and m.group(1)}")
    check(m is not None and bts1.VOCAB_VERSION <= int(m.group(1)), "bts1.VOCAB_VERSION <= ForgedCards.VocabVersion")
    check("Phase BE" in fc and "on_poison_damage" in fc, "ForgedCards.cs comment names Phase BE + the kind")
    check("59: Phase BE" in pathlib.Path(bts1.__file__).read_text(encoding="utf-8"), "bts1.py records the v59 entry")


def _t_engine() -> None:
    print("the engine: the detector, its hook, its exclusions:")
    tp = _cs("Powers", "ForgedTriggerPower.cs")
    body = tp.split("public override async Task AfterDamageGiven(", 1)[1].split("public override async Task AfterBlockGained", 1)[0]
    det = body.split('if (Trigger?.Trigger == "on_poison_damage")', 1)
    check(len(det) == 2, "on_poison_damage is detected in AfterDamageGiven (the hook that fires on a lethal tick)")
    d = det[1] if len(det) == 2 else ""
    check("props != (ValueProp.Unblockable | ValueProp.Unpowered)" in d and "dealer != null || cardSource != null" in d,
          "... keyed on the base-game Poison-tick shape (no dealer, no card, Unblockable|Unpowered)")
    check("target.Player != null || !target.HasPower<PoisonPower>()" in d, "... on an ENEMY still carrying PoisonPower")
    check("ForgedStatusPower.CustomTickInProgress" in d, "... excluding the mod's own damage_over_time tick")
    check('await FireReactive("on_poison_damage", ctx);' in d and "[BE] on_poison_damage" in d, "... fires through FireReactive with a [BE] tag")
    check(d.index('FireReactive("on_poison_damage"') < body.index("_combatCtx = ctx;"),
          "... and returns BEFORE _combatCtx is overwritten with the ThrowingPlayerChoiceContext")
    sp = _cs("Powers", "ForgedStatusPower.cs")
    check("internal static bool CustomTickInProgress;" in sp and "CustomTickInProgress = true;" in sp and "finally { CustomTickInProgress = false; }" in sp,
          "ForgedStatusPower flags its own tick for the duration (try/finally)")
    fc = _cs("Engine", "ForgedCards.cs")
    for lst in ("SupportedTriggers", "MultiFireTriggers", "OncePerCombatTriggers"):
        check('"on_poison_damage"' in fc.split(f"{lst} =", 1)[1].split("];", 1)[0], f"ForgedCards.{lst} carries on_poison_damage")
    check('"on_poison_damage" => "Whenever an enemy takes Poison damage"' in fc, "C# TriggerSentence wording")
    check('"on_poison_damage" => "On Poison Damage"' in tp, "the power's title")


def _t_rules_and_describe() -> None:
    print("validator + describe:")
    check(not _errs(_power()), f"a plain on_poison_damage power validates: {_errs(_power())}")
    check(not _errs(_power({"once_per_turn": True})), "once_per_turn is legal (multi-fire)")
    check(not _errs(_power({"once_per_combat": True})), "once_per_combat is legal (power-hosted)")
    check(not _errs(_power(payload=[{"op": "apply_status", "status": "weak", "amount": 1, "target": "enemy"}])), "a targeted debuff payload is legal")
    check(bool(_errs(_power({"once_per_turn": True, "once_per_combat": True}))), "both gates at once is still rejected")
    check("on_poison_damage" in harness_v2._PREFERRED_TRIGGERS and "on_poison_damage" in harness_v2.vocabulary_triggers(),
          "the harness names the kind and the live vocabulary carries it")
    got = cardgen.describe(_power({"once_per_turn": True})["effects"], "self")
    check(got == "Whenever an enemy takes Poison damage, gain 3 Block (once per turn).", f"describe: {got!r}")


def _t_contract() -> None:
    print("contract surfaces:")
    vocab = paths.VOCABULARY.read_text(encoding="utf-8")
    check("on_poison_damage" in vocab.split("## Triggers", 1)[1] and "on_poison_damage" in vocab.split("| `add_trigger`", 1)[1].split("\n", 1)[0],
          "VOCABULARY names the kind in the add_trigger row and the Triggers section")
    schema = json.loads(CARD_SCHEMA.read_text(encoding="utf-8"))
    check("on_poison_damage" in schema["$defs"]["effect"]["properties"]["trigger"]["enum"], "schema trigger enum carries it")
    pool = {e["card"]["id"]: e for e in json.loads(EXEMPLAR_POOL.read_text(encoding="utf-8"))["exemplars"]}
    check("ex_venom_ward" in pool and "on_poison_damage" in json.dumps(pool["ex_venom_ward"]["card"]), "exemplar ex_venom_ward uses it")
    if "ex_venom_ward" in pool:
        check(not _errs(dict(pool["ex_venom_ward"]["card"], id="be_ex")), f"exemplar validates: {_errs(dict(pool['ex_venom_ward']['card'], id='be_ex'))}")
    ve = next((f for f in featured.FEATURED_MENU if f.id == "venom_engine"), None)
    check(ve is not None, "featured menu has venom_engine")
    if ve is not None:
        p = census.walk_card(_power())
        poison = census.walk_card({"id": "p", "cost": 1, "effects": [{"op": "apply_status", "status": "poison", "amount": 3}]})
        check(not ve.carried_by([p]), "... pool-level: the trigger alone is not carried")
        check(ve.carried_by([p, poison, poison]), "... the trigger + two poison appliers is")
    check(not any(k == "on_poison_damage" for k, _ in coverage.REACTIVE_MENU_V2), "deliberately NOT on the reactive quota menu")
    arch = {a["id"]: a for a in json.loads(ARCHETYPES.read_text(encoding="utf-8"))["archetypes"]}
    check("on_poison_damage" in arch["poison_attrition"]["vocabulary"]["ops"], "poison_attrition lists it")
    check("on_poison_damage:" in RENDER_JS.read_text(encoding="utf-8"), "render.js has the trigger prefix")
    check("`on_poison_damage` power (v59)" in (paths.VOCABULARY.parent / "DESIGN_HEURISTICS.md").read_text(encoding="utf-8"), "DESIGN_HEURISTICS prices it")
    bp = cf._BlueprintContract(mode="dossier", triad=True, seed=1).system_prompt()
    print(f"  (rule 0.9) blueprint prompt: {len(bp):,} chars (scaffolding {len(bp) - len(vocab):,})")


def main() -> int:
    test_version()
    _t_engine()
    _t_rules_and_describe()
    _t_contract()
    print(f"\n{_PASS} passed, {_FAIL} failed")
    return 1 if _FAIL else 0


def test_phase_be_all() -> None:
    global _PASS, _FAIL
    _PASS = _FAIL = 0
    assert main() == 0, f"{_FAIL} Phase BE check(s) failed - see the FAIL lines above"


if __name__ == "__main__":
    sys.exit(main())
