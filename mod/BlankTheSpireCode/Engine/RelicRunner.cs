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
    /// on the reactive <c>attacked</c> trigger (L-3), so a hook with <c>target: "attacker"</c> can hit it back.
    /// <para>Phase AS (v48): <paramref name="cardType"/> is the played card's type ("attack"/"skill"/"power") on
    /// <c>on_card_played</c> — a hook with a <c>card_type</c> filter fires only when it matches. <paramref name="counters"/>
    /// is the relic instance's per-combat occurrence counts (hook index keys) for <c>every_n</c> hooks: an occurrence that
    /// passes the trigger + card-type filter (and isn't spent by once_per_combat) counts, and the hook fires on the Nth,
    /// 2Nth… — counted BEFORE <c>when</c>, so a failed condition still advances the counter (the count is "things that
    /// happened", the condition is "is now a good time").</para></summary>
    public static async Task Fire(RelicSpec? spec, string trigger, PlayerChoiceContext ctx, Player player,
                                  HashSet<int> firedOnce, Creature? attacker = null, int relicClass = 0,
                                  string? cardType = null, Dictionary<int, int>? counters = null)
    {
        if (spec == null) return;
        for (int i = 0; i < spec.Hooks.Length; i++)
        {
            var h = spec.Hooks[i];
            if (h.Trigger != trigger) continue;
            if (h.CardType != null && h.CardType != cardType) continue; // Phase AS: typed on_card_played
            if (h.OncePerCombat && firedOnce.Contains(i)) continue;
            if (h.EveryN > 1)
            {
                // Phase AS: the counter relic — advance, fire only on a multiple of N.
                int n = (counters != null && counters.TryGetValue(i, out var c) ? c : 0) + 1;
                if (counters != null) counters[i] = n;
                if (n % h.EveryN != 0)
                {
                    MainFile.Logger.Info($"[AS] every_n hook[{i}] ({trigger}{(h.CardType != null ? " " + h.CardType : "")}) count {n}/{h.EveryN} — waiting.");
                    continue;
                }
                MainFile.Logger.Info($"[AS] every_n hook[{i}] ({trigger}{(h.CardType != null ? " " + h.CardType : "")}) count {n}/{h.EveryN} — FIRES.");
            }
            else if (h.CardType != null)
                MainFile.Logger.Info($"[AS] card_type hook[{i}] (on_card_played {h.CardType}) matched.");
            if (h.When != null && !Conditions.Evaluate(h.When, player, null)) continue;
            await EffectRunner.RunRelicEffects(h.Effects, ctx, player, ResolveTargets(h.Target, player, attacker), relicClass, h.Target);
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
