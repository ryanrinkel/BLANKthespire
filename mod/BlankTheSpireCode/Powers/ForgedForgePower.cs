using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading.Tasks;
using BaseLib.Abstracts;
using BaseLib.Utils;
using BlankTheSpire.BlankTheSpireCode.Engine;
using MegaCrit.Sts2.Core.Commands;
using MegaCrit.Sts2.Core.Entities.Cards;
using MegaCrit.Sts2.Core.Entities.Players;
using MegaCrit.Sts2.Core.Entities.Powers;
using MegaCrit.Sts2.Core.GameActions.Multiplayer;
using MegaCrit.Sts2.Core.Models;
using MegaCrit.Sts2.Core.Rooms;

namespace BlankTheSpire.BlankTheSpireCode.Powers;

/// <summary>
/// Phase M (VOCABULARY_GAPS #36): the player-level Forge counter — the base-game "Forge N" repeat-empower
/// keyword (Sovereign Blade), rebuilt closed-vocab and parallel to (never touching) the game's AfterForge
/// machinery. The <c>forge</c> op (cards, trigger payloads, relic hooks) adds stacks; a damage/block effect
/// with <c>scale:"forged"</c> ADDS the current stacks to its printed amount — the one ADDITIVE exception in
/// the F5 scale family (see <see cref="EffectRunner.ScaleValue"/> / <c>DataCard.BonusFor</c>). A pure counter:
/// no Modify* hooks; the payoff read lives at the card's calc-var sites. Per-combat by default (powers die at
/// combat end) — a class that sets <c>forge_persist</c> (Phase AY, v54) carries up to <see cref="PersistCap"/>
/// into its next combat instead, via <see cref="Engine.ForgePersist"/>. In-code loc + a runtime emoji icon
/// (the gap-#26 lesson: never depend on base-game loc keys).
/// </summary>
public sealed class ForgedForgePower : BlankTheSpirePower
{
    /// <summary>Phase AY (v54): the most Forge a <c>forge_persist</c> class may carry OUT of a combat. A HEAD START,
    /// never a snowball: without a ceiling the counter would compound floor after floor (a turn_start income engine
    /// banks ten-plus per fight, fifty fights a run) and every <c>scale:"forged"</c> payoff would print free damage by
    /// Act 2. Five is one good income card — and it is the threshold the contract's own example gate reads
    /// (<c>when forged_ge value:5</c>), so a ramping persist class opens the next fight already at its first payoff.</summary>
    public const int PersistCap = 5;

    public override PowerType Type => PowerType.Buff;
    // Counter: "Forge 3" then "Forge 2" -> 5 stacks — the base-game Forge accumulation.
    public override PowerStackType StackType => PowerStackType.Counter;

    /// <summary>Apply <paramref name="amount"/> Forge to the player (self) with a literal amount and no card
    /// context — mirrors <c>TriggerRunner</c>'s self-apply path (the generic Apply needs the concrete power
    /// type at the call site).</summary>
    public static Task Apply(PlayerChoiceContext ctx, Player owner, int amount)
        => BetaMainCompatibility.PowerCmd_.Apply.InvokeGeneric<Task<ForgedForgePower?>, ForgedForgePower>(
               null, ctx, owner.Creature, (decimal)amount, owner.Creature, (CardModel?)null, false)!;

    /// <summary>Phase AX (v53, gap #44): SPEND Forge — the cash-out half of the ramp. Reduces the counter by
    /// <paramref name="amount"/> and returns how much was ACTUALLY spent (0 with no Forge power; the whole
    /// remainder when the card asks for more than you hold — an over-ask empties the counter rather than
    /// failing, so an ungated <c>spend_forge</c> is weak, never broken). At 0 the power is removed, exactly like
    /// the Balance gauge at centre, so the next <see cref="Stoke"/> counts as a fresh first Forge and re-summons
    /// the blade if it is gone. Live-stack mutation (<c>Amount = …; InvokePowerModified(…)</c>) — the same path
    /// <see cref="ForgedBalancePower"/> and the Phase J status decay use, because PowerCmd.Apply only ADDS.</summary>
    public static int Spend(Player owner, int amount)
    {
        int want = Math.Max(1, amount);
        var creature = owner.Creature;
        var power = creature.HasPower<ForgedForgePower>() ? creature.GetPower<ForgedForgePower>() : null;
        if (power == null) return 0;
        int have = (int)power.Amount;
        if (have <= 0) { creature.RemovePowerInternal(power); return 0; }
        int spent = Math.Min(want, have);
        int left = have - spent;
        if (left <= 0) creature.RemovePowerInternal(power);
        else
        {
            power.Amount = left;
            creature.InvokePowerModified(power, -spent, false);
        }
        return spent;
    }

    /// <summary>Phase AY (v54): BANK this combat's Forge for the next one — the run-persistent half of the counter,
    /// for classes that opt in with <c>forge_persist</c>. Runs at combat end (see <see cref="AfterCombatEnd"/>),
    /// while the power is still alive: the game clears powers in <c>Player.AfterCombatEnd</c>, which comes AFTER the
    /// hook. Stores <c>min(stacks, PersistCap)</c> into the run save; <see cref="Engine.ForgePersist"/> pays it back
    /// at the start of the player's first turn of the next combat. A non-persist class never banks (and so always
    /// starts at zero, the Phase M default).</summary>
    private static void Bank(Player owner, int stacks)
    {
        int carry = Math.Min(Math.Max(stacks, 0), PersistCap);
        Engine.ForgePersist.Banked.Set(owner, carry);
        MainFile.Logger.Info($"[AY] forge banked: {stacks} at combat end -> carrying {carry} (cap {PersistCap}).");
    }

    /// <summary>Combat end: bank the counter for a <c>forge_persist</c> class. This hook still sees the live power
    /// (powers are cleared later, in <c>Player.AfterCombatEnd</c>), so <see cref="PowerModel.Amount"/> is this
    /// combat's final Forge.</summary>
    public override Task AfterCombatEnd(CombatRoom room)
    {
        var player = Owner?.Player;
        if (player != null && ForgedCharacters.IsForgePersistPlayer(player))
            Bank(player, (int)Amount);
        return Task.CompletedTask;
    }

    /// <summary>Phase T (Sovereign Blade — base-game Forge): stoke the counter AND, on the FIRST Forge income of
    /// combat, summon the class's signature blade to hand. The base game's blade is NOT in the deck — playing a
    /// Forge card creates it — so every income path (card / trigger payload / relic hook) routes through here.
    /// <paramref name="amount"/> stokes as usual (the first play both summons AND buffs: "Forge 3" as your opener
    /// summons the blade AND makes it hit for base+3 — the damage formula has no skip-the-first carve-out).</summary>
    public static async Task Stoke(PlayerChoiceContext ctx, Player owner, int amount)
    {
        int before = EffectRunner.ForgeStacks(owner); // 0 => no Forge power yet => this is the first income
        await Apply(ctx, owner, amount);
        if (before == 0)
            await SummonBlade(ctx, owner, fromAnywhere: false);
    }

    /// <summary>Phase T: put the forge class's signature blade into <paramref name="owner"/>'s hand. Two callers:
    /// the first-Forge summon (<c>fromAnywhere:false</c> — GENERATE a fresh blade), and the <c>summon_blade</c> op
    /// (<c>fromAnywhere:true</c> — the Summon-Forth analogue that also RETRIEVES an existing blade from draw/
    /// discard/exhaust). No-op when the class ships no blade (a pre-v20 class) or the blade is already in hand.
    /// GUARD: if the blade is already somewhere in combat we do NOT generate a second one — for the first-Forge
    /// path this is the legacy-innate compat (a v20-v24 blade sits in a pile from turn 1) AND a double-summon
    /// belt; for summon_blade it means "already in hand, nothing to do" (or pull it from wherever it sits).</summary>
    internal static async Task SummonBlade(PlayerChoiceContext ctx, Player owner, bool fromAnywhere)
    {
        int k = ForgedCharacters.ClassIndexOfPlayer(owner);
        string? bladeId = ForgedCharacters.BladeCardId(k);
        if (bladeId == null) return; // class has no signature blade (pre-v20) — nothing to summon

        // Find an existing blade across all piles (Spec is protected on DataCard, so match via SpecIsToken —
        // there is at most one token per class, so any token card in play IS this blade).
        var existing = owner.PlayerCombatState.AllCards
            .FirstOrDefault(c => c is DataCard dc && dc.SpecIsToken);
        if (existing != null)
        {
            // Already in hand → nothing to do (both callers). Elsewhere: only summon_blade RETRIEVES it to hand;
            // the first-Forge summon leaves an already-present blade where it is (it will cycle in normally).
            if (existing.Pile?.Type == PileType.Hand) return;
            if (!fromAnywhere) return; // first-Forge: don't move a blade that's mid-deck; only ever create one
            await CardPileCmd.Add(existing, PileType.Hand, CardPilePosition.Random);
            MainFile.Logger.Info($"[T] blade retrieved: '{bladeId}' -> hand (summon_blade).");
            return;
        }

        // No blade in combat: build a fresh OWNER-BOUND copy exactly like Phase Q's add_card and drop it in hand.
        var model = ForgedCharacters.ResolveClassCardModel(k, bladeId, owner, null);
        if (model == null) { MainFile.Logger.Warn($"[T] blade summon: could not resolve '{bladeId}' (class {k})."); return; }
        await CardPileCmd.AddGeneratedCardToCombat(model, PileType.Hand, owner, CardPilePosition.Random);
        MainFile.Logger.Info($"[T] blade summoned: '{bladeId}' -> hand ({(fromAnywhere ? "summon_blade" : "first Forge of combat")}).");
    }

    // The tooltip is baked ONCE, at ModelDb init (BaseLib's ModelLocPatch), so it cannot read the running class —
    // it has to be true for both regimes. Phase AY (v54): most classes still reset each combat; one that keeps its
    // edge carries up to PersistCap.
    public override List<(string, string)>? Localization =>
        (List<(string, string)>)new PowerLoc("Forge",
            "Your first Forge each combat summons your signature blade to your hand. Effects that add your Forge deal or block that much more. Forge resets each combat — unless your class keeps its edge, carrying up to 5 into the next fight.",
            "Your first Forge each combat summons your signature blade to your hand. Effects that add your Forge deal or block that much more. Forge resets each combat — unless your class keeps its edge, carrying up to 5 into the next fight.");

    // Emoji icon via the runtime renderer (kicked in MainFile); falls back to the shipped placeholder.
    public override string? CustomPackedIconPath => EmojiIconRenderer.IconPath("forge") ?? base.CustomPackedIconPath;
    public override string? CustomBigIconPath => EmojiIconRenderer.IconPath("forge") ?? base.CustomBigIconPath;
}
