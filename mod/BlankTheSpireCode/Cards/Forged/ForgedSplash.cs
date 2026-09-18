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

    /// <summary>Per-image downloads (splash/sprite/relic icon) are ~0.5 MB.</summary>
    private const int ImageTimeoutSeconds = 15;

    /// <summary>The per-class card-art archive is ~5 MB — the same 15 s budget times out on a slow line.</summary>
    private const int CardArtTimeoutSeconds = 60;

    public static string SplashPath(int k) => $"{Root}/{k:00}/splash.png";

    /// <summary>On import, fetch the class's generated art if the decoded bundle carried URLs for it:
    /// <c>splash_url</c> (select-screen background), <c>sprite_url</c> (standing combat model, consumed by
    /// <see cref="ForgedSprite"/>), <c>relic_icon_url</c>, and <c>card_art_url</c> (one <c>cards.zip</c> of
    /// per-card portraits, consumed by <see cref="ForgedCardArt"/>). Every key is optional and
    /// ignored-if-absent, so no codec/vocab bump is needed to add one. Synchronous + best-effort (the
    /// import already blocks on file IO); never throws.</summary>
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
            CacheCardArt(d, classSlot);
            // A re-import may have replaced relic.png; drop the slot's taken-over texture so it reloads.
            Powers.ForgedRelicIcon.Invalidate(classSlot);
            // Likewise sprite.png: the select card is derived from it, so drop the stale portrait.png.
            ForgedPortrait.Invalidate(classSlot);
            // And the per-card portraits, whose textures are taken-over the same way.
            ForgedCardArt.Invalidate(classSlot);
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

    /// <summary>Fetch <c>card_art_url</c> — ONE <c>cards.zip</c> holding the class's per-card portraits
    /// (~5 MB, so a longer timeout than the single-image keys) — and unpack it into the class's
    /// <c>cards/</c> dir. Optional and ignored-if-absent exactly like <c>splash_url</c>: old codes carry no
    /// such key, a partial zip is fine (missing cards keep the per-type doodle), and nothing here can fail
    /// the import.</summary>
    private static void CacheCardArt(Godot.Collections.Dictionary d, int k)
    {
        if (!d.ContainsKey("card_art_url")) return;
        string url = d["card_art_url"].AsString().Trim();
        if (url.Length == 0) return;

        byte[]? bytes = Download(url, CardArtTimeoutSeconds);
        if (bytes == null) return;

        // Stage the archive next to the class dir: Godot's ZipReader opens a PATH, not a buffer.
        string dir = $"{Root}/{k:00}";
        if (!DirAccess.DirExistsAbsolute(dir)) DirAccess.MakeDirRecursiveAbsolute(dir);
        string zipPath = $"{dir}/cards.zip";
        using (var zf = Godot.FileAccess.Open(zipPath, Godot.FileAccess.ModeFlags.Write))
        {
            if (zf == null)
            {
                MainFile.Logger.Warn($"[ForgedCardArt] cannot write {zipPath}: {Godot.FileAccess.GetOpenError()}");
                return;
            }
            zf.StoreBuffer(bytes);
        }

        try { Unpack(zipPath, k, bytes.Length, url); }
        finally { if (Godot.FileAccess.FileExists(zipPath)) DirAccess.RemoveAbsolute(zipPath); }
    }

    private static void Unpack(string zipPath, int k, int downloadedBytes, string url)
    {
        string cardsDir = ForgedCardArt.CardsDir(k);
        if (!DirAccess.DirExistsAbsolute(cardsDir)) DirAccess.MakeDirRecursiveAbsolute(cardsDir);

        // Clear the class's STALE ART only. This dir is shared with the class's NN.json card files (which
        // the importer has just written, and which are the class itself) — a blanket wipe here would delete
        // the freshly imported class, so the sweep is restricted to .png.
        using (var dir = DirAccess.Open(cardsDir))
            if (dir != null)
                foreach (var fn in dir.GetFiles())
                    if (fn.EndsWith(".png", StringComparison.OrdinalIgnoreCase))
                        DirAccess.RemoveAbsolute($"{cardsDir}/{fn}");

        using var zip = new ZipReader();
        var err = zip.Open(zipPath);
        if (err != Error.Ok)
        {
            MainFile.Logger.Warn($"[ForgedCardArt] class {k:00}: cards.zip from {url} is not a readable archive ({err}).");
            return;
        }

        int written = 0, entries = 0;
        foreach (string entry in zip.GetFiles())
        {
            if (entry.EndsWith("/", StringComparison.Ordinal)) continue;
            entries++;
            if (!entry.EndsWith(".png", StringComparison.OrdinalIgnoreCase)) continue;
            // Flatten: the zip is a flat <card_id>.png bag, but never trust a path from a downloaded
            // archive (zip-slip) — keep the leaf name only.
            int cut = entry.LastIndexOfAny(new[] { '/', '\\' });
            string name = cut >= 0 ? entry[(cut + 1)..] : entry;
            if (name.Length == 0 || name.Contains("..", StringComparison.Ordinal)) continue;

            byte[] data = zip.ReadFile(entry);
            if (data is not { Length: > 0 }) continue;
            using var f = Godot.FileAccess.Open($"{cardsDir}/{name}", Godot.FileAccess.ModeFlags.Write);
            if (f == null)
            {
                MainFile.Logger.Warn($"[ForgedCardArt] cannot write {cardsDir}/{name}: {Godot.FileAccess.GetOpenError()}");
                continue;
            }
            f.StoreBuffer(data);
            written++;
        }
        zip.Close();
        MainFile.Logger.Info($"[ForgedCardArt] class {k:00}: unpacked {written}/{entries} card portraits from cards.zip ({downloadedBytes} bytes) from {url}.");
    }

    /// <summary>Best-effort GET; null on any failure (already logged).</summary>
    private static byte[]? Download(string url, int timeoutSeconds)
    {
        try
        {
            using var http = new System.Net.Http.HttpClient { Timeout = TimeSpan.FromSeconds(timeoutSeconds) };
            byte[] bytes = http.GetByteArrayAsync(url).GetAwaiter().GetResult();
            if (bytes is not { Length: > 0 })
            {
                MainFile.Logger.Warn($"[ForgedSplash] empty download from {url}");
                return null;
            }
            return bytes;
        }
        catch (Exception e)
        {
            MainFile.Logger.Warn($"[ForgedSplash] download failed ({url}): {e.Message}");
            return null;
        }
    }

    private static void CacheFromUrl(int k, string url, string fileName)
    {
        try
        {
            byte[]? bytes = Download(url, ImageTimeoutSeconds);
            if (bytes == null) return;
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

            // The gpt-image sizes are 3:2 but the select screen is ~16:9, so a plain
            // KeepAspectCovered fill cropped ~9% off the top AND bottom — characters with tight
            // headroom lost their heads. Show the WHOLE splash instead: a contained (letterboxed)
            // foreground over a dimmed cover-stretched copy of itself, so the spill areas read as
            // matching ambience rather than black bars (and nothing of the art is ever cropped).
            var wrap = new Control { Name = OverlayName, MouseFilter = Control.MouseFilterEnum.Ignore };
            wrap.SetAnchorsPreset(Control.LayoutPreset.FullRect);

            var ambience = new TextureRect
            {
                Texture = tex,
                ExpandMode = TextureRect.ExpandModeEnum.IgnoreSize,
                StretchMode = TextureRect.StretchModeEnum.KeepAspectCovered,
                MouseFilter = Control.MouseFilterEnum.Ignore,
                Modulate = new Color(0.30f, 0.30f, 0.34f),
            };
            ambience.SetAnchorsPreset(Control.LayoutPreset.FullRect);
            wrap.AddChild(ambience);

            var art = new TextureRect
            {
                Texture = tex,
                ExpandMode = TextureRect.ExpandModeEnum.IgnoreSize,
                StretchMode = TextureRect.StretchModeEnum.KeepAspectCentered,
                MouseFilter = Control.MouseFilterEnum.Ignore,
            };
            art.SetAnchorsPreset(Control.LayoutPreset.FullRect);
            wrap.AddChild(art);

            bg.AddChild(wrap);
        }
        catch (Exception e)
        {
            MainFile.Logger.Warn($"[ForgedSplash] bg overlay failed: {e.Message}");
        }
    }
}
