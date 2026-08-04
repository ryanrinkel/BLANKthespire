using System;
using System.Collections.Generic;
using System.Linq;
using HarmonyLib;
using MegaCrit.Sts2.Core.Entities.Players;
using MegaCrit.Sts2.Core.Factories;
using MegaCrit.Sts2.Core.Models;
using MegaCrit.Sts2.Core.Runs;

namespace BlankTheSpire.BlankTheSpireCode.Engine;

/// <summary>
/// Central safety net for the reward CARD-GENERATION soft-lock family (the merchant hang, the boss-reward-rarity
/// hang, and the Orobas/Ancient-event relic-reward hang all funnel here). Every "create a card to reward the
/// player" path ultimately calls the private
/// <c>CardFactory.CreateForReward(Player, IEnumerable&lt;CardModel&gt;, CardCreationOptions)</c>, which THROWS
/// <c>InvalidOperationException</c> ("couldn't generate a valid rarity/card") when the class pool can't satisfy
/// the requested rarity/blacklist (e.g. a forged class with too few of a rarity, or all candidates blacklisted).
/// The throw is async + uncaught, so the rewards/event screen never finishes and the run soft-locks.
///
/// This Harmony finalizer wraps that choke point: if generation throws, we DEGRADE to a fallback card instead of
/// hanging — any card from the pool (ignoring the rarity roll), preferring one not already owned/offered, and as a
/// last resort a duplicate of a blacklisted card. The player just gets a slightly off-rarity (or duplicate) reward
/// rather than a frozen game. This complements (and generalizes past) <see cref="MerchantSafetyPatch"/>, which only
/// covers the merchant entry path. Auto-discovered by the existing <c>harmony.PatchAll()</c>; inert on success.
/// </summary>
[HarmonyPatch(typeof(CardFactory), "CreateForReward",
    new[] { typeof(Player), typeof(IEnumerable<CardModel>), typeof(CardCreationOptions) })]
internal static class RewardCardSafetyPatch
{
    private static Exception? Finalizer(Player player, IEnumerable<CardModel> blacklist, CardCreationOptions options,
                                        ref CardModel __result, Exception? __exception)
    {
        if (__exception == null) return null; // normal success — leave the real result untouched

        try
        {
            var bl = blacklist as ICollection<CardModel> ?? blacklist?.ToList() ?? new List<CardModel>();
            var pool = options.GetPossibleCards(player).ToList();
            // Prefer a fresh card; else any pool card (off-rarity is fine); else a duplicate of a blacklisted one.
            CardModel? pick = pool.FirstOrDefault(c => !bl.Contains(c)) ?? pool.FirstOrDefault() ?? bl.FirstOrDefault();
            if (pick != null)
            {
                __result = player.RunState.CreateCard(pick, player);
                MainFile.Logger.Warn(
                    $"[RewardGuard] reward card-gen failed ({__exception.Message}); substituted '{pick.Id}' " +
                    "(off-rarity/duplicate) to avoid a soft-lock.");
                return null; // swallow — we produced a valid result
            }
        }
        catch (Exception e)
        {
            MainFile.Logger.Error($"[RewardGuard] fallback substitution itself failed: {e}");
        }

        // Truly nothing to offer (no pool AND empty blacklist — pathological). Suppress anyway so the run doesn't
        // hang; the game's own "0 options → empty selection" net handles the now-cardless reward screen.
        MainFile.Logger.Warn(
            $"[RewardGuard] reward card-gen failed with no fallback card available; suppressing to avoid a hang. " +
            $"{__exception.Message}");
        return null;
    }
}
