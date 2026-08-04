using System.Collections.Generic;
using Godot;

namespace BlankTheSpire.BlankTheSpireCode.Engine;

/// <summary>
/// EXPLORE SPIKE — can an EMOJI be a custom status's on-creature icon? Powers only accept a path-based icon
/// (<c>CustomPackedIconPath</c>, a string the game turns into a texture — there is no procedural sprite hook
/// like orbs have). So this rasterizes an emoji glyph to a PNG at runtime and saves it under <c>user://</c>,
/// then PROBES whether Godot's resource loader will actually load that file (the open question: the game's
/// icon pipeline likely uses ResourceLoader/GD.Load, which normally needs imported <c>res://</c> assets, not
/// a runtime <c>user://</c> raw PNG). The probe gates exposure so a non-loadable path is never handed to the
/// game (avoids a missing-asset hang like the Phase I orb sprite bug).
///
/// Two things this answers: (1) does Godot render the emoji glyph at all (color font support), and (2) is a
/// runtime PNG loadable as a power icon. The rendered file's globalized path is logged so the PNG can be eyeballed.
/// </summary>
public partial class EmojiIconRenderer : Node
{
    // Color-emoji font (COLR/CPAL on Windows, CBDT on Linux). OS-detected: the Windows box uses Segoe UI
    // Emoji, the Linux dev box uses Noto Color Emoji. A missing/unloadable font fails gracefully -> default
    // theme font (tofu) -> the icon stays a placeholder, so this never hangs. Was hardcoded to the Windows
    // path, which always failed on this native-Linux box (forged emoji icons never rendered).
    private static readonly string EmojiFontPath = ResolveEmojiFont();
    private const int IconSize = 128;

    private static string ResolveEmojiFont()
    {
        const string windowsEmoji = "C:/Windows/Fonts/seguiemj.ttf";
        if (System.OperatingSystem.IsWindows()) return windowsEmoji;
        foreach (var p in new[]
        {
            "/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf",  // Debian/Ubuntu (this box)
            "/usr/share/fonts/noto/NotoColorEmoji.ttf",           // Arch/Fedora
            "/usr/share/fonts/google-noto-emoji/NotoColorEmoji.ttf",
            "/System/Library/Fonts/Apple Color Emoji.ttc",        // macOS
        })
            if (System.IO.File.Exists(p)) return p;
        return windowsEmoji; // nothing found — fail-safe (load fails -> placeholder icon, as before)
    }

    // key -> user:// path, but ONLY once the render finished AND the loader probe succeeded (safe to expose).
    private static readonly Dictionary<string, string> _loadable = new();

    private readonly string _key;
    private readonly string _emoji;
    private SubViewport? _vp;
    private int _frames;

    private EmojiIconRenderer(string key, string emoji) { _key = key; _emoji = emoji; }

    /// <summary>The icon path for <paramref name="key"/> if it rendered and is loadable, else null (caller
    /// should fall back to a shipped placeholder).</summary>
    public static string? IconPath(string key) => _loadable.TryGetValue(key, out var p) ? p : null;

    /// <summary>Kick off a one-shot off-screen render of <paramref name="emoji"/> for <paramref name="key"/>.
    /// Safe to call at mod init; the node adds itself to the scene tree on the next idle frame.</summary>
    public static void Kick(string key, string emoji)
    {
        try
        {
            if (Godot.Engine.GetMainLoop() is not SceneTree tree || tree.Root == null)
            {
                MainFile.Logger.Warn($"[Spike] EmojiIconRenderer.Kick('{key}'): no SceneTree yet; skipping icon render.");
                return;
            }
            tree.Root.CallDeferred(Node.MethodName.AddChild, new EmojiIconRenderer(key, emoji));
        }
        catch (System.Exception e)
        {
            MainFile.Logger.Warn($"[Spike] EmojiIconRenderer.Kick('{key}') failed: {e.Message}");
        }
    }

    public override void _Ready()
    {
        try
        {
            _vp = new SubViewport
            {
                Size = new Vector2I(IconSize, IconSize),
                TransparentBg = true,
                RenderTargetUpdateMode = SubViewport.UpdateMode.Always,
                Disable3D = true,
            };
            var label = new Label
            {
                Text = _emoji,
                HorizontalAlignment = HorizontalAlignment.Center,
                VerticalAlignment = VerticalAlignment.Center,
            };
            label.SetAnchorsPreset(Control.LayoutPreset.FullRect);

            var font = new FontFile();
            var ferr = font.LoadDynamicFont(EmojiFontPath);
            if (ferr == Error.Ok)
                label.AddThemeFontOverride("font", font);
            else
                MainFile.Logger.Warn($"[Spike] emoji font load '{EmojiFontPath}' -> {ferr} (using default theme font).");
            label.AddThemeFontSizeOverride("font_size", (int)(IconSize * 0.72f));

            _vp.AddChild(label);
            AddChild(_vp);
        }
        catch (System.Exception e)
        {
            MainFile.Logger.Warn($"[Spike] EmojiIconRenderer._Ready('{_key}') failed: {e.Message}");
            QueueFree();
        }
    }

    public override void _Process(double delta)
    {
        // Give the SubViewport a few frames to actually render the glyph before grabbing its texture.
        if (_vp == null) { QueueFree(); return; }
        if (++_frames < 3) return;

        try
        {
            var img = _vp.GetTexture().GetImage();
            bool blank = IsBlank(img);

            // Also drop a PNG for eyeballing the rasterized glyph.
            img.SavePng($"user://bts_emoji_{_key}.png");

            // A runtime user:// RAW PNG can't be loaded by ResourceLoader (it needs a .import) — confirmed
            // in-game. But a NATIVE Godot resource (.res) embeds the image and DOES load at runtime, so save
            // the texture as .res and hand the game THAT path.
            var tex = ImageTexture.CreateFromImage(img);
            var resPath = $"user://bts_emoji_{_key}.res";
            var serr = ResourceSaver.Save(tex, resPath);
            string abs = ProjectSettings.GlobalizePath(resPath);
            MainFile.Logger.Info($"[Spike] emoji '{_emoji}' rendered (opaque pixels: {!blank}); saved {abs} -> {serr}.");

            if (serr == Error.Ok)
            {
                // Probe load (gates exposure so a bad path never reaches the game's icon pipeline).
                var probe = ResourceLoader.Load<Texture2D>(resPath);
                if (probe != null)
                {
                    _loadable[_key] = resPath;
                    MainFile.Logger.Info($"[Spike] emoji icon '{_key}' IS loadable (.res) -> exposing as power icon.");
                }
                else
                {
                    MainFile.Logger.Info($"[Spike] emoji icon '{_key}' NOT loadable even as .res -> icon stays placeholder.");
                }
            }
        }
        catch (System.Exception e)
        {
            MainFile.Logger.Warn($"[Spike] EmojiIconRenderer capture('{_key}') failed: {e.Message}");
        }
        QueueFree();
    }

    /// <summary>True if the image has no opaque pixels (i.e. the glyph didn't render — tofu/empty).</summary>
    private static bool IsBlank(Image img)
    {
        for (int y = 0; y < img.GetHeight(); y += 4)
            for (int x = 0; x < img.GetWidth(); x += 4)
                if (img.GetPixel(x, y).A > 0.05f) return false;
        return true;
    }
}
