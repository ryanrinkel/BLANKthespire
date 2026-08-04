using System;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Text.Json;
using HarmonyLib;
using MegaCrit.Sts2.Core.AutoSlay;

namespace BlankTheSpire.BlankTheSpireCode.Testing;

/// <summary>
/// Phase 1 of AUTOSLAY_TESTING_PLAN.md — the unattended crash/hang smoke gate.
///
/// AutoSlay is MegaCrit's built-in run-automation runner (<c>MegaCrit.Sts2.Core.AutoSlay.AutoSlayer</c>,
/// ships in retail sts2.dll). Its player is RANDOM, so this is a CRASH/HANG gate, not a balance tool:
/// it plays a full run with a fixed seed, and any unhandled exception or soft-lock surfaces as a
/// <c>RunFailed</c> log line (the runner's Watchdog turns hangs into <c>AutoSlayTimeoutException</c>).
/// When the run ends the runner calls <c>QuitGame(exitCode)</c>, so the game exits on its own.
///
/// HANDOFF IS FILE-BASED, NOT ENV/ARGS. STS2 must be launched through Steam (Steamworks DRM), and a
/// <c>steam://run</c> launch neither inherits our env nor lets us pass args reliably. So the driver
/// (<c>cli_autoslay_smoke.py</c>) drops a small JSON "request" file; this hook reads it at the main menu
/// and CONSUMES (deletes) it immediately, so a leftover request can't auto-trigger a later manual launch.
/// Request path: <c>%APPDATA%/SlayTheSpire2/autoslay/request.json</c> (override via
/// <c>BTS_AUTOSLAY_REQUEST</c> env for local testing). Shape: <c>{ "seed", "log", "character" }</c>.
///
/// Trigger point: <c>NMainMenu.CheckCommandLineArgs()</c> (the boot hook MegaCrit uses to decide whether
/// to auto-start something); <c>AutoSlayer.Start</c> then awaits <c>WaitForMainMenuAsync</c> itself, so
/// being called as the menu loads is fine. Does NOTHING when no request file is present (normal play).
///
/// Auto-discovered by the existing <c>harmony.PatchAll()</c> in <c>MainFile.Initialize</c> (like
/// <c>MerchantSafetyPatch</c>) — deliberately NO edit to MainFile.cs.
///
/// KNOWN LIMITATION (plan §5a): AutoSlay has no character-select handler — it embarks with whatever
/// class is CURRENTLY selected. So this reliably tests OUR forged class only once that class is the
/// active selection. Pinning a specific character headlessly needs the bootstrap path
/// (<c>IBootstrapSettings.Character</c> + <c>NonInteractiveMode</c>); that's a follow-up, flagged below.
/// </summary>
[HarmonyPatch]
internal static class AutoSlaySmokeHook
{
    private const string EnvRequestOverride = "BTS_AUTOSLAY_REQUEST"; // optional: point at a custom request file

    private static bool _kicked; // guard against CheckCommandLineArgs firing more than once
    private static AutoSlayer? _runner; // keep a strong ref so the runner isn't GC'd mid-run

    /// <summary>
    /// The forged-character TYPE NAME to pin this smoke run to (e.g. "ForgedCharacterSlot01"), or null = no pin
    /// (AutoSlay random-picks any unlocked class). Read by <see cref="AutoSlayCharacterPinPatch"/>. Set once from
    /// the request file; only consulted while <c>AutoSlayer.IsActive</c>, so it never affects normal play.
    /// </summary>
    internal static string? PinCharacterType { get; private set; }

    private sealed class SmokeRequest
    {
        public string? seed { get; set; }
        public string? log { get; set; }
        public string? character { get; set; }
    }

    private static MethodBase? TargetMethod() =>
        AccessTools.Method("MegaCrit.Sts2.Core.Nodes.Screens.MainMenu.NMainMenu:CheckCommandLineArgs");

    private static void Postfix()
    {
        if (_kicked) return;

        string requestPath = RequestPath();
        SmokeRequest? req = ReadAndConsume(requestPath);
        if (req == null || string.IsNullOrWhiteSpace(req.seed)) return; // normal play — no smoke request

        _kicked = true;

        try
        {
            string logFile = string.IsNullOrWhiteSpace(req.log) ? DefaultLogPath(req.seed!) : req.log!;
            Directory.CreateDirectory(Path.GetDirectoryName(logFile)!);

            if (!string.IsNullOrWhiteSpace(req.character))
            {
                // Character pinning (plan §5a): AutoSlayer.PlayMainMenuAsync RANDOM-picks from the UNLOCKED
                // character buttons (Where(!IsLocked) → Rng.NextItem). We pin by normalizing the request to a
                // forged-character type name and having AutoSlayCharacterPinPatch report every OTHER button as
                // "locked" while this run is active — so the random pick collapses to our class.
                PinCharacterType = NormalizeCharacter(req.character!);
                MainFile.Logger.Info($"[AutoSlaySmoke] pinning character to type '{PinCharacterType}' (from '{req.character}').");
            }

            // Let the rest of the game know we're in non-interactive auto-play (suppresses interactive
            // prompts that would otherwise block the runner). Best-effort; reflection so a signature
            // change degrades to a warning instead of breaking normal play.
            TrySetNonInteractive();

            MainFile.Logger.Info($"[AutoSlaySmoke] starting AutoSlay run — seed='{req.seed}', log='{logFile}'.");
            _runner = new AutoSlayer();
            _runner.Start(req.seed!, logFile); // fire-and-forget; AutoSlayer.QuitGame(exitCode) ends the process
        }
        catch (Exception e)
        {
            // Never let the smoke hook break a normal launch.
            MainFile.Logger.Error($"[AutoSlaySmoke] failed to start AutoSlay: {e}");
        }
    }

    /// <summary>Read the request file and delete it (consume-once). Returns null if absent/unreadable.</summary>
    private static SmokeRequest? ReadAndConsume(string path)
    {
        try
        {
            if (!File.Exists(path)) return null;
            string json = File.ReadAllText(path);
            try { File.Delete(path); } catch { /* best-effort consume */ }
            return JsonSerializer.Deserialize<SmokeRequest>(json);
        }
        catch (Exception e)
        {
            MainFile.Logger.Warn($"[AutoSlaySmoke] could not read request '{path}': {e.Message}");
            return null;
        }
    }

    private static string RequestPath()
    {
        string? overridePath = Environment.GetEnvironmentVariable(EnvRequestOverride);
        if (!string.IsNullOrWhiteSpace(overridePath)) return overridePath!;
        return Path.Combine(AutoSlayDir(), "request.json");
    }

    /// <summary>
    /// Best-effort: set <c>NonInteractiveMode.AutoSlayerCheck</c> so the game treats this as an auto-play
    /// session. Reflection so a future signature change degrades to a warning.
    /// </summary>
    private static void TrySetNonInteractive()
    {
        try
        {
            var t = AccessTools.TypeByName("MegaCrit.Sts2.Core.Helpers.NonInteractiveMode");
            var prop = t?.GetProperty("AutoSlayerCheck", BindingFlags.Public | BindingFlags.Static);
            if (prop?.SetMethod != null)
                prop.SetValue(null, new Func<bool>(() => AutoSlayer.IsActive));
        }
        catch (Exception e)
        {
            MainFile.Logger.Warn($"[AutoSlaySmoke] could not set NonInteractiveMode.AutoSlayerCheck: {e.Message}");
        }
    }

    private static string AutoSlayDir()
    {
        string appData = Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData);
        return Path.Combine(appData, "SlayTheSpire2", "autoslay");
    }

    private static string DefaultLogPath(string seed) =>
        Path.Combine(AutoSlayDir(), $"autoslay_{Sanitize(seed)}.log");

    private static string Sanitize(string s)
    {
        foreach (char c in Path.GetInvalidFileNameChars()) s = s.Replace(c, '_');
        return s;
    }

    /// <summary>
    /// Map a request's <c>character</c> value to a forged-character TYPE NAME. Accepts the exact type name
    /// ("ForgedCharacterSlot01"), a bare/"class"/"slot"-prefixed slot number ("1", "01", "class1", "slot1"),
    /// and otherwise passes the string through (so a future real Id can be matched directly).
    /// </summary>
    internal static string NormalizeCharacter(string raw)
    {
        string s = raw.Trim();
        if (s.StartsWith("ForgedCharacterSlot", StringComparison.OrdinalIgnoreCase)) return s;
        string digits = new string(s.Where(char.IsDigit).ToArray());
        if (digits.Length > 0 && int.TryParse(digits, out int n) && n >= 1)
            return $"ForgedCharacterSlot{n:D2}";
        return s;
    }

    /// <summary>True if <paramref name="character"/> is the class this smoke run is pinned to (matched on the
    /// concrete CharacterModel TYPE NAME, which our forged shells define deterministically).</summary>
    internal static bool MatchesPin(object? character)
    {
        if (character == null || string.IsNullOrEmpty(PinCharacterType)) return false;
        return string.Equals(character.GetType().Name, PinCharacterType, StringComparison.OrdinalIgnoreCase);
    }
}

/// <summary>
/// Linux-box embark headroom (found 2026-07-03): AutoSlayer gives the FIRST room only
/// AutoSlayConfig.nodeWaitTimeout = 10s after the run state initializes, but on this machine the
/// embark asset preload (Common ~690 + character ~580 assets) can take longer, so every smoke run
/// died with "Room type not assigned" before the map even appeared — a machine-speed artifact, not a
/// content bug. Widen JUST that wait (keyed on its timeout message); every other AutoSlay timeout
/// stays stock so real hangs are still caught quickly. WaitHelper lives in the AutoSlay namespace and
/// runs only during AutoSlay sessions, so normal play is untouched.
/// </summary>
[HarmonyPatch]
internal static class AutoSlayEmbarkTimeoutPatch
{
    // Cold first-run embark preload (Common ~690 + character ~580 assets) on this modest box (Quadro RTX
    // 3000) exceeded 90s in the 2026-07-04 session — every run then falsely failed "Room type not assigned".
    // Widened to 180s: still AutoSlay-embark-only (keyed on the timeout message), normal play untouched, and
    // a genuine embark hang is still caught (just later).
    private static readonly TimeSpan MinRoomWait = TimeSpan.FromSeconds(180);

    private static MethodBase? TargetMethod() =>
        AccessTools.Method("MegaCrit.Sts2.Core.AutoSlay.Helpers.WaitHelper:Until");

    [HarmonyPrefix]
    private static void Prefix(ref TimeSpan? timeout, string? timeoutMessage)
    {
        if (timeoutMessage == "Room type not assigned" && (timeout == null || timeout < MinRoomWait))
            timeout = MinRoomWait;
    }
}

/// <summary>
/// Companion to <see cref="AutoSlayEmbarkTimeoutPatch"/>: the 30s Watchdog ticks through the same
/// slow embark (it resets on ACTIONS, and there are none between "confirm character" and the first
/// room), so a cold-class preload &gt;30s still killed the run. Skip watchdog checks ONLY while the run
/// has no current room yet — that whole window is already guarded by the (widened) "Room type not
/// assigned" wait, so a genuine embark hang is still caught. In-room behavior is untouched.
/// </summary>
[HarmonyPatch(typeof(MegaCrit.Sts2.Core.AutoSlay.Helpers.Watchdog),
              nameof(MegaCrit.Sts2.Core.AutoSlay.Helpers.Watchdog.Check))]
internal static class AutoSlayEmbarkWatchdogPatch
{
    [HarmonyPrefix]
    private static bool Prefix()
    {
        try
        {
            var state = MegaCrit.Sts2.Core.Runs.RunManager.Instance?.DebugOnlyGetState();
            return state?.CurrentRoom != null; // no room yet = embark/preload — let the room-wait guard it
        }
        catch
        {
            return true; // never let the guard itself hide a real hang
        }
    }
}

/// <summary>
/// Character-pin enforcement for the AutoSlay smoke gate (plan §5a). AutoSlayer picks the run's character by
/// filtering the select-screen buttons to <c>!IsLocked</c> then choosing one at random. While a pinned smoke run
/// is active, this postfix makes every button EXCEPT the pinned class report <c>IsLocked == true</c>, so the
/// random pick has exactly one candidate — ours. Inert outside a pinned smoke run (gated on
/// <c>AutoSlayer.IsActive</c> + a non-null <see cref="AutoSlaySmokeHook.PinCharacterType"/>), so normal play and
/// unpinned smoke runs are untouched.
/// </summary>
[HarmonyPatch]
internal static class AutoSlayCharacterPinPatch
{
    private static MethodBase? TargetMethod() =>
        AccessTools.PropertyGetter(
            "MegaCrit.Sts2.Core.Nodes.Screens.CharacterSelect.NCharacterSelectButton:IsLocked");

    private static void Postfix(object __instance, ref bool __result)
    {
        if (!AutoSlayer.IsActive || string.IsNullOrEmpty(AutoSlaySmokeHook.PinCharacterType)) return;
        try
        {
            object? character = AccessTools.PropertyGetter(__instance.GetType(), "Character")?.Invoke(__instance, null)
                                ?? __instance.GetType().GetProperty("Character")?.GetValue(__instance);
            // Lock everything that isn't the pinned class; keep the pinned class unlocked.
            __result = !AutoSlaySmokeHook.MatchesPin(character);
        }
        catch
        {
            // Best-effort: a reflection failure must never break the select screen — leave the real result.
        }
    }
}
