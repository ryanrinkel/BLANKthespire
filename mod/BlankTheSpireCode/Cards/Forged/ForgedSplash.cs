using System;
using Godot;
using HarmonyLib;
using MegaCrit.Sts2.Core.Models;
using MegaCrit.Sts2.Core.Nodes.Screens.CharacterSelect;

namespace BlankTheSpire.BlankTheSpireCode.Cards.Forged;

/// <summary>
/// Track 2/3 splash art on the mod side: fetch a forged class's generated splash (the web embeds a
/// <c>splash_url</c> in the import code) into the class's user-data dir on import, and show it as the
/// character-select BACKGROUND. Display reuses the vanilla <c>_bgContainer</c> (a Control BaseLib also
/// injects into) — a runtime <see cref="TextureRect"/>, no .tscn. Everything here is best-effort: a
/// missing/failed splash just leaves the Track 1 "?" placeholder, never blocking import or select.
/// </summary>
public interface IForgedCharacterSlot
{
    /// <summary>1-based class slot of this forged character (so the splash patch maps a CharacterModel
    /// back to its slot without parsing the type name).</summary>
    int ClassSlot { get; }
}

public static class ForgedSplash
{
    private const string Root = "user://forged/characters";

    public static string SplashPath(int k) => $"{Root}/{k:00}/splash.png";

    /// <summary>On import, fetch the class's generated art if the decoded bundle carried URLs for it:
    /// <c>splash_url</c> (select-screen background) and/or <c>sprite_url</c> (standing combat model,
    /// consumed by <see cref="ForgedSprite"/>). Synchronous + best-effort (the import already blocks on
    /// file IO); never throws.</summary>
    public static void TryCacheFromBundle(string bundleJson, int classSlot)
    {
        try
        {
            var parser = new Json();
            if (parser.Parse(bundleJson) != Error.Ok || parser.Data.VariantType != Variant.Type.Dictionary) return;
            var d = parser.Data.AsGodotDictionary();
            CacheKey(d, "splash_url", classSlot, "splash.png");
            CacheKey(d, "sprite_url", classSlot, "sprite.png");
            CacheKey(d, "relic_icon_url", classSlot, "relic.png");
            // A re-import may have replaced relic.png; drop the slot's taken-over texture so it reloads.
            Powers.ForgedRelicIcon.Invalidate(classSlot);
        }
        catch (Exception e)
        {
            MainFile.Logger.Warn($"[ForgedSplash] cache skipped for class {classSlot:00}: {e.Message}");
        }
    }

    private static void CacheKey(Godot.Collections.Dictionary d, string key, int k, string fileName)
    {
        if (!d.ContainsKey(key)) return;
        string url = d[key].AsString().Trim();
        if (url.Length == 0) return;
        CacheFromUrl(k, url, fileName);
    }

    private static void CacheFromUrl(int k, string url, string fileName)
    {
        try
        {
            using var http = new System.Net.Http.HttpClient { Timeout = TimeSpan.FromSeconds(15) };
            byte[] bytes = http.GetByteArrayAsync(url).GetAwaiter().GetResult();
            if (bytes is not { Length: > 0 })
            {
                MainFile.Logger.Warn($"[ForgedSplash] empty download from {url}");
                return;
            }
            string dir = $"{Root}/{k:00}";
            if (!DirAccess.DirExistsAbsolute(dir)) DirAccess.MakeDirRecursiveAbsolute(dir);
            string path = $"{dir}/{fileName}";
            using var f = Godot.FileAccess.Open(path, Godot.FileAccess.ModeFlags.Write);
            if (f == null)
            {
                MainFile.Logger.Warn($"[ForgedSplash] cannot write {path}: {Godot.FileAccess.GetOpenError()}");
                return;
            }
            f.StoreBuffer(bytes);
            MainFile.Logger.Info($"[ForgedSplash] cached {fileName} for class {k:00} ({bytes.Length} bytes) from {url}.");
        }
        catch (Exception e)
        {
            MainFile.Logger.Warn($"[ForgedSplash] download failed for class {k:00} ({url}): {e.Message}");
        }
    }

    /// <summary>Load the cached splash as a texture, or null if there is none / it can't be read.</summary>
    public static ImageTexture? LoadTexture(int k)
    {
        try
        {
            string path = SplashPath(k);
            if (!Godot.FileAccess.FileExists(path)) return null;
            using var f = Godot.FileAccess.Open(path, Godot.FileAccess.ModeFlags.Read);
            if (f == null) return null;
            byte[] buf = f.GetBuffer((long)f.GetLength());
            var img = new Image();
            if (img.LoadPngFromBuffer(buf) != Error.Ok) return null;
            return ImageTexture.CreateFromImage(img);
        }
        catch (Exception e)
        {
            MainFile.Logger.Warn($"[ForgedSplash] load failed for class {k:00}: {e.Message}");
            return null;
        }
    }
}

/// <summary>
/// Show a forged class's cached splash as the character-select BACKGROUND. Postfix on the vanilla
/// SelectCharacter (called when a character is highlighted): overlays our own TextureRect into the
/// vanilla background container. Manages ONLY its own overlay node (removed when any other character is
/// selected) so it never disturbs vanilla nodes. No splash cached → no-op → the Track 1 "?" stands.
/// </summary>
[HarmonyPatch(typeof(NCharacterSelectScreen), nameof(NCharacterSelectScreen.SelectCharacter))]
internal static class ForgedSplashBgPatch
{
    private const string OverlayName = "forged_splash_bg";

    [HarmonyPostfix]
    private static void Postfix(NCharacterSelectScreen __instance, CharacterModel characterModel)
    {
        try
        {
            Control bg = __instance._bgContainer;
            if (bg == null) return;

            // Always clear our previous overlay first (covers switching to a non-forged character too).
            var old = bg.GetNodeOrNull(OverlayName);
            if (old != null)
            {
                bg.RemoveChild(old);
                old.QueueFree();
            }

            if (characterModel is not IForgedCharacterSlot fs) return;
            var tex = ForgedSplash.LoadTexture(fs.ClassSlot);
            if (tex == null) return;

            var rect = new TextureRect
            {
                Name = OverlayName,
                Texture = tex,
                ExpandMode = TextureRect.ExpandModeEnum.IgnoreSize,
                StretchMode = TextureRect.StretchModeEnum.KeepAspectCovered,
                MouseFilter = Control.MouseFilterEnum.Ignore,
            };
            rect.SetAnchorsPreset(Control.LayoutPreset.FullRect);
            bg.AddChild(rect);
        }
        catch (Exception e)
        {
            MainFile.Logger.Warn($"[ForgedSplash] bg overlay failed: {e.Message}");
        }
    }
}
