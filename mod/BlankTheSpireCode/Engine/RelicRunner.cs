using System.Collections.Generic;
using System.Linq;
using MegaCrit.Sts2.Core.Entities.Creatures;
using MegaCrit.Sts2.Core.Entities.Players;
using MegaCrit.Sts2.Core.GameActions.Multiplayer;

namespace BlankTheSpire.BlankTheSpireCode.Engine;

/// <summary>
/// Phase L: fires a forged relic's hooks. Called from <see cref="Powers.ForgedRelic"/>'s turn hooks with the
/// (ctx, player) those hooks hand in. Filters the spec's hooks by trigger, checks the fire-time
/// <see cref="RelicHook.When"/> (reusing <see cref="Conditions"/>, no target) and <c>once_per_combat</c>, resolves
/// the target, and runs the payload through <see cref="EffectRunner.RunRelicEffects"/> (the no-card executor that
/// merges TriggerRunner's self path with SummonRunner's targeted path).
/// </summary>
public static class RelicRunner
{
    /// <summary>Run every hook of <paramref name="spec"/> matching <paramref name="trigger"/> on the player.
    /// <paramref name="firedOnce"/> is the relic instance's per-combat once-fired set (hook index keys), reset by
    /// the relic at combat start. <paramref name="attacker"/> is the creature that just dealt damage — supplied only
    /// on the reactive <c>attacked</c> trigger (L-3), so a hook with <c>target: "attacker"</c> can hit it back.</summary>
    public static async Task Fire(RelicSpec? spec, string trigger, PlayerChoiceContext ctx, Player player,
                                  HashSet<int> firedOnce, Creature? attacker = null, int relicClass = 0)
    {
        if (spec == null) return;
        for (int i = 0; i < spec.Hooks.Length; i++)
        {
            var h = spec.Hooks[i];
            if (h.Trigger != trigger) continue;
            if (h.OncePerCombat && firedOnce.Contains(i)) continue;
            if (h.When != null && !Conditions.Evaluate(h.When, player, null)) continue;
            await EffectRunner.RunRelicEffects(h.Effects, ctx, player, ResolveTargets(h.Target, player, attacker), relicClass);
            if (h.OncePerCombat) firedOnce.Add(i);
        }
    }

    /// <summary>self = no enemy targets (self-only effects); all_enemies = every hittable alive enemy; enemy =
    /// the first hittable alive enemy; attacker = the creature that just hit you (the <c>attacked</c> trigger only,
    /// else empty). Mirrors <see cref="SummonRunner"/>'s target resolution.</summary>
    private static List<Creature> ResolveTargets(string target, Player player, Creature? attacker)
    {
        var cs = player.Creature.CombatState;
        switch (target)
        {
            case "all_enemies":
                return cs.HittableEnemies.Where(c => c.IsAlive).ToList();
            case "enemy":
                var first = cs.HittableEnemies.FirstOrDefault(c => c.IsAlive);
                return first != null ? [first] : [];
            case "attacker":
                return attacker != null && attacker.IsAlive ? [attacker] : [];
            default: // "self"
                return [];
        }
    }
}
