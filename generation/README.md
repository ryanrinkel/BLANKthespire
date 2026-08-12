# btsgen — the LLM class-forging harness

`btsgen` is the Python pipeline behind [blankthespire.com](https://blankthespire.com): it turns a
plain-English class concept into a complete, schema-validated **Slay the Spire 2** class (cards +
identity + keystone relic) that the `mod/` runtime can import and play.

It is engine-independent: it reads the mod's published **contract** — `mod/contract/card.schema.json`,
`mod/contract/VOCABULARY.md`, `mod/contract/RELIC_VOCABULARY.md`, `mod/contract/statuses/` — asks an
LLM to compose new content from that **closed effect vocabulary**, then validates the result the same
way the mod does. Because generation is constrained to ops the mod's C# `EffectRunner` can actually
execute, forged classes are guaranteed to load and play.

## The pipeline

```
concept sentence
   │
   ▼
staged creative front-end (btsgen/frontend/): cloud → cluster → map(catalog) → compose
   │                                          (theme facets, archetype packages, keystone relic)
   ▼
blueprint   one LLM call -> class identity + archetypes + per-card design briefs
   │
   ▼
card set    each brief -> generate -> jsonschema validate -> repair once -> balance clamp
   │           (contract carried in the prompt; the jsonschema validator is the enforcement gate)
   ▼
assemble    cards in slot order + starting deck + keystone relic -> BTSC import code
```

The mod consumes only the final validated bundle (a `BTSC.…` code you paste in-game); it never
imports this package.

## Setup

```sh
cd generation
cp .env.example .env          # then paste your LLM API key(s) — optional for tests
uv sync                       # creates .venv, installs deps
```

## Use

```sh
# offline test suite — no API key needed:
uv run pytest -q

# forge a whole class (live; needs a key):
uv run btsgen-forge-class --concept "a frost mage who freezes then shatters"

# same path, deterministic fake content, no key:
uv run btsgen-forge-class --concept "anything" --fake
```

The website (`web/`) drives the same `forge_class()` entry point, streaming progress to the browser.

### Model routing

The hosted forge can run as a **per-role model mixture** (e.g. a small fast model brainstorms, a
stronger model codes cards) via Ollama Cloud and/or OpenRouter — see `ollama_roles.example.json`
and `ollama_roles.hybrid.json`. BYOK (Anthropic/OpenAI-compatible) single-model runs are also
supported via CLI flags / the website.

## Layout

| file | role |
|------|------|
| `btsgen/paths.py` | resolve the contract + content dirs (env-overridable via `BTSGEN_*`) |
| `btsgen/class_forge.py` | the core: concept → blueprint → card set → BTSC bundle |
| `btsgen/frontend/` | staged creative front-end (theme facets, archetype catalog, keystone relic) |
| `btsgen/contract.py` | build the card prompt (vocabulary + schema + exemplars + brief) |
| `btsgen/generator.py` | live LLM call + tolerant JSON extraction |
| `btsgen/ollama_mix.py` | per-role model mixture (hosted path) + metered failover |
| `btsgen/validator.py` | jsonschema + ref-integrity + balance score |
| `btsgen/pipeline.py` | generate → validate → repair once → balance clamp → quarantine |
| `btsgen/art.py` | splash/sprite art generation for forged classes |
| `btsgen/cli_forge_class.py` | the `btsgen-forge-class` entry point |
| `btsgen/fakes.py` | deterministic offline FakeGenerator (`--fake`, tests) |
| `tests/` | offline gate tests (no API key, no game install needed) |
| `reference/` | optional StS2 rarity-calibration data — regenerated locally, never committed (see `reference/README.md`) |
| `btsgen/feedback_store.py` | feedback store + similarity retrieval: ratings most similar to the current concept/brief ride the blueprint and per-card prompts |
| `feedback/card_feedback.jsonl` | curated player card ratings (pull from the droplet via `web/tools/pull_card_feedback.ps1`), read back into prompts as examples/anti-examples. The website also reads its own live rating log directly (`BTSGEN_FEEDBACK_EXTRA`, set in `web/forge.py`), so droplet forges apply fresh feedback without a pull |

### Legacy single-artifact CLIs

The package also carries the older card/relic/character harnesses (`btsgen-generate`,
`btsgen-relic-generate`, `btsgen-character-generate`, and their `-review` counterparts) inherited
from the project's Godot-prototype era. The card pipeline is fully functional against
`mod/contract/`; the relic/character harnesses expect prototype schemas that are not part of this
repo and will fail loudly unless you repoint `btsgen/paths.py` (via `BTSGEN_*` env vars) at your
own contract. The supported, production path is `btsgen-forge-class`.
