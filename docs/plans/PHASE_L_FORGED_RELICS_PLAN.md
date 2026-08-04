# Phase L — Forged Relics (custom, generated starter relics) — PLAN

Status: **✅ LARGELY SHIPPED (L-1…L-4 + compose) — reconciled 2026-06-27.** Forged relics are live: L-1 runtime +
L-2 generation + L-3 reactive hooks (`attacked`/`on_exhaust`/`first_attack`/`on_card_played`/`cost_reduction`) + L-4
relic vocab batch (`combat_end`, conditions, `start_combat_block`) + compose ops (relic `channel_orb`/`summon`) are all
committed (`b5a14b6`, `476caae`, `2362a0b`, `4cbc132`, `56d6eca`, `adb3adf`, `6835f37`) and folded into the AutoSlay
smoke gate (`cd3f784`). STILL OPEN: a RELIC-side `on_hp_lost` hook for a true bleed keystone relic (VOCABULARY_GAPS #9 —
cards done, relic side open). Original status preserved below.

ORIGINAL STATUS: **PROPOSED 2026-06-19, not started.** The 5th "invent your own X" axis after orbs (Phase I), statuses
(Phase J), summons (Phase K). Motivated by the creative-harness rework: the staged front-end's stage-5 output
is a **keystone starter relic** that today is design-intent only (see [[creative-harness-rework]]). Goal: make a
forged class's keystone relic actually PLAYABLE. Build: [[sts2-mod-toolchain]]. Gap analysis: [[relic-creation-gap]].

## Current state — an ASYMMETRY (investigated 2026-06-19)
The generator already knows how to design data-driven relics; the mod can't run them. That shapes the whole phase.

- **Generator (Python) — ~DONE but mis-pointed.** `generation/btsgen/relic_{contract,pipeline,validator}.py`
  model a relic as fully data-driven: `hooks` (trigger → effects from the SAME closed card vocab) + `modifiers`
  (passive stat bonuses), with authored few-shot exemplars (Burning Blood, Vajra, Anchor, …). BUT it targets the
  **prototype** vocab/paths (`slap-the-spoor-(test)/docs/RELIC_VOCABULARY.md`,
  `…/core/validation/schema/relic.schema.json`) for an Ironclad Str/Block character — NOT `mod/contract`. And
  `class_forge.py` deliberately skips relic generation; `point_btsgen_at_mod_contract()` repoints only CARD paths.
- **Mod (C#) — the REAL gap: no relic runtime.** Relics are hand-coded classes
  (`mod/.../Relics/BlankTheSpireRelic.cs : CustomRelicModel`). There is **no data-driven interpreter** — no
  "RelicRunner" analogous to `EffectRunner` for cards. All 4 forged class slots hardcode
  `StartingRelics => [ ModelDb.Relic<BurningBlood>() ]` (placeholder = Ironclad's relic) in the generated
  `Cards/Forged/ForgedClasses.g.cs`. The `BTSC` bundle reserves an optional `relic` field
  (`{kind, character, cards[], relic?}`), but nothing parses it into a live relic.

**So this phase is mostly C# RUNTIME work** (the inverse of Phases I/J/K, where the engine pieces were small and
the generator lift was the bulk). The Python side is largely a port + repoint.

## Constraint (same Q1/Q2 as everything else)
One relic = one compiled `.NET` Type, frozen at init → forged relics are **data-driven shells**: a fixed pool of
generic `ForgedRelic : BlankTheSpireRelic` subclasses, one per class slot, each reading a `RelicSpec` from class
JSON — exactly like `ForgedOrb` / `ForgedStatusPower` / `ForgedSummon` / `ForgedCardSlotNN`. One starter relic per
class (4 shells: `ForgedClass01Relic`..`04`).

## The v1 vocabulary (constrained subset of the prototype's, aligned to the mod's v2 card ops)
Port the prototype relic design, trimmed to what the mod's runtime + v2 card vocab actually support:
- **Triggers (v1):** `combat_start`, `turn_start`, `turn_end`, `combat_end` — the "scheduled/passive" hooks that
  map cleanly to relic lifecycle methods. **Defer** `attacked` (reactive damage hook) to L-3.
- **Conditions:** `always`, `victory`, `defeat`, `hp_below_half`; plus `once_per_combat`.
- **`target` override:** `self` / `enemy` / `all_enemies` (default per trigger, like the prototype).
- **Effects:** the mod's **v2 card ops** in a no-card context — `damage` (with `raw:true` for unscaled relic
  damage; target enemy/all_enemies), `block`, `draw`, `gain_energy`, `heal`, `lose_hp`, `apply_status`
  (buffs→self, debuffs→target). Reuses the `add_trigger` payload executor (self/raw) **plus a resolved target**.
- **Modifiers (v1):** `max_energy` (Energy Core). **Defer** `attack_base`/`first_attack` (Akabeko) to L-3 (no
  clean v2 hook yet).

This keeps relics expressible from the SAME closed vocabulary cards use — the golden rule. New triggers/ops are
human-added (the standard gate), and what the keystones need but this lacks goes to `VOCABULARY_GAPS.md` (below).

---

## L-0 — SPIKE FIRST (de-risk the runtime before any generic infra)

### What reflection ALREADY confirmed (2026-06-19) — the spike is now "confirm + measure", not "discover"
Verified from BaseLib source + `_modref/reflect/dump.txt`:
- **Registration is automatic.** `BaseLib.Abstracts.CustomRelicModel(bool autoAdd=true) : RelicModel` calls
  `CustomContentDictionary.AddModel(GetType())` in its ctor — exactly like `CustomOrb/Pet/PowerModel`. The mod's
  `BlankTheSpireRelic` already extends it. So a `ForgedRelic : BlankTheSpireRelic` self-registers; no MainFile edit.
- **The trigger hooks live on `AbstractModel`** (`dump.txt` §11), and `RelicModel : AbstractModel` (dump line 911)
  — the SAME base that gives `PowerModel` its hooks. So a relic overrides the *identical* methods the mod's
  `ForgedTriggerPower` already overrides for card `add_trigger`. **The relic runtime is the trigger-power pattern
  re-pointed at a `RelicModel`.** Confirmed trigger→hook mapping for the v1 set:

  | relic `trigger`         | AbstractModel hook (override)                                          | ctx/player access |
  |-------------------------|------------------------------------------------------------------------|-------------------|
  | `turn_start`            | `AfterPlayerTurnStart(PlayerChoiceContext ctx, Player player)`         | **handed in** (easy) |
  | `turn_end`              | `AfterSideTurnEnd(ctx, CombatSide side, IEnumerable<Creature>)` ¹      | **handed in** (easy) |
  | `combat_start`          | `BeforeCombatStart()` / `BeforeCombatStartLate()`                      | **none passed — must reach player via a global (the open Q)** |
  | `combat_end` + victory  | `AfterCombatVictory(CombatRoom room)` (or `AfterCombatEnd`)            | via `room` |
  | `attacked` (L-3)        | `AfterDamageReceived(ctx, target, DamageResult, …, Creature dealer, …)`| dealer = attacker |

  ¹ The mod's `ForgedTriggerPower` currently compiles against `AfterSideTurnEnd`; the dump also lists
  `AfterTurnEnd(ctx, side)` — a known version rename ([[sts2-game-update-port]]). **Mirror ForgedTriggerPower's
  signature** (it builds today) and note which is live.
- **No-card effect execution already exists:** `ForgedTriggerPower` runs its payload via
  `TriggerRunner.Run(EffectSpec, Player, PlayerChoiceContext)` — no card. The spike reuses it directly for
  self-effects (block/draw/buff). Enemy-facing relic `damage` needs a target, which `TriggerRunner` doesn't pass.
- **Modifiers are clean overrides, not combat-start hacks:** `ModifyEnergyGain(Player, Decimal)` (→ `max_energy`)
  and `ModifyDamageAdditive(…)` (→ `attack_base`) are overridable on `AbstractModel`. v1 ships `max_energy`.
- **Reactive-hook names for L-3 are confirmed too:** `AfterCardPlayed`, `AfterCardExhausted`, `AfterCardRetained`,
  `AfterCardDrawn` all exist (`decl=AbstractModel`) — so the deferred keystones (Watering Can / Compost Bin /
  Padawan's Patience) have real landing spots; log them in `VOCABULARY_GAPS.md` with these target hooks.

### What the spike must still establish EMPIRICALLY (compile + run — the genuine unknowns)
1. **Do these overrides actually FIRE on an owned relic?** Powers are applied to a `Creature` (they have `Owner`);
   a relic is owned by the run, not a creature. Confirm `AbstractModel`'s hooks are dispatched to equipped relics
   (they should be — base-game relics use them — but verify our `ForgedRelic` instance receives them).
2. **`combat_start` ctx access** — `BeforeCombatStart()` passes no `PlayerChoiceContext`/`Player`. Find how a relic
   reaches the current player + ctx inside it (a `CombatState.Current`-style global, or defer combat_start effects
   to `AfterPlayerTurnStart`+`once_per_combat` the way the prototype's Lantern does). **Resolve which.**
3. **Targeted relic damage** — prove one enemy-facing `damage` (raw, unscaled) from a relic hook by resolving
   "first alive enemy" and calling the same `DamageCmd` raw path cards use — the seed of L-1's
   `EffectRunner.RunRelicEffects(effects, ctx, target)`.
4. **Per-class binding** — confirm `StartingRelics => [ ModelDb.Relic<SpikeRelic>() ]` on a forged class slot grants
   it on character select and persists into combat (temporarily hand-edit one slot in `ForgedClasses.g.cs`).
5. **Missing-art behavior** — `PackedIconPath` derives a png from the relic Id; a forged relic has none. Confirm the
   failure mode and pick a shared **fallback icon** (mirror the orb/summon visual fallback). → `ASSETS_TODO.md`
   ([[assets-todo]]).
6. **No soft-lock** — a `turn_end`/`combat_end`/last-enemy-kill hook must not hang (merchant/boss-reward family,
   [[boss-reward-rarity-hang]]); test the end-of-combat path.

### Deliverable (one throwaway file + one temp binding)
`Relics/SpikeRelic.cs` — hardcoded, NO generic infra (scaffolded 2026-06-19, compile-ready):
```csharp
public sealed class SpikeRelic : BlankTheSpireRelic   // auto-registers via the ctor chain
{
    public override string PackedIconPath => "forged_relic_fallback.png".RelicImagePath(); // fallback-icon test

    // turn_start: prove the easy path (ctx handed in) — draw 1 via the existing no-card runner
    public override async Task AfterPlayerTurnStart(PlayerChoiceContext ctx, Player player)
        => await TriggerRunner.Run(new EffectSpec { Op = "draw", Amount = 1 }, player, ctx);

    // turn_end: prove targeted raw damage (the RunRelicEffects seed) — 3 to first alive enemy
    public override async Task AfterSideTurnEnd(PlayerChoiceContext ctx, CombatSide side, IEnumerable<Creature> ps)
    {
        if (side != /* player side */) return;
        // resolve first alive enemy + deal 3 raw via the card DamageCmd raw path (unknown #3)
    }

    // combat_start: discover ctx/player access (unknown #2) — gain 6 Block, or defer to turn 1 once_per_combat
    public override async Task BeforeCombatStart() { /* reach player+ctx, then block 6 */ }

    public override Decimal ModifyEnergyGain(Player player, Decimal amount) => amount + 1; // modifier test
}
```
Temporarily set class slot 01's `StartingRelics => [ ModelDb.Relic<SpikeRelic>() ]` (back up `ForgedClasses.g.cs`).

**Verify in-game:** select class 01 → SpikeRelic shows in the relic bar with the fallback icon → +1 energy/turn,
draw at turn start, 3 dmg to an enemy at turn end, 6 block at combat start; kill last enemy via the turn-end tick →
no hang; `godot.log` clean. **Gate:** no L-1 until the spike fires (all hooks), binds, renders, and doesn't hang.

### ✅ SPIKE RESULT — RUN 2026-06-19 (built + AutoSlay-driven, pinned to forged slot 01)
**PASS — the relic runtime is proven.** Built clean (the only fix vs. the scaffold: `RelicModel` has one abstract
member, `Rarity` (`MegaCrit.Sts2.Core.Entities.Relics.RelicRarity`) → `=> RelicRarity.Starter`). AutoSlay played a
full pinned run; `godot.log` shows the hooks firing **every turn across ~14 combats**, no relic exception anywhere:
- **Unknown #1 — DO hooks fire on an equipped relic? YES.** `BeforeCombatStart`, `AfterPlayerTurnStart`, and
  `AfterSideTurnEnd` all fired reliably. **`ShouldReceiveCombatHooks => true` was REQUIRED** (relics don't get
  combat hooks without it) — the key finding.
- **No-card effect execution + targeted damage (unknown #3): WORKS.** Self block/draw + 3-dmg-to-first-enemy ran
  every turn with zero exceptions; `Creature.Player` recovers the player inside `AfterSideTurnEnd`.
- **`max_energy` via `ModifyEnergyGain`, fallback icon (`relic.png`), no soft-lock from hooks: all good.** The run's
  end ("main menu did not appear after game over") is the **known** BaseLib/AutoSlay end-screen breakage
  ([[sts2-game-update-port]]), NOT relic-related — no `SpikeRelic` frame in any stack trace.
- **Unknown #2 — reach player+ctx in `BeforeCombatStart()`: STILL OPEN.** It fires but passes neither.
  **L-1 decision:** either find a player/ctx global usable there, OR (recommended, lower-risk) **drop `combat_start`
  from v1 and express those effects as a `turn_start` + `once_per_combat` hook** (the prototype's Lantern pattern) —
  turn_start hands you `(ctx, player)` cleanly. This is the one thing to settle when building L-1.

Spike artifacts: `Relics/SpikeRelic.cs` (kept as the working reference L-1 generalizes; now INERT — binding restored
to BurningBlood). Safe to delete anytime.

---

## L-1 — ENGINE (generic, data-driven; runtime only, NOT yet generated)
Mirror the `OrbSpec`/`ForgedOrb`/`OrbRunner` + `ForgedCharacters` parser shape.

**New files:**
- `Engine/RelicSpec.cs` — `RelicSpec { Id; Name; Description; Tier; Pool; RelicHook[] Hooks; RelicModifier[]
  Modifiers }`; `RelicHook { Trigger; Condition[]; Target?; bool OncePerCombat; EffectSpec[] Effects }` (reuse the
  existing `EffectSpec`); `RelicModifier { Stat; Amount; When }`.
- `Engine/RelicRunner.cs` — `Fire(RelicSpec, trigger, ICombatState, ForgedRelic)`: filter hooks by trigger,
  check conditions + `once_per_combat` (per-combat flag set on the ForgedRelic), resolve the target (default per
  trigger / `target` override; `all_enemies` loops), then `EffectRunner.RunRelicEffects(effects, ctx, target)`
  (the L-0-proven entry point). Plus `ApplyModifiers(RelicSpec)` for `max_energy`, and `Describe(RelicSpec)`
  (lockstep with the Python describe).
- `Powers/ForgedRelic.cs` — `abstract ForgedRelic : BlankTheSpireRelic` (the `ForgedOrb` analogue): abstract
  `RelicClass` (set by shell); `Source => ForgedCharacters.RelicSpecFor(RelicClass)`; override the L-0-confirmed
  lifecycle hooks → `RelicRunner.Fire(Source, <trigger>, …)`; `PackedIconPath` → fallback icon when no art; null
  `Source` → inert (harmless, e.g. a class with no forged relic falls back to a default).

**Edited (established touch-set):** `CharacterSpec.cs` (+`Relic` init prop — a single `RelicSpec`, not a pool);
`ForgedCharacters.cs` (parse the bundle `relic` ≤ one, mirror `TryParseOrbPool` discipline into
`TryParseRelic`/`_validate`; add `HasForgedRelic`/`RelicSpecFor(classIdx)`; **re-validate `relic` on import** like
cards); `EffectRunner.cs` (the `RunRelicEffects` entry point from L-0 — accepts effects + ctx + a resolved
target, no card; reuses op switch); `slotgen.py` (emit one `ForgedClass{k:02}Relic : ForgedRelic` shell per class
with `RelicClass => k`; replace the hardcoded `StartingRelics => [BurningBlood]` with
`StartingRelics => [ ForgedCharacters.HasForgedRelic(k) ? ModelDb.Relic<ForgedClass{k:02}Relic>() : <default> ]`;
regen `ForgedClasses.g.cs`).

Stage a test class (`generation/scratch/stage_phase_l_relic.py`, back up the overwritten slot) with a hand-written
`relic` spec exercising each v1 trigger + the `max_energy` modifier. **In-game verify:** pick class → the relic's
turn hooks fire, the modifier applies; clears/persists correctly; `godot.log` clean.

### ✅ L-1 RESULT — BUILT + VERIFIED 2026-06-19
**DONE — the data-driven forged-relic runtime works end-to-end.** Built clean on the first attempt (all patterns
mirrored Phase J/K). v1 ships **turn_start + turn_end** triggers only (combat_start dropped per the L-0 decision;
its one-shot effects use `once_per_combat`, reset in the arg-less `BeforeCombatStart`). Files:
- NEW: `Engine/RelicSpec.cs` (`RelicSpec`/`RelicHook`/`RelicModifier`), `Engine/RelicRunner.cs` (hook dispatch +
  condition/once-per-combat gating + target resolution), `Powers/ForgedRelic.cs` (abstract shell base:
  `ShouldReceiveCombatHooks => Source != null`, `Rarity => Starter`, icon fallback, turn-hook overrides,
  `ModifyEnergyGain` for `max_energy`).
- EDITED: `EffectRunner.cs` (+`RunRelicEffects` — the no-card executor merging TriggerRunner's self path +
  SummonRunner's targeted path), `CharacterSpec.cs` (+`Relic`), `ForgedCharacters.cs` (`TryParseRelic`/
  `TryParseRelicHook`/`TryParseRelicEffect`/`TryParseRelicCondition`, `RelicSpecFor`/`HasForgedRelic`, `MaxRelics`,
  parse in `TryValidateCharacterDict`, fold top-level bundle `relic` into the character dict on import),
  `slotgen.py` (+`ForgedClass{k:02}Relic` shells + conditional `StartingRelics`).
- Verified via an AutoSlay run pinned to forged slot 01 ("The Swarmlord") carrying a staged "Brood Catalyst" relic.
  `godot.log` (with a temporary diagnostic, since removed) showed across ~14 combats: `turn_start once=True` firing
  **exactly once per combat** (once-per-combat + BeforeCombatStart reset both work); `turn_start once=False` (block)
  every turn; `turn_end target=enemy` (3 dmg) every turn-end with correct target resolution; the `hp_below_half`
  conditional heal correctly **gated off** while HP was healthy; `max_energy` modifier applied; **zero relic
  exceptions**. SpikeRelic.cs deleted (superseded). NOT yet in the LLM contract — that's L-2.

---

## L-2 — OPEN relic generation to the LLM + WIRE INTO THE CLASS BUNDLE (generation-side)
Mirror I-2 / J-2 / K-2.
- **Port the contract into `mod/contract/`:** create `mod/contract/RELIC_VOCABULARY.md` + `relic.schema.json` as
  the **constrained v1 subset** (triggers minus `attacked`; v2 card ops only; `max_energy` modifier). Trim the
  prototype's extra ops (`add_card`/`multi`/`from_state`/`conditional`/`set_flag`) and `attack_base` — they aren't
  in the mod's v2 vocab/runtime yet.
- **Repoint btsgen:** extend `point_btsgen_at_mod_contract()` with `BTSGEN_RELIC_SCHEMA` / `BTSGEN_RELIC_VOCABULARY`
  / relic exemplars dir → the mod contract; point `relic_pipeline`/`relic_validator` at them.
- **Wire the relic stage into `class_forge.py`:** add a relic-generation call (tier `starter`, pool `starter`,
  context = the chosen class identity / keystone) → insert into the BTSC bundle's `relic` field. Reframe so the
  staged front-end's keystone (the dossier from [[creative-harness-rework]]) becomes the relic brief.
- **Lockstep + version:** `RelicValidator` must match `RelicRunner`'s supported triggers/conditions/ops/modifiers
  EXACTLY (the 7-place discipline); C#↔Python `Describe` byte-identical; `bts1.py` + `ForgedCards` version bump
  (add a relic-spec version check on import); `--fake` relic branch for offline.
- **Website redeploy** (outward-facing — confirm first): scp `generation/btsgen` + `mod/contract` → droplet
  `/opt/btsweb`, `systemctl restart btsweb`.

**Verify:** generation tests pass; fake + real forge produce a schema-valid starter relic with 0 skips; in-game a
forged class boots with its OWN generated relic (not Burning Blood) and it plays correctly; AutoSlay smoke gate
(a per-turn relic hook can crash/hang like a card — fold relics into the smoke run).

### ✅ L-2 RESULT — BUILT + VERIFIED 2026-06-19
**DONE — the generator now emits forged keystone relics into the class bundle.** Followed `class_forge.py`'s lean
philosophy (NOT the prototype `relic_pipeline`): a constrained, mod-aligned relic stage lives in `class_forge`.
- NEW `mod/contract/RELIC_VOCABULARY.md` — the v1 relic contract (turn_start/turn_end, the no-card effect ops,
  buffs/debuffs, target, `when` hp_below_half/no_block, once_per_combat, max_energy modifier). Read by the LLM
  prompt + the human/lockstep reference.
- `class_forge.py`: `_RelicContract` (system_prompt from the vocab + the class identity as the brief),
  `_validate_relic` (MIRRORS the C# `TryParseRelic` gate — the lockstep), `_fake_relic`, and a non-fatal
  **stage 2.5** in `forge_class` (one LLM call, repair-once; on failure the class still ships → Burning Blood).
  Relic rides the BTSC bundle as a top-level `relic` sibling (the C# importer folds it into the char dict — added
  in L-1). `cli_forge_class.py` builds a `relic_gen` (fake/BYOK/Anthropic) and passes it.
- **Verified:** `--fake` forge → bundle keys `[cards, character, kind, relic]`, relic `_validate_relic` = **0 errors**;
  BTSC decode confirms the relic round-trips. The LLM contract was exercised via a stand-in model on the "Blade
  Adept" identity → produced "Stillblade" (max_energy +1; a `no_block`-gated turn_start draw+Dexterity that rewards
  the coil loop), which validates clean. No test regression (the 21 suite errors are a pre-existing `fixture 'v'`
  issue in untouched prototype tests). The L-1 runtime already proved generated-shape relics execute in-game; the
  import fold-in is the L-1-verified parse path. **NOT YET REDEPLOYED to the website** (outward-facing — see below).

### Remaining for L-2 (outward-facing, do when ready)
- **Website redeploy** (the plan's last bullet): scp `generation/btsgen` + `mod/contract` → droplet `/opt/btsweb`,
  `systemctl restart btsweb`. Outward-facing — confirm before doing. Until then the live site forges classes
  WITHOUT the keystone relic (they default to Burning Blood, which is harmless).
- **AutoSlay smoke over a generated class WITH its relic** (full import round-trip) — optional extra confidence;
  L-1 already exercised the runtime hooks live.

---

## L-3 — REACTIVE HOOKS & MODIFIERS (deferred; where the flashy keystones live)
The dry-run keystones need hooks v1 deliberately omits — track them in `VOCABULARY_GAPS.md` (relic-hook gaps
mirror card-op gaps: a keystone surfaces a missing hook just like a card identity surfaces a missing op):
- **`attacked`** (Thorns/Bronze-Scales reactive damage) — needs the take-damage hook from L-0 Q1. ✅ **BUILT +
  AutoSlay-VERIFIED 2026-06-19** (fired 23× with attacker resolved; see batched-verify block).
- **`on_card_played`** — "Watering Can" (first Power each turn costs less), "Padawan's Patience" (first card costs
  0). Needs a card-played relic hook + a **cost-reduction** primitive (new). ✅ **BUILT + AutoSlay-VERIFIED
  2026-06-19** (trigger fired 23×; cost_reduction modifier confirmed lowering energy cost). Card-TYPE filter
  (Power-only etc.) deferred — see below.
- **`on_exhaust`** — "Compost Bin" (effects when a card Exhausts). Needs an exhaust hook. ✅ **BUILT +
  AutoSlay-VERIFIED 2026-06-19** (fired 7×).
- **`first_attack`** modifier (Akabeko) ✅ **BUILT + AutoSlay-VERIFIED 2026-06-19** (14 applications / 15 combats —
  once-per-combat reset confirmed). (`attack_base` = flat +N every attack deliberately
  NOT shipped — it's just always-on Strength; add later if wanted.) Per-relic **counters/periods** ("every 3rd
  attack") still deferred.

Each is a separate small follow-up, gated on in-game verify, added via the standard human-only vocabulary gate.

### ✅ L-3 `attacked` (reactive Thorns) — BUILT + BUILD-CLEAN 2026-06-19 (in-game verify PENDING)
**DONE in code — the reactive `attacked` trigger + `attacker` target ship end-to-end; NOT yet run in-game (AutoSlay
deferred at user request).** Lowest-risk reactive sub-item: a new trigger that reuses the existing no-card effect
ops (no new primitive). The L-0 reflection had already pinned the hook signature, so this was pure plumbing.
- **Runtime (C#):** `ForgedRelic.AfterDamageReceived(ctx, target, DamageResult, ValueProp, dealer, CardModel)` —
  fires `RelicRunner.Fire(Source, "attacked", …, attacker: dealer)` ONLY when the damaged creature is our player
  (`target.Player != null`) and the dealer is an enemy (`dealer.Player == null`), so self-cost damage (lose_hp) and
  our own retaliation (which lands on an enemy) never re-trigger it — no recursion. `RelicRunner.Fire` gained an
  optional `Creature? attacker`; `ResolveTargets` gained the `attacker` case (the dealer, if alive). `RelicSpec`
  docs updated. **Namespaces confirmed by the build:** `DamageResult` ∈ `Core.Combat`, `ValueProp` ∈
  `Core.ValueProps`, `CardModel` ∈ `Core.Models` (the only build error — initially guessed `Core.Entities.Cards`).
- **Parser/validator (C#):** `RelicTriggers += "attacked"`, `RelicTargets += "attacker"`, plus a rule that
  `attacker` is valid only on the `attacked` trigger. Existing "damage/debuff need an enemy target" check already
  accepts `attacker` (it's non-self).
- **Lockstep (Python `class_forge._validate_relic`):** mirrored exactly — `_RELIC_TRIGGERS`/`_RELIC_TARGETS` +
  the attacker-requires-attacked rule. `_fake_relic` now emits an `attacked`/`attacker` retaliation hook so the
  offline path exercises it; `_validate_relic(_fake_relic(...)) == []`, and negative/positive spot-checks pass.
- **Contract:** `mod/contract/RELIC_VOCABULARY.md` adds the `attacked` trigger row (reactive, fires per hit —
  keep numbers small or gate with `once_per_combat`), the `attacker` target, and a top-example hook.
- **Lockstep sites touched (the only ones for the mod path):** `RelicSpec.cs`, `RelicRunner.cs`, `ForgedRelic.cs`,
  `ForgedCharacters.cs`, `class_forge.py` (validator + fake), `RELIC_VOCABULARY.md`. `EffectRunner.RunRelicEffects`
  needed NO change (ops unchanged). The prototype `relic_validator.py`/`relic_contract.py` are NOT in the
  class_forge path (confirmed) — left untouched. **Mod builds clean (0 errors).**
- **Still TODO:** in-game verify (equip a forged class carrying an `attacked`/`attacker` relic, confirm it hits the
  attacker back on each enemy hit, `once_per_combat` caps a "first hit" variant, no soft-lock on a killing
  retaliation, clean `godot.log`); then fold into the AutoSlay smoke gate. No version bump needed (the bundle
  `relic` schema is a superset — old specs still validate; a spec USING `attacked` simply requires this build).

### ✅ L-3 `on_exhaust` + `first_attack` (Akabeko) — BUILT + BUILD-CLEAN 2026-06-19 (in-game verify PENDING, BATCHED)
**DONE in code; deferred AutoSlay so all three L-3 features (`attacked` + these two) verify in ONE run (user's call).**
Both reuse existing infra — no new effect primitive.
- **`on_exhaust` (reactive trigger):** `ForgedRelic.AfterCardExhausted(ctx, card, causedByEthereal)` →
  `RelicRunner.Fire(Source, "on_exhaust", …)`. Player recovered from `card.Owner` (dump confirms `CardModel.Owner`
  is a `Player`). No `attacker` context, so self/enemy/all_enemies targets only; relic ops never exhaust a card, so
  no self-trigger. Parser/Python: `"on_exhaust"` added to the trigger sets; `RelicRunner.Fire` needed NO change.
- **`first_attack` modifier (Akabeko):** `ForgedRelic.ModifyDamageAdditive(target, amount, props, dealer,
  cardSource)` adds the bonus to the FIRST player **card** attack each combat — gated to `dealer?.Player != null &&
  cardSource != null` (excludes thorns/poison/orb passives) and one-shot via a new `_firstAttackUsed` flag reset in
  `BeforeCombatStart` (alongside `_firedOnce`). Sync override (returns `decimal`, no await), mirrors the proven
  `ModifyEnergyGain` path. Stat `"first_attack"` added to `RelicModifierStats` (C# + Python). `attack_base`
  intentionally NOT shipped (it's just permanent Strength).
- **Lockstep + offline proof:** `_fake_relic` now also emits an `on_exhaust` block hook and a `first_attack: 3`
  modifier; `_validate_relic(_fake_relic(...)) == []`, and spot-checks pass (on_exhaust self/enemy ok; `attacker`
  still rejected off `attacked`; `first_attack` mod ok; `attack_base` rejected). `RELIC_VOCABULARY.md` gains the
  `on_exhaust` trigger row + the `first_attack` modifier row. **Mod builds clean (0 errors).**
### ✅✅ BATCHED IN-GAME VERIFY — AutoSlay run 2026-06-19 (seed L3PROVE, slot 01) — ALL THREE PASS
Staged slot 01 ("The Swarmlord") with an "L3 Proving Sigil" relic exercising all three at once (thorns `attacked`
+3 to attacker, `on_exhaust` +2 block, `first_attack` +5 modifier, +turn_start block) and made one starting card
`ethereal` so `on_exhaust` reliably fires. Added temp `[L3DIAG]` logging to `RelicRunner.Fire` + the `first_attack`
modifier (since removed — both files back to committed state). Run reached **Act 2 Floor 13 across 15 combats**:
- **`attacked` fired 23×** (`tgts=1`, attacker resolved every time — the Spiny Toad's multi-hit spike attack
  triggered thorns 8× in the final fight); **`on_exhaust` fired 7×**; **`turn_start` 28×**.
- **`first_attack`: 14 applications across 15 combats** → fires AT MOST once per combat — the `_firstAttackUsed`
  reset in `BeforeCombatStart` works (e.g. `+5 applied (6 -> 11)`, `(10 -> 15)`).
- **Zero relic/forged exceptions** anywhere. The only exceptions in `godot.log` are the pre-existing load-time
  BaseLib `RelicCollection.LoadRelics` HarmonyException ([[sts2-game-update-port]]) and the AutoSlay harness
  timeout machinery — none from our code.
- The run's `RunFailed` ("Rewards screen did not appear after combat") is a **legitimate player DEATH** on A2F13
  (the random player lost) that the AutoSlay harness can't gracefully end — SAME known limitation family as "main
  menu did not appear after game over" ([[autoslay-tool]]). NOT a relic soft-lock: the fail stack is 100%
  `AutoSlayer.WaitForRewardsScreenAsync`, no BlankTheSpire frame. **The relic runtime is clean.**

Cleanup done: `[L3DIAG]` diagnostics removed (RelicRunner.cs / ForgedRelic.cs back to committed state, rebuilt
clean), slot 01 restored to its prior "Brood Catalyst" relic. Stage helper: `scratch/stage_phase_l3_autoslay.py`
(gitignored). **Folding relics into the standing AutoSlay smoke gate** (so every smoke run carries a relic) remains
a nice-to-have, not done here.

### ✅ L-3 `on_card_played` trigger + `cost_reduction` modifier — BUILT + AutoSlay-VERIFIED 2026-06-19
**DONE & verified — the last L-3 item.** API mapped via the `_modref/reflect/` tool (the committed `dump.txt` is
filtered and lacked these members). **NOTE — the cost primitive was REWORKED after a verify run proved the first
attempt was a no-op:** the playable cost is a card's **energy** cost, and there is **no per-card temporary energy
mutation** — STS2's `Star*` cost machinery is a *separate, inactive* axis for these cards (`CurrentStarCost == -1`
sentinel). So a `reduce_cost` *effect op* (first attempt) silently did nothing. Cost-reduction is therefore a
**modifier**, via the same hook real relics use (`SpikedGauntlets`).
- **`on_card_played` trigger (VERIFIED, fired 23×):** `ForgedRelic.AfterCardPlayed(ctx, CardPlay cardPlay)` →
  `RelicRunner.Fire(Source, "on_card_played", …)`. Player from `cardPlay.Card.Owner`. Effects never play a card → no
  recursion. v1 fires on ANY card (no card-type filter — see deferral).
- **`cost_reduction` modifier (VERIFIED — `1→0`, `2→1` energy):** `ForgedRelic.TryModifyEnergyCostInCombat(card,
  originalCost, out modifiedCost)` returns `originalCost - N` (floored at 0) when the spec has a `cost_reduction`
  modifier. This is the engine's per-card energy-cost-query hook (decl=AbstractModel; used by `SpikedGauntlets`,
  `BorrowedTimePower`, …). Always-on while equipped — like `max_energy`/`first_attack`, it's a modifier, not an effect.
- **Lockstep:** `RelicTriggers += on_card_played`; `RelicModifierStats += cost_reduction` (C# + `class_forge`). The
  broken `reduce_cost` op was REMOVED from `RelicEffectOps` (now rejected by both validators). `_fake_relic` carries
  an `on_card_played` block hook + a `cost_reduction:1` modifier; `RELIC_VOCABULARY.md` updated (trigger row +
  modifier row; no `reduce_cost` op). **Mod builds clean (0 errors).**
- **Keystone now expressible:** "your cards cost 1 less" (`cost_reduction:1` modifier — a Mummified-Hand/Sundial
  tempo relic). Verified live: energy costs dropped `1→0` / `2→1` across the run; `on_card_played` fired 23×; the
  other L-3 hooks also fired (attacked 47×, turn_start 49×); zero relic exceptions. RunFailed = the harness
  death/rewards-screen limitation again, no BlankTheSpire frame.
- **DEFERRED (follow-up):** a **card-type filter** on `on_card_played` (Power-only "Watering Can"); `CardModel` has
  no clean public card-type accessor (only a `Nullable<CardType> _cardType` field). A **conditional/first-card-only**
  cost reduction (true "Padawan's Patience: first card costs 0") — the cost hook is a pure per-card query, so
  per-play gating needs extra state; flat reduction ships now. Also still deferred from L-3: `attack_base` flat
  modifier, per-relic counters/periods. Logged for the human gate.

---

## L-4 — VOCABULARY EXPANSION BATCH 1 ✅ BUILT + AutoSlay-VERIFIED 2026-06-19
User-chosen expansion ("what other dictionary items can we add"): iconic starters + more reactive triggers +
a conditions pack. Compose ops (relic `channel_orb`/`summon`) deliberately deferred to their own cycle.

**New triggers** (reactive, reuse existing effect ops):
- `combat_end` — fires on `AfterCombatVictory`; **heal-only** (no ctx/live enemies at victory; validator-enforced).
  Unlocks **Burning Blood** (heal after combat) — the very relic we hardcode as the fallback.
- `on_card_drawn` (`AfterCardDrawn`), `on_damage_dealt` (`AfterDamageGiven`; only YOUR card attacks — gated to
  `dealer.Player != null && cardSource != null`, which also breaks the loop), `on_block_gained` (`AfterBlockGained`).

**New conditions** (player-state reads in `Conditions.Eval`): `has_block`, `enemy_count_ge` (value),
`turn_at_least` (value, via `ICombatState.RoundNumber`), `hand_size_ge` (value, via `PlayerCombatState.Hand.Cards`).

**New modifier:** `start_combat_block` — gain N Block on turn 1 (no combat-start hook hands a player, so turn 1 is
earliest; functionally = Orichalcum/Anchor). Granted in `AfterPlayerTurnStart` before turn_start hooks.

**Re-entrancy guard (the load-bearing safety piece):** reactive hooks whose effect re-raises their own event
(`on_card_drawn`→`draw`, `on_block_gained`→`block`) would recurse forever. `ForgedRelic` now routes every trigger
through `FireGuarded`, which drops a re-entrant fire via a per-trigger `_firing` set. Also added `_combatPlayer` +
`_combatCtx` capture (the ctx-less hooks `combat_end`/`on_block_gained` reuse the last real ctx/player).

**API notes (via `_modref/reflect/`):** `AfterCombatVictory(CombatRoom)` — `CombatRoom` ∈ `MegaCrit.Sts2.Core.Rooms`;
`AfterDamageGiven(ctx, dealer, DamageResult, ValueProp, target, CardModel)`; `AfterBlockGained(Creature, decimal,
ValueProp, CardModel)`; `CombatState.RoundNumber`/`HittableEnemies`, `Creature.Block`, `PlayerCombatState.Hand.Cards`.

**Lockstep:** C# `RelicTriggers`/`RelicConditionKinds`/`RelicModifierStats` + `Conditions.{Kinds,Validate,Eval,Phrase}`
+ `class_forge` (`_RELIC_*` sets, `combat_end` heal-only, condition value checks); `_fake_relic` carries a
`combat_end` heal + `start_combat_block`; `RELIC_VOCABULARY.md` updated. **Mod builds clean (0 errors).**

**Verified — AutoSlay run (seed L4BATCH, slot 01) carrying a relic that exercises EVERYTHING incl. a deliberate
`on_block_gained`→block loop test:** the forged class survived **27 combats across all 3 acts to the final boss +
the Architect win event**. All L-4 triggers fired (combat_end/on_block_gained/on_card_drawn 27×, on_damage_dealt
26×, start_combat_block 27×); **the re-entrancy guard HELD (no hang)**; **zero relic exceptions**. The lone NRE is
the game's OWN `Events.TheArchitect.WinRun()` (the ending event — a modded-run edge case, no BlankTheSpire frame),
and the RunFailed is the known harness death/"main menu" limitation ([[autoslay-tool]]). Diagnostics removed, slot
restored. **Still deferred:** card-type filter on card triggers; the compose ops (`channel_orb`/`summon`);
`attack_base`; per-relic counters/periods.

---

## L-5 — COMPOSE OPS (relic `channel_orb` / `summon`) ✅ BUILT + AutoSlay-VERIFIED 2026-06-19
The creative-harness north-star: a relic that COMPOSES with the class's own orb/summon systems (Cracked-Core /
companion relics). A relic reaches its class's pool via `RelicClass` (== the class index that keys the orb/summon
pools), so no new host interface is needed.

- **Runtime:** extracted the orb/summon bodies into shared `EffectRunner.ChannelForgedOrbs` / `SummonForged`
  helpers, now called by BOTH the card ops (refactor, behaviour unchanged) and the new relic ops. `RunRelicEffects`
  gained `channel_orb` + `summon` cases; `relicClass` is threaded `ForgedRelic.FireGuarded → RelicRunner.Fire →
  RunRelicEffects`. Both are **class-conditional** — defensive no-op (`IsOrbClass`/`IsSummonClass`) if the class
  declares no orbs/summons. `channel_orb` needs `orb` ("random" or a pool name); `summon` needs `summon_name`.
- **Generation gating (so the LLM never emits an invalid compose op):** `_validate_relic(relic, bp)` now takes the
  class blueprint — `channel_orb` requires the class to have orbs, `summon` requires the named minion in the pool
  (verified: rejects both mismatches). `_RelicContract.user_brief` tells the model which compose ops THIS class
  supports + the legal orb/summon names. `RELIC_VOCABULARY.md` documents both as CLASS-ONLY.
- **Verified — two AutoSlay runs:**
  - **`summon`** (slot 01 "The Swarmlord", summon class, relic summons a Spiderling at combat start): fired **8×**,
    Spiderlings spawned (the full K-3b recipe — pet + ForgedSummonPower + meat-shield), **zero relic exceptions**.
  - **`channel_orb`** (slot 02 "The Transmuter", orb class, relic channels a random orb at combat start): fired
    **12×**, orbs channeled (SFX + evoke work), run continued 12 combats. The `MegaSpine "Nil GodotObject"` visual
    errors are the **pre-existing custom-orb missing-art gap** (Ember/Cinder have no spine sprite — [[assets-todo]]),
    NOT a compose bug: 51 such errors vs only 12 relic channels — the class's CARDS trigger the same error ~10× more
    often (custom orbs channeled ~123×). Logged non-fatally. The compose op itself channels correctly.
- **Mod builds clean (0 errors).** Diagnostics removed; slots restored. Stage helper:
  `scratch/stage_phase_l_compose.py` (gitignored).
- **Note for a production build:** `channel_orb` makes custom-orb visuals matter more (a relic surfaces them turn 1) —
  the custom-orb spine-sprite gap is already tracked in `ASSETS_TODO.md`; nothing new, just more visible.

---

## Risks & mitigations
- **Hook availability (highest):** the whole phase assumes `CustomRelicModel` exposes combat/turn lifecycle hooks.
  → L-0 reflection-verifies the exact API FIRST; if a trigger has no hook, it drops from v1 (and to the gap log).
- **No-card effect execution:** `EffectRunner.Execute` is card-shaped. → L-0 proves a `RunRelicEffects` entry
  point before L-1 builds on it.
- **Visuals/missing-art NRE:** forged relics have no icon (Phase I/K precedent). → L-0 picks the fallback-icon path.
- **Soft-lock family:** combat-end / last-enemy-kill hooks have hung before (merchant, boss-reward,
  [[boss-reward-rarity-hang]]). → L-0 tests combat-end; AutoSlay smoke gate in L-2.
- **Lockstep drift / version skew:** C#/Python describe + supported-set must stay identical; the bundle `relic`
  must re-validate on import against the live runtime. → L-2 verifies; version bump + import check.
- **Game-update fragility:** the post-v0.103.3 API renames already bit the mod ([[sts2-game-update-port]]); relic
  hooks may shift too. → pin the verified API in L-0 notes.

## Verification (per step)
- **L-0:** dev console / class-select shows the spike relic; combat-start + turn-end hooks fire; binds + renders;
  clean log; no end-of-combat hang.
- **L-1:** staged test class boots with a hand-written relic exercising every v1 trigger + `max_energy`; fires
  correctly; clean.
- **L-2:** generation tests pass; fake + real 0-skip; in-game forged class uses its generated relic; AutoSlay smoke
  clean; website redeploy.
