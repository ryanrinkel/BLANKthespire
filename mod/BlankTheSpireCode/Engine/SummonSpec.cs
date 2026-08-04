namespace BlankTheSpire.BlankTheSpireCode.Engine;

/// <summary>
/// Phase K: the data definition of a forged SUMMON (a player-side minion / autonomous ally — the "Osty axis").
/// A class declares a <c>summon_pool</c> (≤ <see cref="ForgedCharacters.MaxSummons"/> of these); a class card's
/// <c>summon</c> op references one by name. Unlike an enemy, a player-side creature is NEVER driven by the combat
/// turn loop (only enemies roll/perform moves — confirmed by decompiling <c>CombatManager</c>/<c>Creature.TakeTurn</c>),
/// so a summon's behaviour is HOOK-driven: it is a <c>CustomPetModel</c> entity (HP/visuals/death) plus a
/// <see cref="Powers.ForgedSummonPower"/> applied on summon whose <c>AfterTurnEnd</c> runs the current move via
/// <see cref="SummonRunner"/> (the pet is the dealer). The minion has no enemy-style intent and isn't targetable —
/// it is an autonomous ally (the design the user chose 2026-06-18).
/// </summary>
/// <param name="Name">Display name (loc + the pet's HUD label).</param>
/// <param name="Description">Synthesized-or-authored blurb (the behaviour buff's tooltip).</param>
/// <param name="MaxHp">The minion's HP (it can be hit by AoE / die; cleared at combat end). 1..999.</param>
/// <param name="Moves">The per-turn move CYCLE: at the end of each of your turns the minion performs
/// <c>Moves[turn % Moves.Length]</c>. One move = repeats every turn; several = a rotation (e.g. attack, attack,
/// big hit). Always at least one move.</param>
/// <param name="Attackable">K-3a: whether this minion is a normal Osty-style ally (true) — shows an HP bar and
/// soaks the player's hits as a meat-shield — or ETHEREAL (false): an untargetable striker (e.g. a falconer's
/// falcon) that still spawns and acts each turn but has NO HP bar and never absorbs damage. Its <c>MaxHp</c> is
/// cosmetic when false (it can't be hit). Defaults true (the Phase K full-Osty behaviour).</param>
/// <param name="OnSummon">K-3b (swarm): actions performed ONCE the moment this minion is summoned (a "battle cry" —
/// the minion is the actor, full sub-vocab). Empty = nothing on enter.</param>
/// <param name="OnDeath">K-3b (swarm): actions performed ONCE when this minion dies (a "death rattle"). The minion
/// is gone, so the PLAYER deals these — restricted to enemy-facing actions (attack / debuff). Empty = nothing.</param>
public sealed record SummonSpec(
    string Name, string Description, int MaxHp, SummonMove[] Moves, bool Attackable = true,
    SummonAction[]? OnSummon = null, SummonAction[]? OnDeath = null);

/// <summary>One entry in a summon's move cycle: the ordered actions it performs on a single turn.</summary>
public sealed record SummonMove(SummonAction[] Actions);

/// <summary>
/// One action a summon performs on its turn, from the restricted minion sub-vocabulary (see
/// <see cref="SummonRunner"/> / <see cref="ForgedCharacters"/> validation):
///   <c>attack</c> (Amount per-hit damage × Hits, to Target enemies),
///   <c>block</c> (Amount Block on the minion itself),
///   <c>apply_status</c> (Status; a self-buff lands on the minion, a debuff on Target enemies),
///   <c>heal_self</c> (Amount HP to the minion).
/// </summary>
/// <param name="Op">attack / block / apply_status / heal_self.</param>
/// <param name="Amount">Per-hit damage / block / status stacks / heal.</param>
/// <param name="Hits">Hit count for <c>attack</c> (default 1).</param>
/// <param name="Status">Status id for <c>apply_status</c>.</param>
/// <param name="Target">enemy / all_enemies (attacks + debuffs) or self (block/heal/self-buff). Defaulted per op.</param>
public sealed record SummonAction(string Op, int Amount = 0, int Hits = 1, string? Status = null, string Target = "enemy");
