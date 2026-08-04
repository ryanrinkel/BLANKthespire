"""Decode BTSC class code(s) into a readable card list — for comparing forged classes.

    cd generation
    uv run python tools/show_cards.py scratch/ab_<slug>.md          # both legs from an A/B report
    uv run python tools/show_cards.py scratch/silent_shatter.btsc.txt
    uv run python tools/show_cards.py BTSC.17.eyJ...                 # a raw code on the command line

Works on any A/B report (extracts each '## <leg> — BTSC code' block) or any file/string holding a BTSC code.
Pure decode (no LLM, no network)."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from btsgen.bts1 import decode

_RARITY_ORDER = {"basic": 0, "common": 1, "uncommon": 2, "rare": 3}


def _table(bundle: dict, label: str) -> str:
    ch = bundle.get("character", {})
    cards = bundle.get("cards", [])
    rel = bundle.get("relic")
    rel_s = f", relic: {rel.get('name')}" if isinstance(rel, dict) else ""
    rows = sorted(cards, key=lambda c: (_RARITY_ORDER.get(c.get("rarity"), 9), str(c.get("name", "")).lower()))
    out = [f"### {label} — {ch.get('name', '?')} ({ch.get('max_hp', '?')} HP, {len(cards)} cards{rel_s})", "",
           "| # | card | type | rarity | cost | text / effects |",
           "|---|------|------|--------|------|----------------|"]
    for i, c in enumerate(rows, 1):
        text = c.get("text") or c.get("description") or ""
        if not text:
            text = " · ".join(str(e.get("op", "")) for e in (c.get("effects") or []) if isinstance(e, dict))
        text = str(text).replace("|", "/")[:90]
        out.append(f"| {i} | {c.get('name','?')} | {c.get('type','?')} | {c.get('rarity','?')} | "
                   f"{c.get('cost','?')} | {text} |")
    return "\n".join(out) + "\n"


def _codes_from(arg: str) -> list[tuple[str, str]]:
    """Return [(label, code), ...] from a report .md (per-leg code blocks), a code file, or a raw code string."""
    p = Path(arg)
    if p.exists():
        txt = p.read_text(encoding="utf-8")
        # A/B report: '## <leg> — BTSC code ... ```<code>```'
        blocks = re.findall(r"##\s*(\w+)\s*—\s*BTSC code.*?```\s*(BTSC\.[^\s`]+)\s*```", txt, re.DOTALL)
        if blocks:
            return [(leg, code) for leg, code in blocks]
        m = re.search(r"(BTSC\.[^\s`]+)", txt)  # a plain .btsc.txt file
        if m:
            return [(p.stem, m.group(1))]
        raise SystemExit(f"no BTSC code found in {arg}")
    if arg.startswith("BTSC."):
        return [("code", arg)]
    raise SystemExit(f"not a file or a BTSC code: {arg}")


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 2
    for arg in argv:
        for label, code in _codes_from(arg):
            try:
                json_text, kind = decode(code)
            except ValueError as e:
                print(f"### {label} — could not decode: {e}\n")
                continue
            if kind != "class":
                print(f"### {label} — not a class code (kind={kind})\n")
                continue
            print(_table(json.loads(json_text), label))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
