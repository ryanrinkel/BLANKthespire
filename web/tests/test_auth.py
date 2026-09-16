"""Sign-in resolution: the four _resolve_identity rules, the verified-email-only security rule (unverified
addresses must never reach users.email, which gates BTSWEB_UNLIMITED_EMAILS), and the boot backfill that
gives pre-identities accounts their identity row.

Emails are unique per test: the SQLite database is session-scoped and rule 3 links on users.email."""
from __future__ import annotations

from conftest import login


def _resolve(**kw):
    from auth import Profile, _resolve_identity
    current = kw.pop("current_user_id", None)
    return _resolve_identity(Profile(**kw), current_user_id=current)


def _user(app_module, user_id):
    from models import User
    with app_module.session_scope() as s:
        return s.query(User).filter_by(id=user_id).one()


def _identities(app_module, user_id) -> list[tuple[str, str, str]]:
    from models import Identity
    with app_module.session_scope() as s:
        rows = s.query(Identity).filter_by(user_id=user_id).all()
    return sorted((i.provider, i.subject, i.email) for i in rows)


# --- the four rules ---------------------------------------------------------------------------------

def test_known_identity_resolves_to_the_same_user(app_module):
    """Rule 1: the normal repeat sign-in — one identity row, one user, no second account."""
    kw = dict(provider="google", subject="sub-rule1", email="rule1@example.com",
              email_verified=True, name="Rule One")
    first, second = _resolve(**kw), _resolve(**kw)
    assert first["id"] == second["id"]
    assert _identities(app_module, first["id"]) == [("google", "sub-rule1", "rule1@example.com")]


def test_link_while_signed_in_attaches_to_the_current_user(app_module):
    """Rule 2: current_user_id wins over creating a second account (Phase 3's "link another provider")."""
    base = _resolve(provider="google", subject="sub-rule2", email="rule2@example.com",
                    email_verified=True, name="Rule Two")
    linked = _resolve(provider="discord", subject="snow-rule2", email="rule2-alt@example.com",
                      email_verified=True, name="Rule Two", current_user_id=base["id"])
    assert linked["id"] == base["id"]
    assert [i[:2] for i in _identities(app_module, base["id"])] == [
        ("discord", "snow-rule2"), ("google", "sub-rule2")]


def test_verified_email_links_to_the_existing_account_and_keeps_tokens(app_module):
    """Rule 3: a second provider carrying the same verified address is the same person — tokens intact."""
    first = _resolve(provider="google", subject="sub-rule3", email="rule3@example.com",
                     email_verified=True, name="Rule Three")
    from models import User
    with app_module.session_scope() as s:
        s.query(User).filter_by(id=first["id"]).one().token_balance = 7
    second = _resolve(provider="discord", subject="snow-rule3", email="Rule3@Example.com",
                      email_verified=True, name="Rule Three")
    assert second["id"] == first["id"]                       # matched case-insensitively
    assert _user(app_module, first["id"]).token_balance == 7  # linking never touches the balance
    assert len(_identities(app_module, first["id"])) == 2


def test_two_accounts_on_one_email_link_to_neither(app_module):
    """Rule 3 only fires on an unambiguous match: two rows sharing an address -> a fresh account."""
    from models import User
    with app_module.session_scope() as s:
        rows = [User(google_sub="legacy-amb-1", email="amb@example.com"),
                User(google_sub="legacy-amb-2", email="amb@example.com")]
        s.add_all(rows)
        s.flush()
        existing = {r.id for r in rows}
    out = _resolve(provider="google", subject="sub-amb", email="amb@example.com",
                   email_verified=True, name="Amb")
    assert out["id"] not in existing


def test_unknown_identity_creates_a_user_and_an_identity(app_module):
    """Rule 4: brand-new account. google_sub is the legacy NOT NULL UNIQUE column -> "provider:subject"."""
    from models import INITIAL_TOKENS
    out = _resolve(provider="google", subject="sub-rule4", email="rule4@example.com",
                   email_verified=True, name="Rule Four")
    row = _user(app_module, out["id"])
    assert row.google_sub == "google:sub-rule4"
    assert (row.email, row.name, row.token_balance) == ("rule4@example.com", "Rule Four", INITIAL_TOKENS)
    assert _identities(app_module, out["id"]) == [("google", "sub-rule4", "rule4@example.com")]


# --- the security rule: verified addresses only ------------------------------------------------------

def test_unverified_email_is_never_stored_on_the_user_and_never_links(app_module):
    """The whole point of email_verified: is_unlimited() reads users.email, so a provider that lets someone
    claim any address must not be able to write one there — or to hijack an account by claiming it."""
    victim = _resolve(provider="google", subject="sub-victim", email="victim@example.com",
                      email_verified=True, name="Victim")
    liar = _resolve(provider="discord", subject="snow-liar", email="victim@example.com",
                    email_verified=False, name="Liar")
    assert liar["id"] != victim["id"]                      # no link on an unverified claim
    assert liar["email"] == "" and _user(app_module, liar["id"]).email == ""
    # ...but the identity row still records what the provider said, for display/debugging.
    assert _identities(app_module, liar["id"]) == [("discord", "snow-liar", "victim@example.com")]
    # A later unverified sign-in on that identity still cannot write users.email.
    again = _resolve(provider="discord", subject="snow-liar", email="victim@example.com",
                     email_verified=False, name="Liar")
    assert again["id"] == liar["id"] and _user(app_module, liar["id"]).email == ""
    assert _user(app_module, victim["id"]).email == "victim@example.com"


def test_verified_profile_refreshes_the_account_email_and_name(app_module):
    out = _resolve(provider="google", subject="sub-refresh", email="old-refresh@example.com",
                   email_verified=True, name="Old Name")
    again = _resolve(provider="google", subject="sub-refresh", email="New-Refresh@example.com",
                     email_verified=True, name="New Name")
    row = _user(app_module, out["id"])
    assert again["id"] == out["id"]
    assert (row.email, row.name) == ("new-refresh@example.com", "New Name")


# --- the boot backfill ------------------------------------------------------------------------------

def test_backfill_gives_pre_identity_accounts_exactly_one_identity(app_module):
    """db._ensure_identities runs on every boot: legacy rows get an identity derived from google_sub, and a
    second run adds nothing (it only looks at users with no identity row)."""
    import db
    from models import User
    with app_module.session_scope() as s:
        rows = [User(google_sub="107600000000000000001", email="Legacy@Example.com", name="Legacy"),
                User(google_sub="dev:olddev@example.com", email="olddev@example.com", name="Old Dev")]
        s.add_all(rows)
        s.flush()
        legacy_id, dev_id = rows[0].id, rows[1].id

    db._ensure_identities()
    db._ensure_identities()  # idempotent — no duplicate rows, no unique-constraint blowup

    assert _identities(app_module, legacy_id) == [
        ("google", "107600000000000000001", "legacy@example.com")]
    assert _identities(app_module, dev_id) == [("dev", "olddev@example.com", "olddev@example.com")]
    # ...and the backfilled row is what the next real Google sign-in resolves to (no duplicate account).
    out = _resolve(provider="google", subject="107600000000000000001", email="legacy@example.com",
                   email_verified=True, name="Legacy")
    assert out["id"] == legacy_id


# --- the live routes --------------------------------------------------------------------------------

def test_dev_login_creates_a_dev_identity(client, app_module):
    me = login(client, "devident@example.com")
    assert _identities(app_module, me["id"]) == [
        ("dev", "devident@example.com", "devident@example.com")]
    assert _user(app_module, me["id"]).google_sub == "dev:devident@example.com"


def test_is_production_tracks_any_configured_provider(monkeypatch):
    """The boot guards (session secret key, dev-login conflict) key off this, so it must flip on the first
    provider configured — not on Google specifically."""
    import auth
    assert auth.is_production() is False           # conftest unsets every provider id
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "fake-client-id")
    assert auth.is_production() is True
