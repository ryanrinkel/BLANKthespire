# Vocabulary Expansion — Wave 3 (Gate G + Phases U → W, spike Y) · EXECUTABLE RUNBOOK

**Status: READY TO EXECUTE — written for an Opus 4.8 agent told "execute what is in this doc".**
Authored 2026-07-12 (Fable 5 session; re-grounded against live code + `AUTOSLAY_VALIDATION_QUEUE.md`
the same day). Successor to `VOCAB_EXPANSION_2_PLAN.md` (Wave 2, P→S, shipped; P/R/S runtime-validated
2026-07-09, Q fix runtime re-validation pending — that's Gate G below). Gap statuses live in
`VOCABULARY_GAPS.md`; this wave closes **#4 (verify), #16-revalidation, #23 rampage, #18 upgrade-op
(no-choice), #19 purge (self-purge form)** and runs the **card-select UI spike** that gates scry /
player-pick variants / graft.

---

## 0. Agent operating protocol (read this first, follow it exactly)

**Scope per invocation: execute exactly ONE phase — the first row in the §0.2 tracker whose status is
`ready` (or resume a `building` one). Do not start a second phase in the same run.** When the phase is
done, stamp everything (§0.6), commit, and stop. **Gate G must be `done` before any vocab phase starts**
— it re-validates a shipped op (`add_card`) whose crash fix has never run in combat; building new vocab
on top of an unvalidated fix compounds risk.

### 0.1 Orient before touching anything

1. Read the live vocab version — **the code is the source of truth, not this doc**:
   - `mod/BlankTheSpireCode/Engine/ForgedCards.cs` → `public const int VocabVersion` (line ~45; **25**
     as of 2026-07-12, the Phase T true-blade bump).
   - `generation/btsgen/bts1.py` → `VOCAB_VERSION` (line ~28; must equal the C# value).
   Your phase ships `VocabVersion = <live value> + 1` in BOTH places (Gate G and spike Y ship NO bump).
   The version numbers in the phase sections below assume you start from v25 — recompute from the live
   value.
2. Check gap statuses parse and match the tracker:
   `cd generation && uv run python -c "from btsgen.frontend.catalog import gap_status; print(gap_status())"`
3. **Measure the baseline test count BEFORE you change anything** (the suite grew past the numbers in
   older docs — trust your measurement, not this doc):
   `cd generation && for f in tests/test_*.py; do uv run python "$f" | tail -1; done`
   If anything is red at baseline, STOP and report — do not build on a broken base.
4. **Line numbers in this doc are anchors, not gospel.** Re-grep every symbol before editing; the repo
   moves.
5. Read `AUTOSLAY_VALIDATION_QUEUE.md` — it is the live record of what has and hasn't run in combat,
   including the Gate-0 env-hang protocol this wave's Gate G executes.

### 0.2 Phase tracker (update this table as you go: `ready` → `building` → `done <date, result>`)

| phase | gap(s) | ships | status |
|---|---|---|---|
| **G — verification closeout** | #16 re-val, #4, hygiene | Q runtime re-validation post-`CreateCard` fix; riposte verify-then-close; file the Phase-T follow-on gaps; gap-log dedup tooling | **done 2026-07-13** — G-1 Q re-val PASS (439 `[Q]` fires / 0 deaths / 0 exc, Windows box, no reboot needed); G-2 riposte #4 flipped done (fires only on enemy attacks, 0 exc); G-3 filed gaps #39/#40/#41; G-4 dedup tooling + test shipped. |
| **U — rampage** | #23 | `grow` field on `damage` (per-card grow-on-play), the base-StS Rampage archetype | **done 2026-07-13 (v26)** — `grow` field shipped + AutoSlay-verified (rampage 8→13→18, quick 4→6→8; per-instance + per-combat reset; 0 grow exc). `rampage_grow` catalog entry BUILDABLE. Also fixed an unrelated ForgedRelic event-damage NRE the smoke surfaced. |
| **V — in-run upgrade** | #18 (no-choice form), touches #3 | op `upgrade_card` (random-in-hand / all-in-hand) riding `CardCmd.Upgrade` | **done 2026-07-13 (v27)** — op `upgrade_card {cards:random\|all}` shipped, COMBAT-SCOPED (hand cards are deck clones — verified vs decompiled `CardCmd.Upgrade`/`Player.PopulateCombatState`). AutoSlay GAPTEST18 (3 seeds): 662 `[V]` fires (290 random / 115 all upgrading 1–5 cards / 257 clean no-ops), 0 mod exceptions. `all`=card-only, `random`=payload-legal. Catalog `battle_smith` BUILDABLE. Player-pick → spike Y. |
| **W — self-purge** | #19 (self-purge form) | card flag `purge` — played card is removed for the REST OF THE RUN (deck-thinning) | **done 2026-07-14 (v28)** — `purge` flag-op shipped + AutoSlay-verified (213 `[W]` fires across 3 deep runs: 37 drafted run-deck removals + 176 generated-copy combat-vanishes; 0 mod exc). `DataCard.GetResultPileTypeForCardPlay` override → `PileType.None` (combat) + `CardPileCmd.RemoveFromDeck(DeckVersion)` (run-permanent); generated copies (null DeckVersion) leave the run deck untouched. purge ⊥ exhaust, forbidden on basics, `purge_warnings` >3/class. Catalog `ascetic_purge` BUILDABLE. Choose-a-card purge → spike Y. |
| **Y — card-select UI spike** | unblocks scry (R-2), #18 player-pick, #19 choose-purge, #7 graft | research + throwaway test card; a written go/no-go, NO vocab | **done 2026-07-14** — GO. `CardSelectCmd` IS present in the current dump (old "not found" was pre-update); recipe proven by shipped base-game cards (Armaments/Brand/Charge/Begone); `ctx`+`Player` already in `EffectRunner.Execute`. **Plan assumption reversed: AutoSlay CAN drive it** (`AutoSlayCardSelector` auto-random-picks; install `AutoSlayer.cs:168`) → future choice-vocab is smoke-testable. Deliverable `SPIKE_CARD_SELECT.md`; gap lines #7/#17-scry/#18/#19 updated. Per-item verdicts: #18 GO/LOW · #19 GO/LOW-MED · scry GO/MED · #7 PARTIAL (blocked on transform #35/#38, not UI). Throwaway in-game eyeball folded into the first choice-vocab phase (not run standalone — base-game call sites already prove the surface). |

Not scheduled this wave (wave-4 pool, re-rank by gap-resurface demand counts): `#20 corruption` ·
`#25 strike-count` (needs a card-tag convention first) · **status-pool `damage_over_time` hook** (cheaply
serves the recurring burn/freeze fantasies, gap #11) · the transform family `#3/#35/#38` (revisit with
U's play-count plumbing + Y's findings) · `#34 lightning chain` (positional — needs a target-adjacency
read; no known surface) · `#37 weapon autonomy` (agency/forced-play — design-first, not plumbing-first).

### 0.3 Environment facts (Linux box — do not rediscover these)

- **Build:** `DOTNET_ROOT=$HOME/.dotnet PATH="$HOME/.dotnet:$PATH" dotnet build mod/BlankTheSpire.csproj -c Debug`
  — auto-deploys to `~/.local/share/Steam/steamapps/common/Slay the Spire 2/mods/BlankTheSpire/`.
  The DLL is **locked while the game runs** — kill the game (`pkill -x SlayTheSpire2`) before building.
- **Repo tooling is Windows-authored.** Convention (explicit user ask): OS-detect and keep branches
  **side-by-side**; never replace a Windows path. See `generation/btsgen/game_paths.py` for the pattern.
- **Two user dirs on Linux (footgun):** the game's `user://` = `~/.local/share/SlayTheSpire2` (forged
  content, logs, autoslay); .NET `SpecialFolder.ApplicationData` inside the game = `~/.config/SlayTheSpire2`.
  Any new C# path that must match game content belongs to the FIRST. (`game_paths.py` documents both.)
- **Generation tests are script-style, NOT pytest:** run
  `cd generation && for f in tests/test_*.py; do uv run python "$f" | tail -1; done`
  (`test_art.py` is the pytest-style exception; it exits silently as a script — ignore it or run it via
  pytest if touched). Measure the baseline count at orient (§0.1.3).
- **AutoSlay smoke — run it WITHOUT asking** (standing user instruction, 2026-07-06; Steam stays open on
  the shared account in Offline Mode). From `generation/`:
  `uv run btsgen-autoslay-smoke --seeds GAPTEST<gap#> --character class4 --build [--relic force|auto]`
  `--build` builds+deploys first; timeout default 900 s/run; logs land in
  `~/.local/share/SlayTheSpire2/autoslay/autoslay_<seed>.log` (runtime mechanic tags + exceptions in
  `~/.local/share/SlayTheSpire2/logs/godot.log`). Known gotcha: clicking away from the game window
  backgrounds/throttles it and LOOKS like a hang — leave it focused.
- **The env embark hang (Gate-0 pattern):** on long uptimes the game freezes entering the first room
  (`Room type not assigned`) and never reaches combat — an ENV stall, not a code bug. Remedy = reboot
  the box, then prove recovery with a baseline smoke on an already-shipped class BEFORE any gap-tester:
  `uv run btsgen-autoslay-smoke --seeds SANITY1 --character class3` → PASS only if the log shows a
  **combat** memprofile and the run quits on its own. Full protocol in `AUTOSLAY_VALIDATION_QUEUE.md`.
- **Smoke-verdict caveat:** the tool's PASS/FAIL ≠ mechanic-validated. Long-combat decks get classed
  `HANG — wall-clock timeout` on healthy deep runs, and AutoSlay's random bot intermittently fails at
  NEOW/menu (base-game NRE, not ours). Validate by the **godot.log mechanic tags + 0-mod-exception
  bar**, not the tool's seed verdict. AutoSlay plays RANDOMLY — run several seeds (`--seeds X XB XC`)
  when the mechanic needs a specific game state to fire.
- **Gap-tester staging** (worked examples: `generation/scratch/gaptest-{forge,p,q,r,s}/`):
  - character def → `~/.local/share/SlayTheSpire2/forged/characters/04.json`
  - its cards (RAW card JSON, one per slot) → `~/.local/share/SlayTheSpire2/forged/characters/04/cards/NN.json`
  - **Back up the existing slot 04 first** (each gaptest dir has `stage_<x>.sh` / `restore_slot04.sh` —
    copy that pattern for new testers), restore after the smoke. Staged cards are parsed at load by
    `ForgedCards.TryParse` (runtime slot shells) — no codegen needed for testers.

### 0.4 Verification gates — every vocab phase (U/V/W) runs ALL of these, in order

1. **Build clean** (game killed first).
2. **Generation suite green** (baseline count + your new tests; no skips introduced).
3. **Stage the phase's gap-tester class** (slot 04 flow above) and **AutoSlay smoke** on the phase's
   seed. Success = the phase's acceptance line (in its section) observed in the logs + **0 mod
   exceptions** + no unexplained hang. One retry allowed on infra flake; if the embark hang recurs,
   reboot + SANITY1 first (§0.3); a second same-cause failure = STOP (§0.7).
4. **Restore slot 04.**
5. **A real forge exercises the new vocab** (optional but preferred when the Ollama backend is
   reachable — `--ollama` flag, key in gitignored `generation/.env` as `OLLAMA_API_KEY`, consider
   `BTS_STAGE_ATTEMPTS>1`): one CLI forge whose concept invites the new mechanic; confirm the emitted
   cards use it and validate.

### 0.5 Hard-won lessons — violating any of these has already caused a shipped bug once

- **In-code localization only** for new Powers/keywords — never reference base-game loc keys (gap #26
  crash). Model on `Powers/ForgedTempStatPowers.cs` / `Powers/ForgedForgePower.cs` (emoji icon path
  included).
- **Base PowerModel types may be ABSTRACT** — always subclass a concrete shape; never
  `ModelDb.Power<abstract>()` (the actual gap-#26 root cause).
- **NEVER hand a bare `ModelDb.Get(...).ToMutable()` clone to a combat API** — clones have a **null
  `Owner`** and no combat-scope registration; the NRE surfaces as an uncatchable native-looking death
  (the Phase-Q crash). Create combat-bound cards via `owner.Creature.CombatState.CreateCard(canonical,
  owner)` (see `ForgedCharacters.ResolveClassCardModel` post-fix, and `PetDamageAttributionPatch` for
  the same failure family).
- **Multi-fire triggers need re-entrancy guards** and (where sensible) `once_per_turn` gating (the H4
  lesson).
- **Card text is byte-matched** between C# `ForgedCards.Describe`/`TriggerSentence` and Python
  `cardgen.py describe()/trigger_sentence()` — tests enforce it. Change both or neither.
- **Scale semantics:** the F5 family REPLACES the printed amount; `forged` is the one ADDITIVE
  exception. Phase U deliberately ships a separate `grow` FIELD instead of overloading `scale` —
  do not fold it into the scale enum.
- **Never emit vocab the class can't run** — class-only ops stay gated (the orb/status/summon drop nets
  in `class_forge.py` ~:1321-1339 are the pattern).
- **Loop discipline** — any op that generates cards/energy/upgrades must carry validator tripwires (see
  `validator.py` "one-card engine" checks; Q's `add_card` rules are the model).
- **Merchant + rare floors are sacred:** every class needs ≥1 non-basic attack/skill/power and ≥3 rares
  or the game hangs (see `_ensure_merchant_types` / `_ensure_min_rares` in `class_forge.py`). Phase W
  (purge) must respect this: a deck that can purge itself below the floors is a validator concern —
  see W's rules.
- **Token backtick gotcha:** `catalog.live_vocab_tokens()` counts only *backticked* tokens in
  `mod/contract/VOCABULARY.md` — backtick every new token or catalog buildability won't see it.
- **Flipping a gap status can break `tests/test_frontend.py`'s live-log assertions** — update those
  assertions in the same commit as the flip.
- **The reciprocal rule:** a vocab phase without its catalog entry + blueprint-prompt guidance is NOT
  done — that's how the six H4 triggers ended up with ~20 uses across 965 cards. Catalog entries live
  in `generation/btsgen/data/archetypes.json`; use `gap_refs` so buildability auto-tracks the gap flip.
- **BaseLib is referenced as a LIBRARY** (`using BaseLib.*` + our own `harmony.PatchAll()` in
  `MainFile.cs`) — do NOT assume BaseLib's own Harmony patches (e.g. its `PurgePatch`) are active at
  runtime. If you need a BaseLib patch's behavior, copy its shape into the mod as a Forged* patch
  (Phase W does exactly this).

### 0.6 Definition of done (per vocab phase) — all boxes or it didn't happen

- [ ] Engine + contract + generation lockstep complete (§1 checklist — every file).
- [ ] `VocabVersion` bumped in ForgedCards.cs AND `bts1.py` (equal values, comment updated).
- [ ] New tests added (mirror `tests/test_forge.py`'s shape) and full suite green.
- [ ] AutoSlay smoke PASSED with the phase's acceptance line; slot 04 restored.
- [ ] Gap(s) flipped/annotated in `VOCABULARY_GAPS.md` with a stamped one-line result
      (house style: see gap #36's status line).
- [ ] Catalog entry landed in `generation/btsgen/data/archetypes.json` (with `gap_refs` where noted) and
      verified BUILDABLE via `load_catalog()` after the flip.
- [ ] Blueprint prompt guidance added in `class_forge.py` (compact REQUIRED-style lines, not prose — the
      7B local model ignores adjectives).
- [ ] If a featured-mechanic menu exists in code (grep `featured.py`), add this phase's mechanic to it
      (Wave 2 precedent: `token_conjure`, `discard_reflex`, `balance_shift`).
- [ ] §0.2 tracker row updated to `done <date>` + the phase section header stamped with the smoke result.
- [ ] One commit, message style matching history (`git log --oneline`): e.g.
      `mod+forge: Phase U — rampage grow-on-play (vocab v26)`.
      Commit only; **do not push** unless the user asks.

### 0.7 Stop conditions — halt, write findings into the tracker row, report

- Baseline tests or build red before your first edit.
- The smoke fails twice on the same cause (after one env-reboot cycle), or the game logs a mod exception
  you cannot attribute.
- A needed C# surface is absent from `_modref/reflect/dump.txt` and not discoverable via decompile
  (note what reflection dump is missing).
- Anything requiring a semantics decision this doc doesn't cover (add the question to the tracker row).
  Do NOT improvise vocabulary semantics — wrong semantics ship into every future forged class.
  (Where this doc explicitly pre-authorizes both outcomes of a check — V's upgrade scope, W's purge
  persistence — decide per the instructions there and document; that is not a stop condition.)

---

## 1. The lockstep checklist (the files every vocab addition touches)

Verified anchors 2026-07-07 (Wave 2) — re-grep each before editing:

| # | file | what |
|---|---|---|
| 1 | `mod/BlankTheSpireCode/Engine/EffectRunner.cs` | execution: op switch (`Execute`), scalar switch (`ScaleValue`), relic path (`RunRelicEffects`) |
| 2 | `mod/BlankTheSpireCode/Engine/DataCard.cs` | declaration (`DeclareEffects`) so tooltip/preview/upgrade work; per-play calc-vars (`BonusFor` pattern) |
| 3 | `mod/BlankTheSpireCode/Engine/ForgedCards.cs` | `VocabVersion` · `SupportedOps` · `MultiFireTriggers` · `TriggerOps` · `SupportedStatuses` · `SupportedScales` · `AmountOps` · `Validate` · trigger validate · `Describe`/`TriggerSentence` |
| 4 | `mod/BlankTheSpireCode/Engine/TriggerRunner.cs` | trigger payload op set (if the op is payload-legal) |
| 5 | `mod/BlankTheSpireCode/Engine/CardSpec.cs` | parsed card fields (new field ⇒ new property + TryParse wiring) |
| 6 | `mod/contract/card.schema.json` | op/field/scale/condition enums + new fields, semantics in descriptions |
| 7 | `mod/contract/VOCABULARY.md` | the table the LLM reads — **backticked tokens feed catalog buildability** |
| 8 | `generation/btsgen/cardgen.py` | `effect_literal` + `describe()`/`trigger_sentence()` byte-match |
| 9 | `generation/btsgen/validator.py` | structural rules, `_score_effect` balance weights, loop tripwires |
| 10 | `generation/btsgen/bts1.py` | `VOCAB_VERSION` |
| 11 | `generation/btsgen/class_forge.py` | blueprint system-prompt guidance (+ archetype section if class-identity mechanic) |
| 12 | `generation/btsgen/data/archetypes.json` | the catalog entry (vocab without a catalog entry sits unused — the 2026-07-06 census proved it) |
| 13 | `generation/tests/test_<phase>.py` | schema accept/reject, validator rules, C#-emit round-trip, sentence byte-match |
| 14 | (class-level rules) `generation/btsgen/character_validator.py` + `character_pipeline.py` | set-level pairing/floor warnings (model: `forge_pairing_warnings`) |

---

## 2. Gate G — verification closeout (NO vocab bump · effort LOW · mostly runbook execution)

Four independent items; do all of them in one invocation. This phase exists because Wave 2's Q crash fix
(2026-07-10, the `CreateCard` owner-binding fix) has **never run in combat**, and gap #4 has been
"verify-then-close" since the 2026-07-07 re-triage.

### G-1 · Q runtime re-validation (gap #16)

Follow `AUTOSLAY_VALIDATION_QUEUE.md` exactly:
1. **Reboot the box** (the embark hang recurs on long uptimes; it has already eaten two GAPTEST16
   attempts). After reboot, baseline: `uv run btsgen-autoslay-smoke --seeds SANITY1 --character class3`
   → must reach a combat memprofile.
2. Stage the existing tester: `bash scratch/gaptest-q/stage_q.sh` (rebuild via
   `build_gaptest_q.py` if `04.json` is missing), then
   `uv run btsgen-autoslay-smoke --seeds GAPTEST16 --character class4 --relic auto --build`.
3. **Acceptance:** `[Q] add_card` lines appear in godot.log; copies land in the named piles; the
   `on_exhaust → add_card` compost loop runs bounded; **no process death when an add_card card
   resolves** (the old failure mode); copies do not persist across combats; 0 mod exceptions. Run extra
   seeds (`GAPTEST16B/C`) if the random bot doesn't play the add_card cards.
4. Restore slot 04. Stamp: `VOCABULARY_GAPS.md` #16 status line (append "runtime re-validated <date>"),
   the Q rows in `AUTOSLAY_VALIDATION_QUEUE.md` and `VOCAB_EXPANSION_2_PLAN.md` §0.2.

### G-2 · Riposte verify-then-close (gap #4)

The 2026-07-07 re-triage says #4 is likely expressible since v18. Prove it:
1. Author a minimal 3-card tester (new dir `generation/scratch/gaptest-riposte/`, copy the gaptest-q
   script pattern): (a) a power card `add_trigger trigger:"attacked"` whose payload is
   `damage` `target:"enemy"` (the H4 enemy-targeted payload); (b) the same with `once_per_turn` for
   contrast; (c) a plain `thorns` card (the passive form). Validate with the generation validator
   before staging.
2. Smoke on seed `GAPTEST4` (same session as G-1 is fine — reuse the healthy env).
3. **Acceptance:** the `attacked` payload deals damage to the attacker when (and only when) an enemy
   attack connects; `once_per_turn` gates correctly; 0 mod exceptions.
4. Flip **#4 → done** in `VOCABULARY_GAPS.md` ("expressible since v18: `attacked` trigger + enemy
   payload ≈ riposte; thorns covers the passive form — verified <date>, seed GAPTEST4"). If the feel is
   NOT riposte (e.g. payload fires before/regardless of the hit connecting), do not flip — narrow the
   remainder into the status line and leave `captured`.

### G-3 · File the Phase-T follow-on gaps as real entries

Phase T's status prose (gap #36) names three future gaps that are invisible to triage because they are
not entries. Append them to `VOCABULARY_GAPS.md` as new numbered gaps (next free numbers), status
`captured`, `Surfaced by: Phase T follow-on (2026-07-10)`:
- **blade upgrade-cost delta** (2→1 energy on upgrade) — needs an importer upgrade-cost channel;
- **permanent blade mutations** ("blade hits ALL enemies", "+1 hit") — needs per-combat card-model
  mutation (cross-reference the transform family #35/#38);
- **op `blade_empower`** ("blade deals double this turn") — deferred stretch from Phase T.
Copy the sketch text from #36's Phase-T paragraph so the entries are self-contained.

### G-4 · Gap-log dedup tooling (the demand-signal rule)

Small tooling ask recorded in Wave 2's appendix: in `generation/btsgen/frontend/catalog.py`, find
`append_vocab_gaps()` (re-grep the exact name) and add **near-title dedup**: before appending a new gap
whose title closely matches an existing entry (case-insensitive, normalized; a conservative
fuzzy/substring match is fine), skip the append and instead log/annotate a demand-count credit on the
original (the #1 balance-gauge pattern: dupes #30/#32/#33 cost three manual triages). Add a test beside
the existing catalog tests. Keep it conservative — false-positive dedup (suppressing a genuinely new
gap) is worse than a duplicate.

### G done =

All four items stamped; `AUTOSLAY_VALIDATION_QUEUE.md` updated (Q row closed or its failure recorded);
one commit, e.g. `mod+forge: Gate G — Q runtime re-val, riposte #4 closed, Phase-T gaps filed, gap dedup`.
If G-1 fails twice post-reboot, STOP the whole wave (§0.7) — do not proceed to U with a broken add_card.

---

## 3. Phase U — rampage: per-card grow-on-play (gap #23 · v26 · effort MEDIUM)

The wave-3 anchor. Base-StS Rampage: *"Deal 8 damage. Increase this card's damage by 5 (this combat)."*
Its plumbing — a per-card-instance play-count read — also reopens the transform family (#3/#35/#38)
for wave 4.

**Research shortcut (verified 2026-07-12):** you do NOT need BaseLib's `PersistVar` state machinery.
`_modref/BaseLib-StS2/Cards/Variables/PersistVar.cs` shows the recipe — count the combat history:
`CombatManager.Instance.History.CardPlaysFinished.Count(entry => entry.CardPlay.Card == card)`
(PersistVar adds a `HappenedThisTurn` filter; rampage DROPS it — whole combat). Also note
`CardPlay.PlayCount` exists in the dump (`_modref/reflect/dump.txt` ~:599) — investigate whether it is
a per-card play counter; use it if it's simpler, but the History count is the proven fallback.

### Spec

- **New optional field `grow` (int 1..9) legal ONLY on `damage` effects** (attack cards; not payloads):
  `{op:"damage", amount:8, grow:5}` → damage dealt = `amount + grow × (times THIS card was played
  earlier this combat)`. First play = printed amount. Per-CARD-INSTANCE: `add_card` copies and other
  copies of the same card each grow independently (matches base StS). Per-combat reset for free (the
  history is combat-scoped — verify).
- **NOT a scale.** Do not add a `plays_this_combat` token to `SupportedScales` — `grow` is an additive
  step with its own magnitude, which the scale families can't express. `grow` and `scale` are mutually
  exclusive on one effect (validator + C# `Validate` reject the combo).
- **Display:** the card must show its CURRENT damage (base + growth) in hand — use the per-play calc-var
  pattern `DataCard.BonusFor` that `target_debuff_count` (Phase P) uses. Verify the preview updates
  after each play; if the preview only refreshes on state change, note it and move on (cosmetic).
- **Upgrade interplay:** the `upgrade` payload may raise `amount` and/or `grow` (both are plain ints —
  should fall out of the existing upgrade-delta machinery; test it). **Check:** does Rest-site upgrading
  swap the `CardModel` instance mid-run? Irrelevant to combat counting (history is per-combat) — but
  confirm in-combat `upgrade_card` (Phase V) on a grown card doesn't reset or double its count; document
  the observed behavior in the schema description.
- **Validator:** `grow` cards price higher in `_score_effect` (a grown card is a scaling engine);
  cap `grow ≤ amount` (a card that grows faster than its base reads as degenerate); warn if a class has
  >2 grow cards (identity, not wallpaper).

### Text lockstep (byte-match both sides, exact strings yours to finalize)

Suggested: `Deal 8 damage. Grows by 5 each time it is played this combat.` — the requirement is C#
`Describe` and `cardgen.describe()` agree byte-for-byte and a test proves it.

### Catalog + prompt

- New entry `rampage_grow` (leans aggro; `gap_refs: ["VOCABULARY_GAPS#23"]`): "a signature attack that
  grows every time you swing it — commit to the same card again and again".
- Distinguish from `forge_ramp` in both descriptions (Forge = CLASS-level counter pumped by many cards;
  grow = ONE card feeding itself). The map stage must be able to pick the right one.
- Blueprint prompt: one compact line — "RAMPAGE: an attack may carry `grow` (its damage increases by
  `grow` each play this combat); give a grow attack cheap draw/retain support, 1-2 per class max."
- `featured.py`: add a `rampage_grow` featured entry (Wave 2 precedent).

### Gap-tester (seed `GAPTEST23`)

Cards: (1) a cost-1 `grow:5` attack; (2) a cost-0 `grow:2` attack (fires often under the random bot);
(3) draw support so they recur; (4) an `add_card` card that copies the grow attack (independent-growth
check — this also double-exercises the G-1 fix). Log a `[U]` tag with the computed damage at each play.
**Acceptance:** the same card instance logs strictly growing damage across plays; a generated copy
starts back at base; a fresh combat starts at base (per-combat reset); 0 mod exceptions. Flip **#23 →
done**; annotate #3/#35/#38 ("play-count plumbing landed in U — transform family now cheaper").

---

## 4. Phase V — in-run upgrade op, no-choice form (gap #18 · v27 · effort LOW-MEDIUM) — DONE 2026-07-13 (AutoSlay-VERIFIED: 662 `[V]` fires / 0 mod exc; combat-scoped confirmed)

The Armaments fantasy. Phase M's research note (gap #18): `CardCmd.Upgrade(CardModel, CardPreviewStyle)`
is a ready-made synchronous call (`_modref/reflect/dump.txt:580`; a batch overload
`Upgrade(IEnumerable, style)` sits at :581). One-shot per card (`IsUpgraded` bool) — "upgrade many
times" stays out of scope. The player-PICK variant stays blocked on the card-select surface (spike Y).

### Spec

- **op `upgrade_card`** — `{op:"upgrade_card", cards:"random"|"all"}` (no amount; field name yours, keep
  it enum-valued): upgrade one random not-yet-upgraded card in HAND (`random`) or every not-yet-upgraded
  card in HAND (`all`, the Armaments+ form). No-op if nothing qualifies (never an error). Random pick
  must use the run's seeded RNG (the `CombatCardSelection` RNG Phase R's discard uses — reuse that
  pattern, determinism matters for AutoSlay repro).
- **Payload-legal** in `add_trigger` self-payloads (`random` only — `all` in a repeating payload is
  degenerate; validator + C# reject `all` in payloads). A `turn_start → upgrade_card random` rare power
  is the intended ceiling.
- **Scope check (pre-authorized decision):** determine whether `CardCmd.Upgrade` on a deck card persists
  after combat (decompile `CardCmd.Upgrade` / check whether it mutates the run-deck `CardModel` or a
  combat clone; then CONFIRM empirically in the smoke by checking the card's state next combat).
  EXPECTED: combat-scoped (StS convention). Whichever you observe, write it into the schema description,
  VOCABULARY.md row, and card text — and if it turns out RUN-permanent, add a validator warning pricing
  it as rare-only. Do not stop either way.
- **Self-upgrade interaction:** a card whose effect list contains `upgrade_card` CAN hit itself when in
  hand (`all`) — decide by observation whether the in-flight card is in hand during resolution;
  document. (Base Armaments can't hit itself; ours may differ. Cosmetic either way.)
- **Validator:** price like a strong skill; `all` is uncommon+; the existing "every card needs an
  upgrade payload" convention means targets always have a delta — but confirm the importer tolerates
  upgrading a card whose upgrade payload only changes text/cost.

### Text lockstep

Suggested: `Upgrade a random card in your hand.` / `Upgrade ALL cards in your hand.` (+ a
`for the rest of this combat` suffix iff scope is combat — finalize after the scope check). Byte-match.

### Catalog + prompt

- New entry `battle_smith` (leans control/scaling; `gap_refs: ["VOCABULARY_GAPS#18"]`): "sharpen your
  tools mid-fight — upgrades as a combat resource".
- Blueprint prompt: one compact line ("a skill may upgrade random/all cards in hand; pair with retain
  or big hands so upgrades stick around to matter" — adjust to the observed scope).
- `featured.py` entry.

### Gap-tester (seed `GAPTEST18`)

Cards: (1) cost-1 `upgrade_card random`; (2) cost-2 `upgrade_card all`; (3) a rare power
`turn_start → upgrade_card random`; (4) bystander cards with visible upgrade deltas (e.g. damage 6→9)
+ one retain card (holds an upgraded card across turns). Log `[V]` with the upgraded card's name.
**Acceptance:** upgrades apply (log shows the delta), already-upgraded cards are skipped, `all` hits
multiple, no-op case doesn't throw, scope matches what you documented (verify next-combat state), 0 mod
exceptions. Flip **#18 → done (no-choice form)** with a follow-up line "player-pick variant → spike Y",
and annotate #3 ("upgrade-op half landed; rank-up track remains").

---

## 5. Phase W — self-purge: run-permanent deck-thinning (gap #19, self-purge form · v28 · effort LOW-MEDIUM) — DONE 2026-07-14 (AutoSlay-VERIFIED: 213 `[W]` fires / 37 run-deck removals + 176 generated-copy vanishes / 0 mod exc; run-permanence confirmed via a full RunCompleted)

The deck-thinning fantasy in its no-choice form: a card that, when played, is **removed from your deck
for the rest of the run** (a stronger exhaust — you play it now and thin your deck forever). The
choose-a-card-to-purge variant stays blocked on spike Y.

**Research shortcut (verified 2026-07-12):** `_modref/BaseLib-StS2/Patches/Features/PurgePatch.cs` is a
25-line Harmony prefix on `CardModel.GetResultPileTypeForCardPlay` (fallback name
`GetResultPileType`) returning `PileType.None` for keyworded cards; BaseLib's keyword description
promises "Removed from combat and your deck permanently." **Do not rely on BaseLib's patch being
active** (§0.5 last bullet) — copy the shape in-mod as `ForgedPurgePatch`, keyed off the forged card's
spec flag (via the `DataCard`/spec lookup for the model) instead of a BaseLib keyword.

### Spec

- **New optional boolean card field `purge`** (like `exhaust`; mutually exclusive with `exhaust` —
  validator + C# reject both on one card). When a `purge:true` card is PLAYED, it goes to no pile and
  is removed from the run deck.
- **Persistence check (pre-authorized decision):** BaseLib claims `PileType.None` is run-permanent.
  VERIFY in the smoke: the purged card must be absent in the NEXT combat. If it comes back (i.e. the
  run deck rebuilds combat piles from an untouched RunState list), find the run-deck removal call
  (grep the dump/decompile for the shop card-removal service — the merchant "remove a card" flow calls
  it) and remove it there too. If neither works, STOP (§0.7).
- **Token/generated-copy interplay:** a generated copy (`add_card`) of a purge card must NOT try to
  remove anything from the run deck (it isn't in it) — combat-vanish is enough; guard the run-deck
  removal to cards actually present in the run deck.
- **Deck-floor guard (class-level):** purging can shrink a deck below the sacred floors (§0.5). Rules:
  `purge` is forbidden on BASIC cards and on the class's only merchant-type card (reuse the
  `_ensure_merchant_types` machinery to check); `character_validator.py` warns if >3 cards in a class
  carry purge. The floors are about the CLASS DEFINITION (drafting pools), not the run deck — confirm
  the merchant/boss-reward code paths read the class card pool, not the player's current deck (they do
  — the Wave-1 hang bugs were pool-level); if so the floor risk is nil and the warning is a design
  nicety, note that in the validator comment.
- **Keyword text:** render a `Purge.` keyword line in the card text (in-code loc only — an emoji kick
  like the existing ⚒️/☀️ pattern in `MainFile.cs` is fine).

### Text lockstep

Suggested trailing sentence: `Purge. (Removed from your deck for the rest of the run.)` — byte-match.

### Catalog + prompt

- New entry `ascetic_purge` (leans combo/thin-deck; `gap_refs: ["VOCABULARY_GAPS#19"]`): "burn the
  chaff — one-shot cards that thin your deck toward a lean engine".
- Blueprint prompt: compact line ("a strong one-shot skill/attack may carry `purge` (leaves your deck
  for the run); 1-3 per class; never on basics").
- `featured.py` entry.

### Gap-tester (seed `GAPTEST19`)

Cards: (1) a strong cost-1 attack with `purge:true`; (2) a skill with `purge:true`; (3) an `add_card`
card that generates a copy of (1) (the generated-copy guard); (4) filler. Log `[W]` on purge resolution.
**Acceptance:** played purge cards never reappear in later piles THIS combat AND are absent from the
next combat's deck; the generated copy vanishes without touching the run deck; 0 mod exceptions (run at
least 2 combats — use extra seeds if the bot dies early). Flip **#19 → done (self-purge form)** with a
follow-up line "choose-a-card purge → spike Y".

---

## 6. Spike Y — the card-select UI surface (NO vocab · effort = RESEARCH, timebox ~half a day)

One un-dumped surface blocks four backlog items: **scry** (R-2, deferred), **#18 player-pick upgrade**,
**#19 choose-a-card purge**, **#7 graft**. This spike answers "can mod code open a pick-N-cards UI?"
with a working throwaway, or a documented no.

1. **Where to look:** `_modref/reflect/dump.txt` shows `CardCmd.Discard(PlayerChoiceContext, ...)` and
   `DiscardAndDraw(PlayerChoiceContext, ...)` — `PlayerChoiceContext` IS a choice surface. Dump/decompile
   `PlayerChoiceContext` itself; then decompile how a base-game choice card (any "choose a card in your
   hand" effect — e.g. an Armaments-like or a discard-choice card in `sts2.dll`) constructs and awaits
   it. Also re-check for `CardSelectCmd`/`ScryCmd` under whatever names this build uses (the old dump
   says "not found" — the game has updated since; consider re-running the reflection dump tooling that
   produced `_modref/reflect/dump.txt`).
2. **Prove it:** hack ONE throwaway effect into a slot-04 tester card (no contract changes, no lockstep
   — this code does not ship): open a hand-pick UI, await the pick, upgrade (or discard) the picked
   card. AutoSlay CANNOT drive a choice UI (random bot) — this one is a MANUAL in-game check: stage
   slot 04, launch the game normally, play the card, observe. (Also note what AutoSlay DOES when it
   hits the choice — if it hangs, any future choice vocab needs an auto-pick fallback under AutoSlay;
   record that.)
3. **Deliverable:** a `SPIKE_CARD_SELECT.md` at repo root: the exact API recipe (or the dead end),
   the AutoSlay-compat note, and a go/no-go + effort estimate for each of the four blocked items.
   Update those items' lines in `VOCABULARY_GAPS.md` (#7, #17-scry note, #18, #19) to point at it.
   Revert/delete the throwaway card code. No commit of dead code; commit the doc + gap-line updates.

---

## Appendix — why this wave (context, not tasks)

- Wave 2 closed the archetype catalog's last NEEDS-VOCAB entry (balance gauge); the backlog is now the
  2026-07-01 archetype-triage "second wave" (#18/#19/#20/#23/#25) plus captured one-offs. U/V/W are the
  three with verified-cheap C# surfaces (History count / `CardCmd.Upgrade` / `PurgePatch` shape) —
  best leverage-per-risk. #20 corruption needs a cost-modification surface nobody has scouted (wave 4,
  scout first); #25 needs a tag convention (design before code).
- Demand-signal rule stays in force: when the map stage re-surfaces an existing gap, credit the
  original's demand count (G-4 automates the dedup half). Demand counts are the wave-4 ranking input.
- Runtime state going in: P/R/S runtime-PASSED 2026-07-09 (see `AUTOSLAY_VALIDATION_QUEUE.md` results
  table); Q fixed-in-code 2026-07-10, re-val = G-1; #4 verify = G-2. The adjacent generation-side checks
  (Phase S real-forge archetype pick, O-ACC census) live in that queue's "Adjacent track" and are NOT
  part of this wave — run them opportunistically when the Ollama backend is up.
