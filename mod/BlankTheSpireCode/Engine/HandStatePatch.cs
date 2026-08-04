using HarmonyLib;
using MegaCrit.Sts2.Core.Combat;
using MegaCrit.Sts2.Core.Entities.Players;
using MegaCrit.Sts2.Core.Hooks;

namespace BlankTheSpire.BlankTheSpireCode.Engine;

/// <summary>
/// Phase F5: snapshot the PRE-DRAW hand at turn start. <c>Hook.BeforeHandDraw(ICombatState, Player, ctx)</c> is
/// the central dispatcher the engine fires once per player turn-start, BEFORE the start-of-turn draw — so at
/// this moment the hand holds exactly the cards retained from last turn. Feeds <see cref="HandStateTracker"/>'s
/// <c>CardsRetained</c> + the <c>retained_last_turn</c> set. Auto-discovered by <c>harmony.PatchAll()</c>
/// (same mechanism as the reward/merchant safety patches); read-only, never mutates game state.
/// </summary>
[HarmonyPatch(typeof(Hook), "BeforeHandDraw")]
internal static class HandStatePreDrawPatch
{
    // Hook.BeforeHandDraw(ICombatState __0, Player __1, PlayerChoiceContext __2) — grab the player positionally.
    private static void Prefix(Player __1)
    {
        HandStateTracker.SnapshotPreDraw(__1);
        HpLossTracker.SnapshotTurnStart(__1); // Phase AD (gap #12): reset the "HP lost this turn" baseline each turn.
    }
}

/// <summary>
/// Phase F5: capture energy left at the player's turn end → next turn's <c>unspent_energy_last_turn</c>.
/// <c>CombatManager.DoTurnEnd(Player, ctx)</c> runs as the player's turn ends, so <c>PlayerCombatState.Energy</c>
/// is the leftover. Auto-discovered by <c>harmony.PatchAll()</c>; read-only.
/// </summary>
[HarmonyPatch(typeof(CombatManager), "DoTurnEnd")]
internal static class HandStateTurnEndPatch
{
    // CombatManager.DoTurnEnd(Player __0, PlayerChoiceContext __1) — grab the player positionally.
    private static void Prefix(Player __0) => HandStateTracker.CaptureTurnEndEnergy(__0);
}
