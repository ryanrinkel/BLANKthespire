# Phase I — Forged Orbs (custom, generated orb types) — PLAN

Status: **✅ I-1 + I-2 SHIPPED — reconciled 2026-06-27.** Generator integration is live: `class_forge.py`'s blueprint
declares a class `orb_pool` with custom orb defs (the Ember example, lines ~151-172), and the website describes/rates
forged custom orbs (commit `31d8b55`). Engine deployed 2026-06-17 (vocab v9). The original status (below) is preserved;
the only item the docs can't confirm is the one-off in-game verify of the staged "Transmuter" test class.

ORIGINAL STATUS: **I-1 (ENGINE) BUILT — 0 errors + deployed 2026-06-17, vocab v9; awaiting in-game verify. I-2 (generator) NOT
STARTED.** Test class "The Transmuter" staged to forged slot 02 (`generation/scratch/stage_phase_i_orbs.py`; prior
slot-02 Tempest backed up to `scratch/_backup_class02/`). Files: `Engine/OrbSpec.cs`, `Powers/ForgedOrb.cs`,
`Engine/OrbRunner.cs`, `Engine/IForgedOrbHost.cs`; edits to CharacterSpec/ForgedCharacters/EffectRunner/ForgedCards/
slotgen.py. See [[creative-harness-vision]] for the full build log + verification checklist.

The deepest expression of the [[creative-harness-vision]] north-star: a class that invents its
**own elements**, not just channels Lightning/Frost/Dark. Builds on Phase G (orbs as a class identity) and reuses the
H3 trigger architecture almost wholesale (a per-turn engine bound to a compiled shell, run from a restricted vocab).

## Feasibility — CONFIRMED (BaseLib + sts2.dll reflection, 2026-06-17)
- **`BaseLib.Abstracts.CustomOrbModel : OrbModel, ICustomModel, ILocalizationProvider`** exists and **auto-registers**
  (adds itself to `RegisteredOrbs` in its ctor; same `ICustomModel` scan as cards/powers — no MainFile change).
- **`OrbModel` overridable surface** (dump §2, lines 333-386): `Task Passive(PlayerChoiceContext ctx, Creature target)`
  (the per-turn tick — **gets a target**, so an orb passive CAN damage an enemy, unlike a turn-trigger),
  `Task<…> Evoke(PlayerChoiceContext ctx)` (the burst), `Decimal ModifyOrbValue(Decimal)` (Focus scaling), props
  `PassiveVal` / `EvokeVal` (the orb's numbers), `IconPath`/`SpritePath`/`*Sfx` (art, Harmony-patched to read
  `CustomIconPath`/`CustomSpritePath`/`CreateCustomSprite`), `Localization` (return an **`OrbLoc(Title,Description,
  SmartDescription)`**).
- **Orbs are INSTANCED + STATEFUL:** channeled via `((OrbModel)ModelDb.Get(type)).ToMutable(initialAmount)` — each
  channeled orb is its own mutable instance carrying a value, so a custom orb can ACCUMULATE (like Dark). This is the
  big advantage over powers (which merge by ModelId): per-orb state is free.
- **Random pool:** `CustomOrbModel.IncludeInRandomPool => true` makes BaseLib's `GetRandomOrb` postfix include it with
  fair odds. So forged orbs can participate in `channel_orb orb:"random"`.

## The constraint (same as everything else: Q1/Q2)
One orb = one compiled .NET Type, registered at init, frozen. So forged orbs CANNOT be arbitrary runtime data — they
must be **data-driven shells** (a fixed pool of generic `CustomOrbModel` subclasses, each reading an orb-spec from
JSON), exactly like `ForgedCardSlotNN` / `ForgedTriggerPowerNN`.

---

## The class orb pool — the modality system (USER-DECIDED 2026-06-17)
Custom orbs are **strictly class-specific**: an orb a class forges belongs ONLY to that class, never global, never in
another class's pool, never in the global random pool. Each orb class declares an **orb pool** — an ordered, named
list of the orbs it channels — and that one list drives everything (channeling, `random`, the HUD). This single
concept expresses all the **modalities** the user wants:
- **base-only:** pool = e.g. `["lightning","frost","dark"]` (today's Phase G behaviour) — a class that uses the stock
  elements.
- **mixed:** pool = `["lightning", {custom "Ember"…}]` — base orbs plus one or more custom.
- **all-custom:** pool = `[{ "Ember"… }, { "Ash"… }, { "Cinder"… }]` — a class with a wholly invented element set.

Rules: a class pool may mix base orb refs (by name) and **0–3 custom orb defs** (the cap). `channel_orb` on a class
card references a pool entry **by name** (`orb:"ember"`) or `orb:"random"`; **`random` rolls within THIS class's pool
only** — never the global `GetRandomOrb`. (So forged orbs set `IncludeInRandomPool => false`; the class-card random
handler picks from the class pool explicitly. Shared/non-class forged cards keep the base-3 random, unchanged.)

## Architecture (mirror H3 triggers)
1. **`OrbSpec`** (new record, `Engine/`): `Name`, `Color/IconHue`, `PassiveVal`, `EvokeVal`, `Passive`
   (`OrbEffect[]`), `Evoke` (`OrbEffect[]`). An **`OrbEffect`** is an `EffectSpec` + a `target` (self / enemy /
   all_enemies) so each orb effect picks its own modality (see vocab below) — this is the "maximize modalities" call.
   The spec rides the class: `CharacterSpec += OrbPool` (the ordered named list of base-orb refs + custom OrbSpecs).
2. **`ForgedCharacters`** reads the per-class orb pool from `user://forged/characters/KK.json`:
   `"orb_pool": [ "lightning", { "name":"Ember", "passive_val":2, "evoke_val":6, "passive":[…], "evoke":[…] }, … ]`
   (entries are base-orb name strings OR custom orb defs; ≤3 custom). Add `OrbPoolFor(K)` →
   resolved list of orb **Types** (base type or `ForgedClassKOrbM`), `OrbSpecFor(K,m)`, `OrbPoolNames(K)`.
3. **Generic orb shells (slotgen):** per class K, `ForgedClassKOrbM : ForgedOrb` (M = 1..3), each
   `protected override OrbSpec? Source => ForgedCharacters.OrbSpecFor(K, M)`. Hand-written base
   `Powers/ForgedOrb.cs : CustomOrbModel` overrides `Passive`/`Evoke`/`PassiveVal`/`EvokeVal`/`Localization`(OrbLoc)/
   icon, sets **`IncludeInRandomPool => false`** (random is class-scoped, not global), and runs its spec via `OrbRunner`.
4. **`OrbRunner`** (like `TriggerRunner`): runs an orb's `Passive`/`Evoke` `OrbEffect` lists with LITERAL amounts,
   honoring each effect's `target` to **maximize creative modalities**:
   - **Passive** — the game hands `Passive(ctx, target)` a target Creature; an effect with `target:"enemy"` hits it,
     `all_enemies` hits all, `self` runs on the player (block/buff/draw/etc). So a passive can damage, shield, ramp…
   - **Evoke** — supports `self`, `all_enemies`, AND single `enemy` (Dark-style) — resolve the single target via the
     evoke target mechanism (`AfterOrbEvoked` exposes `IEnumerable<Creature> targets`; verify how `Evoke()` gets/picks
     it; fall back to "lowest-HP / first enemy" if no chooser). Full targeting in both = the widest design space.
   - Reuse the EffectRunner scalar ops + the AoE/target helpers from CommonActions; `ModifyOrbValue` applies Focus to
     the orb's `PassiveVal`/`EvokeVal` (the "primary value" each orb advertises).
5. **Channeling (class-pool by name):** `channel_orb` on a class card takes `orb:"<pool name>"` (any orb in the
   class's pool, base or custom) or `orb:"random"`. The card is a `ForgedClassKCardNN` (knows its class K, like
   `IForgedTriggerHost`) → a **class-aware orb resolver** maps the name → a Type from `OrbPoolFor(K)` and channels
   `ModelDb.Get(type).ToMutable(initialAmount)`. **`random` rolls within `OrbPoolFor(K)` only** (USER-DECIDED). Shared
   (non-class) forged cards keep today's literal `lightning/frost/dark/random`-among-base behaviour unchanged.
6. **Vocab version → 9.** Touchpoints: `CharacterSpec`/`ForgedCharacters` (orb pool), `Engine/OrbSpec.cs` (+OrbEffect),
   `Powers/ForgedOrb.cs`, `Engine/OrbRunner.cs`, the class-aware orb resolver (EffectRunner `channel_orb` path +
   an `IForgedOrbHost`-style hook on class card leaves), `ForgedCards` (channel_orb name parse/validate/Describe),
   `slotgen.py` (orb shells + host wiring), the contract (schema/VOCABULARY), `cardgen.py` (orb describe),
   `validator.py`, `bts1.py`, `class_forge.py` (blueprint defines the orb pool), `character_*` import path.

## Orb effect vocabulary (per OrbEffect: an op + a `target`)
To maximize modalities, orb effects carry a `target` (`self` / `enemy` / `all_enemies`) and draw from:
- **damage** (target/all_enemies — a passive tick or an evoke burst), **block** (self), **apply_status**
  (self-buff on self; or a debuff — vulnerable/weak/frail/poison — on enemy/all_enemies, since an orb HAS a target,
  unlike a turn-trigger), **draw** / **gain_energy** / **heal** (self), **gain_orb_slot** (self),
  **channel_orb** (chain another of the class's orbs).
- Passive numbers fire EVERY turn → keep small; evoke is the burst → bigger. The validator enforces sane caps.
- Conditions (`when`) inside orb effects: **deferred** to a follow-up (recommended) unless we find it cheap.

## MVP cut
Phase I-1 (engine): `OrbSpec`/`OrbEffect` + `ForgedOrb` shell + `OrbRunner` (full targeting) + class `orb_pool` +
the class-aware channel resolver + class-scoped `random`; hand-author a test orb class spanning the modalities (e.g.
pool = `["lightning", {Ember: passive deal 2 to enemy, evoke deal 8 to all}]`) → **verify in-game** (channel base +
custom from the same class, passive ticks, evoke burst incl. single-target + AoE, HUD/icon render, random rolls only
the class pool). →
Phase I-2 (generator): blueprint declares the class's `orb_pool` (base/mixed/all-custom); cards channel by pool name;
the safety net keeps orb mechanics orb-class-only. Fake + real forge one class per modality → website redeploy.

Sequencing per the house pattern: build C# shell + hand-authored test orb → **user verifies in-game** → open to the
generator (contract/cardgen/validator/class_forge) → fake+real forge → redeploy.

## Decisions (RESOLVED 2026-06-17 unless noted)
1. **Modalities:** a class declares an `orb_pool` mixing base orb refs + **≤3 custom orb defs** → supports base-only /
   mixed / all-custom. ✅
2. **`random`:** class-scoped — rolls only the class's own `orb_pool` (forged orbs are NOT in the global pool). ✅
3. **Targeting / creative range:** orb effects (passive AND evoke) support `self` / `enemy` / `all_enemies` to maximize
   modalities; single-target evoke included (verify the evoke-target API at build). ✅
4. **Focus scaling:** wire `ModifyOrbValue` to the orb's primary `PassiveVal`/`EvokeVal` (so Focus matters on custom
   orbs like it does on base orbs). ✅ (small; keep if cheap, else defer to I-2.)
5. **Art:** placeholder sprite/color for the MVP (custom hue ok; real per-orb art deferred). ✅
6. **Conditions (`when`) inside orb effects:** **deferred** to a follow-up. ✅

## Risk notes
- `Passive`/`Evoke` exact return types + how the game supplies the passive `target` (single? per-enemy?) — verify with
  a reflect dump of `OrbModel` members + how `LightningOrb`/`DarkOrb` implement Passive/Evoke before building (the
  H3 lesson: trust the dll dump over BaseLib source; e.g. confirm `Evoke`'s targeting + how AoE evoke enumerates).
- Orb HUD/sprite: Phase G proved the HUD renders for a non-Defect class and tolerates a missing sprite (benign
  "asset not cached" warn); a custom orb with no art should likewise fall back gracefully — confirm.
- `ToMutable(initialAmount)`: set the orb's starting value here; verify forged orbs don't need extra init.
