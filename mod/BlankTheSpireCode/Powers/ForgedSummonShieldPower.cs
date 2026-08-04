using System.Collections.Generic;
using System.Linq;
using BaseLib.Abstracts;
using BaseLib.Utils;
using BlankTheSpire.BlankTheSpireCode.Extensions;
using MegaCrit.Sts2.Core.Entities.Cards;
using MegaCrit.Sts2.Core.Entities.Creatures;
using MegaCrit.Sts2.Core.Entities.Powers;
using MegaCrit.Sts2.Core.GameActions.Multiplayer;
using MegaCrit.Sts2.Core.Models;
using MegaCrit.Sts2.Core.ValueProps;

namespace BlankTheSpire.BlankTheSpireCode.Powers;

/// <summary>
/// Phase K: the meat-shield for forged summons. Applied ONCE to the PLAYER (not per-pet) so it can pick the right
/// minion every hit: a powered attack aimed at the player is redirected to the FRONT-most living forged summon, so
/// damage cascades through the minions (oldest first) before reaching the player. Mirrors the base game's
/// <c>DieForYouPower</c> (Osty's <c>ModifyUnblockedDamageTarget</c> redirect) but, being on the player and choosing
/// the front pet dynamically, it cleanly hands off to the NEXT summon when one dies — which stacked per-pet
/// DieForYou powers do not. Harmless when no minion is alive (returns the player → normal damage). Combat-scoped.
/// </summary>
public sealed class ForgedSummonShieldPower : BlankTheSpirePower
{
    public override PowerType Type => PowerType.Buff;
    public override PowerStackType StackType => PowerStackType.Single; // one per player; re-applying is idempotent
    public override bool ShouldPlayVfx => false;

    // Reuse a shipped placeholder texture so the buff isn't a missing-icon blob (no authored art).
    public override string CustomPackedIconPath => "card.png".CardImagePath();
    public override string CustomBigIconPath => "card.png".BigCardImagePath();

    /// <summary>Grant the shield to the <paramref name="player"/> creature (idempotent — Single stack).</summary>
    public static Task Apply(PlayerChoiceContext ctx, Creature player)
        => BetaMainCompatibility.PowerCmd_.Apply.InvokeGeneric<Task<ForgedSummonShieldPower?>, ForgedSummonShieldPower>(
               null, ctx, player, 1m, player, (CardModel?)null, false)!;

    public override Creature ModifyUnblockedDamageTarget(Creature target, decimal amount, ValueProp props, Creature? dealer)
    {
        // Only redirect POWERED attacks aimed at me (the player). Non-powered / self damage passes through.
        if (target != Owner || !props.IsPoweredAttack()) return target;
        // Pick the front-most living forged minion from the authoritative combat ally list (the same source
        // OstyCmd uses to find Osty — more reliable than PlayerCombatState.Pets, which can lag on death).
        // K-3a: skip ETHEREAL summons (attackable:false) — they are untargetable strikers, never meat-shields.
        // K-3a: skip ETHEREAL summons (verified by AutoSlay smoke 2026-06-18 — 33 powered hits redirected to the
        // attackable Hound or the player, never to a Falcon).
        var front = Owner.CombatState?.Allies
            .FirstOrDefault(c => c.IsAlive && c.Monster is ForgedSummon fs && (fs.Source?.Attackable ?? true));
        return front ?? target; // front living attackable minion soaks; when it dies the next one does; else the player.
    }

    public override List<(string, string)>? Localization =>
        (List<(string, string)>)new PowerLoc(
            "Bodyguard",
            "Your summon takes the powered hits aimed at you, until it falls.",
            "Your summon takes the powered hits aimed at you, until it falls.");
}
