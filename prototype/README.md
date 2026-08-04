# prototype/ — archived contract from the original Godot prototype

This is the **archived schema/content contract** inherited from the project's original Godot
prototype (BLANK the spire began life as a data-driven Godot deckbuilder before pivoting to a
Slay the Spire 2 mod). It contains only the data the generator's legacy CLIs and offline test
suite read:

- `core/validation/schema/` — card / relic / character JSON schemas
- `docs/VOCABULARY.md`, `docs/RELIC_VOCABULARY.md` — the prototype-era effect vocabularies
- `data/cards|statuses|relics|characters/` — the authored content pools

**The live contract is `mod/contract/`** — that is what the website forge and
`btsgen-forge-class` actually generate against (via
`btsgen.class_forge.point_btsgen_at_mod_contract()`). This directory exists so that
`generation/btsgen/paths.py`'s env-clean defaults resolve, keeping the legacy single-artifact
harnesses (`btsgen-generate`, `btsgen-relic-generate`, `btsgen-character-generate`) and the
keyless test suite runnable. The Godot engine/scenes themselves are not part of this repo.
