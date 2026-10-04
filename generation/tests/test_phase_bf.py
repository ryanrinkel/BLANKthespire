"""Phase BF — NEXT-ATTACK AMPLIFIERS from the base game: `vigor` + `double_damage` (VOCAB_EXPANSION_5_PLAN, gap #54,
vocab v60) — offline. Run:  uv run python -m tests.test_phase_bf  (from generation/)

Pins: the stamp; both statuses map onto the SEALED base-game powers (VigorPower / DoubleDamagePower — no new power
class) on every status map (DataCard / EffectRunner / TriggerRunner / OrbRunner / SummonRunner / ForgedCards); the
status JSONs exist; double_damage is rare-only with amount 1..2 on the generation side; describe byte-match; the
contract surfaces (the blade_empower pitch clause was cut for vigor — the rule-0.9 offset).
"""
from __future__ import annotations

import json
import pathlib
import re
import sys

from btsgen.class_forge import point_btsgen_at_mod_contract

point_btsgen_at_mod_contract()

from btsgen import bts1, cardgen, census, coverage, featured, paths  # noqa: E402
from btsgen import class_forge as cf  # noqa: E402
from btsgen.validator import CardValidator  # noqa: E402

_PASS = 0
_FAIL = 0
MOD_CODE = paths.VOCABULARY.parents[1] / "BlankTheSpireCode"
CARD_SCHEMA = paths.VOCABULARY.parent / "card.schema.json"
EXEMPLAR_POOL = pathlib.Path(cf.__file__).parent / "data" / "exemplar_pool.json"


def check(cond: bool, msg: str) -> None:
    global _PASS, _FAIL
    if cond:
        _PASS += 1
    else:
        _FAIL += 1
        print(f"  FAIL: {msg}")


def _cs(*parts: str) -> str:
    return (MOD_CODE.joinpath(*parts)).read_text(encoding="utf-8")


def _card(effects, rarity="common", cost=1, ctype="skill"):
    return {"id": "bf_t", "name": "BF", "type": ctype, "rarity": rarity, "cost": cost, "target": "self", "effects": effects}


_V = None


def _errs(card) -> list[str]:
    global _V
    if _V is None:
        _V = CardValidator()
    return _V.validate(card).errors


def test_version() -> None:
    print("Phase BF vocab stamp is at least 60 (Python + C#):")
    check(bts1.VOCAB_VERSION >= 60, f"bts1.VOCAB_VERSION >= 60, got {bts1.VOCAB_VERSION}")
    fc = _cs("Engine", "ForgedCards.cs")
    m = re.search(r"public const int VocabVersion = (\d+);", fc)
    check(m is not None and int(m.group(1)) >= 60, f"ForgedCards.VocabVersion >= 60, got {m and m.group(1)}")
    check(m is not None and bts1.VOCAB_VERSION <= int(m.group(1)), "bts1.VOCAB_VERSION <= ForgedCards.VocabVersion")
    check("Phase BF" in fc and '"vigor"' in fc and '"double_damage"' in fc, "ForgedCards.cs comment names Phase BF + both statuses")
    check("60: Phase BF" in pathlib.Path(bts1.__file__).read_text(encoding="utf-8"), "bts1.py records the v60 entry")


def _t_engine() -> None:
    print("the engine: base-game powers on every status map, no new power class:")
    check("<VigorPower>" in _cs("Engine", "DataCard.cs") and "<DoubleDamagePower>" in _cs("Engine", "DataCard.cs"), "DataCard declares both PowerVars")
    er = _cs("Engine", "EffectRunner.cs")
    check('"vigor", "double_damage",' in er.split("SelfBuffStatuses =", 1)[1].split("];", 1)[0], "SelfBuffStatuses carries both")
    check(er.count("ApplyPowerLogged<VigorPower>") == 1 and er.count("RelicApplyT<VigorPower>") == 1, "EffectRunner card + relic maps")
    check("ApplyT<VigorPower>" in _cs("Engine", "TriggerRunner.cs") and "ApplyT<DoubleDamagePower>" in _cs("Engine", "TriggerRunner.cs"), "TriggerRunner self-buff map")
    for f in ("OrbRunner.cs", "SummonRunner.cs"):
        s = _cs("Engine", f)
        check("Apply<VigorPower>" in s and '"double_damage" => "Double Damage"' in s, f"{f} apply + name maps")
    fc = _cs("Engine", "ForgedCards.cs")
    check('"vigor", "double_damage"' in fc.split("SupportedStatuses =", 1)[1].split("];", 1)[0], "ForgedCards.SupportedStatuses")
    check(fc.count('"vigor" => "Vigor", "double_damage" => "Double Damage"') == 2, "both ForgedCards name maps")
    check(not list(MOD_CODE.glob("Powers/*NextAttack*")), "no new power class was written (the base game's are used)")
    for sid in ("vigor", "double_damage"):
        p = paths.VOCABULARY.parent / "statuses" / f"{sid}.json"
        check(p.exists() and json.loads(p.read_text(encoding="utf-8")).get("kind") == "buff", f"statuses/{sid}.json exists as a buff")


def _t_rules_and_describe() -> None:
    print("validator + describe:")
    vig = _card([{"op": "apply_status", "status": "vigor", "amount": 5}, {"op": "draw", "amount": 1}])
    check(not _errs(vig), f"a Vigor skill validates: {_errs(vig)}")
    dd = _card([{"op": "apply_status", "status": "double_damage", "amount": 1}, {"op": "exhaust"}], rarity="rare", cost=2)
    check(not _errs(dd), f"a rare double_damage validates: {_errs(dd)}")
    check(bool(_errs(_card([{"op": "apply_status", "status": "double_damage", "amount": 1}], rarity="uncommon"))), "double_damage below rare is rejected")
    check(bool(_errs(_card([{"op": "apply_status", "status": "double_damage", "amount": 3}], rarity="rare"))), "double_damage amount 3 is rejected")
    trig = _card([{"op": "add_trigger", "trigger": "on_block_gained", "once_per_turn": True,
                   "effects": [{"op": "apply_status", "status": "vigor", "amount": 2}]}], ctype="power")
    check(not _errs(trig), f"vigor is a legal self-buff payload: {_errs(trig)}")
    check(cardgen.describe(vig["effects"], "self") == "Gain Vigor.\nDraw {Cards} card(s).", "vigor reads 'Gain Vigor.'")
    check(cardgen.describe(dd["effects"], "self") == "Gain Double Damage.\nExhaust.", "double_damage reads 'Gain Double Damage.'")
    check(cardgen.describe(trig["effects"], "self") == "Whenever you gain Block, gain 2 Vigor (once per turn).", "payload wording")
    v = _V
    check(v.score_card(_card([{"op": "apply_status", "status": "double_damage", "amount": 1}], rarity="rare")) >= 12.0, "double_damage is priced rare-tier")


def _t_contract() -> None:
    print("contract surfaces:")
    vocab = paths.VOCABULARY.read_text(encoding="utf-8")
    check("| `vigor`" in vocab and "| `double_damage`" in vocab and "temp_focus/vigor/double_damage" in vocab, "VOCABULARY rows + the payload self-buff list")
    schema = json.loads(CARD_SCHEMA.read_text(encoding="utf-8"))
    for d in ("effect", "triggerEffect"):
        check({"vigor", "double_damage"} <= set(schema["$defs"][d]["properties"]["status"]["enum"]), f"schema {d} status enum")
    pool = {e["card"]["id"]: e for e in json.loads(EXEMPLAR_POOL.read_text(encoding="utf-8"))["exemplars"]}
    for eid, tok in (("ex_coiled_breath", "vigor"), ("ex_phantom_hour", "double_damage")):
        check(eid in pool and tok in json.dumps(pool[eid]["card"]), f"exemplar {eid} uses {tok}")
        if eid in pool:
            check(not _errs(dict(pool[eid]["card"], id="bf_ex")), f"exemplar {eid} validates: {_errs(dict(pool[eid]['card'], id='bf_ex'))}")
    check({"vigor", "double_damage"} <= census.EXOTIC_STATUSES, "both count as exotic statuses for coverage")
    check(any(k == "vigor" for k, _ in coverage.EXOTIC_MENU_V2), "EXOTIC_MENU_V2 carries vigor")
    check(any(f.id == "setup_spike" for f in featured.FEATURED_MENU), "featured menu has setup_spike")
    src = pathlib.Path(cf.__file__).read_text(encoding="utf-8")
    check("`apply_status vigor` (v60" in src, "the Forge pitch names vigor")
    check('OPTIONAL BURST: one `{{"op":"blade_empower"' not in src, "... and the old blade_empower-only clause is gone (the rule-0.9 offset)")
    js = (paths.VOCABULARY.parents[2] / "web" / "static" / "render.js").read_text(encoding="utf-8")
    check('vigor: "Vigor", double_damage: "Double Damage"' in js, "render.js names both")
    check("`vigor` (v60)" in (paths.VOCABULARY.parent / "DESIGN_HEURISTICS.md").read_text(encoding="utf-8"), "DESIGN_HEURISTICS prices them")
    bp = cf._BlueprintContract(mode="dossier", triad=True, seed=1).system_prompt()
    print(f"  (rule 0.9) blueprint prompt: {len(bp):,} chars (scaffolding {len(bp) - len(vocab):,})")


def main() -> int:
    test_version()
    _t_engine()
    _t_rules_and_describe()
    _t_contract()
    print(f"\n{_PASS} passed, {_FAIL} failed")
    return 1 if _FAIL else 0


def test_phase_bf_all() -> None:
    global _PASS, _FAIL
    _PASS = _FAIL = 0
    assert main() == 0, f"{_FAIL} Phase BF check(s) failed - see the FAIL lines above"


if __name__ == "__main__":
    sys.exit(main())
