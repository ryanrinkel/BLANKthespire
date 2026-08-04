namespace BlankTheSpire.BlankTheSpireCode.Engine;

/// <summary>
/// Implemented by each generated forged CLASS card-slot leaf (Phase I forged orbs). When a class card runs a
/// <c>channel_orb</c> op, the orb name is resolved against THAT class's <c>orb_pool</c> (base or custom), and
/// <c>random</c> rolls only within the class's pool — never the global random orb pool. The card leaf knows its
/// class index <see cref="OrbClass"/> (mirroring <see cref="IForgedTriggerHost"/>), so <see cref="EffectRunner"/>
/// can ask <see cref="ForgedCharacters"/> to map the name to a concrete orb Type for that class.
/// </summary>
public interface IForgedOrbHost
{
    /// <summary>The 1-based class index this card belongs to (its <c>orb_pool</c> owner).</summary>
    int OrbClass { get; }
}
