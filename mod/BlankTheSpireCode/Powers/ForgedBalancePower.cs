using System;
using System.Collections.Generic;
using System.Threading.Tasks;
using BaseLib.Abstracts;
using BaseLib.Utils;
using BlankTheSpire.BlankTheSpireCode.Engine;
using MegaCrit.Sts2.Core.Commands;
using MegaCrit.Sts2.Core.Entities.Creatures;
using MegaCrit.Sts2.Core.Entities.Players;
using MegaCrit.Sts2.Core.Entities.Powers;
using MegaCrit.Sts2.Core.GameActions.Multiplayer;
using MegaCrit.Sts2.Core.Models;
using MegaCrit.Sts2.Core.Models.Powers;
using MegaCrit.Sts2.Core.ValueProps;

namespace BlankTheSpire.BlankTheSpireCode.Powers;

/// <summary>
/// Phase S (VOCABULARY_GAPS #1): THE BALANCE GAUGE — a SIGNED player-level counter, the balance-class identity.
/// Built on the <see cref="ForgedForgePower"/> pattern (per-combat counter, in-code loc + emoji icon, resets each
/// combat) but with a SIGNED value: positive = Dark, negative = Light, the power is ABSENT at 0 (centered). The
/// <c>balance_step</c> op (cards AND add_trigger self-payloads — trigger income is the engine, exactly like
/// <c>forge</c>) moves the gauge toward a pole; the <c>light_ge</c> / <c>dark_ge</c> / <c>centered</c> conditions
/// read it (see <see cref="Conditions"/>). What makes it a GAUGE and not a second Forge is the BITE: at
/// |gauge| &gt;= <see cref="ExtremeThreshold"/>, the owner's turn-start applies the pole's penalty (Dark drains HP;
/// Light inflicts Weak) — visible pressure that punishes camping at an extreme. Per-combat by nature (powers die
/// at combat end); a fresh instance starts centered (value 0).
///
/// Display: the native power <see cref="MegaCrit.Sts2.Core.Entities.Powers.PowerModel.Amount"/> mirrors
/// |value| (signed arithmetic can't ride native Counter stacking, so <see cref="BalanceStep"/> owns the math and
/// syncs the display — the same live-stack mutation the Phase J status decay uses), while name/icon flip by sign.
/// </summary>
public sealed class ForgedBalancePower : BlankTheSpirePower
{
    /// <summary>|gauge| at/above which the turn-start extreme penalty fires. Tuned here (the plan's marker value).</summary>
    public const int ExtremeThreshold = 8;
    private const int DarkExtremeHpLoss = 3;   // Dark extreme (value >= +8): lose 3 HP at turn start.
    private const int LightExtremeWeak = 1;    // Light extreme (value <= -8): gain 1 Weak at turn start.

    // The SIGNED gauge (positive = Dark, negative = Light). The single source of truth: the native Amount mirrors
    // |value| for display, name/icon flip by sign, and the power is removed at 0. Instance state — a fresh power
    // per application, so it resets to centered (0) every combat.
    private int _value;

    public override PowerType Type => PowerType.Buff;
    // We own the arithmetic (signed steps can't ride native Counter stacking — a Light step must SUBTRACT):
    // BalanceStep sets the value + syncs Amount/display explicitly. StackType is COUNTER anyway, purely for
    // DISPLAY: in play the gauge's magnitude never rendered on the icon under Single (El Traficante
    // 2026-08-12: the log stepped the gauge 1→2→3 while the badge stayed blank), while the Counter-stacked
    // ForgedForgePower shows its count fine — Single reads as a binary toggle to the power UI. Counter's
    // auto-add path never runs here: BalanceStep is the ONLY applier (EffectRunner + TriggerRunner both
    // funnel through it) and it Applies only when the power is ABSENT, then mutates the live stack.
    public override PowerStackType StackType => PowerStackType.Counter;

    /// <summary>The current signed gauge (positive = Dark, negative = Light, 0 = centered). Read by <see cref="Conditions"/>.</summary>
    public int Value => _value;

    /// <summary>Grant a fresh (centered) Balance gauge to the player (self), literal amount, no card — mirrors the
    /// <see cref="ForgedForgePower.Apply"/> self-apply path (the generic apply needs the concrete type at the call
    /// site). <see cref="BalanceStep"/> immediately overwrites the display via <see cref="SetValue"/>, so the
    /// applied amount is only a placeholder for the gauge's first appearance.</summary>
    public static Task Apply(PlayerChoiceContext ctx, Player owner, int amount)
        => BetaMainCompatibility.PowerCmd_.Apply.InvokeGeneric<Task<ForgedBalancePower?>, ForgedBalancePower>(
               null, ctx, owner.Creature, (decimal)amount, owner.Creature, (CardModel?)null, false)!;

    /// <summary>The <c>balance_step</c> executor — move <paramref name="owner"/>'s gauge <paramref name="amount"/>
    /// toward <paramref name="pole"/> ("dark" = +, "light" = -). Attaches a centered gauge on first use, then does
    /// the signed arithmetic on the on-creature instance. Shared by the card path (<see cref="EffectRunner"/>) and
    /// the trigger path (<see cref="TriggerRunner"/>), exactly like <c>forge</c>.</summary>
    public static async Task BalanceStep(PlayerChoiceContext ctx, Player owner, string? pole, int amount)
    {
        int step = Math.Max(1, amount);
        int delta = pole == "light" ? -step : step;   // positive = Dark (the default/unknown pole reads as Dark)
        var creature = owner.Creature;
        if (!creature.HasPower<ForgedBalancePower>())
            await Apply(ctx, owner, step);             // attach a fresh gauge (SetValue overwrites the display below)
        var power = creature.GetPower<ForgedBalancePower>();
        if (power == null) { MainFile.Logger.Warn("[S] balance_step: gauge failed to attach."); return; }
        power.SetValue(power._value + delta, creature);
        MainFile.Logger.Info($"[S] balance_step {pole} {step} -> gauge {power._value} " +
                             $"({(power._value == 0 ? "centered" : power._value > 0 ? "Dark" : "Light")}).");
    }

    /// <summary>Set the signed gauge and reconcile the display: at 0 the power is removed (centered); otherwise the
    /// native Amount mirrors |value| and the UI is refreshed (name/icon re-read the sign). Same live-stack mutation
    /// the Phase J status decay uses (<c>Amount = …; InvokePowerModified(…)</c>). NOTE: a sign flip that keeps the
    /// SAME magnitude (e.g. +2 → -2) changes no Amount, so the icon may lag one step until the next change; the
    /// stack number and hover tooltip stay correct, and the mechanical sign (read by conditions + the bite) is
    /// always exact — cosmetic-only, tune later.</summary>
    private void SetValue(int newValue, Creature owner)
    {
        _value = newValue;
        if (_value == 0) { owner.RemovePowerInternal(this); return; }
        int oldAmount = Amount;
        Amount = Math.Abs(_value);
        owner.InvokePowerModified(this, Amount - oldAmount, false);
    }

    /// <summary>The player's current signed gauge (0 with no gauge / outside combat). Shared by the three balance
    /// conditions (<see cref="Conditions"/>).</summary>
    public static int Gauge(Player? player)
    {
        var c = player?.Creature;
        return c != null && c.HasPower<ForgedBalancePower>() ? (c.GetPower<ForgedBalancePower>()?.Value ?? 0) : 0;
    }

    // The BITE: at an extreme, the pole's penalty lands at the owner's turn-start. Dark drains HP (the corruption
    // cost); Light inflicts Weak (the zealot's frailty). Logged visibly — it's the smoke's acceptance signal.
    public override async Task AfterPlayerTurnStart(PlayerChoiceContext ctx, Player player)
    {
        if (Owner != player.Creature) return;
        int mag = Math.Abs(_value);
        if (mag < ExtremeThreshold) return;
        Flash();
        if (_value > 0)
        {
            MainFile.Logger.Info($"[S] balance extreme Dark {mag} (>= {ExtremeThreshold}): lose {DarkExtremeHpLoss} HP.");
            // No card/dealer — the null-safe overload (the CardModel-only one NREs on a null card; see TriggerRunner).
            await CreatureCmd.Damage(ctx, Owner, DarkExtremeHpLoss, ValueProp.Unblockable, (Creature?)null, (CardModel?)null);
        }
        else
        {
            MainFile.Logger.Info($"[S] balance extreme Light {mag} (>= {ExtremeThreshold}): gain {LightExtremeWeak} Weak.");
            await ApplyWeakSelf(ctx, player, LightExtremeWeak);
        }
    }

    /// <summary>Apply Weak to the player itself (the Light extreme's penalty) — a literal-amount self-apply, no card.</summary>
    private static Task ApplyWeakSelf(PlayerChoiceContext ctx, Player owner, int amount)
        => BetaMainCompatibility.PowerCmd_.Apply.InvokeGeneric<Task<WeakPower?>, WeakPower>(
               null, ctx, owner.Creature, (decimal)amount, owner.Creature, (CardModel?)null, false)!;

    // In-code localization: name (with the pole emoji) + icon flip by the gauge's sign. At 0 the power is absent,
    // so the neutral "Balance" label is only a fallback (e.g. a stale tooltip mid-removal).
    public override List<(string, string)>? Localization
    {
        get
        {
            string name = _value == 0 ? "Balance" : _value > 0 ? "🌑 Dark" : "☀️ Light";
            string desc = "Your Balance gauge. Shift it toward the Light or the Dark; it clears each combat. " +
                          $"At {ExtremeThreshold}+ it bites at the start of your turn — the Dark drains {DarkExtremeHpLoss} HP, " +
                          $"the Light inflicts {LightExtremeWeak} Weak.";
            return (List<(string, string)>)new PowerLoc(name, desc, desc);
        }
    }

    // Emoji icon via the runtime renderer (kicked in MainFile), flipping by sign; falls back to the placeholder.
    public override string? CustomPackedIconPath =>
        EmojiIconRenderer.IconPath(_value < 0 ? "balance_light" : "balance_dark") ?? base.CustomPackedIconPath;
    public override string? CustomBigIconPath =>
        EmojiIconRenderer.IconPath(_value < 0 ? "balance_light" : "balance_dark") ?? base.CustomBigIconPath;
}
