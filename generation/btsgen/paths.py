"""Locate the content contract the harness reads/writes, relative to this module.

Layout:
    <repo>/generation/     <- this package lives here
    <repo>/mod/contract/   <- the LIVE STS2-mod contract (card schema, relic schema, VOCABULARY.md,
                              RELIC_VOCABULARY.md, DESIGN_HEURISTICS.md, statuses/) — THE DEFAULT
    <repo>/mod/content/    <- the mod's authored card pool (+ relics/)
    <repo>/prototype/      <- the ARCHIVED schema/content contract inherited from the original Godot
                              prototype. Legacy only: reachable through the BTSGEN_* env vars or
                              `prototype_overrides()` (the offline prototype-era tests use it).

Phase AJ-b (VOCAB_GAP_REMEDIATION_PLAN, 2026-09-09): the defaults now target the MOD contract. They used to
target `prototype/`, and `class_forge.point_btsgen_at_mod_contract()` had to repoint everything at forge time —
an import-order footgun that once shipped a whole triad forge on the prototype vocabulary (the model emitted
prototype-only `conditional`/`from_state` ops the mod rejects). `point_btsgen_at_mod_contract()` still exists and
is still safe to call; it is now a no-op safety net. Every path can be repointed via the BTSGEN_* env vars below
(read ONCE at import — set them before importing this package, or reload this module).
"""
from __future__ import annotations

import os
from pathlib import Path

# .../generation/btsgen/paths.py -> repo root is two parents up from the package dir
_REPO_ROOT = Path(__file__).resolve().parents[2]
MOD_CONTRACT = _REPO_ROOT / "mod" / "contract"
MOD_CONTENT = _REPO_ROOT / "mod" / "content"
PROTOTYPE_ROOT = _REPO_ROOT / "prototype"
# Scratch quarantines for generated content under the mod contract (git-ignored; see .gitignore generation/scratch/).
_SCRATCH = _REPO_ROOT / "generation" / "scratch" / "_class_gen"


def _env_path(var: str, default: Path) -> Path:
    """Allow the active contract files to be repointed via BTSGEN_* env vars.

    Defaults target the live STS2-mod contract (mod/contract + mod/content) — only the effect ops the C#
    EffectRunner can actually run, so generated cards are guaranteed playable. The archived prototype contract
    is reachable by pointing these at prototype/ (see `prototype_overrides()`). Read at import, so anything
    overriding them must set the env BEFORE importing this package (or reload this module).
    """
    v = os.environ.get(var)
    return Path(v) if v else default


# The "build root". Only asserted to exist (its content paths are all individual settings below). Historically the
# Godot prototype root; now the repo root, which is deployed everywhere the package runs.
GODOT_ROOT = _env_path("BTSGEN_GODOT_ROOT", _REPO_ROOT)

CARD_SCHEMA = _env_path("BTSGEN_CARD_SCHEMA", MOD_CONTRACT / "card.schema.json")
VOCABULARY = _env_path("BTSGEN_VOCABULARY", MOD_CONTRACT / "VOCABULARY.md")

# The single editable source for the forge's design heuristics (rarity ladder, reprint/loop discipline,
# HP economy, per-archetype balance notes). Prose only — read by path at prompt-build time so edits ship
# via plain git-pull.
DESIGN_HEURISTICS = _env_path("BTSGEN_DESIGN_HEURISTICS", MOD_CONTRACT / "DESIGN_HEURISTICS.md")

CARDS_DIR = _env_path("BTSGEN_CARDS_DIR", MOD_CONTENT / "cards")            # authored pool (+ promoted llm cards)
STATUSES_DIR = _env_path("BTSGEN_STATUSES_DIR", MOD_CONTRACT / "statuses")   # known status ids for ref-integrity
GENERATED_DIR = _env_path("BTSGEN_GENERATED_DIR", _SCRATCH)                  # quarantine

# Relics: fully data-driven (hooks reuse the card effect vocabulary). The mod relic schema mirrors
# mod/BlankTheSpireCode/Engine/RelicSpec.cs; RELIC_VOCABULARY.md is the LLM-facing contract.
RELIC_SCHEMA = _env_path("BTSGEN_RELIC_SCHEMA", MOD_CONTRACT / "relic.schema.json")
RELIC_VOCABULARY = _env_path("BTSGEN_RELIC_VOCABULARY", MOD_CONTRACT / "RELIC_VOCABULARY.md")
RELICS_DIR = _env_path("BTSGEN_RELICS_DIR", MOD_CONTENT / "relics")          # authored pool (+ promoted llm relics)
GENERATED_RELICS_DIR = _env_path("BTSGEN_GENERATED_RELICS_DIR", _SCRATCH / "relics")  # quarantine

# Characters — LEGACY (prototype-era character_contract / character_pipeline only). The mod has no standalone
# character schema: a forged class is a whole BTSC bundle built by class_forge (the production path), validated
# by the C# importer. These default to the prototype so the legacy CLIs + their tests keep working unchanged.
CHARACTER_SCHEMA = _env_path("BTSGEN_CHARACTER_SCHEMA", PROTOTYPE_ROOT / "core" / "validation" / "schema" / "character.schema.json")
CHARACTERS_DIR = _env_path("BTSGEN_CHARACTERS_DIR", PROTOTYPE_ROOT / "data" / "characters")
GENERATED_CHARACTERS_DIR = _env_path("BTSGEN_GENERATED_CHARACTERS_DIR", PROTOTYPE_ROOT / "data" / "generated" / "characters")

# Every contract-defining attribute above (the set the test conftest swaps as a unit).
CONTRACT_ATTRS = ("GODOT_ROOT", "CARD_SCHEMA", "VOCABULARY", "DESIGN_HEURISTICS", "CARDS_DIR", "STATUSES_DIR",
                  "GENERATED_DIR", "RELIC_SCHEMA", "RELIC_VOCABULARY", "RELICS_DIR", "GENERATED_RELICS_DIR",
                  "CHARACTER_SCHEMA", "CHARACTERS_DIR", "GENERATED_CHARACTERS_DIR")


def prototype_overrides() -> dict[str, Path]:
    """The archived PROTOTYPE contract as an attr -> path map (same keys as CONTRACT_ATTRS). The prototype-era
    tests (test_validator / test_relic_validator / test_character_pipeline / test_pipeline_balance_repair) pin
    these; nothing in production reads them. DESIGN_HEURISTICS has no prototype twin — it stays the mod file."""
    p = PROTOTYPE_ROOT
    return {
        "GODOT_ROOT": p,
        "CARD_SCHEMA": p / "core" / "validation" / "schema" / "card.schema.json",
        "VOCABULARY": p / "docs" / "VOCABULARY.md",
        "DESIGN_HEURISTICS": MOD_CONTRACT / "DESIGN_HEURISTICS.md",
        "CARDS_DIR": p / "data" / "cards",
        "STATUSES_DIR": p / "data" / "statuses",
        "GENERATED_DIR": p / "data" / "generated" / "cards",
        "RELIC_SCHEMA": p / "core" / "validation" / "schema" / "relic.schema.json",
        "RELIC_VOCABULARY": p / "docs" / "RELIC_VOCABULARY.md",
        "RELICS_DIR": p / "data" / "relics",
        "GENERATED_RELICS_DIR": p / "data" / "generated" / "relics",
        "CHARACTER_SCHEMA": p / "core" / "validation" / "schema" / "character.schema.json",
        "CHARACTERS_DIR": p / "data" / "characters",
        "GENERATED_CHARACTERS_DIR": p / "data" / "generated" / "characters",
    }


def use_prototype_contract() -> None:
    """LEGACY: point this module at the archived prototype contract IN PLACE (module attrs only — deliberately NOT the
    BTSGEN_* env, so nothing leaks into child processes or a later reload; pytest's conftest re-pins per test anyway).
    Used by the prototype-era standalone tests; never by production. `class_forge.point_btsgen_at_mod_contract()`
    switches back."""
    g = globals()
    for attr, p in prototype_overrides().items():
        g[attr] = p


# This package's own dir (for .env discovery).
PACKAGE_DIR = Path(__file__).resolve().parents[1]

# Player card feedback (the in-game inspect view and the website's rating buttons append JSONL
# entries in this shape). The card/character prompts read it back as few-shot examples /
# anti-examples, and feedback_store retrieves similar entries into class/card briefs.
# Env-overridable: on the droplet the package is installed non-editably (site-packages has no
# feedback/ dir), so web/forge.py points this at the repo checkout's curated file.
FEEDBACK_FILE = _env_path("BTSGEN_FEEDBACK_FILE", PACKAGE_DIR / "feedback" / "card_feedback.jsonl")

# Extra LIVE feedback sources (os.pathsep-separated), unioned with FEEDBACK_FILE by
# feedback_store.load_entries(). The website sets this to its append-only card_feedback.jsonl so
# droplet forges apply fresh player ratings without waiting for the manual pull-into-git cycle.
FEEDBACK_EXTRA = [Path(p.strip()) for p in os.environ.get("BTSGEN_FEEDBACK_EXTRA", "").split(os.pathsep)
                  if p.strip()]

# Distilled StS2 rarity-calibration digest (see reference/distill_sts2.py for provenance).
# Optional: prompts embed it when present to teach the power/complexity ladder per rarity.
STS2_EXAMPLES = PACKAGE_DIR / "reference" / "sts2_rarity_examples.md"


def assert_project_present() -> None:
    """Fail loudly if the build root or its contract files are missing/moved."""
    missing = [p for p in (GODOT_ROOT, CARD_SCHEMA, VOCABULARY, CARDS_DIR, STATUSES_DIR) if not p.exists()]
    if missing:
        raise FileNotFoundError(
            "Contract content not found (repo layout moved?):\n  "
            + "\n  ".join(str(p) for p in missing)
        )


def assert_relic_project_present() -> None:
    """Fail loudly if the relic contract files are missing/moved. RELICS_DIR (the authored relic pool) may be
    absent under the mod contract — forged relics are per-class starters, there is no shared pool yet."""
    missing = [p for p in (GODOT_ROOT, RELIC_SCHEMA, RELIC_VOCABULARY, STATUSES_DIR) if not p.exists()]
    if missing:
        raise FileNotFoundError(
            "Relic contract content not found (repo layout moved?):\n  "
            + "\n  ".join(str(p) for p in missing)
        )


def assert_character_project_present() -> None:
    """LEGACY (prototype character harness): fail loudly if the character contract files are missing/moved (the
    character harness also needs the card + relic contracts, since a class bundle generates both)."""
    assert_project_present()
    assert_relic_project_present()
    missing = [p for p in (CHARACTER_SCHEMA, CHARACTERS_DIR) if not p.exists()]
    if missing:
        raise FileNotFoundError(
            "Character contract content not found (prototype/ moved?):\n  "
            + "\n  ".join(str(p) for p in missing)
        )
