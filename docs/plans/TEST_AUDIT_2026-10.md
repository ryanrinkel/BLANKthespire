# Test audit — 2026-10 (Wave 6, Phase BH-1)

Scope: `VOCAB_EXPANSION_6_PLAN.md` Phase BH, item BH-1 (sub-items 1–8), rule 0.9b. Branch `wave6`.
Everything here is offline. No model or vendor calls were made.

## Baseline before / after

| suite | command | before | after |
|---|---|---|---|
| generation | `cd generation && uv run python -m pytest -q --no-header -p no:cacheprovider` | 548 passed, 3 failed, 3 errors | **580 passed** |
| web | `PYTHONPATH=generation generation/.venv/Scripts/python.exe -m pytest web/tests -q --no-header -p no:cacheprovider` (repo root) | 289 passed | **293 passed** |

The 3 errors before were conftest's `_FAIL` teardown guard on the same 3 failing tests (aq/as/ba). The generation
count grew by 27 `test_phase_<xx>_all` wrappers, 1 live twin (`test_measure_clean_pool_v2`) and 1 new test
(`test_stub_block_expires_after_an_hour`). The web count grew by 4 new tests.

Both suites also pass on a **hostile shell** (droplet-like env: `BTS_HARNESS_V2=1 BTS_VOCAB_GATE=heuristic`,
vendor keys, `RESEND_API_KEY`, model/price overrides, Stripe fee overrides, `BTSWEB_ENV=production`). Before
the audit, generation failed 5 tests on that shell and web refused to boot.

Commits (branch `wave6`):
- `244ee28` forge: rule 0.10 wrappers on every phase test + repoint stale checks
- `ea19941` forge: pin the runtime env in conftest + label rollback-path coverage tests
- `f684efd` web: pin the runtime env in the web test conftest
- `a708fbc` forge: live-path pins (stub TTL, Ollama ceilings) + stop the bench test littering scratch
- `5e07b7f` web: donor-copy guard, admin 4 h + no-fallback pins, quarantine leak
- (this doc) docs: test audit

## 1. Both suites + the known stale aq/as/ba set

The known set was 7 checks in `test_phase_aq/as/ba` that grep `web/static/app.js` for renderers that moved to
`web/static/render.js` (`potionLines`, `effPhrase`, `condCore`, relic `fmtHook`). All seven are repointed at
`render.js`, and every string was confirmed to exist there. The same stale path was also in
`test_phase_ar/at/av/ax`. Those hits were hidden because those files had no pytest wrapper (see §3). They are
repointed too. The only web file still read as `app.js` is `web/tests/test_forge_estimate.py` (the BYOK
`PROVIDERS` literal), and that literal really does live in `app.js`.

## 2. Stale paths / symbols / wording

Swept both suites for: missing file names in string literals, `case "op":` / `app.js` renderer checks,
`_system_prompt_v1`-era strings, removed archetype ids, `MODEL_PRICES` zeros, `BTS_HARNESS_V2` assumptions,
line-anchored comments, and `not in` checks that could pass vacuously on a moved file.

- **`app.js` renderers.** Fixed (§1/§3). `test_pages.py:109` asserts `/static/app.js` is NOT on the deck page.
  That is correct: the page uses `render.js`.
- **Missing files referenced by tests.** Every hit is intentional: a temp/output file the test creates,
  `DiscardHookPatch.cs` (AU asserts it is *absent*), or fixture names. One exception: `test_phase_aw.py:298`
  reads `generation/scratch/gaptest-aw/build_tester.py` behind `if tester.exists()`. scratch is gitignored, so
  that check never runs in a fresh checkout. It is left as is (rule 7 asks for no moves) and listed under
  Follow-ups.
- **Old archetype ids.** Every id that ever appeared in `data/archetypes.json` history is still current. No test
  names a removed id.
- **`MODEL_PRICES` zeros.** None remain in `web/app.py`, and no test asserts a zero hosted price.
  `test_forge_estimate` monkeypatches the table explicitly.
- **Line anchors.** Only informational `print` baselines remain (aq/ar). No asserted line numbers.
- **`_system_prompt_v1`.** No test references it. `test_card_system_prompt_v1_unchanged` is the flag-off card
  prompt and is now labelled ROLLBACK (§4).
- **Prototype-era tests.** `test_character_pipeline`, `test_validator`, `test_relic_validator` and
  `test_pipeline_balance_repair` run on the archived prototype contract, by design (conftest
  `_PROTOTYPE_MODULES`). The CLI under test emits a DeprecationWarning saying so. They are kept as tests of a
  legacy path and are not counted as live coverage.

## 3. Rule 0.10 sweep — `test_phase_<xx>_all()` in every phase file

**27 files had no wrapper.** These are aa, ab, ac, ad, ae, af, ag, ah, ai, ajb, ar, at, au, av, aw, ax, ay, bg,
p, q, r, s, u, v, w, x and z. Each now has the standard wrapper (reset `_PASS/_FAIL`, `assert main() == 0`).

For aa–ai, ajb, p–z and bg, `main()` only calls the module's own `test_*` functions, so the wrapper adds no new
checks there, only uniformity. For **AR, AT, AU, AV, AW, AX and AY**, pytest used to collect only
`test_version`, so every `_t_*` check had never run under pytest. Running them showed:

| phase | hidden reds | cause | fix |
|---|---|---|---|
| AR | 11 | `app.js` → `render.js` (turn_start passive label, 9 `condCore` cases, the `when` gate suffix) | repointed |
| AT | 6 + 2 | (a) the `ForgedTriggerPower.AfterDamageGiven` slice split on the bare word `AfterBlockGained`, which Phase BE's on_poison_damage comment *inside* that method now mentions, so the body was cut before the pet path. (b) `DESIGN_HEURISTICS` summon_swarm note lost the pack-tactics sentence. (c) app.js path | (a) the slice now anchors on the `public override async Task …` declarations. (b) the sentence is restored, see below. (c) repointed |
| AV | 1 + 1 + 6 | (a) the `## Forged summons` slice ended at `## Card shape`, and Phase BA's `## The signature potion` (which says "exactly one custom potion") now sits in between. (b) DESIGN_HEURISTICS lost the ETHEREAL-striker pricing. (c) app.js path | (a) the slice ends at the next `## ` heading. (b) restored. (c) repointed |
| AX | 2 | app.js path (spend_forge / spread_debuffs labels) | repointed |
| AY | 1 | codec stamp pinned to `BTSC.54.` | now asserts the CURRENT `bts1.VOCAB_VERSION` (>= 54) |
| AU, AW | 0 | — | — |

**Product change (contract copy).** The 2026-09-29 archetype-copy rework (`7173537`) rewrote the
`summon_swarm` balance note in `mod/contract/DESIGN_HEURISTICS.md`. It dropped two pricing rules for mechanics
that are still live:
- the `on_damage_dealt` + summon_attack pack-tactics engine (once_per_turn, small reward), from Phase AT;
- the ETHEREAL (`attackable:false`) striker's HP/damage banding, from Phase AV.

Both sentences are restored in condensed form. The rest of the rework's wording is unchanged. The note reaches
only the map/catalog stage for summon archetypes (`contract.archetype_balance_note`), not the rule-0.9 blueprint
scaffold. **Ryan: if dropping them was deliberate, revert that one line and repoint the AT/AV checks instead.**

## 4. Tests on a path production no longer sends

Production runs `BTS_HARNESS_V2=1`, `BTS_VOCAB_GATE=heuristic` and triad ON.

- **`test_coverage.py`.** `test_measure_math`, `test_measure_clean_pool`, `test_plan_repairs` and
  `test_enforce_plumbing` measure the **v1 quota set**. They used to read whatever the shell said, and they
  failed under `BTS_HARNESS_V2=1`. They now pin v1 explicitly (`_V2(False)`) and are labelled ROLLBACK PATH.
  `test_w2_repair_walks_new_menus` computed its v1 report outside the v1 block, which is also fixed. New live
  twin: `test_measure_clean_pool_v2` (the same pool is short only on the v2 keyword quota; two keyword kinds
  clear it; `enforce_coverage` skips repair). The v2 planner and plumbing were already covered by `test_w2_*`.
- **`test_featured.py::test_coverage_targets_featured`.** Same shell dependence. It now runs on **both** paths
  (v2 first). The base pool carries two keyword kinds, so v2's keyword quota is met.
- **`test_harness_v2.py::test_card_system_prompt_v1_unchanged`.** Labelled ROLLBACK (the kill-switch). The live
  twin, `test_card_system_prompt_v2_drops_ironclad_and_names_real_ops`, already existed.
- **`test_vocab_gate.py::test_off_is_byte_identical`.** Already explicit (`delenv`). The heuristic live path is
  the rest of that file.
- **`triad=False` blueprint briefs** (`test_frontend`, `test_featured`, `test_feedback_store`, `test_forge`).
  Already pinned with a "legacy 2-arch shape" comment. The live triad prompt is covered by `test_triad`.
- **Phase tests' blueprint-wording checks** (AM…BF `"…" in _BlueprintContract(...).system_prompt()`). These run
  flag-off, so they read the untrimmed prompt. They are lockstep checks (the sentence exists in the source), not
  budget checks, so they are left as is. The budget/real-prompt repoint belongs to BH-3 (§2.3).

**Owned by BH-3 (not edited here; all green at the time of this audit):**
- `generation/tests/test_harness_v2.py`: `test_rule_0_9_blueprint_scaffolding_stays_within_budget`,
  `test_rule_0_9_total_prompt_stays_under_the_tripwire`, `test_rule_0_9_v2_is_the_worst_case`; the constants
  `BP_SCAFFOLD_BUDGET`, `BP_TOTAL_TRIPWIRE`, `BP_READING`, `BP_READING_V1`, `BP_READING_SCAFFOLD`; `_scaffold_len`.
- `generation/tests/test_wave0_prompts.py` ~63-105: the ALSO-AVAILABLE line tests.
- `generation/tests/test_phase_aw.py` ~146-160: the hybrid keeps the ORB + STATUS pitch sections.
  (BH-1 only appended `test_phase_aw_all` at the end of that file.)

## 5. Environment pins

- **`generation/tests/conftest.py`.** At session start it pops every runtime flag and override the droplet or a
  dev shell may carry, so env-clean (= rollback) is the deterministic default and live-path tests set their flag
  explicitly:
  - flags: `BTS_HARNESS_V2`, `BTS_VOCAB_GATE(_SCHEMA)`, `BTS_TRIAD`, `BTS_BLUEPRINT_VOCAB` (for BH-3),
    `BTS_STAGE_ATTEMPTS`;
  - model and route overrides: `BTSGEN_MODEL`, `BTSGEN_OPENROUTER_*`, `BTSGEN_OLLAMA_*`,
    `BTSGEN_PROMPT_ENRICH*`, `BTSGEN_IMAGE_*`, `BTSGEN_FEEDBACK_*`;
  - every vendor key.

  It also points `BTS_FORGE_LEDGER` at a temp file.
- **`web/tests/conftest.py`.** It already pinned the DB, dev auth, `BTSWEB_UNLIMITED_EMAILS` /
  `BTSWEB_ADMIN_EMAILS` (deliberately different), the public URL, logs and the traffic dir. It now also pops:
  - every other `BTSWEB_*` knob (secret key, env, cookies, proxy, admin write age, card-art budgets, forge
    limits, model prices, workshop URL, mail from);
  - `RESEND_API_KEY`, the Stripe fee and webhook vars, and the Discord/GitHub OAuth vars;
  - the btsgen flags and overrides and the vendor keys.

  It sets a temp `BTS_FORGE_LEDGER`.
- **Quarantine leak (found while checking pins).** Both suites wrote ~20 fake cards per run into the gitignored
  `generation/scratch/_class_gen` (30 MB there now). That directory is also what `CardValidator.known_cards`
  snapshots, so the tests read back cards from earlier runs.
  - Generation culprit: `cli_bench.main()` → `point_btsgen_at_mod_contract()` reloads `btsgen.paths`. The bench
    test now makes the re-point a no-op.
  - Web culprit: `web/forge.py`'s import-time re-point. The web `app_module` fixture now aims
    `paths.GENERATED_DIR` at the temp tree.
  - Verified: a full run of either suite leaves `_class_gen` untouched.
  - Standalone `python -m tests.test_phase_xx` runs skip conftest and can still write the default scratch
    ledger/quarantine. That is acceptable for a dev tool.

## 6. Coverage of what changed since the tests were written

| change | live-path test(s) | added in BH-1 |
|---|---|---|
| Pricing v3 tiers ($3=2/$5=4/$10=10), custom $11..$500 at 1 token/$, Stripe fee passed to donor | `web/tests/test_billing.py`: `test_tier_table_maps_ids_to_tokens`, `test_gross_for_nets_the_tier_after_stripes_cut`, `test_gross_for_follows_a_changed_fee_config`, `test_custom_info_is_one_token_per_whole_dollar_inside_the_bounds`, `test_custom_info_refuses_anything_but_a_whole_dollar_int_in_range`, `test_billing_probe_ships_the_tiers_even_when_disabled`, `test_billing_probe_ships_the_custom_amount_rule`, `test_donate_creates_a_two_line_item_session`, `test_donate_creates_a_custom_amount_session`, credit/refund tests | — |
| "buy"/"purchase" never in donor copy | **was untested** | `web/tests/test_pages.py::test_donor_facing_copy_never_says_buy_or_purchase` (+ scanner self-test). **Caught a live violation**: the donation-history row for pre-v3 pack rows said "Bought N tokens for $X"; now "Token pack, $X". The sanctioned negations from `PRICING_V3_COPY.md` ("nothing to buy", "not purchases of goods or services") are allow-listed. |
| Two-model BYOK split (Design vs Card-coding) | `web/tests/test_byok_two_models.py` (6 tests: role→model routing, blank card model = one-model forge, per-(role, model) usage, route passes `card_model`, estimate split) | — |
| Admin panel 4-hour sign-in rule for writes | `web/tests/test_admin_users.py`: `test_a_fresh_sign_in_is_stamped`, `test_stale_operator_sessions_can_look_but_not_touch`, `test_a_session_without_the_stamp_must_sign_in_again`, `test_a_session_just_inside_the_limit_still_writes`, `test_a_non_admin_with_a_fresh_session_is_still_forbidden`, plus admin-source tests | `test_the_write_window_defaults_to_four_hours`; `test_admin_emails_unset_means_no_operator_even_with_an_unlimited_list` (fresh interpreter) |
| Magic-link email auth | `web/tests/test_auth_email.py` (send, CSRF, 503 when off, dev link, send failure, GET doesn't consume, POST burns the link → 410, expiry, day-old sweep, limiter drops the 4th, production-mode bypass block), `test_auth_link.py` | — |
| `/workshop` redirect + download-page version | `web/tests/test_pages.py`: `test_workshop_short_link_redirects_to_the_item`, `test_workshop_url_env_default`, `test_download_leads_with_the_workshop_and_keeps_the_zip`; `test_security.py::test_download_page_stamps_version_from_manifest` (the version is server-rendered; `download.js` is a 5-line copy helper) | — |
| Hosted route: Ollama Cloud primary + usage/cost gate → OpenRouter glm-5.3 → glm-5.2 | `generation/tests/test_ollama_quota.py` (parse, ceilings, metered-billing hold, poll cache, kill switch, chain routes around saturation), `test_ollama_failover.py::test_default_chain_shape` + breaker/status-code tests | the exact default ceilings (0.95 / 0.97, both sides of each line) in `test_ceilings` |
| Stub-provider retry pinning | `generation/tests/test_generator_stream.py`: `test_looks_like_stub`, `test_stub_answer_blocks_provider_and_retries`, `test_provider_field_only_on_openrouter`; `test_frontend.py::test_run_stage_rerolls_away_from_the_failed_provider` | `test_stub_block_expires_after_an_hour` (TTL 3600, release, static ModelRun never expires) |
| Explicit-request check (`frontend/request.py`) | `generation/tests/test_frontend.py::test_explicit_requests` (detection + negations, HARD RULE line, repair message, window pinning, picker preference, staged forge honours 2/2) | — |
| Site-traffic reporting | `web/tests/test_traffic.py` (parser, bots, referers, windows, CLI, GoAccess soft failure, admin-only routes, CSP) | — |

### Covered only by smokes / not testable offline

| what | why | smoke / check by |
|---|---|---|
| Every C# engine path (EffectRunner, TriggerRunner, DataCard hooks, Powers, codec import) | no C# test project (§8) | AutoSlay smoke per phase: godot.log tags, 0 mod exceptions, 0 "Localization formatting error" |
| Card text in game (`ForgedCards.Describe` == `cardgen.describe`) | no C# string extractor; the phase test greps source fragments only | AutoSlay + godot.log localization grep |
| Energy actually spent / `AfterEnergySpent` | AutoSlay plays through `CardCmd.AutoPlay` and never pays energy (rule 0.3) | manual play |
| Browser JS: BYOK two-model inputs (`byokModels()`), admin "Site traffic" card, donation-history rendering, render.js output | no JS test harness; only source greps | `web/tools/ui_smoke.mjs` (headless Chrome via CDP) or a manual pass after deploy |
| Resend HTTP call itself | the suite stubs `_send_magic_link` | prod sign-in check (configured + verified 2026-09-24; inbox placement still unchecked) |
| Stripe Checkout + webhook against Stripe | network | Stripe test-mode run on the droplet |
| Ollama `/api/usage` live shape, OpenRouter provider names, glm upstream stubs | network | forge log grep (`placeholder`, `[route]`) on the droplet |
| nginx log → `traffic_report.py` timer, GoAccess install | droplet systemd | admin traffic card after deploy |
| Workshop upload / mod zip | Steam | `~/tools/ModUploader` run + item page check |

## 7. Gap-tester folders

The Wave 5 plans cite `generation/scratch/gaptest-bb` … `gaptest-bf`. Those folders are **not in this checkout**.
This checkout's (gitignored) `generation/scratch/` has `gaptest-aj` … `gaptest-ba` and `gapclose-ba` only, and
`generation/scratch/` is in `.gitignore`, so none of them is in the repo either. A fresh clone cannot rebuild any
phase's tester or see its tag record.

**Rule (from Phase BI on).** Each phase's tester is self-contained and committed next to its phase test:

```
generation/tests/gaptest-<xx>/build_tester.py                 # builds + stages the tester class (slot 04)
generation/tests/gaptest-<xx>/godot_<XX>_tags_<SEED>.txt      # the saved godot.log tag grep per smoke seed
```

- The path is not gitignored (checked with `git check-ignore`).
- pytest does not collect `build_tester.py`.
- The phase test asserts the tags file exists and contains the phase tag plus `Auto-selected` where relevant.
  The existence check must be an assert, not an `if exists():` guard.

Nothing was moved in BH-1. Backfilling bb–bf is optional, and only possible from wherever those folders still
exist (the wave-5 worktree).

## 8. C# has no test project

There is no C# test project (`mod/BlankTheSpire.csproj` is the only project). **The AutoSlay smoke is the only
engine test.** For every phase, the `godot_<XX>_tags_<SEED>.txt` grep is the engine's regression record:
- ≥1 phase tag fired;
- 0 mod exceptions;
- no BlankTheSpire frame in a stall stack;
- 0 "Localization formatting error".

It must live in the repo at the §7 path, and the phase test must read it. Today the Python suite reaches C# only
through source greps (`_t_engine` / `_cs(...)`), which prove that wiring text exists, not that it runs.

## Follow-ups (not done in BH-1)

1. `test_phase_aw.py:298`: the `if tester.exists()` guard on the gitignored scratch tester makes that check
   silently absent in a fresh clone. Move the AW tester under the §7 path, or drop the check. (It sits next to
   the BH-3 region, so it is left alone for now.)
2. `class_forge.point_btsgen_at_mod_contract()` overwrites `BTSGEN_GENERATED_DIR` unconditionally, so any caller
   that re-points mid-process (cli_bench, web/forge import) resets the quarantine to scratch. A `setdefault` for
   that one var would remove the hazard at the source. `class_forge.py` is off-limits to BH-1.
3. The DESIGN_HEURISTICS summon_swarm restore (§3) needs Ryan's OK.
4. No JS test harness: consider extending `web/tools/ui_smoke.mjs` with the BYOK two-model inputs and the
   donation-history row.
5. Backfill `gaptest-bb..bf` testers + tag files into the repo if the wave-5 worktree still has them.
6. The phase tests' flag-off blueprint wording checks (§4) can move to the real prompt once BH-3's tree lands.

## Rule-0.9 readings after BH-3 (merged tree, 2026-10-01)

Printed by `uv run python -m tests.test_phase_bh` (harness v2 on, `BTS_BLUEPRINT_VOCAB=tree`, dossier, triad, seed 1).
Re-record here at the §4 pre-release re-pass.

| reading | chars | ceiling |
|---|---|---|
| `vocab_index` | 5,914 (210 tokens, clause cap 34) | 6,000 |
| largest single-archetype prompt (`forge_ramp`) | 61,807 | 70,000 |
| all-ops path | 112,644 | 120,000 |
| scaffold on the all-ops path (from the block markers) | 45,789 | 46,000 |
| `full` path, untrimmed (byte-identical to pre-BH) | 108,282 | snapshot |
| dry run normal / orb / hybrid | 54,778 / 64,437 / 70,514 | — |

Merged suite after BH-1 + BH-2 + BH-3: generation **586 passed**, web **293 passed**, `test_phase_bh` 92/92.

## Exit bar

- generation suite green: `uv run python -m pytest` from generation/ (580 passed at BH-1)
- web suite green: `pytest web/tests` with PYTHONPATH=generation (293 passed at BH-1)
- both suites green on a droplet-like shell (BTS_HARNESS_V2=1, BTS_VOCAB_GATE=heuristic, vendor keys set)
- every tests/test_phase_*.py exposes test_phase_<xx>_all() calling main()
- no test greps web/static/app.js for a renderer that lives in render.js
- every v1 / gate-off / triad-off test is labelled ROLLBACK and has a live-path twin
- no pytest.skip / xfail in generation/tests or web/tests (the one importorskip("PIL") in web test_art_thumbs is a dependency guard; PIL is in the venv)
- a full suite run leaves generation/scratch/_class_gen untouched
- donor-facing copy never says buy / purchase (test_pages)
- each pricing v3, BYOK split, admin 4 h, magic link, /workshop, hosted route, stub pinning, explicit request and traffic change has a live-path test (table in §6)
- each new phase commits generation/tests/gaptest-<xx>/build_tester.py + godot_<XX>_tags_<SEED>.txt

## Final readings at v70 (pre-release, 2026-10-05)

Rule 0.9b re-pass on `wave6` before the v0.4.0 release (plan §4). Printed by `uv run python -m tests.test_phase_bh`
(102/102; harness v2 on, `BTS_BLUEPRINT_VOCAB=tree`, dossier, triad, seed 1). Ceilings are the ones Ryan set during the
wave (§7 of the plan); none was raised for the release.

| reading | chars | ceiling |
|---|---|---|
| `vocab_index` | 9,703 (274 tokens, clause cap 72) | 11,000 |
| largest single-archetype prompt (`slot_machine`) | 77,619 | 80,000 |
| per-archetype scaffold max (`exhaust_pyre`) | 27,537 | 32,000 |
| triad normal / orb / hybrid | 69,442 / 79,433 / 85,178 | 90,000 |
| all-ops path | 130,589 | 140,000 (tripwire) |
| scaffold on the all-ops path | 48,419 | informational |
| `full` path, untrimmed | 121,649 (scaffold 48,141; VOCABULARY.md 73,508) | snapshot |

Suites (clean state, 2026-10-05): generation **608 passed**, web **293 passed**; the same counts on the droplet-like
shell (`BTS_HARNESS_V2=1 BTS_VOCAB_GATE=heuristic BTS_BLUEPRINT_VOCAB=tree`). `generation/scratch/_class_gen` was
untouched by both runs (15,232 files, newest mtime unchanged).

Exit bar walk: every line holds. All 10 wave-6 phase files (bi..br) expose `test_phase_<xx>_all()`, assert a Python
describe literal and grep the C# fragment, and assert their two `godot_<XX>_tags_<SEED>.txt` files; every
`gaptest-b[i-r]/` holds `build_tester.py` + two tag files. One fix in the re-pass: `test_phase_bn` / `bq` / `br` still
carried the build-time "smoke pending" early return (`if not any(p.exists() …): return`), which would have let a
deleted tag record pass silently. The guard is removed; a missing record now fails the test. No skip / xfail (the
`importorskip("PIL")` dependency guard stays); no `app.js` renderer greps (the one `app.js` reader is the BYOK
`PROVIDERS` literal, which lives there); no test still names v0.3.0 / vocab 60 except `test_phase_bf`'s own
history line.

**Wave 6 in one paragraph.** Phases BH..BR on `wave6`: BH (v0.3.0 shipped, this audit, gaps #62–#79 logged, the
vocabulary tree replacing the whole-file paste), then BI (v61, trigger filters) · BJ (v62, combat-history scales +
conditions) · BK (v63, `hits_scale`) · BL (v64, Strength loss / strip / Doom) · BM (v65, base-power statuses, replay,
next-turn Block, retain hand) · BO (v66, recursion / put-back / `on_shuffle` / `grant_keyword`) · BP (v67, `cost_delta`
+ small reactive triggers) · BQ (v68, orb extras) · BN (v69, on-kill, random generation, autoplay) · BR (v70, stun,
discard-all + `cards_removed`, growing turn-start damage) — vocab v61 → v70, generation 580 → 608 tests. The smokes
found three real engine bugs that no offline test could see: an amount-less `retrieve_card` retrieved nothing (BO);
a missing `break` in `DataCard.DeclareEffects` since BM gave every orb / trigger / forge / summon card a stray
`BurstPower` var and crashed any card carrying two such ops at run start (found in BQ); and `trigger_passive` passed
the played target to Frost / Dark / Plasma orbs, whose `Passive` throws on a target (BQ). Two stalls stay
unexplained and unreproduced: the BM1 whole-process freeze in the Act 3 Queen fight (turn 13) and the BR2 Act 1
stall after a Sly auto-play overlapped Gambler's Brew's discard-and-draw; both seeds completed on re-run.
