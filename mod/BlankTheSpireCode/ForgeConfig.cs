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
///
/// i18n (I18N_PLAN D): the section headers and button labels are settings_ui.json KEYS (BaseLib resolves
/// <c>BLANKTHESPIRE-&lt;SLUG&gt;.title</c> in the game language, e.g. "ImportSection" -> IMPORT_SECTION), and every
/// dialog string goes through <see cref="ForgedText"/> under its docs/copy/COPY.md key (<c>mod.dialog.*</c>).
/// </summary>
public class ForgeConfig : SimpleModConfig
{
    private static bool _importedThisSession;

    // === Import a class code (a whole forged CLASS as one paste-able BTSC code) ===============
    [ConfigSection("ImportSection")] // "Import a class code" (settings_ui.json)
    public static string ImportClassCode { get; set; } = "";

    // 0 = auto (update a same-named class, else the lowest empty class slot); 1..ClassCount = that slot.
    [ConfigSlider(0, ForgedCharacters.ClassCount, 1)]
    public static int ImportClassSlot { get; set; } = 0;

    // Button text must stay short: BaseLib's NConfigButton is a fixed 324px texture and long text
    // spills past its edges. The descriptive text lives in the row label + hover tip instead
    // (settings_ui.json keys derived from the method name, e.g. BLANKTHESPIRE-IMPORT_CLASS.title).
    [ConfigButton("ImportButton")] // "Import" 
    [ConfigHoverTip]
    public static void ImportClass(ModConfig config)
    {
        if (string.IsNullOrWhiteSpace(ImportClassCode))
        {
            Dialog(ForgedText.T("mod.dialog.import_title", "Import class"),
                   ForgedText.T("mod.dialog.import_empty", "Paste a class code into the \"Class code\" field above first."));
            return;
        }

        if (!BTS1Codec.TryDecode(ImportClassCode, out var json, out var kind, out var decodeError))
        {
            Dialog(ForgedText.T("mod.dialog.import_failed_title", "Import failed"), decodeError);
            return;
        }
        if (kind != BTS1Codec.BtsKind.Class)
        {
            Dialog(ForgedText.T("mod.dialog.wrong_type_title", "Wrong code type"),
                   ForgedText.T("mod.dialog.wrong_type_body", "That code isn't a class code. Paste a class (BTSC) code from blankthespire.com."));
            return;
        }

        if (!ForgedCharacters.TryImportClassBundle(json, ImportClassSlot, out int classSlot, out var err))
        {
            Dialog(ForgedText.T("mod.dialog.rejected_title", "Import rejected"),
                   ForgedText.F("mod.dialog.rejected_body", "The code decoded, but the class isn't playable here:\n{err}", ("err", err)));
            return;
        }

        // If the code carried a splash_url, fetch the generated art into the class's user-data dir so it
        // shows as the select-screen background. Best-effort — a fetch failure never blocks the import.
        Cards.Forged.ForgedSplash.TryCacheFromBundle(json, classSlot);

        _importedThisSession = true;
        ImportClassCode = "";
        Dialog(ForgedText.T("mod.dialog.imported_title", "Class imported"),
            ForgedText.F("mod.dialog.imported_body",
                "Imported into class slot {slot}.\n\nPress \"Restart game\" below, then pick the class on the character-select screen.",
                ("slot", $"{classSlot:00}")));
    }

    [ConfigButton("ClearSlotButton")] // "Clear slot" 
    [ConfigHoverTip]
    public static void ClearClass(ModConfig config)
    {
        if (ImportClassSlot < 1)
        {
            Dialog(ForgedText.T("mod.dialog.clear_title", "Clear class"),
                   ForgedText.F("mod.dialog.clear_need_slot", "Set \"Class slot\" above to the class slot to clear (1..{max}), then click again.",
                                ("max", ForgedCharacters.ClassCount)));
            return;
        }
        bool ok = ForgedCharacters.DeleteClass(ImportClassSlot);
        Dialog(ForgedText.T("mod.dialog.clear_title", "Clear class"), ok
            ? ForgedText.F("mod.dialog.cleared", "Cleared class slot {slot}.\nPress \"Restart game\" to update the game.", ("slot", $"{ImportClassSlot:00}"))
            : ForgedText.F("mod.dialog.already_empty", "Class slot {slot} was already empty.", ("slot", $"{ImportClassSlot:00}")));
    }

    [ConfigButton("ClearAllButton", Color = "#b03f3f")] // "Clear ALL" 
    [ConfigHoverTip]
    public static void ClearAllClasses(ModConfig config)
    {
        int n = ForgedCharacters.ClearAllClasses();
        Dialog(ForgedText.T("mod.dialog.clear_all_title", "Clear all forged classes"),
            ForgedText.F("mod.dialog.clear_all_body", "Removed {n} forged class(es). Empty class slots stay hidden.\nPress \"Restart game\" to update the game.", ("n", n)));
    }

    // === Restart =============================================================================
    // Imported classes are JSON loaded at startup, so applying them just needs a relaunch. A detached
    // helper waits for THIS process to exit, then re-launches the game via Steam.
    [ConfigSection("ApplySection")]    // "Apply changes"
    [ConfigButton("RestartButton")]    // "Restart game" 
    [ConfigHoverTip]
    public static void RestartGame(ModConfig config)
    {
        if (!_importedThisSession)
            Dialog(ForgedText.T("mod.dialog.restart_title", "Restart"),
                   ForgedText.T("mod.dialog.restart_nothing", "Nothing imported yet this session.\n(Restarting will still apply any classes imported earlier.)"));

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
            Dialog(ForgedText.T("mod.dialog.restart_title", "Restart"),
                   ForgedText.F("mod.dialog.restart_failed", "Couldn't auto-relaunch:\n{err}\n\nPlease quit and start the game yourself to apply changes.", ("err", e.Message)));
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
