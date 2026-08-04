using System.Collections.Generic;
using System.Linq;
using BaseLib.Abstracts;
using BaseLib.Utils;
using BlankTheSpire.BlankTheSpireCode.Engine;
using MegaCrit.Sts2.Core.Combat;
using MegaCrit.Sts2.Core.Entities.Cards;
using MegaCrit.Sts2.Core.Entities.Creatures;
using MegaCrit.Sts2.Core.Entities.Players;
using MegaCrit.Sts2.Core.Entities.Powers;
using MegaCrit.Sts2.Core.GameActions.Multiplayer;
using MegaCrit.Sts2.Core.Models;
using MegaCrit.Sts2.Core.ValueProps;

namespace BlankTheSpire.BlankTheSpireCode.Powers;

/// <summary>
/// Phase H3: the base for the generated <c>ForgedTriggerPowerNN</c> / <c>ForgedClassKTriggerPowerNN</c> shells
/// (one per card slot — a power's behaviour is bound to its compiled .NET Type, so each card that could carry a
/// trigger needs its own power type). The shell binds to its card slot via <see cref="SourceSpec"/>; this base
/// reads that card's single <c>add_trigger</c> effect and, at the matching turn hook, runs its payload through
/// <see cref="TriggerRunner"/> (gated by the trigger's fire-time <c>When</c>). The power is granted unconditionally
/// when the card is played (see EffectRunner.add_trigger) and persists for the combat.
/// </summary>
public abstract class ForgedTriggerPower : BlankTheSpirePower
{
    /// <summary>The card spec this power's trigger comes from (the bound slot's spec). Null on an unfilled slot.</summary>
    protected abstract CardSpec? SourceSpec { get; }

    /// <summary>The card's single add_trigger effect (kind + payload + fire-time When), or null.</summary>
    private EffectSpec? Trigger => SourceSpec?.Effects.FirstOrDefault(e => e.Op == "add_trigger");

    // Phase M (gap #6 "ripen"): a one-shot countdown. -1 = not yet initialized; once initialized it counts
    // down one per turn-start and fires the payload ONCE at zero. Instance state (a fresh power per combat
    // application), so it resets every combat. Only used when Trigger.Trigger == "ripen".
    private int _ripenLeft = -1;
    private bool _ripenFired;

    // Phase M (gap #9 "on_hp_lost"): re-entrancy guard so a lose_hp inside the payload doesn't recurse.
    private bool _firingHpLost;

    // Phase H4 (gaps #13/#14): reactive triggers mirror the ForgedRelic hooks.
    //  _firing      — per-kind re-entrancy guard (a payload that re-raises its own event, e.g. draw→on_card_drawn).
    //  _firedThisTurn — kinds that already fired this turn, for the `once_per_turn` gate (reset at our turn start).
    //  _combatCtx   — the latest ctx captured from a hook that hands one, so AfterBlockGained (which doesn't) can fire.
    private readonly HashSet<string> _firing = [];
    private readonly HashSet<string> _firedThisTurn = [];
    private PlayerChoiceContext? _combatCtx;

    public override PowerType Type => PowerType.Buff;
    // One trigger per card; replaying the same card doesn't stack the effect (literal-amount payload).
    public override PowerStackType StackType => PowerStackType.Single;

    /// <summary>Grant trigger power <typeparamref name="T"/> to the player (self), amount 1. Done from the card
    /// leaf because the generic apply needs the concrete power type at the call site.</summary>
    public static Task Apply<T>(PlayerChoiceContext ctx, Player owner) where T : ForgedTriggerPower
        => BetaMainCompatibility.PowerCmd_.Apply.InvokeGeneric<Task<T?>, T>(
               null, ctx, owner.Creature, 1m, owner.Creature, (CardModel?)null, false)!;

    public override async Task AfterSideTurnEnd(PlayerChoiceContext ctx, CombatSide side, IEnumerable<Creature> participants)
    {
        _combatCtx = ctx;
        var t = Trigger;
        // Fire only at the END of the owner's OWN side's turn.
        if (t?.Trigger == "turn_end" && side == Owner.Side)
        {
            Flash();
            await TriggerRunner.Run(t, Owner.Player, ctx);
        }
    }

    public override async Task AfterPlayerTurnStart(PlayerChoiceContext ctx, Player player)
    {
        _combatCtx = ctx;
        var t = Trigger;
        if (t == null || Owner != player.Creature) return;
        _firedThisTurn.Clear();   // H4: a new turn resets every once_per_turn gate
        if (t.Trigger == "turn_start")
        {
            Flash();
            await TriggerRunner.Run(t, player, ctx);
            return;
        }
        // Phase M (gap #6 "ripen"): wait t.Amount turn-starts, then fire the payload ONCE.
        if (t.Trigger == "ripen" && !_ripenFired)
        {
            if (_ripenLeft < 0) _ripenLeft = System.Math.Max(1, t.Amount);
            if (--_ripenLeft <= 0)
            {
                _ripenFired = true;
                Flash();
                await TriggerRunner.Run(t, player, ctx);
            }
        }
    }

    // gap #9 "on_hp_lost" (Rupture) + H4 "attacked" (reactive Thorns) share the damage-received hook.
    public override async Task AfterDamageReceived(PlayerChoiceContext ctx, Creature target, DamageResult result,
        ValueProp props, Creature? dealer, CardModel? cardSource)
    {
        _combatCtx = ctx;
        var t = Trigger;
        if (t == null) return;
        // on_hp_lost: fire when the owner takes UNBLOCKED HP loss during its OWN turn — scoping this to
        // self-inflicted/card HP loss (enemy attacks land on the enemy's turn), like base-game RupturePower. Its
        // own re-entrancy guard stops a lose_hp payload from recursing; honors once_per_turn if set.
        if (t.Trigger == "on_hp_lost")
        {
            if (target != Owner || result.UnblockedDamage <= 0 || CombatState.CurrentSide != Owner.Side) return;
            if (_firingHpLost) return;
            if (t.OncePerTurn && _firedThisTurn.Contains("on_hp_lost")) return;
            _firingHpLost = true;
            try
            {
                Flash();
                MainFile.Logger.Info($"[H4] reactive trigger 'on_hp_lost' fired (unblocked {result.UnblockedDamage}).");
                await TriggerRunner.Run(t, Owner.Player, ctx);
                if (t.OncePerTurn) _firedThisTurn.Add("on_hp_lost");
            }
            finally { _firingHpLost = false; }
            return;
        }
        // attacked: the REACTIVE retaliate hook — fires when an ENEMY deals us damage (their turn). dealer.Player
        // == null identifies an enemy; our own payload damage lands on the enemy (guarded by _firing), so no loop.
        if (t.Trigger == "attacked")
        {
            if (target != Owner || dealer == null || dealer.Player != null) return;
            await FireReactive("attacked", ctx);
        }
    }

    // ── H4 reactive card hooks (mirror ForgedRelic; grant to the power's owner, run the payload via FireReactive) ──

    // on_exhaust: whenever one of the owner's cards is Exhausted (Feel No Pain / Dark Embrace).
    public override async Task AfterCardExhausted(PlayerChoiceContext ctx, CardModel card, bool causedByEthereal)
    {
        _combatCtx = ctx;
        if (Trigger?.Trigger != "on_exhaust" || card?.Owner != Owner.Player) return;
        await FireReactive("on_exhaust", ctx);
    }

    // on_card_played: after the owner plays a card (Rage / blade tempo). Payload never plays a card → no recursion.
    // on_blade_played (Phase T, Parry analogue): the same hook, filtered to the SIGNATURE BLADE — the played card
    // is a DataCard whose spec is a token (there is at most one token per class, so any token IS this blade).
    public override async Task AfterCardPlayed(PlayerChoiceContext ctx, CardPlay cardPlay)
    {
        _combatCtx = ctx;
        var kind = Trigger?.Trigger;
        if (kind is not ("on_card_played" or "on_blade_played") || cardPlay?.Card?.Owner != Owner.Player) return;
        if (kind == "on_blade_played" && cardPlay.Card is not DataCard { SpecIsToken: true }) return;
        await FireReactive(kind, ctx);
    }

    // on_card_drawn: each time the owner draws a card. Guarded against a draw→draw payload loop by _firing.
    public override async Task AfterCardDrawn(PlayerChoiceContext ctx, CardModel card, bool fromHandDraw)
    {
        _combatCtx = ctx;
        if (Trigger?.Trigger != "on_card_drawn" || card?.Owner != Owner.Player) return;
        await FireReactive("on_card_drawn", ctx);
    }

    // on_damage_dealt: when the owner deals CARD damage (dealer is us + cardSource != null → excludes our own
    // orb/thorns/payload damage, so no loop). Per-hit, like base-game on-attack effects.
    public override async Task AfterDamageGiven(PlayerChoiceContext ctx, Creature dealer, DamageResult result,
        ValueProp props, Creature target, CardModel cardSource)
    {
        _combatCtx = ctx;
        if (Trigger?.Trigger != "on_damage_dealt" || dealer != Owner || cardSource == null) return;
        await FireReactive("on_damage_dealt", ctx);
    }

    // on_block_gained: when the owner gains Block (Juggernaut). AfterBlockGained hands no ctx → use the captured one.
    public override async Task AfterBlockGained(Creature creature, decimal amount, ValueProp props, CardModel cardSource)
    {
        if (Trigger?.Trigger != "on_block_gained" || creature != Owner || _combatCtx == null) return;
        await FireReactive("on_block_gained", _combatCtx);
    }

    /// <summary>Fire a reactive trigger's payload, guarded against re-entrancy (a payload that re-raises its own
    /// event) and gated by once_per_turn + the fire-time When (checked here so a failed condition doesn't burn the
    /// once_per_turn slot). Mirrors ForgedRelic.FireGuarded.</summary>
    private async Task FireReactive(string kind, PlayerChoiceContext ctx)
    {
        var t = Trigger;
        if (t == null || t.Trigger != kind) return;
        if (_firing.Contains(kind)) return;
        if (t.OncePerTurn && _firedThisTurn.Contains(kind)) return;
        if (t.When != null && !Conditions.Evaluate(t.When, Owner.Player, null)) return;
        _firing.Add(kind);
        try
        {
            Flash();
            // H4 verbose smoke logging: one line per reactive fire so a deep AutoSlay run shows the count
            // (proves the hook fires + no crash). [H4] tag greppable in %APPDATA%/SlayTheSpire2/logs/godot.log.
            MainFile.Logger.Info($"[H4] reactive trigger '{kind}' fired (payload {(t.Triggered?.Length ?? 0)} effect(s)).");
            await TriggerRunner.Run(t, Owner.Player, ctx);
            if (t.OncePerTurn) _firedThisTurn.Add(kind);
        }
        finally { _firing.Remove(kind); }
    }

    // In-code localization: the buff icon's tooltip is the trigger's synthesized sentence (no .pck rebuild).
    public override List<(string, string)>? Localization
    {
        get
        {
            var t = Trigger;
            string title = t?.Trigger switch
            {
                "turn_start" => "Turn Start", "ripen" => "Ripen", "on_hp_lost" => "On HP Lost",
                "on_exhaust" => "On Exhaust", "on_card_played" => "On Card Played",
                "on_card_drawn" => "On Card Drawn", "on_damage_dealt" => "On Damage Dealt",
                "on_block_gained" => "On Block Gained", "attacked" => "When Attacked",
                "on_blade_played" => "On Blade Played", // Phase T
                _ => "Turn End",
            };
            string desc = t != null ? ForgedCards.DescribeTrigger(t) : "A forged trigger.";
            return (List<(string, string)>)new PowerLoc(title, desc, desc);
        }
    }
}
