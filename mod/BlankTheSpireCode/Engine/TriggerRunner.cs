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
/// Phase H3: runs an <c>add_trigger</c> power's payload when it FIRES (turn end/start). Unlike
/// <see cref="EffectRunner"/>, there is NO card and NO chosen target at fire time — only the player. So this
/// is a deliberately RESTRICTED, self/orb-only sub-vocabulary executed with LITERAL amounts (the validator,
/// <c>ForgedCards.IsTriggerOp</c> / <c>TriggerStatuses</c>, forbids anything that needs a card var or an enemy
/// target: single-target damage, enemy debuffs, scale:x, multi-hit). The fire-time <c>When</c> gate is checked
/// once up front via <see cref="Conditions"/> with no target (so <c>target_has_status</c> is forbidden there).
/// </summary>
public static class TriggerRunner
{
    /// <summary>Run <paramref name="trigger"/> (an <c>add_trigger</c> EffectSpec) on the player, if its
    /// fire-time condition holds.</summary>
    public static async Task Run(EffectSpec trigger, Player player, PlayerChoiceContext ctx)
    {
        if (trigger.When != null && !Conditions.Evaluate(trigger.When, player, null)) return;

        // F5: a trigger payload may scale to cards_retained, resolved at FIRE time. For a turn_END trigger that
        // means what you're holding OUT of this turn (live retained-hand count); for a turn_start trigger it's
        // the cards you carried IN (the start-of-turn snapshot). Using the snapshot for a turn-end payoff would
        // lag a turn — it'd read what you retained LAST turn, which feels "locked" when you vary your hold.
        int retained = trigger.Trigger == "turn_end"
            ? HandStateTracker.CurrentlyRetainedCount(player)
            : HandStateTracker.CardsRetained;

        foreach (var e in trigger.Triggered ?? [])
        {
            // channel_orb/evoke ignore scale (validator-forbidden); otherwise literal amount.
            int amt = e.Scale == "cards_retained" ? retained : e.Amount;
            switch (e.Op)
            {
                case "block":
                    await CreatureCmd.GainBlock(player.Creature, amt, ValueProp.Move, null, false);
                    break;
                case "draw":
                    await CardPileCmd.Draw(ctx, amt, player);
                    break;
                case "gain_energy":
                    await PlayerCmd.GainEnergy(amt, player);
                    break;
                case "heal":
                    await CreatureCmd.Heal(player.Creature, amt, true);
                    break;
                case "lose_hp":
                    // No card here (a trigger payload) — use the null-safe dealer+cardSource overload; the
                    // CardModel-only overload NREs on a null card. (Self HP loss: no dealer ⇒ no Strength scaling.)
                    await CreatureCmd.Damage(ctx, player.Creature, amt, ValueProp.Unblockable, (Creature?)null, (CardModel?)null);
                    break;
                case "damage":
                {
                    // H4 (gap #14): a targeted payload deals intrinsic (ValueProp.Move) damage with the player as
                    // dealer — the same path RelicRunner/SummonRunner use. Validator guarantees a target here.
                    var targets = ResolveEnemies(e.Target, player);
                    MainFile.Logger.Info($"[H4] targeted payload: deal {amt} damage to {e.Target} ({targets.Count} enemy/ies).");
                    if (targets.Count > 0)
                        await CreatureCmd.Damage(ctx, targets, amt, ValueProp.Move, player.Creature);
                    break;
                }
                case "apply_status":
                    // H4: with a target it's an enemy debuff; otherwise the H3 self-buff.
                    if (e.Target != null)
                    {
                        var dtargets = ResolveEnemies(e.Target, player);
                        MainFile.Logger.Info($"[H4] targeted payload: apply {amt} {e.Status} to {e.Target} ({dtargets.Count} enemy/ies).");
                        foreach (var tgt in dtargets)
                            await ApplyDebuff(e.Status, ctx, player.Creature, tgt, amt);
                    }
                    else
                        await ApplySelfBuff(e.Status, ctx, player, amt);
                    break;
                case "forge":
                    // Phase M (gap #36): trigger-side Forge income ("At the start of your turn, Forge 2") —
                    // the engine half of the Forge archetype. Fixed amounts only (validator-gated, no scale).
                    // Phase T: Stoke summons the blade on the first Forge of combat (turn-1 turn_start income does).
                    await ForgedForgePower.Stoke(ctx, player, Math.Max(1, e.Amount));
                    MainFile.Logger.Info($"[M] forge +{Math.Max(1, e.Amount)} (trigger) -> Forge {EffectRunner.ForgeStacks(player)}.");
                    break;
                case "balance_step":
                    // Phase S (gap #1): trigger-side Balance income ("At the start of your turn, shift 2 toward the
                    // Dark") — the engine half of the balance archetype, exactly like forge. Fixed amounts only.
                    await ForgedBalancePower.BalanceStep(ctx, player, e.Pole, Math.Max(1, e.Amount));
                    break;
                case "gain_orb_slot":
                    await OrbCmd.AddSlots(player, amt);
                    break;
                case "channel_orb":
                {
                    int count = Math.Max(1, e.Amount);
                    for (int n = 0; n < count; n++)
                    {
                        var orbType = e.Orb == "random" ? EffectRunner.RandomOrbType(player) : EffectRunner.OrbTypeFor(e.Orb);
                        await OrbCmd.Channel(ctx, ((OrbModel)ModelDb.Get(orbType)).ToMutable(0), player);
                    }
                    break;
                }
                case "evoke":
                {
                    int count = Math.Max(1, e.Amount);
                    for (int n = 0; n < count; n++)
                        await OrbCmd.EvokeNext(ctx, player, dequeue: true);
                    break;
                }
                case "add_card":
                    // Phase Q (gap #16): trigger-side token generation — the on_exhaust "compost" loop (gap #8).
                    // Same executor as the card path; the class is read off the player, and depth-1 loop discipline
                    // (a generated card can't itself add_card) is enforced in ForgedCharacters.ResolveClassCardModel.
                    await EffectRunner.AddCards(e, player);
                    break;
                case "discard":
                    // Phase R (gap #17): trigger-side forced churn ("At the start of your turn, discard 1"). The
                    // shared executor also fires the discarded cards' on_discard payoffs (effect-driven).
                    await EffectRunner.DiscardRandom(amt, player, ctx);
                    break;
                case "summon_blade":
                    // Phase T: trigger-side blade retrieval — put the class's signature blade into hand from anywhere.
                    await ForgedForgePower.SummonBlade(ctx, player, fromAnywhere: true);
                    break;
                case "upgrade_card":
                    // Phase V (gap #18): trigger-side upgrade — "At the start of your turn, upgrade a random card in
                    // your hand." `random` ONLY here (validator rejects `all` in a repeating payload). Synchronous.
                    EffectRunner.UpgradeInHand("random", player);
                    break;
                case "heal_summon":
                case "shield_summon":
                    // Phase AC (gap #2): trigger-side summon heal/shield — the medic engine ("at turn start, heal your
                    // summon 3"). No card host here, so resolve the class off the player (ClassIndexOfPlayer); no
                    // summon out → logged no-op (HealOrShieldSummonFor).
                    await EffectRunner.HealOrShieldSummonFor(player, ForgedCharacters.ClassIndexOfPlayer(player), e.Op, amt);
                    break;
                // Any other op is validator-forbidden in a trigger; ignore defensively.
            }
        }
    }

    /// <summary>H4 (gap #14): the enemy target(s) of a targeted payload effect. all_enemies = every hittable alive
    /// enemy; enemy = the first hittable alive enemy. Mirrors RelicRunner/SummonRunner target resolution.</summary>
    private static List<Creature> ResolveEnemies(string? target, Player player)
    {
        var cs = player.Creature.CombatState;
        if (target == "all_enemies") return cs.HittableEnemies.Where(c => c.IsAlive).ToList();
        var first = cs.HittableEnemies.FirstOrDefault(c => c.IsAlive);
        return first != null ? [first] : [];
    }

    /// <summary>H4: apply N stacks of an enemy DEBUFF to a resolved target, attributed to the player (source).
    /// Only the four debuffs the validator allows on a targeted trigger apply_status are reachable.</summary>
    private static Task ApplyDebuff(string? status, PlayerChoiceContext ctx, Creature source, Creature target, int amount) => status switch
    {
        "vulnerable" => ApplyTo<VulnerablePower>(ctx, source, target, amount),
        "weak"       => ApplyTo<WeakPower>(ctx, source, target, amount),
        "frail"      => ApplyTo<FrailPower>(ctx, source, target, amount),
        "poison"     => ApplyTo<PoisonPower>(ctx, source, target, amount),
        _ => Task.CompletedTask,
    };

    /// <summary>The literal-amount targeted apply (no card): <paramref name="source"/> applies power T to
    /// <paramref name="target"/>. Mirrors SummonRunner's Apply path.</summary>
    private static Task ApplyTo<T>(PlayerChoiceContext ctx, Creature source, Creature target, int amount) where T : PowerModel
        => BetaMainCompatibility.PowerCmd_.Apply.InvokeGeneric<Task<T?>, T>(
               null, ctx, target, (decimal)amount, source, (CardModel?)null, false)!;

    /// <summary>Apply N stacks of a SELF-BUFF power to the player with a literal amount (no card). Only the
    /// self-buff subset is reachable here — the validator restricts trigger apply_status to those.</summary>
    private static Task ApplySelfBuff(string? status, PlayerChoiceContext ctx, Player player, int amount) => status switch
    {
        "strength"       => ApplyT<StrengthPower>(ctx, player, amount),
        "dexterity"      => ApplyT<DexterityPower>(ctx, player, amount),
        "thorns"         => ApplyT<ThornsPower>(ctx, player, amount),
        "regen"          => ApplyT<RegenPower>(ctx, player, amount),
        "metallicize"    => ApplyT<PlatingPower>(ctx, player, amount),
        "artifact"       => ApplyT<ArtifactPower>(ctx, player, amount),
        "buffer"         => ApplyT<BufferPower>(ctx, player, amount),
        "intangible"     => ApplyT<IntangiblePower>(ctx, player, amount),
        "ritual"         => ApplyT<RitualPower>(ctx, player, amount),
        "blur"           => ApplyT<BlurPower>(ctx, player, amount),
        "temp_strength"  => ApplyT<ForgedTempStrengthPower>(ctx, player, amount),
        "temp_dexterity" => ApplyT<ForgedTempDexterityPower>(ctx, player, amount),
        "barricade"      => ApplyT<BarricadePower>(ctx, player, amount),
        "focus"          => ApplyT<FocusPower>(ctx, player, amount),
        _ => Task.CompletedTask,
    };

    /// <summary>The literal-amount self-apply (no card), mirroring CommonActions' PowerCmd.Apply path.</summary>
    private static Task ApplyT<T>(PlayerChoiceContext ctx, Player player, int amount) where T : PowerModel
        => BetaMainCompatibility.PowerCmd_.Apply.InvokeGeneric<Task<T?>, T>(
               null, ctx, player.Creature, (decimal)amount, player.Creature, (CardModel?)null, false)!;
}
