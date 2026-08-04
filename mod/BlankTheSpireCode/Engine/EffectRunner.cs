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
                    if (e.HasGrow) // Phase U (gap #23) smoke logging: prove per-play growth (plays so far = count)
                    {
                        int plays = PlaysThisCombat(card);
                        MainFile.Logger.Info($"[U] grow damage: base {amt} + grow {e.Grow}×{plays} = {amt + e.Grow * plays} (play #{plays + 1} of '{card.Id}').");
                    }
                    // Hold the command so we can read its per-hit/per-target DamageResults after it resolves — the
                    // unblocked total feeds a later damage_dealt_unblocked heal (Phase P gap #21, lifesteal).
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
                    await CommonActions.CardBlock(card, play);
                    break;
                case "draw":
                    // A scaled draw (F5: x / cards_in_hand / cards_retained / unspent_energy_last_turn) has no
                    // fixed Cards var; resolve the live scalar here and draw that many. CommonActions.Draw only
                    // reads a fixed Cards var, so the unscaled path keeps using the card's Cards var as before.
                    if (e.IsScaled) await CardPileCmd.Draw(ctx, ResolveScaleAmount(e, card), card.Owner);
                    else await CommonActions.Draw(card, ctx);
                    break;
                case "apply_status":
                    await ApplyStatus(e.Status, card, ctx, play);
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
                case "forge":
                    // Phase M (gap #36): stoke the player-level Forge counter (a stacking power). The payoff
                    // is a damage/block effect with scale:"forged", which ADDS the stacks to its printed amount.
                    // Phase T: Stoke also SUMMONS the class blade to hand on the first Forge of combat.
                    await ForgedForgePower.Stoke(ctx, card.Owner, Math.Max(1, amt));
                    MainFile.Logger.Info($"[M] forge +{Math.Max(1, amt)} (card) -> Forge {ForgeStacks(card.Owner)}.");
                    break;
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
                    // payload fires only when the card is effect-discarded (DataCard.FireOnDiscard).
                    if (e.Trigger != "on_discard" && card is IForgedTriggerHost host)
                        await host.ApplyTrigger(ctx, card.Owner);
                    break;
                case "discard":
                    // Phase R (gap #17): discard `amt` RANDOM cards from hand, then fire each discarded card's
                    // on_discard payload (effect-driven — turn-end cleanup never routes through here).
                    await DiscardRandom(amt, card.Owner, ctx);
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

    // Phase R (gap #17): re-entrancy guard — a discard INSIDE an on_discard payload must not cascade on_discard
    // (the cards still discard; their on_discard payoffs just don't fire recursively). Static: one discard
    // resolves fully before the next, so a single flag is enough.
    private static bool _firingOnDiscard;

    /// <summary>Phase R (gap #17): discard <paramref name="n"/> RANDOM cards from <paramref name="owner"/>'s hand
    /// (choiceless — the player-choice variant needs the un-dumped CardSelectCmd UI), then fire each discarded
    /// card's <c>on_discard</c> payload. Shared by the card path (Execute) and the trigger path (TriggerRunner).
    /// on_discard is EFFECT-DRIVEN: it fires ONLY from here, so turn-end hand cleanup (game-driven, never routed
    /// through this) never triggers it. A discard nested inside an on_discard payload is suppressed (no cascade).
    /// Random picks use the run's card-selection RNG stream (seed-correct; no desync with card/other RNG).</summary>
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
        await CardCmd.Discard(ctx, chosen);
        MainFile.Logger.Info($"[R] discard x{chosen.Count} (random from hand).");
        await FireOnDiscardFor(chosen, ctx);
    }

    /// <summary>Phase R (gap #17): fire the on_discard (Reflex) payoff for each just-EFFECT-discarded card — but
    /// NOT for discards nested inside an on_discard payload (no cascade; the <c>_firingOnDiscard</c> guard). Shared
    /// by <see cref="DiscardRandom"/> (Phase R) and <see cref="Scry"/> (Phase AA — a scry-discard is an effect
    /// discard too). Turn-end hand cleanup is game-driven and never routes through here, so it never fires.</summary>
    private static async Task FireOnDiscardFor(IReadOnlyList<CardModel> discarded, PlayerChoiceContext ctx)
    {
        if (_firingOnDiscard) return;
        _firingOnDiscard = true;
        try
        {
            foreach (var c in discarded)
                if (c is DataCard dc) await dc.FireOnDiscard(ctx);
        }
        finally { _firingOnDiscard = false; }
    }

    /// <summary>Phase AA (gap #17 R-2): SCRY — look at the top <paramref name="n"/> cards of the DRAW pile and
    /// discard any subset the player picks. Slices the top N (<c>DrawPile.Cards[0]</c> is the top —
    /// <c>CardPilePosition.Top =&gt; 0</c>), shows them in a grid via <c>CardSelectCmd.FromSimpleGrid</c> with
    /// min 0 / max N (so "discard none" is a legal choice), then discards the picked subset
    /// (<c>CardCmd.Discard</c> → moves draw→discard) and fires their <c>on_discard</c> payoffs. Empty draw pile is
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
        await CardCmd.Discard(ctx, toDiscard);
        MainFile.Logger.Info($"[AA] scry {take} -> discarded {toDiscard.Count} of the top {take}.");
        await FireOnDiscardFor(toDiscard, ctx);
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
        _ => 0,
    };

    /// <summary>Phase P (gap #22): count of DEBUFF powers on <paramref name="target"/> (0 if null). Read by the
    /// <c>target_debuff_count</c> calc-var (<see cref="DataCard"/>.BonusFor) at attack resolution, once per struck
    /// target — so an AoE flechette hits each enemy for that enemy's own debuff count. NOT a player-state read, so
    /// it never routes through <see cref="ScaleValue"/> (which has no target). Counts the game's four debuff
    /// powers (the closed debuff vocabulary this mod applies — mirrors EnemyDebuffStatuses / Conditions'
    /// target_has_status checks) via the same HasPower&lt;T&gt; path, each present debuff = 1 (not its stacks).</summary>
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
                                             List<Creature> targets, int relicClass)
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
                    await ApplyRelicStatus(e.Status, ctx, player, targets, amt);
                    break;
                case "forge":
                    // Phase M (gap #36): relic-side Forge income — the "smoldering heirloom" keystone.
                    // Phase T: a turn-1 relic Forge summons the blade too (Stoke centralizes all three paths).
                    await ForgedForgePower.Stoke(ctx, player, Math.Max(1, amt));
                    MainFile.Logger.Info($"[M] forge +{amt} (relic) -> Forge {ForgeStacks(player)}.");
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
    /// ("random" rolls within the pool, falling back to lightning). Shared by the card and relic channel_orb ops.</summary>
    internal static async Task ChannelForgedOrbs(int orbClass, string? orb, int count, Player owner, PlayerChoiceContext ctx)
    {
        for (int n = 0; n < count; n++)
        {
            Type orbType = (orb == "random"
                               ? ForgedCharacters.RandomOrbType(orbClass, owner)
                               : ForgedCharacters.ResolveOrbType(orbClass, orb)) ?? OrbTypeFor("lightning");
            await OrbCmd.Channel(ctx, ((OrbModel)ModelDb.Get(orbType)).ToMutable(0), owner);
        }
    }

    /// <summary>The base-game Osty Summon keyword for a forged class: ONE minion per class. If the class's minion
    /// is already alive, raise its Max HP by <paramref name="amount"/> (Osty's "Summon while alive" — the user's
    /// "increase XP"); otherwise summon a fresh one with that HP, heal it, and apply the meat-shield. The minion is
    /// PASSIVE — it does nothing on its own turn (its move list is empty); the class's <c>summon_attack</c> cards
    /// strike through it. Shared by the card summon op and the relic summon op. <paramref name="amount"/> = HP (0 /
    /// omitted ⇒ the summon's spec MaxHp). Mirrors the decompiled <c>OstyCmd.Summon</c> (fresh-summon-when-none-alive
    /// instead of reviving a kept corpse — functionally identical, no keep-corpse power needed).</summary>
    internal static async Task SummonForged(int summonClass, string? name, int amount, Player player, PlayerChoiceContext ctx)
    {
        var type = ForgedCharacters.ResolveSummonType(summonClass, name);
        if (type == null) { MainFile.Logger.Warn($"[Forged] summon: class {summonClass} has no summon '{name}'."); return; }
        var model = (MonsterModel)ModelDb.Get(type);
        int hp = amount >= 1 ? amount : Math.Max(1, (model as Powers.ForgedSummon)?.Source?.MaxHp ?? 10);

        // Already on board → just grow its Max HP (the Summon keyword while alive). No second pet.
        var existing = FindLivingSummon(player, summonClass);
        if (existing != null)
        {
            await CreatureCmd.GainMaxHp(existing, hp);
            return;
        }

        // None alive → summon fresh at `hp`, heal to full, then meat-shield + layout.
        var pet = player.Creature.CombatState.CreateCreature(model.ToMutable(), player.Creature.Side, null);
        player.PlayerCombatState.AddPetInternal(pet);
        await CreatureCmd.Add(pet);
        await CreatureCmd.SetMaxHp(pet, hp);
        await CreatureCmd.Heal(pet, hp, true);
        await Powers.ForgedSummonPower.Apply(ctx, pet);   // passive marker/host (empty move list ⇒ acts on no turn)
        pet.Died += _ => Powers.ForgedSummon.LayoutPets(player);
        // Meat shield: redirect the player's incoming powered hits to the living minion (Osty's DieForYou).
        await Powers.ForgedSummonShieldPower.Apply(ctx, player.Creature);
        Powers.ForgedSummon.LayoutPets(player); // non-Osty pets spawn on top of the player → lay out to the right
    }

    /// <summary>The player's currently-living forged summon for <paramref name="summonClass"/>, or null. True-Osty:
    /// a class has at most one on board at a time. Sourced from the authoritative combat ally list (like OstyCmd).</summary>
    internal static Creature? FindLivingSummon(Player player, int summonClass) =>
        player.Creature.CombatState?.Allies.FirstOrDefault(
            c => c.IsAlive && c.Monster is Powers.ForgedSummon fs && fs.OwnerClass == summonClass);

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
                                               List<Creature> targets, int amount)
    {
        if (SelfBuffStatuses.Contains(status ?? ""))
        {
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
            _ => Task.CompletedTask,
        };

    private static Task RelicApplyT<T>(PlayerChoiceContext ctx, Creature target, Creature source, int amount)
        where T : PowerModel
        => BetaMainCompatibility.PowerCmd_.Apply.InvokeGeneric<Task<T?>, T>(
               null, ctx, target, (decimal)amount, source, (CardModel?)null, false)!;
}
