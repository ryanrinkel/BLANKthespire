using System.Collections.Generic;
using System.Linq;
using System.Threading.Tasks;
using BaseLib.Abstracts;
using BlankTheSpire.BlankTheSpireCode.Engine;
using BlankTheSpire.BlankTheSpireCode.Extensions;
using MegaCrit.Sts2.Core.Combat;
using MegaCrit.Sts2.Core.Entities.Cards;
using MegaCrit.Sts2.Core.Entities.Creatures;
using MegaCrit.Sts2.Core.Entities.Potions;
using MegaCrit.Sts2.Core.GameActions.Multiplayer;

namespace BlankTheSpire.BlankTheSpireCode.Powers;

/// <summary>
/// Phase BA (v55): the base for the generated <c>ForgedClassKKPotionM</c> shells — one compiled type per class
/// potion slot, because a potion's identity (like a card's) binds to its .NET Type and pools freeze at init (Q1).
/// The shell sets <see cref="PotionClass"/> / <see cref="PotionIndex"/>; this base reads that slot's
/// <see cref="PotionSpec"/> and runs its effects on use.
///
/// BA-0 findings baked in:
/// <list type="bullet">
/// <item><c>PotionModel.OnUse</c> is handed a <c>PlayerChoiceContext</c> — the exact first argument of
/// <see cref="EffectRunner.RunRelicEffects"/>. A potion is therefore "a relic hook fired on demand", and needs
/// NO new effect runner.</item>
/// <item>Potions target differently from cards: <c>TargetType.Self</c> DOES receive a target (the owner), per
/// PotionModel's own "Do not try to unify this with CardModel.IsValidTarget" note. <c>AllEnemies</c> receives
/// null and the enemies are gathered from the combat state.</item>
/// <item>The icon surface is PATH-based, and BaseLib Harmony-patches the PRIVATE <c>PackedImagePath</c> getter
/// (verified by reflection) — so overriding <see cref="CustomPackedImagePath"/> reaches EVERY consumer,
/// including the potion bar, the tooltip, and the throw VFX's <c>Image</c>.</item>
/// <item>A slot with no spec must never reach the drop table; <c>ForgedClassPotionPoolKK.GetUnlockedPotions</c>
/// withholds it (that method is NOT cached, unlike <c>AllPotions</c>).</item>
/// </list>
/// </summary>
public abstract class ForgedPotion : CustomPotionModel
{
    /// <summary>The 1-based class index this potion belongs to (set by the generated shell).</summary>
    protected abstract int PotionClass { get; }

    /// <summary>The 1-based potion slot within that class (set by the generated shell).</summary>
    protected abstract int PotionIndex { get; }

    /// <summary>This slot's forged potion spec, or null (an unfilled slot — every pre-v55 class).</summary>
    public PotionSpec? Source => ForgedCharacters.PotionSpecFor(PotionClass, PotionIndex);

    /// <summary>True when this shell has no spec behind it, so the pool must withhold it from every roll.</summary>
    public bool IsEmptySlot => Source == null;

    /// <summary>Emoji-icon key, matching the <c>MainFile</c> pre-render (see <see cref="EmojiIconRenderer"/>).</summary>
    private string IconKey => $"potion{PotionClass}_{PotionIndex}";

    // --- the three abstract members PotionModel demands -----------------------------------------------------

    public override PotionRarity Rarity => Source?.Rarity switch
    {
        "uncommon" => PotionRarity.Uncommon,
        "rare"     => PotionRarity.Rare,
        _          => PotionRarity.Common,
    };

    public override PotionUsage Usage => Source?.Usage == "any" ? PotionUsage.AnyTime : PotionUsage.CombatOnly;

    public override TargetType TargetType => Source?.Target switch
    {
        "enemy"       => TargetType.AnyEnemy,
        "all_enemies" => TargetType.AllEnemies,
        _             => TargetType.Self,
    };

    // A potion whose effects need a live combat must not be offered by in-combat random generation when it could
    // not resolve; `heal` is the only op we allow out of combat, and the base game filters healing potions out of
    // in-combat generation for exactly that reason (the FruitJuice convention).
    public override bool CanBeGeneratedInCombat => Source?.Usage != "any";

    // Icon: the class's harness-picked emoji, rasterized to a loadable .res at init (EmojiIconRenderer probes
    // loadability before exposing a path, so a failed render never reaches the game's icon pipeline). Fallback is
    // the shipped generic relic art — deliberately a REAL shipped path, because a null image would NRE NPotion.
    public override string? CustomPackedImagePath =>
        EmojiIconRenderer.IconPath(IconKey) ?? "relic.png".RelicImagePath();
    public override string? CustomPackedOutlinePath => EmojiIconRenderer.IconPath(IconKey);

    // In-code localization (no .pck rebuild) — without this the potion's name/tooltip show the raw loc KEY.
    // Mirrors ForgedRelic/ForgedOrb: the spec's Name + Description become the potion's Title/Description.
    // (PotionLoc's trailing params are EXTRA loc pairs, not a third string — no selectionScreenPrompt is needed
    // because none of the v1 ops opens a card picker.)
    public override List<(string, string)>? Localization
    {
        get
        {
            var s = Source;
            return s == null ? null : (List<(string, string)>)new PotionLoc(s.Name, s.Description);
        }
    }

    // --- the effect entry point -----------------------------------------------------------------------------

    protected override async Task OnUse(PlayerChoiceContext choiceContext, Creature? target)
    {
        var s = Source;
        if (s == null) return;                       // an unfilled slot should never be reachable; no-op if it is
        var player = Owner;
        if (player is null) return;

        var targets = ResolveTargets(s.Target, player.Creature, target);
        MainFile.Logger.Info($"[BA] potion '{s.Name}' (class {PotionClass:00} slot {PotionIndex}) used: " +
                             $"target={s.Target} ({targets.Count} creature(s)), {s.Effects.Length} effect(s).");
        await EffectRunner.RunRelicEffects(s.Effects, choiceContext, player, targets, PotionClass, s.Target);
        MainFile.Logger.Info($"[BA] potion '{s.Name}' resolved.");
    }

    /// <summary>The creature list the effects run against. A `self` potion passes an EMPTY list (the runner sends
    /// self-ops at the owner regardless); `enemy` uses the creature the player picked; `all_enemies` gathers the
    /// living hittable enemies, since OnUse is handed no target for a non-single-target potion.</summary>
    private static List<Creature> ResolveTargets(string target, Creature owner, Creature? picked)
    {
        if (target == "all_enemies")
        {
            var cs = owner.CombatState;
            return cs == null ? [] : cs.HittableEnemies.Where(c => c.IsAlive).ToList();
        }
        if (target == "enemy")
        {
            if (picked is { IsAlive: true }) return [picked];
            // Defensive: a targeted potion always arrives with a target, but if one died between pick and
            // resolution, fall back to the first living enemy rather than silently doing nothing.
            var first = owner.CombatState?.HittableEnemies.FirstOrDefault(c => c.IsAlive);
            return first != null ? [first] : [];
        }
        return [];
    }
}
