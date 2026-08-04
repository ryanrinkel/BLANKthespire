using System.Linq;
using MegaCrit.Sts2.Core.Entities.Cards;

namespace BlankTheSpire.BlankTheSpireCode.Engine;

/// <summary>
/// One atomic effect from the BlankTheSpire closed vocabulary (the C# mirror of the JSON `effects[]`
/// entries - see mod/contract/VOCABULARY.md). The LLM/codegen pipeline emits these.
/// </summary>
/// <param name="Op">Vocabulary op: damage, block, draw, apply_status, ... (EffectRunner dispatches on this).</param>
/// <param name="Amount">Scalar amount for the op (damage/block/draw count, status stacks). For a multi-hit
/// <c>damage</c> op this is the PER-HIT damage.</param>
/// <param name="Status">Status/power id for apply_status (e.g. "vulnerable", "weak").</param>
/// <param name="Hits">Number of hits for a <c>damage</c> op (default 1 = a single hit). >1 makes it a
/// multi-hit attack dealing <c>Amount</c> damage <c>Hits</c> times. Ignored by non-damage ops.</param>
/// <param name="Scale">If set, this op's amount comes from a live combat-state SCALAR, not <c>Amount</c>
/// (Phase F5; only on damage/block/draw). Values: <c>"x"</c> = the resolved X (= energy spent) of an X-cost
/// card (X-cost coupling: requires/required-by a <c>"X"</c> cost); <c>"cards_in_hand"</c> = the count of OTHER
/// cards in your hand; <c>"cards_retained"</c> = how many cards you held into this turn (turn-start snapshot);
/// <c>"unspent_energy_last_turn"</c> = energy left at the end of your last turn. Null = fixed <c>Amount</c>.</param>
/// <param name="Orb">Orb type for the <c>channel_orb</c> op (lightning/frost/dark/random). Ignored by other ops.</param>
/// <param name="When">Optional condition (Phase H): the effect runs ONLY if this predicate holds at play time.
/// Null = always run. The effect is still declared (shown on the card); it's just skipped when false.
/// (Exception: on an <c>add_trigger</c> op, <c>When</c> is the FIRE-time gate the granted power re-evaluates
/// each turn, not a play-time gate — the power is always granted.)</param>
/// <param name="Trigger">Trigger kind for the <c>add_trigger</c> op (Phase H3): <c>turn_end</c> / <c>turn_start</c>.
/// The op grants an ongoing power that runs <see cref="Triggered"/> at that moment. Null for every other op.</param>
/// <param name="Triggered">The effects the <c>add_trigger</c> power runs when it fires (Phase H3). These execute
/// with LITERAL amounts on the player (no card/target context), so they are a SELF/orb-only sub-vocabulary —
/// see <c>TriggerRunner</c>. Null for every other op.</param>
/// <param name="StatusName">The custom (forged) status name for the <c>apply_status_custom</c> op (Phase J),
/// resolved against the card's class <c>status_pool</c> at play time. Null for every other op.</param>
/// <param name="SummonName">The forged-minion name for the <c>summon</c> op (Phase K), resolved against the card's
/// class <c>summon_pool</c> at play time. Null for every other op.</param>
/// <param name="OncePerTurn">Phase H4 (gap #13): on an <c>add_trigger</c> op whose trigger is a MULTI-FIRE reactive
/// kind (on_exhaust / on_card_played / on_card_drawn / on_damage_dealt / on_block_gained / attacked / on_hp_lost),
/// gate the payload to fire AT MOST ONCE per turn. Ignored (and validator-rejected) on turn_start/turn_end/ripen,
/// which already fire at most once per turn. Default false.</param>
/// <param name="Target">Phase H4 (gap #14): on a <c>add_trigger</c> PAYLOAD effect, aim it at enemies —
/// <c>"enemy"</c> (first hittable) or <c>"all_enemies"</c>. Only <c>damage</c> and an enemy-debuff
/// <c>apply_status</c> (vulnerable/weak/frail/poison) may be targeted; every other payload op stays self/orb-only
/// (Target null). Never set on a card-level effect (a card uses <see cref="CardSpec.Target"/>). Default null.</param>
/// <param name="CardId">Phase Q (gap #16): the SAME-CLASS card id the <c>add_card</c> op generates copies of,
/// resolved against the player's forged class at play time (see <c>ForgedCharacters.ResolveClassCardModel</c>).
/// Class-only, like <see cref="SummonName"/>. Null for every other op.</param>
/// <param name="Pile">Phase Q (gap #16): which combat pile <c>add_card</c> drops the generated copies into —
/// <c>"hand"</c> / <c>"discard"</c> / <c>"draw"</c>. Null for every other op.</param>
/// <param name="Pole">Phase S (gap #1): which pole the <c>balance_step</c> op moves the Balance gauge toward —
/// <c>"light"</c> or <c>"dark"</c> (<see cref="Amount"/> is the step size). Null for every other op.</param>
/// <param name="Grow">Phase U (gap #23, Rampage): the per-play additive damage step (damage-only; 0 = none).</param>
/// <param name="Cards">Phase V/X (gap #18): the hand-scope for the <c>upgrade_card</c> op — <c>"random"</c>
/// (one random upgradable card in hand), <c>"all"</c> (every upgradable card in hand), or <c>"choose"</c>
/// (Phase X — the player picks one upgradable hand card via the base-game hand-upgrade picker). The upgrade is
/// COMBAT-SCOPED (hand cards are deck clones; the run deck is untouched). Null for every other op.</param>
public sealed record EffectSpec(string Op, int Amount = 0, string? Status = null, int Hits = 1, string? Scale = null,
    string? Orb = null, Condition? When = null, string? Trigger = null, EffectSpec[]? Triggered = null,
    string? StatusName = null, string? SummonName = null, bool OncePerTurn = false, string? Target = null,
    string? CardId = null, string? Pile = null, string? Pole = null, int Grow = 0, string? Cards = null,
    string? Tag = null)
{
    /// <summary>This op's amount comes from a live scalar (any <see cref="Scale"/>), not <see cref="Amount"/>.</summary>
    public bool IsScaled => Scale != null;

    /// <summary>Phase U (gap #23, Rampage): this <c>damage</c> op's amount INCREASES by <see cref="Grow"/> each
    /// time THIS card instance has been played earlier this combat (<c>amount + Grow × plays_this_combat</c>);
    /// first play = printed amount. Per-card-instance (base StS Rampage). Mutually exclusive with <see cref="Scale"/>.</summary>
    public bool HasGrow => Grow != 0;

    /// <summary>The X-cost scalar specifically (the only scalar coupled to a <c>"X"</c> card cost). Lets the
    /// pre-F5 X-cost wiring stay unchanged: every old <c>ScaleX</c> read keeps meaning "is this X-cost".</summary>
    public bool ScaleX => Scale == "x";
}

/// <summary>A combat-state predicate gating an effect (Phase H per-effect <c>when</c>). <paramref name="Kind"/>
/// selects the check (see <c>Conditions.Kinds</c>); <paramref name="Value"/>/<paramref name="Status"/> are its
/// params; <paramref name="Negate"/> inverts the result (the "else" lever).</summary>
public sealed record Condition(string Kind, int Value = 0, string? Status = null, bool Negate = false);

/// <summary>
/// The full data definition of a card. Two sources produce a CardSpec:
///   1. Codegen (baked path) — emits one tiny <see cref="DataCard"/> subclass per card holding a static
///      CardSpec literal; its name/text live in the shipped .pck localization (so Title/Description are null).
///   2. Forged slots (data-driven path, P1) — <see cref="ForgedCards"/> reads a CardSpec from JSON in the
///      user-data dir at startup and carries its <see cref="Title"/>/<see cref="Description"/> inline, which
///      <see cref="DataCard"/> injects via BaseLib's in-code localization (no .pck rebuild).
/// <see cref="Upgrade"/> is the parallel post-upgrade effect list (same shape as the prototype's JSON);
/// per-var upgrade deltas are derived from it positionally. <see cref="IsEmpty"/> marks an unfilled slot —
/// such a card registers nothing (kept out of pools and the card library) until JSON fills it.
/// <see cref="IsToken"/> marks a non-drafted TOKEN card (the forge class's Sovereign Blade): it is seeded
/// into the starting deck by slot reference like any other, and registers with showInCardLibrary:false so it
/// is not listed in the compendium — but it STAYS pool-registered (autoAdd:true) so CardModel.get_Pool() can
/// resolve it when it is drawn (an unpooled card hangs combat via the MockCardPool guard). It is kept out of
/// rewards/drafts by being Basic rarity, which CardFactory excludes everywhere (see <see cref="DataCard"/>).
/// </summary>
public sealed record CardSpec(
    string Id,
    int Cost,
    CardType Type,
    CardRarity Rarity,
    TargetType Target,
    EffectSpec[] Effects,
    EffectSpec[]? Upgrade = null,
    string? Title = null,
    string? Description = null,
    bool IsEmpty = false,
    bool CostsX = false,
    bool IsToken = false,
    string[]? Tags = null,
    int? UpgradedCost = null)
{
    /// <summary>Phase AE (gap #25): does this card declare <paramref name="tag"/> (a lowercase synergy slug)?
    /// Purely declarative metadata read by the <c>tag_cards_owned</c> scalar's deck scan (see EffectRunner
    /// .TagCardsOwned); we keep tags in the spec (not the game's CanonicalTags) since only our own scan needs them.</summary>
    public bool HasTag(string? tag) => tag != null && Tags != null && System.Array.IndexOf(Tags, tag) >= 0;

    /// <summary>Phase W (gap #19): does this card carry the <c>purge</c> flag-op? A purged card is removed from the
    /// run deck for the rest of the run when played (see <see cref="DataCard.GetResultPileTypeForCardPlay"/> +
    /// EffectRunner's purge case). Read by the DataCard pile-type override, which is why it lives on the spec.</summary>
    public bool HasPurge => Effects.Any(e => e.Op == "purge");

    /// <summary>The CardSpec for an unfilled forged slot: harmless valid enums, no effects, hidden.</summary>
    public static CardSpec EmptySlot(string id) => new(
        Id: id, Cost: 0, Type: CardType.Skill, Rarity: CardRarity.Common, Target: TargetType.Self,
        Effects: [], Title: "Forged Slot (empty)", Description: "", IsEmpty: true);
}
