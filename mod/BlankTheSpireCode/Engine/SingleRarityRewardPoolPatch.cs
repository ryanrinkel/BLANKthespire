using System.Linq;
using System.Reflection;
using HarmonyLib;
using MegaCrit.Sts2.Core.Runs;

namespace BlankTheSpire.BlankTheSpireCode.Engine;

/// <summary>
/// Reward-safety patch (same family as <see cref="RewardCardSafetyPatch"/> / <see cref="MerchantSafetyPatch"/>):
/// stops the <c>CardCreationOptions</c> "single-rarity custom pool" assert from throwing on a forged class.
///
/// The engine's <c>CardCreationOptions..ctor</c> calls <c>AssertUniformOddsIfSingleRarityPool()</c>, which THROWS
/// <c>InvalidOperationException("…custom card pool with only one rarity … must use Uniform rarity odds")</c> when a
/// <see cref="CardCreationOptions.CustomCardPool"/> has a single rarity but the <see cref="CardCreationOptions.RarityOdds"/>
/// are anything other than <c>Uniform</c>. Some base-game relics build their own reward <c>CardCreationOptions</c>
/// from a filtered pool with the room's odds (e.g. <c>LastingCandy.TryModifyCardRewardOptions</c> with
/// <c>RegularEncounter</c> odds) — and against a forged class that filter can collapse to one rarity, so the throw
/// fires inside the post-combat reward flow and the card-reward generation faults (found by the AutoSlay smoke gate
/// on "The Swarmlord", 2026-06-19).
///
/// This Harmony prefix does exactly what the engine's own error message prescribes: when the custom pool is
/// single-rarity, it rewrites the odds to <c>Uniform</c> (the only valid choice — the pool has one rarity anyway) and
/// skips the would-throw assert. Multi-rarity / non-custom pools are left untouched (the original assert is a no-op
/// for them). Auto-discovered by <c>harmony.PatchAll()</c>; inert except on the exact throwing case.
/// </summary>
[HarmonyPatch(typeof(CardCreationOptions), "AssertUniformOddsIfSingleRarityPool")]
internal static class SingleRarityRewardPoolPatch
{
    // The record's RarityOdds is init-only; write its publicized backing field to override it post-construction.
    private static readonly FieldInfo? RarityOddsField =
        AccessTools.Field(typeof(CardCreationOptions), "<RarityOdds>k__BackingField");

    private static bool Prefix(CardCreationOptions __instance)
    {
        var pool = __instance.CustomCardPool;
        if (pool == null || __instance.RarityOdds == CardRarityOddsType.Uniform || RarityOddsField == null)
            return true; // not a custom pool, or already valid — let the (no-op) original assert run

        bool single;
        try { single = pool.Select(c => c.Rarity).Distinct().Take(2).Count() <= 1; }
        catch { return true; } // can't inspect the pool — defer to the engine (RewardCardSafetyPatch nets downstream)
        if (!single) return true; // multi-rarity is valid — original assert passes

        var was = __instance.RarityOdds;
        RarityOddsField.SetValue(__instance, CardRarityOddsType.Uniform);
        MainFile.Logger.Warn($"[RewardGuard] single-rarity custom card pool with {was} odds → forced Uniform " +
                             "(avoids the CardCreationOptions assert throw; e.g. Lasting Candy on a forged class).");
        return false; // corrected — skip the assert that would otherwise throw
    }
}
