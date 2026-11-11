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

Hops that are not plain links (``location.href = "/login"``, a form POST and its redirect, a server redirect)
drop the parameter, so there is a safety net here: a GET page request WITHOUT ``look`` whose ``Referer`` is a
same-origin URL carrying a valid ``look`` (the site sends ``Referrer-Policy: strict-origin-when-cross-origin``,
so same-origin navigations carry the full URL) is answered with a 302 to the same URL plus ``look=board``
(:func:`finish_page`), so the next page's Referer, and board.js, see it again. Only while the aliased
experiment has not ended; never for a non-GET or a non-200 page (those are just served with the look). The
server's own redirects and the hops that leave the site (OAuth state, the emailed sign-in link, Stripe's
return URLs) append it themselves through :func:`carried_look` + :func:`with_look`. Still nothing stored. A
visitor with no ``look`` anywhere (every hash-assigned visitor) never sees a redirect.

This module imports flask, experiments and skin_preview only — never app (app imports this).
"""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Callable
from urllib.parse import parse_qs, urlsplit

from flask import Response, request
from werkzeug.urls import iri_to_uri

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


# ------------------------------------------------------------------------------- carrying the share link

def look_live(look: str | None) -> bool:
    """A known look whose experiment is still in the registry and not ended (before the start counts)."""
    alias = LOOK_ALIASES.get(look or "")
    if not alias:
        return False
    name = alias.partition(":")[0]
    exp = next((e for e in experiments.EXPERIMENTS if e.name == name), None)
    return exp is not None and (exp.ended is None or experiments.today_utc() < exp.ended)


def _own_hosts() -> set[str]:
    """The netlocs this site answers on: the request's own Host (ProxyFix/nginx pass the public one through)
    plus BTSWEB_PUBLIC_URL's, so a proxy that rewrites Host still counts the public origin as ours."""
    hosts = {request.host.lower()}
    public = os.environ.get("BTSWEB_PUBLIC_URL", "").strip()
    if public:
        try:
            netloc = urlsplit(public).netloc.lower()
        except ValueError:
            netloc = ""
        if netloc:
            hosts.add(netloc)
    return hosts


def referer_look() -> str | None:
    """The valid ``look`` in a same-origin Referer's query, else None."""
    ref = request.headers.get("Referer", "")
    if not ref:
        return None
    try:
        parts = urlsplit(ref)
    except ValueError:
        return None
    if parts.scheme not in ("http", "https") or parts.netloc.lower() not in _own_hosts():
        return None
    values = parse_qs(parts.query).get(LOOK_PARAM) or [""]
    return values[0] if values[0] in LOOK_ALIASES else None


def carried_look() -> str | None:
    """The look this request carries — its own ``?look=`` or, failing that, its same-origin Referer's — while
    the experiment behind it is live; None otherwise (always None for a visitor who never had one)."""
    look = request.args.get(LOOK_PARAM)
    if look not in LOOK_ALIASES:
        look = referer_look()
    return look if look_live(look) else None


def with_look(url: str, look: str | None) -> str:
    """``url`` with ``look=<look>`` added to its query (kept before any ``#fragment``); unchanged when
    ``look`` is None or the url already names one. ``/app#account`` -> ``/app?look=board#account``."""
    if not look:
        return url
    base, hash_, frag = url.partition("#")
    path, q, query = base.partition("?")
    if LOOK_PARAM in parse_qs(query, keep_blank_values=True):
        return url
    query = f"{query}&{LOOK_PARAM}={look}" if query else f"{LOOK_PARAM}={look}"
    return f"{path}?{query}{hash_}{frag}"


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
    """Strip the arms not drawn, stamp data-ab, and answer with the no-shared-cache headers.

    The share-link net (module docstring): a GET 200 page with no ``look`` of its own, reached from a
    same-origin page that had one, is answered with a 302 to itself plus ``look=``; a non-GET or non-200
    answer is served with the Referer's look applied instead."""
    look = request.args.get(LOOK_PARAM)
    if look is None:
        carried = referer_look()
        if carried and look_live(carried):
            if request.method == "GET" and status == 200:
                return _look_redirect(carried)
            look = carried
    override = experiments.parse_override(request.args.get("ab"))
    alias = LOOK_ALIASES.get(look or "")
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
    resp.headers["Vary"] = "User-Agent, Referer"   # Referer: the share-link net above
    return resp


def _look_redirect(look: str) -> Response:
    """302 to this same path + query with ``look=`` appended. No cookie, never cached for someone else."""
    query = request.query_string.decode("latin-1")
    target = iri_to_uri(request.path) + "?" + (f"{query}&" if query else "") + f"{LOOK_PARAM}={look}"
    resp = Response("", status=302)
    resp.headers["Location"] = target
    resp.headers["Cache-Control"] = "private, no-cache"
    resp.headers["Vary"] = "User-Agent, Referer"
    return resp


def serve_page(name: str, *, page: str, transform: Callable[[str], str] | None = None,
               status: int = 200) -> Response:
    """Serve static/<name> for route ``page``; ``transform`` (placeholder stamping) runs before the strip."""
    html = read_static(name)
    if transform is not None:
        html = transform(html)
    return finish_page(html, page=page, status=status)
