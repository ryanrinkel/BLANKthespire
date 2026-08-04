"""autoslay-smoke — Phase 1 crash/hang smoke gate for compiled cards (AUTOSLAY_TESTING_PLAN.md).

    uv run btsgen-autoslay-smoke --count 5
    uv run btsgen-autoslay-smoke --seeds ABC DEF --build         # rebuild the mod first
    uv run btsgen-autoslay-smoke --count 3 --character class1     # (character pinning: see plan sec 5a)

What it does: for each seed, drops a JSON "request" file, launches Slay the Spire 2 THROUGH STEAM
(`steam://run/<appid>`), and waits. The in-mod `AutoSlaySmokeHook` reads (and consumes) that request at
the main menu and kicks MegaCrit's built-in `AutoSlayer`, which plays a full RANDOM run for the seed,
writes a structured `[AutoSlay]` log, then quits the game on its own. We poll the log + the game process
and classify: RunCompleted = pass; RunFailed / our own hang timeout = fail (with the captured reason).

WHY FILE-BASED (not env/args): STS2 must be launched via Steam (Steamworks DRM — a direct exe launch
dies with "Steam failed to initialize"). A `steam://` launch neither inherits our env nor lets us pass
args reliably, and detaches (no process handle / exit code). So we hand off via a file and poll the
filesystem + process list instead. See plan sec 5a.

This is a CRASH/HANG gate, NOT balance — AutoSlay's player is random (plan sec 4). It's the
post-compile complement to validator.py's static checks.

RELICS ARE FOLDED IN (--relic, default 'auto'): before launching, the gate ensures the tested class carries
a forged relic so every run also exercises the Phase L forged-relic runtime (triggers/modifiers + the
re-entrancy guard). It injects a broad-coverage smoke relic only when the class has none (or always, with
--relic force), and restores the staged files afterward. See smoke_relic.py.

VALIDATE THE DETECTOR FIRST (plan sec 5b): point this at a deliberately broken class (the known
0-power-card pool that used to hang the merchant) and confirm it reports a RunFailed timeout. A gate
that can't catch the one hang we already understand isn't trustworthy.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from . import game_paths, smoke_relic

REPO = Path(__file__).resolve().parents[2]
CSPROJ = REPO / "mod" / "BlankTheSpire.csproj"

# Steam app id for STS2 on this machine (the same id ForgeConfig relaunches with).
DEFAULT_APP_ID = os.environ.get("BTS_STS2_APPID", "2868840")
GAME_IMAGE = "SlayTheSpire2.exe"   # Windows process image
GAME_PROC_LINUX = "SlayTheSpire2"  # native Linux ELF name (pgrep/pkill -x)
# Primary dir (logs + prints). The request is ALSO dropped in every candidate hook dir — on Linux the
# game dir and the mod hook's .NET ApplicationData dir differ (see game_paths.autoslay_request_dirs).
AUTOSLAY_DIR = game_paths.game_user_dir() / "autoslay"
REQUEST_DIRS = game_paths.autoslay_request_dirs()
REQUEST_NAME = "request.json"  # must match AutoSlaySmokeHook.RequestPath()
GAME_LOG = game_paths.game_user_dir() / "logs" / "godot.log"

# How long to wait for the game process to first appear after a Steam launch before giving up.
STARTUP_GRACE_S = 120
POLL_S = 3

# --- AutoSlay log tokens -----------------------------------------------------------------------
# Pinned against a real captured run (2026-06-17). AutoSlayLog emits, verbatim:
#   start:    "[AutoSlay] Starting run with seed=<seed>"
#   failure:  "[ERROR] [AutoSlay] Run failed with seed=<seed>: <message>"  (RunFailed)
#   complete: "[AutoSlay] Run completed ..."                                (RunCompleted — see note)
# NOTE: RunCompleted CONFIRMED on the first PASS (2026-07-03, seed BTSTWEAK7, Linux): the runner logs
# "Run completed successfully with seed=<seed>" — matched by "run completed". Watchdog "No progress"
# lines are INFORMATIONAL, not failures — deliberately NOT matched here.
TOK_COMPLETED = ("run completed", "runcompleted")
TOK_FAILED = ("run failed", "runfailed", "autoslaytimeoutexception")


@dataclass
class RunResult:
    seed: str
    ok: bool
    reason: str
    log_path: Path


def _dotnet_exe() -> str:
    override = os.environ.get("DOTNET_EXE")
    if override:
        return override
    exe = "dotnet.exe" if game_paths.IS_WINDOWS else "dotnet"
    per_user = Path.home() / ".dotnet" / exe
    return str(per_user) if per_user.exists() else "dotnet"


def _build() -> bool:
    """Rebuild + deploy the mod (mirrors cli_forge's build step) so we smoke the freshest cards."""
    env = dict(os.environ, DOTNET_ROOT=str(Path(_dotnet_exe()).parent),
               DOTNET_CLI_TELEMETRY_OPTOUT="1", DOTNET_NOLOGO="1")
    print("  building mod...")
    b = subprocess.run([_dotnet_exe(), "build", str(CSPROJ), "-c", "Debug"],
                       capture_output=True, text=True, env=env)
    for line in (l for l in b.stdout.splitlines() if "error" in l.lower()
                 or "Build succeeded" in l or "Build FAILED" in l):
        print("  " + line.strip())
    if b.returncode != 0:
        print("BUILD FAILED.", file=sys.stderr)
    return b.returncode == 0


def _game_running() -> bool:
    if game_paths.IS_WINDOWS:
        out = subprocess.run(["tasklist", "/FI", f"IMAGENAME eq {GAME_IMAGE}", "/NH"],
                             capture_output=True, text=True)
        return GAME_IMAGE.lower() in out.stdout.lower()
    return subprocess.run(["pgrep", "-x", GAME_PROC_LINUX], capture_output=True).returncode == 0


def _kill_game() -> None:
    if game_paths.IS_WINDOWS:
        subprocess.run(["taskkill", "/IM", GAME_IMAGE, "/F"], capture_output=True, text=True)
    else:
        subprocess.run(["pkill", "-x", GAME_PROC_LINUX], capture_output=True)


def _launch_steam(app_id: str) -> None:
    url = f"steam://run/{app_id}"
    if game_paths.IS_WINDOWS:
        # os.startfile dispatches the steam:// protocol to the Steam client (Windows-only).
        os.startfile(url)  # type: ignore[attr-defined]
    else:
        # xdg-open hands the steam:// URL to the running Steam client and returns immediately.
        subprocess.Popen(["xdg-open", url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _log_terminal_state(log_path: Path) -> str | None:
    """Return 'failed' | 'completed' | None by scanning the AutoSlay log so far."""
    if not log_path.exists():
        return None
    text = log_path.read_text(encoding="utf-8", errors="replace").lower()
    if any(t in text for t in TOK_FAILED):
        return "failed"
    if any(t in text for t in TOK_COMPLETED):
        return "completed"
    return None


def _classify(seed: str, log_path: Path, timed_out: bool) -> RunResult:
    if timed_out:
        return RunResult(seed, False, "HANG — wall-clock timeout (game never quit on its own)", log_path)
    state = _log_terminal_state(log_path)
    if state == "failed":
        text = log_path.read_text(encoding="utf-8", errors="replace")
        line = next((ln.strip() for ln in text.splitlines()
                     if any(t in ln.lower() for t in TOK_FAILED)), "RunFailed")
        return RunResult(seed, False, f"RunFailed — {line[:200]}", log_path)
    if state == "completed":
        return RunResult(seed, True, "RunCompleted", log_path)
    if not log_path.exists():
        return RunResult(seed, False,
                         "no AutoSlay log written (hook didn't fire — mod not loaded, or game quit before menu?)",
                         log_path)
    # Log exists, game quit, but no terminal marker: ambiguous — soft-fail so a human looks.
    return RunResult(seed, False, "ambiguous — log has no RunCompleted/RunFailed marker", log_path)


def _run_one(seed: str, character: str | None, timeout_s: int, app_id: str) -> RunResult:
    log_path = AUTOSLAY_DIR / f"autoslay_{_sanitize(seed)}.log"
    # The hook consumes the request from ITS dir; drop a copy in every candidate (one on Windows).
    request_paths = [d / REQUEST_NAME for d in REQUEST_DIRS]
    if log_path.exists():
        log_path.unlink()

    request = {"seed": seed, "log": str(log_path)}
    if character:
        request["character"] = character
    for request_path in request_paths:
        request_path.parent.mkdir(parents=True, exist_ok=True)
        request_path.write_text(json.dumps(request), encoding="utf-8")

    print(f"  [{seed}] launching via Steam (app {app_id}); timeout {timeout_s}s…")
    _launch_steam(app_id)

    start = time.monotonic()
    saw_process = False
    try:
        while True:
            elapsed = time.monotonic() - start

            # Terminal marker in the log → done immediately.
            if _log_terminal_state(log_path) is not None:
                time.sleep(1)  # let the line flush
                return _classify(seed, log_path, timed_out=False)

            running = _game_running()
            saw_process = saw_process or running

            # Game launched and has now exited on its own (AutoSlayer.QuitGame) → classify from the log.
            if saw_process and not running:
                time.sleep(2)  # let the log flush after quit
                return _classify(seed, log_path, timed_out=False)

            # Never even started (e.g. Steam failed to launch) → clearer message than a plain timeout.
            if not saw_process and elapsed > STARTUP_GRACE_S:
                return RunResult(seed, False,
                                 f"game process never appeared within {STARTUP_GRACE_S}s "
                                 "(Steam launch failed, or game still loading?)", log_path)

            if elapsed > timeout_s:
                _kill_game()
                return _classify(seed, log_path, timed_out=True)

            time.sleep(POLL_S)
    finally:
        # Defensive: the hook consumes ITS request copy; clean up every copy that didn't get consumed.
        for request_path in request_paths:
            try:
                if request_path.exists():
                    request_path.unlink()
            except OSError:
                pass


def _sanitize(s: str) -> str:
    return "".join(c if c.isalnum() or c in "-_" else "_" for c in s)


def _stage_relics(mode: str, character: str | None):
    """Ensure the class(es) this smoke run will exercise carry a relic (so the run tests the forged-relic
    runtime). Returns a list of restore() callables to revert the staged files after the run.

    Targets the pinned --character slot when given; otherwise every staged forged slot (since, unpinned,
    AutoSlay random-picks among the unlocked classes). `mode` is 'auto' or 'force' (see --relic help).
    """
    force = mode == "force"
    slot = smoke_relic.slot_from_character(character)
    targets = [slot] if slot is not None else smoke_relic.existing_slots()
    if not targets:
        print("  --relic: no forged class slots staged on disk; nothing to inject (continuing).")
        return []

    restores = []
    for s in targets:
        restore = smoke_relic.ensure_relic(s, force=force)
        if restore is not None:
            restores.append(restore)
            print(f"  --relic {mode}: staged '{smoke_relic.SMOKE_RELIC['name']}' onto class slot {s:02d}.")
        else:
            print(f"  --relic {mode}: class slot {s:02d} already carries a relic (kept its own).")
    return restores


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="AutoSlay crash/hang smoke gate for compiled STS2 cards.")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--seeds", nargs="+", help="explicit list of run seeds")
    g.add_argument("--count", type=int, default=5, help="number of generated seeds (default 5)")
    ap.add_argument("--character", default=None, help="forged class id to test (best-effort; see plan sec 5a)")
    ap.add_argument("--relic", choices=("auto", "force", "off"), default="auto",
                    help="ensure the tested class carries a relic so the run exercises the forged-relic "
                         "runtime. auto (default): inject the broad-coverage smoke relic only if the class "
                         "has none (keep an authentic relic); force: always inject it (max coverage); "
                         "off: leave staged content untouched. Restored after the run(s).")
    ap.add_argument("--app-id", default=DEFAULT_APP_ID, help=f"Steam app id (default {DEFAULT_APP_ID})")
    ap.add_argument("--timeout", type=int, default=900, help="per-run hang timeout in seconds (default 900)")
    ap.add_argument("--build", action="store_true", help="dotnet build + deploy the mod before smoking")
    args = ap.parse_args(argv)

    seeds = args.seeds or [f"BTSSMOKE{i + 1}" for i in range(args.count)]

    if _game_running():
        print("ERROR: Slay the Spire 2 is already running. Close it first (one run per launch).",
              file=sys.stderr)
        return 2

    if args.build and not _build():
        return 1

    AUTOSLAY_DIR.mkdir(parents=True, exist_ok=True)
    print(f"autoslay-smoke: {len(seeds)} run(s); logs -> {AUTOSLAY_DIR}"
          + (f"; character={args.character}" if args.character else ""))
    print("  NOTE: each run opens a real game window (no true headless mode); it auto-plays and quits.")

    restores = _stage_relics(args.relic, args.character) if args.relic != "off" else []

    results: list[RunResult] = []
    try:
        for seed in seeds:
            results.append(_run_one(seed, args.character, args.timeout, args.app_id))
            r = results[-1]
            print(f"    -> {'PASS' if r.ok else 'FAIL'}: {r.reason}")
    finally:
        for restore in restores:
            restore()
        if restores:
            print(f"  restored {len(restores)} staged class file-set(s) to their prior state.")

    passed = sum(1 for r in results if r.ok)
    failed = [r for r in results if not r.ok]
    print(f"\n=== autoslay-smoke summary: {passed}/{len(results)} passed ===")
    for r in failed:
        print(f"  FAIL [{r.seed}] {r.reason}")
        print(f"       log: {r.log_path}")
    if failed:
        print(f"\nInspect the AutoSlay log(s) above and the game log ({GAME_LOG}) for the C# stack trace.")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
