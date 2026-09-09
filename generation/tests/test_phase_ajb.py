"""Phase AJ-b — prototype path leakage (VOCAB_GAP_REMEDIATION_PLAN Wave 1; no vocab bump) — offline, no API key.

Run:  uv run python -m tests.test_phase_ajb       (from generation/)
Exits nonzero on any failure. Asserts:
  1. with NO BTSGEN_* env set, `btsgen.paths` defaults to the MOD contract (card + relic schema, vocabularies,
     statuses, authored cards) and `point_btsgen_at_mod_contract()` leaves it there;
  2. every one of the mod's 18 statuses is a KNOWN status to a fresh CardValidator (the prototype status dir
     used to make 12 of them "unknown");
  3. the status balance weights cover all 18 mod statuses (no silent 2.0 default), with the intended ordering;
  4. the new mod relic schema (mod/contract/relic.schema.json) accepts the smoke-coverage relic and agrees with
     class_forge._validate_relic on a few shapes (both accept / both reject);
  5. the archived prototype contract is still reachable via paths.prototype_overrides() (the prototype-era tests);
  6. the PRODUCTION modules carry no prototype op tokens outside comments/docstrings.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from btsgen.class_forge import point_btsgen_at_mod_contract

point_btsgen_at_mod_contract()

from btsgen import class_forge, paths, smoke_relic  # noqa: E402
from btsgen.validator import _STATUS_WEIGHT, CardValidator  # noqa: E402

_PASS = 0
_FAIL = 0

MOD_STATUSES = {"vulnerable", "weak", "frail", "poison", "strength", "dexterity", "temp_strength", "temp_dexterity",
                "thorns", "regen", "metallicize", "artifact", "buffer", "blur", "intangible", "ritual", "barricade",
                "focus"}
PRODUCTION_MODULES = ("validator.py", "contract.py", "class_forge.py", "coverage.py", "harness_v2.py", "census.py",
                      "featured.py", "bridges.py", "cardgen.py", "bts1.py", "slotgen.py", "frontend/builder.py",
                      "frontend/catalog.py", "frontend/stage_cloud.py")
# The unambiguous prototype-only op names. (`fuse` is also the O-1 BRIDGE/fusion term in class_forge/coverage/featured,
# and `multi`/`conditional` survive in validator.py's explicitly legacy-gated block — so those are checked separately.)
_PROTOTYPE_TOKEN = re.compile(r"(?<![a-z_\"'`])(from_state|set_flag)(?![a-z_])")


def check(cond: bool, msg: str) -> None:
    global _PASS, _FAIL
    if cond:
        _PASS += 1
    else:
        _FAIL += 1
        print(f"  FAIL: {msg}")


def test_paths_default_to_mod_contract() -> None:
    print("paths default to the mod contract:")
    check(paths.CARD_SCHEMA == paths.MOD_CONTRACT / "card.schema.json", f"CARD_SCHEMA {paths.CARD_SCHEMA}")
    check(paths.VOCABULARY == paths.MOD_CONTRACT / "VOCABULARY.md", f"VOCABULARY {paths.VOCABULARY}")
    check(paths.RELIC_SCHEMA == paths.MOD_CONTRACT / "relic.schema.json" and paths.RELIC_SCHEMA.exists(),
          f"RELIC_SCHEMA {paths.RELIC_SCHEMA}")
    check(paths.RELIC_VOCABULARY == paths.MOD_CONTRACT / "RELIC_VOCABULARY.md", f"RELIC_VOCABULARY {paths.RELIC_VOCABULARY}")
    check(paths.STATUSES_DIR == paths.MOD_CONTRACT / "statuses", f"STATUSES_DIR {paths.STATUSES_DIR}")
    check(paths.CARDS_DIR == paths.MOD_CONTENT / "cards", f"CARDS_DIR {paths.CARDS_DIR}")
    check("prototype" not in str(paths.GENERATED_DIR), f"GENERATED_DIR must not quarantine into the prototype: {paths.GENERATED_DIR}")
    paths.assert_project_present()
    paths.assert_relic_project_present()
    check(True, "contract files present")


def test_all_mod_statuses_known() -> None:
    print("every mod status is known to the validator and has a balance weight:")
    v = CardValidator()
    missing = MOD_STATUSES - set(v.known_statuses)
    check(not missing, f"unknown mod statuses: {sorted(missing)}")
    unweighted = MOD_STATUSES - set(_STATUS_WEIGHT)
    check(not unweighted, f"statuses falling through to the 2.0 default: {sorted(unweighted)}")
    check(_STATUS_WEIGHT["intangible"] > _STATUS_WEIGHT["strength"] > _STATUS_WEIGHT["dexterity"]
          > _STATUS_WEIGHT["vulnerable"] > _STATUS_WEIGHT["poison"], "weight ordering: intangible > strength > dexterity > vulnerable > poison")
    check(_STATUS_WEIGHT["temp_strength"] < _STATUS_WEIGHT["strength"], "a one-turn burst prices under the permanent stat")
    # scoring proof: Intangible 1 must no longer price like Weak 1
    intangible = {"id": "ajb_i", "name": "I", "type": "power", "rarity": "rare", "cost": 2, "target": "self",
                  "source": "llm", "effects": [{"op": "apply_status", "status": "intangible", "amount": 1}]}
    weak = {**intangible, "id": "ajb_w", "type": "skill", "target": "enemy",
            "effects": [{"op": "apply_status", "status": "weak", "amount": 1}]}
    check(v.score_card(intangible) > 3 * v.score_card(weak), "Intangible 1 scores well above Weak 1")


def test_relic_schema_matches_validate_relic() -> None:
    print("mod relic.schema.json accepts the smoke relic and agrees with _validate_relic:")
    from jsonschema import Draft202012Validator
    schema = json.loads(paths.RELIC_SCHEMA.read_text(encoding="utf-8"))
    sv = Draft202012Validator(schema)

    def schema_ok(r) -> bool:
        return not list(sv.iter_errors(r))

    check(schema_ok(smoke_relic.SMOKE_RELIC), f"smoke relic schema errors: {[e.message for e in sv.iter_errors(smoke_relic.SMOKE_RELIC)][:3]}")
    check(not class_forge._validate_relic(smoke_relic.SMOKE_RELIC), "smoke relic passes _validate_relic")
    good = {"id": "ajb_r", "name": "Ash Heirloom", "tier": "starter", "icon_emoji": "🔥",
            "hooks": [{"trigger": "turn_start", "once_per_combat": True,
                       "effects": [{"op": "apply_status", "status": "strength", "amount": 1}]}]}
    check(schema_ok(good) and not class_forge._validate_relic(good), "a turn_start boon: both accept")
    shapes = [
        ({**good, "hooks": [], "modifiers": []}, "nothing"),
        ({**good, "hooks": [{"trigger": "combat_end", "effects": [{"op": "block", "amount": 3}]}]}, "combat_end non-heal"),
        ({**good, "hooks": [{"trigger": "turn_end", "target": "attacker", "effects": [{"op": "damage", "amount": 2}]}]}, "attacker off attacked"),
        ({**good, "hooks": [{"trigger": "turn_start", "effects": [{"op": "scry", "amount": 2}]}]}, "op not in relic subset"),
        ({**good, "modifiers": [{"stat": "max_hp", "amount": 5}], "hooks": []}, "unknown modifier stat"),
        ({**good, "hooks": [{"trigger": "turn_start", "when": {"kind": "orbs_match"}, "effects": [{"op": "block", "amount": 2}]}]}, "orb condition on a relic"),
    ]
    for r, label in shapes:
        s_ok, v_ok = schema_ok(r), not class_forge._validate_relic(r)
        check(not s_ok and not v_ok, f"{label}: schema={'accept' if s_ok else 'reject'} validate_relic={'accept' if v_ok else 'reject'} (both must reject)")


def test_prototype_still_reachable() -> None:
    print("the archived prototype contract is reachable for the prototype-era tests:")
    ov = paths.prototype_overrides()
    check(set(ov) == set(paths.CONTRACT_ATTRS), "prototype_overrides covers CONTRACT_ATTRS")
    missing = [k for k, p in ov.items() if not p.exists() and "GENERATED" not in k]
    check(not missing, f"prototype contract files missing: {missing}")
    check("prototype" in str(ov["CARD_SCHEMA"]), "prototype card schema lives under prototype/")


def test_production_modules_free_of_prototype_ops() -> None:
    print("production modules name no prototype ops outside comments:")
    root = Path(class_forge.__file__).parent
    for rel in PRODUCTION_MODULES:
        src = (root / rel).read_text(encoding="utf-8")
        # strip comments and docstrings (crudely: '#...' to end of line, and triple-quoted blocks)
        code = re.sub(r'"""[\s\S]*?"""', "", src)
        code = re.sub(r"#[^\n]*", "", code)
        hits = sorted({m.group(0) for m in _PROTOTYPE_TOKEN.finditer(code)})
        check(not hits, f"{rel} still carries prototype op tokens in code: {hits}")
    # validator.py: the prototype composites live ONLY in the legacy set, never in the mod build-around set
    from btsgen import validator as _v
    legacy = {"multi", "conditional", "from_state", "fuse"}
    check(not (legacy & _v._BUILD_AROUND_OPS), f"_BUILD_AROUND_OPS still lists prototype ops: {legacy & _v._BUILD_AROUND_OPS}")
    check(legacy == _v._LEGACY_PROTOTYPE_OPS, "_LEGACY_PROTOTYPE_OPS is exactly the four prototype composites")
    # and a mod-contract validator never scores them: a (schema-invalid) prototype composite contributes 0
    v = CardValidator()
    check(v._mod_contract, "a default CardValidator is on the mod contract")
    check(v._score_effect({"op": "from_state", "emit": "damage", "value": {"state": "block"}}) == 0.0,
          "from_state scores 0 under the mod contract (legacy scorer not reached)")
    check(v._score_effect({"op": "multi", "times": 2, "effects": [{"op": "damage", "amount": 5}]}) == 0.0,
          "multi scores 0 under the mod contract (legacy scorer not reached)")


def main() -> int:
    test_paths_default_to_mod_contract()
    test_all_mod_statuses_known()
    test_relic_schema_matches_validate_relic()
    test_prototype_still_reachable()
    test_production_modules_free_of_prototype_ops()
    print(f"\n{_PASS} passed, {_FAIL} failed")
    return 1 if _FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
