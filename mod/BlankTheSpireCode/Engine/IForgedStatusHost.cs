namespace BlankTheSpire.BlankTheSpireCode.Engine;

/// <summary>
/// Implemented by each generated forged CLASS card-slot leaf (Phase J forged statuses). When a class card runs
/// an <c>apply_status_custom</c> op, the status name is resolved against THAT class's <c>status_pool</c> and a
/// matching <c>ForgedClassKStatusM</c> power is applied. Custom statuses are STRICTLY class-specific (never on a
/// shared forged card), so only class card leaves carry this — mirroring <see cref="IForgedOrbHost"/> /
/// <see cref="IForgedTriggerHost"/>. The leaf knows its class index <see cref="StatusClass"/> so
/// <see cref="EffectRunner"/> can ask <see cref="ForgedCharacters"/> to map the name to a concrete power instance.
/// </summary>
public interface IForgedStatusHost
{
    /// <summary>The 1-based class index this card belongs to (its <c>status_pool</c> owner).</summary>
    int StatusClass { get; }
}
