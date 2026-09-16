"""Discord + GitHub sign-in: the per-provider profile parsers and the generic /login//auth routes.

No network and no Authlib clients (conftest unsets every CLIENT_ID, so nothing registers): every test drives
a fake OAuth client that answers authorize_access_token() and get() with canned JSON. That is exactly the
seam _profile_<provider> exists for. The Authlib registration itself is covered by the boot check in
DEPLOY/the phase notes, not here — authorize_redirect needs a real registered client.

Emails are unique per test: the SQLite database is session-scoped and rule 3 links on users.email.
"""
from __future__ import annotations

import pytest

from conftest import login


class FakeResp:
    """What Authlib's client.get() hands back: .json() plus .raise_for_status()."""
    def __init__(self, data, status: int = 200):
        self._data, self.status_code = data, status

    def json(self):
        return self._data

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class FakeClient:
    """One provider's Authlib client: a canned token and a path -> FakeResp map."""
    def __init__(self, routes: dict, token: dict | None = None):
        self.routes, self.token_ = routes, token or {"access_token": "fake"}

    def authorize_access_token(self):
        return self.token_

    def get(self, path, **kw):
        return self.routes[path]


class FakeOAuth:
    """Stands in for auth._oauth: only the providers passed exist as attributes (the rest -> 503)."""
    def __init__(self, **clients):
        self.__dict__.update(clients)


def _user(app_module, user_id):
    from models import User
    with app_module.session_scope() as s:
        return s.query(User).filter_by(id=user_id).one()


def _identities(app_module, user_id) -> list[tuple[str, str, str]]:
    from models import Identity
    with app_module.session_scope() as s:
        rows = s.query(Identity).filter_by(user_id=user_id).all()
    return sorted((i.provider, i.subject, i.email) for i in rows)


def _discord_client(**me):
    return FakeClient({"users/@me": FakeResp({"id": 42, "username": "u", **me})})


def _github_client(user: dict, emails):
    return FakeClient({"user": FakeResp(user),
                       "user/emails": emails if isinstance(emails, FakeResp) else FakeResp(emails)})


# --- the profile parsers ----------------------------------------------------------------------------

def test_profile_discord_uses_the_verified_flag_and_the_display_name():
    from auth import _profile_discord
    client = _discord_client(id=1070000000000000001, email="d@example.com", verified=True,
                             global_name="Dee", username="dee_raw")
    p = _profile_discord(client, client.token_)
    assert (p.provider, p.subject, p.email, p.email_verified, p.name) == (
        "discord", "1070000000000000001", "d@example.com", True, "Dee")


def test_profile_discord_unverified_email_is_not_trusted():
    """Discord lets an account carry an unclaimed address until it is verified — `verified` is the only
    thing that may set email_verified, or _resolve_identity would link a stranger to someone's account."""
    from auth import _profile_discord
    client = _discord_client(id=7, email="victim@example.com", verified=False, global_name=None,
                             username="liar")
    p = _profile_discord(client, client.token_)
    assert (p.email, p.email_verified, p.name) == ("victim@example.com", False, "liar")


def test_profile_github_picks_the_primary_verified_address():
    from auth import _profile_github
    client = _github_client(
        {"id": 999, "login": "octo", "name": "Octo Cat", "email": None},
        [{"email": "old@example.com", "primary": False, "verified": True},
         {"email": "unverified@example.com", "primary": True, "verified": False},
         {"email": "Real@example.com", "primary": True, "verified": True}])
    p = _profile_github(client, client.token_)
    assert (p.provider, p.subject, p.email, p.email_verified, p.name) == (
        "github", "999", "Real@example.com", True, "Octo Cat")


def test_profile_github_falls_back_to_any_verified_address_and_to_the_login():
    from auth import _profile_github
    client = _github_client({"id": 1000, "login": "nameless", "email": None},
                            [{"email": "only@example.com", "primary": False, "verified": True}])
    p = _profile_github(client, client.token_)
    assert (p.email, p.email_verified, p.name) == ("only@example.com", True, "nameless")


def test_profile_github_private_email_account_gets_no_email():
    """/user.email is null and /user/emails is empty (or all unverified): the account is created without an
    address — it just cannot link to another provider or be on the unlimited list."""
    from auth import _profile_github
    client = _github_client({"id": 1001, "login": "private", "email": None}, [])
    p = _profile_github(client, client.token_)
    assert (p.email, p.email_verified) == ("", False)


def test_profile_github_survives_a_failing_emails_call():
    """No user:email scope (or GitHub simply says no) must not break sign-in."""
    from auth import _profile_github
    client = _github_client({"id": 1002, "login": "scopeless", "email": None},
                            FakeResp({"message": "Forbidden"}, status=403))
    p = _profile_github(client, client.token_)
    assert (p.subject, p.email, p.email_verified) == ("1002", "", False)


# --- the callback route -----------------------------------------------------------------------------

def test_discord_callback_creates_the_user_and_the_identity(app_module, monkeypatch):
    import auth
    client = _discord_client(id=2001, email="newdiscord@example.com", verified=True, global_name="New")
    monkeypatch.setattr(auth, "_oauth", FakeOAuth(discord=client))
    c = app_module.app.test_client()

    assert c.get("/auth/discord/callback").status_code == 302
    me = c.get("/api/me").get_json()["user"]
    assert me["email"] == "newdiscord@example.com"
    assert _identities(app_module, me["id"]) == [("discord", "2001", "newdiscord@example.com")]
    assert me["identities"] == [{"provider": "discord", "label": "newdiscord@example.com"}]


def test_github_callback_links_to_the_existing_account_on_a_verified_email(app_module, monkeypatch):
    """Rule 3 over the wire: the same verified address ⇒ the same user, tokens untouched."""
    import auth
    existing = login(app_module.app.test_client(), "linkme@example.com")
    from models import User
    with app_module.session_scope() as s:
        s.query(User).filter_by(id=existing["id"]).one().token_balance = 11

    gh = _github_client({"id": 3001, "login": "linkme", "name": "Link Me", "email": None},
                        [{"email": "linkme@example.com", "primary": True, "verified": True}])
    monkeypatch.setattr(auth, "_oauth", FakeOAuth(github=gh))
    c = app_module.app.test_client()
    assert c.get("/auth/github/callback").status_code == 302

    me = c.get("/api/me").get_json()["user"]
    assert me["id"] == existing["id"]
    assert _user(app_module, me["id"]).token_balance == 11
    assert [i[0] for i in _identities(app_module, me["id"])] == ["dev", "github"]


def test_unverified_discord_email_never_hijacks_an_account(app_module, monkeypatch):
    """The security rule end to end: an unverified claim on someone else's address creates a SEPARATE
    account with an empty users.email (which is what BTSWEB_UNLIMITED_EMAILS is matched against)."""
    import auth
    victim = login(app_module.app.test_client(), "hijackme@example.com")
    liar = _discord_client(id=4001, email="hijackme@example.com", verified=False, username="liar")
    monkeypatch.setattr(auth, "_oauth", FakeOAuth(discord=liar))
    c = app_module.app.test_client()
    assert c.get("/auth/discord/callback").status_code == 302

    me = c.get("/api/me").get_json()["user"]
    assert me["id"] != victim["id"]
    assert _user(app_module, me["id"]).email == ""
    assert _user(app_module, victim["id"]).email == "hijackme@example.com"


def test_repeat_discord_sign_in_is_the_same_account(app_module, monkeypatch):
    import auth
    client = _discord_client(id=5001, email="repeat@example.com", verified=True, global_name="Rep")
    monkeypatch.setattr(auth, "_oauth", FakeOAuth(discord=client))
    first = app_module.app.test_client()
    first.get("/auth/discord/callback")
    second = app_module.app.test_client()
    second.get("/auth/discord/callback")
    assert first.get("/api/me").get_json()["user"]["id"] == second.get("/api/me").get_json()["user"]["id"]


# --- the chooser + the guards -----------------------------------------------------------------------

def test_login_serves_the_chooser_and_bounces_a_signed_in_user(client, app_module):
    r = app_module.app.test_client().get("/login")
    assert r.status_code == 200 and b'id="providers"' in r.data

    login(client)
    r = client.get("/login")
    assert r.status_code == 302 and r.headers["Location"].endswith("/app")


@pytest.mark.parametrize("path", ["/login/steam", "/auth/steam/callback"])
def test_unknown_provider_is_a_404(client, path):
    assert client.get(path).status_code == 404


@pytest.mark.parametrize("path", ["/login/discord", "/login/github", "/auth/discord/callback"])
def test_configured_nowhere_means_503_not_a_crash(client, path):
    """conftest unsets every CLIENT_ID, so nothing registered — a real provider name must still answer
    politely rather than blowing up on a missing Authlib client."""
    r = client.get(path)
    assert r.status_code == 503 and b"not configured" in r.data


def test_api_me_reports_the_configured_providers(client):
    me = client.get("/api/me").get_json()
    assert me["providers"] == [] and me["email_login"] is False


def test_configured_providers_follows_the_env_pairs(monkeypatch):
    """A button appears only when BOTH halves are set — a half-configured provider would 500 on redirect."""
    import auth
    assert auth.configured_providers() == []
    monkeypatch.setenv("DISCORD_CLIENT_ID", "id")
    assert auth.configured_providers() == []      # secret still missing
    monkeypatch.setenv("DISCORD_CLIENT_SECRET", "secret")
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "id")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "secret")
    assert auth.configured_providers() == ["google", "discord"]   # display order, not env order
