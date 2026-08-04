# Phase H — Compositional Mechanics (randomness + conditions) — PLAN

Status: **◐ PARTIALLY ADDRESSED — reconciled 2026-06-27.** The DSL-shape decision was effectively resolved in the
affirmative — per-effect/card `when` conditions shipped via gap #5 (`hand_size_ge` / `retained_last_turn`) and gap #6
(card-condition lockstep), plus relic-side conditions in L-4. `channel_orb random` also exists. STILL OPEN: the
discrete "sentient slot machine" validation target (channel RANDOM orbs → if they match, big payoff) was never built
or validated as its own phase. Original status preserved below. — This is the [[creative-harness-vision]]
north-star: let the generator **compose** primitives (random generation + conditional payoffs) into novel class
identities, not just pick flat ops. **Concrete validation target: a "sentient slot machine" orb class** — channel
RANDOM orbs, and **if they match, a big payoff**.

## What it needs (and why it's the hard one)
Today a card is a FLAT `effects: [...]` list run top-to-bottom — no branching, no randomness, no state reads.
The slot machine needs three new capabilities:
1. **Randomness** — channel a *random* orb (so a pull can match or not).
2. **State reads** — inspect the orb queue (and board) to evaluate a condition ("do my orbs match?").
3. **Conditionals** — run an effect (the payoff) ONLY when the condition holds.

Feasibility confirmed (reflection): `OrbModel.GetRandomOrb(Rng)`; `OrbQueue.Orbs` (each `OrbModel.ModelId`) for
"match"; `Creature.HasPower(ModelId)` / `CurrentHp`/`MaxHp` / `CardPlay.PlayIndex` for generic conditions. No API
blockers — this is purely an EffectRunner/schema design.

---

## H1 — Randomness (small, independent, build first)
Extend `channel_orb` with `"orb": "random"` → channels a random orb. **Decision (default):** random among the 3
**tested MVP orbs** (lightning/frost/dark), NOT all 5 (plasma/glass are untested). Each orb in a multi-channel
(`amount > 1`) rolls independently — so `channel_orb random amount:3` is a "pull" that can come up matched.
- EffectRunner: a `_randomOrbs` array + an `Rng` from the run (pin the exact `RunState.Rng.<stream>` at build).
- Contract/validator: allow `"random"` in the `orb` enum. Low risk; ships on its own.

## H2 — Conditions (the structural leap) — **needs the DSL decision below**
Add a **condition** predicate the engine can evaluate from combat state, and a way to gate effects on it.

**Condition vocabulary (MVP — start small):**
| condition | true when | reads |
|---|---|---|
| `orbs_match` | you have ≥2 orbs and ALL are the same type (the jackpot) | `OrbQueue.Orbs` → `ModelId` |
| `orbs_full` | every orb slot is filled | `OrbQueue` count vs slots |
| `orb_count_ge` (`value`) | you have ≥ `value` orbs | `OrbQueue.Orbs.Count` |
| `target_has_status` (`status`) | the target has that status/power | `Creature.HasPower` |
| `no_block` | you currently have 0 Block | player Block |
| `hp_below_half` | your HP < 50% | `CurrentHp`/`MaxHp` |

Each is a tiny pure state-read in C#. The set grows later; `orbs_match` is the one the slot machine needs.

### The DSL shape — THREE options (pick one; this drives the EffectRunner refactor)
**Option C — per-effect `when` guard (RECOMMENDED).** Each effect may carry an optional `when` predicate; the
effect runs only if it holds.
```json
{ "effects": [
  { "op": "channel_orb", "orb": "random", "amount": 3 },
  { "op": "damage", "amount": 20, "when": { "kind": "orbs_match" } },
  { "op": "apply_status", "status": "vulnerable", "amount": 3, "when": { "kind": "orbs_match" } }
]}
```
*Pros:* keeps the flat effects list, so the **positional upgrade system stays intact**; maximally composable (guard
any effect); smallest EffectRunner change (skip effect if guard false). *Cons:* "else" = a second effect with the
negated condition (e.g. a future `when: {kind:"orbs_match", negate:true}`).

**Option B — card-level `bonus_effects`.** A card has always-run `effects` + a single `condition` + `bonus_effects`
run only if it holds. Simpler mental model, clean upgrades (separate array), but one condition per card, no nesting.

**Option A — nested `conditional` op (`then`/`else`).** Most expressive (real branches), but it breaks the flat
positional **upgrade** model and adds recursion to schema/validator/Describe. Heaviest.

My recommendation: **Option C** — it composes best, is the least disruptive to upgrades, and fully expresses the
slot machine (and far more). "Great things happen on a match" = several `when: orbs_match` effects with big numbers.

### H2 build (assuming Option C)
- `EffectSpec += Condition` (a small record: `Kind`, optional `Value`, optional `Status`, `Negate`). `ParseEffects`
  reads `when`. EffectRunner: before running effect `i`, `if (e.When != null && !Evaluate(e.When, ...)) continue;`.
- `Conditions.cs` — one `Evaluate(cond, card, ctx, play)` switch (the state reads above). Pin exact accessors
  (`Player.OrbQueue`, player Block, power→ModelId) via a reflect probe at build.
- Validator: known condition kinds + required params (e.g. `orb_count_ge` needs `value`); `target_has_status`
  status ∈ supported. Describe: "… if your orbs match." suffix per guarded effect. Bump `VocabVersion → 7`.
- Contract (VOCABULARY.md/schema) + `cardgen.py` mirror — open `when` + the condition list to the generator,
  with guidance (conditions are payoffs; `orbs_match`/orb conditions are orb-class only).

## H3 — Triggers (DEFERRED). "At end of turn, if …" / "whenever you play an attack…" needs custom compiled
parametric `PowerModel` shells (the game's trigger system is power-based) — a separate, heavier phase. The MVP slot
machine does NOT need it: a single card can "channel 3 random orbs; if matched, payoff" in one play.

---

## Generator (so the slot machine can be FORGED)
- `class_forge.py`: teach the blueprint the **random/condition** primitives and a **slot-machine archetype**
  (channel random orbs + matched-payoff cards), still orb-class-gated. Offline fake + a real forge of a
  slot-machine class as the end-to-end proof. Then **redeploy** `generation/`+`mod/contract/` to the DO droplet so
  the website forges these too (the user's stated next step after this phase).

## Sequencing & MVP cut
H1 (randomness) → H2 (the chosen DSL + `orbs_match` + the few generic conditions) → forge+play a slot-machine class
→ generator archetype → website redeploy. Triggers (H3) and the larger condition set come later.

## Open decisions for you
1. **DSL shape:** per-effect `when` (C, recommended) / card-level `bonus_effects` (B) / nested `conditional` (A)?
2. **Scope now:** H1+H2 (randomness + conditions) and defer triggers (recommended), or also start triggers (H3)?
3. (My default unless you object) random orbs draw from the 3 tested orbs; condition set = the 6 above.
