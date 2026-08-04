# Phase K — Forged Summons (custom, generated minions) — PLAN

Status: **✅ SHIPPED (Osty MVP) — reconciled 2026-06-27.** Forged summons shipped as the base-game Osty refit at
vocab **v15** (commit `ba1699e`); `class_forge.py` declares a `summon_pool` (ONE passive Osty-style minion + the
`summon`/`summon_attack`/`buff_summon` ops). K-3 custom summon mechanics are shelved / engine dormant — see
[[summon-true-osty-refit]] and `PHASE_K3_SUMMONER_ARCHETYPES_PLAN.md`. Original status preserved below.

ORIGINAL STATUS: **APPROVED 2026-06-18, not started.** The 4th "invent your own X" axis after orbs (Phase I = elements),
triggers (H3 = engines), statuses (Phase J = signature buffs/debuffs). User request: summons "like Osty, but
possibly with custom game mechanics." Decisions locked: **tiered scope** (Osty-like MVP first, custom mechanics as
K-3) and **borrow an existing creature** for placeholder visuals. See [[creative-harness-vision]] for the surrounding
harness, [[sts2-mod-toolchain]] for build.

## Feasibility — CONFIRMED (BaseLib source + sts2.dll reflect dump, 2026-06-18)
- **`BaseLib.Abstracts.CustomPetModel(bool visibleHp) : CustomMonsterModel`** auto-registers in its ctor
  (`CustomContentDictionary.RegisterType`), like `CustomOrbModel`/`CustomPowerModel` — no MainFile change. Provides a
  default do-nothing move machine; a real minion overrides `GenerateMoveStateMachine()`.
- **`BaseLib.Monsters.MoveBuilder`** = fluent move authoring, a near-perfect restricted sub-vocab: `.Attack(dmg,
  hitCount)`, `.Block(amt)`, `.ApplyToPlayers<T>(amt, strong)`, `.ApplyToSelf<T>(amt)`, `.HealSelf(amt)`,
  `.FollowingState(id)`, `.Build()` → `MoveState`; auto-attaches the right intent icon. `BaseLib.Utils.MonsterActions`
  wraps the raw cmds.
- **Spawn:** `CreatureCmd.Add(MonsterModel, CombatState, CombatSide, slotName)` (general) and
  `OstyCmd.Summon(ctx, summoner, amount, source)` (Osty-specific). `Creature` exposes `IsPet`/`PetOwner`/`Pets`;
  `MinionPower` tags a minion; `MonsterMoveStateMachine([states], start)` drives its turn.
- **Godot `.pck` pipeline now exists in-repo** (`mod/.godot/.../BlankTheSpire.pck`) — lowers the visuals risk (can
  ship a scene if borrowing an existing monster's `.tscn` proves insufficient).

## Constraint (same Q1/Q2 as everything else)
One minion = one compiled `.NET` Type, frozen at init → forged minions are **data-driven shells**: a fixed pool of
generic `CustomPetModel` subclasses each reading a `SummonSpec` from class JSON, exactly like `ForgedOrb` /
`ForgedStatusPower` / `ForgedCardSlotNN`. Mirrors Phase I/J wholesale.

---

## K-0 — SPIKE FIRST (de-risk before any generic infra)
Two genuinely-new risks: (a) does a custom `CustomPetModel` land player-side, take its turn, and attack; (b) does it
render without the missing-art NRE (Phase I orb bug #1 precedent). One throwaway hardcoded pet, like the orb-HUD and
custom-status spikes.

**Deliverable:** hardcoded `SpikeImp : CustomPetModel` + execution-only card op `summon_spike` (threaded through
`EffectRunner`/`DataCard`/`ForgedCards`, NOT in the LLM contract), driven from a staged throwaway card.

**Must answer:**
1. **Spawn + side** — which call makes a player pet (`CreatureCmd.Add(model, combatState, <player CombatSide>,
   slotName)` + `MinionPower`, or wrap `OstyCmd.Summon`?); confirm `Player.Pets`/`IsPet`/`PetOwner` set + persists.
   Read the player-ally `CombatSide` off `Player.Creature.Side`/`CombatState.CurrentSide`.
2. **Turn-taking** — pet `TakeTurn()` runs its move machine (attack N) + picks an enemy target (moves receive
   `IReadOnlyList<Creature> targets`; confirm via `PrepareForNextTurn(targets, rollNewMove)`).
3. **Visuals (art fork)** — point `CustomVisualPath` at an existing monster `.tscn`; confirm no
   `CreateVisuals`/`VisualsPath` NRE. Else author one placeholder scene via the `.pck` pipeline. **Pick the winner**
   so K-1 is built against a proven path.
4. **Death/cleanup** — pet clears at combat end + `MinionPower` owner-death without a soft-lock (cf. merchant/boss
   hangs).

Verify in-game (dev console `card BLANKTHESPIRE-…` → play → end turns → pet attacks), `godot.log` clean.
**Gate:** no K-1 until the spike summons, fights, and renders.

---

## K-1 — ENGINE (generic, data-driven; execution-path only, NOT yet in the LLM contract)
Mirror `Engine/OrbSpec.cs` + `Powers/ForgedOrb.cs` + `Engine/OrbRunner.cs` + the `ForgedCharacters` orb-pool parser.

**New files:**
- `Engine/SummonSpec.cs` — `SummonSpec { Name; Description; int MaxHp; SummonMove[] Moves }`;
  `SummonMove { string Intent; SummonAction[] Actions }` (move-cycle entry, states chain in order, loop to first via
  `FollowingState`); `SummonAction { Op; Amount; Hits; Status?; Target }` (maps 1:1 to a `MoveBuilder` call).
- `Powers/ForgedSummon.cs` — `abstract ForgedSummon : CustomPetModel` (the `ForgedOrb` analogue): abstract
  `SummonClass`/`SummonIndex` (set by shell); `Source => ForgedCharacters.SummonSpecFor(k, m)`; static `(k,m)->instance`
  registry → `TypeForKey(k, m)`. Overrides `MaxHp`, `IsHealthBarVisible => true`, `CustomVisualPath`/SFX (borrowed
  path from K-0), `Localization` (confirm the monster loc type at build), `GenerateMoveStateMachine()` →
  `SummonRunner.BuildMachine(Source, this)`. Null `Source` → BaseLib default do-nothing machine (harmless).
- `Engine/SummonRunner.cs` — `BuildMachine(SummonSpec, ForgedSummon)`: each `SummonMove` → `MoveState` via
  `MoveBuilder`, chained with `.FollowingState`, → `MonsterMoveStateMachine`. Plus `Describe(SummonSpec)`. Status `T`
  via the same `EffectRunner.SelfBuffStatuses` + the orb status registry (`OrbEnemyStatuses` =
  vulnerable/weak/frail/poison). **MVP op sub-vocab:** `attack`(dmg,hits), `block`, `apply_status`(self-buff→
  ApplyToSelf / debuff→ApplyToPlayers), `heal_self`. No orb/forged-status/trigger composition yet (K-3).
- `Engine/IForgedSummonHost.cs` — `int SummonClass { get; }` (the `IForgedOrbHost` analogue).

**Edited (established touch-set):** `CharacterSpec.cs` (+`SummonPool` init prop, NOT positional);
`ForgedCharacters.cs` (parse `summon_pool` ≤ `MaxSummons`, mirror `TryParseOrbPool`/`TryParseStatusPool`; add
`IsSummonClass`/`SummonSpecFor`/`ResolveSummonType`; accept `summon` on class cards); `CardSpec.cs`
(`EffectSpec += SummonName`); `EffectRunner.cs` (op **`summon`**: class-host resolve like `channel_orb` ~L99-113 →
spawn `Amount` via the K-0-proven call; non-class/unknown → warn+no-op); `DataCard.cs` (`case "summon": break;`);
`ForgedCards.cs` (parse `summon`/`summon_name`, validate class-only, Describe "Summon a <Name>.", `VocabVersion 10→11`);
`slotgen.py` (`SUMMONS_PER_CLASS`; emit `ForgedClass{k:02}Summon{m} : ForgedSummon` shells + `IForgedSummonHost`/
`SummonClass=>k` on class card leaves; update `n_types`; regen `ForgedClasses.g.cs`).

Build via toolchain; stage a test class (`generation/scratch/stage_phase_k_summons.py`, back up the overwritten slot)
with a `summon_pool` of 1–2 minions + cards that summon them. **In-game verify:** pick class → summon card → minion
appears player-side, shows intent, acts on its turn, clears at combat end; `godot.log` clean.

---

## K-2 — OPEN `summon_pool` TO THE LLM GENERATOR (generation-side; one small C# lockstep rebuild for Describe)
Mirror I-2 / J-2: `card.schema.json` (`summon` op + `summon_name` + `$defs/summonMove` restricting the sub-vocab);
`VOCABULARY.md` (op row + "Summons (CLASS IDENTITY — summon-class cards only)" section); `cardgen.py`
(`effect_literal` + describe mirror, **lockstep == `ForgedCards.Describe`**); `validator.py`
(`CardValidator(extra_summons=…)`; `summon` ∈ `_BUILD_AROUND_OPS` + structural membership/sub-vocab check);
`bts1.py` `VOCAB_VERSION 10→11`; `class_forge.py` ("THE SUMMON POOL" blueprint + `_validate_summon_pool` mirror +
`_summon_pool_custom_names` + `_card_uses_summons` drop-safety + assemble + offline fake/`_CardFake` summon branch;
mind the f-string brace gotcha). Validate via `uv run python -m tests.<mod>`; fake+real forge 0-skip at v11; user
in-game verify; then **website redeploy** (scp `generation/btsgen`+`mod/contract` → DO droplet `/opt/btsweb` →
`systemctl restart btsweb`, v10→v11; outward-facing — confirm first).

---

## K-3 — CUSTOM GAME MECHANICS (deferred follow-up; the "possibly with custom mechanics" ask)
Each a separate smaller phase, gated on prior in-game verify:
- **`on_summon`/`on_death` payloads** (death via `MinionPower` hooks or `Creature.Died`).
- **Apply the class's FORGED status** — minion `apply_status` reaches the class `status_pool` (Phase J): cross-axis composition.
- **Orb/status synergy & scaling** — minion numbers scaling with Focus/orb count/a forged status; a minion that channels an orb.
- **Sacrifice/consume** — cards that consume a summon for a payoff (the slot-machine-style composition vision).

---

## Risks & mitigations
- **Visuals (highest):** custom creatures need `NCreatureVisuals`+animator; missing art NRE's (`CreateVisuals`/
  `VisualsPath` Harmony-patched). → K-0 picks borrow-vs-author first; `.pck` fallback; real art → `ASSETS_TODO.md`.
- **Player-side spawn correctness:** general `CreatureCmd.Add(…, side, …)` for a player pet unproven (Osty uses its
  own cmd). → K-0 nails the exact call + `CombatSide` first.
- **Soft-lock family:** new combat entities have hung before (merchant, boss-reward). → K-0 tests combat-end/owner-
  death cleanup; AutoSlay smoke gate later.
- **Lockstep drift:** C#/Python describe mirror must stay byte-identical → K-2 verifies it.

## Verification (per step)
- **K-0:** dev console summons the spike imp; it fights + renders; clean log; cleanup OK.
- **K-1:** staged test class; summon card → minion fights on its turn, clears at end; no crash/hang.
- **K-2:** generation tests pass; fake+real 0-skip at v11; in-game forged summoner; website v10→v11.
