using System.Globalization;
using System.Text;
using MegaCrit.Sts2.Core.Localization;

namespace BlankTheSpire.BlankTheSpireCode.Engine;

/// <summary>
/// The mod's keyed text layer (I18N_PLAN section C1): every rules sentence, fragment, tooltip and UI string the mod
/// renders at runtime goes through <see cref="T"/> / <see cref="F"/> with a stable KEY and its ENGLISH text kept inline
/// at the call site. English output is therefore the inline default by construction; a language table only overrides.
///
/// <para><b>Lookup:</b> the active language is <c>LocManager.Instance.Language</c> (the game's 3-letter code, e.g.
/// <c>"eng"</c>, <c>"zhs"</c>), read on every call (the game can swap it, e.g. the English override it uses while
/// uploading metrics) with the table resolved through a one-entry cache. A key missing from the active table falls
/// back to the inline English, per key. Before <c>LocManager</c> exists (mod init) the language is English.</para>
///
/// <para><b>Placeholders:</b> <see cref="F"/> substitutes ONLY the names passed to it (lower-case by convention,
/// e.g. <c>{amount}</c>, <c>{to}</c>). Every other brace group — the game's own dynamic vars such as
/// <c>{Damage}</c>, <c>{Block}</c>, <c>{CalculatedDamage}</c>, <c>{Damage:diff()}</c> — passes through untouched for
/// the game's SmartFormat pass.</para>
///
/// <para><b>Adding a language</b> = adding one file <c>ForgedText.&lt;code&gt;.cs</c> with a
/// <c>Dictionary&lt;string, string&gt;</c> keyed like the calls here, plus one line in <see cref="TableFor"/>. No call
/// site changes. A table may restructure a sentence freely (word order, measure words, markup) as long as it keeps
/// the named placeholders the English passes.</para>
/// </summary>
public static partial class ForgedText
{
    [ThreadStatic] private static string? _forced;
    private static string? _cachedLang;
    private static IReadOnlyDictionary<string, string>? _cachedTable;

    /// <summary>Keys requested in a non-English language that the table did not have (the i18n dump lists them).</summary>
    internal static readonly HashSet<string> MissingKeys = new(StringComparer.Ordinal);

    /// <summary>Every key requested this session (the i18n dump counts them).</summary>
    internal static readonly HashSet<string> SeenKeys = new(StringComparer.Ordinal);

    /// <summary>The active game language code (<c>"eng"</c> before the game's LocManager exists).</summary>
    public static string Lang => _forced ?? LocManager.Instance?.Language ?? "eng";

    /// <summary>True when no override table applies (English output).</summary>
    public static bool IsEnglish => Table() == null;

    /// <summary>The override table for a language code, or null (English / unsupported = inline English).</summary>
    private static IReadOnlyDictionary<string, string>? TableFor(string lang) => lang switch
    {
        "zhs" => Zhs,
        _ => null,
    };

    /// <summary>Render with <paramref name="lang"/> for the scope of the returned handle (e.g. the spec-time English
    /// description, which must not depend on when the card happened to be parsed).</summary>
    public static IDisposable Force(string lang)
    {
        var prev = _forced;
        _forced = lang;
        return new Restore(() => _forced = prev);
    }

    [ThreadStatic] private static int _classScope;

    /// <summary>The forged class (1-based) whose creative names (custom orbs / statuses / summons / card titles) the text
    /// being rendered should use from the bundle's <c>loc</c> block, or 0 (none: the English names).</summary>
    public static int ClassScope => _classScope;

    /// <summary>Render for class <paramref name="k"/> for the scope of the returned handle (see <see cref="ClassScope"/>).</summary>
    public static IDisposable InClass(int k)
    {
        int prev = _classScope;
        _classScope = k;
        return new Restore(() => _classScope = prev);
    }

    private sealed class Restore(Action undo) : IDisposable
    {
        public void Dispose() => undo();
    }

    private static IReadOnlyDictionary<string, string>? Table()
    {
        string lang = Lang;
        if (!string.Equals(lang, _cachedLang, StringComparison.Ordinal))
        {
            _cachedTable = TableFor(lang);
            _cachedLang = lang;
        }
        return _cachedTable;
    }

    /// <summary>Does the active language override <paramref name="key"/>?</summary>
    public static bool Has(string key) => Table()?.ContainsKey(key) == true;

    /// <summary>The text for <paramref name="key"/> in the active language, else <paramref name="en"/>.</summary>
    public static string T(string key, string en)
    {
        SeenKeys.Add(key);
        var table = Table();
        if (table == null) return en;
        if (table.TryGetValue(key, out var s)) return s;
        MissingKeys.Add(key);
        return en;
    }

    /// <summary><see cref="T"/> with named placeholders filled (<c>{name}</c> for each pair; nothing else touched).</summary>
    public static string F(string key, string en, params (string Name, object? Value)[] args) => Fill(T(key, en), args);

    /// <summary>Replace <c>{name}</c> for exactly the given names. Unknown brace groups (the game's dynamic vars,
    /// including any <c>{Var:format()}</c> form) are copied through verbatim.</summary>
    public static string Fill(string template, params (string Name, object? Value)[] args)
    {
        if (args.Length == 0 || template.IndexOf('{') < 0) return template;
        var sb = new StringBuilder(template.Length + 16);
        int i = 0;
        while (i < template.Length)
        {
            char c = template[i];
            if (c == '{')
            {
                int close = template.IndexOf('}', i + 1);
                if (close > i)
                {
                    string name = template.Substring(i + 1, close - i - 1);
                    bool hit = false;
                    foreach (var (n, v) in args)
                    {
                        if (!string.Equals(n, name, StringComparison.Ordinal)) continue;
                        sb.Append(v switch
                        {
                            null => "",
                            string s => s,
                            IFormattable fmt => fmt.ToString(null, CultureInfo.InvariantCulture),
                            _ => v.ToString(),
                        });
                        hit = true;
                        break;
                    }
                    if (hit) { i = close + 1; continue; }
                }
            }
            sb.Append(c);
            i++;
        }
        return sb.ToString();
    }
}
