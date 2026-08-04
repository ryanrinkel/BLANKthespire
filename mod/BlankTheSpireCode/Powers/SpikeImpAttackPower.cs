using System.Collections.Generic;
using System.Linq;
using BaseLib.Abstracts;
using BaseLib.Utils;
using BlankTheSpire.BlankTheSpireCode.Extensions;
using MegaCrit.Sts2.Core.Combat;
using MegaCrit.Sts2.Core.Commands;
using MegaCrit.Sts2.Core.Entities.Cards;
using MegaCrit.Sts2.Core.Entities.Creatures;
using MegaCrit.Sts2.Core.Entities.Powers;
using MegaCrit.Sts2.Core.GameActions.Multiplayer;
using MegaCrit.Sts2.Core.Models;
using MegaCrit.Sts2.Core.ValueProps;

namespace BlankTheSpire.BlankTheSpireCode.Powers;

/// <summary>
/// PHASE K SPIKE (throwaway): the behaviour driver for <see cref="SpikeImp"/>. The spike learned that
/// PLAYER-side creatures are NEVER driven by the combat turn loop (<c>CombatManager</c> only rolls/performs
/// moves for ENEMIES, and <c>Creature.TakeTurn()</c> hard-throws "Only enemy monsters can take automated
/// turns"). So a summoned pet's move state machine is dead weight — its per-turn behaviour must be HOOK-driven,
/// exactly like the H3 <see cref="ForgedTriggerPower"/>. This power is applied to the pet on summon and, at the
/// END of the player's turn, makes the pet attack an enemy (the pet is the dealer). Damage uses
/// <c>ValueProp.Move</c> (an intrinsic hit, blockable + Vulnerable-aware, not scaled by the player's card
/// mechanics) — the same path forged orbs use.
///
/// K-1 will generalize this into a <c>ForgedSummonPower</c> + a SummonRunner that reads a data-driven move list
/// (attack/block/buff/debuff) from the class JSON, instead of this hardcoded "attack 5".
/// </summary>
public sealed class SpikeImpAttackPower : BlankTheSpirePower
{
    public override PowerType Type => PowerType.Buff;
    public override PowerStackType StackType => PowerStackType.Single;

    // Reuse a shipped placeholder texture so the pet's behaviour buff isn't a missing-icon blob (the spike
    // power has no authored art; real per-summon art is a later concern).
    public override string CustomPackedIconPath => "card.png".CardImagePath();
    public override string CustomBigIconPath => "card.png".BigCardImagePath();

    /// <summary>Grant this driver power to the summoned <paramref name="pet"/> creature (amount 1), via the
    /// BaseLib generic apply path (the concrete type is known here, which the generic call needs).</summary>
    public static Task Apply(PlayerChoiceContext ctx, Creature pet)
        => BetaMainCompatibility.PowerCmd_.Apply.InvokeGeneric<Task<SpikeImpAttackPower?>, SpikeImpAttackPower>(
               null, ctx, pet, 1m, pet, (CardModel?)null, false)!;

    public override async Task AfterSideTurnEnd(PlayerChoiceContext ctx, CombatSide side, IEnumerable<Creature> participants)
    {
        // Fire only at the end of the pet's OWN side (the player side); skip if the pet has died.
        if (side != Owner.Side || Owner.IsDead) return;
        var enemy = Owner.CombatState?.HittableEnemies.FirstOrDefault(c => c.IsAlive);
        if (enemy == null) return;
        Flash();
        await CreatureCmd.Damage(ctx, new[] { enemy }, 5m, ValueProp.Move, Owner);
    }

    // In-code tooltip for the pet's behaviour buff (no .pck rebuild).
    public override List<(string, string)>? Localization =>
        (List<(string, string)>)new PowerLoc(
            "Spike Imp", "Attacks for 5 at the end of your turn.", "Attacks for 5 at the end of your turn.");
}
