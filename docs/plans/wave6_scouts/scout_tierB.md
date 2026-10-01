# Tier-B vocab scout (verify-first), 2026-10-01, vocab v60 on `main`

Read-only scout. Paths:
- **MOD** = `BLANKthespire-prod/BLANKthespire/mod/BlankTheSpireCode/`
- **DECOMP** = `BLANKthespire/_modref/decomp_full/` (`MegaCrit.Sts2.Core.<ns>/<File>.cs`)

Symbol names are authoritative. Line numbers are hints taken from today's tree.
Phase-tag suggestions continue after BG: **BH … BQ**, one per group.

---

## 0. Cross-cutting findings (read these first; several change the per-group plans)

1. **The AutoSlay bot plays every card through `CardCmd.AutoPlay`.**
   - Source: DECOMP `AutoSlay.Handlers.Rooms/CombatRoomHandler.cs:90`, `await CardCmd.AutoPlay(new BlockingPlayerChoiceContext(), cardModel, randomTarget);`
   - Every AutoSlay smoke the project has ever run has therefore exercised the auto-play path. This settles B7, see §B7.
   - Corollary: AutoPlay never calls `CardModel.SpendResources` (DECOMP `Commands/CardCmd.cs:124-131` builds a `ResourceInfo` with `EnergySpent = 0`). **Under AutoSlay no energy and no stars are ever spent.** Three consequences:
     - `Hook.AfterEnergySpent` never fires. It is only raised in `CardModel.SpendEnergy`, `Models/CardModel.cs:1832-1843`. **`on_energy_spent` (B5) cannot be smoke-proven by AutoSlay.**
     - Star costs are never deducted (B9).
     - Cost changes (B4) only matter through the `CanPlay` energy gate.
   - AutoSlay also gives the player Plating 999 and Regen 999 at combat start (`CombatRoomHandler.cs:44-45`).
   - The bot tries each card instance at most once per turn (`attemptedCards`). A 0-cost return-to-hand card therefore cannot loop the bot.
2. **Every card in all five combat piles, the Play pile included, is a hook listener.**
   - Source: DECOMP `Combat/CombatState.cs:150-168`, inside the iterator that backs `IterateHookListeners`, which loops over `PlayerCombatState.AllPiles` = Hand, Draw, Discard, Exhaust, Play (`Entities.Players/PlayerCombatState.cs:82`).
   - So `DataCard` may override card-level hooks such as `ModifyCardPlayResultPileTypeAndPosition`, `AfterCardDrawn`, `AfterCardPlayed`, `BeforeHandDraw` and `AfterCardExhausted`, filtering on `card == this`. Base precedents: `Bolas` / `ThrummingHatchet` (`BeforeHandDraw`), `KinglyKick` (`AfterCardDrawn`), `Pinpoint` / `Stomp` (`AfterCardPlayed` / `BeforeCardPlayed` / `AfterCardEnteredCombat`).
   - ⚠ Caveat from Phase BD (commit d2347db): `DataCard.AfterFlush` never fired for a retained card in AutoSlay, even though the listener loop says it should. Treat every new card-level hook as **smoke-to-prove**. A day-1 tag per hook is mandatory.
3. **Prompts for a mod picker can be custom without crashing.**
   - Base cards pass `SelectionScreenPrompt` (`Models/CardModel.cs:128-140`), which throws if `cards.<ID>.selectionScreenPrompt` is missing. That is the gap-#26 crash rule, and it is why the mod reuses `CardSelectorPrefs.*SelectionPrompt`.
   - The only stock prompts are TO_TRANSFORM, TO_EXHAUST, TO_REMOVE, TO_ENCHANT, TO_DISCARD and TO_UPGRADE (`CardSelection/CardSelectorPrefs.cs:11-21`). None fits "put on top", "make Retain" or "pick from draw".
   - **Fix:** BaseLib `CardLoc(Title, Description, params (string,string)[] ExtraLoc)` (`BaseLib-StS2/Abstracts/ILocalizationProvider.cs`). `ModelLocPatch` writes each extra pair as `"{key}.{name}"` (`Patches/Localization/ModelLocPatch.cs:56`).
   - So `DataCard.Localization` (MOD `Engine/DataCard.cs:138-139`) can add `("selectionScreenPrompt", "…")` for any card that carries a picker op, and expose `internal LocString PickPrompt => SelectionScreenPrompt;`, which is protected on CardModel.
   - This unlocks honest prompts for B3, B5 (grant_keyword) and B1.
4. **Prefer base concrete powers over new mod powers when the base power is sealed and concrete.**
   - Precedent: Phase BF applied `VigorPower` / `DoubleDamagePower` through the plain `apply_status` pipe. Its sites are:
     - the `DataCard.DeclareEffects` status switch, MOD `Engine/DataCard.cs:234-262`
     - `EffectRunner.ApplyStatus`, `Engine/EffectRunner.cs:1228-1257`
     - `EffectRunner.SelfBuffStatuses`, `:1005-1012`
     - `TriggerRunner.ApplySelfBuff`, `Engine/TriggerRunner.cs:302-323`
     - `ForgedCards.SupportedStatuses`, `Engine/ForgedCards.cs:510-515`
   - Several tier-B items reduce to exactly this recipe (B2, B6, part of B8).

---

## B1. `add_random_card {card_type?, pile, amount?, choose_of?, free_this_turn?}`

### Verified surfaces
**Mod:**
- `EffectRunner.AddCards`, MOD `Engine/EffectRunner.cs:539-560`. This is the shared executor (card path plus TriggerRunner `case "add_card"` at `Engine/TriggerRunner.cs:151-156`). It uses `CardPileCmd.AddGeneratedCardToCombat(model, pile, owner, CardPilePosition.Random)`.
- Class index: `ForgedCharacters.ClassIndexOfPlayer`, `Engine/ForgedCharacters.cs:74-75`. Depth-1 loop rule: `ForgedCharacters.ResolveClassCardModel`, `:84-125`.

**Class pool enumeration:**
- Each forged class has its own pool, `ForgedClassPoolKK : CustomCardPoolModel` (MOD `Cards/Forged/ForgedClasses.g.cs:30`). Cards are bound by `[Pool(typeof(ForgedClassPoolKK))]` on `ForgedClassKKCard` (`:43-44`).
- Empty slots are `autoAdd:false` (`DataCard` ctor, `Engine/DataCard.cs:109-110`), so `Owner.Character.CardPool` holds only filled cards.
- No registry walk is needed. Use the same call the base game uses: `Owner.Character.CardPool.GetUnlockedCards(Owner.UnlockState, Owner.RunState.CardMultiplayerConstraint)`.
- `FilterThroughEpochs` is a pass-through by default (DECOMP `Models/CardPoolModel.cs:102-105`), so forged cards are never epoch-filtered.

**Filters the base game already applies:**
- `CardFactory.FilterForCombat` (DECOMP `Factories/CardFactory.cs:160-163`) drops Basic, Ancient, Event and `!CanBeGeneratedInCombat`.
- `DataCard.CanBeGeneratedInCombat` already drops the Token blade (`Engine/DataCard.cs:51`).

**Base API (all public static, callable from the mod):**
- `CardFactory.GetDistinctForCombat(Player, IEnumerable<CardModel>, int count, Rng)`, `Factories/CardFactory.cs:119-130`. It returns owner-bound `CombatState.CreateCard` copies.
- `CardSelectCmd.FromChooseACardScreen(PlayerChoiceContext, IReadOnlyList<CardModel> cards, Player, bool canSkip=false) → Task<CardModel?>`, `Commands/CardSelectCmd.cs:216`.
  - ⚠ It **throws if `cards.Count > 3`**.
  - It logs Error and Sentry `ReportSoftlock` if count is 0 (`:194-199, 222-226`).
- `CardModel.SetToFreeThisTurn()`, `Models/CardModel.cs:1266-1270`, which is `EnergyCost.SetThisTurnOrUntilPlayed(0)` plus star 0.

**AutoSlay:**
- `AutoSlayer` installs `CardSelectCmd.UseSelector(new AutoSlayCardSelector(...))` (`AutoSlay/AutoSlayer.cs:168`).
- `FromChooseACardScreen` calls `Selector.GetSelectedCards(cards, 0, 1)`. `AutoSlayCardSelector.GetSelectedCards` takes `Math.Min(maxSelect, count)`, which is 1 (`AutoSlay.Helpers/AutoSlayCardSelector.cs`).
- **Auto-pick works.** The base Attack/Skill/Power potions route forged pools through the same surface, and `CombatRoomHandler.UseAllPotions` drinks them every combat.

### Copy-from
- Base `Discovery.OnPlay` (DECOMP `Models.Cards/Discovery.cs:22-39`): GetDistinct ×3 → FromChooseACardScreen → SetToFreeThisTurn → AddGeneratedCardToCombat.
- `InfernalBlade` / `WhiteNoise`: type filter ×1, free.
- `CreativeAiPower.BeforeHandDraw` (`Models.Powers/CreativeAiPower.cs:19-32`): the per-turn form.
- Mod side: `AddCards` for pile mapping and logging, and `ExhaustCards` for the `card_type` filter via `EffectRunner.HandKindMatches` (`:663-670`).

### Proposed shape
```json
{"op":"add_random_card","amount":1,"pile":"hand","card_type":"attack","choose_of":3,"free_this_turn":true}
```
- `card_type` ∈ attack|skill|power|non_attack (reuse `HandKindFilters`, `ForgedCards.cs:561`).
- `choose_of` ∈ {2,3}: the player picks 1 of N. If set, `amount` must be 1.
- `free_this_turn` is legal only when `pile == "hand"`.
- Payload form (`turn_start` only): **no `choose_of`** (rule 0.5, choice UI), and `free_this_turn` is allowed.

Describe strings:
- `Add a random Attack to your hand. It costs 0 this turn.`
- `Add 2 random cards to your discard pile.`
- `Choose 1 of 3 random Skills to add to your hand. It costs 0 this turn.`
- Payload fragment: `add a random Power to your hand`

### Engine sites
1. `ForgedCards.SupportedOps` (`:427`).
2. `TriggerOps` (`:488`), for the payload form.
3. Parse: new `choose_of` (int) and `free_this_turn` (bool) fields in `ForgedCards.ParseEffects` (`:950-1002`). `EffectSpec` gets `ChooseOf` / `FreeThisTurn` (`Engine/CardSpec.cs:81-89`).
4. Validate: widen the `card_type` stray-field rule at `ForgedCards.cs:1076`.
5. `DataCard.DeclareEffects` no-var fall-through (`DataCard.cs:194-225`).
6. `EffectRunner.Execute` case plus a new `AddRandomCards(e, owner, ctx)`.
7. `TriggerRunner` case.
8. `Describe` (`:1929+`) and `TriggerFragment` (`:2135+`).

### Risks and blockers
- **Loop discipline.** A free generated card that itself generates (`add_random_card` → free `add_random_card` → …) chains through the pool. Filter candidates with `c is DataCard dc && !dc.HasOp("add_random_card")`, the same idea as `ResolveClassCardModel`'s depth-1 rule.
- Guard `pool.Count == 0` before the call (small classes plus a type filter), otherwise `ReportSoftlock` fires.
- Clamp `choose_of` to ≤ 3 because of the hard throw.
- In a base-class run, a shared forged card generates from that base class's pool. This matches Discovery and is acceptable.
- The audit's colorless option is out of scope. It would need `ModelDb.CardPool<ColorlessCardPool>()`; deferred.

### Estimate and tag
- **~7 h** (C# 3 h, harness and Python lockstep 4 h).
- Tag `[BH] add_random_card <type> x<n> -> <pile> ('<titles>'; free=<bool>; choose_of=<n>)`, plus grep `Auto-selected 1 card(s)`.

**Verdict: GO.**

---

## B2. Replay / play-twice (`replay_next {card_type, count}`) + Echo Form

### Verified surfaces (DECOMP)
**The play loop:**
- `CardModel.OnPlayWrapper` runs `for (int i = 0; i < playCount; i++)`, with `BeforeCardPlayed`, `OnPlay`, `CardPlayFinished` and `AfterCardPlayed` **per replay** (`Models/CardModel.cs:1895-1961`).
- `GeneratePlayCount` → `Hook.ModifyCardPlayCount` → `Hook.AfterModifyingCardPlayCount` (`:2015-2021`). This is play-time only, never preview.
- `Hook.ModifyCardPlayCount` collects only the listeners that changed the count (`Hooks/Hook.cs:1516-1530`). Only those receive `AfterModifyingCardPlayCount(card)` (`:808-818`).

**Base powers.** All are `public sealed class … : PowerModel` with `Counter` stacking:

| Power | Applies to | Decrement | Removal |
|---|---|---|---|
| `BurstPower` (`Models.Powers/BurstPower.cs`) | Skill | Decrement | Removed at own turn end |
| `OneTwoPunchPower` | Attack | Decrement | Removed at turn end |
| `SignalBoostPower` | Power | Decrement | **Persists until used** |
| `DuplicationPower` | Any card | Decrement | Removed at turn end |
| `EchoFormPower` | First `Amount` cards each turn (counts `CardPlaysStarted` with `IsFirstInSeries`) | Permanent | — |

- Base cards apply them with `PowerCmd.Apply<BurstPower>(ctx, owner, n, owner, this)` (`Models.Cards/Burst.cs:25`, `OneTwoPunch.cs:24`, `SignalBoost.cs:25`).

### Mod pattern to copy
- **The BF recipe, not a new forged power.** Each kind maps to an existing sealed power that ships its own loc and icon. Same sites as §0.4:
  - `DataCard` status switch, `Engine/DataCard.cs:234-262`
  - `ApplyStatus`, `EffectRunner.cs:1228-1257`
  - `SelfBuffStatuses`, `:1005`
  - `TriggerRunner.ApplySelfBuff`, `:302-323`
  - `SupportedStatuses`, `ForgedCards.cs:510`
- `ForgedCorruptionPower` (MOD `Powers/ForgedCorruptionPower.cs`) and `ForgedCostShiftPower` (one power per player with an entry list) are the fallback templates. They are only needed for variants the base powers can't express, such as "this combat" for an Attack, or a type plus a cost filter.

### Proposed shape
Op sugar over the base powers. Amount = stacks.
```json
{"op":"replay_next","card_type":"skill","count":2}
```
| `card_type` | Power | Describe |
|---|---|---|
| skill | BurstPower | `This turn, your next 2 Skills are played twice.` |
| attack | OneTwoPunchPower | `This turn, your next Attack is played twice.` |
| power | SignalBoostPower | `Your next Power is played twice.` |
| all | DuplicationPower | `This turn, your next card is played twice.` |

Echo Form: `{"op":"apply_status","status":"echo_form","amount":1}`. Describe: `The first card you play each turn is played twice.`
- Restrict it to a **Power card, rare, amount 1** (the base Echo Form is rare with Ethereal).

Validator caps:
- `count` 1..2. Skill/Attack at uncommon, `all` rare-only.
- `replay_next` is not a payload. A turn_start replay engine is Echo Form's job.

### Risks and blockers
- Replays re-run the whole `EffectRunner.Execute`. Side-effect ops run twice, and all are safe:
  - `purge` / `transform_card`: DeckVersion guard; the second pass sees `deckCard.Pile` ≠ Deck.
  - `graft_card` / `purge_card`: two pickers. AutoSlay auto-picks.
  - `add_trigger`: `Single` stack.
  - `spend_forge`: spends twice. Intended.
- `ForgedCostShiftPower.AfterCardPlayed` (`Powers/ForgedCostShiftPower.cs:152-180`) consumes a budgeted use **per replay**, so a "next Skill costs 1 less" entry burns on a replayed play. Accept and note the quirk, or skip uses when `cardPlay.PlayIndex > 0`. `CardPlay.PlayIndex` exists, `CardModel.cs:1923`.
- `grow` / `plays_this_combat` count each replay because history records each start and finish. That matches the base game.
- X-cost: `CapturedXValue` is reused across replays, same as base Burst + Whirlwind.

### Estimate and tag
- **~5 h.**
- Tag: log in `ApplyPowerLogged` (`EffectRunner.cs:1266`) as `[BI] replay_next <kind> x<n>`. Prove the replay with a `DataCard.BeforeCardPlayed` / `Execute` line when `play.PlayIndex > 0`: `[BI] replay play #2 of '<card>'`.

**Verdict: GO. Cheapest high-value item in tier B.**

---

## B3. Self-routing recursion, put-back, draw-pile tutor, `on_shuffle`, exhaust-from-draw

### Verified surfaces
**Result pile:**
- `CardModel.GetResultPileTypeForCardPlay()` is `protected virtual` and returns a `PileType` only (`Models/CardModel.cs:2070-2082`). OnPlayWrapper then passes it through `Hook.ModifyCardPlayResultPileTypeAndPosition(…, CardPilePosition.Bottom, …)` (`:1890`).
- So **return to hand** = override `GetResultPileTypeForCardPlay` (Discard → Hand), copying `ParticleWall` (`Models.Cards/ParticleWall.cs`).
- **Top of draw** needs a position, so `DataCard` overrides `ModifyCardPlayResultPileTypeAndPosition(card, isAutoPlay, resources, pileType, position)` (`AbstractModel.cs:1488`) with `card == this` → `(PileType.Draw, CardPilePosition.Top)`. The card in the Play pile is a listener (§0.2). Base powers do the same: `ReboundPower`, `NostalgiaPower`, `FeralPower`, `CorruptionPower`.
- MOD already overrides `GetResultPileTypeForCardPlay` for purge (`Engine/DataCard.cs:396-397`). Extend that one method. Purge (None) must keep precedence.

**Return next turn (Bolas):**
- `AbstractModel.BeforeHandDraw(Player, PlayerChoiceContext, ICombatState)` (`AbstractModel.cs:753`).
- `Bolas.BeforeHandDraw` (`Models.Cards/Bolas.cs`) checks `History.CardPlaysFinished.Any(e => e.HappenedLastPlayerTurn(Owner) && e.CardPlay.Card == this)`, then `CardPileCmd.Add(this, PileType.Hand)`. Copy it verbatim.

**Put-back:**
- `CardPileCmd.Add(CardModel, PileType, CardPilePosition = Bottom, AbstractModel? clonedBy = null, bool skipVisuals = false)` (`Commands/CardPileCmd.cs:259`).
- `Headbutt`: `FromCombatPile(Discard)` → `Add(…, Draw, Top)`.
- `ThinkingAhead`: `FromHand` → `Add(…, Draw, Top)`.

**Shuffle:**
- `CardPileCmd.Shuffle(PlayerChoiceContext, Player)` (`:866`) shuffles discard into draw, then raises `Hook.AfterShuffle(combatState, ctx, player)` (`:918-921`).
- `Reboot` = Add every hand card to Draw → Shuffle → Draw.

**Tutor:**
- `CardSelectCmd.FromCombatPile(ctx, CardPile, Player, prefs, Func<CardModel,bool> filter)` (`Commands/CardSelectCmd.cs:381`). It throws on a non-combat pile and returns empty on 0 matches. Under the AutoSlay Selector, a Draw-pile list is ordered by rarity and id (`:410-416`).
- `SecretWeapon` uses filter `c.Type == Attack`, then `CardPileCmd.Add(card, Hand)`.

**Trigger:** `AbstractModel.AfterShuffle(PlayerChoiceContext, Player shuffler)` (`AbstractModel.cs:1139`).

**`retrieve_card` today:**
- `EffectRunner.RetrieveCards` (`Engine/EffectRunner.cs:629-658`).
- Status/Curse exclusion is `Retrievable(c) => c.Type is not (Status or Curse)` (`:620`), applied to both random and choose.
- Pile is Discard or Exhaust only (`ForgedCards.RetrievePiles`, `:554`, validated `:1299-1303`). The comment at `:550-553` says "never the draw pile: that is what draw/scry are for". This rule is now being **reversed deliberately**; record that in the VOCABULARY row.

**`exhaust_card` today:** `EffectRunner.ExhaustCards` (`:681-725`) is hand-only. `CardCmd.Exhaust` (`Commands/CardCmd.cs:237-246`) moves from any pile and raises `AfterCardExhausted`.

### Proposed shapes
**(a) Flag-ops on the card.** Pick one per card; validator-exclusive with each other and with `exhaust` / `purge` / Power.

| Flag-op | Describe |
|---|---|
| `return_to_hand` | `Returns to your hand after you play it.` |
| `to_draw_top` | `Goes on top of your draw pile after you play it.` |
| `return_next_turn` | `At the start of your next turn, return this to your hand.` |

- `return_to_hand` needs cost ≥ 1 and no `gain_energy` / `draw` on the card (an infinite 0-cost loop for a human player; the AutoSlay bot is safe, §0.1).

**(b) `put_back {from: hand|discard, cards: choose, amount: 1}`.**
- Describe: `Put a card from your hand on top of your draw pile.` / `Put a card from your discard pile on top of your draw pile.`
- Card-only. Prompt through `CardLoc` ExtraLoc (§0.3).
- Optional `shuffle_hand` flag-op for Reboot: `Shuffle your hand into your draw pile.`

**(c) Widen `retrieve_card`:** `pile` += `draw`, and allow `card_type` (attack|skill|power|non_attack) on `retrieve_card`.
- Describe: `Put an Attack from your draw pile into your hand.` (choose), `Put a random Skill from your draw pile into your hand.` (random).
- Keep `Retrievable` and AND it with `HandKindMatches`.
- `card_type` stays optional for discard/exhaust.

**(d) `exhaust_card` += `pile: hand|draw`** (default hand). From the draw pile: choose/random only, no `all`.
- Describe: `Exhaust a card in your draw pile.`
- The stock `ExhaustSelectionPrompt` fits.

**(e) Trigger `on_shuffle`:** a `ForgedTriggerPower.AfterShuffle` override → `FireReactive("on_shuffle", ctx)`. Multi-fire and once_per_* eligible.
- Describe: `Whenever you shuffle your draw pile, …`

### Engine sites
- `DataCard.cs`: the pile override at `:396-397`, plus new `ModifyCardPlayResultPileTypeAndPosition` and `BeforeHandDraw` overrides. `CardSpec` gets `HasReturnToHand` etc. next to `HasPurge` (`Engine/CardSpec.cs:161`).
- `EffectRunner`: the `retrieve_card` / `exhaust_card` cases (`:370-382`) and a new `PutBack`.
- `ForgedCards`:
  - `RetrievePiles` `:554`
  - stray-`card_type` rule `:1076`
  - `ExhaustPickModes` `:560` plus a pile field
  - `KeywordOps` / `SupportedOps`
  - `SupportedTriggers` / `MultiFireTriggers` / `OncePerCombatTriggers` (`:466-486`)
  - `TriggerSentence` `:2102-2117`
  - `RetrieveSentence` `:2234-2242`
- `ForgedTriggerPower`: the title switch `:272-281` and the new override.

### Risks and blockers
- `to_draw_top` plus Corruption: the hook order decides whether a Skill exhausts or goes on top. Accept it (both are listeners) or forbid the combination.
- A `return_next_turn` card that was exhausted or purged must not come back. Bolas itself returns from any pile except hand, including exhaust, so add `Pile.Type is Discard or Draw` to the guard.
- Hook reach is unproven (BD AfterFlush lesson, §0.2). Tag both overrides.

### Estimate and tag
- **~11 h total.** Flags 4 h, put_back 2.5 h, retrieve-draw 1.5 h, exhaust-from-draw 1 h, on_shuffle 2 h. Split it: flags + retrieve-draw first.
- Tags: `[BJ] return_to_hand '<card>'`, `[BJ] to_draw_top '<card>'`, `[BJ] return_next_turn '<card>' <- <pile>`, `[BJ] put_back <from> '<card>' -> draw top`, `[BJ] retrieve draw [<type>] '<card>'`, `[BJ] on_shuffle fired`.

**Verdict: GO, in two slices.**

---

## B4. Self cost modification: `cost_delta {on, amount, scope}`

### Verified surfaces
**Mod:**
- `held_discount` lands in `DataCard.OnHeldIntoTurn` → `EnergyCost.AddThisCombat(-n)` (MOD `Engine/DataCard.cs:321-338`). It is driven from `HandStateTracker.SnapshotPreDraw` (`Engine/HandStateTracker.cs:34-53`) because `AfterFlush` never fired.
- The cost floor and X skip are documented at `ForgedCostShiftPower.cs:28-33`.
- Validator rule `held_discount` not on 0-cost or X-cost: `ForgedCards.cs:846`, cap `:1177`.

**Base API:** `CardEnergyCost` (DECOMP `Entities.Cards/CardEnergyCost.cs`), all public. Every Add/Set variant takes an optional `reduceOnly`.
- `SetUntilPlayed(int, bool reduceOnly=false)` :175
- `SetThisTurnOrUntilPlayed` :197
- `SetThisTurn` :219
- `SetThisCombat` :238
- `AddUntilPlayed` :258
- `AddThisTurnOrUntilPlayed` :278
- `AddThisTurn` :300
- `AddThisCombat` :319
- `GetWithModifiers(CostModifiers)` :94 floors at 0.

**Base recipes (`Models.Cards/`):**
- `MomentumStrike`: `EnergyCost.SetThisCombat(0)` at the end of OnPlay.
- `UpMySleeve`: `AddThisCombat(-1)` at the end of OnPlay. `Modded`: `AddThisCombat(+1)`.
- `KinglyKick.AfterCardDrawn`: `card == this` → `AddThisCombat(-1)`.
- `Pinpoint`:
  - `AfterCardPlayed`: an owner's Skill → `AddThisTurn(-1)`.
  - `AfterCardEnteredCombat`: `card == this && !IsClone` → back-fill from `History.CardPlaysFinished` this turn.
- `Stomp`: the same with Attack via `BeforeCardPlayed`.
- `BansheesCry`: back-fill per Ethereal played this combat, `AddThisCombat(-n·2)`.

**Card hooks (`AbstractModel.cs`):**
- `AfterCardPlayed(ctx, CardPlay)` :463
- `BeforeCardPlayed(CardPlay)` :454
- `AfterCardDrawn(ctx, card, fromHandDraw)` :396
- `AfterCardExhausted(ctx, card, causedByEthereal)` :433
- `AfterCardEnteredCombat(card)` :406
- `AfterCardGeneratedForCombat` :421

### Proposed shape
A card **field**, like `held_discount`; card-only, not a payload.
```json
{"op":"cost_delta","on":"skill_played","amount":-1,"scope":"this_turn"}
```
- `on`:
  - `played` (self, after this card's play)
  - `drawn` (self)
  - `attack_played` / `skill_played` / `card_played` (another card of yours)
  - `card_exhausted`
- `amount`: −2..+1. +1 is legal only with `on: played` (Modded).
- `scope`: `this_turn` | `combat`.
- Special case `set_zero: true` with `on: played`: Momentum Strike, `SetThisCombat(0)`.

Describe strings:

| Variant | Describe |
|---|---|
| played, combat, −1 | `Costs 1 less for the rest of combat each time you play it.` |
| played, set_zero | `After you play this, it costs 0 for the rest of combat.` |
| drawn, combat, −1 | `Whenever you draw this, it costs 1 less this combat.` |
| skill_played, this_turn, −1 | `Costs 1 less this turn for each Skill you play.` |
| card_exhausted, combat, −1 | `Costs 1 less for each card you Exhaust this combat.` |
| played, combat, +1 | `Costs 1 more each time you play it.` |

### Engine sites
- `DataCard`: new overrides `AfterCardPlayed`, `AfterCardDrawn`, `AfterCardExhausted` and `AfterCardEnteredCombat`, plus a helper `ApplyCostDelta(e)`. `held_discount`'s X skip is at `:330`.
- `EffectRunner`: the no-op keyword case group `:265-273`. The `played` self form can run at the end of `Execute` or in the `AfterCardPlayed` with `cardPlay.Card == this`. Prefer the latter so a replay counts per play like the base game.
- `ForgedCards`: SupportedOps, the new field parse (`on`), a validator mirroring the held_discount rules (`:846`, `:1177`), and a describe case near `:1990`.

### Risks and blockers
- **Generated or cloned copies** miss earlier this-turn events. Copy Pinpoint's `AfterCardEnteredCombat` back-fill, or use the stateless alternative.
  - Stateless alternative: `DataCard.TryModifyEnergyCostInCombat` computing `−count(History this turn)` for the `*_played`/this_turn forms. No mutation, always correct, previews live. It composes with `ForgedCostShiftPower` (EARLY pass) and Corruption (Late).
  - **Recommend:** stateless for the `*_played` this_turn forms, `CardEnergyCost.Add*` for played/drawn/exhausted with combat scope.
- AutoSlay never spends energy (§0.1), so a smoke can only prove the cost read. Log `GetWithModifiers(CostModifiers.Local)` as BD does. It cannot prove that the energy payment changed.
- The card-hook reach caveat (§0.2) applies.

### Estimate and tag
- **~8 h.**
- Tag `[BK] cost_delta '<card>' on <event>: <old> -> <new> (<scope>)`.

**Verdict: GO.**

---

## B5. Small triggers + `grant_keyword`

### Verified surfaces
**Mod template:** `ForgedTriggerPower`, MOD `Powers/ForgedTriggerPower.cs`.
- Reactive hooks: `:153-226`.
- `FireReactive(kind, ctx, attacker)` with `_firing` re-entrancy plus once_per_*: `:233-264`.
- `_combatCtx` fallback for ctx-less hooks: `AfterBlockGained`, `:222-226`.
- Title switch: `:272-281`.
- Lists: `SupportedTriggers` / `MultiFireTriggers` / `OncePerCombatTriggers` (`ForgedCards.cs:466-486`).
- `TriggerSentence` `:2102-2117`.
- Payload-target validation (`attacker` is only legal on `attacked`): `ForgedCards.cs:1683-1688`.
- `TriggerRunner.ResolveEnemies` handles `attacker` (`TriggerRunner.cs:274-281`).

**Base hooks (`AbstractModel.cs`):**

| Hook | Line | Context | Notes |
|---|---|---|---|
| `AfterCardGeneratedForCombat(CardModel, Player? creator)` | :421 | **no ctx** | Raised by `AddGeneratedCardToCombat` (`CardPileCmd.cs:243-246`). Base `ArsenalPower` uses `new ThrowingPlayerChoiceContext()`. |
| `AfterPowerAmountChanged(ctx, PowerModel power, decimal amount, Creature? applier, CardModel? cardSource)` | :1052 | ctx | `SleightOfFleshPower` filter: `amount != 0 && power.GetTypeForAmount(amount) == Debuff && power.Owner.IsEnemy && applier == Owner && !(power is ITemporaryPower)`. `ViciousPower`: `power is VulnerablePower`. |
| `AfterEnergySpent(CardModel, int amount)` | :686 | **no ctx** | `OrbitPower` keeps a running total and fires every 4. |
| `AfterOrbEvoked(ctx, OrbModel, IEnumerable<Creature> targets)` | :963 | ctx | Raised by `OrbCmd.Evoke` (`Commands/OrbCmd.cs:136-153`). |

**Keyword grant:**
- `CardCmd.ApplyKeyword(CardModel, params CardKeyword[])` (`Commands/CardCmd.cs:676`) and `CardCmd.ApplySingleTurnSly(CardModel)` (`:698`). Both refresh the NCard visuals.
- Base precedents:
  - `Snap`: Retain, filter `!Keywords.Contains(Retain)`.
  - `SculptingStrike`: Ethereal.
  - `HandTrick`: single-turn Sly on a Skill, filter `!IsSlyThisTurn`.
- Mod chooser path: `EffectRunner.GraftCard` / `PurgeChoose` → `CardSelectCmd.FromHand(ctx, owner, prefs, filter, source)` (`EffectRunner.cs:863-888, 947-997`).
- Every-N precedent is relic-only: `RelicSpec.EveryN` (`Engine/RelicSpec.cs:43-44`) and the counter in `RelicRunner` (`Engine/RelicRunner.cs:37-52`). Card `EffectSpec` has **no** `every_n` field, and `count` is reserved for cost_shift (`ForgedCards.cs:1066-1068`).

### Proposed shapes
**`on_card_generated`** (multi-fire): `creator?.Creature == Owner`. Use `_combatCtx ?? new ThrowingPlayerChoiceContext()` and never store the throwing one, per the BE rule.
- Describe: `Whenever you create a card, …`

**`on_debuff_applied`** (multi-fire):
- Optional `status` filter on the add_trigger op. Reuse `EffectSpec.Status`; currently it is only legal on apply_status / buff_summon.
- New payload target **`that_enemy`**. Internally pass `power.Owner` as the existing `attacker` argument and widen the `:1686` rule.
- Describe: `Whenever you apply a debuff, …` / `Whenever you apply Vulnerable, …`. Payload fragment: `deal 3 damage to that enemy`.

**`on_energy_spent` + `every_n`**: add an `EveryN` field (2..9) on add_trigger. Copy RelicRunner's counter onto the power instance.
- Describe: `Whenever you spend 4 energy, gain 1 energy.`
- ⚠ **Untestable under AutoSlay** (§0.1: AutoPlay never spends). Ship only with a manual check or a unit test. Otherwise defer.

**`on_evoke`**: `orb.Owner == Owner.Player`. Multi-fire.
- Describe: `Whenever you Evoke an orb, …`

**`grant_keyword {keyword: retain|ethereal|sly, cards: choose, card_type?}`**: card-only (picker).
- `sly` uses `ApplySingleTurnSly`; retain and ethereal use `ApplyKeyword`.
- Filter already-has-keyword cards out, as the base game does.
- Prompt via `CardLoc` ExtraLoc (§0.3), or reuse nothing.
- Describe: `Choose a card in your hand. It gains Retain.` / `Choose a Skill in your hand. It is Sly this turn.`

### Risks
- **Loops.** Generate-in-payload re-raises `on_card_generated`, and debuff-in-payload re-raises `on_debuff_applied`. The `_firing` guard covers both, the same as the H4 kinds.
- `on_card_generated` also fires for `add_status_card` (Wounds), which is base behaviour (Smokestack/Arsenal count statuses). The opposite reading needs a `card_type` filter.
- `ITemporaryPower` debuffs are excluded, matching base Sleight of Flesh.

### Estimate and tag
- **~13 h** for all five. Per item: on_card_generated 2 h, on_debuff_applied 4 h, on_evoke 2 h, grant_keyword 3.5 h, on_energy_spent 2 h with no smoke.
- Tag `[BL] <kind> fired (...)`. For grant_keyword: `[BL] grant_keyword <kw> -> '<card>'`.

**Verdict: GO for on_card_generated, on_debuff_applied, on_evoke and grant_keyword. NO-GO (defer) for on_energy_spent until it can be verified.**

---

## B6. Grab-bag trivials

| item | base API (verified) | mod site | shape + describe | est |
|---|---|---|---|---|
| `block_next_turn {amount \| scale:"block"}` | `BlockNextTurnPower`: sealed, Counter, `AfterBlockCleared` → `GainBlock(Amount, Unpowered)` then Remove (`Models.Powers/BlockNextTurnPower.cs`). `Prolong` applies it with `creature.Block`. | New op in `EffectRunner` + `TriggerRunner`. Apply via `BetaMainCompatibility.PowerCmd_.Apply.InvokeGeneric` (`TriggerRunner.cs:326-328`). Fixed amount through the BF status pipe; the `scale:"block"` form is an op because apply_status doesn't scale. | `Next turn, gain 8 Block.` / `Next turn, gain Block equal to your current Block.` | 2 h |
| `strip_block {artifact?:bool}` (Expose) | `CreatureCmd.LoseBlock(Creature, decimal)` (`Commands/CreatureCmd.cs:666`). `PowerCmd.Remove<T>(Creature)` (`Commands/PowerCmd.cs:279`). Recipe: `Models.Cards/Expose.cs:33-45`. | New card-only op, single-target (`target:"enemy"`, like `spread_debuffs`). Uses `play.Target`. | `Remove all Block from the enemy.` / `… and its Artifact.` Pairs with the existing `target_has_block`. | 1.5 h |
| `when target_intends_attack` | `MonsterModel.IntendsToAttack` (`Models/MonsterModel.cs:384`). `GoForTheEyes`: `cardPlay.Target.Monster.IntendsToAttack`. | `Conditions.Kinds` (`Engine/Conditions.cs:23-33`), `TargetKinds` (:39), an `Eval` case `target?.Monster?.IntendsToAttack == true`, phrase :169+. Lockstep: `test_phase_ar.py` asserts schema == C# Kinds == `class_forge._ORB_CONDITION_KINDS`. | phrase `the enemy intends to attack` | 1.5 h |
| `turn_start` payload `damage` + `grow` | `RollingBoulderPower` **awaits a VFX `Finished` signal unless `TestMode.IsOn`** (`Models.Powers/RollingBoulderPower.cs`). ⚠ Hang risk under AutoSlay; do **not** apply the base power. | Mod-native. The validator currently rejects grow in payloads (`ForgedCards.cs:1666`): allow it only for `turn_start` + targeted `damage`. Add a per-power fire counter to `ForgedTriggerPower` (beside `_ripenLeft`, `:37`) and pass `amt + grow*fires` into `TriggerRunner.Run` (new optional param). | `At the start of your turn, deal 5 damage to ALL enemies. Increases by 5 each turn.` | 2.5 h |
| `discard cards:"all"` + `scale:"cards_removed"` | `CardCmd.Discard(ctx, IEnumerable)` batch (`Commands/CardCmd.cs:157`). Keep the batch so Sly still fires. | `PickModes` (`ForgedCards.cs:555`, discard check `:1353-1356`). `DiscardRandom` with the whole hand (`EffectRunner.cs:577`). New `DataCard` per-play stash `_removedThisPlay`, set by discard/exhaust_card and read by `ScaleValue("cards_removed")` (`EffectRunner.cs:1040`). Preview fallback is `OtherCardsInHand`. Damage/block calc-vars resolve through `BonusFor` at attack time, after the earlier op ran. | `Discard your hand.` / `Exhaust your hand. Deal 7 damage for each card Exhausted.` (the latter wants `hits_scale`, an audit #8 dependency; until then the form is `Deal damage equal to …`). | 3 h |
| `retain_hand` (this turn) | `RetainHandPower`: sealed, `ShouldFlush(player) → false` for its owner, Decrement at turn end (`Models.Powers/RetainHandPower.cs`). `Equilibrium` applies it. | Plain BF-recipe status `retain_hand` (self-buff, amount 1). | `Retain your hand this turn.` | 1 h |
| `gain_energy scale:"energy"` | `DoubleEnergy`: `PlayerCmd.GainEnergy(PlayerCombatState.Energy, Owner)`. | `DataCard.cs:174` declares `WithEnergy(e.Amount, up)` unconditionally; it needs an `if (!e.IsScaled)` branch like draw (:172). `EffectRunner.cs:188`: use `ResolveScaleAmount`. Validator: `energy` is cost-0-only today (preview reasons, `EffectRunner.cs:1051-1053`). gain_energy has no calc-var, so the rule can relax for gain_energy only. | `Double your energy.` (special-case the sentence) | 1.5 h |

**Risks:**
- Rolling Boulder (see the table).
- `strip_block` on AoE is meaningless; validate it to single-target.
- Under AutoSlay energy is never spent, so `Double your energy` compounds freely. That is harmless.

**Estimate:** ~13 h for all seven. Each is independently shippable.
**Tags:**
- `[BM] block_next_turn +<n> (scale <s>)`
- `[BM] strip_block '<enemy>' -<n> Block (artifact removed=<b>)`
- `[BM] target_intends_attack gate OPEN|closed`
- `[BM] turn_start grow: <base>+<g>x<fires>`
- `[BM] cards_removed -> <n>`
- `[BM] retain_hand`
- `[BM] gain_energy x2 -> <n>`

**Verdict: GO, but excluding the base `RollingBoulderPower`; the mod-native grow is GO.**

---

## B7. Auto-play (Havoc / Mayhem / Uproar / Catastrophe / from exhaust)

### Verified API (DECOMP)
**`CardCmd.AutoPlay(PlayerChoiceContext, CardModel, Creature? target, AutoPlayType type = Default, bool skipXCapture = false, bool skipCardPileVisuals = false)`** (`Commands/CardCmd.cs:51-138`):
- Bails if combat is over or the owner is dead.
- Unplayable / `ShouldPlay` false → `MoveToResultPileWithoutPlaying`.
- `AnyEnemy` with a null target → random `HittableEnemies` (`Rng.CombatTargets`). If none, it moves without playing.
- X captured from current energy.
- Raises `BeforeCardAutoPlayed`, then `OnPlayWrapper(isAutoPlay: true, EnergySpent 0)`.

**Other surfaces:**
- `CardPileCmd.AutoPlayFromDrawPile(PlayerChoiceContext, Player, int count, CardPilePosition position, bool forceExhaust)` (`Commands/CardPileCmd.cs:933-967`): ShuffleIfNecessary per card, Add to Play, then AutoPlay each; `forceExhaust` sets `ExhaustOnNextPlay`.
- `AutoPlayType { None, Default, SlyDiscard }`.
- Turn-phase hooks for engine-style auto-play:
  - `AfterAutoPrePlayPhaseEntered(ctx, Player)` (`AbstractModel.cs:271`; used by `MayhemPower`).
  - `AfterAutoPostPlayPhaseEntered` (:244; used by `HowlFromBeyond` to replay itself from Exhaust).

**Base recipes:**
- `Havoc`: `AutoPlayFromDrawPile(1, Top, forceExhaust:true)`.
- `Uproar`: random Attack from draw (not Unplayable), `StableShuffle(Rng.Shuffle)` → `AutoPlay(…, null)`.

### The AutoSlay question, answered without a spike
- **The AutoSlay driver plays every single card with `CardCmd.AutoPlay`** (`CombatRoomHandler.cs:90`). So every smoke the project has run (BB…BG included) has already exercised `AutoPlay → OnPlayWrapper(isAutoPlay)` on forged cards, including picker ops under the AutoSlay selector.
- Nested auto-play (a played card auto-playing another) is plain recursion of the same awaited method on the same context.
- **Sly evidence, honestly:** `DataCard.BeforeCardAutoPlayed` logs `[BB] sly …` on `SlyDiscard` (`Engine/DataCard.cs:344-350`). No `[BB] sly` line exists in the local godot logs (`%APPDATA%/SlayTheSpire2/logs`, last rotation 2026-09-30). Commit d2347db lists only the `[BB] turn_at_most` and `[BF]` tags, and VOCABULARY_GAPS #55 still says "AutoSlay smoke pending". So Sly is **not** proven evidence. The CombatRoomHandler fact is the real proof.

### The real risks (design, not hang)
1. **Unbounded chains.** Auto-play X → X adds/plays → … A non-exhausting "play the top card" loops through draw → discard → reshuffle forever.
   - Force `forceExhaust: true` on draw-pile auto-play (Havoc semantics).
   - Add a static depth guard (≤ 3), like `DataCard._firingOnDiscard`.
   - Forbid `autoplay_*` cards from being auto-play candidates (depth-1).
2. **Target.** Forged `AnyEnemy` cards get a random target, which is fine. `RandomEnemy` / `AllEnemies` pass null and BaseLib's `CardAttack` resolves them.
3. **Policy.** Gap #37 rejected "weapon overrides the player's choice". `autoplay_top` is an effect the player chose to play, so it is not the same thing. Re-open Mayhem/Stampede-style "forced play from hand" separately.

### Proposed shapes
| Shape | Base equivalent | Describe |
|---|---|---|
| `{"op":"autoplay","from":"draw_top","amount":1}` | Havoc | `Play the top card of your draw pile and Exhaust it.` |
| `{"op":"autoplay","from":"draw_random","card_type":"attack"}` | Uproar | `Play a random Attack from your draw pile.` |
| Payload form on `turn_start` only: `play the top card of your draw pile` | Mayhem | — |

- The `turn_start` payload should fire from `AfterAutoPrePlayPhaseEntered`, **not** `AfterPlayerTurnStart`.
- Defer "from exhaust self-replay" (Howl from Beyond) to a flag-op later. It is the #42/#43 territory the audit re-filed; same mechanism (`AfterAutoPostPlayPhaseEntered` + Pile == Exhaust).

### Estimate and tag
- **~7 h.**
- Tag `[BN] autoplay <from> '<card>' -> <target|none> (depth <d>)`. Also log `BeforeCardAutoPlayed` with `type == Default` when the depth guard is > 0.

**Verdict: GO, no spike.** Gate on the depth guard plus forced exhaust; one AutoSlay seed confirms it.

---

## B8. Orb extras (17 base cards)

### Verified surfaces
**Mod orb executor:**
- `EffectRunner.Execute` cases `gain_orb_slot` / `channel_orb` / `evoke` (MOD `Engine/EffectRunner.cs:320-348`; evoke = `OrbCmd.EvokeNext(ctx, owner, dequeue: true)` × n).
- `EffectRunner.ChannelForgedOrbs` (:1364).
- `TriggerRunner` cases (`Engine/TriggerRunner.cs:118-150`).
- `OrbRunner.RunPassive` / `RunEvoke` for custom orbs (`Engine/OrbRunner.cs:29, 41`).
- `ForgedOrb` (`Powers/ForgedOrb.cs:139-156`).
- Conditions `orbs_match` / `orb_count_ge` (`Engine/Conditions.cs:105-115`; distinct types via `o.GetType()`).

**DECOMP `Commands/OrbCmd.cs`:**
- `AddSlots(Player, int)` :23 (cap 10)
- `RemoveSlots(Player, int)` :41 (**sync void**; `OrbQueue.RemoveCapacity` drops overflow orbs from the back without evoking, `Entities…/OrbQueue.cs:42-49`)
- `Channel` :57/68
- `EvokeNext(ctx, Player, bool dequeue = true)` :94
- **`EvokeLast(ctx, Player, bool dequeue = true)`** :106 (evoke newest)
- `Passive(ctx, OrbModel, Creature? target)` :155 → `orb.Passive(...)`

**Hook:** `AfterOrbEvoked(ctx, orb, targets)` (`AbstractModel.cs:963`).

**Base recipes:**

| Card / power | What it does |
|---|---|
| `Dualcast` | `EvokeNext(dequeue:false)` then `EvokeNext()`. This is "evoke without consuming". |
| `MultiCast` | X evokes; only the last dequeues. |
| `Shatter` | Per orb: evoke twice. |
| `Darkness` | `OrbCmd.Passive` on each DarkOrb. |
| `TeslaCoil` | Passive on Lightning orbs at a target. |
| `LoopPower` | Sealed, Counter; Passive on `Orbs[0]` at turn start. |
| `Chill` | Channel a Frost per `HittableEnemies`. |
| `BulkUp` | Uses `RemoveSlots`. |

### ⚠ Blocker for "trigger passives" on custom orbs
- `ForgedOrb` does **not** override `OrbModel.Passive`. It ticks through `BeforeTurnEndOrbTrigger` / `AfterTurnStartOrbTrigger` → `OrbRunner.RunPassive` (`ForgedOrb.cs:133-149`). The base `OrbModel.Passive` is an empty virtual (`Models/OrbModel.cs:235-238`).
- So `OrbCmd.Passive` / LoopPower **silently no-op on custom orbs**.
- Fix: add `public override Task Passive(ctx, target) => Source == null ? Task.CompletedTask : OrbRunner.RunPassive(Source, this, ctx, target);`. There is no double-fire, because the tick does not call `Passive`. Add it before any passive-trigger op ships.

### Proposed shapes
| Item | Shape | Describe |
|---|---|---|
| Evoke without consuming | `evoke` + `keep: true` | `Evoke your next orb twice.` (Dualcast = keep pass + normal pass; generalize as `times: 2`) |
| Evoke newest | `evoke` + `which: "newest"` | `Evoke your newest orb.` |
| Trigger passives | `trigger_passive {amount, orbs: first\|all}`; Loop = status `loop` (base `LoopPower`, BF recipe) | `Trigger the passive of your next orb 2 times.` / `At the start of your turn, trigger your next orb's passive.` |
| Lose a slot | `lose_orb_slot {amount}`, card-only, a drawback; validator requires an orb class | `Lose 1 Orb Slot.` |
| On evoke | `on_evoke` trigger (see B5) | — |
| Orb-type counts | `scale: "orb_count"` (damage/block/draw) and `scale: "orb_types"` (distinct `GetType()`, Compile Driver) | `Deal damage equal to the number of orbs you have.` |
| Typed condition | `orb_count_ge` + `status`-style `orb` filter (base names map via `EffectRunner.OrbTypeFor`, `:1016`; custom names via `ForgedCharacters.ResolveOrbType`, `ForgedCharacters.cs:1255`) | — |
| Channel per enemy | `channel_orb` + `per_enemy: true` (count = `HittableEnemies.Count`) | `Channel 1 Frost for each enemy.` |

### Risks
- The custom-orb Passive gap (above).
- `RemoveSlots` to 0 on an orb class: `OrbCmd.Channel` re-adds one slot only if `BaseOrbSlotCount == 0` (`OrbCmd.cs:73-76`). Forged orb classes have `BaseOrbSlotCount = Spec.OrbSlots` (`ForgedClasses.g.cs:522`), so channel then fails silently (`TryEnqueue` false at capacity 0). Validator: lose_orb_slot needs ≥ 3 slots, amount 1.
- "Evoke without consuming" × "evoke N" interacts with `MultiCast` semantics; keep it to a single shape.

### Estimate and tag
- **~11 h.** Passive override 1 h, evoke variants 2 h, trigger_passive + loop 2.5 h, lose slot 1 h, scales 2.5 h, per_enemy 1 h, on_evoke shared with B5.
- Tags: `[BO] evoke <which> keep=<b>`, `[BO] trigger_passive x<n> on '<orb>'`, `[BO] lose_orb_slot -> <cap>`, `[BO] orb_count/orb_types -> <n>`.

**Verdict: GO, after the ForgedOrb.Passive fix.**

---

## B9. Stars (Regent), sizing

### Verified generic (not Regent-gated) state
**Player state:**
- `PlayerCombatState.Stars`, the `StarsChanged` event, `GainStars` / `LoseStars` (`Entities.Players/PlayerCombatState.cs:109-133, 217-232`).
- Playability: `StarCostTooHigh` is checked for **any** card (`:199-212`).

**Commands and hooks:**
- `PlayerCmd.GainStars(decimal, Player)` (`Commands/PlayerCmd.cs:90-96`; hooks `ShouldGainStars` / `AfterStarsGained`), `LoseStars` :104, `SetStars` :119.
- `CardModel.SpendResources` spends stars for any card (`Models/CardModel.cs:1816-1852`).

**Card star cost:**
- `public virtual int CanonicalStarCost => -1` (`CardModel.cs:409`), read lazily through `BaseStarCost` (:411-430). A `DataCard` override is safe in the ctor ordering.
- `CurrentStarCost` :446-465. `HasStarCostX`.
- `TryModifyStarCost` hook (`AbstractModel.cs:2045`).
- `SetStarCostThisTurn` etc. (:1278-1291).

**HUD:**
- `NStarCounter.RefreshVisibility`: `Visible = Visible || Character.ShouldAlwaysShowStarCounter || stars > 0` (`Nodes.Combat/NStarCounter.cs:295-304`).
- `NCombatUi` initializes it for every player and reparents it onto the energy counter (`Nodes.Combat/NCombatUi.cs:319-330`).
- `CharacterModel.ShouldAlwaysShowStarCounter` is `virtual` (`Models/CharacterModel.cs:90`); Regent overrides it true.
- Forged character shells are generated (`ForgedCharacterSlotKK : PlaceholderCharacterModel`, MOD `Cards/Forged/ForgedClasses.g.cs:467`). They can override it from the spec exactly like `BaseOrbSlotCount => Spec.OrbSlots` (:522), which needs a `slotgen.py` change.
- **So the HUD is generic.** Any character shows the counter once stars > 0.

**Card frame:** `NCard.UpdateStarCostVisuals` renders when `HasStarCostX || CurrentStarCost >= 0` (`Nodes.Cards/NCard.cs:924`). It is generic, but **forged cards render through the same card scene. Unverified visually.**

**BaseLib:** no star references, so nothing to fight there.

### What a minimal vertical needs
- **`gain_stars {amount}`**: an `EffectRunner` / `TriggerRunner` op. It is also a payload, as the turn-start income.
- **`star_cost: N`**: a card field (0..5).
  - Plumbing: `CardSpec` field, parse, `DataCard.CanonicalStarCost => Spec.StarCost ?? -1`, upgrade delta through `UpgradeStarCostBy` in `OnUpgrade` (`DataCard.cs:369-389`, a protected base method).
  - Validator: a star-cost card needs a class star income.
- **`when stars_ge`** (`Conditions`) and **`scale:"stars"`**.
- **Class flag `uses_stars`** → `ShouldAlwaysShowStarCounter` in slotgen-generated shells.
- **Python:** schema, VOCABULARY rows, cardgen (star cost is NOT text; it is the frame), validator pricing (1 star ≈ ½ energy is the base exchange rate per `SpendResources` `(energy − have) * 2`), census, coverage/featured (a new `FEATURED_CLASS_KIND` "stars" or a menu entry), gate, archetype (a Regent-style `royal_stars`), exemplars, `render.js` (the site preview must draw a star-cost pip), and `test_featured.py`'s pinned kind set.
- **AutoSlay limitation (§0.1):** stars are never deducted. A smoke proves gain, display and play-gating only.

### Estimate
- **Spike: 2 h.** Confirm three things on a forged class in game: the star counter appears after `gain_stars`, the star pip renders on a forged card, and a star-cost card greys out below cost.
- **Then ~14-18 h**: C# 5 h, slotgen + class flag 2 h, Python harness + featured kind + archetype + exemplars 6-8 h, `render.js` 1 h, smoke 1-2 h.
- That is the whole 2-day window by itself, with no slack for anything else in tier B.

**Verdict: NEEDS-SPIKE. NO-GO for a shared 2-day window. GO only if stars is the window's sole deliverable after a green spike.**

---

## B10. Stun (gap #11 re-open)

### Verified API
**`CreatureCmd.Stun`:**
- `CreatureCmd.Stun(Creature, string? nextMoveId = null)` and `Stun(Creature, Func<IReadOnlyList<Creature>, Task> stunMove, string? nextMoveId = null)` (`Commands/CreatureCmd.cs:871-910`). These call `Creature.StunInternal`, and the wrapper adds `NStunnedVfx` (null-safe).
- `Creature.StunInternal` (`Entities.Creatures/Creature.cs:524-544`):
  - **Throws** `InvalidOperationException` for a player.
  - No-op if dead.
  - If `nextMoveId` is null it uses `Monster.MoveStateMachine.StateLog.Last().Id`. ⚠ That throws if `StateLog` is empty, which is unlikely after the first intent roll but should be guarded.
  - Builds `MoveState("STUNNED", …, new StunIntent()) { FollowUpStateId = nextMoveId, MustPerformOnceBeforeTransitioning = true }` → `Monster.SetMoveImmediate(state)`.
- `MonsterModel.SetMoveImmediate` (`Models/MonsterModel.cs:562-574`) **only replaces the move if `NextMove.CanTransitionAway`**. A move that must be performed once (`MoveState.CanTransitionAway`, `MonsterMoves…/MoveState.cs:26-35`) silently ignores the stun. So:
  - Locked boss moves and phase transitions are naturally immune.
  - A second stun in the same turn is a no-op, because STUNNED itself is MustPerformOnce.
  - After the stun the monster **repeats its last logged move** (FollowUpStateId = last StateLog entry). That is base behaviour.

**Bosses:** no boss check anywhere. `Whistle` (Ancient, 3-cost, Exhaust, 33 damage + `CreatureCmd.Stun(target)`) can hit any enemy. `AsleepPower` (Lagavulin) uses the overload with a custom move.

**There is no StunnedPower.** Stun is a move-state swap, not a power. `AsleepPower` is monster-specific (it casts `Owner.Monster` to `LagavulinMatriarch`), so it is **not** reusable.

### Mod enemy-debuff path
- `ForgedCards.EnemyDebuffStatuses` (`:509`).
- `EffectRunner.ApplyStatus` / `CustomStatusTargets(card, play)` (`EffectRunner.cs:1225-1257`).
- `TriggerRunner.ApplyDebuff` (`:285-292`).
- Stun is **not** a status, so it gets its own op.

### Proposed shape
- `{"op":"stun"}`: a flag-op, card-only, `target: "enemy"` only.
- Describe: `Stun the enemy.` (base keyword `StunIntent` hover tip; the intent icon renders natively).

**Guard rails, needed because stun is a hard lock if it is ever repeatable each turn:**
- Not in `TriggerOps` (never a payload).
- Requires `exhaust` on the card.
- Cost ≥ 2, rarity uncommon or rare.
- At most one stun card per class.
- Never with `return_to_hand` / `retrieve_card` loops (validator cross-check with B3).

**Runtime:**
- `if (target.Monster?.MoveStateMachine.StateLog.Count > 0) await CreatureCmd.Stun(target);` inside try/catch.
- Log whether `NextMove` actually became STUNNED, which proves the CanTransitionAway branch.

### Risks
- The balance lock-down covered by the guard rails.
- A repeat-last-move quirk after stun.
- AutoSlay: the STUNNED move is performed in the enemy turn through the same `PerformMove` path; the NStunnedVfx is added deferred. Low risk, but there is no prior smoke of Whistle under the mod.

### Estimate and tag
- **~4 h.**
- Tag `[BQ] stun '<enemy>': next move <old> -> STUNNED (applied=<bool>)` and `[BQ] stunned turn performed '<enemy>'` (read `Monster.NextMove.Id` at the enemy turn start).

**Verdict: GO, with the guard rails.** It is a policy re-open of gap #11. The original "re-open if a stun primitive is scouted" condition is now met.

---

## Effort roll-up (C# + harness lockstep, excluding release)

| group | est. | verdict |
|---|---|---|
| B1 add_random_card | 7 h | GO |
| B2 replay_next / echo_form | 5 h | GO |
| B3 recursion / put-back / tutor / on_shuffle | 11 h | GO (two slices) |
| B4 cost_delta | 8 h | GO |
| B5 triggers + grant_keyword | 11 h (+2 h on_energy_spent) | GO; on_energy_spent NO-GO (AutoSlay can't prove it) |
| B6 grab-bag | 13 h | GO (mod-native grow; never the base RollingBoulderPower) |
| B7 auto-play | 7 h | GO, no spike (the AutoSlay bot already plays every card through CardCmd.AutoPlay) |
| B8 orb extras | 11 h | GO after the ForgedOrb.Passive override |
| B9 stars | 2 h spike + 14-18 h | NEEDS-SPIKE; NO-GO for a shared 2-day window |
| B10 stun | 4 h | GO with guard rails (policy re-open of #11) |
