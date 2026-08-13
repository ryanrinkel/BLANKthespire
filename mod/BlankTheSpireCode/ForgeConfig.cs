using System.Diagnostics;
using BaseLib.Config;
using BlankTheSpire.BlankTheSpireCode.Engine;
using Godot;

namespace BlankTheSpire.BlankTheSpireCode;

/// <summary>
/// The in-game mod menu (appears in the main-menu mods/settings list). It is now focused on a single
/// end-user flow: paste a shared BTSC class code, import it into a slot, then restart the game to play it.
///
/// Class codes are self-contained and data-only: importing re-validates every card against the live
/// EffectRunner vocabulary, so an imported class is always playable. No SDK / Python / repo required.
/// </summary>
public class ForgeConfig : SimpleModConfig
{
    private static bool _importedThisSession;

    // === Import a class code (a whole forged CLASS as one paste-able BTSC code) ===============
    [ConfigSection("Import a class code")]
    public static string ImportClassCode { get; set; } = "";

    // 0 = auto (update a same-named class, else the lowest empty class slot); 1..ClassCount = that slot.
    [ConfigSlider(0, ForgedCharacters.ClassCount, 1)]
    public static int ImportClassSlot { get; set; } = 0;

    // Button text must stay short: BaseLib's NConfigButton is a fixed 324px texture and long text
    // spills past its edges. The descriptive text lives in the row label + hover tip instead
    // (settings_ui.json keys derived from the method name, e.g. BLANKTHESPIRE-IMPORT_CLASS.title).
    [ConfigButton("Import")]
    [ConfigHoverTip]
    public static void ImportClass(ModConfig config)
    {
        if (string.IsNullOrWhiteSpace(ImportClassCode)) { Dialog("Import class", "Paste a class code into the \"Class code\" field above first."); return; }

        if (!BTS1Codec.TryDecode(ImportClassCode, out var json, out var kind, out var decodeError))
        {
            Dialog("Import failed", decodeError);
            return;
        }
        if (kind != BTS1Codec.BtsKind.Class)
        {
            Dialog("Wrong code type", "That code isn't a class code. Paste a class (BTSC) code from blankthespire.com.");
            return;
        }

        if (!ForgedCharacters.TryImportClassBundle(json, ImportClassSlot, out int classSlot, out var err))
        {
            Dialog("Import rejected", $"The code decoded, but the class isn't playable here:\n{err}");
            return;
        }

        // If the code carried a splash_url, fetch the generated art into the class's user-data dir so it
        // shows as the select-screen background. Best-effort — a fetch failure never blocks the import.
        Cards.Forged.ForgedSplash.TryCacheFromBundle(json, classSlot);

        _importedThisSession = true;
        ImportClassCode = "";
        Dialog("Class imported",
            $"Imported into class slot {classSlot:00}.\n\nPress \"Restart game\" below, then pick the class on the character-select screen.");
    }

    [ConfigButton("Clear slot")]
    [ConfigHoverTip]
    public static void ClearClass(ModConfig config)
    {
        if (ImportClassSlot < 1)
        {
            Dialog("Clear class", $"Set \"Class slot\" above to the class slot to clear (1..{ForgedCharacters.ClassCount}), then click again.");
            return;
        }
        bool ok = ForgedCharacters.DeleteClass(ImportClassSlot);
        Dialog("Clear class", ok
            ? $"Cleared class slot {ImportClassSlot:00}.\nPress \"Restart game\" to update the game."
            : $"Class slot {ImportClassSlot:00} was already empty.");
    }

    [ConfigButton("Clear ALL", Color = "#b03f3f")]
    [ConfigHoverTip]
    public static void ClearAllClasses(ModConfig config)
    {
        int n = ForgedCharacters.ClearAllClasses();
        Dialog("Clear all forged classes",
            $"Removed {n} forged class(es). Empty class slots stay hidden.\nPress \"Restart game\" to update the game.");
    }

    // === Restart =============================================================================
    // Imported classes are JSON loaded at startup, so applying them just needs a relaunch. A detached
    // helper waits for THIS process to exit, then re-launches the game via Steam.
    [ConfigSection("Apply changes")]
    [ConfigButton("Restart game")]
    [ConfigHoverTip]
    public static void RestartGame(ModConfig config)
    {
        if (!_importedThisSession)
            Dialog("Restart", "Nothing imported yet this session.\n(Restarting will still apply any classes imported earlier.)");

        try
        {
            int pid = Process.GetCurrentProcess().Id;
            var psi = new ProcessStartInfo("powershell.exe") { UseShellExecute = true };
            psi.ArgumentList.Add("-NoProfile");
            psi.ArgumentList.Add("-WindowStyle"); psi.ArgumentList.Add("Hidden");
            psi.ArgumentList.Add("-Command");
            psi.ArgumentList.Add(
                $"Wait-Process -Id {pid} -ErrorAction SilentlyContinue; Start-Sleep -Seconds 2; Start-Process 'steam://run/2868840'");
            Process.Start(psi);
        }
        catch (System.Exception e)
        {
            Dialog("Restart", $"Couldn't auto-relaunch:\n{e.Message}\n\nPlease quit and start the game yourself to apply changes.");
            return;
        }

        (Godot.Engine.GetMainLoop() as SceneTree)?.Quit();
    }

    // --- helpers -----------------------------------------------------------
    private static void Dialog(string title, string body)
    {
        var tree = Godot.Engine.GetMainLoop() as SceneTree;
        if (tree?.Root == null) { MainFile.Logger.Info($"[Forge] {title}: {body}"); return; }
        var dlg = new AcceptDialog { Title = title, DialogText = body };
        dlg.Confirmed += dlg.QueueFree;
        dlg.Canceled += dlg.QueueFree;
        tree.Root.AddChild(dlg);
        dlg.PopupCentered();
    }
}
