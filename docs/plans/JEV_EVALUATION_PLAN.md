# Jev (TypeSafe "System One") evaluation plan

Status: Phase 0 + 0c measured; Phases 1a + 1b BUILT behind `BTS_VOCAB_GATE` (default off) and A/B'd locally 2026-09-25/26, NOT committed or deployed. Paired 1b A/B DONE 2026-09-26 (with the when/trigger fixes): parity on cards, -35% card input tokens. Written 2026-09-25.

## 1. What Jev is

TypeSafe AI's Jev, early access since 2026-09-15. It is not a language model. You send a `state`
(string/object/array) plus a map of typed `questions`, and it answers every question in one
parallel pass with calibrated probabilities. It never writes text.

| Fact | Value | Source |
|---|---|---|
| Question types | `choice` (up to 255 options, each with optional free-text criteria), `noul` (yes/no probability), `score` (2-10 ordered levels) | docs.typesafe.ai/api |
| Endpoint | `POST https://api.typesafe.ai/v1/systemone`, bearer key, `model: "jev-latest"` | docs.typesafe.ai/api |
| Python SDK | `pip install typesafe-sdk`, `TypeSafeClient().system_one(state=..., questions={...})`, async client available | docs.typesafe.ai/sdk/python |
| Pricing | $0.042 per million input tokens, output unmetered | DataCamp write-up (TypeSafe says it may be subsidized, expects prices to fall) |
| Latency | 70-500 ms per request | multiple sources |
| Also on OpenRouter | VERIFIED by a live probe 2026-09-25 with our existing `OPENROUTER_API_KEY`: `POST https://openrouter.ai/api/alpha/decisions`, body `{model, state, questions}` identical to TypeSafe's, model `typesafe/jev-1.13` or alias `~typesafe/jev-latest`, listed under `GET /api/v1/models?output_modalities=decisions`. Pricing $0.042/M input, output $0. **Context window 32,000 tokens.** Response carries `usage.cost` in USD (fits the metered ledger). Probe: 626 input tokens, 0.25 s, $0.000026, answers sensible (see 3a). No TypeSafe account or waitlist needed. Chat-completions SDKs cannot call it. | live probe; openrouter.ai/docs/guides/community/jev |
| Accuracy | Banking77, 77 intents: Jev 81.0% vs Claude Opus 5 84.4%. Trails frontier by 3-6 points on intent tasks. | openrouter.ai blog, DataCamp |
| Cascade result | Jev at confidence >= 0.90 answers 76% of traffic, rest to Opus: 84.0% accuracy at $0.69/1k vs $2.42/1k | openrouter.ai blog |
| Errors | 401 bad key, 422 validation, 429/529 rate limit (backoff) | docs.typesafe.ai/api |

Hard properties that decide fit:

- Questions in one request are evaluated INDEPENDENTLY against the same state. Answer A is never
  context for answer B. Anything with a cross-field constraint ("exactly 3, all strategies differ")
  has to be enforced in code afterwards.
- Only bounded answer spaces. No names, no descriptions, no effect trees, no recursion.
- No rationale. Debugging a wrong decision means looking at the probability map only.
- Undocumented: max state size, max questions per request, rate limits, free tier. Must measure.
- Open reconstructions exist (HiGal/parallel-constrained-decoding, OpenJev, jevfire). All need a
  local GPU or logprob access; the droplet has neither, so they are not an option for the hosted route.

## 2. Where our pipeline actually spends on enums

Inventory taken 2026-09-25 (see the agent notes summarised here; all paths under `BLANKthespire/`).

- Every LLM enum choice today is free-form JSON at most pinned to `json_object`, validated by
  Python, one repair call, then drop/abort. No structured output anywhere; `contract.py` notes the
  card schema is recursive.
- The cost is not the CHOOSING of enum values. It is PASTING the allowed sets so the generator can
  write valid JSON:
  - Card system prompt: ~115k chars (~28k tokens), 51% `VOCABULARY.md`, 39% `card.schema.json`.
    Sent once per card, ~34 cards plus repairs per triad forge. Nothing prunes it by class kind or
    by card brief.
  - Blueprint prompt: ~104k chars (~26k tokens), pastes `VOCABULARY.md` in full. The rule-0.9 tests
    in `generation/tests/test_harness_v2.py` record that the vocab paste is 79% of prompt growth
    and that kind-gating it is "scoped, NOT built". The recorded hazard: the blueprint is where the
    class kind is CHOSEN, so gating there hides options the model has not picked yet.
  - `FORGE_ESTIMATE_FALLBACK`: 53 calls, 1.37M input tokens (720k cached), 28k output per forge.
- Places where an enum choice is made badly or silently today:
  - `featured_resonance` (36-entry menu) and `coverage_nominations` (7/14/7/10/4/13 menus):
    unknown ids are filtered in code and never re-asked.
  - Relic intent "pick exactly ONE form": the chosen form is never checked.
  - Map stage: unknown `archetype_id` is not rejected, just scored down.
  - Card stage never checks `type`/`rarity` against the blueprint brief (code bug, not a Jev job).
  - `validator.vocab_misses` logs "is not one of" enum misses as vocab demand with no triage
    between typo, near-synonym, and genuinely missing op.

## 3. Fit verdict

Jev cannot touch the generative core (effect trees, names, text, blueprint composition). It fits
the pipeline in exactly one cost-relevant slot and several cheap quality slots.

### 3a. The one cost lever: card-stage vocabulary gating (recommended)

Ryan's framing (2026-09-25): "Jev looks at the proposed card design and the archetypes, then feeds
exactly what data is needed to code the card into a prompt." Jev does not design; it reads the
brief and picks which rulebook families the designer gets.

Measured on 576 real-model cards on disk (scratch/_class_gen minus fake-offline, plus the exemplar
pool): median card uses 2 ops; 40% use only basic ops + statuses; triggers 28%, conditions 21%,
scaling 17%, orbs ~7%, custom status ~7%, forge ~4%, summons ~3%; 6 of 41 ops never used. The
potion section (~850 tokens) never applies to a card. Script: scratchpad `section_usage.py`
(re-create under `generation/tools/` in Phase 0).

Two tiers of gating, in order:
1. **Class-kind gating, deterministic, no model.** The blueprint says whether the class owns orb
   slots, a status pool, a summon pool, or forge. Drop those sections and schema branches for classes
   that lack them. ~3-4k tokens off every card call. This is the "scoped, NOT built" lever from the
   rule-0.9 note, moved to the card stage where it is safe.
2. **Per-card gating via Jev (or the heuristic that beats it).** Triggers, conditions, scaling, pile
   ops. ~8k more off the simple 40% of cards. Coverage directives in the brief force a family on.

At card time the class kind and the per-card brief are already fixed, so the blueprint-stage
hazard does not apply. The decision "which VOCABULARY.md sections and which schema subsets does
THIS card need" is a bounded, per-card, read-it-out-of-the-brief classification. That is Jev's
shape.

Design sketch:

Probe result (2026-09-25, brief "power, uncommon, temper: whenever you retain a card, gain 3 block"):
needs_triggers 0.75, needs_conditions 0.19, needs_scaling 0.13, needs_orbs 0.11, primary family
block 0.84 / trigger 0.13. Correct on the one that matters (triggers) and below a 0.15 threshold on
the three it should exclude. One data point, not a measurement.

1. One Jev request per BATCH of cards, `state` = a class summary + the briefs. The OpenRouter window
   is 32k tokens, so do NOT send the whole blueprint prompt; the blueprint JSON plus ~10 briefs fits
   comfortably. Cost is negligible either way.
   Questions = for each pool card `i`, one `noul` per gateable section:
   `card_i.orbs`, `card_i.statuses`, `card_i.summons`, `card_i.triggers`, `card_i.conditions`,
   `card_i.scaling`, `card_i.pile_ops`, `card_i.balance`. Roughly 34 x 8 = 272 nouls in one call.
   (Undocumented max questions per request; fall back to one request per card if 422.)
2. Include a section when p >= 0.15. Bias toward inclusion; a missed section costs a repair call,
   an included section costs only tokens.
3. Assemble the card system prompt from the surviving sections plus the matching
   `card.schema.json` `$defs`. Keep a small fixed set of PROFILES (for example base, +triggers,
   +statuses, +orbs, +summons, full) rather than fully bespoke prompts so the system prompt still
   caches per profile. OpenRouter caching is real (~83% measured) and a per-card unique prompt
   would throw that away.
4. Repair call always uses the FULL prompt. So does any card whose first attempt failed with an
   enum miss on a gated section.
5. Env flag `BTS_VOCAB_GATE=off|jev|heuristic`. `heuristic` = keyword rules over the brief, as the
   no-vendor baseline that must be beaten.

Expected effect (to be measured, not promised): if the median card prompt drops from ~28k to
~12-15k tokens, that is roughly 450-550k fewer input tokens per forge, or about a third of the
1.37M estimate. On Ollama Cloud per-token pricing that is the largest single saving available.
On OpenRouter metered with caching the saving is smaller because the static half was already
cached; the profile approach preserves most of that.

Cost of Jev itself: under $0.005 per forge at list price. Negligible against $0.93/forge measured.

### 3b. Quality slots (cheap, no cost saving, worth doing after 3a proves the integration)

- Snap unknown `featured_resonance` ids and `coverage_nominations` to the nearest valid menu
  entry with a `choice` that includes `none_of_these`. Replaces silent drops.
- Validate the relic intent's chosen form with a `choice` over `relic_forms`.
- Triage `vocab_misses`: `choice` over existing ops plus `genuinely_new`. Separates real vocab
  gaps from typos and synonyms in the demand log.
- Post-card `noul`s as QA signals before spending a repair call: "name matches effect",
  "description reads as a Slay the Spire card", `score` 1-5 for perceived power. Log them next to
  `_relic_balance_errors`-style heuristics and compare before trusting them.
- Placeholder/stub answer detection on the OpenRouter route as a `noul`, alongside the existing
  string detector.

### 3c. Explicitly not a fit

- Picking the triad archetypes or strategies (cross-question constraints, creative composition).
- Anything in the card body, blueprint, relic, potion, or art prompts.
- Replacing the validator. Jev is a prior, the jsonschema check stays the truth.
- Model-tier routing per card ("simple brief -> gemma4"). Possible, but it changes card quality,
  not just cost, and there is no quality metric yet to gate it on. Revisit after 3a.

## 4. Phased plan

### Phase 0: measure before building (about 1 day, no product code)

1. DONE 2026-09-25: OpenRouter exposes the Decisions API to our existing key (see section 1). No
   TypeSafe account needed. Still unknown: rate limits and max questions per request; find both by
   pushing the batch size in step 3. Add `~typesafe/jev-latest` to `MODEL_PRICES` in `web/app.py`
   (or rely on `usage.cost`) so the ledger prices it.
2. Build the ground truth offline from past forges: for every forged card in the droplet DB and
   `btsgen/data/exemplar_pool.json`, compute the set of VOCABULARY sections its final JSON actually
   used (walk the effect tree, map each op/trigger/when.kind/scale/status to its section).
3. Run three predictors from the BRIEF ONLY (card role, type, rarity, pitch, plus the blueprint
   summary): Jev nouls, a keyword heuristic, gemma4:31b with `reasoning_effort: low` returning a
   JSON bool map. Score per-section recall and the resulting prompt size at thresholds 0.10,
   0.15, 0.25.
4. Gate to proceed: recall >= 97% per section at a threshold that still cuts the median card prompt
   by >= 40%. If the heuristic already meets the gate, ship the heuristic and skip Jev for 3a.
   Script lives in `generation/tools/`, results appended to this doc.

### Phase 0 RESULTS (2026-09-25, both scripts in `generation/tools/`, caches in `generation/scratch/`)

Ground truth: 576 real-model cards (glm-5.2/5.3, claude-opus-4-8) in `scratch/_class_gen` with their
brief line. Truth = what the FINISHED card used, which over-counts "needed": the model often adds a
draw, a gate, or a trigger the brief never asked for. Most listed "misses" are those embellishments.

**0a. Section gating** (`tools/jev_gate_eval.py`; 7 families, 11.1k gateable tokens per card):

| Predictor | Cards with every needed family | Avg tokens saved | triggers / conditions / scaling recall |
|---|---|---|---|
| keyword heuristic | 94.1% | 8,325 | 95 / 82 / 99 |
| Jev >= 0.15 | 94.6% | 6,854 | 98 / 86 / 96 |
| Jev >= 0.05 | 98.6% | 1,691 | 100 / 93 / 100 |
| **heuristic OR Jev >= 0.15** | **96.7%** | **6,488** | 99 / 88 / 99 |

Jev and the regex are peers here; the union is best. Jev cost for all 576: $0.0126 in 12 calls
(336 questions per call worked, no 422, no 429). Per forge: one call, ~$0.001.

**0b. Per-op gating** (`tools/jev_op_eval.py`; 38 ops gated, damage/block/apply_status always on,
~268 tokens per op row = vocab row + schema branch; question text = the op's own VOCABULARY row):

| Predictor | Cards with every needed op | Ops kept of 38 | Avg tokens saved |
|---|---|---|---|
| Jev >= 0.05 | 92.5% | 7.0 | 8,316 |
| top-10 ops by frequency (no model) | 81.1% | 10 | 7,516 |
| top-20 ops by frequency | 95.3% | 20 | 4,832 |
| **Jev >= 0.05 OR top-8** | **97.9%** | 11.6 | **7,082** |
| Jev >= 0.05 OR top-10 | 99.0% | 13.5 | 6,577 |

Weakest ops for Jev: draw (81%, mostly embellishments), forge (76%), summon helpers (n<7). Cost for all
576: $0.115 (the op rows ride in every question; 456 questions per call worked). Per forge ~$0.007.

**Decision gate check.** Section + per-op gating together save roughly 13-14k of the ~28k card prompt,
about 48%, at ~95% of cards needing no repair (0.967 x 0.979). That clears the 40% cut. The 97% recall
bar is met per family for triggers and scaling, missed for conditions (88%) where nearly every miss is
a gate the model invented. Conclusion: BUILD Phase 1, as heuristic + Jev union, with Jev optional behind
a flag so the A/B can measure its marginal value against the heuristic alone.

### Phase 0c: offline quality A/B, full vs gated prompt (2026-09-25, `tools/gate_ab.py`)

Paired design on 40 real briefs (seed 7, stratified for triggers/conditions/scaling), same model and
settings as the production `cards` role on the OpenRouter tier (z-ai/glm-5.3, t=0.3, json_object,
reasoning low), same validator + repair loop via `pipeline.generate_card`. Arm A = full system prompt
(112.5k chars). Arm B = same text with unselected vocab sections and op rows cut, schema whole
(avg 76.6k chars, 32% smaller). Quarantine redirected to `scratch/gate_ab/`, report in `report.md`.

| Metric | A full | B gated |
|---|---|---|
| card produced (after <=1 repair) | 100% | 100% |
| valid on first attempt | 90% | 85% |
| type / rarity / cost match the brief | 100 / 100 / 95% | 100 / 100 / 97.5% |
| over power ceiling after repair | 0% | 0% |
| avg ops per card / distinct ops across the set | 2.15 / 16 | 2.20 / 16 |
| avg input tokens per card (incl. repairs) | 37.4k | 26.8k |
| LLM judge, gpt-5.4-mini, position-swapped x2 | A 6, B 6, tie 28; fidelity 3.91 vs 3.95 |
| Jev judge (choice + fidelity score) | A 10, B 11, tie 19; fidelity 3.06 vs 2.96 |

The first-attempt failures: A had 4, B had 6, and 4 are the SAME briefs in both arms (custom orb
"ember", custom status "Festering", summon ops) which fail only because the offline validator has no
class scope loaded. B's two extras: one JSON missing required fields (a model hiccup), one more
class-scope custom status. **No failure was caused by a pruned section or op row.**

Conclusion: quality parity on every measure; the gated arm is not worse. Note the cache column: A
averaged 18.7k cached tokens per card, B only 2.7k, because B's prompt varied per brief and was NOT
prefix-ordered. That is the caching concern shown in data and why the layout below is required.
Cost of the run: ~2.6M input tokens on OpenRouter, ~$3.

### Cache-safe layout (the fix for the prompt-caching concern, 2026-09-25)

Facts from the droplet ledger (`forge_usage`, grouped by model) and the provider price lists:

| Route / model | Input $/M | Cached input $/M | Cached share of input tokens observed |
|---|---|---|---|
| OpenRouter z-ai/glm-5.3 | 1.40 | 0.26 | 79% (39 rows, 2026-09-18..24) |
| OpenRouter z-ai/glm-5.2 | 0.65 | 0.12 | 74% |
| Ollama Cloud glm-5.3 (primary) | list 1.40-ish | 0.26 (pricing page "Cached input") | 92% (2026-09-26 rows) |
| Ollama Cloud gemma4 | 0.14 | 0.05 | 0-6% (brainstorm prompts differ per call) |

Both routes do automatic PREFIX caching and bill cache hits at ~19% of the input rate. So a cached
token is nearly free and a fresh token is expensive, which flips the arithmetic per card call
(~28.5k input today):

| Layout | Fresh tokens | Cached tokens | Cost per card call (glm-5.3) |
|---|---|---|---|
| today, 80% cached | 5.7k | 22.8k | ~$0.0139 |
| today, 92% cached | 2.3k | 26.2k | ~$0.0100 |
| naive gating, bespoke prompt per card (cache lost) | 14.5k | 0 | ~$0.0203  **WORSE** |
| prefix-ordered gating (below) | ~3k | ~14k | ~$0.0078 |

Over ~40 card calls per forge that is roughly $0.40-0.56 today vs ~$0.31 gated: about a quarter of the
$0.93 measured forge cost. The raw 48% token cut becomes a ~25-45% money cut because the tokens being
removed were mostly the cheap cached ones.

Rules that make gating cache-safe:
1. **Static core first, byte-identical for every card in the forge**: identity, task rules, the always-on
   vocab sections (core op rows, statuses, targeting, card shape, rarity), the core schema, the authored
   pool catalog, feedback. All of these are already stable within a forge (the pool catalog reads
   `mod/content/cards`, not the forge's own cards).
2. **Gated add-ons AFTER the core, in one canonical order**, most-frequently-included first (triggers,
   then conditions, scaling, extra op rows, class-kind sections). Cards that share the leading add-ons then
   share a longer cached prefix; the per-card brief stays in the user message where it always was.
3. **"Full prompt" for repairs = core + every add-on in the same canonical order**, so a repair still
   hits the core cache instead of paying for 28k fresh tokens.
4. **Schema handling in two steps.** Phase 1a keeps `card.schema.json` whole inside the cached core and
   gates only the prose (vocab sections + op rows): smaller saving, no schema surgery. Phase 1b renders the
   schema per op as self-contained fragments so each op's field spec can ride in the tail with its row.
5. **Anthropic BYOK path**: explicit `cache_control` breakpoints, one after the core block and one at the
   end of the tail (the API allows four); today there is a single breakpoint on the whole system prompt.
6. Verify with the ledger, not by eye: `cached_tokens / input_tokens` per model must stay >= today's
   share after the A/B, and metered cost per forge must fall. If the cached share drops, the layout
   broke rule 1 somewhere (something in the core varies per card).

### Phase 1: gated card prompt behind a flag (2-3 days)

- `contract.py`: split `VOCABULARY.md` and `card.schema.json` into named sections/profiles;
  `system_prompt(profile=...)`.
- `pipeline.generate_card`: profile on attempt 1, full prompt on repair.
- New `btsgen/gate.py` with the Jev client, the heuristic, and the `off` path. Jev failures
  (429/529/timeout) degrade to `full`, never block a forge.
- Usage ledger: tag Jev calls as role `gate` so `web/forge.py` and `ForgeUsage` account for them.
- Tests: extend the rule-0.9 budget tests with a card-prompt reading per profile; a test that
  every op in `card.schema.json` maps to exactly one profile section.
- A/B on the droplet the same way as the 2026-09-18 route A/B: three cowboy forges per arm,
  metered cost from the ledger, validator failure and repair counts, and a manual read of the
  cards for regressions.

### Phase 1a BUILT (2026-09-25, uncommitted working tree)

- `generation/btsgen/gate.py`: modes `off` (default, byte-identical prompt) / `heuristic` / `jev` (union, the Phase 0
  winner). Cache-safe layout: core = head + always-on vocab + whole schema + ladder/reprint/feedback/task; tail =
  `# VOCABULARY ADD-ONS` with triggers, conditions, scaling, forge, then extra op rows, always in that order.
  Repairs and Jev failures send core + every add-on. Decisions memoized per brief so failover tiers don't re-ask.
- Class-kind tier: `class_forge` now always binds the class scope with `kinds` (= `_declared_kinds(bp)`); an owned
  kind's section and op rows ride the core, an unowned kind's are dropped even from the full prompt. The
  signature-potion section is always dropped. With no kinds (bare card call) those families are gated per card.
- Core op rows: damage, block, apply_status, add_trigger, draw, retain, gain_energy, exhaust, heal, forge, lose_hp.
  Gateable rows are an explicit list; a NEW op defaults to the core until measured.
- Wiring: `contract.card_prompt_gate`, both generators (`first_attempt` gated, `repair` full; Anthropic gets two
  cache breakpoints), `_FailoverGenerator.last_gate`, `PipelineResult.gate` + a log line + `vocab_gate` in the
  quarantine meta, a per-forge `vocab gate [...]` note, Jev usage booked as role `gate` (ollama_mix `_tagged` no
  longer overwrites an explicit `_role`), `typesafe/jev-1.13` in `MODEL_PRICES`.
- Tests: `generation/tests/test_vocab_gate.py` (11). Suite: 522 pass; the 3 failures (phase AQ/AS/BA checks) were
  red before this change. Web: 225 pass.

### Phase 1 A/B RESULTS (2026-09-25, `tools/gate_forge_ab.py`, local, not the droplet)

Nine whole forges of "a cowboy gunslinger" through the website's own hosted path (`forge_to_bundle`, staged, triad,
harness v2), route pinned to metered OpenRouter glm-5.3, three per arm, all nine run in parallel. Cost ~$6.7.

| arm | forges ok | $ / forge | cards-role $ | Jev $ | card input tokens | cached share | card calls | cards ok / failed | prompt vs full layout |
|---|---|---|---|---|---|---|---|---|---|
| off | 3/3 | 0.805 | 0.749 | 0 | 1,312,662 | 46% | 41.3 | 98 / 0 | - |
| heuristic | 3/3 | 0.703 | 0.644 | 0 | 964,678 | 32% | 40.7 | 98 / 0 | 82% |
| jev | 3/3 | 0.739 | 0.686 | 0.006 | 1,063,979 | 43% | 44.3 | 100 / 0 | 81% |

Reading it:
- Quality held: every card in every forge was produced, no skips, repair counts within noise (first-try valid:
  heuristic 86/98, jev 85/100; one jev forge had 11 repairs, the other two 3 and 1).
- The cut is smaller than Phase 0's 48% because 1a keeps `card.schema.json` (~44.5k chars) whole in the core: the
  core alone is ~67% of the full layout, so a gated card lands at ~80%. Input tokens fell 19-27%, money 8-13%.
- Jev added nothing over the heuristic here. Its edge in Phase 0 was per-OP picks, and op rows are small next to
  the schema. The families Jev adds (triggers 29/34 vs 12/34) cost tokens without fixing a failure.
- The cached share is noisy (the off arm's 46% is far under the ledger's 79%, likely nine concurrent forges spread
  over upstream providers). Fresh tokens still fell in both gated arms. Re-check rule 6 on the droplet ledger.
- n=3 per arm: the direction is solid, the exact percentages are not.

Recommendation: ship `heuristic` first (no vendor, measured parity, the bigger saving), keep `jev` for Phase 1b.
Phase 1b (schema split into per-op fragments riding the tail with their rows) is where the remaining ~44k-char
lever is, and where Jev's per-op recall would matter. Deploy = commit, `deploy.sh`, set `BTS_VOCAB_GATE=heuristic`
in the droplet env, then compare `forge_usage` cards rows for a week against the prior week.

### Phase 1b BUILT (2026-09-26): the schema split

- `BTS_VOCAB_GATE_SCHEMA=split` (default whenever the gate is on; `whole` = Phase 1a exactly). The core keeps the
  card-level fields, the core ops' enum values + prose + fields + rules, and anything it cannot attribute. Each gated
  element moves to ONE `## Schema additions` JSON block at the end of the tail (`more_op_values`,
  `notes_on_those_ops`, `more_effect_fields`, `more_effect_rules`, `more_defs`), built only from the units the
  card's decision included. Units = gated op names + `fam:<family>` (namespaced: the Forge family vs the `forge` op).
  The op prose is cut at each op's own `'op' (` lead-in. Lossless: core + every addition = card.schema.json minus
  the unowned class kinds (tested for 4 kind sets). The validator still checks the complete schema.
- `add_trigger` joins the triggers family under split, so `triggerEffect` (~8.3k chars) rides the tail.
- `when` + the `condition` def STAY in the core (see the A/B below).
- Sizes, normal class (chars): original 112.5k; 1a core 64.5k; 1b core 30.1k; 1b plain-attack card 53.1k (47%
  of the original); 1b trigger card 73.7k; 1b full layout 91.4k.
- Also: repaired cards now record `first_attempt_errors` in their quarantine meta (the only record of WHY).

### Phase 1b A/B (2026-09-26, unpaired, 3 forges per arm, fresh gate-off baseline run alongside)

| arm | $ / forge | card input tokens | cards ok / failed | card calls | repaired cards |
|---|---|---|---|---|---|
| off | 0.915 | 1,336,094 | 100 / 1 | 41.7 | 6 of 103 |
| heuristic (split) | 0.636 | 962,845 | 99 / 0 | 49.3 | 23 of 107 |
| jev (split) | 0.768 | 948,059 | 98 / 2 | 47.0 | 18 of 106 |

Money fell 30% (heuristic) / 16% (jev), but repairs roughly tripled. Diagnosis:
- Gate misses: 9 of the heuristic arm's 23 repaired cards used something their gated prompt lacked — mostly a
  `when` gate (the 1b split had moved the `when` schema out; in 1a the schema alone let the model write a valid
  gate the prose never showed) and card-latent "on-discard fuel" triggers the keyword rule missed.
  FIXED: `when` + `condition` def back in the core (+~4.5k chars); triggers keywords widened (recall on the 576
  Phase 0 cards 93.9% -> 97.0%, included on 36% of cards instead of 32%).
- Not the gate: two diagnostic reruns captured the real first-attempt errors: 5 of 9 were custom orb names written
  as slugs (`'lead_slug'` for the pool's "Lead Slug") on ORB classes, plus a model `payload`/`target` slip and a
  no-JSON answer. The unpaired design confounds this: each forge rolls its own class, and orb/hybrid classes landed
  only in gated arms. Hence the paired design below.

### Paired A/B RESULTS (2026-09-26, with the when/trigger fixes)

`tools/gate_forge_ab.py capture` saves the staged front end's blueprint and stops before any card; `paired` replays
each saved blueprint into every arm, so all arms design cards for the byte-identical class and briefs. Four
blueprints (`scratch/gate_forge_ab/bp/`): summon (beastmaster), status (cowboy), status (plague doctor), normal
(sea witch). 4 x 3 = 12 card stages on metered OpenRouter glm-5.3, all in parallel. (A first attempt on 2026-09-25
died on HTTP 402 `in_flight_budget_exhausted` with ~$7 left; rerun after the top-up.)

| arm | cards ok / failed | repaired cards | card input tokens / forge | cached share | $ / forge (card stage) |
|---|---|---|---|---|---|
| off | 133 / 0 | 2 of 150 | 1,287,283 | 53% | 0.556 |
| heuristic (split) | 133 / 0 | 8 of 147 | 834,683 (-35%) | 37% | 0.484 (-13%) |
| jev (split) | 133 / 0 | 5 of 148 | 812,862 (-37%) | 53% | 0.325 (-42%) |

Per blueprint the token cut is consistent (heuristic -28..-40%, jev -21..-44%) and every blueprint produced every
card in every arm.

Repair causes (from the new `first_attempt_errors` meta): none traced to something the gate cut. They are the model
slips that also hit the off arm (a stray `target` on a flag op, two effects declaring the same value, `hits` +
`scale`, a custom status name in a `when`, `random_enemy` in a trigger payload, a PLACEHOLDER upgrade) plus three
"upgrade may only APPEND a keyword; got 'draw'" — a rule in the always-on Card shape section.

Money is noisier than tokens: the cached share swings with OpenRouter's upstream routing (the heuristic arm's 37%
is the outlier; its tail is if anything MORE uniform than jev's). Read tokens as the stable effect, money as
"between -13% and -42% at list rates"; the droplet's forge_usage ledger over a week is the real number.

Jev vs heuristic after 1b: ~2.6% fewer input tokens and 3 fewer repairs of ~148 — marginal, and it adds a vendor
call (degrades to the full prompt on failure, ~$0.007/forge).

**Recommendation: ship `BTS_VOCAB_GATE=heuristic` (split schema, the default).** No vendor dependency, measured
card parity, -35% card input tokens. Keep `jev` as the switch to flip if the droplet ledger shows a real cache or
repair difference. Deploy: commit, `deploy.sh`, set the env on the droplet, compare a week of `forge_usage` cards
rows before/after (cached share per rule 6).

### Phase 2: quality slots from 3b (1-2 days, only if Phase 1 ships)

Each is a small contract change plus a validator hook. Do nomination snapping first because it
directly feeds the coverage machinery already built in W0.5.

## 4b. LATER, unrelated to Jev: an `on_retain` trigger (Ryan, 2026-09-25: "I kind of like that idea")

Found while probing: the vocabulary has no retain EVENT. Retain is a keyword flag; the engine snapshots
the pre-draw hand at turn start (`HandStateTracker.SnapshotPreDraw`, Harmony on `Hook.BeforeHandDraw`)
to feed `scale: cards_retained` and `when: retained_last_turn`. "Whenever you retain a card" is therefore
only expressible as turn_start + cards_retained scale, or a retained_last_turn gate.

Proposed scope, one vocab phase (v56):
- **Card-latent `on_retain` trigger**, same pattern as `on_discard` (the card carries the trigger; the
  payload fires when the event happens to THIS card, not on play). Fire point: right after the pre-draw
  snapshot, walk the held-over hand and run each carrying card's payload against itself. Not the early
  turn-start hook (the lethal-tick NRE recorded in memory) and not the turn-end flush (retained cards never
  pass through it).
- **A self-empower op** so the Watcher shapes exist: Windmill Strike (+damage per retain), Perseverance
  (+block per retain), Sands of Time (`cost_shift` already covers the cost drop). Today only `blade_empower`
  (blade-only) exists; either widen it or add `empower_self` with damage / block variants, combat-scoped.
- Touch points, going by on_discard (~30 refs): C# trigger sets + text renderer ("Whenever you retain
  this card, …"), VOCABULARY.md Triggers row, card.schema.json enum + description, btsgen validator,
  coverage `REACTIVE_MENU_V2`, a DESIGN_HEURISTICS archetype-note (payload sizing like countdown_ripen),
  `VOCAB_VERSION` 55 -> 56 (mod zip ships BEFORE the web deploy), AutoSlay smoke with a tester card,
  localization-error grep on the card text.
- Demand: none yet. No real forge or gap log has reached for `on_retain` (grepped 2026-09-25). Give the
  retain-payoff archetype the new trigger in its blueprint pitch so it gets exercised.

## 5. Risks and open questions

- Early access: availability, rate limits, and price stability are all unproven. Everything degrades
  to the full prompt, so an outage costs money, not forges.
- Domain jargon: Jev's published numbers are on intent datasets, not on Slay the Spire mechanics.
  Phase 0 is the only honest answer.
- Cache interaction: bespoke per-card prompts could cost more on OpenRouter than the full cached
  prompt saves. Profiles, not bespoke prompts.
- BYOK: the gate runs on our Jev key regardless of whose generation key is used. At well under a
  cent per forge that is acceptable; note it in the BYOK policy doc when built.
- Card `type`/`rarity` vs brief mismatch is a separate code bug found during this inventory. Fix
  it in the validator independently of Jev.

## 6. Sources

- https://docs.typesafe.ai/api and https://docs.typesafe.ai/sdk/python.md
- https://openrouter.ai/blog/insights/jev-vs-claude-opus-5-classification/
- https://www.datacamp.com/blog/system-one-models-jev
- https://github.com/AbdelStark/awesome-typesafe-jev
- https://github.com/HiGal/parallel-constrained-decoding
- https://github.com/zhangcy122/OpenJev
- https://gist.github.com/pjburnhill/adf8d28efcad9df037bfdece178ef965
