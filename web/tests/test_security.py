"""Hardening: CSRF header check, security headers, body limit, POST-only logout, retired hosted mode, the
share slug, BYOK keys never landing in any table, the SSRF guard on BOTH forge paths, and /healthz."""
from __future__ import annotations

import pytest

from conftest import DB_PATH, H, login, sse_events


def test_mutating_api_calls_need_the_csrf_header(client):
    login(client)
    assert client.post("/api/checkout", json={"pack": "pack_5"}).status_code == 403
    assert client.patch("/api/classes/1", json={"name": "x"}).status_code == 403
    assert client.delete("/api/classes/1").status_code == 403
    assert client.post("/api/forge-class", json={"concept": "x", "mode": "fake"}).status_code == 403
    # GETs and the Stripe webhook (signature-authenticated, not under /api/) are exempt
    assert client.get("/api/me").status_code == 200
    assert client.post("/webhook/stripe", data=b"{}").status_code != 403


def test_security_headers_on_every_response(client):
    for path in ("/", "/app", "/download", "/terms", "/api/me", "/healthz"):
        h = client.get(path).headers
        assert h["X-Content-Type-Options"] == "nosniff", path
        assert h["X-Frame-Options"] == "DENY", path
        assert "frame-ancestors 'none'" in h["Content-Security-Policy"], path
        assert "script-src 'self'" in h["Content-Security-Policy"], path
        assert "Referrer-Policy" in h and "Permissions-Policy" in h, path


def test_pages_have_no_inline_script(app_module):
    """The CSP forbids inline JS, so a stray onclick= or <script> body would silently break a page."""
    import re
    static = app_module.WEB_DIR / "static"
    for page in static.glob("*.html"):
        html = page.read_text(encoding="utf-8")
        assert not re.search(r"\son\w+\s*=\s*[\"']", html), page.name
        assert not re.search(r"<script(?![^>]*\ssrc=)[^>]*>\s*\S", html), page.name


def test_body_limit(client):
    login(client)
    big = {"concept": "x" * (300 * 1024), "mode": "fake"}
    assert client.post("/api/forge-class", json=big, headers=H).status_code == 413


def test_logout_is_post_only(client):
    login(client)
    assert client.get("/logout").status_code == 405
    assert client.post("/logout").status_code == 302
    assert client.get("/api/me").get_json()["user"] is None


def test_hosted_mode_is_gone_and_unknown_modes_rejected(client):
    login(client)
    r = client.post("/api/forge-class", json={"concept": "x", "mode": "hosted"}, headers=H)
    assert r.status_code == 410
    r = client.post("/api/forge-class", json={"concept": "x", "mode": "bogus"}, headers=H)
    assert r.status_code == 400


def test_deck_share_uses_unguessable_slug_and_hides_the_id(client, app_module, stub_forge):
    login(client, "share@example.com")
    ev = sse_events(client.post("/api/forge-class", json={"concept": "x", "mode": "token"}, headers=H))
    res = ev[-1][1]
    slug, cid = res["slug"], res["id"]
    assert len(slug) >= 20
    anon = app_module.app.test_client()  # no login: sharing is public
    d = anon.get(f"/api/deck/{slug}").get_json()
    assert d["name"] == res["name"] and d["code"] == res["code"] and "id" not in d
    assert anon.get(f"/api/deck/{cid}").status_code == 404   # numeric ids no longer resolve
    assert anon.get("/api/deck/").status_code == 404
    # the owner's list view carries the slug so the UI can build a share link
    rows = client.get("/api/classes").get_json()["classes"]
    assert any(r["slug"] == slug for r in rows)


def test_existing_classes_get_slugs_backfilled(app_module):
    from models import ForgedClass
    import db
    with app_module.session_scope() as s:
        cls = ForgedClass(user_id=1, name="old", concept="c", bundle_json="{}", code="BTSC.x", slug=None)
        s.add(cls)
        s.flush()
        cid = cls.id
    db._backfill_slugs()
    with app_module.session_scope() as s:
        assert s.query(ForgedClass).filter_by(id=cid).one().slug


def test_byok_key_never_lands_in_the_database(client, app_module, stub_forge):
    login(client, "keys@example.com")
    secret = "sk-ant-SUPERSECRET-0123456789abcdef"
    ev = sse_events(client.post("/api/forge-class", headers=H,
                                json={"concept": "x", "mode": "anthropic",
                                      "key": {"api_key": secret, "model": "claude-x"}}))
    assert ev[-1][0] == "result"
    # flush SQLite's WAL into the main file, then scan every byte of it
    import db
    db.engine.dispose()
    import sqlite3
    con = sqlite3.connect(DB_PATH)
    con.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    con.close()
    assert secret.encode() not in DB_PATH.read_bytes()


@pytest.mark.parametrize("url", ["http://127.0.0.1:11434/v1", "http://localhost/v1", "http://169.254.169.254/",
                                 "ftp://example.com/v1", "https:///nohost"])
def test_ssrf_guard_on_both_forge_paths(url):
    import forge
    key = {"base_url": url, "api_key": "k", "model": "m"}
    with pytest.raises(forge.ForgeError):
        forge._build_generators(key, hosted=False, fake=False)      # one-shot path
    with pytest.raises(forge.ForgeError):
        forge._make_gen_factory(key, hosted=False, fake=False)      # staged path
    with pytest.raises(forge.ForgeError):
        forge.list_models(url, "k")


def test_healthz(client, app_module, monkeypatch):
    r = client.get("/healthz")
    assert r.status_code == 200 and r.get_json()["db"] is True
    monkeypatch.setattr(app_module, "db_ping", lambda: False)
    assert client.get("/healthz").status_code == 503


def test_feedback_is_rate_limited(client, app_module, stub_forge, monkeypatch):
    login(client, "fb@example.com")
    res = sse_events(client.post("/api/forge-class", json={"concept": "x", "mode": "token"}, headers=H))[-1][1]
    card_id = res["cards"][0]["id"]
    monkeypatch.setattr(app_module, "FEEDBACK_HOURLY_CAP", 2)
    body = {"class_id": res["id"], "card_id": card_id, "category": "great", "note": "n" * 600}
    assert client.post("/api/card-feedback", json=body, headers=H).status_code == 200
    assert client.post("/api/card-feedback", json=body, headers=H).status_code == 200
    assert client.post("/api/card-feedback", json=body, headers=H).status_code == 429


def test_download_page_stamps_version_from_manifest(client, app_module):
    html = client.get("/download").get_data(as_text=True)
    assert "{{VERSION}}" not in html
    assert app_module.mod_version() in html and app_module.mod_version().startswith("v")
