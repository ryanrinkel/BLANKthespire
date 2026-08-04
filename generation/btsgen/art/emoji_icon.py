"""Relic icon from an emoji — no image-generation tokens.

The relic call picks an `icon_emoji` (one emoji = a huge icon vocabulary for free); this module turns
it into a small PNG by fetching the matching Twemoji asset (72x72, MIT/CC-BY-4.0 — Twitter/X emoji
art via the maintained jdecked/twemoji fork, pinned + served by jsDelivr). Stdlib urllib only, like
backends/openai.py. Best-effort: any failure returns None and the mod keeps its shipped fallback icon.
"""
from __future__ import annotations

import urllib.error
import urllib.request
from pathlib import Path

_CDN = "https://cdn.jsdelivr.net/gh/jdecked/twemoji@15.1.0/assets/72x72/{code}.png"
_TIMEOUT_S = 10


def _candidate_codes(emoji: str) -> list[str]:
    """Twemoji file names are hyphen-joined lowercase codepoints. Assets usually OMIT the U+FE0F
    variation selector (except keycap-style sequences that need it), so try the verbatim sequence
    first, then the fe0f-stripped one."""
    cps = [ord(c) for c in emoji.strip()]
    if not cps:
        return []
    full = "-".join(f"{c:x}" for c in cps)
    bare = "-".join(f"{c:x}" for c in cps if c != 0xFE0F)
    return [c for i, c in enumerate([bare, full]) if c and c not in [bare, full][:i]]


def fetch_emoji_png(emoji: str, out_path: Path) -> Path | None:
    """Fetch the Twemoji PNG for `emoji` to `out_path`. Returns the path, or None on any failure."""
    for code in _candidate_codes(emoji):
        try:
            req = urllib.request.Request(_CDN.format(code=code), headers={"User-Agent": "btsgen"})
            with urllib.request.urlopen(req, timeout=_TIMEOUT_S) as resp:
                data = resp.read()
            if not data.startswith(b"\x89PNG"):
                continue
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_bytes(data)
            return out_path
        except (urllib.error.URLError, OSError, ValueError):
            continue
    return None
