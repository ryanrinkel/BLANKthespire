# Tier-A vocab scout: verify-first report (2026-10-01, vocab v60)

This was a read-only scout. No repository file was changed. Paths are abbreviated as follows:

- **MOD** = `BLANKthespire-prod/BLANKthespire/mod/BlankTheSpireCode/`
- **DECOMP** = `BLANKthespire/_modref/decomp_full/`
- **BL** = `BLANKthespire/_modref/BaseLib-StS2/`

Symbol names are authoritative. Line numbers are hints taken from the files as they stand today.

Shared harness and contract touch points per phase follow `VOCAB_EXPANSION_5_PLAN.md` §1. These are not repeated per group. Each phase touches:

- `card.schema.json`: op enum `:35`, scale enum `:52`, status enum `:54`, trigger enum `:56`, and the condition kinds and triggerEffect `target` enum.
- `VOCABULARY.md` rows.
- `bts1.py` (bump `VOCAB_VERSION`).
- `cardgen.describe` / `cond_phrase` / `_trigger_fragment`.
- `validator.py` (shape rules and `_score_effect`).
- `census` / `coverage` / `featured` / `harness_v2` / `gate`.
- `render.js` / `app.js`.

Suggested AutoSlay tags continue the phase letters after BG: BH through BN.

---

## A1. Card `add_trigger` filters (`card_type`, `every_n`), payload `random_enemy`, `this_turn` duration

### Verified surfaces (mod)

**The relic implementation to port (v48 / Phase AS)**

- `Engine/RelicSpec.cs`: `record RelicHook(... string? CardType = null, int EveryN = 0)`.
- `Engine/RelicRunner.cs:28` `Fire(...)`:
  - The `card_type` filter is `if (h.CardType != null && h.CardType != cardType) continue;`.
  - The `every_n` counter keeps a per-hook count in a `Dictionary<int,int> counters`. It advances before `When` and fires on `n % EveryN == 0`.
  - Log tags: `[AS] every_n hook[i] ... count n/N — waiting|FIRES`.
- `Powers/ForgedRelic.cs`:
  - `:44` `_counters` (reset at combat start, `:96`).
  - `:207` `AfterCardPlayed` maps `CardType.Attack/Skill/Power` to `"attack"/"skill"/"power"` and passes it to `FireGuarded`.
  - `:222` `AfterCardDrawn` passes no type today.
  - `:124-136` `ShowCounter` / `DisplayAmount` show the counter on the icon.
- Parse and validation live in `Engine/ForgedCharacters.cs:483-598`: `RelicCardTypes = [attack, skill, power]`, `MinEveryN=2, MaxEveryN=9`, `card_type` is `on_card_played`-only, and `every_n` is rejected on `combat_end`.

**The card side, where the port lands**

- `Powers/ForgedTriggerPower.cs`:
  - `:32` `Trigger` returns the slot's first `add_trigger`.
  - `:59` `StackType` is `Single` (except `ripen`, which is `Counter`).
  - `:166` `AfterCardPlayed` already reads `cardPlay.Card`, so the type filter is one line.
  - `:176` `AfterCardDrawn(ctx, card, fromHandDraw)` already has `card`.
  - `:233` `FireReactive(kind, ctx, attacker)` handles `_firing`, `_firedThisTurn`, `_firedThisCombat` and the `When` gate. **This is the place for the `every_n` counter** (an instance field, a fresh power per combat, the same idea as `_firedThisCombat`).
  - `:72` `AfterSideTurnEnd` already filters `side == Owner.Side`. **This is the place for the `this_turn` removal.**
  - `:63` `DisplayAmount` / `:59` `StackType`: copy the BG ripen trick (make the stack type `Counter` so the icon draws a number) when `every_n > 1`.
- `Engine/ForgedCards.cs`:
  - `ParseEffects` `:1014` already parses `card_type` into `EffectSpec.CardKind`, and `:1015` parses `scope`. `every_n` needs a new parse line next to `:1018` (`count`) and a new `EffectSpec` field (`CardSpec.cs:81-89`, e.g. `int EveryN = 0`).
  - `Validate` `:1073-1076` currently REJECTS `card_type` on any op except `cost_shift`/`exhaust_card`/`draw_until`. Add `add_trigger` there and move the real rule into `ValidateTrigger` (`:1641`).
  - `:1070-1071` also rejects `scope` off `cost_shift`. That only matters if `scope` is reused for `this_turn`.
  - `HandKindFilters` (`:561`) is `[attack, skill, power, non_attack]`. Add `status` for `on_card_drawn` only.
  - `MultiFireTriggers` (`:474`) is the natural legality set for `every_n`.
  - `TriggerSentence` (`:2098`) needs typed / every-N wording (the `on_card_played` case today is the literal "Whenever you play a card").
- Helper to reuse: `EffectRunner.HandKindMatches(CardModel, string?)` (`EffectRunner.cs:663`) already handles `non_attack`. Add `"status" => c.Type == CardType.Status`.

**Payload `random_enemy`**

- `Engine/TriggerRunner.cs:274` `ResolveEnemies(target, player, attacker)` handles `all_enemies` / `attacker` / default first enemy. Add `random_enemy`.
- `ForgedCards.ValidateTrigger` (`:1683-1685`) hard-codes the allowed targets `enemy` / `all_enemies` / `attacker`.
- Relic parity, if wanted: `RelicRunner.ResolveTargets` (`:62`).

### Base API (DECOMP)

- `RagePower` (`Models.Powers/RagePower.cs`): `AfterCardPlayed` filters `cardPlay.Card.Owner == Owner.Player && cardPlay.Card.Type == CardType.Attack`. `AfterSideTurnEnd` calls `PowerCmd.Remove(this)` when `participants.Contains(Owner)`. This is exactly the `this_turn` shape.
- `JuggernautPower.cs:24` / `SerpentFormPower.cs:48` pick a random target with `Owner.Player.RunState.Rng.CombatTargets.NextItem(hittableEnemies)`.
- `PanachePower` (every 5 cards) and `JugglingPower` (3rd Attack) **count per TURN** (they reset at `AfterSideTurnEnd`). The relic `every_n` counts **per COMBAT**.
- `PowerCmd.Remove(PowerModel)` (`Commands/PowerCmd.cs:288`) is public.
- `CardType.Status` exists. `AfterCardDrawn` supplies the drawn `card`.

### Copy-from pattern

- `RelicRunner.Fire` filter and counter → `ForgedTriggerPower.FireReactive` (a new `string? cardType` param, the same as `FireGuarded`).
- `ForgedRelic.AfterCardPlayed` type mapping → the `ForgedTriggerPower.AfterCardPlayed` / `AfterCardDrawn` call sites.
- For `this_turn`: copy `RagePower.AfterSideTurnEnd`. The mod already self-removes in the ripen branch (`Owner.RemovePowerInternal(this)`, `ForgedTriggerPower.cs:~108`). Prefer `PowerCmd.Remove(this)` here so `AfterRemoved` runs.

### Proposed shape and describe

```json
{"op":"add_trigger","trigger":"on_card_played","card_type":"attack","every_n":3,
 "effects":[{"op":"damage","amount":4,"target":"random_enemy"}]}
{"op":"add_trigger","trigger":"on_card_played","card_type":"attack","scope":"this_turn",
 "effects":[{"op":"block","amount":3}]}                       // Rage
{"op":"add_trigger","trigger":"on_card_drawn","card_type":"status","once_per_turn":true,
 "effects":[{"op":"draw","amount":1}]}                         // Iteration
```

Field choice for the duration:

- **Option A (recommended): reuse `scope:"this_turn"`.** It is already parsed, already in the schema `:47`, and its enum already contains the value. Only the `:1070` stray rule needs widening.
- **Option B: a new `duration` field.** Same engine, one more schema field plus a `FIELD_UNITS` entry.

Describe strings. These are lockstep pairs, `TriggerSentence` with `cardgen._trigger_fragment` / `trigger_sentence`.

Typed `when` heads:

- "Whenever you play an Attack"
- "Whenever you play a Skill"
- "Whenever you play a Power"
- "Whenever you play a non-Attack card"
- "Whenever you draw a Status"

Every-N heads (`n` is ordinal; per-combat wording):

- "Every 3rd time you play an Attack"
- "Every 5th card you play"

Duration prefix: "This turn, whenever you play an Attack, gain 3 Block."

Payload target: `to = " to a random enemy"`, giving "deal 4 damage to a random enemy". This is the existing `TriggerFragment` `to` switch at `:2141`.

### Risks and blockers

1. **Per-combat vs per-turn counting.** The relic is per combat; Panache and Juggling are per turn. Recommend per-combat (lockstep with the relic, no new reset logic). An optional `every_n` + `once_per_turn` is NOT a substitute.
2. **Stacking.** `StackType Single` (`:59`) means a second Rage played the same turn does NOT double the payload: the payload amounts are literal. Base `RagePower` is `Counter`. The choice is to accept this and price accordingly, or for `this_turn` powers to multiply payload amounts by `Amount` (a small `TriggerRunner` change). Flag it as an open decision.
3. **Self-trigger.** The granted power is live when the granting card's own `AfterCardPlayed` hook dispatches. A filter equal to the granting card's own type (or no filter) will count or fire on itself. This is already true of unfiltered `on_card_played` today. Verify in the `[H4]` log, and decide whether to skip `cardPlay.Card == granting card` (the power has no handle to it today, so it would need `SourceSpec.Id` vs `DataCard.SpecId`).
4. **Contract conflict.** `card_type` on `add_trigger` collides with the `:1073` "stray field" rule and with `validator.py`'s equivalent. Both need widening.
5. **`every_n` with `once_per_combat`:** reject the combination (it is meaningless).

**Effort:** about 6 to 8 h engine and contract, plus about 4 h harness.

**AutoSlay tag:** `[BH] card_type <kind> matched` and `[BH] every_n <kind> count n/N — waiting|FIRES` (mirroring `[AS]`); `[BH] this_turn trigger removed at turn end`; `[BH] random_enemy payload -> <monster>`.

---

## A2. New `scale` sources, `gain_energy scale:"energy"`, and `draw` to hand size N

### How existing scales resolve (mod)

- `EffectRunner.ScaleValue(string? scale, CardModel card)` (`EffectRunner.cs:1040-1056`) is the **single source of truth** for player-level reads. It is used by the executor and by `DataCard.BonusFor` (`DataCard.cs:59-73`) for calc-var previews.
  - `plays_this_combat` → `CardsPlayedThisCombat(player)` (`:1071`) = `CombatManager.Instance.History.CardPlaysFinished.Count(entry.CardPlay.Card.Owner == player)`.
  - `hp_lost_this_turn` → `HpLossTracker.HpLostThisTurn` (a mod tracker, not History).
  - `cards_retained` → `HandStateTracker.CardsRetained`.
  - `target_debuff_count` **bypasses `ScaleValue`**: `DataCard.BonusFor` uses the calc-var's `(card, target)` second arg, `(_, tgt) => EffectRunner.DebuffCount(tgt)` (`DataCard.cs:68`, `EffectRunner.cs:1145`). **This is the template for per-target stack reads.**
  - `damage_dealt_unblocked` is execution-ordered: the local `unblockedDealt` in `Execute` (`:64`) is summed from `atk.Results` (`:140-142`) and is heal-only (`:194`).
- Validation:
  - `SupportedScales` `:607`, `DamageBlockOnlyScales` `:616`, `TriggerScales` `:622` (payload-legal subset).
  - The per-scale op rules are at `ForgedCards.cs:1100-1145`; the catch-all `'scale' only applies to damage/block/draw` is at `:1134`.
  - `ScalePhrase` `:1912` and `TriggerScalePhrase` `:2127`.
  - `PhaseAmScales` `:1059` drives the `[AM]` play-time log.
  - The cost-0 rule for `energy` is in `TryBuildSpec` `:843-844` and currently applies to every op.
- Executor sites:
  - `draw` scaled `EffectRunner.cs:153-165`.
  - `gain_energy` `:187-189` (`PlayerCmd.GainEnergy(amt, owner)`; no scale path).
  - `DataCard.DeclareEffects`: `gain_energy` always declares `WithEnergy(e.Amount, up)`; a scaled draw declares no var.

### DECOMP History and base recipes per new source (all verified)

All History reads use `CombatManager.Instance.History.Entries.OfType<T>()`, `public IEnumerable<CombatHistoryEntry> Entries` (`Combat.History/CombatHistory.cs:24`).

| proposed scale | base recipe (verbatim read) | entry class / API |
|---|---|---|
| `exhaust_pile_size` | `AshenStrike`: `PileType.Exhaust.GetPile(card.Owner).Cards.Count` | pile read |
| `discards_this_turn` | `MementoMori`: `OfType<CardDiscardedEntry>().Count(e => e.HappenedThisTurn(card.CombatState) && e.Card.Owner == card.Owner)` | `CardDiscardedEntry.Card` |
| `cards_drawn_this_turn` | `DeathMarch`: `OfType<CardDrawnEntry>().Count(e => e.HappenedThisTurn(cs) && e.Actor == owner.Creature && !e.FromHandDraw)` | `CardDrawnEntry.FromHandDraw` (base EXCLUDES the hand draw) |
| `cards_drawn_this_combat` | `Murder`: `OfType<CardDrawnEntry>().Count(e => e.Actor == owner.Creature)` | |
| `energy_spent_this_turn` | `HelixDrill`: `OfType<EnergySpentEntry>().Where(HappenedThisTurn && e.Actor.Player == owner).Sum(Amount)`, **minus this card's own cost when `card.Pile.Type == PileType.Play`** (keeps preview == resolve) | `EnergySpentEntry.Amount` |
| `hp_loss_events_this_combat` | `TearAsunder`: `OfType<DamageReceivedEntry>().Count(e => e.Receiver == owner.Creature && e.Result.UnblockedDamage > 0)` | `DamageReceivedEntry.Receiver/Result` |
| `cards_generated_this_combat` | `Supermassive`: `OfType<CardGeneratedEntry>().Count(c => c.Creator == card.Owner)` | `CardGeneratedEntry.Creator` |
| `discard_pile_size` | `Stack`: `PileType.Discard.GetPile(card.Owner).Cards.Count()` | pile read |
| `total_enemy_poison` | `Mirage`: `card.CombatState?.Enemies.Where(IsAlive).Sum(c => c.GetPowerAmount<PoisonPower>())` | |
| `target_status_stacks` + `status` | `Bully`: `target?.GetPowerAmount<VulnerablePower>()`; `TimesUp`: `target?.GetPowerAmount<DoomPower>()` | per-target calc-var arg |
| `gain_energy scale:energy` | `DoubleEnergy`: `PlayerCmd.GainEnergy(Owner.PlayerCombatState.Energy, Owner)` (cost 1, upgrade 0) | `PlayerCmd.GainEnergy(decimal, Player)` (`PlayerCmd.cs:29`) |
| `draw` to hand size | `Expertise`: `Math.Max(0, Cards - Hand.Cards.Count)` then `CardPileCmd.Draw(ctx, count, Owner)` (NO explicit clamp; Draw handles a full hand) | `CardPileCmd.Draw(ctx, decimal, Player, bool)` (`CardPileCmd.cs:800`) |

The entry helpers `HappenedThisTurn(ICombatState)` and `HappenedLastPlayerTurn(Player)` are public (`Combat.History/CombatHistoryEntry.cs:62, 99`). `PlayerCombatState.ExhaustPile` / `DiscardPile` are readable (the `SoulStorm` recipe).

### Copy-from pattern

- Player-level sources: add a branch to `ScaleValue` (with helpers next to `CardsPlayedThisTurn` `:1081`). `DataCard.BonusFor` picks them up for free.
- `target_status_stacks`: add a `DataCard.BonusFor` branch `(_, tgt) => EffectRunner.StatusStacks(tgt, e.Status)`, copying `target_debuff_count`, including its rules: single-target only (`ForgedCards.cs:1184-1192` random_enemy rejection), damage/block only, not in triggers.
- `gain_energy`:
  1. In `DataCard`, skip `WithEnergy` when scaled.
  2. Add a scaled branch at `EffectRunner.cs:187`.
  3. At `:1134`, allow `gain_energy` for `energy` only.
  4. **Narrow the cost-0 rule** (`:843`) to damage/block/draw. A `gain_energy` has no calc-var preview, and the base `DoubleEnergy` reads post-pay energy on a 1-cost card.
- `draw` to N: add a new scale such as `to_hand_size` whose `amount` IS the target size. In `EffectRunner.cs:153`: `n = Math.Max(0, amt - owner.PlayerCombatState.Hand.Cards.Count)`. The card itself is already in the Play pile at `OnPlay`, the same as `Expertise`. Keep `WithCards` declared so the upgrade-aware `{Cards}` prints; `VarKey` (`:1873`) must return `Cards` for this scale.

### Proposed shape and describe

```json
{"op":"damage","amount":0,"scale":"exhaust_pile_size"}
{"op":"damage","amount":0,"scale":"target_status_stacks","status":"vulnerable"}
{"op":"gain_energy","amount":1,"scale":"energy"}
{"op":"draw","amount":6,"scale":"to_hand_size"}
```

`ScalePhrase` additions (used by "Deal damage equal to …" / "Gain Block equal to …"):

- `exhaust_pile_size`: "the cards in your exhaust pile"
- `discards_this_turn`: "the cards you have discarded this turn"
- `cards_drawn_this_turn`: "the cards you have drawn this turn" (if it excludes the hand draw: "… drawn this turn outside your turn-start draw")
- `cards_drawn_this_combat`: "the cards you have drawn this combat"
- `energy_spent_this_turn`: "the energy you have spent this turn"
- `hp_loss_events_this_combat`: "the times you have lost HP this combat"
- `cards_generated_this_combat`: "the cards you have created this combat"
- `discard_pile_size`: "the cards in your discard pile"
- `total_enemy_poison`: "the total Poison on ALL enemies"
- `target_status_stacks`: "the enemy's {Status}" (e.g. "the enemy's Vulnerable")

Other describe strings:

- `gain_energy scale:energy`: "Double your energy." (or "Gain energy equal to your energy.")
- `draw to_hand_size`: "Draw cards until you have {Cards} in hand."

### Risks and blockers

1. Every new History source is a replace-semantics calc-var. The **one-calc-var-per-card** budget (`ForgedCards.cs:1416-1420`; BaseLib `ConstructedCardModel.WithCalculatedDamage` throws on a second) still holds.
2. Several of these reads scale without bound: `cards_drawn_this_combat`, `hp_loss_events_this_combat`, `cards_generated_this_combat`, `total_enemy_poison`. Base cards use them as `base + N×count` (`CalculationBaseVar` + `ExtraDamageVar`). Our `scale` is **replace-semantics**, so `Murder` (1 + count) and `MementoMori` (9 + 4×count) need an ADDITIVE / multiplier form to be faithful.
   - Recommendation: ship them replace-semantics first, damage/block only, priced as late-game.
   - Follow-up: an `additive` flag like `forged` / `tag_cards_owned`.
3. `energy_spent_this_turn` must subtract the card's own cost while it is in the Play pile, or the preview and the resolved number disagree (the `HelixDrill` code).
4. `discards_this_turn` counts effect discards only. The end-of-turn flush goes through `CardPileCmd.Add`, not `CardCmd.Discard`, so it is not logged as a discard. That matches the base game.
5. `target_status_stacks` needs `status` allowed on damage/block. There is no generic "status only on apply_status" rule in C#, but `validator.py` and the schema `if/then` likely have one; check `card.schema.json:68`.
6. Payload legality: start card-only (not in `TriggerScales`), except maybe `total_enemy_poison` / `exhaust_pile_size`, which are pure player reads.

**Effort:** about 8 to 10 h for C# (10 sources are about 20 lines each, plus `BonusFor` and validator), plus about 4 h harness and describe.

**AutoSlay tag:** `[BI] scale <name> -> <n> (<op>, '<card>')`, extending the `[AM]` line via `PhaseAmScales`-style membership. Also `[BI] draw to_hand_size: hand <h> -> draw <n>` and `[BI] gain_energy x energy: <e> -> +<e>`.

---

## A3. New `when` kinds: `exhausted_this_turn`, `target_intends_attack`, `target_killed`, `played_cards_last_turn_ge`

### Verified surfaces (mod)

- `Engine/Conditions.cs`: `Kinds` `:23-33`, `TargetKinds` `:39` (single-enemy-only reads), `Validate` `:50-77` (the value ≥ 1 list `:56-64`, caps `:66-69`), `Evaluate(c, card, ctx, play)` `:82` → `Evaluate(c, player, target)` `:95` → `Eval` switch `:101-157`, `Phrase` `:171-195`.
- `ForgedCards.Validate`:
  - `:1195` rejects a `TargetKinds` gate on a non-`enemy` card.
  - `ValidateTrigger`'s tail (just before `:1838`'s return) rejects `target_has_status` / `retained_last_turn` / `TargetKinds` in a trigger `when`.
- `EffectRunner.Execute` gate: `:70-92` (calls `Conditions.Evaluate(e.When, card, ctx, play)`; logs `[AD]`/`[AM]`/`[BB]`).
- The damage case holds `var atk = CommonActions.CardAttack(card, play, hits); await atk.Execute(ctx);` and already walks `atk.Results` for `unblockedDealt` (`EffectRunner.cs:136-142`). **This is the hook for `target_killed`.** Effects run strictly in list order in one `for` loop (`:65`), so a later effect can read a local set by an earlier damage op.

### Base API (DECOMP)

**`target_intends_attack`**

- `MonsterModel.IntendsToAttack` (`Models/MonsterModel.cs:384`), public: `NextMove.Intents.Any(IntentType.Attack || IntentType.DeathBlow)`.
- `NextMove` defaults to `new MoveState()`, so it is never null.
- `GoForTheEyes.cs:49`: `if (cardPlay.Target.Monster.IntendsToAttack)`. Use `target?.Monster?.IntendsToAttack ?? false` (a pet or player has no Monster).

**`target_killed`**

- `AttackCommand.Results` is `IEnumerable<List<DamageResult>>` (`Commands.Builders/AttackCommand.cs:144`).
- `DamageResult.WasTargetKilled` is `{ get; init; }` (`Entities.Creatures/DamageResult.cs:99`); `Receiver` is at `:14`.
- Base `Feed` / `HandOfGreed` / `Sunder` / `KnockoutBlow`: `attackCommand.Results.SelectMany(r => r).Any(r => r.WasTargetKilled)`.
- **Feed and HandOfGreed also gate on** `cardPlay.Target.Powers.All(p => p.ShouldOwnerDeathTriggerFatal())`, computed BEFORE the attack. `PowerModel.ShouldOwnerDeathTriggerFatal()` (`Models/PowerModel.cs:646`) is virtual, and `MinionPower` / `ReattachPower` override it, so killing a minion or a reattaching part does not pay out.

**`exhausted_this_turn`**

- `EvilEye.cs:25`: `History.Entries.OfType<CardExhaustedEntry>().Any(e => e.HappenedThisTurn(CombatState) && e.Card.Owner == Owner)`.

**`played_cards_last_turn_ge`**

- `PaleBlueDotPower.cs:31`: `History.CardPlaysFinished.Count(c => c.HappenedLastPlayerTurn(player) && c.CardPlay.Card.Owner == Owner.Player)`.
- `HappenedLastPlayerTurn(Player)` is public (`CombatHistoryEntry.cs:99`).

### Copy-from pattern

- `exhausted_this_turn` / `played_cards_last_turn_ge`: copy `cards_played_this_turn_ge` (a `Conditions.Eval` case with an `EffectRunner` helper like `CardsPlayedThisTurn` `:1081`, a value cap like `CardsPlayedGeMax`, and the `[AM]` log). Both are player reads, so they are legal on cards AND as a trigger fire-time gate.
- `target_intends_attack`: copy `target_has_block` (`Conditions.cs:145`). Add it to `TargetKinds`, which gives the single-enemy-only and no-trigger rules automatically.
- `target_killed`: it **cannot** live in `Conditions.Eval`, which has no play-local state.
  - Add `bool killedThisPlay` next to `unblockedDealt` (`EffectRunner.cs:64`).
  - After each damage op, OR in `atk.Results.SelectMany(r=>r).Any(r => r.WasTargetKilled && r.Receiver.Powers.All(p => p.ShouldOwnerDeathTriggerFatal()))`.
  - In the gate (`:72`), special-case `e.When.Kind == "target_killed"` → `gateOpen = killedThisPlay ^ negate`.
  - Validation copies the `damage_dealt_unblocked` ordering rule: legal only on an effect AFTER a `damage` op in the same list, never on `add_trigger`, never in a trigger `when` or an orb `when` (add it to the rejection lists). `Conditions.Eval` default returns false, which is a harmless fallback.

### Proposed shape and describe

```json
{"op":"gain_max_hp","amount":3,"when":{"kind":"target_killed"}}           // Feed
{"op":"apply_status","status":"weak","amount":1,"when":{"kind":"target_intends_attack"}}  // Go for the Eyes
{"op":"block","amount":5,"when":{"kind":"exhausted_this_turn"}}           // Evil Eye (2nd copy)
{"op":"draw","amount":2,"when":{"kind":"played_cards_last_turn_ge","value":5}}
```

`Phrase` strings (lockstep with `cardgen.cond_phrase`):

- `target_killed`: "this kills the enemy" → "Gain 3 Max HP if this kills the enemy." Negated: "unless this kills the enemy".
- `target_intends_attack`: "the enemy intends to attack"
- `exhausted_this_turn`: "you have Exhausted a card this turn"
- `played_cards_last_turn_ge`: "you played {N}+ cards last turn"

### Risks and blockers

1. **`target_killed` on AoE / random_enemy cards.** Results span every target. Recommend allowing it with "any kill" semantics ("if this kills an enemy"), with the phrase switched on the card target. Or restrict it to single-enemy cards (the Feed shape) for v1.
2. Multi-hit: `WasTargetKilled` is set on the killing hit only, and `SelectMany` covers it.
3. `gain_max_hp` is run-permanent. Gating it on a kill makes it Feed-exact; reprice it in `validator._score_effect` (the expected value goes up).
4. `target_intends_attack` is read at play time against the shown intent, which is fine. It has no meaning in triggers; `TargetKinds` already forbids that.
5. The audit's buildability note matches. No contradiction.

**Effort:** about 5 to 6 h C# plus about 3 h harness.

**AutoSlay tag:** `[BJ] target_killed gate OPEN|closed (killed=<bool>, fatal=<bool>)`; `[BJ] target_intends_attack gate … (intent <types>)`; reuse the `[AM]` gate line via `PhaseAmConditions` for the two player reads.

---

## A4. `hits_scale`: hit count from a scale source (including `x`)

### Verified surfaces (mod)

- Hits today:
  - `DataCard.DeclareEffects` `:164`: `if (e.Hits > 1) WithVar("Hits", e.Hits, HitsUpgradeDelta)`.
  - `EffectRunner.cs:99`: `int hits = card.DynamicVars.TryGetValue("Hits", out var hv) ? (int)hv.BaseValue : 1;`.
  - `:136`: `CommonActions.CardAttack(card, play, hits)`.
  - The trigger payload loops `CreatureCmd.Damage` `hits` times (`TriggerRunner.cs:~85`).
- **`hits` + `scale` is rejected** at `ForgedCards.cs:1143-1144` (card) and at `ValidateTrigger ~:1732` (payload). `validator.py:706-707` and `:1094-1095` mirror both.
- One multi-hit damage per card: `ForgedCards.cs:1413-1415` (`validator.py:754`).
- X coupling: `TryBuildSpec :834-838` (`anyX = effects.Any(e => e.ScaleX)`; X-cost requires a `scale:x` effect and vice versa).
- **There is no multi-hit cap** anywhere (C#, schema `hits.minimum: 2` only, or `validator.py`). Pricing multiplies `amount × hits` (`validator.py:1338`).

### Base API (DECOMP) and BaseLib

- `AttackCommand.WithHitCount(int)` (`AttackCommand.cs:476`). Execute runs `Hook.ModifyAttackHitCount(...)`, and 0 hits is a clean no-op loop.
- Base recipe (`Finisher`, `Flechettes`, `TearAsunder`, `HelixDrill`, `PullFromBelow`): `new CalculatedVar("CalculatedHits").WithMultiplier(...)`, then `DamageCmd.Attack(Damage.BaseValue).WithHitCount((int)((CalculatedVar)DynamicVars["CalculatedHits"]).Calculate(target))`.
- X recipe (`Whirlwind`, `Skewer`): `WithHitCount(ResolveEnergyXValue())`.
- BaseLib `ConstructedCardModel.WithCalculatedVar(string name, int baseVal, Func<CardModel,Creature?,decimal> bonus, …)` (`BL/Abstracts/ConstructedCardModel.cs:152`) creates a `CustomCalculatedVar(name)` with keys `{name}Base` / `{name}Extra` (`SetupCalculatedVar :274-299`). **It does NOT trip `_hasBasegameCalculatedVar`**, so `CalculatedHits` coexists with a `CalculatedDamage` and stays outside the one-calc-var budget.
- `CommonActions.CardAttack(card, play, int hitCount)` (`BL/Utils/CommonActions.cs:32/47`) passes `hitCount` straight to `WithHitCount`.

### Copy-from pattern

- `DataCard`: `if (e.HitsScale != null) WithCalculatedVar("CalculatedHits", 0, (c, t) => EffectRunner.ScaleValue(e.HitsScale, c));`. For `x`, `ScaleValue("x")` is already `ResolveEnergyXValue()`.
- `EffectRunner`: `hits = e.HitsScale != null ? Math.Min(HitsScaleCap, (int)((CalculatedVar)card.DynamicVars["CalculatedHits"]).Calculate(play?.Target)) : <existing>`. If 0, log and skip the attack (do not play an empty swing).

### Proposed shape and describe

```json
{"op":"damage","amount":5,"hits_scale":"x"}                                  // Whirlwind (cost "X", target all_enemies)
{"op":"damage","amount":6,"hits_scale":"attacks_played_this_turn"}           // Finisher
{"op":"damage","amount":4,"hits_scale":"cards_in_hand"}
```

- A new EffectSpec field `HitsScale` (`string?`). It is mutually exclusive with `hits` > 1, with `scale` (initially), and with `grow` / `grow_held`. It counts as THE card's one multi-hit. `x` participates in the X coupling (`anyX` must include `e.HitsScale == "x"`).
- Allowed sources:
  - v1: `x`, `cards_in_hand`, `plays_this_combat`.
  - New: `attacks_played_this_turn` (the `Finisher` read, i.e. `CardsPlayedThisTurn` + a `Type == Attack` filter) and `skills_in_hand` (`Flechettes`).
  - From A2: `exhaust_pile_size`, `hp_loss_events_this_combat`, `energy_spent_this_turn`.
  - `orb_count`.
- Describe: x → "Deal {Damage} damage X times{suffix}." Others → "Deal {Damage} damage for each {noun}{suffix}." This needs a small `HitsPhrase` table, e.g. "Attack you played this turn", "other card in your hand", "card in your exhaust pile". Optionally append "({CalculatedHits} times)", which tracks live in hand.

### Risks and blockers

1. **Cap.** No cap exists today. A replace-semantics count like `plays_this_combat` can reach 20+ hits: animation-time and AutoSlay timeout risk. Recommendation: a runtime clamp (e.g. 10, logged) plus validator pricing at the expected count.
2. `damage_dealt_unblocked` lifesteal and `target_killed` already sum over `atk.Results`, so they work unchanged.
3. Upgrades: `hits_scale` has no upgrade delta. Upgrade the per-hit damage only (`Damage` var).
4. Contract churn: one new FIELD (schema `additionalProperties:false` at `:32`, `gate.FIELD_UNITS`, `census` counter, `bridges.card_tokens`).
5. Audit check: "`hits_scale` fixes both" holds. Note that `scale` on the AMOUNT plus `hits_scale` together is out of v1.

**Effort:** about 5 h C# plus about 3 h harness.

**AutoSlay tag:** `[BK] hits_scale <src> -> <n> hits (cap <c>) x <dmg> from '<card>'`.

---

## A5. Enemy Strength loss (temporary and permanent), `lose_block`, remove Artifact

### Base API (DECOMP), verified

- `StrengthPower` (`Models.Powers/StrengthPower.cs`): sealed, `StackType Counter`, **`AllowNegative => true`**, with no owner-side restriction. Base `Malaise.cs:40` applies `PowerCmd.Apply<StrengthPower>(ctx, cardPlay.Target, -powerAmount, Owner.Creature, this)` to monsters; `Resonance.cs:33` and `SharedFate.cs:39` do the same.
- `PowerModel.GetTypeForAmount(decimal)` (`Models/PowerModel.cs:460`): Counter + AllowNegative + amount < 0 → `PowerType.Debuff`. So **`ArtifactPower.TryModifyPowerAmountReceived` blocks negative Strength** and consumes a stack, which is correct behaviour.
- `TemporaryStrengthPower` (`Models.Powers/TemporaryStrengthPower.cs`) is **abstract**:
  - It has an abstract `OriginModel` and `protected virtual bool IsPositive => true`.
  - `Type` is Debuff when `!IsPositive`.
  - `BeforeApplied` applies `StrengthPower` at `Sign*amount`.
  - `AfterSideTurnEnd` removes when `participants.Contains(Owner)`, i.e. at the end of the OWNER's side turn. For an enemy that is the end of the enemy's turn, the right window.
  - Concrete base subclasses: `PiercingWailPower`, `DarkShacklesPower`, `ManglePower`, `EnfeeblingTouchPower`, `CrushUnderPower`. Each is `class X : TemporaryStrengthPower { OriginModel => ModelDb.Card<X>(); IsPositive => false; }` and none is sealed.
- `CreatureCmd.LoseBlock(Creature creature, decimal amount)` (`Commands/CreatureCmd.cs:666`), public static async. Base `Expose.cs:39`: `LoseBlock(target, target.Block)`.
- `PowerCmd.Remove<T>(Creature) where T : PowerModel` (`Commands/PowerCmd.cs:279`) = `Remove(creature.GetPower<T>())`, which is null-safe. Base `Expose.cs:40-43` guards with `HasPower<ArtifactPower>()`.

### Mod: how `temp_strength` is done (the gap #26 pattern)

- `Powers/ForgedTempStatPowers.cs:26`: `abstract class ForgedTempStatPower : CustomTemporaryPowerModel` (BaseLib). Its concrete `ForgedTempStrengthPower` (`:57`) has `InternallyAppliedPower => ModelDb.Power<StrengthPower>()` and `ApplyInternal` → `PowerCmd.Apply<StrengthPower>` via `BetaMainCompatibility`, with in-code `PowerLoc` and an icon. It auto-registers via the ICustomPower scan.
- BaseLib `CustomTemporaryPowerModel` (`BL/Abstracts/CustomTemporaryPowerModel.cs`):
  - It has **`protected virtual bool InvertInternalPowerAmount => false`**. When true, it applies `-amount` and restores `+Amount` at turn end, so the down version is built in.
  - It removes at `AfterSideTurnEnd` when `participants.Contains(Owner) != UntilEndOfOtherSideTurn` (default: the owner's own side, matching base).
  - **However**, `Type => InternallyAppliedPower.Type`, which is Buff (StrengthPower's canonical type).

### Copy-from pattern

```csharp
public sealed class ForgedTempStrengthDownPower : ForgedTempStatPower {
  public override PowerModel InternallyAppliedPower => ModelDb.Power<StrengthPower>();
  protected override bool InvertInternalPowerAmount => true;
  public override PowerType Type => PowerType.Debuff;   // REQUIRED, see risk 1
  protected override Task ApplyInternal(...) => PowerCmd.Apply<StrengthPower>(...);  // same as ForgedTempStrengthPower
  protected override string? ExpiryLogTag => "[BL] temp_strength_down";
  // PowerLoc "Strength Down" / icon
}
```

Wiring:

- Card: `DataCard` `Power<ForgedTempStrengthDownPower>(vname, amt, up)`; `EffectRunner.ApplyStatus` (`:1228`) → `ApplyPower<…>(self:false…)`.
- Payload: `TriggerRunner.ApplyDebuff` (`:285`).
- Relic: `EffectRunner.RelicApply` (`:1517`).
- Sets: `ForgedCards.EnemyDebuffStatuses` (`:509`) and `SupportedStatuses` (`:510`); `StatusDisplay` (`:1890`).

**Permanent Strength loss: do NOT reuse `Power<StrengthPower>`.** `CommonActions.Apply<StrengthPower>` reads the card's positive `PowerVar<StrengthPower>`, which would GIVE the enemy Strength. It would also collide (duplicate var key) with a self-`strength` on the same card.

- Declare `WithVar("StrengthLoss", amt, up)` (the base `PiercingWail` / `DarkShackles` var name).
- Apply through the literal path `RelicApplyT<StrengthPower>(ctx, target, owner, -amt)` (the `AX` second-status path at `EffectRunner.cs:174-182` shows the literal-apply idiom).

**`lose_block` / remove Artifact** are new flag ops in `EffectRunner`: `await CreatureCmd.LoseBlock(t, t.Block)` and `if (t.HasPower<ArtifactPower>()) await PowerCmd.Remove<ArtifactPower>(t)` over `CustomStatusTargets(card, play)` (`:1225`). Card-only. Put them BEFORE the debuff in effect order (the `Expose` order).

### Proposed shape and describe

```json
{"op":"apply_status","status":"temp_strength_down","amount":6}     // Piercing Wail (all_enemies) / Dark Shackles
{"op":"apply_status","status":"strength_down","amount":2}          // Malaise / Shared Fate (permanent)
{"op":"strip_block"}  {"op":"strip_artifact"}                      // Expose (then apply vulnerable)
```

Describe strings:

- `temp_strength_down`: "Apply Strength Down." (the `apply_status` idiom); power tooltip "Loses {N} Strength until the end of its turn."
- `strength_down`: "The enemy loses {StrengthLoss} Strength." / "ALL enemies lose {StrengthLoss} Strength."
- `strip_block`: "Remove all of the enemy's Block."
- `strip_artifact`: "Remove the enemy's Artifact."

### Risks and blockers

1. **An Artifact exploit if `Type` is not overridden.** If the temp-down shell stays a Buff, Artifact blocks only the inner `-N StrengthPower`. The shell survives, and at turn end it applies **+N Strength**, so the enemy nets a GAIN. Base `PiercingWailPower` avoids this because its own `Type` is Debuff, so Artifact eats the whole thing. **The override is mandatory**, and it needs an Artifact-enemy test in AutoSlay.
2. **Multiplayer scaling.** `PowerCmd.Apply` scales debuffs on enemies by player count only when `ShouldScaleInMultiplayer`; StrengthPower does not. Multiplayer is out of scope anyway.
3. **`spread_debuffs` / `DebuffCount` / `target_has_status`** know only 4 debuffs (`EffectRunner.cs:1101-1156`, `Conditions.StatusChecks :47`). Decide whether Strength Down counts. Base Misery does copy it; that is what `IgnoreNextInstance` handles.
4. **Option B (zero-code temp):** apply base `PiercingWailPower` directly. It is concrete, registered and public, but the tooltip title would read "Piercing Wail". Not recommended.
5. The audit note "Custom statuses can't do it: `damage_dealt` is buff-only" is consistent with this finding.

**Effort:** about 5 to 6 h C# plus about 3 h harness.

**AutoSlay tag:** `[BL] temp_strength_down +N on '<monster>' (Str now <s>)`, `[BL] temp_strength_down expired`, `[BL] strength_down -N`, `[BL] strip_block <b>->0`, `[BL] strip_artifact (had <n>)`.

---

## A6. `doom` as an enemy debuff

### Base API (DECOMP), verified

- `DoomPower` (`Models.Powers/DoomPower.cs`): **sealed and concrete**, `Type Debuff`, `StackType Counter`, with the default ctor (it is created via `ModelDb.Power<T>().ToMutable()` like every power).
  - It kills in `BeforeSideTurnEnd(ctx, side, participants)`: when the owner's side ends its turn, the owner is alive, and `IsOwnerDoomed()` (`CurrentHp <= Amount`) holds, it batch-kills every doomed creature on that side via `public static DoomKill(IReadOnlyList<Creature>)` → `CreatureCmd.Kill` + `Hook.AfterDiedToDoom`.
  - It does not decay or tick down; stacks persist.
  - **It is fully generic.** There is no Necrobinder, Osty, or player-side state, and it works on any owner. Necrobinder cards apply it with plain `PowerCmd.Apply<DoomPower>(ctx, target, amount, Owner.Creature, this)` (`NoEscape.cs:44`).
  - `PlayVfx` handles `Hook.ShouldDie` / `ShouldDisappearFromDoom`, so bosses and revivers are respected.
- Doom reads: `TimesUp` damage = `target?.GetPowerAmount<DoomPower>()`; `NoEscape` doom = 10 + 5 × (Doom / 10).

### How the mod applies base debuffs today

- Card: `DataCard.DeclareEffects` `apply_status` → `Power<VulnerablePower>(vname, amt, up)` (`DataCard.cs:~235`). `EffectRunner.ApplyStatus` (`:1228`) → `ApplyPower<T>(self, card, ctx, play)` → `CommonActions.Apply<T>(ctx, card, play)` (BaseLib reads the card's `PowerVar<T>`).
- Gated second copy: the literal `RelicApply` (`:1517`).
- Payload: `TriggerRunner.ApplyDebuff` (`:285`), a 4-case switch → `ApplyTo<T>` → `BetaMainCompatibility.PowerCmd_.Apply.InvokeGeneric`.
- Relic: `ApplyRelicStatus` (`:1497`) → `RelicApply`.
- Sets: `ForgedCards.EnemyDebuffStatuses = [vulnerable, weak, frail, poison]` (`:509`, used for payload targeted apply legality at `:1691`); `SupportedStatuses` (`:510`); `Conditions.StatusChecks` (`:47`) and `TargetHasStatus` (`:160`); `EffectRunner.DebuffCount` (`:1145`) and `SpreadDebuffs.Take<>` (`:1101`).

### Copy-from pattern

Copy `poison` exactly, adding `"doom"` at every site:

- `DataCard` `Power<DoomPower>`
- `ApplyStatus` / `ApplyDebuff` / `RelicApply`
- `EnemyDebuffStatuses`, `SupportedStatuses`, `StatusDisplay` ("Doom")
- `StatusChecks` + `TargetHasStatus`
- `DebuffCount` + `SpreadDebuffs` (optional)
- the schema status enum `:54`

The scale `target_status_stacks status:doom` comes from A2 (`TimesUp`).

**Doom = damage dealt** (`BlightStrike`): widen `damage_dealt_unblocked` (heal-only today, `ForgedCards.cs:1107-1110`, `EffectRunner.cs:194`) to `apply_status status:doom`, applied through the literal `RelicApply` with `unblockedDealt`. The PowerVar path cannot carry a play-time number.

### Proposed shape and describe

```json
{"op":"apply_status","status":"doom","amount":7}
{"op":"damage","amount":6},{"op":"apply_status","status":"doom","amount":0,"scale":"damage_dealt_unblocked"}   // Blight Strike
{"op":"damage","amount":0,"scale":"target_status_stacks","status":"doom"}  // Time's Up (A2)
{"op":"damage","amount":12,"when":{"kind":"target_has_status","status":"doom"}}
```

Describe strings:

- "Apply Doom." (the `apply_status` idiom)
- "Apply Doom equal to the unblocked damage dealt."
- condition phrase "the enemy has doom" (the existing `target_has_status` phrase is lowercase `{c.Status}`)

VOCABULARY row: "`doom` | debuff | If the target's HP is at or below its Doom at the end of ITS turn, it dies. Doom never decays."

### Risks and blockers

1. **Balance.** Doom never decays, so stacking it is a guaranteed execute. It needs a pricing band and per-class caps (`validator._score_effect`). The kill happens at the end of the ENEMY turn, so the enemy still acts once.
2. **Doom triggers** (`ShroudPower`: on Doom applied → Block; `CountdownPower`) are not in Tier A. `Hook.AfterDiedToDoom` is the hook if an `on_doom_kill` trigger is wanted later.
3. Lowercase "doom" in the `target_has_status` phrase. Cosmetic; it matches existing behaviour.
4. The audit note ("Small; DoomPower concrete") is confirmed.

**Effort:** about 3 to 4 h C# plus about 3 h harness (the BlightStrike widening is about 1 h more).

**AutoSlay tag:** `[BM] doom +N on '<monster>' (HP <hp>, Doom <d>, doomed=<bool>)`. The kill itself shows in godot.log as a creature death with no mod exception; optionally add a `[BM]` line from a DataCard `AfterDiedToDoom` override, since `Hook.AfterDiedToDoom` reaches card listeners like `AfterCardDiscarded`.

---

## A7. Self-drawback debuffs on the player

### Base API (DECOMP), verified constructors and semantics

All are `sealed class X : PowerModel` with the default ctor, applied via `PowerCmd.Apply<T>(ctx, owner.Creature, amount, owner.Creature, card)`. All are `Type Debuff`.

| power | stack | behaviour | removal | base card |
|---|---|---|---|---|
| `NoDrawPower` | Single | `ShouldDraw(player, fromHandDraw)` → false for non-hand-draw draws of `Owner.Player` | `AfterSideTurnEnd` owner's side → Remove | `BattleTrance.cs:23`, `BulletTime` |
| `NoEnergyGainPower` | Single | `ModifyEnergyGain(player, amt)` → 0 for `Owner.Player` | owner side turn end → Remove | `ExpectAFight.cs:37` |
| `NoBlockPower` | Counter (turns) | `ModifyBlockMultiplicative` → 0 when `target==Owner && cardSource != null && !Unpowered` | `AfterSideTurnEnd` **Enemy** side → Decrement | `PanicButton.cs:34` (`Turns` var) |
| `WraithFormPower` | Counter | `AfterSideTurnStart` (owner side) → `Apply<DexterityPower>(-Amount)` | permanent | WraithForm |
| `BiasedCognitionPower` | Counter | `AfterSideTurnStart` → `Apply<FocusPower>(-Amount)` | permanent | BiasedCognition |

- **Permanent stat loss:** base cards apply a negative stat directly. `Friendship.cs:30` and `SharedFate.cs:38` use `Apply<StrengthPower>(self, -N)`; `Hyperbeam.cs:56` uses `Apply<FocusPower>(self, -N)`. Dexterity and Focus are `AllowNegative => true` (`DexterityPower.cs:16`, `FocusPower.cs:12`).
- **Correction:** Hyperbeam is "lose Focus", **not** "end your turn". The base end-turn card is **`VoidForm.cs:26`**: `PlayerCmd.EndTurn(Owner, canBackOut: false)` (`Commands/PlayerCmd.cs:279`, `public static void EndTurn(Player, bool canBackOut, Func<Task>? = null)`, synchronous, which calls `CombatManager.SetReadyToEndTurn`).
- There is **no base "lose N Strength each turn" power** (WraithForm is Dex and BiasedCognition is Focus). That form would need a forged copy of `WraithFormPower` (about 15 lines).
- **Player-safety:** every one keys off `Owner` / `Owner.Player`. There is no Ironclad/Silent/Defect state, so they are safe on a forged class. `FocusPower` on a non-orb class is inert, which is harmless. `NoBlockPower` only zeroes **card** Block, so trigger and relic payload Block (`CreatureCmd.GainBlock(..., null)`, no cardSource) still lands. That matches base.

### Mod today

- `apply_status` with a negative amount on self: **not possible.** `AmountOps` contains `apply_status` and `ForgedCards.cs:1051` requires `amount >= 1`. The schema and `validator.py` mirror this.
- Routing is by set membership: `EffectRunner.SelfBuffStatuses` (`:1005`) → player; everything else → the card's target(s). The `Describe` verb ("Gain" vs "Apply") keys off the same set (`ForgedCards.cs:2066`).
- The relic precedent: `ApplyRelicStatus` (`EffectRunner.cs:1497-1512`) lands a debuff on the owner when `hookTarget == "self"` (`[AS] self-debuff`). That is the "routing exists" the audit cites, but **it is relic-only**. Cards and payloads have no self-debuff route.

### Copy-from pattern

- Add a `SelfDebuffStatuses` set: `no_draw`, `no_energy_gain`, `no_block`, `dex_decay` (WraithForm), `focus_decay` (BiasedCognition), plus the literal permanent losses `lose_strength` / `lose_dexterity` / `lose_focus`.
- `EffectRunner.ApplyStatus`: `self = SelfBuffStatuses ∪ SelfDebuffStatuses`.
- The PowerVar route works for the five real powers (`DataCard` `Power<NoDrawPower>` etc.).
- The `lose_*` trio follows the A5 rule: a named var (`"StrengthLoss"`-style) plus a literal `RelicApplyT<StrengthPower>(self, -amt)`. This avoids the var collision with a `strength` gain on the same card (the BulkUp / SharedFate shape).
- Payload: `TriggerRunner.ApplySelfBuff` gains these entries (`ValidateTrigger` `:1705` allows only `SelfBuffStatuses` today; widen or keep card-only).
- Relic: `RelicApply` cases.
- `end_turn` is a new flag op: `PlayerCmd.EndTurn(card.Owner, canBackOut:false)` as the LAST effect. Validator: must be the final effect; card-only; never in a payload.

### Proposed shape and describe

Bespoke sentences rather than the "Gain X." idiom, which would misread:

```json
{"op":"draw","amount":3},{"op":"apply_status","status":"no_draw","amount":1}   // Battle Trance
  -> "Draw 3 cards. You cannot draw additional cards this turn."
{"op":"apply_status","status":"no_energy_gain","amount":1}  -> "You cannot gain energy this turn."
{"op":"block","amount":30},{"op":"apply_status","status":"no_block","amount":2}  // Panic Button
  -> "You cannot gain Block from cards for 2 turns."
{"op":"apply_status","status":"intangible","amount":2},{"op":"apply_status","status":"dex_decay","amount":1}  // Wraith Form
  -> "At the start of your turn, lose 1 Dexterity."
{"op":"apply_status","status":"lose_strength","amount":2}   -> "Lose 2 Strength."
{"op":"end_turn"}                                            -> "End your turn."
```

### Risks and blockers

1. **Your own Artifact eats these.** They are Debuffs (and negative Strength reads as Debuff via `GetTypeForAmount`), so `ArtifactPower` blocks them and burns a stack. That matches base, but it makes `artifact` + drawback cards anti-synergistic. Note it in `DESIGN_HEURISTICS`.
2. **`end_turn` needs an AutoSlay spike.**
   - `EndTurn` is synchronous and sets "ready". Base VoidForm calls it inside `OnPlay`, so it is legal. However, the remaining effects of the card and any queued AutoSlay plays must not race it. Verify the bot doesn't hang at "Combat turn N" (the known hang signature in `power-hook-turn-start-pitfall`).
   - It also interacts with retain / `turn_end` triggers (they still fire through the normal end-turn path).
3. **Pricing.** Price these like `lose_hp` (negative value). `no_draw` on a card that draws 0 is a dead drawback; the validator should require a draw or energy payoff on the same card.
4. **The audit's "relic path already lands a self-debuff on the owner, so this is cheap"** is only half-true. That routing lives in `ApplyRelicStatus` keyed on `hookTarget`. Cards need the new `SelfDebuffStatuses` set and new describe branches. Still small.
5. **Scope.** "Cards cost +1", "die if hit", "lose orb slot" and "lose max HP" from the audit row are NOT covered by these five powers; leave them out of Tier A. Also: `CreatureCmd.LoseMaxHp` exists if needed.

**Effort:** about 6 to 8 h C# (statuses plus bespoke describe) plus about 3 h harness. The `end_turn` spike is about 2 to 3 h, AutoSlay included.

**AutoSlay tag:** `[BN] self-debuff <status> +N on player (Artifact <a>)`, `[BN] no_draw blocked a draw` (from a `ShouldDraw`-false observation, or just the power's own Flash), `[BN] end_turn requested by '<card>'`, `[BN] dex_decay -N (Dex now <d>)`.

---

## Summary verdicts

| group | verdict | main reason |
|---|---|---|
| A1 filters / every_n / random_enemy / this_turn | **GO** | Direct port of shipped relic code. Decide per-combat counting and Single-stack behaviour. |
| A2 new History scales, energy, draw-to-N | **GO** | Every source has a verbatim base recipe. Additive (base + N×count) form is a follow-up. |
| A3 new `when` kinds | **GO** | `target_killed` is play-local in EffectRunner (Results + Fatal filter), not in Conditions. |
| A4 `hits_scale` | **GO** | The BaseLib named calc-var sidesteps the one-calc-var limit. Add a hit cap (none exists). |
| A5 enemy Strength loss / strip | **GO** | The temp-down shell must override `Type => Debuff` (Artifact bug otherwise). Permanent loss needs a literal negative apply, not the PowerVar. |
| A6 doom | **GO** | DoomPower is generic and concrete; copy `poison`. Pricing is the only real work. |
| A7 self-drawbacks | **GO** for the statuses; **needs-spike** for `end_turn` | All five powers are player-safe. Negative `apply_status` is impossible today, so new named statuses are needed. |
