# Vocabulary Gap Remediation Plan

**Written 2026-09-09 from a three-agent audit of the live vocabulary (v39, Phase AI) against the C# engine,
the planning docs' deferred items, and the generation-side contracts/coverage.** Every issue the audit
surfaced has a fix or a mitigation below. The plan is ordered so that the cheapest, highest-leverage work
(prompt and doc text that is actively suppressing supported features) ships first, and the deepest engine
work ships last, each as its own lockstep phase.

**Scout caveat:** file:line references came from an automated audit on 2026-09-09. **Re-grep the symbol
before trusting a line number** — names are authoritative, line numbers are hints.

**STATUS (2026-09-09): Wave 0 EXECUTED** — all eleven items W0.1–W0.11 landed (uncommitted at time of writing).
Tests: `tests/test_wave0_docs.py`, `tests/test_wave0_prompts.py`, `tests/test_archetypes.py`,
`tests/test_exemplars.py`; full suite 365 passed. Notes from execution: metallicize is STS2 Plating and DECAYS
one stack per turn (verified against the decompiled `PlatingPower.cs`; the vocabulary row now says so); the
exemplar pool grew 46 → 82; `battle_smith` deliberately carries no `mechanic_kind:"forge"` (its ops are base
vocab); gap #48 is `planned (verify-then-close)`, not done — it still needs the AutoSlay run its entry specifies.
Run tests with `uv run python -m pytest` from `generation/` — bare `uv run pytest` can resolve a different
checkout's `btsgen`.

**STATUS (2026-09-09): Phase AJ EXECUTED (vocab v40)** — all six items landed in lockstep (`ForgedCards.cs`
Validate/ValidateTrigger/Describe + `OrbNameError`, `ForgedCharacters.cs` import passes the class's custom orb names,
`EffectRunner`/`OrbRunner` warn + skip an unknown orb, `card.schema.json`, `VOCABULARY.md`, `cardgen.py`,
`validator.py`, `bts1.py`). Verify-first finding: `random_enemy` needs NO runtime change — BaseLib's `CardAttack`
already rolls a random enemy per hit (`TargetingRandomOpponents`) and `Apply<T>`/`GetTargets` one random enemy per
status effect — so the contract rule is "no `when:target_has_status` / `scale:target_debuff_count` on a random_enemy
card" (each effect rolls independently). Tests: `tests/test_phase_aj.py` (22 checks); suite 367 passed. C# build
0 errors (`~/.dotnet/dotnet.exe build mod/BlankTheSpire.csproj -c Debug` — the Program Files dotnet is runtime-only).
AutoSlay GAPTESTAJ2 (tester `generation/scratch/gaptest-aj/build_tester.py`, staged into slot 04, Act 2 floor 27):
**206 `[AJ]` tags** (random_enemy damage x1/x3/x5, random_enemy weak/vulnerable, trigger channel_orb 'ember' x27,
unknown-orb warn+skip x22) · **0 mod exceptions** · tool verdict = the documented base-game map-nav watchdog at a
shop ("There is no item to purchase"), not mod-attributable. **Incidental fix (pre-existing, also in the 2026-08-19
log):** every custom-orb channel threw `Expected a GodotObject but was Nil` from `NOrb.UpdateVisuals` because the
game now wraps the sprite's `SpineSkeleton` child in a MegaSprite and the procedural circle had none —
`ForgedOrb.CreateCustomSprite` now instantiates the Lightning orb's real spine scene tinted to the orb's hue, and
borrows Lightning's channel/passive/evoke sound events (64 "No loader found" errors per run gone). GAPTESTAJ1 (before
that fix): 138 tags, 32 of those exceptions; GAPTESTAJ2 (after): 0.

**STATUS (2026-09-09): Phase AJ-b EXECUTED (no vocab bump)** — `btsgen.paths` now DEFAULTS to the mod contract
(card + new `mod/contract/relic.schema.json` + both vocabularies + statuses + `mod/content/cards`); every contract
attr has a `BTSGEN_*` override, `paths.prototype_overrides()` / `use_prototype_contract()` reach the archived
prototype, and `point_btsgen_at_mod_contract()` is a no-op safety net. `_STATUS_WEIGHT` is keyed to all 18 mod
statuses (Intangible 8, Ritual/Strength/Barricade 4, Dexterity/Metallicize/Buffer/Focus 3, Vulnerable/Thorns/Regen/
Artifact/Blur/temp_strength 2, Weak/Frail/temp_dexterity 1.5, Poison 1.2). The prototype composites are out of
`_BUILD_AROUND_OPS` and live only in `_LEGACY_PROTOTYPE_OPS`, consulted when `_mod_contract` is False; the legacy
relic/character modules + CLIs carry a LEGACY banner and the two generate CLIs warn. **Deviations from the plan
text, deliberately:** (a) the prototype ops are GATED, not deleted — deleting them retires the prototype-era
validator suite (test_validator / test_relic_validator / test_character_pipeline / test_pipeline_balance_repair),
which is a separate decision; those four tests now pin the prototype contract themselves for standalone runs;
(b) the legacy CLIs are deprecated, not rewired onto `class_forge` (they generate a single relic/character, which
the mod has no concept of). Tests: `tests/test_phase_ajb.py`; `test_contract_binding` updated (env-clean default =
mod); suite 372 passed; every test file also runs standalone.

**STATUS (2026-09-09): Wave 2 EXECUTED (no vocab bump)** — all four items landed. **W2.1** `census.py` now counts
multi-hit (`hits` ≥ 2 on damage / summon_attack — and a multi-hit card is no longer "plain"), the four keywords
(exhaust / retain / innate / ethereal, with `multi_hit` joining them as a keyword KIND), `apply_status_custom`
statuses, `buff_summon` statuses (default strength), the poison / frail / focus SPECIALTY bucket (neither generic nor
exotic), `tags`, `upgrade.cost`, `once_per_turn`, `ripen` amounts and targeted trigger payloads; `format_report` prints
every counter (fixed baseline columns first, then the full tally). **W2.2** `coverage.py`: `WHEN_MENU_V2` +
retained_last_turn / draw_pile_empty / hp_lost_ge / target_has_status; `WHEN_MENU_KIND` (forged_ge → forge, dark_ge /
light_ge / centered → balance, orbs_match / orb_count_ge → orb) gated by the class's kind set
(`harness_v2.pool_kind`, the blueprint kind ∪ the selected archetypes' `mechanic_kind`); `SCALE_MENU` (5 sources) +
`SCALE_MENU_KIND` (tag_cards_owned → tags, forged → forge) replace the one fixed scale directive; `EXOTIC_NOMINATE_ONLY`
(ritual / barricade / intangible — never dealt off the shuffle, reachable by nomination); `KEYWORD_MENU` (retain /
innate / ethereal / hits) with `MIN_KEYWORD_KINDS = 2`; `NOMINATION_CATEGORIES` += scale / keyword; a `CENSUS_DETECTOR`
per menu key; the blueprint's nomination ask names every category and the class-kind keys. **Deviation, deliberate:**
the widened menus and the keyword quota ride the creative-harness-v2 path only — the v1 menus / quotas stay
byte-for-byte because `BTS_HARNESS_V2` is the live A/B and the control arm must not move. **W2.3** `featured.py`:
`FEATURED_CLASS_KIND` (orb / status / summon / forge / balance / discard / transform — 12 entries), `roll_class_kind`
(one pick per class, seeded on the concept with its own salt, kind-order-proof), `Featured.carried_by` (`min_cards` = 3
for the custom-status spread, `detect_pool` for the scry + on_discard loop). The pick is dealt AFTER the blueprint (the
kind is only known then) and enforced by the coverage round like any featured miss. It is dealt on the triad path too:
the 2026-08-15 triad exclusion was about the wild slot landing off-theme subsystems, and these entries only exist for
the class's own kind (`test_triad` updated: no base-menu ids under triad, exactly one class-kind id on an orb fake).
**W2.4** `class_forge.py`: blueprint `max_energy` (2..4; assembly default 3) and `color` (a hue 0-359, a palette name
crimson/amber/gold/emerald/teal/azure/violet/magenta, `{hue}` or `{h,s,v}` — emitted as the importer's `{h,s,v}`;
omitted → the engine's per-slot hue), `max_hp` 55..100, `orb_slots` ≤ 5, summon `max_hp` ≤ 100 (the C# ranges stay the
hard ceiling); the prompt grew two format fields + one rule line; the legacy `character_validator` bands follow.
Tests: W2 checks appended to `tests/test_census.py` (68), `test_coverage.py` (215), `test_featured.py` (153),
`test_forge.py` (88); suite **380 passed**; four v2 fake forges verified end-to-end (forge → blade_recall, summon →
summon_drill, orb → orb_focus_power, normal → none; colors + energy in the bundle). NOT in this wave: the cross-cutting
"vocab drift" / "prompt-vs-vocab" tests.

---

## 0. Ground rules

These are the `VOCAB_EXPANSION_4_PLAN.md` §0 rules; the load-bearing ones repeated so this file stands alone.

- **0.1 Lockstep or nothing.** Any vocab change ships across ALL of: `mod/BlankTheSpireCode/` (`ForgedCards.cs`
  SupportedOps / TriggerOps / AmountOps / Validate / ValidateTrigger / Describe / TriggerFragment / VocabVersion ·
  `EffectRunner.cs` · `TriggerRunner.cs` · `DataCard.cs` · `CardSpec.cs` · `Conditions.cs`) +
  `mod/contract/card.schema.json` + `mod/contract/VOCABULARY.md` + `generation/btsgen/` (`cardgen.py` describe
  byte-match · `validator.py` · `census.py` · `bts1.py` VOCAB_VERSION · `class_forge.py` blueprint · `featured.py`
  · `coverage.py` · `data/archetypes.json` · `data/exemplar_pool.json`) + `character_validator.py` when class-level
  rules change.
- **0.2 Describe text is a byte-match contract.** `cardgen.describe()` == `ForgedCards.Describe()` byte-for-byte.
- **0.3 AutoSlay validation is by godot.log tags.** Pass bar per run: ≥1 phase tag fired · 0 mod exceptions · no
  mod-attributable hang. Tag every new mechanic `[<PHASE>] ...`.
- **0.4 Deck-deletion / choice mechanics need an all-aggression tester.**
- **0.5 Choice UIs are AutoSlay-safe** via `AutoSlayCardSelector`; grep for `Auto-selected`.
- **0.6 STOP rules.** Verify-first step contradicts the spec → STOP that phase, write findings, move on.
- **0.7 Commit convention.** One commit per phase: `mod+forge: Phase <LETTER> — <mechanic> (vocab v<N>)`.
  Doc/prompt-only phases: `docs:` or `forge:` prefix, no vocab bump.
- **0.8 Vocab versions.** Assigned in build order starting at **v40**. Phase letters continue from **AJ**.
- **0.9 Prompt budget.** The blueprint prompt is tuned for 7B-class local models. Every prompt addition in this
  plan must be paid for by a removal of equal size or land as a one-line "menu" pointer, not a paragraph.
  Measure with the existing prompt-size assert in `tests/test_harness_v2.py` before and after.

### Standard commands

```powershell
# Generation-side phase test (each file is a standalone module, exit 0 = pass)
cd generation
uv run python -m tests.test_phase_aj

# Full generation suite
cd generation
Get-ChildItem tests/test_phase_*.py | ForEach-Object { uv run python -m ("tests." + $_.BaseName); if ($LASTEXITCODE -ne 0) { throw $_.BaseName } }
uv run pytest -q

# C# build (deploys to the game's mods folder via CopyToModsFolderOnBuild)
dotnet build mod/BlankTheSpire.csproj -c Debug
```

---

## Wave 0 — Text that suppresses supported features (no vocab bump; 1–2 days)

Everything in this wave is prose or data. It ships with `docs:` / `forge:` commits and needs no C# build.
It is first because it is the cheapest creative-range gain in the whole plan: the model is currently being
told that features it can use do not exist.

### W0.1 `DESIGN_HEURISTICS.md` — remove false negatives
- **Issue:** `relic_forms` note says there is no "whenever you lose HP" trigger (`:112-114`); `on_hp_lost` has
  existed since gap #9 (`RELIC_VOCABULARY.md:48`, `ForgedRelic.cs:134-143`). The RELIC FORMS menu (`:95-110`)
  omits `on_hp_lost`, `forge`, `channel_orb`, `summon`. The rarity ladder (`:41`) and reprint rule (`:51`) name
  prototype ops `multi / conditional / from_state / fuse`.
- **Fix:** delete the stale note; add a seventh form **"Bleed payoff"** (`on_hp_lost` → small buff/block) and a
  **"Class-kind boon"** line naming `forge` / `channel_orb` / `summon` hooks. Rewrite the rarity-ladder
  parenthetical to the mod's actual compositional tools: `when` gates, `scale`, `hits`, `add_trigger`, `add_card`,
  X-cost, `grow`, `transform_card`. Same substitution in `reprint_section`.
- **Test:** extend `tests/test_contract_binding.py`: assert no heuristic block contains `from_state`, `multi`,
  `fuse`, or the phrase "no \"whenever you lose HP\"".

### W0.2 `VOCABULARY.md` — stale and misleading lines
- **Issue A:** `:332` "Deeper build-around rares need ops not yet supported; for now make rares hit hard and wide"
  is prompt-injected and false.
  **Fix:** replace with two lines pointing rares at `add_trigger`, `when`-gated payoffs, `scale`, `transform_card`,
  and class-kind engines.
- **Issue B:** `on_discard` (`:232-235`) says it fires when "discarded by an effect"; the engine only fires it from
  the mod's own `discard`/`scry` ops (`EffectRunner.cs:439-441, 462-476`).
  **Fix:** add the caveat "(only THIS class's `discard`/`scry` — base-game relic/enemy discards do not fire it)"
  until Phase AU below lands, then remove.
- **Issue C:** `metallicize` (`:72`) is implemented as `PlatingPower` (`EffectRunner.cs:832`). Verify STS2 Plating
  semantics (does it decay when hit?). If it decays, reword the row; if not, add a comment in EffectRunner so the
  next reader doesn't re-audit it.
- **Issue D:** the `discard` row (`:35`) says "no card-selection UI" — the picker exists since Phase X/Z.
  **Fix:** leave until Phase AP (chosen discard) lands; then reword.
- **Test:** `tests/test_contract_binding.py` asserts the `:332` sentence is gone.

### W0.3 `RELIC_VOCABULARY.md` — defects
- **Issue:** truncated sentence "There is no" at `:51-52`; `summon` row (`:69`) says "Summon `amount` of your
  class's minion" (the old multi-pet wording; `amount` is HP now).
- **Fix:** finish the sentence ("There is no `combat_end` for losses; see `combat_end` for wins.") or delete it;
  reword `summon` to match `VOCABULARY.md:29`.
- **Test:** `tests/test_relic_validator.py` asserts the relic vocab text has no line ending in "There is no".

### W0.4 `class_forge.py` blueprint prompt — contradictions with the vocabulary
- **Issue A:** `:257-258` "no conditionals, no state-scaling, no card generation" — `when`, `scale`, `add_card`
  exist.
  **Fix:** replace with "no ops outside the list; but the list INCLUDES `when` gates, `scale` amounts,
  `add_trigger` engines, and `add_card` tokens — use them."
- **Issue B:** `:316` trigger payloads "NO targeted damage or enemy debuffs" — contradicts `VOCABULARY.md:238-242`.
  **Fix:** "payload may carry `target: enemy/all_enemies` on `damage` or an enemy debuff (Noxious Fumes /
  Combust)".
- **Issue C:** `:259-261` fantasy-translation table maps freeze → Weak/Frail, burn/venom → Poison, berserk →
  Strength + lose_hp; `:270` and `contract.py:341-343` then penalize exactly those statuses.
  **Fix:** rewrite the table to route fantasies to **distinct shapes first**: freeze → a `status_pool` debuff
  (`damage_taken` hook, "Brittle") or Frail + `blur`; burn → a `status_pool` DoT once Phase AQ lands, until then
  `poison` OR `on_hp_lost`/`turn_start` targeted damage engine; berserk → `forge` + `scale:"forged"` or
  `temp_strength` + `hp_lost_ge`; venom → `poison` + `target_debuff_count` payoff. Keep Vulnerable/Weak as the
  explicit last resort, but stop banning them outright in `contract.py:341` — replace "reach for them LAST" with
  "at most N cards per class lean on them" (N = the existing `MAX_GENERIC_DEBUFF_SHARE` quota, so the rule and
  the coverage gate agree).
- **Issue D:** `:14` docstring "Starter relics are NOT generated (the mod uses a placeholder)" is stale (Phase L).
  **Fix:** delete.
- **Test:** `tests/test_harness_v2.py` — assert the assembled blueprint prompt does not contain "no conditionals"
  or "NO targeted damage"; assert prompt length is within ±5% of the pre-change size (rule 0.9).

### W0.5 `class_forge.py` section pruning hides the vocabulary from the blueprint stage
- **Issue:** `_PRUNABLE_SECTIONS` (`:912-930`) drops TAGGED SYNERGY, TOKEN GENERATION, RAMPAGE, IN-RUN UPGRADE,
  DECK-THINNING, DISCARD/HAND-CHURN, CORRUPTION, METAMORPH, FORGE, BALANCE, STATUS POOL, SUMMON POOL unless an
  archetype already selected them. The blueprint model therefore never learns those exist, so it can never
  nominate them.
- **Fix:** keep the pruning (prompt budget), but append ONE compact line after the vocab block:
  `ALSO AVAILABLE (ask for the section by name in coverage_nominations): tags, tokens (add_card), rampage (grow),
  in-run upgrade, purge, discard/scry, corruption, transform/graft, forge+blade, balance gauge, custom statuses,
  a summon.` Extend `coverage.sanitize_nominations` to accept a fourth category `"sections"` whose values unprune
  the named section on the compose pass. This costs ~40 tokens.
- **Test:** `tests/test_harness_v2.py` — a blueprint nominating `sections: ["rampage"]` gets the RAMPAGE section
  in its compose prompt; one that doesn't, doesn't.

### W0.6 `contract.py` v1 card prompt — prototype residue
- **Issue A:** `_FEW_SHOT_IDS` (`:75-78`) lists `body_slam`, `twin_strike`, `disarm`, `battle_trance`, `anger`,
  `bloodletting`, `inflame`. None exist in `mod/content/cards/` (only `bash cleave clothesline defend expose
  hold_the_line iron_wave last_stand measured_riposte pommel_strike quick_jab rampart reckoning strike`). Under
  the repointed contract those few-shots are silently missing; under the default paths they are prototype cards
  using `from_state`/`set_flag`/`multi`.
  **Fix:** `_FEW_SHOT_IDS = ["strike", "defend", "bash", "cleave", "iron_wave", "expose", "hold_the_line",
  "rampart", "reckoning", "last_stand"]` and assert at import that every id resolves in `CARDS_DIR`.
- **Issue B:** `:276-279` names `multi, from_state, conditional`; only `harness_v2.compositional_clause` fixes it
  under `BTS_HARNESS_V2=1`.
  **Fix:** make the v2 clause the only clause (v2 has been live since 2026-09-08 for A/B; if the A/B is still
  running, gate the wording on the flag but make BOTH branches name mod ops).
- **Test:** `tests/test_contract_binding.py` — every few-shot id resolves; the rendered card prompt contains none
  of `from_state`, `set_flag`, `multi`, `fuse`.

### W0.7 `archetypes.json` — stale flags and metadata
- **Issue:** `buildable:false` on `reaper_lifesteal` (`:550`), `countdown_ripen` (`:613`), `balance_gauge`
  (`:643`), `token_conjurer` (`:708`) though their gaps are `done`; runtime recomputes (`catalog.py:167-180`) so
  the file lies. Duplicate metaphors: "the blade reforged" (`:46`, `:787`), "the rising storm" (`:82`, `:250`),
  "momentum" (`:244`, `:276`), "the curse" (`:406`, `:493`), "the crimson tithe" (`:468`, `:533`). `ops` lists mix
  statuses/conditions/scales/triggers (`:98`, `:196`, `:867-868`, `:898-901`, `:931`).
- **Fix:** flip the four flags; give each duplicated metaphor a distinct phrase; rename the field `ops` →
  `vocab` (it is what `catalog.live_vocab_tokens()` treats it as) or leave the name and add a schema comment.
  Add a `tests/test_archetypes.py`: no two archetypes share a metaphor string; every `buildable:false` names an
  open gap id that is not `done` in `VOCABULARY_GAPS.md`.

### W0.8 `exemplar_pool.json` — coverage imbalance and mis-tagging
- **Issue:** 46 exemplars, 14 archetypes with exactly one, and two of those (`token_conjurer` via `ex_ash_dividend`
  `:34`, `metamorph` via `ex_surge_capacitor` `:38`) don't use their archetype's mechanic. No exemplar uses
  `summon`, `buff_summon`, `heal_summon`, `add_card`, `transform_card`, `graft_card`, `blade_empower`,
  `summon_blade`, `gain_orb_slot`, `evoke`, `focus`, `draw_pile_empty`, `light_ge`, `centered`, a custom orb, or
  `upgrade.cost`.
- **Fix:** author ~20 exemplars so every archetype has ≥2 and every op/condition/scale in `VOCABULARY.md` appears
  in ≥1 exemplar. Retag `ex_ash_dividend` → `exhaust_pyre` only, `ex_surge_capacitor` → `big_energy` only. Add
  `needs:"balance"` support (see W0.9).
- **Test:** `tests/test_exemplars.py` — (a) every archetype id has ≥2 exemplars; (b) every exemplar uses ≥1 token
  from each tagged archetype's `ops`; (c) every backtick op/status/when-kind/scale token in `VOCABULARY.md`
  appears in some exemplar; (d) every exemplar passes `validator.validate_card`.

### W0.9 Exemplar dealing by archetype, not substring
- **Issue:** `harness_v2._pool_kind` (`:160-167`) satisfies `needs:"forge"` only when an archetype id contains
  the substring "forge"; `balance_gauge` and `forge_ramp` are `class_kind:"normal"` (`archetypes.json:641`, `:68`)
  so no `needs:"balance"` can exist and no class-kind guidance attaches.
- **Fix:** add an optional `mechanic_kind` field on archetypes (`forge` / `balance` / `discard` / …), and make
  `_pool_kind` return the union of the blueprint's `class_kind` plus every selected archetype's `mechanic_kind`.
  Leave `class_kind` alone (it drives pool declarations).
- **Test:** `tests/test_harness_v2.py` — a triad containing `balance_gauge` is dealt the balance exemplars.

### W0.10 Balance notes for every archetype
- **Issue:** only 4 of 34 archetypes have an `archetype-note` (`DESIGN_HEURISTICS.md:120-130`), so the MAP stage
  prints no `balance:` line for the other 30.
- **Fix:** write a one-sentence note for each of the remaining 30 (numbers cap, what counts as the payoff, what
  must not be stacked). Prioritize class-kind archetypes (orb_channel, slot_machine, summon_swarm,
  status_signature, forge_ramp, balance_gauge, madness_discard, token_conjurer, metamorph, exhaust_pyre).
- **Test:** `tests/test_contract_binding.py` — every archetype id has a non-empty note.

### W0.11 `VOCABULARY_GAPS.md` triage of #42–#48
- **#48 Penance Counter:** likely expressible today (`on_hp_lost` trigger + targeted `damage` payload). Build the
  Gap Tester, run AutoSlay, mark `done` with the verify-then-close pattern from gap #4.
- **#44 Coin & Ledger:** re-sketch as Forge-with-spend (a `spend_forge` op that consumes N counter for a payoff).
  Mark `planned` → Phase AX below.
- **#45/#46/#47 Contagion:** re-sketch as ONE op `spread_debuffs` (copy the target's debuffs to all other
  enemies). Mark `planned` → Phase AX. Adjacency stays rejected (#34).
- **#42/#43 Graveyard:** mark `rejected` for now (needs a fourth pile; `ForgedCards.cs:289` piles are
  hand/draw/discard). Note the nearest expressible shape: `ripen` + `add_card` from a "buried" token.

---

## Wave 1 — Lockstep hygiene: expose what the engine already runs (Phase AJ, vocab v40; ~2 days)

One phase, one vocab bump, because all four items change only validation and schema.

### Phase AJ — "Hidden capacity" (v40)
1. **`random_enemy` card target.** Engine maps it (`ForgedCards.cs:351`), Describe already says "to a random
   enemy" (`:1137`, `cardgen.py:344`). Add to `card.schema.json:13` enum, `VOCABULARY.md` Targeting table,
   `validator.py` target set, `census.py` target counts.
2. **Multi-hit `summon_attack`.** Engine executes `hits` (`EffectRunner.cs:320-322`); `validator.py:416-417`
   rejects `hits` off `damage`. Change the guard to `op not in ("damage", "summon_attack")`.
3. **Custom orb names in trigger payloads.** `TriggerRunner.cs:107-109` resolves them; `ForgedCards.cs:1012-1013`
   and `card.schema.json:147` restrict to base orbs. Relax both to "base orb, `random`, or a name in the class's
   `orb_pool`" (mirror the card-side check). `VOCABULARY.md` Triggers list: "`channel_orb` (any pool orb)".
4. **`once_per_turn` on `on_blade_played`.** Add to `validator.py:68` `_MULTI_FIRE_TRIGGERS`.
5. **Unknown custom orb silently channels Lightning.** `EffectRunner.cs:906-908` and `OrbRunner.cs:89-90`
   `?? OrbTypeFor("lightning")`. Replace with `Logger.Warn("[Forged] unknown orb '{orb}' — skipped")` + `continue`.
   Make `ForgedCards.Validate` reject an unknown pool name at import so it never reaches runtime.
6. **`VocabVersion = 40`, `bts1.VOCAB_VERSION = 40`.**
- **Test spec:** `tests/test_phase_aj.py` — random_enemy card validates and describes byte-identically; a
  `summon_attack` with `hits:3` validates; a trigger `channel_orb orb:"ember"` validates for a class whose pool
  has Ember and fails for one that doesn't; `on_blade_played` + `once_per_turn` validates. Gap Tester
  `generation/scratch/gaptest-aj/` (random-enemy attack, multi-hit summon attack, Ember auto-channeler) →
  AutoSlay, grep `[AJ]`.

### Phase AJ-b — Prototype path leakage (no vocab bump; `forge:` commit)
- **Issue:** `paths.py:36-61` defaults point card schema/vocab/statuses/cards at `prototype/`; `RELIC_*` and
  `CHARACTER_*` have no `BTSGEN_*` override at all and `point_btsgen_at_mod_contract()` (`class_forge.py:131-160`)
  never repoints them. `relic_contract.py` and `character_contract.py` therefore read prototype schemas
  (`combat_start`, `victory`, `attack_base`, tiers common/boss, `raw:true`, `max_energy 1..6`). `validator.py:159`
  reads prototype statuses so 12 of 18 mod statuses are "unknown" unless repointed. `validator.py:39`, `:244-250`,
  `:722-733` still walk `multi/conditional/from_state/fuse`. `_STATUS_WEIGHT` (`:26-32`) keys are prototype names.
- **Fix:**
  1. Flip `paths.py` defaults to the mod contract (`CARD_SCHEMA`, `VOCABULARY`, `STATUSES_DIR`, `CARDS_DIR`,
     `RELIC_VOCABULARY`, and a NEW `mod/contract/relic.schema.json` extracted from `class_forge._RelicContract`).
     Keep the `BTSGEN_*` env overrides for the prototype; make `point_btsgen_at_mod_contract()` a no-op that
     stays for callers.
  2. Delete the prototype ops from `validator.py` (`:39`, `:244-250`, `:722-733`).
  3. Re-key `_STATUS_WEIGHT` to the 18 mod statuses (proposed: vulnerable 2, weak 1.5, frail 1.5, poison 1.2,
     strength 4, dexterity 3, temp_strength 2, temp_dexterity 1.5, thorns 2, regen 2, metallicize 3, artifact 2,
     buffer 3, blur 2, intangible 8, ritual 5, barricade 5, focus 3). Keep `power_ceiling` warning-only.
  4. `relic_contract.py` / `character_contract.py` / `character_pipeline.py`: either retire (the production path is
     `class_forge`) or repoint. Recommendation: mark deprecated in the docstring, delete the prototype schema
     embed, and make `cli_relic_generate` / `cli_character_generate` call the `class_forge` contracts.
- **Test:** `tests/test_contract_binding.py` — with NO env set, `paths.CARD_SCHEMA` is the mod schema; every
  mod status is known to `validator`; no `from_state` anywhere in `btsgen/` except a comment.

---

## Wave 2 — Coverage pressure: make the generator reach for the whole vocabulary (no vocab bump; ~2 days)

The vocabulary is wide, but `coverage.py`/`featured.py`/`census.py` only measure a slice, so nothing pushes
the model toward the rest.

### W2.1 `census.py` — count what exists
- Count multi-hit (`hits ≥ 2`) as non-plain (`:123-131`); count the four keywords (exhaust/retain/innate/ethereal);
  count `apply_status_custom` statuses and `buff_summon` statuses (`:92-95`); move `poison`, `frail`, `focus` into
  their own bucket (`:44-47`); count `tags`, `upgrade.cost`, `once_per_turn`, `ripen` amounts, targeted payloads.
- `format_report` (`:256-264`) prints every counter, not a fixed subset.
- **Test:** `tests/test_census.py` extended per counter.

### W2.2 `coverage.py` — widen the menus, gate by class kind
- `WHEN_MENU_V2`: add `retained_last_turn`, `draw_pile_empty`, `hp_lost_ge value:3`, `target_has_status
  status:vulnerable`; class-kind-gated entries `forged_ge` (forge), `dark_ge`/`light_ge`/`centered` (balance),
  `orbs_match`/`orb_count_ge` (orb).
- `SCALE_DIRECTIVE` → a `SCALE_MENU`: `cards_in_hand`, `cards_retained`, `unspent_energy_last_turn`,
  `target_debuff_count`, `damage_dealt_unblocked` (heal), `tag_cards_owned` (needs a tag), `forged` (forge only).
- `EXOTIC_MENU_V2`: add `ritual`, `barricade`, `intangible` as **nominate-only, rare-tier** (repair never injects
  them; the blueprint may nominate one).
- New `KEYWORD_MENU`: `retain`, `innate`, `ethereal`, `hits` (multi-hit) with a `MIN_KEYWORD_KINDS = 2` quota.
- `NOMINATION_CATEGORIES` += `"scale"`, `"keyword"`, `"sections"` (W0.5).
- **Test:** `tests/test_coverage.py` — each new menu key has a directive, a census detector, and appears in
  `DIRECTIVE_BY_KEY`; repair walks the new menus.

### W2.3 `featured.py` — class-kind-aware roulette
- Keep the base menu as is. Add a second menu `FEATURED_CLASS_KIND` dealt only when the blueprint's class kind or
  a selected archetype's `mechanic_kind` (W0.9) matches: orb (`evoke` burst card, `gain_orb_slot`, `focus`
  power), status (`apply_status_custom` on ≥3 cards), summon (`heal_summon`/`shield_summon` medic,
  `buff_summon`), forge (`blade_empower`, `summon_blade`, `on_blade_played`), balance (a `centered` payoff),
  discard (`scry` + `on_discard`), transform (`graft_card`).
- **Test:** `tests/test_featured.py` — a summon-kind class rolls at least one summon featured entry; a normal
  class never does.

### W2.4 Character-level knobs the generator never touches
- **`max_energy` is never prompted** (assembly default 3, `class_forge.py:2730`; C# allows 1..10).
  **Fix:** blueprint field `max_energy` ∈ {2,3,4} with a one-line rule ("4 only with a smaller HP pool or a
  drawback relic; 2 only for a big-energy/X-cost class with cost 0–1 cards"). Validator range 2..4.
- **Pool `color {h,s,v}`** parsed by C# (`ForgedCharacters.cs:280-286`) but never emitted (`class_forge.py:2725`).
  **Fix:** blueprint field `color` (hue 0–359, or a named palette entry); emit it. Default stays slot-index hue.
- **Caps:** summon `max_hp` 60 → 100 (`class_forge.py:1838`); `orb_slots` 4 → 5 (`:1440`); `max_hp` 60..95 →
  55..100 (`:1432`). Keep the engine caps as the hard ceiling.
- **Test:** `tests/test_forge.py` — assembled blueprint carries `max_energy` and `color`; ranges enforced.

---

## Wave 3 — Cheap engine additions (one phase each, vocab bumps v41+; ~1 day each)

Each phase uses an API already called nearby, so the verify-first step is a grep, not a spike.

### Phase AK — Attacker target + once_per_combat on card triggers (v41)
- **`target:"attacker"`** on `attacked` payloads. `ForgedTriggerPower.cs:98-129` already holds `dealer`; thread it
  into `TriggerRunner.Run(t, player, ctx, attacker: dealer)` and resolve `"attacker"` in `ResolveEnemies`
  (`TriggerRunner.cs:158-165`), mirroring `RelicRunner.cs:50`. Closes the riposte polish (gap #4 note) and the
  J-3 "true Thorns" item.
- **`once_per_combat`** on `add_trigger` (relic pattern `RelicRunner.cs:30-33`). Trigger powers are per-combat
  instances already (`ForgedTriggerPower.cs:33-37`), so it's a bool + a fired flag.
- Lockstep: schema `triggerEffect.target` enum += `attacker` (attacked only); `add_trigger` += `once_per_combat`
  (reactive only); Describe: "…to the attacker" / "Once per combat, …".
- **Test:** `tests/test_phase_ak.py`; Gap Tester: two-enemy fight, riposte hits the one that struck.

### Phase AL — Richer trigger payloads (v42)
- Allow in `TriggerOps` (`ForgedCards.cs:267-277`) + schema `triggerEffect.op`: `apply_status_custom` (status
  class only), `summon_attack` / `buff_summon` (summon class only; the dormant move-cycle re-expressed as a card
  engine), `hits` on payload `damage`/`summon_attack` (`ForgedCards.cs:1094` currently rejects; `SummonRunner.cs:47`
  already loops hits).
- Payload `scale` (`ForgedCards.cs:315`) += `forged`, `unspent_energy_last_turn`, `cards_in_hand` (all player-level
  reads: `EffectRunner.ForgeStacks`, `HandStateTracker.cs:27`).
- **Test:** `tests/test_phase_al.py`; Gap Tester: "At turn start, gain 1 Razor Focus"; "At turn end, your summon
  attacks for 4 twice".

### Phase AM — New scales and conditions (v43)
- `scale` += `block` (Body Slam), `hp_lost_this_turn` (`HpLossTracker.cs:29`), `draw_pile_count`
  (`Conditions.cs:107`), `energy` (`HandStateTracker.cs:52`), `plays_this_combat` (`EffectRunner.cs:786-791`).
  One `ScaleValue` case each (`EffectRunner.cs:730-738`).
- `when` += `target_hp_below_half`, `target_has_block` (target creature already flows into `Conditions.Eval`
  `:78-91`), `energy_ge`, `cards_played_this_turn_ge` (`CombatManager.History`, `:788-790`).
- **Test:** `tests/test_phase_am.py`; describe byte-match for each new phrase.

### Phase AN — Small ops (v44)
- `gain_max_hp` (`CreatureCmd.GainMaxHp` in use `EffectRunner.cs:931`) — Feed; cap 1..5, rare-tier note.
- `damage` flag `unblockable:true` (`ValueProp.Unblockable` in use `:149`).
- `temp_thorns`, `temp_focus` statuses via `CustomTemporaryPowerModel` shells (`ForgedTempStatPowers.cs:24-37`).
- **Test:** `tests/test_phase_an.py`.

### Phase AO — Card-type-scoped cost modifiers (v45)
- New op `cost_shift {card_type: attack|skill|power|all, amount: -1..-2, scope: this_turn|combat, count?: 1}`.
  Generalizes `ForgedCorruptionPower.TryModifyEnergyCostInCombatLate` (`:43-54`); `count:1` gives "next Skill
  costs 0". Closes the Corruption `card_type` deferral (`VOCAB_EXPANSION_4_PLAN.md:142`) and the relic
  "first card costs 0" deferral (`PHASE_L…:367-369`) via the same power.
- Loop-discipline rule: `cost_shift` with `scope:combat` is rare-only and at most one per class.
- **Test:** `tests/test_phase_ao.py`; Gap Tester: "Your Attacks cost 1 less this turn".

### Phase AP — Pile manipulation and status cards (v46)
- `discard` gets `cards: random|choose` (`CardSelectCmd.FromHand` `EffectRunner.cs:562,649` + `CardCmd.Discard`
  `:457`). Then reword `VOCABULARY.md:35`.
- `retrieve_card {pile: discard|exhaust, cards: random|choose}` — the blade path minus the token filter
  (`CardPileCmd.Add` `ForgedForgePower.cs:74`; `CardSelectCmd.FromCombatPile` per `SPIKE_CARD_SELECT.md`).
- `add_status_card {card: dazed|wound|burn, pile, amount}` — `AddGeneratedCardToCombat` (`EffectRunner.cs:425`)
  with `ModelDb.Get(typeof(Dazed))` (pattern at `:248`; `Dazed` referenced at `PetDamageAttributionPatch.cs:12`).
  Closes F4 (`VOCAB_EXPANSION_PLAN.md:89-93`).
- Rule 0.4/0.5 apply (choice UI + deck-thinning tester).
- **Test:** `tests/test_phase_ap.py`; grep `Auto-selected`.

### Phase AQ — Status-pool hooks (v47)
- `damage_over_time` hook (debuff; stacks lose HP at the afflicted enemy's turn start, then decay per `decay`)
  — the burn/freeze fantasy (`VOCAB_EXPANSION_2_PLAN.md:363-364`). Implement as a `ForgedStatusPower` branch on
  `BeforeTurnStart` of the owner creature.
- `mode: multiplicative` — parsed already (`StatusSpec.cs:27`); implement for `damage_dealt`/`damage_taken`
  (`×(1 + 0.1·stacks)`, capped) and open the validator.
- `hit_count` hook — **verify first**: the J-1 blocker was no dealer accessor on `AttackCommand`.
  `PetDamageAttributionPatch.cs` now attributes pet damage, so check whether the same patch point exposes the
  dealer. If yes, implement; if no, STOP and record.
- **Test:** `tests/test_phase_aq.py`; Gap Tester: a "Scorch" DoT class.

### Phase AR — Conditions inside custom orb effects (v48)
- `OrbSpec.OrbEffect` (`OrbSpec.cs:11`) gains `When`; `OrbRunner` evaluates `Conditions.Eval` before each orb
  effect. Closes `PHASE_I_FORGED_ORBS_PLAN.md:95,118`.
- **Plasma / Glass:** do NOT add base orbs. Instead add two **custom-orb recipes** to `VOCABULARY.md` (Plasma =
  passive `gain_energy 1`; Glass = passive nothing, evoke `damage` ×3) so the model builds them from the existing
  pool machinery. Verify `gain_energy` is legal in orb passives; if not, add it.
- **Test:** `tests/test_phase_ar.py`.

### Phase AS — Relic vocabulary (v49)
- `on_card_played` hook gains `card_type` filter — **verify first**: `PHASE_L…:366` said `CardModel` had no clean
  type accessor; `DataCard.cs:283-284` frames by type, so the accessor exists on our own cards — check base cards.
- `every_n` on a hook (per-relic counter): `{trigger, every_n: 3}` fires on the 3rd, 6th… occurrence.
- `attack_base` modifier (always-on +N attack damage) — cheap (`PHASE_L…:271`); price it in `_MODIFIER_VALUE`.
- **Reprice `max_energy` / `cost_reduction`** (`class_forge.py:1092-1098`): keep them above budget ALONE, but let a
  second `drawback` hook (new: `turn_start` → `lose_hp` / `discard 1` / `apply_status weak self`) subtract from
  the price so "Coffee Dripper with a cost" is reachable. Add a `max_hp` modifier (±) to the modifier table as the
  standard drawback.
- True `combat_start`: **spike** (`PHASE_L…:149` unknown #2: reach player+ctx in `BeforeCombatStart`). If
  `ForgedRelic.cs:88-98` still can't get a ctx, keep the `turn_start + once_per_combat` idiom and document it as
  the ONLY spelling (already done). Do not block AS on it.
- Update `DESIGN_HEURISTICS.md` relic forms with "Counter relic" and "Boon with a price".
- **Test:** `tests/test_phase_as.py`, `tests/test_relic_validator.py`, `tests/test_keystone_balance.py`.

### Phase AT — Summon damage counts as "you deal damage" (v50)
- `ForgedTriggerPower.cs:164-169` requires `dealer == Owner && cardSource != null`; `summon_attack` deals via the pet
  with no card. Use `PetDamageAttributionPatch` to attribute pet damage to the owner for `on_damage_dealt` (and the
  relic twin). Summon classes can then build "whenever you deal damage" engines.
- **Test:** `tests/test_phase_at.py`; Gap Tester: summon attack + on_damage_dealt draw.

### Phase AU — `on_discard` for base-game discards (v51)
- **Verify first:** find the base-game discard hook (grep the decompiled API for the equivalent of
  `AfterCardDiscarded` / `CardCmd.Discard` completion). If present, call `DataCard.FireOnDiscard`
  (`DataCard.cs:263`) from it with the existing `_firingOnDiscard` guard. If absent, STOP; the W0.2 caveat stays.

---

## Wave 4 — Dormant subsystems, structural caps, and new content types (~1 week+)

### Phase AV — Re-enable the autonomous minion model (v52)
- Engine is present and mostly live: `SummonSpec.cs:19-28` (`Moves`, `Attackable`, `OnSummon`, `OnDeath`), parser
  `ForgedCharacters.cs:622-680`, move cycle `ForgedSummonPower.cs:43-52`, death rattle `:57-64`, ethereal
  `ForgedSummonShieldPower.cs:47-49`.
- Two C# fixes: fire `SummonRunner.RunActions(spec.OnSummon, pet, ctx)` inside `SummonForged`
  (`EffectRunner.cs:920-946` — parsed but never called); key `FindLivingSummon` on summon NAME so `MaxSummons = 2`
  (`ForgedCharacters.cs:593`) is reachable.
- Generation lockstep: drop `_REMOVED_SUMMON_FIELDS` (`class_forge.py:1901`), `_MAX_SUMMONS` 1 → 2 (`:1837`),
  re-add the K-3 prompt section (gated: a summon class may opt into ONE autonomous minion; the passive Osty model
  stays the default), restore `VOCABULARY.md:318-319`.
- Add the K-3 deferred payoffs while here: `on_nth_attack` counter on the summon spec; `sacrifice_summon` op
  (consume the living minion for a payoff, `PHASE_K…:111`).
- Rule 0.3: the K-3 AutoSlay history shows random bots stall on pets; reuse the K-3 Gap Testers.
- **Test:** `tests/test_phase_av.py`.

### Phase AW — Hybrid class kinds in generation (v52, no engine change)
- Blocked on an AutoSlay smoke that drives a hybrid (orb + status, say) into combat
  (`PHASE_N_CREATIVE_BREADTH_PLAN.md:40`). Run that smoke FIRST with a hand-built BTS1 code (the importer already
  accepts hybrids, O-2a). If it passes: `class_forge.py:795-800` `class_kind` becomes a set; pools are emitted for
  each kind; exemplar dealing (W0.9) already handles unions.
- **Test:** `tests/test_phase_aw.py`.

### Phase AX — Structural caps and the gap #44/#45 ops (v53)
- **Cost 0..3 → 0..4** (`card.schema.json:12,24`; engine has no cap). Rule: cost 4 only at rare with a headline
  effect.
- **Upgrade may add a keyword** (`ForgedCards.cs:963-964`, `validator.py:620-622` require equal effect counts).
  Relax: the upgrade may append exactly one of `exhaust`/`retain`/`innate`/`ethereal` or remove `exhaust`.
- **Two-of-a-kind values.** Keep "one damage / one block per card" (the Damage/Block vars are canonical,
  `DataCard.cs:142,149`). Allow a second `apply_status` of the SAME status when the second is `when`-gated, by
  suffixing the var name (`Weak2`). Leave Loss/Discard/Scry/Heal/Energy singletons.
- **`tags` maxItems 2 → 3** (`card.schema.json:16`).
- **`spend_forge {amount}`** — consumes Forge for a payoff (gap #44 re-sketch); pairs with `forged_ge`.
- **`spread_debuffs`** — copy every debuff on the target to all other enemies (gap #45–47 re-sketch; reads the
  target's powers the way `target_debuff_count` does).
- **Test:** `tests/test_phase_ax.py`.

### Phase AY — Run-persistent Forge (spike, then v54 if green)
- `PHASE_M_FORGE_PLAN.md:45-46`, `SOVEREIGN_BLADE_SCOPE.md:167`: needs run-persistent state. Spike: does the mod
  already persist anything per run (`user://forged/...` is per-install, not per-run)? If STS2 exposes a run-save
  hook, store `forge_persist` on the character and rehydrate `ForgedForgePower` at combat start. Otherwise STOP and
  keep per-combat.

### Phase AZ — New content types (scoping only; each is its own plan)
- **Forged potions** — a `potion_pool` on the character (1–2 potions), spec `{name, emoji, effects[]}` reusing the
  card effect vocab (self/enemy target), runtime `ForgedPotion : BlankTheSpirePotion`
  (`Potions/BlankTheSpirePotion.cs`), pool wiring in `Character/BlankTheSpirePotionPool.cs`. Write
  `PHASE_BA_FORGED_POTIONS_PLAN.md`.
- **Curses / status cards as generated content** — extend card `type` with `curse` (unplayable, ethereal-ish
  drawback) only after Phase AP proves base status cards work. Write a scope note; do not build until a class
  concept demands it (no demand signal in `VOCABULARY_GAPS.md` yet).
- **Events** — no engine surface, no demand signal. Record as "not planned" in `VOCABULARY_GAPS.md` so it stops
  being re-audited.

---

## Cross-cutting mitigations (apply from Wave 0 onward)

- **A "vocab drift" test.** `tests/test_vocab_lockstep.py`: parse `ForgedCards.cs` (`SupportedOps`, `TriggerOps`,
  `SupportedTriggers`, `SupportedOrbs`, `Conditions.Kinds`), `card.schema.json` enums, `VOCABULARY.md` backtick
  tokens, `validator.py` sets, and `exemplar_pool.json` usage; assert set equality (engine ⊆ schema ⊆ vocab, every
  vocab token has an exemplar). This would have caught `random_enemy`, the `hits` guard, the orb enum, and
  `on_blade_played` once_per_turn.
- **A "prompt-vs-vocab" test.** Assert the rendered blueprint/card/relic prompts never contain the phrases
  "not yet", "no conditionals", "does not exist", or a prototype op name.
- **Stale-doc sweep.** `PHASE_L…:7` "STILL OPEN" (relic on_hp_lost), `SPLASH_ART_PLAN.md:15` "PLAN ONLY",
  `class_forge.py:14`: mark LANDED in place so future audits don't re-surface them.
- **Importer version gate** (`BTS1Codec.cs:65-67`) is one-directional. Add a min-version check in the OTHER
  direction only if an older mod build is still in the wild; otherwise document.

---

## Scoreboard

| Wave | Phases | Vocab | Effort | Creative-range gain |
|------|--------|-------|--------|---------------------|
| 0 | W0.1–W0.11 | — | 1–2 days | Highest per hour: the model stops being told features don't exist; exemplars cover every op |
| 1 | AJ, AJ-b | v40 | 2 days | Random-enemy, multi-hit summons, custom-orb engines, correct balance weights |
| 2 | W2.1–W2.4 | — | 2 days | Coverage pushes the model across the whole vocabulary; classes can vary energy and color |
| 3 | AK–AU | v41–v51 | ~1 day each | Attacker riposte, richer engines, five new scales, four new conditions, cost tricks, pile ops, status cards, DoT statuses, orb conditions, relic counters |
| 4 | AV–AZ | v52+ | 1 week+ | Autonomous minions, hybrid classes, cost 4, upgrade-adds-keyword, Forge spend, contagion, potions |

**Recommended order:** Wave 0 in one sitting → AJ + AJ-b → Wave 2 → AK, AL, AM (the three that most widen card
design) → AQ (the most-requested fantasy, burn/DoT) → AS (relics) → the rest of Wave 3 by demand → Wave 4.
