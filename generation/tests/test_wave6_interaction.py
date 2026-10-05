"""Wave 6 interaction smoke record (v0.4.0 release prep) — offline.

The tester (tests/gaptest-wave6/build_tester.py) combines the v61..v70 mechanics on single cards and in one deck; its
AutoSlay smoke (GAPTESTW61 / GAPTESTW62) is the engine's interaction regression record. This test asserts the tester's
cards still validate and that both saved tag greps exist and record a clean run: 0 mod exceptions, 0 BlankTheSpire frames,
0 "Localization formatting error", no import rejection, a clean outcome (completed / died to a boss — never a hang), and every phase prefix [BI]..[BR] fired.

    uv run python -m pytest tests/test_wave6_interaction.py   (from generation/)
"""
from __future__ import annotations

import importlib.util
import re
from pathlib import Path

TESTER_DIR = Path(__file__).resolve().parent / "gaptest-wave6"


def _tester():
    spec = importlib.util.spec_from_file_location("w6_tester", TESTER_DIR / "build_tester.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_wave6_tester_validates():
    mod = _tester()
    assert mod.validate(verbose=True) == 0
    types = [c["type"] for c in mod.CARDS if c["rarity"] != "basic"]
    assert types.count("attack") >= 3 and types.count("skill") >= 3 and types.count("power") >= 1
    assert mod.CHARACTER["max_hp"] >= 90


def test_wave6_smoke_records():
    mod = _tester()
    seen: dict[str, int] = {p: 0 for p in mod.PHASE_PREFIXES}
    for seed in mod.SMOKE_SEEDS:
        p = TESTER_DIR / f"godot_W6_tags_{seed}.txt"
        assert p.exists(), f"missing smoke record {p}"
        txt = p.read_text(encoding="utf-8")
        for line in ("# mod exceptions: 0", "# BlankTheSpire stack frames: 0", "# Localization formatting errors: 0",
                     "# [Forged] import rejections: 0"):
            assert line in txt, f"{p.name}: expected '{line}'"
        # the hand-written verdict line: "completed" or "died to <boss>" — never a hang / freeze / stall
        out = re.search(r"# outcome: (.*)", txt)
        assert out and re.match(r"(completed|died to )", out.group(1)), f"{p.name}: outcome line missing or not a clean end"
        m = re.search(r"# per-phase prefix counts: (.*)", txt)
        assert m, f"{p.name}: no per-phase prefix line"
        for pref, n in re.findall(r"(\[B[I-R]\]) (\d+)", m.group(1)):
            seen[pref] += int(n)
    missing = [p for p, n in seen.items() if n == 0]
    assert not missing, f"phase prefixes that never fired across the two seeds: {missing}"
