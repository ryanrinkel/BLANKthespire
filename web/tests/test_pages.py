"""Public pages: the Workshop-first /download, the /help walkthrough, and the shareable /deck/<slug> view.

These routes take no login and render straight off disk (plus, for /deck, one slug lookup), so the tests
here are about the template placeholders actually being substituted and the slug never reaching the page
unescaped.
"""
from __future__ import annotations

import json
import re

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
    """The default points at the BLANK the spire Workshop item itself, not the game's Workshop hub."""
    assert app_module.WORKSHOP_URL == "https://steamcommunity.com/sharedfiles/filedetails/?id=3803255976"


def test_workshop_short_link_redirects_to_the_item(client, app_module):
    r = client.get("/workshop")
    assert r.status_code == 302
    assert r.headers["Location"] == app_module.WORKSHOP_URL


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


def test_help_step_two_says_subscribe_on_the_workshop_first(client):
    """FORGE_FIRST_PLAN.md 3.5: the Workshop step left the pre-forge tutorial, so /help step 2 carries it."""
    body = client.get("/help").get_data(as_text=True)
    assert "the mod must be subscribed on" in body
    assert 'href="/workshop"' in body
    assert "Steam Workshop" in body


# --- /app (index.html) ----------------------------------------------------------------------------

def test_app_is_forge_first_with_a_hidden_pay_step_and_a_play_it_block(client):
    """FORGE_FIRST_PLAN.md Phase A: the concept box leads, the pay boxes sit in a hidden #pay-step with a
    "Change my tokens provider" opener, the chooser is gone, and the result carries the "Play it" install steps."""
    login(client)
    r = client.get("/app")
    assert r.status_code == 200
    body = r.get_data(as_text=True)
    assert 'id="pay-step" class="pay-step hidden"' in body
    assert 'id="pay-open"' in body
    assert 'id="pay-reason"' in body
    # The concept box comes before the pay step, which holds both boxes and comes before the one Forge button.
    assert body.index('id="concept"') < body.index('id="pay-step"') < body.index('id="forge-btn"')
    assert body.index('id="pay-step"') < body.index('id="forge-token"') < body.index('id="forge-byok"')
    assert body.index('id="forge-byok"') < body.index('id="forge-btn"') < body.index('id="pay-open"')
    assert body.count('id="forge-btn"') == 1
    # "Play it" under the code, with the Workshop link.
    assert '<h3 class="play-title">Play it</h3>' in body
    assert body.index('id="copy-code"') < body.index('class="play-how"')
    play = body[body.index('class="play-how"'):]
    play = play[:play.index("</div>")]
    assert 'href="/workshop"' in play and "Subscribe to the mod on Steam Workshop" in play
    assert "Import a class code" in play and 'href="/help"' in play
    # Retired: the chooser cards, the five-step tutorial's subscribe step, the old wording.
    assert 'id="chooser"' not in body
    assert 'id="tut-subscribe"' not in body
    assert not re.search(r"support\s+the\s+forge", body, re.I)  # the D5 wording sweep
    assert "Get a forge token" in body


# --- The Archive (FORGE_FIRST_PLAN.md Phase B) ------------------------------------------------------------

def test_archive_page_is_public_and_csp_clean(client):
    r = client.get("/archive")
    assert r.status_code == 200 and "text/html" in r.headers["Content-Type"]
    body = r.get_data(as_text=True)
    assert 'id="archive-grid"' in body and 'id="archive-empty"' in body
    assert "<h1>The Archive</h1>" in body and "<title>The Archive — BLANK the spire</title>" in body
    assert '<meta property="og:title" content="The Archive — BLANK the spire" />' in body
    assert "/static/archive.js" in body and "/static/featured.js" in body
    assert body.index("/static/featured.js") < body.index("/static/archive.js")
    assert 'href="/app"' in body and 'href="/download"' in body and 'href="/help"' in body
    # CSP: no inline script body, no on*= handlers.
    assert not re.search(r"<script(?![^>]*\ssrc=)[^>]*>\s*\S", body)
    assert not re.search(r"\son\w+\s*=\s*[\"']", body)


def test_every_header_links_the_archive(client, app_module):
    login(client)
    assert 'href="/archive"' in client.get("/app").get_data(as_text=True)
    for path in ("/help", "/download"):
        assert '<a class="tab" href="/archive">The Archive</a>' in client.get(path).get_data(as_text=True), path
    slug = _make_class(app_module, client)
    deck = client.get(f"/deck/{slug}").get_data(as_text=True)
    assert '<a class="tab" href="/archive">The Archive</a>' in deck
    assert "nav-more" not in deck and "More featured classes" not in deck


def test_landing_promotes_the_archive(client):
    body = client.get("/").get_data(as_text=True)
    assert '<h2 class="how-title">The Archive</h2>' in body
    assert 'href="/archive">Browse The Archive' in body
    assert "Or play a class from The Archive — no account needed." in body
    assert "Try a featured class" not in body and "featured class right now" not in body
    assert "Create Your Own Class" in body
    assert body.index("/static/featured.js") < body.index("/static/landing.js")


def test_app_has_the_nominate_button_and_the_admin_archive_card(client):
    login(client)
    body = client.get("/app").get_data(as_text=True)
    assert 'id="nominate" class="btn hidden"' in body and "Nominate for The Archive" in body
    assert body.index('id="share-link"') < body.index('id="nominate"')
    assert 'id="admin-archive" class="card hidden"' in body
    assert 'id="admin-nominations"' in body and 'id="admin-featured"' in body
    assert body.index('id="admin-users"') < body.index('id="admin-archive"')
    nav = body[body.index("<nav>"):body.index("</nav>")]
    assert nav.index('id="nav-library"') < nav.index('href="/archive"') < nav.index('id="nav-account"')


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


# --- favicon --------------------------------------------------------------------------------------

def test_favicon_ico_is_served_from_the_site_root(client):
    """Browsers request /favicon.ico regardless of the <link> tags, so the root path must serve the real
    multi-size icon (not a 404, and not an HTML error page)."""
    r = client.get("/favicon.ico")
    assert r.status_code == 200
    assert r.headers["Content-Type"].startswith("image/"), r.headers["Content-Type"]
    assert r.get_data()[:4] == b"\x00\x00\x01\x00"  # ICO magic


def test_every_static_page_links_the_favicon(app_module):
    """Every page we serve carries the icon <link>s, so no route shows the browser's blank default."""
    pages = sorted((app_module.WEB_DIR / "static").glob("*.html"))
    assert len(pages) >= 10, [p.name for p in pages]
    for page in pages:
        html = page.read_text(encoding="utf-8")
        assert 'rel="icon"' in html, page.name
        assert "/static/img/favicon-32.png" in html, page.name
        assert 'rel="apple-touch-icon"' in html, page.name


# --- pricing v3 copy rule (BH-1 audit): donor-facing copy never says "buy" / "purchase" --------------------
# The only sanctioned uses are the two NEGATIONS docs/plans/PRICING_V3_COPY.md itself prescribes. Identifiers
# (element ids, /api/purchases, the ?purchase= return flag) are not copy: HTML is checked as rendered text
# (tags, comments, scripts stripped) and JS only inside string literals that contain a space (i.e. prose).
_SANCTIONED = ("nothing to buy", "not purchases of goods or services")


def _banned_words():
    import re
    return re.compile(r"\b(buy\w*|bought|purchas\w*)\b", re.I)


def test_donor_facing_copy_never_says_buy_or_purchase(app_module):
    import re
    banned = _banned_words()
    static = app_module.WEB_DIR / "static"
    hits = []
    for page in sorted(static.glob("*.html")):
        s = re.sub(r"<!--.*?-->", "", page.read_text(encoding="utf-8"), flags=re.S)
        s = re.sub(r"<script.*?</script>|<style.*?</style>", "", s, flags=re.S)
        text = re.sub(r"<[^>]+>", " ", s)
        for ok in _SANCTIONED:
            text = text.replace(ok, "")
        hits += [f"{page.name}: ...{text[max(0, m.start() - 30):m.end() + 20]!r}" for m in banned.finditer(text)]
    lit = re.compile(r'"(?:[^"\\\n]|\\.)*"|\'(?:[^\'\\\n]|\\.)*\'|`(?:[^`\\]|\\.)*`')
    for js in sorted(static.glob("*.js")):
        src = re.sub(r"/\*.*?\*/", "", js.read_text(encoding="utf-8"), flags=re.S)
        src = re.sub(r"(?m)^\s*//.*$", "", src)
        for m in lit.finditer(src):
            prose = m.group(0)
            for ok in _SANCTIONED:
                prose = prose.replace(ok, "")
            if " " in prose and banned.search(prose):
                hits.append(f"{js.name}: {prose[:100]}")
    assert not hits, "donor-facing copy says buy/purchase (pricing v3 rule):\n" + "\n".join(hits)


def test_the_copy_rule_scanner_catches_a_violation():
    """The scanner above must not pass vacuously."""
    assert _banned_words().search("Bought 4 tokens") and _banned_words().search("purchase more")
    assert not _banned_words().search("buoyant busy")
