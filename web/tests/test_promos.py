"""Sign-up events (promo.py + the /api/admin/promos routes + the grant hook in auth._resolve_identity).

Every NEW account created while an event is live starts with tokens_per_signup tokens, up to max_grants
accounts. The test database is shared by the whole session, so every test here starts and ends with no
events at all (otherwise a live event would hand tokens to signups in other test files).
"""
from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone

import pytest

from conftest import H, login, sse_events

ADMIN = "unlimited@example.com"


_FIRST_ACTION = {"id": 0}   # audit rows before this test started belong to other tests


@pytest.fixture(autouse=True)
def _no_events(app_module):
    from sqlalchemy import func
    from models import AdminAction, PromoGrant, Promotion
    with app_module.session_scope() as s:
        _FIRST_ACTION["id"] = int(s.query(func.max(AdminAction.id)).scalar() or 0)

    def wipe():
        with app_module.session_scope() as s:
            s.query(PromoGrant).delete()
            s.query(Promotion).delete()
    wipe()
    yield
    wipe()


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _body(**kw) -> dict:
    now = _now()
    body = {"label": "Launch week", "tokens_per_signup": 1, "max_grants": 10,
            "starts_at": _iso(now - timedelta(hours=1)), "ends_at": _iso(now + timedelta(hours=1))}
    body.update(kw)
    return body


def _create(client, **kw):
    login(client, ADMIN)
    return client.post("/api/admin/promos", json=_body(**kw), headers=H)


def _signup(client, email: str) -> dict:
    """A brand-new account via dev-login; returns its /api/me user dict (which also consumes welcome_grant)."""
    client.post("/logout", headers=H)
    return login(client, email)


def _balance(app_module, email: str) -> int:
    from models import User
    with app_module.session_scope() as s:
        return int(s.query(User).filter_by(email=email).one().token_balance)


def _grants(app_module, email: str | None = None) -> list:
    from models import PromoGrant, User
    with app_module.session_scope() as s:
        q = s.query(PromoGrant)
        if email is not None:
            q = q.join(User, User.id == PromoGrant.user_id).filter(User.email == email)
        return [(g.promo_id, g.user_id, g.tokens) for g in q.all()]


def _actions(app_module) -> list:
    from models import AdminAction
    with app_module.session_scope() as s:
        return [(a.action, a.old_value, a.new_value, a.note, a.target_user_id, a.actor_email, a.ip)
                for a in s.query(AdminAction).filter(AdminAction.action.like("promo_%"),
                                                     AdminAction.id > _FIRST_ACTION["id"])
                .order_by(AdminAction.id).all()]


def _listing(client) -> list:
    login(client, ADMIN)
    r = client.get("/api/admin/promos")
    assert r.status_code == 200
    return r.get_json()["promos"]


# --- the grant ----------------------------------------------------------------------------------------

def test_signup_inside_the_window_gets_the_tokens(client, app_module):
    r = _create(client, tokens_per_signup=3)
    assert r.status_code == 201, r.get_json()
    pid = r.get_json()["id"]
    me = _signup(client, "promo-new1@example.com")
    assert me["token_balance"] == 3
    assert _grants(app_module, "promo-new1@example.com") == [(pid, me["id"], 3)]


def test_signup_before_the_window_gets_nothing(client, app_module):
    now = _now()
    assert _create(client, starts_at=_iso(now + timedelta(hours=1)),
                   ends_at=_iso(now + timedelta(hours=2))).status_code == 201
    assert _listing(client)[0]["status"] == "scheduled"
    assert _signup(client, "promo-early@example.com")["token_balance"] == 0
    assert _grants(app_module) == []


def test_signup_after_the_window_gets_nothing(client, app_module, monkeypatch):
    import promo
    assert _create(client).status_code == 201
    later = promo._now() + timedelta(hours=2)
    monkeypatch.setattr(promo, "_now", lambda: later)
    assert _signup(client, "promo-late@example.com")["token_balance"] == 0
    assert _grants(app_module) == []
    assert _listing(client)[0]["status"] == "ended"


def test_end_now_stops_grants_and_is_idempotent(client, app_module):
    pid = _create(client).get_json()["id"]
    r = client.post(f"/api/admin/promos/{pid}/end", headers=H)
    assert r.status_code == 200
    first = r.get_json()
    assert first["status"] == "ended" and first["ended_at"]
    again = client.post(f"/api/admin/promos/{pid}/end", headers=H).get_json()
    assert again["ended_at"] == first["ended_at"]
    assert [a[0] for a in _actions(app_module)] == ["promo_create", "promo_end"]   # one end row, not two
    assert _signup(client, "promo-after-end@example.com")["token_balance"] == 0
    assert _grants(app_module) == []


def test_cap_is_respected(client, app_module):
    pid = _create(client, max_grants=1).get_json()["id"]
    assert _signup(client, "promo-cap1@example.com")["token_balance"] == 1
    assert _signup(client, "promo-cap2@example.com")["token_balance"] == 0   # account made, no token
    assert len(_grants(app_module)) == 1
    row = _listing(client)[0]
    assert row["id"] == pid and row["status"] == "capped" and row["stats"]["granted"] == 1
    assert client.get("/api/promo/active").get_json() == {"active": None}


def test_raising_the_cap_mid_event_reopens_it(client, app_module):
    pid = _create(client, max_grants=1).get_json()["id"]
    _signup(client, "promo-raise1@example.com")
    login(client, ADMIN)
    r = client.post(f"/api/admin/promos/{pid}", json=_body(max_grants=5), headers=H)
    assert r.status_code == 200 and r.get_json()["status"] == "live"
    assert _signup(client, "promo-raise2@example.com")["token_balance"] == 1
    edits = [a for a in _actions(app_module) if a[0] == "promo_edit"]
    assert len(edits) == 1 and edits[0][1:3] == (1, 5) and "max_grants" in edits[0][3]


def test_existing_account_and_repeat_sign_in_get_nothing(client, app_module):
    _signup(client, "promo-old@example.com")           # before any event
    assert _create(client).status_code == 201
    assert _signup(client, "promo-old@example.com")["token_balance"] == 0   # rule 1: repeat sign-in
    me = _signup(client, "promo-twice@example.com")
    assert me["token_balance"] == 1
    assert _signup(client, "promo-twice@example.com")["token_balance"] == 1  # no double grant
    assert len(_grants(app_module, "promo-twice@example.com")) == 1
    assert _grants(app_module, "promo-old@example.com") == []


def test_linking_a_second_provider_gets_nothing(client, app_module):
    assert _create(client).status_code == 201
    me = _signup(client, "promo-link@example.com")
    assert me["token_balance"] == 1
    client.post("/logout", headers=H)
    # Email magic link for the same verified address -> rule 3 links to the existing account.
    link = client.post("/api/auth/email/start", json={"email": "promo-link@example.com"},
                       headers=H).get_json()["link"]
    assert client.post(link.replace("http://testserver", "")).status_code == 302
    after = client.get("/api/me").get_json()["user"]
    assert after["id"] == me["id"]
    assert sorted(i["provider"] for i in after["identities"]) == ["dev", "email"]
    assert after["token_balance"] == 1
    assert len(_grants(app_module, "promo-link@example.com")) == 1


def test_a_failing_grant_never_breaks_sign_in(client, app_module, monkeypatch):
    """The grant runs in a savepoint: blow up AFTER the PromoGrant is added and the balance bumped (the flush
    fails on a NULL promo_id) and the account still exists, with no grant row and no stray token."""
    import promo
    from models import PromoGrant as RealGrant
    assert _create(client).status_code == 201

    def broken(**kw):
        kw["promo_id"] = None
        return RealGrant(**kw)
    monkeypatch.setattr(promo, "PromoGrant", broken)
    me = _signup(client, "promo-broken@example.com")
    assert me["id"] and me["token_balance"] == 0
    assert _balance(app_module, "promo-broken@example.com") == 0
    assert _grants(app_module) == []

    def boom(*a, **k):
        raise RuntimeError("promo lookup down")
    monkeypatch.setattr(promo, "active_promotion", boom)
    assert _signup(client, "promo-broken2@example.com")["token_balance"] == 0


# --- admin: create / edit / validation ------------------------------------------------------------------

def test_create_shape_and_audit_row(client, app_module):
    r = _create(client, label="  Halloween  ", tokens_per_signup=2, max_grants=50)
    assert r.status_code == 201
    row = r.get_json()
    assert row["label"] == "Halloween" and row["tokens_per_signup"] == 2 and row["max_grants"] == 50
    assert row["status"] == "live" and row["ended_at"] is None and row["created_by_email"] == ADMIN
    assert row["starts_at"].endswith("+00:00") and row["ends_at"].endswith("+00:00")
    assert row["stats"] == {"granted": 0, "tokens_granted": 0, "forged_after": 0, "hosted_cost_usd": None,
                            "donated_after": 0, "donated_cents_after": 0}
    acts = _actions(app_module)
    assert len(acts) == 1
    action, old, new, note, target, actor, ip = acts[0]
    assert (action, old, new, target, actor) == ("promo_create", 0, 50, None, ADMIN)
    assert f"#{row['id']}" in note and "Halloween" in note and ip


def test_offsets_are_converted_to_utc(client, app_module):
    now = _now()
    start = (now - timedelta(hours=1)).astimezone(timezone(timedelta(hours=-5))).replace(microsecond=0)
    r = _create(client, starts_at=start.isoformat(),
                ends_at=(now + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ"))
    assert r.status_code == 201
    assert r.get_json()["starts_at"] == start.astimezone(timezone.utc).isoformat()


@pytest.mark.parametrize("override, fragment", [
    ({"label": "   "}, "label"),
    ({"label": "x" * 121}, "label"),
    ({"tokens_per_signup": 0}, "tokens_per_signup"),
    ({"tokens_per_signup": 11}, "tokens_per_signup"),
    ({"tokens_per_signup": True}, "tokens_per_signup"),
    ({"max_grants": None}, "max_grants"),
    ({"max_grants": -1}, "max_grants"),
    ({"max_grants": "lots"}, "max_grants"),
    ({"starts_at": "2026-11-01T18:00:00"}, "offset"),
    ({"starts_at": "next tuesday"}, "starts_at"),
    ({"ends_at": None}, "ends_at"),
    ({"ends_at": _iso(_now() - timedelta(hours=2))}, "ends_at"),
    ({"ends_at": _iso(_now() - timedelta(minutes=30)),
      "starts_at": _iso(_now() - timedelta(hours=3))}, "past"),
])
def test_validation_errors(client, app_module, override, fragment):
    r = _create(client, **override)
    assert r.status_code == 400
    assert fragment in r.get_json()["error"]
    assert client.get("/api/admin/promos").get_json()["promos"] == []
    assert _actions(app_module) == []


def test_missing_max_grants_and_non_object_body(client, app_module):
    login(client, ADMIN)
    body = _body()
    body.pop("max_grants")
    assert client.post("/api/admin/promos", json=body, headers=H).status_code == 400
    assert client.post("/api/admin/promos", json=[1, 2], headers=H).status_code == 400
    body = _body()
    body.pop("tokens_per_signup")
    r = client.post("/api/admin/promos", json=body, headers=H)
    assert r.status_code == 201 and r.get_json()["tokens_per_signup"] == 1   # default


def test_overlap_is_rejected_until_the_other_ends(client, app_module):
    now = _now().replace(microsecond=0)
    edge = now + timedelta(hours=1)
    first = _create(client, ends_at=_iso(edge)).get_json()["id"]
    r = _create(client, label="Other", starts_at=_iso(now + timedelta(minutes=30)),
                ends_at=_iso(now + timedelta(hours=3)))
    assert r.status_code == 409 and r.get_json()["conflict_id"] == first
    assert "overlaps" in r.get_json()["error"]
    # Back-to-back is not an overlap ([start, end) windows).
    nxt = _create(client, label="Next", starts_at=_iso(edge), ends_at=_iso(edge + timedelta(hours=2)))
    assert nxt.status_code == 201
    assert nxt.get_json()["status"] == "scheduled"
    client.post(f"/api/admin/promos/{nxt.get_json()['id']}/end", headers=H)
    client.post(f"/api/admin/promos/{first}/end", headers=H)
    assert _create(client, label="After end").status_code == 201   # ended events never block


def test_edit_cannot_overlap_and_ended_cannot_be_edited(client, app_module):
    now = _now()
    a = _create(client).get_json()["id"]
    b = _create(client, label="Later", starts_at=_iso(now + timedelta(days=1)),
                ends_at=_iso(now + timedelta(days=2))).get_json()["id"]
    r = client.post(f"/api/admin/promos/{b}", json=_body(label="Later"), headers=H)
    assert r.status_code == 409 and r.get_json()["conflict_id"] == a
    client.post(f"/api/admin/promos/{a}/end", headers=H)
    r = client.post(f"/api/admin/promos/{a}", json=_body(max_grants=99), headers=H)
    assert r.status_code == 409
    assert client.post("/api/admin/promos/999999", json=_body(), headers=H).status_code == 404
    assert client.post("/api/admin/promos/999999/end", headers=H).status_code == 404
    r = client.post(f"/api/admin/promos/{b}", json=_body(label="Later", max_grants=-3), headers=H)
    assert r.status_code == 400


def test_listing_is_newest_first(client, app_module):
    now = _now()
    a = _create(client).get_json()["id"]
    b = _create(client, label="Later", starts_at=_iso(now + timedelta(days=1)),
                ends_at=_iso(now + timedelta(days=2))).get_json()["id"]
    assert [p["id"] for p in _listing(client)] == [b, a]


# --- who may use it --------------------------------------------------------------------------------------

def test_signed_out_and_non_admin_are_refused(client, app_module):
    pid = _create(client).get_json()["id"]
    client.post("/logout", headers=H)
    assert client.get("/api/admin/promos").status_code == 401
    assert client.post("/api/admin/promos", json=_body(), headers=H).status_code == 401
    login(client, "promo-nosy@example.com")
    assert client.get("/api/admin/promos").status_code == 403
    assert client.post("/api/admin/promos", json=_body(label="x"), headers=H).status_code == 403
    assert client.post(f"/api/admin/promos/{pid}", json=_body(max_grants=9999), headers=H).status_code == 403
    assert client.post(f"/api/admin/promos/{pid}/end", headers=H).status_code == 403
    assert [p["max_grants"] for p in _listing(client)] == [10]
    assert [a[0] for a in _actions(app_module)] == ["promo_create"]


def test_writes_need_a_fresh_sign_in_and_the_csrf_header(client, app_module):
    login(client, ADMIN)
    assert client.post("/api/admin/promos", json=_body()).status_code == 403          # no CSRF header
    with client.session_transaction() as sess:
        sess["auth_at"] = int(time.time() - app_module.ADMIN_WRITE_MAX_AGE_S - 60)
    r = client.post("/api/admin/promos", json=_body(), headers=H)
    assert r.status_code == 403 and r.get_json().get("reauth") is True
    assert client.get("/api/admin/promos").status_code == 200                       # reading is fine


# --- public + per-user surfaces --------------------------------------------------------------------------

def test_public_active_shape(client, app_module):
    client.post("/logout", headers=H)
    assert client.get("/api/promo/active").get_json() == {"active": None}
    _create(client, label="Launch", tokens_per_signup=2, max_grants=7)
    client.post("/logout", headers=H)
    active = client.get("/api/promo/active").get_json()["active"]
    assert set(active) == {"label", "tokens_per_signup", "ends_at"}
    assert active["label"] == "Launch" and active["tokens_per_signup"] == 2
    assert active["ends_at"].endswith("+00:00")


def test_welcome_grant_shows_once(client, app_module):
    _create(client, label="Welcome week", tokens_per_signup=2)
    client.post("/logout", headers=H)
    assert client.get("/dev-login?email=promo-welcome@example.com").status_code == 302
    first = client.get("/api/me").get_json()["user"]
    assert first["welcome_grant"] == {"label": "Welcome week", "tokens": 2}
    assert client.get("/api/me").get_json()["user"]["welcome_grant"] is None
    # An account without a grant always reads null.
    login(client, ADMIN)
    assert client.get("/api/me").get_json()["user"]["welcome_grant"] is None


def test_admin_users_listing_names_the_event(client, app_module):
    _create(client, label="Users panel week")
    _signup(client, "promo-panel@example.com")
    login(client, ADMIN)
    row = client.get("/api/admin/users?q=promo-panel@example.com").get_json()["users"][0]
    assert row["promo_label"] == "Users panel week" and row["promo_tokens"] == 1
    other = client.get(f"/api/admin/users?q={ADMIN}").get_json()["users"][0]
    assert other["promo_label"] is None and other["promo_tokens"] == 0


def test_stats_count_forges_cost_and_donations_after_the_grant(client, app_module, stub_forge):
    from models import ForgeUsage, Purchase, User
    pid = _create(client, max_grants=10).get_json()["id"]
    _signup(client, "promo-stats1@example.com")
    r = client.post("/api/forge-class", json={"concept": "a plague doctor", "mode": "token"}, headers=H)
    assert sse_events(r)[-1][0] == "result"            # spent the granted token
    _signup(client, "promo-stats2@example.com")          # granted, never forges, donates
    with app_module.session_scope() as s:
        u1 = s.query(User).filter_by(email="promo-stats1@example.com").one()
        u2 = s.query(User).filter_by(email="promo-stats2@example.com").one()
        assert u1.token_balance == 0
        # A known metered cost row for u1's hosted forge (plus one est-only row) so the sum is checkable.
        s.query(ForgeUsage).filter(ForgeUsage.user_id == u1.id).delete()
        s.add(ForgeUsage(user_id=u1.id, forge_id="promo-stats", mode="token", role="cards", model="m",
                         metered_cost_micros=400_000, est_cost_micros=1))
        s.add(ForgeUsage(user_id=u1.id, forge_id="promo-stats", mode="token", role="structure", model="m",
                         est_cost_micros=100_000))
        s.add(ForgeUsage(user_id=u1.id, forge_id="promo-byok", mode="byok", role="cards", model="m",
                         metered_cost_micros=9_000_000))   # not ours: excluded
        s.add(Purchase(user_id=u2.id, stripe_session_id="cs_promo_stats", price_id="t5", tokens=4,
                       amount_cents=500, status="paid"))
        s.add(Purchase(user_id=u2.id, stripe_session_id="cs_promo_refunded", price_id="t3", tokens=2,
                       amount_cents=300, status="refunded"))
    stats = next(p for p in _listing(client) if p["id"] == pid)["stats"]
    assert stats["granted"] == 2 and stats["tokens_granted"] == 2
    assert stats["forged_after"] == 1
    assert stats["hosted_cost_usd"] == pytest.approx(0.5)
    assert stats["donated_after"] == 1 and stats["donated_cents_after"] == 500
