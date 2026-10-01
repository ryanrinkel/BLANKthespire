# Wave 6 scout: generation / harness side (2026-10-01, HEAD ae10f06 on main, vocab v60)

Read-only. No repo file modified. Scripts used live in this scratchpad (`budget.py`, `kindsave.py`, `gateratio.py`).
Line numbers are from today's tree. Symbol names are authoritative; numbers are hints.

---

## 1. Prompt budget (rule 0.9)

**Where it is:** `generation/tests/test_harness_v2.py`
- `BP_SCAFFOLD_BUDGET = 46_000` :354
- `BP_TOTAL_TRIPWIRE = 120_000` :357
- `BP_READING = 108_282` :374 (v2, re-taken at the end of Wave 5)
- `BP_READING_V1 = 108_179` :376
- `BP_READING_SCAFFOLD = 45_537` :377
- `_scaffold_len()` :381 is `len(bp) - len(VOCABULARY.md)`.
- Asserts: `test_rule_0_9_blueprint_scaffolding_stays_within_budget` :387 (v2), `test_rule_0_9_total_prompt_stays_under_the_tripwire` :398 (v2), `test_rule_0_9_v2_is_the_worst_case` :408 (v1 must be `<= BP_READING`).
- All three measure `_BlueprintContract(mode="dossier", triad=True, seed=1).system_prompt()`. That call passes **no** `selected_ops` and no `class_kind`, so the prompt is unpruned. Production never runs that path; see §2.

**Measured now** (`scratchpad/budget.py`, mirroring the test exactly). The numbers match the snapshots to the char:

| reading | now | ceiling | headroom |
|---|---|---|---|
| VOCABULARY.md | 62,745 chars (63,435 bytes) | none | n/a |
| v2 total | **108,282** | 120,000 tripwire | **11,718** |
| v2 scaffold (total minus vocab) | **45,537** | 46,000 | **463** |
| v1 total | 108,179 | `BP_READING` 108,282 | **103** |

The three tests all pass today (the full suite included them).

**What the headroom means for Wave 6:**
- **`test_rule_0_9_v2_is_the_worst_case` trips on the first VOCABULARY.md row larger than 103 chars.** That is by design: the readings are snapshots. The first phase of the wave must re-take all three readings in one commit and put the numbers in the commit message (the Wave 5 §2 procedure).
- **The scaffold budget is the real constraint.** 463 chars across ~12 phases is about 38 chars per phase, below the Wave 5 allowance of ≤60. Every `class_forge.py` pitch or prose addition must be paid for with a cut. Wave 5 ended net -37 on scaffold (45,574 to 45,537), so it is doable, but only with discipline.
- **Row sizes are bigger than 250.** The Wave 5 rows measured 422 to 808 chars for op rows (`sly` 422, `held_discount` 494, `draw_until` 446, `exhaust_card` 808), 284 to 345 for status rows, and ~200 for a condition row. VOCABULARY.md grew 58,591 to 62,745 (+4,154) over 5 vocab phases, about **830 chars per phase** once prose touch-ups (Triggers list, payload lists) are counted.

**Projection for +12 phases:**

| assumption | vocab growth | v2 total | vs 120k |
|---|---|---|---|
| the brief's 12 × 2 × 250 | +6,000 | ~114.3k | 5.7k under |
| measured Wave 5 rate (830/phase) + 60/phase scaffold | +10,700 | ~119.0k | ~1k under (brushes it) |
| Wave 2 to AZ historic rate (996/phase) | +12,000 | ~120.3k | **crosses** |

**Verdict:** at realistic row sizes the 120k tripwire is reached in the last two or three phases of the wave. The 463-char scaffold budget binds well before that. Plan to build the shrink lever (§2) early in the wave rather than at the trip.

---

## 2. The shrink lever: kind-gating the VOCABULARY paste

### Where the vocabulary is pasted

- **Blueprint prompt:** `class_forge.py:_BlueprintContract._system_prompt_legacy` :255. `vocab = paths.VOCABULARY.read_text()` :257 is interpolated whole at `{vocab}` :265 ("expressible with ONLY these:\n{vocab}\n\nThere are NO ops…"). `system_prompt()` :238 then runs `_prune_archetype_sections` (:1047) only when `harness_v2.enabled() and self.selected_ops is not None`. That pruning acts on class_forge's own pitch paragraphs (`_PRUNABLE_SECTIONS` :1006–1034), never on the vocabulary. (Line 1514 is the RELIC vocabulary in `_RelicContract`, unrelated.)
- **Card prompt:** `contract.py:_system_prompt_v1` :247 (vocab :249, pasted :257) and `_system_prompt_v2` :303 (vocab :311, pasted :327).
  - **The card prompt is already kind-gated.** `btsgen/gate.py` (`GatedPrompt` :369, `build` :653) runs when `BTS_VOCAB_GATE` ≠ off, and the droplet runs `heuristic`.
  - Its class-kind tier uses `SECTION_FAMILY` :72, `KIND_FAMILY` :86 and `CLASS_FAMILIES`. It drops `## Orbs` / `## Forged statuses` / `## Forged summons` / `## Hybrid classes` and their `FAMILY_OPS` rows for a class that does not own them. It always drops `## The signature potion` (`ALWAYS_DROP` :82).
  - The kinds arrive through the `contract.set_class_scope({"kinds": _declared_kinds(bp)})` ContextVar (`class_forge.py:~3176-3185`, `_declared_kinds` :1712).
  - Measured card prompt (v2): full 122,564; normal-class core 32,170; orb core 36,091; summon core 40,282. `test_gated_card_prompt_budget` (`test_vocab_gate.py:203`, core < 0.65 × full) has ~47k of headroom.
  - **Wave 6 rule for the card side:** a new op that is in none of `CORE_OPS` / `GATED_OP_ORDER` / `FAMILY_OPS` lands in the core and every card pays for it. Append each new op to `GATED_OP_ORDER` (:108), as BB/BC/BD did.
- **So the lever only has to be built for the blueprint.**

### How the class kind is known at blueprint time

`frontend/builder.py:480-483` (the staged front end, the production path) constructs:

`_BlueprintContract(mode="dossier", triad=…, seed=…, selected_ops=<chosen archetypes' ops>, class_kind=(chosen.class_kinds or chosen.class_kind), nominated_sections=…)`

- This happens only under v2. `Candidate.class_kind` / `class_kinds` (`frontend/dossier.py:32-62`) is `normal | orb | status | summon`, or a hybrid list.
- Forge, balance, discard and transform are not class kinds. They are archetype `mechanic_kind`s (`harness_v2._pool_kind` :209) and are already visible through `selected_ops`.
- Legacy one-shot paths pass no kind and would stay ungated: `cli_forge_class.py:117/132` and `ollama_mix.py:551` (used only when the staged front end is off).

### Proposed design (about half a day to one day)

1. **Factor a pure helper out of `GatedPrompt.__init__`'s section loop:** `gate.kind_gate_vocab(vocab: str, kinds, *, keep_potion=True) -> str`.
   - It splits on `^## `.
   - It drops `SECTION_FAMILY` class families (orbs / custom_status / summons / hybrid) the kinds don't own.
   - It strips those families' `FAMILY_OPS` rows from the Effect-ops table, reusing `_split_op_table`'s row regex.
   - Orb only: it also strips the `orbs_match` / `orb_count_ge` condition rows (VOCABULARY.md:214-215, 251 chars).
   - It **keeps** `## The signature potion`, because the blueprint declares the potion (test_phase_ba: "contract: the blueprint prompt requires it").
   - Do not restructure VOCABULARY.md itself. `test_exemplars.vocab_ops()` (:82), `catalog.live_vocab_tokens()` and gate.py all parse the file.
2. **In `_BlueprintContract.system_prompt()`** (:238), when `harness_v2.enabled() and self.class_kind is not None`, gate the vocab before interpolation. The simplest way is to give `_system_prompt_legacy(vocab=None)` a parameter. A nominated section key `orb` / `status` / `summon` in `self.nominated_sections` keeps that kind's vocab section, so the existing W0.5 override still works.
3. **Consistency fix.** `_prune_archetype_sections` currently lists pruned `orbs` / `status_pool` / `summon_pool` in the ALSO-AVAILABLE one-liner. Once the vocab rows are gone, that line must stop offering unowned pool kinds, or it advertises ops the prompt no longer documents. Drop the three pool pitches from the line when vocab gating is on. That is also a small scaffold saving.
4. **Optional second tier (forge):** gate `## Run-persistent Forge` (732) plus the `spend_forge` / `summon_blade` / `blade_empower` rows (~1,572) on `selected_ops ∩ {forge tokens}`. This saves ~2.3k on non-forge classes. `forge` itself stays core.

### Chars saved (measured, `scratchpad/kindsave.py`, current VOCABULARY.md)

| class kinds | vocab dropped | vocab pasted |
|---|---|---|
| normal | 13,426 (orb 3,640 + status 3,354 + summon 5,948 + hybrid 484) | 49,319 |
| orb | 9,786 | 52,959 |
| status | 10,072 | 52,673 |
| summon | 7,478 | 55,267 |
| orb+status | 5,948 | 56,797 |
| orb+summon | 3,354 | 59,391 |
| status+summon | 3,640 | 59,105 |

The optional forge tier adds about −2.3k for non-forge classes.

### The catch: the rule-0.9 tests measure a path production never runs

- The asserts build the contract with no `selected_ops` / `class_kind`, so they see neither the existing pitch pruning nor this vocab gate. Building the lever alone moves **no** reading.
- The test change must go with it. Keep the ungated reading as an informational snapshot. Assert the tripwire on the **worst real path**: the max over `class_kind ∈ {normal, orb, status, summon, each hybrid pair}` with `selected_ops` = every `_PRUNABLE_SECTIONS` token (nothing pruned). That is roughly orb+summon (only the status section dropped, about −3.4k). Relief on that path is modest: about 3.4k worst case, about 13k typical.
- `_scaffold_len` (:381) subtracts the **full** VOCABULARY.md length. On a gated prompt it must subtract the gated vocab length, or the scaffold reading goes wrong. Change it to measure from the `{vocab}` boundaries, for example by splitting on "expressible with ONLY these:\n" and "\n\nThere are NO ops".

### Tests that pin blueprint or vocab prompt content (to re-check when building)

- `test_harness_v2.py:387/398/408` (the readings, plus `_scaffold_len`). `:436` `test_blueprint_prompt_prunes_unselected_pitches_and_asks_nominations` asserts `len(pruned) < 0.8 * len(full)`; gating only helps that.
- `test_wave0_prompts.py:63-105`: the ALSO-AVAILABLE line must name `summon_pool`, `status_pool` and `orbs` (:72). **This breaks if step 3 removes the pool pitches.** Update it to expect them only when vocab gating is off.
- `test_phase_aw.py:146-160`: hybrid keeps ORB + STATUS pitch sections. Unaffected, but add a vocab-section analog.
- `test_vocab_gate.py:124` `test_class_kinds_move_sections_into_the_core_or_out` is the card-side pattern to copy. If `kind_gate_vocab` is factored out of `GatedPrompt`, all of test_vocab_gate must stay green, especially `:63` `test_off_is_byte_identical` and `:249` `test_schema_split_loses_nothing`.
- Many phase tests (am…bf) print the blueprint length or assert their own wording is in the prompt. They use the ungated call, so they are unaffected.
- New test needed:
  - an orb-kind blueprint keeps `## Orbs` and the `channel_orb` row;
  - a normal-kind blueprint has neither;
  - a hybrid keeps `## Hybrid classes`;
  - `## The signature potion` is present for every kind;
  - nominated `summon` re-adds `## Forged summons`.

---

## 3. Lockstep checklist (Wave 5 §1, items 1-17), re-anchored for today

| # | file / symbol | Wave-5 line | **today** | note |
|---|---|---|---|---|
| 1 | card.schema.json `$defs.effect` `additionalProperties:false` | :32 | **:32** | effect def :30 |
| 1 | op enum `$defs.effect.properties.op.enum` | :35 | **:35** | |
| 1 | `effect.trigger.enum` | n/a | **:56** | |
| 1 | `effect.status.enum` / `scale.enum` | n/a | **:54 / :52** | |
| 1 | `triggerEffect` def / its `op.enum` | :199 | **:223 / :229** | moved +30 |
| 1 | `$defs.condition` / `.kind` enum | :283 | **:307 / :313** | moved +30 |
| 2 | VOCABULARY.md `## Effect ops` | :7 | **:7** (rows :10-54) | |
| 2 | `add_trigger` row | :30 | **:32** | |
| 2 | Conditions section / rows | :200-221 | **:205 / rows :214-234** | |
| 2 | Triggers section | :233 | **:246** (trigger list prose ~:264) | |
| 2 | paste sites | `class_forge.py:257/265`, `contract.py:311/327` | **same** (+ v1 card prompt `contract.py:249/257`) | |
| 3 | `bts1.py` `VOCAB_VERSION` | :28 | **:28** (=60) | stamp is inline: "60: Phase BF …" on the same line/comment; test_version greps `"60: Phase BF"` |
| 4 | `cardgen.effect_literal` | :152 | **:187** | named-arg idiom (`Grow:` :280, `OncePerCombat:` :297) |
| 4 | `cardgen.cond_phrase` | :278 | **:327** | |
| 4 | `cardgen._trigger_fragment` | :336 | **:387** | |
| 4 | `cardgen.trigger_sentence` | :414 | **:465** | |
| 4 | `cardgen.describe` | :464 | **:517** | |
| 5 | `validator._BUILD_AROUND_OPS` | :59-75 | **:61** | |
| 5 | caps constants | :171 style | **:81-198** (`_HELD_DISCOUNT_MAX` :81 … `_MAX_SAME_STATUS` :198) | |
| 5 | `_MULTI_FIRE_TRIGGERS` / `_ONCE_PER_COMBAT_TRIGGERS` | :106 / :113 | **:115 / :123** | |
| 5 | `_engine_structural_errors` | :405 | **:422** | |
| 5 | "not on a BASIC" idiom | :815-822 | **:771-945** (purge :779 … add_status_card :945) | |
| 5 | card-only payload rejection | :1022 | **:1118-1122** | |
| 5 | `score_card` / `_score_effect` | :1112 | **:1208 / :1211** | |
| 6 | `census.EXOTIC_STATUSES` | n/a | **:51** | |
| 6 | `census.KEYWORD_OPS` | :62 | **:63** (includes `sly`) | |
| 6 | `_walk_effects` / `cc.ops` / `Census` / `format_report` | :128 / :139 / :222 / :432 | **:131 / :141 / :228 / :415** | |
| 6 | test_census pins | :165/:214 | **:163-165, :214** | these pin `keyword_kinds` of a FIXTURE card (`{"exhaust","retain","innate","ethereal"}` + multi_hit), **not** `KEYWORD_OPS` itself; adding a keyword op does not break them unless the fixture uses it |
| 7 | `bridges.card_tokens` | :40-52 | **:40** (`unblockable` :50) | |
| 8 | `coverage.EXOTIC_MENU_V2` / `REACTIVE_MENU_V2` / `WHEN_MENU_V2` | — / :75 / :79 | **:65 / :77 / :81** | |
| 8 | `coverage.WHEN_MENU_KIND` / `SCALE_MENU` / `SCALE_MENU_KIND` / `KEYWORD_MENU` | :103 / :115 / :137 / :150 | **:108 / :120 / :142 / :155** | |
| 8 | `DIRECTIVE_BY_KEY` / `CENSUS_DETECTOR` / `SECTION_KEYS` / `KEY_KIND` | n/a | **:166 / :202 / :223 / :228** | |
| 8 | test_coverage exact-set pins | :222/218/265 | **:221** (WHEN_MENU_KIND), **:223** (SCALE_MENU), **:228** (SCALE_MENU_KIND), **:229** (EXOTIC_NOMINATE_ONLY), **:230** (KEYWORD_MENU), **:232** (KEY_KIND), samples dict **:243**, `set(samples) == set(_w2_keys())` **:279** (`_w2_keys` :206) | any new WHEN_MENU_V2 / SCALE_MENU / KEYWORD_MENU key needs a sample |
| 9 | `featured.Featured` dataclass | :36-53 | **:35-53** | |
| 9 | `FEATURED_MENU` / `contagion` template | — / :186-190 | **:60 / :189** | |
| 9 | `FEATURED_CLASS_KIND` | :202-299 | **:233-338** (orb :234, status :253, summon :265, forge :288, balance :309, discard :315, transform :332) | |
| 9 | test_featured pins | :164/:237/:290 | sample-set == FEATURED_MENU **:174** (samples :118); kinds == {orb,status,summon,forge,balance,discard,transform} **:247**; class-kind samples :277, set-equality **:302** | |
| 10 | `harness_v2._PREFERRED_OPS` / `_CONDITIONS` / `_TRIGGERS` | :62 / :67 / :70 | **:62 / :70 / :73** | |
| 10 | `compositional_clause` / `exemplar_validator` / `_pool_kind` | :119 | **:123 / :178 / :209** | |
| 11 | `gate.SECTION_FAMILY` / `FAMILY_OPS` / `CORE_OPS` / `GATED_OP_ORDER` / `FIELD_UNITS` | — / :93 / :104 / :108 / :116 | **:72 / :93 / :104 / :108 / :119** | `GATED_OP_ORDER` ends with BD's `held_discount` |
| 11 | test_vocab_gate "schema op with no row" | :104 | **:104** `test_every_schema_op_has_exactly_one_home` | also :124 kinds, :203 budget ratio, :249 schema split |
| 12 | class_forge translation paragraph | :270-281 | **:270-291** | |
| 12 | archetype pitch sections | :338-598 | **:292-597** (ORB CLASSES :292 … SUMMON POOL :557; STRATEGIC LINES :597) | |
| 12 | `_PRUNABLE_SECTIONS` + ALSO-AVAILABLE | :1007-1033 | **:1006-1034, `_ALSO_AVAILABLE_HEAD` :1036, `_prune_archetype_sections` :1047** | |
| 12 | `_ORB_CONDITION_KINDS` | :2096 | **:2099** (value kinds :2104, max :2107) | |
| 12 | test_phase_ar lockstep | :184-198 | **:186-202** | asserts `_ORB_CONDITION_KINDS == schema enum − FORBIDDEN` (:191) and C# `Conditions.Kinds` regex == schema enum (:196-198), plus `TargetKinds` (:199-202) |
| 12 | condition uptime heuristic | :1383-1384 | **`_cond_uptime` :1361**, kind branches :1378-1390 | |
| 13 | archetypes.json `vocabulary.ops` | ids at :5…:3724 | retain_hold :5, forge_ramp :149, ascetic_purge :535, poison_attrition :692, strike_tempo :1060, countdown_ripen :2186, balance_gauge :2296, madness_discard :2379, exhaust_pyre :2633, ambush_alpha :3400, burst_window :3735 | ~+3 to +11 shift |
| 13 | test_archetypes backtick rule | :122 | **:121-129** `test_ops_are_live_tokens` (uses `catalog.live_vocab_tokens`, i.e. every backticked token in VOCABULARY.md); buildable pin **:80** | |
| 14 | test_exemplars coverage | :143 | **:143** `test_pool_covers_every_vocabulary_token` | harvests ops / statuses / conditions from VOCABULARY tables and scales / triggers from the schema; every one needs ≥1 exemplar. `needs` discipline :181 (class-only token map :30-39) |
| 15 | DESIGN_HEURISTICS.md | — | read by `contract.archetype_balance_note` **:77**, `catalog.prompt_block` :327 | |
| 16 | VOCABULARY_GAPS.md | — | last entry `### 61.` :644 | see §7 |
| 17 | **MOVED.** `web/static/app.js case "op":` | app.js | **web/static/render.js**: `effPhrase` :527 (`switch (e.op)` :532), `condCore` :497 (`switch (c.kind)` :499; `turn_at_most` :508), relic `fmtHook` :141, `potionLines` :253 | **`case "op":` no longer exists anywhere.** BB-BF tests grep `render.js`. The tests that still grep app.js are the 3 pre-existing failures (§5). |

---

## 4. The phase-test idiom (from `tests/test_phase_bf.py`, 147 lines; BB/BC identical in shape)

```
"""Phase XX — <mechanic> (VOCAB_EXPANSION_6_PLAN, gap #N, vocab vNN) — offline. Run: uv run python -m tests.test_phase_xx"""
from btsgen.class_forge import point_btsgen_at_mod_contract
point_btsgen_at_mod_contract()                       # BEFORE importing paths-bearing modules
from btsgen import bts1, cardgen, census, coverage, featured, paths
from btsgen import class_forge as cf
from btsgen.validator import CardValidator
_PASS = 0; _FAIL = 0                                  # module-level counter: conftest's guard reads _FAIL
MOD_CODE = paths.VOCABULARY.parents[1] / "BlankTheSpireCode"
def check(cond, msg): ... prints "  FAIL: msg"
def _cs(*parts): read a C# source file under MOD_CODE
def _card(effects, rarity=..., cost=..., ctype=...): minimal card dict
def _errs(card): lazily-built CardValidator().validate(card).errors

def test_version():   bts1.VOCAB_VERSION >= NN; regex `public const int VocabVersion = (\d+);` on ForgedCards.cs >= NN;
                      bts1 <= C#; "Phase XX" + tokens in ForgedCards.cs; "NN: Phase XX" in bts1.py text
def _t_engine():      substring greps of C# sources (DataCard / EffectRunner / TriggerRunner / OrbRunner / SummonRunner /
                      ForgedCards / Conditions) for the exact wiring lines
def _t_rules_and_describe(): validator accepts / rejects shapes; cardgen.describe(effects, target) == "<literal>"
def _t_contract():    VOCABULARY rows, schema enums (json.loads), exemplar ids in exemplar_pool.json + they validate,
                      census / coverage / featured membership, class_forge pitch wording, render.js wording,
                      DESIGN_HEURISTICS stamp; prints the blueprint length (rule 0.9, informational only, no ceiling)
def main() -> int: run all, print "N passed, M failed", return 1 if _FAIL else 0
def test_phase_xx_all(): global _PASS,_FAIL; _PASS=_FAIL=0; assert main() == 0, ...   # rule 0.10
if __name__ == "__main__": sys.exit(main())
```

- **Describe byte-match is half-automated. There is no C# string extractor and no C#-side test.**
  - Python side: `cardgen.describe()` is asserted against a hand-written expected literal. BC uses a `cases` table (`test_phase_bc.py:144-170`).
  - C# side: the test checks that **source fragments** of `ForgedCards.Describe` exist in ForgedCards.cs. Examples are `'case "sly": parts.Add("Sly."); break;'` (bb:125) and `'return $"Exhaust {what} in your hand.";'` (bc:163).
  - `cardgen.effect_literal()` is asserted against the exact `new EffectSpec(...)` C# literal (bc:166-170).
  - So the two strings are "byte-matched" only through a human writing the same literal in both places. The C# interpolation is not executed.
  - The in-game check is AutoSlay plus the `godot.log` "Localization formatting error" grep from memory.
- **Rule 0.10:** `test_phase_xx_all()` must call `main()`. `tests/conftest.py:68-78` `_check_counter_guard` also fails any test whose module `_FAIL` grew, so even a bare `test_version()` gets caught. That is the "ERROR at teardown" seen in §5. Don't pin a private prompt ceiling; just print it.
- No new `test_phase_*` file needs registering. pytest collects `tests/test_*.py` by default.

---

## 5. Test-suite baseline

Command: `uv run python -m pytest -q --no-header -p no:cacheprovider` from `generation/`. I ran it **without** `-x` so every failure shows. 96.8 s.

**548 passed, 3 failed, 3 errors** (the errors are the same three tests' conftest teardown guard, not extra failures).

All of it is the pre-existing aq/as/ba set, and all of it is **stale test paths, not broken features**. These tests still grep `web/static/app.js` for strings that moved to `render.js` in the web refactor:

| test | failing checks |
|---|---|
| `test_phase_aq.py::test_phase_aq_all` | "app.js labels both hooks and the multiplicative mode" |
| `test_phase_as.py::test_phase_as_all` | "app.js labels both modifiers"; "app.js renders every_n / card_type (+ the missing on_hp_lost label)" |
| `test_phase_ba.py::test_phase_ba_all` | "app.js lists potion_pool among the class mechanics"; "app.js formats the potion's lines" (`function potionLines(` is now `render.js:253`); "… tells the player it is an ADDITION to the table"; "the feedback popout has a potion prompt" |

A 15-minute fix before Wave 6 is to repoint those 7 checks at `render.js` (or app.js + render.js). That gives a fully green baseline, so a Wave 6 regression can't hide among known reds. Full log: `scratchpad/fullsuite.txt`.

---

## 6. AutoSlay smoke + release tooling

**`btsgen/cli_autoslay_smoke.py`** (entry point `btsgen-autoslay-smoke`, pyproject :39), `main()` :247:
- `--seeds` (nargs+) and `--count` (default 5) are mutually exclusive.
- `--character` (`classN` = slot N), `--relic {auto,force,off}` (default auto), `--app-id` (default 2868840), `--timeout` (default 900 s per run), `--build` (dotnet build + deploy first).
- The smoke does **not** stage tester classes itself. It only injects or restores a smoke relic (`_stage_relics` :222).
- `godot.log` is at `GAME_LOG = game_paths.game_user_dir()/"logs"/"godot.log"` (:55), which is **`C:\Users\ryanr\AppData\Roaming\SlayTheSpire2\logs\godot.log`**.

**How a tester class is authored.** The latest tester present is `generation/scratch/gaptest-ba/build_tester.py`. The Wave 5 `gaptest-bb..bf` folders are not in this checkout, and the vocab-expansion-5 worktree is gone.
- **Layout:**
  - one `build_tester.py` (the docstring gives the commands, the tags to grep, and the pass bar);
  - saved tag greps `godot_<XX>_tags_<SEED>.txt`.
- **What the script does:**
  - builds `CHARACTER_N` dicts (name, description, max_hp, max_energy, orb_slots, optional status / summon / orb / potion pools, and `starting_deck: [{"slot": k, "count": n}]`, where `slot` = 1-based index into the cards list);
  - builds `CARDS_N` via a `card(cid, name, type, rarity, cost, target, effects, upgrade_effects, character)` helper;
  - validates everything first (`CardValidator(extra_statuses=…)`, `cf._validate_potion`);
  - backs up and stages to `%APPDATA%\SlayTheSpire2\forged\characters\NN.json` plus `NN\cards\01.json, 02.json …`;
  - restores with `--remove` (backup suffix `.bagaptestbak`).
- Run it with `uv run btsgen-autoslay-smoke --seeds GAPTESTXX1 --character class4 --timeout 900`.

**Release tooling:**
- `mod/tools/package_release.ps1` exists. `param([string]$Version="0.1.0", [string]$GameMods="C:\Program Files (x86)\Steam\steamapps\common\Slay the Spire 2\mods", [string]$OutDir)`.
- `workshop/build_workspace.ps1` exists. `param([string]$Version, [string]$ChangeNote="update", [string]$GameMods=<same>)`.
- The workspace is `workshop/workspace/` (content/, image.png, mod_id.txt, previews/, workshop.json).

**Versions:**
- `ForgedCards.VocabVersion = 60` (`ForgedCards.cs:45`) and `bts1.VOCAB_VERSION = 60` confirmed.
- **`mod/BlankTheSpire.json` is NOT v0.2.2 in the working tree.**
  - HEAD has `"version": "v0.2.2"`. The working tree has an **uncommitted** `"version": "v0.3.0"` (`git status`: ` M mod/BlankTheSpire.json`).
  - `workshop/workspace/workshop.json` already carries changeNote "v0.3.0 - Vocabulary wave 5 (v56-v60) …".
  - So the Wave 5 mod release is prepared locally but not committed. Whether it was uploaded or deployed is unknown from here.
  - Wave 6 should branch off a tree where that bump is committed, or decide it, so the v0.3.0 / v0.4.0 ordering stays clean.

---

## 7. Catalog coupling

**`frontend/catalog.py:gap_status()` :140:**
- `re.split(r"^###\s+(\d+)\.", text, flags=re.M)` pairs each number with its body.
- The status is `re.search(r"\*\*Status:\*\*\s*\**\s*([a-z]+)", body, re.I)`, lowercased. No match means `captured`.
- New entries parse correctly if they follow the existing block shape:

```
### 62. <title>
- **Surfaced by:** …
- **Fantasy it serves:** …
- **Mechanic sketch:** …
- **Buildable today?** …
- **Priority:** …
- **Status:** captured            (or **Status:** **done (2026-10-0x, vocab v61, Phase BH)** — …)
```

- Only the first `[a-z]+` word after the label matters, so `**done (...)` reads as `done`.
- A header must be `### N.` at column 0. `_GAP_TITLE_RE` :63 also feeds duplicate detection.
- **Collision hazard:** `append_vocab_gaps()` :464 auto-appends `captured` blocks numbered `max+1` when the map stage surfaces off-vocab concepts (the CLI passes it in). Before numbering #62+, check the droplet's copy of VOCABULARY_GAPS.md for auto-appended entries, or a number may be taken twice.
- The audit's "already logged" rows re-open rejected gaps (#11 stun, #37 forced play, #42/#43). Flipping a `rejected` to `planned` is read the same way.

**`gap_refs` format** (archetypes.json, e.g. :49): `"gap_refs": ["VOCABULARY_GAPS#5"]`.
- `_gap_ref_number` :162 takes `#(\d+)`.
- An archetype is BUILDABLE iff every `vocabulary.ops` token is backticked in VOCABULARY.md **and** every gap_ref is `done` (`resolve_buildability`). `test_archetypes.py:80` cross-checks the file's `buildable` flag.
- So a new archetype that references an open gap must ship `"buildable": false` until the phase flips it.

**Which archetype ids should take the new mechanics** (34 archetypes; current `vocabulary.ops` in brackets):

| mechanic | archetype id(s) | why |
|---|---|---|
| `on_card_played` card_type / every_n | `power_ramp` [add_trigger, apply_status, scale]; `strike_tempo` | Rage / Storm / Panache are power-engine shapes; "every 3rd Attack" is Juggling-style attack tempo |
| new history scales | `exhaust_pyre` (exhaust-pile size); `madness_discard` (discards this turn); `tempo_draw` (cards drawn); `big_energy` (energy spent); `poison_attrition` (total enemy Poison); `debuff_expose` (target Vulnerable / Doom stacks) | each already owns the counter's fuel |
| `hits_scale` / X-hits | `strike_tempo` (Finisher); `big_energy` (X-cost Whirlwind / Skewer); `horde_breaker` (Whirlwind AoE) | scaled hit count is their payoff shape |
| enemy Strength loss | `block_bulwark`; `debuff_expose`; `untouchable_ward` | Piercing Wail / Dark Shackles defense; it's a debuff payoff |
| doom | `reaper_lifesteal` (execute + Feed); `debuff_expose` (`target_has_status: doom`); `countdown_ripen` (CountdownPower-style delayed kill) | no Necrobinder archetype exists; a new `doom_reaper` archetype may be cleaner |
| self-drawback debuffs | `self_sacrifice`; `big_energy` (price for energy); `burst_window` (Bullet Time / Wraith Form) | the price-for-power identity |
| on-kill (`when: target_killed`) | `reaper_lifesteal` (Feed / Sunder); `horde_breaker` (Echoing Slash); `iron_regrowth` (gain_max_hp Feed) | |
| random card generation | `token_conjurer` [add_card…]; `fleeting_flux` (Discovery / ethereal generated) | generation is their engine |
| replay / play-twice | `burst_window` (Burst / Double Tap); `power_ramp` (Echo Form) | |
| recursion / put-back / tutor | `madness_discard` (recursion from discard); `retain_hold` (put-back, Thinking Ahead); `ascetic_purge` (draw-pile tutor, Secret Weapon); `exhaust_pyre` (already has retrieve_card) | |
| `cost_delta` | `tempo_draw` [cost_shift]; `big_energy`; `retain_hold` (generalized held_discount); `strike_tempo` (Momentum Strike) | |
| `grant_keyword` | `madness_discard` (grant Sly); `retain_hold` (grant Retain); `fleeting_flux` (grant Ethereal) | |
| orb extras | `orb_channel`; `slot_machine` | the only orb archetypes |

A new archetype would also need a `mechanic_kind` from the fixed set `harness_v2._pool_kind` understands (test_archetypes :105).
