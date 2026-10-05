using System.Linq;
using HarmonyLib;
using MegaCrit.Sts2.Core.Entities.Players;
using MegaCrit.Sts2.Core.Models.Powers;

namespace BlankTheSpire.BlankTheSpireCode.Engine;

/// <summary>
/// Phase BQ (v68, gap #78): the smoke tag for the `loop` status. A card's `loop` applies the BASE game's sealed
/// <see cref="LoopPower"/> (shipped loc + icon), which at your turn start calls <c>OrbCmd.Passive</c> on your FRONT orb
/// <c>Amount</c> times — so there is no mod code on that path to log from. This Prefix is LOG-ONLY (it never changes the
/// arguments or skips the original): it names the orb Loop is about to pump, mirroring LoopPower's own guard
/// (<c>player == Owner.Player</c> and a non-empty rack). For a custom orb the pump then shows up as the
/// "[BQ] passive override" line from <see cref="Powers.ForgedOrb.Passive"/>. Auto-discovered by the existing
/// <c>harmony.PatchAll()</c>.
/// </summary>
[HarmonyPatch(typeof(LoopPower), nameof(LoopPower.AfterPlayerTurnStart))]
internal static class LoopTickTagPatch
{
    private static void Prefix(LoopPower __instance, Player player)
    {
        try
        {
            var owner = __instance.Owner?.Player;
            var orbs = player?.PlayerCombatState?.OrbQueue?.Orbs;
            if (owner == null || player != owner || orbs == null || orbs.Count == 0) return;
            MainFile.Logger.Info($"[BQ] loop tick -> '{EffectRunner.OrbName(orbs.First())}' x{__instance.Amount} ({orbs.Count} orbs).");
        }
        catch (System.Exception ex)
        {
            MainFile.Logger.Warn($"[BQ] loop tick tag failed (log-only, ignored): {ex.Message}");
        }
    }
}
