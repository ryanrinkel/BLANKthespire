using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading.Tasks;
using BaseLib.Abstracts;
using BaseLib.Utils;
using BlankTheSpire.BlankTheSpireCode.Engine;
using MegaCrit.Sts2.Core.Combat;
using MegaCrit.Sts2.Core.Entities.Cards;
using MegaCrit.Sts2.Core.Entities.Creatures;
using MegaCrit.Sts2.Core.Entities.Players;
using MegaCrit.Sts2.Core.Entities.Powers;
using MegaCrit.Sts2.Core.GameActions.Multiplayer;
using MegaCrit.Sts2.Core.Models;

namespace BlankTheSpire.BlankTheSpireCode.Powers;

/// <summary>
/// Phase AO (VOCAB_GAP_REMEDIATION Wave 3, vocab v45): COST SHIFT — card-type-scoped energy discounts. The
/// <c>cost_shift</c> op ("Your Attacks cost 1 less this turn" / "Your next Skill costs 2 less this turn" / "Your
/// Skills cost 1 less this combat") generalizes <see cref="ForgedCorruptionPower"/>'s per-type cost hook into a
/// REDUCTION (never a set-to-0) with a card-type filter, a lifetime, and an optional use budget. ONE power instance
/// per player holds a LIST of live discounts (entries), because the game keys powers by type per creature — a second
/// power class per card type / scope would still collide, so the list is the only shape that lets "Attacks cost 1 less
/// this turn" and "Skills cost 1 less this combat" coexist. The native Amount mirrors the live entry count (the
/// Phase-J/S live-stack mutation: set Amount + InvokePowerModified; RemovePowerInternal when the list empties).
///
/// Verified against the decompiled source: <c>CardEnergyCost.GetWithModifiers</c> skips the global hook for X-cost
/// cards and floors the result at 0, so a reduction can never go negative or touch X; <c>Hook.ModifyEnergyCostInCombat</c>
/// runs every <c>TryModifyEnergyCostInCombat</c> BEFORE the <c>…Late</c> pass, so this discount composes additively
/// with a relic <c>cost_reduction</c> and Corruption's Late set-to-0 still wins for Skills. <c>PlayCardAction</c> spends
/// resources BEFORE <c>OnPlayWrapper</c> fires Before/AfterCardPlayed, so consuming a use in <see cref="AfterCardPlayed"/>
/// can never un-discount the card being paid for (the base game's <c>FreeAttackPower</c> decrements the same way).
/// </summary>
public sealed class ForgedCostShiftPower : BlankTheSpirePower
{
    public override PowerType Type => PowerType.Buff;
    // The entry list is the real state; Amount is a display mirror (managed in Sync), never stacked by the engine.
    public override PowerStackType StackType => PowerStackType.Single;

    /// <summary>One live discount. <see cref="Remaining"/> 0 = unlimited uses (the flat form); N = consumed by the
    /// next N matching plays (the "next Skill" form). <see cref="Armed"/> keeps the CARD THAT GRANTED the entry from
    /// consuming its own use: the power is added during that card's OnPlay, and AfterCardPlayed for that same play
    /// fires right after — a Skill saying "your next Skill costs 1 less" must not spend itself.</summary>
    private sealed class Entry
    {
        public string Kind = "all";     // attack | skill | power | all
        public int Amount = 1;          // the discount (1..2)
        public bool ThisTurn = true;    // true = expires at the end of the owner's turn; false = this combat
        public int Remaining;           // 0 = unlimited
        public string Source = "";      // for the log
        public CardModel? Granter;      // the card whose play added this entry (null for a relic hook)
        public bool Armed;              // false until the granter's own play has passed

        public string Text()
        {
            string kind = Kind == "all" ? "cards" : Kind + "s";
            string life = ThisTurn ? "this turn" : "this combat";
            return Remaining > 0 ? $"next {Remaining} {kind} -{Amount} {life}" : $"{kind} -{Amount} {life}";
        }
    }

    private readonly List<Entry> _entries = new();
    // Spam guard: the cost hook runs constantly (tooltip preview included); log each card's discount once per combat.
    private readonly HashSet<CardModel> _costLogged = new();

    private static Task Apply(PlayerChoiceContext ctx, Player owner)
        => BetaMainCompatibility.PowerCmd_.Apply.InvokeGeneric<Task<ForgedCostShiftPower?>, ForgedCostShiftPower>(
               null, ctx, owner.Creature, (decimal)1, owner.Creature, (CardModel?)null, false)!;

    /// <summary>The <c>cost_shift</c> executor (card op AND relic hook): add one discount entry to the owner's power,
    /// attaching the power on first use. <paramref name="granter"/> is the played card (null from a relic hook).</summary>
    public static async Task Add(PlayerChoiceContext ctx, Player owner, string? kind, int amount, string? scope, int count,
                                 string source, CardModel? granter)
    {
        var creature = owner.Creature;
        if (!creature.HasPower<ForgedCostShiftPower>())
            await Apply(ctx, owner);
        var power = creature.GetPower<ForgedCostShiftPower>();
        if (power == null) { MainFile.Logger.Warn("[AO] cost_shift: power failed to attach."); return; }
        var entry = new Entry
        {
            Kind = string.IsNullOrEmpty(kind) ? "all" : kind!,
            Amount = Math.Max(1, amount),
            ThisTurn = scope != "combat",
            Remaining = Math.Max(0, count),
            Source = source,
            Granter = granter,
            Armed = granter == null,
        };
        power._entries.Add(entry);
        power._costLogged.Clear(); // the discount set changed — let every card log its new cost once more
        power.Sync();
        MainFile.Logger.Info($"[AO] cost_shift added: {entry.Text()} from '{source}' ({power._entries.Count} live).");
    }

    /// <summary>Mirror the entry count onto the native Amount (the Phase-J/S live-stack mutation); drop the power
    /// when nothing is live any more.</summary>
    private void Sync()
    {
        int n = _entries.Count;
        if (n == 0)
        {
            MainFile.Logger.Info("[AO] cost_shift: no live discounts — power removed.");
            Owner.RemovePowerInternal(this);
            return;
        }
        if (Amount != n)
        {
            int old = Amount;
            Amount = n;
            Owner.InvokePowerModified(this, n - old, false);
        }
    }

    // "all" = your PLAYABLE cards (Attacks / Skills / Powers). A Status or Curse is never discounted (an unplayable
    // curse carries cost -1; GAPTESTAO1 caught Ascender's Bane being rewritten -1 -> 0 before this filter) and never
    // consumes a use.
    private static bool Matches(Entry en, CardModel card) => en.Kind switch
    {
        "attack" => card.Type == CardType.Attack,
        "skill"  => card.Type == CardType.Skill,
        "power"  => card.Type == CardType.Power,
        _        => card.Type is CardType.Attack or CardType.Skill or CardType.Power,
    };

    // Like the base game's FreeAttackPower: only a card in hand / in play is discounted (a draw-pile preview is noise).
    private static bool InPlayablePile(CardModel card) => card.Pile?.Type is PileType.Hand or PileType.Play;

    /// <summary>Base-game hook (the EARLY pass, so a relic's cost_reduction and Corruption's Late set-to-0 compose):
    /// the owner's matching cards cost the SUM of the live matching discounts less, floored at 0 by the engine.</summary>
    public override bool TryModifyEnergyCostInCombat(CardModel card, decimal originalCost, out decimal modifiedCost)
    {
        modifiedCost = originalCost;
        // originalCost < 0 = unplayable (Hook.ModifyEnergyCostInCombat skips those itself, but the CardCostHelper
        // preview path hands listeners the raw cost — verified in the decompiled source); 0 = nothing to discount.
        // Pass both through untouched.
        if (originalCost <= 0 || card.Owner?.Creature != Owner || !InPlayablePile(card)) return false;
        int reduce = 0;
        foreach (var en in _entries)
            if (Matches(en, card)) reduce += en.Amount;
        if (reduce <= 0) return false;
        modifiedCost = Math.Max(0, originalCost - reduce);
        if (_costLogged.Add(card))
            MainFile.Logger.Info($"[AO] cost_shift: '{card.Id}' ({card.Type}) cost {originalCost} -> {modifiedCost} (-{reduce}).");
        return true;
    }

    /// <summary>Consume a use of every budgeted entry the played card matches (the "next N Skills" form); the card
    /// that GRANTED an entry arms it instead of spending it. Fires AFTER the cost was paid (verified: PlayCardAction
    /// spends resources before OnPlayWrapper), so the discount always applied to this play.</summary>
    public override async Task AfterCardPlayed(PlayerChoiceContext ctx, CardPlay cardPlay)
    {
        var card = cardPlay?.Card;
        if (card == null || card.Owner?.Creature != Owner) return;
        bool changed = false;
        for (int i = _entries.Count - 1; i >= 0; i--)
        {
            var en = _entries[i];
            if (!en.Armed)
            {
                en.Armed = true; // the granter's play is over now (this play IS it, or a later one)
                if (en.Granter == card) continue; // the granting play itself — not a use
            }
            if (en.Remaining <= 0 || !Matches(en, card)) continue;
            en.Remaining--;
            MainFile.Logger.Info($"[AO] cost_shift: '{card.Id}' used a discount ({en.Text()} from '{en.Source}'; {en.Remaining} left).");
            if (en.Remaining == 0)
            {
                _entries.RemoveAt(i);
                changed = true;
            }
        }
        if (changed)
        {
            _costLogged.Clear();
            Sync();
        }
        await Task.CompletedTask;
    }

    /// <summary>The this-turn entries expire at the end of the OWNER's turn (the temp-stat lifetime — same hook the
    /// CustomTemporaryPowerModel shells use); combat-scoped entries ride until the power dies with the combat.</summary>
    public override async Task AfterSideTurnEnd(PlayerChoiceContext ctx, CombatSide side, IEnumerable<Creature> participants)
    {
        var people = participants as ICollection<Creature> ?? participants.ToList();
        if (!people.Contains(Owner)) return;
        int expired = _entries.RemoveAll(en => en.ThisTurn);
        if (expired > 0)
        {
            MainFile.Logger.Info($"[AO] cost_shift: {expired} this-turn discount(s) expired at the end of your turn ({_entries.Count} live).");
            _costLogged.Clear();
            Sync();
        }
        await Task.CompletedTask;
    }

    public override List<(string, string)>? Localization =>
        (List<(string, string)>)new PowerLoc("Cost Shift",
            "Some of your cards cost less energy (for this turn, this combat, or your next few plays). Each stack is one live discount.",
            "Some of your cards cost less energy (for this turn, this combat, or your next few plays). Each stack is one live discount.");

    // Emoji icon via the runtime renderer (kicked in MainFile); falls back to the shipped placeholder.
    public override string? CustomPackedIconPath => EmojiIconRenderer.IconPath("cost_shift") ?? base.CustomPackedIconPath;
    public override string? CustomBigIconPath => EmojiIconRenderer.IconPath("cost_shift") ?? base.CustomBigIconPath;
}
