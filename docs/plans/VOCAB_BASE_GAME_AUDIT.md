# Base-game card mechanics vs. the forge vocabulary: audit (2026-10-01, vocab v60)

This is a read-only audit. It compares every mechanic used by base-game **player** cards (decompiled STS2,
`_modref/decomp_full/MegaCrit.Sts2.Core.Models.Cards` + the powers those cards apply) against what our closed
vocabulary can express today (`mod/contract/VOCABULARY.md`, `card.schema.json`, `ForgedCards.cs` v60,
`Conditions.cs`, `RELIC_VOCABULARY.md`). It cross-checks each gap against `VOCABULARY_GAPS.md` (#1–#61).

**Scope counted:** 549 cards across the Ironclad, Silent, Defect, Necrobinder and Regent pools (87–88 each), plus
Colorless (64), Event (27) and Token (14). The Status, Curse and Quest pools are excluded. "# base cards" is how many
of those cards use the mechanic, either directly or through the power they apply. Multiplayer-only cards are left
out of the counts.

## Executive summary

1. **Tally:** about **45 base mechanics are covered**, **24 are partial**, **31 are missing and not logged**, and **7 are missing but already logged**. Nearly all of the missing ones have never been triaged. `VOCABULARY_GAPS.md` was built from forge-harness demand, not from the base game.
2. **Stars (Regent resource), 31 cards.** Needs a second spendable counter plus a star-cost channel on `DataCard`. `forge` / `spend_forge` is the template, but the star UI is unverified.
3. **Random card generation, 19 cards** (InfernalBlade, Discovery, WhiteNoise, Calamity…). Needs an `add_random_card {card_type?, pile, choose_of?, free_this_turn?}` op over the forged class pool, built from `CardFactory.GetDistinctForCombat` + `CardSelectCmd.FromChooseACardScreen`.
4. **Self-drawback debuffs, 15 cards** (BattleTrance NoDraw, ExpectAFight, PanicButton, WraithForm, BiasedCognition…). The base `NoDrawPower` / `NoEnergyGainPower` / `NoBlockPower` are concrete classes. The relic path already lands a self-debuff on the owner, so this is cheap.
5. **Doom (Necrobinder execute), 13 cards.** `DoomPower` is concrete. Add `doom` as an enemy debuff, plus `target_has_status:doom` and a `target_status_stacks` scale.
6. **Auto-play other cards, 13 cards** (Havoc, Cascade, Mayhem, Uproar, KnifeTrap…). Uses `CardCmd.AutoPlay` / `CardPileCmd.AutoPlayFromDrawPile`. Needs an AutoSlay risk spike first, since gap #37 rejected forced play.
7. **Self cost modification, 13 cards** (Stomp, MomentumStrike, UpMySleeve, KinglyKick…). Generalize the `held_discount` cost mutation (`EnergyCost.AddThisCombat` / `SetThisCombat`) into event-driven fields.
8. **Scaled hit counts / X-cost hits, 12 + 12 cards (partial)** (Finisher, Flechettes, Whirlwind, Skewer…). Today `scale` and `hits` exclude each other. A `hits_scale` field fixes both.
9. **Enemy Strength loss, 11 cards** (PiercingWail, DarkShackles, Mangle, Malaise…). Needs a per-source `TemporaryStrengthPower` subclass (the gap #26 pattern) plus a negative `StrengthPower` apply.
10. **`on_card_played` type / every-N filter, 11 cards (partial)** (Rage, Storm, Panache, Juggling…). The relic hooks already ship `card_type` + `every_n` (v48), so this only needs exposing on card `add_trigger`. Cheapest high-count win.
11. **Next tier:** replay / play-twice (8: Burst, EchoForm, OneTwoPunch), self-recursion (9), draw-pile tutor (8: SecretWeapon, Wish), on-kill payoffs (6: Sunder, KnockoutBlow), and new history scales (~18).

---

## Missing — not yet logged in VOCABULARY_GAPS.md

| mechanic | base-game example cards | # base cards | character(s) | buildability in our engine (nearest existing pattern) |
|---|---|---|---|---|
| **Stars: second spendable resource + star-cost cards** (gain stars, star cost, star-X, star triggers) | `Venerate`, `Comet` (star cost 5), `Stardust` (star-X hits), `ChildOfTheStars`, `BlackHole`, `Genesis` | 31 | Regent | Large. `PlayerCmd.GainStars`, `CardModel.CanonicalStarCost`, `TryModifyStarCost` exist. Needs a star-cost channel on `DataCard` plus ops `gain_stars` / triggers. Nearest analog is `forge` + `spend_forge` (gap #44's coin ledger, done). Verify the star HUD renders for a non-Regent character. |
| **Random card generation** from your pool, by type, colorless, or "choose 1 of 3"; often free this turn | `InfernalBlade`, `WhiteNoise`, `Discovery`, `Splash`, `Quasar`, `JackOfAllTrades`, `Calamity`/`CreativeAiPower`/`HelloWorldPower` (per turn) | 19 | all | Medium. Same plumbing as `add_card` (`AddGeneratedCardToCombat`) over `CardFactory.GetDistinctForCombat(forged pool)`. Choice uses `CardSelectCmd.FromChooseACardScreen`; free via `SetToFreeThisTurn`. Also wants a payload form for `turn_start`. |
| **Self-drawback debuffs** (no draw, no energy gain, no Block, cards cost +1, lose Str/Dex/Focus per turn, end turn, die if hit, lose orb slot, lose max HP) | `BattleTrance`/`BulletTime` (`NoDrawPower`), `ExpectAFight`, `PanicButton`, `BorrowedTime`, `WraithForm`, `BiasedCognition`, `Hyperbeam`, `Friendship`, `SharedFate`, `BulkUp`, `VoidForm`, `TheGambit`, `BrightestFlame`, `Neurosurge` | 15 | all | Small to medium. The base powers are concrete. Add self-debuff statuses; routing exists (relic "debuff on a self-target hook lands on the owner"). Negative Str/Dex needs `apply_status` to allow a negative amount on self. Price these like `lose_hp`. |
| **Doom** (enemy dies at the end of its turn if HP ≤ Doom), its scales, and Doom triggers | `Scourge`, `Deathbringer`, `BlightStrike` (Doom = damage dealt), `NoEscape`, `TimesUp`, `EndOfDays`, `CountdownPower`, `ReaperFormPower`, `ShroudPower` | 13 | Necrobinder | Small. Apply base `DoomPower` (concrete) as a new enemy debuff in `EnemyDebuffStatuses`. Add `doom` to `target_has_status` and a `target_status_stacks` scale. Doom-on-damage reuses the `on_damage_dealt` payload. |
| **Auto-play other cards** (top of draw, random from draw/discard, from hand at end of turn, a Strike when drawn, Shivs from exhaust, self from exhaust or draw top) | `Havoc`, `Cascade`, `MayhemPower`, `Uproar`, `Catastrophe`, `BeatDown`, `StampedePower`, `HellraiserPower`, `KnifeTrap`, `DecisionsDecisions`, `HowlFromBeyond`, `Bombardment`, `IAmInvincible` | 13 | all | Medium, risky. Uses `CardCmd.AutoPlay` / `CardPileCmd.AutoPlayFromDrawPile`. It is not the "weapon overrides choice" of gap #37 (rejected), but needs the same safety review. Spike under AutoSlay before vocab. |
| **Self cost modification** (cheaper per Attack/Skill played this turn, 0 for the rest of combat after play, ±1 per play, cheaper when drawn, cheaper per Ethereal played or per death, 0 if the summon attacked) | `Stomp`, `Pinpoint`, `MomentumStrike`, `UpMySleeve`, `Modded`, `KinglyKick`, `BansheesCry`, `Melancholy`, `Flatten`, `RocketPunch`, `AdaptiveStrike`, `Transfigure`, `Enlightenment` | 13 | all | Medium. `held_discount` already mutates cost per event (`EnergyCost.AddThisCombat`). Generalize to `cost_delta {on: played/drawn/attack_played/…, amount, scope}` card fields. |
| **Enemy Strength loss** (this turn or permanent; attacks that sap Strength) | `PiercingWail`, `DarkShackles`, `Mangle`, `EnfeeblingTouch`, `CrushUnder`, `DyingStar` (temporary), `Malaise`, `SharedFate`, `Resonance` (permanent), `MonarchsGazePower` | 11 | all | Small. Use a per-source subclass of abstract `TemporaryStrengthPower` (exactly how gap #26 fixed `temp_strength`), plus `StrengthPower` with a negative amount on the target. Custom statuses can't do it: `damage_dealt` is buff-only. |
| **Self-routing recursion** (returns to hand after play or next turn, goes on top of draw, played cards go to top of draw, 0-cost Attacks return) | `ParticleWall`, `Bolas`, `ThrummingHatchet`, `RightHandHand`, `MakeItSo`, `ShiningStrike`, `FeralPower`, `NostalgiaPower`, `ReboundPower` | 9 | all | Medium. Flag-ops on `DataCard`: override `GetResultPileTypeForCardPlay` (`return_to_hand`, `to_draw_top`). Return-next-turn uses the `BeforeHandDraw` card hook (Bolas). The power forms reuse `ModifyCardPlayResultPileTypeAndPosition`. |
| **Tutor from the draw pile** (choose, type-filtered, next turn, on shuffle, all Rares; also exhaust from draw) | `SecretWeapon`, `SecretTechnique`, `Wish`, `SeekerStrike`, `ForegoneConclusion`, `StratagemPower`, `Anointed`, `Cleanse` | 8 | Col, Ev, Reg, Nec | Small. Widen `retrieve_card` `pile` to `draw` with a `card_type` filter (`CardSelectCmd.FromCombatPile(DrawPile)`). `exhaust_card` gains a `pile:draw` source. The on-shuffle form needs a trigger (`AfterShuffle`). |
| **Replay / play-twice** (next N Skills/Attacks/Powers twice, first card each turn twice, +replay on a card) | `Burst`, `OneTwoPunch`, `SignalBoost`, `EchoForm`, `Transfigure`, `HiddenGem`, `DecisionsDecisions` (3×), `SwordSagePower` | 8 | all | Small to medium. A forged power overriding `ModifyCardPlayCount` + `AfterModifyingCardPlayCount` (the `BurstPower` pattern; same shape as `ForgedCorruptionPower`). Op `replay_next {card_type, count}`. |
| **Put-back / draw-pile ordering** (hand → top of draw, discard → top, shuffle hand into draw) | `Glimmer`, `PhotonCut`, `ThinkingAhead`, `Headbutt`, `CosmicIndifference`, `Reboot` | 6 | Iro, Def, Reg, Col | Small. Op `put_back {from: hand|discard, cards: choose}` → `CardPileCmd.Add(…, PileType.Draw, CardPilePosition.Top)`. Reboot = `CardPileCmd.Shuffle`. |
| **On-kill payoff** (if this killed the target: energy, max HP, stars, gold, card reward, repeat) | `Feed`, `Sunder`, `KnockoutBlow`, `HandOfGreed`, `TheHunt`, `EchoingSlash` | 6 | all | Small. `AttackCommand.Results…WasTargetKilled`. Add `when:{kind:"target_killed"}`, valid only after a `damage` op (ordering rule like `spend_forge`/`forged_ge`). Today `gain_max_hp` is unconditional (a Feed approximation). |
| **New history/state scale sources** (exhaust-pile size, discards this turn, cards drawn this combat or this turn, times HP lost, energy spent this turn, cards generated, discard-pile size, total enemy Poison, target's Vulnerable/Doom stacks) | `AshenStrike`, `PactsEnd`, `MementoMori`, `Murder`, `DeathMarch`, `TearAsunder`, `HelixDrill`, `Supermassive`, `Stack`, `Mirage`, `Bully`, `Dominate`, `MoltenFist`, `TimesUp`, `NoEscape`, `SoulStorm`, `PullFromBelow`, `Radiate` | ~18 | all | Small each. Same mechanism as `plays_this_combat` / `hp_lost_this_turn` (`CombatManager.Instance.History` entries: `CardExhaustedEntry`, `CardDiscardedEntry`, `CardDrawnEntry`, `EnergySpentEntry`, `CardGeneratedEntry`). Target-stack reads mirror `target_debuff_count`. |
| **Grant a keyword to another card** (Sly / Ethereal / Retain on a chosen hand card; played Skills gain Sly; Shivs retain) | `HandTrick`, `SculptingStrike`, `Snap`, `MasterPlannerPower`, `PhantomBladesPower`, `CallOfTheVoidPower` | 6 | Sil, Nec | Small. `CardCmd.ApplyKeyword` / `ApplySingleTurnSly` behind the existing hand chooser (the `graft_card` / `purge_card` pick path). Op `grant_keyword {keyword, cards: choose}`. |
| **"Whenever a card is generated" trigger** (incl. Status generated) | `ArsenalPower`, `PillarOfCreationPower`, `SmokestackPower`, `TrashToTreasurePower`, `RocketPunch` | 6 | Reg, Def | Small. New reactive kind `on_card_generated` on `AfterCardGeneratedForCombat`. Pairs with `add_card` / `add_status_card`, which already generate. |
| **Hand-composition conditions/scales** (count of a type in hand, drawn card's type, "no Attacks in hand", fewer cards = more damage) | `Flechettes`, `ExpectAFight`, `Impatience`, `EscapePlan`, `PreciseCut`, `Clash` | 6 | Sil, Iro, Col, Ev | Small. Add a `card_type` qualifier to `cards_in_hand` / `hand_size_ge`. `EscapePlan` needs a "the card just drawn was X" gate after `draw`. |
| **Run-economy effects** (gold, potion, extra card reward, card-removal reward, upgrade at combat end, lose max HP) | `HandOfGreed`, `RoyaltiesPower`, `Alchemize`, `TheHunt`, `ForbiddenGrimoirePower`, `MadScience` (`ImprovementPower`), `BrightestFlame` | 7 | Col, Reg, Sil, Nec, Ev | Medium. `PlayerCmd.GainGold`, `PotionCmd.TryToProcure`, `room.AddExtraReward`. Relics have `combat_end` (heal only); widening it covers the combat-end forms. Balance risk is run-level. |
| **Damage/Block multipliers and debuff amplifiers** (Vulnerable stronger, Weak/Vulnerable doubled on target, ×2 vs Weak targets, first Attack each turn +50%, ×2 Block this turn, first Block each turn ×2, less damage from Vulnerable enemies, self-stacking ×) | `CrueltyPower`, `DebilitatePower`, `TrackingPower`, `LethalityPower`, `Shadowmeld`, `UnmovablePower`, `ColossusPower`, `Hang` | 8 | all | Medium. Forged powers on `ModifyDamageMultiplicative` / `ModifyBlockMultiplicative`. Custom-status `mode: multiplicative` (v47) is the only analog: +10%/stack on `damage_taken`, ×2 cap. |
| **Copy another chosen card** (to hand now, N copies next turn, 3rd Attack each turn copies itself) | `DualWield`, `HeirloomHammer`, `Nightmare`, `JugglingPower` | 4 | Ev, Reg, Sil, Iro | Small to medium. `CreateClone()` of a hand pick + `AddGeneratedCardToCombat` (the `add_card` path with a chosen source). Needs the depth-1 loop rule from `add_card`. |
| **"Whenever you apply a debuff" trigger** | `ViciousPower` (Vulnerable → draw), `SleightOfFleshPower` (debuff → damage that enemy), `ShroudPower` (Doom → Block), `OutbreakPower` (every 3rd Poison → AoE) | 4 | Iro, Nec, Sil | Small. Reactive kind `on_debuff_applied` (`AfterPowerAmountChanged`, applier = owner), optional `status` filter and `attacker`-style "that enemy" target. |
| **Shared or persistent growth across copies** (all copies grow when one is played; grows when drawn; absorbs an exhausted Attack's damage) | `Claw`, `Maul`, `KinglyPunch`, `Thrash` | 4 | Def, Ev, Reg, Iro | Medium. `grow` is per-instance. A `grow_shared` field would iterate `PlayerCombatState.AllCards` of the same id (the Claw `BuffFromClawPlay` pattern). |
| **Per-card-played debuff on the enemy** (target loses HP or gains Doom whenever you play a card this turn) | `Strangle`, `Oblivion`, `MadScience` (Choking) | 3 | Sil, Nec | Small. A forged instanced debuff on `BeforeCardPlayed` / `AfterCardPlayed` (the `StranglePower` pattern). Could be a new custom-status hook (`on_opponent_card_played`). |
| **Block carry and reflect variants** (next turn Block = current Block, same Block for 2 turns, blocked damage reflected) | `Prolong`, `ToricToughness`, `Reflect` | 3 | Col, Ev, Reg | Small. `ripen` can't take `scale:"block"` in a payload. Add a `block_next_turn {scale?}` op (base `BlockNextTurnPower`). Reflect is a forged `AfterDamageReceived` power. |
| **Status-card synergy** (exhaust all Statuses for hits, transform Statuses, first Status drawn → draw) | `FlakCannon`, `Compact`, `IterationPower` | 3 | Defect | Small, once `on_card_generated` exists. Needs a `card_type:"status"` filter on `exhaust_card` / `on_card_drawn` and a `status_cards_owned` scale. |
| **Turn-history conditions** (you exhausted a card this turn, you applied Doom this turn, first play of THIS card this turn, played 5+ cards last turn) | `EvilEye`, `ForgottenRitual`, `DeathsDoor`, `Fetch`, `PaleBlueDotPower` | 5 | Iro, Nec, Reg | Small. New `Conditions.Kinds` read from `History` (`CardExhaustedEntry`, `PowerReceivedEntry`, `CardPlaysFinished` for this card). |
| **Draw to hand size N / fill hand** | `Expertise`, `Scrawl`, `Anointed` (fill with Rares), `CrashLanding` (fill with Debris) | 4 | Sil, Col, Reg | Small. `draw` with `scale:"missing_to"` (N − hand). Clamp to `CardPile.MaxCardsInHand`. |
| **Energy multiplication / energy-spent triggers** | `DoubleEnergy` (gain energy = current energy), `OrbitPower` (every 4 energy spent → energy) | 2 | Def, Reg | Small. `gain_energy scale:"energy"` (only damage/block/draw scale today). `on_energy_spent` + `every_n`. |
| **Overflow damage to other enemies** | `Omnislice` (damage dealt is copied to all other enemies), `EchoingSlash` (repeat AoE per kill) | 2 | Col, Sil | Small. Post-hit `CreatureCmd.Damage` to teammates of the receiver. Shares the result-reading code with on-kill. |
| **Strip enemy Block / Artifact** | `Expose` (lose all Block, remove Artifact, Vulnerable) | 1 | Silent | Trivial. `CreatureCmd.LoseBlock` + `PowerCmd.Remove<ArtifactPower>`. Pairs with `target_has_block`. |
| **Read enemy intent** | `GoForTheEyes` (Weak only if the target intends to attack) | 1 | Defect | Trivial. `when:{kind:"target_intends_attack"}` → `Monster.IntendsToAttack`. Single-target cards only, like `target_has_block`. |
| **Growing per-turn damage power** | `RollingBoulder` (AoE each turn, +5 per turn) | 1 | Colorless | Small. Let the `turn_start` payload `damage` carry `grow` (illegal in payloads today). |

## Missing — already logged

| mechanic | base examples | # base cards | gap # | status / note |
|---|---|---|---|---|
| Enemy stun | `Whistle` (`CreatureCmd.Stun`) | 1 | #11 | **rejected** (the stun half). Base `CreatureCmd.Stun` is a real, scoutable surface now. The rejection said "re-open if a stun primitive is ever scouted", so this re-opens it. |
| Run-permanent per-card growth (stat saved to the deck card) | `GeneticAlgorithm`, `TheScythe` (`DeckVersion…BuffFromPlay`) | 2 | #3 (and #23) | **partial**: `grow` (#23) is per-combat, and `transform_card` covers single-tier rank-up. In-place growth that persists across the run is the open "track" half of #3. |
| Blade structural mutation (blade hits all, blade replays) | `SeekingEdgePower` (SovereignBlade → AllEnemies), `SwordSagePower` (+replay) | 2 | #40 | **partial**: discrete variants are buildable via `transform_card`. In-place target/hit mutation is unbuilt. Replay folds into the new replay mechanic above. |
| Additional base Status cards as a price (Slimed, Void, Debris) | `GunkUp` (Slimed), `Turbo` (Void), `CollisionCourse` / `CrashLanding` (Debris) | 4 | #49 | **not planned** for class-authored curses. `add_status_card` ships dazed/wound/burn only. Adding the 3 base status ids is a vocab enum change, not #49's curse-authoring work. |
| Forced play from hand / when drawn | `StampedePower`, `HellraiserPower` | 2 | #37 | **rejected** (weapon overrides the player's choice). Re-evaluate together with the auto-play row above. |
| Self-damage that retaliates | `InfernoPower` (lose HP each turn; whenever you lose HP on your turn, damage ALL) | 1 | #48 | **planned (verify-then-close)**: `on_hp_lost` + `target:"all_enemies"` already expresses it; the tester has not run yet. |
| Self-recursion out of the exhaust pile | `HowlFromBeyond`, `Bombardment` (auto-play from exhaust each turn) | 2 | #42 / #43 | **rejected** (the graveyard-pile framing). These need no 4th pile, just auto-play from `PileType.Exhaust`, so the request belongs to the auto-play row above. |

## Partial

| mechanic | what we have | what's missing | base examples |
|---|---|---|---|
| X-cost | `cost:"X"` + `scale:"x"` on one damage/block/draw amount | X as **hit count**, X on `apply_status` / `channel_orb` / `evoke` / `summon` / auto-play, X+1 on upgrade, star-X, "X≥4 doubles" | `Whirlwind`, `Skewer`, `Eradicate`, `Volley`, `Malaise`, `Tempest`, `MultiCast`, `Dirge`, `Cascade`, `HeavenlyDrill`, `Stardust` (12) |
| Scaled hit counts | `hits` (fixed) and `scale` (amount); mutually exclusive | `hits` driven by a live count (Attacks or Skills played this turn, orbs, cards exhausted, HP-loss events, energy spent, summon attacks) | `Finisher`, `LunarBlast`, `Flechettes`, `Barrage`, `HelixDrill`, `TearAsunder`, `Rattle`, `PullFromBelow`, `Radiate`, `FiendFire`, `FlakCannon`, `StormOfSteel` (12) |
| `on_card_played` filters | unfiltered `on_card_played`, `once_per_turn` / `once_per_combat`; **relics** have `card_type` + `every_n` (v48) | `card_type` / `every_n` / tag / cost≥N / Ethereal filters on card `add_trigger` | `RagePower` (Attack), `StormPower` / `SubroutinePower` (non-Power), `CalamityPower` (non-Attack), `JugglingPower` (3rd Attack), `PanachePower` (every 5), `DanseMacabrePower` (cost≥2), `SpiritOfAshPower` (Ethereal), `HauntPower` / `DevourLifePower` (Soul), `MakeItSo` (11) |
| Turn-scoped reactive powers | `add_trigger` powers last all combat; `temp_thorns` covers `FlameBarrier` | a `duration:"this_turn"` on a reactive trigger | `Rage`, `CorrosiveWave` (draw → Poison all this turn), `Monologue` (each card → +1 temp Strength) (3) |
| Next card / first N cards free | `cost_shift` `count` + `scope:"this_turn"` | persists until used (not turn-end), Ethereal filter, "first N cards each turn" (cards can't put `cost_shift` in a `turn_start` payload; relics can) | `Unrelenting` (`FreeAttackPower`), `Pounce`, `Synthesis`, `Veilpiercer`, `VoidForm` (5) |
| Retrieve from discard | `retrieve_card` 1–2, choose/random, discard/exhaust → hand | up to N (3), to top of draw, filter (0-cost: `AllForOne`), per-turn payload (`AggressionPower`: random Attack + upgrade) | `Headbutt`, `CosmicIndifference`, `Dredge`, `NeowsFury`, `AllForOne`, `Aggression` (6) |
| In-combat upgrade | `upgrade_card` random/all/choose, **hand only** | discard-pile targets (`DrainPower`), every card in combat (`Apotheosis`), upgrading generated tokens (`HiddenDaggers+`, `StormOfSteel+`, `Reave+`), run-permanent at combat end (`ImprovementPower`) | (5) |
| Combat-scoped transform | `transform_card` / `graft_card`: run-permanent, choose 1 from hand, same-class target | combat-only transform, all/up-to-N of a type, draw-pile source, random target (`EntropyPower`) | `PrimalForce` (all Attacks → GiantRock), `Compact`, `Begone`, `Guards`, `Charge`, `Seance`, `Entropy` (7) |
| Summon variants | `summon`, `summon_attack` (incl. all), `buff_summon`, `heal_summon`, `sacrifice_summon` | scale by summon HP/MaxHP, "summon attacked this turn" gate/scale, summon-HP-lost trigger, "summon hit target → grow", X summons | `Protector`, `Unleash`, `Sacrifice` (2×MaxHP Block), `Flatten`, `Rattle`, `NecroMasteryPower`, `SicEmPower`, `Dirge` (8) |
| Draw-triggered effects | unfiltered `on_card_drawn` | filter by drawn type (Ethereal, Status), "not from hand draw", every-N, card-latent "when THIS is drawn" | `PagestormPower`, `IterationPower`, `SpeedsterPower`, `AutomationPower`, `KinglyKick`, `KinglyPunch`, `DeathMarch` (7) |
| Ethereal-matters | `ethereal` keyword | Ethereal-filtered triggers/scales/costs, apply Ethereal to another card, generate Ethereal copies | `BansheesCry`, `PullFromBelow`, `SpiritOfAsh`, `Pagestorm`, `Veilpiercer`, `CallOfTheVoid`, `SculptingStrike` (7) |
| Shiv / tag payoffs | `tags` + `scale:"tag_cards_owned"`; tokens via `add_card` | tag-scoped damage/Block modifiers, tag-filtered keyword grant, "tokens hit ALL", count tagged cards in exhaust | `AccuracyPower`, `FastenPower` (Defend-tag Block), `PhantomBladesPower`, `FanOfKnivesPower`, `KnifeTrap`, `SoulStorm` (6) |
| Retain variants | `retain` keyword, `cards_retained`, `retained_last_turn`, `grow_held` / `held_discount` | retain your whole hand this turn (`RetainHandPower`), choose N to retain each turn, grant Retain to another card | `Equilibrium`, `Convergence`, `Salvo`, `WellLaidPlans`, `Snap` (5) |
| Orb operations | `channel_orb` (incl. random/custom), `evoke` oldest, `gain_orb_slot`, `focus` / `temp_focus`, `orbs_match`, `orb_count_ge` | evoke without consuming, evoke newest, trigger a passive, lose a slot, orb-type and distinct-type scales/conditions, `on_evoke` trigger, channel per enemy, channel count from history | `Dualcast`, `Quadcast`, `Shatter`, `MultiCast`, `ConsumingShadowPower`, `Darkness`, `TeslaCoil`, `LoopPower`, `BulkUp`, `Barrage`, `CompileDriver`, `Synchronize`, `CoolantPower`, `HailstormPower`, `ThunderPower`, `Chill`, `Voltaic` (17) |
| Hand-wide discard / exhaust with a count | `exhaust_card cards:"all"` (whole hand) | `discard` "all" (random/choose only), and a scale for "how many were just removed" | `FiendFire`, `StormOfSteel`, `CalculatedGamble`, `Stoke`, `Eidolon`, `ShadowStep` (6) |
| Poison extras | `poison`, `on_poison_damage`, `when target_has_status poison`, `spread_debuffs` | extra ticks (`AccelerantPower`), total-enemy-Poison scale, every-N Poison application, Poison the **struck** enemy from `on_damage_dealt` (payload `enemy` = first enemy), repeated random-target apply | `Accelerant`, `Mirage`, `Outbreak`, `Envenom`, `BouncingFlask` (5) |
| Random-target trigger payloads | payload `target`: enemy (first) / all_enemies / attacker | `random_enemy` in a payload | `JuggernautPower`, `SerpentFormPower`, `CountdownPower`, `HauntPower` (4) |
| Per-turn choose payloads | `turn_start` payload `discard` (random only); `exhaust_card` is card-only | choose-discard / choose-exhaust / choose-transform each turn | `ToolsOfTheTradePower`, `TyrannyPower`, `EntropyPower` (3) |
| Damage-dealt-as-X | `scale:"damage_dealt_unblocked"`, heal only | Block = damage dealt (incl. overkill), Doom = damage dealt | `Fisticuffs`, `BlightStrike` (2) |
| Additive debuff-count damage | `scale:"target_debuff_count"` (damage **equal to** the count) | base + N per non-temporary debuff | `Rend` (1) |
| Conditional extra hits | `when target_has_status` / `hp_lost_ge` can gate one `damage` | ungated hit + gated extra hits on one card ("one damage per card") | `Dismantle`, `Spite` (2) |
| Playability restriction | a `when` gate on the payoff (`draw_pile_empty`) | true "unplayable unless" (card greyed out) | `GrandFinale`, `Clash`, `HighFive` (3) |
| Cost ceiling | cost 0–4 (4 rare-only) | cost 5+ (usually paired with self-reduction) | `MeteorStrike` (5), `BansheesCry` (9) (2) |
| Stars-like spend resource | `forge` + `spend_forge` + `forged_ge` (forge classes only) | an alternate **card cost** in that resource, plus gain/spend triggers (listed as Missing above; this row records the analog) | `Comet`, `Alignment`, `RoyalGamble` (see Stars) |

## Covered

| base mechanic | our primitive | base examples |
|---|---|---|
| Single / AoE / random / multi-hit damage | `damage` (+`hits`), target `enemy` / `all_enemies` / `random_enemy` | `StrikeIronclad`, `TwinStrike`, `Thunderclap`, `SwordBoomerang`, `Ricochet` |
| Unblockable damage | `damage` `unblockable` | `CaptureSpirit` |
| Block / Draw / Energy / Heal | `block` / `draw` / `gain_energy` / `heal` | `DefendSilent`, `Skim`, `Bloodletting`, `NotYet` |
| Self HP cost | `lose_hp` | `Hemokinesis`, `Offering`, `BloodWall`, `Brand` |
| Gain max HP | `gain_max_hp` (unconditional) | `Feed` (kill gate missing, see on-kill) |
| Vulnerable / Weak / Poison | `apply_status` | `Bash`, `Neutralize`, `DeadlyPoison` |
| Strength / Dexterity / Thorns / Plating | `strength` / `dexterity` / `thorns` / `metallicize` | `Inflame`, `Footwork`, `Caltrops`, `StoneArmor` |
| Buffer / Blur / Intangible / Barricade / Focus | same-named statuses | `Buffer`, `Blur`, `Apparition`, `Barricade`, `Defragment` |
| Temporary Str / Dex / Focus | `temp_strength` / `temp_dexterity` / `temp_focus` | `SetupStrike`, `FeedingFrenzy`, `Anticipate`, `FocusedStrike`, `Hotfix` |
| Vigor / Double Damage | `vigor` / `double_damage` | `Patter`, `Terraforming`, `PrepTimePower`, `ShadowStep` (next turn via `ripen`) |
| Exhaust / Ethereal / Innate / Retain / Sly keywords | flag-ops | `TrueGrit`, `Defile`, `Assassinate`, `Snakebite`, `FlickFlack`, `Tactician` |
| Upgrade adds/removes a keyword, lowers cost | `upgrade` keyword append/drop, `upgrade.cost` | `Hologram` (loses Exhaust), `Aggression` (+Innate), `Barricade` (cost −1) |
| Exhaust other hand cards (choose/random/up-to/all-of-type) | `exhaust_card` | `BurningPact`, `Cinder`, `SecondWind`, `Purity`, `Brand` |
| Discard (choose/random) | `discard` | `Survivor`, `Acrobatics`, `DaggerThrow`, `Prepared`, `HiddenDaggers` |
| Draw until a type | `draw_until` | `Pillage` |
| Return a card from discard (choose) | `retrieve_card` | `Hologram`, `Graveblast` |
| Add base Status cards as a price | `add_status_card` (dazed/wound/burn) | `BoostAway`, `FightThrough`, `Overclock` |
| Copy of self into a pile | `add_card` (self-reference) | `Anger`, `Undeath` |
| Class tokens into hand/draw/discard (incl. per turn) | `add_card` (+ `turn_start` payload) | `BladeDance`, `CloakAndDagger`, `GraveWarden`/`Reave` (Soul), `InfiniteBladesPower`, `SentryModePower` |
| Upgrade hand cards | `upgrade_card` | `Armaments` |
| Skills cost 0 and Exhaust | `corruption` | `Corruption` |
| Damage = your Block / double your Block | `scale:"block"` | `BodySlam`, `Entrench` |
| Per-tag scaling | `tags` + `tag_cards_owned` | `PerfectedStrike`, `CrescentSpear`-style, `Squeeze` (OstyAttack tag) |
| Damage = draw-pile size / cards played this combat | `draw_pile_count` / `plays_this_combat` | `MindBlast`, `GoldAxe` |
| Grows each play | `grow` | `Rampage` |
| Only after the deck is drawn | `when draw_pile_empty` | `GrandFinale` |
| Fewer than N cards played this turn | `when cards_played_this_turn_ge` + `negate` | `Ftl` |
| Lost HP this turn gate | `when hp_lost_ge` | `Spite` (approx.) |
| Only card in hand | `when hand_size_ge` + `negate` | `Restlessness` |
| If target is poisoned | `when target_has_status` | `BubbleBubble` |
| Copy the target's debuffs to all other enemies | `spread_debuffs` | `Misery` |
| Per-turn engines (Strength, Poison all, Block, Forge, energy, draw) | `add_trigger turn_start` / `turn_end` | `DemonFormPower`, `NoxiousFumesPower`, `CrimsonMantlePower`, `FurnacePower`, `PyrePower`, `DemesnePower`, `MachineLearningPower` |
| Next-turn energy / Block / draw / summon / bomb | `add_trigger ripen` (amount 1–3) | `ChargeBattery`, `Delay`, `Scavenge`, `DodgeAndRoll`, `Glitterstream`, `Predator`, `Glow`, `Relax`, `Invoke`, `TheBomb` |
| Whenever exhausted → Block / draw | `on_exhaust` | `FeelNoPainPower`, `DarkEmbracePower` |
| Whenever you lose HP → Strength / AoE | `on_hp_lost` (+ targeted payload) | `RupturePower`, `InfernoPower` (#48 verify) |
| Whenever you gain Block → damage | `on_block_gained` + targeted `damage` | `JuggernautPower` (first enemy, not random) |
| Whenever you play a card → Block | `on_card_played` | `AfterimagePower` |
| Retaliation this turn | `temp_thorns` | `FlameBarrier` |
| Lightning / Frost / Dark / random orbs, Plasma / Glass | `channel_orb` (+ custom `orb_pool` recipes) | `Zap`, `ColdSnap`, `Null`, `Chaos`, `Rainbow`, `Fusion`, `Glasswork`, `Refract` |
| Evoke N, orb slots, Focus, per-turn channel | `evoke`, `gain_orb_slot`, `focus`, `turn_start channel_orb` | `Dualcast`-lite, `Capacitor`, `Defragment`, `LightningRodPower`, `SpinnerPower` |
| Osty: summon / grow / attack through / heal / buff / sacrifice | `summon`, `summon_attack`, `heal_summon`, `buff_summon`, `sacrifice_summon` | `Bodyguard`, `Reanimate`, `Poke`, `HighFive`, `Spur`, `CalcifyPower`, `BoneShards` |
| Forge, Sovereign Blade, Summon Forth, Parry | `forge`, `scale:"forged"`, `summon_blade`, `on_blade_played` | `WroughtInWar`, `Bulwark`, `TheSmith`, `SummonForth`, `ParryPower` |
| Blade double damage vs a target | `blade_empower` (≈; all targets, one turn) | `Conqueror` |
| Next card of a type is cheaper/free this turn | `cost_shift count` | `Pounce`, `Synthesis` (this-turn form) |
| Max-energy / hand-size powers | `turn_start gain_energy` / `draw` | `PyrePower`, `FriendshipPower` (+energy half), `ToolsOfTheTradePower` (draw half) |

(Not every row above is a separate mechanic; the table has 45 covered rows. Reverse finding: our
`frail`, `regen`, `ritual` and an applied `artifact` are used by **no** STS2 player card. They are STS1 carry-overs,
still valid for forged classes.)

## Excluded / out of scope

**Excluded:**
- The 21 **multiplayer-only** cards and their powers: `DemonicShield`, `Tank`, `Flanking`, `Sneaky`, `EnergySurge`, `Ignition`, `GlimpseBeyond`, `LegionOfBone`, `HammerTime`, `Largesse`, `BeaconOfHope`, `BelieveInYou`, `Coordinate`, `GangUp`, `HuddleUp`, `Intercept`, `Knockdown`, `Lift`, `Mimic`, `Rally`, `TagTeam` (ally targeting, Covered/Guarded/Flanking).
- The Status / Curse / Quest pools, and Token Status cards chosen from events (`Disintegration`, `MindRot`, `Sloth`, `WasteAway`).
- Monster-only powers.
- The `Ancient` rarity tier: 18 cards such as `Break` and `Whistle`, an acquisition channel rather than a mechanic.
- `MadScience`'s event-driven self-customization (gap #50 territory).
- The Byrdpip pet attack in `ByrdSwoop`.
- **Enchantments**: `BladeOfInk` → Inky on Shivs; `HiddenGem` uses the enchant replay count. A small card-granted surface, worth a look only after replay ships.
- `CardKeyword.Eternal` (`ForbiddenGrimoire`, `EternalArmor`), and UI-only glow and preview code.

**Caveat:** card behavior was read from decompiled `OnPlay` and power hooks. There is no localization text, so the counts are code-derived and may be off by one or two at the edges.
