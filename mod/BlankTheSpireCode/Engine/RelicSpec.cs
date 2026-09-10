namespace BlankTheSpire.BlankTheSpireCode.Engine;

/// <summary>
/// Phase L: the data definition of a forged RELIC — a class's starting relic, read from the class bundle's
/// optional <c>relic</c> object by <see cref="ForgedCharacters"/> and fed to the compiled
/// <c>ForgedClassKKRelic</c> shell (see <see cref="Powers.ForgedRelic"/>). Like a card, a relic is fully
/// data-driven: <see cref="Hooks"/> (a trigger + effects drawn from the SAME closed effect vocabulary cards use)
/// and <see cref="Modifiers"/> (passive stat bonuses).
///
/// v1 (the spike-proven subset, L-0): scheduled triggers are <c>turn_start</c> / <c>turn_end</c> — both hand the
/// hook a (ctx, player). A "combat start" effect is expressed as a <c>turn_start</c> hook with
/// <see cref="RelicHook.OncePerCombat"/> (the prototype's Lantern pattern), since the engine's BeforeCombatStart
/// hook passes no ctx/player (L-0 unknown #2). L-3 adds reactive triggers: <c>attacked</c> (an enemy damages you,
/// via <c>AfterDamageReceived</c>) plus the <c>attacker</c> target (the creature that just hit you — the
/// Thorns/Bronze-Scales pattern), <c>on_exhaust</c> (one of your cards is Exhausted, via
/// <c>AfterCardExhausted</c> — the Compost-Bin pattern), and <c>on_card_played</c> (you play a card, via
/// <c>AfterCardPlayed</c> — the Watering-Can/tempo pattern). Modifiers v1: <c>max_energy</c>, <c>first_attack</c>,
/// <c>cost_reduction</c> (cards cost N less energy in combat, via <c>TryModifyEnergyCostInCombat</c>). Phase AS (v48): hooks gain a <c>card_type</c> filter (<c>on_card_played</c> only)
/// and an <c>every_n</c> per-combat counter ("every 3rd Attack you play"); modifiers gain <c>attack_base</c> (+N to every
/// card attack — always-on Strength that never decays) and <c>max_hp</c> (±N Max HP granted once when the relic is
/// obtained — the negative form is the sanctioned price for a flat energy stat).
/// </summary>
public sealed record RelicSpec(
    string Id,
    string Name,
    string Description,
    string Tier,                 // "starter" (v1: forged relics are always the class's starter relic)
    RelicHook[] Hooks,
    RelicModifier[] Modifiers);

/// <summary>One triggered relic behaviour: when <see cref="Trigger"/> fires (and <see cref="When"/> holds), run
/// <see cref="Effects"/> on the resolved <see cref="Target"/>. <see cref="OncePerCombat"/> gates one-shot hooks
/// (reset each combat). Phase AS: <see cref="CardType"/> filters <c>on_card_played</c> by the played card's type;
/// <see cref="EveryN"/> makes the hook a counter — it fires on the Nth, 2Nth… matching occurrence (counted per combat,
/// after the trigger + card-type filter, before <see cref="When"/>; the relic UI shows the running count). <see cref="When"/> reuses the card <see cref="Condition"/>, evaluated at FIRE time with no
/// target (so target_has_status is never valid here — the validator/contract forbids it).</summary>
public sealed record RelicHook(
    string Trigger,                  // turn_start|turn_end|attacked|on_exhaust|on_card_played | L-4: combat_end|on_card_drawn|on_damage_dealt|on_block_gained
    EffectSpec[] Effects,
    Condition? When = null,
    string Target = "self",          // "self" | "enemy" | "all_enemies" | "attacker" (default target for damage/debuffs)
    bool OncePerCombat = false,
    string? CardType = null,         // Phase AS (v48): on_card_played only — fire only when the played card is this type (attack|skill|power)
    int EveryN = 0);                 // Phase AS (v48): a per-combat counter — fire on every Nth matching occurrence (2..9; 0/1 = every time)

/// <summary>A passive stat bonus the engine reads directly (not the effect queue). <c>max_energy</c> (+Amount
/// energy per turn, via <see cref="Powers.ForgedRelic.ModifyEnergyGain"/>); L-3 <c>first_attack</c> (Akabeko —
/// +Amount to your first card attack each combat, via <see cref="Powers.ForgedRelic.ModifyDamageAdditive"/>); L-3
/// <c>cost_reduction</c> (your cards cost Amount less energy in combat, via
/// <see cref="Powers.ForgedRelic.TryModifyEnergyCostInCombat"/>). Phase AS (v48): <c>attack_base</c> (+Amount to EVERY card
/// attack, via the same <c>ModifyDamageAdditive</c> — Vajra without the Strength icon) and <c>max_hp</c> (±Amount Max HP,
/// applied once in <see cref="Powers.ForgedRelic.AfterObtained"/> — the Distinguished-Cape recipe; a starter relic's
/// <c>AfterObtained</c> runs from <c>RunManager.FinalizeStartingRelics</c>).</summary>
public sealed record RelicModifier(
    string Stat,                     // "max_energy" | "first_attack" | "cost_reduction" | "start_combat_block" (L-4) | "attack_base" | "max_hp" (Phase AS, v48)
    int Amount);                     // non-zero; max_hp may be NEGATIVE (the standard "boon with a price" drawback)
