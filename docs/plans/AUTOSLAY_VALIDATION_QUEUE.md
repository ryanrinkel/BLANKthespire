# AutoSlay Validation Queue

**Status (2026-07-13): Q RUNTIME RE-VALIDATED — QUEUE CLOSED.** On the WINDOWS box (no reboot needed — no
embark hang on Windows; the `Room type not assigned` stall was a Linux-box condition), Gate G-1 re-ran the
`add_card` tester across seeds GAPTEST16/B/C: **439 `[Q] add_card` fires, 0 process deaths, 0 mod exceptions**
— the null-Owner fix HOLDS. All three piles + the compost loop confirmed. Details in the Q row below and
`VOCABULARY_GAPS.md` #16. P/R/S remain runtime-PASSED (2026-07-09). The four wave-2 items are all closed.

**Prior status (2026-07-09, PM): RUN — Gate 0 CLEARED (box rebooted; env recovered). P/R/S VALIDATED at runtime.
Q = REPRODUCIBLE NATIVE CRASH (see below).** The whole queue was executed post-reboot.

**UPDATE 2026-07-10: Q CRASH FIXED IN CODE (root cause confirmed).** The crash was a NULL-Owner NRE deep in
`CardPileCmd.AddGeneratedCardsToCombat`: `ResolveClassCardModel` built the copy with a bare `ModelDb.Get(...).ToMutable()`,
which yields a clone with **no `Owner` and no combat-scope registration**. `AddGeneratedCardsToCombat` immediately
dereferences `list[0].Owner.Creature.CombatState` → fault → faulted turn task soft-locks/kills the run (same class
of bug the in-mod `PetDamageAttributionPatch` already fixes). Fix: build via `owner.Creature.CombatState.CreateCard(
canonical, owner)` — the exact recipe every base-game generator uses (Anger `CreateClone`, Infernal Blade
`GetDistinctForCombat` → `CreateCard`), which ToMutable()s + binds Owner + registers scope + runs `AfterCreated()`.
Build clean (0 err), import-clean (class 04 + all 10 tester cards load, 0 exceptions). **RUNTIME re-validation still
PENDING** — the Gate 0 embark hang RECURRED (box at ~24 h uptime): GAPTEST16 + QFIX1(+QFIX2) all timed out at
`Room type not assigned` before combat, even with `gnome-session-inhibit` idle-inhibition. Needs a REBOOT, then
re-run the GAPTEST16 smoke and confirm `[Q] add_card … -> pile` logs with no process death.

Sibling docs: `AUTOSLAY_TESTING_PLAN.md` (what AutoSlay is / how it's wired) · `VOCAB_EXPANSION_2_PLAN.md`
(the P→S runbook whose acceptance lines this queue exists to close).

---

## ✅ RESULTS — 2026-07-09 post-reboot run

The box had a fresh reboot (11-min uptime); Gate 0 baseline (`class3`/SANITY1) reached combat and logged
`RunCompleted` — **env recovered**. Then all four wave-2 items were run against slot 04 (`class4`).

| Phase | Op | Verdict | Evidence |
|---|---|---|---|
| **P** v21 | precision reads | **PASS** (0 exc) | Deep run to Act 2. `on_hp_lost` relic hook CONFIRMED card-caused-only (10× uniform "unblocked 3", no enemy-attack firings). Lifesteal / `target_debuff_count` / `draw_pile_empty` cards all resolved dozens of times, 0 exceptions (exact HP/dmg numbers aren't log-tagged — behavioral). Run ended at an unrelated base-game event, not a crash. |
| **Q** v22 | `add_card` | **✅ FIXED + RUNTIME RE-VALIDATED (2026-07-13, Gate G-1)** — 439 `[Q]` fires / 0 deaths / 0 mod exc; all 3 piles + compost loop. | Was: 7/7 combat runs hard-crashed the instant an `add_card` card resolved; `[Q] add_card` never logged, no catchable managed exception. **Root cause (confirmed vs decompiled Linux `sts2.dll`):** the generated copy had a NULL `Owner` (bare `ToMutable()` clone, no scope) → NRE deep in `CardPileCmd.AddGeneratedCardsToCombat` (`list[0].Owner.Creature.CombatState`) → faulted turn task soft-locks the run (presents as a native death; cf. in-mod `PetDamageAttributionPatch` for the same null-owner NRE). **Fix:** `ResolveClassCardModel` now builds via `owner.Creature.CombatState.CreateCard(canonical, owner)` (base-game recipe). Build+import clean. Runtime blocked only by the recurred env embark hang — see status note at top. |
| **R** v23 | `discard` / `on_discard` | **PASS** (0 exc) | Deep run (Act 1 F17+): 84 `discard` events (x1/x2), 35 `on_discard` across all 3 riders (Ashen Ward 19 / Reflex Dart 10 / The Reckoning 6). The Reckoning (`once_per_turn`) is rarest → gating OK. on_discard fires on only ~42% of discards (tied to rider cards) → effect-driven, NOT turn-end cleanup. No re-entrancy runaway. |
| **S** v24 | balance gauge | **PASS** (0 exc) | `balance_step` both directions with sign flip across 0 (gauge −5..+32). **|8| extreme bite BOTH poles: Dark = lose 3 HP** (15+ firings, GAPTEST1) **+ Light = gain 1 Weak** (forced via a cherry-picked Light-bias tester — the stock deck's dark income never let Light reach −8). Per-combat reset confirmed (9 combats, gauge resets to 0). `centered` window visited (Equilibrium played near 0). |

**Smoke-verdict caveat:** the tool's PASS/FAIL ≠ mechanic-validated. The discard/balance decks make very long
combats, so healthy deep runs get classed `HANG — wall-clock timeout`; and AutoSlay's random bot intermittently
fails at NEOW/menu (base-game `AutoSlayLog.RunFailed` NRE, not our mod). Validation here is by the **godot.log
`[P]/[Q]/[R]/[S]` mechanic tags + 0-mod-exception bar**, not the tool's seed verdict.

**Q root cause — SOLVED (2026-07-10).** It was NOT a missing visual field. The forged `CardModel` from a bare
`ModelDb.Get(ForgedClassKKCardNN).ToMutable()` has a **null `Owner`** and is not registered in the combat scope.
Decompiling the real Linux `sts2.dll`: `AddGeneratedCardsToCombat` runs `list[0].Owner.Creature.CombatState` before
its first await — with a null Owner that NREs, faults the async turn task, and (via the game's `LogTaskExceptions`
machinery) soft-locks/kills the run rather than surfacing at our `await` (hence "no catchable exception"). Base-game
generators NEVER hand a bare `ToMutable()` to that API — Anger uses `CreateClone()`, Infernal Blade uses
`CardFactory.GetDistinctForCombat` → `CombatState.CreateCard(canonical, owner)`, which does ToMutable + `AddCard(owner)`
(binds Owner, registers scope) + `AfterCreated()`. Fix applied in `ForgedCharacters.ResolveClassCardModel`: it now
takes the `owner` and returns `owner.Creature.CombatState.CreateCard((CardModel)ModelDb.Get(type), owner)`. The
in-mod `PetDamageAttributionPatch` (a Harmony fix for the identical null-owner NRE from pet-dealt Dazed) is the
precedent that confirms this failure mode.

---

---

## ⛔ Gate 0 — clear the env hang FIRST (this is why everything is pending)

Every recent smoke (GAPTEST21 / 16 / 17 / 1, and the O-2 hybrid) stalled at the **same point**: the game
confirms the character, reaches the `baseline` mem-profile, then **freezes entering the first room**
(`Room type not assigned`) and **never reaches combat** — so no runtime log lines can appear. This is an
**environment stall, not a code bug** (imports are clean; see each item's "already proven" note). It was
resolved once by reboot (2026-07-06, first post-reboot run passed) and has since recurred.

- [ ] **Reboot the box.**
- [ ] **Confirm recovery with a baseline smoke on an already-shipped class** before touching any gap-tester:
      `cd generation && uv run btsgen-autoslay-smoke --seeds SANITY1 --character class3`
      → PASS only if the log shows a **combat** memprofile (not just `baseline`) and the run quits on its own.
- [ ] **Focus gotcha:** leave the game window focused for the whole run — clicking away throttles/backgrounds
      it and looks exactly like a hang.

Do not run the queue below until a baseline run reaches combat.

---

## How to run one item

Each phase has a validator-checked gap-tester staged-ready under `generation/scratch/gaptest-<x>/`
(gitignored). The flow is always:

```bash
cd generation
bash scratch/gaptest-<x>/stage_<x>.sh          # backs up slot 04, stages the tester into slot 04
uv run btsgen-autoslay-smoke --seeds <SEED> --character class4 --relic auto
#   ...inspect ~/.local/share/SlayTheSpire2/autoslay/autoslay_<SEED>.log
#   ...and ~/.local/share/SlayTheSpire2/logs/godot.log for the tagged lines + any exceptions
bash scratch/gaptest-<x>/restore_slot04.sh     # ALWAYS restore slot 04 afterward
```

If a gap-tester's `04.json` isn't present, rebuild it first: `uv run python scratch/gaptest-<x>/build_gaptest_<x>.py`.

**Universal pass bar for every item:** **0 mod exceptions** in `godot.log`, **no hang**, and the run quits on
its own. (Import is already proven clean for all four — every card loaded with 0 exceptions before the env hang.)

**Coverage caveat — AutoSlay plays RANDOMLY.** A single seed may never push the gauge to |8|, empty the draw
pile, or exhaust a card. To raise the odds the mechanic actually fires, run each item with **several seeds**
(e.g. `--seeds GAPTEST1 GAPTEST1B GAPTEST1C`) or **loop mode**. Most sensitive to this: P's `draw_pile_empty`
and S's |8| bite + `centered` window.

---

## The four wave-2 runtime smokes

### [x] 1. Phase P — precision reads (v21) · seed `GAPTEST21` — ✅ PASS (2026-07-09)
`scratch/gaptest-p/` · `uv run btsgen-autoslay-smoke --seeds GAPTEST21 --character class4 --relic auto`
(`--relic auto` keeps the tester's own `on_hp_lost` starter relic — that's the point.)

Acceptance — observe in the log:
- lifesteal heal == the **unblocked** damage dealt (a blocked portion excluded at least once);
- `target_debuff_count` damage **grows** as debuff stacks accumulate on the target;
- the `draw_pile_empty`-gated bomb fires **only** when the draw pile is empty;
- the **relic** `on_hp_lost` hook fires on **card-caused** HP loss but **NOT** on enemy attacks.

Signal: mostly **behavioral** (no dedicated `[P]` tag — watch HP/damage numbers); the card-side `on_hp_lost`
twin logs `[H4]`. Already proven: all P cards import clean.

### [x] 2. Phase Q — add_card (v22) · seed `GAPTEST16` — ✅ FIXED (2026-07-10) + RUNTIME RE-VALIDATED (2026-07-13, Gate G-1: 439 fires / 0 deaths / 0 exc)
`scratch/gaptest-q/` · `uv run btsgen-autoslay-smoke --seeds GAPTEST16 --character class4 --relic auto`

Acceptance:
- `add_card` fires ×N into the named piles (hand/discard/draw);
- the `on_exhaust → add_card` **compost loop** runs **bounded** per turn (no runaway);
- generated copies **do not persist** across combats.

Signal: `[Q]`. Already proven: all `add_card` cards (Conjure Embers / Echo Blade / Stockpile / Grand Hoard +
on_exhaust & turn_start payloads) import clean.

### [x] 3. Phase R — discard (v23) · seed `GAPTEST17` — ✅ PASS (2026-07-09)
`scratch/gaptest-r/` · `uv run btsgen-autoslay-smoke --seeds GAPTEST17 --character class4 --relic auto`

Acceptance:
- `discard` fires ×N (random from hand);
- `on_discard` (Reflex) payoffs fire **ONLY** on effect-driven discards — **NONE** at turn-end hand cleanup;
- no re-entrancy runaway (a discard inside an `on_discard` payload does not cascade).

Signal: `[R]`. Already proven: the discard / on_discard cards import clean.

### [x] 4. Phase S — balance gauge (v24) · seed `GAPTEST1` — ✅ PASS (2026-07-09, both poles)
`scratch/gaptest-s/` · `uv run btsgen-autoslay-smoke --seeds GAPTEST1 --character class4 --relic auto`

Acceptance:
- gauge steps observed **BOTH** directions with a **sign flip at 0** (Dark ↔ Light);
- the **|8| extreme bite** fires at turn-start (Dark: lose 3 HP; Light: gain 1 Weak — both poles if the run allows);
- the `centered` payoff fires **only** near 0 (|gauge| ≤ N);
- **per-combat reset** (a fresh combat starts centered).

Signal: `[S]`. Already proven (2026-07-08): build clean + all 10 Balance Gap Tester cards imported with 0 mod
exceptions, then the env hang. This is the one most likely to need multiple seeds (the engine reaches |8| by
~turn 4, so the run must survive that long).

---

## Secondary / lower priority

### [ ] O-2a — hybrid combat smoke (Phase O weave)
Forge a real **two-archetype hybrid** class, stage it, and smoke that the bridge cards + strategy idioms run
in combat without crashing. No dedicated gap-tester — needs a **real forge** first (so it also depends on the
backend below), then stage the forged class into slot 04 and smoke it like the items above.

---

## Adjacent track — NOT AutoSlay (backend / generation checks)

These are **generation-side** checks that need the **Ollama Cloud forge backend**, not the crash/hang gate.
Listed here only so they don't get lost — run them on the generation pipeline, not through `btsgen-autoslay-smoke`.

- [ ] **Phase S real-forge pick:** run one forge on a duality-flavoured concept and confirm the
      **`balance_gauge` archetype is PICKED** by the map stage now that it resolves BUILDABLE.
- [ ] **O-ACC census sweep:** the real-forge vocab-usage census — are the new tokens (`balance_step`,
      `discard`, `add_card`, the P scalars, …) actually emitted at healthy rates by real forges?

**Ollama backend how-to (no secret in this file — by design):**
- The TRUE forge harness uses Ollama Cloud: invoke the generation CLI with the **`--ollama`** flag (see
  `generation/btsgen/ollama_mix.py`; base URL `https://ollama.com/v1`). All-local `--fake`/dolphin models
  whiff the strict stages and produce stunted classes — use `--ollama` for real coverage.
- **The credential lives in `generation/.env` as `OLLAMA_API_KEY` (that file is gitignored — keep it that
  way; do NOT paste the key value into this or any tracked file).** `ollama_mix.load_env()` reads it at
  runtime by expanding `${OLLAMA_API_KEY}`. If a forge dies on auth, check that `.env` exists and the var is
  set; if it dies resolving `ollama.com`, that's this box's intermittent DNS flakiness — just retry.
- Consider bumping `BTS_STAGE_ATTEMPTS>1` for the strict stages when exercising new vocab.
