using MegaCrit.Sts2.Core.Entities.Cards;

namespace BlankTheSpire.BlankTheSpireCode.Engine;

/// <summary>
/// The data-driven "slot" runtime (plan §10.1 / P1) and slot-file store (P2). The mod ships a fixed set of
/// generic <c>ForgedCardSlotNN</c> classes (see Cards/Forged); each, at construction during
/// <c>ModelDb.InitIds</c>, asks this loader for its <see cref="CardSpec"/>. Specs come from JSON files in the
/// writable user-data dir (<c>user://forged/cards/NN.json</c>) — so adding a card is writing a file, with no
/// SDK, no recompile, and (via in-code loc in <see cref="DataCard"/>) no .pck rebuild.
///
/// JSON shape matches the baked codegen corpus (mod/content/cards/*.json): id, name, type, rarity, cost,
/// target, effects[], optional upgrade.effects[], optional description/text. Every spec is re-validated
/// against the live EffectRunner vocabulary via <see cref="TryParseCardJson"/>; anything unsupported is
/// rejected (the slot stays empty and a reason is logged/surfaced) rather than crashing init. That same
/// validator is the safety boundary for the P2 paste-import path (see <see cref="BTS1Codec"/>).
///
/// Slots are read once at startup (Q2: pools freeze at init), so new files require a game restart.
/// </summary>
public static class ForgedCards
{
    /// <summary>How many <c>ForgedCardSlotNN</c> classes the mod ships. Keep in sync with slotgen.py.</summary>
    public const int SlotCount = 40;

    /// <summary>The closed-vocabulary version this build understands. BTS1 codes carry the version they were
    /// generated against; the importer rejects codes that need a newer one. Bump when the vocab grows.
    /// v2 (vocab grow): + statuses strength/dexterity/frail/poison, + ops gain_energy/lose_hp/heal/exhaust.
    /// v3 (breadth): + statuses thorns/regen/metallicize/artifact/buffer/intangible/ritual/blur/temp_strength/
    /// temp_dexterity/barricade (all self-buffs), + keyword ops innate/retain/ethereal.
    /// v4 (structural-lite): + multi-hit on `damage` (the `hits` field → deal Amount damage Hits times).
    /// v5 (X-cost): + `cost:"X"` cards with `scale:"x"` on a damage/block/draw effect (amount = energy spent).
    /// v6 (orbs, Phase G — execution path; not in the LLM contract until G3): + ops channel_orb(orb)/evoke/
    /// gain_orb_slot, + status focus; + CharacterSpec.OrbSlots (starting orb slots via BaseOrbSlotCount).
    /// v7 (composition, Phase H): + `orb:"random"`, + per-effect `when` conditions (orbs_match/orb_count_ge/
    /// target_has_status/no_block/hp_below_half) — the effect runs only when the predicate holds.
    /// v8 (triggers, Phase H3): + `add_trigger` op (trigger turn_end/turn_start + a nested self/orb-only
    /// `effects` payload + optional fire-time `when`) — grants an ongoing power that runs the payload each
    /// turn (see ForgedTriggerPower / TriggerRunner).
    /// v9 (forged orbs, Phase I): + CharacterSpec.OrbPool (a class's ordered base/custom orb list, ≤3 custom
    /// orb defs read from `orb_pool`; see ForgedCharacters / ForgedOrb / OrbRunner). Class cards may channel a
    /// custom orb by pool name (the `channel_orb` op gains `allowCustomOrbs`); shared cards stay base-only.
    /// v10 (forged statuses, Phase J): + CharacterSpec.StatusPool (a class's ≤4 custom modifier-family statuses
    /// read from `status_pool`; see ForgedCharacters / ForgedStatusPower). Class cards may apply a custom status
    /// by pool name via the `apply_status_custom` op (class-only, like custom-orb channels).</summary>
    public const int VocabVersion = 55; // 55: Phase BA (VOCAB_GAP_REMEDIATION Wave 4) — FORGED POTIONS.
                                        //     A new CHARACTER-level array `potion_pool` (0..MaxPotions entries): the
                                        //     class's own signature potion — {name, emoji, rarity, usage, target,
                                        //     description, effects[]}. Effects are the RELIC sub-vocabulary (no card,
                                        //     a ctx + targets) minus the drawback ops, plus `apply_status_custom` so a
                                        //     status class's potion can hand out its OWN status. The potion lands in
                                        //     that class's own ForgedClassPotionPoolKK, which PotionFactory
                                        //     concatenates with the base game's SharedPotionPool at roll time — so it
                                        //     is an EXTRA entry in the normal drop table, never a replacement. No new
                                        //     card op and no card-text change; every pre-v55 class parses unchanged
                                        //     (an absent potion_pool means the class contributes no potion, which is
                                        //     exactly today's behaviour). See Powers/ForgedPotion.cs.
                                        // 54: Phase AY (VOCAB_GAP_REMEDIATION Wave 4) — RUN-PERSISTENT FORGE.
                                        //     A new CHARACTER-level flag `forge_persist` (bool, default false,
                                        //     FORGE-CLASS ONLY): the class BANKS min(Forge, ForgedForgePower.PersistCap)
                                        //     at combat end and gets it back at the start of its first turn of the next
                                        //     combat (through Stoke, so the blade is summoned too). The bank rides the
                                        //     RUN SAVE — a BaseLib SavedSpireField<Player,int> on SerializablePlayer —
                                        //     so it survives save-and-quit. No new card op, no card-text change; the
                                        //     Forge tooltip now covers both regimes. See Engine/ForgePersist.cs.
                                        // 53: Phase AX (VOCAB_GAP_REMEDIATION Wave 4) — STRUCTURAL CAPS + THE #44/#45 OPS.
                                        //     Card `cost` ceiling 3 -> 4 (the heavyweight slot: RARE-ONLY, and the upgrade
                                        //     `cost` band widens with it); `tags` maxItems 2 -> 3.
                                        //     An UPGRADE MAY CHANGE ONE KEYWORD: the upgrade effect list may append exactly one
                                        //     of exhaust/retain/innate/ethereal, or drop a trailing exhaust (BaseLib
                                        //     UpgradeKeywords via WithKeyword(kw, UpgradeType.Add/Remove)); every other shape
                                        //     still requires an exact count match.
                                        //     TWO-OF-A-KIND STATUSES: a card may declare the SAME apply_status twice when the
                                        //     SECOND one is `when`-gated — it takes a suffixed var ("Weak2") and applies with a
                                        //     literal amount, so the DynamicVarSet never sees a duplicate key.
                                        //     New CARD ops: `spend_forge` (amount 1..10 — consume that much of your Forge counter
                                        //     as the card's PRICE; gap #44 re-sketch, pairs with when:forged_ge) and
                                        //     `spread_debuffs` (flag-op — copy the struck target's Vulnerable/Weak/Frail/Poison
                                        //     onto every OTHER living enemy; gaps #45–#47 re-sketch, single-enemy cards only).
                                        //     Both are card-only, never on a BASIC, at most one per card. [AX] tags on every path.
                                        // 52: Phase AV (VOCAB_GAP_REMEDIATION Wave 4) — THE AUTONOMOUS MINION MODEL IS BACK.
                                        //     The K-3 summon_pool fields are live again (dormant since the v15 true-Osty refit):
                                        //     `moves`/`actions` (a per-turn action cycle the minion runs at the end of your turn),
                                        //     `attackable:false` (ETHEREAL — no HP bar, never meat-shields), `on_summon` (battle cry,
                                        //     now actually RUN by EffectRunner.SummonForged) and `on_death` (enemy-facing rattle).
                                        //     New spec field `on_nth_attack` { n: 2..5, actions: [...] } — every Nth hit the minion
                                        //     DEALS runs the payload (ForgedSummonPower.AfterDamageGiven, re-entrancy-guarded).
                                        //     FindLivingSummon is name-keyed so MaxSummons = 2 is reachable (two differently named
                                        //     minions coexist); every other op still means the FRONT-most living one ("your summon").
                                        //     New CARD op `sacrifice_summon` (flag-op, class-only, card-only, never on a BASIC, at most
                                        //     one per card, never a card's only effect): kills your front-most minion via the game's
                                        //     CreatureCmd.Kill so its on_death rattle fires; the rest of the card is the payoff.
                                        //     Describe: "Sacrifice your summon." [AV] tags on every new path.
                                        // 51: Phase AU (VOCAB_GAP_REMEDIATION W0.2-B) — on_discard FIRES ON BASE-GAME DISCARDS.
                                        //     DataCard overrides the game's own CardModel hook AfterCardDiscarded (CardCmd.Discard →
                                        //     Hook.AfterCardDiscarded reaches every card in every pile, the just-discarded one included),
                                        //     so a Reflex payload now fires for ANY effect discard — our discard/scry ops AND base-game
                                        //     sources (Gambling Chip, Gambler's Brew, other-class discard cards). No Harmony patch; the
                                        //     mod ops stopped firing it themselves (double-fire). Turn-end cleanup still never fires it
                                        //     (CombatManager flushes via CardPileCmd.Add + Hook.AfterFlush). No new token, no describe
                                        //     change. [AU] tag carries source=mod-op|base-game (EffectRunner.ModDiscardDepth).
                                        // 50: Phase AT (VOCAB_GAP_REMEDIATION Wave 3) — SUMMON DAMAGE COUNTS AS "YOU DEAL DAMAGE".
                                        //     on_damage_dealt (the add_trigger kind AND the relic hook) now fires when the owner's PET
                                        //     deals damage (summon_attack: pet is the dealer, no card) — the base game's own idiom
                                        //     (ReaperFormPower / HandDrill: `dealer.PetOwner?.Creature == Owner`). No new token, no
                                        //     describe change ("Whenever you deal damage" was already the sentence); the contract
                                        //     wording drops "card". Engine: ForgedTriggerPower / ForgedRelic AfterDamageGiven, [AT] tag.
                                        // 49: Phase AR (VOCAB_GAP_REMEDIATION Wave 3) — CONDITIONS INSIDE CUSTOM ORB EFFECTS. An
                                        //     orb_pool custom orb's passive/evoke effect may carry a `when` gate (any Conditions.Kinds
                                        //     entry except the chosen-target / retained reads — an orb fires with no card/target, the
                                        //     trigger rule; OrbRunner evaluates it at fire time, the tooltip prints "… if …"). A custom
                                        //     orb also gains `passive_timing` (turn_end default = BeforeTurnEndOrbTrigger; turn_start =
                                        //     the game's Plasma hook AfterTurnStartOrbTrigger) and a passive `gain_energy`/`draw` MUST
                                        //     be turn_start (dead at turn end). No base orbs added: Plasma / Glass are VOCABULARY.md
                                        //     custom-orb recipes. Engine: OrbSpec / ForgedCharacters.TryParseOrbEffects+TryParseCustomOrb
                                        //     / OrbRunner / ForgedOrb.
                                        // 48: Phase AS (VOCAB_GAP_REMEDIATION Wave 3) — RELIC VOCABULARY. Relic hooks gain a
                                        //     `card_type` filter (on_card_played only: attack/skill/power — CardModel.Type) and an
                                        //     `every_n` per-combat counter (2..9: fires on the Nth, 2Nth… matching occurrence; the
                                        //     icon shows the running count). Modifiers gain `attack_base` (+N to every card attack,
                                        //     1..5) and `max_hp` (±N Max HP once on obtain, |N| <= 30 — the negative form is the
                                        //     sanctioned price of a flat energy stat). New relic drawback op `discard` (1..2 random)
                                        //     and a debuff on a self-target hook now lands on the owner ("you gain 1 Weak"). No
                                        //     card-level change. Engine: RelicSpec / ForgedCharacters.TryParseRelic* / RelicRunner /
                                        //     ForgedRelic (AfterObtained max_hp, AfterCardPlayed type, ShowCounter) / EffectRunner.
                                        // 47: Phase AQ (VOCAB_GAP_REMEDIATION Wave 3) — STATUS-POOL HOOKS. Two new class
                                        //     `status_pool` hooks: `damage_over_time` (DEBUFF, must decay — at the start of the
                                        //     afflicted enemy's turn it loses HP equal to its stacks, unblockable + unpowered like
                                        //     Poison; ForgedStatusPower.AfterSideTurnStart + CreatureCmd.Damage) and `hit_count`
                                        //     (BUFF, must decay — your card attacks hit +stacks extra times;
                                        //     ModifyAttackHitCount gated on AttackCommand.Attacker == Owner). `mode: multiplicative`
                                        //     opens on damage_dealt / damage_taken (×(1 + 0.1·stacks), capped ×2, powered attacks
                                        //     only; ModifyDamageMultiplicative). No card-level change: cards still apply by name via
                                        //     apply_status_custom. Closes the burn/DoT fantasy (VOCAB_EXPANSION_2 §6).
                                        // 46: Phase AP (VOCAB_GAP_REMEDIATION Wave 3) — PILE MANIPULATION AND STATUS CARDS.
                                        //     `discard` gains `cards: random|choose` (choose = the player picks which hand cards
                                        //     to discard via the base-game hand picker — CardSelectCmd.FromHandForDiscard; card-only,
                                        //     a payload discard stays random). New card-only op `retrieve_card {pile: discard|exhaust,
                                        //     cards: random|choose, amount?: 1..2}` — return card(s) from a pile to your hand (the
                                        //     Headbutt / Exhume shape; CardSelectCmd.FromCombatPile + CardPileCmd.Add; Status/Curse
                                        //     cards are never retrieved). New card-only op `add_status_card {card: dazed|wound|burn,
                                        //     pile: hand|discard|draw, amount?: 1..3}` — generate base-game Status cards as the
                                        //     self-drawback of an over-statted card (Wild Strike / Power Through / Overclock;
                                        //     CombatState.CreateCard<T> + AddGeneratedCardToCombat). Closes VOCAB_EXPANSION F4.
                                        // 45: Phase AO (VOCAB_GAP_REMEDIATION Wave 3) — CARD-TYPE-SCOPED COST MODIFIERS.
                                        //     New card-only op `cost_shift {card_type: attack|skill|power|all, amount: 1..2,
                                        //     scope: this_turn|combat, count?: 1..3}` — "Your Attacks cost 1 less this turn" /
                                        //     "Your next Skill costs 2 less this turn" / "Your Skills cost 1 less this combat"
                                        //     (ForgedCostShiftPower: ONE power holding a list of live discounts; the early
                                        //     TryModifyEnergyCostInCombat pass, so it composes with relic cost_reduction and
                                        //     Corruption). Also a relic hook op (this_turn only). scope:combat is amount-1 +
                                        //     rare-only (generation side) and ≤1 per class (character_validator).
                                        // 44: Phase AN (VOCAB_GAP_REMEDIATION Wave 3) — SMALL OPS. New card-only op
                                        //     `gain_max_hp` (1..5; the base-game Feed payoff: raise Max HP AND heal that
                                        //     much), a `damage` flag `unblockable:true` (ValueProp.Unblockable rides the
                                        //     damage var, so preview and resolution both ignore Block; card-level only),
                                        //     and two one-turn self-buffs `temp_thorns` / `temp_focus` (CustomTemporaryPowerModel
                                        //     shells like temp_strength; temp_focus is orb-class-only like focus).
                                        // 43: Phase AM (VOCAB_GAP_REMEDIATION Wave 3) — NEW SCALES AND CONDITIONS. Card-level
                                        //     scale += block (Body Slam / Entrench), hp_lost_this_turn (the AD snapshot read),
                                        //     draw_pile_count, energy (cost-0 ONLY — preview and resolution agree), plays_this_combat
                                        //     (the cards you have played this combat, PLAYER-level; the per-instance count stays
                                        //     `grow`). block/hp_lost/draw_pile/plays are damage/block-only; energy is damage/block/draw.
                                        //     `when` += target_hp_below_half / target_has_block (chosen-target reads: single-enemy
                                        //     cards only, never in a trigger), energy_ge {1..6} / cards_played_this_turn_ge {1..10}
                                        //     (player reads; legal as a trigger gate). One ScaleValue case each; Conditions
                                        //     Kinds/Validate/Eval/Phrase. Log tag [AM].
                                        // 42: Phase AL (VOCAB_GAP_REMEDIATION Wave 3) — RICHER TRIGGER PAYLOADS: apply_status_custom /
                                        //     summon_attack / buff_summon inside add_trigger payloads (class-only), `hits` on a payload
                                        //     damage/summon_attack, payload scale += cards_in_hand / unspent_energy_last_turn / forged
                                        //     (a targeted payload damage may be scaled). 41: Phase AK — ATTACKER TARGET + ONCE PER COMBAT.
                                        //     (1) A trigger-payload effect on the `attacked` trigger may carry
                                        //     target:"attacker": ForgedTriggerPower hands the AfterDamageReceived dealer
                                        //     into TriggerRunner.Run(attacker:), and ResolveEnemies resolves it (the
                                        //     RelicRunner L-3 pattern) — a riposte now hits the enemy that STRUCK you, not
                                        //     the first hittable one (closes the gap #4 nuance + the J-3 "true Thorns" item).
                                        //     Wording: "… to the attacker". (2) `once_per_combat` on add_trigger for the
                                        //     POWER-HOSTED reactive kinds (every MultiFireTrigger except the card-latent
                                        //     on_discard): a fired flag on the per-combat power instance (the relic-hook
                                        //     pattern, RelicRunner.Fire). Never combined with once_per_turn. Wording:
                                        //     "… (once per combat)."
                                        // 40: Phase AJ (VOCAB_GAP_REMEDIATION Wave 1) — HIDDEN CAPACITY. No new runtime
                                        //     mechanic; the contract catches up with what the engine already runs. (1) Card
                                        //     target `random_enemy` exposed (TargetMap/Describe had it; BaseLib CardAttack
                                        //     rolls a random hittable enemy PER HIT, CommonActions.Apply/GetTargets one random
                                        //     enemy per status effect) — each effect rolls independently, so a random_enemy
                                        //     card may not carry `when:target_has_status` / `scale:target_debuff_count` (no
                                        //     chosen target to read); status wording gains " to a random enemy". (2) Trigger-
                                        //     payload `channel_orb` accepts any orb in the class's pool (TriggerRunner already
                                        //     resolved custom names; validation pinned base orbs). (3) Class import rejects a
                                        //     channel_orb naming an orb outside base ∪ the class's custom pool (was: silently
                                        //     channeled Lightning at runtime; EffectRunner/OrbRunner now warn + skip). (4)
                                        //     `hits` on summon_attack + once_per_turn on on_blade_played: generation-side
                                        //     gates opened to match this file (no C# change).
                                        // 39: Phase AI (gap #7) — GRAFT. New op `graft_card` {card_id}: the CHOOSE form of
                                        //     transform_card (as purge_card is the choose form of purge). When played, YOU pick a
                                        //     card in HAND (CardSelectCmd.FromHand) and THAT picked card PERMANENTLY becomes the
                                        //     named same-class card for the rest of the run (deck original swapped + the picked
                                        //     hand clone transformed now). Reuses ResolveTransformTarget (no-chain / no-self /
                                        //     same-class) + the purge DeckVersion guard (null-DeckVersion pick = combat-only).
                                        //     Guards: same-class + exists · not on BASIC · card-only · ⊥ purge/purge_card · counts
                                        //     toward the same ≤3 transform-family cap (warning). Delivers the transform-the-picked-
                                        //     card half of gap #7; a true "consume X to buff Y" transfer stays a wave-5+ follow-up.
                                        // 38: Phase AH (gaps #35/#38) — TRANSFORM_CARD. New op `transform_card` {card_id}:
                                        //     when the carrying card is PLAYED it PERMANENTLY becomes that same-class card
                                        //     for the rest of the run (deck original swapped via CardCmd.Transform under the
                                        //     purge DeckVersion guard; this combat's in-hand clone is transformed too so the
                                        //     change is felt immediately). Guards: same-class + exists · not on BASIC · card-
                                        //     only · ⊥ purge · no transform CHAINS (target may not itself carry transform_card;
                                        //     a two-card mode-swap A↔B is ALLOWED — each target is a leaf w.r.t. the OTHER) ·
                                        //     self-transform (card_id == own id) rejected · class cap ≤3 (warning).
                                        // 37: Phase AG (gap #39) — UPGRADE-COST CHANNEL. The `upgrade` object gains an
                                        //     optional `cost` (0..3) = the card's ABSOLUTE cost after upgrade (upgrades
                                        //     cheapen, never tax: cost <= base; not on X-cost cards). CardSpec.UpgradedCost;
                                        //     DataCard rebuilds the energy cost via MockSetEnergyCost on the Upgraded event
                                        //     (covers live/rest-site/deck-load). The signature blade's upgrade now drops 2→1.
                                        // 36: Phase AF (gap #41) — BLADE EMPOWER. New op `blade_empower` {amount 2..3}:
                                        //     a one-turn ×N multiplier on the forge class's signature blade token (a
                                        //     burst spike distinct from the slow Forge ramp). Applies ForgedBladeEmpower
                                        //     Power (refresh, not stack; cleared at your next turn start); the blade's
                                        //     scale:"forged" calc multiplies its total by N (token-scoped). Forge-class
                                        //     only + card-only (generation-gated). Rejected in add_trigger payloads.
                                        // 35: Phase AE (gap #25) — CARD TAGS. New optional card field `tags` (1..2
                                        //     lowercase slugs, declarative) + new ADDITIVE scale `tag_cards_owned`
                                        //     (damage/block only) requiring a sibling `tag`: resolves to printed
                                        //     amount + the count of cards carrying that tag across your combat piles
                                        //     (Perfected-Strike synergy). Live deck scan (EffectRunner.TagCardsOwned).
                                        // 34: Phase AD (gap #12) — HP-LOST GATE. New `when` condition `hp_lost_ge`
                                        //     {1..15}: true when you've lost >= N HP THIS turn (any source — the Ice
                                        //     Shatter self-fuel→payoff threshold). Snapshot-based (HpLossTracker: HP
                                        //     at turn start minus now); no damage hook. Reset each turn via the F5
                                        //     BeforeHandDraw patch. Slots into Conditions (Kinds/Validate/Eval/Phrase).
                                        // 33: Phase AC (gap #2) — SUMMON HEAL/SHIELD. New ops `heal_summon` {1..9}
                                        //     and `shield_summon` {1..12}: heal / grant Block to YOUR living summon
                                        //     (CreatureCmd.Heal / CreatureCmd.GainBlock on the pet). Class-only (summon
                                        //     class, like summon_attack/buff_summon); legal on cards AND in add_trigger
                                        //     self-payloads (a per-turn medic engine). No summon out → logged no-op.
                                        // 32: Phase AB (gap #20) — CORRUPTION. New flag-op `corruption` (no amount/
                                        //     target, card-only, power/skill): grants ForgedCorruptionPower — a binary
                                        //     per-combat power whose two base-game hooks (TryModifyEnergyCostInCombatLate
                                        //     → owner's Skills cost 0; ModifyCardPlayResultPileTypeAndPosition → owner's
                                        //     Skills go to Exhaust) make your Skills free-but-exhausting. Rejected in
                                        //     add_trigger payloads (not in TriggerOps — re-granting a binary power every
                                        //     turn is noise); ≤1 corruption card per class (character_validator warning).
                                        // 31: Phase AA (gap #17 R-2) — SCRY. New op `scry` {amount:N}: look at the
                                        //     top N cards of your DRAW pile and discard any subset (the third
                                        //     discard-subsystem primitive, after Phase R's discard + on_discard).
                                        //     Slices the top N (DrawPile.Cards[0] = top), shows them via
                                        //     CardSelectCmd.FromSimpleGrid (min 0 / max N — "discard none" allowed),
                                        //     discards the picked subset (CardCmd.Discard, draw→discard) and fires
                                        //     their on_discard payoffs (a scry-discard is an effect-discard). Card-only
                                        //     (rejected in payloads for v31). AutoSlay auto-picks (AutoSlayCardSelector).
                                        // 30: Phase Z (gap #19 choose-a-card) — CHOOSE-PURGE. New op `purge_card`:
                                        //     the player PICKS one card in hand and PURGES it (removes it from the
                                        //     run deck for the rest of the run — deck-thinning at a target of your
                                        //     choosing). Opens base-game CardSelectCmd.FromHand (like Brand), then
                                        //     CardPileCmd.RemoveFromDeck(chosen.DeckVersion) + RemoveFromCombat —
                                        //     reuses the Phase-W run-deck removal + null-DeckVersion guard. Card-only
                                        //     (rejected in trigger payloads — a repeating pick would spam the UI and
                                        //     shred the deck). AutoSlay auto-picks (AutoSlayCardSelector).
                                        // 29: Phase X (gap #18 player-pick) — CHOOSE-UPGRADE. New `cards` scope
                                        //     `choose` on the existing `upgrade_card` op: the player PICKS one
                                        //     upgradable hand card (the true Armaments fantasy) via base-game
                                        //     CardSelectCmd.FromHandForUpgrade → CardCmd.Upgrade. Card-only (like
                                        //     `all`; rejected in trigger payloads — a repeating pick spams the UI).
                                        //     AutoSlay auto-picks (AutoSlayCardSelector), so it's smoke-testable.
                                        // 28: Phase W (gap #19) — SELF-PURGE. New flag-op `purge`: a played card
                                        //     is removed from your run deck for the rest of the run (deck-thinning;
                                        //     a stronger exhaust). purge ⊥ exhaust (validator + C# reject both on one
                                        //     card). GetResultPileTypeForCardPlay override → PileType.None (out of
                                        //     combat) + CardPileCmd.RemoveFromDeck(DeckVersion) (run-permanent). A
                                        //     generated copy (add_card) has no DeckVersion → run deck untouched.
                                        // 27: Phase V (gap #18) — IN-RUN UPGRADE. New op `upgrade_card` {cards:
                                        //     random|all}: upgrade cards in HAND (choiceless) — `random` upgrades
                                        //     one random UPGRADABLE hand card, `all` every upgradable hand card (the
                                        //     Armaments/Armaments+ fantasy). COMBAT-SCOPED: hand cards are deck
                                        //     CLONES (Player.PopulateCombatState → state.CloneCard), so CardCmd.Upgrade
                                        //     mutates the clone only; the run deck is untouched (verified vs decompiled
                                        //     CardCmd.Upgrade — the run-history record fires only for Deck-pile cards).
                                        //     No amount / no card var. Legal on cards AND in add_trigger payloads —
                                        //     but the payload form is `random` ONLY (`all` in a repeating payload is
                                        //     degenerate; validator + ValidateTrigger reject it). The player-PICK
                                        //     variant stays blocked on the card-select UI (spike Y). Rides
                                        //     CardCmd.Upgrade + the run's CombatCardSelection RNG (seeded — determinism).
                                        // 26: Phase U (gap #23) — RAMPAGE. New optional `grow` (1..9) field on a
                                        //     `damage` op: damage dealt = amount + grow × (times THIS card was
                                        //     played earlier this combat); first play = printed. Per-card-instance
                                        //     (a generated copy grows independently); per-combat reset (History is
                                        //     combat-scoped). NOT a scale (grow ⊥ scale); an additive per-play step
                                        //     with its own magnitude. Rides WithCalculatedDamage (live in-hand preview)
                                        //     + EffectRunner.PlaysThisCombat (CombatManager History count).
                                        // 25: Phase T — the TRUE BLADE (base-game Forge). The signature blade is
                                        //     no longer innate + deck-seeded; instead the FIRST Forge income of
                                        //     combat SUMMONS it to hand (ForgedForgePower.Stoke, all three income
                                        //     paths). Blade shape: token:true + `damage scale:"forged"` + `retain`,
                                        //     cost 2 / base 10, rarity `token` (CardRarity.Token; CanBeGeneratedIn
                                        //     Combat:false + never merchant/reward-rolled keeps it out of drafts).
                                        //     + op `summon_blade` (Summon-Forth analogue: put your blade into hand
                                        //     from anywhere; class-only, no amount; card + trigger payload). + trigger
                                        //     kind `on_blade_played` (Parry analogue: fires when you play your blade;
                                        //     multi-fire, once_per_turn-eligible). Legacy v20-v24 blades (innate +
                                        //     deck-seeded, basic/token rarity) still load: the summon guard sees the
                                        //     blade already in a pile and skips, so old classes behave unchanged.
                                        // 24: Phase S (gap #1) — THE BALANCE GAUGE. op `balance_step` {pole:
                                        //     light/dark, amount:1..5}: move a SIGNED per-combat player counter
                                        //     (ForgedBalancePower; positive = Dark, negative = Light, absent at 0)
                                        //     toward a pole. Legal on cards AND in add_trigger self-payloads (income
                                        //     is the engine, like forge). + three `when` conditions: light_ge N /
                                        //     dark_ge N (that pole's magnitude >= N) / centered N (|gauge| <= N).
                                        //     The gauge BITES: at |gauge| >= 8, turn-start applies the pole's penalty
                                        //     (Dark: lose 3 HP; Light: gain 1 Weak). balance_step declares no card var
                                        //     (literal, like forge); amount is the step SIZE (not upgrade-scaled).
                                        // 23: Phase R (gap #17) — discard subsystem. op `discard` {amount:N}:
                                        //     discard N RANDOM cards from hand (choiceless; CardPileCmd.Discard).
                                        //     Legal on cards AND in add_trigger payloads (turn_start/turn_end forced
                                        //     churn). + trigger kind `on_discard` — CARD-LATENT (Reflex): fires THIS
                                        //     card's payload when it is discarded BY AN EFFECT (v51: any effect — the
                                        //     mod's discard/scry ops AND base-game relics/potions/cards, via the game's
                                        //     AfterCardDiscarded hook), NOT at turn-end cleanup (that flushes the hand
                                        //     through CardPileCmd.Add + Hook.AfterFlush, a different path).
                                        //     Playing an on_discard card grants NO power.
                                        //     Multi-fire (once_per_turn eligible, tracked by RoundNumber); a re-entrancy
                                        //     suppress-flag stops a discard-in-payload from cascading on_discard.
                                        // 22: Phase Q (gap #16) — op `add_card` {card_id, pile: hand/discard/draw,
                                        //     amount? 1..3}: generate combat-transient copies of a SAME-CLASS card
                                        //     into a pile (CardPileCmd.AddGeneratedCardToCombat). Class-only (resolved
                                        //     against the player's forged class; see ForgedCharacters). Legal on cards
                                        //     AND in add_trigger self-payloads (the on_exhaust "compost" loop, gap #8).
                                        //     Loop discipline: a DIFFERENT added card may not itself add_card (depth-1 —
                                        //     no chains; ResolveClassCardModel refuses it at runtime). A SELF-copy
                                        //     (Anger) is exempt — gated by the deck cycle. The generation validator's
                                        //     loop_warnings catch the 0-cost self-to-hand one-card engine.
                                        // 21: Phase P precision reads (gaps #21/#22/#24 + #9-relic). scale
                                        //     "damage_dealt_unblocked" (heal-ONLY lifesteal — heal the UNBLOCKED
                                        //     damage this card's earlier damage effects dealt this play; requires a
                                        //     preceding damage op on the same list) + scale "target_debuff_count"
                                        //     (damage-ONLY — deal damage equal to the debuff powers on the struck
                                        //     target, resolved per hit via the calc-var) + when {kind:
                                        //     "draw_pile_empty"} (Grand-Finale boolean gate) + relic hook
                                        //     "on_hp_lost" (mirrors the v17 card-side twin: own-turn unblocked HP loss).
                                        // 20: Sovereign Blade (Tier 1) — a card may carry `token:true`, marking it a
                                        //     non-drafted TOKEN (the forge class's signature blade): seeded into the
                                        //     starting deck by slot, but registered autoAdd:false + showInCardLibrary:
                                        //     false so it is never offered as a reward/draft nor listed in the
                                        //     compendium. No new op — the blade is `damage scale:"forged"` + `retain`
                                        //     + `innate`, all shipped in v19; token is card-level metadata (CardSpec
                                        //     .IsToken, honored by DataCard). Bumped so a v20 blade code isn't silently
                                        //     mis-imported by a v19 mod (which would leak the blade into rewards).
                                        // 19: Phase M "Forge" (gap #36) — op `forge` (amount N: stoke a per-combat
                                        //     player-level Forge counter, ForgedForgePower; allowed on cards, in
                                        //     add_trigger self payloads, and relic hooks) + scale:"forged" on
                                        //     damage/block (ADDITIVE: printed amount + Forge — the one additive
                                        //     exception in the scale family) + `when` condition forged_ge N.
                                        // 18: Phase H4 reactive card triggers (gaps #13 + #14). add_trigger gains 6
                                        //     reactive kinds (on_exhaust / on_card_played / on_card_drawn /
                                        //     on_damage_dealt / on_block_gained / attacked) mirroring the relic hooks,
                                        //     a `once_per_turn` gate for the multi-fire kinds, and enemy-targeted
                                        //     payloads (`target: enemy|all_enemies` on damage / debuff apply_status).
                                        // 17: gap #9 "on_hp_lost" — add_trigger trigger:"on_hp_lost" fires its
                                        //     self/orb payload whenever you take UNBLOCKED HP loss on your own turn
                                        //     (self/card-caused; the Rupture hook AfterDamageReceived + a re-entrancy
                                        //     guard). The bleed/sacrifice payoff.
                                        // 16: gap #6 "ripen" — add_trigger trigger:"ripen" with amount=N waits N
                                        //     turn-starts then fires its self/orb payload ONCE (a delayed-maturation
                                        //     / countdown trigger, distinct from per-turn turn_start/turn_end).
                                        // 15: true-Osty summons — `summon` op = grow Max HP / (re)summon ONE passive
                                        // minion (no autonomous moves); + `summon_attack` (strike through the summon,
                                        // scales with its Strength) + `buff_summon` (buff the living summon). The
                                        // K-3 custom mechanics (move cycles / ethereal / on_summon / on_death /
                                        // multi-pet) are disabled in generation but kept dormant in the engine.
                                        // 14: F5 retain/hand-state — scale cards_in_hand/cards_retained/
                                        // unspent_energy_last_turn, when hand_size_ge/retained_last_turn,
                                        // add_trigger payload may scale:cards_retained

    private const string ForgedDir = "user://forged/cards";

    // The intersection the C# EffectRunner / DataCard actually execute (kept in lockstep with both).
    private static readonly HashSet<string> SupportedOps =
        ["damage", "block", "draw", "apply_status", "gain_energy", "lose_hp", "heal",
         "gain_max_hp", // Phase AN (v44): Feed — raise your Max HP by amount (and heal that much). Card-only, 1..5.
         "cost_shift", // Phase AO (v45): a card-type-scoped energy discount (this turn / this combat / next N plays). Card-only.
         "exhaust", "innate", "retain", "ethereal",
         "gain_orb_slot", "channel_orb", "evoke", // Phase G orbs (opened to the LLM contract in G3)
         "forge", // Phase M (gap #36): stoke the per-combat Forge counter (payoff = scale:"forged")
         "add_trigger", // Phase H3 triggers
         "apply_status_custom", // Phase J: apply a forged class-specific status by name
         "summon", // Phase K: summon the class's minion / grow its Max HP (true-Osty)
         "summon_attack", // Phase K (true-Osty): deal damage THROUGH the class's living summon
         "buff_summon", // Phase K (true-Osty): buff the class's living summon (e.g. Strength)
         "heal_summon", // Phase AC (gap #2): heal your living summon (class-only; no summon out → no-op)
         "shield_summon", // Phase AC (gap #2): grant Block to your living summon (class-only; no summon out → no-op)
         "sacrifice_summon", // Phase AV (v52): flag-op — consume your living summon (its on_death rattle fires). Class-only, card-only.
         "add_card", // Phase Q (gap #16): generate copies of a same-class card into a combat pile (class-only)
         "discard", // Phase R (gap #17): discard N random cards from hand. Phase AP (v46): + `cards:"choose"` (the player picks; card-only)
         "retrieve_card", // Phase AP (v46): return card(s) from your discard/exhaust pile to your hand (random / choose). Card-only.
         "add_status_card", // Phase AP (v46): generate base-game Status cards (dazed/wound/burn) into a pile — a self-drawback. Card-only.
         "balance_step", // Phase S (gap #1): move the signed Balance gauge toward a pole (light/dark)
         "summon_blade", // Phase T: put the class's signature blade into your hand from anywhere (class-only)
         "upgrade_card", // Phase V (gap #18): upgrade random/all cards in hand this combat (choiceless)
         "purge", // Phase W (gap #19): flag-op — played card leaves your RUN deck for the rest of the run (deck-thinning)
         "purge_card", // Phase Z (gap #19 choose): the player picks a card in hand and purges it (run-permanent). Card-only.
         "scry", // Phase AA (gap #17 R-2): look at the top N of your draw pile, discard any (draw-filter). Card-only.
         "corruption", // Phase AB (gap #20): flag-op — grant Corruption (your Skills cost 0 + Exhaust). Card-only, power/skill.
         "blade_empower", // Phase AF (gap #41): one-turn ×N multiplier on the forged blade token. Forge-class only, card-only.
         "transform_card", // Phase AH (gaps #35/#38): played card PERMANENTLY becomes the named same-class card for the rest of the run (self-rewrite / mode-swap). Card-only.
         "spend_forge", // Phase AX (v53, gap #44): SPEND Forge as a card's price (the cash-out half of the ramp). Forge-class, card-only.
         "spread_debuffs", // Phase AX (v53, gaps #45-#47): copy the struck target's debuffs to every OTHER living enemy. Card-only.
         "graft_card", // Phase AI (gap #7): CHOOSE form of transform_card — pick a card in hand, IT permanently becomes the named same-class card for the rest of the run. Card-only.
         "apply_custom", // EXPLORE SPIKE: apply a hardcoded modifier-family custom status (not in LLM contract)
         "summon_spike"]; // PHASE K SPIKE: summon a hardcoded player pet (not in LLM contract)
    // Phase H3/H4: the trigger kinds. turn_start/turn_end fire every turn; ripen is a one-shot countdown; the rest
    // are REACTIVE (H4) — they mirror the ForgedRelic hooks and can fire many times a turn (see ForgedTriggerPower).
    private static readonly HashSet<string> SupportedTriggers =
        ["turn_end", "turn_start", "ripen", "on_hp_lost",
         "on_exhaust", "on_card_played", "on_card_drawn", "on_damage_dealt", "on_block_gained", "attacked",
         "on_discard", // Phase R (gap #17): CARD-LATENT Reflex — fires THIS card's payload when ANY effect discards it (v51)
         "on_blade_played"]; // Phase T: Parry analogue — fires whenever you play your signature blade (a token card)
    // H4: the reactive kinds that can fire MULTIPLE times per turn → eligible for the `once_per_turn` gate.
    // (turn_start/turn_end/ripen already fire at most once per turn, so once_per_turn is rejected on them.)
    private static readonly HashSet<string> MultiFireTriggers =
        ["on_hp_lost", "on_exhaust", "on_card_played", "on_card_drawn", "on_damage_dealt", "on_block_gained", "attacked",
         "on_discard", // Phase R: a card can be discarded → redrawn → discarded again within a turn
         "on_blade_played"]; // Phase T: you can play the blade more than once a turn (retrieve + replay)
    // Phase AK (v41): the POWER-HOSTED reactive kinds eligible for `once_per_combat` — the fired flag lives on the
    // granted ForgedTriggerPower, a fresh instance per combat. on_discard is card-latent (no power; DataCard tracks
    // it by round), so it is excluded.
    private static readonly HashSet<string> OncePerCombatTriggers =
        ["on_hp_lost", "on_exhaust", "on_card_played", "on_card_drawn", "on_damage_dealt", "on_block_gained", "attacked",
         "on_blade_played"];
    // Phase H3: the self/orb-only sub-vocabulary a trigger's payload may use when it has NO target. (H4 lifts this
    // for effects that carry a `target`: damage + enemy-debuff apply_status may then hit enemies — see TriggerRunner.)
    private static readonly HashSet<string> TriggerOps =
        ["block", "draw", "gain_energy", "heal", "lose_hp", "apply_status",
         "gain_orb_slot", "channel_orb", "evoke",
         "forge", // Phase M (gap #36): trigger-side Forge income (fixed amounts only — no scale)
         "add_card", // Phase Q (gap #16): trigger-side token generation (the on_exhaust "compost" loop, gap #8)
         "discard", // Phase R (gap #17): trigger-side forced churn ("At the start of your turn, discard 1")
         "balance_step", // Phase S (gap #1): trigger-side Balance income ("At the start of your turn, shift 2 toward the Dark")
         "summon_blade", // Phase T: trigger-side blade retrieval ("Whenever you play a card, put your blade into your hand")
         "upgrade_card", // Phase V (gap #18): trigger-side upgrade ("At the start of your turn, upgrade a random card in your hand") — `random` only
         "heal_summon", // Phase AC (gap #2): trigger-side summon heal (the medic engine — "at turn start, heal your summon 3")
         "shield_summon", // Phase AC (gap #2): trigger-side summon shield ("at turn start, your summon gains 4 Block")
         // Phase AL (v42): the class engines re-expressed as payloads. Class-only (ValidateTrigger); resolved off the
         // player's class at fire time (TriggerRunner) exactly like heal_summon / trigger channel_orb.
         "apply_status_custom", // status class: "At the start of your turn, gain 1 Razor Focus" (a debuff needs a target)
         "summon_attack", // summon class: "At the end of your turn, deal 4 damage 2 times with your summon" (the dormant move-cycle as a card engine)
         "buff_summon"]; // summon class: "At the start of your turn, your summon gains 1 Strength"
    // H4 (gap #14): payload ops that may aim at enemies (with a `target`), and the debuffs a targeted apply_status
    // may apply. Everything else stays self/orb-only. Phase AL (v42): + summon_attack (the summon strikes the
    // resolved enemies; no target = the first living enemy) and apply_status_custom (a custom DEBUFF lands on the
    // resolved enemies; an untargeted apply_status_custom is the self-buff form).
    private static readonly HashSet<string> TriggerTargetedOps = ["damage", "apply_status", "summon_attack", "apply_status_custom"];
    private static readonly HashSet<string> EnemyDebuffStatuses = ["vulnerable", "weak", "frail", "poison"];
    private static readonly HashSet<string> SupportedStatuses =
        ["vulnerable", "weak", "frail", "poison",
         "strength", "dexterity", "thorns", "regen", "metallicize", "artifact", "buffer",
         "intangible", "ritual", "blur", "temp_strength", "temp_dexterity", "barricade", "focus",
         "temp_thorns", "temp_focus"]; // Phase AN (v44): one-turn Thorns / Focus (removed at the end of your turn)
    // Phase AN (v44): the gain_max_hp cap (Feed is +3/+4; a run-permanent stat, so the band is tight). Lockstep with
    // validator._GAIN_MAX_HP_MAX and the schema clause.
    private const int GainMaxHpMaxAmount = 5;
    // Phase AO (v45): the cost_shift shape — which cards it discounts, how long it lives, the discount band, the use
    // budget band. Lockstep with validator._COST_SHIFT_* and the schema clauses.
    private static readonly HashSet<string> CostShiftKinds = ["attack", "skill", "power", "all"];
    private static readonly HashSet<string> CostShiftScopes = ["this_turn", "combat"];
    private const int CostShiftMaxAmount = 2;
    private const int CostShiftMaxCount = 3;

    /// <summary>Phase AO (v45): the cost_shift shape rules, shared by the card validator and the relic parser
    /// (<paramref name="relic"/> adds the hook-side rule: this_turn only — a hook fires every turn, so a combat-scoped
    /// entry would accumulate; the whole-combat relic discount is the <c>cost_reduction</c> modifier).</summary>
    internal static string? ValidateCostShift(EffectSpec e, bool relic = false)
    {
        if (e.CardKind == null || !CostShiftKinds.Contains(e.CardKind))
            return $"cost_shift needs a 'card_type' (one of {string.Join("/", CostShiftKinds)}); got '{e.CardKind}'.";
        if (e.Scope == null || !CostShiftScopes.Contains(e.Scope))
            return $"cost_shift needs a 'scope' (one of {string.Join("/", CostShiftScopes)}); got '{e.Scope}'.";
        if (e.Amount < 1 || e.Amount > CostShiftMaxAmount)
            return $"cost_shift 'amount' (the discount) must be 1..{CostShiftMaxAmount}; got {e.Amount}.";
        if (e.Count < 0 || e.Count > CostShiftMaxCount)
            return $"cost_shift 'count' (the plays it applies to) must be 1..{CostShiftMaxCount}; got {e.Count}.";
        if (e.Scope == "combat" && e.Amount != 1)
            return "cost_shift with scope 'combat' must use amount 1 (a whole-combat -2 is degenerate).";
        if (relic && e.Scope != "this_turn")
            return "a relic cost_shift must use scope 'this_turn' (a hook fires every turn; the whole-combat relic discount is the cost_reduction modifier).";
        return null;
    }
    private static readonly HashSet<string> SupportedOrbs = ["lightning", "frost", "dark", "random"]; // Phase G/H
    // Phase Q (gap #16): the combat piles add_card may drop generated copies into. Mirrors PileType (hand/discard/
    // draw) — the base-game "generate a card into combat" destinations. Kept in lockstep with validator._ADD_CARD_PILES.
    private static readonly HashSet<string> AddCardPiles = ["hand", "discard", "draw"];
    private const int AddCardMaxAmount = 3; // amount cap (copies per play) — small numbers keep token engines bounded
    // Phase AP (v46): the piles retrieve_card may pull a card back to hand FROM (the Headbutt / Exhume shape — never the
    // draw pile: that is what draw/scry are for), the pick modes shared by discard / retrieve_card (random / choose),
    // the base-game Status cards add_status_card may generate, and the per-play caps. Lockstep with validator.py
    // (_RETRIEVE_PILES / _PICK_MODES / _STATUS_CARDS / _RETRIEVE_MAX / _STATUS_CARD_MAX) + card.schema.json.
    private static readonly HashSet<string> RetrievePiles = ["discard", "exhaust"];
    private static readonly HashSet<string> PickModes = ["random", "choose"];
    private static readonly HashSet<string> StatusCards = ["dazed", "wound", "burn"];
    private const int RetrieveMaxAmount = 2;   // "Return 2 cards" is the ceiling — a 3+ recursion is a degenerate loop
    private const int StatusCardMaxAmount = 3; // Power Through adds 2 Wounds; 3 is the ceiling
    // Phase S (gap #1): the poles balance_step may move the gauge toward, and the per-step cap (small steps keep the
    // gauge a slow tug-of-war so the |8| extreme is a deliberate commitment, not one card). Lockstep with validator.
    private static readonly HashSet<string> BalancePoles = ["light", "dark"];
    private const int BalanceStepMaxAmount = 5;
    // Phase AC (gap #2): the per-op caps for summon heal/shield (small numbers keep a per-turn medic engine bounded).
    // Lockstep with validator._HEAL_SUMMON_MAX / _SHIELD_SUMMON_MAX.
    private const int HealSummonMaxAmount = 9;
    private const int ShieldSummonMaxAmount = 12;
    // Phase AX (v53, gap #44): the spend_forge cap. A ramp cash-out should be a real commitment but never a
    // whole-combat counter wipe in one line; 10 is the ceiling (a card asking for more Forge than any realistic
    // ramp reaches is a dead card). Lockstep with validator._SPEND_FORGE_MAX + the schema clause.
    private const int SpendForgeMaxAmount = 10;
    // Phase AX (v53): the card energy-cost ceiling, raised 3 -> 4. Cost 4 is the HEAVYWEIGHT slot and is RARE-ONLY
    // (a 4-cost common is a dead draw); the upgrade `cost` band widens with it. Lockstep with validator._MAX_COST +
    // card.schema.json's cost clauses.
    internal const int MaxCardCost = 4;
    // Phase AX (v53): the keyword flag-ops an UPGRADE may ADD (exactly one, appended to the end of the upgrade
    // effect list). Removal is exhaust-only (an upgrade that drops a drawback), so it has no set of its own.
    private static readonly HashSet<string> UpgradeAddableKeywords = ["exhaust", "retain", "innate", "ethereal"];
    // Phase AX (v53): the keyword flag-ops whose presence differs between the base and upgrade lists — the set
    // DataCard diffs to pick each keyword's BaseLib UpgradeType (None / Add / Remove). `purge` is deliberately
    // absent: it is not a CardKeyword (it rides Spec.HasPurge + GetResultPileTypeForCardPlay).
    internal static readonly HashSet<string> KeywordOps = ["exhaust", "retain", "innate", "ethereal"];
    // Phase AX (v53): how many times one card may declare the SAME apply_status. The second one must be
    // `when`-gated and takes a suffixed var ("Weak2"); a third is always a reject.
    private const int MaxSameStatusPerCard = 2;
    // Phase V (gap #18): the hand-scopes upgrade_card may use. `random` (one random upgradable hand card) is legal
    // on cards AND in trigger payloads; `all` (every upgradable hand card) and `choose` (Phase X — the player picks
    // one upgradable hand card) are card-only (rejected in payloads — ValidateTrigger; a repeating pick spams the
    // UI). Lockstep with validator._UPGRADE_SCOPES.
    private static readonly HashSet<string> UpgradeScopes = ["random", "all", "choose"];
    // Phase F5: the live state scalars an effect's amount may scale to (damage/block/draw only). "x" stays the
    // X-cost scalar (coupled to a "X" card cost); the rest are hand/energy state reads with no cost coupling.
    // Phase M: "forged" is the ADDITIVE exception (printed amount + Forge stacks) and is damage/block-only.
    // Phase P (gaps #21/#22): "damage_dealt_unblocked" is heal-only (lifesteal — an execution-ordered read of the
    // unblocked damage this card already dealt) and "target_debuff_count" is damage-only (per-target debuff count).
    private static readonly HashSet<string> SupportedScales =
        ["x", "cards_in_hand", "cards_retained", "unspent_energy_last_turn", "forged",
         "damage_dealt_unblocked", "target_debuff_count",
         "tag_cards_owned", // Phase AE (gap #25): ADDITIVE (printed amount + count of cards with the sibling `tag`); damage/block-only
         // Phase AM (v43): five more live player reads (replace-semantics). `energy` is damage/block/draw but cost-0
         // ONLY (checked at the card level where the cost is known); the other four are damage/block-only (a draw
         // equal to your Block / draw pile is absurd; see DamageBlockOnlyScales).
         "block", "hp_lost_this_turn", "draw_pile_count", "energy", "plays_this_combat"];
    // Phase AM (v43): the AM scales that may NOT drive a draw.
    private static readonly HashSet<string> DamageBlockOnlyScales =
        ["block", "hp_lost_this_turn", "draw_pile_count", "plays_this_combat"];
    // The scalars a trigger payload may use — PLAYER-level reads only (a trigger fires with no card, so `x` and the
    // target/lifesteal/tag reads make no sense). cards_retained (F5) is the per-turn snapshot; Phase AL (v42) adds
    // cards_in_hand (the hand when it fires), unspent_energy_last_turn (the turn-end snapshot) and the ADDITIVE
    // forged (printed amount + Forge — damage/block only, amount >= 1, like the card-level rule).
    private static readonly HashSet<string> TriggerScales =
        ["cards_retained", "cards_in_hand", "unspent_energy_last_turn", "forged"];
    // The payload ops whose amount a scale may replace/add to (each has a scaled TriggerFragment wording). damage
    // needs a target (H4) — Phase AL lifts the "a targeted effect can't be scaled" rule for damage ONLY.
    private static readonly HashSet<string> TriggerScalableOps =
        ["damage", "block", "draw", "gain_energy", "heal", "lose_hp", "gain_orb_slot", "apply_status"];
    // Ops that carry a numeric amount (>= 1 required). exhaust/innate/retain/ethereal are flag ops (no amount).
    private static readonly HashSet<string> AmountOps =
        ["damage", "block", "draw", "apply_status", "gain_energy", "lose_hp", "heal", "gain_orb_slot",
         "gain_max_hp", // Phase AN (v44): Max HP to gain (needs amount>=1; capped 1..5 in Validate)
         "cost_shift", // Phase AO (v45): the discount (needs amount>=1; capped 1..2 in ValidateCostShift)
         "discard", // Phase R (gap #17): how many random cards to discard (needs amount>=1)
         "scry", // Phase AA (gap #17 R-2): how many top-of-draw cards to look at (needs amount>=1)
         "forge", // Phase M (gap #36): how much Forge to stoke (needs amount>=1)
         "balance_step", // Phase S (gap #1): the step size (how far to move the gauge; needs amount>=1)
         "apply_status_custom", // Phase J: stacks of the forged status to apply
         "summon_attack", // Phase K (true-Osty): damage dealt through the summon (needs amount>=1)
         "buff_summon", // Phase K (true-Osty): stacks of the buff to apply to the summon (needs amount>=1)
         "heal_summon", // Phase AC (gap #2): HP to heal the summon (needs amount>=1; capped 1..9 in Validate)
         "shield_summon", // Phase AC (gap #2): Block to grant the summon (needs amount>=1; capped 1..12 in Validate)
         "blade_empower", // Phase AF (gap #41): the blade multiplier (needs amount>=2; capped 2..3 in Validate)
         "spend_forge", // Phase AX (v53, gap #44): the Forge consumed (needs amount>=1; capped 1..10 in Validate)
         // NOTE: `summon` is intentionally NOT here. Its `amount` is the HP to grant and is OPTIONAL — a missing/0
         // amount means "use the summon's spec MaxHp" (EffectRunner falls back), matching the generator validator
         // (which never enforces summon amount>=1) and the relic path (ForgedCharacters special-cases summon before
         // its amount<1 check). Requiring amount>=1 here rejected valid blueprints.
         "apply_custom", // EXPLORE SPIKE: stacks of the custom status to apply
         "summon_spike"]; // PHASE K SPIKE: how many pets to summon

    private static readonly Dictionary<string, CardType> TypeMap = new()
    {
        ["attack"] = CardType.Attack, ["skill"] = CardType.Skill, ["power"] = CardType.Power,
    };
    private static readonly Dictionary<string, CardRarity> RarityMap = new()
    {
        ["basic"] = CardRarity.Basic, ["common"] = CardRarity.Common,
        ["uncommon"] = CardRarity.Uncommon, ["rare"] = CardRarity.Rare,
        // Phase T: the signature blade carries real Token rarity (base-game tokens do). Legal ONLY on a
        // token:true card (gated in TryBuildSpec); CardFactory never rolls Token for merchant/reward drafts.
        ["token"] = CardRarity.Token,
    };
    private static readonly Dictionary<string, TargetType> TargetMap = new()
    {
        ["enemy"] = TargetType.AnyEnemy, ["self"] = TargetType.Self,
        ["all_enemies"] = TargetType.AllEnemies, ["random_enemy"] = TargetType.RandomEnemy,
        ["none"] = TargetType.Self,
    };

    private static Dictionary<int, CardSpec>? _slots;

    /// <summary>Returns the filled spec for the given 1-based slot, or an empty (hidden) spec if none.</summary>
    public static CardSpec SpecForSlot(int slot)
    {
        _slots ??= LoadAll();
        return _slots.TryGetValue(slot, out var spec) ? spec : CardSpec.EmptySlot($"forged_card_slot{slot:00}");
    }

    // --- slot-file store (used by the in-game import screen) ----------------------------------------

    /// <summary>The user-data path of a slot's JSON file (whether or not it exists).</summary>
    public static string SlotPath(int slot) => $"{ForgedDir}/{slot:00}.json";

    public static bool SlotFileExists(int slot) => Godot.FileAccess.FileExists(SlotPath(slot));

    /// <summary>Lowest 1-based slot with no JSON file yet, or null if all <see cref="SlotCount"/> are taken.</summary>
    public static int? FirstFreeSlot()
    {
        for (int i = 1; i <= SlotCount; i++)
            if (!SlotFileExists(i)) return i;
        return null;
    }

    /// <summary>
    /// The slot already holding a card with this <paramref name="cardId"/>, or null. Used to dedupe imports:
    /// re-importing the same card updates its existing slot in place instead of spawning a duplicate.
    /// </summary>
    public static int? FindSlotByCardId(string cardId)
    {
        for (int i = 1; i <= SlotCount; i++)
        {
            if (!SlotFileExists(i)) continue;
            using var file = Godot.FileAccess.Open(SlotPath(i), Godot.FileAccess.ModeFlags.Read);
            if (file == null) continue;
            var parser = new Godot.Json();
            if (parser.Parse(file.GetAsText()) != Godot.Error.Ok) continue;
            if (parser.Data.VariantType != Godot.Variant.Type.Dictionary) continue;
            var d = parser.Data.AsGodotDictionary();
            if (d.ContainsKey("id") && d["id"].AsString() == cardId) return i;
        }
        return null;
    }

    /// <summary>Deletes a slot's JSON file. Returns true if a file was removed.</summary>
    public static bool DeleteSlotFile(int slot)
    {
        if (!SlotFileExists(slot)) return false;
        return Godot.DirAccess.RemoveAbsolute(SlotPath(slot)) == Godot.Error.Ok;
    }

    /// <summary>Deletes every forged slot file. Returns how many were removed.</summary>
    public static int ClearAllSlots()
    {
        int removed = 0;
        for (int i = 1; i <= SlotCount; i++)
            if (DeleteSlotFile(i)) removed++;
        return removed;
    }

    /// <summary>Writes a card's JSON into a slot file (creating the dir). Throws on I/O failure.</summary>
    public static void WriteSlotFile(int slot, string json)
    {
        if (!Godot.DirAccess.DirExistsAbsolute(ForgedDir))
            Godot.DirAccess.MakeDirRecursiveAbsolute(ForgedDir);

        using var file = Godot.FileAccess.Open(SlotPath(slot), Godot.FileAccess.ModeFlags.Write);
        if (file == null)
            throw new IOException($"{Godot.FileAccess.GetOpenError()} opening {SlotPath(slot)}");
        file.StoreString(json);
    }

    // --- parsing + validation (shared by the startup loader AND the importer) -----------------------

    /// <summary>
    /// Parses a single card JSON and re-validates it against the live EffectRunner vocabulary. On success
    /// returns a playable <see cref="CardSpec"/>; on failure returns a human-readable reason (shown to the
    /// user on import). <paramref name="slot"/> only supplies a fallback id when the JSON omits one.
    /// </summary>
    public static bool TryParseCardJson(string json, int slot, out CardSpec? spec, out string error,
        bool allowBasic = false, bool allowCustomOrbs = false, IReadOnlySet<string>? orbNames = null)
    {
        spec = null;
        var parser = new Godot.Json();
        var code = parser.Parse(json);
        if (code != Godot.Error.Ok)
        {
            error = $"invalid JSON (line {parser.GetErrorLine()}): {parser.GetErrorMessage()}";
            return false;
        }
        if (parser.Data.VariantType != Godot.Variant.Type.Dictionary)
        {
            error = "root is not a JSON object.";
            return false;
        }
        return TryBuildSpec(parser.Data.AsGodotDictionary(), slot, out spec, out error, allowBasic, allowCustomOrbs, orbNames);
    }

    private static bool TryBuildSpec(Godot.Collections.Dictionary card, int slot, out CardSpec? spec, out string error,
        bool allowBasic = false, bool allowCustomOrbs = false, IReadOnlySet<string>? orbNames = null)
    {
        spec = null;
        string id = Str(card, "id", $"forged_card_slot{slot:00}");

        if (!TypeMap.TryGetValue(Str(card, "type"), out var type))
        { error = $"unknown type '{Str(card, "type")}' (expected attack/skill/power)."; return false; }
        if (!RarityMap.TryGetValue(Str(card, "rarity"), out var rarity))
        { error = $"unknown rarity '{Str(card, "rarity")}' (expected common/uncommon/rare)."; return false; }
        if (!TargetMap.TryGetValue(Str(card, "target"), out var target))
        { error = $"unknown target '{Str(card, "target")}'."; return false; }

        // Shared-pool forged content forbids Basic (reward-only). Class card slots (allowBasic) permit it,
        // since a class's starting deck legitimately needs literal Strike/Defend basics.
        if (!allowBasic && rarity == CardRarity.Basic)
        { error = "rarity 'basic' is not allowed for forged cards (would never be offered)."; return false; }

        // Phase T: `token` metadata and Token rarity are coupled. A token:true card IS the signature blade — it
        // carries Token rarity (base-game tokens do; the summon path + CardFactory keep it out of drafts). Token
        // rarity is meaningless on any other card. Legacy v20-v24 blades were Basic, so accept that too.
        bool isToken = card.ContainsKey("token") && card["token"].AsBool();
        if (rarity == CardRarity.Token && !isToken)
        { error = "rarity 'token' is only for the signature blade (a card with token:true)."; return false; }
        if (isToken && rarity != CardRarity.Token && rarity != CardRarity.Basic)
        { error = "a token:true blade must be rarity 'token' (or legacy 'basic')."; return false; }

        var effects = ParseEffects(card.ContainsKey("effects") ? card["effects"].AsGodotArray() : []);
        if (effects.Length == 0)
        { error = "card has no effects."; return false; }

        EffectSpec[]? upgrade = null;
        int? upgradedCost = null; // Phase AG (gap #39): the card's cost AFTER upgrade (absolute), if the upgrade lowers cost.
        if (card.ContainsKey("upgrade") && card["upgrade"].VariantType == Godot.Variant.Type.Dictionary)
        {
            var up = card["upgrade"].AsGodotDictionary();
            if (up.ContainsKey("effects"))
                upgrade = ParseEffects(up["effects"].AsGodotArray());
            if (up.ContainsKey("cost")) upgradedCost = Int(up, "cost");
        }

        var invalid = Validate(effects, upgrade, allowCustomOrbs, target, orbNames);
        if (invalid != null) { error = invalid; return false; }

        // Cost is an int (0–4, Phase AX) OR the string "X" (an X-cost card: X = all energy, resolved at play time).
        bool costsX = card.ContainsKey("cost")
                      && card["cost"].VariantType == Godot.Variant.Type.String
                      && card["cost"].AsString().Trim().Equals("X", StringComparison.OrdinalIgnoreCase);
        int cost = costsX ? 0 : Int(card, "cost");
        // Phase AX (v53): the band, raised 0..3 -> 0..4. Cost 4 is the HEAVYWEIGHT slot and is RARE-ONLY — a
        // 4-cost common/uncommon is a dead draw at every point in a run. (The "headline effect" half of the rule
        // is a generation-side warning; the rarity gate is hard on both sides.)
        if (!costsX)
        {
            if (cost < 0 || cost > MaxCardCost)
            { error = $"card 'cost' must be 0..{MaxCardCost} (or \"X\"); got {cost}."; return false; }
            if (cost == MaxCardCost && rarity != CardRarity.Rare)
            { error = $"cost {MaxCardCost} is RARE-only (got '{rarity}') — the heavyweight slot needs a headline effect."; return false; }
        }

        // X-cost coupling is specific to scale:"x" (the OTHER F5 scalars are not tied to the card cost).
        bool anyX = effects.Any(e => e.ScaleX);
        if (costsX && !anyX)
        { error = "an X-cost card needs a 'scale:x' effect (otherwise X does nothing)."; return false; }
        if (!costsX && anyX)
        { error = "'scale:x' requires the card cost to be \"X\"."; return false; }
        // Phase AM (v43): scale:"energy" reads your CURRENT energy. The game spends the card's cost BEFORE OnPlay
        // (PlayCardAction.SpendResources), so on a paid card the in-hand preview (pre-pay) and the resolved amount
        // (post-pay) would disagree by the cost — only a cost-0 card keeps them equal. X-cost is excluded too
        // (X spends everything → always 0).
        if (effects.Concat(upgrade ?? []).Any(e => e.Scale == "energy") && (costsX || cost != 0))
        { error = "'scale:energy' requires a cost-0 card (the cost is paid before the card resolves, so a paid card would preview one number and deal another)."; return false; }

        // Phase AG (gap #39): an upgrade may LOWER the card's energy cost (absolute, 0..4 since Phase AX). House rules: never on an
        // X-cost card (X has no fixed cost to change); the upgraded cost must be <= the base cost (upgrades cheapen,
        // never tax). Applied at runtime by DataCard (MockSetEnergyCost on the Upgraded event).
        if (upgradedCost is { } ucost)
        {
            if (costsX)
            { error = "upgrade 'cost' is not allowed on an X-cost card."; return false; }
            if (ucost < 0 || ucost > MaxCardCost) // Phase AX (v53): the band widens with the base cost ceiling
            { error = $"upgrade 'cost' must be 0..{MaxCardCost}; got {ucost}."; return false; }
            if (ucost > cost)
            { error = $"upgrade 'cost' ({ucost}) may not exceed the base cost ({cost}) — upgrades cheapen, never tax."; return false; }
        }

        string title = Str(card, "name", id);
        // Allow explicit text (e.g. website-authored), else synthesize like cardgen.py.
        string description = card.ContainsKey("description") ? Str(card, "description")
                           : card.ContainsKey("text") ? Str(card, "text")
                           : Describe(effects, target);

        // Phase AE (gap #25): optional declarative `tags` (lowercase synergy slugs) read by the tag_cards_owned
        // deck scan. Purely metadata (no runtime behavior on its own); shape (1..2, pattern) is contract-enforced.
        string[]? tags = null;
        if (card.ContainsKey("tags") && card["tags"].VariantType == Godot.Variant.Type.Array)
        {
            var tl = new List<string>();
            foreach (var t in card["tags"].AsGodotArray())
                if (t.VariantType == Godot.Variant.Type.String)
                {
                    string s = t.AsString().Trim().ToLowerInvariant();
                    if (s.Length > 0) tl.Add(s);
                }
            if (tl.Count > 0) tags = tl.ToArray();
        }

        // Sovereign Blade: a non-drafted TOKEN. Phase T summons it on the first Forge (no longer deck-seeded);
        // DataCard reads IsToken to hide it from the compendium + block combat-generation. `isToken` is parsed
        // and rarity-gated above (near the Basic gate).
        spec = new CardSpec(id, cost, type, rarity, target, effects, upgrade, title, description,
                            CostsX: costsX, IsToken: isToken, Tags: tags, UpgradedCost: upgradedCost);
        error = "";
        return true;
    }

    private static Dictionary<int, CardSpec> LoadAll()
    {
        var result = new Dictionary<int, CardSpec>();
        try
        {
            if (!Godot.DirAccess.DirExistsAbsolute(ForgedDir))
            {
                Godot.DirAccess.MakeDirRecursiveAbsolute(ForgedDir);
                MainFile.Logger.Info($"[Forged] created {ForgedDir}; no forged cards yet.");
                return result;
            }

            using var dir = Godot.DirAccess.Open(ForgedDir);
            if (dir == null)
            {
                MainFile.Logger.Warn($"[Forged] could not open {ForgedDir}.");
                return result;
            }

            foreach (var fileName in dir.GetFiles())
            {
                if (!fileName.EndsWith(".json")) continue;

                var stem = fileName[..^".json".Length];
                if (!int.TryParse(stem, out var slot) || slot < 1 || slot > SlotCount)
                {
                    MainFile.Logger.Warn($"[Forged] skipping '{fileName}': name must be NN.json with 1..{SlotCount}.");
                    continue;
                }

                using var file = Godot.FileAccess.Open($"{ForgedDir}/{fileName}", Godot.FileAccess.ModeFlags.Read);
                if (file == null)
                {
                    MainFile.Logger.Warn($"[Forged] cannot open '{fileName}': {Godot.FileAccess.GetOpenError()}.");
                    continue;
                }

                if (TryParseCardJson(file.GetAsText(), slot, out var spec, out var err) && spec != null)
                {
                    if (result.ContainsKey(slot))
                        MainFile.Logger.Warn($"[Forged] slot {slot} already filled; '{fileName}' overrides it.");
                    result[slot] = spec;
                    MainFile.Logger.Info($"[Forged] slot {slot:00} <- '{spec.Title}' ({spec.Rarity} {spec.Type}).");
                }
                else
                {
                    MainFile.Logger.Warn($"[Forged] slot {slot:00} ('{fileName}') rejected: {err}");
                }
            }
        }
        catch (Exception e)
        {
            MainFile.Logger.Error($"[Forged] load failed: {e}");
        }

        MainFile.Logger.Info($"[Forged] loaded {result.Count} forged card(s) from {ForgedDir}.");
        return result;
    }

    private static EffectSpec[] ParseEffects(Godot.Collections.Array arr)
    {
        var list = new List<EffectSpec>(arr.Count);
        foreach (var item in arr)
        {
            if (item.VariantType != Godot.Variant.Type.Dictionary) continue;
            var e = item.AsGodotDictionary();
            string op = Str(e, "op");
            int amount = Int(e, "amount");
            string? status = e.ContainsKey("status") ? Str(e, "status") : null;
            int hits = e.ContainsKey("hits") ? Int(e, "hits", 1) : 1;
            // F5: `scale` is a string scalar source ("x"/"cards_in_hand"/"cards_retained"/"unspent_energy_last_turn");
            // null = fixed amount. Lowercased here; membership validated in Validate.
            string? scale = e.ContainsKey("scale") && Str(e, "scale").Trim().Length > 0
                          ? Str(e, "scale").Trim().ToLowerInvariant() : null;
            string? orb = e.ContainsKey("orb") ? Str(e, "orb").Trim().ToLowerInvariant() : null;
            // Phase J: apply_status_custom names a class status_pool entry (kept case-sensitive for display; the
            // resolver lowercases for matching). A distinct field from `status` so base-status checks don't fire.
            string? statusName = e.ContainsKey("status_name") ? Str(e, "status_name").Trim() : null;
            // Phase K: summon names a class summon_pool entry (a distinct field from status_name).
            string? summonName = e.ContainsKey("summon_name") ? Str(e, "summon_name").Trim() : null;
            Condition? when = null;
            if (e.ContainsKey("when") && e["when"].VariantType == Godot.Variant.Type.Dictionary)
            {
                var w = e["when"].AsGodotDictionary();
                when = new Condition(
                    Str(w, "kind").Trim().ToLowerInvariant(),
                    Int(w, "value"),
                    w.ContainsKey("status") ? Str(w, "status").Trim().ToLowerInvariant() : null,
                    w.ContainsKey("negate") && w["negate"].AsBool());
            }
            // Phase H3: add_trigger carries a trigger kind + a nested payload effects list (parsed recursively).
            string? trigger = null;
            EffectSpec[]? triggered = null;
            if (op == "add_trigger")
            {
                trigger = e.ContainsKey("trigger") ? Str(e, "trigger").Trim().ToLowerInvariant() : null;
                triggered = e.ContainsKey("effects") ? ParseEffects(e["effects"].AsGodotArray()) : [];
            }
            // Phase H4: `once_per_turn` gates a multi-fire reactive trigger (on the add_trigger op); `target`
            // aims a trigger PAYLOAD effect at enemies (enemy/all_enemies). Both default off/null; validated below.
            bool oncePerTurn = e.ContainsKey("once_per_turn") && e["once_per_turn"].AsBool();
            // Phase AK (v41): `once_per_combat` gates a power-hosted reactive trigger to ONE fire per combat.
            bool oncePerCombat = e.ContainsKey("once_per_combat") && e["once_per_combat"].AsBool();
            string? target = e.ContainsKey("target") ? Str(e, "target").Trim().ToLowerInvariant() : null;
            // Phase Q (gap #16): add_card names the SAME-CLASS card id to copy (case-sensitive, like summon_name)
            // and the destination pile (lowercased: hand/discard/draw). Distinct fields so base checks don't fire.
            string? cardId = e.ContainsKey("card_id") ? Str(e, "card_id").Trim() : null;
            string? pile = e.ContainsKey("pile") ? Str(e, "pile").Trim().ToLowerInvariant() : null;
            // Phase S (gap #1): balance_step names the pole to move the gauge toward (lowercased: light/dark).
            string? pole = e.ContainsKey("pole") ? Str(e, "pole").Trim().ToLowerInvariant() : null;
            // Phase U (gap #23): `grow` is the per-play damage step (Rampage). 0 = no grow; membership/legality
            // (damage-only, ⊥scale, 1..9, ≤amount) validated in Validate.
            int grow = e.ContainsKey("grow") ? Int(e, "grow") : 0;
            // Phase V (gap #18): `cards` is the upgrade_card hand-scope (lowercased: random/all). Membership +
            // op-legality validated in Validate; `all` is rejected inside a trigger payload (ValidateTrigger).
            string? cards = e.ContainsKey("cards") ? Str(e, "cards").Trim().ToLowerInvariant() : null;
            // Phase AE (gap #25): the `tag` the tag_cards_owned scalar counts (lowercased; membership/legality in Validate).
            string? tag = e.ContainsKey("tag") ? Str(e, "tag").Trim().ToLowerInvariant() : null;
            // Phase AN (v44): `unblockable` flags a damage op to ignore Block (damage-only, card-level; validated below).
            bool unblockable = e.ContainsKey("unblockable") && e["unblockable"].AsBool();
            // Phase AO (v45): cost_shift's card-type filter / lifetime (lowercased; membership in ValidateCostShift) and
            // its optional use budget (0 = the flat form).
            string? cardKind = e.ContainsKey("card_type") ? Str(e, "card_type").Trim().ToLowerInvariant() : null;
            string? scope = e.ContainsKey("scope") ? Str(e, "scope").Trim().ToLowerInvariant() : null;
            int count = e.ContainsKey("count") ? Int(e, "count") : 0;
            // Phase AP (v46): add_status_card's Status-card kind (lowercased: dazed/wound/burn; membership in Validate).
            string? statusCard = e.ContainsKey("card") ? Str(e, "card").Trim().ToLowerInvariant() : null;
            list.Add(new EffectSpec(op, amount, status, hits, scale, orb, when, trigger, triggered, statusName,
                                    summonName, oncePerTurn, target, cardId, pile, pole, grow, cards, tag,
                                    OncePerCombat: oncePerCombat, Unblockable: unblockable,
                                    CardKind: cardKind, Scope: scope, Count: count, StatusCard: statusCard));
        }
        return list.ToArray();
    }

    /// <summary>Re-validate every op/status against what EffectRunner + DataCard actually run. When
    /// <paramref name="allowCustomOrbs"/> (class cards), <c>channel_orb</c> accepts any non-empty orb name (it
    /// is resolved against the class's own pool at runtime, with a fallback); shared cards stay strict.</summary>
    private static string? Validate(EffectSpec[] effects, EffectSpec[]? upgrade, bool allowCustomOrbs = false,
        TargetType? target = null, IReadOnlySet<string>? orbNames = null)
    {
        foreach (var e in effects.Concat(upgrade ?? []))
        {
            if (!SupportedOps.Contains(e.Op))
                return $"unsupported op '{e.Op}'.";
            // H4: `target` aims a trigger PAYLOAD effect at enemies — never a card-level effect (cards use the
            // card-level target). `once_per_turn` gates a trigger — only meaningful on the add_trigger op.
            if (e.Target != null)
                return $"'target' only applies inside an add_trigger payload (op '{e.Op}' used it at card level).";
            if (e.OncePerTurn && e.Op != "add_trigger")
                return $"'once_per_turn' only applies to add_trigger (op '{e.Op}').";
            if (e.OncePerCombat && e.Op != "add_trigger") // Phase AK (v41)
                return $"'once_per_combat' only applies to add_trigger (op '{e.Op}').";
            if (e.Op == "apply_status" && (e.Status == null || !SupportedStatuses.Contains(e.Status)))
                return $"unsupported status '{e.Status}'.";
            if (AmountOps.Contains(e.Op) && !e.IsScaled && e.Amount < 1)
                return $"op '{e.Op}' needs amount >= 1.";
            if (e.Hits < 1)
                return $"op '{e.Op}' has hits < 1.";
            if (e.Hits > 1 && e.Op != "damage" && e.Op != "summon_attack")
                return $"'hits' only applies to 'damage'/'summon_attack' (op '{e.Op}' had hits {e.Hits}).";
            // Phase AN (v44): `unblockable` is a damage-op flag (it rides the damage var's ValueProp); a trigger payload
            // is rejected separately (ValidateTrigger) — the flag is card-level only.
            if (e.Unblockable && e.Op != "damage")
                return $"'unblockable' only applies to damage (op '{e.Op}').";
            // Phase AN (v44): gain_max_hp is a run-permanent stat gain (Feed) — a tight band. amount>=1 via AmountOps.
            if (e.Op == "gain_max_hp" && e.Amount > GainMaxHpMaxAmount)
                return $"gain_max_hp 'amount' may be at most {GainMaxHpMaxAmount}; got {e.Amount}.";
            // Phase AO (v45): cost_shift shape rules (shared with the relic parser); its three fields belong to it alone.
            // Card-only: not in TriggerOps (ValidateTrigger rejects a payload cost_shift).
            if (e.Op == "cost_shift")
            {
                var cserr = ValidateCostShift(e);
                if (cserr != null) return cserr;
            }
            else if (e.CardKind != null || e.Scope != null || e.Count != 0)
                return $"'card_type'/'scope'/'count' only apply to cost_shift (op '{e.Op}').";
            if (e.IsScaled)
            {
                if (!SupportedScales.Contains(e.Scale!))
                    return $"unsupported scale '{e.Scale}' (one of {string.Join("/", SupportedScales)}).";
                // Phase P (gap #21): lifesteal is heal-ONLY (replace-semantics; a preceding-damage check runs
                // per effect list below). Phase P (gap #22): debuff-count is damage-ONLY. Everything else
                // (F5 hand/energy reads + M's additive "forged") stays damage/block/draw.
                if (e.Scale == "damage_dealt_unblocked")
                {
                    if (e.Op != "heal")
                        return "'scale:damage_dealt_unblocked' only applies to heal (lifesteal — heal the unblocked damage this card dealt).";
                }
                else if (e.Scale == "target_debuff_count")
                {
                    if (e.Op != "damage")
                        return "'scale:target_debuff_count' only applies to damage (deal damage equal to the debuffs on the target).";
                }
                else if (e.Scale == "tag_cards_owned")
                {
                    // Phase AE (gap #25): ADDITIVE (printed amount + tagged-card count), damage/block-only, needs a tag.
                    if (e.Op is not ("damage" or "block"))
                        return "'scale:tag_cards_owned' only applies to damage/block (it ADDS the count of your tagged cards to a printed amount).";
                    if (string.IsNullOrEmpty(e.Tag))
                        return "a 'scale:tag_cards_owned' effect needs a 'tag' (the card tag it counts).";
                    if (e.Amount < 1)
                        return "a 'scale:tag_cards_owned' effect needs amount >= 1 (the count ADDS to the printed amount).";
                }
                else if (DamageBlockOnlyScales.Contains(e.Scale!)) // Phase AM (v43)
                {
                    if (e.Op is not ("damage" or "block"))
                        return $"'scale:{e.Scale}' only applies to damage/block (op '{e.Op}').";
                }
                else if (e.Op is not ("damage" or "block" or "draw"))
                    return $"'scale' only applies to damage/block/draw (op '{e.Op}').";
                // Phase M: the additive "forged" scalar adds Forge to a PRINTED damage/block base; a draw has
                // no calc-var site to add to (and "draw N plus your Forge" is not the keyword's fantasy).
                if (e.Scale == "forged" && e.Op == "draw")
                    return "'scale:forged' only applies to damage/block (Forge adds to a printed damage/block amount).";
                // Unlike the replace-semantics scalars (nominal amount ignored), a forged effect's printed
                // amount is REAL — it must exist (the generic amount>=1 check above skips scaled effects).
                if (e.Scale == "forged" && e.Amount < 1)
                    return "a 'scale:forged' effect needs amount >= 1 (Forge ADDS to the printed amount).";
                if (e.Hits > 1)
                    return "a scaled effect can't also be multi-hit (hits + scale on one effect).";
            }
            // Phase AE (gap #25): a `tag` only means something on a tag_cards_owned effect.
            if (e.Tag != null && e.Scale != "tag_cards_owned")
                return $"'tag' only applies to a 'scale:tag_cards_owned' effect (op '{e.Op}').";
            // Phase U (gap #23, Rampage): `grow` is an additive per-play damage step, damage-only, and NOT a scale.
            if (e.HasGrow)
            {
                if (e.Op != "damage")
                    return $"'grow' only applies to damage (op '{e.Op}').";
                if (e.IsScaled)
                    return "'grow' and 'scale' can't combine on one effect (grow is an additive per-play step, not a scalar).";
                if (e.Grow < 1 || e.Grow > 9)
                    return $"'grow' must be 1..9 (got {e.Grow}).";
                if (e.Grow > e.Amount)
                    return $"'grow' ({e.Grow}) can't exceed the base damage ({e.Amount}) — a card growing faster than its base reads as degenerate.";
            }
            if (e.Op == "channel_orb")
            {
                var oerr = OrbNameError(e.Orb, allowCustomOrbs, orbNames, "channel_orb");
                if (oerr != null) return oerr;
            }
            // Phase AJ (v40): a random_enemy card has NO chosen target — BaseLib rolls a random hittable enemy per
            // damage hit and per status effect — so the target-reading condition/scale can't be evaluated on it.
            if (target == TargetType.RandomEnemy)
            {
                if (e.When != null && e.When.Kind == "target_has_status")
                    return "'when:target_has_status' can't be used on a random_enemy card (no chosen target to read — each effect rolls its own random enemy).";
                if (e.Scale == "target_debuff_count")
                    return "'scale:target_debuff_count' can't be used on a random_enemy card (no chosen target to read — each effect rolls its own random enemy).";
            }
            // Phase AM (v43): the chosen-target conditions need a chosen target — a single-enemy card. AoE (play.Target
            // is null), self and random_enemy cards have none (the gate would silently never open).
            if (e.When != null && Conditions.TargetKinds.Contains(e.When.Kind) && target != null && target != TargetType.AnyEnemy)
                return $"'when:{e.When.Kind}' needs a single-enemy card (target \"enemy\") — it reads the chosen target.";
            if (e.Orb != null && e.Op != "channel_orb")
                return $"'orb' only applies to channel_orb (op '{e.Op}').";
            // Phase J: apply_status_custom is class-only (a forged status lives in a class's status_pool, resolved
            // at runtime against that class). allowCustomOrbs is the "class card" flag (set for every class card).
            if (e.Op == "apply_status_custom")
            {
                if (!allowCustomOrbs)
                    return "apply_status_custom is only valid on a class card (a forged status belongs to a class status_pool).";
                if (string.IsNullOrWhiteSpace(e.StatusName))
                    return "apply_status_custom needs a non-empty 'status_name' (a class status_pool entry).";
            }
            else if (e.StatusName != null)
                return $"'status_name' only applies to apply_status_custom (op '{e.Op}').";
            // Phase K: summon is class-only (a forged minion lives in a class's summon_pool, resolved at runtime).
            if (e.Op == "summon")
            {
                if (!allowCustomOrbs)
                    return "summon is only valid on a class card (a forged minion belongs to a class summon_pool).";
                if (string.IsNullOrWhiteSpace(e.SummonName))
                    return "summon needs a non-empty 'summon_name' (a class summon_pool entry).";
            }
            else if (e.SummonName != null)
                return $"'summon_name' only applies to summon (op '{e.Op}').";
            // Phase K (true-Osty): summon_attack / buff_summon act on the class's single living summon — class-only,
            // like summon. summon_attack strikes through the minion (the card's target/AoE applies); buff_summon's
            // status must be a self-buff (it lands on the minion), defaulting to Strength when omitted.
            if (e.Op == "summon_attack" && !allowCustomOrbs)
                return "summon_attack is only valid on a class card (it strikes through a class summon).";
            if (e.Op == "buff_summon")
            {
                if (!allowCustomOrbs)
                    return "buff_summon is only valid on a class card (it buffs a class summon).";
                if (e.Status != null && !EffectRunner.SelfBuffStatuses.Contains(e.Status))
                    return $"buff_summon 'status' must be a self-buff (e.g. strength); got '{e.Status}'.";
            }
            // Phase AC (gap #2): heal_summon / shield_summon heal / Block the class's one living summon — class-only,
            // like summon_attack/buff_summon (a lone card in a non-summon class has no minion to act on). amount>=1 is
            // enforced by AmountOps above; the per-op caps keep the medic engine bounded.
            if (e.Op == "heal_summon")
            {
                if (!allowCustomOrbs)
                    return "heal_summon is only valid on a class card (it heals a class summon).";
                if (e.Amount > HealSummonMaxAmount)
                    return $"heal_summon 'amount' may be at most {HealSummonMaxAmount}; got {e.Amount}.";
            }
            if (e.Op == "shield_summon")
            {
                if (!allowCustomOrbs)
                    return "shield_summon is only valid on a class card (it shields a class summon).";
                if (e.Amount > ShieldSummonMaxAmount)
                    return $"shield_summon 'amount' may be at most {ShieldSummonMaxAmount}; got {e.Amount}.";
            }
            // Phase Q (gap #16): add_card is class-only (the id resolves against the player's forged class at
            // runtime; a standalone forged card has no sibling set). card_id existence is checked at runtime
            // (ResolveClassCardModel warns + skips if the class has no such card), like unknown orb/summon names.
            if (e.Op == "add_card")
            {
                if (!allowCustomOrbs)
                    return "add_card is only valid on a class card (it copies a card from this class's own set).";
                if (string.IsNullOrWhiteSpace(e.CardId))
                    return "add_card needs a non-empty 'card_id' (a card in this class's own set).";
                if (e.Pile == null || !AddCardPiles.Contains(e.Pile))
                    return $"add_card needs a 'pile' (one of {string.Join("/", AddCardPiles)}); got '{e.Pile}'.";
                if (e.Amount > AddCardMaxAmount)
                    return $"add_card 'amount' (copies) may be at most {AddCardMaxAmount}; got {e.Amount}.";
            }
            // Phase AH (gaps #35/#38): transform_card also carries a same-class card_id (the card it PERMANENTLY
            // becomes when played) — so it shares the card_id allow-list with add_card. Class-only (the id resolves
            // against the player's forged class at runtime); it carries NO pile (transform is deck+hand, not a pile
            // drop) and NO amount. card_id existence / same-class + the no-chain (target not itself transform_card) /
            // self-transform (id == own id) / BASIC ban are checked runtime-side (ResolveTransformTarget logs + skips)
            // + generation-side (validator.py, which has full class context — mirrors add_card's depth-1 precedent).
            else if (e.Op == "transform_card")
            {
                if (!allowCustomOrbs)
                    return "transform_card is only valid on a class card (it becomes a card from this class's own set).";
                if (string.IsNullOrWhiteSpace(e.CardId))
                    return "transform_card needs a non-empty 'card_id' (the same-class card it becomes).";
                if (e.Pile != null)
                    return $"'pile' does not apply to transform_card (op '{e.Op}').";
                if (e.Amount != 0)
                    return "transform_card carries no amount (it's a flag-op naming the card to become).";
            }
            // Phase AI (gap #7): graft_card is the CHOOSE form of transform_card — it also carries a same-class
            // card_id (the card the PICKED hand card becomes), so it shares the card_id allow-list. Class-only,
            // no pile, no amount. Existence / same-class / no-chain / BASIC ban are checked runtime-side
            // (ResolveTransformTarget logs + skips) + generation-side (validator.py). Mirrors transform_card.
            else if (e.Op == "graft_card")
            {
                if (!allowCustomOrbs)
                    return "graft_card is only valid on a class card (the picked card becomes a card from this class's own set).";
                if (string.IsNullOrWhiteSpace(e.CardId))
                    return "graft_card needs a non-empty 'card_id' (the same-class card the picked card becomes).";
                if (e.Pile != null)
                    return $"'pile' does not apply to graft_card (op '{e.Op}').";
                if (e.Amount != 0)
                    return "graft_card carries no amount (it's a flag-op naming the card to graft into).";
            }
            // Phase AP (v46): retrieve_card pulls card(s) back to hand from the discard or exhaust pile (the Headbutt /
            // Exhume shape). Not class-only (any pile card qualifies; Status/Curse cards are skipped at runtime). Carries a
            // pile (discard/exhaust), a pick mode (random/choose) and an optional amount 1..2 (default 1 — not in
            // AmountOps, like add_card's copies). No card_id. Card-only (not in TriggerOps).
            else if (e.Op == "retrieve_card")
            {
                if (e.Pile == null || !RetrievePiles.Contains(e.Pile))
                    return $"retrieve_card needs a 'pile' (one of {string.Join("/", RetrievePiles)}); got '{e.Pile}'.";
                if (e.Cards == null || !PickModes.Contains(e.Cards))
                    return $"retrieve_card needs a 'cards' pick mode (one of {string.Join("/", PickModes)}); got '{e.Cards}'.";
                if (e.CardId != null)
                    return "'card_id' does not apply to retrieve_card (it returns whatever is in the pile, not a named card).";
                if (e.Amount > RetrieveMaxAmount)
                    return $"retrieve_card 'amount' (cards returned) may be at most {RetrieveMaxAmount}; got {e.Amount}.";
            }
            // Phase AP (v46): add_status_card generates base-game STATUS cards (dazed/wound/burn) into a combat pile — the
            // self-drawback of an over-statted card. Not class-only (the cards are the game's own). Carries the kind
            // (`card`), a pile (hand/discard/draw — the add_card piles) and an optional amount 1..3 (default 1).
            else if (e.Op == "add_status_card")
            {
                if (e.StatusCard == null || !StatusCards.Contains(e.StatusCard))
                    return $"add_status_card needs a 'card' (one of {string.Join("/", StatusCards)}); got '{e.StatusCard}'.";
                if (e.Pile == null || !AddCardPiles.Contains(e.Pile))
                    return $"add_status_card needs a 'pile' (one of {string.Join("/", AddCardPiles)}); got '{e.Pile}'.";
                if (e.CardId != null)
                    return "'card_id' does not apply to add_status_card (use 'card': dazed/wound/burn).";
                if (e.Amount > StatusCardMaxAmount)
                    return $"add_status_card 'amount' (cards added) may be at most {StatusCardMaxAmount}; got {e.Amount}.";
            }
            else if (e.CardId != null || e.Pile != null)
                return $"'card_id'/'pile' only apply to add_card/transform_card/graft_card/retrieve_card/add_status_card (op '{e.Op}').";
            if (e.StatusCard != null && e.Op != "add_status_card")
                return $"'card' only applies to add_status_card (op '{e.Op}').";
            // Phase T: summon_blade retrieves THIS class's signature blade — class-only, like add_card/summon.
            // It carries no amount/card_id (the blade is resolved from the class at runtime; no such card → no-op).
            if (e.Op == "summon_blade" && !allowCustomOrbs)
                return "summon_blade is only valid on a class card (it retrieves this class's signature blade).";
            // Phase S (gap #1): balance_step needs a valid pole and a bounded step size. Unlike orbs/status/summon
            // there is no class pool to gate on — a lone balance card is a warning (generation side), not a reject;
            // the runtime just moves the gauge. amount>=1 is enforced by the AmountOps check above.
            if (e.Op == "balance_step")
            {
                if (e.Pole == null || !BalancePoles.Contains(e.Pole))
                    return $"balance_step needs a 'pole' (one of {string.Join("/", BalancePoles)}); got '{e.Pole}'.";
                if (e.Amount > BalanceStepMaxAmount)
                    return $"balance_step 'amount' (step size) may be at most {BalanceStepMaxAmount}; got {e.Amount}.";
            }
            else if (e.Pole != null)
                return $"'pole' only applies to balance_step (op '{e.Op}').";
            // Phase V (gap #18): upgrade_card needs a valid hand-scope (random/all). Not class-only (it works on
            // whatever cards are in hand — no class pool). Carries no amount (not in AmountOps). Combat-scoped.
            if (e.Op == "upgrade_card")
            {
                if (e.Cards == null || !UpgradeScopes.Contains(e.Cards))
                    return $"upgrade_card needs a 'cards' scope (one of {string.Join("/", UpgradeScopes)}); got '{e.Cards}'.";
            }
            // Phase AP (v46): discard's optional pick mode — `random` (the Phase-R choiceless form, the default when
            // absent) or `choose` (the player picks which hand cards to discard; card-only — ValidateTrigger rejects it).
            else if (e.Op == "discard")
            {
                if (e.Cards != null && !PickModes.Contains(e.Cards))
                    return $"discard 'cards' must be one of {string.Join("/", PickModes)}; got '{e.Cards}'.";
            }
            else if (e.Cards != null && e.Op != "retrieve_card") // retrieve_card's pick mode is validated above
                return $"'cards' only applies to upgrade_card/discard/retrieve_card (op '{e.Op}').";
            // Phase AV (v52): sacrifice_summon is a flag-op that consumes the class's living minion so its on_death
            // rattle fires. Class-only (like `summon` — it needs a summon_pool to have anything to kill), carries no
            // amount/target/status, and card-only (it is not in TriggerOps, so ValidateTrigger rejects a payload one).
            if (e.Op == "sacrifice_summon")
            {
                if (!allowCustomOrbs)
                    return "sacrifice_summon is only valid on a class card (a summon class — it consumes that class's minion).";
                if (e.Amount != 0)
                    return "sacrifice_summon carries no amount (it's a flag-op that consumes your summon).";
                if (e.Status != null)
                    return $"'status' does not apply to sacrifice_summon (op '{e.Op}').";
            }
            // Phase AB (gap #20): corruption is a binary flag-op (grants the Corruption power). It carries no amount
            // (like exhaust/purge). Card-type legality (power/skill only, card-only) is enforced generation-side +
            // the payload rejection is automatic (corruption is not in TriggerOps → ValidateTrigger rejects it).
            if (e.Op == "corruption" && e.Amount != 0)
                return "corruption carries no amount (it's a flag-op that grants the Corruption power).";
            // Phase AF (gap #41): blade_empower is the ×N blade multiplier — bounded 2..3 (×1 is a no-op, ×4+ is a
            // degenerate spike). amount>=1 is enforced by AmountOps above; here we tighten the band. Forge-class-only +
            // card-only are enforced generation-side (validator + character_validator) / by not being in TriggerOps.
            if (e.Op == "blade_empower" && (e.Amount < 2 || e.Amount > 3))
                return $"blade_empower 'amount' (the multiplier) must be 2 or 3; got {e.Amount}.";
            // Phase AX (v53, gap #44): spend_forge CONSUMES the per-combat Forge counter as this card's price (the
            // cash-out half of the ramp `forge` builds). amount>=1 is enforced by AmountOps above; here we cap the
            // band. Forge-class-only + card-only are enforced generation-side (validator + character_validator) /
            // by not being in TriggerOps — exactly like blade_empower.
            if (e.Op == "spend_forge" && e.Amount > SpendForgeMaxAmount)
                return $"spend_forge 'amount' (the Forge consumed) may be at most {SpendForgeMaxAmount}; got {e.Amount}.";
            // Phase AX (v53, gaps #45-#47): spread_debuffs is a flag-op — it copies the STRUCK target's debuffs onto
            // every OTHER living enemy, so it reads the chosen target (single-enemy cards only, like the AM target
            // conditions) and carries no amount/status/hits/scale of its own.
            if (e.Op == "spread_debuffs")
            {
                if (e.Amount != 0)
                    return "spread_debuffs carries no amount (it copies the debuffs already on the target).";
                if (e.Status != null)
                    return $"'status' does not apply to spread_debuffs (it copies whatever debuffs the target has).";
                if (e.IsScaled)
                    return "'scale' does not apply to spread_debuffs (it copies the target's live debuff stacks).";
                if (target != null && target != TargetType.AnyEnemy)
                    return "spread_debuffs needs a single-enemy card (target \"enemy\") — it copies the CHOSEN target's debuffs to the others.";
            }
            if (e.When != null)
            {
                var cerr = Conditions.Validate(e.When);
                if (cerr != null) return cerr;
            }
            if (e.Op == "add_trigger")
            {
                var terr = ValidateTrigger(e, allowCustomOrbs, orbNames);
                if (terr != null) return terr;
            }
        }
        // One "Hits" DynamicVar per card → at most one multi-hit damage effect (in the base effects).
        if (effects.Count(e => e.Hits > 1) > 1)
            return "at most one multi-hit damage effect per card.";
        // One calculated var per card (BaseLib limit): damage/block scaling each declares a CalculatedVar, so at
        // most one scaled damage/block per card (a scaled draw uses no var and is exempt). Phase U (gap #23): a
        // `grow` damage ALSO declares a CalculatedDamage var, so it counts toward the same one-calc-var budget.
        if (effects.Count(e => (e.IsScaled && e.Op is "damage" or "block") || (e.HasGrow && e.Op == "damage")) > 1)
            return "at most one scaled/grow damage/block effect per card (the engine allows one calculated value).";
        // The game builds one DynamicVarSet per card and THROWS on a duplicate key, so a card may declare each
        // canonical value only ONCE (one damage, one block, one of each status, …). This is a hard safety
        // boundary: an authored/LLM card with two same-type effects would otherwise crash the game on play.
        // Phase AX (v53): apply_status is the ONE exception — a card may declare the same status TWICE when the
        // SECOND one is `when`-gated (the "Weak now, Weak2 if the gate opens" shape). The second takes a SUFFIXED
        // var ("Weak2", see StatusVarName) so the DynamicVarSet still sees unique keys, and it applies with a
        // literal amount at execution (EffectRunner) instead of through the card's PowerVar.
        for (int i = 0; i < effects.Length; i++)
        {
            if (effects[i].Op != "apply_status") continue;
            int occ = StatusOccurrence(effects, i);
            if (occ >= MaxSameStatusPerCard)
                return $"a card may declare '{effects[i].Status}' at most {MaxSameStatusPerCard} times " +
                       "(one plain + one `when`-gated); a third is never readable on the card.";
            if (occ > 0 && effects[i].When == null)
                return $"a second '{effects[i].Status}' effect must be `when`-gated (the first is the printed " +
                       "amount; the second is the conditional bonus) — an ungated pair should just be one bigger number.";
        }
        var varKeys = Enumerable.Range(0, effects.Length).Select(i => VarKey(effects, i)).Where(k => k != null).ToList();
        var dup = varKeys.GroupBy(k => k).FirstOrDefault(g => g.Count() > 1);
        if (dup != null)
            return $"two effects both declare '{dup.Key}' — a card may use each value only once " +
                   "(one damage, one block, one of each status, etc.); combine them or use different ops.";
        // Phase AX (v53): the two new ops are one-per-effect-list (base + upgrade counted independently, like
        // graft_card / cost_shift — an upgrade repeating one is the normal replace-on-upgrade pattern).
        if (effects.Count(e => e.Op == "spend_forge") > 1 || (upgrade ?? []).Count(e => e.Op == "spend_forge") > 1)
            return "at most one 'spend_forge' effect per card (one cash-out per play).";
        if (effects.Count(e => e.Op == "spread_debuffs") > 1 || (upgrade ?? []).Count(e => e.Op == "spread_debuffs") > 1)
            return "at most one 'spread_debuffs' effect per card (the debuffs only need copying once).";
        // Phase AX (v53): spend_forge is the PRICE half of a card, so it may never be the whole card — the rest of
        // the effect list is what the Forge buys (mirrors the sacrifice_summon rule).
        foreach (var list in new[] { effects, upgrade })
            if (list is { Length: > 0 } && list.All(e => e.Op == "spend_forge"))
                return "'spend_forge' can't be a card's only effect (the spend is the price — the rest of the card is the payoff).";
        // One add_trigger per card: a card grants a single trigger power, which reads only the first add_trigger.
        if (effects.Count(e => e.Op == "add_trigger") > 1)
            return "at most one add_trigger per card (a card grants a single trigger power).";
        // Phase W (gap #19): purge ⊥ exhaust. Both are "the card leaves after this play"; a card can't do both
        // (exhaust → Exhaust pile this combat only; purge → gone from the run). One at most, per base-StS convention.
        if (effects.Any(e => e.Op == "purge") && effects.Any(e => e.Op == "exhaust"))
            return "a card can't be both 'purge' and 'exhaust' (purge already removes it from the run — pick one).";
        // Phase AH (gaps #35/#38): transform_card ⊥ purge. Both permanently rewrite the run-deck original; a card
        // can't both BECOME another card and DELETE itself from the run (contradictory). One at most, per card.
        if ((effects.Concat(upgrade ?? [])).Any(e => e.Op == "transform_card")
            && (effects.Concat(upgrade ?? [])).Any(e => e.Op == "purge"))
            return "a card can't be both 'transform_card' and 'purge' (transform rewrites the run-deck original; purge deletes it — pick one).";
        // Phase AH: at most one transform_card per card (a card becomes ONE thing; two targets is ambiguous).
        if ((effects.Concat(upgrade ?? [])).Count(e => e.Op == "transform_card") > 1)
            return "at most one 'transform_card' effect per card (a card can only become one other card).";
        // Phase AI (gap #7): graft_card ⊥ purge/purge_card. Graft transforms a picked card; purge/purge_card DELETE
        // a card from the run — mixing a transform-the-deck op with a delete-from-the-deck op on one play is a
        // contradiction (same transform-vs-delete permanence family as transform_card ⊥ purge). One at most, per card.
        var allFx = effects.Concat(upgrade ?? []).ToList();
        if (allFx.Any(e => e.Op == "graft_card") && allFx.Any(e => e.Op == "purge" || e.Op == "purge_card"))
            return "a card can't be both 'graft_card' and 'purge'/'purge_card' (graft transforms a card; purge deletes one — pick one).";
        // Phase AI: at most one graft_card per EFFECT LIST (one pick becomes one thing per play; two grafts is
        // ambiguous). Base + upgrade are counted INDEPENDENTLY — an upgrade repeating graft_card is the normal
        // replace-on-upgrade pattern (the played card runs one list at a time), matching validator.py.
        if (effects.Count(e => e.Op == "graft_card") > 1 || (upgrade ?? []).Count(e => e.Op == "graft_card") > 1)
            return "at most one 'graft_card' effect per card (a graft transforms the picked card into one other card).";
        // Phase AB (gap #20): at most one corruption per card (Corruption is a binary power — a second grant is noise).
        if (effects.Count(e => e.Op == "corruption") > 1)
            return "at most one 'corruption' effect per card (Corruption is a binary power — one grant is enough).";
        // Phase AV (v52): at most one sacrifice_summon per EFFECT LIST (you only have one front-most minion to spend;
        // base + upgrade counted independently, like graft_card / cost_shift — an upgrade repeating it is the normal
        // replace-on-upgrade pattern), and it may never be a card's ONLY effect: the sacrifice is the PRICE and the
        // rest of the card is the payoff, so a lone sacrifice_summon would be a card that does nothing but kill your pet.
        if (effects.Count(e => e.Op == "sacrifice_summon") > 1 || (upgrade ?? []).Count(e => e.Op == "sacrifice_summon") > 1)
            return "at most one 'sacrifice_summon' effect per card (you have one summon to spend).";
        foreach (var list in new[] { effects, upgrade })
            if (list is { Length: > 0 } && list.All(e => e.Op == "sacrifice_summon"))
                return "'sacrifice_summon' can't be a card's only effect (the sacrifice is the price — the rest of the card is the payoff).";
        // Phase AO (v45): at most one cost_shift per EFFECT LIST (one discount sentence per play; base + upgrade counted
        // independently, like graft_card — an upgrade repeating it is the normal replace-on-upgrade pattern).
        if (effects.Count(e => e.Op == "cost_shift") > 1 || (upgrade ?? []).Count(e => e.Op == "cost_shift") > 1)
            return "at most one 'cost_shift' effect per card (one discount per play).";
        // Phase P (gap #21): a lifesteal heal reads the unblocked damage this card ALREADY dealt this play, so it
        // needs a damage op earlier in the SAME list (base and upgrade checked independently — the runtime runs
        // each list top-to-bottom, so a heal with no prior damage would always lifesteal 0).
        foreach (var list in new[] { effects, upgrade })
        {
            if (list == null) continue;
            for (int i = 0; i < list.Length; i++)
                if (list[i].Op == "heal" && list[i].Scale == "damage_dealt_unblocked"
                    && !list.Take(i).Any(p => p.Op == "damage"))
                    return "a 'scale:damage_dealt_unblocked' heal needs a 'damage' op earlier in the same card (you heal the damage you dealt).";
        }
        // Phase AX (v53, gap #44): a `when:forged_ge` gate reads the LIVE Forge counter at execution time, and
        // effects resolve top-to-bottom — so a gated payoff placed AFTER the spend_forge that empties the counter
        // would test a number the same card just spent (the gate reads 0 and the payoff never fires). Order the
        // card "gated payoff first, spend last". Base and upgrade checked independently, like the lifesteal rule.
        foreach (var list in new[] { effects, upgrade })
        {
            if (list == null) continue;
            for (int i = 0; i < list.Length; i++)
                if (list[i].When?.Kind == "forged_ge" && list.Take(i).Any(q => q.Op == "spend_forge"))
                    return "a 'when:forged_ge' effect can't come after a 'spend_forge' in the same card " +
                           "(the spend empties the counter the gate reads) — put the gated payoff FIRST and spend last.";
        }
        // Phase AX (v53): the upgrade list is a POSITIONAL overlay (EffectRunner.UpgradeDelta reads it by index), so
        // it normally has to match the base list's length exactly. The one relaxation: an upgrade may CHANGE ONE
        // KEYWORD — append exactly one of exhaust/retain/innate/ethereal that the base doesn't have (the upgrade
        // gains Exhaust/Retain/…), or drop a TRAILING exhaust (the upgrade sheds the drawback). Both keep indices
        // 0..n-1 aligned, so the overlay still works; DataCard turns the base-vs-upgrade keyword diff into BaseLib
        // UpgradeType.Add / UpgradeType.Remove. Anything else is still a reject.
        if (upgrade != null)
        {
            var kerr = ValidateUpgradeShape(effects, upgrade);
            if (kerr != null) return kerr;
        }
        return null;
    }

    /// <summary>Phase AX (v53): the base-vs-upgrade effect-list shape rule (see the call site). Returns null when the
    /// pair is legal. Shared by nothing else — kept separate so the rule reads in one piece and mirrors
    /// validator.py's <c>_upgrade_shape_errors</c> line for line.</summary>
    private static string? ValidateUpgradeShape(EffectSpec[] effects, EffectSpec[] upgrade)
    {
        int delta = upgrade.Length - effects.Length;
        var baseKw = effects.Where(e => KeywordOps.Contains(e.Op)).Select(e => e.Op).ToHashSet();
        var upKw = upgrade.Where(e => KeywordOps.Contains(e.Op)).Select(e => e.Op).ToHashSet();
        if (delta == 0)
        {
            // Equal length: the keyword set must be identical too (the positional overlay carries amounts, not
            // keywords — a silently different keyword at the same index would never reach the card).
            if (!baseKw.SetEquals(upKw))
                return "an equal-length upgrade must carry the same keywords as the base card " +
                       "(to ADD a keyword, APPEND it as one extra upgrade effect; to remove one, drop the trailing 'exhaust').";
            return null;
        }
        if (delta == 1)
        {
            var extra = upgrade[^1];
            if (!UpgradeAddableKeywords.Contains(extra.Op))
                return $"an upgrade with one extra effect may only APPEND a keyword " +
                       $"({string.Join("/", UpgradeAddableKeywords)}); got '{extra.Op}'.";
            if (baseKw.Contains(extra.Op))
                return $"the base card already has '{extra.Op}' — an upgrade can't add it twice.";
            // The first N upgrade effects still overlay the base positionally, so only the appended keyword is new.
            if (!upKw.SetEquals(baseKw.Append(extra.Op).ToHashSet()))
                return "an upgrade may change at most ONE keyword (append one, or drop the trailing 'exhaust').";
            return null;
        }
        if (delta == -1)
        {
            if (effects[^1].Op != "exhaust")
                return "an upgrade with one FEWER effect may only drop a TRAILING 'exhaust' " +
                       $"(the base card's last effect is '{effects[^1].Op}').";
            if (upKw.Contains("exhaust"))
                return "the upgrade still carries 'exhaust' — drop it from the upgrade list to remove it.";
            if (!upKw.SetEquals(baseKw.Where(k => k != "exhaust").ToHashSet()))
                return "an upgrade may change at most ONE keyword (append one, or drop the trailing 'exhaust').";
            return null;
        }
        return "upgrade effect count must match base effect count " +
               "(or append exactly one keyword / drop a trailing 'exhaust').";
    }

    /// <summary>Phase AX (v53): how many EARLIER effects apply the SAME status as <paramref name="i"/> (0 = this is
    /// the first / not an apply_status). Occurrence 1 is the `when`-gated second copy, which takes the suffixed var
    /// name and applies with a literal amount. Mirrors validator._status_occurrence.</summary>
    internal static int StatusOccurrence(EffectSpec[] effects, int i)
    {
        if (effects[i].Op != "apply_status") return 0;
        int n = 0;
        for (int j = 0; j < i; j++)
            if (effects[j].Op == "apply_status" && effects[j].Status == effects[i].Status) n++;
        return n;
    }

    /// <summary>Validate a Phase H3 <c>add_trigger</c>: a known trigger kind, a non-empty payload drawn only
    /// from the self/orb-only <see cref="TriggerOps"/> (trigger apply_status must be a self-buff) or the targeted
    /// <see cref="TriggerTargetedOps"/>, no nested trigger / inner when, only the player-level
    /// <see cref="TriggerScales"/> (Phase AL, v42), multi-hit on damage/summon_attack only (Phase AL), and a
    /// fire-time When that doesn't need a target.</summary>
    /// <summary>Phase AJ (v40): the ONE orb-name rule for card-level AND trigger-payload channel_orb. Shared cards:
    /// base orbs / 'random' only. Class cards: any non-empty name — and when the importer hands over the class's
    /// declared CUSTOM pool names (<paramref name="orbNames"/>, lowercase), a custom name must be in it (mirrors the
    /// generation validator's base ∪ random ∪ declared-customs rule; an unknown name used to channel Lightning silently).</summary>
    private static string? OrbNameError(string? orb, bool allowCustomOrbs, IReadOnlySet<string>? orbNames, string where)
    {
        if (string.IsNullOrEmpty(orb))
            return allowCustomOrbs
                ? $"{where} needs a non-empty 'orb' name (a class pool entry or 'random')."
                : $"{where} needs a valid 'orb' (one of {string.Join("/", SupportedOrbs)}); got '{orb}'.";
        if (!allowCustomOrbs)
            return SupportedOrbs.Contains(orb) ? null
                : $"{where} needs a valid 'orb' (one of {string.Join("/", SupportedOrbs)}); got '{orb}'.";
        if (orbNames != null && !SupportedOrbs.Contains(orb) && !orbNames.Contains(orb.ToLowerInvariant()))
            return $"{where} 'orb':'{orb}' is not a base orb, 'random', or a custom orb in this class's orb_pool " +
                   $"({(orbNames.Count == 0 ? "none declared" : string.Join("/", orbNames))}).";
        return null;
    }

    private static string? ValidateTrigger(EffectSpec e, bool allowCustomOrbs = false, IReadOnlySet<string>? orbNames = null)
    {
        if (e.Trigger == null || !SupportedTriggers.Contains(e.Trigger))
            return $"add_trigger needs a valid 'trigger' (one of {string.Join("/", SupportedTriggers)}); got '{e.Trigger}'.";
        if (e.Triggered == null || e.Triggered.Length == 0)
            return "add_trigger needs a non-empty 'effects' list (what it does each turn when it fires).";
        // gap #6 "ripen": the add_trigger Amount is the countdown (turns to wait before the one-shot fires).
        if (e.Trigger == "ripen" && e.Amount < 1)
            return "a 'ripen' trigger needs amount >= 1 (the number of turns to wait before it fires once).";
        // H4: `once_per_turn` only makes sense on a multi-fire reactive trigger (turn_start/turn_end/ripen already
        // fire at most once per turn).
        if (e.OncePerTurn && !MultiFireTriggers.Contains(e.Trigger))
            return $"'once_per_turn' only applies to a multi-fire trigger ({string.Join("/", MultiFireTriggers)}); " +
                   $"'{e.Trigger}' already fires at most once per turn.";
        // Phase AK (v41): `once_per_combat` only on a POWER-HOSTED reactive trigger (the fired flag lives on the
        // per-combat power instance); on_discard is card-latent, turn_start/turn_end/ripen aren't reactive.
        if (e.OncePerCombat && !OncePerCombatTriggers.Contains(e.Trigger))
            return $"'once_per_combat' only applies to a power-hosted reactive trigger ({string.Join("/", OncePerCombatTriggers)}); got '{e.Trigger}'.";
        if (e.OncePerCombat && e.OncePerTurn)
            return "'once_per_combat' already implies once per turn — set one, not both.";
        foreach (var t in e.Triggered)
        {
            // Phase U (gap #23): `grow` is a per-card-play attack mechanic (a card growing as YOU replay IT) — it
            // has no meaning in a trigger payload (which re-runs from a granted power, not a card the player replays).
            if (t.HasGrow)
                return "'grow' is not allowed in a trigger payload (it's a per-card-play attack mechanic).";
            // Phase AN (v44): `unblockable` rides a CARD's damage var; a payload damage is an intrinsic CreatureCmd hit
            // with no var to flag. Card-level only.
            if (t.Unblockable)
                return "'unblockable' is not allowed in a trigger payload (it flags a card-level damage).";
            // Phase AL (v42): `hits` inside a payload — on damage (targeted) and summon_attack only, like the card
            // level ("Whenever you are attacked, deal 2 damage 3 times to the attacker"). TriggerRunner loops the
            // hits; no DynamicVar is involved (payload amounts are literal).
            if (t.Hits < 1)
                return $"trigger effect '{t.Op}' has hits < 1.";
            if (t.Hits > 1 && t.Op is not ("damage" or "summon_attack"))
                return $"'hits' only applies to a trigger 'damage'/'summon_attack' (trigger effect '{t.Op}' had hits {t.Hits}).";
            // H4 (gap #14): a payload effect with a `target` may hit enemies (damage / enemy-debuff apply_status;
            // Phase AL: + summon_attack / a custom-debuff apply_status_custom); without a target it stays self/orb-only.
            if (t.Target != null)
            {
                if (t.Target != "enemy" && t.Target != "all_enemies" && t.Target != "attacker")
                    return $"a trigger effect 'target' must be 'enemy', 'all_enemies' or 'attacker' (got '{t.Target}').";
                // Phase AK (v41): 'attacker' (the creature that just hit you) only exists on the `attacked` trigger.
                if (t.Target == "attacker" && e.Trigger != "attacked")
                    return $"a trigger effect target 'attacker' is only valid on the 'attacked' trigger (got '{e.Trigger}').";
                if (!TriggerTargetedOps.Contains(t.Op))
                    return $"a targeted trigger effect must be 'damage', an enemy-debuff 'apply_status', 'summon_attack' or 'apply_status_custom' (got '{t.Op}').";
                if (t.Op == "apply_status" && (t.Status == null || !EnemyDebuffStatuses.Contains(t.Status)))
                    return $"a targeted trigger apply_status must be an enemy debuff " +
                           $"({string.Join("/", EnemyDebuffStatuses)}); got '{t.Status}'.";
                // Phase AL (v42): a targeted payload DAMAGE may be scaled ("deal damage equal to the cards in your hand
                // to ALL enemies"); a targeted debuff / summon strike / custom status stays literal.
                if (t.IsScaled && t.Op != "damage")
                    return $"only a targeted trigger 'damage' may be scaled (trigger effect '{t.Op}' had scale '{t.Scale}').";
            }
            else
            {
                if (!TriggerOps.Contains(t.Op))
                    return $"trigger effect '{t.Op}' is not allowed in a self trigger (self/orb-only: {string.Join("/", TriggerOps)}); " +
                           "add a 'target' (enemy/all_enemies) for a damage, enemy-debuff or summon_attack effect.";
                if (t.Op == "apply_status" && (t.Status == null || !EffectRunner.SelfBuffStatuses.Contains(t.Status)))
                    return $"a self trigger apply_status must be a self-buff (got '{t.Status}'); add target:enemy for a debuff.";
                // Phase AJ (v40): a trigger-payload channel_orb may name any orb in the class's pool (TriggerRunner
                // resolves it against the player's class at fire time) — the same rule as the card-level op.
                if (t.Op == "channel_orb")
                {
                    var oerr = OrbNameError(t.Orb, allowCustomOrbs, orbNames, "trigger channel_orb");
                    if (oerr != null) return oerr;
                }
            }
            // F5 / Phase AL (v42): a payload effect may scale to a PLAYER-level read (TriggerScales), and only on the
            // ops that carry a scalable amount — never channel_orb/evoke (a count), never forge/balance_step (fixed
            // income drumbeat — the payoff card is where scaling lives), never the summon/custom-status/pile ops.
            if (t.IsScaled)
            {
                if (!TriggerScales.Contains(t.Scale!))
                    return $"inside a trigger 'scale' must be one of {string.Join("/", TriggerScales)} (got scale '{t.Scale}').";
                if (t.Op is "channel_orb" or "evoke")
                    return $"'scale:{t.Scale}' can't be used on a trigger '{t.Op}' (it has no scalable amount).";
                if (t.Op == "forge" || t.Op == "balance_step")
                    return $"a trigger '{t.Op}' uses a fixed amount (no scale).";
                if (!TriggerScalableOps.Contains(t.Op))
                    return $"'scale:{t.Scale}' can't be used on a trigger '{t.Op}' (only {string.Join("/", TriggerScalableOps)} carry a scalable amount).";
                // Phase AL: the ADDITIVE forged scalar keeps its card-level shape — damage/block only, printed amount real.
                if (t.Scale == "forged" && t.Op is not ("damage" or "block"))
                    return "'scale:forged' inside a trigger only applies to damage/block (Forge ADDS to a printed damage/block amount).";
                if (t.Scale == "forged" && t.Amount < 1)
                    return "a 'scale:forged' trigger effect needs amount >= 1 (Forge ADDS to the printed amount).";
                if (t.Hits > 1)
                    return "a scaled trigger effect can't also be multi-hit (hits + scale on one effect).";
                // AutoSlay finding (GAPTESTAL1): AfterSideTurnEnd fires AFTER the end-of-turn discard, so a turn_end
                // cards_in_hand always reads 0 (only Retained cards remain — that is what cards_retained is for).
                if (t.Scale == "cards_in_hand" && e.Trigger == "turn_end")
                    return "'scale:cards_in_hand' can't be used on a turn_end trigger (the hand is already discarded when it fires — use turn_start or a reactive trigger, or scale:cards_retained).";
            }
            if (t.Orb != null && t.Op != "channel_orb")
                return $"'orb' only applies to channel_orb (trigger effect '{t.Op}').";
            // Phase AL (v42): the class engines as payloads — class-only (the class is read off the player at fire
            // time), a non-empty status_name for apply_status_custom (pool membership is a runtime warn+skip, like the
            // card-level op), a self-buff status for buff_summon. amount >= 1 is enforced by the AmountOps check below.
            if (t.Op == "apply_status_custom")
            {
                if (!allowCustomOrbs)
                    return "a trigger apply_status_custom is only valid on a class card (a forged status belongs to a class status_pool).";
                if (string.IsNullOrWhiteSpace(t.StatusName))
                    return "a trigger apply_status_custom needs a non-empty 'status_name' (a class status_pool entry).";
            }
            else if (t.StatusName != null)
                return $"'status_name' only applies to apply_status_custom (trigger effect '{t.Op}').";
            if (t.Op == "summon_attack" && !allowCustomOrbs)
                return "a trigger summon_attack is only valid on a class card (it strikes through this class's summon).";
            if (t.Op == "buff_summon")
            {
                if (!allowCustomOrbs)
                    return "a trigger buff_summon is only valid on a class card (it buffs this class's summon).";
                if (t.Status != null && !EffectRunner.SelfBuffStatuses.Contains(t.Status))
                    return $"a trigger buff_summon 'status' must be a self-buff (e.g. strength); got '{t.Status}'.";
            }
            // Phase Q (gap #16): a trigger-payload add_card (the on_exhaust "compost" loop) — class-only, with a
            // valid card_id/pile and the amount cap. Runtime resolves the id against the player's class + refuses a
            // nested add_card (depth-1). Targeting add_card is already rejected above (only damage/apply_status target).
            if (t.Op == "add_card")
            {
                if (!allowCustomOrbs)
                    return "a trigger add_card is only valid on a class card (it copies a card from this class's own set).";
                if (string.IsNullOrWhiteSpace(t.CardId))
                    return "a trigger add_card needs a non-empty 'card_id' (a card in this class's own set).";
                if (t.Pile == null || !AddCardPiles.Contains(t.Pile))
                    return $"a trigger add_card needs a 'pile' (one of {string.Join("/", AddCardPiles)}); got '{t.Pile}'.";
                if (t.Amount > AddCardMaxAmount)
                    return $"a trigger add_card 'amount' (copies) may be at most {AddCardMaxAmount}; got {t.Amount}.";
            }
            else if (t.CardId != null || t.Pile != null)
                return $"'card_id'/'pile' only apply to add_card (trigger effect '{t.Op}').";
            // Phase T: a trigger-payload summon_blade (blade retrieval on a reactive trigger) — class-only, no amount.
            if (t.Op == "summon_blade" && !allowCustomOrbs)
                return "a trigger summon_blade is only valid on a class card (it retrieves this class's signature blade).";
            // Phase S (gap #1): a trigger-payload balance_step (the "engine" — steady per-turn gauge income) needs a
            // valid pole and a bounded step; amount>=1 is enforced by the AmountOps check below.
            if (t.Op == "balance_step")
            {
                if (t.Pole == null || !BalancePoles.Contains(t.Pole))
                    return $"a trigger balance_step needs a 'pole' (one of {string.Join("/", BalancePoles)}); got '{t.Pole}'.";
                if (t.Amount > BalanceStepMaxAmount)
                    return $"a trigger balance_step 'amount' (step size) may be at most {BalanceStepMaxAmount}; got {t.Amount}.";
            }
            else if (t.Pole != null)
                return $"'pole' only applies to balance_step (trigger effect '{t.Op}').";
            // Phase AC (gap #2): a trigger-payload heal_summon / shield_summon (the medic engine — "at turn start,
            // heal your summon 3") is class-only + bounded, like the card-level op. amount>=1 checked below.
            if (t.Op == "heal_summon")
            {
                if (!allowCustomOrbs)
                    return "a trigger heal_summon is only valid on a class card (it heals this class's summon).";
                if (t.Amount > HealSummonMaxAmount)
                    return $"a trigger heal_summon 'amount' may be at most {HealSummonMaxAmount}; got {t.Amount}.";
            }
            if (t.Op == "shield_summon")
            {
                if (!allowCustomOrbs)
                    return "a trigger shield_summon is only valid on a class card (it shields this class's summon).";
                if (t.Amount > ShieldSummonMaxAmount)
                    return $"a trigger shield_summon 'amount' may be at most {ShieldSummonMaxAmount}; got {t.Amount}.";
            }
            // Phase V (gap #18): a trigger-payload upgrade_card is `random` ONLY — `all` in a repeating payload is
            // degenerate (it would upgrade the whole hand every turn) and `choose` (Phase X) would spam the pick UI
            // every turn. Both stay legal at card level.
            if (t.Op == "upgrade_card")
            {
                if (t.Cards != "random")
                    return $"a trigger upgrade_card must be 'cards':'random' ('all'/'choose' are card-only — degenerate in a repeating payload); got '{t.Cards}'.";
            }
            // Phase AP (v46): a payload discard stays the choiceless form (`cards` absent or "random") — a repeating pick
            // UI every turn is the same footgun as a payload upgrade_card choose. TriggerRunner always calls DiscardRandom.
            else if (t.Op == "discard")
            {
                if (t.Cards != null && t.Cards != "random")
                    return $"a trigger discard must be random ('cards':'choose' is card-only — a repeating pick UI); got '{t.Cards}'.";
            }
            else if (t.Cards != null)
                return $"'cards' only applies to upgrade_card/discard (trigger effect '{t.Op}').";
            if (t.StatusCard != null)
                return $"'card' only applies to the card-level add_status_card (trigger effect '{t.Op}').";
            if (AmountOps.Contains(t.Op) && t.Amount < 1)
                return $"trigger effect '{t.Op}' needs amount >= 1.";
            if (t.When != null)
                return "a trigger's inner effects can't carry their own 'when' (put the condition on the add_trigger itself).";
            if (t.Trigger != null || t.Triggered != null)
                return "triggers can't nest (no add_trigger inside a trigger).";
            if (t.OncePerTurn)
                return "'once_per_turn' goes on the add_trigger op, not on a payload effect.";
            if (t.OncePerCombat) // Phase AK (v41)
                return "'once_per_combat' goes on the add_trigger op, not on a payload effect.";
            // (Phase AL, v42: multi-hit inside a trigger is legal on damage/summon_attack — see the hits rule above.)
        }
        if (e.When != null && (e.When.Kind == "target_has_status" || e.When.Kind == "retained_last_turn"
                               || Conditions.TargetKinds.Contains(e.When.Kind))) // Phase AM (v43): the chosen-target reads
            return $"a trigger's 'when' can't use {e.When.Kind} (a trigger fires with no card/target).";
        return null;
    }

    /// <summary>The DynamicVar key an effect declares in <see cref="DataCard"/> (null = declares none). Two
    /// effects with the same key would make the game's DynamicVarSet ctor throw — see the dup check above.
    /// damage/block collapse to one key each (normal or scale:x) since the attack/block path reads one var.</summary>
    /// <summary>Phase AO (v45): the cost_shift sentence — "Your Attacks cost 1 less this turn." / "Your next Skill costs 2
    /// less this turn." / "Your next 2 cards cost 1 less this combat." Literal numbers (no DynamicVar, like forge /
    /// balance_step). Byte-lockstep with cardgen._cost_shift_sentence.</summary>
    private static string CostShiftSentence(EffectSpec e)
    {
        string plural = e.CardKind switch { "attack" => "Attacks", "skill" => "Skills", "power" => "Powers", _ => "cards" };
        string single = e.CardKind switch { "attack" => "Attack", "skill" => "Skill", "power" => "Power", _ => "card" };
        string life = e.Scope == "combat" ? "this combat" : "this turn";
        int amt = Math.Max(1, e.Amount);
        if (e.Count == 1) return $"Your next {single} costs {amt} less {life}.";
        if (e.Count > 1) return $"Your next {e.Count} {plural} cost {amt} less {life}.";
        return $"Your {plural} cost {amt} less {life}.";
    }

    /// <summary>Phase AX (v53): the var key of the i-th effect. apply_status is occurrence-numbered, so a card's
    /// SECOND (gated) Weak declares 'status:weak:2' instead of colliding with the first.</summary>
    private static string? VarKey(EffectSpec[] effects, int i)
    {
        var e = effects[i];
        if (e.Op != "apply_status") return VarKey(e);
        int occ = StatusOccurrence(effects, i);
        return "status:" + e.Status + (occ > 0 ? ":" + (occ + 1) : "");
    }

    private static string? VarKey(EffectSpec e) => e.Op switch
    {
        "damage"       => "Damage",
        "block"        => "Block",
        "draw"         => e.IsScaled ? null : "Cards", // a scaled draw declares no var (resolved at play time)
        "gain_energy"  => "Energy",
        "heal"         => "Heal",
        "lose_hp"      => "Loss",
        "gain_max_hp"  => "MaxHp", // Phase AN (v44): the Max HP gain (a real MaxHpVar, upgrade-aware in card text)
        "discard"      => "Discard", // Phase R (gap #17): the random-discard count (upgrade-aware in card text)
        "scry"         => "Scry", // Phase AA (gap #17 R-2): the top-of-draw look count (upgrade-aware in card text)
        "apply_status" => "status:" + e.Status,
        _ => null, // channel_orb / evoke / gain_orb_slot / exhaust / innate / retain / ethereal declare no var
    };

    /// <summary>Phase AX (v53): the DISPLAY name of a base status — the word the card text prints and the stem the
    /// second (gated) copy's suffixed var is built from ("Weak" -> "Weak2"). Shared by <see cref="Describe"/> and
    /// <see cref="DataCard"/>; lockstep with cardgen.STATUS_NAME.</summary>
    internal static string StatusDisplay(string? status) => status switch
    {
        "vulnerable" => "Vulnerable", "weak" => "Weak", "frail" => "Frail", "poison" => "Poison",
        "strength" => "Strength", "dexterity" => "Dexterity", "thorns" => "Thorns",
        "regen" => "Regen", "metallicize" => "Metallicize", "artifact" => "Artifact",
        "buffer" => "Buffer", "intangible" => "Intangible", "ritual" => "Ritual", "blur" => "Blur",
        "temp_strength" => "Strength", "temp_dexterity" => "Dexterity", "barricade" => "Barricade",
        "focus" => "Focus",
        "temp_thorns" => "Thorns", "temp_focus" => "Focus", // Phase AN (v44): worded like the temp stats
        _ => status ?? "",
    };

    /// <summary>Phase AX (v53): the DynamicVar name the i-th apply_status declares — the status's display name, plus
    /// an occurrence suffix for the gated second copy ("Weak2"). Mirrors validator._status_var_name.</summary>
    internal static string StatusVarName(EffectSpec[] effects, int i)
    {
        int occ = StatusOccurrence(effects, i);
        return StatusDisplay(effects[i].Status) + (occ > 0 ? (occ + 1).ToString() : "");
    }

    /// <summary>The human phrase for a non-X scalar (F5), e.g. "the cards you retained". Lockstep with cardgen.py.</summary>
    private static string ScalePhrase(string? scale) => scale switch
    {
        "cards_in_hand"            => "the cards in your hand",
        "cards_retained"           => "the cards you retained",
        "unspent_energy_last_turn" => "your unspent energy last turn",
        "target_debuff_count"      => "the debuffs on the target",     // Phase P (gap #22)
        "damage_dealt_unblocked"   => "the unblocked damage dealt",    // Phase P (gap #21, lifesteal heal)
        "block"                    => "your Block",                                    // Phase AM (v43)
        "hp_lost_this_turn"        => "the HP you have lost this turn",                // Phase AM (v43)
        "draw_pile_count"          => "the cards in your draw pile",                   // Phase AM (v43)
        "energy"                   => "your energy",                                   // Phase AM (v43)
        "plays_this_combat"        => "the cards you have played this combat",         // Phase AM (v43)
        _ => "X",
    };

    // Synthesize card text from effects + target (must match cardgen.py describe()). STS2 AoE cards spell out
    // "to ALL enemies" in their text — the game does NOT auto-append it — so the target must inform the wording.
    private static string Describe(EffectSpec[] effects, TargetType target)
    {
        bool aoe = target == TargetType.AllEnemies;
        string dmgSuffix = target switch
        {
            TargetType.AllEnemies => " to ALL enemies",
            TargetType.RandomEnemy => " to a random enemy",
            _ => "",
        };
        var parts = new List<string>(effects.Length);
        foreach (var e in effects)
        {
            int before = parts.Count;
            switch (e.Op)
            {
                case "damage":
                    // Phase AN (v44): an unblockable hit reads "…, ignoring Block." (the clause closes the damage sentence
                    // in every shape; lockstep with cardgen.describe).
                    string ub = e.Unblockable ? ", ignoring Block" : "";
                    if (e.IsScaled)
                        parts.Add(e.Scale == "x"
                            ? $"Deal X damage{dmgSuffix}{ub}."
                            : e.Scale == "forged"
                                ? $"Deal {e.Amount} damage{dmgSuffix}, plus your Forge{ub}."
                                : e.Scale == "tag_cards_owned"
                                    ? $"Deal {e.Amount} damage{dmgSuffix}, plus 1 per '{e.Tag}' card you own{ub}."
                                    : $"Deal damage equal to {ScalePhrase(e.Scale)}{dmgSuffix}{ub}.");
                    else if (e.HasGrow) // Phase U (gap #23): {Damage} shows the CURRENT grown value (calc-var)
                        parts.Add($"Deal {{Damage}} damage{dmgSuffix}{ub}. Grows by {e.Grow} each time it is played this combat.");
                    else
                        parts.Add(e.Hits > 1
                            ? $"Deal {{Damage}} damage {{Hits}} times{dmgSuffix}{ub}."
                            : $"Deal {{Damage}} damage{dmgSuffix}{ub}.");
                    break;
                case "block":       parts.Add(!e.IsScaled ? "Gain {Block} Block."
                                        : e.Scale == "x" ? "Gain X Block."
                                        : e.Scale == "forged" ? $"Gain {e.Amount} Block, plus your Forge."
                                        : e.Scale == "tag_cards_owned" ? $"Gain {e.Amount} Block, plus 1 per '{e.Tag}' card you own."
                                        : $"Gain Block equal to {ScalePhrase(e.Scale)}."); break;
                case "draw":        parts.Add(!e.IsScaled ? "Draw {Cards} card(s)."
                                        : e.Scale == "x" ? "Draw X cards."
                                        : $"Draw cards equal to {ScalePhrase(e.Scale)}."); break;
                case "gain_energy": parts.Add("Gain {Energy} energy."); break;
                case "heal":        parts.Add(e.IsScaled ? $"Heal HP equal to {ScalePhrase(e.Scale)}." : "Heal {Heal} HP."); break;
                case "lose_hp":     parts.Add("Lose {Loss} HP."); break;
                case "gain_max_hp": parts.Add("Gain {MaxHp} Max HP."); break; // Phase AN (v44): the Feed payoff (MaxHpVar)
                case "discard":     parts.Add(e.Cards == "choose" ? "Discard {Discard} card(s) of your choice." // Phase AP (v46): the chosen form
                                                                  : "Discard {Discard} random card(s)."); break; // Phase R (gap #17)
                case "retrieve_card":   parts.Add(RetrieveSentence(e)); break;   // Phase AP (v46): literal (no var), lockstep with cardgen
                case "add_status_card": parts.Add(StatusCardSentence(e)); break; // Phase AP (v46): literal (no var), lockstep with cardgen
                case "scry":        parts.Add("Scry {Scry}. (Look at that many cards from the top of your draw pile and discard any.)"); break; // Phase AA (gap #17 R-2)
                case "exhaust":     parts.Add("Exhaust."); break;
                case "innate":      parts.Add("Innate."); break;
                case "retain":      parts.Add("Retain."); break;
                case "ethereal":    parts.Add("Ethereal."); break;
                case "purge":       parts.Add("Purge. (Removed from your deck for the rest of the run.)"); break; // Phase W (gap #19)
                case "purge_card":  parts.Add("Choose a card in your hand and Purge it. (Removed from your deck for the rest of the run.)"); break; // Phase Z (gap #19 choose)
                case "sacrifice_summon": parts.Add("Sacrifice your summon."); break; // Phase AV (v52): flag-op sentence (byte-lockstep with cardgen.py)
                case "spend_forge": parts.Add($"Spend {Math.Max(1, e.Amount)} Forge."); break; // Phase AX (v53, gap #44): literal (no var), byte-lockstep with cardgen.py
                case "spread_debuffs": parts.Add("Copy the target's debuffs to all other enemies."); break; // Phase AX (v53, gaps #45-#47)
                case "corruption":  parts.Add("Your Skills cost 0."); parts.Add("Your Skills Exhaust when played."); break; // Phase AB (gap #20)
                case "cost_shift":  parts.Add(CostShiftSentence(e)); break; // Phase AO (v45): the discount sentence (literal, no var)
                case "blade_empower": parts.Add($"Your blade deals {Math.Max(2, e.Amount)}x damage this turn."); break; // Phase AF (gap #41)
                case "transform_card": parts.Add($"Transforms into {AddCardName(e.CardId)} for the rest of the run."); break; // Phase AH (gaps #35/#38): target title title-cased from the id (no sibling context here, like add_card)
                case "graft_card":  parts.Add($"Choose a card in your hand. It transforms into {AddCardName(e.CardId)} for the rest of the run."); break; // Phase AI (gap #7): the choose-form transform (target title from the id, like transform_card)
                case "gain_orb_slot": parts.Add($"Gain {e.Amount} orb slot(s)."); break;
                case "forge": parts.Add($"Forge {e.Amount}."); break; // Phase M (gap #36): the keyword sentence
                case "balance_step": parts.Add(BalanceSentence(e, capitalize: true)); break; // Phase S (gap #1)
                case "channel_orb":
                    string orbName = OrbDisplay(e.Orb);
                    int oc = Math.Max(1, e.Amount);
                    parts.Add(oc > 1 ? $"Channel {oc} {orbName} orbs." : $"Channel a {orbName} orb.");
                    break;
                case "evoke":
                    int ec = Math.Max(1, e.Amount);
                    parts.Add(ec > 1 ? $"Evoke {ec} times." : "Evoke your next orb.");
                    break;
                case "apply_custom": // EXPLORE SPIKE
                    parts.Add($"Gain {Math.Max(1, e.Amount)} 🗡️ Sharpen.");
                    break;
                case "summon": // Phase K (true-Osty): summon the class's minion, or grow its Max HP if already out.
                    string mn = OrbDisplay(e.SummonName); // reuse the title-caser used for custom orb names
                    parts.Add(e.Amount >= 1 ? $"Summon a {mn} with {e.Amount} HP." : $"Summon a {mn}.");
                    break;
                case "summon_attack": // Phase K (true-Osty): the class's summon deals the damage (literal, no var).
                    parts.Add(e.Hits > 1
                        ? $"Deal {e.Amount} damage {e.Hits} times with your summon{dmgSuffix}."
                        : $"Deal {e.Amount} damage with your summon{dmgSuffix}.");
                    break;
                case "buff_summon": // Phase K (true-Osty): a self-buff on the class's summon (default Strength).
                    parts.Add($"Your summon gains {Math.Max(1, e.Amount)} {SummonRunner.StatusDisplay(e.Status ?? "strength")}.");
                    break;
                case "heal_summon": // Phase AC (gap #2): heal the class's living summon (literal, no var).
                    parts.Add($"Heal your summon {Math.Max(1, e.Amount)} HP.");
                    break;
                case "shield_summon": // Phase AC (gap #2): grant Block to the class's living summon (literal, no var).
                    parts.Add($"Your summon gains {Math.Max(1, e.Amount)} Block.");
                    break;
                case "summon_spike": // PHASE K SPIKE
                    int sc = Math.Max(1, e.Amount);
                    parts.Add(sc > 1 ? $"Summon {sc} Spike Imps." : "Summon a Spike Imp.");
                    break;
                case "apply_status_custom":
                    // Phase J: no class status-pool context here (no emoji), so wording keys off the card's
                    // TARGET — a self-target card GAINs the (buff) status, an enemy-target card APPLIES the
                    // (debuff). Lockstep with cardgen.describe's apply_status_custom case. (Hand-authored J-1
                    // cards carry explicit text; real per-status emoji in card text is a cosmetic follow-up.)
                    parts.Add(target == TargetType.Self
                        ? $"Gain {Math.Max(1, e.Amount)} {e.StatusName}."
                        : $"Apply {Math.Max(1, e.Amount)} {e.StatusName}{dmgSuffix}."); // AJ: " to a random enemy" too
                    break;
                case "add_trigger":
                    // The trigger sentence WITHOUT its condition; the generic When-weave below appends it (so
                    // card text and the power tooltip stay in lockstep). cardgen.py mirrors this.
                    parts.Add(TriggerSentence(e));
                    break;
                case "add_card":
                    // Phase Q (gap #16): the referenced title is derived from the card_id (title-cased) — no class
                    // context here, exactly like OrbDisplay/summon wording. Lockstep with cardgen.describe().
                    parts.Add(AddCardSentence(e, capitalize: true));
                    break;
                case "summon_blade": // Phase T: no class context here, so a fixed phrase (lockstep with cardgen.py).
                    parts.Add("Put your blade into your hand from anywhere.");
                    break;
                case "upgrade_card": // Phase V (gap #18): combat-scoped hand upgrade (lockstep with cardgen.py).
                    parts.Add(UpgradeSentence(e, capitalize: true));
                    break;
                case "apply_status":
                    string name = StatusDisplay(e.Status); // Phase AX (v53): shared with the suffixed-var stem
                    // Self-buffs are worded "Gain"; debuffs are "Apply"-ed to the target. SelfBuffStatuses is the
                    // single source of truth (shared with EffectRunner) so wording matches actual targeting.
                    bool buff = EffectRunner.SelfBuffStatuses.Contains(e.Status ?? "");
                    parts.Add($"{(buff ? "Gain" : "Apply")} {name}{(buff ? "" : dmgSuffix)}."); // AJ: random_enemy suffix too
                    break;
            }
            // Phase H: weave the condition into the gated effect's sentence ("… if your orbs match.").
            if (e.When != null && parts.Count > before)
            {
                string p = parts[^1];
                string clause = (e.When.Negate ? "unless " : "if ") + Conditions.Phrase(e.When);
                parts[^1] = p.EndsWith(".") ? $"{p[..^1]} {clause}." : $"{p} {clause}";
            }
        }
        return string.Join("\n", parts);
    }

    // --- Phase H3 trigger text (must match cardgen.py) ----------------------------------------------

    /// <summary>The full trigger sentence WITH its fire-time condition — used for the granted power's tooltip
    /// (which doesn't pass through the card-level When-weave). Kept in lockstep with cardgen.py.</summary>
    public static string DescribeTrigger(EffectSpec t)
    {
        string s = TriggerSentence(t);
        if (t.When != null)
        {
            string clause = (t.When.Negate ? "unless " : "if ") + Conditions.Phrase(t.When);
            s = s.EndsWith(".") ? $"{s[..^1]} {clause}." : $"{s} {clause}";
        }
        return s;
    }

    /// <summary>The trigger sentence WITHOUT its condition, e.g. "At the end of your turn, gain 5 Block."</summary>
    private static string TriggerSentence(EffectSpec t)
    {
        // gap #6 "ripen": a one-shot after N turns. turn_start/turn_end are the recurring per-turn forms; the H4
        // reactive kinds are "Whenever …" clauses mirroring the relic hooks.
        string when = t.Trigger switch
        {
            "turn_start"      => "At the start of your turn",
            "ripen"           => t.Amount == 1 ? "After 1 turn" : $"After {t.Amount} turns",
            "on_hp_lost"      => "Whenever you lose HP",
            "on_exhaust"      => "Whenever a card is Exhausted",
            "on_card_played"  => "Whenever you play a card",
            "on_card_drawn"   => "Whenever you draw a card",
            "on_damage_dealt" => "Whenever you deal damage",
            "on_block_gained" => "Whenever you gain Block",
            "attacked"        => "Whenever you are attacked",
            "on_discard"      => "Whenever this card is discarded", // Phase R (gap #17): Reflex — card-latent
            "on_blade_played" => "Whenever you play your blade", // Phase T: Parry analogue (fires on the token blade)
            _                 => "At the end of your turn",
        };
        var frags = (t.Triggered ?? []).Select(TriggerFragment).Where(s => s.Length > 0).ToList();
        // Phase AK (v41): once_per_combat reads "(once per combat)"; it is never combined with once_per_turn.
        string once = t.OncePerCombat ? " (once per combat)" : t.OncePerTurn ? " (once per turn)" : "";
        return $"{when}, {(frags.Count > 0 ? string.Join(", ", frags) : "do nothing")}{once}.";
    }

    /// <summary>Phase AL (v42): the "equal to …" phrase for a REPLACE-semantics payload scalar. cards_retained keeps
    /// its F5 wording ("equal to cards retained"); the two new player reads reuse the card-level ScalePhrase text.
    /// Lockstep with cardgen._trigger_scale_phrase.</summary>
    private static string TriggerScalePhrase(string? scale) => scale switch
    {
        "cards_retained"           => "cards retained",
        "cards_in_hand"            => "the cards in your hand",
        "unspent_energy_last_turn" => "your unspent energy last turn",
        _                          => "X",
    };

    private static string TriggerFragment(EffectSpec e)
    {
        // F5 / Phase AL (v42): a numeric trigger effect may scale to a player read → phrase it instead of a fixed
        // number. `forged` is the ADDITIVE exception ("gain 2 Block, plus your Forge" — the card-level wording).
        bool sc = e.IsScaled && e.Scale != "forged";
        bool fg = e.Scale == "forged";
        string eq = TriggerScalePhrase(e.Scale);
        // H4 (gap #14): a targeted payload effect is worded "… to ALL enemies" for AoE (single-enemy → no suffix,
        // matching the base-card Describe convention). Phase AK (v41): "… to the attacker" for the riposte target.
        string to = e.Target == "all_enemies" ? " to ALL enemies" : e.Target == "attacker" ? " to the attacker" : "";
        return e.Op switch
        {
            "damage"        => e.Target == null ? ""
                                  : sc ? $"deal damage equal to {eq}{to}"
                                  : fg ? $"deal {e.Amount} damage{to}, plus your Forge"
                                  : e.Hits > 1 ? $"deal {e.Amount} damage {e.Hits} times{to}" // Phase AL: multi-hit payload
                                  : $"deal {e.Amount} damage{to}",
            "block"         => sc ? $"gain Block equal to {eq}" : fg ? $"gain {e.Amount} Block, plus your Forge" : $"gain {e.Amount} Block",
            "draw"          => sc ? $"draw cards equal to {eq}" : $"draw {e.Amount} card(s)",
            "gain_energy"   => sc ? $"gain energy equal to {eq}" : $"gain {e.Amount} energy",
            "heal"          => sc ? $"heal HP equal to {eq}" : $"heal {e.Amount} HP",
            "lose_hp"       => sc ? $"lose HP equal to {eq}" : $"lose {e.Amount} HP",
            "gain_orb_slot" => sc ? $"gain orb slots equal to {eq}" : $"gain {e.Amount} orb slot(s)",
            "forge"         => $"Forge {e.Amount}", // Phase M: fixed-amount income ("At the start of your turn, Forge 2.")
            "balance_step"  => BalanceSentence(e, capitalize: false), // Phase S (gap #1): the trigger-income fragment
            "apply_status"  => e.Target != null
                                  ? $"apply {e.Amount} {StatusName(e.Status)}{to}"
                                  : (sc ? $"gain {StatusName(e.Status)} equal to {eq}" : $"gain {e.Amount} {StatusName(e.Status)}"),
            // Phase AL (v42): the class engines as payload fragments (lockstep with cardgen._trigger_fragment). No
            // class context here (same choice as the card-level Describe): a custom status is worded by its name,
            // GAIN when untargeted (the self-buff form) / APPLY when targeted (the debuff form).
            "summon_attack" => e.Hits > 1 ? $"deal {e.Amount} damage {e.Hits} times with your summon{to}"
                                          : $"deal {e.Amount} damage with your summon{to}",
            "buff_summon"   => $"your summon gains {Math.Max(1, e.Amount)} {SummonRunner.StatusDisplay(e.Status ?? "strength")}",
            "apply_status_custom" => e.Target != null ? $"apply {Math.Max(1, e.Amount)} {e.StatusName}{to}"
                                                      : $"gain {Math.Max(1, e.Amount)} {e.StatusName}",
            "channel_orb"   => ChannelFragment(e),
            "evoke"         => Math.Max(1, e.Amount) > 1 ? $"evoke {e.Amount} times" : "evoke your next orb",
            "discard"       => $"discard {e.Amount} random card(s)", // Phase R (gap #17): forced-churn payload
            "add_card"      => AddCardSentence(e, capitalize: false), // Phase Q (gap #16): the compost-loop fragment
            "summon_blade"  => "put your blade into your hand from anywhere", // Phase T: blade-retrieval fragment
            "upgrade_card"  => UpgradeSentence(e, capitalize: false), // Phase V (gap #18): trigger-side upgrade (random only)
            "heal_summon"   => $"heal your summon {e.Amount} HP", // Phase AC (gap #2): the medic-engine fragment
            "shield_summon" => $"your summon gains {e.Amount} Block", // Phase AC (gap #2)
            _ => "",
        };
    }

    /// <summary>Phase V (gap #18): the upgrade_card sentence/fragment. <paramref name="capitalize"/> = a card-level
    /// sentence ("Upgrade … ." with a period); false = a trigger-payload fragment ("upgrade …", no period). The
    /// upgrade is COMBAT-SCOPED (the trailing "for the rest of this combat" says so; hand cards are deck clones).
    /// An absent/unknown scope reads as `random` (matching the engine default). Lockstep with cardgen.py
    /// (describe's upgrade_card case + _trigger_fragment / _upgrade_sentence).</summary>
    private static string UpgradeSentence(EffectSpec e, bool capitalize)
    {
        string verb = capitalize ? "Upgrade" : "upgrade";
        string what = e.Cards switch { "all" => "ALL cards", "choose" => "a card of your choice", _ => "a random card" };
        string body = $"{verb} {what} in your hand for the rest of this combat";
        return capitalize ? body + "." : body;
    }

    /// <summary>Phase Q (gap #16): the add_card sentence/fragment. <paramref name="capitalize"/> = a card-level
    /// sentence ("Add … ." with a period); false = a trigger-payload fragment ("add …", no period). The referenced
    /// title is title-cased from the card_id (no sibling-name context here — same choice as OrbDisplay). Lockstep
    /// with cardgen.py (describe's add_card case + _trigger_fragment).</summary>
    private static string AddCardSentence(EffectSpec e, bool capitalize)
    {
        string verb = capitalize ? "Add" : "add";
        string name = AddCardName(e.CardId);
        string pile = PilePhrase(e.Pile);
        int n = Math.Max(1, e.Amount);
        string body = n > 1 ? $"{verb} {n} copies of {name} to your {pile}"
                            : $"{verb} a copy of {name} to your {pile}";
        return capitalize ? body + "." : body;
    }

    /// <summary>Phase S (gap #1): the balance_step sentence/fragment. <paramref name="capitalize"/> = a card-level
    /// sentence ("Shift N toward the Dark." with a period); false = a trigger-payload fragment ("shift N toward the
    /// Dark", no period). An unknown/absent pole reads as Dark (matching the engine's default). Lockstep with
    /// cardgen.py (describe's balance_step case + _trigger_fragment).</summary>
    private static string BalanceSentence(EffectSpec e, bool capitalize)
    {
        string verb = capitalize ? "Shift" : "shift";
        string pole = e.Pole == "light" ? "Light" : "Dark";
        int n = Math.Max(1, e.Amount);
        string body = $"{verb} {n} toward the {pole}";
        return capitalize ? body + "." : body;
    }

    /// <summary>Display title for an add_card's referenced card: the snake_case id, title-cased (mirrors
    /// OrbDisplay's custom-name path and cardgen's title-casing).</summary>
    private static string AddCardName(string? cardId) =>
        string.IsNullOrWhiteSpace(cardId) ? "a card"
            : System.Globalization.CultureInfo.InvariantCulture.TextInfo.ToTitleCase(cardId.Replace('_', ' '));

    /// <summary>Phase AP (v46): the retrieve_card sentence — "Return a random card from your discard pile to your hand." /
    /// "Return 2 cards of your choice from your exhaust pile to your hand." Literal numbers (no DynamicVar, like add_card);
    /// an absent/unknown pile reads as the discard pile and an absent mode as random (the engine defaults). Lockstep with
    /// cardgen._retrieve_sentence.</summary>
    private static string RetrieveSentence(EffectSpec e)
    {
        int n = Math.Max(1, e.Amount);
        string pile = e.Pile == "exhaust" ? "exhaust pile" : "discard pile";
        string what = e.Cards == "choose"
            ? (n > 1 ? $"{n} cards of your choice" : "a card of your choice")
            : (n > 1 ? $"{n} random cards" : "a random card");
        return $"Return {what} from your {pile} to your hand.";
    }

    /// <summary>Phase AP (v46): the add_status_card sentence — "Add a Wound to your discard pile." / "Add 2 Wounds to your
    /// hand." / "Add 2 Dazed to your draw pile." (Dazed is its own plural; Wound/Burn take an s). Literal numbers (no
    /// DynamicVar). An unknown kind reads as Wound (the engine default). Lockstep with cardgen._status_card_sentence.</summary>
    private static string StatusCardSentence(EffectSpec e)
    {
        int n = Math.Max(1, e.Amount);
        string name = StatusCardName(e.StatusCard);
        string what = n > 1 ? $"{n} {(name == "Dazed" ? name : name + "s")}" : $"a {name}";
        return $"Add {what} to your {PilePhrase(e.Pile)}.";
    }

    /// <summary>Phase AP (v46): the display name of a base-game Status card kind. Lockstep with cardgen.STATUS_CARD_NAME.</summary>
    internal static string StatusCardName(string? kind) => kind switch
    {
        "dazed" => "Dazed",
        "burn"  => "Burn",
        _       => "Wound",
    };

    /// <summary>The human phrase for an add_card / add_status_card destination pile, or a retrieve_card source pile
    /// (Phase AP adds the exhaust pile). Lockstep with cardgen._pile_phrase.</summary>
    private static string PilePhrase(string? pile) => pile switch
    {
        "discard" => "discard pile",
        "draw"    => "draw pile",
        "exhaust" => "exhaust pile", // Phase AP (v46): retrieve_card's second source
        _         => "hand",
    };

    private static string ChannelFragment(EffectSpec e)
    {
        string name = OrbDisplay(e.Orb);
        int oc = Math.Max(1, e.Amount);
        return oc > 1 ? $"channel {oc} {name} orbs" : $"channel a {name} orb";
    }

    /// <summary>Display name for an orb in card text. Base orbs title-cased; <c>random</c> stays lowercase; a
    /// custom orb name (Phase I, declared in a class orb_pool) is title-cased from its lowercase id. Mirrors
    /// cardgen.py <c>_orb_display</c>.</summary>
    private static string OrbDisplay(string? orb) => orb switch
    {
        "lightning" => "Lightning", "frost" => "Frost", "dark" => "Dark", "random" => "random",
        null or "" => "orb",
        _ => System.Globalization.CultureInfo.InvariantCulture.TextInfo.ToTitleCase(orb.Replace('_', ' ')),
    };

    /// <summary>Display name for a status (mirrors the apply_status case in Describe and cardgen.STATUS_NAME).</summary>
    private static string StatusName(string? status) => status switch
    {
        "vulnerable" => "Vulnerable", "weak" => "Weak", "frail" => "Frail", "poison" => "Poison",
        "strength" => "Strength", "dexterity" => "Dexterity", "thorns" => "Thorns", "regen" => "Regen",
        "metallicize" => "Metallicize", "artifact" => "Artifact", "buffer" => "Buffer",
        "intangible" => "Intangible", "ritual" => "Ritual", "blur" => "Blur",
        "temp_strength" => "Strength", "temp_dexterity" => "Dexterity", "barricade" => "Barricade",
        "focus" => "Focus",
        "temp_thorns" => "Thorns", "temp_focus" => "Focus", // Phase AN (v44)
        _ => status ?? "",
    };

    private static string Str(Godot.Collections.Dictionary d, string key, string fallback = "") =>
        d.ContainsKey(key) ? d[key].AsString() : fallback;

    private static int Int(Godot.Collections.Dictionary d, string key, int fallback = 0) =>
        d.ContainsKey(key) ? d[key].AsInt32() : fallback;
}
