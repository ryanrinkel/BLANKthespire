"""Shared pytest fixtures + contract pinning for the btsgen offline test suite.

These files each pass alone (`python -m tests.<name>`) but collided under pytest, which imports every
module into ONE process where `btsgen.paths` is a single global. Two hazards, both fixed here:

1. **Conflicting contracts.** `btsgen.paths` reads its BTSGEN_* env vars ONCE, at first import, so the
   active card schema/vocabulary/corpus is process-global. test_frontend and test_keystone_balance
   point at the constrained *mod* contract at import (`point_btsgen_at_mod_contract()`); their
   module-level objects (test_keystone's `_V`, the forge catalog) bake that in. But
   test_pipeline_balance_repair uses the looser *prototype* contract — its 4×`draw` card is
   valid-with-a-warning under the prototype and hard-INVALID under the mod contract's "each value used
   once" rule. Whichever module pytest imported first won the binding, so one file always ran on the
   wrong corpus. We pin the mod contract as the process default (below), then swap in the prototype
   contract per-test for the file that needs it (the `contract` fixture).

2. **Shared quarantine dir.** Each module points `paths.GENERATED_DIR` (the card quarantine) at its own
   dir; last write wins and every test then quarantines into the same place. `CardValidator.known_cards`
   snapshots that dir at construction, so tests leak cards to each other. `contract` also hands every
   test a fresh, empty quarantine dir.

Standalone `python -m tests.<name>` runs don't load conftest, so each file keeps its original
module-level setup there — this only hardens the pytest path.
"""
from __future__ import annotations

import importlib
import os
import tempfile
from pathlib import Path

import pytest

# The contract-defining path attributes point_btsgen_at_mod_contract() controls (GENERATED_DIR is the
# quarantine, handled separately per-test), plus the relic/character contract paths the prototype-era
# harness tests read. Swapping this set re-points the whole validator corpus.
_CONTRACT_ATTRS = ("GODOT_ROOT", "CARD_SCHEMA", "VOCABULARY", "DESIGN_HEURISTICS", "CARDS_DIR",
                   "STATUSES_DIR", "RELIC_SCHEMA", "RELIC_VOCABULARY", "RELICS_DIR",
                   "CHARACTER_SCHEMA", "CHARACTERS_DIR")

# Test modules that need the looser PROTOTYPE contract instead of the mod default. Matched as a
# substring of the test's module name. (test_validator / test_relic_validator / test_character_pipeline
# exercise the prototype-era engine-faithful validators and authored pools; the phase/forge tests pin
# the mod contract themselves.)
_PROTOTYPE_MODULES = ("pipeline_balance_repair", "test_validator", "relic_validator",
                      "character_pipeline")

# --- Snapshot the PROTOTYPE contract (paths' env-clean defaults), THEN pin the mod contract as the
# process default. conftest is imported before any test module, so this is the first paths binding. ---
for _k in ("BTSGEN_GODOT_ROOT", "BTSGEN_CARD_SCHEMA", "BTSGEN_VOCABULARY", "BTSGEN_DESIGN_HEURISTICS",
           "BTSGEN_STATUSES_DIR", "BTSGEN_CARDS_DIR", "BTSGEN_GENERATED_DIR"):
    os.environ.pop(_k, None)

from btsgen import paths  # env-clean here -> prototype defaults

_PROTOTYPE = {k: getattr(paths, k) for k in _CONTRACT_ATTRS}

from btsgen.class_forge import point_btsgen_at_mod_contract  # imports paths lazily; safe to import now

point_btsgen_at_mod_contract()      # sets the mod-contract BTSGEN_* env
importlib.reload(paths)             # re-read them into the (single) paths module -> mod contract default
_MOD = {k: getattr(paths, k) for k in _CONTRACT_ATTRS}


@pytest.fixture(autouse=True)
def _check_counter_guard(request):
    """The standalone-style test files record failures via a module-level `check()` + `_FAIL` counter
    (their main() exits nonzero on it) instead of asserting. Under pytest that would silently swallow
    failed checks — so fail the test if its module's counter grew during the test."""
    mod = request.module
    before = getattr(mod, "_FAIL", None)
    yield
    if before is not None:
        grew = mod._FAIL - before
        assert grew == 0, f"{grew} check(s) failed in {mod.__name__} (see 'FAIL:' lines in captured stdout)"


@pytest.fixture(autouse=True)
def contract(request, monkeypatch):
    """Pin the right contract for this test's module (mod default; prototype for _PROTOTYPE_MODULES) and
    give it fresh, empty quarantine dirs. monkeypatch restores every attribute afterward."""
    modname = request.module.__name__
    wanted = _PROTOTYPE if any(m in modname for m in _PROTOTYPE_MODULES) else _MOD
    for attr, value in wanted.items():
        monkeypatch.setattr(paths, attr, value)
    monkeypatch.setattr(paths, "GENERATED_DIR", Path(tempfile.mkdtemp(prefix="btsgen_pytest_")))
    monkeypatch.setattr(paths, "GENERATED_RELICS_DIR", Path(tempfile.mkdtemp(prefix="btsgen_pytest_relic_")))
    monkeypatch.setattr(paths, "GENERATED_CHARACTERS_DIR", Path(tempfile.mkdtemp(prefix="btsgen_pytest_char_")))


def _annotated_validator(request, param: str):
    """Instantiate the validator class named in the test function's `param` annotation, resolved in the
    test's own module namespace (annotations are strings under `from __future__ import annotations`).
    Lets the standalone-style test files (whose main() passes validator instances explicitly) run under
    pytest too: `def test_accepts(v: CardValidator)` gets a fresh CardValidator built AFTER the contract
    fixture pinned this module's contract."""
    import sys as _sys
    ann = request.function.__annotations__.get(param)
    if isinstance(ann, str):
        ann = getattr(_sys.modules[request.function.__module__], ann)
    return ann()


@pytest.fixture
def v(request, contract):
    return _annotated_validator(request, "v")


@pytest.fixture
def _v(request, contract):
    return _annotated_validator(request, "_v")


@pytest.fixture
def vs(request, contract):
    # `vs` is the summon-class validator convention (see test_phase_ac.main): a CardValidator with a
    # declared summon pool, vs `vn` the plain non-summon one.
    import sys as _sys
    ann = request.function.__annotations__.get("vs")
    if isinstance(ann, str):
        ann = getattr(_sys.modules[request.function.__module__], ann)
    return ann(extra_summons={"wolf"})


@pytest.fixture
def vn(request, contract):
    return _annotated_validator(request, "vn")


@pytest.fixture
def bv(request, contract):
    return _annotated_validator(request, "bv")
