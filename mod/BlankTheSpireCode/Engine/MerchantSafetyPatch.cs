using System;
using System.Reflection;
using HarmonyLib;

namespace BlankTheSpire.BlankTheSpireCode.Engine;

/// <summary>
/// Safety net for the merchant hang. The shop builds one card entry per merchant card type
/// (Attack / Skill / <b>Power</b>) and fills each by calling
/// <c>MegaCrit.Sts2.Core.Factories.CardFactory.CreateForMerchant(player, options, type)</c>, which rolls a
/// rarity among the rarities PRESENT in the pool filtered to that type. A forged class whose pool has no card
/// of a wanted type (commonly: <b>zero Power cards</b>) makes that roll fail with
/// <c>InvalidOperationException: Can't generate a valid rarity for the merchant card options passed.</c>,
/// thrown from inside <c>MerchantCardEntry.Populate()</c>. The throw is async and uncaught, so the merchant
/// room never finishes entering and the game black-screens (unrecoverable; force-quit required).
///
/// This Harmony finalizer wraps <c>MerchantCardEntry.Populate()</c>: if it throws, we swallow the exception
/// and leave that one entry un-stocked (the shop just shows fewer cards) instead of hanging the run. The
/// class generator also guarantees a merchant-safe pool now (≥1 non-basic Attack/Skill/Power per class), so
/// in practice this only fires for legacy / hand-authored pools — it's the belt to the generator's braces.
/// </summary>
[HarmonyPatch]
internal static class MerchantSafetyPatch
{
    private static MethodBase? TargetMethod() =>
        AccessTools.Method("MegaCrit.Sts2.Core.Entities.Merchant.MerchantCardEntry:Populate");

    // Harmony passes the thrown exception (or null) in __exception; returning null swallows it.
    private static Exception? Finalizer(Exception? __exception)
    {
        if (__exception != null)
            MainFile.Logger.Warn(
                "[MerchantGuard] suppressed a merchant card-entry failure (the class pool is too thin for a " +
                $"required card type — e.g. no Power cards). The shop will show fewer cards. {__exception.Message}");
        return null; // never let it bubble up and black-screen the run
    }
}
