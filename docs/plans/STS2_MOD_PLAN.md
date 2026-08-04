# Plan — Turning BLANK the spire into a Slay the Spire 2 Mod

**Author:** Ryan Rinkel
**Date:** 2026-06-15
**Status:** Draft plan
**Goal:** Ship an STS2 mod that adds a custom character + cards + relics, **keeping the LLM
content-generation feature** (users connect an LLM to generate their own classes/cards). Art is
placeholder for now.

---

## 1. The core realization

STS2 is **not** modded by porting a Godot project into it. STS2 mods are **C# (.NET 9) assemblies**
compiled against the game's own engine and loaded at runtime:

| | BLANK the spire prototype | Slay the Spire 2 |
|---|---|---|
| Engine | Godot **4.6**, **GDScript** | Godot **4.5.1 .NET (Mono / C#)** |
| Shape | Standalone game with its **own** combat engine, powers, relics, map, run loop, UI | A finished game; mods **register content into it** |
| Mod format | n/a | `<Mod>.dll` + `<Mod>.pck` + `<Mod>.json` manifest in `mods/<Mod>/`, native "Load with Mods" |
| Content API | JSON validated against schema, interpreted by `Effect.gd` | C# classes via `MegaCrit.Sts2.Core.Modding` + **BaseLib-StS2** (community base lib) |
| Card definition | Declarative JSON `effects[]` | Imperative C#: `class X : CustomCardModel(cost,type,rarity,target)`, override `async OnPlay()` enqueuing actions (`DamageCmd.Attack().Execute(...)`) |

**Consequence:** the prototype's GDScript combat engine (CombatManager, Effect ops, Powers, Relics
interpreters, MapGen, RunState, all UI scenes) is **not portable** — STS2 already provides all of it.
It is retained only as **reference semantics** and as an **offline balance simulator**, not shipped.

**What transfers (the valuable parts):**
1. **btsgen** — the Python/Anthropic generation pipeline. Engine-independent; survives nearly intact.
2. **The "closed JSON vocabulary → interpreter" architecture.** This is the bridge between an LLM
   (which reliably emits schema-shaped JSON) and STS2 (which wants imperative C#). We rebuild the
   `Effect.gd` op-dispatch table **in C#**, mapping each vocabulary op onto STS2's action API.

---

## 2. Target architecture

```
                         ┌─────────────────────────────────────────────┐
   LLM (Anthropic) ─────▶│  btsgen  (Python, mostly unchanged)         │
                         │  brief → prompt(VOCAB+schema) → JSON → valid. │
                         └───────────────────────┬─────────────────────┘
                                                 │  validated JSON content
                                                 ▼
                         data/cards/*.json, relics/*.json, characters/*.json
                                                 │
                                                 ▼
   ┌─────────────────────────────────────────────────────────────────────────┐
   │  CODEGEN  (new step — Python or C# source generator)                     │
   │  each validated JSON card → one .cs file:                                │
   │     [Pool(typeof(MyCharPool))] [CustomID("frost_shard")]                 │
   │     public class FrostShard : CustomCardModel(1, Attack, Common, Enemy) {│
   │        // embedded effect list + DynamicVars/tags from JSON              │
   │        protected override Task OnPlay(ctx, play) =>                      │
   │            EffectRunner.Run(EFFECTS_JSON, this, ctx, play);  // delegate │
   │     }                                                                    │
   │  + localization entry (cards.json) for name/text/numbers                 │
   └───────────────────────────────────┬─────────────────────────────────────┘
                                        │  dotnet build
                                        ▼
   ┌─────────────────────────────────────────────────────────────────────────┐
   │  STS2 Mod  (C#, .dll + .pck + manifest)  — loaded once at ModelDb.InitIds │
   │                                                                          │
   │   EffectRunner.cs   ← THE hand-written interpreter (C# port of Effect.gd)│
   │     Run(effects, card, ctx, play):  op-dispatch over the vocabulary      │
   │        "damage"       → CommonActions.CardAttack(...).Execute()          │
   │        "block"        → block command                                    │
   │        "apply_status" → apply power command                              │
   │        "multi"/"conditional"/"from_state" → recursion / live state reads │
   │                                                                          │
   │   <generated card classes>     ← one per LLM card (thin, delegate above) │
   │   CustomCharacterModel / CustomCardPoolModel  ← class + color (BaseLib)  │
   │   CustomRelicModel             ← relic hooks                             │
   └─────────────────────────────────────────────────────────────────────────┘
```

Two things stay in lockstep: the schema's op `enum`, and `EffectRunner`'s `switch` cases. Anything the
interpreter can't translate isn't in the vocabulary, so the LLM can never emit it — the schema remains
prompt, validator, and safety boundary at once (PRD §10). The **only** change vs. the prototype is that
the interpreter is reached through a generated, compiled class shell instead of a runtime data load.

---

## 3. The central technical risk — RESOLVED in M0 (2026-06-15)

Both deciding questions were answered from BaseLib/ModTemplate source (`_modref/`). **Both are NO**, and
this fixes the architecture:

- **Q1 — Can one class back many JSON-defined card ids?** ❌ **NO.** BaseLib binds card identity to the
  compiled .NET **Type**. `CustomCardModel`'s ctor self-registers `GetType()` into a `HashSet<Type>`
  (`BaseLib-StS2/Abstracts/CustomCardModel.cs`, `Patches/Content/ContentPatches.cs`); ids derive from
  the type name + prefix (`PrefixIdPatch.cs`). The only override, `[CustomID("...")]`, is still
  per-class. **One C# class = exactly one card.** No instance/arbitrary-id registration exists.
- **Q2 — Can content be added mid-run?** ❌ **NO.** Everything registers once at the game's
  `ModelDb.InitIds`; pools are computed from static, init-populated lists and are effectively frozen
  afterward (`ContentPatches.cs`, `PostModInitPatch.cs`). The only late "register" call is a save/load
  deserializer for custom *reward types*, not a way to add a card/relic to a live pool.

**Architectural consequence (the new shape):** LLM content **cannot** be shipped as live JSON data. Each
generated card/relic/character must become a **compiled C# class**, registered at mod init. We therefore
add a **codegen step**: validated LLM JSON → one thin generated `CustomCardModel` subclass per card that
**embeds its effect list and delegates to a single shared `EffectRunner`** (the C# port of `Effect.gd`).
All real logic stays in one hand-written interpreter; codegen only emits a class shell + the embedded
data + the `DynamicVars`/tags the game needs for tooltips and upgrade scaling.

This *is* still the prototype's "closed vocabulary → interpreter" design — we lose only **runtime
dynamism**. Since you chose **offline-authoring first**, that loss is free. **True in-run generation
(old M5) is impossible** under Q2; the closest fallback is "generate mid-run → write C# → recompile →
**restart** to play," which is demoted to a note, not a milestone.

---

## 4. What we keep, adapt, and retire

**Keep (port directly):**
- `generation/` (btsgen) — Anthropic wrapper, contract/prompt builders, validator, balance scoring,
  quarantine/review CLIs, `--fake` offline mode. ~90% unchanged.
- The schema + VOCABULARY docs **as a contract** (content reconciled to STS2 — see Phase 3).
- The card/relic/character JSON corpus as **few-shot exemplars** and a regression set.

**Adapt:**
- **Vocabulary/schema** → the op set becomes the **intersection** of "LLM can express it" and "C#
  interpreter can translate it into a real STS2 action." Some prototype ops map 1:1 (`damage`,
  `block`, `apply_status`, `draw`, `gain_energy`, `multi`); some need STS2 equivalents (`from_state`,
  `conditional`, `fuse`, `set_flag`); some prototype statuses/relics may not exist in STS2 and get
  dropped or remapped to STS2 keywords.
- **Balance numbers** → recalibrate against STS2 (the `generation/reference/` distillation already
  does this for STS2; refresh it against the current EA build).
- **CharacterForge.gd** subprocess bridge → reborn as `LlmBridge.cs` (C# `HttpClient` to Anthropic, or
  `Process` shelling to btsgen) **if** runtime generation lands; otherwise dropped.

**Retire (keep as reference only, do not ship):**
- All GDScript engine code: `autoload/`, `core/effects|powers|relics|run|map`, `scenes/`, the
  prototype's CombatManager/RunState. Archived as the **semantic oracle** for the C# interpreter and
  reused headless as a **balance simulator** (Phase 6).

---

## 5. Milestones

### M0 — Toolchain & feasibility spike  ✅ *(source analysis done 2026-06-15)*
**Done:**
- Cloned & analyzed `BaseLib-StS2`, `ModTemplate-StS2`, `STS2FirstMod` (in `_modref/`).
- Resolved Q1 (no data-driven cards) and Q2 (no mid-run injection) → see §3. Architecture set: **codegen
  + shared `EffectRunner`**.
- Confirmed game install: `C:\Program Files (x86)\Steam\steamapps\common\Slay the Spire 2`, **v0.103.3**
  (2026-05-29), `sts2.dll` under `data_sts2_windows_x86_64\` (= `$(Sts2DataDir)`); no `mods/` folder yet.
- Confirmed toolchain facts: `.csproj` uses `Godot.NET.Sdk/4.5.1`, `net9.0`, `EnableDynamicLoading`;
  references `sts2.dll` + `0Harmony.dll`; NuGet `Alchyr.Sts2.BaseLib`, `Krafs.Publicizer`,
  `Alchyr.Sts2.ModAnalyzers`; post-build copies `.dll/.pdb/.json` into `mods/<Name>/`.
- Manifest fields: `id, name, author, description, version, has_pck, has_dll, dependencies[],
  affects_gameplay`. Gameplay mods need `affects_gameplay:true` **and** a `BaseLib` dependency.

**Toolchain proven (2026-06-15):**
- ✅ Installed **.NET 9 SDK 9.0.315** per-user at `%USERPROFILE%\.dotnet\` (no admin; winget UAC path
  failed with 1602, the official per-user `dotnet-install.ps1` worked). Invoke via that path or set
  `DOTNET_ROOT`; the `C:\Program Files\dotnet\` on PATH is runtime-only.
- ✅ Installed template pack **`Alchyr.Sts2.Templates` 2.4.3** (`dotnet new install`) → templates
  `alchyrsts2mod`, `alchyrsts2charmod`, `alchyrsts2contentmod`.
- ✅ Scaffolded a content mod (`dotnet new alchyrsts2contentmod -M "Ryan Rinkel" -P`), **`dotnet build`
  succeeded 0/0**, NuGet auto-restored BaseLib, and the post-build target **auto-copied
  `SlapSpoorSpike.dll/.json/.pdb` into the game's `mods/SlapSpoorSpike/`**. (Spike project lives in
  `_modref/spike-build/` — throwaway.)

**Remaining for in-game verification (user-side):**
- Install the **BaseLib runtime mod** into `mods/` (manifest declares `dependencies:["BaseLib"]`; the
  NuGet pkg is compile-time only — the game needs the BaseLib *mod* present at runtime).
- Install **MegaDot / Godot 4.5.1 mono** (`C:/megadot/...` per `Directory.Build.props`) and `Publish`
  to emit the `.pck` carrying localization JSON + (placeholder) images, else card text/art is missing.
- Launch via **"Load with Mods"** and confirm the sample card appears.
- *Exit:* a trivial custom card appears in a real run.

### M1 — The `EffectRunner` interpreter + card codegen (the heart)  ✅ *code-side done 2026-06-16*
**Done — builds 0 errors, auto-deploys to the game's `mods/`:**
- Real character mod scaffolded at `mod/` (`BLANK the spire`, char template). Per-user SDK build loop working.
- `mod/BlankTheSpireCode/Engine/`: `CardSpec`/`EffectSpec` (C# mirror of the JSON vocab), `EffectRunner`
  (the op-dispatch interpreter — damage/block/draw/apply_status), `DataCard : ConstructedCardModel`
  (declares DynamicVars in ctor, executes via EffectRunner in `OnPlay`).
- Verified STS2 API via a `MetadataLoadContext` reflection tool (`_modref/reflect/`): built-in powers are
  `MegaCrit.Sts2.Core.Models.Powers.{Vulnerable,Weak,Strength,...}Power`; attacks run via
  `CommonActions.CardAttack(card, play).Execute(ctx)`.
- Codegen `generation/btsgen/cardgen.py` (pure stdlib): card JSON → thin `DataCard` subclass + `cards.json`
  loc. Regenerated Strike/Defend/Bash/PommelStrike from `mod/content/cards/*.json`; rebuilds clean.
- Cards wired into the character's starting deck (5 Strike / 4 Defend / 1 Bash); Pommel in the pool.
- *Temp:* `.editorconfig` downgrades analyzer STS001 to warning until M2 writes character/architect loc.

**In-game verification — now LAUNCHABLE (2026-06-16):**
- ✅ BaseLib runtime mod (v3.2.1) installed in `mods/BaseLib/`.
- ✅ `.pck` produced by **`BSchneppe.StS2.PckPacker`** at build time (no MegaDot needed for simple PNG+JSON
  assets) → `mods/BLANK the spire/` now has `.dll + .pck + .json`. Throwaway M0 spike removed from `mods/`.
- ✅ **Renamed (2026-06-16):** project/id/namespace `BlankTheSpire`, display name **"BLANK the spire"**,
  loc prefix `BLANKTHESPIRE-`. Character localization authored (14 keys) so the character shows a real
  name/description; only 4 optional `THE_ARCHITECT.talk.*` banter keys remain (different loc table).
- ⚠️ **Gotcha:** STS2 scans `mods/` only at startup and locks loaded mod `.dll`s — must fully QUIT and
  relaunch after each deploy. (This is why the first session "only showed BaseLib": the mod was rebuilt
  after the game had already launched.)
- ✅ **VALIDATED IN-GAME (2026-06-16):** "BLANK the spire" loads (`RUNNING MODDED`, 0 exceptions), is
  selectable, Neow card reward works, first combat won, post-combat rewards work. Generated cards
  (Quick Jab, Hold the Line) offered & picked. The full loop runs.
- Reward-pool lesson: a custom character needs enough non-Basic cards across Common/Uncommon/Rare or
  `CardFactory.CreateForReward` throws and the run hangs. Pool now 5 common / 3 uncommon / 2 rare + 3 basics.
- ⚠️ Still unverified by eye: exact tooltip numbers, AoE (Cleave/Reckoning) and Weak (Clothesline) when played.

#### Original M1 plan (for reference)
- **`EffectRunner.cs`** — the one hand-written interpreter: `Run(effects, card, ctx, play)` op-dispatch
  mapping each vocabulary op to STS2 commands (`CommonActions.CardAttack(...).Execute()` for `damage`,
  block command for `block`, apply-power for `apply_status`, etc.). High-value ops first: `damage`,
  `block`, `apply_status`, `draw`, `gain_energy`, `multi`; then `from_state`, `conditional`, `lose_hp`,
  `heal`, `add_card`; defer `fuse`/`set_flag`.
- Port targeting (`self`, `enemy`, `random_enemy`, `all_enemies`) to STS2 `TargetType`/action targets.
- **Codegen** — one thin `CustomCardModel` subclass per JSON card: `[Pool]`/`[CustomID]`, ctor args from
  JSON (cost/type/rarity/target), embedded effect list, `DynamicVars`/`CanonicalTags` for tooltip &
  upgrade scaling, `OnPlay` delegating to `EffectRunner`. Plus the localization `cards.json` entry.
- Validate semantics against the prototype as oracle (same JSON → same logical outcome).
- *Exit:* a hand-authored data card, codegenned and compiled, plays correctly in STS2 with correct
  tooltip numbers.

### M2 — Custom character, color, starter deck, relics from data
- `DataColor` + `DataCharacter` registering one custom class (HP, energy, starting deck, starter relic)
  from `characters/*.json`. Placeholder color/art.
- `DataRelic` mapping the prototype's relic-hook JSON onto STS2 hooks (BaseLib hooks / Harmony patches).
- Wire the basic/common card pool so rewards draw from the data cards.
- *Exit:* a full custom character is selectable and playable start-to-boss using only data-defined content.

### M3 — Retarget btsgen to the STS2 contract
- Reconcile `card.schema.json` / `relic.schema.json` / `character.schema.json` op & status `enum`s to
  **exactly** what the M1/M2 C# interpreter supports (schema enum ≡ interpreter switch).
- Refresh `VOCABULARY.md` / `RELIC_VOCABULARY.md` and STS2 balance reference numbers.
- Repoint `btsgen/paths.py` at the mod's schema/data dirs; regenerate few-shot exemplars from the new corpus.
- Keep `--fake` working; keep the validator runnable with no API key.
- *Exit:* `btsgen-generate` / `-relic-generate` / `-character-generate` produce JSON that the mod loads
  and plays without manual fixups; validator rejects anything the interpreter can't run.

### M4 — Offline generation → playable content loop  ✅ *wired & proven 2026-06-16*
**Done — one command does brief → LLM → validate → codegen → build → deploy:**
- `generation/btsgen/cli_forge.py` (`uv run btsgen-forge`). Repoints btsgen (via new `BTSGEN_*` env
  overrides in `paths.py`) at a **constrained contract** `mod/contract/` (card.schema.json + VOCABULARY.md
  + statuses/) that allows ONLY the ops EffectRunner runs (damage/block/draw/apply_status[vulnerable|weak],
  targets enemy/self/all_enemies) — so generated cards are guaranteed playable. Reuses btsgen's
  generate→validate→repair→quarantine, then promotes JSON to `mod/content/cards/`, runs `cardgen.py`,
  `dotnet build`, deploys.
- Proven end-to-end with `--fake` (no API key): brief → valid card → codegen → **Build succeeded** → deploy.
  cardgen now self-cleans stale generated `.cs`. `generation/.env` created (user pastes ANTHROPIC_API_KEY).
- Constraint: rares wanting build-around ops (multi/from_state/etc.) await EffectRunner growth (M2/M5).
- Generated cards join the reward pool at their rarity (not auto-added to the starting deck).

#### Earlier milestones below
- CLI authoring loop: generate → validate → quarantine (`data/generated/`) → review/approve → bake into
  the mod's shipped `data/` (or `.pck`). Approved classes/cards appear in-game on next launch.
- *Exit:* "user connects an LLM, generates a class, it's playable in STS2" works via the offline path.

### M5 — In-game "forge" screen (between-sessions generation)  ✅ *built 2026-06-16*
True mid-run injection is impossible (pools freeze at `ModelDb.InitIds`), so this is the realistic shape
the user asked for: an in-game **pre-game forge screen** that generates outside live gameplay and applies
on restart.
- `mod/BlankTheSpireCode/ForgeConfig.cs` — a BaseLib `SimpleModConfig` (appears in the main-menu mod
  settings list; also makes BLANK the spire show there). Dropdowns (type/rarity), theme text field,
  repo-path field, fake toggle, **Forge** button, **Apply & Restart** button. Popups via Godot `AcceptDialog`.
- **Forge** runs `btsgen-forge --no-build` via the venv python on a background thread (LLM + codegen run
  while the game is open — the "come back later" wait; the build is deferred because the running game
  locks its own DLL). Popup on completion.
- **Apply & Restart** spawns `tools/apply_and_restart.ps1` (detached) and quits the game; the helper waits
  for exit, `dotnet build`s (DLL now unlocked → deploys), and relaunches via `steam://run/2868840`.
- Registered in `MainFile.Initialize` via `ModConfigRegistry.Register`. Compiles 0 errors; deployed.
- ⏳ Needs in-game testing by the user (the forge UI, the restart cycle).
- Note: depends on the dev box (repo + .NET SDK + Python venv + API key) — it's an author tool, not a
  shippable end-user feature.

### M6 — Polish, packaging, distribution
- Placeholder-art pipeline (a single default card/relic frame + generated text) so every generated
  card is legible without bespoke art; real art later.
- Loader-compat handling (EA updates change `sts2.dll` signatures — pin/verify per the tutorial).
- Package `.dll`+`.pck`+manifest; publish to Nexus now, Steam Workshop when it opens.

---

## 6. Reuse the old engine as a balance simulator (bonus)
The retired GDScript engine is deterministic and headless-testable. Point slagen's balance step at a
**headless sim** (the prototype's CombatManager driving an autoplayer) to score generated cards by
simulated win-rate, upgrading the current heuristic score. Optional, high-value later.

---

## 7. Key decisions — CONFIRMED (2026-06-15)
1. **Generation timing:** ✅ **offline-authoring first**; in-run (M5) is a gated stretch.
2. **LLM transport in-mod:** ✅ **subprocess to Python btsgen** (reuse all existing
   prompt/validate/repair/balance code). Pure-C# path revisited only if shipping Python is awkward.
3. **BaseLib dependency:** depend on **BaseLib-StS2** (community-standard, fastest). *(default — confirm in M0)*
4. **Repo shape:** new `mod/` C# project beside `generation/`; archive `slap-the-spoor-(test)/` as
   `reference/` once M1 proves the interpreter. *(default — confirm in M0)*

## 8. Open questions
- ~~Q1 — one class, many ids?~~ **Resolved: NO** (codegen one class per card).
- ~~Q2 — mid-run registration?~~ **Resolved: NO** (offline + recompile only).
- Which prototype statuses/relics have no STS2 analog and must be dropped/remapped to STS2 keywords?
- STS2 action API surface for `from_state` / `conditional` (reading live combat state mid-card) —
  confirm against decompiled `sts2.dll` during M1.
- How upgrade variants map: prototype's `upgrade.effects` vs. STS2 `OnUpgrade()` + `DynamicVar.UpgradeValueBy`.
- Loader fragility: EA updates change `main_assembly_hash`/signatures (currently `-1584622192`, v0.103.3) —
  plan a re-pin step per game update.

> Reference clones live in `_modref/` (git-ignore or delete before committing). Game data is read-only.

---

## 9. Sources
- STS2 runs on Godot 4.5.1 .NET; mods are C# `.dll`+`.pck`+`.json`, native "Load with Mods."
- Example mod: `MegaCrit.Sts2.Core.Modding`, `[ModInitializer("ModLoaded")]` — github.com/jiegec/STS2FirstMod
- BaseLib-StS2 (Alchyr): `CustomCardModel(cost,type,rarity,target)`, `[Pool(...)]`, override `OnPlay`,
  `DamageCmd.Attack().Execute(...)` — github.com/Alchyr/BaseLib-StS2 + alchyr.github.io/BaseLib-Wiki
- Modding tutorial (setup, manifests, Harmony, .pck, packaging) — github.com/fresh-milkshake/Modding-Tutorial
- STS2 modding MCP server (game-data query / codegen / build) — github.com/elliotttate/sts2-modding-mcp

---

## 10. The public / shippable solution — website generation + import codes  *(planned 2026-06-16)*

**Goal:** anyone with the game + a browser can generate and share custom cards/characters. No .NET SDK,
no Python, no API key, no recompile on the player's machine. Decisions: **hosted cloud generation** (our
key, on a website) + **paste-a-code import** in-game (also the sharing mechanism). *(Plan-first; not yet built.)*

### 10.1 The root fix — stop compiling cards, load JSON (data-driven "slots")
Everything that ties the current pipeline to a dev box traces to ONE thing: we compile each card into a
C# type. Remove that and the SDK / Python / `dotnet build` / repo dependencies all vanish for end users.

- Ship the mod with a fixed set of generic **slot classes** — `ForgedCardSlot01..NN` (subclasses of the
  existing `DataCard`) and a few `ForgedCharacterSlot01..MM`. At **game load** (`ModelDb.InitIds`) each
  slot reads its definition from JSON in the writable user-data dir (`user://forged/cards/NN.json`,
  `.../characters/NN.json`) instead of from a baked-in literal.
- We're ~80% there: `DataCard` already takes a `CardSpec` and builds vars/effects in its ctor; `EffectRunner`
  already interprets it. Change = *read the CardSpec from JSON at ctor* instead of a compile-time literal.
- **Card text/name** comes from BaseLib's in-code loc hook (`ILocalizationProvider` → `CardLoc`) read from
  the same JSON → **no `.pck` rebuild** either. Empty slots register as hidden, never offered.
- Net effect: **adding content = writing a JSON file.** The compiled mod (slots + EffectRunner) ships once
  and never changes; only data changes. Survivor constraint: JSON is read at startup → **restart to load**
  (Q2). Fixed live-slot cap (e.g. 100 cards / 8 characters), recyclable.

### 10.2 The website (hosted generation — our key)
- Static front-end + one stateless serverless function holding the Anthropic key and the SAME constrained
  contract + validator (the schema/vocabulary is the shared source of truth; port the validator to JS/TS or
  run the Python one behind the function).
- Player describes a card/character → generate → validate → assemble a JSON **bundle** (a card, or a
  character = `{character, starting_deck, relic?, pool_cards[]}`) → **encode to an import code** → "Copy".
- Cheap to run (stateless, per-request LLM cost). Add rate-limiting + light moderation. Optional gallery later.

### 10.3 The import code (the shareable artifact)
- `code = base64url(gzip(json))` with a short header: `BTS1.<vocabVersion>.<payload>.<crc>`.
- Self-contained → **sharing needs no backend**: trade codes on Discord/Reddit, paste to import. (Optional
  hosted gallery is a nice-to-have, not required.)
- `vocabVersion` lets the mod gracefully reject a code that needs newer ops ("this character needs BLANK
  the spire vNN — update the mod").
- **Safe by construction:** a code is DATA over a closed vocabulary; the mod re-validates every op/status/
  target against its live `EffectRunner` on import and never executes code. Pasting a stranger's code is safe.

### 10.4 The in-game import screen (mod becomes a pure importer)
- A BaseLib `SimpleModConfig` (like the M5 forge screen) but minimal: a **paste field** + **Import** button
  + **Restart to apply** button. Import → decode → re-validate → write `user://forged/.../NN.json` into a
  free slot → popup "Imported into slot NN; Restart to play."
- No network calls, no async generation, no Python/SDK in the mod. Restart loads the slots.

### 10.5 Phasing
- **P1 — Slot runtime (the enabler):** convert `DataCard` to load JSON slots from user-data at startup +
  in-code loc; ship N empty card slots. Prove with hand-written slot JSON. *After this, no end user needs an
  SDK or recompile.* ✅ **DONE & VALIDATED IN-GAME 2026-06-16** — "Slot Test Blade" loaded from JSON into
  the reward pool with correct name/text and dealt damage + applied Weak as described. The data-driven slot
  path works end-to-end (write JSON → restart → playable, no recompile).
  - `ForgedCards.cs` (Engine): reads `user://forged/cards/NN.json` (= `%APPDATA%\SlayTheSpire2\forged\cards\`)
    at startup via Godot `Json`/`FileAccess`/`DirAccess` (no extra deps), parses the **same JSON shape as the
    baked corpus** (`mod/content/cards/*.json`), synthesizes description text like `cardgen.py` `describe()`,
    and **re-validates every op/status/target against the live EffectRunner vocab** — anything unsupported
    (or rarity `basic`, or 0 effects) leaves the slot empty + logs, never crashes init. (This validator is
    what the P2 paste-import will reuse.)
  - `CardSpec` gained `Title`/`Description`/`IsEmpty`; `DataCard` now implements BaseLib `ILocalizationProvider`
    → injects forged card name/text at `ModelDb.Init` with **no `.pck` rebuild** (baked cards keep Title null
    and still use the shipped `.pck` `cards.json`). Empty slots pass `autoAdd:false`+`showInCardLibrary:false`
    so unfilled slots are invisible (out of reward pool + compendium) until JSON fills them.
  - Ships **40** generic `ForgedCardSlotNN` classes (`Cards/Forged/ForgedCardSlots.g.cs`, generated by
    `generation/btsgen/slotgen.py`; count = `ForgedCards.SlotCount`). Distinct compiled type per slot (Q1).
  - Proof file written: `%APPDATA%\SlayTheSpire2\forged\cards\01.json` = "Slot Test Blade" (uncommon attack,
    1 cost, 9→12 dmg + Weak 1→2). **Needs in-game check** (fully quit + relaunch first): card should appear in
    the BLANK-the-spire reward pool as an uncommon with correct name/text/tooltips, and play correctly.
- **P2 — Import screen + code format:** define `BTS1` codec; in-game paste→validate→slot→restart. Test with
  codes pasted by hand / from a stub. (Sharing works at this point, via hand-made or website codes.)
  ✅ *code-side done 2026-06-16 — builds 0 errors, deployed; awaits in-game paste test.*
  - `BTS1Codec.cs` (Engine): `BTS1.<vocabVersion>.<base64url(gzip(json))>.<crc32>`. `TryDecode` strips
    whitespace (line-wrapped pastes), rejects non-BTS1 / bad-version (`code v > ForgedCards.VocabVersion`
    → "update the mod") / checksum-mismatch with human messages. Safe by construction (data only, never
    executed). `generation/btsgen/bts1.py` is the byte-compatible Python encoder/decoder (reference for the
    P3 website). Cross-impl verified: hand-rolled C# CRC-32/IEEE proven == `zlib.crc32` (std vector
    `cbf43926` + real payload), base64url/gzip standard.
  - `ForgedCards` refactor: parsing now returns error strings via `TryParseCardJson` (shared by the startup
    loader AND the importer — one validator, one source of truth). Added slot-file store helpers
    `SlotPath`/`SlotFileExists`/`FirstFreeSlot`/`WriteSlotFile` + `VocabVersion=1`.
  - `ForgeConfig.cs` gained an **"Import a shared code"** section (same screen as the dev forge, since one
    config per mod-id): paste field, `ImportSlot` slider (0 = auto lowest-free), **Import code into a slot**
    button (decode → re-validate vs live vocab → write `NN.json` → popup), **Restart to apply** button
    (build-free: detached `Wait-Process <pid>` → relaunch `steam://run/2868840`, then Quit). This is the
    end-user path — no SDK/Python/repo needed to import.
  - **Validated in-game 2026-06-16:** paste→import→restart→play works (Slot Test Blade, Coded Bolt, Sunder
    Wave all imported via codes and played; console `card BLANKTHESPIRE-FORGED_CARD_SLOTNN` adds them instantly).
  - **Post-test fixes (2026-06-16):** (a) **dedupe** — re-importing a card now updates its existing slot in
    place (by id) instead of spawning a duplicate, unless `ImportSlot` is set explicitly. (b) **Slot
    management** — "Clear slot (set ImportSlot first)" + "Clear ALL forged cards" buttons (delete slot JSON;
    restart to apply) so a slot is never stuck. (c) **AoE text bug** — description synthesis ignored the
    card's target, so `all_enemies` cards read "Deal X damage" with no "to ALL enemies". Fixed in the SHARED
    describe logic (both `cardgen.py` for baked cards AND `ForgedCards.Describe` for slots): damage→"… to ALL
    enemies"/"… to a random enemy", status→"Apply Vulnerable to ALL enemies". Regenerated baked loc
    (Cleave/Reckoning/Expose now correct); slot cards re-synthesize text at load (no re-import needed).
    Codec delivery lesson: NEVER hand-transcribe a BTS1 code into chat (drops the `.` separator → "not a valid
    code"); hand it to the user as a file.
  - **Test code ready** (encodes "Coded Bolt", common attack, 1 cost, 6→9 dmg + Vulnerable 1→2):
    `BTS1.1.H4sIAAAAAAAC_6WPTQrCQAyF9z1FmHU3dSHoUo8hUtJOWsTOD9NUGMrc3UlHhC7FXfLl5eVlrQDUQ6szqN5p0m3nJla1UIuGhF-Fw-XLOfqNIzP2z8IChgfH4mKMs4X2bubMmrKGYSRpFVkysShoGKjnOdNbbgFWUM6LRqPBkVSdzxi3WNk7Qqr3IvR-iu3MyMss0k-VJ69lshSwm_YWDaTscN9OL34MqOWT9bccp_9zHEqOVKXqDdwjHviBAQAA.f81e23dc`
    Paste it in-game (main menu → mod settings → BLANK the spire → Import), Import, Restart; "Coded Bolt"
    should appear in the reward pool (slot 02, since slot 01 holds Slot Test Blade).
- **P3 — Website:** generation UI + serverless endpoint (our key) emitting codes. Start as one page + one function.
- **P4 — Character bundles:** character slots (color/relic/deck/pool wiring per slot); codes carry whole classes.
- **P5 — Community:** optional hosted gallery, ratings, "character of the week"; art generation.

### 10.6 What still stays hard (honest)
- **Restart to load** new content (engine; framed as pre-game).
- **EA churn:** `sts2.dll` changes per patch → maintain the mod + keep the website's vocab/version in lockstep
  (the code's `vocabVersion` makes mismatches fail gracefully rather than crash).
- **Hosting cost / abuse** for the generate endpoint (stateless + rate-limited keeps it small).
- **Character slots** are more involved than card slots (per-slot color, starter relic, deck, pool).
- **Art:** placeholder frames + text until an image-gen step is added; long codes for big character bundles
  (acceptable; offer a file/short-link later).

### 10.7 Why this is the right shape
Player setup = the mod + a browser. We operate only a tiny stateless function; **sharing needs no storage**.
It's safe (data-only, re-validated), and it turns every generated character into a fun, paste-able code —
exactly the StS-seed-style sharing that makes it spread. The current dev-box forge (M5) remains the
**author/power-user** path; this is the **everyone** path.
