# Vocabulary Expansion — Wave 2 (Phases P → S) · EXECUTABLE RUNBOOK

**Status: READY TO EXECUTE — written for an Opus 4.8 agent told "execute what is in this doc".**
Authored 2026-07-07 (Fable 5 session; re-grounded against live code the same day). Successor to
`VOCAB_EXPANSION_PLAN.md` (Wave 1, shipped). Sibling: `PHASE_N_CREATIVE_BREADTH_PLAN.md` (harness-side;
independent — but see §1.4 "reciprocal rule").

---

## 0. Agent operating protocol (read this first, follow it exactly)

**Scope per invocation: execute exactly ONE phase — the first row in the §0.2 tracker whose status is
`ready` (or resume a `building` one). Do not start a second phase in the same run.** When the phase is
done, stamp everything (§0.6), commit, and stop.

### 0.1 Orient before touching anything

1. Read the live vocab version — **the code is the source of truth, not this doc**:
   - `mod/BlankTheSpireCode/Engine/ForgedCards.cs` → `public const int VocabVersion` (line ~45; **20**
     as of 2026-07-07, the Sovereign Blade bump).
   - `generation/btsgen/bts1.py` → `VOCAB_VERSION` (line ~28; must equal the C# value).
   Your phase ships `VocabVersion = <live value> + 1` in BOTH places. The version numbers written in the
   phase sections below assume you start from v20 — recompute from the live value.
2. Check gap statuses parse and match the tracker:
   `cd generation && uv run python -c "from btsgen.frontend.catalog import gap_status; print(gap_status())"`
3. Confirm the baseline test suite is green BEFORE you change anything (§0.4). If it is red at baseline,
   STOP and report — do not build on a broken base.
4. **Line numbers in this doc are anchors, not gospel.** Re-grep every symbol before editing; the repo
   moves.

### 0.2 Phase tracker (update this table as you go: `ready` → `building` → `done <date, result>`)

| phase | gap(s) | ships | status |
|---|---|---|---|
| **P — precision reads** | #21, #22, #24, #9-relic | scalars `damage_dealt_unblocked` + `target_debuff_count`, `when draw_pile_empty`, relic `on_hp_lost` hook | **done 2026-07-08 (v21)** — full engine+contract+generation lockstep; C# build clean; gen suite green (754 asserts, `tests/test_phase_p.py` +29); gaps #21/#22/#24 + #9-relic flipped done; catalog `reaper_lifesteal` + `debuff_expose` token. **AutoSlay GAPTEST21 smoke PENDING env reboot** — tester authored + validator-checked in `generation/scratch/gaptest-p/` (stage+smoke scripts ready). |
| **Q — add_card** | #16 | token/card generation op | **done 2026-07-08 (v22)** — full engine+contract+generation lockstep; C# build clean; gen suite green (779 asserts, `tests/test_phase_q.py` +25); gaps #16 + #8 (compost) flipped done; catalog `token_conjurer` BUILDABLE + `exhaust_pyre` compost note + `featured.py token_conjure`. **AutoSlay RUNTIME RE-VALIDATED 2026-07-13 (Gate G-1, Windows box)** after the 2026-07-10 null-Owner `CreateCard` fix: seeds GAPTEST16/B/C logged **439 `[Q] add_card` fires across a deep run, 0 process deaths, 0 mod exceptions**; all 3 piles (Hand/Draw/Discard) + Anger self-copy + the `on_exhaust` compost loop (bounded) confirmed. (The prior 2026-07-09 Linux run hit the `Room type not assigned` embark hang — a Linux-box env stall not seen on Windows.) Tester rebuilt in `generation/scratch/gaptest-q/`. |
| **R — discard** | #17 | `discard` op + `on_discard` trigger (scry = stretch) | **done R-1 2026-07-08 (v23)** — full engine+contract+generation lockstep; C# build clean; gen suite green (804 asserts, `tests/test_phase_r.py` +21); gap #17 flipped done (R-1); catalog `madness_discard` BUILDABLE + `featured.py discard_reflex`. **R-2 (scry) DEFERRED** per plan. **AutoSlay GAPTEST17 smoke PENDING env reboot** — embark hang (`Room type not assigned`, same env stall as Phase P/Q); the class + discard/on_discard cards imported cleanly. Also fixed a pre-existing `smoke_relic` bug (its ethereal-injection broke the base/upgrade count on slot 05). Tester in `generation/scratch/gaptest-r/`. |
| **S — balance gauge** | #1 | `balance_step` op, pole conditions, `ForgedBalancePower` | **done 2026-07-08 (v24)** — full engine+contract+generation lockstep; C# build clean; gen suite green (846 asserts, `tests/test_phase_s.py` +41); gap #1 flipped done → catalog `balance_gauge` auto-flips BUILDABLE; new `Powers/ForgedBalancePower.cs` (signed gauge, sign-flip name/icon, |8| turn-start bite); three conditions `light_ge`/`dark_ge`/`centered`; class-level `balance_pairing_warnings` (both-pole income + gated payoff); `featured.py balance_shift`; `test_frontend` gap-#1/buildability assertions updated + the fake-compose stage re-anchored (catalog is now fully buildable — Phase S shipped the last NEEDS-VOCAB archetype). **AutoSlay GAPTEST1 smoke ran 2026-07-08: build clean (0 errors); all 10 Balance Gap Tester cards IMPORTED into class 04 with 0 mod exceptions (Shadowstep/Sunstep/Plunge/Ascend/Descent Into Dark/Shadow Reap/Radiant Ward/Equilibrium — every balance_step + dark_ge/light_ge/centered card parsed); then hit the SAME pre-combat env stall as GAPTEST16/17/21 (game froze entering the first room, never reached combat → no runtime [S] balance lines). RUNTIME behaviour PENDING env reboot.** Tester + stage/restore scripts in `generation/scratch/gaptest-s/` (10 cards: light/dark income, turn_start dark engine reaching the |8| bite, dark_ge/light_ge/centered payoffs). |

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
  Baseline 2026-07-07: **485 passed, 0 failed** (`test_art.py` is the pytest-style exception; it exits
  silently as a script — ignore it or run it via pytest if touched).
- **AutoSlay smoke — run it WITHOUT asking** (standing user instruction, 2026-07-06; Steam stays open on
  the shared account in Offline Mode). From `generation/`:
  `uv run btsgen-autoslay-smoke --seeds GAPTEST<gap#> --character class4 --build [--relic force|auto]`
  `--build` builds+deploys first; timeout default 900 s/run; logs land in
  `~/.local/share/SlayTheSpire2/autoslay/autoslay_<seed>.log`. Known gotcha: clicking away from the game
  window backgrounds/throttles it and LOOKS like a hang — leave it focused.
- **Gap-tester staging** (worked example: `generation/scratch/gaptest-forge/`, used by Phase M):
  - character def → `~/.local/share/SlayTheSpire2/forged/characters/04.json`
  - its cards (RAW card JSON, one per slot) → `~/.local/share/SlayTheSpire2/forged/characters/04/cards/NN.json`
  - **Back up the existing slot 04 first** (mirror `gaptest-forge/_backup_slot04/`), restore after the
    smoke. Staged cards are parsed at load by `ForgedCards.TryParse` (runtime slot shells) — no codegen
    needed for testers; `cardgen.py` codegen serves `mod/content/cards` and must merely stay byte-matched.

### 0.4 Verification gates — every phase runs ALL of these, in order

1. **Build clean** (game killed first).
2. **Generation suite green** (baseline count + your new tests; no skips introduced).
3. **Stage the phase's gap-tester class** (slot 04 flow above) and **AutoSlay smoke** on seed
   `GAPTEST<gap#>`. Success = the phase's acceptance line (in its section) observed in the autoslay log
   + **0 mod exceptions** + no hang. One retry allowed on infra flake; a second failure = STOP (§0.7).
4. **Restore slot 04.**
5. **A real forge exercises the new vocab** (optional but preferred when the local model is reachable —
   see memory: local ollama backend, `BTS_STAGE_ATTEMPTS>1`): one CLI forge whose concept invites the
   new mechanic; confirm the emitted cards use it and validate.

### 0.5 Hard-won lessons — violating any of these has already caused a shipped bug once

- **In-code localization only** for new Powers — never reference base-game loc keys (gap #26 crash:
  `POWER.TEMPORARY_STRENGTH_POWER` KeyNotFound). Model on `Powers/ForgedTempStatPowers.cs` /
  `Powers/ForgedForgePower.cs` (emoji icon path included).
- **Base PowerModel types may be ABSTRACT** — always subclass a concrete `CustomTemporaryPowerModel`-style
  shape; never `ModelDb.Power<abstract>()` (the actual gap-#26 root cause).
- **Multi-fire triggers need re-entrancy guards** and (where sensible) `once_per_turn` gating — the H4
  lesson; `on_block_gained` payloads that gain Block recurse without the guard.
- **Card text is byte-matched** between C# `ForgedCards.Describe`/`TriggerSentence` and Python
  `cardgen.py describe()/trigger_sentence()` — tests enforce it. Change both or neither.
- **Scale semantics:** the F5 family REPLACES the printed amount; `forged` is the one ADDITIVE exception.
  New scalars in P are replace-family. Document semantics in `card.schema.json`'s `scale` description.
- **Never emit vocab the class can't run** — class-only ops stay gated (the orb/status/summon drop nets
  in `class_forge.py:1321-1339` are the pattern).
- **Loop discipline** — any op that generates cards/energy must carry validator tripwires (see
  `validator.py` "one-card engine" checks; Q has explicit rules).
- **Merchant + rare floors are sacred:** every class needs ≥1 non-basic attack/skill/power and
  ≥3 rares or the game hangs — never let a new safety net or filter starve those (see
  `_ensure_merchant_types` / `_ensure_min_rares` in `class_forge.py`).
- **Token backtick gotcha:** `catalog.live_vocab_tokens()` counts only *backticked* tokens in
  `mod/contract/VOCABULARY.md`. `cards_in_hand`, `unspent_energy_last_turn`, `forged` are NOT backticked
  as of 2026-07-07 — **Phase P backticks them** (docs-only) so catalog entries can reference them.
- **Flipping a gap status can break `tests/test_frontend.py`'s live-log assertions** (they pin #5/#6/#1
  statuses) — update those assertions in the same commit as the flip.

### 0.6 Definition of done (per phase) — all boxes or it didn't happen

- [ ] Engine + contract + generation lockstep complete (§1 checklist — every file).
- [ ] `VocabVersion` bumped in ForgedCards.cs AND `bts1.py` (equal values, comment updated).
- [ ] New tests added (mirror `tests/test_forge.py`'s shape) and full suite green.
- [ ] AutoSlay smoke PASSED with the phase's acceptance line; slot 04 restored.
- [ ] Gap(s) flipped to `done` in `VOCABULARY_GAPS.md` with a stamped one-line result
      (house style: see gap #36's status line).
- [ ] Catalog entry landed in `generation/btsgen/data/archetypes.json` (with `gap_refs` where noted) and
      verified to show BUILDABLE via `load_catalog()`.
- [ ] Blueprint prompt guidance added in `class_forge.py` (compact REQUIRED-style lines, not prose — the
      7B local model ignores adjectives).
- [ ] If `PHASE_N_CREATIVE_BREADTH_PLAN.md`'s featured-mechanic menu exists in code by then (grep for
      `coverage.py` / a FEATURED menu), add this phase's mechanics to it. If not, add a TODO line to that
      plan doc instead.
- [ ] §0.2 tracker row updated to `done <date>` + the phase section header stamped with the smoke result.
- [ ] One commit, message style matching history (`git log --oneline`): e.g.
      `mod+forge: Phase P — precision reads: lifesteal/debuff-count scalars, draw_pile_empty, relic on_hp_lost (vocab v21)`.
      Commit only; **do not push** unless the user asks.

### 0.7 Stop conditions — halt, write findings into the tracker row, report

- Baseline tests or build red before your first edit.
- The smoke fails twice on the same cause, or the game logs a mod exception you cannot attribute.
- A needed C# surface is absent from `_modref/reflect/dump.txt` and not discoverable (note what
  reflection dump is missing).
- Anything requiring a semantics decision this doc doesn't cover (add the question to the tracker row).
  Do NOT improvise vocabulary semantics — wrong semantics ship into every future forged class.

---

## 1. The lockstep checklist (the files every vocab addition touches)

Verified anchors, 2026-07-07 — re-grep each before editing:

| # | file | what |
|---|---|---|
| 1 | `mod/BlankTheSpireCode/Engine/EffectRunner.cs` | execution: op switch (`Execute`), scalar switch (`ScaleValue` ~:279), relic path (`RunRelicEffects`) |
| 2 | `mod/BlankTheSpireCode/Engine/DataCard.cs` | declaration (`DeclareEffects`) so tooltip/preview/upgrade work |
| 3 | `mod/BlankTheSpireCode/Engine/ForgedCards.cs` | `VocabVersion` ~:45 · `SupportedOps` ~:82 · `MultiFireTriggers` ~:101 · `TriggerOps` ~:105 · `SupportedStatuses` ~:113 · `SupportedScales` ~:121 · `AmountOps` ~:127 · `Validate` ~:432 · trigger validate ~:543 · `Describe`/`TriggerSentence` |
| 4 | `mod/BlankTheSpireCode/Engine/TriggerRunner.cs` | trigger payload op set (if the op is payload-legal) |
| 5 | relic path (P only): `Engine/RelicRunner.cs` (`Fire` ~:22), `Engine/ForgedCharacters.cs` (`RelicTriggers` ~:319, `TryParseRelic` ~:344) | relic hooks/triggers |
| 6 | `mod/contract/card.schema.json` | op/status/scale/condition enums + new fields |
| 7 | `mod/contract/VOCABULARY.md` (+ `RELIC_VOCABULARY.md` for relic changes) | the table the LLM reads — **backticked tokens feed catalog buildability** |
| 8 | `generation/btsgen/cardgen.py` | `effect_literal` + `describe()`/`trigger_sentence()` byte-match |
| 9 | `generation/btsgen/validator.py` | `_SUPPORTED_SCALES` ~:44, `_MULTI_FIRE_TRIGGERS` ~:52, structural rules, `_score_effect` balance weights |
| 10 | `generation/btsgen/bts1.py` | `VOCAB_VERSION` ~:28 |
| 11 | `generation/btsgen/class_forge.py` | blueprint system-prompt guidance; relic mirror sets `_RELIC_TRIGGERS` ~:493 / `_RELIC_EFFECT_OPS` ~:495 (P) |
| 12 | `generation/btsgen/data/archetypes.json` | the catalog entry (**the M-2 lesson: the mapping stage can only use mechanics the catalog names** — vocab without a catalog entry sits unused; the 2026-07-06 census proved it) |
| 13 | `generation/tests/test_<phase>.py` | schema accept/reject, validator rules, C#-emit round-trip, sentence byte-match |
| 14 | (statuses only) `mod/contract/statuses/<name>.json` | status descriptor |

**1.4 The reciprocal rule:** a vocab phase without its catalog entry + prompt guidance is NOT done —
that's how the six H4 triggers ended up with ~20 uses across 965 cards.

---

## 2. Phase P — precision reads: scalars + conditions micro-batch (v21 · effort LOW · F5-shaped)

Four small self-contained additions. Scalars/conditions have the best leverage-per-line in the system —
they cross with every attack, block, and payload.

### Spec

1. **`scale:"damage_dealt_unblocked"`** (gap #21, lifesteal) — legal ONLY on `heal`. Resolves to the
   total UNBLOCKED damage this card's earlier `damage` effects dealt during this same play ("Deal 12 to
   ALL enemies. Heal that much."). Replace-semantics.
   *Engine note:* unlike the F5 pre-reads this is an execution-ordered read — accumulate unblocked damage
   in the per-card execution context at the damage sites in `EffectRunner.Execute`, read it in the heal
   arm. Multi-hit and AoE damage must all accumulate.
   *Validator:* a `heal` with this scale requires a preceding `damage` op on the same effect list (base
   and upgrade lists checked independently); forbidden inside trigger payloads (payload scale stays
   `cards_retained`-only, `validator.py` ~:326).
2. **`scale:"target_debuff_count"`** (gap #22, flechettes) — legal ONLY on `damage` with an enemy target.
   Resolves to the count of DEBUFF powers on the struck target at resolution (per hit is fine and simpler;
   document whichever you implement in the schema description). Replace-semantics. Forbidden in payloads.
3. **`when {kind:"draw_pile_empty"}`** (gap #24, Grand Finale) — boolean predicate, no `value`. Slots
   beside `turn_at_least` in `Conditions` (C#) + `cond_phrase` (`cardgen.py` ~:142: "your draw pile is
   empty").
4. **Relic `on_hp_lost` hook** (gap #9 remainder) — add `on_hp_lost` to `ForgedCharacters.RelicTriggers`
   (~:319), fire it where the card-side twin fires (`ForgedTriggerPower.AfterDamageReceived` — same
   Rupture scoping: unblocked, own-turn/self-caused; reuse its re-entrancy guard pattern), payload through
   `RelicRunner.Fire`. Mirror in `RELIC_VOCABULARY.md`, `class_forge.py _RELIC_TRIGGERS` ~:493,
   `relic_validator.py`, and `smoke_relic.py`'s broad-coverage relic if it enumerates triggers.
5. **Docs-only:** backtick `cards_in_hand`, `unspent_energy_last_turn`, `forged`,
   `damage_dealt_unblocked`, `target_debuff_count`, `draw_pile_empty` in `VOCABULARY.md` (catalog
   buildability greps backticked tokens).

### Text lockstep (byte-match both sides)

- lifesteal heal: `Heal HP equal to the unblocked damage dealt.`
- flechettes damage: `Deal damage equal to the debuffs on the target.` (+ existing AoE suffix rules)
- condition phrase: `if your draw pile is empty`
(Exact strings are yours to finalize — the REQUIREMENT is C# `Describe` and `cardgen.describe()` agree
byte-for-byte and a test proves it.)

### Catalog + prompt

- New entry `reaper_lifesteal` (ops `damage`, `heal`, plus the new scalar token;
  `gap_refs: ["VOCABULARY_GAPS#21"]` — the gap_ref keeps it NEEDS-VOCAB until you flip #21 done, since
  `damage`/`heal` alone would read as buildable today).
- Extend `debuff_expose`'s description + metaphors with the debuff-count payoff (its ops already gate on
  nothing new — add the scalar token to its ops so buildability tracks #22 via the token).
- Blueprint prompt: one compact paragraph — "LIFESTEAL / EXPLOIT payoffs: a damage card may heal for the
  unblocked damage it dealt (`scale:"damage_dealt_unblocked"` on the heal); a damage card may scale with
  the debuffs on its target; a rare may be gated `when draw_pile_empty` (Grand-Finale style)."

### Gap-tester (stage slot 04, seed `GAPTEST21`, smoke with `--relic force`)

Cards: (1) AoE attack + lifesteal heal; (2) single-target lifesteal w/ multi-hit; (3) apply 2 debuffs then
a `target_debuff_count` attack; (4) a `draw_pile_empty`-gated bomb + cheap draw cards to empty the pile;
plus a starter relic carrying an `on_hp_lost` hook and one `lose_hp` card to trigger it.

**Acceptance:** log shows lifesteal heals matching unblocked damage (blocked portions excluded at least
once), debuff-count damage growing with stacks, the gated bomb firing only on empty draw pile, the relic
on_hp_lost hook firing on card-caused HP loss (not on enemy attacks), 0 mod exceptions.

---

## 3. Phase Q — `add_card`: token generation (v22 · effort MEDIUM) — DONE 2026-07-08 (v22; AutoSlay GAPTEST16 PENDING env reboot — embark hang, all add_card cards imported clean)

Gap #16. `{op:"add_card", card_id:"<same-class card id>", pile:"hand"|"discard"|"draw", amount?:1..3}`.
The Godot prototype had this op; the mod contract dropped it. C# path researched in Wave 1:
`CardPileCmd.AddGeneratedCardToCombat` (`_modref/reflect/dump.txt`).

### Rules (validator + C# Validate, both sides)

- `card_id` must exist in the SAME class (generation: `validator.known_cards`; C#: the class's parsed
  slot set — reject at import like unknown orb/summon names are rejected).
- **Loop discipline (hard rejects):** an added card may not itself contain `add_card` (depth-1 — check the
  REFERENCED card's spec at validate time where visible, and enforce at runtime by stripping/refusing
  nested add_card execution); a 0-cost card may not add copies of ITSELF; extend the existing "one-card
  engine" tripwire so add_card + energy refund on the same cheap card warns.
- Added copies are combat-transient (generated into combat piles, not the deck) — confirm
  `AddGeneratedCardToCombat` gives this for free; if it persists, STOP (semantics decision).
- Balance: `_score_effect` prices add_card like a draw-adjacent tempo op; amount cap 3.

### Text lockstep

`Add a copy of <Name> to your hand/discard pile/draw pile.` (amount >1: `Add N copies …`). Byte-match.

### Catalog + prompt

- New entry `token_conjurer` (leans combo; `gap_refs: ["VOCABULARY_GAPS#16"]`).
- Update `exhaust_pyre`'s description to name the compost loop (`on_exhaust` + add_card = "what burns
  returns" — this completes gap #8's second half; note that in #8's status line when flipping).
- Blueprint prompt: compact guidance + the loop-discipline warning ("small numbers; never make a 0-cost
  card that re-adds itself").

### Gap-tester (seed `GAPTEST16`)

Cards: a skill that adds 2 copies of a cheap attack to hand; a power `on_exhaust → add_card` (Mulch-style
token into discard); an exhaust enabler. **Acceptance:** add_card fires ×N into the named piles, the
on_exhaust+add_card engine loops without runaway (bounded per turn), copies do not persist across combats,
0 mod exceptions. Flip **#16 done** and annotate **#8** ("second half unblocked — compost loop now
expressible; buildable via exhaust_pyre + token_conjurer").

---

## 4. Phase R — discard subsystem (v23 · effort MEDIUM-CHUNKY — biggest single unlock) — DONE R-1 2026-07-08 (v23; scry R-2 deferred; AutoSlay GAPTEST17 PENDING env reboot — embark hang, discard/on_discard cards imported clean)

Gap #17, split. **R-1 is the phase; R-2 (scry) is a stretch — cut it without hesitation.**

### R-1 spec

- **op `discard`** — `{op:"discard", amount:N}`: discard N RANDOM cards from hand (choiceless — the
  player-choice variant needs the un-dumped `CardSelectCmd` UI surface; that stays out, same blocker as
  F4). Find the discard command on `CardCmd`/`CardPileCmd` in `_modref/reflect/dump.txt`; if only a
  choice-based surface exists, random-pick in mod code and call the raw pile move.
- **trigger kind `on_discard`** — fires when THIS card is discarded (the Madness/Reflex payoff). Joins
  `MultiFireTriggers` (needs `once_per_turn` support + the H4 re-entrancy guard — a payload that discards
  must not recurse). Card-side only (no relic hook in R-1).
  *Semantics to enforce:* end-of-turn hand cleanup does NOT count as "discarded" unless the base game
  says otherwise — match base-StS Reflex behavior: triggered by discard EFFECTS, not turn-end discard.
  Write this into the schema description and test it.
- `when` interplay: none new.

### Text lockstep

`Discard N random card(s).` · trigger sentence: `Whenever this card is discarded, …` (byte-match).

### Catalog + prompt

- New entry `madness_discard` (leans combo; `gap_refs: ["VOCABULARY_GAPS#17"]`): "churn your hand —
  discard as fuel, cards that reward being thrown away".
- Blueprint prompt: compact discard-archetype paragraph (discard income at common, on_discard payoffs,
  a rare engine power).

### Gap-tester (seed `GAPTEST17`)

Cards: a cheap attack with `discard 1` rider; a card whose `on_discard` payload gains Block; a power
`turn_start → discard 1` (forced churn); a big hand-refill draw card. **Acceptance:** discard fires ×N,
on_discard payoffs fire ONLY on effect-driven discards (log shows none at turn-end cleanup), no
re-entrancy runaway, 0 mod exceptions. Flip **#17 done** (note scry deferred if cut — leave a #17
follow-up line rather than a new gap).

---

## 5. Phase S — the balance gauge (v24 · effort MEDIUM-HIGH · the marquee) — DONE 2026-07-08 (v24; full lockstep shipped, `balance_gauge` now BUILDABLE, gen suite green 846; AutoSlay GAPTEST1 build-clean + all 10 balance cards IMPORTED with 0 mod exceptions, then the known pre-combat env hang — runtime PENDING reboot)

Gap #1 — demand ×4 (four themes independently re-surfaced it; see Appendix). The first genuinely novel
class axis in the backlog. The catalog entry `balance_gauge` ALREADY EXISTS with
`gap_refs: ["VOCABULARY_GAPS#1"]` and `ops: ["balance_step"]` — it auto-flips BUILDABLE the moment #1 is
`done` and the op token is backticked in VOCABULARY.md. Zero catalog work; the system was built for this.

**Phase M made this cheaper than the gap's 2026-06-19 sketch:** `Powers/ForgedForgePower.cs` is the
worked example of a player-level counter power with in-code loc + emoji icon + per-combat reset. Balance
is that pattern with a SIGNED value.

### Spec

- **op `balance_step`** — `{op:"balance_step", pole:"light"|"dark", amount:1..5}`: moves the gauge.
  New `Powers/ForgedBalancePower.cs` holds the signed value (suggest: internal int, positive = Dark);
  display stacks = |value|, name/icon flip by sign (☀️ Light / 🌑 Dark), power absent at 0. Legal on cards
  AND in `add_trigger` self-payloads (trigger income = the engine, exactly like `forge`).
- **conditions** — `when {kind:"light_ge", value:N}` · `{kind:"dark_ge", value:N}` ·
  `{kind:"centered", value:N}` (true iff |gauge| ≤ N). Three predicates beside `forged_ge`.
- **the bite (what makes it a gauge, not a second Forge):** inside `ForgedBalancePower`'s turn-start:
  if |gauge| ≥ `ExtremeThreshold = 8`, apply the extreme's penalty — Dark: lose 3 HP; Light: gain 1 Weak.
  Constants in the power class; tune later. The penalty must log visibly (it's the acceptance signal).
- **Class-level pairing rule** (in `character_validator.py` + surfaced in `class_forge.py`, mirroring
  `forge_pairing_warnings` ~:147): a class using `balance_step` must (a) have income on BOTH poles, and
  (b) have ≥1 pole-or-centered-gated payoff; warn otherwise (one-pole balance is just Forge with extra
  steps).
- **Scope guard:** `balance_step` and the three conditions are BALANCE-CLASS mechanics — but unlike
  orbs/status/summon there is no pool to declare. Gate instead on usage-pairing (the validator rule) +
  blueprint guidance ("never sprinkle"); a lone balance card is a warning, not a reject.
- Per-combat reset (powers die at combat end) — same as Forge.

### Text lockstep

`Shift N toward the Dark.` / `Shift N toward the Light.` · phrases: `if your Dark is N+` /
`if your Light is N+` / `if you are centered (within N)`. Byte-match, both sides, tested.

### Blueprint prompt

A THE BALANCE ARCHETYPE section modeled on THE FORGE section's shape (`class_forge.py` ~:240): the gauge
is a CLASS IDENTITY, income small and at common on both poles, payoffs gated by pole/centered at
uncommon/rare, the extremes bite at |8| — and the knife's-edge fantasy is `centered`-gated power. Include
the never-sprinkle rule.

### Gap-tester (seed `GAPTEST1`)

Cards: light income, dark income, a `turn_start → balance_step dark 2` engine power, a `dark_ge 5` payoff
attack, a `light_ge 5` block payoff, a `centered 2`-gated rare bomb. **Acceptance:** steps observed BOTH
directions with sign flips at 0, extreme penalty fires at |8| (both poles if the run allows), centered
payoff fires only near 0, per-combat reset, 0 mod exceptions. Flip **#1 done**, confirm
`load_catalog()` now shows `balance_gauge buildable=True`, update `tests/test_frontend.py`'s gap-#1
assertion (currently pins `planned`), and run one real forge on a duality-flavored concept to see the
archetype get PICKED.

---

## 6. Second wave (not scheduled — pick by demand after S)

`#20 corruption` · `#23 rampage` (BaseLib PersistVar spike; its plumbing reopens the transform family
#3/#35/#38) · `#19 purge` (BaseLib `PurgePatch` likely carries the runtime) · `#18 upgrade-op`
(no-choice variant buildable today per the Phase M research note) · `#25 strike-count` (needs a card-tag
convention first) · **status-pool hook expansion** (`damage_over_time` hook — cheaply serves the
recurring burn/freeze fantasies, gap #11). Re-rank by gap-resurface counts when the time comes.

---

## Appendix — 2026-07-07 re-triage record (context, not tasks)

Statuses live in `VOCABULARY_GAPS.md`; this table is the record of the 2026-07-07 pass:

| gap | verdict |
|---|---|
| #5 #6 #9(cards) #13 #14 #26 #36 | done (v14–v19) |
| #10 #15 #27 #28 #29 | rejected — offline `--fake` test artifacts |
| #30 #32 #33 | rejected as duplicates of #1 (demand credited: **#1 demand ×4**) |
| #31 | done — already expressible (Phase I custom orbs); false gap |
| #4 | likely expressible since v18 (`attacked` trigger + payload, thorns) — verify-then-close, cheap side quest for any phase |
| #2 | mostly covered by Phase K (`buff_summon`); low |
| #8 | half-unblocked by H4 `on_exhaust`; completes with Phase Q |
| #1 #16 #17 #21 #22 #24 | planned — Phases P–S above |
| #18 #19 #20 #23 #25 | planned, second wave |
| #3 #7 #11 #12 #34 #35 #37 #38 | captured — transform/positional/agency families; revisit after #23's PersistVar plumbing |

**Demand-signal rule:** when the map stage re-surfaces an existing gap, credit the original's demand count
instead of numbering a duplicate (small tooling ask: `catalog.append_vocab_gaps()` near-title dedup —
fold into any phase). Demand count is the wave-3 ranking input.

**The two lessons this plan is built on:** (1) the M-2 lesson — the mapping stage can only use mechanics
the catalog names, so every phase ships its catalog + prompt hookup (§1.4); (2) demand is real — #1 was
independently requested by four unrelated themes. Census evidence for both lives in
`PHASE_N_CREATIVE_BREADTH_PLAN.md`.
