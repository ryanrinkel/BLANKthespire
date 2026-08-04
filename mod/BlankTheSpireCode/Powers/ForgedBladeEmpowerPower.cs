using System.Threading.Tasks;
using System.Collections.Generic;
using BaseLib.Abstracts;
using BaseLib.Utils;
using BlankTheSpire.BlankTheSpireCode.Engine;
using MegaCrit.Sts2.Core.Entities.Cards;
using MegaCrit.Sts2.Core.Entities.Creatures;
using MegaCrit.Sts2.Core.Entities.Players;
using MegaCrit.Sts2.Core.Entities.Powers;
using MegaCrit.Sts2.Core.GameActions.Multiplayer;
using MegaCrit.Sts2.Core.Models;

namespace BlankTheSpire.BlankTheSpireCode.Powers;

/// <summary>
/// Phase AF (VOCABULARY_GAPS #41): BLADE EMPOWER — a transient ×N multiplier on the forged signature blade for
/// ONE turn (the burst button distinct from the slow Forge ramp). A one-turn power holding the multiplier N as its
/// Amount; the blade's <c>scale:"forged"</c> damage calc (<see cref="DataCard"/>.BonusFor) reads it via
/// <see cref="EffectRunner.BladeMultiplier"/> and multiplies the BLADE TOKEN's total by N (token-scoped, so it's
/// "blade deals double", not "everything forged deals double"). Removed at your next turn start (the temp-power
/// lifetime — functionally "this turn": you empower and swing the same turn). Re-application REFRESHES (overwrite,
/// never stacks). In-code loc + a runtime emoji icon.
/// </summary>
public sealed class ForgedBladeEmpowerPower : BlankTheSpirePower
{
    public override PowerType Type => PowerType.Buff;
    // The multiplier is a single value (×2 / ×3), not a stack — re-applying REFRESHES it (see ApplyOrRefresh).
    public override PowerStackType StackType => PowerStackType.Single;

    /// <summary>Grant a fresh Blade Empower power (self), literal amount — mirrors the <see cref="ForgedForgePower.Apply"/>
    /// self-apply path (the generic apply needs the concrete type at the call site).</summary>
    private static Task Apply(PlayerChoiceContext ctx, Player owner, int mult)
        => BetaMainCompatibility.PowerCmd_.Apply.InvokeGeneric<Task<ForgedBladeEmpowerPower?>, ForgedBladeEmpowerPower>(
               null, ctx, owner.Creature, (decimal)mult, owner.Creature, (CardModel?)null, false)!;

    /// <summary>The <c>blade_empower</c> executor: set the owner's blade multiplier to <paramref name="mult"/> for this
    /// turn. Attaches a fresh power on first use, then OVERWRITES the value (refresh, not stack) — the Phase-J/S
    /// live-stack mutation (set Amount + InvokePowerModified).</summary>
    public static async Task ApplyOrRefresh(PlayerChoiceContext ctx, Player owner, int mult)
    {
        int m = System.Math.Max(2, mult);
        var creature = owner.Creature;
        if (!creature.HasPower<ForgedBladeEmpowerPower>())
            await Apply(ctx, owner, m);
        var power = creature.GetPower<ForgedBladeEmpowerPower>();
        if (power == null) { MainFile.Logger.Warn("[AF] blade_empower: power failed to attach."); return; }
        if (power.Amount != m)
        {
            int old = power.Amount;
            power.Amount = m;
            creature.InvokePowerModified(power, m - old, false);
        }
        MainFile.Logger.Info($"[AF] blade_empower x{m} (this turn).");
    }

    /// <summary>The player's current blade multiplier (1 with no power / outside combat). Read by the blade's
    /// <c>scale:"forged"</c> calc-var (<see cref="DataCard"/>.BonusFor), token-scoped.</summary>
    public static int Multiplier(Player? owner)
    {
        var c = owner?.Creature;
        return c != null && c.HasPower<ForgedBladeEmpowerPower>()
            ? System.Math.Max(1, c.GetPower<ForgedBladeEmpowerPower>()?.Amount ?? 1)
            : 1;
    }

    // Temp lifetime: removed at your NEXT turn start (functionally "this turn" — you empower + swing the blade the
    // same turn; the enemy turn between doesn't matter). The applying turn is already past its turn-start, so this
    // fires next turn and clears the multiplier before you act.
    public override async Task AfterPlayerTurnStart(PlayerChoiceContext ctx, Player player)
    {
        if (Owner != player.Creature) return;
        MainFile.Logger.Info("[AF] blade_empower expired (turn start).");
        Owner.RemovePowerInternal(this);
        await Task.CompletedTask;
    }

    public override List<(string, string)>? Localization =>
        (List<(string, string)>)new PowerLoc("Blade Empower",
            "Your blade deals multiplied damage this turn (cleared at the start of your next turn).",
            "Your blade deals multiplied damage this turn (cleared at the start of your next turn).");

    public override string? CustomPackedIconPath => EmojiIconRenderer.IconPath("blade_empower") ?? base.CustomPackedIconPath;
    public override string? CustomBigIconPath => EmojiIconRenderer.IconPath("blade_empower") ?? base.CustomBigIconPath;
}
