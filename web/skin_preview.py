"""Local-only design preview of the "board" look (arm b of the sitewide experiment ``skin``).

Every page carries the look's assets inside ``<!--ab skin:b-->...<!--/ab-->`` blocks (board.css after style.css,
the deferred board.js before ``</body>``; landing.html also has its board hero copy). pages.finish_page keeps
or drops them per the visitor's arm. With ``BTSWEB_SKIN_PREVIEW=b`` in the server's environment it strips them
as if every request drew ``skin:b`` (whatever the registry says) and stamps ``data-look="board"`` on ``<html>``,
so the look can be browsed everywhere locally. Unset (production) it does nothing. Read per request.
"""
from __future__ import annotations

import os
import re

ENV = "BTSWEB_SKIN_PREVIEW"
SKINS = ("b",)
_HTML_TAG_RE = re.compile(r"<html\b([^>]*)>", re.IGNORECASE)


def active() -> str:
    """The skin arm to force for every request, or "" (the default, and the only production state)."""
    name = os.environ.get(ENV, "").strip().lower()
    return name if name in SKINS else ""


def stamp(html: str, skin: str) -> str:
    """Mark the page as previewed (``skin`` is the forced arm; the attribute value stays neutral)."""
    return _HTML_TAG_RE.sub(lambda m: f'<html{m.group(1)} data-look="board">', html, count=1)
