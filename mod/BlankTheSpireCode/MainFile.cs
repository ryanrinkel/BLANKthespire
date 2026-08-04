using BaseLib.Config;
using Godot;
using HarmonyLib;
using MegaCrit.Sts2.Core.Modding;

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

        // The in-game "forge" screen (appears in the main-menu mod settings list).
        ModConfigRegistry.Register(ModId, new ForgeConfig());

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

        // Phase J: pre-render each forged class status's emoji to a .res icon (key = "status{K}_{M}", matching
        // ForgedStatusPower.IconKey). Best-effort — a status with no/failed emoji falls back to the placeholder.
        for (int k = 1; k <= Engine.ForgedCharacters.ClassCount; k++)
            for (int m = 1; m <= Engine.ForgedCharacters.MaxCustomStatuses; m++)
            {
                var st = Engine.ForgedCharacters.StatusSpecFor(k, m);
                if (st != null && !string.IsNullOrEmpty(st.Emoji))
                    Engine.EmojiIconRenderer.Kick($"status{k}_{m}", st.Emoji);
            }
    }
}
