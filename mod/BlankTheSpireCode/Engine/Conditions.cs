using BaseLib.Abstracts;
using BlankTheSpire.BlankTheSpireCode.Powers;
using MegaCrit.Sts2.Core.Entities.Cards;
using MegaCrit.Sts2.Core.Entities.Creatures;
using MegaCrit.Sts2.Core.Entities.Players;
using MegaCrit.Sts2.Core.GameActions.Multiplayer;
using MegaCrit.Sts2.Core.Models.Powers;

namespace BlankTheSpire.BlankTheSpireCode.Engine;

/// <summary>
/// Phase H compositional layer: a small set of pure combat-state predicates that gate an effect (the per-effect
/// <c>when</c>). Each <see cref="EffectSpec"/> may carry a <see cref="Condition"/>; <see cref="EffectRunner"/>
/// skips the effect when <see cref="Evaluate"/> is false. Read-only — never mutates state. The "slot machine"
/// jackpot is <c>orbs_match</c> (all channeled orbs the same type).
/// </summary>
public static class Conditions
{
    /// <summary>The condition kinds the validator accepts and <see cref="Evaluate"/> understands. L-4 adds the
    /// player-state reads <c>has_block</c>, <c>enemy_count_ge</c>, <c>turn_at_least</c>, <c>hand_size_ge</c>.
    /// F5 adds <c>retained_last_turn</c> (this card was held into this turn — card-instance scoped).
    /// Phase M (gap #36) adds <c>forged_ge</c> (your Forge counter is at least <c>value</c> — the gated payoff).</summary>
    public static readonly HashSet<string> Kinds =
        ["orbs_match", "orb_count_ge", "target_has_status", "no_block", "hp_below_half",
         "has_block", "enemy_count_ge", "turn_at_least", "hand_size_ge", "retained_last_turn", "forged_ge",
         "draw_pile_empty", // Phase P (gap #24): Grand-Finale boolean gate (no value)
         "hp_lost_ge", // Phase AD (gap #12): you have lost >= value HP this turn (Ice Shatter threshold)
         "light_ge", "dark_ge", "centered"]; // Phase S (gap #1): the Balance gauge reads (light/dark pole magnitude; |gauge| <= N)

    /// <summary>Statuses that <c>target_has_status</c> can test (a debuff subset — maps to a HasPower&lt;T&gt;).</summary>
    public static readonly HashSet<string> StatusChecks = ["poison", "vulnerable", "weak", "frail"];

    /// <summary>Returns null if the condition is well-formed, else a human-readable reason (for the validator).</summary>
    public static string? Validate(Condition c)
    {
        if (!Kinds.Contains(c.Kind))
            return $"unknown condition kind '{c.Kind}'.";
        if (c.Kind == "orb_count_ge" && c.Value < 1)
            return "condition 'orb_count_ge' needs value >= 1.";
        if ((c.Kind == "enemy_count_ge" || c.Kind == "turn_at_least" || c.Kind == "hand_size_ge"
             || c.Kind == "forged_ge"
             // Phase S (gap #1): light_ge/dark_ge are pole magnitude thresholds; centered N tests |gauge| <= N (a
             // window >= 1). All need value >= 1 (matching card.schema.json's global value minimum).
             || c.Kind == "light_ge" || c.Kind == "dark_ge" || c.Kind == "centered"
             || c.Kind == "hp_lost_ge") && c.Value < 1) // Phase AD (gap #12)
            return $"condition '{c.Kind}' needs value >= 1.";
        // Phase AD (gap #12): the HP-spent threshold is capped (a self-fuel payoff shouldn't gate on more HP than
        // any realistic single-turn spend — keeps it in the Ice Shatter band, not "lose 40 HP").
        if (c.Kind == "hp_lost_ge" && c.Value > 15)
            return "condition 'hp_lost_ge' may be at most 15.";
        if (c.Kind == "target_has_status" && (c.Status == null || !StatusChecks.Contains(c.Status)))
            return $"condition 'target_has_status' needs status in {string.Join("/", StatusChecks)}.";
        return null;
    }

    /// <summary>Evaluate the predicate from a card play (play-time gate). Negate inverts the result.
    /// <c>retained_last_turn</c> is card-instance scoped (was THIS card held into this turn), so it's resolved
    /// here from <see cref="HandStateTracker"/> rather than the player-only overload.</summary>
    public static bool Evaluate(Condition c, ConstructedCardModel card, PlayerChoiceContext ctx, CardPlay play)
    {
        if (c.Kind == "retained_last_turn")
        {
            bool held = HandStateTracker.WasRetained(card);
            return c.Negate ? !held : held;
        }
        return Evaluate(c, card.Owner, play.Target);
    }

    /// <summary>Evaluate the predicate from a player + optional target. Used both by the card play-time gate
    /// (target = the chosen card target) and by trigger powers at FIRE time (target = null — so
    /// <c>target_has_status</c> is never true in a trigger; the validator forbids it there). Negate inverts.</summary>
    public static bool Evaluate(Condition c, Player player, Creature? target)
    {
        bool r = Eval(c, player, target);
        return c.Negate ? !r : r;
    }

    private static bool Eval(Condition c, Player player, Creature? target)
    {
        switch (c.Kind)
        {
            case "orbs_match":
            {
                var orbs = player.PlayerCombatState.OrbQueue.Orbs;
                // The jackpot: 2+ orbs and every one is the same orb type (compare the concrete runtime type).
                return orbs.Count >= 2 && orbs.Select(o => o.GetType()).Distinct().Count() == 1;
            }
            case "orb_count_ge":
                return player.PlayerCombatState.OrbQueue.Orbs.Count >= c.Value;
            case "target_has_status":
                return target != null && TargetHasStatus(target, c.Status);
            case "no_block":
                return player.Creature.Block <= 0;
            case "hp_below_half":
                return player.Creature.CurrentHp * 2 < player.Creature.MaxHp;
            case "has_block":
                return player.Creature.Block >= Math.Max(1, c.Value);
            case "enemy_count_ge":
                return player.Creature.CombatState.HittableEnemies.Count(e => e.IsAlive) >= c.Value;
            case "turn_at_least":
                return player.Creature.CombatState.RoundNumber >= c.Value;
            case "hand_size_ge":
                return player.PlayerCombatState.Hand.Cards.Count >= c.Value;
            case "forged_ge": // Phase M (gap #36): the Forge-gated payoff ("If your Forge is 10+ …")
                return EffectRunner.ForgeStacks(player) >= c.Value;
            case "draw_pile_empty": // Phase P (gap #24): Grand-Finale gate — nothing left to draw
                return player.PlayerCombatState.DrawPile.Cards.Count == 0;
            case "hp_lost_ge": // Phase AD (gap #12): you have lost >= value HP this turn (Ice Shatter threshold)
                return HpLossTracker.HpLostThisTurn(player) >= c.Value;
            // Phase S (gap #1): the Balance gauge is signed (positive = Dark, negative = Light; 0 = centered).
            case "dark_ge":   // your Dark magnitude is at least value
                return ForgedBalancePower.Gauge(player) >= c.Value;
            case "light_ge":  // your Light magnitude is at least value (gauge <= -value)
                return -ForgedBalancePower.Gauge(player) >= c.Value;
            case "centered":  // you are within value of center (|gauge| <= value)
                return Math.Abs(ForgedBalancePower.Gauge(player)) <= c.Value;
            default:
                return false;
        }
    }

    private static bool TargetHasStatus(Creature t, string? status) => status switch
    {
        "poison"     => t.HasPower<PoisonPower>(),
        "vulnerable" => t.HasPower<VulnerablePower>(),
        "weak"       => t.HasPower<WeakPower>(),
        "frail"      => t.HasPower<FrailPower>(),
        _ => false,
    };

    /// <summary>The bare predicate phrase for card text, e.g. "your orbs match". The caller prefixes
    /// "if "/"unless " (per <see cref="Condition.Negate"/>). Kept in lockstep with cardgen.py.</summary>
    public static string Phrase(Condition c) => c.Kind switch
    {
        "orbs_match"         => "your orbs match",
        "orb_count_ge"       => $"you have {c.Value}+ orbs",
        "target_has_status"  => $"the enemy has {c.Status}",
        "no_block"           => "you have no Block",
        "hp_below_half"      => "your HP is below half",
        "has_block"          => c.Value > 1 ? $"you have {c.Value}+ Block" : "you have Block",
        "enemy_count_ge"     => $"there are {c.Value}+ enemies",
        "turn_at_least"      => $"it is turn {c.Value}+",
        "hand_size_ge"       => $"you hold {c.Value}+ cards",
        "retained_last_turn" => "you held this card",
        "forged_ge"          => $"your Forge is {c.Value}+",
        "draw_pile_empty"    => "your draw pile is empty",   // Phase P (gap #24)
        "hp_lost_ge"         => $"you have lost {c.Value} or more HP this turn", // Phase AD (gap #12)
        "dark_ge"            => $"your Dark is {c.Value}+",              // Phase S (gap #1)
        "light_ge"           => $"your Light is {c.Value}+",            // Phase S (gap #1)
        "centered"           => $"you are centered (within {c.Value})", // Phase S (gap #1)
        _ => c.Kind,
    };
}
