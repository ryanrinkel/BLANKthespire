using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading.Tasks;
using BaseLib.Abstracts;
using BaseLib.Utils;
using BlankTheSpire.BlankTheSpireCode.Extensions;
using MegaCrit.Sts2.Core.Combat; // Phase AN (v44): CombatSide for the expiry-log override
using MegaCrit.Sts2.Core.Entities.Creatures;
using MegaCrit.Sts2.Core.Entities.Powers; // Phase BL (v64): PowerType for the Strength Down shell
using MegaCrit.Sts2.Core.GameActions.Multiplayer;
using MegaCrit.Sts2.Core.Models;
using MegaCrit.Sts2.Core.Models.Powers;

namespace BlankTheSpire.BlankTheSpireCode.Powers;

/// <summary>
/// Fix for the temp_strength / temp_dexterity crash. The base-game <c>TemporaryStrengthPower</c> /
/// <c>TemporaryDexterityPower</c> are ABSTRACT — never instantiated directly; every source subclasses them
/// (e.g. <c>FlexPotionPower</c>). So <c>ModelDb.Power&lt;TemporaryStrengthPower&gt;()</c> throws
/// <c>KeyNotFoundException</c> ('POWER.TEMPORARY_STRENGTH_POWER' is not a registered model). We instead ship our
/// own CONCRETE temp powers via BaseLib's <see cref="CustomTemporaryPowerModel"/> — a <c>CustomPowerModel</c>, so it
/// carries in-code localization like our other forged powers (no .pck / loc-table dependency) and auto-registers via
/// the ICustomPower scan. The base handles the mechanic: apply the <see cref="InternallyAppliedPower"/> now, then
/// remove it at the end of your turn.
/// </summary>
public abstract class ForgedTempStatPower : CustomTemporaryPowerModel
{
    // Required by ITemporaryPower. CustomTemporaryPowerModel draws its display from the CustomPowerModel loc path
    // (Localization, below), NOT from OriginModel, so returning the internal stat power (a valid model) is safe.
    public override AbstractModel OriginModel => InternallyAppliedPower;

    // The base flips the sign to remove the buff at end of turn, so this just applies the internal stat power for
    // whatever (possibly negative) amount it's handed.
    protected override Func<PlayerChoiceContext, Creature, decimal, Creature?, CardModel?, bool, Task> ApplyPowerFunc =>
        (ctx, target, amount, applier, cardSource, silent) => ApplyInternal(ctx, target, amount, applier, cardSource, silent);

    protected abstract Task ApplyInternal(PlayerChoiceContext ctx, Creature target, decimal amount,
                                          Creature? applier, CardModel? cardSource, bool silent);

    /// <summary>Phase AN (v44): a smoke-log tag (e.g. "[AN] temp_thorns"); null = no expiry log. The base removes the
    /// internal power in AfterSideTurnEnd (verified in BaseLib's CustomTemporaryPowerModel); we log AFTER it so the
    /// godot.log proves the one-turn shell expired at the end of the owner's turn.</summary>
    protected virtual string? ExpiryLogTag => null;

    public override async Task AfterSideTurnEnd(PlayerChoiceContext choiceContext, CombatSide side, IEnumerable<Creature> participants)
    {
        var people = participants as ICollection<Creature> ?? participants.ToList();
        bool mine = people.Contains(Owner);
        var had = Amount;
        await base.AfterSideTurnEnd(choiceContext, side, people);
        if (mine && ExpiryLogTag != null)
            MainFile.Logger.Info($"{ExpiryLogTag} expired at the end of your turn (had {had}).");
    }
}

/// <summary>Temporary Strength: +Strength now, removed at the end of your turn (Flex-style).</summary>
public sealed class ForgedTempStrengthPower : ForgedTempStatPower
{
    public override PowerModel InternallyAppliedPower => ModelDb.Power<StrengthPower>();

    protected override Task ApplyInternal(PlayerChoiceContext ctx, Creature target, decimal amount,
        Creature? applier, CardModel? cardSource, bool silent)
        => BetaMainCompatibility.PowerCmd_.Apply.InvokeGeneric<Task<StrengthPower?>, StrengthPower>(
               null, ctx, target, amount, applier ?? target, cardSource, silent)!;

    public override string CustomPackedIconPath => "strength_temp.png".PowerImagePath();
    public override string CustomBigIconPath => "strength_temp.png".BigPowerImagePath();
    public override List<(string, string)>? Localization =>
        (List<(string, string)>)new PowerLoc("Temporary Strength",
            "Gain Strength for this turn (removed at the end of your turn).",
            "Gain Strength for this turn (removed at the end of your turn).");
}

/// <summary>Temporary Dexterity: +Dexterity now, removed at the end of your turn.</summary>
public sealed class ForgedTempDexterityPower : ForgedTempStatPower
{
    public override PowerModel InternallyAppliedPower => ModelDb.Power<DexterityPower>();

    protected override Task ApplyInternal(PlayerChoiceContext ctx, Creature target, decimal amount,
        Creature? applier, CardModel? cardSource, bool silent)
        => BetaMainCompatibility.PowerCmd_.Apply.InvokeGeneric<Task<DexterityPower?>, DexterityPower>(
               null, ctx, target, amount, applier ?? target, cardSource, silent)!;

    public override string CustomPackedIconPath => "dexterity_temp.png".PowerImagePath();
    public override string CustomBigIconPath => "dexterity_temp.png".BigPowerImagePath();
    public override List<(string, string)>? Localization =>
        (List<(string, string)>)new PowerLoc("Temporary Dexterity",
            "Gain Dexterity for this turn (removed at the end of your turn).",
            "Gain Dexterity for this turn (removed at the end of your turn).");
}

/// <summary>Phase AN (v44) — Temporary Thorns: +Thorns now, removed at the end of your turn (a one-turn bristle: the
/// riposte window without a permanent Thorns ramp). Same CustomTemporaryPowerModel shell as the temp stats — the base
/// removes the internal ThornsPower stacks in AfterSideTurnEnd, AFTER the enemy has attacked into it this turn.</summary>
public sealed class ForgedTempThornsPower : ForgedTempStatPower
{
    public override PowerModel InternallyAppliedPower => ModelDb.Power<ThornsPower>();

    protected override Task ApplyInternal(PlayerChoiceContext ctx, Creature target, decimal amount,
        Creature? applier, CardModel? cardSource, bool silent)
        => BetaMainCompatibility.PowerCmd_.Apply.InvokeGeneric<Task<ThornsPower?>, ThornsPower>(
               null, ctx, target, amount, applier ?? target, cardSource, silent)!;

    protected override string? ExpiryLogTag => "[AN] temp_thorns";

    public override string CustomPackedIconPath => "thorns_temp.png".PowerImagePath();
    public override string CustomBigIconPath => "thorns_temp.png".BigPowerImagePath();
    public override List<(string, string)>? Localization =>
        (List<(string, string)>)new PowerLoc("Temporary Thorns",
            "Gain Thorns for this turn (removed at the end of your turn).",
            "Gain Thorns for this turn (removed at the end of your turn).");
}

/// <summary>Phase AN (v44) — Temporary Focus: +Focus now, removed at the end of your turn. Orb passives fire in
/// OrbQueue.BeforeTurnEnd (verified in the decompiled source), which runs BEFORE this power's AfterSideTurnEnd removal —
/// so a one-turn Focus boosts this turn's evokes AND this turn's end-of-turn passives, then expires. Orb-class only
/// (like focus): on a class with no orb slots it does nothing.</summary>
public sealed class ForgedTempFocusPower : ForgedTempStatPower
{
    public override PowerModel InternallyAppliedPower => ModelDb.Power<FocusPower>();

    protected override Task ApplyInternal(PlayerChoiceContext ctx, Creature target, decimal amount,
        Creature? applier, CardModel? cardSource, bool silent)
        => BetaMainCompatibility.PowerCmd_.Apply.InvokeGeneric<Task<FocusPower?>, FocusPower>(
               null, ctx, target, amount, applier ?? target, cardSource, silent)!;

    protected override string? ExpiryLogTag => "[AN] temp_focus";

    public override string CustomPackedIconPath => "focus_temp.png".PowerImagePath();
    public override string CustomBigIconPath => "focus_temp.png".BigPowerImagePath();
    public override List<(string, string)>? Localization =>
        (List<(string, string)>)new PowerLoc("Temporary Focus",
            "Gain Focus for this turn (removed at the end of your turn).",
            "Gain Focus for this turn (removed at the end of your turn).");
}

/// <summary>Phase BL (v64, gap #66) — Temporary Strength DOWN on an ENEMY (Piercing Wail / Dark Shackles): -N Strength now,
/// restored at the end of the OWNER's side turn (the enemy's turn end — after it has attacked with less Strength).
/// BaseLib's <see cref="CustomTemporaryPowerModel"/> carries the inverted form (<c>InvertInternalPowerAmount</c>: apply
/// -amount, restore +Amount at expiry). <b>The Type override is MANDATORY:</b> the base shell reports
/// <c>InternallyAppliedPower.Type</c> = Buff, so Artifact would ignore the SHELL, eat only the inner -N Strength, and the
/// shell would still restore +N at turn end — an Artifact enemy would GAIN Strength. As a Debuff the whole shell is
/// what Artifact blocks (PowerCmd.Apply: modified amount 0 → BeforeApplied applies -0 = nothing, ApplyInternal skips a
/// 0-amount power), exactly like the base game's PiercingWailPower (a TemporaryStrengthPower with IsPositive=false).</summary>
public sealed class ForgedTempStrengthDownPower : ForgedTempStatPower
{
    public override PowerModel InternallyAppliedPower => ModelDb.Power<StrengthPower>();

    protected override bool InvertInternalPowerAmount => true;

    // MANDATORY (see the summary): the shell is a DEBUFF so Artifact negates all of it (never just the inner -N).
    public override PowerType Type => PowerType.Debuff;

    protected override Task ApplyInternal(PlayerChoiceContext ctx, Creature target, decimal amount,
        Creature? applier, CardModel? cardSource, bool silent)
        => BetaMainCompatibility.PowerCmd_.Apply.InvokeGeneric<Task<StrengthPower?>, StrengthPower>(
               null, ctx, target, amount, applier ?? target, cardSource, silent)!;

    /// <summary>Phase BL smoke tag: the restore ran at the end of the OWNER's (the enemy's) turn — log the Strength
    /// it left behind (the base removes the shell and re-applies +Amount; see CustomTemporaryPowerModel).</summary>
    public override async Task AfterSideTurnEnd(PlayerChoiceContext choiceContext, CombatSide side, IEnumerable<Creature> participants)
    {
        var people = participants as ICollection<Creature> ?? participants.ToList();
        var owner = Owner;
        bool mine = owner != null && people.Contains(owner);
        var had = Amount;
        await base.AfterSideTurnEnd(choiceContext, side, people);
        if (mine)
            MainFile.Logger.Info($"[BL] temp_strength_down expired (Str now {owner!.GetPowerAmount<StrengthPower>()}) on " +
                                 $"'{owner.Monster?.GetType().Name ?? "creature"}' (had {had}).");
    }

    public override string CustomPackedIconPath => "strength_down.png".PowerImagePath();
    public override string CustomBigIconPath => "strength_down.png".BigPowerImagePath();
    public override List<(string, string)>? Localization =>
        (List<(string, string)>)new PowerLoc("Strength Down",
            "Loses Strength until the end of its turn.",
            "Loses {Amount} Strength until the end of its turn."); // smartDescription: PowerModel adds "Amount"
}
