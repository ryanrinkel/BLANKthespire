using System;
using System.Collections.Generic;
using Godot;

namespace BlankTheSpire.BlankTheSpireCode.Powers;

/// <summary>
/// Custom relic icon for forged classes: the web layer renders the relic's harness-picked emoji to a
/// small PNG and embeds a <c>relic_icon_url</c> in the import bundle; import caches it at
/// <c>user://forged/characters/KK/relic.png</c> (see ForgedSplash.TryCacheFromBundle). RelicModel's
/// icon surface is PATH-based (ResourceLoader.Load with CacheMode.Reuse), so a runtime PNG can't ride
/// a real file path — instead the loaded ImageTexture is registered into Godot's resource cache under
/// a synthetic res:// path via <see cref="Resource.TakeOverPath"/>, which both ResourceLoader.Load and
/// AssetCache/ResourceLoader.Exists then resolve from cache. Best-effort: no icon → null → callers
/// keep the shipped fallback relic.png.
/// </summary>
public static class ForgedRelicIcon
{
    public static string IconPath(int k) => $"user://forged/characters/{k:00}/relic.png";

    /// <summary>Per-slot resolved synthetic paths (icon, outline), or null when no cached icon. Emptied
    /// by <see cref="Invalidate"/> when an import rewrites the slot.</summary>
    private static readonly Dictionary<int, (string Icon, string Outline)?> _resolved = new();

    /// <summary>Synthetic res:// path for class <paramref name="k"/>'s emoji icon, or null.</summary>
    public static string? TryGetPath(int k) => Resolve(k)?.Icon;

    /// <summary>White-silhouette variant (the hover/highlight outline the relic UI layers on), or null.</summary>
    public static string? TryGetOutlinePath(int k) => Resolve(k)?.Outline;

    /// <summary>Forget a slot's cached takeover so a re-import (new relic.png) is picked up.</summary>
    public static void Invalidate(int k) => _resolved.Remove(k);

    private static (string Icon, string Outline)? Resolve(int k)
    {
        if (_resolved.TryGetValue(k, out var cached)) return cached;
        (string, string)? result = null;
        try
        {
            string path = IconPath(k);
            if (Godot.FileAccess.FileExists(path))
            {
                using var f = Godot.FileAccess.Open(path, Godot.FileAccess.ModeFlags.Read);
                var img = new Image();
                if (f != null && img.LoadPngFromBuffer(f.GetBuffer((long)f.GetLength())) == Error.Ok)
                {
                    if (img.GetFormat() != Image.Format.Rgba8) img.Convert(Image.Format.Rgba8);
                    string iconPath = $"res://BlankTheSpire/images/relics/forged_relic_{k:00}_live.png";
                    string outlinePath = $"res://BlankTheSpire/images/relics/forged_relic_{k:00}_outline_live.png";
                    ImageTexture.CreateFromImage(img).TakeOverPath(iconPath);
                    ImageTexture.CreateFromImage(Silhouette(img)).TakeOverPath(outlinePath);
                    result = (iconPath, outlinePath);
                    MainFile.Logger.Info($"[ForgedRelicIcon] emoji icon live for class {k:00}.");
                }
            }
        }
        catch (Exception e)
        {
            MainFile.Logger.Warn($"[ForgedRelicIcon] icon for class {k:00} failed, using fallback: {e.Message}");
        }
        _resolved[k] = result;
        return result;
    }

    /// <summary>The icon's alpha shape filled white — what the game expects of a relic _outline sprite.</summary>
    private static Image Silhouette(Image src)
    {
        var img = (Image)src.Duplicate();
        for (int y = 0; y < img.GetHeight(); y++)
            for (int x = 0; x < img.GetWidth(); x++)
            {
                float a = img.GetPixel(x, y).A;
                if (a > 0f) img.SetPixel(x, y, new Color(1f, 1f, 1f, a));
            }
        return img;
    }
}
