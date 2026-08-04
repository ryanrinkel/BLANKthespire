# Phase K-3 — Summoner Archetypes (the creative harness for pet classes)

Status: **⏸️ SHELVED — reconciled 2026-06-27.** K-3 custom summon mechanics were disabled when forged summons were
refit to the base-game Osty (vocab v15); the K-3 engine is dormant. See [[summon-true-osty-refit]]. The archetype
design below is retained for if/when custom summon mechanics are revived.

Phase K shipped ONE shape of forged summon: a persistent, HP-bar'd, meat-shielding autonomous ally with a
fixed stat line and a fixed per-turn move cycle (see `phase-k-summons` memory + `Engine/SummonSpec.cs`,
`Powers/ForgedSummon.cs`, `ForgedSummonPower.cs`, `ForgedSummonShieldPower.cs`, `Engine/SummonRunner.cs`).

K-3 grows the harness so the LLM can compose **three distinct summoner archetypes**, not just the one shape.
The unifying mechanism is a per-summon **`kind`** (`commander` | `swarm` | `ethereal`), declared in a class's
`summon_pool`, that drives both the C# engine behaviour and the `class_forge.py` archetype guidance.

Each sub-phase follows the established K loop: **engine change → rebuild → in-game verify (staged test class)
→ THEN open to the LLM generator** (`class_forge.py` blueprint + validation + `VOCABULARY.md`).

---

## The three archetypes

### 1. Commander (Osty clone — a single growing pet)  → **K-3c**
- **Fantasy:** one persistent pet; cards pump its HP / power over the fight; the "Summon" feel.
- **Engine today:** the persistent meat-shield pet ✓; a pet can self-buff in its move cycle ✓ (Strength on the
  pet boosts its own attacks since it is the dealer).
- **Gap:** no card op reaches the *living* summon to grow it. → new card op **`buff_summon`**
  (apply a self-buff e.g. Strength / `heal` the summon; later raise max HP — riskiest, HP is set at creation).
- **Decision (user, 2026-06-18):** build `buff_summon` (Strength/heal safe first; +max-HP if it proves out).

### 2. Swarm (many cheap minions with enter/die/attack payoffs)  → **K-3b**
- **Fantasy:** spit out several small minions; value is in them entering, dying, or landing hits — not stats.
- **Engine today:** multi-count summon (`amount`) ✓; per-turn move cycle ✓; `pet.Died` already wired.
- **Gaps:** **on-summon**, **on-death**, **on-Nth-attack** payloads don't exist (only the per-turn cycle). →
  new `SummonSpec` fields `on_summon[]` / `on_death[]` + an attack-counter payoff in `SummonRunner`. Plus a
  **tuning pass**: cheap multi-summons are overtuned (1 energy → 8-HP pet that Blocks 4 ≈ 12 armour/turn that
  grows). Add validator caps: low `max_hp` for swarm kind, capped per-turn block, value-vs-cost sanity.

### 3. Ethereal (non-attackable striker — the falconer's falcon)  → **K-3a (FIRST)**
- **Fantasy:** a pet that strikes but has no HP bar and is never targeted/hit.
- **Engine today:** this is the engine's DEFAULT *before* the Osty treatment — `ToggleIsInteractable(true)`
  (HP bar) + `ForgedSummonShieldPower` (meat-shield) are what we ADDED. So the change is to make those
  conditional on the summon being attackable.
- **Gap:** a per-summon flag (`attackable: false`, i.e. `kind: "ethereal"`) that (a) skips the HP-bar toggle
  in `LayoutPets` and (b) excludes the pet from the shield redirect. Smallest, lowest-risk change of the three.

---

## K-3a — Ethereal summons (engine)  ← active

Add `bool Attackable` to `SummonSpec` (default `true`). An ethereal summon still spawns, is positioned, and
acts each turn via `ForgedSummonPower`; it just has no HP bar and never soaks damage.

**Engine edits:**
1. `Engine/SummonSpec.cs` — `SummonSpec` record `+ bool Attackable = true`.
2. `Engine/ForgedCharacters.cs` — `Bool` helper; `TryParseSummon` reads `attackable` (default true) → spec.
3. `Powers/ForgedSummon.cs` `LayoutPets` — position every living pet, but only `ToggleIsInteractable(true)`
   for pets whose `ForgedSummon.Source.Attackable` is true (ethereal stays non-interactable → no HP bar).
4. `Powers/ForgedSummonShieldPower.cs` — the front-pick filters to `fs.Source?.Attackable == true`, so an
   ethereal minion is never the meat-shield (it stays untouched).
5. `Engine/SummonRunner.cs` `Describe` — append "(cannot be attacked)" for an ethereal spec (pet tooltip; C#
   only, no cardgen lockstep needed).

**In-game test:** stage a "The Falconer" class (slot 01) with an ethereal **Falcon** (attack, untargetable)
alongside a normal attackable summon, to confirm both behaviours side-by-side. Verify: Falcon spawns, has NO
HP bar, attacks each turn end, and enemy powered hits flow PAST it to the attackable minion / player.

**Then K-3a-gen:** `class_forge.py` — `attackable` in `_validate_summon_pool`; THE SUMMON POOL guidance gains
the ethereal/falconer pattern. `VOCABULARY.md` Forged-summons section documents `attackable`. Fake+real forge
→ website redeploy (outward — confirm first).

---

## Build order (user-chosen 2026-06-18): K-3a ethereal → K-3b swarm → K-3c commander growth.
