using System;
using System.Collections.Generic;
using System.Threading.Tasks;
using BaseLib.Abstracts;
using BaseLib.Utils;
using BlankTheSpire.BlankTheSpireCode.Extensions;
using MegaCrit.Sts2.Core.Entities.Creatures;
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
