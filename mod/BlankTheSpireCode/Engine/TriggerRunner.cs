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
/// <c>ForgedCards.ValidateTrigger</c>, forbids anything that needs a card var: scale:x, grow, nested triggers).
/// H4 lets a payload effect carry a <c>target</c>; Phase AL (v42) adds the class engines as payloads
/// (apply_status_custom / summon_attack / buff_summon — the class is read off the player, like heal_summon),
/// multi-hit on a payload damage/summon_attack, and the player-level scalars cards_in_hand /
/// unspent_energy_last_turn / forged next to cards_retained (<see cref="ResolveAmount"/>). The fire-time
/// <c>When</c> gate is checked once up front via <see cref="Conditions"/> with no target (so
/// <c>target_has_status</c> is forbidden there).
/// </summary>
public static class TriggerRunner
{
    /// <summary>Run <paramref name="trigger"/> (an <c>add_trigger</c> EffectSpec) on the player, if its
    /// fire-time condition holds. <paramref name="attacker"/> (Phase AK, v41) is the creature that just dealt us
    /// damage — supplied only by the <c>attacked</c> hook, so a payload effect with target:"attacker" resolves to
    /// it (the RelicRunner L-3 pattern); null on every other trigger.</summary>
    public static async Task Run(EffectSpec trigger, Player player, PlayerChoiceContext ctx, Creature? attacker = null)
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
            // channel_orb/evoke ignore scale (validator-forbidden); otherwise the literal amount, or a
            // player-level scalar resolved at fire time (Phase AL, v42).
            int amt = ResolveAmount(e, player, retained);
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
                    var targets = ResolveEnemies(e.Target, player, attacker);
                    int hits = Math.Max(1, e.Hits); // Phase AL (v42): a multi-hit payload loops the intrinsic hit
                    MainFile.Logger.Info($"[H4] targeted payload: deal {amt} damage to {e.Target} ({targets.Count} enemy/ies).");
                    if (e.Target == "attacker") // Phase AK (v41) smoke tag: the riposte lands on the one that struck (or nobody, if it died)
                        MainFile.Logger.Info($"[AK] riposte: deal {amt} damage to the attacker ({(targets.Count > 0 ? "resolved" : "no living attacker — skipped")}).");
                    if (hits > 1)
                        MainFile.Logger.Info($"[AL] payload damage x{hits}: deal {amt} damage {hits} times to {e.Target} ({targets.Count} enemy/ies).");
                    if (targets.Count > 0)
                        for (int h = 0; h < hits; h++)
                            await CreatureCmd.Damage(ctx, targets, amt, ValueProp.Move, player.Creature);
                    break;
                }
                case "apply_status":
                    // H4: with a target it's an enemy debuff; otherwise the H3 self-buff.
                    if (e.Target != null)
                    {
                        var dtargets = ResolveEnemies(e.Target, player, attacker);
                        MainFile.Logger.Info($"[H4] targeted payload: apply {amt} {e.Status} to {e.Target} ({dtargets.Count} enemy/ies).");
                        if (e.Target == "attacker") // Phase AK (v41)
                            MainFile.Logger.Info($"[AK] riposte: apply {amt} {e.Status} to the attacker ({(dtargets.Count > 0 ? "resolved" : "no living attacker — skipped")}).");
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
                    // A forged orb-class player resolves the orb name against ITS class's pool (base or custom),
                    // and "random" rolls only within that pool — Phase-I parity with the card and relic channel_orb
                    // paths. Without this, a trigger payload rolled the GLOBAL lightning/frost/dark pool (base orbs
                    // a custom-orb class doesn't list), and a custom orb NAME here threw in OrbTypeFor. The class
                    // has no card host at fire time, so it's read off the player (the heal_summon pattern below).
                    int orbClass = ForgedCharacters.ClassIndexOfPlayer(player);
                    if (ForgedCharacters.IsOrbClass(orbClass))
                    {
                        if (e.Orb is not ("lightning" or "frost" or "dark" or "random")) // Phase AJ smoke: a custom pool orb in a payload
                            MainFile.Logger.Info($"[AJ] trigger channel_orb '{e.Orb}' x{count} resolved against class {orbClass}'s pool.");
                        await EffectRunner.ChannelForgedOrbs(orbClass, e.Orb, count, player, ctx);
                    }
                    else
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
                case "summon_attack":
                {
                    // Phase AL (v42): the summon strikes on the trigger — the dormant per-turn move-cycle re-expressed
                    // as a card engine ("At the end of your turn, deal 4 damage 2 times with your summon"). The PET
                    // is the dealer (scales with its Strength, the card-level summon_attack path); targets resolve
                    // like any targeted payload (no target = the first living enemy). No summon out → logged no-op.
                    int k = ForgedCharacters.ClassIndexOfPlayer(player);
                    var pet = ForgedCharacters.IsSummonClass(k) ? EffectRunner.FindLivingSummon(player, k) : null;
                    if (pet == null) { MainFile.Logger.Info("[AL] trigger summon_attack: no summon (no-op)."); break; }
                    var stargets = ResolveEnemies(e.Target, player, attacker).Where(c => c.IsAlive).ToList();
                    int shits = Math.Max(1, e.Hits);
                    MainFile.Logger.Info($"[AL] trigger summon_attack: deal {amt} damage x{shits} with '{(pet.Monster as ForgedSummon)?.Source?.Name ?? "summon"}' to {e.Target ?? "enemy"} ({stargets.Count} enemy/ies).");
                    if (stargets.Count > 0)
                        for (int h = 0; h < shits; h++)
                            await CreatureCmd.Damage(ctx, stargets, amt, ValueProp.Move, pet);
                    break;
                }
                case "buff_summon":
                {
                    // Phase AL (v42): buff the living summon on the trigger ("At the start of your turn, your summon
                    // gains 1 Strength") — the card-level buff_summon path (SummonRunner.ApplyBuff). No summon → no-op.
                    int k = ForgedCharacters.ClassIndexOfPlayer(player);
                    var pet = ForgedCharacters.IsSummonClass(k) ? EffectRunner.FindLivingSummon(player, k) : null;
                    if (pet == null) { MainFile.Logger.Info("[AL] trigger buff_summon: no summon (no-op)."); break; }
                    string bst = e.Status ?? "strength";
                    MainFile.Logger.Info($"[AL] trigger buff_summon: +{amt} {bst} -> '{(pet.Monster as ForgedSummon)?.Source?.Name ?? "summon"}'.");
                    await SummonRunner.ApplyBuff(ctx, pet, bst, amt);
                    break;
                }
                case "apply_status_custom":
                {
                    // Phase AL (v42): apply one of the class's OWN statuses on the trigger ("At the start of your turn,
                    // gain 1 Razor Focus"). Mirrors the card-level split: a BUFF lands on the player (any target is
                    // ignored, as at card level); a DEBUFF lands on the resolved enemy target(s) — no target = the
                    // first living enemy. Unknown name (not in this class's status_pool) → warn + skip, like the card op.
                    int k = ForgedCharacters.ClassIndexOfPlayer(player);
                    var inst = ForgedCharacters.IsStatusClass(k) ? ForgedCharacters.ResolveStatusInstance(k, e.StatusName) : null;
                    if (inst?.Spec is not { } st)
                    {
                        MainFile.Logger.Warn($"[Forged] trigger apply_status_custom: class {k} has no status '{e.StatusName}' (skipped).");
                        break;
                    }
                    int n = Math.Max(1, amt);
                    if (st.IsBuff)
                    {
                        MainFile.Logger.Info($"[AL] trigger apply_status_custom: gain {n} {st.Name} (self buff).");
                        await inst.ApplyStacks(ctx, player.Creature, player.Creature, n);
                    }
                    else
                    {
                        var ctargets = ResolveEnemies(e.Target, player, attacker);
                        MainFile.Logger.Info($"[AL] trigger apply_status_custom: apply {n} {st.Name} to {e.Target ?? "enemy"} ({ctargets.Count} enemy/ies).");
                        foreach (var tgt in ctargets)
                            await inst.ApplyStacks(ctx, tgt, player.Creature, n);
                    }
                    break;
                }
                // Any other op is validator-forbidden in a trigger; ignore defensively.
            }
        }
    }

    /// <summary>Phase AL (v42): a payload effect's live amount. cards_retained keeps its F5 turn_end twist (the
    /// caller resolves <paramref name="retained"/>); cards_in_hand = the hand RIGHT NOW (all of it — no card to
    /// exclude at fire time); unspent_energy_last_turn = the turn-end snapshot (<see cref="HandStateTracker"/>);
    /// forged = the printed amount PLUS the Forge counter (ADDITIVE, the card-level rule). Anything else = literal.</summary>
    private static int ResolveAmount(EffectSpec e, Player player, int retained)
    {
        switch (e.Scale)
        {
            case "cards_retained": return retained;
            case "cards_in_hand":
            {
                int n = player.PlayerCombatState?.Hand?.Cards?.Count ?? 0;
                MainFile.Logger.Info($"[AL] payload scale cards_in_hand -> {n} ({e.Op}).");
                return n;
            }
            case "unspent_energy_last_turn":
            {
                int n = HandStateTracker.UnspentEnergyLastTurn;
                MainFile.Logger.Info($"[AL] payload scale unspent_energy_last_turn -> {n} ({e.Op}).");
                return n;
            }
            case "forged":
            {
                int n = e.Amount + EffectRunner.ForgeStacks(player);
                MainFile.Logger.Info($"[AL] payload scale forged -> {e.Amount} + Forge {EffectRunner.ForgeStacks(player)} = {n} ({e.Op}).");
                return n;
            }
            default: return e.Amount;
        }
    }

    /// <summary>H4 (gap #14): the enemy target(s) of a targeted payload effect. all_enemies = every hittable alive
    /// enemy; enemy = the first hittable alive enemy; attacker (Phase AK, v41) = the creature that just hit you
    /// (the <c>attacked</c> trigger only — empty if it is gone or unknown). Mirrors RelicRunner/SummonRunner.</summary>
    private static List<Creature> ResolveEnemies(string? target, Player player, Creature? attacker = null)
    {
        var cs = player.Creature.CombatState;
        if (target == "all_enemies") return cs.HittableEnemies.Where(c => c.IsAlive).ToList();
        if (target == "attacker") return attacker != null && attacker.IsAlive ? [attacker] : [];
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
