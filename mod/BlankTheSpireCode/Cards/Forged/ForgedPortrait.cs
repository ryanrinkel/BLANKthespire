using System;
using System.Collections.Generic;
using Godot;
using HarmonyLib;
using MegaCrit.Sts2.Core.Models;
using MegaCrit.Sts2.Core.Nodes.Screens.CharacterSelect;

namespace BlankTheSpire.BlankTheSpireCode.Cards.Forged;

/// <summary>
/// The small 132x195 character-select CARD for a forged class. Vanilla cards are a close-up of the
/// character's head on a flat class color; forged classes only ship a full-body cut-out at
/// <c>user://forged/characters/KK/sprite.png</c> (see <see cref="ForgedSprite"/>), so the head crop and
/// its colored backdrop are derived here at runtime and cached next to the sprite as <c>portrait.png</c>
/// (computed once, and a human can open the file to see what the crop picked).
///
/// Display patches the CONSUMER node, not the model's icon path: unlike the relic icon (which rides a
/// synthetic res:// path via <see cref="Resource.TakeOverPath"/>, see <c>Powers.ForgedRelicIcon</c>),
/// <c>CharacterModel.CharacterSelectIcon</c> resolves with <c>ResourceLoader.Load&lt;CompressedTexture2D&gt;</c>
/// — an <see cref="ImageTexture"/> parked under a synthetic path would satisfy the loader's cache but
/// throw <see cref="InvalidCastException"/> on that cast. So a postfix on
/// <see cref="NCharacterSelectButton"/> assigns the derived texture to the button's own TextureRect
/// after vanilla has set it. Best-effort throughout: no sprite / bad PNG → null → the shipped "?" card.
/// </summary>
public static class ForgedPortrait
{
    /// <summary>Card size the select button's %Icon expects (matches char_select_char_name.png).</summary>
    private const int CardWidth = 132;
    private const int CardHeight = 195;

    /// <summary>Fraction of the trimmed sprite height kept below the head top — a head-and-shoulders
    /// bust rather than a face, which is what the vanilla cards read as at this size.</summary>
    private const float CropHeightFraction = 0.28f;

    /// <summary>A row counts as "the head" once its longest opaque run covers this much of the trimmed
    /// width. Runs shorter than this are a raised staff/sword/antenna tip, not a skull.</summary>
    private const float HeadRunFraction = 0.12f;

    private const float AlphaThreshold = 0.5f;

    /// <summary>Headroom above the detected head top, as a fraction of the crop height, so hair/helmet
    /// tops don't kiss the card edge.</summary>
    private const float HeadroomFraction = 0.04f;

    /// <summary>The crop is centred horizontally on the alpha centroid of the figure's LOWER part
    /// (this fraction of the trimmed height down to the feet). Tuned on real sprites: centring on the
    /// head band itself failed whenever a wide prop (jetpack, pauldron, raised weapon) shared those rows
    /// and dragged the centre off the face, while torso + legs sit under the head on any upright figure.</summary>
    private const float BodyAnchorTop = 0.45f;

    public static string PortraitPath(int k) => $"user://forged/characters/{k:00}/portrait.png";

    /// <summary>Per-slot resolved portraits, strong refs so the texture outlives the button that shows
    /// it (null entries are cached too: a slot without a sprite must not re-derive on every Init).</summary>
    private static readonly Dictionary<int, ImageTexture?> _cache = new();

    /// <summary>Drop a slot's portrait, memory AND disk, so a re-import (new sprite.png) derives a fresh
    /// one instead of serving the previous class's head forever.</summary>
    public static void Invalidate(int k)
    {
        _cache.Remove(k);
        try
        {
            string path = PortraitPath(k);
            if (Godot.FileAccess.FileExists(path)) DirAccess.RemoveAbsolute(path);
        }
        catch (Exception e)
        {
            MainFile.Logger.Warn($"[ForgedPortrait] could not delete stale portrait for class {k:00}: {e.Message}");
        }
    }

    /// <summary>The 132x195 select card for class <paramref name="k"/>, derived on first use and cached
    /// to disk, or null when there is no usable sprite (caller keeps the "?" card). Never throws.</summary>
    public static ImageTexture? TryGetTexture(int k)
    {
        if (_cache.TryGetValue(k, out var cached)) return cached;

        ImageTexture? result = null;
        try
        {
            var img = LoadCached(k);
            bool derived = img == null;
            if (img == null) img = DeriveAndSave(k);
            if (img != null)
            {
                result = ImageTexture.CreateFromImage(img);
                MainFile.Logger.Info($"[ForgedPortrait] portrait live for class {k:00} ({(derived ? "derived" : "cached")}).");
            }
        }
        catch (Exception e)
        {
            MainFile.Logger.Warn($"[ForgedPortrait] portrait for class {k:00} failed, using placeholder: {e.Message}");
            result = null;
        }

        _cache[k] = result;
        return result;
    }

    /// <summary>The already-derived portrait.png, or null if it has not been built yet.</summary>
    private static Image? LoadCached(int k)
    {
        string path = PortraitPath(k);
        if (!Godot.FileAccess.FileExists(path)) return null;
        using var f = Godot.FileAccess.Open(path, Godot.FileAccess.ModeFlags.Read);
        if (f == null) return null;
        var img = new Image();
        if (img.LoadPngFromBuffer(f.GetBuffer((long)f.GetLength())) != Error.Ok)
        {
            MainFile.Logger.Warn($"[ForgedPortrait] {path} is not a readable PNG; re-deriving.");
            return null;
        }
        return img;
    }

    /// <summary>Build the card from the cached full-body sprite and write it to portrait.png. Null when
    /// the sprite is missing or unreadable.</summary>
    private static Image? DeriveAndSave(int k)
    {
        string spritePath = ForgedSprite.SpritePath(k);
        if (!Godot.FileAccess.FileExists(spritePath)) return null;

        Image src;
        using (var f = Godot.FileAccess.Open(spritePath, Godot.FileAccess.ModeFlags.Read))
        {
            if (f == null) return null;
            src = new Image();
            if (src.LoadPngFromBuffer(f.GetBuffer((long)f.GetLength())) != Error.Ok)
            {
                MainFile.Logger.Warn($"[ForgedPortrait] {spritePath} is not a readable PNG.");
                return null;
            }
        }
        if (src.GetFormat() != Image.Format.Rgba8) src.Convert(Image.Format.Rgba8);

        // The generated cut-outs carry a lot of transparent padding; every measurement below (head
        // scan, centroid, crop fractions) is relative to the figure, so trim first.
        var used = src.GetUsedRect();
        if (used.Size.X > 0 && used.Size.Y > 0 && used.Size != src.GetSize()) src = src.GetRegion(used);
        int w = src.GetWidth(), h = src.GetHeight();
        if (w < 1 || h < 1) return null;

        // One GetData() and raw byte indexing: a per-pixel GetPixel() scan of a ~1024x1536 sprite is
        // hundreds of thousands of marshalled calls.
        byte[] data = src.GetData();
        if (data.Length < w * h * 4) return null;

        int headTop = FindHeadTop(data, w, h);
        int cropH = Mathf.Clamp((int)Math.Round(h * CropHeightFraction), 1, h);
        int cropY = Mathf.Clamp(headTop - (int)Math.Round(cropH * HeadroomFraction), 0, h - cropH);
        int cropW = Mathf.Clamp((int)Math.Round(cropH * (double)CardWidth / CardHeight), 1, w);
        int bodyTop = Mathf.Clamp((int)Math.Round(h * BodyAnchorTop), 0, h - 1);
        int cropX = Mathf.Clamp(AlphaCentroidX(data, w, bodyTop, h - bodyTop) - cropW / 2, 0, w - cropW);
        var crop = src.GetRegion(new Rect2I(cropX, cropY, cropW, cropH));

        float hue = DominantHue(data, w, h) ?? (k * 0.61803398875f) % 1f;

        // Composite at the crop's NATIVE resolution and resize the finished card once, so the head's
        // alpha edge is resampled together with the backdrop instead of against transparency.
        var card = BuildGradient(cropW, cropH, hue);
        card.BlendRect(crop, new Rect2I(0, 0, cropW, cropH), Vector2I.Zero);
        card.Resize(CardWidth, CardHeight, Image.Interpolation.Lanczos);

        Save(k, card);
        return card;
    }

    /// <summary>First row whose longest contiguous opaque run is a real head's width. Row 0 when the
    /// sprite never widens that far (tiny or unusual art) — a worse crop, never a failure.</summary>
    private static int FindHeadTop(byte[] data, int w, int h)
    {
        int minRun = Math.Max(1, (int)Math.Round(w * HeadRunFraction));
        byte cut = (byte)(AlphaThreshold * 255f);
        for (int y = 0; y < h; y++)
        {
            int run = 0, best = 0, row = y * w * 4;
            for (int x = 0; x < w; x++)
            {
                if (data[row + x * 4 + 3] > cut)
                {
                    run++;
                    if (run > best) best = run;
                }
                else run = 0;
            }
            if (best >= minRun) return y;
        }
        return 0;
    }

    /// <summary>Alpha-weighted mean x over a row band (see <see cref="BodyAnchorTop"/>), so the crop
    /// centres on the figure rather than on the image middle (figures are rarely centred in their own
    /// cut-out).</summary>
    private static int AlphaCentroidX(byte[] data, int w, int top, int bandH)
    {
        double sum = 0, weight = 0;
        for (int y = top; y < top + bandH; y++)
        {
            int row = y * w * 4;
            for (int x = 0; x < w; x++)
            {
                byte a = data[row + x * 4 + 3];
                if (a == 0) continue;
                sum += (double)a * x;
                weight += a;
            }
        }
        return weight > 0 ? (int)Math.Round(sum / weight) : w / 2;
    }

    /// <summary>The class color: the saturation-weighted CIRCULAR mean hue of the sprite's colorful
    /// opaque pixels (a linear mean of hue would send a red character to cyan by averaging 0.02 and
    /// 0.98). Null when the art is too grey/small to have an opinion — caller picks a slot hue.</summary>
    private static float? DominantHue(byte[] data, int w, int h)
    {
        const int Step = 4;
        const int MinSamples = 200;
        byte cut = (byte)(AlphaThreshold * 255f);
        double x = 0, y = 0;
        int n = 0;
        for (int py = 0; py < h; py += Step)
        {
            int row = py * w * 4;
            for (int px = 0; px < w; px += Step)
            {
                int i = row + px * 4;
                if (data[i + 3] <= cut) continue;
                var c = new Color(data[i] / 255f, data[i + 1] / 255f, data[i + 2] / 255f);
                float s = c.S;
                if (s <= 0.35f || c.V <= 0.2f) continue;
                double ang = c.H * Math.Tau;
                x += s * Math.Cos(ang);
                y += s * Math.Sin(ang);
                n++;
            }
        }
        if (n < MinSamples || (x == 0 && y == 0)) return null;
        double hue = Math.Atan2(y, x) / Math.Tau;
        if (hue < 0) hue += 1.0;
        return (float)hue;
    }

    /// <summary>Opaque vertical gradient in the class hue, light at the top and darker at the bottom —
    /// the same shape as the shipped "?" card, so a mixed row of cards reads as one set.</summary>
    private static Image BuildGradient(int w, int h, float hue)
    {
        var img = Image.CreateEmpty(w, h, false, Image.Format.Rgba8);
        for (int y = 0; y < h; y++)
        {
            float t = h > 1 ? (float)y / (h - 1) : 0f;
            var c = Color.FromHsv(hue, Mathf.Lerp(0.45f, 0.55f, t), Mathf.Lerp(0.95f, 0.62f, t));
            img.FillRect(new Rect2I(0, y, w, 1), c);
        }
        return img;
    }

    private static void Save(int k, Image card)
    {
        string dir = $"user://forged/characters/{k:00}";
        if (!DirAccess.DirExistsAbsolute(dir)) DirAccess.MakeDirRecursiveAbsolute(dir);
        var err = card.SavePng(PortraitPath(k));
        if (err != Error.Ok)
            MainFile.Logger.Warn($"[ForgedPortrait] could not cache portrait for class {k:00}: {err}");
    }
}

/// <summary>
/// Swap the derived portrait onto a forged class's select button. Postfixes every vanilla assignment of
/// <c>_icon.Texture</c> that can show the unlocked icon: <c>Init</c> (screen build) plus <c>DebugUnlock</c>
/// and <c>UnlockIfPossible</c> (which re-read <c>CharacterSelectIcon</c> after unlocking). The hover
/// glow copies <c>_icon.Texture</c> at hover time, so it picks the portrait up for free. Locked buttons
/// are left alone, and a slot with no portrait keeps the shipped "?" card.
/// </summary>
[HarmonyPatch(typeof(NCharacterSelectButton))]
internal static class ForgedPortraitIconPatch
{
    [HarmonyPostfix]
    [HarmonyPatch(nameof(NCharacterSelectButton.Init))]
    private static void AfterInit(NCharacterSelectButton __instance, CharacterModel character)
        => Apply(__instance, character);

    [HarmonyPostfix]
    [HarmonyPatch(nameof(NCharacterSelectButton.DebugUnlock))]
    private static void AfterDebugUnlock(NCharacterSelectButton __instance)
        => Apply(__instance, __instance._character);

    [HarmonyPostfix]
    [HarmonyPatch(nameof(NCharacterSelectButton.UnlockIfPossible))]
    private static void AfterUnlockIfPossible(NCharacterSelectButton __instance)
        => Apply(__instance, __instance._character);

    private static void Apply(NCharacterSelectButton button, CharacterModel? character)
    {
        try
        {
            if (character is not IForgedCharacterSlot fs) return;
            // Still locked → vanilla just set the padlock icon; overwriting it would leak the art.
            if (button._isLocked || button._icon == null) return;
            var tex = ForgedPortrait.TryGetTexture(fs.ClassSlot);
            if (tex == null) return;
            button._icon.Texture = tex;
        }
        catch (Exception e)
        {
            MainFile.Logger.Warn($"[ForgedPortrait] select icon swap failed: {e.Message}");
        }
    }
}
