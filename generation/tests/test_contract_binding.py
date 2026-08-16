"""Regression: point_btsgen_at_mod_contract() must win even when a paths-bearing btsgen module was
imported FIRST (the import-order footgun that shipped the Blood Orchard triad forge on the prototype
contract — the model emitted prototype `conditional`/`from_state` ops instead of the mod's `when` guards,
so every `when`/scale/balance_step coverage floor read zero).

`btsgen.paths` snapshots its BTSGEN_* env vars once at first import. Importing generator/contract/validator
binds paths to the ENV-CLEAN prototype defaults; a later env-set alone is a no-op, so the function reloads
the already-imported paths module in place. That import-order behaviour can only be exercised in a clean
process (pytest's shared process already has paths bound to the mod contract via conftest), so this runs a
subprocess with the exact BROKEN order.

Run:  uv run python -m tests.test_contract_binding      (from generation/)
"""
from __future__ import annotations

import subprocess
import sys

# The subprocess reproduces forge_triad_dump.py's import order: a paths-bearing module (generator) imported
# BEFORE point_btsgen_at_mod_contract(), with NO manual importlib.reload(paths). It asserts the function
# still flips paths to the mod contract, that a `when`-gated card validates + is counted, and that the
# prototype `conditional`-op card is (now correctly) rejected.
_CHILD = r'''
import os
for k in ("BTSGEN_CARD_SCHEMA", "BTSGEN_VOCABULARY", "BTSGEN_GODOT_ROOT",
          "BTSGEN_STATUSES_DIR", "BTSGEN_CARDS_DIR", "BTSGEN_GENERATED_DIR"):
    os.environ.pop(k, None)

# BROKEN order: generator (top-level `from . import paths`) binds paths = PROTOTYPE, before the point call.
from btsgen.generator import AnthropicGenerator  # noqa: F401
from btsgen.class_forge import point_btsgen_at_mod_contract
from btsgen import paths
assert paths.VOCABULARY.parent.parent.name == "prototype", paths.VOCABULARY

point_btsgen_at_mod_contract()  # must reload paths in place -> mod contract, with no manual reload
assert paths.VOCABULARY.parent.parent.name == "mod", ("point() did not flip paths:", paths.VOCABULARY)
assert paths.CARD_SCHEMA.parent.name == "contract", paths.CARD_SCHEMA

from btsgen import census, validator
v = validator.CardValidator()

when_card = {"id": "p1", "name": "P1", "type": "attack", "rarity": "uncommon", "cost": 1,
             "target": "enemy", "source": "llm",
             "effects": [{"op": "damage", "amount": 10},
                         {"op": "block", "amount": 8, "when": {"kind": "dark_ge", "value": 4}}]}
vr = v.validate(when_card)
assert vr.ok, ("mod when-card should validate:", vr.errors)
assert dict(census.walk_card(when_card).whens) == {"dark_ge": 1}, census.walk_card(when_card).whens

# the prototype conditional-op shape (what Blood Orchard shipped) is NOT in the mod op enum -> rejected now
cond_card = {"id": "p2", "name": "P2", "type": "attack", "rarity": "uncommon", "cost": 1,
             "target": "enemy", "source": "llm",
             "effects": [{"op": "damage", "amount": 10},
                         {"op": "conditional", "if": {"state": "hp", "op": "lt", "value": 30},
                          "then": [{"op": "damage", "amount": 8}]}]}
assert not v.validate(cond_card).ok, "prototype conditional-op should be rejected under the mod contract"

# the generator's system prompt now teaches the mod `when` guard (a dark_ge/light_ge gated payoff)
from btsgen import contract
sp = contract.system_prompt()
assert "dark_ge" in sp, "mod system prompt should teach the when-guard conditions"

print("OK")
'''


def test_point_reloads_already_imported_paths() -> None:
    proc = subprocess.run([sys.executable, "-c", _CHILD], capture_output=True, text=True)
    assert proc.returncode == 0, (
        f"subprocess failed:\nSTDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}")
    assert proc.stdout.strip().endswith("OK"), proc.stdout


if __name__ == "__main__":
    test_point_reloads_already_imported_paths()
    print("test_contract_binding: PASS")
