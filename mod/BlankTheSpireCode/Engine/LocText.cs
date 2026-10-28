namespace BlankTheSpire.BlankTheSpireCode.Engine;

/// <summary>
/// i18n (I18N_PLAN C2, "Bundle loc schema"): one locale's translated creative strings for a bundle entry. For a card,
/// <see cref="Name"/> is its title and <see cref="Description"/> its flavor (the rules text is never translated by the
/// bundle; the mod renders it through <see cref="ForgedText"/>). For a character / relic / potion / status / summon / orb
/// it is the name and description. Either may be null (= fall back to the English string).
/// </summary>
public sealed record LocText(string? Name, string? Description);

public static class LocTextExtensions
{
    /// <summary>The translated name for <paramref name="lang"/>, or null (absent / English / blank).</summary>
    public static string? LocName(this IReadOnlyDictionary<string, LocText>? loc, string lang) =>
        loc != null && lang != "eng" && loc.TryGetValue(lang, out var t) && !string.IsNullOrWhiteSpace(t.Name) ? t.Name : null;

    /// <summary>The translated description for <paramref name="lang"/>, or null (absent / English / blank).</summary>
    public static string? LocDescription(this IReadOnlyDictionary<string, LocText>? loc, string lang) =>
        loc != null && lang != "eng" && loc.TryGetValue(lang, out var t) && !string.IsNullOrWhiteSpace(t.Description) ? t.Description : null;
}
