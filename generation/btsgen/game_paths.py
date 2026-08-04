"""Per-OS locations of the installed STS2's user files (Phase 1b of the autoslay Linux port).

The tooling was authored on Windows (%APPDATA%); this box runs the NATIVE Linux Steam build. Keep the
branches SIDE-BY-SIDE — never replace the Windows path (explicit project convention). Two dirs matter,
and on Linux they are NOT the same place:

  * the game's own user:// dir (Godot custom user dir) — saves, logs/, forged/ staged classes:
      Windows: %APPDATA%/SlayTheSpire2          Linux: ~/.local/share/SlayTheSpire2   (verified 2026-07-03)
  * what .NET's SpecialFolder.ApplicationData resolves to INSIDE the game (the mod's
    AutoSlaySmokeHook builds its request path from it):
      Windows: %APPDATA%/SlayTheSpire2 (same)   Linux: $XDG_CONFIG_HOME|~/.config / SlayTheSpire2

Override the user dir with BTS_STS2_USERDIR when a setup deviates (e.g. Proton prefix)."""
from __future__ import annotations

import os
from pathlib import Path

IS_WINDOWS = os.name == "nt"


def game_user_dir() -> Path:
    """The game's user:// dir (saves, logs/, autoslay logs, forged/ characters)."""
    override = os.environ.get("BTS_STS2_USERDIR")
    if override:
        return Path(override)
    if IS_WINDOWS:
        return Path(os.environ.get("APPDATA", str(Path.home()))) / "SlayTheSpire2"
    return Path.home() / ".local" / "share" / "SlayTheSpire2"


def dotnet_appdata_dir() -> Path:
    """Where .NET SpecialFolder.ApplicationData + '/SlayTheSpire2' lands inside the game process."""
    if IS_WINDOWS:
        return Path(os.environ.get("APPDATA", str(Path.home()))) / "SlayTheSpire2"
    xdg = os.environ.get("XDG_CONFIG_HOME")
    return (Path(xdg) if xdg else Path.home() / ".config") / "SlayTheSpire2"


def autoslay_request_dirs() -> list[Path]:
    """Every dir the in-game hook might watch for request.json. One on Windows; on Linux both
    candidates (the hook reads .NET ApplicationData, but write to the game dir too so a runtime that
    remaps XDG inside the Steam container still gets served — the hook consumes whichever it sees)."""
    dirs = [game_user_dir() / "autoslay", dotnet_appdata_dir() / "autoslay"]
    out: list[Path] = []
    for d in dirs:
        if d not in out:
            out.append(d)
    return out
