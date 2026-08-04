using System.Collections.Generic;
using System.Threading.Tasks;
using BaseLib.Abstracts;
using BaseLib.Utils;
using BlankTheSpire.BlankTheSpireCode.Engine;
using MegaCrit.Sts2.Core.Entities.Creatures;
using MegaCrit.Sts2.Core.Entities.Players;
using MegaCrit.Sts2.Core.Entities.Powers;
using MegaCrit.Sts2.Core.GameActions.Multiplayer;
using MegaCrit.Sts2.Core.Models;
using MegaCrit.Sts2.Core.ValueProps;

namespace BlankTheSpire.BlankTheSpireCode.Powers;

/// <summary>
/// EXPLORE SPIKE (not in the LLM contract) — the first MODIFIER-family custom status: a buff that makes the
/// owner's attacks deal extra damage equal to its stacks. The whole point is to prove that a player-applied
/// <see cref="CustomPowerModel"/> actually receives the <c>Modify*</c> return-value hooks mid-combat (Phase H3
/// only proved the <c>After*Turn*</c> reactive hooks fire). If <see cref="ModifyDamageAdditive"/> below is
/// invoked and the buffed number lands, the entire modifier family (deal/take more/less, +block, +draw,
/// +energy, +hits, …) is unblocked and a real "forged statuses" phase can mirror the H3/I pattern.
///
/// Secondary spike: the name/description carry EMOJI to test whether Godot renders emoji glyphs in the power
/// tooltip (the realistic "display name" for a generated status). The on-creature icon badge is a separate
/// experiment — see <see cref="EmojiIconRenderer"/>.
/// </summary>
public sealed class SpikeSharpenPower : BlankTheSpirePower
{
    public override PowerType Type => PowerType.Buff;
    // Counter = re-applying adds stacks (so "Sharpen 3" then "Sharpen 2" -> 5), the normal numeric-buff behaviour.
    public override PowerStackType StackType => PowerStackType.Counter;

    /// <summary>Apply <paramref name="amount"/> stacks of Sharpen to the player (self), with a literal amount and
    /// no card context — mirrors <c>TriggerRunner</c>'s self-apply path (the generic Apply needs the concrete
    /// power type at the call site).</summary>
    public static Task Apply(PlayerChoiceContext ctx, Player owner, int amount)
        => BetaMainCompatibility.PowerCmd_.Apply.InvokeGeneric<Task<SpikeSharpenPower?>, SpikeSharpenPower>(
               null, ctx, owner.Creature, (decimal)amount, owner.Creature, (CardModel?)null, false)!;

    /// <summary>The hook UNDER TEST. Fires while computing a damage event; we add this power's stack count
    /// (<see cref="MegaCrit.Sts2.Core.Entities.Powers.PowerModel.Amount"/>) to the amount, but ONLY when the
    /// dealer is our owner — so it buffs the player's own attacks and never the enemy's.</summary>
    public override decimal ModifyDamageAdditive(
        Creature target, decimal amount, ValueProp props, Creature dealer, CardModel cardSource)
    {
        // The return value is the BONUS DELTA the game ADDS to the damage (not the new total) — confirmed in-game:
        // returning amount+Amount made a 6 hit deal 15 (6 + 9). So contribute just our stack count, and 0 for
        // damage we don't deal. PowerModel.Owner is the Creature this power sits on; buff only damage WE deal.
        return dealer == Owner ? Amount : 0m;
    }

    // Emoji in the title — the in-code tooltip test (no .pck rebuild). Description kept emoji-free/clean.
    public override List<(string, string)>? Localization =>
        (List<(string, string)>)new PowerLoc(
            "🗡️ Sharpen",
            "Your attacks deal bonus damage equal to its stacks.",
            "Your attacks deal bonus damage equal to its stacks.");

    // Emoji-as-icon experiment: a runtime-rendered PNG of an emoji glyph (see EmojiIconRenderer). Returns null
    // until the render is ready AND proven loadable by Godot's resource loader, so a failure can't hang/break
    // the badge — it just falls back to the shipped placeholder power.png (BlankTheSpirePower base path).
    public override string? CustomPackedIconPath => EmojiIconRenderer.IconPath("sharpen") ?? base.CustomPackedIconPath;
    public override string? CustomBigIconPath => EmojiIconRenderer.IconPath("sharpen") ?? base.CustomBigIconPath;
}
