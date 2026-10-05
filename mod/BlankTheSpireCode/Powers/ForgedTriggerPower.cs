using System.Collections.Generic;
using System.Linq;
using BaseLib.Abstracts;
using BaseLib.Utils;
using BlankTheSpire.BlankTheSpireCode.Engine;
using MegaCrit.Sts2.Core.Combat;
using MegaCrit.Sts2.Core.Commands; // Phase BI (v61): PowerCmd.Remove (the this_turn self-removal, RagePower)
using MegaCrit.Sts2.Core.Entities.Cards;
using MegaCrit.Sts2.Core.Entities.Creatures;
using MegaCrit.Sts2.Core.Entities.Players;
using MegaCrit.Sts2.Core.Entities.Powers;
using MegaCrit.Sts2.Core.GameActions.Multiplayer;
using MegaCrit.Sts2.Core.Models;
using MegaCrit.Sts2.Core.Models.Orbs; // Phase BP (v67): OrbModel (the on_evoke hook)
using MegaCrit.Sts2.Core.Models.Powers; // Phase BE (v59): PoisonPower (the on_poison_damage detector)
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
    // Phase AK (v41): kinds that already fired THIS COMBAT, for the `once_per_combat` gate. Never cleared — this
    // power is a fresh instance per combat application (the relic-hook firedOnce pattern, RelicRunner.Fire).
    private readonly HashSet<string> _firedThisCombat = [];
    // Phase BI (v61, gap #62): the every_n occurrence count — matching events this combat (the relic `counters`
    // pattern, RelicRunner.Fire; a fresh power per combat, so it is never reset). Advanced BEFORE `when`.
    private int _everyNCount;

    public override PowerType Type => PowerType.Buff;
    // One trigger per card; replaying the same card doesn't stack the effect (literal-amount payload).
    // Phase BG (gap #60): a RIPEN power is Counter purely so the icon DRAWS A NUMBER — NPower only renders
    // DisplayAmount for Counter powers (the ForgedBalancePower finding) — and DisplayAmount below is the countdown,
    // never the stack; the ripen logic reads _ripenLeft, so a replay stacking Amount is harmless.
    // Phase BI (v61): an every_n power is Counter for the same reason (the icon shows how many events are left).
    public override PowerStackType StackType =>
        Trigger?.Trigger == "ripen" || (Trigger?.EveryN ?? 0) > 1 ? PowerStackType.Counter : PowerStackType.Single;

    /// <summary>Phase BG (gap #60): the number on the icon. For a ripen power it is the TURNS LEFT (the full
    /// countdown before the first turn-start initializes it), so the player always sees when it lands.
    /// Phase BI (v61): for an every_n power it is the EVENTS LEFT until the next fire (N, N-1, … 1).</summary>
    public override int DisplayAmount =>
        Trigger?.Trigger == "ripen" ? (_ripenLeft < 0 ? System.Math.Max(1, Trigger.Amount) : _ripenLeft)
        : (Trigger?.EveryN ?? 0) > 1 ? Trigger!.EveryN - _everyNCount % Trigger.EveryN
        : Amount;

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
        // Phase BI (v61, gap #62): a `scope:"this_turn"` reactive power lasts only the turn it was granted — remove it
        // at the end of the owner's own turn (RagePower.AfterSideTurnEnd; PowerCmd.Remove so AfterRemoved runs).
        if (t?.Scope == "this_turn" && side == Owner.Side && participants.Contains(Owner))
        {
            MainFile.Logger.Info($"[BI] this_turn trigger removed at turn end ('{SourceSpec?.Title ?? SourceSpec?.Id}', {t.Trigger}).");
            await PowerCmd.Remove(this);
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
            // Phase BN (v69, gap #73): a payload that auto-plays (Mayhem) waits for AfterAutoPrePlayPhaseEntered — after the hand
            // draw, where the base MayhemPower plays — so the whole payload fires there instead.
            if (PlaysCards(t)) return;
            Flash();
            await TriggerRunner.Run(t, player, ctx);
            return;
        }
        // Phase M (gap #6 "ripen"): wait t.Amount turn-starts, then fire the payload ONCE.
        if (t.Trigger == "ripen" && !_ripenFired)
        {
            if (_ripenLeft < 0) _ripenLeft = System.Math.Max(1, t.Amount);
            --_ripenLeft;
            InvokeDisplayAmountChanged(); // Phase BG (gap #60): the icon counts down live
            MainFile.Logger.Info($"[BG] ripen '{SourceSpec?.Title ?? SourceSpec?.Id}': {_ripenLeft} turn(s) left.");
            if (_ripenLeft <= 0)
            {
                _ripenFired = true;
                Flash();
                await TriggerRunner.Run(t, player, ctx);
                // Phase BG: a spent countdown is noise on the tray — remove it after its one shot.
                if (Owner != null)
                    Owner.RemovePowerInternal(this);
            }
        }
    }

    /// <summary>Phase BN (v69, gap #73): does this turn_start payload auto-play a card (Mayhem)?</summary>
    private static bool PlaysCards(EffectSpec t) => (t.Triggered ?? []).Any(x => x.Op == "autoplay");

    /// <summary>Phase BN (v69, gap #73): Mayhem — the base MayhemPower plays from AfterAutoPrePlayPhaseEntered (the hand is drawn
    /// and the turn's auto-play window is open), NOT AfterPlayerTurnStart. A turn_start payload carrying `autoplay` fires here.</summary>
    public override async Task AfterAutoPrePlayPhaseEntered(PlayerChoiceContext ctx, Player player)
    {
        var t = Trigger;
        if (t?.Trigger != "turn_start" || !PlaysCards(t) || Owner == null || player != Owner.Player) return;
        MainFile.Logger.Info($"[BN] mayhem payload from AfterAutoPrePlayPhaseEntered ('{SourceSpec?.Title ?? SourceSpec?.Id}').");
        Flash();
        await TriggerRunner.Run(t, player, ctx);
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
            if (t.OncePerCombat && _firedThisCombat.Contains("on_hp_lost")) return; // Phase AK (v41)
            if (!EveryNFires(t, "on_hp_lost")) return; // Phase BI (v61)
            _firingHpLost = true;
            try
            {
                Flash();
                MainFile.Logger.Info($"[H4] reactive trigger 'on_hp_lost' fired (unblocked {result.UnblockedDamage}).");
                await TriggerRunner.Run(t, Owner.Player, ctx);
                if (t.OncePerTurn) _firedThisTurn.Add("on_hp_lost");
                if (t.OncePerCombat) { _firedThisCombat.Add("on_hp_lost"); MainFile.Logger.Info("[AK] once_per_combat 'on_hp_lost' consumed."); }
            }
            finally { _firingHpLost = false; }
            return;
        }
        // attacked: the REACTIVE retaliate hook — fires when an ENEMY deals us damage (their turn). dealer.Player
        // == null identifies an enemy; our own payload damage lands on the enemy (guarded by _firing), so no loop.
        // Phase AK (v41): the dealer rides along as the `attacker` target so a riposte payload hits the one that struck.
        if (t.Trigger == "attacked")
        {
            if (target != Owner || dealer == null || dealer.Player != null) return;
            await FireReactive("attacked", ctx, dealer);
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
        await FireReactive(kind, ctx, cardFilter: cardPlay.Card);
    }

    // on_card_drawn: each time the owner draws a card. Guarded against a draw→draw payload loop by _firing.
    public override async Task AfterCardDrawn(PlayerChoiceContext ctx, CardModel card, bool fromHandDraw)
    {
        _combatCtx = ctx;
        if (Trigger?.Trigger != "on_card_drawn" || card?.Owner != Owner.Player) return;
        await FireReactive("on_card_drawn", ctx, cardFilter: card);
    }

    // on_damage_dealt: when the owner deals CARD damage (dealer is us + cardSource != null → excludes our own
    // orb/thorns/payload damage, so no loop). Per-hit, like base-game on-attack effects.
    // Phase AT (v50): damage dealt THROUGH the owner's pet counts too — the base game's own "you deal damage" idiom
    // (ReaperFormPower: `dealer == Owner || dealer.PetOwner?.Creature == Owner`; HandDrill likewise). A summon_attack
    // deals with the pet as dealer and no card, so the card-only gate silently excluded every summon class. A pet
    // hit needs no cardSource (the pet never deals thorns/orb/payload damage of ITS own — the only way it hits is a
    // summon_attack, card- or payload-driven); a payload summon_attack re-raising this hook is stopped by _firing.
    public override async Task AfterDamageGiven(PlayerChoiceContext ctx, Creature dealer, DamageResult result,
        ValueProp props, Creature target, CardModel cardSource)
    {
        // Phase BE (v59, gap #56): on_poison_damage — "whenever an enemy takes Poison damage". The base game's Poison
        // tick (PoisonPower.AfterSideTurnStart) is CreatureCmd.Damage(new ThrowingPlayerChoiceContext(), owner, amount,
        // Unblockable | Unpowered, null, null): no dealer, no card, and the stacks are still on the target when the
        // hooks run (PowerCmd.Decrement comes after). This hook is the right one — Hook.AfterDamageReceived is SKIPPED
        // when the tick kills, AfterDamageGiven always fires. The ctx here is a ThrowingPlayerChoiceContext, so it is
        // deliberately NOT stored in _combatCtx (AfterBlockGained reuses that). Our own damage_over_time tick has the
        // same shape and is excluded by ForgedStatusPower.CustomTickInProgress.
        if (Trigger?.Trigger == "on_poison_damage")
        {
            if (dealer != null || cardSource != null || props != (ValueProp.Unblockable | ValueProp.Unpowered)) return;
            if (target == null || target.Player != null || !target.HasPower<PoisonPower>()) return;
            if (ForgedStatusPower.CustomTickInProgress) return;
            MainFile.Logger.Info($"[BE] on_poison_damage: '{target.Monster?.GetType().Name ?? "enemy"}' took {result.UnblockedDamage} " +
                                 $"Poison damage ({target.GetPowerAmount<PoisonPower>()} stacks; HP {target.CurrentHp}{(target.IsAlive ? "" : ", killed")}).");
            await FireReactive("on_poison_damage", ctx);
            return;
        }
        _combatCtx = ctx;
        if (Trigger?.Trigger != "on_damage_dealt") return;
        bool byCard = dealer == Owner && cardSource != null;
        bool byPet = dealer != null && dealer != Owner && dealer.PetOwner?.Creature == Owner;
        if (!byCard && !byPet) return;
        if (byPet)
            MainFile.Logger.Info($"[AT] on_damage_dealt: pet '{(dealer.Monster as ForgedSummon)?.Source?.Name ?? dealer.Monster?.GetType().Name ?? "pet"}' " +
                                 $"dealt {result.TotalDamage} to '{target?.Monster?.GetType().Name ?? "target"}' — attributed to the owner.");
        await FireReactive("on_damage_dealt", ctx);
    }

    // Phase BO (v66, gap #74): on_shuffle — whenever the owner shuffles the discard pile into the draw pile (the game's
    // CardPileCmd.Shuffle raises Hook.AfterShuffle once per shuffle: an empty-draw-pile refill or a shuffle_hand / Reboot).
    // The ctx may come from a hand draw (turn start), so like on_poison_damage it is NOT stored in _combatCtx. A payload that
    // draws into another shuffle is stopped by FireReactive's _firing guard; once_per_* / every_n / this_turn apply as usual.
    public override async Task AfterShuffle(PlayerChoiceContext ctx, Player shuffler)
    {
        if (Trigger?.Trigger != "on_shuffle" || shuffler != Owner.Player) return;
        MainFile.Logger.Info($"[BO] on_shuffle fired ('{SourceSpec?.Title ?? SourceSpec?.Id}', draw pile " +
                             $"{shuffler.PlayerCombatState?.DrawPile.Cards.Count ?? 0}).");
        await FireReactive("on_shuffle", ctx);
    }

    // Phase BP (v67, gap #77): on_card_generated — whenever the OWNER creates a card for combat (an add_card token, an
    // add_status_card Wound — base Arsenal / Smokestack count both). The game hook hands no ctx (Arsenal applies with a
    // fresh ThrowingPlayerChoiceContext), so the payload runs on the latest captured ctx or a throwing one that is NEVER
    // stored. A payload that itself generates a card is stopped by FireReactive's _firing guard ([BP] re-entry blocked).
    public override async Task AfterCardGeneratedForCombat(CardModel card, Player? creator)
    {
        if (Trigger?.Trigger != "on_card_generated" || creator == null || creator.Creature != Owner) return;
        MainFile.Logger.Info($"[BP] on_card_generated fired ('{SourceSpec?.Title ?? SourceSpec?.Id}': '{card?.Title}' created" +
                             $"{(_firing.Contains("on_card_generated") ? ", inside its own payload" : "")}).");
        await FireReactive("on_card_generated", _combatCtx ?? new ThrowingPlayerChoiceContext());
    }

    // Phase BP (v67, gap #77): on_debuff_applied — the base SleightOfFleshPower filter verbatim (a non-zero change that reads
    // as a DEBUFF, on an ENEMY, applied BY the owner, never a temporary wrapper such as Strength Down's shell) plus the
    // optional Vicious-style `status` filter. The debuffed enemy rides the `attacker` slot, so a payload with target
    // "that_enemy" hits it. The ctx may be a ThrowingPlayerChoiceContext (a tick), so like on_poison_damage it is NOT stored.
    public override async Task AfterPowerAmountChanged(PlayerChoiceContext ctx, PowerModel power, decimal amount,
        Creature? applier, CardModel? cardSource)
    {
        var t = Trigger;
        if (t?.Trigger != "on_debuff_applied" || power == null) return;
        if (amount == 0m || power.GetTypeForAmount(amount) != PowerType.Debuff || power.Owner == null || !power.Owner.IsEnemy
            || applier != Owner || power is ITemporaryPower) return;
        if (t.Status != null && !DebuffMatches(power, t.Status)) return;
        MainFile.Logger.Info($"[BP] on_debuff_applied fired ('{SourceSpec?.Title ?? SourceSpec?.Id}': {power.GetType().Name} {amount} on " +
                             $"'{power.Owner.Monster?.GetType().Name ?? "enemy"}'{(t.Status != null ? $", filter {t.Status}" : "")}).");
        await FireReactive("on_debuff_applied", ctx, attacker: power.Owner);
    }

    /// <summary>Phase BP (v67): does <paramref name="power"/> carry the add_trigger's status filter (Vicious = Vulnerable)?
    /// Lockstep with ForgedCards.DebuffTriggerStatuses.</summary>
    private static bool DebuffMatches(PowerModel power, string status) => status switch
    {
        "vulnerable" => power is VulnerablePower,
        "weak"       => power is WeakPower,
        "frail"      => power is FrailPower,
        "poison"     => power is PoisonPower,
        "doom"       => power is DoomPower,
        _            => false,
    };

    // Phase BP (v67, gap #77): on_evoke — whenever one of the OWNER's orbs is evoked (OrbCmd.Evoke raises AfterOrbEvoked once
    // per evoke; orb classes only, generation-gated). A payload evoke re-entering is stopped by the _firing guard.
    public override async Task AfterOrbEvoked(PlayerChoiceContext ctx, OrbModel orb, IEnumerable<Creature> targets)
    {
        if (Trigger?.Trigger != "on_evoke" || orb == null || orb.Owner != Owner.Player) return;
        MainFile.Logger.Info($"[BP] on_evoke fired ('{SourceSpec?.Title ?? SourceSpec?.Id}': {orb.GetType().Name}).");
        await FireReactive("on_evoke", ctx);
    }

    // on_block_gained: when the owner gains Block (Juggernaut). AfterBlockGained hands no ctx → use the captured one.
    public override async Task AfterBlockGained(Creature creature, decimal amount, ValueProp props, CardModel cardSource)
    {
        if (Trigger?.Trigger != "on_block_gained" || creature != Owner || _combatCtx == null) return;
        await FireReactive("on_block_gained", _combatCtx);
    }

    /// <summary>Fire a reactive trigger's payload, guarded against re-entrancy (a payload that re-raises its own
    /// event) and gated by once_per_turn / once_per_combat (Phase AK) + the fire-time When (checked here so a failed
    /// condition doesn't burn a once-slot). <paramref name="attacker"/> is the creature that just hit us — supplied
    /// only by the <c>attacked</c> hook (Phase AK, v41) so a payload with target:"attacker" hits it back. Mirrors
    /// ForgedRelic.FireGuarded.</summary>
    private async Task FireReactive(string kind, PlayerChoiceContext ctx, Creature? attacker = null, CardModel? cardFilter = null)
    {
        var t = Trigger;
        if (t == null || t.Trigger != kind) return;
        if (_firing.Contains(kind))
        {
            // Phase BP (v67): a BP payload that re-raises its own event (a debuff payload on on_debuff_applied, a generated card
            // on on_card_generated, an evoke on on_evoke) is stopped here — tagged so the smoke proves the guard held.
            if (kind is "on_card_generated" or "on_debuff_applied" or "on_evoke")
                MainFile.Logger.Info($"[BP] re-entry blocked ({kind}).");
            return;
        }
        // Phase BI (v61, gap #62): the card_type filter (on_card_played / on_card_drawn hand in the card) — the relic
        // v48 filter (RelicRunner.Fire), with EffectRunner.HandKindMatches mapping attack/skill/power/non_attack/status.
        if (t.CardKind != null)
        {
            if (cardFilter == null || !EffectRunner.HandKindMatches(cardFilter, t.CardKind)) return;
            MainFile.Logger.Info($"[BI] card_type {t.CardKind} matched ({kind}: '{cardFilter.Title}').");
        }
        if (t.OncePerTurn && _firedThisTurn.Contains(kind)) return;
        if (t.OncePerCombat && _firedThisCombat.Contains(kind)) return;
        if (!EveryNFires(t, kind)) return; // Phase BI (v61): counted before `when` (relic parity)
        if (t.When != null)
        {
            bool open = Conditions.Evaluate(t.When, Owner.Player, null);
            if (EffectRunner.PhaseAmConditions.Contains(t.When.Kind)) // Phase AM (v43): prove the reactive-trigger gate
                MainFile.Logger.Info($"[AM] trigger {kind} gate {t.When.Kind} {(open ? "OPEN" : "closed")} " +
                                     $"(energy {Owner.Player.PlayerCombatState?.Energy ?? 0}, played {EffectRunner.CardsPlayedThisTurn(Owner.Player)} this turn; need {t.When.Value}).");
            if (!open) return;
        }
        _firing.Add(kind);
        try
        {
            Flash();
            // H4 verbose smoke logging: one line per reactive fire so a deep AutoSlay run shows the count
            // (proves the hook fires + no crash). [H4] tag greppable in %APPDATA%/SlayTheSpire2/logs/godot.log.
            MainFile.Logger.Info($"[H4] reactive trigger '{kind}' fired (payload {(t.Triggered?.Length ?? 0)} effect(s)).");
            await TriggerRunner.Run(t, Owner.Player, ctx, attacker);
            if (t.OncePerTurn) _firedThisTurn.Add(kind);
            if (t.OncePerCombat)
            {
                _firedThisCombat.Add(kind);
                MainFile.Logger.Info($"[AK] once_per_combat '{kind}' consumed (no further fires this combat).");
            }
        }
        finally { _firing.Remove(kind); }
    }

    /// <summary>Phase BI (v61, gap #62): advance the every_n counter for one matching event and say whether THIS one
    /// fires (the Nth, 2Nth…). A trigger without every_n always fires. Counted per combat (open decision 1).</summary>
    private bool EveryNFires(EffectSpec t, string kind)
    {
        if (t.EveryN <= 1) return true;
        int n = ++_everyNCount;
        InvokeDisplayAmountChanged();
        bool fires = n % t.EveryN == 0;
        MainFile.Logger.Info($"[BI] every_n count {n}/{t.EveryN} — {(fires ? "FIRES" : "waiting")} ({kind}{(t.CardKind != null ? " " + t.CardKind : "")}).");
        return fires;
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
                "on_poison_damage" => "On Poison Damage", // Phase BE (v59)
                "on_shuffle" => "On Shuffle", // Phase BO (v66)
                "on_card_generated" => "On Card Created", "on_debuff_applied" => "On Debuff Applied", // Phase BP (v67)
                "on_evoke" => "On Evoke", // Phase BP (v67)
                _ => "Turn End",
            };
            string desc = t != null ? ForgedCards.DescribeTrigger(t) : "A forged trigger.";
            return (List<(string, string)>)new PowerLoc(title, desc, desc);
        }
    }
}
