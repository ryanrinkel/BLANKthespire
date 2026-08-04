using MegaCrit.Sts2.Core.Entities.Players;

namespace BlankTheSpire.BlankTheSpireCode.Engine;

/// <summary>
/// Phase AD (gap #12): a per-turn "HP lost this turn" read for the <c>hp_lost_ge</c> condition (the Ice Shatter
/// threshold — "once you've spent N HP this turn, …"). SNAPSHOT-based (no damage hook needed): capture the
/// player's CurrentHp at each turn start (the same <c>Hook.BeforeHandDraw</c> dispatch F5's HandStateTracker
/// rides), then HP-lost-this-turn = max(0, snapshot - current). Counts ANY source that lowers HP during your
/// turn — self-inflicted <c>lose_hp</c> / card costs (the Ice Shatter fuel) plus any damage taken — and is net
/// of any mid-turn heal (a heal shrinks the delta). Single local player → one static snapshot (mirrors
/// HandStateTracker). Tolerant: outside combat / before the first snapshot it reads 0.
/// </summary>
public static class HpLossTracker
{
    // Player HP snapshotted at the start of the current turn; -1 = no snapshot yet (outside combat).
    private static int _turnStartHp = -1;

    /// <summary>Snapshot the player's HP at turn start (fired before the start-of-turn draw). Re-taken each turn,
    /// so the delta below is always "since THIS turn started".</summary>
    public static void SnapshotTurnStart(Player? player)
    {
        try { _turnStartHp = player?.Creature?.CurrentHp ?? -1; }
        catch { _turnStartHp = -1; }
    }

    /// <summary>HP the player has lost since this turn started (clamped &gt;= 0). 0 before the first snapshot /
    /// outside combat. Read by the <c>hp_lost_ge</c> condition (<see cref="Conditions"/>).</summary>
    public static int HpLostThisTurn(Player? player)
    {
        try
        {
            if (_turnStartHp < 0 || player?.Creature == null) return 0;
            int lost = _turnStartHp - player.Creature.CurrentHp;
            return lost > 0 ? lost : 0;
        }
        catch { return 0; }
    }
}
