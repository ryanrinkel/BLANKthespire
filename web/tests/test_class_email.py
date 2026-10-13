"""POST /api/classes/<id>/email — the "Email it to me" phone -> PC hand-off (PHONE_FUNNEL_PLAN.md 5.2).

No mail leaves the process: `mail_configured` is forced True and the Resend POST itself (`auth.requests.post`)
is swapped for a capture stub, so the factored `_send_mail` transport is exercised end to end. Emails are
unique per test: the SQLite database is session-scoped.
"""
from __future__ import annotations

import json

import pytest

from conftest import H, login


class _Resp:
    def __init__(self, status: int = 200):
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


@pytest.fixture()
def resend(monkeypatch):
    """Pretend Resend is configured; capture every POST's JSON payload instead of sending it."""
    import auth
    sent: list[dict] = []
    monkeypatch.setattr(auth, "mail_configured", lambda: True)

    def fake_post(url, headers=None, json=None, timeout=None):
        assert url == auth.RESEND_ENDPOINT
        sent.append(json)
        return _Resp(200)

    monkeypatch.setattr(auth.requests, "post", fake_post)
    return sent


def _seed(app_module, email: str, name: str = "Mail Test", code: str = "BTSC.mailcode123",
          slug: str | None = "mailslug") -> int:
    from models import ForgedClass, User, new_slug
    with app_module.session_scope() as s:
        uid = s.query(User).filter_by(email=email).one().id
        cls = ForgedClass(user_id=uid, name=name, concept="c", code=code,
                          slug=(slug + "-" + new_slug()[:6]) if slug else None,
                          bundle_json=json.dumps({"character": {"name": name}, "cards": []}))
        s.add(cls)
        s.flush()
        return cls.id


def _send(client, cid: int):
    return client.post(f"/api/classes/{cid}/email", headers=H)


def test_owner_gets_the_link_and_the_code(client, app_module, resend):
    login(client, "mailowner@example.com")
    cid = _seed(app_module, "mailowner@example.com", name="Plague Doctor", code="BTSC.thecode42")
    r = _send(client, cid)
    assert r.status_code == 200
    assert r.get_json() == {"sent": True, "to": "mailowner@example.com"}
    assert len(resend) == 1
    msg = resend[0]
    assert msg["to"] == ["mailowner@example.com"]
    assert "Plague Doctor" in msg["subject"]
    from models import ForgedClass
    with app_module.session_scope() as s:
        slug = s.query(ForgedClass).filter_by(id=cid).one().slug
    for body in (msg["text"], msg["html"]):
        assert "BTSC.thecode42" in body
        assert f"http://testserver/deck/{slug}" in body


def test_a_class_without_a_slug_gets_one(client, app_module, resend):
    login(client, "noslug@example.com")
    cid = _seed(app_module, "noslug@example.com", slug=None)
    assert _send(client, cid).status_code == 200
    from models import ForgedClass
    with app_module.session_scope() as s:
        slug = s.query(ForgedClass).filter_by(id=cid).one().slug
    assert slug and f"/deck/{slug}" in resend[0]["text"]


def test_someone_elses_class_is_404_and_sends_nothing(client, app_module, resend):
    login(client, "mailvictim@example.com")
    cid = _seed(app_module, "mailvictim@example.com")
    other = app_module.app.test_client()
    login(other, "mailthief@example.com")
    assert _send(other, cid).status_code == 404
    assert _send(other, 999999).status_code == 404
    assert resend == []


def test_signed_out_is_401(client, app_module, resend):
    assert client.post("/api/classes/1/email", headers=H).status_code == 401
    assert resend == []


def test_needs_the_csrf_header(client, app_module, resend):
    login(client, "mailcsrf@example.com")
    cid = _seed(app_module, "mailcsrf@example.com")
    assert client.post(f"/api/classes/{cid}/email").status_code == 403
    assert resend == []


def test_account_without_an_email_is_400(client, app_module, resend):
    login(client, "mailnone@example.com")
    cid = _seed(app_module, "mailnone@example.com")
    from models import User
    with app_module.session_scope() as s:
        s.query(User).filter_by(email="mailnone@example.com").one().email = ""
    r = _send(client, cid)
    assert r.status_code == 400 and "no email" in r.get_json()["error"]
    assert resend == []


def test_mail_unconfigured_is_503(client, app_module, monkeypatch):
    import auth
    sent = []
    monkeypatch.setattr(auth.requests, "post", lambda *a, **k: sent.append(a))
    login(client, "mailoff@example.com")
    cid = _seed(app_module, "mailoff@example.com")
    r = _send(client, cid)  # conftest strips RESEND_API_KEY / BTSWEB_MAIL_FROM, so mail is off
    assert r.status_code == 503 and "isn't set up" in r.get_json()["error"]
    assert sent == []


def test_rate_limited_after_five_an_hour(client, app_module, resend):
    login(client, "mailspam@example.com")
    cid = _seed(app_module, "mailspam@example.com")
    for _ in range(5):
        assert _send(client, cid).status_code == 200
    r = _send(client, cid)
    assert r.status_code == 429 and "try again" in r.get_json()["error"]
    assert len(resend) == 5
    # The cap is per account: another account on the same IP still gets its mail.
    other = app_module.app.test_client()
    login(other, "mailspam2@example.com")
    assert _send(other, _seed(app_module, "mailspam2@example.com")).status_code == 200


def test_provider_failure_is_502(client, app_module, monkeypatch):
    import auth
    monkeypatch.setattr(auth, "mail_configured", lambda: True)
    monkeypatch.setattr(auth.requests, "post", lambda *a, **k: _Resp(500))
    login(client, "mailfail@example.com")
    cid = _seed(app_module, "mailfail@example.com")
    assert _send(client, cid).status_code == 502


def test_api_me_reports_whether_mail_is_configured(client, monkeypatch):
    import auth
    assert client.get("/api/me").get_json()["mail"] is False
    monkeypatch.setattr(auth, "mail_configured", lambda: True)
    assert client.get("/api/me").get_json()["mail"] is True


def test_magic_link_still_goes_through_the_shared_transport(client, resend):
    """The factored _send_mail carries the magic link too: text only, no html part."""
    import auth
    auth._send_magic_link("transport@example.com", "http://testserver/auth/email/tok")
    assert resend[0]["to"] == ["transport@example.com"]
    assert "http://testserver/auth/email/tok" in resend[0]["text"] and "html" not in resend[0]
