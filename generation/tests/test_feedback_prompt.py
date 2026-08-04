"""Offline tests for the feedback loop's prompt side — no API key needed.

Run:  uv run python -m tests.test_feedback_prompt     (from generation/)
Exits nonzero on any failure. Covers feedback_section(): missing/empty file, great vs
flagged rendering, the optional player `note` riding each line (the in-game "why" box,
2026-06-11), and the max_entries window.
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

from btsgen import contract, paths

_PASS = 0
_FAIL = 0


def check(cond: bool, msg: str) -> None:
    global _PASS, _FAIL
    if cond:
        _PASS += 1
    else:
        _FAIL += 1
        print(f"  FAIL: {msg}")


def _entry(card_id: str, category: str, note: str | None = None) -> str:
    d = {"card_id": card_id, "name": card_id.replace("_", " ").title(),
         "character": "test_class", "source": "llm", "category": category,
         "card": {"effects": [{"op": "damage", "amount": 6}]}}
    if note:
        d["note"] = note
    return json.dumps(d)


def main() -> int:
    real = paths.FEEDBACK_FILE
    try:
        with tempfile.TemporaryDirectory() as td:
            paths.FEEDBACK_FILE = Path(td) / "card_feedback.jsonl"

            print("feedback_section without/with ratings:")
            check(contract.feedback_section() == "", "missing file -> empty section")
            paths.FEEDBACK_FILE.write_text("not json\n\n")
            check(contract.feedback_section() == "", "malformed-only file -> empty section")

            paths.FEEDBACK_FILE.write_text("\n".join([
                _entry("great_card", "great", note="the X-cost scaling feels amazing"),
                _entry("op_card", "overpowered", note="12 damage for 0 energy"),
                _entry("meh_card", "underpowered"),
                "not json",
            ]) + "\n")
            s = contract.feedback_section()
            check("PLAYER FEEDBACK" in s, "section renders when entries exist")
            check("great_card" in s and "emulate" in s, "great ratings render as examples")
            check('[player: "the X-cost scaling feels amazing"]' in s,
                  "a note on a great rating is quoted")
            check('overpowered -- "12 damage for 0 energy"' in s,
                  "a note on a flag is quoted next to the complaint")
            check("[player flag: underpowered]" in s, "a note-less flag renders plain")

            print("max_entries window:")
            paths.FEEDBACK_FILE.write_text(
                "\n".join(_entry(f"card_{i}", "confusing") for i in range(30)) + "\n")
            s = contract.feedback_section(max_entries=5)
            check("card_29" in s and "card_24" not in s,
                  "only the most recent entries are kept")
    finally:
        paths.FEEDBACK_FILE = real
    print(f"\n{_PASS} passed, {_FAIL} failed")
    return 1 if _FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
