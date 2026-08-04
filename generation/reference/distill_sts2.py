"""Distill the spire-codex StS2 card dump into a compact rarity-calibration digest.

Source: https://github.com/ptrlrd/spire-codex (community extraction of Slay the Spire 2
data). Game data (c) Mega Crit Games — used here as a noncommercial community design
reference only, never shipped or recombined into content.

Reads sts2_cards.json (the raw eng dump, checked in beside this script) and writes
sts2_rarity_examples.md — a ~25-card digest the card-generation prompt embeds to teach
the rarity ladder: what real commons/uncommons/rares FEEL like in power and complexity.
The digest calibrates power/complexity only; the generator still composes exclusively
from the engine's closed vocabulary.

Run from generation/:  uv run python reference/distill_sts2.py
Deterministic: same input -> same digest (sorted picks, no randomness).
"""
from __future__ import annotations

import json
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
SRC = HERE / "sts2_cards.json"
OUT = HERE / "sts2_rarity_examples.md"

_TAG = re.compile(r"\[/?[a-z]+\]")
_BUILD_AROUND = ("Whenever", "At the start", "At the end", "for each", "Every ", " all ")
# StS2-specific systems with no analogue here; examples using them teach nothing portable.
_OPAQUE = ("Summon", "Forge", "Orb", "Focus", "[star", "star:", "Ethereal", "other player",
           "Stance", "Mantra", "Scry", "Channel", "Wrath", "Calm", "Potion")


def clean(s: str) -> str:
    return " ".join(_TAG.sub("", s or "").split())


def pick(cards: list[dict], rarity: str, n_simple: int, n_build: int) -> list[dict]:
    """Deterministic picks: `n_simple` shortest-text cards spanning types, plus
    `n_build` build-around cards (engine text markers), all sorted by name."""
    pool = sorted((c for c in cards if c["rarity"] == rarity), key=lambda c: c["name"])
    by_len = sorted(pool, key=lambda c: (len(clean(c["description"])), c["name"]))
    out: list[dict] = []
    seen_types: dict[str, int] = {}
    for c in by_len:                                   # simple picks, max 2 per type
        if len(out) >= n_simple:
            break
        if seen_types.get(c["type"], 0) >= 2:
            continue
        seen_types[c["type"]] = seen_types.get(c["type"], 0) + 1
        out.append(c)
    builds = [c for c in pool
              if any(m in clean(c["description"]) for m in _BUILD_AROUND) and c not in out]
    out += builds[:n_build]
    return sorted(out, key=lambda c: c["name"])


def main() -> None:
    cards = json.loads(SRC.read_text())
    usable = [c for c in cards
              if c.get("rarity") in ("Common", "Uncommon", "Rare")
              and c.get("type") in ("Attack", "Skill", "Power")
              and c.get("description")
              and not any(tok in clean(c["description"]) for tok in _OPAQUE)]

    sections = [
        ("Common", "cheap single-purpose enablers: one clear effect, modest numbers",
         pick(usable, "Common", 5, 2)),
        ("Uncommon", "amplifiers: two effects, a condition, or a twist that rewards a theme",
         pick(usable, "Uncommon", 4, 3)),
        ("Rare", "archetype payoffs: build-arounds and splashy numbers you draft the deck for",
         pick(usable, "Rare", 3, 7)),
    ]

    lines = [
        "# Slay the Spire 2 — rarity calibration examples",
        "",
        "Source: spire-codex community extraction (v0.100.0-beta); game data (c) Mega Crit",
        "Games — noncommercial community design reference ONLY. These calibrate the POWER and",
        "COMPLEXITY ladder per rarity; they are NOT vocabulary (many reference mechanics this",
        "engine does not have).",
        "",
    ]
    for rarity, blurb, picks in sections:
        lines.append(f"## {rarity} — {blurb}")
        for c in picks:
            cost = "X" if c.get("is_x_cost") else c.get("cost", "?")
            lines.append(f"- {c['name']} ({c['type']}, {cost} energy): {clean(c['description'])}")
        lines.append("")
    OUT.write_text("\n".join(lines))
    total = sum(len(p) for _, _, p in sections)
    print(f"wrote {OUT.name}: {total} cards from {len(usable)} usable")


if __name__ == "__main__":
    main()
