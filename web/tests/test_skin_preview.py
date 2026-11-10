"""The local skin preview (skin_preview.py, BTSWEB_SKIN_PREVIEW=b): forces arm b of the sitewide `skin`
experiment's blocks on every page through pages.finish_page; unset it changes nothing."""
from __future__ import annotations

import re

import pytest

import experiments
from conftest import login

PAGES = ("/", "/login", "/download", "/help", "/archive", "/terms", "/privacy")
SKIN_CSS, SKIN_JS = '<link rel="stylesheet" href="/static/board.css?v=', '<script src="/static/board.js?v='


@pytest.fixture(autouse=True)
def before_the_skin_test(monkeypatch):
    """Pin 'today' before the real `skin` experiment starts, so arm a is what every visitor draws."""
    monkeypatch.setattr(experiments, "today_utc", lambda: "2026-11-10")


@pytest.fixture
def no_skin(monkeypatch):
    monkeypatch.delenv("BTSWEB_SKIN_PREVIEW", raising=False)


def _bodies(client):
    """The public pages signed out (/login redirects a signed-in visitor), then /app signed in."""
    for path in PAGES:
        yield path, client.get(path)
    login(client)
    yield "/app", client.get("/app")


def test_unset_adds_nothing_anywhere(client, no_skin):
    for path, r in _bodies(client):
        assert r.status_code == 200, path
        body = r.get_data(as_text=True)
        assert "board.css" not in body and "board.js" not in body and "data-look" not in body and "<!--ab" not in body, path


def test_unset_app_is_the_file_with_its_blocks_stripped(client, app_module, no_skin):
    login(client)
    r = client.get("/app")
    raw = (app_module.WEB_DIR / "static" / "index.html").read_text(encoding="utf-8")
    want = experiments.strip_arms(raw, {})
    want = re.sub(r"<html\b([^>]*)>", r'<html\1 data-ab="skin:a">', want, count=1)   # the sitewide stamp
    assert r.get_data(as_text=True) == want
    assert r.headers["Cache-Control"] == "private, no-cache"


def test_set_links_the_skin_on_every_page(client, monkeypatch):
    monkeypatch.setenv("BTSWEB_SKIN_PREVIEW", "b")
    for path, r in _bodies(client):
        assert r.status_code == 200, path
        body = r.get_data(as_text=True)
        assert body.count(SKIN_CSS) == 1, path
        link = body.index(SKIN_CSS)
        assert body.index("/static/style.css") < link < body.index("</head>"), path
        assert re.search(r'<html\b[^>]*\sdata-look="board"', body), path
        # the menu script: once, deferred, before </body> and after every script the page carries itself
        assert body.count(SKIN_JS) == 1, path
        script = body.index(SKIN_JS)
        assert '" defer></script>' in body[script:script + 80] and script < body.rindex("</body>"), path
        own = [m.start() for m in re.finditer(r'<script src="/static/(?!board\.js)', body)]
        assert all(pos < script for pos in own), path
        assert "<!--ab" not in body, path


def test_set_uses_the_board_hero_copy(client, monkeypatch):
    monkeypatch.setenv("BTSWEB_SKIN_PREVIEW", "b")
    body = client.get("/").get_data(as_text=True)
    assert 'data-i18n="landing.hero.tagline_lead"' in body and 'data-i18n="landing.hero.subtitle_full"' in body
    assert 'data-i18n="landing.hero.tagline"' not in body
    # the question comes before the board in the markup (reading order), the sign-in note stays for landing.js
    assert body.index("landing.hero.tagline_lead") < body.index('id="board"')
    assert 'id="splash-note"' in body


def test_unknown_skin_value_is_ignored(client, monkeypatch):
    monkeypatch.setenv("BTSWEB_SKIN_PREVIEW", "zzz")
    body = client.get("/").get_data(as_text=True)
    assert "data-look" not in body and "board.css" not in body


def test_set_leaves_json_alone(client, monkeypatch):
    monkeypatch.setenv("BTSWEB_SKIN_PREVIEW", "b")
    r = client.get("/api/me")
    assert r.is_json and "skin" not in r.get_data(as_text=True)
