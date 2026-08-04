using MegaCrit.Sts2.Core.Entities.Players;
using MegaCrit.Sts2.Core.GameActions.Multiplayer;

namespace BlankTheSpire.BlankTheSpireCode.Engine;

/// <summary>
/// Implemented by each generated forged card-slot leaf (Phase H3 triggers). A card that carries an
/// <c>add_trigger</c> effect grants an ongoing power; because a power's behaviour is keyed to its compiled
/// .NET Type, each card slot has its OWN <c>ForgedTriggerPowerNN</c> shell, and only the leaf knows that
/// concrete type. So the leaf applies it here (the generic apply needs the type at the call site).
/// <see cref="EffectRunner"/> calls this when it executes an <c>add_trigger</c> op.
/// </summary>
public interface IForgedTriggerHost
{
    /// <summary>Grant this card's trigger power to <paramref name="owner"/> (self).</summary>
    System.Threading.Tasks.Task ApplyTrigger(PlayerChoiceContext ctx, Player owner);
}
