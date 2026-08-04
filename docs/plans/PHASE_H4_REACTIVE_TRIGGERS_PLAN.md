# Phase H4 — Reactive Card Triggers (VOCABULARY_GAPS #13 + #14)

**Status:** ✅ DONE + AutoSlay-VERIFIED (2026-07-01, vocab v18). Engine + lockstep + tests all shipped;
smoke fired all 9 trigger paths **465×** across 6 deep runs with **0 mod exceptions** (targeted apply ×98,
targeted deal ×86, on_card_played ×81, on_block_gained ×56, on_card_drawn ×47, on_damage_dealt ×44,
attacked ×37, on_exhaust ×13, on_hp_lost ×3). All RunFailed verdicts were AutoSlay-driver harness limits
(Event-proceed / Navigating-map watchdog), no BlankTheSpire stack frames. Gaps #13/#14 flipped to done.
**Side finding:** `temp_strength`/`temp_dexterity` crash on apply (`POWER.TEMPORARY_STRENGTH_POWER`
KeyNotFound) — pre-existing vocab bug, logged as VOCABULARY_GAPS #26 (HIGH). · **Vocab bump:** v17 →
**v18** · **Depends on:** the H3 trigger
runtime (`ForgedTriggerPower` / `TriggerRunner`) and the L-3/L-4 relic hooks (`ForgedRelic` /
`RelicRunner`), both shipped. · **AutoSlay:** ask before any smoke run (per standing preference).

## Why this is the cheapest big win

The relic runtime **already fires every hook we need** and **already has a targeted executor**.
This phase is mostly *plumbing*: mirror the relic's hook overrides onto the card-trigger power, and
reuse the relic's target-resolving payload runner. One pass unlocks a dozen+ classic power cards
(Feel No Pain, Dark Embrace, Juggernaut, Rage, Noxious Fumes, Combust, Choke, Bouncing Flask).

**Build decision (2026-07-01):** ship H4a + H4b as **one combined phase** — a single build, one
AutoSlay run, one deploy. The H4a/H4b split below is kept as the logical build order *within* the
phase (get the reactive hooks compiling and self-payload-correct before layering enemy targets), not
as two separate releases. Do the H4-0 spike first regardless.

---

## What already exists (verified — file : symbol)

| Piece | Location | Note |
|---|---|---|
| Card-trigger power base | `mod/…/Powers/ForgedTriggerPower.cs` | Abstract base; the generated `ForgedTriggerPowerNN` shells only bind `SourceSpec`. **Adding a hook override here needs NO shell regen.** |
| Existing card hooks | same | Overrides `AfterSideTurnEnd` (turn_end), `AfterPlayerTurnStart` (turn_start, ripen), `AfterDamageReceived` (on_hp_lost) |
| Self/orb payload runner | `mod/…/Engine/TriggerRunner.cs` → `Run(EffectSpec, Player, ctx)` | No target; literal amounts; `cards_retained` scale |
| **Reactive hooks, already wired for RELICS** | `mod/…/Powers/ForgedRelic.cs` | `AfterCardExhausted`→`on_exhaust`, `AfterCardPlayed`→`on_card_played`, `AfterCardDrawn`→`on_card_drawn`, `AfterDamageGiven`→`on_damage_dealt`, `AfterBlockGained`→`on_block_gained`, `AfterDamageReceived`→`attacked` |
| Re-entrancy guard pattern | `ForgedRelic._firing` (HashSet<string>) + `FireGuarded(...)` | Stops draw→draw / block→block loops — copy this exactly |
| **Targeted payload runner (for #14)** | `EffectRunner.RunRelicEffects(effects, ctx, player, targets, relicClass)` | Merges TriggerRunner's self path with SummonRunner's enemy path; `SummonRunner`/`RelicRunner.ResolveTargets` resolve `enemy`/`all_enemies` |
| Validation | `mod/…/Engine/ForgedCards.cs` | `SupportedTriggers`, `ValidateTrigger`, `TriggerOps`, `TriggerScale`, `SelfBuffStatuses`, `VocabVersion` (=17) |
| Card text | `ForgedCards.TriggerSentence` / `DescribeTrigger` / `TriggerFragment` | Keep byte-lockstep with `cardgen.py` |
| Python lockstep | `generation/btsgen/{cardgen.py, validator.py, bts1.py}`, `mod/contract/card.schema.json`, `mod/contract/VOCABULARY.md` | Same 6-file lockstep as gaps #6/#9 |

---

## ✅ Slice H4-0 — RESOLVED (static, 2026-07-01): powers DO get these hooks

**Result: PASS — clean overrides, no Harmony fallback needed.** Evidence from
`_modref/reflect/dump.txt`:
- `PowerModel : ... inheritsChain=AbstractModel Object` (line 7); `AbstractModel : base=Object` (911).
- The dump section *"PowerModel virtual hooks (overridable) — the trigger surface"* (line 1240) lists
  all six needed hooks as overridable on `PowerModel`, each `[decl=AbstractModel]`: `AfterBlockGained`
  (1247), `AfterCardDrawn` (1251), `AfterCardExhausted` (1254), `AfterCardPlayed` (1256),
  `AfterDamageGiven` (1265), `AfterDamageReceived` (1266).
- Clincher: `ForgedTriggerPower` already overrides three sibling `AbstractModel` hooks
  (`AfterSideTurnEnd`/`AfterPlayerTurnStart`/`AfterDamageReceived`) that fire at runtime
  (ripen + on_hp_lost are AutoSlay-verified). The card-lifecycle hooks share that base and surface →
  dispatched to active powers identically. No power-side `ShouldReceiveCombatHooks` gate to satisfy.

Optional belt-and-suspenders runtime proof folds into the H4a Gap-Tester smoke (an `on_exhaust`
card whose log/Flash fires when a card exhausts) — no separate spike build required.

<details><summary>Original risk write-up (kept for context)</summary>

## ⚠️ Slice H4-0 — the one real risk (spike FIRST, ~30 min)

**Do STS2 *powers* receive the card-lifecycle hooks the way relics do?** `ForgedRelic` overrides
`AfterCardExhausted`/`AfterCardPlayed`/`AfterCardDrawn`/`AfterDamageGiven`/`AfterBlockGained` via
`BlankTheSpireRelic`. `ForgedTriggerPower : BlankTheSpirePower : CustomPowerModel` already overrides
`AfterSideTurnEnd`/`AfterPlayerTurnStart`/`AfterDamageReceived` — so the shared `Hook` base clearly
dispatches *some* hooks to active powers. We must confirm the **card-lifecycle** ones are also
dispatched to powers (not only relics).

- **Check:** `_modref/reflect/dump.txt` for these virtual method signatures on `PowerModel`/`Hook`;
  and note BaseLib patches `Hook.AfterCardPlayed` at a single dispatch point
  (`_modref/BaseLib-StS2/Patches/Hooks/AfterCardPlayedPatch.cs`), which suggests a fan-out to all
  hook holders.
- **Cheap runtime proof:** add ONE test override (e.g. `AfterCardExhausted` → `Flash()` + log) to
  `ForgedTriggerPower`, grant it via a Gap-Tester card, exhaust a card, confirm the log fires.
- **If powers do NOT get a given hook:** fall back to a Harmony patch on the game's `Hook.<event>`
  that walks the player's active `ForgedTriggerPower`s (same shape as BaseLib's own patch). Only
  needed for the specific hooks that don't dispatch; keep the rest as clean overrides.

Everything below assumes the spike passes (clean overrides). Adjust only the affected hook(s) if not.

</details>

---

## Slice H4a — reactive hooks, self/orb payload (gap #13)

### Engine (`ForgedTriggerPower.cs`)
1. Add the reactive trigger kinds to the fire dispatch. For each, mirror the corresponding
   `ForgedRelic` override, but grant to the **power's owner (player)** and fire via
   `TriggerRunner.Run(Trigger, player, ctx)`:
   - `AfterCardExhausted(ctx, card, causedByEthereal)` → if `Trigger.Trigger=="on_exhaust"` and
     `card?.Owner == Owner.Player`.
   - `AfterCardPlayed(ctx, cardPlay)` → `on_card_played`.
   - `AfterCardDrawn(ctx, card, fromHandDraw)` → `on_card_drawn`.
   - `AfterDamageGiven(ctx, dealer, result, props, target, cardSource)` → `on_damage_dealt`
     (gate: `dealer == Owner && cardSource != null` — card damage only, excludes orb/thorns → no loop).
   - `AfterBlockGained(creature, amount, props, cardSource)` → `on_block_gained` (no ctx passed —
     capture the latest ctx from a turn hook like `ForgedRelic._combatCtx`).
2. **Re-entrancy guard:** add a `HashSet<string> _firing` and route all reactive fires through a
   `FireGuarded(kind, ctx, ...)` helper (copy `ForgedRelic.FireGuarded`). The recurring hooks
   (turn_start/turn_end/ripen/on_hp_lost) keep their existing paths.
3. **Multi-fire discipline** (gaps #13/#14 call this out — reactive hooks fire many times/turn):
   add an optional **`once_per_turn`** boolean on the `add_trigger` effect. Track a
   `_firedThisTurn` set (hook kind → bool), reset in a turn-start/`BeforeCombatStart` hook. Gate the
   payload when set. Keeps Feel-No-Pain-style powers from firing 5× on a big draw turn.
4. **Localization/tooltip:** extend the `Localization` title switch and `TriggerSentence`'s `when`
   phrase for each new kind ("Whenever a card is Exhausted", "Whenever you play a card", "Whenever
   you draw a card", "Whenever you deal damage", "Whenever you gain Block").

### Validation + generation lockstep (v18)
5. `ForgedCards.cs`: add the six kinds to `SupportedTriggers`; bump `VocabVersion = 18`; extend the
   header comment. `ValidateTrigger` mostly unchanged (payload stays self/orb-only in H4a). If
   `once_per_turn` is added, validate it's a bool and only on reactive kinds (pointless on
   turn_start/end).
6. `card.schema.json` (`mod/contract/` + regen any mirrors under `core/`): add the kinds to the
   `trigger` enum + doc string; add `once_per_turn` to the effect props; note reactive kinds fire
   multiple times/turn → keep payloads small.
7. `cardgen.py` + `validator.py` + `bts1.py`: mirror the trigger set, the `TriggerSentence`
   wording, and the `once_per_turn` field (byte-lockstep — the C#/Python text must match exactly, as
   with #6/#9). Bump the Python vocab-version constant.
8. `mod/contract/VOCABULARY.md`: add the new triggers row + `once_per_turn` note.

### Text/tooltip lockstep
9. Update `TriggerSentence` (C#) and `describe()` (cardgen.py) together; a mismatch is the classic
   lockstep bug. Add a generation test asserting each new trigger's synthesized sentence.

### Cards this unlocks (self/orb payload)
Feel No Pain (`on_exhaust` → block), Dark Embrace (`on_exhaust` → draw), Juggernaut-lite
(`on_block_gained` → self-buff), Rage (`on_card_played` gated to attacks → block), Battle-tempo
draws (`on_card_drawn` / `on_damage_dealt` → small self buffs).

---

## Slice H4b — enemy-target payloads (gap #14)

Goal: let a trigger payload hit enemies (per-turn damage / debuff powers). The engine already does
this for relics — we route card-trigger payloads through the **same** executor.

### Engine
1. In `ForgedTriggerPower`, when a trigger has an enemy-targeted payload, fire via
   **`EffectRunner.RunRelicEffects(payload, ctx, player, targets, relicClass:0)`** instead of
   `TriggerRunner.Run`. Resolve `targets` with the same helper `RelicRunner.ResolveTargets` uses
   (`enemy` = first hittable alive; `all_enemies` = all hittable alive). Self/orb effects in the
   same payload still resolve correctly (RunRelicEffects merges both paths).
2. Add an optional payload-level **`target`** (`enemy` | `all_enemies`) to the trigger; default stays
   self-only (H4a behavior) when absent.

### Vocabulary / validation (still v18, same bump)
3. `card.schema.json` `triggerEffect`: add `target` (`enemy`/`all_enemies`); widen the payload `op`
   enum to allow `damage` and the debuff statuses (`vulnerable`/`weak`/`frail`/`poison`) **only when
   a `target` is present**; keep multi-hit/scale restrictions.
4. `ForgedCards.ValidateTrigger`: replace the blanket "self/orb-only" rule with: if `target` set →
   allow `damage` + enemy-debuff `apply_status`; if no `target` → current self-only rule holds.
   Reject `damage`/enemy-debuff without a `target`, and `target` on a purely-self op.
5. `TriggerFragment`/`TriggerSentence` + cardgen.py: word the targeted forms ("apply 3 Poison to ALL
   enemies", "deal 2 damage to a random enemy"). Lockstep.

### Cards this unlocks
Noxious Fumes (`turn_start` → apply Poison to all_enemies), Combust (`turn_end` → AoE damage), Choke,
Bouncing Flask.

---

## Testing & rollout

1. **Build clean** after each slice (autonomous OK).
2. **Generation tests** (`generation/tests/`): extend `test_validator.py` with accept/reject cases
   per new trigger + `once_per_turn` + (H4b) `target`; assert the 300+ existing tests still pass.
3. **Gap-Tester class:** reuse the reusable Gap-Tester smoke class (seed convention from #6/#9) —
   forge a class whose cards exercise each new trigger; card text must read correctly in-game.
4. **AutoSlay smoke:** **ASK FIRST**, then run a deep-run smoke seed (à la GAPTEST3 for #9) to prove
   many-fire stability + guard integrity + 0 mod exceptions.
5. **Deploy:** btsgen is non-editable in prod → reinstall; website deploy is the git-pull path
   (`/opt/btsweb/deploy.sh`).

## Risks / watch-items
- **H4-0 power-hook dispatch** — RESOLVED (static, 2026-07-01): powers get all six hooks via
  `AbstractModel`; clean overrides, no Harmony fallback. See the H4-0 section.
- **Multi-fire storms** — reactive hooks fire per-card; `once_per_turn` + small payloads are the
  mitigation. Same lesson as #9's re-entrancy guard.
- **Lockstep drift** — C# `TriggerSentence` vs cardgen.py `describe()` must match byte-for-byte.
- **on_block_gained / on_card_drawn ctx** — those relic hooks pass no ctx; reuse the captured-ctx
  trick from `ForgedRelic` (`_combatCtx`).

## Definition of done
`VocabVersion == 18`; six reactive triggers + `once_per_turn` (+ H4b `target`) valid end-to-end
(schema → validator → cardgen → C# runtime → tooltip); generation tests green; Gap-Tester in-game
text correct; AutoSlay deep-run clean (after ask). Then flip #13 and #14 to **done** in
`VOCABULARY_GAPS.md` with the vocab-v18 note.
