using System.Linq;
using BaseLib.Utils;
using BlankTheSpire.BlankTheSpireCode.Powers;
using MegaCrit.Sts2.Core.Commands;
using MegaCrit.Sts2.Core.Entities.Cards;
using MegaCrit.Sts2.Core.Entities.Creatures;
using MegaCrit.Sts2.Core.Entities.Players;
using MegaCrit.Sts2.Core.GameActions.Multiplayer;
using MegaCrit.Sts2.Core.Models;
using MegaCrit.Sts2.Core.Models.Orbs;
using MegaCrit.Sts2.Core.Models.Powers;
using MegaCrit.Sts2.Core.ValueProps;

namespace BlankTheSpire.BlankTheSpireCode.Engine;

/// <summary>
/// Phase I: runs a forged orb's <c>passive</c> (per-turn tick) and <c>evoke</c> (burst) effect lists. Unlike
/// <see cref="TriggerRunner"/> (which fires with no target and is self/orb-only), an orb DOES reach the board:
/// its <c>Passive</c> is handed a Creature and its <c>Evoke</c> can enumerate enemies, so each <see cref="OrbEffect"/>
/// carries its own <c>target</c> (self / enemy / all_enemies). Damage/block amounts are Focus-scaled via the
/// orb's <c>ModifyOrbValue</c> (<see cref="ForgedOrb.FocusValue"/>); the rest run with literal amounts. Like the
/// other runners this is a deliberately restricted sub-vocabulary; the validator (see <see cref="ForgedCharacters"/>)
/// rejects anything outside it.
/// </summary>
public static class OrbRunner
{
    /// <summary>Run the orb's passive list. The game supplies <paramref name="passiveTarget"/> (the tick's
    /// target Creature); <c>enemy</c> effects use it, <c>all_enemies</c> hits the board, <c>self</c> the player.</summary>
    public static async Task RunPassive(OrbSpec spec, ForgedOrb orb, PlayerChoiceContext ctx, Creature? passiveTarget)
    {
        var affected = new List<Creature>();
        foreach (var oe in spec.Passive)
            await RunEffect(oe, orb, ctx, passiveTarget, affected);
    }

    /// <summary>Run the orb's evoke (burst) list and return the enemies it affected (for VFX/animation). No
    /// game-supplied target at evoke time, so <c>enemy</c> picks the first hittable enemy.</summary>
    public static async Task<IEnumerable<Creature>> RunEvoke(OrbSpec spec, ForgedOrb orb, PlayerChoiceContext ctx)
    {
        var affected = new List<Creature>();
        foreach (var oe in spec.Evoke)
            await RunEffect(oe, orb, ctx, null, affected);
        return affected.Distinct().ToList();
    }

    private static async Task RunEffect(OrbEffect oe, ForgedOrb orb, PlayerChoiceContext ctx, Creature? passiveTarget,
        List<Creature> affected)
    {
        var e = oe.Effect;
        var player = orb.Owner;
        switch (e.Op)
        {
            case "damage":
            {
                var targets = ResolveTargets(oe.Target, orb, passiveTarget);
                if (targets.Count == 0) break;
                // ValueProp.Move = an intrinsic (non-card) hit, like a monster move / base orb; still blockable
                // and affected by the target's Vulnerable, but not scaled by the player's card mechanics.
                await CreatureCmd.Damage(ctx, targets, orb.FocusValue(e.Amount), ValueProp.Move, player.Creature);
                affected.AddRange(targets);
                break;
            }
            case "block":
                await CreatureCmd.GainBlock(player.Creature, orb.FocusValue(e.Amount), ValueProp.Move, null, false);
                break;
            case "apply_status":
                await ApplyStatus(e.Status, oe.Target, orb, ctx, passiveTarget, e.Amount, affected);
                break;
            case "draw":
                await CardPileCmd.Draw(ctx, e.Amount, player);
                break;
            case "gain_energy":
                await PlayerCmd.GainEnergy(e.Amount, player);
                break;
            case "heal":
                await CreatureCmd.Heal(player.Creature, e.Amount, true);
                break;
            case "gain_orb_slot":
                await OrbCmd.AddSlots(player, e.Amount);
                break;
            case "channel_orb":
            {
                int count = System.Math.Max(1, e.Amount);
                for (int n = 0; n < count; n++)
                {
                    var type = e.Orb == "random"
                        ? ForgedCharacters.RandomOrbType(orb.ClassK, player)
                        : ForgedCharacters.ResolveOrbType(orb.ClassK, e.Orb);
                    type ??= EffectRunner.OrbTypeFor("lightning"); // defensive: unknown name falls back
                    await OrbCmd.Channel(ctx, ((OrbModel)ModelDb.Get(type)).ToMutable(0), player);
                }
                break;
            }
            // Any other op is validator-forbidden in an orb; ignore defensively.
        }
    }

    /// <summary>Resolve an orb effect's target list. <c>self</c> = the player; <c>all_enemies</c> = every
    /// hittable enemy; <c>enemy</c> = the passive's supplied target if valid, else the first hittable enemy.</summary>
    private static List<Creature> ResolveTargets(string target, ForgedOrb orb, Creature? passiveTarget)
    {
        var player = orb.Owner;
        switch (target)
        {
            case "self":
                return [player.Creature];
            case "all_enemies":
                return orb.CombatState.HittableEnemies.Where(c => c.IsAlive).ToList();
            case "enemy":
            default:
                if (passiveTarget != null && passiveTarget.IsEnemy && passiveTarget.IsAlive)
                    return [passiveTarget];
                var first = orb.CombatState.HittableEnemies.FirstOrDefault(c => c.IsAlive);
                return first != null ? [first] : [];
        }
    }

    /// <summary>Apply a status: a self-buff always lands on the player; a debuff lands on the resolved target(s).
    /// Mirrors <see cref="EffectRunner.SelfBuffStatuses"/> for the buff/debuff split.</summary>
    private static async Task ApplyStatus(string? status, string target, ForgedOrb orb, PlayerChoiceContext ctx,
        Creature? passiveTarget, int amount, List<Creature> affected)
    {
        var player = orb.Owner;
        if (EffectRunner.SelfBuffStatuses.Contains(status ?? ""))
        {
            await ApplyT(status, ctx, player.Creature, player.Creature, amount);
            return;
        }
        foreach (var t in ResolveTargets(target, orb, passiveTarget))
        {
            await ApplyT(status, ctx, t, player.Creature, amount);
            affected.Add(t);
        }
    }

    private static Task ApplyT(string? status, PlayerChoiceContext ctx, Creature target, Creature source, int amount) =>
        status switch
        {
            "vulnerable"     => Apply<VulnerablePower>(ctx, target, source, amount),
            "weak"           => Apply<WeakPower>(ctx, target, source, amount),
            "frail"          => Apply<FrailPower>(ctx, target, source, amount),
            "poison"         => Apply<PoisonPower>(ctx, target, source, amount),
            "strength"       => Apply<StrengthPower>(ctx, target, source, amount),
            "dexterity"      => Apply<DexterityPower>(ctx, target, source, amount),
            "thorns"         => Apply<ThornsPower>(ctx, target, source, amount),
            "regen"          => Apply<RegenPower>(ctx, target, source, amount),
            "metallicize"    => Apply<PlatingPower>(ctx, target, source, amount),
            "artifact"       => Apply<ArtifactPower>(ctx, target, source, amount),
            "buffer"         => Apply<BufferPower>(ctx, target, source, amount),
            "intangible"     => Apply<IntangiblePower>(ctx, target, source, amount),
            "ritual"         => Apply<RitualPower>(ctx, target, source, amount),
            "blur"           => Apply<BlurPower>(ctx, target, source, amount),
            "temp_strength"  => Apply<ForgedTempStrengthPower>(ctx, target, source, amount),
            "temp_dexterity" => Apply<ForgedTempDexterityPower>(ctx, target, source, amount),
            "barricade"      => Apply<BarricadePower>(ctx, target, source, amount),
            "focus"          => Apply<FocusPower>(ctx, target, source, amount),
            _ => Task.CompletedTask,
        };

    /// <summary>Apply N stacks of power <typeparamref name="T"/> to <paramref name="target"/> from
    /// <paramref name="source"/> with a literal amount (no card), via the BaseLib generic PowerCmd.Apply path.</summary>
    private static Task Apply<T>(PlayerChoiceContext ctx, Creature target, Creature source, int amount)
        where T : PowerModel
        => BetaMainCompatibility.PowerCmd_.Apply.InvokeGeneric<Task<T?>, T>(
               null, ctx, target, (decimal)amount, source, (CardModel?)null, false)!;

    // --- text (the orb HUD tooltip; I-2 will mirror this in cardgen.py) -----------------------------

    /// <summary>Synthesize an orb's tooltip: "Passive: …. Evoke: …."</summary>
    public static string Describe(OrbSpec spec)
    {
        string passive = Phrase(spec.Passive);
        string evoke = Phrase(spec.Evoke);
        var parts = new List<string>(2);
        if (passive.Length > 0) parts.Add($"Passive: {passive}");
        if (evoke.Length > 0) parts.Add($"Evoke: {evoke}");
        return parts.Count > 0 ? string.Join("\n", parts) : "A forged orb.";
    }

    private static string Phrase(OrbEffect[] effects)
    {
        var frags = effects.Select(Fragment).Where(s => s.Length > 0).ToList();
        return frags.Count > 0 ? string.Join(", ", frags) + "." : "";
    }

    private static string Fragment(OrbEffect oe)
    {
        var e = oe.Effect;
        string to = oe.Target switch { "all_enemies" => " to ALL enemies", "enemy" => "", _ => "" };
        return e.Op switch
        {
            "damage"        => $"deal {e.Amount} damage{to}",
            "block"         => $"gain {e.Amount} Block",
            "draw"          => $"draw {e.Amount} card(s)",
            "gain_energy"   => $"gain {e.Amount} energy",
            "heal"          => $"heal {e.Amount} HP",
            "gain_orb_slot" => $"gain {e.Amount} orb slot(s)",
            "apply_status"  => EffectRunner.SelfBuffStatuses.Contains(e.Status ?? "")
                                   ? $"gain {e.Amount} {StatusName(e.Status)}"
                                   : $"apply {e.Amount} {StatusName(e.Status)}{(oe.Target == "all_enemies" ? " to ALL enemies" : "")}",
            "channel_orb"   => System.Math.Max(1, e.Amount) > 1 ? $"channel {e.Amount} {e.Orb} orbs" : $"channel a {e.Orb} orb",
            _ => "",
        };
    }

    private static string StatusName(string? status) => status switch
    {
        "vulnerable" => "Vulnerable", "weak" => "Weak", "frail" => "Frail", "poison" => "Poison",
        "strength" => "Strength", "dexterity" => "Dexterity", "thorns" => "Thorns", "regen" => "Regen",
        "metallicize" => "Metallicize", "artifact" => "Artifact", "buffer" => "Buffer",
        "intangible" => "Intangible", "ritual" => "Ritual", "blur" => "Blur",
        "temp_strength" => "Strength", "temp_dexterity" => "Dexterity", "barricade" => "Barricade",
        "focus" => "Focus", _ => status ?? "",
    };
}
