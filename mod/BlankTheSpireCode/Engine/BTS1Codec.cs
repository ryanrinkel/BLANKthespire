using System.IO;
using System.IO.Compression;
using System.Text;

namespace BlankTheSpire.BlankTheSpireCode.Engine;

/// <summary>
/// The BTS1 import-code codec (plan §10.3). A code is a self-contained, shareable string that encodes a
/// single forged-card JSON:
/// <code>BTS1.&lt;vocabVersion&gt;.&lt;base64url(gzip(json))&gt;.&lt;crc32&gt;</code>
/// It carries no executable content — just data over the closed vocabulary — so pasting a stranger's code is
/// safe: the importer re-validates every op/status/target against the live EffectRunner (via
/// <see cref="ForgedCards.TryParseCardJson"/>) before writing a slot, and never executes anything from the code.
///
/// The header version lets the mod reject a code that needs newer ops ("update the mod") instead of crashing.
/// The trailing CRC32 (over the raw JSON bytes) catches paste/transport corruption. The Python encoder
/// (generation/btsgen/bts1.py) and the future website MUST stay byte-compatible with this format — the three
/// primitives (gzip, base64url, CRC-32/IEEE) are all standard, so cross-implementation round-trips work.
/// </summary>
public static class BTS1Codec
{
    /// <summary>What a decoded code carries: a single card (<c>BTS1</c>) or a whole class bundle (<c>BTSC</c>).</summary>
    public enum BtsKind { Card, Class }

    private const string CardMagic = "BTS1";   // single forged card
    private const string ClassMagic = "BTSC";  // whole class bundle {kind:"class", character, cards[], relic?}

    /// <summary>Encodes a single card's JSON into a shareable BTS1 code.</summary>
    public static string EncodeCard(string cardJson) => Encode(CardMagic, cardJson);

    /// <summary>Encodes a class-bundle JSON into a shareable BTSC code.</summary>
    public static string EncodeClass(string bundleJson) => Encode(ClassMagic, bundleJson);

    private static string Encode(string magic, string json)
    {
        byte[] jsonBytes = Encoding.UTF8.GetBytes(json);
        string payload = Base64UrlEncode(Gzip(jsonBytes));
        return $"{magic}.{ForgedCards.VocabVersion}.{payload}.{Crc32(jsonBytes):x8}";
    }

    /// <summary>
    /// Decodes a BTS1 (card) or BTSC (class) code back to its JSON, reporting which <paramref name="kind"/> it
    /// is. Returns false with a human-readable <paramref name="error"/> for any malformed/corrupted/too-new
    /// code. Does NOT validate the payload's vocabulary — that's the importer's job (so the two stages report
    /// distinct reasons). Safe by construction: data only, never executed.
    /// </summary>
    public static bool TryDecode(string code, out string json, out BtsKind kind, out string error)
    {
        json = "";
        kind = BtsKind.Card;
        if (string.IsNullOrWhiteSpace(code)) { error = "empty code."; return false; }

        // Strip ALL whitespace — codes shared via chat/forums often get line-wrapped. base64url + '.' separators
        // contain no whitespace, so this is lossless.
        string clean = new string(code.Where(c => !char.IsWhiteSpace(c)).ToArray());

        var parts = clean.Split('.');
        if (parts.Length != 4) { error = "not a BLANK the spire code."; return false; }
        if (parts[0] == CardMagic) kind = BtsKind.Card;
        else if (parts[0] == ClassMagic) kind = BtsKind.Class;
        else { error = "not a BLANK the spire (BTS1/BTSC) code."; return false; }

        if (!int.TryParse(parts[1], out int ver))
        { error = "malformed code (bad version field)."; return false; }
        if (ver > ForgedCards.VocabVersion)
        {
            error = $"this code needs a newer BLANK the spire (code is v{ver}, this mod supports v{ForgedCards.VocabVersion}). Update the mod.";
            return false;
        }

        byte[] jsonBytes;
        try { jsonBytes = Gunzip(Base64UrlDecode(parts[2])); }
        catch (Exception e) { error = $"corrupted code ({e.Message})."; return false; }

        if (Crc32(jsonBytes).ToString("x8") != parts[3].ToLowerInvariant())
        { error = "corrupted code (checksum mismatch — try copying it again)."; return false; }

        json = Encoding.UTF8.GetString(jsonBytes);
        error = "";
        return true;
    }

    // --- gzip ---------------------------------------------------------------
    private static byte[] Gzip(byte[] data)
    {
        using var output = new MemoryStream();
        using (var gz = new GZipStream(output, CompressionLevel.Optimal, leaveOpen: true))
            gz.Write(data, 0, data.Length);
        return output.ToArray();
    }

    private static byte[] Gunzip(byte[] data)
    {
        using var input = new MemoryStream(data);
        using var gz = new GZipStream(input, CompressionMode.Decompress);
        using var output = new MemoryStream();
        gz.CopyTo(output);
        return output.ToArray();
    }

    // --- base64url (RFC 4648 §5, no padding) --------------------------------
    private static string Base64UrlEncode(byte[] b) =>
        Convert.ToBase64String(b).TrimEnd('=').Replace('+', '-').Replace('/', '_');

    private static byte[] Base64UrlDecode(string s)
    {
        s = s.Replace('-', '+').Replace('_', '/');
        s += (s.Length % 4) switch { 2 => "==", 3 => "=", _ => "" };
        return Convert.FromBase64String(s);
    }

    // --- CRC-32/IEEE (polynomial 0xEDB88320) — matches Python zlib.crc32 ----
    private static uint Crc32(byte[] data)
    {
        uint crc = 0xFFFFFFFFu;
        foreach (byte b in data)
        {
            crc ^= b;
            for (int k = 0; k < 8; k++)
                crc = (crc >> 1) ^ (0xEDB88320u & (uint)(-(int)(crc & 1)));
        }
        return ~crc;
    }
}
