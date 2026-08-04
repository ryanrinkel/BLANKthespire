using System.Reflection;
using System.Threading.Tasks;
using HarmonyLib;

namespace BlankTheSpire.BlankTheSpireCode.Engine;

/// <summary>
/// Safety net for the VICTORY hang. The post-boss Architect event loads its dialogue per CHARACTER
/// (<c>TheArchitect.LoadDialogue</c> → <c>GetValidDialogues(characterId, …, allowAnyCharacterDialogues: false)</c>),
/// and the Architect's dialogue set defines NO agnostic fallback (<c>AgnosticDialogues = Array.Empty</c>).
/// A forged class has no Architect dialogues, so <c>Dialogue</c> stays null. The event's option list handles
/// that (a bare "Proceed"), but <c>WinRun()</c> dereferences <c>Dialogue.EndAttackers</c> unconditionally →
/// NullReferenceException → the act-change handshake (<c>SetLocalPlayerReady</c>) never runs → the game hangs
/// on "Waiting for main menu after victory" and the WIN never completes. Found by the AutoSlay smoke gate the
/// first time a forged class actually WON a run (Hivekeeper, seed STRAT3, 2026-07-03).
///
/// This prefix fires only when <c>Dialogue</c> is null: it skips the victory cinematic (which needs the
/// dialogue's EndAttackers) and performs the essential tail of WinRun directly — mark the local player ready
/// so the act-change synchronizer returns to the main menu. With a real dialogue loaded (every base-game
/// class), vanilla WinRun runs untouched.
/// </summary>
[HarmonyPatch]
internal static class ArchitectVictoryPatch
{
    private static MethodBase? TargetMethod() =>
        AccessTools.Method("MegaCrit.Sts2.Core.Models.Events.TheArchitect:WinRun");

    private static bool Prefix(object __instance, ref Task __result)
    {
        if (AccessTools.Field(__instance.GetType(), "_dialogue")?.GetValue(__instance) != null)
            return true; // a real dialogue is loaded — vanilla WinRun is safe

        // Resolve the whole reflection chain BEFORE acting; any miss → run vanilla (no worse than today).
        var owner = AccessTools.Property(__instance.GetType(), "Owner")?.GetValue(__instance);
        // IsMe is overloaded (Player? / Creature?) — name the Player overload explicitly.
        var playerType = AccessTools.TypeByName("MegaCrit.Sts2.Core.Entities.Players.Player");
        var isMe = playerType is null
            ? null
            : AccessTools.Method("MegaCrit.Sts2.Core.Context.LocalContext:IsMe", new[] { playerType });
        var runManager = AccessTools.PropertyGetter("MegaCrit.Sts2.Core.Runs.RunManager:Instance")
            ?.Invoke(null, null);
        var synchronizer = runManager is null
            ? null
            : AccessTools.Property(runManager.GetType(), "ActChangeSynchronizer")?.GetValue(runManager);
        var setReady = synchronizer is null
            ? null
            : AccessTools.Method(synchronizer.GetType(), "SetLocalPlayerReady");
        if (owner is null || isMe is null || synchronizer is null || setReady is null)
        {
            MainFile.Logger.Warn("[ArchitectGuard] Dialogue is null but the reflection chain didn't resolve — " +
                                 "letting vanilla WinRun proceed.");
            return true;
        }

        MainFile.Logger.Info("[ArchitectGuard] no Architect dialogue for this class (forged classes have none " +
                             "and the set has no agnostic fallback) — skipping the victory cinematic and " +
                             "completing the win directly.");
        if (isMe.Invoke(null, new[] { owner }) is true)
            setReady.Invoke(synchronizer, null);
        __result = Task.CompletedTask;
        return false; // skip vanilla WinRun (it would NRE on Dialogue.EndAttackers)
    }
}
