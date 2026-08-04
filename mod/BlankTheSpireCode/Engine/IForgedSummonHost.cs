namespace BlankTheSpire.BlankTheSpireCode.Engine;

/// <summary>
/// Phase K: implemented by a class card leaf so the <c>summon</c> op can resolve a summon NAME against THAT
/// card's class summon_pool (the <see cref="IForgedOrbHost"/> / <see cref="IForgedStatusHost"/> analogue). The
/// generated <c>ForgedClassKCardNN</c> shells return their class index K.
/// </summary>
public interface IForgedSummonHost
{
    int SummonClass { get; }
}
