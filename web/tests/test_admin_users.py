"""The operator user panel: /api/admin/users, the two write routes, and /api/admin/actions.

conftest pins the two roles separately: BTSWEB_ADMIN_EMAILS=unlimited@example.com (the operator) and
BTSWEB_UNLIMITED_EMAILS=unlimited@example.com,tester@example.com. So unlimited@example.com is both the
operator and an env-unlimited account — which is what the "env wins over the flag" cases lean on — while
tester@example.com is env-unlimited and nothing more, which is what the privilege cases lean on.
"""
from __future__ import annotations

import logging
import time

from conftest import H, login, seed_tokens, sse_events

ADMIN = "unlimited@example.com"


def _user(app_module, email):
    # users.email is written lowercased (auth._resolve_identity), so look up the same way.
    from models import User
    with app_module.session_scope() as s:
        return s.query(User).filter_by(email=email.strip().lower()).one()


def _uid(app_module, email: str) -> int:
    return _user(app_module, email).id


def _make(client, app_module, email: str) -> int:
    """Create an account by signing it in, then sign back in as the admin."""
    login(client, email)
    uid = _uid(app_module, email)
    login(client, ADMIN)
    return uid


def _forge(client, mode="token", **extra):
    body = {"concept": "a plague doctor", "mode": mode, **extra}
    return client.post("/api/forge-class", json=body, headers=H)


# --- who may look, and who may write ----------------------------------------------------------------

def test_signed_out_is_401_everywhere(client):
    client.post("/logout", headers=H)
    assert client.get("/api/admin/users").status_code == 401
    assert client.get("/api/admin/actions").status_code == 401
    assert client.post("/api/admin/users/1/tokens", json={"balance": 5}, headers=H).status_code == 401
    assert client.post("/api/admin/users/1/unlimited", json={"unlimited": True}, headers=H).status_code == 401


def test_non_admin_is_forbidden_everywhere(client, app_module):
    uid = _make(client, app_module, "nosy@example.com")
    login(client, "nosy@example.com")
    assert client.get("/api/admin/users").status_code == 403
    assert client.get("/api/admin/actions").status_code == 403
    assert client.post(f"/api/admin/users/{uid}/tokens", json={"balance": 999}, headers=H).status_code == 403
    assert client.post(f"/api/admin/users/{uid}/unlimited", json={"unlimited": True},
                       headers=H).status_code == 403
    # ...and the refused write really did nothing.
    assert _user(app_module, "nosy@example.com").token_balance == 0


def test_writes_need_the_csrf_header(client, app_module):
    uid = _make(client, app_module, "csrf@example.com")
    assert client.post(f"/api/admin/users/{uid}/tokens", json={"balance": 5}).status_code == 403
    assert client.post(f"/api/admin/users/{uid}/unlimited", json={"unlimited": True}).status_code == 403
    assert _user(app_module, "csrf@example.com").token_balance == 0


# --- the listing ------------------------------------------------------------------------------------

def test_listing_shape_and_context(client, app_module, stub_forge):
    login(client, "context@example.com")
    seed_tokens(app_module, "context@example.com", 2)
    assert sse_events(_forge(client))[-1][0] == "result"   # one forge on the ledger
    login(client, ADMIN)

    body = client.get("/api/admin/users?q=context@example.com").get_json()
    assert body["total"] == 1
    row = body["users"][0]
    assert row["email"] == "context@example.com"
    assert row["token_balance"] == 1        # the forge spent one of the two
    assert row["forges"] == 1
    assert row["unlimited"] is False and row["unlimited_env"] is False and row["admin"] is False
    assert row["providers"] == ["dev"]
    assert row["donated_cents"] == 0
    assert row["created_at"]


def test_search_is_case_insensitive_and_filters(client, app_module):
    _make(client, app_module, "Needle.Person@example.com")
    _make(client, app_module, "haystack@example.com")
    found = client.get("/api/admin/users?q=NEEDLE").get_json()
    assert [u["email"] for u in found["users"]] == ["needle.person@example.com"]
    assert found["total"] == 1
    assert client.get("/api/admin/users?q=definitely-nobody").get_json()["users"] == []


def test_the_admin_row_says_env_unlimited_and_admin(client, app_module):
    login(client, ADMIN)
    row = client.get(f"/api/admin/users?q={ADMIN}").get_json()["users"][0]
    assert row["unlimited_env"] is True and row["admin"] is True
    assert row["unlimited"] is False       # the DB flag is untouched — env is what makes them unlimited


def test_limit_is_capped(client, app_module):
    _make(client, app_module, "capped-listing@example.com")
    assert client.get("/api/admin/users?limit=99999").get_json()["limit"] == app_module.ADMIN_USERS_LIMIT
    assert client.get("/api/admin/users?limit=nonsense").get_json()["limit"] == app_module.ADMIN_USERS_LIMIT
    assert client.get("/api/admin/users?limit=1").get_json()["limit"] == 1


# --- setting a balance ------------------------------------------------------------------------------

def test_set_balance_absolute(client, app_module):
    uid = _make(client, app_module, "setme@example.com")
    seed_tokens(app_module, "setme@example.com", 2)
    body = client.post(f"/api/admin/users/{uid}/tokens", json={"balance": 10}, headers=H).get_json()
    assert body == {"id": uid, "token_balance": 10, "previous": 2}
    assert _user(app_module, "setme@example.com").token_balance == 10


def test_delta_moves_the_balance_and_floors_at_zero(client, app_module):
    uid = _make(client, app_module, "delta@example.com")
    seed_tokens(app_module, "delta@example.com", 3)
    assert client.post(f"/api/admin/users/{uid}/tokens", json={"delta": 4},
                       headers=H).get_json()["token_balance"] == 7
    # "Take 20 away" from 7 leaves 0, not -13 and not an error.
    assert client.post(f"/api/admin/users/{uid}/tokens", json={"delta": -20},
                       headers=H).get_json()["token_balance"] == 0
    assert _user(app_module, "delta@example.com").token_balance == 0


def test_bad_token_bodies_are_rejected(client, app_module):
    uid = _make(client, app_module, "badbody@example.com")
    seed_tokens(app_module, "badbody@example.com", 4)
    for body in ({}, {"balance": 5, "delta": 1}, {"balance": -1},
                 {"balance": app_module.ADMIN_TOKENS_MAX + 1}, {"balance": "lots"}, {"delta": None}):
        r = client.post(f"/api/admin/users/{uid}/tokens", json=body, headers=H)
        assert r.status_code == 400, body
    assert _user(app_module, "badbody@example.com").token_balance == 4   # nothing moved


def test_unknown_user_is_404(client, app_module):
    login(client, ADMIN)
    assert client.post("/api/admin/users/9999999/tokens", json={"balance": 1},
                       headers=H).status_code == 404
    assert client.post("/api/admin/users/9999999/unlimited", json={"unlimited": True},
                       headers=H).status_code == 404


def test_a_granted_balance_is_spendable(client, app_module, stub_forge):
    """The whole point: hand someone tokens and their next hosted forge goes through."""
    uid = _make(client, app_module, "granted@example.com")
    client.post(f"/api/admin/users/{uid}/tokens", json={"balance": 1}, headers=H)
    login(client, "granted@example.com")
    assert client.get("/api/me").get_json()["user"]["token_balance"] == 1
    assert sse_events(_forge(client))[-1][0] == "result"
    assert _user(app_module, "granted@example.com").token_balance == 0


# --- the unlimited flag -----------------------------------------------------------------------------

def test_unlimited_flag_stops_the_balance_being_spent(client, app_module, stub_forge):
    uid = _make(client, app_module, "freerider@example.com")
    seed_tokens(app_module, "freerider@example.com", 1)
    body = client.post(f"/api/admin/users/{uid}/unlimited", json={"unlimited": True}, headers=H).get_json()
    assert body["unlimited"] is True and body["unlimited_env"] is False

    login(client, "freerider@example.com")
    assert client.get("/api/me").get_json()["user"]["unlimited"] is True
    for _ in range(3):
        assert sse_events(_forge(client))[-1][0] == "result"
    assert _user(app_module, "freerider@example.com").token_balance == 1   # never decremented


def test_unlimited_flag_forges_on_an_empty_balance(client, app_module, stub_forge):
    """Unlimited has to mean unlimited: an empty balance must not 402 the way it does for everyone else."""
    uid = _make(client, app_module, "broke-but-free@example.com")
    client.post(f"/api/admin/users/{uid}/unlimited", json={"unlimited": True}, headers=H)
    login(client, "broke-but-free@example.com")
    assert sse_events(_forge(client))[-1][0] == "result"


def test_turning_the_flag_off_restores_spending(client, app_module, stub_forge):
    uid = _make(client, app_module, "revoked@example.com")
    seed_tokens(app_module, "revoked@example.com", 2)
    client.post(f"/api/admin/users/{uid}/unlimited", json={"unlimited": True}, headers=H)
    client.post(f"/api/admin/users/{uid}/unlimited", json={"unlimited": False}, headers=H)
    login(client, "revoked@example.com")
    assert client.get("/api/me").get_json()["user"]["unlimited"] is False
    assert sse_events(_forge(client))[-1][0] == "result"
    assert _user(app_module, "revoked@example.com").token_balance == 1


def test_env_unlimited_survives_the_flag_being_off(client, app_module, stub_forge):
    """BTSWEB_UNLIMITED_EMAILS is the break-glass path: no write to the database can take it away."""
    login(client, ADMIN)
    uid = _uid(app_module, ADMIN)
    seed_tokens(app_module, ADMIN, 1)
    body = client.post(f"/api/admin/users/{uid}/unlimited", json={"unlimited": False}, headers=H).get_json()
    assert body["unlimited"] is False and body["unlimited_env"] is True
    assert client.get("/api/me").get_json()["user"]["unlimited"] is True
    assert sse_events(_forge(client))[-1][0] == "result"
    assert _user(app_module, ADMIN).token_balance == 1   # still free


def test_bad_unlimited_bodies_are_rejected(client, app_module):
    uid = _make(client, app_module, "badflag@example.com")
    for body in ({}, {"unlimited": "yes"}, {"unlimited": 1}, {"unlimited": None}):
        assert client.post(f"/api/admin/users/{uid}/unlimited", json=body,
                           headers=H).status_code == 400, body
    assert _user(app_module, "badflag@example.com").unlimited_tokens == 0


def test_granting_unlimited_grants_no_admin_power(client, app_module):
    """Unlimited is a BILLING grant, never a privilege one. The panel writes users.unlimited_tokens and
    nothing else; is_admin() reads BTSWEB_ADMIN_EMAILS and never that column, so there is no path from the
    checkbox to the operator card. Locked down here because the two ideas are one env var apart in prod."""
    uid = _make(client, app_module, "rich-not-royal@example.com")
    client.post(f"/api/admin/users/{uid}/unlimited", json={"unlimited": True}, headers=H)
    client.post(f"/api/admin/users/{uid}/tokens", json={"balance": 99}, headers=H)

    me = login(client, "rich-not-royal@example.com")
    assert me["unlimited"] is True and me["token_balance"] == 99   # the grant landed...
    assert me["admin"] is False                                    # ...and bought nothing else
    # The panel itself is shut to them, read and write alike.
    assert client.get("/api/admin/users").status_code == 403
    assert client.get("/api/admin/stats").status_code == 403
    assert client.get("/api/admin/actions").status_code == 403
    assert client.post(f"/api/admin/users/{uid}/unlimited", json={"unlimited": True},
                       headers=H).status_code == 403
    assert client.post(f"/api/admin/users/{uid}/tokens", json={"balance": 100000},
                       headers=H).status_code == 403


def test_the_env_unlimited_list_confers_no_admin_either(client, app_module):
    """The other half of the same promise, and the reason ADMIN_EMAILS stopped defaulting to the unlimited
    list: BTSWEB_UNLIMITED_EMAILS is a billing roster, so being on it must not open the operator cards.
    tester@example.com is on that list and on no other."""
    me = login(client, "tester@example.com")
    assert me["unlimited"] is True      # env-unlimited, really
    assert me["admin"] is False         # and that is all it buys
    assert client.get("/api/admin/users").status_code == 403
    assert client.get("/api/admin/stats").status_code == 403


def test_admin_emails_is_the_only_source_of_admin(app_module):
    """Belt and braces on the gate itself: is_admin answers from BTSWEB_ADMIN_EMAILS and nothing else."""
    from auth import ADMIN_EMAILS, UNLIMITED_EMAILS, is_admin
    assert ADMIN_EMAILS == {ADMIN}
    assert "tester@example.com" in UNLIMITED_EMAILS and "tester@example.com" not in ADMIN_EMAILS
    assert is_admin(ADMIN) is True
    assert is_admin("tester@example.com") is False
    # A user row carrying the DB grant is not consulted by the gate at all — it takes an address.
    from models import User
    assert is_admin(User(google_sub="x", email="tester@example.com", unlimited_tokens=1).email) is False


def test_the_panel_cannot_make_anyone_admin(client, app_module):
    """There is no route that writes the admin flag: it is env-only, so the listing reports it read-only."""
    uid = _make(client, app_module, "aspiring@example.com")
    for field in ("admin", "is_admin"):
        r = client.post(f"/api/admin/users/{uid}/unlimited", json={"unlimited": True, field: True}, headers=H)
        assert r.status_code == 200 and "admin" not in r.get_json()
    row = client.get("/api/admin/users?q=aspiring@example.com").get_json()["users"][0]
    assert row["admin"] is False and row["unlimited"] is True
    assert login(client, "aspiring@example.com")["admin"] is False


# --- the audit trail --------------------------------------------------------------------------------

def _actions(client, limit=50):
    return client.get(f"/api/admin/actions?limit={limit}").get_json()["actions"]


def test_every_write_is_recorded(client, app_module):
    uid = _make(client, app_module, "audited@example.com")
    client.post(f"/api/admin/users/{uid}/tokens", json={"balance": 7}, headers=H)
    client.post(f"/api/admin/users/{uid}/unlimited", json={"unlimited": True}, headers=H)

    rows = [a for a in _actions(client) if a["target_email"] == "audited@example.com"]
    assert [a["action"] for a in rows] == ["set_unlimited", "set_tokens"]   # newest first
    tokens = rows[1]
    assert (tokens["old_value"], tokens["new_value"]) == (0, 7)
    assert tokens["actor_email"] == ADMIN
    assert tokens["target_user_id"] == uid and tokens["created_at"]
    assert rows[0]["old_value"] == 0 and rows[0]["new_value"] == 1


def test_a_no_op_write_is_not_recorded(client, app_module):
    """Saving a row without changing it shouldn't bury the real edits in noise."""
    uid = _make(client, app_module, "noop@example.com")
    seed_tokens(app_module, "noop@example.com", 5)
    before = len(_actions(client))
    client.post(f"/api/admin/users/{uid}/tokens", json={"balance": 5}, headers=H)
    client.post(f"/api/admin/users/{uid}/unlimited", json={"unlimited": False}, headers=H)
    assert len(_actions(client)) == before


def test_actions_limit_is_capped_and_newest_first(client, app_module):
    uid = _make(client, app_module, "chatty@example.com")
    for n in (1, 2, 3):
        client.post(f"/api/admin/users/{uid}/tokens", json={"balance": n}, headers=H)
    assert len(client.get("/api/admin/actions?limit=99999").get_json()["actions"]) <= \
        app_module.ADMIN_ACTIONS_LIMIT
    newest = client.get("/api/admin/actions?limit=2").get_json()["actions"]
    assert len(newest) == 2 and newest[0]["id"] > newest[1]["id"]


def test_a_note_is_kept(client, app_module):
    uid = _make(client, app_module, "noted@example.com")
    client.post(f"/api/admin/users/{uid}/tokens", json={"balance": 3, "note": "kickstarter backer"},
                headers=H)
    row = [a for a in _actions(client) if a["target_email"] == "noted@example.com"][0]
    assert row["note"] == "kickstarter backer"


# --- writes need a fresh sign-in ----------------------------------------------------------------------
# Sessions last 31 days; a balance edit from a sign-in older than app.ADMIN_WRITE_MAX_AGE_S is refused (403
# with reauth=true) so a stolen or left-open operator cookie is not a month of free rein. Reads are not gated.

def _age_session(client, seconds: float | None) -> None:
    """Back-date the signed-in session's auth_at stamp, or (None) remove it — a cookie from before the stamp."""
    with client.session_transaction() as sess:
        if seconds is None:
            sess.pop("auth_at", None)
        else:
            sess["auth_at"] = int(time.time() - seconds)


def test_a_fresh_sign_in_is_stamped(client):
    login(client, ADMIN)
    with client.session_transaction() as sess:
        assert abs(time.time() - sess["auth_at"]) < 5


def test_stale_operator_sessions_can_look_but_not_touch(client, app_module):
    uid = _make(client, app_module, "stale@example.com")
    _age_session(client, app_module.ADMIN_WRITE_MAX_AGE_S + 60)

    r = client.post(f"/api/admin/users/{uid}/tokens", json={"balance": 5}, headers=H)
    assert r.status_code == 403 and r.get_json()["reauth"] is True
    r = client.post(f"/api/admin/users/{uid}/unlimited", json={"unlimited": True}, headers=H)
    assert r.status_code == 403 and r.get_json()["reauth"] is True
    assert _user(app_module, "stale@example.com").token_balance == 0
    assert not _user(app_module, "stale@example.com").unlimited_tokens
    # ...but the listing and the audit trail still answer.
    assert client.get("/api/admin/users").status_code == 200
    assert client.get("/api/admin/actions").status_code == 200

    # Signing in again restores writing.
    login(client, ADMIN)
    assert client.post(f"/api/admin/users/{uid}/tokens", json={"balance": 5}, headers=H).status_code == 200
    assert _user(app_module, "stale@example.com").token_balance == 5


def test_a_session_without_the_stamp_must_sign_in_again(client, app_module):
    """A cookie issued before auth_at existed has no age to check; it counts as too old."""
    uid = _make(client, app_module, "unstamped@example.com")
    _age_session(client, None)
    r = client.post(f"/api/admin/users/{uid}/tokens", json={"balance": 5}, headers=H)
    assert r.status_code == 403 and r.get_json()["reauth"] is True
    assert _user(app_module, "unstamped@example.com").token_balance == 0


def test_a_session_just_inside_the_limit_still_writes(client, app_module):
    uid = _make(client, app_module, "recent@example.com")
    _age_session(client, app_module.ADMIN_WRITE_MAX_AGE_S - 60)
    assert client.post(f"/api/admin/users/{uid}/tokens", json={"balance": 2}, headers=H).status_code == 200


def test_a_non_admin_with_a_fresh_session_is_still_forbidden(client, app_module):
    """Freshness is a second gate, never a substitute for the first."""
    uid = _make(client, app_module, "fresh-nosy@example.com")
    login(client, "fresh-nosy@example.com")
    r = client.post(f"/api/admin/users/{uid}/tokens", json={"balance": 5}, headers=H)
    assert r.status_code == 403 and "reauth" not in r.get_json()


# --- every write is also in the app log, with the operator's address ------------------------------------

def test_a_write_records_the_ip_and_logs_a_line(client, app_module, caplog):
    uid = _make(client, app_module, "traced@example.com")
    caplog.set_level(logging.INFO, logger=app_module.app.logger.name)
    r = client.post(f"/api/admin/users/{uid}/tokens", json={"balance": 4, "note": "why"}, headers=H,
                    environ_base={"REMOTE_ADDR": "203.0.113.9"})
    assert r.status_code == 200

    row = [a for a in _actions(client) if a["target_email"] == "traced@example.com"][0]
    assert row["ip"] == "203.0.113.9"

    lines = [rec.getMessage() for rec in caplog.records if rec.getMessage().startswith("admin action:")]
    assert len(lines) == 1, lines
    line = lines[0]
    for needle in ("set_tokens", ADMIN, "203.0.113.9", "traced@example.com", "0 -> 4", "note='why'"):
        assert needle in line, (needle, line)


def test_a_no_op_write_logs_nothing(client, app_module, caplog):
    uid = _make(client, app_module, "quiet@example.com")
    seed_tokens(app_module, "quiet@example.com", 5)
    caplog.set_level(logging.INFO, logger=app_module.app.logger.name)
    client.post(f"/api/admin/users/{uid}/tokens", json={"balance": 5}, headers=H)
    assert not [rec for rec in caplog.records if rec.getMessage().startswith("admin action:")]
