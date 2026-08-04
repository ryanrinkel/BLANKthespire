# BLANK the spire — Creative Harness Front-End Plan (associative class design)

Status: **✅ SHIPPED + DEFAULT — reconciled 2026-06-27** (commit `1a56fea` built the staged front-end as the AUGMENT drop-in; `debdf02` made it the default forge path; `generation/btsgen/frontend/` modules + `generation/btsgen/data/archetypes.json` are present). Original plan status preserved below. — Validated by two end-to-end dry-runs (subagents, no API key) on
"Jedi" and "a gardener" 2026-06-19. This plan turns those runs into a concrete `btsgen` build spec.

## Goal
Replace the single opaque "concept → blueprint" LLM call with a **staged associative front-end** that thinks
the way a designer does: diverge on theme, then converge on a buildable identity. The stages are visible,
inspectable, and each one can be nudged or improved independently — which is what makes the harness more
creative AND more legible.

```
theme ──▶ 1.CLOUD ──▶ 2.CLUSTER ──▶ 3.MAP ──▶ 4.COMPOSE (N candidates) ──▶ 5.RELIC ──▶ 6.CHECKPOINT
                                     (catalog)        (collision+buildability)              (human picks)
                                                                                                │
                                                                                                ▼
                                                              chosen identity ──▶ existing blueprint stage
```

## What changes vs. what doesn't (the seam)
The whole change lives **upstream of one line.** In `generation/btsgen/class_forge.py::forge_class()`, stage 1
is today:

```python
text, messages = blueprint_gen.first_attempt(brief)   # one call → the blueprint dict
bp = _extract(text); errs = _validate_blueprint(bp); ...repair...
```

Everything after (stage 2 card set, the orb/status/summon pool injection, merchant/rare safety nets, BTSC
assembly) consumes `bp` and is **untouched**. The new front-end is a drop-in producer of a `bp` dict that
passes `_validate_blueprint()`.

## Architecture decision: AUGMENT, don't replace
Two options were considered:
- **(A) Replace** the blueprint call with staged calls that directly emit the full blueprint dict, card briefs
  and all.
- **(B) Augment (CHOSEN):** the staged front-end produces a **creative dossier** (the chosen identity), and the
  *existing* blueprint prompt is reframed from "concept → everything" into "**dossier → card briefs + pools**."

**Why B:** the existing `_BlueprintContract` already encodes hard-won expertise — the merchant rule (≥1 non-basic
of each type), the `MIN_RARES` floor, the orb/status/summon pool grammar, the `TARGET_*` pool sizing. Throwing
that away (A) re-litigates solved problems. Instead, the front-end hands the blueprint stage a *much more
constrained, higher-quality input* (a named identity + two archetypes-in-vocabulary-terms + metaphors + relic),
and the blueprint stage does what it's already good at: turning that into validated card briefs. All existing
validation and safety nets stay live.

## The stages (each is one LLM call — mirrors the per-card cost model)
| # | stage | in → out | notes |
|---|-------|----------|-------|
| 1 | **Cloud** | theme → 20-30 concept association cloud | pure thematic divergence, NO mechanics. |
| 2 | **Cluster** | cloud → 3-5 named thematic threads | each with a one-line "feeling". |
| 3 | **Map** | clusters + **archetype catalog** → cluster→archetype mappings w/ cited metaphor resonance | emits collision signal + appends unmapped concepts to the gap log. |
| 4 | **Compose** | mappings → **N candidate builds** (2 archetypes each, in tension) | each: name, fantasy, core loop, weakness, **buildability flag**. |
| 5 | **Relic** | chosen candidate → keystone starter relic (design intent) | see *Relic dependency* below. |
| 6 | **Checkpoint** | candidates → chosen identity | human picks (testing default); auto-pick top in autonomous mode. |
| → | **Dossier→blueprint** | chosen identity → `bp` dict via the reframed blueprint stage | reuses all existing pool/brief/safety logic. |

Stages 1-2 may be merged into one call, and 3-4 into one call, to cut latency/cost (the dry-runs did exactly
this — 2 calls covered 4 stages — with no quality loss). Recommend shipping **merged** (cloud+cluster,
map+compose) = ~3 front-end calls + the blueprint call, and only splitting if a stage needs isolation.

## New authored data asset: the archetype catalog
The catalog is the heart of the system and the main thing to author and curate over time. Proposed home:
`generation/btsgen/data/archetypes.json` (read by the map stage; mirrored into the map prompt).

Each entry:
```json
{
  "id": "retain_hold",
  "name": "Retain / hold & build",
  "description": "keep cards in hand, set up the perfect turn",
  "metaphors": ["the held breath", "coiling", "the perfect strike", "foresight"],
  "vocabulary": { "ops": ["retain", "draw", "add_trigger"], "class_kind": "normal" },
  "buildable": true,
  "gap_refs": ["VOCABULARY_GAPS#5"]
}
```
- `metaphors` — **seeded but OPEN**: the map stage matches against them AND may add its own connections
  (consistency floor + creative ceiling — see [[creative-harness-rework]]).
- `vocabulary` — which ops/pools/`class_kind` (normal/orb/status/summon) the archetype needs. Drives the
  **buildability flag**.
- `buildable` / `gap_refs` — false when the archetype's signature needs an op not yet in `VOCABULARY.md`;
  links to the gap entry that would unlock it.

Seed catalog (12 archetypes) is captured in the dry-run notes; promote it into this file as task 1.

## The three refinements the dry-runs argued for (bake in from day one)
1. **Collision check** (compose stage). When ≥2 clusters map to the same archetype (gardener: A+B→Powers,
   D+E→Debuff), the stage must either (a) differentiate them mechanically (e.g. per-turn Power vs. the "ripen"
   countdown, gap #6) or (b) flag the archetype as the theme's **spine** and lean in. A theme's archetype
   collisions reveal its mechanical center of gravity — surface it, don't silently overwrite one mapping.
2. **Buildability flag** (checkpoint). Every candidate is tagged `buildable-now` vs `needs-vocab:<gap>` by
   cross-referencing the catalog's `buildable`/`gap_refs` against the live `VOCABULARY.md`. The human (or the
   autonomous picker) sees the cost of each choice *before* card-gen, not after. Pattern observed in BOTH runs:
   the most thematically distinctive candidate is the one needing new vocab — so this flag is what keeps the
   harness from quietly converging on generic builds.
3. **`VOCABULARY_GAPS.md` as a first-class roadmap input.** The map/compose stages append discovered gaps
   (already the standing practice); conversely the catalog's `buildable` flags are derived from what the gap
   log marks `done`. The gap log is the bridge between "what the harness can imagine" and "what the engine can
   build" — it drives the vocabulary roadmap (see `VOCAB_EXPANSION_PLAN.md`, e.g. Phase L from the Jedi run).

## Dossier → blueprint dict (the translation)
The chosen candidate carries: class name, fantasy, two archetypes (each with a vocabulary-terms description),
a suggested `max_hp`, the `class_kind` implied by the archetypes (→ `orb_slots`/`orb_pool`/`status_pool`/
`summon_pool`), and the keystone relic. The reframed blueprint stage receives this as structured context and
produces the `cards[]` briefs + any pools, then `_validate_blueprint()` runs exactly as today (merchant rule,
`MIN_RARES`, pool grammar all still enforced). No change to the dict shape → no change downstream.

## Code touch-points
- `generation/btsgen/class_forge.py` — `forge_class()` stage 1: call the new `BlueprintBuilder` (the staged
  front-end) instead of `blueprint_gen.first_attempt`; keep the same `_validate_blueprint`/repair guard.
- `generation/btsgen/frontend/` (new) — one module per stage contract (cloud, cluster, map, compose, relic),
  styled after `_BlueprintContract` (system_prompt / user_brief / repair_message). Plus the dossier→blueprint
  reframed contract.
- `generation/btsgen/data/archetypes.json` (new) — the catalog.
- `generation/btsgen/cli_forge_class.py` — add a `--checkpoint`/`--auto` flag (human-in-loop vs autonomous) and
  surface candidate previews; the website wires the checkpoint into a browser screen (see [[p3-website-plan]]).
- `_fake_blueprint` / `fakes.py` — fake outputs for each new stage so `--fake` (offline, no key) still works.

## Dependencies & sequencing
- **Relic dependency:** `class_forge.py` does NOT generate starter relics today ("the mod uses a placeholder;
  custom forged relics are a later phase"). So stage 5's keystone relic is, for now, **design intent that
  informs the card briefs + gets logged** — NOT a generated, playable relic. Wiring the keystone into a real
  forged relic depends on the separate forged-relic phase (the prototype `relic_pipeline.py` is not yet on the
  class path). Track as a follow-up; the front-end is valuable without it.
- **Human-in-the-loop:** checkpoint ON by default during testing; the `--auto` path (pick top candidate) is the
  road to autonomous generation later (see [[creative-harness-rework]]).
- **Cost note (website/BYOK):** the front-end adds ~3 calls before the per-card calls. Acceptable; merge stages
  (above) keeps it modest. Expose model/effort knobs as the existing CLI already does.

## Build order (suggested)
1. Author `data/archetypes.json` (seed 12 + metaphors + vocabulary + buildable flags).
2. `frontend/` stage contracts (start merged: cloud+cluster, map+compose, relic) + fakes.
3. `BlueprintBuilder` orchestrator + dossier→blueprint reframed contract; wire into `forge_class` stage 1.
4. Collision check + buildability flag + gap-append hooks.
5. CLI `--checkpoint/--auto`; then website checkpoint screen.

## Open decisions for you
- **Merged vs. split stages** for v1 (recommend merged: ~3 front-end calls).
- **Catalog home:** `generation/btsgen/data/` (generator-local) vs `mod/contract/` (alongside VOCABULARY.md, if
  the mod/website should read it too).
- **Autonomous picker policy:** when `--auto`, prefer the highest-`buildable` candidate, or the most
  thematically distinctive (and accept a vocab gap)?
