"""GitHub #2: the autoslay smoke must run on the Workshop BaseLib, never a local mods/BaseLib that shadows it."""
from __future__ import annotations

from pathlib import Path

from btsgen import cli_autoslay_smoke as smoke

SHADOW_BASELIB = ("[WARN] Mod with ID BaseLib is loaded both via Steam and local mods directory. "
                  "Disabling the Steam workshop version.")
SHADOW_OURS = ("[WARN] Mod with ID BlankTheSpire is loaded both via Steam and local mods directory. "
               "Disabling the Steam workshop version.")
WORKSHOP_LOAD = ("[INFO] Loading assembly DLL C:\\Program Files (x86)\\Steam\\steamapps\\workshop\\content\\"
                 "2868840\\3737335127\\BaseLib\\BaseLib.dll")


def test_baselib_shadow_line_detected():
    assert smoke.baselib_shadowed("[INFO] boot\n" + SHADOW_BASELIB + "\n[INFO] more\n")


def test_our_own_workshop_shadow_is_not_a_baselib_shadow():
    # A dev subscribed to their own Workshop item: the local BlankTheSpire wins. Harmless; must not fail.
    assert not smoke.baselib_shadowed(SHADOW_OURS + "\n" + WORKSHOP_LOAD + "\n")


def test_clean_workshop_log_passes():
    assert not smoke.baselib_shadowed(WORKSHOP_LOAD + "\n[INFO] [BaseLib] Registered config for mod BaseLib\n")
    assert not smoke.baselib_shadowed("")


def test_classify_fails_when_shadowed(tmp_path: Path, monkeypatch):
    monkeypatch.delenv(smoke.ALLOW_LOCAL_BASELIB_ENV, raising=False)
    autoslay = tmp_path / "autoslay_X.log"
    autoslay.write_text("[AutoSlay] Starting run with seed=X\n[AutoSlay] Run completed successfully with seed=X\n",
                        encoding="utf-8")
    game_log = tmp_path / "godot.log"
    game_log.write_text(SHADOW_BASELIB + "\n", encoding="utf-8")
    r = smoke._classify("X", autoslay, timed_out=False, game_log=game_log)
    assert not r.ok
    assert smoke.BASELIB_SHADOW_REASON in r.reason

    game_log.write_text(SHADOW_OURS + "\n", encoding="utf-8")
    r = smoke._classify("X", autoslay, timed_out=False, game_log=game_log)
    assert r.ok and r.reason == "RunCompleted"


def test_classify_escape_hatch(tmp_path: Path, monkeypatch):
    monkeypatch.setenv(smoke.ALLOW_LOCAL_BASELIB_ENV, "1")
    autoslay = tmp_path / "autoslay_X.log"
    autoslay.write_text("[AutoSlay] Run completed successfully with seed=X\n", encoding="utf-8")
    game_log = tmp_path / "godot.log"
    game_log.write_text(SHADOW_BASELIB + "\n", encoding="utf-8")
    assert smoke._classify("X", autoslay, timed_out=False, game_log=game_log).ok


def test_missing_game_log_is_not_a_shadow(tmp_path: Path):
    assert smoke._baselib_shadow_check(tmp_path / "nope.log") is None


def test_local_baselib_dir(tmp_path: Path):
    assert smoke.local_baselib_dir(None) is None
    assert smoke.local_baselib_dir(tmp_path) is None
    (tmp_path / "mods" / "BaseLib").mkdir(parents=True)
    assert smoke.local_baselib_dir(tmp_path) == tmp_path / "mods" / "BaseLib"


def test_main_refuses_with_local_baselib(tmp_path: Path, monkeypatch, capsys):
    (tmp_path / "mods" / "BaseLib").mkdir(parents=True)
    monkeypatch.delenv(smoke.ALLOW_LOCAL_BASELIB_ENV, raising=False)
    monkeypatch.setattr(smoke, "_game_running", lambda: False)
    monkeypatch.setattr(smoke.game_paths, "game_install_dir", lambda: tmp_path)
    launched = []
    monkeypatch.setattr(smoke, "_run_one", lambda *a, **k: launched.append(a))
    assert smoke.main(["--seeds", "X", "--relic", "off"]) == 2
    assert not launched
    assert smoke.ALLOW_LOCAL_BASELIB_ENV in capsys.readouterr().err
