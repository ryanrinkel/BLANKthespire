"""Linking a second sign-in method to the account you are already signed in as (_resolve_identity rule 2).

Same seams as the other auth tests: a fake Authlib client for the OAuth callbacks (test_auth_providers) and a
capture stub for the mail (test_auth_email). What is new here is the SESSION — every test signs in first, so
the callback carries a current_user_id and the identity attaches instead of starting a second account.

Emails are unique per test: the SQLite database is session-scoped and rule 3 links on users.email.
"""
from __future__ import annotations

import pytest

from conftest import H, login
from test_auth_providers import FakeOAuth, _identities, _discord_client


@pytest.fixture()
def mail(monkeypatch):
    """Pretend Resend is configured; collect (email, url) instead of sending. Returns the capture list."""
    import auth
    sent: list[tuple[str, str]] = []
    monkeypatch.setattr(auth, "mail_configured", lambda: True)
    monkeypatch.setattr(auth, "_send_magic_link", lambda email, url: sent.append((email, url)))
    return sent


def _token_of(url: str) -> str:
    return url.rsplit("/", 1)[-1]


# --- linking ----------------------------------------------------------------------------------------

def test_a_provider_run_while_signed_in_attaches_to_that_account(app_module, monkeypatch):
    """The whole point of Phase 3: one user, two ways in. The Discord profile deliberately carries an
    unrelated (and unverified) address, so nothing but the session could have joined the two."""
    import auth
    c = app_module.app.test_client()
    me = login(c, "link3@example.com")

    discord = _discord_client(id=6001, email="other@example.com", verified=False, global_name="Linky")
    monkeypatch.setattr(auth, "_oauth", FakeOAuth(discord=discord))
    r = c.get("/auth/discord/callback")
    assert r.status_code == 302 and r.headers["Location"].endswith("/app#account")

    after = c.get("/api/me").get_json()["user"]
    assert after["id"] == me["id"]
    assert [i[0] for i in _identities(app_module, me["id"])] == ["dev", "discord"]
    assert sorted(i["provider"] for i in after["identities"]) == ["dev", "discord"]

    # ...and next week, from a browser that has never seen this account, Discord alone gets them back in.
    later = app_module.app.test_client()
    assert later.get("/auth/discord/callback").status_code == 302
    assert later.get("/api/me").get_json()["user"]["id"] == me["id"]


def test_a_magic_link_consumed_while_signed_in_attaches_an_email_identity(app_module, mail):
    """Same rule through the mail path: a link clicked while signed in adds email sign-in to THIS account
    rather than starting one for the address."""
    c = app_module.app.test_client()
    me = login(c, "link3mail@example.com")

    assert c.post("/api/auth/email/start", json={"email": "second3@example.com"}, headers=H).status_code == 200
    r = c.post(f"/auth/email/{_token_of(mail[0][1])}")
    assert r.status_code == 302 and r.headers["Location"].endswith("/app#account")

    after = c.get("/api/me").get_json()["user"]
    assert after["id"] == me["id"]
    assert sorted(i["provider"] for i in after["identities"]) == ["dev", "email"]


def test_an_identity_owned_by_someone_else_signs_in_as_them_and_merges_nothing(app_module, monkeypatch):
    """Rule 1 beats rule 2, deliberately: the identity already belongs to A, so B's browser simply becomes
    A's session. Merging two accounts is a support action, never something a stray click does — and B keeps
    everything it had, identity included."""
    import auth
    discord = _discord_client(id=6002, email="owner3@example.com", verified=True, global_name="Owner")
    monkeypatch.setattr(auth, "_oauth", FakeOAuth(discord=discord))

    first = app_module.app.test_client()
    first.get("/auth/discord/callback")
    a = first.get("/api/me").get_json()["user"]

    second = app_module.app.test_client()
    b = login(second, "notowner3@example.com")
    assert second.get("/auth/discord/callback").status_code == 302

    now = second.get("/api/me").get_json()["user"]
    assert now["id"] == a["id"] != b["id"]
    assert _identities(app_module, b["id"]) == [("dev", "notowner3@example.com", "notowner3@example.com")]


# --- the chooser in link mode -----------------------------------------------------------------------

def test_login_serves_the_chooser_to_a_signed_in_user_only_with_link(client):
    """?link=1 is what the Account tab's "Link another" points at: without it a signed-in visitor is bounced
    to /app (so a bookmarked /login is never a dead end), with it they get the chooser to add a provider."""
    login(client, "linkmode3@example.com")
    r = client.get("/login")
    assert r.status_code == 302 and r.headers["Location"].endswith("/app")

    r = client.get("/login?link=1")
    assert r.status_code == 200 and b'id="providers"' in r.data
