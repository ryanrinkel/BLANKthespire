# Phase BA — Forged Potions (custom, generated class potions) — PLAN

Status: **DONE 2026-09-15 (vocab v55). Mod builds clean (0 errors); generation suite 408 passed;
`tests/test_phase_ba.py` 120/120; the AutoSlay gate (rule 0.3) PASSED on both arms.**

The scope below was written 2026-09-14 against a reflected API. Four things changed once BA-0 (the
verify-first step) was actually done; each is recorded in place, and the sections they contradict are
marked. The short version:

1. **The blocking pool question answered itself — option (A), and (B) turned out to be IMPOSSIBLE, not just
   inelegant.** `PotionPoolModel.AllPotions` lazily caches into `_allPotions`, AND the first read calls
   `ModHelper.ConcatModelsFromMods`, which sets `isFrozen = true` on that pool's modded content forever. A
   shared pool that filters by the running class could therefore never change after the first roll. Per-class
   `ForgedClassPotionPoolKK` it is.
2. **Composition with the base table needs NO work at all.** `PotionFactory.GetPotionOptions` is literally
   `player.Character.PotionPool.GetUnlockedPotions(…).Concat(ModelDb.PotionPool<SharedPotionPool>().GetUnlockedPotions(…))`.
   The character's pool is ADDED to the base table by the game itself. `IsShared` stays false (that flag does the
   opposite — it would publish the class's potion to *every* character).
3. **The icons never needed the web round-trip.** The plan assumed the `ForgedRelicIcon` path (render on the web,
   carry a `potion_icon_url`, download on import, `TakeOverPath` a synthetic `res://`). But the mod already has
   `EmojiIconRenderer`, which rasterizes an emoji to a `.res` at init and PROBES it through `ResourceLoader`
   before exposing the path — the surface a potion needs. Reflection confirmed BaseLib Harmony-patches the
   PRIVATE `PotionModel.PackedImagePath` getter, so one `CustomPackedImagePath` override reaches every consumer
   (the belt, the tooltip, and the throw VFX's `Image`). **No web/app.py change, no `potion_icon_url`, no
   download, and none of the weak-reference hazard the relic path carries.**
4. **Save/load round-trips safely.** `ToSerializable` writes only `{Id, SlotIndex}` and `FromSerializable` is
   `SaveUtil.PotionOrDeprecated(save.Id).ToMutable()` — an id lookup against models registered at init, which is
   exactly what a compiled shell is. Nothing to build.

**Scope change from the brief:** the plan said 1–2 potions per class, optional. It ships as **exactly one,
always** — `MaxPotions = 1`, `POTIONS_PER_CLASS = 1`, four shells rather than eight. That is the requested
outcome ("each time a class is forged they have in the pool an extra custom potion"), and it simplifies the
prompt (one required object, not an optional array) and the pool wiring.

---

## What actually shipped

**Mod (C#)**
- `Engine/PotionSpec.cs` — the record.
- `Engine/CharacterSpec.cs` — `PotionPool` (`= []`, so every pre-v55 class is byte-identical).
- `Engine/ForgedCharacters.cs` — `potion_pool` parse, `MaxPotions`, `PotionSpecFor` / `HasForgedPotions`, and the
  rarity / usage / target / op validation, mirroring the generator. Parsed AFTER the orb/status/summon pools so
  the class-conditional ops can be checked against the class's own content at import time.
- `Powers/ForgedPotion.cs` — the `CustomPotionModel` base. `OnUse` resolves targets and awaits
  `EffectRunner.RunRelicEffects`; rarity/usage/target map onto the game's enums; the icon comes from
  `EmojiIconRenderer` with a shipped fallback (a null image would NRE `NPotion`).
- `Engine/EffectRunner.cs` — **`apply_status_custom` added to `RunRelicEffects`.** The one new op path, and the
  reason a status class's potion can hand out its own status. The relic vocabulary does not list it, so a relic
  bundle carrying it is still rejected at import.
- `MainFile.cs` — pre-render each class potion's emoji (`potion{K}_{M}`), beside the existing status pre-render.
- `ForgedCards.VocabVersion` → **55**.

**Codegen** — `slotgen.py` gains `POTIONS_PER_CLASS = 1`, `CLASS_POTION_POOL_TMPL`, `CLASS_POTION_LINE`, the
`CHARACTER_TMPL` swap to the per-class pool, and the `n_types` bump (368 → 380). An unfilled slot is withheld in
`GetUnlockedPotions`, which is the one seam the `AllPotions` cache does not cover.

**Generation (Python)** — `bts1.VOCAB_VERSION` → 55; `class_forge.py` gains the blueprint FORMAT row + the
REQUIRED rule, `_validate_potion` (a mirror of the C# parser) and `_default_potion`; assembly always writes
`character["potion_pool"]`. `mod/contract/VOCABULARY.md` gains **THE SIGNATURE POTION** (the op table lives here,
in the half of the prompt that legitimately grows). `web/static/app.js` renders the potion as a class-mechanics
chip; `web/forge.py` + `web/app.py` accept `potion` as a rateable element.

**Two deviations from the MVP cut, both because the file said so:**
- *`card.schema.json` is untouched.* Step 5 listed "a `potion_pool` block", but that schema describes a CARD; the
  character-level pools (`orb_pool` / `status_pool` / `summon_pool`) are not in it either — they are only
  referenced from field docs. There is nothing there for a potion to add.
- *`census.py` / `coverage.py` / `featured.py` are untouched.* All three are card-op machinery (census walks
  `bundle["cards"]`); a character-level potion is invisible to them, and inventing a counter would have been
  scope, not lockstep.

**Rule 0.9** — scaffolding **44,845 → 45,484** (+639), against the `BP_SCAFFOLD_BUDGET = 46,000` set at Phase AZ;
516 chars of headroom remain. Total prompt 100,041 → 104,075, well under the 120,000 tripwire. Paid down mid-build
by moving the op table out of the blueprint and into `VOCABULARY.md`. **No private ceiling in
`test_phase_ba.py`** — the one budget stays in `tests/test_harness_v2.py`, whose recorded readings were updated.
(`test_phase_ay.py`'s `== 54` version pin was relaxed to `>= 54`: it was a measuring stick for a shared global,
the exact antipattern the AZ note calls out.)

**The AutoSlay gate — PASSED, both arms.** `generation/scratch/gaptest-ba/build_tester.py` stages TWO arms, because
one potion per class cannot cover both target modes:

```bash
cd generation
uv run python scratch/gaptest-ba/build_tester.py     # slot 04 = enemy arm, slot 03 = self arm
uv run btsgen-autoslay-smoke --seeds GAPTESTBA1 --character class4 --timeout 900
uv run btsgen-autoslay-smoke --seeds GAPTESTBA2 --character class3 --timeout 900
uv run python scratch/gaptest-ba/build_tester.py --remove
```

Slot 04 is a STATUS class whose `Vial of Rot` (enemy, common) deals 14 and applies 3 of its own `Rotting`; slot 03
is a plain class whose `Bracing Draught` (self, common) gives 16 Block and draws 2. Both are `common` so the ~65%
common tier actually rolls them in a random run.

**Results** (tags saved beside the builder as `godot_BA_tags_<seed>.txt`):

| arm | seed | verdict |
|---|---|---|
| enemy (class 04) | `GAPTESTBA1` | **PASS** — `[BA] potion 'Vial of Rot' (class 04 slot 1) used: target=enemy (1 creature(s)), 2 effect(s).` · `[BA] apply_status_custom: apply 3 Rotting to 1 enemy/ies.` · `[BA] … resolved.` |
| self (class 03) | `GAPTESTBA2` | inconclusive — potion registered (`potion3_1` icon rendered + probed loadable), but 16 potion rolls never hit the forged common |
| self (class 03) | `GAPTESTBA3` | **PASS** — `[BA] potion 'Bracing Draught' (class 03 slot 1) used: target=self (0 creature(s)), 2 effect(s).` · `[BA] … resolved.` |

**0 mod exceptions on every run** — `grep "at BlankTheSpire"` over `godot.log` returns nothing on all three. The
only errors in the log are BaseLib's own boot-time Harmony patch failures and MegaCrit's
`AutoSlayTimeoutException` inside `AutoSlayer.AbandonRunAsync` (the harness hunting a top-bar Options button
during teardown) — both pre-existing and neither in a mod frame.

**Composition confirmed in-game, which was the load-bearing unknown.** `GAPTESTBA1` was offered 18 distinct
potions: 17 base-game (`FIRE_POTION`, `FAIRY_IN_A_BOTTLE`, `WEAK_POTION`, …) plus exactly one
`BLANKTHESPIRE-FORGED_CLASS04_POTION1`. `GAPTESTBA3` likewise showed 12 base-game plus one
`BLANKTHESPIRE-FORGED_CLASS03_POTION1`, and never class 04's — so the per-class pools isolate correctly AND
compose with `SharedPotionPool`, exactly as `PotionFactory.GetPotionOptions` promised.

**Note the `target=self (0 creature(s))` line**: a self potion passes an EMPTY target list and the runner still
lands its effects on the owner — the design working as intended, not a miss.

**A coverage lesson for the next phase that gates on a random drop:** the self arm needed a second seed. A
`common` forged potion is ~1-in-12 of the common tier, and ~40% of runs never roll it at all, so ONE seed is not
evidence of absence. `AUTOSLAY_VALIDATION_QUEUE.md` already says to run several seeds; this is that caveat
biting on a drop-table feature rather than a play-pattern one.

---

## Original scope (2026-09-14)

The API below is reflected off the shipped binaries, not guessed — see Feasibility. Nothing in `mod/` had been
touched at the time of writing.

A forged class currently invents its own cards (Phase B), orbs (I), statuses (J), summons (K), a relic (L) and a
Forge/blade (M). Potions are the last "invent your own X" axis with a live engine surface and no generator
behind it: `Potions/BlankTheSpirePotion.cs` and `Character/BlankTheSpirePotionPool.cs` are BaseLib scaffolding
with **zero concrete potions** — every forged class today draws the base game's potion table.

This phase gives a class 1–2 potions of its own, declared in the bundle as `potion_pool`, reusing the card
effect vocabulary. It is the CHEAPEST remaining content type by a wide margin, for one reason established
below: the potion's effect entry point already hands us a `PlayerChoiceContext`, so **no new effect runner is
needed** — `EffectRunner.RunRelicEffects` runs as-is.

---

## Feasibility — CONFIRMED (BaseLib 3.2.1 + `sts2.dll` reflection, 2026-09-14)

Probed with a `MetadataLoadContext` dump (the `_modref/reflect/` technique; throwaway probe, not committed).

**`MegaCrit.Sts2.Core.Models.PotionModel`** — what a potion must supply:

| member | kind | note |
|---|---|---|
| `Rarity` → `PotionRarity` | **abstract** | `None / Common / Uncommon / Rare / Event / Token` |
| `Usage` → `PotionUsage` | **abstract** | `None / CombatOnly / AnyTime / Automatic` |
| `TargetType` | **abstract** | the same `TargetType` cards use |
| `OnUse(PlayerChoiceContext choiceContext, Creature target)` → `Task` | virtual | **the effect entry point** |
| `Title` / `Description` → `LocString` | — | fed by `CustomPotionModel.Localization` (in-code loc, no .pck) |
| `PackedImagePath` / `PackedOutlinePath` | — | path-based, like `RelicModel` — see Icons below |
| `CanBeGeneratedInCombat`, `PassesCustomUsabilityCheck`, `ExtraHoverTips` | virtual | left at defaults in v1 |

**`BaseLib.Abstracts.CustomPotionModel : PotionModel`** adds `AutoAdd`, `CustomPackedImagePath`,
`CustomPackedOutlinePath`, `Localization` — the same four-override shape `BlankTheSpireRelic` uses.

**`PotionPoolModel`** has `abstract GenerateAllPotions()`; `CustomPotionPoolModel` overrides it (plus `IsShared`,
`SeenByDefault`, `EnergyColorName`). `BlankTheSpirePotion` already carries `[Pool(typeof(BlankTheSpirePotionPool))]`,
so pool membership rides the same attribute mechanism the card pools use.

**The load-bearing find:** `OnUse` receives a `PlayerChoiceContext`. That is exactly the first argument of

```csharp
EffectRunner.RunRelicEffects(EffectSpec[] effects, PlayerChoiceContext ctx, Player player,
                             List<Creature> targets, int relicClass, string hookTarget = "self")
```

which already runs the no-card sub-vocabulary (damage, block, draw, gain_energy, heal, lose_hp, apply_status
buff→player/debuff→targets, discard) by merging the `TriggerRunner` self path and the `SummonRunner` targeted
path. A potion is a no-card effect with a ctx and a target — **structurally identical to a relic hook firing**.
So Phase BA adds a data spec, shells, a pool and a parse step, and reuses the runner. Compare Phase L, which had
to build `RelicRunner` from nothing.

---

## The constraint (same Q1 as every other forged type)

Models are discovered and registered at mod init, so a forged potion cannot be a runtime-constructed type. It
must be a **pre-compiled shell** that reads its spec from JSON at load, exactly like `ForgedClass{KK}Relic`
(`slotgen.CLASS_RELIC_LINE`):

```csharp
public sealed class ForgedClass01Potion01 : BlankTheSpire.BlankTheSpireCode.Powers.ForgedPotion
{ protected override int PotionClass => 1; protected override int PotionIndex => 1; }
```

`POTIONS_PER_CLASS = 2` in `slotgen.py` (mirroring `SUMMONS_PER_CLASS`), so 4 classes × 2 = **8 new shells**;
`n_types` in `gen_classes()` grows by `CLASS_COUNT * POTIONS_PER_CLASS`. An undeclared potion slot reports
`IsEmpty` and is withheld from the pool, the same way a blank card slot is never seeded into a starting deck.

---

## ⚠ The pool is SHARED — decide this first (BLOCKING)  
**RESOLVED — option (A). (B) is impossible; see decision 1 at the top.**

`ForgedCharacterSlot{KK}` (in `ForgedClasses.g.cs`, from `slotgen.CHARACTER_TMPL`) currently says:

```csharp
public override CardPoolModel   CardPool   => ModelDb.CardPool<ForgedClassPool{k:02}>();     // PER CLASS
public override PotionPoolModel PotionPool => ModelDb.PotionPool<BlankTheSpirePotionPool>(); // SHARED, all 4
```

Cards got an isolated per-class pool precisely so one forged class never draws another's cards. Potions did not,
because there were none. The moment class 01 and class 02 both declare a `potion_pool`, **class 01 starts
rolling class 02's potions** — cross-class bleed, the exact failure the card pools were built to prevent.

Two ways out, and the phase should not start until one is chosen:

- **(A) Per-class potion pools — RECOMMENDED.** `ForgedClassPotionPool{KK} : CustomPotionPoolModel`, generated by
  `slotgen.py` beside `ForgedClassPool{KK}`, and the character template points at its own. Mirrors the card pools
  exactly, needs no filtering logic, and the pool's `LabOutlineColor` / energy icons can take the class's own hue.
  Cost: 4 more generated types and a `CHARACTER_TMPL` edit.
- **(B) One shared pool that filters.** Override `GenerateAllPotions()` / `GetUnlockedPotions(UnlockState)` on
  `BlankTheSpirePotionPool` to emit only the running class's potions. Fewer types, but it makes pool contents
  depend on run state, and `AllPotions` / `AllPotionIds` are cached on `PotionPoolModel` (the `_allPotions` /
  `_allPotionIds` fields) — a cache very likely populated once at init. **Verify that caching before
  considering (B).**

Whichever wins, the base game's potions should keep appearing alongside the class's: a forged class with two
potions and nothing else would gut potion variety for a whole run. Confirm how a custom pool composes with the
base table (`IsShared` on `CustomPotionPoolModel` is the likely lever) — **verify-first, rule 0.6.**

---

## The spec (generation side)

The bundle gains an optional character-level `potion_pool`, 1–2 entries, shaped like the existing `status_pool` /
`summon_pool` arrays:

```json
"potion_pool": [
  { "name": "Emberdraught", "emoji": "🔥", "rarity": "common", "usage": "combat",
    "target": "enemy", "description": "Deal 12 damage.",
    "effects": [ { "op": "damage", "amount": 12 } ] }
]
```

- `rarity` — `common | uncommon | rare` (the drop table's three tiers; `None` / `Event` / `Token` are
  base-game-internal and stay out of the vocabulary).
- `usage` — `combat` → `PotionUsage.CombatOnly`, `any` → `AnyTime`. `Automatic` is out of scope in v1.
- `target` — `self | enemy | all_enemies`, mapped to `TargetType`. A `self` potion passes an empty target list to
  the runner; `enemy` passes the `Creature target` that `OnUse` was handed.
- `effects` — the **relic sub-vocabulary**, not the full card vocabulary: damage, block, draw, gain_energy, heal,
  lose_hp, apply_status, discard. That is precisely what `RunRelicEffects` executes, so v1 costs zero new ops.
  No `add_trigger`, no `add_card`, no orb/summon/forge ops in v1 — each would need its own runner path and its
  own balance argument.

New C# `PotionSpec` record in `Engine/PotionSpec.cs`, mirroring `RelicSpec`:

```csharp
public sealed record PotionSpec(string Id, string Name, string Description, string Emoji,
                                string Rarity, string Usage, string Target, EffectSpec[] Effects);
```

`CharacterSpec` gains `PotionSpec[] Potions { get; init; } = [];` — defaulting empty keeps every pre-v55 class
byte-identical, the Phase AY `forge_persist` precedent. `ForgedCharacters` parses `potion_pool` next to the
existing `relic` branch (`ForgedCharacters.cs:317`), with `MaxPotions = 2`, `PotionSpecFor(k, m)` and
`HasForgedPotions(k)` alongside `MaxRelics` / `RelicSpecFor` / `HasForgedRelic` (`:447`, `:485`, `:489`).

---

## Icons
**SUPERSEDED — the emoji is rendered IN-MOD by `EmojiIconRenderer`; no web round-trip. See decision 3.**


`PotionModel`'s image surface is PATH-based — the same problem `ForgedRelicIcon` already solved: the web layer
renders the harness-picked emoji to a PNG, the bundle carries a `potion_icon_url`, import caches it under
`user://forged/characters/KK/potion_M.png`, and the texture is registered into Godot's resource cache under a
synthetic `res://` path via `Resource.TakeOverPath`. **Reuse `ForgedRelicIcon` wholesale — including its
hard-won lesson**: the cache holds taken-over resources only WEAKLY, so the `ImageTexture` needs a strong ref
held for the process lifetime or the icon dies between boot and run start (the invisible-relic bug, 2026-08-12).
No icon → fall back to a shipped placeholder, never null into the potion bar.

---

## MVP cut

1. **Verify-first (rule 0.6).** Resolve the pool question above; confirm custom potions compose with the base
   table rather than replacing it; confirm `AllPotions` caching. A contradiction here STOPS the phase.
2. `PotionSpec.cs` + `CharacterSpec.Potions` + `ForgedCharacters` parse/accessors + `MaxPotions`.
3. `Powers/ForgedPotion.cs` — a `CustomPotionModel` subclass reading its spec via `PotionClass` / `PotionIndex`;
   `OnUse` resolves targets and awaits `EffectRunner.RunRelicEffects`; `Localization` supplies name/description.
4. `slotgen.py`: `POTIONS_PER_CLASS = 2`, `CLASS_POTION_LINE`, the pool decision from (1), `n_types` bump; regen
   `ForgedClasses.g.cs`.
5. Generation lockstep (rule 0.1): `card.schema.json` (a `potion_pool` block), `VOCABULARY.md`, `bts1.py`
   VOCAB_VERSION → **v55**, `class_forge.py` blueprint, `validator.py`, `census.py`, `coverage.py` /
   `featured.py`, `web/static/app.js` (render the potions on the class page).
6. `tests/test_phase_ba.py`.
7. AutoSlay gate (rule 0.3): a tester class in slot 04 with two potions, one `self` and one `enemy`; grep
   `godot.log` for `[BA]` tags on each use, the effects resolving, and **0 mod exceptions**.

---

## Rule 0.9 — the prompt cost, budgeted in advance

A `potion_pool` section is a new class-kind pool, and the three existing ones cost real prompt text (THE STATUS
POOL 2,442 · THE ORB POOL 2,516 · THE SUMMON POOL 3,912). At Phase AZ the scaffolding budget
(`BP_SCAFFOLD_BUDGET` in `generation/tests/test_harness_v2.py`) has ~1,155 chars of headroom, and the vocabulary
half is uncapped but tracked. **A full potion-pool paragraph does not fit.** Plan for that up front:

- The blueprint gets a **one-line** pitch plus the `potion_pool` format row, and the full section goes into
  `_PRUNABLE_SECTIONS` + the W0.5 "ALSO AVAILABLE" menu + a `coverage.sanitize_nominations({"sections":
  ["potions"]})` entry — the machinery that exists for exactly this.
- The `VOCABULARY.md` rows land in the vocabulary half, which is the half that legitimately grows.
- If it still breaches, the phase argues for headroom in the one place the ceiling lives, with the reading in the
  commit message. It does NOT pin a private ceiling in `test_phase_ba.py` (see the AT/AW regression).

---

## Open questions
**The first two are ANSWERED (see the top); the last two stand.**

- **Potion rewards vs. the class's own potions.** Base-game potion drops roll from the pool; a 2-potion class
  pool alongside the base table is the intent, but the drop weighting is unverified.
- **`Automatic` usage** (a potion that fires itself) is a genuinely different fantasy, and is deferred.
- **Upgraded / "Potion Belt"-style interactions** — untouched; whatever the base game does, does.
- **Does a forged potion survive save/load?** `PotionModel.ToSerializable(int slotIndex)` /
  `FromSerializable(SerializablePotion)` exist, and a spec-backed shell should round-trip by id — but potions ARE
  carried between floors, so this is unverified and belongs in the verify-first step.
