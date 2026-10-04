# Vocabulary Expansion — Wave 6 Plan (base-game audit closure, gaps #62–#79 + #11)

**Written 2026-10-01 from `docs/plans/VOCAB_BASE_GAME_AUDIT.md` (the base-game mechanics audit, vocab v60) and a
three-scout verify-first pass (tier A engine, tier B engine, generation/harness).** Scout reports are saved beside
this plan in `docs/plans/wave6_scouts/` (`scout_tierA.md`, `scout_tierB.md`, `scout_generation.md`); every
`file:line` below comes from them. **Names are authoritative, line numbers are hints — re-grep before trusting.**

**Why this wave:** the gaps log (#1–#61) was built from forge-harness demand. The audit compared the vocabulary
against the 549 base-game player cards instead and found 31 mechanics that are missing and never triaged, 24 that
are partial, and 7 already logged. This wave closes the generic, high-count ones. Character-specific resource
systems (Stars) and anything AutoSlay cannot prove are deferred (§6).

**Window:** the workstation is free for ~2 days from 2026-10-01. §5 gives the cut line. Phases BH–BM are the core
(they cover ~110 base cards); BN–BR are stretch, in order.

**Where the game sources are:** `C:\Users\ryanr\Desktop\NOVOGODOT\BLANKthespire\_modref\` (`decomp_full\` =
DECOMP, `BaseLib-StS2\` = BL). MOD = `mod/BlankTheSpireCode/`.

---

## 0. Ground rules (Wave 5 §0 carries over; changes and load-bearing rules repeated)

- **0.1 Lockstep or nothing.** Engine (`ForgedCards.cs` SupportedOps/TriggerOps/AmountOps/KeywordOps/Validate/
  ValidateTrigger/Describe/TriggerFragment/VocabVersion · `EffectRunner.cs` · `TriggerRunner.cs` · `DataCard.cs` ·
  `CardSpec.cs` · `Conditions.cs` · `Powers/*`) + `mod/contract/card.schema.json` + `mod/contract/VOCABULARY.md` +
  `generation/btsgen/` (`cardgen` · `validator` · `census` · `bts1` · `coverage` · `featured` · `harness_v2` ·
  `gate` · `class_forge` · `data/archetypes.json` · `data/exemplar_pool.json`) + `web/static/render.js`. Full
  checklist in §1 (re-anchored 2026-10-01).
- **0.2 Describe text is a byte-match contract.** `cardgen.describe()` == `ForgedCards.Describe()`. The phase test
  asserts the Python literal AND greps the C# source fragment (there is no C# extractor — see §1 item 4).
- **0.3 AutoSlay validation is by godot.log tags, not the tool verdict.** Pass bar per run: ≥1 phase tag fired ·
  0 mod exceptions · no BlankTheSpire frame in a stall stack · 0 "Localization formatting error". Map-nav FAIL is
  expected. **New (scout B §0.1): AutoSlay plays every card through `CardCmd.AutoPlay` and never spends energy or
  stars.** A smoke proves cost READS (log `GetWithModifiers`), never energy actually paid; `AfterEnergySpent` never
  fires. **New (Phase BD lesson): every new card-level hook (`DataCard` overrides) is smoke-to-prove** — `AfterFlush`
  never fired for a retained card. One tag per hook, day one.
- **0.4 / 0.5 Choice testers** are all-aggression decks; grep `Auto-selected` to confirm the picker resolved. Custom
  picker prompts are now SAFE via BaseLib `CardLoc` ExtraLoc (`("selectionScreenPrompt", "…")` in
  `DataCard.Localization`, `DataCard.cs:138`) — no more reusing `CardSelectorPrefs.*` keys that don't fit.
- **0.6 STOP rules.** Verify-first contradicts the spec → STOP that phase, write findings into its section, move on.
  C# build breaks unrecoverably → revert the phase, record why. Smoke hangs at "Combat turn N" → check
  `power-hook-turn-start-pitfall` first (damage ticks belong on `AfterSideTurnStart` + `ThrowingPlayerChoiceContext`).
- **0.7 Commit convention.** One commit per phase: `mod+forge: Phase <XX> — <mechanic> (vocab v<N>)`; generation-only
  phases `forge: Phase <XX> — …`.
- **0.8 Vocab versions** are assigned in build order from **v61**. Reorder → renumber.
- **0.9 Prompt budget — READ §2 FIRST.** Today's rule-0.9 tests measure the UNTRIMMED blueprint prompt, a path
  production never sends, and they have **463 chars** (scaffold) / **103 chars** (worst-case reading) of room,
  so the FIRST VOCABULARY.md row trips `test_rule_0_9_v2_is_the_worst_case`. Phase BH replaces the whole-file
  paste with the **vocabulary tree** (index + per-forge detail, §2) and repoints the tests at the real prompt
  BEFORE any vocab row lands. After BH, a new VOCABULARY row costs one index line (~80 chars) on every forge and
  its full row only on forges that select it.
- **0.9b Tests are part of the deliverable.** BH-1 is a full audit of `generation/tests` + `web/tests` against
  what BTS does today (stale paths, tests measuring dead code paths, phase tests with no pytest wrapper); §4
  repeats the pass before the release. A phase is not done while a test asserts something the code no longer does.
- **0.10 Phase tests run under pytest.** `def test_phase_<xx>_all(): assert main() == 0`. Run from `generation/`
  with `uv run python -m pytest`. conftest's `_FAIL` guard also catches a bare `test_version`.
- **0.11 Release ordering.** The codec rejects codes newer than the installed mod (`BTS1Codec.cs:65-67`). **The
  wave-5 lesson (2026-10-01): the droplet was deployed at v60 while the public mod was v0.2.2/v55 — every forge in
  between produced un-importable codes.** Rule: NO web deploy of a vocab bump until the mod zip + Workshop item are
  live. Build BI→BR on one branch, ONE mod release (v0.4.0) at the end, THEN deploy (§4). The v0.3.0 wave-5 release
  is step 0 of Phase BH.
- **0.13 Keep the mobile tracker current.** Ryan follows the wave from the artifact **Wave 6 Tracker**
  (https://claude.ai/artifact/HLDCp8LSudRp1YY9JZz3SU). Its status lives in the artifact database, so update it with
  the `ArtifactData` tool (never republish the page for a status change): collection `phases`, one doc per phase id
  (`bh`, `bi` … `br`, `rel`) with `{status: "todo"|"doing"|"done"|"blocked", done_items: [...], note: "..."}`; the
  item ids are `bh0..bh3` for BH, `eng` / `harn` / `smoke` for BI–BR, `tests` / `zip` / `ws` / `deploy` for REL. The
  banner is doc `meta/wave` `{headline, updated (ISO), vocab}`. Cadence: when a phase starts (`doing` + headline),
  when its smoke passes (`done_items` += `smoke`), when it ships (`done`, headline names the next phase), and
  immediately on any `blocked`. Short plain sentences; it is a phone checklist, not a log.
- **0.12 Gap log is the catalog's switch.** `frontend/catalog.py:gap_status` reads `### N.` + `**Status:**`; flipping
  an entry to `done` is what makes an archetype BUILDABLE. New entries start at **#62** (droplet copy checked
  2026-10-01: max is #61; the map stage auto-appends `captured` entries, so re-check before numbering).

### Standard commands

```powershell
# generation-side (from generation/)
uv run python -m tests.test_phase_bi          # standalone
uv run python -m pytest                        # full suite (baseline after BH: all green)

# C# (Program Files dotnet is runtime-only; close the game first)
~/.dotnet/dotnet.exe build mod/BlankTheSpire.csproj -c Debug

# AutoSlay smoke (tester staged into slot 04 by the phase's build_tester.py; verdict FAIL on map-nav is expected)
uv run btsgen-autoslay-smoke --seeds GAPTESTBI1 GAPTESTBI2 --character class4 --relic auto --timeout 900
# gate: grep %APPDATA%\SlayTheSpire2\logs\godot.log for "[BI]", "Auto-selected", 0 mod exceptions, 0 "Localization formatting error"
```

---

## 1. Harness wiring — the checklist every phase walks (re-anchored 2026-10-01)

**Contract**
1. `mod/contract/card.schema.json` — op enum `$defs.effect.properties.op.enum` (:35); `scale.enum` (:52); `status.enum`
   (:54); `trigger.enum` (:56); `triggerEffect` (:223, its `op.enum` :229) ONLY if legal as a payload; `$defs.condition`
   (:307, `kind` enum :313). The effect object is `additionalProperties:false` (:32) — every new FIELD is declared here.
2. `mod/contract/VOCABULARY.md` — op rows :10-54 (`add_trigger` row :32); Conditions :205 (rows :214-234); Triggers :246
   (list prose ~:264). Pasted whole into the blueprint prompt today (`class_forge.py:257/265`) — after BH-3 the
   blueprint gets the INDEX plus the per-forge DETAIL block (§2.2) — and into the card prompt (`contract.py:311/327`,
   already tiered by `gate.py`). A new row therefore needs: the row itself, its token in `GATED_OP_ORDER` or a
   family, and nothing else for the index (it is derived).
3. `generation/btsgen/bts1.py:28` — bump `VOCAB_VERSION`, add the `"NN: Phase XX — …"` comment (the test greps it).

**Card text + C# emit**
4. `cardgen.py` — `describe()` (:517); `cond_phrase` (:327); `trigger_sentence` (:465) + `_trigger_fragment` (:387);
   `effect_literal` (:187) named arg for any field that must reach C# (`Grow:` :280, `OncePerCombat:` :297 idiom).
   Byte-match is half-automated: the phase test asserts the Python literal AND greps the C# fragment
   (e.g. `'case "sly": parts.Add("Sly."); break;'`), so write both literals by hand and keep them identical.

**Validator / pricing**
5. `validator.py` — `_BUILD_AROUND_OPS` (:61); caps constants (:81-198); `_MULTI_FIRE_TRIGGERS` (:115) /
   `_ONCE_PER_COMBAT_TRIGGERS` (:123); `_engine_structural_errors` (:422) per-op shape rules + "not on a BASIC" idiom
   (:771-945) + card-only payload rejection (:1118-1122); `_score_effect` (:1211).

**Census / coverage / featured / harness / gate**
6. `census.py` — `cc.ops` counts ops automatically (:141); a new FIELD needs a counter + `_walk_effects` branch (:131),
   the `Census` aggregate (:228) and a `format_report` line (:415). Nullary keyword ops → `KEYWORD_OPS` (:63).
   `test_census` pins a FIXTURE card's counts (:163-165, :214), not the set.
7. `bridges.py:40 card_tokens` — surface a non-op FIELD an archetype lists in `vocabulary.ops` (as `unblockable` :50).
8. `coverage.py` — `REACTIVE_MENU_V2` (:77) / `WHEN_MENU_V2` (:81) / `WHEN_MENU_KIND` (:108) / `SCALE_MENU` (:120) /
   `SCALE_MENU_KIND` (:142) / `KEYWORD_MENU` (:155). `test_coverage.py` pins exact sets (:221-232) and needs a `samples`
   entry per key (:243, `set(samples) == set(_w2_keys())` :279).
9. `featured.py` — `Featured(...)` (:35-53); base ops → `FEATURED_MENU` (:60; `contagion` :189 is the template);
   class-kind ops → `FEATURED_CLASS_KIND[kind]` (:233-338; kinds pinned to orb/status/summon/forge/balance/discard/
   transform by `test_featured.py:247`). Samples pinned at :174 / :302.
10. `harness_v2.py` — `_PREFERRED_OPS` (:62) / `_PREFERRED_CONDITIONS` (:70) / `_PREFERRED_TRIGGERS` (:73);
    `compositional_clause` (:123); `exemplar_validator` (:178); `_pool_kind` (:209).
11. `gate.py` — **every new op goes in `GATED_OP_ORDER` (:108)** or a `FAMILY_OPS` family (:93); otherwise it lands in
    the core tier and every card prompt pays for it. New field → `FIELD_UNITS` (:119).
    `test_vocab_gate.py:104` fails on a schema op with no VOCABULARY row.
12. `class_forge.py` — translation paragraph (:270-291), archetype pitch sections (:292-597), `_PRUNABLE_SECTIONS`
    (:1006-1034) + ALSO-AVAILABLE (:1036), `_ORB_CONDITION_KINDS` (:2099) for any new condition (`test_phase_ar.py:186-202`
    asserts schema == C# `Conditions.Kinds` == this set, plus `TargetKinds` :199-202), uptime heuristic `_cond_uptime`
    (:1361, kind branches :1378-1390). Pitch prose is pruned per forge, but keep additions to a sentence or two:
    the §2.3 scaffold assert (46k on the real path) still applies.

**Catalog + exemplars + heuristics + web**
13. `data/archetypes.json` — the archetype's `vocabulary.ops` += token; `build_notes` reworded; every token must be
    backticked in VOCABULARY.md (`test_archetypes.py:121-129`); `gap_refs: ["VOCABULARY_GAPS#N"]`; `buildable` pin :80.
    Ids (line hints): `retain_hold` :5, `forge_ramp` :149, `ascetic_purge` :535, `poison_attrition` :692,
    `strike_tempo` :1060, `countdown_ripen` :2186, `balance_gauge` :2296, `madness_discard` :2379, `exhaust_pyre`
    :2633, `ambush_alpha` :3400, `burst_window` :3735; also `power_ramp`, `tempo_draw`, `big_energy`, `debuff_expose`,
    `block_bulwark`, `untouchable_ward`, `reaper_lifesteal`, `horde_breaker`, `iron_regrowth`, `self_sacrifice`,
    `token_conjurer`, `fleeting_flux`, `orb_channel`, `slot_machine` (grep by id).
14. `data/exemplar_pool.json` — ≥1 exemplar per new op / status / condition / scale / trigger
    (`test_exemplars.py:143`); class-only tokens carry `needs` (:181); every exemplar validates.
15. `DESIGN_HEURISTICS.md` — a balance note per mechanic (`contract.archetype_balance_note` :77).
16. `VOCABULARY_GAPS.md` — Status → `done (date, vocab vNN, Phase XX)`.
17. `web/static/render.js` — **the `app.js case "op":` renderer is GONE.** Card preview is `render.js` `effPhrase`
    (:527, `switch (e.op)` :532) and `condCore` (:497); relic `fmtHook` :141; `potionLines` :253.

---

## 2. Rule 0.9 — the budget, and the vocabulary tree that Phase BH builds

Readings 2026-10-01 (`tests/test_harness_v2.py`, `_BlueprintContract(mode="dossier", triad=True, seed=1)`):

| Assert | Ceiling | Now | Headroom |
|---|---|---|---|
| `test_rule_0_9_blueprint_scaffolding_stays_within_budget` (:387) — prompt minus VOCABULARY.md | `BP_SCAFFOLD_BUDGET = 46_000` (:354) | 45,537 | **463** |
| `test_rule_0_9_total_prompt_stays_under_the_tripwire` (:398) | `BP_TOTAL_TRIPWIRE = 120_000` (:357) | 108,282 | 11,718 |
| `test_rule_0_9_v2_is_the_worst_case` (:408) — flag-off vs `BP_READING` (:374) | 108,282 | 108,179 | **103** |

- VOCABULARY.md is 62,745 chars. Wave 5 rows measured 422–808 chars per op row (not 250) and the file grew ~830
  chars per phase. Ten vocab phases at that rate → ~119k on the untrimmed path: without the tree the tripwire is
  reached in the last phases, and the 463-char scaffold room would force a cut for every pitch sentence.
- **After the tree (2.2 + 2.3) the per-phase discipline is:** keep pitch additions short (the pitches are pruned
  per forge, so they cost only the forges that select them); add every new op to `GATED_OP_ORDER`; and print the
  three readings in the phase test (informational) so growth stays visible.
### 2.1 What exists today (so BH builds on it, not beside it)

- **Card prompt: already a two-tier tree, live.** `gate.py` (`BTS_VOCAB_GATE=heuristic` on the droplet) lays the
  card prompt out as a byte-identical CORE (always-on sections + the core ops + the schema's core half) followed by
  per-card ADD-ONS chosen by keyword rules over the brief (or Jev), in canonical order so provider prefix caching
  survives (`gate.py` docstring; `GatedPrompt` :373, `build` :653, `SECTION_FAMILY` :72, `FAMILY_OPS` :93,
  `CORE_OPS` :104, `GATED_OP_ORDER` :108, `_split_op_table`). Measured: normal-class core 32k vs 122k full.
- **Blueprint (design) prompt: still pastes VOCABULARY.md whole** (`class_forge.py:_system_prompt_legacy` :255,
  `vocab = paths.VOCABULARY.read_text()` :257, interpolated at :265) even though by then the pipeline already knows
  (a) the chosen archetypes' ops — `frontend/builder.py:480-483` passes `selected_ops` — and (b) the class kind.
  `_prune_archetype_sections` (:1047) uses them to prune the PITCH paragraphs only. The W0.5 **nominate** hook
  (`nominated_sections`, :236/:241) lets the model ask for a pruned pitch section and the front end re-adds it —
  the exact mechanism a tree needs for "I want a mechanic you did not detail".

### 2.2 The vocabulary tree (BH-3) — index for everyone, detail for what this forge selected

Design, all in `gate.py` so the card tier and the design tier share one parser:

1. **`gate.vocab_index(vocab_text) -> str`** — a deterministic one-line-per-token index built FROM VOCABULARY.md
   (never a hand-kept copy, so a new row shows up automatically): for every op / status / condition / trigger kind
   / scale source / keyword row, `` `token` — <first clause of its meaning, ≤ 12 words> ``, grouped under the file's
   own `## ` headings, class-only tokens tagged `[orb]` / `[status]` / `[summon]` / `[forge]`. Target ≤ 6k chars.
   Unit-test that every backticked token `catalog.live_vocab_tokens()` finds in VOCABULARY.md appears in the index.
2. **`gate.vocab_detail(vocab_text, tokens, kinds, *, keep_potion=True) -> str`** — the FULL rows for `tokens`,
   plus the prose that gives those rows meaning: the section intro paragraphs of any section that contributed a
   row ("Effect order is a design lever", the Triggers / Conditions / Scaled-amounts intros), the class-identity
   sections (`SECTION_FAMILY`) for kinds the class owns, and ALWAYS `## The signature potion` (the blueprint
   declares the potion). Closure rule: selecting any op of a `FAMILY_OPS` family pulls the whole family (e.g.
   `spend_forge` → `forge`, `forged_ge`, `summon_blade`); an `add_trigger` selection pulls the trigger-kind rows;
   a `scale` selection pulls the scale-source rows. Reuse `_split_op_table`'s row regex; do not restructure
   VOCABULARY.md (`test_exemplars.vocab_ops`, `catalog.live_vocab_tokens`, the card gate all parse it).
3. **Token selection for the design call** = `selected_ops` (chosen archetypes' `vocabulary.ops`) ∪ `CORE_OPS` ∪
   the tokens `frontend/request.py` (explicit-request check) names for this request ∪ the rows of any
   `nominated_sections` kind ∪ family closure. Everything else is index-only.
4. **Layout (cache-safe, the card-gate rule):** `[fixed head + translation paragraph + INDEX + schema pointer]`
   identical for every forge → `[pruned archetype pitches]` → `[VOCABULARY DETAIL for this forge]` → `[task]`.
   Put the index BEFORE the pruned pitches so the cached prefix is as long as possible. Mark the detail block
   with a header like the card gate's `ADDON_HEADER` and a pointer in the head ("the full rules for the mechanics
   this class selected are under VOCABULARY DETAIL at the end; the index above lists every other mechanic by name;
   to use one of those, nominate it").
5. **Nominate tokens, not just sections.** Extend the W0.5 contract: the blueprint JSON may carry
   `nominate_ops: [...]` (tokens from the index). `frontend/builder.py` re-issues the design call ONCE with those
   rows added to the detail block (same retry shape as `nominated_sections`). Log `[tree] nominated <tokens>`; if
   more than ~20% of forges nominate, the selection rule in step 3 is too narrow — widen it, don't drop the tree.
6. **Switch + rollback:** `BTS_BLUEPRINT_VOCAB = tree | full` (default `tree` once BH's tests are green; `full` is
   byte-identical to today's prompt, the `BTS_VOCAB_GATE=off` idiom). The legacy one-shot paths
   (`cli_forge_class.py:117/132`, `ollama_mix.py:551`) pass no `selected_ops` and keep `full`.
7. **Card-side hygiene stays:** every new op of this wave is appended to `GATED_OP_ORDER` (:108) or a `FAMILY_OPS`
   family, otherwise it lands in the card core and every card pays for it.

**Expected size:** index ~5k + detail for a typical 2–3-archetype class ~12–20k, versus the 62.7k paste today:
the design prompt drops from ~108k to roughly 50–60k, and later waves add ~80 chars per row to the shared part.

### 2.3 Repoint the rule-0.9 tests at the real prompt (same commit as 2.2)

- Keep the untrimmed reading as an INFORMATIONAL print (it is the `full` rollback path), not an assert.
- Asserts, all on `BTS_BLUEPRINT_VOCAB=tree` and `harness_v2.enabled()` (revised 2026-10-04, Ryan):
  (a) `vocab_index` ≤ 8,500 chars (`BP_INDEX_CEILING` = `gate.INDEX_BUDGET`; the adaptive clause cap stays the
  safety net); (b) for EVERY archetype in `data/archetypes.json` alone (`selected_ops` = its ops, its `class_kind`),
  the design prompt ≤ 70,000; (b2) three fixed sample triads — normal (`retain_hold`+`poison_attrition`+
  `block_bulwark`), orb (`orb_channel`+`slot_machine`+`tempo_draw`), hybrid orb+status (`orb_channel`+
  `status_signature`+`debuff_expose`), built as the BH dry run builds them — each ≤ 80,000 (`BP_TRIAD_BUDGET`);
  (c) the all-ops path (`selected_ops` = every archetype's ops, nothing pruned) ≤ `BP_TOTAL_TRIPWIRE` 140,000 —
  the only synthetic assert (raised from 120,000 on 2026-10-04 at 117,639: the real guards are (b) and (b2));
  (d) scaffold = prompt minus index minus detail block (measured from the block markers) ≤ 32,000 (`BP_SCAFFOLD_BUDGET_PER_ARCHETYPE`) for EVERY archetype
  alone, its pitches pruned as production prunes them; the all-ops scaffold is an INFORMATIONAL print
  (`BP_TREE_READING_SCAFFOLD` is its recorded reading, not a snapshot assert); (e) the `full` path is
  byte-identical to today's prompt (`BP_READING_SCAFFOLD` exact snapshot).
- Fix `test_wave0_prompts.py:63-105`: the ALSO-AVAILABLE line must stop naming pool kinds whose rows are now
  index-only (it may name them as "in the index"). `test_phase_aw.py:146-160` (hybrid keeps ORB + STATUS pitch
  sections) gets a detail-block analog. New tests: an orb-kind blueprint's detail has `## Orbs` + the `channel_orb`
  row and a normal-kind one has neither; the potion section is present for every kind; `nominate_ops:["doom"]`
  re-issues with the `doom` row present; every archetype's own ops appear in full in its detail block.

---

## 3. Phases

Ordered by (base-card coverage × generality) / cost, with the budget prep first.

### Phase BH — Prep: v0.3.0 shipped, test audit, gap entries, the vocabulary tree (no vocab bump; ~1½ days)

- **BH-0 Release v0.3.0 (wave 5) — DONE 2026-10-01** (commit e84f613; zip on the droplet, Workshop item updated,
  deploy healthy, `/download` serves v0.3.0). Recipe recorded in §4. One lesson for §4: an EMPTY `previews/` folder
  makes the uploader delete every preview on the item — remove the folder entirely or fill it with all real
  images (<1 MB each); the three screenshots were restored as JPEGs the same day.
- **BH-1 Test audit — a full pass over `generation/tests` (551 tests) and `web/tests` (289) against what BTS does
  today.** Write the findings + fixes to `docs/plans/TEST_AUDIT_2026-10.md` and fix in the same commit(s):
  1. Run both suites; fix the known stale set first (`test_phase_aq/as/ba` grep `web/static/app.js` for code that
     lives in `render.js` since the web refactor — `potionLines` is `render.js:253`, `effPhrase` :527, `condCore` :497).
  2. Grep every test for file paths, symbols, line-anchored comments and prompt wording that no longer exist
     (`case "op":`, `app.js` renderers, `_system_prompt_v1`-era strings, old archetype ids, `MODEL_PRICES` zeros,
     `BTS_HARNESS_V2` assumptions). Repoint or delete; never skip-mark.
  3. Rule 0.10 sweep: every `test_phase_*.py` must expose `test_phase_<xx>_all()` calling `main()` (AX/AY only
     exposed `test_version`, so their real checks never ran under pytest). Add the wrapper where missing and fix
     whatever those checks then reveal.
  4. Tests that measure a code path production no longer sends: the rule-0.9 trio (repointed in BH-3), and any
     test building prompts with `harness_v2` off / `BTS_VOCAB_GATE=off` as if that were the live path — keep those
     as rollback-path tests but label them so, and add the live-path twin where missing.
  5. Environment pins: tests that depend on droplet-only env (`BTSWEB_ADMIN_EMAILS`, `BTS_VOCAB_GATE`,
     `BTS_HARNESS_V2`, model/price tables) must set it explicitly; a test that passes only because of a developer's
     shell is a bug.
  6. Coverage of what changed since the tests were written: the pricing v3 tiers + Stripe fee, the two-model BYOK
     split, the admin panel's 4-hour sign-in rule, the magic-link auth, `/workshop` redirect + download-page version
     read, the hosted route (Ollama primary + cost gate), the stub-provider retry pinning, the explicit-request check,
     site-traffic reporting. Each needs at least one live-path test or a written "not testable offline, smoke by X".
  7. The gap-tester folders the plans cite (`generation/scratch/gaptest-bb..bf`) are not in this checkout; note it,
     and make each new phase's tester self-contained (`build_tester.py` + its saved tag grep).
  8. C# has no test project: the AutoSlay smoke is the only engine test. State that in the audit; the per-phase
     tags (rule 0.3) are the engine's regression record, so every phase's test must grep its tags file into the
     repo (`generation/scratch/gaptest-<xx>/godot_<XX>_tags_<SEED>.txt`).
  Exit bar: both suites green, no test asserts a dead path, the audit doc lists what is covered only by smokes.
- **BH-2 Gap entries.** Append `### 62.`–`### 79.` to `VOCABULARY_GAPS.md` per §3's table below (Status `planned`),
  plus the deferred set as `captured` (§6). Re-triage `### 11.` (stun) from `rejected` to `planned` — its own re-open
  condition ("if a stun primitive is ever scouted") is met: `CreatureCmd.Stun` exists and `Whistle` uses it.
- **BH-3 The vocabulary tree + repointed budget tests** (§2.2 + §2.3). One commit, the new readings in the message
  (index size, per-archetype max, all-ops path, scaffold). Verify end-to-end with one live-shaped dry run:
  `uv run btsgen-forge-class` (or the staged front end's dry-run) on a normal, an orb and a hybrid request with
  `BTS_BLUEPRINT_VOCAB=tree`, confirming the detail block holds exactly the selected rows and the `[tree]` log line.
  Do NOT deploy it in isolation — it ships with the wave's web deploy (§4), after the mod.
- **Test:** `tests/test_phase_bh.py` (tree unit tests, nominate round-trip, the §2.3 asserts, the audit's exit bar as
  a checklist printed by `main()`). No tester, no smoke.

| gap | mechanic | phase |
|---|---|---|
| #62 | Card trigger filters: `card_type` / `every_n` / `scope:"this_turn"` / payload `random_enemy` | BI |
| #63 | Combat-history scales + `draw` to hand size + `gain_energy scale:"energy"` | BJ |
| #64 | Conditions `exhausted_this_turn` / `played_cards_last_turn_ge` / `target_intends_attack` | BJ |
| #65 | `hits_scale` (scaled hit counts, X-cost hits) | BK |
| #66 | Enemy Strength loss (`temp_strength_down` / `strength_down`) + `strip_block` / `strip_artifact` | BL |
| #67 | `doom` debuff (+ Doom = unblocked damage) | BL |
| #68 | Self-drawback statuses (`no_draw` / `no_energy_gain` / `no_block` / `dex_decay` / `focus_decay` / `lose_*`) | BM |
| #69 | Replay: `replay_next` + `echo_form` | BM |
| #70 | `block_next_turn` + `retain_hand` | BM |
| #71 | On-kill payoff: `when target_killed` | BN |
| #72 | `add_random_card` (random generation from the class pool, choose-1-of-N, free this turn) | BN |
| #73 | `autoplay` (play the top / a random card of your draw pile) | BN |
| #74 | Self-routing recursion (`return_to_hand` / `to_draw_top` / `return_next_turn`), `put_back`, draw-pile `retrieve_card` / `exhaust_card`, trigger `on_shuffle` | BO |
| #75 | `grant_keyword` (Retain / Ethereal / Sly to a chosen card) | BO |
| #76 | Self cost modification `cost_delta` | BP |
| #77 | Triggers `on_card_generated` / `on_debuff_applied` (+ payload target `that_enemy`) / `on_evoke` | BP |
| #78 | Orb extras (evoke keep/newest, `trigger_passive`, `loop`, `lose_orb_slot`, `orb_count` / `orb_types` scales, `per_enemy` channel) | BQ |
| #79 | `discard cards:"all"` + `scale:"cards_removed"`; `turn_start` payload `damage` with `grow` | BR |
| #11 | Stun (re-opened) | BR |

### Phase BI — Card trigger filters (v61; gap #62; ~1 day) — audit "partial" rows, 11 base cards

Port the relic v48 hook filters to card `add_trigger`. Base: `RagePower` (Attack-filtered, removed at own turn end),
`PanachePower` / `JugglingPower` (every N), `IterationPower` (first Status drawn), `JuggernautPower` (random target).

**Engine.** Copy `RelicRunner.Fire` (:28; `CardType` filter + `every_n` counter, `[AS]` tags) into
`ForgedTriggerPower.FireReactive` (:233) with a `string? cardType` param; `AfterCardPlayed` (:166) / `AfterCardDrawn`
(:176) already hold the card — map type as `ForgedRelic.AfterCardPlayed` (:207) does; `EffectRunner.HandKindMatches`
(:663) gains `"status" => c.Type == CardType.Status`. `every_n` counter = instance field (fresh power per combat),
counting PER COMBAT (relic parity; base Panache counts per turn — open decision 1); when `every_n > 1`, `StackType`
→ `Counter` so the icon shows the count (the BG ripen trick, :59/:63). `scope:"this_turn"` → in `AfterSideTurnEnd` (:72)
`PowerCmd.Remove(this)` (DECOMP `PowerCmd.cs:288`) copying `RagePower.AfterSideTurnEnd`. Payload `random_enemy` →
`TriggerRunner.ResolveEnemies` (:274) via `Owner.Player.RunState.Rng.CombatTargets.NextItem(hittableEnemies)`.
`ForgedCards`: parse `every_n` next to `count` (:1018) into a new `EffectSpec.EveryN` (`CardSpec.cs:81-89`); widen
the stray-field rules at :1070 (`scope`) and :1073-1076 (`card_type`) to `add_trigger`; `HandKindFilters` (:561) +=
`status` for `on_card_drawn` only; `MultiFireTriggers` (:474) is the `every_n` legality set; `ValidateTrigger` (:1683)
allows `random_enemy`; reject `every_n` + `once_per_combat`.
**Shape / describe (lockstep `TriggerSentence` :2098 ↔ `cardgen.trigger_sentence`):** heads "Whenever you play an
Attack" / "a Skill" / "a Power" / "a non-Attack card" / "Whenever you draw a Status"; "Every 3rd time you play an
Attack" / "Every 5th card you play"; prefix "This turn, whenever you play an Attack, gain 3 Block."; payload `to`
" to a random enemy" (`TriggerFragment` :2141).
**Validator:** `card_type` legal on `on_card_played` / `on_card_drawn` only; `every_n` 2..9 on multi-fire kinds;
`this_turn` only on reactive kinds (never `turn_start`/`ripen`); price every-N payloads at `amount / n`.
**Harness:** `power_ramp` + `strike_tempo` gain the tokens; `_PREFERRED_TRIGGERS` unchanged; `gate.FIELD_UNITS` +=
`every_n`; coverage `REACTIVE_MENU_V2` unchanged (filters are fields, not kinds); exemplars for all three forms.
**Budget:** 3 VOCABULARY touch-ups (the `add_trigger` row + Triggers prose), per-archetype scaffold ≤ 32k; keep pitch
additions to a sentence.
**Open decisions:** (1) per-combat vs per-turn `every_n` (default per-combat); (2) `StackType Single` means a second
Rage in one turn does NOT double the payload — accept and price, or multiply payload by `Amount` for `this_turn` powers
(default accept); (3) self-trigger: the granting card's own play counts toward its filter (already true today) — leave.
**Test:** `tests/test_phase_bi.py`. **Tester** `generation/scratch/gaptest-bi/build_tester.py`: Rage-style power
(Attack filter, this_turn), "every 3rd Attack → 4 damage to a random enemy", Iteration (Status drawn, with
`add_status_card` fuel). **Tags:** `[BI] card_type <kind> matched`, `[BI] every_n count n/N — waiting|FIRES`,
`[BI] this_turn trigger removed`, `[BI] random_enemy payload -> <monster>`.
**Findings (BI, done 2026-10-02 on `wave6`):** (1) `every_n` and `scope:"this_turn"` are legal on the POWER-HOSTED
reactive kinds (`OncePerCombatTriggers`), not all of `MultiFireTriggers`: the card-latent `on_discard` has no power
instance to hold the counter or remove itself. (2) `status` went into a separate `TriggerCardKinds` set, not
`HandKindFilters` (that would have let `exhaust_card` / `draw_until` take `status`). (3) The tester + tag greps live
in `generation/tests/gaptest-bi/` (TEST_AUDIT §7). (4) GAPTESTBI1 stalled after the base merchant threw "There is no
item to purchase" (one non-basic Attack/Skill in the pool; no mod frame); the tester gained two pool fillers and
GAPTESTBI2 completed the run. All four tags fired on both seeds; 0 mod exceptions, 0 localization errors. (5) Rule
0.9: the `full` scaffold snapshot was re-taken (+136, the TRIGGERS pitch sentence); readings index 5,924 ·
per-archetype max 62,512 (`forge_ramp`) · all-ops 113,349 · scaffold 45,925 / 46,000. Defaults 1-3 of §7 taken.

### Phase BJ — Combat-history scales + conditions (v62; gaps #63, #64; ~1½ days) — ~25 base cards

**Scales (A2).** `EffectRunner.ScaleValue` (:1040-1056) is the single source of truth; `DataCard.BonusFor` (:59-73)
picks new player-level branches up for free; per-target reads copy `target_debuff_count` (`DataCard.cs:68` →
`EffectRunner.DebuffCount` :1145). Each has a verbatim base recipe (`CombatManager.Instance.History.Entries.OfType<T>()`):

| scale | base recipe | ops |
|---|---|---|
| `exhaust_pile_size` | `AshenStrike`: `PileType.Exhaust.GetPile(owner).Cards.Count` | damage/block/draw |
| `discard_pile_size` | `Stack` | damage/block |
| `discards_this_turn` | `MementoMori`: `CardDiscardedEntry` + `HappenedThisTurn` (effect discards only — matches base) | damage/block |
| `cards_drawn_this_turn` | `DeathMarch`: `CardDrawnEntry`, `!FromHandDraw` | damage/block |
| `cards_drawn_this_combat` | `Murder` | damage |
| `energy_spent_this_turn` | `HelixDrill`: `EnergySpentEntry.Amount`, **minus this card's own cost while in the Play pile** (preview == resolve) | damage/block |
| `hp_loss_events_this_combat` | `TearAsunder`: `DamageReceivedEntry.Result.UnblockedDamage > 0` | damage |
| `cards_generated_this_combat` | `Supermassive`: `CardGeneratedEntry.Creator` | damage/block |
| `total_enemy_poison` | `Mirage`: sum `GetPowerAmount<PoisonPower>()` over living enemies | damage |
| `target_status_stacks` + `status` (vulnerable/weak/poison/doom) | `Bully` / `TimesUp`: `target.GetPowerAmount<T>()` — per-target calc-var, single-enemy only, damage/block | damage/block |
| `energy` on `gain_energy` | `DoubleEnergy`: `PlayerCmd.GainEnergy(PlayerCombatState.Energy, Owner)` — `DataCard.cs:174` skips `WithEnergy` when scaled; narrow the cost-0 rule (:843) to damage/block/draw | gain_energy |
| `to_hand_size` on `draw` (`amount` = target size) | `Expertise`: `Math.Max(0, N - Hand.Count)`; keep `WithCards` so `{Cards}` prints; `VarKey` (:1873) → `Cards` | draw |

All replace-semantics (ours), damage/block-only, card-only (not in `TriggerScales` :622) except `total_enemy_poison`
/ `exhaust_pile_size` (pure player reads, payload-legal). Base `Murder` / `MementoMori` are `base + N×count`; an
additive form is a follow-up (open decision 4). `ScalePhrase` (:1912) nouns: "the cards in your exhaust pile", "the
cards you have discarded this turn", "the energy you have spent this turn", "the total Poison on ALL enemies", "the
enemy's {Status}" …; "Double your energy."; "Draw cards until you have {Cards} in hand."
**Conditions (A3, player/target reads only).** `Conditions.cs` `Kinds` (:23-33), `TargetKinds` (:39), `Eval` (:101-157),
`Phrase` (:171-195): `exhausted_this_turn` (`EvilEye`: `CardExhaustedEntry` + `HappenedThisTurn`),
`played_cards_last_turn_ge {value}` (`PaleBlueDotPower`: `CardPlaysFinished` + `HappenedLastPlayerTurn`),
`target_intends_attack` (`MonsterModel.IntendsToAttack` :384 → `target?.Monster?.IntendsToAttack ?? false`; in
`TargetKinds` so single-enemy-only + no-trigger rules apply automatically). Phrases: "you have Exhausted a card this
turn" / "you played {N}+ cards last turn" / "the enemy intends to attack". Lockstep `class_forge._ORB_CONDITION_KINDS`
(:2099) + `_cond_uptime` + `render.js condCore` + `test_phase_ar` set equality.
**Validator:** per-scale op rules at `ForgedCards.cs:1100-1145` (+ `validator.py` mirror); `status` field now legal on
damage/block when `scale:"target_status_stacks"` (check the schema `if/then` at :68); price unbounded counts
(`cards_drawn_this_combat`, `hp_loss_events_this_combat`) as late-game payoffs.
**Harness:** `SCALE_MENU` / `SCALE_MENU_KIND` + samples; archetypes: `exhaust_pyre` (exhaust pile), `madness_discard`
(discards), `tempo_draw` (drawn), `big_energy` (energy spent, double energy), `poison_attrition` (total poison),
`debuff_expose` (target stacks), `countdown_ripen` / `ambush_alpha` (intent gate); `WHEN_MENU_V2` += the 3 kinds.
**Budget:** this is the biggest VOCABULARY delta of the wave (~12 scale rows ≈ 1.5k + 3 condition rows). Fold the
scales into ONE table row group under Scaled amounts rather than one row each; per-archetype scaffold ≤ 32k; keep
pitch additions to a sentence.
**Test:** `tests/test_phase_bj.py`. **Tester** `gaptest-bj`: one card per scale (exhaust/discard fuel in the deck),
Expertise, Double Energy, Evil Eye, Go for the Eyes. **Tags:** `[BJ] scale <name> -> <n> ('<card>')` via
`PhaseAmScales` (:1059) membership, `[BJ] draw to_hand_size: hand <h> -> draw <n>`, `[BJ] gain_energy x energy`, the
`[AM]` gate line for the conditions.
**Findings (BJ, done 2026-10-04 on `wave6`):** (1) `target_status_stacks` reads vulnerable / weak / poison only — Doom
does not exist until Phase BL (add it to `StatusStackStatuses` + the schema `if/then` there). It is single-enemy only
(target `enemy`), damage/block. (2) `energy_spent_this_turn` clamps at 0: the base HelixDrill recipe subtracts the
card's cost while it sits in the Play pile even when nothing was paid (AutoPlay / Sly), which would go negative.
(3) `to_hand_size` takes `amount` 2..10 (the target hand size); `gain_energy` + `scale:"energy"` is legal at any cost
(the cost-0 rule now covers damage/block/draw only). (4) Pricing: `cards_drawn_this_combat` / `hp_loss_events_this_combat`
damage is scored at an expected 18 / 8 (late-game payoffs); `total_enemy_poison` is damage-only like the plan says
(Mirage itself is Block). (5) VOCABULARY: the eleven new scale tokens are ONE bullet (index lists them by name);
`exhaust_pyre` also claims `exhausted_this_turn`, `poison_attrition` also claims `scale`; `played_cards_last_turn_ge`,
`hp_loss_events_this_combat` and `cards_generated_this_combat` belong to no archetype yet (index-only).
(6) Smoke (tests/gaptest-bj, 25-card deck): GAPTESTBJ1 completed the run (max floor) — every [BJ] scale tag fired with
non-zero values (incl. the payload `exhaust_pile_size`), `energy_spent_this_turn` read 0 on 20 of 22 plays (AutoSlay
spends nothing; 2 non-zero reads), all three cond tags opened `true`; 0 mod exceptions, 0 localization errors.
GAPTESTBJ2 completed the run too — every scale non-zero except `energy_spent_this_turn` (0 on all 41 reads: the AutoSlay limit, the READ is proven), all three conds true; 0 mod exceptions, 0 localization errors. One build, one smoke pass per seed (no iteration needed).

### Phase BK — `hits_scale` (v63; gap #65; ~1 day) — 24 base cards (Finisher, Flechettes, Whirlwind, Skewer …)

**Engine.** New `EffectSpec.HitsScale` (`string?`). `DataCard.DeclareEffects` (:164): `WithCalculatedVar("CalculatedHits",
0, (c, t) => EffectRunner.ScaleValue(e.HitsScale, c))` — BaseLib's named calc-var (`BL/Abstracts/ConstructedCardModel.cs:152`)
does NOT trip `_hasBasegameCalculatedVar`, so it coexists with `CalculatedDamage`. `EffectRunner.cs:99`: `hits =
Math.Min(HitsScaleCap, (int)((CalculatedVar)card.DynamicVars["CalculatedHits"]).Calculate(play?.Target))`; 0 hits →
log and skip (`WithHitCount(0)` is a clean no-op but don't swing). `x` → `ScaleValue("x")` = `ResolveEnergyXValue()`
and joins the X coupling (`TryBuildSpec` :834-838 `anyX`). Lift the `hits`+`scale` rejection (:1143, payload ~:1732)
only for `hits_scale`; `hits_scale` counts as THE card's one multi-hit (:1413). **Runtime cap 10, logged** (no cap exists
today; `plays_this_combat` can reach 20+ hits → animation time + AutoSlay timeout).
**Sources v1:** `x`, `cards_in_hand`, `plays_this_combat`, new `attacks_played_this_turn` (`Finisher`:
`CardsPlayedThisTurn` + `Type == Attack`), `skills_in_hand` (`Flechettes`), plus BJ's `exhaust_pile_size` /
`hp_loss_events_this_combat` / `energy_spent_this_turn`, and `orb_count`.
**Describe:** x → "Deal {Damage} damage X times{suffix}."; others → "Deal {Damage} damage for each {noun}{suffix}."
(`HitsPhrase` table: "Attack you played this turn", "other card in your hand", "card in your exhaust pile" …).
**Validator:** mutually exclusive with `hits`, `scale`, `grow`, `grow_held`; upgrades touch per-hit damage only; price
at expected count (x: ~2.5; attacks_this_turn: ~2; cards_in_hand: ~3; exhaust pile: late-game).
**Harness:** `strike_tempo` (Finisher), `big_energy` / `horde_breaker` (Whirlwind, Skewer); `gate.FIELD_UNITS` +=
`hits_scale`; `census` field counter; `bridges.card_tokens`; one `SCALE_MENU` line mentions it.
**Test:** `tests/test_phase_bk.py`. **Tester** `gaptest-bk`: Whirlwind (X, all_enemies), Finisher, Flechettes, an
exhaust-pile ripper. **Tags:** `[BK] hits_scale <src> -> <n> hits (cap <c>) x <dmg> from '<card>'`.

### Phase BL — Enemy Strength loss, strip, Doom (v64; gaps #66, #67; ~1½ days) — 24 base cards

**Strength loss (A5).** `StrengthPower` is `AllowNegative => true`, `GetTypeForAmount` makes a negative apply read as a
Debuff (so Artifact blocks it — correct). Temporary: `Powers/ForgedTempStatPowers.cs:26` already has the
`CustomTemporaryPowerModel` shell with `InvertInternalPowerAmount` built in — add `ForgedTempStrengthDownPower`
(`InternallyAppliedPower => StrengthPower`, `InvertInternalPowerAmount => true`, **`public override PowerType Type =>
PowerType.Debuff` — MANDATORY**: if the shell stays a Buff, Artifact eats only the inner −N and the shell restores +N at
turn end, so an Artifact enemy GAINS Strength; base `PiercingWailPower` is a Debuff for this reason). Removal at the
OWNER's side-turn end = the enemy's turn end (the right window). Permanent: **do NOT reuse `Power<StrengthPower>`**
(it applies the card's positive PowerVar and collides with a self-`strength` on the same card) — declare
`WithVar("StrengthLoss", amt, up)` and apply literally via the `RelicApplyT<StrengthPower>(ctx, target, owner, -amt)`
idiom (`EffectRunner.cs:174-182`). `strip_block` / `strip_artifact`: flag ops over `CustomStatusTargets` (:1225) —
`CreatureCmd.LoseBlock(t, t.Block)` (`CreatureCmd.cs:666`), `if (t.HasPower<ArtifactPower>()) PowerCmd.Remove<ArtifactPower>(t)`
(`PowerCmd.cs:279`); single-target only (`target:"enemy"`, like `spread_debuffs`); card-only; put them BEFORE the
debuff in effect order (the `Expose` order).
**Doom (A6).** `DoomPower` is sealed, concrete, generic (no Necrobinder state): kills at `BeforeSideTurnEnd` when
`CurrentHp <= Amount`, never decays, respects `ShouldDie` / bosses. Copy `poison` at every site: `DataCard`
`Power<DoomPower>`, `ApplyStatus` (:1228) / `TriggerRunner.ApplyDebuff` (:285) / `RelicApply` (:1517),
`EnemyDebuffStatuses` (:509), `SupportedStatuses` (:510), `StatusDisplay` (:1890), `Conditions.StatusChecks` (:47) +
`TargetHasStatus` (:160), `DebuffCount` (:1145) + `SpreadDebuffs` (:1101, optional), schema status enum. Doom = damage
dealt (`BlightStrike`): widen `damage_dealt_unblocked` (heal-only today, :1107-1110 / :194) to `apply_status
status:doom` via the literal `RelicApply` with `unblockedDealt`. `target_status_stacks status:doom` comes from BJ.
**Shape / describe:** `apply_status temp_strength_down 6` → "Apply Strength Down." (tooltip "Loses {N} Strength until
the end of its turn."); `strength_down 2` → "The enemy loses {StrengthLoss} Strength." / "ALL enemies lose …";
`strip_block` → "Remove all of the enemy's Block."; `strip_artifact` → "Remove the enemy's Artifact."; `doom 7` →
"Apply Doom."; "Apply Doom equal to the unblocked damage dealt."; condition phrase "the enemy has doom".
VOCABULARY row for doom: "If the target's HP is at or below its Doom at the end of ITS turn, it dies. Doom never decays."
**Validator:** Doom pricing band (never decays = guaranteed execute; the enemy still acts once): cap per card 12,
per class ≤ 4 doom cards, rare for amounts ≥ 10; `strength_down` ≤ 3 permanent / ≤ 9 temporary; decide whether
Strength Down counts for `spread_debuffs` / `target_debuff_count` (default: yes, like base Misery).
**Harness:** `block_bulwark` / `debuff_expose` / `untouchable_ward` (Strength loss); `reaper_lifesteal` / `debuff_expose`
/ `countdown_ripen` (Doom) — or a new `doom_reaper` archetype (needs a `mechanic_kind` from `_pool_kind`'s fixed set;
`buildable:false` until #67 flips). `EXOTIC_STATUSES` (:51) += the new statuses.
**Test:** `tests/test_phase_bl.py`. **Tester** `gaptest-bl`: Piercing Wail (all_enemies temp), Malaise (permanent),
Expose, a Doom stacker + Time's Up, **an Artifact-enemy check** (seed through an act-1 Artifact monster or inject
`artifact` on an enemy via a `turn_start` payload test card — the sign-flip is the wave's biggest correctness risk).
**Tags:** `[BL] temp_strength_down +N on '<monster>' (Str now <s>)`, `[BL] temp_strength_down expired`, `[BL]
strength_down -N`, `[BL] strip_block <b>->0`, `[BL] strip_artifact (had <n>)`, `[BL] doom +N on '<monster>' (HP <hp>,
Doom <d>, doomed=<bool>)`.

### Phase BM — Base-power statuses: self-drawbacks, replay, next-turn Block, retain hand (v65; gaps #68–#70; ~1 day) — 30 base cards

All of these are **sealed, concrete base powers that ship their own loc + icon**, applied through the Phase-BF
`apply_status` pipe (`DataCard.cs:234-262`, `EffectRunner.ApplyStatus` :1228, `SelfBuffStatuses` :1005,
`TriggerRunner.ApplySelfBuff` :302, `SupportedStatuses` :510). No new power classes except one 15-line decay power.

**Self-drawbacks (A7, gap #68).** New `EffectRunner.SelfDebuffStatuses` set routed to the player (`self =
SelfBuffStatuses ∪ SelfDebuffStatuses`; the relic-only `ApplyRelicStatus` self-debuff path (:1497) is the precedent but
cards have NO self-debuff route today — negative `apply_status` is impossible, :1051 requires amount ≥ 1):

| status | base power | semantics | base card |
|---|---|---|---|
| `no_draw` | `NoDrawPower` (Single; removed at own turn end) | "You cannot draw additional cards this turn." | BattleTrance, BulletTime |
| `no_energy_gain` | `NoEnergyGainPower` | "You cannot gain energy this turn." | ExpectAFight |
| `no_block` | `NoBlockPower` (Counter = turns; zeroes CARD Block only) | "You cannot gain Block from cards for {N} turns." | PanicButton |
| `dex_decay` | `WraithFormPower` | "At the start of your turn, lose {N} Dexterity." | WraithForm |
| `focus_decay` | `BiasedCognitionPower` | "At the start of your turn, lose {N} Focus." | BiasedCognition |
| `lose_strength` / `lose_dexterity` / `lose_focus` | literal negative apply (named var `"StrengthLoss"`-style + `RelicApplyT<T>(self, -amt)`, the BL rule) | "Lose {N} Strength." | Friendship, SharedFate, Hyperbeam |

(`str_decay` has no base power; a forged copy of `WraithFormPower` is ~15 lines if wanted.) **`end_turn` (VoidForm:
`PlayerCmd.EndTurn(Owner, canBackOut:false)`) is NOT in this phase — needs an AutoSlay spike (§6).** Bespoke describe
sentences (the "Gain X." idiom misreads). Validator: price like `lose_hp` (negative value); `no_draw` requires a draw
or energy payoff on the same card; note in `DESIGN_HEURISTICS` that your own Artifact eats these.
**Replay (B2, gap #69).** Op `replay_next {card_type: skill|attack|power|all, count: 1..2}` = sugar over
`BurstPower` (Skill, own turn end) / `OneTwoPunchPower` (Attack) / `SignalBoostPower` (Power, persists until used) /
`DuplicationPower` (any; rare-only), applied with amount = count. `echo_form` = `apply_status` of `EchoFormPower`
(Power card, rare, amount 1). Describe: "This turn, your next 2 Skills are played twice." / "Your next Power is played
twice." / "The first card you play each turn is played twice." Replays re-run `EffectRunner.Execute` whole — every
side-effect op is safe (purge/transform DeckVersion guards, pickers auto-pick, `add_trigger` Single-stack,
`spend_forge` spends twice by design); `ForgedCostShiftPower.AfterCardPlayed` (:152-180) burns a budgeted use per
replay — accept and note, or skip when `cardPlay.PlayIndex > 0`. Not a payload.
**`block_next_turn {amount | scale:"block"}` (gap #70)** = `BlockNextTurnPower` (`AfterBlockCleared` → GainBlock →
Remove); fixed amount via the status pipe, the `scale:"block"` form is an op (apply_status doesn't scale) applied via
`BetaMainCompatibility.PowerCmd_.Apply.InvokeGeneric` (`TriggerRunner.cs:326`). "Next turn, gain 8 Block." / "Next turn,
gain Block equal to your current Block." **`retain_hand`** = `RetainHandPower` (self-buff, amount 1): "Retain your hand
this turn."
**Harness:** `self_sacrifice` / `big_energy` / `burst_window` (drawbacks); `burst_window` / `power_ramp` (replay);
`block_bulwark` / `retain_hold` (block_next_turn, retain_hand). `EXOTIC_STATUSES` += all; `KEYWORD_MENU` unchanged.
**Budget:** 5 status rows + 3 op rows ≈ 2k — the second-biggest delta; keep status rows to one line each.
**Test:** `tests/test_phase_bm.py`. **Tester** `gaptest-bm`: Battle Trance, Panic Button, Wraith Form, Burst + a
2-Skill hand, Echo Form power, Prolong, Equilibrium. **Tags:** `[BM] self-debuff <status> +N on player (Artifact <a>)`,
`[BM] replay_next <kind> x<n>` (in `ApplyPowerLogged` :1266) + `[BM] replay play #2 of '<card>'` (from
`DataCard.BeforeCardPlayed` when `play.PlayIndex > 0`), `[BM] block_next_turn +<n>`, `[BM] retain_hand`.

### Phase BN — On-kill, random generation, auto-play (v66; gaps #71–#73; ~1½ days) — 38 base cards

**`when target_killed` (A3, gap #71).** Cannot live in `Conditions.Eval` (no play-local state). `EffectRunner.Execute`
(:64): `bool killedThisPlay` beside `unblockedDealt`; after each damage op OR in
`atk.Results.SelectMany(r=>r).Any(r => r.WasTargetKilled && r.Receiver.Powers.All(p => p.ShouldOwnerDeathTriggerFatal()))`
(`DamageResult.WasTargetKilled` :99; `PowerModel.ShouldOwnerDeathTriggerFatal` :646 — minions / reattaching parts don't
pay out, as Feed does); gate at :72 special-cases the kind. Legal only on an effect AFTER a `damage` op (the
`damage_dealt_unblocked` ordering rule), never on `add_trigger` / trigger `when` / orb `when`. "Any kill" semantics
on AoE ("if this kills an enemy"; open decision 5). Phrase: "this kills the enemy" → "Gain 3 Max HP if this kills the
enemy."; negated "unless this kills the enemy". Reprice gated `gain_max_hp` (Feed-exact).
**`add_random_card` (B1, gap #72).** `{card_type?, pile, amount? (1..2), choose_of? (2..3), free_this_turn?}`. Pool =
`Owner.Character.CardPool.GetUnlockedCards(Owner.UnlockState, Owner.RunState.CardMultiplayerConstraint)` (forged pools
are `ForgedClassPoolKK`, `ForgedClasses.g.cs:30`; empty slots `autoAdd:false`); filter `HandKindMatches` +
`!dc.HasOp("add_random_card")` (depth-1 loop rule) + `CanBeGeneratedInCombat`; **guard `pool.Count == 0`** (else
`ReportSoftlock`); `CardFactory.GetDistinctForCombat(player, pool, n, rng)` (`CardFactory.cs:119`);
`choose_of` → `CardSelectCmd.FromChooseACardScreen(ctx, cards, player)` (`CardSelectCmd.cs:216`, **throws above 3**;
AutoSlay auto-picks 1); `SetToFreeThisTurn()` (`CardModel.cs:1266`); then `AddGeneratedCardToCombat` via the shared
`EffectRunner.AddCards` (:539). Payload form (`turn_start` only, Creative AI): no `choose_of`. Describe: "Add a random
Attack to your hand. It costs 0 this turn." / "Add 2 random cards to your discard pile." / "Choose 1 of 3 random Skills
to add to your hand. It costs 0 this turn."; payload fragment "add a random Power to your hand". Colorless source is
out of scope.
**`autoplay` (B7, gap #73).** `{from: draw_top|draw_random, amount? (1..2), card_type?}`. `draw_top` →
`CardPileCmd.AutoPlayFromDrawPile(ctx, player, n, CardPilePosition.Top, forceExhaust: true)` (`CardPileCmd.cs:933`;
Havoc semantics — **forced exhaust is mandatory**, a non-exhausting top-card loop cycles the deck forever);
`draw_random` → filter draw pile (`!Unplayable`, `card_type`), `StableShuffle(Rng.Shuffle)`, `CardCmd.AutoPlay(ctx, card,
null)` (`CardCmd.cs:51`; null target → random hittable enemy). **Static depth guard ≤ 3** (like
`DataCard._firingOnDiscard`); `autoplay` cards are never auto-play candidates. Payload form (`turn_start`, Mayhem) fires
from `AfterAutoPrePlayPhaseEntered` (`AbstractModel.cs:271`), NOT `AfterPlayerTurnStart`. Describe: "Play the top card
of your draw pile and Exhaust it." / "Play a random Attack from your draw pile." **No spike:** the AutoSlay bot itself
plays every card through `CardCmd.AutoPlay` (`CombatRoomHandler.cs:90`), so every smoke ever run has exercised the
path. Policy: this is an effect the player chose to play, not gap #37's "weapon overrides the player's choice";
forced-from-hand (Stampede/Hellraiser) stays rejected; Howl-from-Beyond exhaust self-replay stays deferred (#42/#43).
**Harness:** `reaper_lifesteal` / `horde_breaker` / `iron_regrowth` (on-kill); `token_conjurer` / `fleeting_flux`
(random generation); `madness_discard` / `big_energy` (autoplay — a new `chaos_havoc` archetype is cleaner, `buildable:
false` until #73 flips). `gate.GATED_OP_ORDER` += both ops; `FEATURED_MENU` entries for both.
**Test:** `tests/test_phase_bn.py`. **Tester** `gaptest-bn`: Feed, Sunder, Discovery, Infernal Blade, Havoc, Uproar,
a Creative-AI power. **Tags:** `[BN] target_killed gate OPEN|closed (killed=<b>, fatal=<b>)`, `[BN] add_random_card
<type> x<n> -> <pile> ('<titles>'; free=<b>; choose_of=<n>)` + grep `Auto-selected 1 card(s)`, `[BN] autoplay <from>
'<card>' -> <target|none> (depth <d>)`.

### Phase BO — Recursion, put-back, draw-pile tutor, `on_shuffle`, `grant_keyword` (v67; gaps #74, #75; ~1½ days) — 29 base cards

Every card in all five piles (Play included) is a hook listener (DECOMP `CombatState.cs:150-168`), so `DataCard` can
own these. **Each new override gets its own tag on day one (rule 0.3).**
**Flag-ops (one per card; exclusive with each other and with `exhaust` / `purge` / Power):** `return_to_hand` —
extend the existing `GetResultPileTypeForCardPlay` override (`DataCard.cs:396-397`; purge's `None` keeps precedence)
→ `Hand` (`ParticleWall`); needs cost ≥ 1 and no `gain_energy` / `draw` on the card (human infinite loop; the bot is safe
— it tries each instance once per turn). `to_draw_top` — override `ModifyCardPlayResultPileTypeAndPosition(card,
isAutoPlay, resources, pileType, position)` (`AbstractModel.cs:1488`) with `card == this` → `(Draw, Top)` (`ReboundPower`
pattern). `return_next_turn` — override `BeforeHandDraw` (`AbstractModel.cs:753`) copying `Bolas` (History
`CardPlaysFinished` + `HappenedLastPlayerTurn` + `card == this`) → `CardPileCmd.Add(this, Hand)`; guard `Pile.Type is
Discard or Draw` (never resurrect an exhausted/purged copy). Describe: "Returns to your hand after you play it." /
"Goes on top of your draw pile after you play it." / "At the start of your next turn, return this to your hand."
**`put_back {from: hand|discard, cards: choose, amount: 1}`** — hand/discard picker → `CardPileCmd.Add(card, Draw,
CardPilePosition.Top)` (`CardPileCmd.cs:259`); custom prompt via `CardLoc` ExtraLoc (rule 0.4). Optional flag-op
`shuffle_hand` (Reboot: Add all → `CardPileCmd.Shuffle` :866). "Put a card from your hand on top of your draw pile."
**`retrieve_card pile:"draw"` + `card_type`** — `CardSelectCmd.FromCombatPile(ctx, DrawPile, player, prefs, filter)`
(`CardSelectCmd.cs:381`); keep `Retrievable` (:620) AND `HandKindMatches`. `RetrievePiles` (:554) += draw; **this
reverses the documented "never the draw pile" rule (:550-553) on purpose — say so in the row.** "Put an Attack from your
draw pile into your hand." / "Put a random Skill from your draw pile into your hand."
**`exhaust_card pile: hand|draw`** (default hand; from draw: choose/random only) — `CardCmd.Exhaust` moves from any pile.
**Trigger `on_shuffle`** — `ForgedTriggerPower.AfterShuffle` override (`AbstractModel.cs:1139`) → `FireReactive`;
multi-fire + once_per_* eligible. "Whenever you shuffle your draw pile, …".
**`grant_keyword {keyword: retain|ethereal|sly, cards: choose, card_type?}` (B5, gap #75)** — hand picker (the
`GraftCard` / `PurgeChoose` path, `EffectRunner.cs:863-888, 947-997`) → `CardCmd.ApplyKeyword(card, kw)` (`CardCmd.cs:676`)
or `CardCmd.ApplySingleTurnSly(card)` (:698); filter cards that already have it (base Snap / HandTrick). "Choose a card
in your hand. It gains Retain." / "Choose a Skill in your hand. It is Sly this turn." Card-only.
**Validator:** `to_draw_top` + `corruption` on a Skill — forbid (hook order decides who wins); stun (BR) × recursion
loops cross-check.
**Harness:** `madness_discard` (discard recursion, grant Sly), `retain_hold` (put-back, grant Retain), `ascetic_purge`
(draw tutor), `exhaust_pyre` (exhaust from draw), `fleeting_flux` (grant Ethereal). `KEYWORD_OPS` += the three flags.
**Test:** `tests/test_phase_bo.py`. **Tester** `gaptest-bo`: Particle Wall, Bolas, Make It So, Headbutt, Secret
Weapon, Snap, a shuffle-payoff power with a thin deck. **Tags:** `[BO] return_to_hand '<card>'`, `[BO] to_draw_top
'<card>'`, `[BO] return_next_turn '<card>' <- <pile>`, `[BO] put_back <from> '<card>' -> draw top`, `[BO] retrieve
draw [<type>] '<card>'`, `[BO] on_shuffle fired`, `[BO] grant_keyword <kw> -> '<card>'`.

### Phase BP — `cost_delta` + small reactive triggers (v68; gaps #76, #77; ~1 day) — 24 base cards

**`cost_delta {on, amount, scope}` (B4, gap #76)** — a card FIELD like `held_discount` (card-only). `on` ∈ `played`
(self) | `drawn` (self) | `attack_played` | `skill_played` | `card_played` | `card_exhausted`; `amount` −2..+1 (+1 only
with `played`, Modded); `scope` `this_turn` | `combat`; `set_zero:true` with `played` = Momentum Strike
(`EnergyCost.SetThisCombat(0)`). **Two implementations:** stateless for the `*_played` this-turn forms —
`DataCard.TryModifyEnergyCostInCombat` computing `−count(History this turn)` (always correct, previews live, no
back-fill for generated copies, composes with `ForgedCostShiftPower` EARLY and Corruption LATE); mutating
`CardEnergyCost.AddThisCombat` / `AddThisTurn` / `SetThisCombat` (`CardEnergyCost.cs:175-319`, floor 0, X skipped as
`held_discount` does at `DataCard.cs:330`) for `played` / `drawn` / `card_exhausted` via `DataCard` overrides
`AfterCardPlayed` (per replay, like base) / `AfterCardDrawn` (`KinglyKick`) / `AfterCardExhausted`. Describe: "Costs 1
less this turn for each Skill you play." / "After you play this, it costs 0 for the rest of combat." / "Whenever you
draw this, it costs 1 less this combat." / "Costs 1 more each time you play it." Validator mirrors `held_discount`
(:846 not on 0/X-cost, cap :1177). **AutoSlay proves only the cost READ** — log `GetWithModifiers(CostModifiers.Local)`.
**Triggers (B5, gap #77):** `on_card_generated` — `AfterCardGeneratedForCombat(card, creator)` (`AbstractModel.cs:421`,
no ctx: use `_combatCtx ?? new ThrowingPlayerChoiceContext()`, never store the throwing one), `creator?.Creature ==
Owner`; fires for `add_status_card` Wounds too (base Smokestack/Arsenal behaviour). `on_debuff_applied` —
`AfterPowerAmountChanged(ctx, power, amount, applier, cardSource)` (:1052) with the `SleightOfFleshPower` filter
(`amount != 0 && GetTypeForAmount(amount) == Debuff && power.Owner.IsEnemy && applier == Owner && !(power is
ITemporaryPower)`), optional `status` filter (reuse `EffectSpec.Status`), new payload target **`that_enemy`** (pass
`power.Owner` through the existing `attacker` argument; widen `ForgedCards.cs:1686`). `on_evoke` —
`AfterOrbEvoked(ctx, orb, targets)` (:963), `orb.Owner == Owner.Player`, orb classes only. Describe: "Whenever you
create a card, …" / "Whenever you apply a debuff, …" / "Whenever you apply Vulnerable, …" / "Whenever you Evoke an
orb, …"; fragment "deal 3 damage to that enemy". The `_firing` guard (:233) covers payload re-entry loops.
**`on_energy_spent` is NOT built** (AutoSlay never spends energy; §6).
**Harness:** `tempo_draw` / `big_energy` / `retain_hold` / `strike_tempo` (cost_delta); `token_conjurer` (generated),
`debuff_expose` / `poison_attrition` (debuff applied), `orb_channel` (evoke). `REACTIVE_MENU_V2` += the 3 kinds + samples;
`gate.FIELD_UNITS` += `cost_delta` fields.
**Test:** `tests/test_phase_bp.py`. **Tester** `gaptest-bp`: Stomp, Momentum Strike, Kingly Kick, Arsenal-style power,
Vicious (Vulnerable → draw), Sleight of Flesh (debuff → 3 damage to that enemy). **Tags:** `[BP] cost_delta '<card>'
on <event>: <old> -> <new> (<scope>)`, `[BP] <kind> fired (...)`, `[BP] that_enemy -> '<monster>'`.

### Phase BQ — Orb extras (v69; gap #78; ~1 day) — 17 base cards, orb classes only

**Blocker first:** `ForgedOrb` (`Powers/ForgedOrb.cs:139-156`) does NOT override `OrbModel.Passive` (an empty virtual,
`OrbModel.cs:235`), so `OrbCmd.Passive` / `LoopPower` silently no-op on custom orbs. Add `public override Task
Passive(ctx, target) => Source == null ? Task.CompletedTask : OrbRunner.RunPassive(Source, this, ctx, target);` (the
turn tick does not call `Passive`, so no double-fire).
**Ops (DECOMP `OrbCmd.cs`: `EvokeNext(ctx, player, dequeue)` :94, `EvokeLast` :106, `Passive(ctx, orb, target)`
:155, `RemoveSlots` :41 sync):** `evoke` + `keep:true` ("Evoke your next orb twice." — Dualcast = keep pass + normal
pass); `evoke` + `which:"newest"` ("Evoke your newest orb."); `trigger_passive {amount, orbs: first|all}` ("Trigger
the passive of your next orb 2 times." — Darkness / TeslaCoil); status `loop` = base `LoopPower` via the BF pipe ("At
the start of your turn, trigger your next orb's passive."); `lose_orb_slot {amount:1}` card-only drawback ("Lose 1 Orb
Slot."; validator: class has ≥ 3 slots — at 0 slots `OrbCmd.Channel` only re-adds for `BaseOrbSlotCount == 0`, so a
forged class would channel into nothing); scales `orb_count` / `orb_types` (distinct `GetType()`, Compile Driver) on
damage/block/draw; `orb_count_ge` + an `orb` filter (base names via `EffectRunner.OrbTypeFor` :1016, custom via
`ForgedCharacters.ResolveOrbType` :1255); `channel_orb` + `per_enemy:true` (count = `HittableEnemies.Count`, Chill).
`on_evoke` ships in BP.
**Harness:** `orb_channel` / `slot_machine` only; `FEATURED_CLASS_KIND["orb"]` entries; `SCALE_MENU_KIND` orb entries.
**Test:** `tests/test_phase_bq.py`. **Tester** `gaptest-bq` (orb class): Dualcast, Multi-Cast-lite, Darkness, Loop
power, Bulk Up, Compile Driver, Chill. **Tags:** `[BQ] evoke <which> keep=<b>`, `[BQ] trigger_passive x<n> on '<orb>'`,
`[BQ] lose_orb_slot -> <cap>`, `[BQ] orb_count/orb_types -> <n>`, `[BQ] channel per_enemy x<n>`.

### Phase BR — Stun (re-open #11), discard-all + `cards_removed`, growing turn-start damage (v70; gaps #11, #79; ~1 day)

**Stun (B10).** `CreatureCmd.Stun(Creature, string? nextMoveId = null)` (`CreatureCmd.cs:871`) → `Creature.StunInternal`
(:524): throws for a player, no-op if dead, **throws if `Monster.MoveStateMachine.StateLog` is empty** (guard it),
builds a STUNNED `MoveState` with `FollowUpStateId` = the last logged move → `SetMoveImmediate`, which **only replaces
the move if `NextMove.CanTransitionAway`** — locked boss moves and phase transitions are naturally immune, a second
stun the same turn is a no-op, and after the stun the monster repeats its last move (base behaviour). There is no
StunnedPower; `AsleepPower` is Lagavulin-specific. Flag-op `stun`, `target:"enemy"` only: `if
(target.Monster?.MoveStateMachine.StateLog.Count > 0) await CreatureCmd.Stun(target);` in try/catch; log whether
`NextMove.Id` became STUNNED. "Stun the enemy." **Guard rails (it is a hard lock if repeatable):** never a payload;
requires `exhaust`; cost ≥ 2; uncommon/rare; ≤ 1 stun card per class; never with `return_to_hand` / `retrieve_card`
loops (cross-check BO). Flip `### 11.` to done at ship.
**`discard cards:"all"` + `scale:"cards_removed"` (B6).** `PickModes` (:555, check :1353); `DiscardRandom` with the
whole hand through the batch `CardCmd.Discard(ctx, IEnumerable)` (:157; keeps Sly firing); per-play stash
`DataCard._removedThisPlay` set by `discard` / `exhaust_card`, read by `ScaleValue("cards_removed")`; preview fallback
`OtherCardsInHand`. "Discard your hand." / "Exhaust your hand. Deal damage equal to the cards Exhausted." (with BK:
`hits_scale:"cards_removed"` → Fiend Fire proper).
**Growing turn-start damage (Rolling Boulder).** **Do NOT apply the base `RollingBoulderPower`** — it awaits a VFX
`Finished` signal outside TestMode (AutoSlay hang risk). Mod-native: allow `grow` in a `turn_start` payload only on a
targeted `damage` (lift `ForgedCards.cs:1666`), per-power fire counter in `ForgedTriggerPower` (beside `_ripenLeft`
:37), pass `amt + grow*fires` into `TriggerRunner.Run`. "At the start of your turn, deal 5 damage to ALL enemies.
Increases by 5 each turn."
**Harness:** stun → `ambush_alpha` / `block_bulwark` (one card); discard-all → `madness_discard` / `exhaust_pyre`;
growing damage → `power_ramp` / `countdown_ripen`.
**Test:** `tests/test_phase_br.py`. **Tester** `gaptest-br`: Whistle-lite (3-cost exhaust 20 damage + stun), Fiend Fire,
Calculated Gamble, Rolling Boulder power. **Tags:** `[BR] stun '<enemy>': next move <old> -> STUNNED (applied=<b>)`,
`[BR] stunned turn performed '<enemy>'`, `[BR] cards_removed -> <n>`, `[BR] turn_start grow: <base>+<g>x<fires>`.

---

## 4. Release (one mod release for the wave)

**Pre-release test re-pass (rule 0.9b):** re-run the BH-1 checklist against the finished tree — both suites green,
every `test_phase_b[i-r].py` exposes its `_all` wrapper and its describe byte-match, each phase's tags file is in
`generation/scratch/gaptest-<xx>/`, the §2.3 readings printed and recorded in `TEST_AUDIT_2026-10.md`, and the
C# build is clean from a fresh clone (gitignored `mod/Directory.Build.props` + `.editorconfig` noted).

Then: merge to main → bump `mod/BlankTheSpire.json` (v0.3.0 → **v0.4.0**, vocab v70) → build from HEAD →
`mod/tools/package_release.ps1 -Version 0.4.0` → smoke one seed on the packaged DLL → Workshop update
(`workshop/build_workspace.ps1 -Version 0.4.0 -ChangeNote "…"`, keep `visibility: public`; **either move the whole
`previews/` folder out of the tree (previews unchanged) or leave it holding the complete set of real images <1 MB —
never empty, never with `.gitkeep` inside**; `~/tools/ModUploader/ModUploader.exe upload -w workshop/workspace`;
restore) → scp zip to `/opt/btsweb/web/static/releases/` + `chown btsweb:btsweb` → commit + push →
`sudo /opt/btsweb/deploy.sh` (this is also when the BH-3 tree goes live) → check `/download` shows v0.4.0 and the
droplet's `bts1.py` VOCAB_VERSION matches the zip. **Never deploy the web before the zip + Workshop item are live
(rule 0.11).** Players on v0.3.0 get "this code needs a newer BLANK the spire" until they update; the welcome banner
already points at the Workshop item.

If the window closes mid-wave: release whatever is merged (the phases are independent, each is a vocab bump), as long
as every merged phase passed its smoke.

---

## 5. Scoreboard and the cut line

| Phase | Gaps | Vocab | Scout est. | Base cards | What the forge can newly say |
|---|---|---|---|---|---|
| BH | — (+ #62–#79 logged) | — | 1½ days | — | v0.3.0 shipped ✔; full test audit (both suites green, no dead-path asserts); the vocabulary tree (index + per-forge detail) replaces the whole-file paste; budget tests measure the real prompt |
| BI | #62 | v61 | 1 day | 11 | Rage / Storm / Panache / Juggling / Iteration engines; random-enemy payloads |
| BJ | #63, #64 | v62 | 1½ days | ~25 | Ashen Strike, Memento Mori, Helix Drill, Mirage, Bully, Expertise, Double Energy, Evil Eye, Go for the Eyes |
| BK | #65 | v63 | 1 day | 24 | Whirlwind / Skewer (X hits), Finisher, Flechettes, Fiend Fire-style rippers |
| BL | #66, #67 | v64 | 1½ days | 24 | Piercing Wail, Dark Shackles, Malaise, Expose; Doom executes (Necrobinder's axis for any class) |
| BM | #68–#70 | v65 | 1 day | 30 | Battle Trance, Panic Button, Wraith Form prices; Burst / Double Tap / Echo Form; Prolong; Equilibrium |
| **cut line** | | | **~7½ days of scout estimate (Wave 5 ran ~5 estimated days in one real day)** | **~114** | |
| BN | #71–#73 | v66 | 1½ days | 38 | Feed / Sunder on-kill; Discovery / Infernal Blade; Havoc / Uproar / Mayhem |
| BO | #74, #75 | v67 | 1½ days | 29 | Particle Wall, Bolas, Headbutt, Secret Weapon, Reboot; Snap / Hand Trick |
| BP | #76, #77 | v68 | 1 day | 24 | Stomp / Momentum Strike / Kingly Kick; Arsenal, Vicious, Sleight of Flesh |
| BQ | #78 | v69 | 1 day | 17 | Dualcast, Darkness, Loop, Compile Driver, Chill — the orb class catches up |
| BR | #11, #79 | v70 | 1 day | 5 | Whistle; Fiend Fire / Calculated Gamble; Rolling Boulder |

**Recommended order:** BH → BI (cheapest high-count win, proves the lockstep on this tree) → BJ → BK → BL → BM, then
BN → BO → BP → BQ → BR as the window allows. Phases are independent except: BK uses BJ's scales; BL's
`target_status_stacks status:doom` uses BJ; BR's Fiend Fire form uses BK; BQ's `on_evoke` ships in BP (BQ can ship
without it). Run smokes serially (one game instance); batch two testers per smoke session when phases land together.

---

## 6. Deferred (log as `captured`, not planned this wave)

| mechanic | base cards | why deferred | what unblocks it |
|---|---|---|---|
| **Stars** (second resource, star costs, star-X) | 31 (Regent) | Scout B9: state + HUD + card frame are generic (not Regent-gated), BUT it is a 2 h spike + 14–18 h build with a new class kind — the whole window by itself | a Wave 7 whose sole deliverable is a `royal_stars` class kind, after the spike confirms the star pip renders on a forged card |
| `end_turn` (VoidForm) | 1 | `PlayerCmd.EndTurn` inside OnPlay races queued AutoSlay plays; hang risk at "Combat turn N" | a 2–3 h AutoSlay spike |
| `on_energy_spent` (Orbit) | 1 | AutoSlay never spends energy, so it cannot be smoke-proven | a manual in-game check protocol |
| Run-economy (gold, potions, extra rewards, upgrade at combat end) | 7 | run-level balance risk; `combat_end` relic hook exists for the heal form only | Ryan's call on run-economy in forged classes |
| Damage / Block multipliers (Cruelty, Debilitate, Tracking, Colossus) | 8 | medium; needs forged powers on `ModifyDamageMultiplicative` / `ModifyBlockMultiplicative` | after BM proves the base-power pipe at scale |
| Combat-scoped transform (Primal Force, Compact, Entropy) | 7 | medium; `transform_card` is run-permanent by design | a `scope:"combat"` on the transform family |
| Copy another chosen card (Dual Wield, Nightmare) | 4 | needs `CreateClone` of a hand pick + depth rule | small follow-up after BN's `add_random_card` lands the picker |
| Status-card synergy (Flak Cannon, Compact, Iteration-draw) | 3 | needs `on_card_generated` + `card_type:"status"` filters | BP + a `status_cards_owned` scale |
| Shared growth across copies (Claw, Maul) | 4 | `grow` is per-instance | a `grow_shared` field iterating `AllCards` by id |
| Per-card-played enemy debuff (Strangle, Oblivion) | 3 | a forged instanced enemy power | a custom-status hook `on_opponent_card_played` |
| Additive history scales (base + N×count: Murder, Memento Mori exact) | — | BJ ships replace-semantics | an `additive` flag on `scale` |
| Howl-from-Beyond exhaust self-replay; forced play from hand (Stampede) | 4 | #42/#43 and #37 policy | re-evaluate after BN's autoplay is in players' hands |
| Playability restriction ("unplayable unless"), cost 5+ with self-reduction | 5 | niche | BP's `cost_delta` makes 5-cost + reduction expressible later |

---

## 7. Open decisions for Ryan (defaults in bold; the wave proceeds on the defaults)

1. **`every_n` counting** (BI): **per combat** (relic parity, no new reset logic) vs per turn (base Panache / Juggling).
2. **`this_turn` reactive powers are Single-stack** (BI): **accept** (two Rages in one turn = one payload; price it) vs
   multiply the payload by `Amount`.
3. **`hits_scale` cap** (BK): **10**, logged.
4. **History scales are replace-semantics** (BJ): **ship replace first**, additive form as a follow-up.
5. **`target_killed` on AoE** (BN): **"if this kills an enemy" (any kill)** vs single-target only.
6. **Doom pricing band** (BL): **cap 12 per card, ≤ 4 Doom cards per class, rare for ≥ 10**.
7. **Stun re-open** (BR): **yes, with the guard rails** (exhaust + cost ≥ 2 + 1 per class + never a payload).
8. **Autoplay policy vs gap #37** (BN): **GO with forced exhaust + depth guard 3**; forced-from-hand stays rejected.
9. **Stars**: **deferred to Wave 7** (spike only if the window has slack after BR).
10. **`retrieve_card` from the draw pile** (BO): **accept** reversing the documented rule.
11. **Release cadence**: **one v0.4.0 at the end**; no mid-wave release.
12. **Strength Down counts as a debuff** for `spread_debuffs` / `target_debuff_count` (BL): **yes** (base Misery copies it).

13. **Tree selection width** (BH-3): **selected archetypes' ops + core ops + explicit-request tokens + family
    closure**, with one nominate retry; widen if more than ~20% of forges nominate.

**Status (2026-10-01 night):** **Phase BH DONE** on branch `wave6` (not pushed, not deployed — rule 0.11). BH-0
v0.3.0 (e84f613). BH-1 test audit: `docs/plans/TEST_AUDIT_2026-10.md`, generation 580 → web 293 green, 27 phase
files gained their rule-0.10 wrapper (32 hidden failures fixed), both conftests pin the runtime env. BH-2: gaps
#62–#79 `planned`, #80–#91 `captured`, #11 re-opened (next free number **#92**). BH-3: the vocabulary tree
(`gate.vocab_index` / `vocab_detail` / `tree_selection`, `BTS_BLUEPRINT_VOCAB=tree|full`, `nominate_ops` retry)
— readings: index 5,914 · per-archetype max 61,807 (`forge_ramp`) · all-ops 112,644 · scaffold 45,789 · `full`
108,282 unchanged; typical triads 55–70k. Merged suite: generation **586**, web **293**, `test_phase_bh` 92/92.
Open after BH-3 (Ryan): index clause cap is 34 chars at the 6,000 ceiling (raise `gate.INDEX_BUDGET` + the test to
~8,500 for 12-word clauses); `apply_status` does not pull the Statuses section (vulnerable/weak/strength are
index-only unless an archetype lists them); the ORB pitch still says "see the 'Orbs' section above" (it is below in
tree mode). BH-1 needs Ryan's OK on two product fixes: `app.js` donation history "Bought N tokens" → "Token pack",
and the restored `summon_swarm` pricing sentences in DESIGN_HEURISTICS.md — **both OK'd by Ryan 2026-10-02**; the
status lookup + orb pitch were fixed in the BH-3 follow-up (388ec64, merged 26fcbd7); the index budget stays 6,000.

**Phase BI DONE 2026-10-02** (f9500db on `wave6`, vocab v61; smokes GAPTESTBI1/BI2 all four `[BI]` tags, 0 mod
exceptions, 0 localization errors; tester + tags in `generation/tests/gaptest-bi/`). Merged suite: generation **588**,
web **293**, `test_phase_bh` 101/101. Readings: index 5,924 · per-archetype max 64,742 · all-ops 114,296 ·
**scaffold 45,951 of 46,000 (49 chars of headroom)** · `full` 108,977.
**Decided 2026-10-04 (Ryan):** scaffold (§2.3 d) measured per archetype on the real (pruned) path ≤ 32,000; triad
samples ≤ 80,000; index budget 8,500; all-ops tripwire (§2.3 c) 120,000 → 140,000 (decided before Phase BK at
117,639 — the all-ops path is synthetic, the real guards are per-archetype ≤ 70k and the triads ≤ 80k).
Readings: index 7,172 (clause cap 72) · per-archetype max 65,990 (`forge_ramp`) ·
per-archetype scaffold max 25,345 (`exhaust_pyre`) · triads 59,197 / 68,992 / 75,069 · all-ops 115,544 · all-ops
scaffold 45,951 (informational) · `full` 108,977. **Next: Phase BJ** (v62).

**Phase BJ DONE 2026-10-04** (on `wave6`, vocab v62; smokes GAPTESTBJ1/BJ2 both completed the run, every `[BJ]` tag fired,
0 mod exceptions, 0 localization errors; tester + tags in `generation/tests/gaptest-bj/`). Merged suite: generation
**592**, web **293**, `test_phase_bj` 231/231. Readings: index 7,627 (cap 72) · per-archetype max 67,956
(`exhaust_pyre`) · per-archetype scaffold max 25,571 · triads 60,934 / 70,730 / 76,807 · all-ops 117,639 · all-ops
scaffold 46,178 (informational) · `full` 110,775 (scaffold snapshot 45,900, +227). **Next: Phase BK** (v63).
