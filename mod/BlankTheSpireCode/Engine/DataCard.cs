using System.Linq;
using BaseLib.Abstracts;
using BaseLib.Extensions;
using BaseLib.Utils;
using BlankTheSpire.BlankTheSpireCode.Character;
using BlankTheSpire.BlankTheSpireCode.Extensions;
using BlankTheSpire.BlankTheSpireCode.Powers;
using MegaCrit.Sts2.Core.Entities.Cards;
using MegaCrit.Sts2.Core.Entities.Creatures;
using MegaCrit.Sts2.Core.GameActions.Multiplayer;
using MegaCrit.Sts2.Core.Models;
using MegaCrit.Sts2.Core.Models.Powers;

namespace BlankTheSpire.BlankTheSpireCode.Engine;

/// <summary>
/// Shared base for every data-defined / LLM-generated card. A generated card is just:
///   <c>public sealed class Strike : DataCard { ... static CardSpec Spec ...; public Strike() : base(Spec) {} }</c>
/// The constructor DECLARES each effect as a DynamicVar (via ConstructedCardModel's protected With*
/// builders, so card text/preview/upgrade all work); OnPlay EXECUTES the effects via EffectRunner.
/// All real logic stays here + in EffectRunner - generated classes carry only data.
/// </summary>
[Pool(typeof(BlankTheSpireCardPool))]
public abstract class DataCard : ConstructedCardModel
{
    protected readonly CardSpec Spec;

    /// <summary>Phase T: is this the forge class's signature blade (a non-drafted TOKEN)? Read across combat
    /// piles by <see cref="ForgedForgePower.SummonBlade"/> to find an already-summoned blade (Spec is protected,
    /// so the summon guard can't read it directly).</summary>
    internal bool SpecIsToken => Spec.IsToken;

    /// <summary>Phase AH (gaps #35/#38): this card's stable SPEC id (the class-card id, e.g. the same string
    /// <c>transform_card</c>'s <c>card_id</c> names). Read by <see cref="EffectRunner.TransformCard"/> to identify
    /// the played card + find its in-hand sibling clones (Spec is protected, so the transform can't read it directly).
    /// A generated combat copy keeps its source card's Spec, so <c>SpecId</c> stays the class-card id.</summary>
    internal string SpecId => Spec.Id;

    /// <summary>Phase AE (gap #25): does this card declare <paramref name="tag"/>? Read across combat piles by
    /// <see cref="EffectRunner.TagCardsOwned"/> (Spec is protected, so the deck scan can't read Tags directly).</summary>
    internal bool SpecHasTag(string? tag) => Spec.HasTag(tag);

    /// <summary>Phase T: the signature blade is never Attack-Potion/Discovery-generated in combat (it only ever
    /// enters play via the first-Forge summon or the <c>summon_blade</c> op). Closes CardFactory.FilterForCombat,
    /// which excludes Basic/Ancient/Event but NOT Token — see the token-rarity note in the ctor.</summary>
    public override bool CanBeGeneratedInCombat => !Spec.IsToken && base.CanBeGeneratedInCombat;

    /// <summary>The CalculatedVar bonus for a SCALED damage/block effect (F5): its value resolves to the live
    /// scalar (x / cards_in_hand / cards_retained / unspent_energy_last_turn) at evaluation time via the same
    /// <see cref="EffectRunner.ScaleValue"/> the executor uses — so "Deal damage equal to …" tracks live and on
    /// play, and the tooltip preview matches what actually resolves. Phase M (gap #36): <c>scale:"forged"</c>
    /// is the ADDITIVE exception — the bonus is the printed amount (upgrade-aware) PLUS the player's Forge
    /// stacks, so the payoff is never a dead card before forge income comes online.</summary>
    private static Func<CardModel, Creature?, decimal> BonusFor(EffectSpec e, int up) =>
        e.Scale == "forged"
            // Phase AF (gap #41): the blade's forged total is ×N this turn when the empower power is up (token-scoped
            // — BladeMultiplier returns 1 for any non-blade forged payoff). The calc-var re-evaluates each preview/
            // resolve, so applying blade_empower mid-turn updates the blade's shown + dealt damage immediately.
            ? (c, _) => (e.Amount + (c.IsUpgraded ? up : 0) + EffectRunner.ScaleValue("forged", c)) * EffectRunner.BladeMultiplier(c)
            // Phase P (gap #22): target_debuff_count resolves per STRUCK TARGET — the calc-var's second arg is the
            // attack's current target, so an AoE flechette computes each enemy's own debuff count (preview + resolve).
            : e.Scale == "target_debuff_count"
                ? (_, tgt) => EffectRunner.DebuffCount(tgt)
                // Phase AE (gap #25): tag_cards_owned is ADDITIVE like forged (printed amount + the count of cards
                // carrying e.Tag across your piles), so the payoff is never dead and the in-hand preview tracks live.
                : e.Scale == "tag_cards_owned"
                    ? (c, _) => e.Amount + (c.IsUpgraded ? up : 0) + EffectRunner.TagCardsOwned(c.Owner, e.Tag)
                    : (c, _) => EffectRunner.ScaleValue(e.Scale, c);

    /// <summary>Phase U (gap #23, Rampage): the calc-var for a <c>grow</c> damage op. Current damage =
    /// printed amount (upgrade-aware) + <c>Grow</c> × the times THIS card instance was played earlier this
    /// combat. First play = printed amount (the in-flight play isn't in the finished-plays history yet); the
    /// in-hand preview updates as the count climbs. Per-card-instance + per-combat reset ride the combat history.</summary>
    private static Func<CardModel, Creature?, decimal> GrowBonusFor(EffectSpec e, int up) =>
        (c, _) => e.Amount + (c.IsUpgraded ? up : 0) + e.Grow * EffectRunner.PlaysThisCombat(c);

    protected DataCard(CardSpec spec)
        // An empty forged slot self-registers nothing: showInCardLibrary:false keeps it out of the
        // compendium and autoAdd:false keeps it out of the reward pool, so unfilled slots are invisible
        // until JSON fills them (then a normal card registers as usual).
        // A TOKEN card (the forge class's Sovereign Blade, spec.IsToken) is hidden from the compendium
        // (showInCardLibrary:false) but MUST still be pool-registered (autoAdd:true). autoAdd is NOT just a
        // "reward pool" flag: a card that is in NO CardPoolModel cannot be resolved by CardModel.get_Pool()
        // (it scans ModelDb.AllCardPools, finds nothing, then probes MockCardPool — whose AllCards throws
        // "You monster!"). A token is SUMMONED to hand on the first Forge of combat (Phase T; legacy v20-v24
        // blades are innate + deck-seeded) and IS drawn/rendered, which reads card.Pool for the energy-cost
        // color, so an unpooled token faults the draw task and hangs combat (found in-game on "Foundry Rot",
        // whose Smoghammer is token + innate + basic). The blade stays OUT of rewards by being Token rarity
        // (Phase T; base-game tokens are), which CardFactory never rolls for a merchant / non-uniform reward,
        // combined with CanBeGeneratedInCombat:false below (blocks Attack-Potion/Discovery-style combat
        // generation). The one residual path is a Uniform-odds card reward (filters only Basic/Ancient, not
        // Token) — rare enough to accept; if it ever surfaces, fall back to "basic" rarity (also excluded
        // everywhere, per FORGE_SUMMON_BLADE_PLAN decision #8).
        // X-cost cards carry spec.Cost = 0 here; the real X cost is applied in the body via MockSetEnergyCost.
        // (Passing -1 does NOT make a card X-cost — the game then throws "does not have an X-cost" the moment
        // anything resolves X, freezing the card mid-deal. CostsX must be set explicitly.)
        : base(spec.Cost, spec.Type, spec.Rarity, spec.Target,
               showInCardLibrary: !spec.IsEmpty && !spec.IsToken, autoAdd: !spec.IsEmpty)
    {
        Spec = spec;
        // Mark X-cost BEFORE anything previews the card: a CalculatedDamage/Block var (and the draw-X path)
        // call ResolveEnergyXValue(), which throws unless the card genuinely has CostsX. MockSetEnergyCost is
        // protected on CardModel, so this subclass may call it; the CardEnergyCost ctor is public.
        if (spec.CostsX) MockSetEnergyCost(new CardEnergyCost(this, 0, costsX: true));
        // Phase AG (gap #39): an upgrade that LOWERS the card's energy cost is applied in OnUpgrade (below), NOT here.
        DeclareEffects();
        // Tag the synthesized basic Strike/Defend with CardTag.Strike/Defend so base-game systems that look up a
        // character's basics by tag work for forged classes too. Without this, relics/events that do
        // CardPool.AllCards.First(c => c.Rarity == Basic && c.Tags.Contains(CardTag.Strike)) — e.g. LargeCapsule,
        // PandorasBox — throw "Sequence contains no matching element" and soft-lock (a forged class's untagged
        // Strike/Defend matched nothing). The synthesized basics are named exactly "Strike"/"Defend" at Basic rarity
        // (class_forge `_synthesize_basic`); a forged Basic SIGNATURE card is named otherwise, so it stays untagged.
        if (spec.Rarity == CardRarity.Basic)
        {
            if (spec.Title == "Strike") WithTags(CardTag.Strike);
            else if (spec.Title == "Defend") WithTags(CardTag.Defend);
        }
    }

    /// <summary>
    /// In-code localization (BaseLib <see cref="ILocalizationProvider"/>): forged-slot cards carry their
    /// name/text in the spec and inject it at <c>ModelDb.Init</c> — no .pck rebuild. Baked codegen cards
    /// leave Title null and fall back to the shipped .pck cards.json table.
    /// </summary>
    public override List<(string, string)>? Localization =>
        Spec.Title != null ? (List<(string, string)>)new CardLoc(Spec.Title, Spec.Description ?? "") : null;

    private void DeclareEffects()
    {
        for (int i = 0; i < Spec.Effects.Length; i++)
        {
            var e = Spec.Effects[i];
            int up = EffectRunner.UpgradeDelta(Spec, i);
            switch (e.Op)
            {
                case "damage":
                    // Scaled (F5) → damage var = the live scalar; CommonActions.CardAttack auto-reads CalculatedDamage.
                    // Phase U (gap #23): a `grow` damage is ALSO a calc-var (amount + grow×plays_this_combat), so the
                    // in-hand preview + resolved hit both track the live count. grow ⊥ scale (validator-enforced).
                    if (e.HasGrow) WithCalculatedDamage(0, GrowBonusFor(e, up));
                    else if (e.IsScaled) WithCalculatedDamage(0, BonusFor(e, up));
                    else WithDamage(e.Amount, up); // per-hit damage
                    // Multi-hit: a "Hits" var carries the count (upgrade-aware, shown as {Hits} in text).
                    // Single-hit (Hits<=1) declares no var, so EffectRunner defaults to 1 — unchanged path.
                    if (e.Hits > 1) WithVar("Hits", e.Hits, EffectRunner.HitsUpgradeDelta(Spec, i));
                    break;
                case "block":
                    if (e.IsScaled) WithCalculatedBlock(0, BonusFor(e, up)); // block = scalar; CardBlock auto-reads CalculatedBlock
                    else WithBlock(e.Amount, up);
                    break;
                case "draw":
                    if (!e.IsScaled) WithCards(e.Amount, up); // a scaled draw resolves the scalar at play time (no fixed var)
                    break;
                case "gain_energy": WithEnergy(e.Amount, up); break;   // var "Energy" + energy tooltip
                // Phase P (gap #21): a scaled heal (damage_dealt_unblocked lifesteal) has no fixed var — it
                // resolves at execution from the unblocked damage dealt, like the scaled-draw path above.
                case "heal":        if (!e.IsScaled) WithHeal(e.Amount, up); break;     // var "Heal"
                case "lose_hp":     WithVar("Loss", e.Amount, up); break; // generic var "Loss"
                case "discard":     WithVar("Discard", e.Amount, up); break; // Phase R (gap #17): random-discard count
                case "scry":        WithVar("Scry", e.Amount, up); break;    // Phase AA (gap #17 R-2): top-of-draw look count
                case "exhaust":     WithKeyword(CardKeyword.Exhaust); break;   // keyword: game exhausts on play
                case "innate":      WithKeyword(CardKeyword.Innate); break;    // keyword: starts in opening hand
                case "retain":      WithKeyword(CardKeyword.Retain); break;    // keyword: not discarded at end of turn
                case "ethereal":    WithKeyword(CardKeyword.Ethereal); break;  // keyword: exhausts if still in hand
                case "gain_orb_slot":         // Phase G orbs: executed in OnPlay; counts shown via Describe (no var)
                case "channel_orb":
                case "evoke":
                case "forge":                 // Phase M (gap #36): stokes the Forge power in OnPlay (literal, no var)
                case "balance_step":          // Phase S (gap #1): moves the Balance gauge in OnPlay (literal, no var)
                case "add_trigger":           // Phase H3: grants a power in OnPlay; text via Describe (no card var)
                case "apply_status_custom":   // Phase J: applies a forged status in OnPlay (literal amount, no var)
                case "summon":                // Phase K: summons a forged minion in OnPlay (literal amount, no var)
                case "summon_attack":         // Phase K (true-Osty): summon deals damage in OnPlay (literal, no var)
                case "buff_summon":           // Phase K (true-Osty): buffs the summon in OnPlay (literal, no var)
                case "heal_summon":           // Phase AC (gap #2): heals the summon in OnPlay (literal, no var)
                case "shield_summon":         // Phase AC (gap #2): shields the summon in OnPlay (literal, no var)
                case "add_card":              // Phase Q (gap #16): generates card copies in OnPlay (no card var)
                case "summon_blade":          // Phase T: retrieves the class blade to hand in OnPlay (no card var)
                case "upgrade_card":          // Phase V/X (gap #18): upgrades hand cards in OnPlay — random/all/choose (no card var)
                case "purge":                 // Phase W (gap #19): run-deck removal in OnPlay + pile override (no card var); text via Describe
                case "purge_card":            // Phase Z (gap #19 choose): pick-a-hand-card purge in OnPlay (no card var); text via Describe
                case "corruption":            // Phase AB (gap #20): grants the Corruption power in OnPlay (no card var); text via Describe
                case "blade_empower":         // Phase AF (gap #41): applies the one-turn blade multiplier in OnPlay (literal, no var)
                case "transform_card":        // Phase AH (gaps #35/#38): run-permanent self-transform in OnPlay (no card var); text via Describe
                case "graft_card":            // Phase AI (gap #7): pick-a-hand-card + transform the pick in OnPlay (no card var); text via Describe
                case "summon_spike":          // PHASE K SPIKE: summons a pet in OnPlay (literal amount, no var)
                case "apply_custom":  break;   // EXPLORE SPIKE: applies a custom power in OnPlay (literal amount, no var)
                case "apply_status":
                    switch (e.Status)
                    {
                        case "vulnerable":     WithPower<VulnerablePower>(e.Amount, up); break;
                        case "weak":           WithPower<WeakPower>(e.Amount, up); break;
                        case "frail":          WithPower<FrailPower>(e.Amount, up); break;
                        case "poison":         WithPower<PoisonPower>(e.Amount, up); break;
                        case "strength":       WithPower<StrengthPower>(e.Amount, up); break;
                        case "dexterity":      WithPower<DexterityPower>(e.Amount, up); break;
                        case "thorns":         WithPower<ThornsPower>(e.Amount, up); break;
                        case "regen":          WithPower<RegenPower>(e.Amount, up); break;
                        case "metallicize":    WithPower<PlatingPower>(e.Amount, up); break;
                        case "artifact":       WithPower<ArtifactPower>(e.Amount, up); break;
                        case "buffer":         WithPower<BufferPower>(e.Amount, up); break;
                        case "intangible":     WithPower<IntangiblePower>(e.Amount, up); break;
                        case "ritual":         WithPower<RitualPower>(e.Amount, up); break;
                        case "blur":           WithPower<BlurPower>(e.Amount, up); break;
                        case "temp_strength":  WithPower<ForgedTempStrengthPower>(e.Amount, up); break;
                        case "temp_dexterity": WithPower<ForgedTempDexterityPower>(e.Amount, up); break;
                        case "barricade":      WithPower<BarricadePower>(e.Amount, up); break;
                        case "focus":          WithPower<FocusPower>(e.Amount, up); break;
                        default:
                            throw new NotSupportedException($"DataCard: unsupported status '{e.Status}'");
                    }
                    break;
                default:
                    throw new NotSupportedException($"DataCard: unsupported op '{e.Op}'");
            }
        }
    }

    protected override async Task OnPlay(PlayerChoiceContext choiceContext, CardPlay play)
        => await EffectRunner.Execute(Spec, this, choiceContext, play);

    /// <summary>Phase AG (gap #39): an upgrade that LOWERS the card's energy cost. This overrides the game's
    /// DESIGNED per-instance upgrade hook (CardModel.OnUpgrade — called inside UpgradeInternal, right before
    /// DynamicVars.RecalculateForUpgradeOrEnchant + Upgraded?.Invoke). It is the clone-safe application point:
    /// the constructor's <c>Upgraded +=</c> event was INERT in-game because CardModel.AfterCloned() nulls EVERY
    /// event field (Upgraded/Drawn/Played/EnergyCostChanged/…) on a cloned card, and every card the player holds
    /// (run deck + combat hand) is a clone — so the event never fired for the instance actually being upgraded.
    /// A virtual method survives cloning, and UpgradeInternal calls it on the real instance for BOTH a live
    /// in-combat upgrade (upgrade_card / CardCmd.Upgrade) AND the replay of a run-deck card's stored upgrade level.
    /// We use the game's intended cost-upgrade API — <see cref="CardEnergyCost.UpgradeBy"/> (base-game precedent:
    /// SummonForth.OnUpgrade uses the DynamicVar equivalent) — which adds a delta (here uc - Cost, ≤ 0), clamps at
    /// 0, sets WasJustUpgraded for the green upgrade preview, and pairs with the EnergyCost.FinalizeUpgrade() the
    /// game already calls in FinalizeUpgradeInternal. It also self-invokes EnergyCostChanged (via SetCustomBaseCost),
    /// so no manual InvokeEnergyCostChanged is needed. MaxUpgradeLevel is 1 for our cards, so this fires once — no
    /// idempotency flag. Downgrade needs nothing here: DowngradeInternal calls EnergyCost.ResetForDowngrade().</summary>
    protected override void OnUpgrade()
    {
        base.OnUpgrade();
        if (Spec.UpgradedCost is { } uc && !Spec.CostsX && IsUpgraded)
        {
            EnergyCost.UpgradeBy(uc - Spec.Cost); // delta ≤ 0; UpgradeBy clamps the result at 0
            MainFile.Logger.Info($"[AG] upgrade cost: '{Spec.Id}' {Spec.Cost} -> {uc}.");
        }
    }

    /// <summary>Phase W (gap #19): a <c>purge</c> card goes to NO combat pile when played (a stronger exhaust) —
    /// the run-deck removal that makes it run-permanent happens in EffectRunner's purge case (on the card's
    /// <c>DeckVersion</c>). We OWN this CardModel subclass, so an override is cleaner + safer than BaseLib's
    /// generic Harmony <c>PurgePatch</c> (which we don't rely on being active — §0.5). Power cards already
    /// return None; this covers Attack/Skill purge cards. base() preserves exhaust/discard behaviour for the rest.</summary>
    protected override PileType GetResultPileTypeForCardPlay()
        => Spec.HasPurge ? PileType.None : base.GetResultPileTypeForCardPlay();

    // Phase R (gap #17): the combat round this card last fired its on_discard payload — for the once_per_turn
    // gate. Per-instance state (the CardModel persists across pile moves within a combat); -1 = never fired.
    private int _onDiscardLastRound = -1;

    /// <summary>Phase R (gap #17): if this card carries an <c>on_discard</c> trigger, run its payload NOW —
    /// it was just discarded BY AN EFFECT (the mod's discard op; see <see cref="EffectRunner.DiscardRandom"/>).
    /// This is CARD-LATENT (Reflex): the payload never fires on play (the add_trigger grants no power) nor at
    /// turn-end cleanup (that never routes through DiscardRandom). Honors the fire-time <c>When</c> and
    /// <c>once_per_turn</c> (tracked by combat round, so a discard→redraw→discard within one turn fires once).</summary>
    internal async Task FireOnDiscard(PlayerChoiceContext ctx)
    {
        var t = Spec.Effects.FirstOrDefault(e => e.Op == "add_trigger" && e.Trigger == "on_discard");
        if (t == null || Owner == null) return;
        if (t.When != null && !Conditions.Evaluate(t.When, Owner, null)) return;
        if (t.OncePerTurn)
        {
            int round = Owner.Creature.CombatState.RoundNumber;
            if (_onDiscardLastRound == round) return; // already fired this turn
            _onDiscardLastRound = round;
        }
        MainFile.Logger.Info($"[R] on_discard fired ('{Spec.Title ?? Spec.Id}').");
        await TriggerRunner.Run(t, Owner, ctx);
    }

    // Placeholder art per card TYPE (attack/skill/power doodles from mod/tools/gen_placeholder_card_art.py),
    // so a hand of generated cards reads at a glance. CardImagePath()/BigCardImagePath() still fall back to
    // the shared card.png if a per-type file is missing. Per-card art comes later.
    private string TypePlaceholder => Spec.Type switch
    {
        CardType.Attack => "card_attack.png",
        CardType.Power => "card_power.png",
        _ => "card_skill.png",
    };
    public override string CustomPortraitPath => TypePlaceholder.BigCardImagePath();
    public override string PortraitPath => TypePlaceholder.CardImagePath();
    public override string BetaPortraitPath => TypePlaceholder.CardImagePath();
}
