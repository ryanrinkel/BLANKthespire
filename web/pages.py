"""The one helper that serves the public HTML pages (docs/plans/AB_TESTING_PLAN.md 3.3).

Every page that can carry an experiment goes through :func:`serve_page` (or :func:`finish_page` when the
route builds the HTML itself, like /deck/<slug>): the file is read (cached by mtime + size — the files only
change on a deploy), the visitor's arms are computed from IP + User-Agent by ``experiments.served_arms``,
every ``<!--ab name:arm-->...<!--/ab-->`` block that was not drawn is dropped, the drawn arms are stamped as
``data-ab="hero:b"`` on the ``<html>`` tag (only for pages with an experiment in the registry), and the answer
says ``Cache-Control: private, no-cache`` + ``Vary: User-Agent`` so no browser or proxy hands one visitor's arm
to another. Nothing is set on the visitor's device: no cookie, ever (asserted by tests/test_experiments.py).

``?ab=hero:b`` forces an arm for THAT request only (operator preview; the admin badge carries the links).

Sitewide experiments (``Experiment.sitewide``, e.g. a whole-site skin) draw their arm on EVERY page that goes
through here, so their blocks resolve the same way on /, /login, /app and the rest.

Local design preview: with ``BTSWEB_SKIN_PREVIEW=b`` (skin_preview.py) every page is served as if the visitor
drew ``skin:b`` — the same strip as a real arm — and ``data-look="board"`` is stamped on ``<html>``. Unset, nothing
changes.

Share link: ``?look=board`` on any page is a neutral alias of ``?ab=skin:b`` for that one request (nothing is
stored anywhere; board.js carries the parameter on to same-origin links so a visitor who arrived with it keeps
the look while browsing). Like ``?ab=``, it works from the deploy day (before the start date too) and stops
mattering once ``skin`` has ended (its winner is then served to everyone). tools/traffic_report.py drops an IP
that sent ``look=`` that day from the experiment's numbers, as it does for ``ab=``.

This module imports flask, experiments and skin_preview only — never app (app imports this).
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Callable

from flask import Response, request

import experiments
import skin_preview

STATIC_DIR = Path(__file__).resolve().parent / "static"

# name -> (mtime_ns, size, text)
_CACHE: dict[str, tuple[int, int, str]] = {}

_HTML_TAG_RE = re.compile(r"<html\b([^>]*)>", re.IGNORECASE)

# The share link: ?look=board == ?ab=skin:b for that request (unknown values are ignored).
LOOK_PARAM = "look"
LOOK_ALIASES = {"board": "skin:b"}


def client_ip() -> str:
    """The caller's address: X-Forwarded-For's first hop (nginx's $remote_addr), else the socket peer."""
    return request.headers.get("X-Forwarded-For", request.remote_addr or "?").split(",")[0].strip()


def _user_agent() -> str:
    return request.headers.get("User-Agent", "")


def read_static(name: str) -> str:
    """static/<name> as text, cached until its mtime or size changes."""
    path = STATIC_DIR / name
    st = path.stat()
    hit = _CACHE.get(name)
    if hit is not None and hit[0] == st.st_mtime_ns and hit[1] == st.st_size:
        return hit[2]
    text = path.read_text(encoding="utf-8")
    _CACHE[name] = (st.st_mtime_ns, st.st_size, text)
    return text


def _has_experiment(page: str) -> bool:
    return any(experiments.applies_to(e, page) for e in experiments.EXPERIMENTS)


def _stamp_data_ab(html: str, value: str) -> str:
    def repl(m: re.Match) -> str:
        attrs = re.sub(r'\s+data-ab="[^"]*"', "", m.group(1))
        return f'<html{attrs} data-ab="{value}">'
    return _HTML_TAG_RE.sub(repl, html, count=1)


def arms_for_request(page: str, override: dict[str, str] | None = None) -> dict[str, str]:
    return experiments.served_arms(client_ip(), _user_agent(), page, override)


def page_arms() -> dict[str, str]:
    """The arms the CURRENT request would be served for ``request.path`` (no ``?ab=`` override)."""
    return arms_for_request(request.path)


def finish_page(html: str, *, page: str, status: int = 200) -> Response:
    """Strip the arms not drawn, stamp data-ab, and answer with the no-shared-cache headers."""
    override = experiments.parse_override(request.args.get("ab"))
    alias = LOOK_ALIASES.get(request.args.get(LOOK_PARAM, ""))
    if alias:   # an explicit ?ab= for the same experiment wins
        override = {**experiments.parse_override(alias), **override}
    arms = arms_for_request(page, override)
    preview = skin_preview.active()
    # Always strip, so markers for an experiment that left the registry never leak into the page.
    html = experiments.strip_arms(html, {**arms, "skin": preview} if preview else arms)
    if _has_experiment(page):
        value = experiments.data_ab(arms)
        if value:
            html = _stamp_data_ab(html, value)
    if preview:
        html = skin_preview.stamp(html, preview)
    resp = Response(html, status=status, mimetype="text/html")
    resp.headers["Content-Type"] = "text/html; charset=utf-8"
    resp.headers["Cache-Control"] = "private, no-cache"
    resp.headers["Vary"] = "User-Agent"
    return resp


def serve_page(name: str, *, page: str, transform: Callable[[str], str] | None = None,
               status: int = 200) -> Response:
    """Serve static/<name> for route ``page``; ``transform`` (placeholder stamping) runs before the strip."""
    html = read_static(name)
    if transform is not None:
        html = transform(html)
    return finish_page(html, page=page, status=status)
