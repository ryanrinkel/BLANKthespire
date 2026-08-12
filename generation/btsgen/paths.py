"""Locate the content contract the harness reads/writes, relative to this module.

Layout:
    <repo>/generation/     <- this package lives here
    <repo>/prototype/      <- the ARCHIVED schema/content contract inherited from the original
                              Godot prototype (the legacy CLIs' default "build root")
    <repo>/mod/contract/   <- the LIVE STS2-mod contract (card schema, VOCABULARY.md, statuses)

The production path — the website forge and `btsgen-forge-class` — calls
`class_forge.point_btsgen_at_mod_contract()`, which overrides everything below to
`mod/contract/`. With no env vars set, the defaults target the archived `prototype/`
contract so the legacy single-artifact CLIs and the offline test suite still run.
Every path can be repointed via the BTSGEN_* env vars below.
"""
from __future__ import annotations

import os
from pathlib import Path

# .../generation/btsgen/paths.py -> repo root is two parents up from the package dir
_REPO_ROOT = Path(__file__).resolve().parents[2]


def _env_path(var: str, default: Path) -> Path:
    """Allow the active 'build root' / contract files to be repointed via BTSGEN_* env vars.

    Default targets the archived prototype contract (prototype/) so the legacy CLIs are unchanged.
    The STS2 mod's forge sets these to its CONSTRAINED contract (only the effect ops the
    C# EffectRunner can actually run), so generated cards are guaranteed playable. Read at import,
    so anything overriding them must set the env BEFORE importing this package.
    """
    v = os.environ.get(var)
    return Path(v) if v else default


GODOT_ROOT = _env_path("BTSGEN_GODOT_ROOT", _REPO_ROOT / "prototype")

CARD_SCHEMA = _env_path("BTSGEN_CARD_SCHEMA", GODOT_ROOT / "core" / "validation" / "schema" / "card.schema.json")
VOCABULARY = _env_path("BTSGEN_VOCABULARY", GODOT_ROOT / "docs" / "VOCABULARY.md")

# The single editable source for the forge's design heuristics (rarity ladder, reprint/loop discipline,
# HP economy, per-archetype balance notes). Prose only — read by path at prompt-build time so edits ship
# via plain git-pull. Lives in mod/contract/; default anchors at the repo's mod contract (the real file),
# and point_btsgen_at_mod_contract() overrides it for the non-editable droplet install.
DESIGN_HEURISTICS = _env_path("BTSGEN_DESIGN_HEURISTICS", _REPO_ROOT / "mod" / "contract" / "DESIGN_HEURISTICS.md")

CARDS_DIR = _env_path("BTSGEN_CARDS_DIR", GODOT_ROOT / "data" / "cards")            # authored pool (+ promoted llm cards)
STATUSES_DIR = _env_path("BTSGEN_STATUSES_DIR", GODOT_ROOT / "data" / "statuses")   # known status ids for ref-integrity
GENERATED_DIR = _env_path("BTSGEN_GENERATED_DIR", GODOT_ROOT / "data" / "generated" / "cards")  # quarantine

# Relics: same shape as cards now that relics are fully data-driven (hooks reuse the card effect
# vocabulary). The relic harness reads these and quarantines into GENERATED_RELICS_DIR.
RELIC_SCHEMA = GODOT_ROOT / "core" / "validation" / "schema" / "relic.schema.json"
RELIC_VOCABULARY = GODOT_ROOT / "docs" / "RELIC_VOCABULARY.md"
RELICS_DIR = GODOT_ROOT / "data" / "relics"          # authored pool (+ promoted llm relics)
GENERATED_RELICS_DIR = GODOT_ROOT / "data" / "generated" / "relics"  # quarantine

# Characters: a class is pure data (max_hp / starting relic / starting deck of existing card ids).
# The character harness generates a whole BUNDLE (class + its cards + its starter relic), so it
# also writes to the card/relic quarantines above.
CHARACTER_SCHEMA = GODOT_ROOT / "core" / "validation" / "schema" / "character.schema.json"
CHARACTERS_DIR = GODOT_ROOT / "data" / "characters"  # authored classes (+ promoted llm classes)
GENERATED_CHARACTERS_DIR = GODOT_ROOT / "data" / "generated" / "characters"  # quarantine

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
            "Godot project content not found (build root moved?):\n  "
            + "\n  ".join(str(p) for p in missing)
        )


def assert_relic_project_present() -> None:
    """Fail loudly if the relic contract files are missing/moved."""
    missing = [p for p in (GODOT_ROOT, RELIC_SCHEMA, RELIC_VOCABULARY, RELICS_DIR, STATUSES_DIR) if not p.exists()]
    if missing:
        raise FileNotFoundError(
            "Relic contract content not found (build root moved?):\n  "
            + "\n  ".join(str(p) for p in missing)
        )


def assert_character_project_present() -> None:
    """Fail loudly if the character contract files are missing/moved (the character harness
    also needs the card + relic contracts, since a class bundle generates both)."""
    assert_project_present()
    assert_relic_project_present()
    missing = [p for p in (CHARACTER_SCHEMA, CHARACTERS_DIR) if not p.exists()]
    if missing:
        raise FileNotFoundError(
            "Character contract content not found (build root moved?):\n  "
            + "\n  ".join(str(p) for p in missing)
        )
