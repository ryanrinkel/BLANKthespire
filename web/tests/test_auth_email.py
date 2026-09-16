"""Email magic links: the start endpoint, the render-then-consume split, expiry, and the rate limiter.

No mail ever leaves the process — `auth._send_magic_link` is swapped for a capture stub and `mail_configured`
is forced True (conftest pins the env at import, so the real vars are absent). The two paths that matter are
tested separately: with "mail" configured the link is only in the stub's capture; under the dev bypass with no
mail it comes back in the JSON.

Emails are unique per test: the SQLite database is session-scoped and rule 3 links on users.email.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from conftest import H, login


@pytest.fixture()
def mail(monkeypatch):
    """Pretend Resend is configured; collect (email, url) instead of sending. Returns the capture list."""
    import auth
    sent: list[tuple[str, str]] = []
    monkeypatch.setattr(auth, "mail_configured", lambda: True)
    monkeypatch.setattr(auth, "_send_magic_link", lambda email, url: sent.append((email, url)))
    return sent


def start(client, email: str):
    return client.post("/api/auth/email/start", json={"email": email}, headers=H)


def _links(app_module, email: str) -> list:
    """The login_links rows for an address, as plain tuples (the session closes before we read them)."""
    from models import LoginLink
    with app_module.session_scope() as s:
        rows = s.query(LoginLink).filter_by(email=email).order_by(LoginLink.id).all()
        return [(r.token_hash, r.expires_at, r.used_at) for r in rows]


def _token_of(url: str) -> str:
    return url.rsplit("/", 1)[-1]


# --- the start endpoint -----------------------------------------------------------------------------

def test_start_stores_one_link_and_sends_one_mail(client, app_module, mail):
    r = start(client, "  Start@Example.com ")
    assert r.status_code == 200
    assert r.get_json() == {"ok": True, "message": "Check your inbox."}  # uniform: no link, no hints

    rows = _links(app_module, "start@example.com")
    assert len(rows) == 1 and rows[0][2] is None
    assert len(mail) == 1
    to, url = mail[0]
    assert to == "start@example.com"
    assert url.startswith("http://testserver/auth/email/") and len(_token_of(url)) > 20


@pytest.mark.parametrize("bad", ["nope", "a@b", "a b@c.d", "", "two@@example.com", "x@.com"])
def test_bad_syntax_still_answers_the_same_and_stores_nothing(client, app_module, mail, bad):
    """A typo must not be distinguishable from a real send, and must not cost a row or an email."""
    r = start(client, bad)
    assert r.status_code == 200 and r.get_json()["ok"] is True
    assert mail == []
    from models import LoginLink
    with app_module.session_scope() as s:
        assert s.query(LoginLink).filter_by(email=bad.strip().lower()).count() == 0


def test_start_needs_the_csrf_header(client, mail):
    assert client.post("/api/auth/email/start", json={"email": "csrf@example.com"}).status_code == 403
    assert mail == []


def test_start_is_503_when_email_sign_in_is_off(client, monkeypatch):
    """No mail and no dev bypass ⇒ the form is not offered and the endpoint refuses outright."""
    import auth
    monkeypatch.setattr(auth, "_dev_auth_enabled", lambda: False)  # mail_configured() is already False here
    r = start(client, "off@example.com")
    assert r.status_code == 503 and "not configured" in r.get_json()["error"]


def test_dev_auth_without_mail_returns_the_link_instead_of_sending(client, monkeypatch):
    import auth
    sent = []
    monkeypatch.setattr(auth, "_send_magic_link", lambda *a: sent.append(a))
    body = start(client, "devlink@example.com").get_json()
    assert sent == []
    assert body["ok"] is True and body["link"].startswith("http://testserver/auth/email/")


def test_api_me_advertises_email_login(client):
    assert client.get("/api/me").get_json()["email_login"] is True


# --- clicking the link ------------------------------------------------------------------------------

def test_get_renders_the_continue_form_without_consuming(client, app_module, mail):
    start(client, "render@example.com")
    url = mail[0][1]
    r = client.get(f"/auth/email/{_token_of(url)}")
    assert r.status_code == 200 and b'method="post"' in r.data and b"Continue to" in r.data
    assert _links(app_module, "render@example.com")[0][2] is None  # used_at still NULL: a scanner may GET


def test_post_signs_in_and_burns_the_link(client, app_module, mail):
    start(client, "consume@example.com")
    token = _token_of(mail[0][1])

    r = client.post(f"/auth/email/{token}")
    assert r.status_code == 302 and r.headers["Location"].endswith("/app")
    me = client.get("/api/me").get_json()["user"]
    assert me["email"] == "consume@example.com"
    assert me["identities"] == [{"provider": "email", "label": "consume@example.com"}]
    assert _links(app_module, "consume@example.com")[0][2] is not None

    # Single use: the same token is dead for both verbs, from any browser.
    assert client.post(f"/auth/email/{token}").status_code == 410
    fresh = app_module.app.test_client()
    r = fresh.get(f"/auth/email/{token}")
    assert r.status_code == 410 and b"expired or was already used" in r.data


def test_an_unknown_token_is_the_expired_page(client):
    assert client.get("/auth/email/not-a-real-token").status_code == 410


def test_expiry_is_honoured(client, app_module, mail, monkeypatch):
    import auth
    start(client, "stale@example.com")
    token = _token_of(mail[0][1])
    later = datetime.now(timezone.utc) + timedelta(minutes=16)
    monkeypatch.setattr(auth, "_now", lambda: later)
    assert client.get(f"/auth/email/{token}").status_code == 410
    assert client.post(f"/auth/email/{token}").status_code == 410


def test_a_magic_link_lands_on_the_existing_verified_account(client, app_module, mail):
    """Rule 3 through the mail path: the same address is the same person — tokens and classes intact."""
    existing = login(client, "link@example.com")
    from models import User
    with app_module.session_scope() as s:
        s.query(User).filter_by(id=existing["id"]).one().token_balance = 9

    other = app_module.app.test_client()          # a different browser, not signed in
    start(other, "LINK@example.com")
    assert other.post(f"/auth/email/{_token_of(mail[0][1])}").status_code == 302
    me = other.get("/api/me").get_json()["user"]
    assert me["id"] == existing["id"] and me["token_balance"] == 9
    assert sorted(i["provider"] for i in me["identities"]) == ["dev", "email"]


# --- the guards -------------------------------------------------------------------------------------

def test_the_limiter_drops_the_fourth_request_for_an_address_silently(client, app_module, mail):
    """Three links per address per 15 minutes. The fourth answers identically and does nothing — the
    endpoint must not be usable to bomb someone's inbox, or to tell whether a send happened."""
    for _ in range(4):
        r = start(client, "flood@example.com")
        assert r.status_code == 200 and r.get_json()["ok"] is True
    assert len(_links(app_module, "flood@example.com")) == 3
    assert len(mail) == 3


def test_start_sweeps_links_older_than_a_day(client, app_module, mail):
    from models import LoginLink
    old = datetime.now(timezone.utc) - timedelta(days=2)
    with app_module.session_scope() as s:
        s.add(LoginLink(email="ancient@example.com", token_hash="dead" * 16, ip="1.2.3.4",
                        created_at=old.replace(tzinfo=None),
                        expires_at=(old + timedelta(minutes=15)).replace(tzinfo=None)))

    start(client, "sweeper@example.com")
    with app_module.session_scope() as s:
        assert s.query(LoginLink).filter_by(token_hash="dead" * 16).count() == 0
        assert s.query(LoginLink).filter_by(email="sweeper@example.com").count() == 1


def test_a_send_failure_never_changes_the_answer(client, app_module, monkeypatch):
    """Resend being down is our problem, not a different HTTP response (and never a stacktrace)."""
    import auth

    def boom(email, url):
        raise RuntimeError("resend is down")

    monkeypatch.setattr(auth, "mail_configured", lambda: True)
    monkeypatch.setattr(auth, "_send_magic_link", boom)
    r = start(client, "boom@example.com")
    assert r.status_code == 200 and r.get_json() == {"ok": True, "message": "Check your inbox."}
    assert len(_links(app_module, "boom@example.com")) == 1


def test_mail_config_counts_as_production_and_blocks_the_dev_bypass(monkeypatch):
    """Boot guard: mail alone makes this a production-looking deploy, so BTSWEB_DEV_AUTH must refuse to boot
    beside it — exactly as an OAuth client id does."""
    import auth
    from flask import Flask
    monkeypatch.setenv("RESEND_API_KEY", "re_testkey")
    monkeypatch.setenv("BTSWEB_MAIL_FROM", "sign-in@example.com")
    assert auth.mail_configured() and auth.is_production()
    with pytest.raises(RuntimeError, match="BTSWEB_DEV_AUTH"):
        auth.init_auth(Flask(__name__))

    monkeypatch.delenv("RESEND_API_KEY")  # half a config sends no mail, so it is no config at all
    assert not auth.mail_configured() and not auth.is_production()
