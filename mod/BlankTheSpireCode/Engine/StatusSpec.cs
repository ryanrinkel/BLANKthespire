namespace BlankTheSpire.BlankTheSpireCode.Engine;

/// <summary>
/// A custom (forged) STATUS effect — Phase J. The third "invent your own X" axis after orbs (Phase I, a class
/// invents its own elements) and triggers (Phase H3, a class builds its own engines): a forged status is the
/// signature buff/debuff a whole archetype is built around. Mechanically it is a <c>CustomPowerModel</c> of the
/// MODIFIER family — "while active, change a number" — driven by the return-value <c>Modify*</c> hooks that no
/// base power exposes generically (the spike proved <c>ModifyDamageAdditive</c> fires on a player-applied power).
///
/// A class declares 0–4 of these in its <c>status_pool</c> (read from <c>user://forged/characters/KK.json</c>);
/// each is run by a generic <c>ForgedClassKStatusM</c> shell (one compiled <c>CustomPowerModel</c> type, Q1).
/// Cards apply a status by its lowercased <see cref="Name"/> via the <c>apply_status_custom</c> op; the side
/// (<see cref="IsBuff"/> → self, debuff → the card's target) mirrors the orb/effect runner's buff/debuff split.
///
/// J-1 shipped the ADDITIVE modifier hooks; Phase AQ (v47) added the two status-pool hooks the J-1 cut deferred —
/// <c>damage_over_time</c> (a Poison-shaped debuff: the afflicted enemy loses HP equal to its stacks at the start of
/// its turn) and <c>hit_count</c> (a buff: your card attacks hit +stacks extra times) — plus <c>mode:
/// multiplicative</c> for the two damage hooks (×(1 + 0.1·stacks), capped at ×2). Reactive (After*/retaliate) hooks
/// stay with <c>add_trigger</c>. Emoji is the default art (text glyph + a rendered <c>.res</c> icon, see EmojiIconRenderer).
/// </summary>
/// <param name="Name">The status's display name (e.g. "Razor Focus"). Cards reference it by lowercased name.</param>
/// <param name="Emoji">A single emoji used as the status's text glyph + on-creature icon badge.</param>
/// <param name="Description">Tooltip body (what the status does); synthesized if the JSON omits it.</param>
/// <param name="IsBuff">True = a buff applied to the player (self); false = a debuff applied to the card's target.</param>
/// <param name="SingleStack">True = <c>PowerStackType.Single</c> (does not accumulate); false = Counter (stacks).</param>
/// <param name="Decay">Per-turn decay: <c>none</c> | <c>lose_one_eot</c> (−1 stack at end of your turn) |
/// <c>lose_all_eot</c> (clears at end of your turn, Temporary-* style).</param>
/// <param name="Hook">Which number it changes: <c>damage_dealt</c> | <c>damage_taken</c> | <c>block_gained</c> |
/// <c>energy_gain</c> | <c>card_draw</c> (J-1 additive set) | <c>damage_over_time</c> (AQ: debuff, HP loss = stacks at
/// the afflicted enemy's turn start; must decay) | <c>hit_count</c> (AQ: buff, +stacks hits on your card attacks; must
/// decay). See <c>ForgedStatusPower</c>.</param>
/// <param name="Mode">Modifier mode — <c>additive</c> (stacks are a flat bonus) or, on <c>damage_dealt</c> /
/// <c>damage_taken</c> only, <c>multiplicative</c> (×(1 + 0.1·stacks), capped at ×2; Phase AQ).</param>
public sealed record StatusSpec(
    string Name,
    string Emoji,
    string Description,
    bool IsBuff,
    bool SingleStack,
    string Decay,
    string Hook,
    string Mode);
