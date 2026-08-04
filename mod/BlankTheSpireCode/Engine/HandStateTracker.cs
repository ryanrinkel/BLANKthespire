using MegaCrit.Sts2.Core.Entities.Cards;
using MegaCrit.Sts2.Core.Entities.Players;
using MegaCrit.Sts2.Core.Models;

namespace BlankTheSpire.BlankTheSpireCode.Engine;

/// <summary>
/// Phase F5 (retain / hand-state payoff): a per-combat snapshot of the player's hand + energy carry-over,
/// read by the <c>cards_retained</c> / <c>unspent_energy_last_turn</c> scalars (<see cref="DataCard"/> calc vars
/// and <see cref="EffectRunner"/> draw) and the <c>retained_last_turn</c> condition (<see cref="Conditions"/>).
///
/// It is captured by Harmony (<see cref="HandStatePreDrawPatch"/> / <see cref="HandStateTurnEndPatch"/>):
/// - at the PRE-DRAW turn start (<c>Hook.BeforeHandDraw</c>) the hand holds exactly the cards retained from last
///   turn, so its count = <see cref="CardsRetained"/> and its members = <see cref="WasRetained"/>;
/// - at the player's turn end (<c>CombatManager.DoTurnEnd</c>) the remaining Energy carries over as
///   <see cref="UnspentEnergyLastTurn"/>.
///
/// Single local player → one static snapshot (mirrors the static patterns already used for the relic runtime).
/// All reads are tolerant: outside combat / before the first snapshot the scalars resolve to 0.
/// </summary>
public static class HandStateTracker
{
    /// <summary>Cards held into this turn (the pre-draw hand size). 0 on turn 1 / outside combat.</summary>
    public static int CardsRetained { get; private set; }

    /// <summary>Energy left unspent at the end of your last turn. 0 on turn 1 / outside combat.</summary>
    public static int UnspentEnergyLastTurn { get; private set; }

    // The exact card instances held into this turn (reference identity — a retained card is the same object).
    private static readonly HashSet<CardModel> _retained = new(ReferenceEqualityComparer.Instance);

    /// <summary>Snapshot the pre-draw hand at turn start: its size is "cards retained", its members feed
    /// <see cref="WasRetained"/>. On the combat's first turn there is no prior turn, so clear the carry-over.</summary>
    public static void SnapshotPreDraw(Player player)
    {
        try
        {
            var pcs = player?.PlayerCombatState;
            if ((pcs?.TurnNumber ?? 0) <= 1) UnspentEnergyLastTurn = 0; // fresh combat → no "last turn"
            _retained.Clear();
            var hand = pcs?.Hand?.Cards;
            if (hand == null) { CardsRetained = 0; return; }
            CardsRetained = hand.Count;
            foreach (var c in hand) _retained.Add(c);
        }
        catch { CardsRetained = 0; _retained.Clear(); }
    }

    /// <summary>Capture energy remaining at the player's turn end → next turn's "unspent energy last turn".</summary>
    public static void CaptureTurnEndEnergy(Player player)
    {
        try { UnspentEnergyLastTurn = player?.PlayerCombatState?.Energy ?? 0; }
        catch { UnspentEnergyLastTurn = 0; }
    }

    /// <summary>Was this specific card instance in your hand at the start of this turn (held over)?</summary>
    public static bool WasRetained(CardModel? card) => card != null && _retained.Contains(card);

    /// <summary>Cards in hand RIGHT NOW that carry the Retain keyword — i.e. what you're holding OUT of this
    /// turn (they survive the end-of-turn discard and carry forward). A turn_end trigger reads this so its
    /// payoff tracks the live retained count, instead of <see cref="CardsRetained"/> (the start-of-turn
    /// snapshot, which lags a turn for an end-of-turn payoff). 0 outside combat.</summary>
    public static int CurrentlyRetainedCount(Player? player)
    {
        try
        {
            var hand = player?.PlayerCombatState?.Hand?.Cards;
            if (hand == null) return 0;
            int n = 0;
            foreach (var c in hand)
                if (c.Keywords.Contains(CardKeyword.Retain)) n++;
            return n;
        }
        catch { return 0; }
    }
}
