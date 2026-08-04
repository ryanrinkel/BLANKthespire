using BaseLib.Abstracts;
using BlankTheSpire.BlankTheSpireCode.Engine;
using Godot;
using MegaCrit.Sts2.Core.Entities.Creatures;
using MegaCrit.Sts2.Core.GameActions.Multiplayer;
using MegaCrit.Sts2.Core.Models;
using MegaCrit.Sts2.Core.Models.Orbs;

namespace BlankTheSpire.BlankTheSpireCode.Powers;

/// <summary>
/// Phase I: the base for the generated <c>ForgedClassKOrbM</c> shells (M = 1..3 per class) — the orb analogue
/// of <see cref="ForgedTriggerPower"/>. One orb = one compiled <see cref="CustomOrbModel"/> subclass (Q1), so
/// the mod ships a fixed pool of generic shells; each shell reads its <see cref="OrbSpec"/> from the class JSON
/// (<see cref="ForgedCharacters.OrbSpecFor"/>) and runs its passive/evoke through <see cref="OrbRunner"/>.
///
/// A shell whose class declares no orb (or fewer than M custom orbs) has a null <see cref="Source"/>: it still
/// auto-registers (the <see cref="CustomOrbModel"/> ctor adds itself to BaseLib's orb registry, like the empty
/// card slots) but advertises harmless zero values, a placeholder color/loc, and never runs — it is simply
/// never referenced by any class's pool. <see cref="IncludeInRandomPool"/> is false for ALL forged orbs:
/// <c>random</c> is class-scoped (the class-pool resolver picks explicitly), never the global pool.
/// </summary>
public abstract class ForgedOrb : CustomOrbModel
{
    /// <summary>The 1-based class index this orb belongs to (set by the generated shell).</summary>
    protected abstract int OrbClass { get; }

    /// <summary>The 1-based custom-orb slot within the class's pool (1..3; set by the generated shell).</summary>
    protected abstract int OrbIndex { get; }

    /// <summary>Public view of the owning class index — used by <see cref="OrbRunner"/> to resolve
    /// <c>channel_orb</c> chains against this orb's class pool.</summary>
    public int ClassK => OrbClass;

    /// <summary>This orb's spec, or null on an unfilled shell (the class declared no such custom orb).</summary>
    private OrbSpec? Source => ForgedCharacters.OrbSpecFor(OrbClass, OrbIndex);

    // (class, custom-index) -> the canonical registered instance. Populated in the ctor (the BaseLib ICustomModel
    // scan creates one instance per shell type at init, and that instance IS the canonical model in ModelDb), so
    // ForgedCharacters can map a custom orb NAME -> its compiled Type without referencing the generated symbols.
    private static readonly Dictionary<(int, int), ForgedOrb> _registry = new();

    protected ForgedOrb()
    {
        // OrbClass/OrbIndex are constant overrides (no field access), so reading them in the base ctor is safe.
        _registry[(OrbClass, OrbIndex)] = this;
    }

    /// <summary>The compiled orb Type for class <paramref name="k"/>'s custom orb slot <paramref name="m"/>,
    /// or null if no such shell registered.</summary>
    public static System.Type? TypeForKey(int k, int m) =>
        _registry.TryGetValue((k, m), out var o) ? o.GetType() : null;

    // --- OrbModel surface (abstract members MUST be provided) ---------------------------------------

    public override decimal PassiveVal => Source?.PassiveVal ?? 0m;
    public override decimal EvokeVal => Source?.EvokeVal ?? 0m;

    // Placeholder color from the orb's hue (real per-orb art deferred); darkened for the inactive look.
    public override Color DarkenedColor => Color.FromHsv(Source?.Hue ?? 0f, 0.7f, 0.55f);

    public override bool IncludeInRandomPool => false; // class-scoped random only — never the global pool

    // --- placeholder art (Phase I MVP; real per-orb art deferred — see ASSETS_TODO.md) --------------
    // A custom orb has no shipped sprite/icon, and the game's CreateSprite/Icon path throws a
    // NullReferenceException on the missing asset (unlike base orbs, which have real art). For the HUD orb we
    // PROCEDURALLY draw a solid circle in the orb's own hue (CreateCustomSprite) — so each custom orb reads as a
    // distinct colored orb instead of all looking like Lightning. The hover-tip icon (a CompressedTexture2D
    // loaded from a path, which we can't synthesize) still borrows Lightning's icon, and CustomSpritePath keeps
    // Lightning's path as a harmless non-HUD fallback. The orb's PassiveVal/EvokeVal still drive the HUD numbers.
    private static OrbModel? _lightning;
    private static OrbModel Lightning => _lightning ??= (OrbModel)ModelDb.Get(typeof(LightningOrb));

    public override string? CustomIconPath => Lightning.IconPath;
    public override string? CustomSpritePath => Lightning.SpritePath;

    public override Node2D? CreateCustomSprite()
    {
        var hue = Source?.Hue ?? 0f;
        return MakeCircleSprite(Color.FromHsv(hue, 0.75f, 0.95f));
    }

    /// <summary>A simple filled-circle orb graphic (a generated texture, no shipped asset): the body in
    /// <paramref name="fill"/>, a darker rim, and a soft highlight so it reads as an orb. NOrb does NOT rescale
    /// the sprite, so the texture size IS the on-screen size — kept small (~48px) to match the base orbs.
    /// All bands are proportional to the diameter. Placeholder until real orb art.</summary>
    private static Sprite2D MakeCircleSprite(Color fill)
    {
        const int d = 48;
        var img = Image.CreateEmpty(d, d, false, Image.Format.Rgba8);
        img.Fill(new Color(0, 0, 0, 0)); // transparent background
        var center = new Vector2(d / 2f, d / 2f);
        float radius = d / 2f - 1f;
        float rimBand = d * 0.10f;       // darker outer ring
        float hiRadius = d * 0.16f;      // specular highlight radius
        var rim = new Color(fill.R * 0.45f, fill.G * 0.45f, fill.B * 0.45f);
        var hi = new Color(
            fill.R + (1f - fill.R) * 0.6f, fill.G + (1f - fill.G) * 0.6f, fill.B + (1f - fill.B) * 0.6f);
        var hiCenter = new Vector2(d * 0.36f, d * 0.34f); // upper-left
        for (int y = 0; y < d; y++)
            for (int x = 0; x < d; x++)
            {
                var p = new Vector2(x + 0.5f, y + 0.5f);
                float dist = center.DistanceTo(p);
                if (dist > radius) continue;
                Color c = dist >= radius - rimBand ? rim : fill;
                if (dist < radius - rimBand && hiCenter.DistanceTo(p) < hiRadius) c = hi;
                img.SetPixel(x, y, c);
            }
        return new Sprite2D { Texture = ImageTexture.CreateFromImage(img) };
    }

    // The PER-TURN TICK. The game calls BeforeTurnEndOrbTrigger at end of turn (this is what Lightning/Frost/Dark
    // override); OrbModel.Passive(ctx, target) is only a helper a subclass's tick may call, so overriding Passive
    // ALONE does nothing — confirmed in-game 2026-06-17 (the orb showed its value but the passive never fired).
    // We run the passive list here and resolve the target ourselves (null -> first hittable enemy for `enemy`).
    public override Task BeforeTurnEndOrbTrigger(PlayerChoiceContext ctx)
    {
        var s = Source;
        return s == null ? Task.CompletedTask : OrbRunner.RunPassive(s, this, ctx, null);
    }

    public override async Task<IEnumerable<Creature>> Evoke(PlayerChoiceContext ctx)
    {
        var s = Source;
        if (s == null) return System.Array.Empty<Creature>();
        return await OrbRunner.RunEvoke(s, this, ctx);
    }

    /// <summary>Focus-scaled value for damage/block effects — mirrors base orbs applying <c>ModifyOrbValue</c>
    /// (which folds in the owner's FocusPower) to their headline numbers, so Focus matters on forged orbs too.</summary>
    public decimal FocusValue(int amount) => ModifyOrbValue((decimal)amount);

    // In-code localization (no .pck rebuild): the orb's HUD title/tooltip is its synthesized description.
    public override List<(string, string)>? Localization
    {
        get
        {
            var s = Source;
            string title = s?.Name ?? "Forged Orb";
            string desc = s != null ? OrbRunner.Describe(s) : "An empty forged orb.";
            return (List<(string, string)>)new OrbLoc(title, desc, desc);
        }
    }
}
