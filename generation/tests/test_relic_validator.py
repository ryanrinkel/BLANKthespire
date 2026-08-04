"""Offline relic-validator tests — no API key needed.

Run:  uv run python -m tests.test_relic_validator     (from generation/)
Exits nonzero on any failure. Confirms the relic harness gate mirrors the engine's data-driven
relic contract: shape/vocab/recursion via relic.schema.json, hook-effect ref-integrity, the
'does nothing' reject, and the coarse tier-band power surfacer.
"""
from __future__ import annotations

import json
import sys

from btsgen import paths
from btsgen.relic_validator import RelicValidator

_PASS = 0
_FAIL = 0


def check(cond: bool, msg: str) -> None:
    global _PASS, _FAIL
    if cond:
        _PASS += 1
    else:
        _FAIL += 1
        print(f"  FAIL: {msg}")


def _relic(rid: str) -> dict:
    return json.loads((paths.RELICS_DIR / f"{rid}.json").read_text())


def test_all_authored_relics_validate(v: RelicValidator) -> None:
    print("authored relics validate clean AND sit inside their tier band:")
    # Human-accepted band warnings: the coarse trigger-frequency proxy over-counts these, but they
    # were reviewed and promoted by hand (the heuristic SURFACES for review, it is not the judge).
    #   battle_tempo: turn_end x3 + from_state flat-6 over-counts a ~3-block common (2026-06-08).
    accepted_warnings = {"battle_tempo"}
    files = sorted(paths.RELICS_DIR.glob("*.json"))
    check(len(files) >= 15, f"expected >=15 authored relics, found {len(files)}")
    for f in files:
        relic = json.loads(f.read_text())
        res = v.validate(relic)
        check(res.ok, f"{f.name} should be valid: {res.errors}")
        check(isinstance(res.score, float), f"{f.name} score not numeric")
        # the heuristic is calibrated so the authored corpus is warning-free (bar known exceptions)
        if relic.get("id") not in accepted_warnings:
            check(not res.warnings, f"{f.name} unexpectedly warned: {res.warnings}")


def test_power_proxy_examples(v: RelicValidator) -> None:
    print("power proxy matches the documented heuristic:")
    cases = {
        "burning_blood": 3.0,        # combat_end heal 6 * 0.5 * freq 1
        "vajra": 4.0,                # combat_start strength 1 * 4 * 1
        "mercury_hourglass": 9.0,    # turn_start damage 3 * freq 3
        "lantern": 6.0,              # turn_start once gain_energy 1*6 * freq 1
        "energy_core": 20.0,         # modifier max_energy 1 * 20
        "akabeko": 8.0,              # modifier attack_base 8 first_attack * 1
    }
    for rid, expected in cases.items():
        got = v.score_relic(_relic(rid))
        check(abs(got - expected) < 1e-6, f"{rid} proxy {got} != {expected}")


def test_hard_rejects(v: RelicValidator) -> None:
    print("known-bad relics are rejected:")

    def bad(mutate, label) -> None:
        r = _relic("vajra")
        mutate(r)
        res = v.validate(r)
        check(not res.ok, f"{label} should reject")

    bad(lambda r: r["hooks"][0].update(trigger="on_pickup"), "unknown trigger")
    bad(lambda r: r["hooks"][0]["effects"][0].update(status="poison"), "unknown status in hook")
    bad(lambda r: r["hooks"][0].update(effects=[{"op": "nuke", "amount": 5}]), "unknown op in hook")
    bad(lambda r: r["hooks"][0].update(condition="when_the_stars_align"), "unknown condition")
    bad(lambda r: r.pop("id"), "missing id")
    bad(lambda r: r.update(tier="legendary"), "bad tier enum")
    bad(lambda r: r.update(wizardry=True), "extra top-level property")
    bad(lambda r: r.update(modifiers=[{"stat": "luck", "amount": 1}]), "bad modifier stat")
    bad(lambda r: r["hooks"][0].update(effects=[{"op": "add_card", "card_id": "zzz_nope", "pile": "hand"}]),
        "add_card bad ref in hook")


def test_inert_relic_rejected(v: RelicValidator) -> None:
    print("a relic that does nothing is rejected:")
    r = _relic("vajra")
    r.pop("hooks", None)
    r.pop("modifiers", None)
    res = v.validate(r)
    check(not res.ok, "relic with no hooks and no modifiers should reject")
    check(any("nothing" in e for e in res.errors), f"expected a 'does nothing' error, got {res.errors}")


def test_raw_damage_validates(v: RelicValidator) -> None:
    print("raw damage flag is accepted:")
    check(v.validate(_relic("bronze_scales")).ok, "bronze_scales (raw thorns) should validate")
    r = _relic("vajra")
    r.update(id="spiky", name="Spiky",
             hooks=[{"trigger": "attacked", "effects": [{"op": "damage", "amount": 5, "raw": True}]}])
    check(v.validate(r).ok, f"a fresh raw-damage relic should validate: {v.validate(r).errors}")


def test_overloaded_warns_not_rejects(v: RelicValidator) -> None:
    print("an out-of-band relic warns but is not rejected:")
    r = _relic("vajra")
    # turn_start draw 5 -> 5*5*3 = 75, far above the common ceiling (~13)
    r.update(id="hoarder", name="Hoarder", tier="common", pool="combat",
             hooks=[{"trigger": "turn_start", "effects": [{"op": "draw", "amount": 5}]}])
    res = v.validate(r)
    check(res.ok, f"overloaded relic should still validate (warn, not reject): {res.errors}")
    check(any("power proxy" in w for w in res.warnings), f"expected a band warning, got {res.warnings}")


def main() -> int:
    v = RelicValidator()
    for t in (test_all_authored_relics_validate, test_power_proxy_examples,
              test_hard_rejects, test_inert_relic_rejected,
              test_raw_damage_validates, test_overloaded_warns_not_rejects):
        t(v)
    print(f"\n{_PASS} passed, {_FAIL} failed")
    return 1 if _FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
