namespace BlankTheSpire.BlankTheSpireCode.Engine;

/// <summary>
/// Phase I (forged orbs): one effect inside a custom orb's <c>passive</c> or <c>evoke</c> list — an
/// <see cref="EffectSpec"/> op paired with a <paramref name="Target"/> modality. Unlike a card effect (which
/// targets via the card's <c>TargetType</c>) or a trigger (which has no target at all), an orb effect picks
/// its own target because an orb's <c>Passive</c> is handed a Creature and its <c>Evoke</c> can reach the
/// board — so a passive can damage an enemy, an evoke can hit all enemies, etc. <paramref name="Target"/> is
/// <c>self</c> / <c>enemy</c> / <c>all_enemies</c> (see <c>OrbRunner</c>).
/// Phase AR (v49): an orb effect may carry a <c>when</c> gate — it rides on the inner <see cref="EffectSpec.When"/>
/// (the same JSON shape as a card effect's <c>when</c>) and is exposed here as <see cref="When"/>; <c>OrbRunner</c>
/// evaluates it at fire time (player-state reads only — an orb fires with no card and no chosen target, so the
/// target / retained reads are validator-forbidden, exactly like a trigger's fire-time gate).
/// </summary>
public sealed record OrbEffect(EffectSpec Effect, string Target)
{
    /// <summary>The fire-time gate (null = unconditional). Phase AR (v49).</summary>
    public Condition? When => Effect.When;
}

/// <summary>
/// A custom (forged) orb type (Phase I). A class declares 0–3 of these inside its <c>orb_pool</c>; each is
/// read from <c>user://forged/characters/KK.json</c> and run by a generic <c>ForgedClassKOrbM</c> shell (a
/// compiled <see cref="BaseLib.Abstracts.CustomOrbModel"/> subclass — one orb = one .NET Type, Q1) through
/// <c>OrbRunner</c>. Like Lightning/Frost/Dark, a custom orb advertises a headline <see cref="PassiveVal"/>
/// (per-turn tick) and <see cref="EvokeVal"/> (burst) shown on the HUD and scaled by Focus, and runs its
/// <see cref="Passive"/> / <see cref="Evoke"/> effect lists. <see cref="Hue"/> drives the placeholder color
/// (real per-orb art is deferred).
/// Phase AR (v49): <see cref="PassiveTiming"/> says WHEN the passive list ticks — <c>turn_end</c> (the default;
/// Lightning/Frost/Glass's <c>BeforeTurnEndOrbTrigger</c>) or <c>turn_start</c> (Plasma's
/// <c>AfterTurnStartOrbTrigger</c>). A passive that grants energy or draws MUST tick at turn start (at turn end
/// the energy evaporates and the cards are discarded); the validator enforces it (see
/// <c>ForgedCharacters.OrbTurnStartOnlyOps</c>).
/// </summary>
public sealed record OrbSpec(
    string Name,
    string Description,
    float Hue,
    int PassiveVal,
    int EvokeVal,
    OrbEffect[] Passive,
    OrbEffect[] Evoke,
    string PassiveTiming = "turn_end")
{
    /// <summary>True when the passive list ticks at the start of your turn (Phase AR, v49).</summary>
    public bool PassiveAtTurnStart => PassiveTiming == "turn_start";
}

/// <summary>
/// One entry in a class's ordered <c>orb_pool</c> (Phase I): either a BASE orb (referenced by name —
/// lightning/frost/dark — with <see cref="CustomSpec"/> null) or a CUSTOM forged orb (<see cref="CustomSpec"/>
/// set, <see cref="CustomIndex"/> = its 1-based slot among the class's ≤3 custom orbs, which maps to the
/// compiled <c>ForgedClassK Orb{CustomIndex}</c> shell). The pool is the single source of truth for what the
/// class can channel (by name) and for class-scoped <c>random</c>.
/// </summary>
public sealed record OrbPoolEntry(string Name, OrbSpec? CustomSpec = null, int CustomIndex = 0)
{
    public bool IsCustom => CustomSpec != null;
}
