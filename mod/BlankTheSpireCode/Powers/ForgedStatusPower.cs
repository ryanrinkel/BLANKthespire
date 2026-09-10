using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading.Tasks;
using BaseLib.Abstracts;
using BaseLib.Utils;
using BlankTheSpire.BlankTheSpireCode.Engine;
using MegaCrit.Sts2.Core.Combat;
using MegaCrit.Sts2.Core.Commands;          // Phase AQ: CreatureCmd.Damage for the damage_over_time tick
using MegaCrit.Sts2.Core.Commands.Builders; // Phase AQ: AttackCommand (ModifyAttackHitCount's attack.Attacker gate)
using MegaCrit.Sts2.Core.Entities.Cards;
using MegaCrit.Sts2.Core.Entities.Creatures;
using MegaCrit.Sts2.Core.Entities.Players;
using MegaCrit.Sts2.Core.Entities.Powers;
using MegaCrit.Sts2.Core.GameActions.Multiplayer;
using MegaCrit.Sts2.Core.Models;
using MegaCrit.Sts2.Core.ValueProps;

namespace BlankTheSpire.BlankTheSpireCode.Powers;

/// <summary>
/// Phase J: the base for the generated <c>ForgedClassKStatusM</c> shells (M = 1..4 per class) — the custom-status
/// analogue of <see cref="ForgedOrb"/> / <see cref="ForgedTriggerPower"/>. One status = one compiled
/// <see cref="CustomPowerModel"/> subclass (Q1), so the mod ships a fixed pool of generic shells; each reads its
/// <see cref="StatusSpec"/> from the class JSON (<see cref="ForgedCharacters.StatusSpecFor"/>) and behaves as a
/// MODIFIER: it overrides the return-value <c>Modify*</c> hooks and contributes its stack count to ONE number
/// (which one is the spec's <c>Hook</c>) while active.
///
/// A shell whose class declares no such custom status has a null <see cref="Source"/>: it still auto-registers
/// (the <see cref="CustomPowerModel"/> ICustomPower scan instantiates one per shell type at init, like the empty
/// orb/trigger shells), advertises a harmless zero-modifier no-op, and is simply never applied.
///
/// MVP families (J-1): the ADDITIVE hooks below. <c>damage_dealt</c>/<c>damage_taken</c>/<c>block_gained</c>
/// return a BONUS DELTA (the game adds the sum of all powers' returns to the base — confirmed for
/// <c>ModifyDamageAdditive</c> by the spike). <c>energy_gain</c>/<c>card_draw</c> use the bare transform hooks
/// (<c>ModifyEnergyGain</c>/<c>ModifyHandDraw</c>), which are handed the running value and return the modified
/// one. Every hook is gated on the relevant creature/player being THIS power's <see cref="PowerModel.Owner"/>, so
/// a buff only ever changes the owning player's numbers and a debuff only the afflicted enemy's.
///
/// Phase AQ (v47) lifted the J-1 cuts: <c>mode: multiplicative</c> on the two damage hooks rides
/// <c>ModifyDamageMultiplicative</c> (a FACTOR — the game multiplies the running damage by the product of every
/// power's return, Vulnerable/Weak-style; ×(1 + 0.1·stacks), capped at ×2, powered attacks only);
/// <c>hit_count</c> rides <c>ModifyAttackHitCount(AttackCommand, int)</c> gated on <c>attack.Attacker == Owner</c>
/// (the accessor the J-1 note thought was missing is public on the current AttackCommand) and returns
/// <c>hitCount + stacks</c> for the owner's CARD attacks; <c>damage_over_time</c> is the Poison recipe — at the
/// start of the OWNER's side's turn (<c>AfterSideTurnStart</c>, PoisonPower's hook) the owner takes <c>stacks</c>
/// unblockable, unpowered damage (<c>CreatureCmd.Damage</c>, the same props PoisonPower passes), then the existing
/// end-of-turn decay burns it down. Reactive hooks stay with <c>add_trigger</c>.
/// </summary>
public abstract class ForgedStatusPower : BlankTheSpirePower
{
    /// <summary>The 1-based class index this status belongs to (set by the generated shell).</summary>
    protected abstract int StatusClass { get; }

    /// <summary>The 1-based slot within the class's <c>status_pool</c> (1..4; set by the generated shell).</summary>
    protected abstract int StatusIndex { get; }

    /// <summary>This status's spec, or null on an unfilled shell (the class declared no such custom status).</summary>
    protected StatusSpec? Source => ForgedCharacters.StatusSpecFor(StatusClass, StatusIndex);

    /// <summary>Public view of this status's spec (used by <see cref="EffectRunner"/> to read its buff/debuff side).</summary>
    public StatusSpec? Spec => Source;

    // (class, status-index) -> the canonical registered instance. Populated in the ctor (the ICustomPower scan
    // creates one instance per shell type at init, and that instance IS the canonical model in ModelDb), so
    // ForgedCharacters can map a custom-status NAME -> its instance without referencing the generated symbols.
    private static readonly Dictionary<(int, int), ForgedStatusPower> _registry = new();

    protected ForgedStatusPower()
    {
        // StatusClass/StatusIndex are constant overrides (no field access), so reading them in the ctor is safe.
        _registry[(StatusClass, StatusIndex)] = this;
    }

    /// <summary>The canonical registered status instance for class <paramref name="k"/> slot <paramref name="m"/>,
    /// or null if no such shell registered.</summary>
    public static ForgedStatusPower? ForKey(int k, int m) =>
        _registry.TryGetValue((k, m), out var p) ? p : null;

    public override PowerType Type => (Source?.IsBuff ?? true) ? PowerType.Buff : PowerType.Debuff;
    public override PowerStackType StackType =>
        (Source?.SingleStack ?? false) ? PowerStackType.Single : PowerStackType.Counter;

    // --- application (the concrete .NET type is needed at the call site, so the generated leaf supplies it) ----

    /// <summary>Apply <paramref name="amount"/> stacks of THIS status to <paramref name="target"/> from
    /// <paramref name="source"/>. Overridden by the generated leaf with its own concrete type (the generic apply
    /// needs the power type at the call site, mirroring <see cref="ForgedTriggerPower.Apply"/>).</summary>
    public abstract Task ApplyStacks(PlayerChoiceContext ctx, Creature target, Creature source, int amount);

    /// <summary>Apply N stacks of <typeparamref name="T"/> with a literal amount (no card), via the BaseLib
    /// generic PowerCmd.Apply path — the same call the orb/trigger runners use.</summary>
    protected static Task Apply<T>(PlayerChoiceContext ctx, Creature target, Creature source, int amount)
        where T : ForgedStatusPower
        => BetaMainCompatibility.PowerCmd_.Apply.InvokeGeneric<Task<T?>, T>(
               null, ctx, target, (decimal)amount, source, (CardModel?)null, false)!;

    // --- modifier hooks (additive MVP) ------------------------------------------------------------------------
    // The Additive hooks return the BONUS DELTA (the game adds the sum of all powers' returns to the base), so a
    // no-match returns 0m. The bare transform hooks (energy/draw) are handed the running value and return the
    // modified value, so a no-match returns the value unchanged. All gated to this power's Owner.

    public override decimal ModifyDamageAdditive(
        Creature target, decimal amount, ValueProp props, Creature dealer, CardModel cardSource)
    {
        var s = Source;
        if (s == null || s.Mode == "multiplicative") return 0m; // AQ: a multiplicative status contributes below, not here
        var h = s.Hook;
        if (h == "damage_dealt" && dealer == Owner) return Amount;  // your attacks deal +stacks (Strength-like)
        if (h == "damage_taken" && target == Owner) return Amount;  // this creature takes +stacks (Brittle-like)
        return 0m;
    }

    // --- Phase AQ (v47): multiplicative mode, hit_count, damage_over_time ------------------------------------

    /// <summary>Per-stack step of a multiplicative status (×1.1 per stack).</summary>
    public const decimal MultiplicativeStep = 0.1m;

    /// <summary>The hard cap on a multiplicative status's factor (×2 — stacks past 10 add nothing).</summary>
    public const decimal MultiplicativeCap = 2.0m;

    /// <summary>The factor <paramref name="stacks"/> of a multiplicative status contributes: 1 + 0.1·stacks, capped.</summary>
    public static decimal MultiplicativeFactor(int stacks) =>
        Math.Min(MultiplicativeCap, 1m + MultiplicativeStep * Math.Max(0, stacks));

    /// <summary>The game multiplies the running damage by the product of every power's return (Vulnerable ×1.5, Weak
    /// ×0.75), so a no-match returns 1m. Gated like those two: the owner as dealer (damage_dealt) / as target
    /// (damage_taken) AND a powered attack (never a DoT tick, Poison, or thorns — the same
    /// <c>IsPoweredAttack</c> gate Vulnerable/Weak/Strength use).</summary>
    public override decimal ModifyDamageMultiplicative(
        Creature target, decimal amount, ValueProp props, Creature dealer, CardModel cardSource)
    {
        var s = Source;
        if (s == null || s.Mode != "multiplicative" || !props.IsPoweredAttack()) return 1m;
        bool match = (s.Hook == "damage_dealt" && dealer == Owner) || (s.Hook == "damage_taken" && target == Owner);
        if (!match) return 1m;
        decimal f = MultiplicativeFactor(Amount);
        MainFile.Logger.Info($"[AQ] {s.Hook} multiplicative '{s.Name}' x{f} ({Amount} stacks) on {amount} damage.");
        return f;
    }

    /// <summary>hit_count: the owner's CARD attacks hit +stacks extra times. <c>AttackCommand.Attacker</c> is the
    /// creature performing the attack (set by the card/monster builder before Execute runs the hook), so gating on
    /// it keeps a player stance off enemy attacks; the <c>ModelSource is CardModel</c> gate keeps it off relic /
    /// potion / pet attacks ("your attacks" = your cards). The game runs the loop <c>attackCount</c> times, so the
    /// return is the new total.</summary>
    public override int ModifyAttackHitCount(AttackCommand attack, int hitCount)
    {
        var s = Source;
        if (s == null || s.Hook != "hit_count" || Amount <= 0) return hitCount;
        if (attack.Attacker != Owner || attack.ModelSource is not CardModel) return hitCount;
        MainFile.Logger.Info($"[AQ] hit_count '{s.Name}' +{Amount} hits ({hitCount} -> {hitCount + Amount}) on {attack.ModelSource.Id}.");
        return hitCount + Amount;
    }

    /// <summary>damage_over_time: at the start of the OWNER's side's turn (a debuff on an enemy ticks on the enemy's
    /// turn, like Poison), the owner loses HP equal to its stacks — unblockable AND unpowered, the exact props
    /// PoisonPower passes, so Block, Strength, Vulnerable and our own damage statuses never touch the tick. The
    /// stacks then burn down through the existing end-of-turn decay (the spec MUST declare one — validated).
    /// This is PoisonPower's hook and context, byte-for-byte: <c>AfterSideTurnStart</c> + a
    /// <c>ThrowingPlayerChoiceContext</c> (no player choice can occur under a damage tick). NOT
    /// <c>BeforeSideTurnStart</c> — that runs before the game's per-creature turn-start (<c>ClearBlock</c> etc.),
    /// and a LETHAL tick there pulls the creature out from under the next hook iteration
    /// (<c>Hook.ShouldClearBlock → IterateCombatHookListeners</c> NRE, seen on GAPTESTAQ1 turn 2).</summary>
    public override async Task AfterSideTurnStart(CombatSide side, IReadOnlyList<Creature> participants, ICombatState combatState)
    {
        var s = Source;
        if (s == null || s.Hook != "damage_over_time" || Amount <= 0) return;
        if (side != Owner.Side || !participants.Contains(Owner) || !Owner.IsAlive) return;
        int n = Amount;
        MainFile.Logger.Info($"[AQ] damage_over_time '{s.Name}' ticks {n} on {Owner.Name} (decay {s.Decay}).");
        await CreatureCmd.Damage(new ThrowingPlayerChoiceContext(), Owner, n,
                                 ValueProp.Unblockable | ValueProp.Unpowered, (Creature?)null, (CardModel?)null);
    }

    public override decimal ModifyBlockAdditive(
        Creature target, decimal block, ValueProp props, CardModel cardSource, CardPlay cardPlay)
        => Source?.Hook == "block_gained" && target == Owner ? Amount : 0m; // +block when you gain block (Dex-like)

    public override decimal ModifyEnergyGain(Player player, decimal amount)
        => Source?.Hook == "energy_gain" && player == Owner.Player ? amount + Amount : amount; // +energy per turn

    public override decimal ModifyHandDraw(Player player, decimal count)
        => Source?.Hook == "card_draw" && player == Owner.Player ? count + Amount : count; // +cards drawn

    // --- decay -----------------------------------------------------------------------------------------------

    public override Task AfterSideTurnEnd(PlayerChoiceContext ctx, CombatSide side, IEnumerable<Creature> participants)
    {
        // Decay only at the end of the OWNER's own side's turn (a debuff on an enemy decays on the enemy's turn).
        if (side != Owner.Side) return Task.CompletedTask;
        switch (Source?.Decay)
        {
            case "lose_all_eot":
                Owner.RemovePowerInternal(this);
                break;
            case "lose_one_eot":
                if (Amount <= 1) Owner.RemovePowerInternal(this);
                else { Amount -= 1; Owner.InvokePowerModified(this, -1, false); } // mutate live stacks + refresh UI
                break;
        }
        return Task.CompletedTask;
    }

    // --- presentation ----------------------------------------------------------------------------------------

    /// <summary>The emoji-icon render key for this status (stable + path-safe; keyed by class/slot, kicked by
    /// MainFile). See <see cref="EmojiIconRenderer"/>.</summary>
    private string IconKey => $"status{StatusClass}_{StatusIndex}";

    public override List<(string, string)>? Localization
    {
        get
        {
            var s = Source;
            string title = s != null ? $"{s.Emoji} {s.Name}".Trim() : "Forged Status";
            string desc = s != null ? Describe(s) : "An empty forged status.";
            return (List<(string, string)>)new PowerLoc(title, desc, desc);
        }
    }

    public override string? CustomPackedIconPath => EmojiIconRenderer.IconPath(IconKey) ?? base.CustomPackedIconPath;
    public override string? CustomBigIconPath => EmojiIconRenderer.IconPath(IconKey) ?? base.CustomBigIconPath;

    /// <summary>Synthesize the status tooltip from its hook (kept human-readable; the CARD text that grants it is
    /// produced separately by <see cref="ForgedCards"/> / cardgen for lockstep).</summary>
    public static string Describe(StatusSpec s)
    {
        if (!string.IsNullOrWhiteSpace(s.Description)) return s.Description;
        string who = s.IsBuff ? "Your" : "This enemy's";
        bool mult = s.Mode == "multiplicative";
        string body = s.Hook switch
        {
            "damage_dealt" => mult
                ? $"{who} attacks deal 10% more damage per stack (up to double)."
                : $"{who} attacks deal bonus damage equal to its stacks.",
            "damage_taken" => mult
                ? (s.IsBuff ? "You take 10% more damage per stack (up to double)."
                            : "This enemy takes 10% more damage per stack (up to double).")
                : (s.IsBuff ? "You take bonus damage equal to its stacks."
                            : "This enemy takes bonus damage equal to its stacks."),
            "block_gained" => "You gain bonus Block equal to its stacks when you gain Block.",
            "energy_gain"  => "You gain bonus energy equal to its stacks each turn.",
            "card_draw"    => "You draw bonus cards equal to its stacks.",
            "damage_over_time" => "At the start of its turn, this enemy loses HP equal to its stacks.", // AQ
            "hit_count"    => "Your Attacks hit an extra time per stack.",                             // AQ
            _ => "A forged status.",
        };
        // Decay runs at the end of the OWNER's side's turn: "your" turn for a buff, "its" turn for a debuff on an enemy.
        string whose = s.IsBuff ? "your" : "its";
        string decay = s.Decay switch
        {
            "lose_one_eot" => $" Loses 1 stack at the end of {whose} turn.",
            "lose_all_eot" => $" Expires at the end of {whose} turn.",
            _ => "",
        };
        return body + decay;
    }
}
