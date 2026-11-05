using BaseLib.Config;
using Godot;
using HarmonyLib;
using MegaCrit.Sts2.Core.Modding;
using System.Reflection;

namespace BlankTheSpire.BlankTheSpireCode;

[ModInitializer(nameof(Initialize))]
public partial class MainFile : Node
{
    public const string ModId = "BlankTheSpire"; //Used for resource filepath
    public const string ResPath = $"res://{ModId}";

    public static MegaCrit.Sts2.Core.Logging.Logger Logger { get; } = new(ModId, MegaCrit.Sts2.Core.Logging.LogType.Generic);

    public static void Initialize()
    {
        //If you want to use scripts defined in your mod for Godot scenes, uncomment the following line.
        //Godot.Bridge.ScriptManagerBridge.LookupScriptsInAssembly(Assembly.GetExecutingAssembly());
        
        Harmony harmony = new(ModId);

        harmony.PatchAll();

        // Release banner (v0.4.0 prep): one line that says which card vocabulary this DLL reads, so a packaged-DLL
        // smoke (and a player's log) can confirm the build matches the site's codes (BTS1Codec rejects newer ones).
        Logger.Info($"[BTS] BLANK the spire loaded: card vocabulary v{Engine.ForgedCards.VocabVersion}.");
        LogBaseLibVersion();

        // The in-game "forge" screen (appears in the main-menu mod settings list).
        ModConfigRegistry.Register(ModId, new ForgeConfig());

        // Queued import (the file-drop twin of the settings screen's "Import" button): runs a dropped class code
        // through the SAME codec + importer, BEFORE any class spec is read, so the class plays in this launch.
        Engine.ForgedCharacters.ImportQueuedCode();

        // EXPLORE SPIKE: pre-render an emoji glyph to a PNG so SpikeSharpenPower can try it as its icon.
        Engine.EmojiIconRenderer.Kick("sharpen", "🗡️");

        // Phase M (gap #36): the Forge counter power's icon (ForgedForgePower).
        Engine.EmojiIconRenderer.Kick("forge", "⚒️");

        // Phase S (gap #1): the Balance gauge's two pole icons (ForgedBalancePower flips by sign).
        Engine.EmojiIconRenderer.Kick("balance_dark", "🌑");
        Engine.EmojiIconRenderer.Kick("balance_light", "☀️");

        // Phase AB (gap #20): the Corruption power's icon (ForgedCorruptionPower).
        Engine.EmojiIconRenderer.Kick("corruption", "☠️");

        // Phase AF (gap #41): the Blade Empower power's icon (ForgedBladeEmpowerPower).
        Engine.EmojiIconRenderer.Kick("blade_empower", "💥");

        // Phase AO (v45): the Cost Shift power's icon (ForgedCostShiftPower).
        Engine.EmojiIconRenderer.Kick("cost_shift", "🏷️");

        // Phase J: pre-render each forged class status's emoji to a .res icon (key = "status{K}_{M}", matching
        // ForgedStatusPower.IconKey). Best-effort — a status with no/failed emoji falls back to the placeholder.
        for (int k = 1; k <= Engine.ForgedCharacters.ClassCount; k++)
            for (int m = 1; m <= Engine.ForgedCharacters.MaxCustomStatuses; m++)
            {
                var st = Engine.ForgedCharacters.StatusSpecFor(k, m);
                if (st != null && !string.IsNullOrEmpty(st.Emoji))
                    Engine.EmojiIconRenderer.Kick($"status{k}_{m}", st.Emoji);
            }

        // Phase BA (v55): pre-render each forged class potion's emoji the same way (key = "potion{K}_{M}",
        // matching ForgedPotion.IconKey). A potion's art surface is path-based and BaseLib patches the private
        // PackedImagePath getter, so the rendered .res reaches the potion bar, the tooltip and the throw VFX
        // alike. Best-effort — no/failed emoji falls back to the shipped placeholder art.
        for (int k = 1; k <= Engine.ForgedCharacters.ClassCount; k++)
            for (int m = 1; m <= Engine.ForgedCharacters.MaxPotions; m++)
            {
                var po = Engine.ForgedCharacters.PotionSpecFor(k, m);
                if (po != null && !string.IsNullOrEmpty(po.Emoji))
                    Engine.EmojiIconRenderer.Kick($"potion{k}_{m}", po.Emoji);
            }
    }

    /// <summary>GitHub #2: one [BOOT] line with the BaseLib actually loaded (version + file path, which proves
    /// whether it came from the Workshop or a local mods/BaseLib that shadows it) and the BaseLib this DLL was
    /// compiled against (the csproj's BaseLibBuiltAgainst assembly metadata). BaseLib is not binary-compatible
    /// across minors, so an older one than we built against is logged as "BaseLib too old". Never throws.</summary>
    private static void LogBaseLibVersion()
    {
        try
        {
            var baseLib = typeof(BaseLib.Utils.CommonActions).Assembly;
            var loaded = baseLib.GetName().Version;
            string? info = baseLib.GetCustomAttribute<AssemblyInformationalVersionAttribute>()?.InformationalVersion;
            string? builtAgainst = typeof(MainFile).Assembly.GetCustomAttributes<AssemblyMetadataAttribute>()
                .FirstOrDefault(a => a.Key == "BaseLibBuiltAgainst")?.Value;
            string line = $"[BOOT] BaseLib loaded v{loaded}" + (info != null ? $" ({info})" : "") +
                          $" from '{baseLib.Location}'; built against v{builtAgainst ?? "?"}.";
            if (loaded != null && System.Version.TryParse(builtAgainst, out var built) && loaded < built)
                Logger.Warn(line + " BaseLib too old: update BaseLib (Workshop item 3737335127) and delete any " +
                            "local mods/BaseLib copy, or statuses and other effects will fail mid-combat.");
            else
                Logger.Info(line);
        }
        catch (Exception ex)
        {
            Logger.Warn($"[BOOT] could not read the BaseLib version: {ex.GetType().Name}: {ex.Message}");
        }
    }
}
