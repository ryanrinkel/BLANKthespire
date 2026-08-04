using System.Collections.Generic;
using System.Threading.Tasks;
using BaseLib.Abstracts;
using BaseLib.Utils;
using BlankTheSpire.BlankTheSpireCode.Engine;
using MegaCrit.Sts2.Core.Entities.Cards;
using MegaCrit.Sts2.Core.Entities.Players;
using MegaCrit.Sts2.Core.Entities.Powers;
using MegaCrit.Sts2.Core.GameActions.Multiplayer;
using MegaCrit.Sts2.Core.Models;

namespace BlankTheSpire.BlankTheSpireCode.Powers;

/// <summary>
/// Phase AB (VOCABULARY_GAPS #20): CORRUPTION — the reckless-tempo power. While active: your Skills cost 0, and
/// your Skills Exhaust when played. A verbatim rebuild of the base game's <c>CorruptionPower</c>
/// (<c>_modref/decomp_full/.../CorruptionPower.cs</c>) — both hooks are public <c>AbstractModel</c> overrides, so
/// NO Harmony patch is needed (the mod already uses the cost hook on <see cref="ForgedRelic"/> and the result-pile
/// hook on <see cref="DataCard.GetResultPileTypeForCardPlay"/>). Binary + per-combat: <see cref="PowerStackType.Single"/>
/// (re-applying is a no-op), the power dies at combat end. Granted by the <c>corruption</c> flag-op
/// (see <see cref="EffectRunner"/>). In-code loc + runtime emoji icon (the gap-#26 lesson: never depend on
/// base-game loc keys).
/// </summary>
public sealed class ForgedCorruptionPower : BlankTheSpirePower
{
    public override PowerType Type => PowerType.Buff;
    // Binary — you either have Corruption or you don't; re-applying never stacks.
    public override PowerStackType StackType => PowerStackType.Single;

    // Spam guard: the cost hook runs constantly (tooltip preview included), so log each Skill's cost-0 only once
    // per combat. Per-instance state — a fresh power each combat, so it resets naturally.
    private readonly HashSet<CardModel> _costLogged = new();

    /// <summary>Grant Corruption to the player (self), no card context — mirrors the <see cref="ForgedForgePower.Apply"/>
    /// / <see cref="ForgedBalancePower.Apply"/> self-apply path (the generic apply needs the concrete type at the call
    /// site). Amount 1 is a placeholder (binary power — the value is never read).</summary>
    public static Task Apply(PlayerChoiceContext ctx, Player owner)
        => BetaMainCompatibility.PowerCmd_.Apply.InvokeGeneric<Task<ForgedCorruptionPower?>, ForgedCorruptionPower>(
               null, ctx, owner.Creature, (decimal)1, owner.Creature, (CardModel?)null, false)!;

    /// <summary>Base-game hook (a): the owner's Skills cost 0. Scoped to this power's owner + <see cref="CardType.Skill"/>;
    /// returns false (unmodified) for everything else. Verbatim from <c>CorruptionPower</c>.</summary>
    public override bool TryModifyEnergyCostInCombatLate(CardModel card, decimal originalCost, out decimal modifiedCost)
    {
        if (card.Owner?.Creature != Owner || card.Type != CardType.Skill)
        {
            modifiedCost = originalCost;
            return false;
        }
        if (_costLogged.Add(card))
            MainFile.Logger.Info($"[AB] corruption: '{card.Id}' cost 0.");
        modifiedCost = default(decimal);
        return true;
    }

    /// <summary>Base-game hook (b): the owner's Skills go to the Exhaust pile when played. Scoped to owner +
    /// <see cref="CardType.Skill"/>; passes everything else through unchanged. Verbatim from <c>CorruptionPower</c>.</summary>
    public override (PileType, CardPilePosition) ModifyCardPlayResultPileTypeAndPosition(
        CardModel card, bool isAutoPlay, ResourceInfo resources, PileType pileType, CardPilePosition position)
    {
        if (card.Owner?.Creature != Owner || card.Type != CardType.Skill)
            return (pileType, position);
        MainFile.Logger.Info($"[AB] corruption: '{card.Id}' -> Exhaust.");
        return (PileType.Exhaust, position);
    }

    public override List<(string, string)>? Localization =>
        (List<(string, string)>)new PowerLoc("Corruption",
            "Your Skills cost 0. Your Skills Exhaust when played.",
            "Your Skills cost 0. Your Skills Exhaust when played.");

    // Emoji icon via the runtime renderer (kicked in MainFile); falls back to the shipped placeholder.
    public override string? CustomPackedIconPath => EmojiIconRenderer.IconPath("corruption") ?? base.CustomPackedIconPath;
    public override string? CustomBigIconPath => EmojiIconRenderer.IconPath("corruption") ?? base.CustomBigIconPath;
}
