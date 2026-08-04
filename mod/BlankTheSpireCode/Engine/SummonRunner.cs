using System.Linq;
using BaseLib.Utils;
using BlankTheSpire.BlankTheSpireCode.Powers;
using MegaCrit.Sts2.Core.Commands;
using MegaCrit.Sts2.Core.Entities.Creatures;
using MegaCrit.Sts2.Core.GameActions.Multiplayer;
using MegaCrit.Sts2.Core.Models;
using MegaCrit.Sts2.Core.Models.Powers;
using MegaCrit.Sts2.Core.ValueProps;

namespace BlankTheSpire.BlankTheSpireCode.Engine;

/// <summary>
/// Phase K: runs a forged summon's per-turn move. The minion (a <see cref="Powers.ForgedSummon"/> pet Creature) is
/// the DEALER, so its attacks/debuffs come from the pet (not the player) — <c>ValueProp.Move</c> = an intrinsic hit
/// (blockable, Vulnerable-aware, not scaled by the player's card mechanics), the same path forged orbs use. A
/// deliberately restricted sub-vocabulary (attack / block / apply_status / heal_self); the validator
/// (<see cref="ForgedCharacters"/>) rejects anything outside it.
/// </summary>
public static class SummonRunner
{
    /// <summary>Perform <paramref name="move"/>'s actions with <paramref name="pet"/> as the dealer.</summary>
    public static Task RunMove(SummonMove move, Creature pet, PlayerChoiceContext ctx)
        => RunActions(move.Actions, pet, ctx);

    /// <summary>
    /// K-3b: run an arbitrary action list (a move, or an on_summon / on_death payload). The minion is the actor by
    /// default; pass <paramref name="dealerOverride"/> (the player's creature) for a DEATH RATTLE, where the minion
    /// is already gone and can't be the dealer. Targets are still resolved from the minion's combat state.
    /// </summary>
    public static async Task RunActions(IEnumerable<SummonAction> actions, Creature pet, PlayerChoiceContext ctx,
                                        Creature? dealerOverride = null)
    {
        foreach (var a in actions)
            await RunAction(a, pet, ctx, dealerOverride);
    }

    private static async Task RunAction(SummonAction a, Creature pet, PlayerChoiceContext ctx, Creature? dealerOverride)
    {
        var dealer = dealerOverride ?? pet; // who damage/debuffs are attributed to (the minion, or the player on death)
        switch (a.Op)
        {
            case "attack":
            {
                var targets = ResolveTargets(a.Target, pet);
                if (targets.Count == 0) break;
                for (int h = 0; h < System.Math.Max(1, a.Hits); h++)
                    await CreatureCmd.Damage(ctx, targets, a.Amount, ValueProp.Move, dealer);
                break;
            }
            case "block":
                await CreatureCmd.GainBlock(pet, a.Amount, ValueProp.Move, null, false);
                break;
            case "heal_self":
                await CreatureCmd.Heal(pet, a.Amount, true);
                break;
            case "apply_status":
                await ApplyStatus(a, pet, ctx, dealer);
                break;
            // Anything else is validator-forbidden; ignore defensively.
        }
    }

    /// <summary>self = the minion; all_enemies = every hittable enemy; enemy = the first hittable enemy.</summary>
    private static System.Collections.Generic.List<Creature> ResolveTargets(string target, Creature pet)
    {
        switch (target)
        {
            case "self":
                return [pet];
            case "all_enemies":
                return pet.CombatState.HittableEnemies.Where(c => c.IsAlive).ToList();
            case "enemy":
            default:
                var first = pet.CombatState.HittableEnemies.FirstOrDefault(c => c.IsAlive);
                return first != null ? [first] : [];
        }
    }

    /// <summary>A self-buff lands on the minion; a debuff lands on the resolved enemy target(s), attributed to
    /// <paramref name="dealer"/> (the minion, or the player for a death rattle). Mirrors
    /// <see cref="EffectRunner.SelfBuffStatuses"/> for the buff/debuff split.</summary>
    private static async Task ApplyStatus(SummonAction a, Creature pet, PlayerChoiceContext ctx, Creature dealer)
    {
        if (EffectRunner.SelfBuffStatuses.Contains(a.Status ?? ""))
        {
            await ApplyT(a.Status, ctx, pet, pet, a.Amount);
            return;
        }
        foreach (var t in ResolveTargets(a.Target, pet))
            await ApplyT(a.Status, ctx, t, dealer, a.Amount);
    }

    /// <summary>Apply <paramref name="amount"/> stacks of a self-buff (e.g. Strength) to a summoned minion — the
    /// <c>buff_summon</c> card op (true-Osty: pump your one summon so its summon_attacks hit harder). Reuses the
    /// per-status apply map. An unknown / non-buff status is a no-op (the validator restricts it to self-buffs).</summary>
    public static Task ApplyBuff(PlayerChoiceContext ctx, Creature pet, string status, int amount)
        => ApplyT(status, ctx, pet, pet, amount);

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

    private static Task Apply<T>(PlayerChoiceContext ctx, Creature target, Creature source, int amount)
        where T : PowerModel
        => BetaMainCompatibility.PowerCmd_.Apply.InvokeGeneric<Task<T?>, T>(
               null, ctx, target, (decimal)amount, source, (CardModel?)null, false)!;

    // --- text (the behaviour-buff tooltip; K-2 mirrors this in cardgen.py) --------------------------

    /// <summary>Synthesize the minion's behaviour blurb: "Each turn: …." or a per-turn rotation.</summary>
    public static string Describe(SummonSpec spec)
    {
        // K-3a: an ethereal summon can't be hit, so its HP is cosmetic — lead with "Ethereal" instead of HP.
        string hp = spec.Attackable ? $"{spec.MaxHp} HP" : "Ethereal (cannot be attacked)";
        string body;
        if (spec.Moves.Length == 0) body = "A forged summon.";
        else if (spec.Moves.Length == 1) body = $"{hp}. Each turn: {MovePhrase(spec.Moves[0])}.";
        else
        {
            var rotation = string.Join("; ", spec.Moves.Select((m, i) => $"Turn {i + 1}: {MovePhrase(m)}"));
            body = $"{hp}. Rotates — {rotation}.";
        }
        // K-3b: append the swarm triggers if present.
        if (spec.OnSummon is { Length: > 0 } os)
            body += $" On summon: {ActionsPhrase(os)}.";
        if (spec.OnDeath is { Length: > 0 } od)
            body += $" On death: {ActionsPhrase(od)}.";
        return body;
    }

    /// <summary>Join an action list into a fragment (for on_summon / on_death blurbs).</summary>
    private static string ActionsPhrase(SummonAction[] actions)
    {
        var frags = actions.Select(Fragment).Where(s => s.Length > 0).ToList();
        return frags.Count > 0 ? string.Join(", ", frags) : "do nothing";
    }

    private static string MovePhrase(SummonMove move)
    {
        var frags = move.Actions.Select(Fragment).Where(s => s.Length > 0).ToList();
        return frags.Count > 0 ? string.Join(", ", frags) : "do nothing";
    }

    private static string Fragment(SummonAction a)
    {
        string to = a.Target == "all_enemies" ? " to ALL enemies" : "";
        return a.Op switch
        {
            "attack"    => a.Hits > 1 ? $"deal {a.Amount}×{a.Hits} damage{to}" : $"deal {a.Amount} damage{to}",
            "block"     => $"gain {a.Amount} Block",
            "heal_self" => $"heal {a.Amount} HP",
            "apply_status" => EffectRunner.SelfBuffStatuses.Contains(a.Status ?? "")
                                 ? $"gain {a.Amount} {StatusName(a.Status)}"
                                 : $"apply {a.Amount} {StatusName(a.Status)}{to}",
            _ => "",
        };
    }

    /// <summary>Public status display name (e.g. "strength" → "Strength"), shared by the buff_summon card text in
    /// <see cref="ForgedCards"/> (byte-lockstep with cardgen.py).</summary>
    internal static string StatusDisplay(string? status) => StatusName(status);

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
