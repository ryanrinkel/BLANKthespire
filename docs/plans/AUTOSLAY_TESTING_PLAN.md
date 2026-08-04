# AutoSlay Testing Plan

Status: **Phase 0 (static spike) complete — green-lit for Phase 1.** No mod code wired yet.
Author context: investigated 2026-06-16 after seeing AutoSlay referenced as an internal MegaCrit
testing tool. Phase 0 reflection spike run 2026-06-17 against `sts2.dll` v0.103.3 — see §4.

## TL;DR

AutoSlay is **MegaCrit's built-in run-automation tool**, unlocked by the community
[STS2AutoSlayMod](https://www.nexusmods.com/slaythespire2/mods/216). It auto-plays full runs to
**stress-test for crashes/hangs**, *not* to evaluate balance. It fits a real hole in our pipeline:
today we have **only static validation** of generated cards and no automated proof that a compiled
card doesn't crash or soft-lock the actual game.

**Recommendation:** adopt AutoSlay narrowly as an **automated crash/hang/smoke gate on compiled
generated cards**, downstream of codegen+compile. Keep **balance evaluation as a separate track**
using a stronger RL/agentic bot — AutoSlay's decision AI is not a trustworthy power-level signal.

**Phase 0 verdict (2026-06-17): green light.** The static spike confirmed AutoSlay has a clean
programmatic entry point, a headless launch-arg/bootstrap path that can pin our custom character +
seed, a structured machine-parseable log, and a watchdog that turns hangs into `RunFailed` events —
and that its player is **random** (so: crash/hang gate yes, balance no, exactly as scoped). We also
likely **do not need the Nexus mod** — our publicized `sts2.dll` lets our own mod call the runner
directly. Details in §4.

---

## 1. What AutoSlay is

- A run-automation runner baked into the shipping game; MegaCrit uses it internally for testing.
- STS2AutoSlayMod **unlocks and extends** the built-in runner — it does not reimplement it and does
  **not** alter cards, balance, or rules.
- Surface area exposed by the mod:
  - **AUTO SLAY button on the main menu** + a config popup (no dev console required).
  - **F9** freezes/resumes mid-run; while paused the board is fully interactive for inspection.
  - **Loop-after-run mode** runs games back-to-back indefinitely for stress-testing.
- Stated purpose: *"validate that mods don't crash the game by simulating many games quickly."*

**Critical nuance:** AutoSlay is a **stability/smoke-test tool**, not a balance evaluator. Its AI
plays to *complete* runs, not to play *well*, so its win/loss outcomes are a noisy and untrustworthy
signal for "is this card over/underpowered."

## 2. The gap it fills

Current generated-card testing is **static only**:

- `generation/btsgen/validator.py` — schema/vocab closure, ref-integrity, weighted balance *score*,
  plus dominance / permanence / loop warnings.
- `generation/tests/` — validator unit tests. **No gameplay simulation.**
- In-game verification is **manual** (a human plays a few runs) + player feedback JSONL
  (`generation/btsgen/feedback/card_feedback.jsonl`).
- A "headless balance simulator" is deferred to Phase 6 in `STS2_MOD_PLAN.md`.

The hole: once a card is **promoted → codegen'd → compiled into the mod**, *nothing automatically
confirms it doesn't crash or hang the real game when played.* AutoSlay's loop mode is well-suited to
surfacing exactly that — and would plausibly help reproduce/detect the open
**merchant-hang bug** (`merchant-hang-bug.md`, `_bugs/`), since loop runs hammer shops repeatedly.

## 3. Fit analysis — what it can and can't do for us

| Use | Fit | Notes |
|---|---|---|
| Crash/hang regression testing of compiled generated cards | ✅ Strong | Loop mode over many runs surfaces EffectRunner ops that throw, null refs, soft-locks, the merchant hang. |
| "Does this card even function in a real run" smoke test | ✅ Good | Confirms the card drafts, plays, and upgrades without breaking combat. |
| Balance / power-level evaluation | ⚠️ Weak | AutoSlay's AI isn't a strong/honest player; win-rate deltas would be noisy. Our static balance score is arguably better today. |
| Mid-generation testing (pre-promotion JSON) | ❌ No | AutoSlay only runs *compiled* cards. STS2 binds card identity to compiled .NET types (no mid-run loading), so this is inherently a post-codegen gate, not a replacement for static validation. |

## 4. Phase 0 findings (RESOLVED — reflection spike, `sts2.dll` v0.103.3, 2026-06-17)

Method: a read-only `MetadataLoadContext` probe over the game's `data_sts2_windows_x86_64/`
assemblies (same technique as `_modref/reflect/`). Probe source + raw output live in
**`_modref/autoslay_probe/`** (throwaway; git-ignored like the rest of `_modref/`). The whole runner
lives in namespace **`MegaCrit.Sts2.Core.AutoSlay`** — it ships in the retail build, not a dev-only
DLL.

The four gating questions are now answered:

**Q1 — Entry point: YES, two of them. Not GUI-only.**
- Programmatic: `AutoSlay.AutoSlayer.Start(string seed, string logFile)` (public) + `.Stop()` +
  static `AutoSlayer.IsActive`. This is what the Nexus button wraps; our own mod can call it directly
  because our build publicizes `sts2.dll`. **We likely don't need STS2AutoSlayMod at all.**
- Headless launch path: `NMainMenu.CheckCommandLineArgs()` + `Helpers.NonInteractiveMode`
  (`AutoSlayerCheck : Func<bool>`, `IsActive`) + `Nodes.Debug.IBootstrapSettings`
  (`BootstrapSettingsUtil.Get()`, `NSceneBootstrapper.StartNewRun()`). `IBootstrapSettings` exposes
  **`Character`, `Seed`, `Ascension`, `Act`, `Encounter`, `RoomType`, `Modifiers`, `SaveRunHistory`** —
  i.e. the game can boot straight into an autoslay run, pinned to a chosen character and seed, with no
  clicks. This is the CI path.
- At run end the runner calls `AutoSlayer.QuitGame(int exitCode)` → **process exit code is a usable
  pass/fail signal** for a CI wrapper.

**Q2 — Output: YES, structured + machine-parseable.** `AutoSlay.AutoSlayLog` writes a file (prefix
`[AutoSlay]`) via `OpenLogFile(path)`/`CloseLogFile()`, with explicit events:
`RunStarted(seed)`, `RunCompleted(seed)`, `RunFailed(seed, Exception ex)`,
`EnterRoom(RoomType,act,floor)`/`ExitRoom`, `EnterScreen(name)`/`ExitScreen`, `Action`,
`Info/Warn/Error(msg[,ex])`, `StateSnapshot(RunState)`. A smoke gate = run N seeds, then grep the log:
**any `RunFailed` (or exit code ≠ 0) = fail; capture the seed + exception**. Hangs are caught by
`AutoSlay.Helpers.Watchdog` (`Check`/`Reset`/`DumpState`, `_lastProgressTime`) + the timeouts in
`AutoSlayConfig` (`runTimeout`, `defaultRoomTimeout`, `defaultScreenTimeout`, `mapScreenTimeout`,
`watchdogTimeout`, `maxFloor = 49`), surfaced as `AutoSlayTimeoutException` → `RunFailed`.

**Q3 — Deck seeding: partial, and good enough.** AutoSlay's own card picks are **random**
(`AutoSlay.Helpers.AutoSlayCardSelector : ICardSelector`, built from an `Rng`). You cannot tell it
"draft card X." BUT `IBootstrapSettings` pins **Character + Seed (+ Encounter/RoomType)**, so runs are
reproducible and can be locked to our forged class. For *guaranteed* single-card exercise, combine
with the dev console (`card <id>`, `fight`, `room`, `travel`, `kill`, `win` — all present as
`AbstractConsoleCmd` subclasses) → that's the Phase 2 targeted harness. Note: `AutoPlayType` /
`CardCmd.AutoPlay` / `CardPlay.IsAutoPlay` are an **unrelated in-combat mechanic** (cards that auto-play
other cards, e.g. Hellraiser) — do not conflate with the run automation.

**Q4 — AI quality: confirmed random/weak.** The selector is `Rng`-driven and combat is screen-driving
(wait-for-screen → click with `buttonClickDelay`), bounded by watchdog timeouts. It plays to
*complete or abandon* runs and to *catch hangs*, **not to play well.** → Use for crash/hang/smoke only;
**do not** derive balance from win rates. (Matches our original assumption.)

**Throughput caveat:** it drives the *real* UI, not a millisecond headless combat sim. A full run is
gated by real (sped-up) screen transitions + `runTimeout`, so think *nightly / N-runs smoke*, not
*thousands-of-runs statistics*. That reinforces keeping balance on a separate (true-sim) track.

## 5. Phased plan

### Phase 0 — Static spike — ✅ DONE (2026-06-17)
Resolved all four gating questions via the reflection probe in `_modref/autoslay_probe/` (see §4).
Outcome: green light for Phase 1; AutoSlay is a scriptable, headless-capable, parseable crash/hang
gate with a random player. **Still owed (needs the running game, can't be done from reflection):**
a manual smoke pass — see §5a below — to confirm character targeting and watch one real run. This is
a verification step, not a blocker for designing Phase 1.

### Phase 1 — Crash-smoke gate (the realistic high-value win)
**VERIFIED END-TO-END 2026-06-17 — and it caught a real bug on run #1.**
First live run (seed BTSSMOKE1, forged class slot 04): hook fired ~6s after launch, file handoff worked,
AutoSlay selected the forged class, played all of Act 1 with our forged cards, and the driver correctly
classified the outcome as `RunFailed` (exit 1). The failure was a genuine soft-lock — the boss card
reward threw `CardFactory.CreateForReward: couldn't generate a valid rarity` (BossEncounter odds, no
available Rare) → rewards screen never appeared. This is the same family as the merchant hang on a
different code path; tracked separately (see memory `boss-reward-rarity-hang`). So §5b ("validate the
detector") is satisfied by a REAL hang rather than a synthetic one. Log tokens are now pinned to the
verbatim format. Remaining: observe a PASS run to confirm the `RunCompleted` token; decide whether to
pin a SPECIFIC character (today it embarks on whatever class the save last selected).

- `mod/BlankTheSpireCode/Testing/AutoSlaySmokeHook.cs` — a `[HarmonyPatch]` (auto-discovered by the
  existing `PatchAll()`, **no MainFile edit**) that, at `NMainMenu.CheckCommandLineArgs`, reads + consumes
  a request file and kicks `AutoSlayer.Start(seed, log)`. No-ops during normal play.
- `generation/btsgen/cli_autoslay_smoke.py` (+ `btsgen-autoslay-smoke` entry point) — per seed: writes the
  request, launches **via Steam**, polls the `[AutoSlay]` log + game process, classifies pass/fail.
- **HANDOFF IS FILE-BASED, NOT ENV/ARGS** (corrected 2026-06-17): STS2 must be launched through Steam
  (Steamworks DRM — a direct exe launch dies with *"Steam failed to initialize"*), and a `steam://`
  launch neither inherits our env nor passes args reliably, and detaches (no process handle / exit code).
  So the driver drops a JSON request at `%APPDATA%/SlayTheSpire2/autoslay/request.json`, the hook consumes
  it once, and the driver waits by polling the log file + the `SlayTheSpire2.exe` process (no exit code).
- **Still owed before trusting it:** (1) `dotnet build` the mod (do it when the game is closed and the
  status-effects spike is quiescent); (2) the §5a manual smoke pass to confirm it embarks on our forged
  class — **character pinning is stubbed** (logs a warning, uses the currently-selected class); (3) pin
  the exact `RunCompleted`/`RunFailed` log tokens in `cli_autoslay_smoke.py` (`TOK_*`) against the first
  real captured log; (4) the §5b detector-validation run against a 0-power-card class.

Design recap:
- Add a thin hook in **our** mod (preferred over the Nexus mod) that, when a sentinel is set
  (env var / launch arg / config button), calls `AutoSlayer.Start(seed, logFile)` for a list of seeds
  and writes the `[AutoSlay]` log to a known path. Use `NonInteractiveMode` + `IBootstrapSettings` to
  pin our forged **Character** and **Seed** so it boots straight into the run, then self-quits with an
  exit code.
- Add a `btsgen` CLI wrapper (e.g. `cli_autoslay_smoke.py`) that, after codegen+`dotnet build`,
  launches the game in that mode for N seeds, waits for exit, **parses the log**: `RunFailed` /
  non-zero exit / `AutoSlayTimeoutException` ⇒ fail, and reports the offending seed + exception. This
  becomes a post-promotion gate complementing `validator.py`.
- **Validate the detector first:** point it at a deliberately broken class (the known
  *0-power-card* pool that caused the merchant hang — see §5b) and confirm AutoSlay reports a
  `RunFailed` timeout when it reaches the shop. A gate that can't catch the one hang we already know
  about isn't trustworthy.

### Phase 1b — Linux port of the driver — ✅ DONE (2026-07-03)
The dev box moved to Linux (native STS2 Steam build). `cli_autoslay_smoke.py` + `smoke_relic.py` now
OS-detect through the new `generation/btsgen/game_paths.py` — the Windows paths are kept verbatim
(side-by-side, per project convention). Linux specifics, verified against a live run:
- game user dir = `~/.local/share/SlayTheSpire2` (logs, autoslay logs, forged/ staged classes);
  override with `BTS_STS2_USERDIR`.
- the mod hook's `SpecialFolder.ApplicationData` resolves to `~/.config/SlayTheSpire2` inside the
  game — NOT user:// — so the driver drops `request.json` in BOTH candidate dirs and the hook
  consumes whichever it watches (observed: the `~/.config` copy).
- launch = `xdg-open steam://run/<appid>` (Steam client running; offline mode OK); process
  detection/kill = `pgrep`/`pkill -x SlayTheSpire2`; dotnet = `~/.dotnet/dotnet`.

### Phase 2 — Targeted per-card harness (optional)
- AutoSlay drafts randomly, so it won't reliably exercise a *specific* new card. For guaranteed
  coverage, script the dev console (`card <id>` to inject the forged card, `fight`/`room`/`travel` to
  force the encounters) — independent of AutoSlay's own selection — and assert no exception.

### Phase 3 — Balance signal — NOT AutoSlay (confirmed)
- Phase 0 confirmed the player is random, so **do not** use AutoSlay for balance. Point Phase 6's
  "headless balance simulator" at a *stronger* agent (see §6). Keep balance a separate track.

### 5a. Manual smoke pass still owed from Phase 0 (needs the running game)
A short checklist for when the game is launched (interactive; ~15 min):
1. With our mod loaded, trigger `AutoSlayer.Start(<seed>, <logPath>)` (dev console / a temporary
   config button) **or** install STS2AutoSlayMod and use its AUTO SLAY button as a reference.
2. Confirm it can **select / be pinned to our custom character** (the one open question reflection
   can't answer — verify `IBootstrapSettings.Character` accepts our `CustomCharacterModel`).
3. Watch one run; confirm the `[AutoSlay]` log appears at the expected path and contains
   `RunStarted` → `EnterRoom`/`EnterScreen` … → `RunCompleted`.
4. Confirm our forged cards get drafted/played over a few runs without throwing.

### 5b. Honoring the two caveats (2026-06-17)
- **Merchant bug is already fixed** (root cause: a forged class with **0 Power cards** breaking
  merchant card generation). So it's no longer a bug to find — instead reuse it as the **repro fixture
  to validate the Phase 1 detector** (a temporary no-power-card pool should make AutoSlay `RunFailed`
  at the shop). Don't spend AutoSlay effort hunting a hang that's already patched.
- **A parallel agent is editing status-effect files.** Phase 0 touched **only** the isolated
  `_modref/autoslay_probe/` folder and this plan doc — no `mod/` source. Phase 1+ will touch mod code
  (a new hook file) and should be sequenced *after* the status spike lands, or kept to a brand-new
  file (e.g. `mod/BlankTheSpireCode/Testing/AutoSlayHook.cs`) to avoid colliding with their edits.

## 6. Stronger alternatives for the *balance* half (complementary, not either/or)

For genuine power-level data rather than crash-testing:

- **[AI Playtesting / AIPA](https://github.com/AIPlaytesting/AIPA)** — Deep-RL agent built to
  playtest StS-style card games and report dominant strategies / imbalanced cards. Closest match to
  "AI that tells you if a card is broken."
- **[bottled_ai](https://github.com/xaved88/bottled_ai)** — automated StS player.
- **[STS2MCP](https://github.com/Gennadiyev/STS2MCP)** — exposes in-game state + an MCP server for
  "full agentic runs"; fits our existing tooling style and could drive much stronger playtests than
  AutoSlay's built-in AI.

## 7. Where this sits in the pipeline

```
LLM → JSON card
  → validator.py (static: schema, ref, balance score, pattern warnings)   [EXISTING gate]
  → quarantine → human review → promote
  → cardgen.py codegen → C# DataCard shell → compile .NET
  → AutoSlay loop mode (crash/hang smoke gate)                            [PROPOSED Phase 1]
  → [optional] targeted per-card harness                                 [PROPOSED Phase 2]
  → [separate track] RL/agentic bot for balance                          [PROPOSED Phase 3 / Phase 6]
```

AutoSlay is a **downstream, post-compile gate** — it complements, never replaces, static validation.

## Sources

- [STS2AutoSlayMod (Nexus)](https://www.nexusmods.com/slaythespire2/mods/216)
- [AI Playtesting](https://aiplaytesting.github.io/) / [AIPA repo](https://github.com/AIPlaytesting/AIPA)
- [bottled_ai](https://github.com/xaved88/bottled_ai)
- [STS2MCP](https://github.com/Gennadiyev/STS2MCP)
