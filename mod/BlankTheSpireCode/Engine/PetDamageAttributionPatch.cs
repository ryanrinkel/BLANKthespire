using MegaCrit.Sts2.Core.Entities.Creatures;
using MegaCrit.Sts2.Core.Models.Monsters;
using MegaCrit.Sts2.Core.Models.Powers;
using HarmonyLib;

namespace BlankTheSpire.BlankTheSpireCode.Engine;

/// <summary>
/// Compatibility fix for forged SUMMON pets dealing damage to enemies that react on-hit by GENERATING cards.
///
/// Some enemy powers run an <c>AfterDamageReceived</c> hook that creates a card "from" the attacker and needs a
/// real <see cref="MegaCrit.Sts2.Core.Entities.Players.Player"/>: e.g. <c>PersonalHivePower</c> does
/// <c>CombatState.CreateCard&lt;Dazed&gt;(dealer.Player)</c>. The game special-cases ONLY the built-in pet
/// (<c>if (dealer.Monster is Osty) dealer = dealer.PetOwner.Creature;</c>) so that <c>dealer.Player</c> resolves
/// to the pet's OWNER — a pet creature's own <c>Player</c> is null. Our forged minions (<see cref="Powers.ForgedSummon"/>,
/// the dealer for their attacks via <see cref="SummonRunner"/>) are NOT Osty, so that branch is skipped and
/// <c>dealer.Player</c> is null → <c>NullReferenceException</c> deep in <c>CardPileCmd.AddGeneratedCardsToCombat</c>,
/// which faults the turn-end task and soft-locks the run. (Found by the AutoSlay smoke gate, Act 2 elite.)
///
/// This Prefix generalizes the engine's Osty special-case to ANY player pet: if the dealer is a pet (has a
/// <c>PetOwner</c>) that the engine wouldn't itself remap, swap it for the owner's creature BEFORE the hook runs —
/// exactly the substitution the game already does for Osty, so <c>dealer.Player</c> resolves. Inert for the player
/// and for Osty (which the engine handles itself). Auto-discovered by the existing <c>harmony.PatchAll()</c>.
/// </summary>
[HarmonyPatch(typeof(PersonalHivePower), "AfterDamageReceived")]
internal static class PetDamageAttributionPatch
{
    private static void Prefix(ref Creature? dealer)
    {
        if (dealer != null && dealer.PetOwner != null && dealer.Monster is not Osty)
            dealer = dealer.PetOwner.Creature;
    }
}
