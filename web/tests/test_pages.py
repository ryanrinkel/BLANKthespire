"""Public pages: the Workshop-first /download, the /help walkthrough, and the shareable /deck/<slug> view.

These routes take no login and render straight off disk (plus, for /deck, one slug lookup), so the tests
here are about the template placeholders actually being substituted and the slug never reaching the page
unescaped.
"""
from __future__ import annotations

import json

from conftest import login


def _make_class(app_module, client, *, char_name="The Tempest", description="A storm-caller.",
                name="The Tempest", code="BTSC.6.FAKEPAYLOAD.c0953037") -> str:
    """Insert one forged class straight through the session and hand back its share slug."""
    from models import ForgedClass, User, new_slug
    login(client)  # creates the dev user if this is the first test to need one
    slug = new_slug()
    with app_module.session_scope() as s:
        user_id = s.query(User).filter_by(email="dev@example.com").one().id
        bundle = {"kind": "class", "character": {"name": char_name, "description": description},
                  "cards": [], "archetypes": []}
        s.add(ForgedClass(user_id=user_id, name=name, concept="a storm-caller",
                          bundle_json=json.dumps(bundle), code=code, slug=slug))
    return slug


# --- /download ------------------------------------------------------------------------------------

def test_download_leads_with_the_workshop_and_keeps_the_zip(client, app_module):
    r = client.get("/download")
    assert r.status_code == 200
    body = r.get_data(as_text=True)
    assert "Steam Workshop" in body
    assert app_module.WORKSHOP_URL in body
    assert app_module.GITHUB_URL in body
    assert f"{app_module.GITHUB_URL}/issues" in body
    # The manual-install fallback still offers the versioned zip, collapsed behind <details>.
    assert f"BlankTheSpire-{app_module.mod_version()}.zip" in body
    assert "Manual install (advanced)" in body
    # Every placeholder is substituted server-side.
    for ph in ("{{VERSION}}", "{{WORKSHOP_URL}}", "{{GITHUB_URL}}"):
        assert ph not in body


def test_workshop_url_env_default(app_module):
    """The default points at the STS2 Workshop hub until the item itself is uploaded."""
    assert app_module.WORKSHOP_URL.startswith("https://steamcommunity.com/")
    assert "2868840" in app_module.WORKSHOP_URL


def test_download_links_to_help(client):
    body = client.get("/download").get_data(as_text=True)
    assert 'href="/help"' in body


# --- /help ----------------------------------------------------------------------------------------

def test_help_page_explains_where_the_code_goes(client):
    r = client.get("/help")
    assert r.status_code == 200
    body = r.get_data(as_text=True)
    assert "Import a class code" in body
    assert "Where do I paste my code?" in body
    assert "BTSC." in body
    # The screenshot slots ship before the screenshots do.
    assert "/static/img/help/step-1.png" in body
    assert "/static/img/help/step-6.png" in body


def test_help_needs_no_login(client):
    assert client.get("/help").status_code == 200


# --- /deck/<slug> ---------------------------------------------------------------------------------

def test_deck_unknown_slug_is_404(client):
    r = client.get("/deck/nope-there-is-no-such-slug")
    assert r.status_code == 404
    assert "text/html" in r.headers["Content-Type"]
    assert "not" in r.get_data(as_text=True).lower()


def test_deck_page_renders_unfurl_tags_and_the_fetch_url(client, app_module):
    slug = _make_class(app_module, client, char_name='Storm & Ash "Tempest"',
                       description="A storm-caller who channels lightning.")
    r = client.get(f"/deck/{slug}")
    assert r.status_code == 200
    body = r.get_data(as_text=True)
    # The class name lands in og:title, HTML-escaped (quote=True, so the " is escaped too).
    assert '<meta property="og:title" content="Storm &amp; Ash &quot;Tempest&quot;" />' in body
    assert 'content="A storm-caller who channels lightning."' in body
    assert '<meta property="og:site_name" content="BLANK the spire" />' in body
    assert 'name="twitter:card" content="summary_large_image"' in body
    assert f'<meta property="og:url" content="http://testserver/deck/{slug}" />' in body
    # The client-side renderer needs the slug to fetch the class.
    assert f"/api/deck/{slug}" in body
    # No placeholder survives, and the shared render markup is present for render.js to fill.
    for ph in ("{{TITLE}}", "{{DESC}}", "{{IMAGE}}", "{{URL}}", "{{SLUG}}"):
        assert ph not in body
    assert 'id="r-code"' in body and 'id="copy-code"' in body and 'id="result"' in body
    assert "/static/render.js" in body
    assert "/static/app.js" not in body


def test_deck_page_falls_back_to_the_row_name_and_truncates_the_blurb(client, app_module):
    long_desc = "poison " * 60
    slug = _make_class(app_module, client, char_name="", description=long_desc, name="Row Name")
    body = client.get(f"/deck/{slug}").get_data(as_text=True)
    assert '<meta property="og:title" content="Row Name" />' in body
    assert "…" in body  # the ellipsis the truncation appends
    assert long_desc.strip() not in body


def test_deck_page_has_no_splash_meta_when_there_is_no_art(client, app_module):
    slug = _make_class(app_module, client)
    body = client.get(f"/deck/{slug}").get_data(as_text=True)
    assert '<meta property="og:image" content="" />' in body


def test_deck_slug_with_script_tags_is_rejected(client):
    """A malformed slug never reaches the page — the route 404s and nothing is echoed back."""
    for path in ("/deck/%3Cscript%3Ealert(1)%3C/script%3E", "/deck/%3Cscript%3E", "/deck/%20"):
        r = client.get(path)
        assert r.status_code == 404, path
        assert "<script>" not in r.get_data(as_text=True), path
