using System;
using System.Collections.Generic;
using System.Linq;
using Godot;
using BaseLib.Abstracts;
using BlankTheSpire.BlankTheSpireCode.Engine;
using MegaCrit.Sts2.Core.Entities.Players;
using MegaCrit.Sts2.Core.Models;
using MegaCrit.Sts2.Core.Models.Monsters;
using MegaCrit.Sts2.Core.MonsterMoves.MonsterMoveStateMachine;
using MegaCrit.Sts2.Core.Nodes.Combat;
using MegaCrit.Sts2.Core.Nodes.Rooms;

namespace BlankTheSpire.BlankTheSpireCode.Powers;

/// <summary>
/// Phase K: the base for the generated <c>ForgedClassKSummonM</c> shells (M = 1..<see cref="ForgedCharacters.MaxSummons"/>
/// per class) — the summon analogue of <see cref="ForgedOrb"/>. One minion = one compiled <see cref="CustomPetModel"/>
/// (Q1), so the mod ships a fixed pool of generic shells; each reads its <see cref="SummonSpec"/> from the class JSON
/// (<see cref="ForgedCharacters.SummonSpecFor"/>).
///
/// This type is ONLY the entity (HP / visuals / death). The minion's per-turn BEHAVIOUR lives in
/// <see cref="ForgedSummonPower"/> (applied to the pet on summon), because player-side creatures are never driven by
/// the turn loop — see <see cref="SummonSpec"/>. The move state machine therefore stays the BaseLib default (NOTHING).
///
/// A shell whose class declares fewer than M summons has a null <see cref="Source"/>: it still auto-registers (the
/// <see cref="CustomMonsterModel"/> ctor adds itself to BaseLib's model registry, like the empty card slots) but is
/// never referenced by any class's pool.
/// </summary>
public abstract class ForgedSummon : CustomPetModel, ILocalizationProvider
{
    /// <summary>The 1-based class index this summon belongs to (set by the generated shell).</summary>
    protected abstract int SummonClass { get; }

    /// <summary>The 1-based slot within the class's summon_pool (1..MaxSummons; set by the generated shell).</summary>
    protected abstract int SummonIndex { get; }

    protected ForgedSummon() : base(visibleHp: true)
    {
        // SummonClass/SummonIndex are constant overrides (no field access), so reading them in the base ctor is safe.
        _registry[(SummonClass, SummonIndex)] = this;
    }

    /// <summary>This summon's spec, or null on an unfilled shell (the class declared no such summon).</summary>
    public SummonSpec? Source => ForgedCharacters.SummonSpecFor(SummonClass, SummonIndex);

    /// <summary>Public read of the owning class index — lets the runtime enforce "one summon per class" and find
    /// the living minion for the <c>summon</c> / <c>summon_attack</c> / <c>buff_summon</c> ops.</summary>
    public int OwnerClass => SummonClass;

    // (class, slot) -> the canonical registered instance, populated in the ctor (the BaseLib ICustomModel scan
    // creates one instance per shell type at init). Lets ForgedCharacters map a summon NAME -> its compiled Type
    // without referencing the generated symbols (mirrors ForgedOrb._registry).
    private static readonly Dictionary<(int, int), ForgedSummon> _registry = new();

    /// <summary>The compiled summon Type for class <paramref name="k"/>'s summon slot <paramref name="m"/>, or null.</summary>
    public static Type? TypeForKey(int k, int m) =>
        _registry.TryGetValue((k, m), out var s) ? s.GetType() : null;

    // --- MonsterModel surface (abstract members MUST be provided) ------------------------------------
    // HP rolls from Min..Max (equal => fixed). >=1 so the creature is valid; ForgedCharacters clamps max_hp to 1..999.
    public override int MinInitialHp => Math.Max(1, Source?.MaxHp ?? 1);
    public override int MaxInitialHp => Math.Max(1, Source?.MaxHp ?? 1);

    // Placeholder art (Phase K MVP; real per-summon art deferred — see ASSETS_TODO.md): BORROW the game's Osty pet
    // visuals (a real, shipped creature scene with a sprite) rather than the bare "error" fallback. Each call
    // instantiates a fresh node; on any failure return null → the game's own CreateVisuals catch handles it.
    public override NCreatureVisuals? CreateCustomVisuals()
    {
        try { return ((MonsterModel)ModelDb.Get(typeof(Osty))).CreateVisuals(); }
        catch (Exception e)
        {
            MainFile.Logger.Warn($"[ForgedSummon] borrowing Osty visuals failed: {e.Message}");
            return null;
        }
    }

    // In-code localization (no .pck rebuild): the minion's name under the "monsters" loc table.
    public string? LocTable => "monsters";
    public List<(string, string)>? Localization =>
        (List<(string, string)>)new MonsterLoc(Source?.Name ?? "Forged Summon", []);

    /// <summary>
    /// Re-lay-out the player's summoned pets to the RIGHT of the player. The game's default pet placement
    /// (<c>NCombatRoom.AddCreature</c>) spreads non-Osty pets ACROSS the player's own sprite (one pet lands dead-on
    /// the PC), so we override it after a summon: pets sit clear of the PC and extras fan out. Pet + player nodes
    /// share the _allyContainer parent, so local <c>Position</c> is comparable. (Shared by the K-0 spike too.)
    /// </summary>
    public static void LayoutPets(Player owner)
    {
        var room = NCombatRoom.Instance;
        var playerNode = room?.GetCreatureNode(owner.Creature);
        if (room == null || playerNode == null) return;

        // Only LIVING pets, so when one dies the survivors close the gap (a dead pet's node lingers briefly).
        var pets = room.CreatureNodes.Where(n => n.Entity.PetOwner == owner && n.Entity.IsAlive).ToList();
        if (pets.Count == 0) return;

        float startX = playerNode.Position.X + playerNode.Visuals.Bounds.Size.X * 0.5f + 120f;
        const float spacing = 160f;
        for (int i = 0; i < pets.Count; i++)
        {
            pets[i].Position = new Vector2(startX + i * spacing, playerNode.Position.Y + 10f);
            // The game hides non-Osty pet HP/state bars (AddCreature → ToggleIsInteractable(false) sets the
            // %HealthBar invisible); re-enable so forged minions show an HP bar + are hoverable, like Osty.
            // Player attacks only target enemies, so an interactable player-side pet isn't wrongly attackable.
            // K-3a: ETHEREAL summons (attackable:false) stay non-interactable — no HP bar (they can't be hit;
            // ForgedSummonShieldPower also skips them), so a falconer's falcon strikes but never soaks.
            // (Verified by AutoSlay smoke 2026-06-18: ~1199 ethereal layouts all kept the bar hidden.)
            if ((pets[i].Entity.Monster as ForgedSummon)?.Source?.Attackable ?? true)
                pets[i].ToggleIsInteractable(true);
        }
    }
}
