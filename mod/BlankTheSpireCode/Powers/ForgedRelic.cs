using System.Collections.Generic;
using System.Linq;
using BaseLib.Abstracts;
using BlankTheSpire.BlankTheSpireCode.Engine;
using BlankTheSpire.BlankTheSpireCode.Extensions;
using BlankTheSpire.BlankTheSpireCode.Relics;
using MegaCrit.Sts2.Core.Combat;
using MegaCrit.Sts2.Core.Commands;
using MegaCrit.Sts2.Core.Entities.Cards;
using MegaCrit.Sts2.Core.Entities.Creatures;
using MegaCrit.Sts2.Core.Entities.Players;
using MegaCrit.Sts2.Core.Entities.Relics;
using MegaCrit.Sts2.Core.GameActions.Multiplayer;
using MegaCrit.Sts2.Core.Models;
using MegaCrit.Sts2.Core.Rooms;
using MegaCrit.Sts2.Core.ValueProps;

namespace BlankTheSpire.BlankTheSpireCode.Powers;

/// <summary>
/// Phase L: the base for the generated <c>ForgedClassKKRelic</c> shells (one compiled type per class — a relic's
/// behaviour is bound to its .NET Type, so each class needs its own). The shell sets <see cref="RelicClass"/>;
/// this base reads that class's single <see cref="RelicSpec"/> and runs its hooks at the matching turn hook via
/// <see cref="RelicRunner"/>. The <c>ForgedCharacterSlotKK</c> shell equips this relic on startup only when the
/// class declares one (<c>ForgedCharacters.HasForgedRelic</c>), else it falls back to Burning Blood.
///
/// L-0 findings baked in: relics only receive combat hooks when <see cref="ShouldReceiveCombatHooks"/> is true;
/// <c>BeforeCombatStart()</c> passes no ctx/player so it's used ONLY to reset the per-combat once-fired set;
/// turn_start/turn_end hand in (ctx, player), so all real effects run from those.
/// </summary>
public abstract class ForgedRelic : BlankTheSpireRelic
{
    /// <summary>The 1-based class index this relic belongs to (set by the generated shell).</summary>
    protected abstract int RelicClass { get; }

    /// <summary>This class's forged relic spec, or null (an unfilled slot / a class with no relic).</summary>
    protected RelicSpec? Source => ForgedCharacters.RelicSpecFor(RelicClass);

    /// <summary>Hook indices whose <c>once_per_combat</c> has already fired THIS combat (reset at combat start).</summary>
    private readonly HashSet<int> _firedOnce = [];

    /// <summary>L-3 <c>first_attack</c> (Akabeko): whether this combat's first card attack has already taken the
    /// bonus (reset at combat start).</summary>
    private bool _firstAttackUsed;

    /// <summary>L-4 <c>start_combat_block</c>: whether this combat's opening block has been granted (on turn 1).</summary>
    private bool _startBlockDone;

    /// <summary>L-4: the player + a recent ctx captured from the hooks that DO hand them, so the hooks that don't
    /// (<c>combat_end</c> from AfterCombatVictory, <c>on_block_gained</c> from AfterBlockGained) can still reach a
    /// Player + a usable PlayerChoiceContext. Set every turn/action; valid by the time block is gained / a combat ends.</summary>
    private Player? _combatPlayer;
    private PlayerChoiceContext? _combatCtx;

    /// <summary>L-4 re-entrancy guard: triggers currently mid-fire. A reactive hook whose effect re-raises its own
    /// event (on_card_drawn→draw, on_block_gained→block) would recurse forever; this drops the re-entrant fire.</summary>
    private readonly HashSet<string> _firing = [];

    // Only opt into combat hooks when there's a spec to run — AbstractModel won't dispatch turn/combat hooks
    // otherwise (L-0). A class without a forged relic never equips this shell anyway.
    public override bool ShouldReceiveCombatHooks => Source != null;

    // Forged relics are the class's starter relic (never rolled into rewards). RelicModel's one abstract member.
    public override RelicRarity Rarity => RelicRarity.Starter;

    // Icon: prefer the emoji icon delivered with the import (ForgedRelicIcon caches + takes over a
    // synthetic res:// path); else the missing-art fallback — RelicImagePath() returns relic.png when
    // the per-relic png is absent (L-0 confirmed).
    public override string PackedIconPath =>
        ForgedRelicIcon.TryGetPath(RelicClass) ?? "forged_relic_fallback.png".RelicImagePath();
    protected override string PackedIconOutlinePath =>
        ForgedRelicIcon.TryGetOutlinePath(RelicClass) ?? base.PackedIconOutlinePath;
    protected override string BigIconPath =>
        ForgedRelicIcon.TryGetPath(RelicClass) ?? base.BigIconPath;

    // In-code localization (no .pck rebuild) — without this the relic's name/tooltip show the raw loc KEY
    // (e.g. "...relic.title"). Mirrors ForgedOrb/ForgedStatusPower: the spec's Name + Description become the
    // relic's Title/Description. Flavor reuses the description (relics have no separate flavour line in the spec).
    public override List<(string, string)>? Localization
    {
        get
        {
            var s = Source;
            return s == null ? null : (List<(string, string)>)new RelicLoc(s.Name, s.Description, s.Description);
        }
    }

    // combat start: NO ctx/player here (L-0 unknown #2) — used solely to reset per-combat state for the new combat.
    public override Task BeforeCombatStart()
    {
        _firedOnce.Clear();
        _firstAttackUsed = false;
        _startBlockDone = false;
        _combatPlayer = null;
        _combatCtx = null;
        _firing.Clear();
        return Task.CompletedTask;
    }

    /// <summary>Fire a trigger's hooks, guarded against re-entrancy (a hook whose effect re-raises the same event).
    /// Captures the latest real ctx/player so the ctx-less hooks can reuse them.</summary>
    private async Task FireGuarded(string trigger, PlayerChoiceContext? ctx, Player player, Creature? attacker = null)
    {
        if (Source is null || ctx is null || !_firing.Add(trigger)) return;
        _combatCtx = ctx; _combatPlayer = player;
        try { await RelicRunner.Fire(Source, trigger, ctx, player, _firedOnce, attacker, RelicClass); }
        finally { _firing.Remove(trigger); }
    }

    public override async Task AfterPlayerTurnStart(PlayerChoiceContext ctx, Player player)
    {
        _combatCtx = ctx; _combatPlayer = player;
        await GrantStartCombatBlock(player);   // L-4 start_combat_block (no combat-start hook has a player → turn 1)
        await FireGuarded("turn_start", ctx, player);
    }

    public override async Task AfterSideTurnEnd(PlayerChoiceContext ctx, CombatSide side, IEnumerable<Creature> participants)
    {
        var player = participants.FirstOrDefault(c => c.Player != null)?.Player;
        if (player is null) return; // an enemy side's turn ended — not ours
        _combatPlayer = player;
        await FireGuarded("turn_end", ctx, player);
    }

    // attacked (L-3): the REACTIVE hook — fires whenever a creature takes damage. Run our hooks only when the
    // damaged creature is OUR player and the dealer is an enemy (dealer.Player == null), passing the dealer as the
    // "attacker" target so a Thorns-style hook can hit back. Our own retaliation damage lands on the enemy (whose
    // .Player is null), so the guard stops it re-triggering — no recursion.
    public override async Task AfterDamageReceived(PlayerChoiceContext ctx, Creature target, DamageResult result,
                                                   ValueProp props, Creature dealer, CardModel cardSource)
    {
        var player = target.Player;
        if (player is null) return;                            // not the player taking the hit
        // on_hp_lost (Phase P — gap #9 relic mirror): fire on the player's OWN-turn, UNBLOCKED, self/card-caused
        // HP loss (lose_hp cards, self-damage). Enemy attacks land on the enemy's turn → excluded by the own-turn
        // scope, matching base-game Rupture and the card-side twin. FireGuarded's per-trigger guard stops a
        // lose_hp payload from recursing. This runs regardless of dealer, so it precedes the enemy-only "attacked".
        // GUARD (found by AutoSlay 2026-07-13): out-of-combat EVENT damage (e.g. ColossalFlower "Reach Deeper")
        // also routes through this hook, but there is no active combat then → CombatState is null. A null combat
        // state means "not a combat HP-loss", so skip on_hp_lost rather than NRE-faulting the event task.
        var combat = player.Creature.CombatState;
        if (result.UnblockedDamage > 0 && combat != null && combat.CurrentSide == player.Creature.Side)
            await FireGuarded("on_hp_lost", ctx, player);
        if (dealer is null || dealer.Player != null) return;   // self-cost / non-enemy damage (lose_hp etc.) — ignore
        await FireGuarded("attacked", ctx, player, dealer);
    }

    // on_exhaust (L-3): reactive — fires whenever one of your cards is Exhausted (the Compost-Bin pattern). A
    // CardModel's Owner is the Player (dump: prop Player Owner). No attacker context here, so self/enemy/all_enemies
    // targets only. Relic ops never exhaust a card, so this can't re-trigger itself.
    public override async Task AfterCardExhausted(PlayerChoiceContext ctx, CardModel card, bool causedByEthereal)
    {
        var player = card?.Owner;
        if (player is null) return;
        await FireGuarded("on_exhaust", ctx, player);
    }

    // on_card_played (L-3): reactive — fires after you play a card (the Watering-Can / tempo pattern). The played
    // card's Owner is the Player. Effects never play a card, so no AfterCardPlayed recursion. (v1 fires on ANY card.)
    public override async Task AfterCardPlayed(PlayerChoiceContext ctx, CardPlay cardPlay)
    {
        var player = cardPlay?.Card?.Owner;
        if (player is null) return;
        await FireGuarded("on_card_played", ctx, player);
    }

    // on_card_drawn (L-4): reactive — fires each time you draw a card. Guarded against the draw→draw loop.
    public override async Task AfterCardDrawn(PlayerChoiceContext ctx, CardModel card, bool fromHandDraw)
    {
        var player = card?.Owner;
        if (player is null) return;
        await FireGuarded("on_card_drawn", ctx, player);
    }

    // on_damage_dealt (L-4): reactive — fires when YOU deal CARD damage (dealer is the player + cardSource != null,
    // which excludes our own relic/thorns/orb damage → no loop). Per-hit, like the base game's on-attack effects.
    public override async Task AfterDamageGiven(PlayerChoiceContext ctx, Creature dealer, DamageResult result,
                                                ValueProp props, Creature target, CardModel cardSource)
    {
        if (dealer?.Player is not Player player || cardSource is null) return;
        // Consume the first_attack (Akabeko) one-shot on the FIRST real card hit — here, on actual damage, NOT in
        // ModifyDamageAdditive (which the engine also runs for the tooltip preview). Per-hit, so a multi-hit first
        // attack only buffs its first hit, matching the prior intent — but previews no longer burn the bonus.
        _firstAttackUsed = true;
        await FireGuarded("on_damage_dealt", ctx, player);
    }

    // on_block_gained (L-4): reactive — fires when you gain Block. Uses the last captured ctx (AfterBlockGained hands
    // none). Guarded against the block→block loop.
    public override async Task AfterBlockGained(Creature creature, decimal amount, ValueProp props, CardModel cardSource)
    {
        if (creature?.Player is not Player player) return;
        await FireGuarded("on_block_gained", _combatCtx, player);
    }

    // combat_end (L-4): fires on victory. AfterCombatVictory passes only the room, so we heal the player captured
    // during the combat's turns (validator restricts combat_end effects to the ctx-free `heal`).
    public override async Task AfterCombatVictory(CombatRoom room)
    {
        if (_combatPlayer is not null && _combatCtx is not null)
            await FireGuarded("combat_end", _combatCtx, _combatPlayer);
    }

    // L-4 modifier: start_combat_block — gain N Block on turn 1 (no combat-start hook hands a player, so turn 1 is
    // the earliest point we can; functionally identical to "start combat with N Block").
    private async Task GrantStartCombatBlock(Player player)
    {
        if (_startBlockDone) return;
        int block = Source?.Modifiers.Where(m => m.Stat == "start_combat_block").Sum(m => m.Amount) ?? 0;
        _startBlockDone = true;
        if (block > 0) await CreatureCmd.GainBlock(player.Creature, block, ValueProp.Move, null, false);
    }

    // modifier: max_energy (+N energy/turn), summed over the spec's max_energy modifiers.
    public override decimal ModifyEnergyGain(Player player, decimal amount)
    {
        var mods = Source?.Modifiers;
        if (mods == null) return amount;
        int bonus = mods.Where(m => m.Stat == "max_energy").Sum(m => m.Amount);
        return amount + bonus;
    }

    // modifier: first_attack (Akabeko) — +N to the FIRST card attack you deal each combat. ModifyDamageAdditive
    // fires on every damage instance, so gate to a player card attack (dealer is the player, cardSource != null —
    // excludes thorns/poison/orb passives) and one-shot it via _firstAttackUsed (reset at combat start).
    public override decimal ModifyDamageAdditive(Creature target, decimal amount, ValueProp props, Creature dealer, CardModel cardSource)
    {
        // Return the BONUS DELTA the game ADDS to the hit (0 = unchanged), NOT the new total — the contract every
        // other Modify*Additive here follows (ForgedStatusPower / SpikeSharpenPower). Returning `amount` added the
        // hit's own base back onto it, DOUBLING every player card attack for any class with a forged relic (the
        // Strike→12 bug). Also READ-ONLY: the engine runs this for the tooltip preview too, so the first_attack
        // one-shot must be consumed in AfterDamageGiven (on real damage), never here.
        var mods = Source?.Modifiers;
        if (mods == null || _firstAttackUsed) return 0m;
        if (dealer?.Player == null || cardSource == null) return 0m;
        return mods.Where(m => m.Stat == "first_attack").Sum(m => m.Amount);  // 0 unless this relic grants first_attack
    }

    // modifier: cost_reduction (the L-3 cost primitive, done right) — every card's ENERGY cost is reduced by N in
    // combat (floored at 0), via the engine's per-card cost-query hook. This is how real relics (e.g. SpikedGauntlets)
    // do it; a per-card "reduce_cost" effect can't, since there's no temporary per-card energy mutation.
    public override bool TryModifyEnergyCostInCombat(CardModel card, decimal originalCost, out decimal modifiedCost)
    {
        modifiedCost = originalCost;
        int reduce = Source?.Modifiers.Where(m => m.Stat == "cost_reduction").Sum(m => m.Amount) ?? 0;
        if (reduce <= 0) return false;
        modifiedCost = Math.Max(0, originalCost - reduce);
        return true;
    }
}
