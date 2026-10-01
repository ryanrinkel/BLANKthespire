"""Phase BG — mod-only UX: the ripen countdown + the Balance gauge text (VOCAB_EXPANSION_5_PLAN, gaps #60/#61).

Run:  uv run python -m tests.test_phase_bg  (from generation/). No vocab bump — this pins the C# shape only:
ripen powers are Counter with a DisplayAmount countdown that ticks (InvokeDisplayAmountChanged) and self-remove after
firing; the Balance gauge stays at 0, flips its title live through PowerLoc extra keys, and names the penalty.
"""
from __future__ import annotations

import sys

from btsgen.class_forge import point_btsgen_at_mod_contract

point_btsgen_at_mod_contract()

from btsgen import paths  # noqa: E402

_PASS = 0
_FAIL = 0
MOD_CODE = paths.VOCABULARY.parents[1] / "BlankTheSpireCode"


def check(cond: bool, msg: str) -> None:
    global _PASS, _FAIL
    if cond:
        _PASS += 1
    else:
        _FAIL += 1
        print(f"  FAIL: {msg}")


def _cs(*parts: str) -> str:
    return (MOD_CODE.joinpath(*parts)).read_text(encoding="utf-8")


def test_ripen_countdown() -> None:
    print("ripen countdown (gap #60):")
    tp = _cs("Powers", "ForgedTriggerPower.cs")
    check('Trigger?.Trigger == "ripen" ? PowerStackType.Counter : PowerStackType.Single' in tp, "a ripen power is Counter (so the icon draws a number)")
    check("public override int DisplayAmount =>" in tp and "_ripenLeft < 0 ? System.Math.Max(1, Trigger.Amount) : _ripenLeft" in tp,
          "DisplayAmount is the turns left (the full countdown before init)")
    check("InvokeDisplayAmountChanged(); // Phase BG" in tp and "[BG] ripen" in tp, "the tick refreshes the badge and logs [BG]")
    check("Owner.RemovePowerInternal(this);" in tp.split('t.Trigger == "ripen"', 1)[1].split("// gap #9", 1)[0], "a fired ripen removes itself")


def test_balance_gauge() -> None:
    print("balance gauge (gap #61):")
    bp = _cs("Powers", "ForgedBalancePower.cs")
    sv = bp.split("private void SetValue(", 1)[1].split("/// <summary>", 1)[0]
    check("RemovePowerInternal" not in sv, "SetValue no longer removes the gauge at 0")
    check("InvokeDisplayAmountChanged();" in sv, "... and refreshes the badge")
    check('public override LocString Title =>' in bp and '".titleDark"' in bp and '".titleLight"' in bp, "the title flips LIVE through a Title override")
    check('("titleDark", "🌑 Dark"), ("titleLight", "☀️ Light")' in bp, "the extra loc keys are registered via PowerLoc ExtraLoc")
    check('new PowerLoc("Balance", desc, desc,' in bp, "the baked title is the neutral 'Balance'")
    check("PENALTY: while it leans" in bp and "the name is which way" in bp, "the description names the penalty and reads the lean/pole")
    check("using MegaCrit.Sts2.Core.Localization;" in bp, "LocString is imported")


def main() -> int:
    test_ripen_countdown()
    test_balance_gauge()
    print(f"\n{_PASS} passed, {_FAIL} failed")
    return 1 if _FAIL else 0


def test_phase_bg_all() -> None:
    # Rule 0.10 (BH-1 audit): run the standalone main() under pytest too, so a check outside the
    # individual test_* functions can never go unrun again.
    global _PASS, _FAIL
    _PASS = _FAIL = 0
    assert main() == 0, f"{_FAIL} Phase BG check(s) failed - see the FAIL lines above"


if __name__ == "__main__":
    sys.exit(main())
