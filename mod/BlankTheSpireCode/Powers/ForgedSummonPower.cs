using System.Collections.Generic;
using BaseLib.Abstracts;
using BaseLib.Utils;
using BlankTheSpire.BlankTheSpireCode.Engine;
using BlankTheSpire.BlankTheSpireCode.Extensions;
using MegaCrit.Sts2.Core.Combat;
using MegaCrit.Sts2.Core.Entities.Cards;
using MegaCrit.Sts2.Core.Entities.Creatures;
using MegaCrit.Sts2.Core.Entities.Powers;
using MegaCrit.Sts2.Core.GameActions.Multiplayer;
using MegaCrit.Sts2.Core.Models;
using MegaCrit.Sts2.Core.ValueProps;

namespace BlankTheSpire.BlankTheSpireCode.Powers;

/// <summary>
/// Phase K: the per-turn behaviour driver applied to a summoned <see cref="ForgedSummon"/> pet. Player-side
/// creatures are never driven by the combat turn loop, so the minion acts via this power's <c>AfterTurnEnd</c>
/// hook (gated to the player's own side) — the same H3-style mechanism the K-0 spike proved. This is ONE
/// non-generic type: it reads the move list FROM THE PET (<c>Owner.Monster as ForgedSummon</c> → its
/// <see cref="SummonSpec"/>, since <c>ToMutable()</c> preserves the derived type), so it needs no per-slot shells.
/// A turn counter cycles the minion through its moves.
/// </summary>
public sealed class ForgedSummonPower : BlankTheSpirePower
{
    private int _turn;

    // Phase AV (v52): the on_nth_attack counter — how many damage INSTANCES (hits) this minion has dealt since the
    // last payoff. Per-power, so it is per-pet and per-combat (the pet and its powers die with the combat).
    private int _hits;
    // Re-entrancy guard: the payoff itself attacks through the same pet, so its own hits must NOT count toward the
    // next trigger (a 2-hit payoff on n=2 would otherwise re-fire forever). Mirrors ForgedTriggerPower's _firing set.
    private bool _firingNth;

    public override PowerType Type => PowerType.Buff;
    public override PowerStackType StackType => PowerStackType.Single;

    // Reuse a shipped placeholder texture so the behaviour buff isn't a missing-icon blob (no authored art).
    public override string CustomPackedIconPath => "card.png".CardImagePath();
    public override string CustomBigIconPath => "card.png".BigCardImagePath();

    /// <summary>The summon spec driving this power, read off the pet it's attached to (null if not yet owned /
    /// not a ForgedSummon / an unfilled shell).</summary>
    private SummonSpec? Spec => (Owner?.Monster as ForgedSummon)?.Source;

    /// <summary>Grant the driver to the summoned <paramref name="pet"/> (amount 1), via the BaseLib generic apply.</summary>
    public static Task Apply(PlayerChoiceContext ctx, Creature pet)
        => BetaMainCompatibility.PowerCmd_.Apply.InvokeGeneric<Task<ForgedSummonPower?>, ForgedSummonPower>(
               null, ctx, pet, 1m, pet, (CardModel?)null, false)!;

    public override async Task AfterSideTurnEnd(PlayerChoiceContext ctx, CombatSide side, IEnumerable<Creature> participants)
    {
        // Fire only at the end of the minion's OWN side (the player side); skip if it has died.
        if (side != Owner.Side || Owner.IsDead) return;
        var spec = Spec;
        if (spec == null || spec.Moves.Length == 0) return;
        Flash();
        await SummonRunner.RunMove(spec.Moves[_turn % spec.Moves.Length], Owner, ctx);
        _turn++;
    }

    /// <summary>K-3b: the minion's DEATH RATTLE. Fires once when this pet dies (the awaitable in-pipeline death hook,
    /// not the sync <c>Died</c> event — so it's safe to run commands). The minion is gone, so the PLAYER deals the
    /// payload (enemy-facing only; the validator forbids self-target on_death actions).</summary>
    public override async Task AfterDeath(PlayerChoiceContext ctx, Creature creature, bool wasRemovalPrevented, float deathAnimLength)
    {
        if (Owner == null || creature != Owner) return;
        var spec = Spec;
        if (spec?.OnDeath is not { Length: > 0 } death) return;
        var dealer = Owner.PetOwner?.Creature ?? Owner; // the dead minion can't be the dealer → the player retaliates
        // Phase AV (v52): tag the rattle — it is what `sacrifice_summon` cashes in, and the tag is the AutoSlay proof
        // that CreatureCmd.Kill reaches Hook.AfterDeath before the creature's powers are stripped.
        MainFile.Logger.Info($"[AV] on_death rattle '{spec!.Name}': {death.Length} action(s).");
        await SummonRunner.RunActions(death, Owner, ctx, dealer);
    }

    /// <summary>Phase AV (v52): count the damage this MINION deals and fire <c>on_nth_attack</c> every Nth hit.
    /// The hook is dispatched to every combat listener (the pet's powers included — <c>CombatState.IterateHookListeners</c>
    /// walks each ally's Powers), so we filter on <c>dealer == Owner</c>. Counting is PER DAMAGE INSTANCE: a
    /// <c>summon_attack</c> with <c>hits: 2</c> raises a hook per hit, and so does each hit of the minion's own
    /// <c>attack</c> move action — that is the "every Nth hit" the contract promises. A fully-blocked hit still counts
    /// (0 total damage does not), and the payoff's own attacks are excluded by <see cref="_firingNth"/>.</summary>
    public override async Task AfterDamageGiven(PlayerChoiceContext ctx, Creature dealer, DamageResult result,
        ValueProp props, Creature target, CardModel cardSource)
    {
        if (_firingNth || Owner == null || dealer != Owner || Owner.IsDead) return;
        if (result.TotalDamage <= 0) return;
        var spec = Spec;
        if (spec?.OnNthAttack is not { Actions.Length: > 0 } nth) return;
        _hits++;
        if (_hits < nth.N) return;
        _hits = 0;
        MainFile.Logger.Info($"[AV] on_nth_attack '{spec.Name}' fired (hit #{nth.N}).");
        _firingNth = true;
        try { await SummonRunner.RunActions(nth.Actions, Owner, ctx); }
        finally { _firingNth = false; }
    }

    // In-code tooltip for the behaviour buff. This is TYPE-LEVEL loc, registered ONCE at ModelDb.Init before any
    // pet exists, so it must NOT read Owner / the pet (doing so NRE'd at init — there is no canonical owner). The
    // minion's name + per-turn behaviour are shown on the minion itself (ForgedSummon's MonsterLoc + HP bar / its
    // own describe); this buff just labels the driver generically.
    public override List<(string, string)>? Localization =>
        (List<(string, string)>)new PowerLoc(
            "Summoned Ally",
            "A bodyguard that soaks the hits aimed at you; your summon cards strike through it.",
            "A bodyguard that soaks the hits aimed at you; your summon cards strike through it.");
}
