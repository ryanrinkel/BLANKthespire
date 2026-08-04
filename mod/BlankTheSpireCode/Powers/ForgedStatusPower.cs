using System.Collections.Generic;
using System.Threading.Tasks;
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
/// a buff only ever changes the owning player's numbers and a debuff only the afflicted enemy's. Multiplicative
/// scaling, <c>hit_count</c> (no clean dealer gate on AttackCommand), and reactive hooks are deferred to J-3.
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
        var h = Source?.Hook;
        if (h == "damage_dealt" && dealer == Owner) return Amount;  // your attacks deal +stacks (Strength-like)
        if (h == "damage_taken" && target == Owner) return Amount;  // this creature takes +stacks (Brittle-like)
        return 0m;
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
        string body = s.Hook switch
        {
            "damage_dealt" => $"{who} attacks deal bonus damage equal to its stacks.",
            "damage_taken" => s.IsBuff
                ? "You take bonus damage equal to its stacks."
                : "This enemy takes bonus damage equal to its stacks.",
            "block_gained" => "You gain bonus Block equal to its stacks when you gain Block.",
            "energy_gain"  => "You gain bonus energy equal to its stacks each turn.",
            "card_draw"    => "You draw bonus cards equal to its stacks.",
            _ => "A forged status.",
        };
        string decay = s.Decay switch
        {
            "lose_one_eot" => " Loses 1 stack at the end of your turn.",
            "lose_all_eot" => " Expires at the end of your turn.",
            _ => "",
        };
        return body + decay;
    }
}
