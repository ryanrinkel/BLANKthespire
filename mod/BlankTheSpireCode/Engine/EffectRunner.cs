using System.Linq;
using BaseLib.Abstracts;
using BaseLib.Extensions;
using BaseLib.Utils;
using BlankTheSpire.BlankTheSpireCode.Powers;
using MegaCrit.Sts2.Core.CardSelection; // Phase Z (gap #19 choose): CardSelectorPrefs for CardSelectCmd.FromHand
using MegaCrit.Sts2.Core.Combat;
using MegaCrit.Sts2.Core.Commands;
using MegaCrit.Sts2.Core.Entities.Cards;
using MegaCrit.Sts2.Core.Entities.Creatures;
using MegaCrit.Sts2.Core.Entities.Players;
using MegaCrit.Sts2.Core.GameActions.Multiplayer;
using MegaCrit.Sts2.Core.Models;
using MegaCrit.Sts2.Core.Models.Orbs;
using MegaCrit.Sts2.Core.Models.Powers;
using MegaCrit.Sts2.Core.Nodes.CommonUi; // Phase V (gap #18): CardPreviewStyle for CardCmd.Upgrade
using MegaCrit.Sts2.Core.ValueProps;

namespace BlankTheSpire.BlankTheSpireCode.Engine;

/// <summary>
/// THE interpreter. The C# port of the prototype's core/effects/Effect.gd op-dispatch table.
/// One hand-written switch maps each vocabulary op onto STS2 actions (via BaseLib's CommonActions or
/// the raw Cmd builders). Declaration (turning ops into DynamicVars so tooltips/previews/upgrades work)
/// lives in <see cref="DataCard"/> because the With* builders are protected; execution lives here.
///
/// Vocab v3: damage, block, draw, apply_status, gain_energy, lose_hp, heal, exhaust, innate, retain,
/// ethereal. Statuses: vulnerable/weak/frail/poison (debuffs on the target) + strength/dexterity/thorns/
/// regen/metallicize/artifact/buffer/intangible/ritual/blur/temp_strength/temp_dexterity/barricade
/// (self-buffs — see <see cref="SelfBuffStatuses"/>). damage/block/draw/apply_status read the card's canonical
/// DynamicVar via CommonActions (already upgrade-aware). The simple scalar ops below have no CommonActions
/// helper, so we compute the amount from the spec + IsUpgraded (mirrors the var-upgrade the others get).
/// Multi-instance / state-scaled ops (multi/from_state/conditional) come later via named vars.
/// </summary>
public static class EffectRunner
{
    /// <summary>Per-var upgrade delta = (upgraded amount - base amount) for the i-th effect, else 0.</summary>
    public static int UpgradeDelta(CardSpec spec, int i) =>
        spec.Upgrade != null && i < spec.Upgrade.Length
            ? spec.Upgrade[i].Amount - spec.Effects[i].Amount
            : 0;

    /// <summary>Per-effect hit-count upgrade delta = (upgraded hits - base hits) for the i-th effect, else 0.
    /// Lets an upgrade raise a multi-hit attack's hit count (e.g. 3→4 times).</summary>
    public static int HitsUpgradeDelta(CardSpec spec, int i) =>
        spec.Upgrade != null && i < spec.Upgrade.Length
            ? spec.Upgrade[i].Hits - spec.Effects[i].Hits
            : 0;

    public static async Task Execute(CardSpec spec, ConstructedCardModel card, PlayerChoiceContext ctx, CardPlay play)
    {
        // Sprite spike: base-game cards fire their own Cast/PowerUp animation cue inside each Use(); data
        // cards must do the same or non-attack plays are motionless. Attacks are covered — CardAttack's
        // AttackCommand fires "Attack" itself — so cue only cards with no damage op (the small awaited
        // delay is the same pacing beat base cards take).
        if (!spec.Effects.Any(e => e.Op == "damage") && card.Owner?.Creature != null)
        {
            bool isPower = card.Type == CardType.Power;
            await CreatureCmd.TriggerAnim(card.Owner.Creature, isPower ? "PowerUp" : "Cast",
                isPower ? card.Owner.Character.PowerUpAnimDelay : card.Owner.Character.CastAnimDelay);
        }
        // Phase P (gap #21): running total of UNBLOCKED damage this card has dealt so far this play, so a later
        // damage_dealt_unblocked heal (lifesteal) heals exactly what got through the enemy's Block. Accumulates
        // across multi-hit and AoE (every DamageResult from each damage effect's attack).
        int unblockedDealt = 0;
        for (int i = 0; i < spec.Effects.Length; i++)
        {
            var e = spec.Effects[i];
            // Phase H: a gated effect runs only when its condition holds (the effect is still declared/shown).
            // EXCEPTION: add_trigger's When is the granted power's FIRE-time gate, not a play-time gate — the
            // power is always granted, and it re-evaluates When each turn (see TriggerRunner), so don't skip here.
            if (e.Op != "add_trigger" && e.When != null)
            {
                bool gateOpen = Conditions.Evaluate(e.When, card, ctx, play);
                // Phase AD (gap #12): log BOTH branches of an hp_lost_ge gate at play time (the smoke's
                // both-branches proof — gate OPEN grants the bonus, gate closed skips it). Play-time only
                // (Execute is the OnPlay path), so no tooltip-preview spam.
                if (e.When.Kind == "hp_lost_ge")
                    MainFile.Logger.Info($"[AD] hp_lost_ge gate {(gateOpen ? "OPEN" : "closed")} " +
                                         $"(lost {HpLossTracker.HpLostThisTurn(card.Owner)} this turn, need {e.When.Value}).");
                // Phase AM (v43): log both branches of the four new gates with the live read they compared against.
                if (PhaseAmConditions.Contains(e.When.Kind))
                    MainFile.Logger.Info($"[AM] {e.When.Kind} gate {(gateOpen ? "OPEN" : "closed")}{(e.When.Negate ? " (negated)" : "")} " +
                                         $"({PhaseAmConditionRead(e.When, card, play)}; need {e.When.Value}).");
                if (!gateOpen) continue;
            }
            // The card's vars (read by CommonActions) already carry the upgrade; for the scalar ops we
            // replicate that by adding the positional upgrade delta when this instance is upgraded.
            int amt = e.Amount + (card.IsUpgraded ? UpgradeDelta(spec, i) : 0);
            switch (e.Op)
            {
                case "damage":
                    // Hit count rides a "Hits" DynamicVar (declared by DataCard only when >1), so it both
                    // shows in card text ({Hits}) and upgrades. CardAttack deals the card's Damage var per hit.
                    int hits = card.DynamicVars.TryGetValue("Hits", out var hv) ? (int)hv.BaseValue : 1;
                    if (e.Scale == "forged") // Phase M smoke logging: prove the additive payoff resolves + grows
                        MainFile.Logger.Info($"[M] forged payoff: damage base {amt} + Forge {ForgeStacks(card.Owner)}.");
                    if (e.Scale == "forged") // Phase AF (gap #41): log the empowered blade hit (base+Forge -> ×N) when active
                    {
                        int bm = BladeMultiplier(card);
                        if (bm > 1)
                        {
                            int b = amt + ForgeStacks(card.Owner);
                            MainFile.Logger.Info($"[AF] blade hit: base {b} -> {b * bm} (x{bm}).");
                        }
                    }
                    if (e.Scale == "tag_cards_owned") // Phase AE (gap #25): prove the live tag scan (count varies as piles shift)
                        MainFile.Logger.Info($"[AE] tag_cards_owned('{e.Tag}') = {TagCardsOwned(card.Owner, e.Tag)} (damage base {amt}).");
                    if (PhaseAmScales.Contains(e.Scale ?? "")) // Phase AM (v43): prove the live read at resolution
                        MainFile.Logger.Info($"[AM] scale {e.Scale} -> {ScaleValue(e.Scale, card)} (damage, '{card.Id}').");
                    if (e.HasGrow) // Phase U (gap #23) smoke logging: prove per-play growth (plays so far = count)
                    {
                        int plays = PlaysThisCombat(card);
                        MainFile.Logger.Info($"[U] grow damage: base {amt} + grow {e.Grow}×{plays} = {amt + e.Grow * plays} (play #{plays + 1} of '{card.Id}').");
                    }
                    // Hold the command so we can read its per-hit/per-target DamageResults after it resolves — the
                    // unblocked total feeds a later damage_dealt_unblocked heal (Phase P gap #21, lifesteal).
                    if (card.TargetType == TargetType.RandomEnemy) // Phase AJ smoke: BaseLib rolls a random enemy per hit
                        MainFile.Logger.Info($"[AJ] random_enemy damage x{hits} from '{card.Id}' (BaseLib TargetingRandomOpponents).");
                    if (e.Unblockable) // Phase AN (v44) smoke: the Unblockable prop rides the damage var (BaseLib CardAttack reads .Props)
                        MainFile.Logger.Info($"[AN] unblockable damage x{hits} from '{card.Id}' (target Block {(play?.Target != null ? play.Target.Block.ToString() : "n/a")}; " +
                                             $"props {(card.DynamicVars.ContainsKey("CalculatedDamage") ? card.DynamicVars.CalculatedDamage.Props : card.DynamicVars.Damage.Props)}).");
                    var atk = CommonActions.CardAttack(card, play, hits);
                    await atk.Execute(ctx);
                    // Results is per-hit lists of per-target DamageResults — flatten both to sum every unblocked hit.
                    if (atk.Results != null)
                        foreach (var hitResults in atk.Results)
                            foreach (var r in hitResults) unblockedDealt += (int)r.UnblockedDamage;
                    break;
                case "block":
                    if (e.Scale == "forged")
                        MainFile.Logger.Info($"[M] forged payoff: block base {amt} + Forge {ForgeStacks(card.Owner)}.");
                    if (e.Scale == "tag_cards_owned") // Phase AE (gap #25)
                        MainFile.Logger.Info($"[AE] tag_cards_owned('{e.Tag}') = {TagCardsOwned(card.Owner, e.Tag)} (block base {amt}).");
                    if (PhaseAmScales.Contains(e.Scale ?? "")) // Phase AM (v43)
                        MainFile.Logger.Info($"[AM] scale {e.Scale} -> {ScaleValue(e.Scale, card)} (block, '{card.Id}').");
                    await CommonActions.CardBlock(card, play);
                    break;
                case "draw":
                    // A scaled draw (F5: x / cards_in_hand / cards_retained / unspent_energy_last_turn) has no
                    // fixed Cards var; resolve the live scalar here and draw that many. CommonActions.Draw only
                    // reads a fixed Cards var, so the unscaled path keeps using the card's Cards var as before.
                    if (e.IsScaled)
                    {
                        int n = ResolveScaleAmount(e, card);
                        if (PhaseAmScales.Contains(e.Scale ?? "")) // Phase AM (v43): only `energy` is draw-legal
                            MainFile.Logger.Info($"[AM] scale {e.Scale} -> {n} (draw, '{card.Id}').");
                        await CardPileCmd.Draw(ctx, n, card.Owner);
                    }
                    else await CommonActions.Draw(card, ctx);
                    break;
                case "apply_status":
                    if (card.TargetType == TargetType.RandomEnemy && !SelfBuffStatuses.Contains(e.Status ?? "")) // Phase AJ smoke
                        MainFile.Logger.Info($"[AJ] random_enemy debuff '{e.Status}' from '{card.Id}' (BaseLib GetTargets rolls one enemy).");
                    if (e.Status is "temp_thorns" or "temp_focus") // Phase AN (v44) smoke: the one-turn shells apply (expiry logs from the power)
                        MainFile.Logger.Info($"[AN] {e.Status} +{amt} (this turn only) from '{card.Id}'.");
                    // Phase AX (v53): a card may declare the SAME status twice when the second one is `when`-gated.
                    // The first copy keeps the canonical PowerVar path (CommonActions reads the card's var); the
                    // second declares a SUFFIXED var ("Weak2", see DataCard) that CommonActions can't find, so it
                    // applies with the literal upgrade-aware amount instead — the apply_status_custom card path.
                    if (ForgedCards.StatusOccurrence(spec.Effects, i) > 0)
                    {
                        MainFile.Logger.Info($"[AX] second '{e.Status}' ({ForgedCards.StatusVarName(spec.Effects, i)}) " +
                                             $"+{Math.Max(1, amt)} from '{card.Id}' (gated copy, literal amount).");
                        if (SelfBuffStatuses.Contains(e.Status ?? ""))
                            await RelicApply(e.Status, ctx, card.Owner.Creature, card.Owner.Creature, Math.Max(1, amt));
                        else
                            foreach (var t in CustomStatusTargets(card, play))
                                await RelicApply(e.Status, ctx, t, card.Owner.Creature, Math.Max(1, amt));
                    }
                    else await ApplyStatus(e.Status, card, ctx, play);
                    break;
                case "gain_energy":
                    await PlayerCmd.GainEnergy(amt, card.Owner);
                    break;
                case "heal":
                    // Phase P (gap #21): a damage_dealt_unblocked heal lifesteals the unblocked damage this card
                    // already dealt this play (0 if fully blocked — skip so no empty heal number logs); otherwise
                    // the fixed, upgrade-aware Heal amount.
                    int healAmt = e.Scale == "damage_dealt_unblocked" ? unblockedDealt : amt;
                    if (healAmt > 0) await CreatureCmd.Heal(card.Owner.Creature, healAmt, true);
                    break;
                case "lose_hp":
                    // Pure HP loss: Unblockable (ignores Block); the CardModel overload takes no dealer,
                    // so the player's Strength does not scale self-damage.
                    await CreatureCmd.Damage(ctx, card.Owner.Creature, amt, ValueProp.Unblockable, card);
                    break;
                case "gain_max_hp":
                {
                    // Phase AN (v44): the base-game Feed payoff — CreatureCmd.GainMaxHp raises Max HP by amt AND heals
                    // the gained amount (verified in the decompiled CreatureCmd: SetMaxHp, then Heal(num)). The amount
                    // is the upgrade-aware {MaxHp} var (a real MaxHpVar on the card). Card-only; capped 1..5 by Validate.
                    int before = card.Owner.Creature.MaxHp;
                    await CreatureCmd.GainMaxHp(card.Owner.Creature, amt);
                    MainFile.Logger.Info($"[AN] gain_max_hp +{amt}: Max HP {before} -> {card.Owner.Creature.MaxHp} (HP now {card.Owner.Creature.CurrentHp}) ('{card.Id}').");
                    break;
                }
                case "forge":
                    // Phase M (gap #36): stoke the player-level Forge counter (a stacking power). The payoff
                    // is a damage/block effect with scale:"forged", which ADDS the stacks to its printed amount.
                    // Phase T: Stoke also SUMMONS the class blade to hand on the first Forge of combat.
                    await ForgedForgePower.Stoke(ctx, card.Owner, Math.Max(1, amt));
                    MainFile.Logger.Info($"[M] forge +{Math.Max(1, amt)} (card) -> Forge {ForgeStacks(card.Owner)}.");
                    break;
                case "spend_forge":
                {
                    // Phase AX (v53, gap #44): CONSUME the per-combat Forge counter as this card's price (the
                    // cash-out half of the ramp `forge` builds). Spending more than you hold just empties it — a
                    // harmless no-op at 0, so an ungated card is weak rather than broken (gate it with
                    // when:forged_ge to make it honest). The payoff is the rest of the effect list.
                    int have = ForgeStacks(card.Owner);
                    int spent = ForgedForgePower.Spend(card.Owner, Math.Max(1, amt));
                    MainFile.Logger.Info($"[AX] spend_forge {Math.Max(1, amt)} (had {have}, spent {spent}) -> Forge {ForgeStacks(card.Owner)} ('{card.Id}').");
                    break;
                }
                case "spread_debuffs":
                {
                    // Phase AX (v53, gaps #45-#47): the CONTAGION payoff — copy every debuff on the struck target
                    // (Vulnerable / Weak / Frail / Poison, at their live stack counts) onto every OTHER living
                    // enemy. Single-enemy cards only (validator-gated), so play.Target is the source; no other
                    // enemy / an undebuffed target is a harmless no-op.
                    await SpreadDebuffs(card, ctx, play);
                    break;
                }
                case "balance_step":
                    // Phase S (gap #1): move the signed Balance gauge toward a pole (light/dark). Shared executor
                    // owns the arithmetic + display; the light_ge/dark_ge/centered conditions read it, and the gauge
                    // bites at |8| (see ForgedBalancePower). Amount is the step size (magnitude), not upgrade-scaled.
                    await ForgedBalancePower.BalanceStep(ctx, card.Owner, e.Pole, Math.Max(1, amt));
                    break;
                case "blade_empower":
                    // Phase AF (gap #41): ×N multiplier on the forged blade for ONE turn (a burst spike). Applies a
                    // one-turn power (refresh, not stack); the blade token's scale:"forged" calc reads it (BladeMultiplier
                    // + DataCard.BonusFor). Forge-class only + card-only (generation-gated); a class with no blade =
                    // harmless (the multiplier reads on nothing). amt is the multiplier (2..3, upgrade-aware).
                    await ForgedBladeEmpowerPower.ApplyOrRefresh(ctx, card.Owner, amt);
                    break;
                case "corruption":
                    // Phase AB (gap #20): grant the Corruption power — your Skills cost 0 and Exhaust when played.
                    // Binary per-combat power (Single); the two base-game hooks (cost + result-pile) live on the
                    // power itself, so there is nothing to run per-Skill here (see ForgedCorruptionPower).
                    await ForgedCorruptionPower.Apply(ctx, card.Owner);
                    MainFile.Logger.Info("[AB] corruption power applied.");
                    break;
                case "cost_shift":
                    // Phase AO (v45): add a card-type-scoped discount to the owner's Cost Shift power (ONE power, a list
                    // of live entries — see ForgedCostShiftPower). amt is the discount (1..2, upgrade-aware); the card
                    // itself is passed as the granter so a "next Skill costs less" Skill never spends its own use.
                    await ForgedCostShiftPower.Add(ctx, card.Owner, e.CardKind, amt, e.Scope, e.Count, spec.Id, card);
                    break;
                case "exhaust":
                case "innate":
                case "retain":
                case "ethereal":
                    // Card-keyword ops: declared as a CardKeyword at declaration time (the game applies the
                    // keyword behavior — exhaust-on-play, opening hand, retain, etc.); nothing to run here.
                    break;
                case "purge":
                    // Phase W (gap #19): deck-thinning. The DataCard pile-type override already sends this played
                    // card to NO combat pile (PileType.None) so it vanishes for the rest of THIS combat. Here we make
                    // it RUN-permanent: the played card is a per-combat clone whose DeckVersion points at its run-deck
                    // original (Player.PopulateCombatState → CloneCard sets DeckVersion), so we remove THAT from the
                    // run deck. A GENERATED copy (add_card) has no DeckVersion → the run deck is untouched (combat
                    // vanish is enough). Guard on Deck-pile membership: RemoveFromDeck throws on a non-Deck card, and a
                    // second clone referencing an already-removed original would otherwise fault. showPreview:false —
                    // the removal tween needs the run UI (absent under AutoSlay/headless) and is cosmetic.
                    if (card.DeckVersion is { } deckCard && deckCard.Pile?.Type == PileType.Deck)
                    {
                        await CardPileCmd.RemoveFromDeck(deckCard, showPreview: false);
                        MainFile.Logger.Info($"[W] purge -> removed '{spec.Id}' from the run deck.");
                    }
                    else
                        MainFile.Logger.Info($"[W] purge -> '{spec.Id}' not in run deck (generated copy / token) — combat-vanish only.");
                    break;
                case "purge_card":
                    // Phase Z (gap #19 choose): the player PICKS one card in HAND and purges it — run-permanent
                    // deck-thinning at a target of your choosing (the choose form of Phase W's self-purge flag).
                    // Opens the base-game hand picker (CardSelectCmd.FromHand — the Brand "choose a card" surface),
                    // then removes the chosen card from the run deck (via its DeckVersion, reusing W's guard) AND from
                    // combat this fight. Under AutoSlay the AutoSlayCardSelector auto-picks (no hang).
                    await PurgeChoose(ctx, card.Owner, card);
                    break;
                case "transform_card":
                    // Phase AH (gaps #35/#38): the played card PERMANENTLY becomes e.CardId (a same-class card) for
                    // the rest of the run. Two halves (spike AH-0 proved both): (1) the RUN-DECK original is swapped
                    // via CardCmd.Transform(DeckVersion, replacement, None) under the purge DeckVersion guard — so it
                    // is the new card in every subsequent combat and the old card never returns; (2) this combat's
                    // in-hand CLONE is transformed too, so the change is felt immediately (a self-transform card is
                    // already leaving play, but transforming the hand clone keeps any OTHER copies in hand current).
                    // A GENERATED copy (add_card token) has DeckVersion == null → deck half is skipped, combat-only.
                    await TransformCard(e, card, ctx);
                    break;
                case "graft_card":
                    // Phase AI (gap #7): GRAFT — the choose form of transform_card (as purge_card is the choose form
                    // of purge). The player PICKS one card in HAND (CardSelectCmd.FromHand — the Brand/Begone "choose a
                    // card" surface) and that PICKED card PERMANENTLY becomes e.CardId (a same-class card) for the rest
                    // of the run: the run-deck original is swapped via CardCmd.Transform(DeckVersion, replacement, None)
                    // AND the picked hand clone is transformed now, so the change is felt this combat. A generated/token
                    // copy (null DeckVersion) skips the deck half (combat-only). Empty hand / no selection is a no-op;
                    // under AutoSlay the AutoSlayCardSelector auto-picks (no hang).
                    await GraftCard(e, card, ctx);
                    break;
                // --- ORBS (Phase G). In the execution path; NOT YET in the LLM contract (opened in G3). ---
                case "gain_orb_slot":
                    await OrbCmd.AddSlots(card.Owner, amt); // per-combat slots (like Capacitor)
                    break;
                case "channel_orb":
                {
                    // Channel max(1, amount) orbs: canonical model → mutable instance → channel. "random" rolls
                    // independently per orb (so a multi-channel "pull" can come up matched — the slot machine).
                    int count = Math.Max(1, amt);
                    // Phase I: a forged-orb class card resolves the orb name against ITS class's pool (base or custom),
                    // and "random" rolls only within that pool (shared with the relic channel_orb op). Non-orb-class
                    // cards keep the literal base lightning/frost/dark (+ random-among-base) behaviour unchanged.
                    if (card is IForgedOrbHost oh && ForgedCharacters.IsOrbClass(oh.OrbClass))
                        await ChannelForgedOrbs(oh.OrbClass, e.Orb, count, card.Owner, ctx);
                    else
                        for (int n = 0; n < count; n++)
                        {
                            Type orbType = e.Orb == "random" ? RandomOrbType(card) : OrbTypeFor(e.Orb);
                            await OrbCmd.Channel(ctx, ((OrbModel)ModelDb.Get(orbType)).ToMutable(0), card.Owner);
                        }
                    break;
                }
                case "evoke":
                {
                    // Evoke max(1, amount) of the oldest orb(s).
                    int count = Math.Max(1, amt);
                    for (int n = 0; n < count; n++)
                        await OrbCmd.EvokeNext(ctx, card.Owner, dequeue: true);
                    break;
                }
                case "add_trigger":
                    // Phase H3: grant an ongoing power that runs e.Triggered at turn end/start. The power's
                    // behaviour is bound to a compiled type per card slot, so the slot leaf (which knows that
                    // type) does the apply. Baked/non-forged cards can't host triggers (validator-gated).
                    // Phase R (gap #17): on_discard is CARD-LATENT (Reflex) — it grants NO power on play; its
                    // payload fires when the card is discarded by ANY effect, through the game's own
                    // Hook.AfterCardDiscarded (Phase AU, v51 — DataCard.AfterCardDiscarded → FireOnDiscard).
                    if (e.Trigger != "on_discard" && card is IForgedTriggerHost host)
                        await host.ApplyTrigger(ctx, card.Owner);
                    break;
                case "discard":
                    // Phase R (gap #17): discard `amt` RANDOM cards from hand; each discarded card's on_discard
                    // payload fires off the game's AfterCardDiscarded hook (AU) — effect-driven, so turn-end
                    // cleanup (CardPileCmd.Add + Hook.AfterFlush) still never triggers it.
                    // Phase AP (v46): `cards:"choose"` opens the base-game hand picker instead (the player picks which
                    // cards to pitch — the true discard-fuel feel); under AutoSlay the selector auto-picks (no hang).
                    if (e.Cards == "choose")
                        await DiscardChoose(amt, ctx, card.Owner, card);
                    else
                        await DiscardRandom(amt, card.Owner, ctx);
                    break;
                case "retrieve_card":
                    // Phase AP (v46): return `amt` card(s) from the discard/exhaust pile to hand — random (the Exhume-
                    // roulette) or the player's pick (CardSelectCmd.FromCombatPile, the Headbutt surface). Status/Curse
                    // cards are never offered (a random recursion pulling Wounds is anti-fun). Empty pile → no-op.
                    await RetrieveCards(e, amt, ctx, card.Owner);
                    break;
                case "add_status_card":
                    // Phase AP (v46): generate `amt` base-game Status cards (Dazed/Wound/Burn) into a pile — the
                    // self-drawback of an over-statted card (Wild Strike / Power Through / Overclock). Combat-transient
                    // (AddGeneratedCardToCombat), exactly like add_card copies.
                    await AddStatusCards(e, amt, card.Owner);
                    break;
                case "scry":
                    // Phase AA (gap #17 R-2): look at the top `amt` cards of the draw pile and discard any subset
                    // the player picks (CardSelectCmd.FromSimpleGrid); scry-discards feed on_discard like any
                    // effect-discard. Under AutoSlay the AutoSlayCardSelector auto-picks (no hang).
                    await Scry(amt, ctx, card.Owner);
                    break;
                case "apply_custom":
                    // EXPLORE SPIKE (not in the LLM contract): apply the modifier-family custom status to the
                    // player with a literal amount (mirrors TriggerRunner's self-apply path). One hardcoded
                    // power for now (SpikeSharpenPower) to prove Modify* hooks fire on a player-applied power.
                    await Powers.SpikeSharpenPower.Apply(ctx, card.Owner, Math.Max(1, amt));
                    break;
                case "summon_spike":
                    // PHASE K SPIKE (not in the LLM contract): summon max(1, amount) hardcoded pets onto the
                    // player's side via the decompiled OstyCmd/PlayerCmd recipe (PlayerCmd.AddPet<T> sets
                    // PetOwner, adds to Player.Pets, creates the node). Player-side creatures are NEVER driven by
                    // the turn loop (only enemies roll/perform moves), so each pet also gets a hook-power that
                    // makes it attack at the player's turn end (H3-style). Proves the summon path before K-1.
                    for (int s = 0; s < Math.Max(1, amt); s++)
                    {
                        var pet = await PlayerCmd.AddPet<Powers.SpikeImp>(card.Owner);
                        await Powers.SpikeImpAttackPower.Apply(ctx, pet);
                        pet.Died += _ => Powers.ForgedSummon.LayoutPets(card.Owner);
                    }
                    await Powers.ForgedSummonShieldPower.Apply(ctx, card.Owner.Creature);
                    // The game places non-Osty pets ON TOP of the player; re-lay-out to the player's right.
                    Powers.ForgedSummon.LayoutPets(card.Owner);
                    break;
                case "summon":
                    // Phase K (true-Osty): summon the class's minion, or — if it's already on board — raise its
                    // Max HP (the base-game Summon keyword). ONE per class. Class-only, like apply_status_custom /
                    // custom-orb channels. Shared with the relic summon op (Phase L compose). amount = HP.
                    if (card is IForgedSummonHost summonHost && ForgedCharacters.IsSummonClass(summonHost.SummonClass))
                        await SummonForged(summonHost.SummonClass, e.SummonName, amt, card.Owner, ctx);
                    break;
                case "summon_attack":
                    // Phase K (true-Osty): deal damage THROUGH the class's living summon — the pet is the dealer,
                    // so it scales with the summon's Strength (a base-game "Osty attack"). No living summon → no-op.
                    if (card is IForgedSummonHost atkHost && ForgedCharacters.IsSummonClass(atkHost.SummonClass))
                    {
                        var atkPet = FindLivingSummon(card.Owner, atkHost.SummonClass);
                        if (atkPet != null)
                        {
                            var targets = CustomStatusTargets(card, play).Where(c => c.IsAlive).ToList();
                            if (targets.Count > 0)
                            {
                                int hitCount = Math.Max(1, e.Hits + (card.IsUpgraded ? HitsUpgradeDelta(spec, i) : 0));
                                if (hitCount > 1) MainFile.Logger.Info($"[AJ] summon_attack x{hitCount} from '{card.Id}'."); // Phase AJ smoke
                                for (int h = 0; h < hitCount; h++)
                                    await CreatureCmd.Damage(ctx, targets, amt, ValueProp.Move, atkPet);
                            }
                        }
                    }
                    break;
                case "buff_summon":
                    // Phase K (true-Osty): buff the class's living summon (a self-buff on the minion — e.g. Strength
                    // so its summon_attacks hit harder). No living summon → no-op.
                    if (card is IForgedSummonHost buffHost && ForgedCharacters.IsSummonClass(buffHost.SummonClass))
                    {
                        var buffPet = FindLivingSummon(card.Owner, buffHost.SummonClass);
                        if (buffPet != null)
                            await SummonRunner.ApplyBuff(ctx, buffPet, e.Status ?? "strength", amt);
                    }
                    break;
                case "sacrifice_summon":
                    // Phase AV (v52): consume your summon — the front-most living minion dies through the game's own
                    // death path, so its on_death rattle fires. Class-only (like summon); no summon out → logged no-op
                    // and the rest of the card still resolves (the payoff is the REST of this card).
                    if (card is IForgedSummonHost sacHost && ForgedCharacters.IsSummonClass(sacHost.SummonClass))
                        await SacrificeSummon(card.Owner, sacHost.SummonClass);
                    else
                        MainFile.Logger.Info("[AV] sacrifice_summon: not a summon class (no-op).");
                    break;
                case "heal_summon":
                    // Phase AC (gap #2): heal the class's living summon (the selfless "medic" op). No summon out → a
                    // logged no-op (never throws). Amount is upgrade-aware (amt); heal via the same path summon
                    // heal_self moves use (CreatureCmd.Heal).
                    await HealOrShieldSummon(card, "heal_summon", amt);
                    break;
                case "shield_summon":
                    // Phase AC (gap #2): grant Block to the class's living summon (CreatureCmd.GainBlock — the same
                    // path a summon's own `block` move uses). No summon out → logged no-op.
                    await HealOrShieldSummon(card, "shield_summon", amt);
                    break;
                case "add_card":
                    // Phase Q (gap #16): generate combat-transient copies of a SAME-CLASS card into a pile. The
                    // class index comes off the player (add_card is a class mechanic); ResolveClassCardModel enforces
                    // depth-1 loop discipline (refuses a card that itself add_cards). Copies live only for this combat
                    // (AddGeneratedCardToCombat — the base-game "generate a card" path; not added to the deck).
                    await AddCards(e, card.Owner, spec.Id); // spec.Id = the playing card → self-copies (Anger) allowed
                    break;
                case "summon_blade":
                    // Phase T: put the class's signature blade into hand from anywhere (Summon-Forth analogue) —
                    // retrieves an existing blade from draw/discard/exhaust, or generates one if none is in combat.
                    await ForgedForgePower.SummonBlade(ctx, card.Owner, fromAnywhere: true);
                    break;
                case "upgrade_card":
                    // Phase V (gap #18): upgrade cards in HAND for the rest of this combat. `random`/`all` are
                    // CHOICELESS (random = one random upgradable card, all = every upgradable card, the Armaments+
                    // form). Phase X (gap #18 player-pick): `choose` opens the hand-upgrade picker
                    // (CardSelectCmd.FromHandForUpgrade — the base-game Armaments surface), awaits the player's pick,
                    // then upgrades it; under AutoSlay the installed AutoSlayCardSelector auto-picks (no hang).
                    // Combat-scoped either way — hand cards are deck clones (Player.PopulateCombatState → CloneCard),
                    // so CardCmd.Upgrade mutates the clone, never the run deck.
                    if (e.Cards == "choose")
                        await UpgradeChoose(ctx, card.Owner, card);
                    else
                        UpgradeInHand(e.Cards, card.Owner);
                    break;
                case "apply_status_custom":
                {
                    // Phase J: apply a forged (class-specific) status by name. The status's behaviour is bound to
                    // a compiled type per class slot, so the resolved instance's ApplyStacks supplies that type.
                    // A buff lands on the player (self); a debuff lands on the card's target(s).
                    if (card is IForgedStatusHost sh)
                    {
                        var inst = ForgedCharacters.ResolveStatusInstance(sh.StatusClass, e.StatusName);
                        if (inst?.Spec is { } st)
                        {
                            int n = Math.Max(1, amt);
                            if (st.IsBuff)
                                await inst.ApplyStacks(ctx, card.Owner.Creature, card.Owner.Creature, n);
                            else
                                foreach (var t in CustomStatusTargets(card, play))
                                    await inst.ApplyStacks(ctx, t, card.Owner.Creature, n);
                        }
                        else
                            MainFile.Logger.Warn($"[Forged] apply_status_custom: class {sh.StatusClass} has no status '{e.StatusName}'.");
                    }
                    break;
                }
                default:
                    throw new NotSupportedException($"EffectRunner.Execute: unsupported op '{e.Op}'");
            }
        }
    }

    /// <summary>Phase Q (gap #16): the shared add_card executor — generate <c>max(1, amount)</c> combat-transient
    /// copies of the SAME-CLASS card <c>e.CardId</c> into <c>e.Pile</c> (hand/discard/draw) for
    /// <paramref name="owner"/>. Called from the card path (Execute, passing the playing card's id as
    /// <paramref name="adderId"/> so an Anger-style self-copy is allowed) and the trigger path (TriggerRunner,
    /// no adder → strict depth-1). <see cref="ForgedCharacters.ResolveClassCardModel"/> builds a fresh OWNER-BOUND
    /// combat card per copy (via CombatState.CreateCard, like base-game Anger/Infernal Blade) and enforces depth-1
    /// loop discipline. Copies are added via CardPileCmd.AddGeneratedCardToCombat (base-game generate-into-combat),
    /// so they live only for this combat and never enter the deck.</summary>
    internal static async Task AddCards(EffectSpec e, Player owner, string? adderId = null)
    {
        int k = ForgedCharacters.ClassIndexOfPlayer(owner);
        PileType pile = e.Pile switch
        {
            "draw"    => PileType.Draw,
            "discard" => PileType.Discard,
            _         => PileType.Hand,
        };
        int copies = Math.Max(1, e.Amount);
        int made = 0;
        for (int c = 0; c < copies; c++)
        {
            var model = ForgedCharacters.ResolveClassCardModel(k, e.CardId, owner, adderId); // owner-bound copy; null = skip
            if (model == null) break;   // unknown id or depth-1 refusal — ResolveClassCardModel logs the reason
            // creator = the player (marks the copy player-generated, like base-game Shivs/Insight); position Random.
            await CardPileCmd.AddGeneratedCardToCombat(model, pile, owner, CardPilePosition.Random);
            made++;
        }
        if (made > 0) MainFile.Logger.Info($"[Q] add_card '{e.CardId}' x{made} -> {pile}.");
        else MainFile.Logger.Warn($"[Q] add_card '{e.CardId}': nothing added (class {k}).");
    }

    // Phase AU (v51): how deep we are inside one of the MOD's OWN discard ops (discard / scry). Purely for the
    // `source=` attribution on DataCard's [AU] tag — the fire itself is the game's Hook.AfterCardDiscarded, which
    // reaches the card whatever discarded it. An int (not a bool) because a payload discard can nest; try/finally
    // keeps it balanced even if the discard throws. The no-cascade guard lives in DataCard, not here.
    internal static int ModDiscardDepth;

    /// <summary>Phase R (gap #17): discard <paramref name="n"/> RANDOM cards from <paramref name="owner"/>'s hand
    /// (choiceless — the player-choice variant needs the un-dumped CardSelectCmd UI). Shared by the card path
    /// (Execute) and the trigger path (TriggerRunner). Phase AU (v51): the <c>on_discard</c> payoffs fire from the
    /// game's own <c>Hook.AfterCardDiscarded</c> (which <c>CardCmd.Discard</c> raises per card) via
    /// <see cref="DataCard.AfterCardDiscarded"/> — this method no longer fires them itself (that would double-fire).
    /// on_discard stays EFFECT-DRIVEN: turn-end hand cleanup flushes the hand through CardPileCmd.Add +
    /// Hook.AfterFlush, which is not that hook. A discard nested inside an on_discard payload is suppressed (no
    /// cascade — DataCard's guard). Random picks use the run's card-selection RNG stream (seed-correct; no desync
    /// with card/other RNG).</summary>
    internal static async Task DiscardRandom(int n, Player owner, PlayerChoiceContext ctx)
    {
        var hand = owner.PlayerCombatState.Hand.Cards;
        if (n < 1 || hand.Count == 0) return;
        var pool = new List<CardModel>(hand);
        var rng = owner.RunState.Rng.CombatCardSelection;
        int take = Math.Min(n, pool.Count);
        var chosen = new List<CardModel>(take);
        for (int i = 0; i < take; i++)
        {
            int idx = rng.NextInt(pool.Count);
            chosen.Add(pool[idx]);
            pool.RemoveAt(idx);
        }
        ModDiscardDepth++;                                  // AU: tag attribution only (source=mod-op)
        try { await CardCmd.Discard(ctx, chosen); }         // → Hook.AfterCardDiscarded → each card's on_discard
        finally { ModDiscardDepth--; }
        MainFile.Logger.Info($"[R] discard x{chosen.Count} (random from hand).");
    }

    /// <summary>Phase AP (v46): the CHOOSE form of <c>discard</c> — the player picks <paramref name="n"/> cards in hand
    /// to discard via the base-game hand picker (<c>CardSelectCmd.FromHandForDiscard</c> — the discard-styled
    /// <c>FromHand</c>: it auto-returns the whole hand when there are ≤ n cards, no-ops the empty hand, and under AutoSlay
    /// the run-scoped <c>AutoSlayCardSelector</c> auto-picks, so this never blocks the bot). The picked cards are
    /// discarded through the same effect-discard path as the random form (<c>CardCmd.Discard</c> → <c>on_discard</c>
    /// payoffs), so a chosen discard fuels Reflex cards exactly like a random one. The playing card is the choice
    /// <paramref name="source"/> (as base-game Brand passes <c>this</c>).</summary>
    internal static async Task DiscardChoose(int n, PlayerChoiceContext ctx, Player owner, AbstractModel source)
    {
        var hand = owner.PlayerCombatState.Hand.Cards;
        if (n < 1 || hand.Count == 0) { MainFile.Logger.Info("[AP] discard choose: empty hand (no-op)."); return; }
        int take = Math.Min(n, hand.Count);
        var chosen = (await CardSelectCmd.FromHandForDiscard(ctx, owner,
            new CardSelectorPrefs(CardSelectorPrefs.DiscardSelectionPrompt, take), filter: null, source)).ToList();
        if (chosen.Count == 0) { MainFile.Logger.Info("[AP] discard choose: no selection (no-op)."); return; }
        ModDiscardDepth++;                                  // AU: tag attribution only (source=mod-op)
        try { await CardCmd.Discard(ctx, chosen); }         // → Hook.AfterCardDiscarded → each card's on_discard
        finally { ModDiscardDepth--; }
        MainFile.Logger.Info($"[AP] discard choose x{chosen.Count} ({string.Join(", ", chosen.Select(c => $"'{c.Title}'"))}).");
    }

    /// <summary>Phase AP (v46): is this pile card RETRIEVABLE — i.e. not a base-game Status / Curse card (a random
    /// recursion pulling a Wound or a Curse back to hand is anti-fun, and the chosen form shouldn't offer them either).</summary>
    private static bool Retrievable(CardModel c) => c.Type is not (CardType.Status or CardType.Curse);

    /// <summary>Phase AP (v46): RETRIEVE — return <paramref name="n"/> card(s) from the owner's discard or exhaust pile
    /// (<c>e.Pile</c>) to their hand. <c>e.Cards</c> = <c>"choose"</c> opens the base-game pile picker
    /// (<c>CardSelectCmd.FromCombatPile</c> with a filter — the Headbutt surface; the discard-prompt loc key is reused
    /// since the game has no "return to hand" prompt and inventing a loc key is the gap-#26 crash rule); otherwise the
    /// picks are random (the run's card-selection RNG stream, seed-correct). The move is <c>CardPileCmd.Add(card, Hand,
    /// Random)</c> — the exact call Phase T's blade retrieval uses from any pile, exhaust included. Empty / all-Status
    /// pile is a logged no-op. Under AutoSlay the <c>AutoSlayCardSelector</c> auto-picks (no hang).</summary>
    internal static async Task RetrieveCards(EffectSpec e, int n, PlayerChoiceContext ctx, Player owner)
    {
        PileType pileType = e.Pile == "exhaust" ? PileType.Exhaust : PileType.Discard;
        var pile = pileType.GetPile(owner);
        var pool = pile.Cards.Where(Retrievable).ToList();
        if (n < 1 || pool.Count == 0) { MainFile.Logger.Info($"[AP] retrieve_card: nothing retrievable in the {pileType} pile (no-op)."); return; }
        int take = Math.Min(n, pool.Count);
        List<CardModel> chosen;
        if (e.Cards == "choose")
        {
            chosen = (await CardSelectCmd.FromCombatPile(ctx, pile, owner,
                new CardSelectorPrefs(CardSelectorPrefs.DiscardSelectionPrompt, take), Retrievable)).ToList();
            if (chosen.Count == 0) { MainFile.Logger.Info("[AP] retrieve_card choose: no selection (no-op)."); return; }
        }
        else
        {
            var rng = owner.RunState.Rng.CombatCardSelection;
            chosen = new List<CardModel>(take);
            for (int i = 0; i < take; i++)
            {
                int idx = rng.NextInt(pool.Count);
                chosen.Add(pool[idx]);
                pool.RemoveAt(idx);
            }
        }
        foreach (var c in chosen)
            await CardPileCmd.Add(c, PileType.Hand, CardPilePosition.Random);
        MainFile.Logger.Info($"[AP] retrieve_card {e.Cards ?? "random"} x{chosen.Count} from {pileType} -> hand " +
                             $"({string.Join(", ", chosen.Select(c => $"'{c.Title}'"))}).");
    }

    /// <summary>Phase AP (v46): generate <paramref name="n"/> base-game STATUS cards (<c>e.StatusCard</c>: dazed / wound /
    /// burn) into <c>e.Pile</c> (hand / discard / draw) for the owner — the self-drawback of an over-statted card. Each
    /// card is built OWNER-BOUND through <c>CombatState.CreateCard&lt;T&gt;</c> and added via
    /// <c>CardPileCmd.AddGeneratedCardToCombat</c> (creator = the player), which is byte-for-byte the base-game recipe
    /// (FightThrough / BoostAway / Overclock) and the same generate-into-combat path Phase Q's add_card uses — so the cards
    /// live only for this combat and never enter the deck. Position Random (a Wound shuffled into the draw pile, not
    /// stacked on top).</summary>
    internal static async Task AddStatusCards(EffectSpec e, int n, Player owner)
    {
        PileType pile = e.Pile switch
        {
            "draw"    => PileType.Draw,
            "discard" => PileType.Discard,
            _         => PileType.Hand,
        };
        int made = 0;
        for (int i = 0; i < Math.Max(1, n); i++)
        {
            var cs = owner.Creature.CombatState;
            CardModel card = e.StatusCard switch
            {
                "dazed" => cs.CreateCard<MegaCrit.Sts2.Core.Models.Cards.Dazed>(owner),
                "burn"  => cs.CreateCard<MegaCrit.Sts2.Core.Models.Cards.Burn>(owner),
                _       => cs.CreateCard<MegaCrit.Sts2.Core.Models.Cards.Wound>(owner),
            };
            await CardPileCmd.AddGeneratedCardToCombat(card, pile, owner, CardPilePosition.Random);
            made++;
        }
        MainFile.Logger.Info($"[AP] add_status_card {ForgedCards.StatusCardName(e.StatusCard)} x{made} -> {pile}.");
    }

    /// <summary>Phase AA (gap #17 R-2): SCRY — look at the top <paramref name="n"/> cards of the DRAW pile and
    /// discard any subset the player picks. Slices the top N (<c>DrawPile.Cards[0]</c> is the top —
    /// <c>CardPilePosition.Top =&gt; 0</c>), shows them in a grid via <c>CardSelectCmd.FromSimpleGrid</c> with
    /// min 0 / max N (so "discard none" is a legal choice), then discards the picked subset
    /// (<c>CardCmd.Discard</c> → moves draw→discard, raising the game's AfterCardDiscarded hook so each discarded
    /// card's <c>on_discard</c> payoff fires — Phase AU (v51); we no longer fire them by hand). Empty draw pile is
    /// a harmless no-op. Under AutoSlay the <c>AutoSlayCardSelector</c> auto-picks (it takes maxSelect → discards
    /// all N, exercising the discard path fully); it never blocks the bot.</summary>
    internal static async Task Scry(int n, PlayerChoiceContext ctx, Player owner)
    {
        var draw = owner.PlayerCombatState.DrawPile.Cards;
        if (n < 1 || draw.Count == 0) { MainFile.Logger.Info("[AA] scry: empty draw pile (no-op)."); return; }
        int take = Math.Min(n, draw.Count);
        var topN = draw.Take(take).ToList();
        var prefs = new CardSelectorPrefs(CardSelectorPrefs.DiscardSelectionPrompt, 0, take);
        var toDiscard = (await CardSelectCmd.FromSimpleGrid(ctx, topN, owner, prefs)).ToList();
        if (toDiscard.Count == 0) { MainFile.Logger.Info($"[AA] scry {take} -> kept all (0 discarded)."); return; }
        ModDiscardDepth++;                                  // AU: tag attribution only (source=mod-op)
        try { await CardCmd.Discard(ctx, toDiscard); }      // → Hook.AfterCardDiscarded → each card's on_discard
        finally { ModDiscardDepth--; }
        MainFile.Logger.Info($"[AA] scry {take} -> discarded {toDiscard.Count} of the top {take}.");
    }

    /// <summary>Phase V (gap #18): upgrade the UPGRADABLE cards in <paramref name="owner"/>'s hand (choiceless —
    /// the player-choice variant needs the un-dumped card-select UI, spike Y). <paramref name="scope"/> "all"
    /// upgrades every upgradable hand card (Armaments+); anything else ("random"/null) upgrades ONE random one.
    /// Shared by the card path (Execute) and the trigger path (TriggerRunner, "random" only). COMBAT-SCOPED: a hand
    /// card is a clone of its deck card (Player.PopulateCombatState → CombatState.CloneCard), so CardCmd.Upgrade
    /// mutates the clone and the run deck is untouched — the base-StS "upgrade a card in your hand for this combat"
    /// convention. Filters on CardModel.IsUpgradable (already-upgraded / non-upgradable cards are skipped, exactly
    /// like base-game Armaments). No-op (never throws) when nothing qualifies. The random pick uses the run's
    /// CombatCardSelection RNG stream (seed-correct — deterministic for AutoSlay repro; shared with DiscardRandom).
    /// The upgrade VFX only shows for Deck-pile cards, so a hand upgrade shows none regardless of style — pass None.</summary>
    internal static void UpgradeInHand(string? scope, Player owner)
    {
        var upgradable = owner.PlayerCombatState.Hand.Cards.Where(c => c.IsUpgradable).ToList();
        if (upgradable.Count == 0) { MainFile.Logger.Info("[V] upgrade_card: no upgradable card in hand (no-op)."); return; }
        if (scope == "all")
        {
            CardCmd.Upgrade(upgradable, CardPreviewStyle.None);
            MainFile.Logger.Info($"[V] upgrade_card all -> {upgradable.Count} card(s) upgraded.");
        }
        else
        {
            var rng = owner.RunState.Rng.CombatCardSelection;
            var chosen = upgradable[rng.NextInt(upgradable.Count)];
            CardCmd.Upgrade(chosen, CardPreviewStyle.None);
            MainFile.Logger.Info($"[V] upgrade_card random -> '{chosen.Title}' upgraded.");
        }
    }

    /// <summary>Phase X (gap #18 player-pick): the CHOOSE form of upgrade_card. Opens the base-game hand-upgrade
    /// picker (<c>CardSelectCmd.FromHandForUpgrade</c> — the same surface Armaments uses: it filters to
    /// <c>IsUpgradable</c>, auto-returns the lone card when only one qualifies, and no-ops the empty hand) and awaits
    /// the player's pick, then upgrades it. Under AutoSlay the run-scoped <c>AutoSlayCardSelector</c> auto-picks, so
    /// this never blocks the bot. Combat-scoped like the choiceless forms (hand cards are deck clones — CardCmd.Upgrade
    /// mutates the clone, not the run deck). The playing card is passed as the choice <paramref name="source"/> (as
    /// base-game Armaments passes <c>this</c>).</summary>
    internal static async Task UpgradeChoose(PlayerChoiceContext ctx, Player owner, AbstractModel source)
    {
        var upgradable = owner.PlayerCombatState.Hand.Cards.Where(c => c.IsUpgradable).ToList();
        if (upgradable.Count == 0) { MainFile.Logger.Info("[V] upgrade_card choose: no upgradable card in hand (no-op)."); return; }
        var chosen = await CardSelectCmd.FromHandForUpgrade(ctx, owner, source);
        if (chosen != null)
        {
            CardCmd.Upgrade(chosen, CardPreviewStyle.None);
            MainFile.Logger.Info($"[V] upgrade_card choose -> '{chosen.Title}' upgraded.");
        }
        else
            MainFile.Logger.Info("[V] upgrade_card choose -> no selection (no-op).");
    }

    /// <summary>Phase Z (gap #19 choose): the CHOOSE-A-CARD purge. Opens the base-game hand picker
    /// (<c>CardSelectCmd.FromHand</c> — the same surface Brand uses to pick a card to exhaust) and awaits the
    /// player's pick, then PURGES that card: removes its run-deck original (via <c>DeckVersion</c>, reusing the
    /// Phase-W guard — a generated/token copy with no DeckVersion leaves the run deck untouched) AND removes the
    /// chosen combat clone from this fight. Empty hand / no selection is a harmless no-op (never throws). Under
    /// AutoSlay the run-scoped <c>AutoSlayCardSelector</c> auto-picks, so this never blocks the bot. The playing
    /// card is passed as the choice <paramref name="source"/> (as base-game Brand passes <c>this</c>).</summary>
    internal static async Task PurgeChoose(PlayerChoiceContext ctx, Player owner, AbstractModel source)
    {
        if (owner.PlayerCombatState.Hand.Cards.Count == 0)
        {
            MainFile.Logger.Info("[Z] purge_card: empty hand (no-op).");
            return;
        }
        var chosen = (await CardSelectCmd.FromHand(ctx, owner,
            new CardSelectorPrefs(CardSelectorPrefs.RemoveSelectionPrompt, 1), filter: null, source)).FirstOrDefault();
        if (chosen == null)
        {
            MainFile.Logger.Info("[Z] purge_card: no selection (no-op).");
            return;
        }
        // Run-permanent: remove the chosen card's run-deck original (its DeckVersion), guarded exactly like the
        // self-purge flag — a generated/token copy (null DeckVersion / not in the Deck pile) skips this.
        if (chosen.DeckVersion is { } deckCard && deckCard.Pile?.Type == PileType.Deck)
        {
            await CardPileCmd.RemoveFromDeck(deckCard, showPreview: false);
            MainFile.Logger.Info($"[Z] purge_card -> removed '{chosen.Title}' from the run deck.");
        }
        else
            MainFile.Logger.Info($"[Z] purge_card -> '{chosen.Title}' not in run deck (generated copy / token) — combat-vanish only.");
        // Combat vanish: the chosen card is sitting in hand (not being played), so remove it from combat explicitly.
        await CardPileCmd.RemoveFromCombat(chosen, skipVisuals: true);
    }

    /// <summary>Phase AH (gaps #35/#38): PERMANENTLY transform the played card into <c>e.CardId</c> (a same-class
    /// card) for the rest of the run. The RUN-DECK original is swapped via <c>CardCmd.Transform(DeckVersion,
    /// replacement, None)</c> under the Phase-W purge DeckVersion guard (a generated/token copy with a null
    /// DeckVersion leaves the run deck untouched — combat-only). This combat's in-hand CLONES of the same card are
    /// transformed too, so the change is visible immediately. Each half resolves its own OWNER-BOUND replacement via
    /// <c>ForgedCharacters.ResolveTransformTarget</c> (which enforces the no-chain / no-self / same-class discipline
    /// and logs+skips on any refusal). Spike AH-0 proved both halves are AutoSlay-safe. <paramref name="playing"/> is
    /// the card being played (its <c>spec.Id</c> = the adder, so the chain-guard can allow an A↔B mode-swap back).</summary>
    /// <summary>Phase AH: a card's stable SPEC id (the class-card id transform_card names). A forged card is a
    /// <see cref="DataCard"/> (its SpecId is the JSON id); the fallback stringifies the model id for anything else.</summary>
    private static string SpecIdOf(CardModel c) => c is DataCard dc ? dc.SpecId : c.Id.ToString();

    internal static async Task TransformCard(EffectSpec e, ConstructedCardModel playing, PlayerChoiceContext ctx)
    {
        _ = ctx;
        var owner = playing.Owner;
        int k = ForgedCharacters.ClassIndexOfPlayer(owner);
        string fromId = SpecIdOf(playing);
        // --- (1) run-deck permanence: swap the played card's DeckVersion (its run-deck original). ---
        if (playing.DeckVersion is { } deckCard && deckCard.Pile?.Type == PileType.Deck && deckCard.IsTransformable)
        {
            var replacement = ForgedCharacters.ResolveTransformTarget(k, e.CardId, owner, fromId);
            if (replacement != null)
            {
                await CardCmd.Transform(deckCard, replacement, CardPreviewStyle.None);
                MainFile.Logger.Info($"[AH] transform_card: '{fromId}' -> '{e.CardId}' (run deck)");
            }
        }
        else
            MainFile.Logger.Info($"[AH] transform_card: '{fromId}' not in run deck (generated copy) — combat only");
        // --- (2) combat clone(s) in hand: transform any in-hand copy of THIS card so the swap is felt this combat.
        // (The played card is itself leaving play; this catches sibling copies still held — and makes a
        // conditionally-gated rank-up visibly upgrade the hand before the next draw.) ---
        var handCopies = owner.PlayerCombatState.Hand.Cards
            .Where(c => c != null && c != playing && c.IsTransformable && SpecIdOf(c) == fromId)
            .ToList();
        foreach (var handCard in handCopies)
        {
            var replacement = ForgedCharacters.ResolveTransformTarget(k, e.CardId, owner, fromId);
            if (replacement == null) break;   // refused (chain/self/unknown) — logged; don't retry per copy
            await CardCmd.Transform(handCard, replacement, CardPreviewStyle.None);
            MainFile.Logger.Info($"[AH] transform_card: '{fromId}' -> '{e.CardId}' (combat clone)");
        }
    }

    /// <summary>Phase AI (gap #7): GRAFT — the choose form of <c>transform_card</c> (as <c>purge_card</c> is the
    /// choose form of <c>purge</c>). Opens the base-game hand picker (<c>CardSelectCmd.FromHand</c> — the Brand/Begone
    /// "choose a card" surface, exactly as Phase Z's <c>PurgeChoose</c> does) and awaits the player's pick, then
    /// PERMANENTLY transforms that PICKED card into <c>e.CardId</c> (a same-class card) for the rest of the run: the
    /// picked card's RUN-DECK original is swapped via <c>CardCmd.Transform(DeckVersion, replacement, None)</c> under
    /// the Phase-W purge DeckVersion guard (a generated/token copy with a null DeckVersion leaves the run deck
    /// untouched — combat-only), AND the picked hand CLONE is transformed now so the change is felt this combat.
    /// Empty hand / no selection is a harmless no-op (never throws). If the pick already IS the target (its SpecId ==
    /// <c>e.CardId</c>) it's a no-op (a card becoming itself). The <paramref name="playing"/> card is the graft card
    /// being played (passed as the choice source); a graft card CAN pick itself (like purge_card), but since it is
    /// leaving play its own transform only matters if a sibling copy is held — handled by the shared runtime. Under
    /// AutoSlay the run-scoped <c>AutoSlayCardSelector</c> auto-picks, so this never blocks the bot.</summary>
    internal static async Task GraftCard(EffectSpec e, ConstructedCardModel playing, PlayerChoiceContext ctx)
    {
        var owner = playing.Owner;
        int k = ForgedCharacters.ClassIndexOfPlayer(owner);
        if (owner.PlayerCombatState.Hand.Cards.Count == 0)
        {
            MainFile.Logger.Info("[AI] graft: no selection (no-op)");
            return;
        }
        // Pick one card in hand (the base-game Brand/Begone "choose a card" surface — Phase Z's PurgeChoose recipe).
        var chosen = (await CardSelectCmd.FromHand(ctx, owner,
            new CardSelectorPrefs(CardSelectorPrefs.TransformSelectionPrompt, 1), filter: null, playing)).FirstOrDefault();
        if (chosen == null)
        {
            MainFile.Logger.Info("[AI] graft: no selection (no-op)");
            return;
        }
        string pickedId = SpecIdOf(chosen);
        // A card becoming ITSELF (the pick already is the target) is a no-op — mirror transform_card's self-guard.
        var replacement = ForgedCharacters.ResolveTransformTarget(k, e.CardId, owner, pickedId);
        if (replacement == null)
        {
            // ResolveTransformTarget logs the specific refusal (self / chain / unknown); this is the shared no-op.
            MainFile.Logger.Info($"[AI] graft: '{pickedId}' -> '{e.CardId}' refused (no-op)");
            return;
        }
        // --- (1) run-deck permanence: swap the picked card's DeckVersion (its run-deck original). ---
        if (chosen.DeckVersion is { } deckCard && deckCard.Pile?.Type == PileType.Deck && deckCard.IsTransformable)
        {
            await CardCmd.Transform(deckCard, replacement, CardPreviewStyle.None);
            MainFile.Logger.Info($"[AI] graft: '{pickedId}' -> '{e.CardId}' (run deck)");
            // (2) the picked HAND clone: transform it now so the change is visible this combat (build a fresh
            // owner-bound replacement — CardCmd.Transform consumes the model into the pile, so reuse isn't safe).
            var handRepl = ForgedCharacters.ResolveTransformTarget(k, e.CardId, owner, pickedId);
            if (handRepl != null && chosen.IsTransformable)
            {
                await CardCmd.Transform(chosen, handRepl, CardPreviewStyle.None);
                MainFile.Logger.Info($"[AI] graft: '{pickedId}' -> '{e.CardId}' (combat clone)");
            }
        }
        else
        {
            // Generated/token pick (no run-deck original): transform only the combat clone in hand.
            MainFile.Logger.Info($"[AI] graft: '{pickedId}' not in run deck (generated copy) — combat only");
            if (chosen.IsTransformable)
            {
                await CardCmd.Transform(chosen, replacement, CardPreviewStyle.None);
                MainFile.Logger.Info($"[AI] graft: '{pickedId}' -> '{e.CardId}' (combat clone)");
            }
        }
    }

    /// <summary>
    /// Self-buff statuses ALWAYS land on the PLAYER (like Block), regardless of the card's target — so
    /// "Gain Strength" is correct even on an attack/AoE card and never buffs the enemy. Everything else is a
    /// debuff placed on the card's target(s). This set is the SINGLE source of truth for buff-vs-debuff side:
    /// the executor below and <c>ForgedCards.Describe</c> both read it, so targeting and wording never drift.
    /// </summary>
    public static readonly HashSet<string> SelfBuffStatuses =
    [
        "strength", "dexterity", "thorns", "regen", "metallicize", "artifact", "buffer",
        "intangible", "ritual", "blur", "temp_strength", "temp_dexterity", "barricade",
        "focus", // orb output scaling (Phase G)
        "temp_thorns", "temp_focus", // Phase AN (v44): one-turn Thorns / Focus (ForgedTempThornsPower / ForgedTempFocusPower)
    ];

    /// <summary>Orb type for the <c>channel_orb</c> op (Phase G; lightning/frost/dark for the MVP).
    /// Internal so the trigger path (<see cref="TriggerRunner"/>) channels via the same mapping.</summary>
    internal static Type OrbTypeFor(string? orb) => orb switch
    {
        "lightning" => typeof(LightningOrb),
        "frost"     => typeof(FrostOrb),
        "dark"      => typeof(DarkOrb),
        _ => throw new NotSupportedException($"EffectRunner: unsupported orb '{orb}'"),
    };

    private static readonly Type[] _randomOrbs = [typeof(LightningOrb), typeof(FrostOrb), typeof(DarkOrb)];

    /// <summary>A random orb type from the tested MVP set, via the run's dedicated orb-generation RNG stream
    /// (so it doesn't desync card/other RNG and stays seed-correct).</summary>
    private static Type RandomOrbType(ConstructedCardModel card) => RandomOrbType(card.Owner);

    /// <summary>Random-orb roll from a player (used by the trigger path, which has no card).</summary>
    internal static Type RandomOrbType(Player player) =>
        _randomOrbs[player.RunState.Rng.CombatOrbGeneration.NextInt(_randomOrbs.Length)];

    // === Phase F5: live state scalars (scale: x / cards_in_hand / cards_retained / unspent_energy_last_turn) ===
    /// <summary>Resolve a scaled effect's live amount for <paramref name="card"/>. The SINGLE source of truth for
    /// both the draw path (here) and <see cref="DataCard"/>'s damage/block calc vars, so the previewed and the
    /// executed number always agree. Tolerant outside combat (returns 0). See <see cref="HandStateTracker"/>.
    /// Phase M (gap #36): <c>"forged"</c> is the ADDITIVE exception — the returned stacks are added to the
    /// printed amount at the damage/block calc-var sites (DataCard.BonusFor), never a replacement.</summary>
    internal static int ScaleValue(string? scale, CardModel card) => scale switch
    {
        "x"                        => card.ResolveEnergyXValue(),
        "cards_in_hand"            => OtherCardsInHand(card),
        "cards_retained"           => HandStateTracker.CardsRetained,
        "unspent_energy_last_turn" => HandStateTracker.UnspentEnergyLastTurn,
        "forged"                   => ForgeStacks(card.Owner),
        // Phase AM (v43): five more live player reads (replace-semantics, like the F5 hand/energy reads).
        "block"                    => card.Owner?.Creature?.Block ?? 0,                   // Body Slam / Entrench
        "hp_lost_this_turn"        => HpLossTracker.HpLostThisTurn(card.Owner),           // the AD snapshot read
        "draw_pile_count"          => card.Owner?.PlayerCombatState?.DrawPile?.Cards?.Count ?? 0,
        // `energy` is cost-0-ONLY (validator-enforced) so the in-hand preview (pre-pay) and the resolved amount
        // (post-pay — PlayCardAction.SpendResources runs before OnPlay) always agree.
        "energy"                   => card.Owner?.PlayerCombatState?.Energy ?? 0,
        "plays_this_combat"        => CardsPlayedThisCombat(card.Owner),                  // the OTHER cards you played
        _ => 0,
    };

    /// <summary>Phase AM (v43): the scales this phase added (for the [AM] play-time log below).</summary>
    internal static readonly HashSet<string> PhaseAmScales =
        ["block", "hp_lost_this_turn", "draw_pile_count", "energy", "plays_this_combat"];

    /// <summary>Phase AM (v43): the condition kinds this phase added (for the [AM] gate log below).</summary>
    internal static readonly HashSet<string> PhaseAmConditions =
        ["target_hp_below_half", "target_has_block", "energy_ge", "cards_played_this_turn_ge"];

    /// <summary>Phase AM (v43): cards <paramref name="player"/> has FINISHED playing this combat (any turn). The
    /// PLAYER-level sibling of <see cref="PlaysThisCombat"/> (which is per-card-instance and feeds `grow`): the
    /// <c>plays_this_combat</c> scale — "deal damage equal to the cards you have played this combat". The in-flight
    /// play is not yet in the finished history, so it counts the OTHER cards played before it. Combat-scoped
    /// history → per-combat reset is free. Owner-filtered (the base-game Finisher pattern) for multiplayer safety.</summary>
    internal static int CardsPlayedThisCombat(Player? player)
    {
        var cm = CombatManager.Instance;
        if (player == null || cm?.History?.CardPlaysFinished == null) return 0;
        return cm.History.CardPlaysFinished.Count(entry => entry.CardPlay.Card.Owner == player);
    }

    /// <summary>Phase AM (v43): cards <paramref name="player"/> has FINISHED playing THIS turn — the
    /// <c>cards_played_this_turn_ge</c> condition (Finisher: <c>HappenedThisTurn</c> + owner filter). On a card it
    /// counts the other cards played earlier this turn; on a turn_end trigger it is the whole turn's plays.</summary>
    internal static int CardsPlayedThisTurn(Player? player)
    {
        var cm = CombatManager.Instance;
        var cs = player?.Creature?.CombatState;
        if (player == null || cs == null || cm?.History?.CardPlaysFinished == null) return 0;
        return cm.History.CardPlaysFinished.Count(entry => entry.HappenedThisTurn(cs) && entry.CardPlay.Card.Owner == player);
    }

    /// <summary>Phase P (gap #22): count of DEBUFF powers on <paramref name="target"/> (0 if null). Read by the
    /// <c>target_debuff_count</c> calc-var (<see cref="DataCard"/>.BonusFor) at attack resolution, once per struck
    /// target — so an AoE flechette hits each enemy for that enemy's own debuff count. NOT a player-state read, so
    /// it never routes through <see cref="ScaleValue"/> (which has no target). Counts the game's four debuff
    /// powers (the closed debuff vocabulary this mod applies — mirrors EnemyDebuffStatuses / Conditions'
    /// target_has_status checks) via the same HasPower&lt;T&gt; path, each present debuff = 1 (not its stacks).</summary>
    /// <summary>Phase AX (v53, gaps #45-#47): the <c>spread_debuffs</c> executor — COPY every debuff the struck
    /// target carries onto every OTHER living hittable enemy, at the source's current stack counts. Reads the same
    /// four-power closed debuff vocabulary <see cref="DebuffCount"/> does (the debuffs this mod can apply), each at
    /// its live amount, and lands them through the literal-amount <see cref="RelicApply"/> path (no card var — the
    /// numbers come from the target, not the card). The source enemy is skipped (it already has them); a target
    /// with no debuffs, or a fight with no second enemy, is a silent no-op.</summary>
    private static async Task SpreadDebuffs(ConstructedCardModel card, PlayerChoiceContext ctx, CardPlay play)
    {
        var source = play?.Target;
        if (source == null)
        {
            MainFile.Logger.Info($"[AX] spread_debuffs: no chosen target ('{card.Id}') — no-op.");
            return;
        }
        var stacks = new List<(string Status, int Amount)>();
        void Take<T>(string name) where T : PowerModel
        {
            if (source.HasPower<T>())
            {
                int n = source.GetPowerAmount<T>();
                if (n > 0) stacks.Add((name, n));
            }
        }
        Take<VulnerablePower>("vulnerable");
        Take<WeakPower>("weak");
        Take<FrailPower>("frail");
        Take<PoisonPower>("poison");
        var others = source.CombatState.HittableEnemies.Where(c => c.IsAlive && c != source).ToList();
        if (stacks.Count == 0 || others.Count == 0)
        {
            MainFile.Logger.Info($"[AX] spread_debuffs: {stacks.Count} debuff(s) on the target, {others.Count} other enemy(ies) — no-op ('{card.Id}').");
            return;
        }
        foreach (var (status, amount) in stacks)
            foreach (var other in others)
                await RelicApply(status, ctx, other, card.Owner.Creature, amount);
        MainFile.Logger.Info($"[AX] spread_debuffs: copied {string.Join(", ", stacks.Select(t => $"{t.Status} {t.Amount}"))} " +
                             $"to {others.Count} other enemy(ies) ('{card.Id}').");
    }

    internal static int DebuffCount(Creature? target)
    {
        if (target == null) return 0;
        int n = 0;
        if (target.HasPower<VulnerablePower>()) n++;
        if (target.HasPower<WeakPower>()) n++;
        if (target.HasPower<FrailPower>()) n++;
        if (target.HasPower<PoisonPower>()) n++;
        return n;
    }

    /// <summary>Phase AE (gap #25): count of cards carrying <paramref name="tag"/> across the player's combat piles
    /// (draw + discard + hand + exhaust — all of PlayerCombatState.AllCards). Read by the <c>tag_cards_owned</c>
    /// ADDITIVE scalar (see <see cref="DataCard"/>.BonusFor + the damage/block log) — "Deal N damage, +1 per Strike
    /// you own." Live scan (not a constant): the count shifts as cards move between piles / are generated / exhausted.
    /// Only OUR cards (DataCards) carry Spec tags; base-game cards never match. Empty/unknown tag → 0.</summary>
    internal static int TagCardsOwned(Player? owner, string? tag)
    {
        if (owner == null || string.IsNullOrEmpty(tag)) return 0;
        var all = owner.PlayerCombatState?.AllCards;
        if (all == null) return 0;
        int n = 0;
        foreach (var c in all)
            if (c is DataCard dc && dc.SpecHasTag(tag)) n++;
        return n;
    }

    /// <summary>Phase AF (gap #41): the blade-empower multiplier that applies to <paramref name="card"/> — N if the
    /// card is the forge class's signature blade TOKEN (Spec.IsToken) and its owner has a live
    /// <see cref="Powers.ForgedBladeEmpowerPower"/>, else 1. Token-scoped so empower is "the blade deals double",
    /// not "everything forged deals double". Read by the blade's scale:"forged" calc-var (<see cref="DataCard"/>.BonusFor).</summary>
    internal static int BladeMultiplier(CardModel card) =>
        card is DataCard dc && dc.SpecIsToken ? Powers.ForgedBladeEmpowerPower.Multiplier(card.Owner) : 1;

    /// <summary>Phase U (gap #23, Rampage): how many times THIS card instance has already FINISHED playing this
    /// combat. Read by the <c>grow</c> calc-var (<see cref="DataCard"/>.GrowBonusFor) — damage = amount + grow ×
    /// this count. The in-flight play is not yet in the finished-plays history, so the first play reads 0 (deals
    /// the printed amount). Whole-combat scope: unlike BaseLib's PersistVar we DROP the <c>HappenedThisTurn</c>
    /// filter. Per-card-INSTANCE (`entry.CardPlay.Card == card` is reference identity — a generated copy is a
    /// different instance and grows independently). Per-combat reset is free (the history is combat-scoped).</summary>
    internal static int PlaysThisCombat(CardModel card)
    {
        var cm = CombatManager.Instance;
        if (cm?.History?.CardPlaysFinished == null) return 0;
        return cm.History.CardPlaysFinished.Count(entry => entry.CardPlay.Card == card);
    }

    /// <summary>Phase M (gap #36): the player's current Forge stacks (0 with no power / outside combat).
    /// Shared by the scale read above and the <c>forged_ge</c> condition (<see cref="Conditions"/>).</summary>
    internal static int ForgeStacks(Player? player)
    {
        var c = player?.Creature;
        return c != null && c.HasPower<ForgedForgePower>() ? c.GetPowerAmount<ForgedForgePower>() : 0;
    }

    /// <summary>Cards in hand EXCLUDING this one — stable whether the card is still in hand (preview) or already
    /// moved to the play pile (resolution), so "Deal damage equal to the cards in your hand" never flickers ±1.</summary>
    private static int OtherCardsInHand(CardModel card)
    {
        var hand = card.Owner?.PlayerCombatState?.Hand?.Cards;
        if (hand == null) return 0;
        int n = 0;
        foreach (var c in hand) if (!ReferenceEquals(c, card)) n++;
        return n;
    }

    private static int ResolveScaleAmount(EffectSpec e, ConstructedCardModel card) => ScaleValue(e.Scale, card);

    /// <summary>Phase AM (v43): the live value an [AM]-logged gate compared against (log text only).</summary>
    private static string PhaseAmConditionRead(Condition w, ConstructedCardModel card, CardPlay play) => w.Kind switch
    {
        "target_hp_below_half" => play?.Target == null ? "no target" : $"target HP {play.Target.CurrentHp}/{play.Target.MaxHp}",
        "target_has_block"     => play?.Target == null ? "no target" : $"target Block {play.Target.Block}",
        "energy_ge"            => $"energy {card.Owner?.PlayerCombatState?.Energy ?? 0} after paying this card",
        "cards_played_this_turn_ge" => $"played {CardsPlayedThisTurn(card.Owner)} other cards this turn",
        _ => "",
    };

    /// <summary>The creature(s) a card-played custom DEBUFF lands on: the chosen single target if any, else the
    /// card's resolved targets (AoE). Mirrors BaseLib CommonActions.Apply(ctx, card, cardPlay).</summary>
    private static IEnumerable<Creature> CustomStatusTargets(ConstructedCardModel card, CardPlay play) =>
        play?.Target != null ? [play.Target] : card.GetTargets();

    private static Task ApplyStatus(string? status, ConstructedCardModel card, PlayerChoiceContext ctx, CardPlay play)
    {
        bool self = SelfBuffStatuses.Contains(status ?? "");
        return status switch
        {
            "vulnerable"     => ApplyPower<VulnerablePower>(self, card, ctx, play),
            "weak"           => ApplyPower<WeakPower>(self, card, ctx, play),
            "frail"          => ApplyPower<FrailPower>(self, card, ctx, play),
            "poison"         => ApplyPower<PoisonPower>(self, card, ctx, play),
            "strength"       => ApplyPower<StrengthPower>(self, card, ctx, play),
            "dexterity"      => ApplyPower<DexterityPower>(self, card, ctx, play),
            "thorns"         => ApplyPower<ThornsPower>(self, card, ctx, play),
            "regen"          => ApplyPower<RegenPower>(self, card, ctx, play),
            "metallicize"    => ApplyPower<PlatingPower>(self, card, ctx, play),
            "artifact"       => ApplyPower<ArtifactPower>(self, card, ctx, play),
            "buffer"         => ApplyPower<BufferPower>(self, card, ctx, play),
            "intangible"     => ApplyPower<IntangiblePower>(self, card, ctx, play),
            "ritual"         => ApplyPower<RitualPower>(self, card, ctx, play),
            "blur"           => ApplyPower<BlurPower>(self, card, ctx, play),
            "temp_strength"  => ApplyPower<ForgedTempStrengthPower>(self, card, ctx, play),
            "temp_dexterity" => ApplyPower<ForgedTempDexterityPower>(self, card, ctx, play),
            "barricade"      => ApplyPower<BarricadePower>(self, card, ctx, play),
            "focus"          => ApplyPower<FocusPower>(self, card, ctx, play),
            "temp_thorns"    => ApplyPower<ForgedTempThornsPower>(self, card, ctx, play), // Phase AN (v44)
            "temp_focus"     => ApplyPower<ForgedTempFocusPower>(self, card, ctx, play),  // Phase AN (v44)
            _ => throw new NotSupportedException($"EffectRunner.ApplyStatus: unsupported status '{status}'"),
        };
    }

    /// <summary>Apply N stacks of power <typeparamref name="T"/> — to the player if <paramref name="self"/>
    /// (self-buff), else to the card's target(s) (debuff). Reads the card's <c>PowerVar&lt;T&gt;</c>.</summary>
    private static Task ApplyPower<T>(bool self, ConstructedCardModel card, PlayerChoiceContext ctx, CardPlay play)
        where T : PowerModel
        => self ? CommonActions.ApplySelf<T>(ctx, card) : CommonActions.Apply<T>(ctx, card, play);

    // === Phase L: forged-relic effect execution (NO card) ===========================================
    /// <summary>Run a relic hook's effects with no card: the player is the actor; <paramref name="targets"/> are
    /// the resolved enemy target(s) for damage/debuffs (empty for self-only effects). Relic v1 sub-vocabulary:
    /// damage, block, draw, gain_energy, heal, lose_hp, apply_status (buff→player, debuff→targets). Merges the
    /// no-card paths of <see cref="TriggerRunner"/> (self) and <see cref="SummonRunner"/> (targeted). Called by
    /// <see cref="RelicRunner"/>.</summary>
    public static async Task RunRelicEffects(EffectSpec[] effects, PlayerChoiceContext ctx, Player player,
                                             List<Creature> targets, int relicClass, string hookTarget = "self")
    {
        foreach (var e in effects)
        {
            int amt = Math.Max(1, e.Amount);
            switch (e.Op)
            {
                case "block":       await CreatureCmd.GainBlock(player.Creature, amt, ValueProp.Move, null, false); break;
                case "draw":        await CardPileCmd.Draw(ctx, amt, player); break;
                case "gain_energy": await PlayerCmd.GainEnergy(amt, player); break;
                case "heal":        await CreatureCmd.Heal(player.Creature, amt, true); break;
                case "lose_hp":     await CreatureCmd.Damage(ctx, player.Creature, amt, ValueProp.Unblockable, (Creature?)null, (CardModel?)null); break;
                case "damage":
                    // Relic damage is intrinsic (ValueProp.Move), player as dealer; only if there's a target.
                    if (targets.Count > 0)
                        await CreatureCmd.Damage(ctx, targets, amt, ValueProp.Move, player.Creature);
                    break;
                case "apply_status":
                    await ApplyRelicStatus(e.Status, ctx, player, targets, amt, hookTarget);
                    break;
                case "apply_status_custom":
                {
                    // Phase BA (v55): apply one of the CLASS's OWN statuses from a no-card effect — the op that lets a
                    // status class's POTION hand out its signature status ("drink this, gain 3 Razor Focus"). Same
                    // resolution as the card/trigger op (ResolveStatusInstance); a buff lands on the owner, a debuff on
                    // the resolved targets. Unknown name => warn + skip, never a throw.
                    // Reachable today only from a potion: the relic vocabulary (ForgedCharacters.RelicEffectOps) does
                    // NOT list this op, so a relic bundle carrying it is rejected at import.
                    var inst = ForgedCharacters.IsStatusClass(relicClass)
                                   ? ForgedCharacters.ResolveStatusInstance(relicClass, e.StatusName) : null;
                    if (inst?.Spec is not { } cst)
                    {
                        MainFile.Logger.Warn($"[BA] apply_status_custom: class {relicClass} has no status '{e.StatusName}' (skipped).");
                        break;
                    }
                    if (cst.IsBuff)
                    {
                        MainFile.Logger.Info($"[BA] apply_status_custom: gain {amt} {cst.Name} (self buff).");
                        await inst.ApplyStacks(ctx, player.Creature, player.Creature, amt);
                    }
                    else
                    {
                        MainFile.Logger.Info($"[BA] apply_status_custom: apply {amt} {cst.Name} to {targets.Count} enemy/ies.");
                        foreach (var t in targets)
                            await inst.ApplyStacks(ctx, t, player.Creature, amt);
                    }
                    break;
                }
                case "discard":
                    // Phase AS (v48): the relic DRAWBACK op — discard N random cards from hand (the Phase R random path, so
                    // on_discard payoffs still fire). Random only; a relic never opens a picker. No-op on an empty hand.
                    MainFile.Logger.Info($"[AS] discard x{amt} (relic drawback).");
                    await DiscardRandom(amt, player, ctx);
                    break;
                case "forge":
                    // Phase M (gap #36): relic-side Forge income — the "smoldering heirloom" keystone.
                    // Phase T: a turn-1 relic Forge summons the blade too (Stoke centralizes all three paths).
                    await ForgedForgePower.Stoke(ctx, player, Math.Max(1, amt));
                    MainFile.Logger.Info($"[M] forge +{amt} (relic) -> Forge {ForgeStacks(player)}.");
                    break;
                case "cost_shift":
                    // Phase AO (v45): relic-side discount — the "first card each turn costs 1 less" keystone (the Phase-L
                    // deferral). this_turn only (import-validated), so a per-turn hook never accumulates; no granter.
                    await ForgedCostShiftPower.Add(ctx, player, e.CardKind, amt, e.Scope, e.Count, "relic", null);
                    break;
                // Phase L compose ops — a relic reaches its OWN class's orb/summon pool (RelicClass == class index).
                // Defensive no-op if the class declares no orbs/summons (the generator gates these; the runtime guards).
                case "channel_orb":
                    if (ForgedCharacters.IsOrbClass(relicClass))
                        await ChannelForgedOrbs(relicClass, e.Orb, amt, player, ctx);
                    break;
                case "summon":
                    if (ForgedCharacters.IsSummonClass(relicClass))
                        await SummonForged(relicClass, e.SummonName, amt, player, ctx);
                    break;
                // Any other op is validator-forbidden in a relic; ignore defensively.
            }
        }
    }

    /// <summary>Channel <paramref name="count"/> orbs from forged class <paramref name="orbClass"/>'s pool
    /// ("random" rolls within the pool). Shared by the card and relic channel_orb ops. Phase AJ (v40): an orb name the
    /// class's pool doesn't resolve is WARNED and skipped — it used to fall back to Lightning silently, which hid typos
    /// and contradicted the "custom orbs are strictly per-class" contract (the importer now rejects such names too).</summary>
    internal static async Task ChannelForgedOrbs(int orbClass, string? orb, int count, Player owner, PlayerChoiceContext ctx)
    {
        for (int n = 0; n < count; n++)
        {
            Type? orbType = orb == "random"
                               ? ForgedCharacters.RandomOrbType(orbClass, owner)
                               : ForgedCharacters.ResolveOrbType(orbClass, orb);
            if (orbType == null)
            {
                MainFile.Logger.Warn($"[AJ] channel_orb: class {orbClass} has no orb '{orb}' — skipped (no Lightning fallback).");
                return;
            }
            await OrbCmd.Channel(ctx, ((OrbModel)ModelDb.Get(orbType)).ToMutable(0), owner);
        }
    }

    /// <summary>The base-game Osty Summon keyword for a forged class. If THIS NAMED minion is already alive, raise
    /// its Max HP by <paramref name="amount"/> (Osty's "Summon while alive" — the user's "increase XP"); otherwise
    /// summon a fresh one with that HP, heal it, and apply the meat-shield. Phase AV (v52): the lookup is keyed on the
    /// NAME, so a class's two pool entries can coexist on board (<c>ForgedCharacters.MaxSummons</c> = 2) — before AV
    /// the class-wide lookup meant a second named minion only ever grew the first. A minion is PASSIVE unless its spec
    /// declares a move cycle (Phase AV re-enabled the autonomous model); the class's <c>summon_attack</c> cards strike
    /// through whichever one is FRONT-most. Shared by the card summon op and the relic summon op.
    /// <paramref name="amount"/> = HP (0 / omitted ⇒ the summon's spec MaxHp). Mirrors the decompiled
    /// <c>OstyCmd.Summon</c> (fresh-summon-when-none-alive instead of reviving a kept corpse — functionally
    /// identical, no keep-corpse power needed).</summary>
    internal static async Task SummonForged(int summonClass, string? name, int amount, Player player, PlayerChoiceContext ctx)
    {
        var type = ForgedCharacters.ResolveSummonType(summonClass, name);
        if (type == null) { MainFile.Logger.Warn($"[Forged] summon: class {summonClass} has no summon '{name}'."); return; }
        var model = (MonsterModel)ModelDb.Get(type);
        var spec = (model as Powers.ForgedSummon)?.Source;
        int hp = amount >= 1 ? amount : Math.Max(1, spec?.MaxHp ?? 10);

        // THIS minion already on board → just grow its Max HP (the Summon keyword while alive). No second copy.
        var existing = FindLivingSummon(player, summonClass, spec?.Name ?? name);
        if (existing != null)
        {
            await CreatureCmd.GainMaxHp(existing, hp);
            return;
        }
        // Phase AV (v52): a DIFFERENT minion of the class may already be out — they coexist (MaxSummons = 2).
        var other = FindLivingSummon(player, summonClass);
        if (other != null)
            MainFile.Logger.Info($"[AV] second summon '{spec?.Name ?? name}' joins '{(other.Monster as Powers.ForgedSummon)?.Source?.Name ?? "summon"}'.");

        // None alive → summon fresh at `hp`, heal to full, then meat-shield + layout.
        var pet = player.Creature.CombatState.CreateCreature(model.ToMutable(), player.Creature.Side, null);
        player.PlayerCombatState.AddPetInternal(pet);
        await CreatureCmd.Add(pet);
        await CreatureCmd.SetMaxHp(pet, hp);
        await CreatureCmd.Heal(pet, hp, true);
        await Powers.ForgedSummonPower.Apply(ctx, pet);   // the move-cycle / on_nth_attack driver (no moves ⇒ passive)
        pet.Died += _ => Powers.ForgedSummon.LayoutPets(player);
        // Meat shield: redirect the player's incoming powered hits to the living minion (Osty's DieForYou).
        await Powers.ForgedSummonShieldPower.Apply(ctx, player.Creature);
        Powers.ForgedSummon.LayoutPets(player); // non-Osty pets spawn on top of the player → lay out to the right

        // Phase AV (v52): the BATTLE CRY. Parsed since K-3 but never run — fire it once the pet is fully placed
        // (after LayoutPets) so its attacks/debuffs resolve from a real board position. Fresh summons only: the
        // grow path above returns before here, so re-summoning to pump Max HP never re-triggers the cry.
        var petSpec = (pet.Monster as Powers.ForgedSummon)?.Source ?? spec;
        if (petSpec?.OnSummon is { Length: > 0 } cry)
        {
            MainFile.Logger.Info($"[AV] on_summon '{petSpec.Name}': {cry.Length} action(s).");
            await SummonRunner.RunActions(cry, pet, ctx);
        }
    }

    /// <summary>Phase AV (v52): kill the class's FRONT-most living summon so its <c>on_death</c> rattle fires — the
    /// <c>sacrifice_summon</c> card op. Uses the base game's own death path (<c>CreatureCmd.Kill</c>, force: true —
    /// the decompile shows it runs <c>Hook.BeforeDeath</c> → <c>InvokeDiedEvent</c> → <c>Hook.AfterDeath</c> BEFORE
    /// stripping the creature's powers, so <see cref="Powers.ForgedSummonPower.AfterDeath"/> still sees its spec and
    /// runs the rattle). force: true so the sacrifice can't be refused by a death-prevention effect. No summon out →
    /// a logged no-op; the rest of the card still resolves.</summary>
    internal static async Task SacrificeSummon(Player owner, int summonClass)
    {
        var pet = FindLivingSummon(owner, summonClass);
        if (pet == null) { MainFile.Logger.Info("[AV] sacrifice_summon: no summon (no-op)."); return; }
        string name = (pet.Monster as Powers.ForgedSummon)?.Source?.Name ?? "summon";
        MainFile.Logger.Info($"[AV] sacrifice_summon '{name}' (HP {pet.CurrentHp}).");
        await CreatureCmd.Kill(pet, true);
        Powers.ForgedSummon.LayoutPets(owner);
    }

    /// <summary>The player's currently-living forged summon for <paramref name="summonClass"/>, or null. With
    /// <paramref name="name"/> null this is "YOUR SUMMON" — the FRONT-most living minion of the class, which is what
    /// every card op except <c>summon</c> means (summon_attack / buff_summon / heal_summon / shield_summon /
    /// sacrifice_summon all act on the front-most one, exactly as the meat-shield redirect picks the front-most
    /// attackable one). Phase AV (v52): pass a <paramref name="name"/> (case-insensitive, trimmed) to find ONE
    /// specific pool entry — the <c>summon</c> op does that, so summoning a second, differently-named minion adds it
    /// to the board instead of growing the first. Sourced from the authoritative combat ally list (like OstyCmd).</summary>
    internal static Creature? FindLivingSummon(Player player, int summonClass, string? name = null)
    {
        string? want = string.IsNullOrWhiteSpace(name) ? null : name!.Trim().ToLowerInvariant();
        return player.Creature.CombatState?.Allies.FirstOrDefault(
            c => c.IsAlive && c.Monster is Powers.ForgedSummon fs && fs.OwnerClass == summonClass
                 && (want == null || (fs.Source?.Name ?? "").Trim().ToLowerInvariant() == want));
    }

    /// <summary>Phase AC (gap #2): heal / shield the class's living summon — CARD path. Resolves the class from the
    /// card's <see cref="IForgedSummonHost"/>; a non-summon-class card or no living summon is a logged no-op.</summary>
    internal static async Task HealOrShieldSummon(ConstructedCardModel card, string op, int amount)
    {
        if (card is IForgedSummonHost host && ForgedCharacters.IsSummonClass(host.SummonClass))
            await HealOrShieldSummonFor(card.Owner, host.SummonClass, op, amount);
        else
            MainFile.Logger.Info($"[AC] {op}: not a summon class (no-op).");
    }

    /// <summary>Phase AC (gap #2): shared executor — heal (<see cref="CreatureCmd.Heal"/>) or grant Block
    /// (<see cref="CreatureCmd.GainBlock"/>, the same path a summon's own block move uses) to the player's living
    /// summon for <paramref name="summonClass"/>. No summon out → logged no-op. Shared by the card + trigger paths.</summary>
    internal static async Task HealOrShieldSummonFor(Player owner, int summonClass, string op, int amount)
    {
        var pet = FindLivingSummon(owner, summonClass);
        string name = (pet?.Monster as Powers.ForgedSummon)?.Source?.Name ?? "summon";
        if (pet == null) { MainFile.Logger.Info($"[AC] {op}: no summon (no-op)."); return; }
        int amt = Math.Max(1, amount);
        if (op == "heal_summon")
        {
            await CreatureCmd.Heal(pet, amt, true);
            MainFile.Logger.Info($"[AC] heal_summon {amt} -> '{name}'.");
        }
        else
        {
            await CreatureCmd.GainBlock(pet, amt, ValueProp.Move, null, false);
            MainFile.Logger.Info($"[AC] shield_summon {amt} -> '{name}'.");
        }
    }

    /// <summary>A self-buff lands on the player; a debuff lands on each resolved enemy target, attributed to the
    /// player. Mirrors the buff/debuff split in <see cref="SummonRunner"/>.</summary>
    private static async Task ApplyRelicStatus(string? status, PlayerChoiceContext ctx, Player player,
                                               List<Creature> targets, int amount, string hookTarget = "self")
    {
        if (SelfBuffStatuses.Contains(status ?? ""))
        {
            await RelicApply(status, ctx, player.Creature, player.Creature, amount);
            return;
        }
        // Phase AS (v48): a debuff on a SELF-target hook lands on the owner (the "you gain 1 Weak" drawback). Keyed on the
        // hook's declared target, never on an empty target list — an enemy-target debuff with no live enemy stays a no-op.
        if (hookTarget == "self")
        {
            MainFile.Logger.Info($"[AS] self-debuff {status} {amount} (relic drawback).");
            await RelicApply(status, ctx, player.Creature, player.Creature, amount);
            return;
        }
        foreach (var t in targets)
            await RelicApply(status, ctx, t, player.Creature, amount);
    }

    private static Task RelicApply(string? status, PlayerChoiceContext ctx, Creature target, Creature source, int amount) =>
        status switch
        {
            "vulnerable"     => RelicApplyT<VulnerablePower>(ctx, target, source, amount),
            "weak"           => RelicApplyT<WeakPower>(ctx, target, source, amount),
            "frail"          => RelicApplyT<FrailPower>(ctx, target, source, amount),
            "poison"         => RelicApplyT<PoisonPower>(ctx, target, source, amount),
            "strength"       => RelicApplyT<StrengthPower>(ctx, target, source, amount),
            "dexterity"      => RelicApplyT<DexterityPower>(ctx, target, source, amount),
            "thorns"         => RelicApplyT<ThornsPower>(ctx, target, source, amount),
            "regen"          => RelicApplyT<RegenPower>(ctx, target, source, amount),
            "metallicize"    => RelicApplyT<PlatingPower>(ctx, target, source, amount),
            "artifact"       => RelicApplyT<ArtifactPower>(ctx, target, source, amount),
            "buffer"         => RelicApplyT<BufferPower>(ctx, target, source, amount),
            "intangible"     => RelicApplyT<IntangiblePower>(ctx, target, source, amount),
            "ritual"         => RelicApplyT<RitualPower>(ctx, target, source, amount),
            "blur"           => RelicApplyT<BlurPower>(ctx, target, source, amount),
            "temp_strength"  => RelicApplyT<ForgedTempStrengthPower>(ctx, target, source, amount),
            "temp_dexterity" => RelicApplyT<ForgedTempDexterityPower>(ctx, target, source, amount),
            "barricade"      => RelicApplyT<BarricadePower>(ctx, target, source, amount),
            "focus"          => RelicApplyT<FocusPower>(ctx, target, source, amount),
            "temp_thorns"    => RelicApplyT<ForgedTempThornsPower>(ctx, target, source, amount), // Phase AN (v44)
            "temp_focus"     => RelicApplyT<ForgedTempFocusPower>(ctx, target, source, amount),  // Phase AN (v44)
            _ => Task.CompletedTask,
        };

    private static Task RelicApplyT<T>(PlayerChoiceContext ctx, Creature target, Creature source, int amount)
        where T : PowerModel
        => BetaMainCompatibility.PowerCmd_.Apply.InvokeGeneric<Task<T?>, T>(
               null, ctx, target, (decimal)amount, source, (CardModel?)null, false)!;
}
