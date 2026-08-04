# Phase N + O — Creative Breadth & Mechanic Weave · EXECUTABLE RUNBOOK

**Status: READY TO EXECUTE — written for an Opus 4.8 agent told "execute what is in this doc".**
Authored 2026-07-07 (Fable 5 session; anchors re-verified against live code the same day). Harness-side
only: **Phase N is pure generation-side Python** (no C#, no `VocabVersion` bump); Phase O has exactly one
slice (O-2) that touches the game. Sibling: `VOCAB_EXPANSION_2_PLAN.md` (engine-side vocab growth;
independent — its §1.4 reciprocal rule points back here).

---

## 0. Agent operating protocol (read this first, follow it exactly)

**Scope per invocation: execute slices in §0.2 tracker order.** You MAY land several slices in one run,
but every slice ends with the full suite green + its own commit before the next begins — never leave a
slice half-landed. **Do not start Phase O until the Phase N acceptance sweep (N-ACC) has passed.**

### 0.1 Orient before touching anything

1. Confirm the baseline: `cd generation && for f in tests/test_*.py; do uv run python "$f" | tail -1; done`
   — **485 passed, 0 failed** as of 2026-07-07 (script-style runners, NOT pytest; `test_art.py` is the
   pytest-style exception and exits silently as a script). If red at baseline, STOP and report.
2. Read `HARNESS_VERSION` in `generation/btsgen/class_forge.py` (~:57; `"1.0"` as of 2026-07-07). Every
   slice that changes forge behavior bumps it with a short suffix (e.g. `1.1-n1-coverage`); stamp
   `1.1-breadth` at N-ACC and `1.2-weave` at O-ACC.
3. Check the §0.2 tracker for the first non-`done` row; resume a `building` row before starting new work.
4. **Line numbers in this doc are anchors, not gospel** — re-grep every symbol before editing.

### 0.2 Slice tracker (update as you go: `ready` → `building` → `done <date, result>`)

| slice | what | depends on | status |
|---|---|---|---|
| **N-0** | census tool (`btsgen/census.py` + CLI) — the acceptance metric | — | done 2026-07-07 — CLI reproduces §1 exactly (965 cards, 25% plain); 29 tests green |
| **N-3** | catalog expansion: 8 new archetypes + metaphor enrichment | — | done 2026-07-07 — 26 entries, 8 new BUILDABLE, metaphors ≥10, ASCII-folded; test_frontend 93 green |
| **N-1** | set-level coverage quotas + one bounded repair round | N-0 | done 2026-07-07 — coverage.py wired; suite+fakes green; real local forge fired the round + census summary. NOTE: local-7B single-shot regen hit rate ~25% (2/8 measured; simple exotic/scale land, nested add_trigger/when mostly fail) → repair degrades to WARNINGs on this backend. §0.5 loosen-once deferred to N-ACC. |
| **N-2** | featured-mechanic roulette (inject + detect) | N-1 | done 2026-07-07 — featured.py rolls 2/concept (sha256), both briefs inject the REQUIRED block, detectors+WARNING wired into coverage; suite+fake green; real-forge confirm running |
| **N-4** | cross-forge usage ledger + picker novelty term | — | done 2026-07-07 — ledger.py; recency line into map/compose+blueprint, novelty penalty in _score (logged per candidate); 35 tests + two-fake-forge demo (forge-2 shows recency line + 1.40 penalty) |
| **N-ACC** | acceptance sweep (≥6 real forges) + census diff vs baseline | N-0..N-4 | done 2026-07-08 — 7/7 cloud forges (glm-5.2 harness); every class meets ≥2 reactive/≥3 when/≥2 exotic; plain 25%→21%; innate/turn_at_least/on_card_drawn/on_damage_dealt all 0→>0; smoke: 0 mod exceptions (imports+embarks), AutoSlay run hit env map-stall. HARNESS_VERSION=1.1-breadth. See §1 result. Miss: enemy_count_ge=0. |
| **O-1** | required bridge cards (fusion enforcer) | N-1, N-3 | done 2026-07-08 — bridges.py (witness math: catalog ops A−B, overlap fallback); _validate_blueprint requires ≥3 `bridge:true` pool cards incl ≥1 rare; blueprint RULE + _POOL_ASK inject it; fake path (_fake_blueprint/_topup) tags bridges; enforce_coverage(bridge_ctx=) repairs non-fusing bridges IN PLACE, first, before featured/quota; _resolve_bridge_ctx loads catalog ops (None→skip on invented ids). 717 tests (47 new test_bridges), `--fake --staged` proved full detect→repair→warn on the real staged path (Ambusher×big_energy resolved). Real-forge witness confirm DEFERRED to O-ACC — ollama cloud in a transient bad window (3 forges flaked/hung mid-stream; [[forge-ollama-dns-flakiness]], not a code bug). |
| **O-2a** | hybrid-kinds RESEARCH GATE (C# read + hand-staged smoke) | — | done 2026-07-08 — PARTIAL PASS. (1) C# read: ForgedCharacters.TryParse (:180-210) parses orb_pool/status_pool/summon_pool INDEPENDENTLY and CharacterSpec carries all three — NO mutual-exclusivity gate; ForgedCards SupportedOps holds both orb ops + apply_status_custom with no parse-time class-kind XOR. So the IMPORT side accepts hybrids by construction. (2) Hand-staged a minimal hybrid to slot 04 ('Hybrid Smoke O2a': orb_slots 3 + orb_pool [lightning] + status_pool [Focus Edge], 5 cards incl channel/evoke/apply_status_custom), built, AutoSlay seed GAPTESTO2 --character class4. Result: **import PASS** (`class 04 <- 'Hybrid Smoke O2a' (HP 75, deck 5)`, all 5 cards registered, **0 mod exceptions**), **embark PASS** (`Embarking on a singleplayer ...SLOT04 run`, no orb/status runtime exception). **Combat HUD-coexistence + both-mechanics-firing UNVERIFIED** — the AutoSlay driver stalled at `Room type not assigned` (env map-stall in MegaCrit's AutoSlay helper, BEFORE any room/combat; the earlier N-ACC run today hit the same class of env watchdog). Not a hybrid defect — the game accepted + embarked the hybrid; the env just can't drive combat today. Backup/restore of slot 04 done. |
| **O-2b** | hybrid class kinds in generation | O-2a PASS | SKIPPED 2026-07-08 (§0.5) — O-2a proved import+embark but the runtime HUD/mechanic coexistence is UNVERIFIED (AutoSlay env-blocked). Conservatively do NOT build hybrid GENERATION on unverified runtime support; revisit when AutoSlay can drive a hybrid to combat (or a manual combat playthrough) confirms the orb HUD + custom-status icons coexist and both fire. Phase O ships without hybrids, as §0.5 anticipates. |
| **O-3** | strategy idioms (free-text texture) | — | done 2026-07-08 — each strategic line gains an OPTIONAL free-text `idiom` (texture tag: turtle-scale/one-turn-burst/thin-and-loop/…): suggested in stage_map `_LINES_ASK`/`_LINES_SCHEMA`, NEVER enum-validated (never a validation error even over-long), length-capped (IDIOM_MAXLEN=32) in `hydrate_candidate`, rendered in the forge narration (builder.py), the dossier preview + brief (dossier.py + `_dossier_brief`); `_FAKE_LINES` carry idioms. 725 tests (8 new in test_frontend: carry+cap, absent-stays-valid, over-long-not-rejected, brief renders/omits). `--fake --staged` narration shows `[plays like: one-turn-burst]`/`turtle-scale`. Absent idiom stays valid. |
| **O-ACC** | Phase O acceptance (bridge sweep; hybrid smoke if O-2b landed) | O-1, O-3 | PARTIAL 2026-07-08 — HARNESS_VERSION stamped `1.2-weave` (O-1 bridges + O-3 idioms are live in the flow; O-2b hybrids skipped, see its row). The real-forge CENSUS SWEEP (≥4 concepts, confirm every class ships ≥3 bridges that WITNESS both families incl a rare) is DEFERRED / **pending backend** — the ollama cloud harness was in a sustained bad window this session (5+ forges flaked/hung at the cluster/compose cloud stages; DNS resolves but streaming reads drop — [[forge-ollama-dns-flakiness]], not a code bug). Bridge PLUMBING is proven offline (`--fake --staged`: detect→repair-first→warn with real catalog-ops resolution; 725 tests incl 47 bridge + 8 idiom). TO FINISH when the backend recovers: run §3 O-ACC (e.g. `BTS_STAGE_ATTEMPTS=3 uv run btsgen-forge-class --concept "<c>" --ollama --out scratch/o-acc-sweep/<slug>.btsc.txt` for ≥4 varied concepts, then `btsgen-census` + grep each log for `coverage bridges: N tagged, M fuse both engines` with M≥3 incl a rare), then flip this row to done. |

### 0.3 Environment facts (do not rediscover these)

- **Tests:** script-style runners (see §0.1). Add new test files in the same style (own `main()`,
  `check()` counters) so the suite loop picks them up.
- **Offline pipeline exercise:** `uv run btsgen-forge-class --concept "anything" --fake --staged`
  runs the ENTIRE staged pipeline with fake generators — free plumbing verification for every slice.
  **Gotcha:** any new REQUIRED blueprint/compose rule must also be satisfied by the fake path
  (`_fake_blueprint` / `_topup_blueprint_briefs` / each contract's `fake_output`) or `--fake` and the
  test suite break. This is a known bug-shape — check it for every validator change.
- **Real forges (for N-ACC / O-ACC), two backends:**
  - LOCAL (no key; the default on this box): from `generation/`,
    `BTS_STAGE_ATTEMPTS=3 uv run btsgen-forge-class --concept "<c>" --ollama --ollama-config ollama_roles.local.json --out scratch/breadth-sweep/<slug>.btsc.txt`
    (all roles → local dolphin-mistral; strict stages need the retries — that is what
    `BTS_STAGE_ATTEMPTS` is for).
  - CLOUD (only if `OLLAMA_API_KEY` is set in the env): drop `--ollama-config` to use the cloud role
    map — higher quality, used by the 2026-07-06 overnight run. Known flake: this box's DNS
    intermittently fails to resolve ollama.com, killing a whole forge — **retry the forge; it is not a
    code bug.** Worked sweep-driver example: `generation/scratch/overnight-2026-07-06/run_forge_suite.sh`.
- **The website reuses this code read-only** (`web/forge.py` sets `BTS_REPO_ROOT`; the server must never
  dirty tracked files — see the `_log_gaps` comment in `frontend/builder.py`). Anything the forge WRITES
  at runtime goes to an untracked path: `generation/scratch/…` (gitignored) or an env-pointed location.
  Keep `forge_class(front_end=None)` (the one-shot path) working — the web exposes both paths.
- **7B principle (shapes every slice):** the local model ignores prose adjectives — "use sparingly" and
  "range widely" are already in the prompt and measurably ignored. Creativity ships as STRUCTURE:
  validators + bounded repair, catalog entries, deterministic injection, picker scoring. Prompt additions
  are compact REQUIRED lines only.
- **AutoSlay (O-2a only):** run WITHOUT asking (standing instruction). Staging + smoke procedure:
  `VOCAB_EXPANSION_2_PLAN.md` §0.3 (slot-04 flow, worked example `generation/scratch/gaptest-forge/`).
- **Never abort a class on a creativity shortfall** — bounded repair, then ship with streamed `note()`
  warnings (posture precedent: the summon dead-buff warning, `class_forge.py:1364`).

### 0.4 Verification gates — every slice, in order

1. Full suite green (baseline + your new tests).
2. `--fake --staged` forge completes end-to-end (and `--fake` WITHOUT `--staged` for slices touching the
   one-shot path).
3. Slice-specific gate (in its section).
4. Commit (one per slice), message style matching `git log --oneline` (e.g.
   `forge: Phase N-1 — set-level coverage quotas + bounded repair`). Commit only; **do not push** unless
   the user asks.

### 0.5 Stop conditions — halt, write findings into the tracker row, report

- Baseline suite red before your first edit.
- N-ACC: no LLM backend reachable (local ollama down AND no cloud key) — land code + tests, mark N-ACC
  `pending backend`, stop. `--fake` cannot validate creativity.
- N-1: repair-round hit rate so poor the sweep can't meet quotas even after loosening constants once
  (10% looser) — stop and report the measured hit rate rather than loosening again.
- O-2a smoke fails or the HUD misbehaves — **not a stop:** record the failure in the tracker, mark O-2b
  `skipped (O-2a failed)`, and continue with O-1/O-3. Phase O ships without hybrids.
- Anything needing a semantics decision this doc doesn't cover.

---

## 1. Why: the measured baseline (this table IS the acceptance metric)

Census of the 36-class overnight run (`generation/scratch/overnight-2026-07-06/codes/`, 965 cards,
vocab v18). The harness has ~50 vocabulary tokens but effectively uses ~20:

| metric | baseline (36 cls, 965 cards) | **post-N (7 cls, 187 cards)** |
|---|---|---|
| cards using ONLY damage/block/apply_status/draw | **25%** | **21%** |
| Vulnerable / Weak applications | **162 / 80** (top statuses despite "use sparingly") | 12 / 10 (per-100: 16.8/8.3 → **6.4/5.4** — halved) |
| Blur, Metallicize, Artifact, Buffer / Intangible, Ritual | 2 each / **0 each** | **2 / 6 / 4 / 6 / 2 / 0** (per-100 ~10-15× more exotic) |
| turn_end+turn_start triggers vs six H4 reactive kinds | **246** vs 20/8/6/6/0/0 | 52 vs **6/2/4/4/2/2** (all six kinds now nonzero) |
| `when`: turn_at_least / enemy_count_ge / hp_below_half | **0 / 0 / 12** | **6 / 0 / 12** |
| scales: unspent_energy_last_turn / x | **0 / 10** | 0 / 6 |
| `innate` / `ethereal` | **0 / 2** | **4 / 0** |

**N-ACC result (2026-07-08, post-N census diff).** Sweep of 7 varied concepts (concepts.tsv #37-50) on the
**true cloud harness** — `--ollama` no config: `ministral-3:8b` brainstorm (moved LOCAL for speed) +
**`glm-5.2`** for the strict map/compose/blueprint/card stages (see [[local-ollama-forge-backend]]).
**7/7 forged** (vs the all-local dolphin-mistral map, which produced stunted 9-11 card classes and ~40%
blueprint success — the census improvement needs glm-5.2 on the strict stages, not mistral). Codes in
`generation/scratch/breadth-sweep-cloud/`.

- **Every one of the 7 classes** meets the per-class quotas: plain ≤30% (5/7; 2 at 37%), **≥2 reactive
  trigger kinds, ≥3 `when` kinds, ≥2 exotic statuses — all 7**. Zero classes aborted by coverage.
- Aggregate flips from baseline: `on_card_drawn` 0→2, `on_damage_dealt` 0→2, `turn_at_least` 0→6,
  `innate` 0→4, exotic statuses up ~10-15×, plain share 25%→21%, Vulnerable/Weak dominance halved.
- Featured roulette fired every forge (glm-5.2 often actually wove the picks in, e.g. attila x_dump +
  blood_engine both present); N-4 recency line + per-candidate novelty penalty (0.15-0.30) both visible
  in the logs (the canonical-id fix made the penalty match).
- **One shortfall:** `enemy_count_ge` stayed 0 across the 7 (no horde payoff rolled/produced) — the only
  §N-ACC aggregate criterion not met. Not worth another sweep; a horde-heavy concept would exercise it.
- Shape-regression smoke ('The Blueprinter', normal, 27 cards): mod **builds 0 errors**; **all 27 forged
  cards register with 0 mod exceptions** (godot.log `[ForgedClass] class 04 card 01..27`), the class
  embarks and (run 2) reaches Act 1 Floor 2 combat. The AutoSlay auto-play then hit its watchdog on the
  backgrounded combat UI (the documented focus-throttle, see [[autoslay-embark-hang]]) — an environment
  timeout, not a card/mod defect. Import+shape side is clean.

Chosen archetype PAIRS were decently spread — sameness lived at the card level, produced by four chokes:
(1) the catalog under-names the live vocabulary; (2) cross-archetype weaving is requested, never
enforced; (3) hard exclusivity rules (exactly 2 archetypes, one class_kind, no pools on "normal");
(4) the 7B ignores adjectives. Each slice above attacks one choke with structure, not prose.

---

## 2. Phase N slices

### N-0 — census tool

- New `generation/btsgen/census.py`: pure functions — `walk_card(card) -> CardCensus` (ops, statuses,
  trigger kinds, `when` kinds, scales, X-cost, plain flag: op set ⊆ {damage, block, apply_status, draw})
  walking base + upgrade + nested `add_trigger` payload effects; `census_bundle(bundle)` /
  `census_cards(cards)` aggregators. Decode helper for `.btsc.txt` codes — format
  `BTSC.<ver>.<base64url(gzip(json))>.<crc32>` (`bts1.py:5`; pad with `"=" * (-len % 4)` before
  `urlsafe_b64decode`; `bts1.decode` may already do this — reuse it if so).
- CLI entry `btsgen-census <paths...>` (add to `[project.scripts]` in `generation/pyproject.toml`):
  prints per-class + aggregate tables. Put the §1 baseline table in the module docstring.
- Tests `tests/test_census.py` (hand-built mini-bundle; plain-flag edges: a card with a `when` guard or
  scale is NOT plain).
- **Gate:** running the CLI over `scratch/overnight-2026-07-06/codes/` reproduces §1's numbers
  (25% plain, 0 innate, etc.).

### N-3 — catalog expansion

Add 8 entries to `generation/btsgen/data/archetypes.json` (shape: copy an existing entry; `leans` from
{aggro, control, combo}; `gap_refs: []` — all buildable TODAY, that is the point):

| id | name / engine (description says the ENGINE, metaphors carry the flavor) | ops | leans |
|---|---|---|---|
| `counter_riposte` | Counterpuncher — get hit, hit back: retaliation triggers + thorns | `add_trigger`, `attacked`, `on_hp_lost`, `thorns` | control, aggro |
| `threshold_duelist` | Duelist of moments — `when`-gated payoffs as the identity (execute windows, late-game spikes, no-block daring) | `hp_below_half`, `turn_at_least`, `no_block`, `has_block` | combo, aggro |
| `horde_breaker` | Crowd-breaker — AoE payoffs that want MANY enemies | `damage`, `all_enemies`, `enemy_count_ge` | aggro, control |
| `ambush_alpha` | Ambusher — innate opening-hand burst; win the first three turns | `innate`, `damage`, `gain_energy` | aggro |
| `fleeting_flux` | Use-it-or-lose-it — ethereal cards over-statted for their cost; hand churn | `ethereal`, `draw`, `damage` | combo, aggro |
| `untouchable_ward` | Untouchable — mitigation exotica (negate/absorb/phase) over flat Block | `apply_status`, `buffer`, `artifact`, `intangible`, `blur` | control |
| `burst_window` | Glass tempest — temp-stat spike turns; all at once, then gone | `temp_strength`, `temp_dexterity`, `damage` | aggro, combo |
| `iron_regrowth` | Regrower — heal/regen attrition; outlast by healing more than they land | `heal`, `regen`, `apply_status` | control |

(Fix the mojibake if any sneaks into descriptions — ASCII only; these stream to the Windows console, see
the `builder.py` narration comment.)

- **Token gotcha (verified 2026-07-07):** every `ops` token above IS backticked in
  `mod/contract/VOCABULARY.md`; `cards_in_hand`/`unspent_energy_last_turn`/`forged` are NOT — do not use
  them in `ops` unless you backtick them there first (docs-only edit; `VOCAB_EXPANSION_2_PLAN.md` Phase P
  also does this — coordinate, don't collide).
- Enrich all 18 existing entries' `metaphors` to ≥10 each (wider map-stage resonance surface); add
  multi-hit language to `strike_tempo`'s description. Do not touch ids — the web report and dossiers
  reference them.
- Tests (extend `tests/test_frontend.py`): every new entry resolves `buildable=True` via
  `load_catalog()`; ids unique; leans ⊆ STRATEGIES.
- **Gate:** `load_catalog()` shows 26 entries, new ones BUILDABLE; `--fake --staged` still green
  (fake map/compose picks from `buildable_ids()` — more entries must not break it).

### N-1 — set-level coverage quotas + one bounded repair round

New `generation/btsgen/coverage.py` (imports `census.py`), wired into `forge_class`
(`class_forge.py`) AFTER the per-card loop, BEFORE `_ensure_merchant_types` (~:1349) so repaired cards
flow through the safety nets. Precedent for posture: `forge_pairing_warnings`
(`character_validator.py:147`) — advisory, never fatal.

Quotas (module constants; measured over the NON-basic pool; basics/blade excluded; the reprint-homage
card — detect via its plan `theme` starting with `"Reprint of"` — is EXEMPT from the plain-share count):

| constant | initial | meaning |
|---|---|---|
| `MAX_PLAIN_SHARE` | 0.30 | plain-stat-line cards / pool |
| `MIN_REACTIVE_TRIGGER_KINDS` | 2 | distinct trigger kinds beyond turn_start/turn_end |
| `MIN_WHEN_KINDS` | 3 | distinct `when` kinds (orb-only kinds count for orb classes) |
| `MIN_EXOTIC_STATUSES` | 2 | distinct statuses from {thorns, regen, metallicize, artifact, buffer, blur, intangible, ritual, barricade, temp_strength, temp_dexterity} |
| `MAX_GENERIC_DEBUFF_SHARE` | 0.25 | pool cards applying vulnerable/weak |
| `MIN_SCALED_OR_X` | 1 | cards with any `scale` or X-cost |
| `REPAIR_BUDGET` | 6 | max card regenerations, ONE round |

Flow: census → violations → pick victims (plain stat-line commons/uncommons first; NEVER
`_BASIC_ROLES`, `_SIGNATURE_ROLES` (incl. the blade), the reprint, or — post-O-1 — bridge-tagged cards)
→ re-run `generate_card` per victim with the plan's theme + an appended directive naming the missing
mechanic (directive templates live beside the N-2 menu — one phrasebook for roulette and repair) →
re-census → surviving violations stream as `WARNING:` `note()` lines and ride `ClassResult.log`.

- Tests `tests/test_coverage.py`: census math, victim selection (protected roles never picked), repair
  plumbing with the fake generator. **Do NOT assert quota satisfaction under `--fake`** — fake cards are
  deliberately simple; assert plumbing, not outcomes.
- **Gate:** suite green; `--fake --staged` and `--fake` one-shot both complete (with WARNING lines, not
  failures); one real local forge shows the repair round firing and the census summary in the log.

### N-2 — featured-mechanic roulette

- Menu lives beside the coverage code (`coverage.py` or a sibling `featured.py`): entries
  `{id, injection_line, detector(card) -> bool, exclusion}`. Seed the roll with
  `hashlib.sha256(concept.strip().lower().encode())` — reproducible per concept; NEVER `random` module
  state. `N_FEATURED = 2`.

| id | mechanic (detector checks the card JSON for exactly this) |
|---|---|
| `reactive_played` | `add_trigger` `on_card_played` (suggest `once_per_turn`) |
| `reactive_drawn` | `add_trigger` `on_card_drawn` |
| `reactive_damage` | `add_trigger` `on_damage_dealt` |
| `reactive_block` | `add_trigger` `on_block_gained` |
| `counterattack` | `add_trigger` `attacked` (payload may target the enemy) |
| `blood_engine` | `add_trigger` `on_hp_lost` |
| `long_fuse` | `ripen` countdown trigger |
| `late_game` | `when turn_at_least` |
| `horde_payoff` | `when enemy_count_ge` (+ all_enemies) |
| `desperation` | `when hp_below_half` |
| `patient_reserve` | `scale unspent_energy_last_turn` |
| `x_dump` | an X-cost card |
| `opening_gambit` | `innate` |
| `fleeting_power` | `ethereal` on an over-statted card |
| `untouchable` | buffer / artifact / intangible (rare-gated) |
| `burst_window` | temp_strength / temp_dexterity spike |

  Orb/status/summon-only mechanics stay OFF the menu — class-kind pools remain the compose stage's call.
- Threading: add `featured: list[str] | None = None` to `ClassBrief` (`class_forge.py:108`) AND
  `DossierBrief` (`frontend/dossier.py:43`). Roll in `forge_class` before stage 1; the builder copies it
  when constructing the DossierBrief (`builder.py` ~:274, `dbrief = DossierBrief(...)`). Inject into BOTH
  `_concept_brief` and `_dossier_brief` next to `_POOL_ASK` (~:387-401) as one compact block:
  `FEATURED MECHANICS (REQUIRED): weave at least one pool card around each of: <injection lines>.`
- Detectors register as N-1 quota items (a missing featured mechanic → the repair round targets it with
  its own directive).
- Tests: seeded-roll reproducibility, both brief modes carry the block, detector round-trips, exclusion
  rules.
- **Gate:** suite green; a real local forge's log shows the two featured picks announced (add a `note()`
  line) and the census confirming them present (or the WARNING naming the miss).

### N-4 — cross-forge usage ledger + picker novelty term

- Append-only JSONL at `os.environ.get("BTS_FORGE_LEDGER", REPO / "generation/scratch/forge_ledger.jsonl")`
  (scratch is gitignored — safe under the website read-only rule). One line per SUCCESSFUL forge (write at
  the end of `forge_class`, only when `res.ok`): `{ts, name, archetype_ids, class_kind, top_ops,
  statuses_used, trigger_kinds}` — computed via `census.py`.
- Read window: last `LEDGER_WINDOW = 12` entries at forge start. Inject ONE compact line into the
  map/compose payload (`builder.build` payload dict ~:233; both `_MapComposeContract` and the
  interactive split read `payload`) — `RECENTLY OVERUSED (prefer alternatives): pairs […]; ops […]` —
  and one status-focused line into the blueprint brief.
- Picker: novelty term in `BlueprintBuilder._score` (`frontend/builder.py:443`) — penalty up to `-2.0`
  proportional to recency-weighted appearances of the candidate's archetypes/pair in the window.
  STRICTLY below `_FIDELITY_WEIGHT = 10.0` (:31): fidelity dominates; novelty breaks ties, exactly like
  `_distinctiveness` today.
- Robustness: missing/corrupt/unwritable ledger must NEVER break a forge (try/except around both read
  and write; posture precedent: the `note()` sink guard `class_forge.py:1236-1242`).
- Tests: round-trip, window trim, penalty math, corrupt-file tolerance.
- **Gate:** suite green; two consecutive real local forges — the second's log shows the recency line and
  a different pair choice pressure (log the penalty per candidate).

### N-ACC — Phase N acceptance sweep

1. Pick ≥6 varied concepts (reuse `scratch/overnight-2026-07-06/concepts.tsv` rows #37-50 — never
   reached by the overnight run). Forge each via the LOCAL backend command in §0.3 (cloud if the key is
   present; retry DNS flakes).
2. `btsgen-census` over the sweep codes; compare against §1:
   - per class: plain share ≤ 30%, ≥2 reactive trigger kinds, ≥3 `when` kinds, ≥2 exotic statuses, both
     featured mechanics present (or an explicit WARNING in that class's log);
   - aggregate: `on_card_drawn`, `on_damage_dealt`, `turn_at_least`, `enemy_count_ge`, `innate` all > 0;
   - zero classes aborted by coverage machinery.
3. One AutoSlay smoke on a sweep class (no vocab changed, so this is a shape-regression check only):
   0 mod exceptions. Staging/procedure per `VOCAB_EXPANSION_2_PLAN.md` §0.3.
4. Stamp `HARNESS_VERSION = "1.1-breadth"`, tracker rows → `done`, write the census diff into this doc
   under §1 (a "post-N" column), commit.

---

## 3. Phase O slices

### O-1 — required bridge cards (the fusion enforcer)

- Blueprint contract rule (`_BlueprintContract.system_prompt` RULES + `_POOL_ASK`): at least
  `MIN_BRIDGES = 3` pool cards carry `"bridge": true`, each themed to combine BOTH archetypes' engines in
  ONE card; ≥1 bridge is a rare (the fusion's poster card). `_validate_blueprint` (~:664) enforces
  tag-count + the rare. **Update the fake path in the same commit** (`_fake_blueprint` /
  `_topup_blueprint_briefs` must emit valid bridge tags) or `--fake` breaks — see §0.3.
- Post-generation detector (extends N-1): per archetype, witness-token set = its catalog `ops` MINUS the
  partner's. A bridge card must touch ≥1 witness token of EACH archetype (walk effects incl. payloads,
  `when` kinds, scales, statuses). If either difference is empty (heavily overlapping pair), fall back
  to: touches ≥2 distinct tokens from the union + carries the tag. Failed bridges join the N-1 repair
  round with both engines spelled out in the directive.
- N-1 victim rule update: bridge-tagged cards are protected from UNRELATED quota repairs.
- Tests: witness math (disjoint pair, overlapping pair, orb-vs-normal), fake-path validity, repair
  targeting.
- **Gate:** suite green; `--fake --staged` green; one real forge ships ≥3 verified bridges incl. a rare
  (census/log evidence).

### O-2a — hybrid class kinds: RESEARCH GATE (game-facing; run before any generation work)

1. READ `mod/BlankTheSpireCode/Engine/ForgedCharacters.cs` (`TryParse*` around :200-350): do the pool
   parsers reject a bundle declaring BOTH `orb_pool` and `status_pool`? (Generation-side validators are
   already independent — `class_forge.py:718-723`.)
2. Hand-author a minimal hybrid bundle (orb class + 1 custom status; reuse a staged class shape from
   `generation/scratch/gaptest-forge/`), stage to slot 04, AutoSlay smoke seed `GAPTESTO2`
   (procedure: `VOCAB_EXPANSION_2_PLAN.md` §0.3; run without asking).
3. PASS = import accepted, orb HUD + custom-status icons coexist, both mechanics fire in the log, 0 mod
   exceptions. FAIL = record exactly what broke in the tracker, mark O-2b `skipped`, move on — **do not
   patch the C# to force it**; that is a user-scoped decision.

### O-2b — hybrid class kinds in generation (ONLY after O-2a PASS)

- Compose contracts (`stage_map.py`, both fused + split): candidates may declare
  `"splash_kind": "orb"|"status"|"summon"|null` alongside the dominant kind, only when the theme demands
  it. `hydrate_candidate` (`frontend/catalog.py:151`) carries it; `Candidate` gains the field.
- Splash budgets, enforced in `_validate_blueprint`: splash orb = 2 slots + ≤1 custom orb; splash status
  = 1 custom status; splash summon = the one minion with summon-op cards capped at 3.
- Blueprint `kind_guidance` (`class_forge.py:408-417`) gains a hybrid branch: primary engine leads, the
  splash is seasoning.
- `_KIND_WEIGHT` (`frontend/builder.py:26`): verified hybrid = 3.5 (boldest).
- The per-kind drop nets (`class_forge.py:1321-1339`) already key off declared pools — add a test
  proving a hybrid's splash cards survive them. Update the fake path.
- **Gate:** suite + fakes green; one forged hybrid AutoSlay-verified end-to-end (splash mechanics fire,
  0 mod exceptions).

### O-3 — strategy idioms (cheap texture)

- `strategic_lines` entries gain optional free-text `"idiom"` (suggested menu in the prompt, NEVER
  enum-validated — length-cap only, 7B-safe): turtle-scale, one-turn-burst, thin-and-loop,
  attrition-stall, all-in-gamble, midrange-tempo.
- Touches: `stage_map.py` `_LINES_ASK`/`_LINES_SCHEMA` (~:20-30), line normalization in
  `hydrate_candidate` (`catalog.py:177-183`), `_dossier_brief`'s lines block (`class_forge.py:434-440`),
  report display (web optional).
- **Gate:** suite green; idioms visible in a real forge's narration/report; absent idiom stays valid.

### O-ACC — Phase O acceptance

- Sweep ≥4 concepts: every class ships ≥3 verified bridges incl. a rare poster card; census shows
  bridges witnessing both families.
- If O-2b landed: the hybrid smoke evidence recorded; if skipped, the tracker says why.
- Stamp `HARNESS_VERSION = "1.2-weave"`, tracker → `done`, commit.

---

## Out of scope / deferred

- **3-archetype candidates** — exactly-2 is baked into validators and prompts; bridge cards deliver most
  of the value at a fraction of the churn. Revisit only if post-O sweeps still feel narrow.
- **Web census panel** — optional polish; the report already shows archetype cards.
- **Any vocab/engine change** — `VOCAB_EXPANSION_2_PLAN.md`. Reciprocal rule: every vocab phase adds its
  mechanics to the N-2 menu + an N-3-style catalog entry, or it sits unused like the H4 triggers did.

## Open questions (safe defaults chosen — deviate only with a reason, and record it in the tracker)

- Quota levels: start at §N-1's table; loosen ONCE by 10% if the 7B repair hit rate can't meet them
  (then stop — §0.5).
- Ledger injection: map+compose + blueprint only; the cloud stage stays unconstrained divergence.
- Reprint homage: EXEMPT from plain-share (baked into N-1 above).
