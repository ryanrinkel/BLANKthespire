using System;
using BaseLib.Extensions;
using BlankTheSpire.BlankTheSpireCode.Engine;
using Godot;
using MegaCrit.Sts2.Core.Nodes.Combat;

namespace BlankTheSpire.BlankTheSpireCode.Cards.Forged;

/// <summary>
/// Sprite spike (Tier 1+2): build a forged class's standing combat model from a generated PNG cached at
/// <c>user://forged/characters/KK/sprite.png</c> (delivered like the splash: a <c>sprite_url</c> in the
/// import bundle, see <see cref="ForgedSplash.TryCacheFromBundle"/>). Best-effort: no sprite / bad PNG →
/// null → the caller falls back to the Track 1 "?" texture. Micro-animations (idle bob + trigger tweens)
/// live in <see cref="ForgedSpriteAnimator"/>.
/// </summary>
public static class ForgedSprite
{
    /// <summary>On-screen character height in px (the Sprite2D renders at image pixel size; base-game
    /// characters stand ~280-320px tall). The cached image is resized to this on load.</summary>
    private const float TargetHeight = 300f;

    public static string SpritePath(int k) => $"user://forged/characters/{k:00}/sprite.png";

    /// <summary>The forged-sprite combat model for class <paramref name="k"/>, or null if no usable
    /// sprite is cached (caller falls back to the "?" placeholder). Never throws.</summary>
    public static NCreatureVisuals? TryCreateVisuals(int k)
    {
        try
        {
            var tex = LoadTexture(k);
            return tex == null ? null : BuildVisuals(tex);
        }
        catch (Exception e)
        {
            MainFile.Logger.Warn($"[ForgedSprite] visuals for class {k:00} failed, using placeholder: {e.Message}");
            return null;
        }
    }

    /// <summary>The cached sprite as a bare texture (trimmed + scaled to combat height), for consumers
    /// other than the combat model — e.g. the merchant-screen shopper. Null if absent/bad; never throws.</summary>
    public static ImageTexture? TryLoadTexture(int k)
    {
        try { return LoadTexture(k); }
        catch (Exception e)
        {
            MainFile.Logger.Warn($"[ForgedSprite] texture for class {k:00} failed: {e.Message}");
            return null;
        }
    }

    private static ImageTexture? LoadTexture(int k)
    {
        string path = SpritePath(k);
        if (!Godot.FileAccess.FileExists(path)) return null;
        using var f = Godot.FileAccess.Open(path, Godot.FileAccess.ModeFlags.Read);
        if (f == null) return null;
        byte[] buf = f.GetBuffer((long)f.GetLength());
        var img = new Image();
        if (img.LoadPngFromBuffer(buf) != Error.Ok)
        {
            MainFile.Logger.Warn($"[ForgedSprite] {path} is not a readable PNG.");
            return null;
        }
        if (img.GetFormat() != Image.Format.Rgba8) img.Convert(Image.Format.Rgba8);

        // Generated art rarely arrives tightly cropped; transparent padding would inflate the on-screen
        // footprint (feet float, bounds oversize), so trim to the used rect before sizing.
        var used = img.GetUsedRect();
        if (used.Size.X > 0 && used.Size.Y > 0 && used.Size != img.GetSize()) img = img.GetRegion(used);
        if (img.GetHeight() < 1 || img.GetWidth() < 1) return null;

        float scale = TargetHeight / img.GetHeight();
        if (Mathf.Abs(scale - 1f) > 0.01f)
            img.Resize(Mathf.Max(1, (int)Math.Round(img.GetWidth() * scale)), (int)TargetHeight,
                Image.Interpolation.Lanczos);
        return ImageTexture.CreateFromImage(img);
    }

    /// <summary>
    /// Same node contract BaseLib's NCreatureVisualsFactory produces from a Texture2D, with one difference:
    /// %Visuals is a feet-pivot CONTAINER holding the Sprite2D rather than being the sprite itself.
    /// NCreature's own tweens (AnimShake / DoScaleTween) animate the NCreatureVisuals ROOT while the
    /// animator tweens this inner body — separate nodes, so they never fight over a property — and with the
    /// feet at the container origin, squash/stretch and death-tip pivot at the ground, not the sprite center.
    /// </summary>
    private static NCreatureVisuals BuildVisuals(Texture2D tex)
    {
        var root = new NCreatureVisuals();
        Vector2 size = tex.GetSize();

        var body = new Node2D();
        root.AddUnique(body, "Visuals");
        body.AddChild(new Sprite2D { Texture = tex, Position = new Vector2(0f, -size.Y * 0.5f) });

        Vector2 boundsSize = size * 1.1f;
        var bounds = new Control();
        root.AddUnique(bounds, "Bounds");
        bounds.Position = new Vector2(-boundsSize.X / 2f, -boundsSize.Y);
        bounds.Size = boundsSize;

        var intent = new Marker2D();
        root.AddUnique(intent, "IntentPos");
        intent.Position = bounds.Position + bounds.Size * new Vector2(0.5f, 0f) + new Vector2(0f, -70f);

        var center = new Marker2D();
        root.AddUnique(center, "CenterPos");
        center.Position = bounds.Position + bounds.Size * new Vector2(0.5f, 0.6f);

        // Tweens need an in-tree node, so the idle bob starts on the tree's ready signal.
        root.Connect(Node.SignalName.Ready,
            Callable.From(() => ForgedSpriteAnimator.StartIdle(body)),
            (uint)GodotObject.ConnectFlags.OneShot);
        return root;
    }
}
