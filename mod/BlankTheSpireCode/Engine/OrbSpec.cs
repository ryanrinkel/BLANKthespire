namespace BlankTheSpire.BlankTheSpireCode.Engine;

/// <summary>
/// Phase I (forged orbs): one effect inside a custom orb's <c>passive</c> or <c>evoke</c> list — an
/// <see cref="EffectSpec"/> op paired with a <paramref name="Target"/> modality. Unlike a card effect (which
/// targets via the card's <c>TargetType</c>) or a trigger (which has no target at all), an orb effect picks
/// its own target because an orb's <c>Passive</c> is handed a Creature and its <c>Evoke</c> can reach the
/// board — so a passive can damage an enemy, an evoke can hit all enemies, etc. <paramref name="Target"/> is
/// <c>self</c> / <c>enemy</c> / <c>all_enemies</c> (see <c>OrbRunner</c>).
/// </summary>
public sealed record OrbEffect(EffectSpec Effect, string Target);

/// <summary>
/// A custom (forged) orb type (Phase I). A class declares 0–3 of these inside its <c>orb_pool</c>; each is
/// read from <c>user://forged/characters/KK.json</c> and run by a generic <c>ForgedClassKOrbM</c> shell (a
/// compiled <see cref="BaseLib.Abstracts.CustomOrbModel"/> subclass — one orb = one .NET Type, Q1) through
/// <c>OrbRunner</c>. Like Lightning/Frost/Dark, a custom orb advertises a headline <see cref="PassiveVal"/>
/// (per-turn tick) and <see cref="EvokeVal"/> (burst) shown on the HUD and scaled by Focus, and runs its
/// <see cref="Passive"/> / <see cref="Evoke"/> effect lists. <see cref="Hue"/> drives the placeholder color
/// (real per-orb art is deferred).
/// </summary>
public sealed record OrbSpec(
    string Name,
    string Description,
    float Hue,
    int PassiveVal,
    int EvokeVal,
    OrbEffect[] Passive,
    OrbEffect[] Evoke);

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
