using System;
using System.Collections.Generic;
using System.Text;
using BlankTheSpire.BlankTheSpireCode.Engine;
using Godot;

namespace BlankTheSpire.BlankTheSpireCode.Cards.Forged;

/// <summary>
/// Per-CARD art for forged classes. The web layer renders one PNG per card and ships them as ONE
/// <c>cards.zip</c> per class (a <c>card_art_url</c> in the import bundle); import unpacks it into
/// <c>user://forged/characters/KK/cards/&lt;card_id&gt;.png</c> — see
/// <see cref="ForgedSplash.TryCacheFromBundle"/>. This class turns those files into the texture BaseLib
/// hands the game.
///
/// Delivery is BaseLib's <c>CustomCardModel.CustomPortrait</c> (a <see cref="Texture2D"/>), which its
/// Harmony prefixes on <c>CardModel.Portrait</c> and <c>CardModel.PortraitPath</c> check BEFORE
/// <c>CustomPortraitPath</c> (verified against BaseLib 3.2.1: <c>BaseLib.Abstracts.CustomCardPortrait</c> /
/// <c>CustomCardPortraitPath</c>). <c>CardModel.Portrait</c> is NON-virtual, so that prefix is
/// authoritative for every <see cref="DataCard"/>, and vanilla's <c>NCard</c> assigns
/// <c>Model.Portrait</c> straight into its %Portrait TextureRect — one file serves the in-hand card and
/// the zoomed card alike. The PortraitPath prefix instead reads <c>CustomPortrait.ResourcePath</c>, which
/// is EMPTY for a runtime <see cref="ImageTexture"/>, so every texture is also parked under a synthetic
/// <c>res://</c> path via <see cref="Resource.TakeOverPath"/> (the same trick as
/// <see cref="Powers.ForgedRelicIcon"/>).
///
/// The cache holds STRONG refs, and caches NEGATIVES too: Godot's resource cache keeps taken-over
/// resources only WEAKLY (the invisible-relic bug — see ForgedRelicIcon's note), and a null entry keeps a
/// card with no art from hitting the disk every time the hand is redrawn. A PARTIAL zip is normal: a card
/// with no PNG falls back to <see cref="DataCard"/>'s per-type doodle.
/// </summary>
public static class ForgedCardArt
{
    /// <summary>Where a class's per-card PNGs live (shared with its <c>NN.json</c> card files — the
    /// extensions never collide, and <c>ForgedCharacters.DeleteClass</c> already clears the whole dir).</summary>
    public static string CardsDir(int k) => $"user://forged/characters/{k:00}/cards";

    /// <summary>The cached art file for one card id (whether or not it exists).</summary>
    public static string CardArtPath(int k, string cardId) => $"{CardsDir(k)}/{Sanitize(cardId)}.png";

    /// <summary>Resolved per (class, card id): the live texture, or null when this card ships no art.
    /// Strong refs on purpose (see the class remarks).</summary>
    private static readonly Dictionary<(int Class, string Card), ImageTexture?> _cache = new();

    /// <summary>Classes whose "N/M card portraits live" line has already been logged this launch.</summary>
    private static readonly HashSet<int> _reported = new();

    /// <summary>The card's generated portrait, or null when there is none (caller keeps the type doodle).
    /// Cached both ways; never throws.</summary>
    public static Texture2D? TryGetTexture(int classSlot, string? cardId)
    {
        if (classSlot < 1 || string.IsNullOrWhiteSpace(cardId)) return null;
        var key = (classSlot, cardId!);
        if (_cache.TryGetValue(key, out var cached)) return cached;

        ImageTexture? result = null;
        try
        {
            result = Load(classSlot, cardId!);
        }
        catch (Exception e)
        {
            MainFile.Logger.Warn($"[ForgedCardArt] class {classSlot:00} card '{cardId}' failed, using the type doodle: {e.Message}");
        }
        _cache[key] = result;

        // One summary line the first time this class asks for any card's art (the smoke gate).
        if (_reported.Add(classSlot)) Report(classSlot);
        return result;
    }

    /// <summary>Drop a class's resolved art (and its summary line) so a re-import picks up the new zip.
    /// Called from <see cref="ForgedSplash.TryCacheFromBundle"/> like <c>ForgedPortrait.Invalidate</c>.</summary>
    public static void Invalidate(int classSlot)
    {
        var drop = new List<(int, string)>();
        foreach (var key in _cache.Keys)
            if (key.Class == classSlot) drop.Add(key);
        foreach (var key in drop) _cache.Remove(key);
        _reported.Remove(classSlot);
    }

    /// <summary>Log "N/M card portraits live" for a class: M = its filled card slots, N = those with a
    /// cached PNG. Best-effort telemetry — never throws, never affects what is shown.</summary>
    public static void Report(int classSlot)
    {
        try
        {
            int filled = 0, live = 0;
            for (int n = 1; n <= ForgedCharacters.CardsPerClass; n++)
            {
                var spec = ForgedCharacters.CardSpecFor(classSlot, n);
                if (spec.IsEmpty) continue;
                filled++;
                if (Godot.FileAccess.FileExists(CardArtPath(classSlot, spec.Id))) live++;
            }
            MainFile.Logger.Info($"[ForgedCardArt] class {classSlot:00}: {live}/{filled} card portraits live.");
        }
        catch (Exception e)
        {
            MainFile.Logger.Warn($"[ForgedCardArt] class {classSlot:00} report failed: {e.Message}");
        }
    }

    private static ImageTexture? Load(int k, string cardId)
    {
        string path = CardArtPath(k, cardId);
        if (!Godot.FileAccess.FileExists(path)) return null;
        using var f = Godot.FileAccess.Open(path, Godot.FileAccess.ModeFlags.Read);
        if (f == null)
        {
            MainFile.Logger.Warn($"[ForgedCardArt] cannot open {path}: {Godot.FileAccess.GetOpenError()}");
            return null;
        }
        var img = new Image();
        if (img.LoadPngFromBuffer(f.GetBuffer((long)f.GetLength())) != Error.Ok)
        {
            MainFile.Logger.Warn($"[ForgedCardArt] {path} is not a readable PNG; falling back to the type doodle.");
            return null;
        }
        var tex = ImageTexture.CreateFromImage(img);
        // Non-empty ResourcePath for BaseLib's PortraitPath prefix. The mod's shipped portraits live under
        // BlankTheSpire/images/card_portraits/big/, so the synthetic twin sits beside them.
        tex.TakeOverPath($"res://BlankTheSpire/images/card_portraits/big/forged_{k:00}_{Sanitize(cardId)}_live.png");
        return tex;
    }

    /// <summary>Card ids are generator-produced snake_case, but they are user-influenced text that ends up
    /// in a FILE path — keep only path-safe characters so a hostile/odd id can never escape the class dir.</summary>
    private static string Sanitize(string id)
    {
        var sb = new StringBuilder(id.Length);
        foreach (char c in id)
            sb.Append(char.IsAsciiLetterOrDigit(c) || c == '_' || c == '-' ? c : '_');
        return sb.Length == 0 ? "_" : sb.ToString();
    }
}
