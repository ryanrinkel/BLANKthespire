using System;
using System.Collections.Generic;
using BaseLib.Abstracts;
using BaseLib.Monsters;
using MegaCrit.Sts2.Core.Entities.Creatures;
using MegaCrit.Sts2.Core.Models;
using MegaCrit.Sts2.Core.Models.Monsters;
using MegaCrit.Sts2.Core.MonsterMoves.MonsterMoveStateMachine;
using MegaCrit.Sts2.Core.Nodes.Combat;

namespace BlankTheSpire.BlankTheSpireCode.Powers;

/// <summary>
/// PHASE K SPIKE (throwaway, NOT in the LLM contract): one hardcoded summonable player pet, to prove the
/// summon path end-to-end before building the generic <c>ForgedSummon</c> system (K-1). Summoned via the
/// execution-only <c>summon_spike</c> card op (EffectRunner → <c>PlayerCmd.AddPet&lt;SpikeImp&gt;</c>).
///
/// Recipe learned by decompiling the game's <c>OstyCmd.Summon</c> / <c>PlayerCmd.AddPet&lt;T&gt;</c>:
///   <code>
///   pet = player.Creature.CombatState.CreateCreature(ModelDb.Monster&lt;T&gt;().ToMutable(), player.Creature.Side, null);
///   player.PlayerCombatState.AddPetInternal(pet); await CreatureCmd.Add(pet);
///   </code>
/// <c>AddPet&lt;T&gt;</c> wraps all of that (sets PetOwner, adds to Player.Pets, creates the node, joins the
/// turn order), so the op just calls <c>PlayerCmd.AddPet&lt;SpikeImp&gt;(owner)</c>. Auto-registers in ModelDb
/// via the BaseLib ICustomModel scan (the <see cref="CustomMonsterModel"/> ctor), like the empty card slots /
/// forged orbs — no MainFile change.
///
/// Visuals: borrow the game's own shipped fallback creature scene (a real <c>NCreatureVisuals</c>) so the pet
/// renders without authoring art and without the missing-asset NRE that bit custom orbs (Phase I bug #1). Real
/// per-minion art is a later concern (ASSETS_TODO.md). Loc is in-code via BaseLib <see cref="MonsterLoc"/>
/// (table "monsters"), the monster analogue of <c>ForgedOrb</c>'s <c>OrbLoc</c> — no .pck rebuild.
///
/// Unlike Osty (whose move is NOTHING — its damage is a separate mechanic), this pet has a real attack move so
/// the spike can confirm a summoned creature actually takes its turn and hits an enemy.
/// </summary>
public sealed class SpikeImp : CustomPetModel, ILocalizationProvider
{
    private const string AttackMove = "ATTACK";

    public SpikeImp() : base(visibleHp: true) { }

    // Pet HP is rolled from Min..Max (equal => fixed). Kept low so it can die and we can watch combat-end /
    // owner-death cleanup (the soft-lock risk flagged in the plan).
    public override int MinInitialHp => 12;
    public override int MaxInitialHp => 12;

    // In-code name + the move title shown when it acts (loc table "monsters"). The loc patch prefixes the
    // model's Id.Entry, matching MonsterModel.Title = LocString("monsters", Id.Entry + ".name").
    public string? LocTable => "monsters";
    public List<(string, string)>? Localization =>
        (List<(string, string)>)new MonsterLoc("Spike Imp", new[] { (AttackMove, "Jab") });

    // Placeholder art: BORROW the game's Osty pet visuals (a real, shipped creature scene with sprite + HP-bar
    // markers) rather than the bare "creature_visuals/fallback" error scene (which renders as the word "error"
    // and has no HP bar). Each call instantiates a fresh node. On any failure, return null → the game's own
    // CreateVisuals catch falls back to the error scene (so behaviour still works). Real per-summon art later.
    public override NCreatureVisuals? CreateCustomVisuals()
    {
        try { return ((MonsterModel)ModelDb.Get(typeof(Osty))).CreateVisuals(); }
        catch (Exception e)
        {
            MainFile.Logger.Warn($"[SpikeImp] borrowing Osty visuals failed: {e.Message}");
            return null;
        }
    }

    // Attack for 5 every turn, looping on itself. A MoveState with no follow-up throws "No valid followup
    // state", so FollowingState points the move back at itself.
    protected override MonsterMoveStateMachine GenerateMoveStateMachine()
    {
        MoveState attack = new MoveBuilder(this, AttackMove)
            .Attack(5)
            .FollowingState(AttackMove)
            .Build();
        return new MonsterMoveStateMachine(new MonsterState[] { attack }, attack);
    }
}
