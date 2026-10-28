using System;
using System.Collections.Generic;
using System.Linq;
using System.Text;
using BlankTheSpire.BlankTheSpireCode.Engine;
using BlankTheSpire.BlankTheSpireCode.Powers;
using HarmonyLib;
using MegaCrit.Sts2.Core.Entities.Cards;
using MegaCrit.Sts2.Core.Localization;
using MegaCrit.Sts2.Core.Models;

namespace BlankTheSpire.BlankTheSpireCode.Testing;

/// <summary>
/// i18n regression dump (I18N_PLAN phase 2). Writes every string the mod renders for the staged forged classes to
/// <c>user://logs/bts_describe_&lt;lang&gt;.txt</c> (next to godot.log), so an English run before and after a text
/// refactor can be diffed byte-for-byte, and a Chinese run can be scanned for English leaks.
///
/// WHEN: once per launch, at the main menu (<see cref="AutoSlaySmokeHook"/>'s CheckCommandLineArgs postfix, i.e. after
/// ModelDb.Init injected the in-code localization), whenever an AutoSlay smoke request is present, or whenever the
/// env var <c>BTS_DESCRIBE_DUMP</c> is set (a manual, non-Steam launch). Normal play never writes it.
///
/// WHAT (one line per string, newlines escaped as \n, sorted so two runs diff cleanly):
///   1. every <c>BLANKTHESPIRE</c> key of every loaded loc table (own keys + the eng fallback's), raw text: card
///      titles/descriptions/picker prompts, relic/potion/orb/power/status/summon/character text, settings labels;
///   2. every filled forged card's FORMATTED description (the game's SmartFormat pass, so a bad dynamic var shows up
///      as a "Localization formatting error" in godot.log) and its upgrade preview;
///   3. an optional offline corpus: every <c>user://bts_describe_corpus/*.json</c> (a card JSON or a class bundle) is
///      parsed WITHOUT being registered and its synthesized text printed (card + upgrade text, every trigger
///      sentence, custom status / orb / summon blurbs). This widens the regression net past the staged classes.
/// </summary>
internal static class DescribeDump
{
    private const string EnvFlag = "BTS_DESCRIBE_DUMP";
    private const string CorpusDir = "user://bts_describe_corpus";
    private static bool _written;

    internal static bool EnvRequested => !string.IsNullOrWhiteSpace(Environment.GetEnvironmentVariable(EnvFlag));

    internal static void WriteOnce(string reason)
    {
        if (_written) return;
        _written = true;
        try { Write(reason); }
        catch (Exception e) { MainFile.Logger.Error($"[i18n] describe dump failed: {e}"); }
    }

    private static string Esc(string? s) => (s ?? "<null>").Replace("\r", "\\r").Replace("\n", "\\n");

    private static void Write(string reason)
    {
        string lang = LocManager.Instance?.Language ?? "unknown";
        var sb = new StringBuilder();
        sb.Append("# bts describe dump; lang=").Append(lang).Append('\n');

        // --- 1. loc tables ------------------------------------------------------------------------------------
        var tablesField = AccessTools.Field(typeof(LocManager), "_tables");
        var fallbackField = AccessTools.Field(typeof(LocTable), "_fallback");
        if (LocManager.Instance != null && tablesField?.GetValue(LocManager.Instance) is Dictionary<string, LocTable> tables)
        {
            foreach (var name in tables.Keys.OrderBy(k => k, StringComparer.Ordinal))
            {
                var t = tables[name];
                var keys = new HashSet<string>(t.Keys, StringComparer.Ordinal);
                if (fallbackField?.GetValue(t) is LocTable fb) keys.UnionWith(fb.Keys);
                foreach (var key in keys.Where(k => k.Contains("BLANKTHESPIRE", StringComparison.OrdinalIgnoreCase))
                                        .OrderBy(k => k, StringComparer.Ordinal))
                    sb.Append('[').Append(name).Append("] ").Append(key).Append(" = ").Append(Esc(t.GetRawText(key))).Append('\n');
            }
        }

        // --- 2. formatted forged cards ------------------------------------------------------------------------
        var contentField = AccessTools.Field(typeof(ModelDb), "_contentById");
        if (contentField?.GetValue(null) is System.Collections.IDictionary content)
        {
            var cards = new List<(string Id, CardModel Card)>();
            foreach (System.Collections.DictionaryEntry kv in content)
                if (kv.Value is DataCard dc && dc.Localization != null) cards.Add((kv.Key.ToString() ?? "", dc));
            foreach (var (id, card) in cards.OrderBy(c => c.Id, StringComparer.Ordinal))
            {
                sb.Append("[fmt] ").Append(id).Append(" title = ").Append(Esc(Try(() => card.Title))).Append('\n');
                sb.Append("[fmt] ").Append(id).Append(" desc = ").Append(Esc(Try(() => card.GetDescriptionForPile(PileType.None)))).Append('\n');
                sb.Append("[fmt] ").Append(id).Append(" upgrade = ").Append(Esc(Try(() => card.GetDescriptionForUpgradePreview()))).Append('\n');
            }
        }

        // --- 3. offline corpus ----------------------------------------------------------------------------------
        if (Godot.DirAccess.DirExistsAbsolute(CorpusDir))
        {
            using var dir = Godot.DirAccess.Open(CorpusDir);
            var files = dir?.GetFiles().Where(f => f.EndsWith(".json")).OrderBy(f => f, StringComparer.Ordinal).ToArray() ?? [];
            foreach (var fn in files)
            {
                string json;
                using (var f = Godot.FileAccess.Open($"{CorpusDir}/{fn}", Godot.FileAccess.ModeFlags.Read))
                    json = f?.GetAsText() ?? "";
                DumpCorpusFile(sb, fn, json);
            }
        }

        string path = Godot.ProjectSettings.GlobalizePath($"user://logs/bts_describe_{lang}.txt");
        System.IO.File.WriteAllText(path, sb.ToString(), new UTF8Encoding(false));
        MainFile.Logger.Info($"[i18n] describe dump ({reason}) -> {path}");

        // --- side file: codec messages + ForgedText key stats (not part of the byte-for-byte English diff) ---------------
        var ui = new StringBuilder();
        ui.Append("# bts describe ui dump; lang=").Append(lang).Append('\n');
        foreach (var code in new[] { "", "x.y", "ABCD.1.x.y", "BTSC.9999.x.y", "BTSC.1.%%%.0", "BTSC.1.H4sIAAAAAAAAA6uuBQBDv6ajAgAAAA.deadbeef" })
        {
            BTS1Codec.TryDecode(code, out _, out _, out var err);
            ui.Append("[codec] ").Append(Esc(code)).Append(" -> ").Append(Esc(err)).Append('\n');
        }
        ui.Append("[keys] seen=").Append(ForgedText.SeenKeys.Count).Append(" missing=").Append(ForgedText.MissingKeys.Count).Append('\n');
        foreach (var k in ForgedText.MissingKeys.OrderBy(k => k, StringComparer.Ordinal))
            ui.Append("[missing] ").Append(k).Append('\n');
        string uiPath = Godot.ProjectSettings.GlobalizePath($"user://logs/bts_describe_ui_{lang}.txt");
        System.IO.File.WriteAllText(uiPath, ui.ToString(), new UTF8Encoding(false));
    }

    private static string Try(Func<string> f)
    {
        try { return f(); }
        catch (Exception e) { return $"<ERR {e.GetType().Name}: {e.Message}>"; }
    }

    private static void DumpCorpusFile(StringBuilder sb, string fn, string json)
    {
        var parser = new Godot.Json();
        if (parser.Parse(json) != Godot.Error.Ok || parser.Data.VariantType != Godot.Variant.Type.Dictionary)
        { sb.Append("[corpus] ").Append(fn).Append(" <bad json>\n"); return; }
        var root = parser.Data.AsGodotDictionary();
        if (root.ContainsKey("character") && root["character"].VariantType == Godot.Variant.Type.Dictionary)
        {
            var ch = root["character"].AsGodotDictionary();
            if (root.ContainsKey("relic") && !ch.ContainsKey("relic")) ch["relic"] = root["relic"];
            DumpCharacter(sb, fn, Godot.Json.Stringify(ch));
            if (root.ContainsKey("cards") && root["cards"].VariantType == Godot.Variant.Type.Array)
            {
                int i = 0;
                foreach (var c in root["cards"].AsGodotArray())
                    DumpCard(sb, $"{fn}#{++i}", Godot.Json.Stringify(c));
            }
        }
        else if (root.ContainsKey("max_hp") || root.ContainsKey("starting_deck"))
            DumpCharacter(sb, fn, json);
        else
            DumpCard(sb, fn, json);
    }

    private static void DumpCard(StringBuilder sb, string tag, string json)
    {
        if (!ForgedCards.TryParseCardJson(json, 1, out var spec, out var err, allowBasic: true, allowCustomOrbs: true) || spec == null)
        { sb.Append("[corpus] ").Append(tag).Append(" REJECTED ").Append(Esc(err)).Append('\n'); return; }
        sb.Append("[corpus] ").Append(tag).Append(' ').Append(spec.Id).Append(" desc = ")
          .Append(Esc(Try(() => ForgedCards.DumpDescribe(spec.Effects, spec.Target)))).Append('\n');
        if (spec.Upgrade != null)
            sb.Append("[corpus] ").Append(tag).Append(' ').Append(spec.Id).Append(" upgrade = ")
              .Append(Esc(Try(() => ForgedCards.DumpDescribe(spec.Upgrade, spec.Target)))).Append('\n');
        foreach (var t in spec.Effects.Concat(spec.Upgrade ?? []).Where(e => e.Op == "add_trigger"))
            sb.Append("[corpus] ").Append(tag).Append(' ').Append(spec.Id).Append(" trigger = ")
              .Append(Esc(Try(() => ForgedCards.DescribeTrigger(t)))).Append('\n');
    }

    private static void DumpCharacter(StringBuilder sb, string tag, string json)
    {
        if (!ForgedCharacters.DumpParseClass(json, out var cs, out var err) || cs == null)
        { sb.Append("[corpus] ").Append(tag).Append(" class REJECTED ").Append(Esc(err)).Append('\n'); return; }
        foreach (var s in cs.StatusPool)
            sb.Append("[corpus] ").Append(tag).Append(" status ").Append(s.Name).Append(" = ")
              .Append(Esc(Try(() => ForgedStatusPower.Describe(s)))).Append('\n');
        foreach (var o in cs.OrbPool.Where(o => o.CustomSpec != null))
            sb.Append("[corpus] ").Append(tag).Append(" orb ").Append(o.Name).Append(" = ")
              .Append(Esc(Try(() => OrbRunner.Describe(o.CustomSpec!)))).Append('\n');
        foreach (var m in cs.SummonPool)
            sb.Append("[corpus] ").Append(tag).Append(" summon ").Append(m.Name).Append(" = ")
              .Append(Esc(Try(() => SummonRunner.Describe(m)))).Append('\n');
    }
}
