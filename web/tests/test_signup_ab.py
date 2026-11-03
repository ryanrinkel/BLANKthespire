"""Page experiments, Phase 2 (docs/plans/AB_TESTING_PLAN.md 3.6): users.signup_ab is stamped by
auth._resolve_identity rule 4 ONLY — the arms label the sign-up request's IP + UA draws for every live
experiment — and rules 1-3 (repeat sign-in, linking a provider, a verified-email match) never touch it.

Emails / subjects are unique per test: the SQLite database is session-scoped."""
from __future__ import annotations

import pytest
from sqlalchemy import create_engine, inspect, text

import experiments
from experiments import Experiment

TODAY = "2026-11-20"
IP, UA = "203.0.113.7", "Mozilla/5.0 (signup-ab test)"
HDR = {"X-Forwarded-For": IP, "User-Agent": UA}


def _exp(**over) -> Experiment:
    base = dict(name="sig", page="/", arms=("a", "b"), weights=(50, 50), salt="s-sig",
                started="2026-11-03", planned_end="2026-12-15", primary="login",
                hypothesis="A sentence.", arms_text={"a": "today", "b": "the change"})
    base.update(over)
    return Experiment(**base)


LIVE = [_exp(), _exp(name="sig2", page="/login", salt="s-sig2", arms=("a", "b", "c"), weights=(34, 33, 33),
                     arms_text={"a": "x", "b": "y", "c": "z"}),
        _exp(name="old", page="/help", started="2026-09-01", planned_end="2026-09-30",
             ended="2026-10-01", winner="a")]   # ended: never in the label


@pytest.fixture
def live(monkeypatch):
    monkeypatch.setattr(experiments, "EXPERIMENTS", list(LIVE))
    monkeypatch.setattr(experiments, "today_utc", lambda: TODAY)
    return LIVE


@pytest.fixture
def none_live(monkeypatch):
    monkeypatch.setattr(experiments, "EXPERIMENTS", [LIVE[2]])
    monkeypatch.setattr(experiments, "today_utc", lambda: TODAY)


def _expected(ip=IP, ua=UA) -> str:
    return experiments.data_ab({e.name: experiments.arm_for(ip, ua, e) for e in LIVE[:2]})


def _signup_ab(app_module, user_id):
    from models import User
    with app_module.session_scope() as s:
        return s.query(User).filter_by(id=user_id).one().signup_ab


def _set_signup_ab(app_module, user_id, value):
    from models import User
    with app_module.session_scope() as s:
        s.query(User).filter_by(id=user_id).one().signup_ab = value


def _dev_login(client, email, headers=HDR) -> dict:
    r = client.get(f"/dev-login?email={email}", headers=headers)
    assert r.status_code == 302
    return client.get("/api/me").get_json()["user"]


def _resolve_in_request(app_module, headers=HDR, **kw):
    from auth import Profile, _resolve_identity
    current = kw.pop("current_user_id", None)
    with app_module.app.test_request_context("/auth/callback", headers=headers):
        return _resolve_identity(Profile(**kw), current_user_id=current)


# --- rule 4 stamps -----------------------------------------------------------------------------------

def test_new_account_is_stamped_with_the_arms_its_request_draws(client, app_module, live):
    me = _dev_login(client, "sab-new@example.com")
    label = _signup_ab(app_module, me["id"])
    assert label == _expected()
    toks = dict(t.split(":") for t in label.split())
    assert set(toks) == {"sig", "sig2"}                       # every LIVE experiment, any page; not "old"
    assert toks["sig"] == experiments.arm_for(IP, UA, LIVE[0])
    assert toks["sig2"] == experiments.arm_for(IP, UA, LIVE[1])


def test_label_follows_ip_and_ua_and_never_stores_them(client, app_module, live):
    other = {"X-Forwarded-For": "198.51.100.9, 10.0.0.1", "User-Agent": "Other/1.0"}
    me = _dev_login(client, "sab-other@example.com", headers=other)
    label = _signup_ab(app_module, me["id"])
    assert label == _expected("198.51.100.9", "Other/1.0")    # first X-Forwarded-For hop, like pages.client_ip
    assert "198.51.100.9" not in label and "Other" not in label


def test_no_live_experiment_stamps_none_not_an_empty_string(client, app_module, none_live):
    me = _dev_login(client, "sab-none@example.com")
    assert _signup_ab(app_module, me["id"]) is None


def test_no_request_context_stamps_none(app_module, live):
    from auth import Profile, _resolve_identity
    out = _resolve_identity(Profile("google", "sab-noctx", "sab-noctx@example.com", True, "N"))
    assert _signup_ab(app_module, out["id"]) is None


def test_an_experiment_bug_never_breaks_sign_in(client, app_module, live, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("registry exploded")
    monkeypatch.setattr(experiments, "live_experiments", boom)
    me = _dev_login(client, "sab-boom@example.com")
    assert me is not None and me["email"] == "sab-boom@example.com"
    assert _signup_ab(app_module, me["id"]) is None


def test_label_is_truncated_to_the_column(app_module, monkeypatch):
    many = [_exp(name=f"exp_with_a_long_name_{i:02d}", page=f"/p{i}", salt=f"s{i}") for i in range(20)]
    monkeypatch.setattr(experiments, "EXPERIMENTS", many)
    monkeypatch.setattr(experiments, "today_utc", lambda: TODAY)
    import auth
    with app_module.app.test_request_context("/", headers=HDR):
        label = auth.signup_arms_label()
    assert label is not None and len(label) == 200


# --- rules 1-3 never stamp ---------------------------------------------------------------------------

def test_repeat_sign_in_never_rewrites_the_label(client, app_module, live):
    stamped = _dev_login(client, "sab-r1a@example.com")
    _set_signup_ab(app_module, stamped["id"], "x:y")
    _dev_login(client, "sab-r1a@example.com", headers={"X-Forwarded-For": "192.0.2.1", "User-Agent": "Z"})
    assert _signup_ab(app_module, stamped["id"]) == "x:y"

    unstamped = _dev_login(client, "sab-r1b@example.com")
    _set_signup_ab(app_module, unstamped["id"], None)        # an account from before any experiment
    _dev_login(client, "sab-r1b@example.com")
    assert _signup_ab(app_module, unstamped["id"]) is None


def test_linking_another_provider_never_rewrites_the_label(app_module, live):
    base = _resolve_in_request(app_module, provider="google", subject="sab-r2", email="sab-r2@example.com",
                               email_verified=True, name="R2")
    _set_signup_ab(app_module, base["id"], None)
    linked = _resolve_in_request(app_module, provider="github", subject="sab-r2-gh",
                                 email="sab-r2-gh@example.com", email_verified=True, name="R2",
                                 current_user_id=base["id"])
    assert linked["id"] == base["id"] and _signup_ab(app_module, base["id"]) is None
    _set_signup_ab(app_module, base["id"], "x:y")
    _resolve_in_request(app_module, provider="email", subject="sab-r2-mail@example.com",
                        email="sab-r2-mail@example.com", email_verified=True, name="R2",
                        current_user_id=base["id"])
    assert _signup_ab(app_module, base["id"]) == "x:y"


def test_verified_email_match_never_rewrites_the_label(app_module, live):
    first = _resolve_in_request(app_module, provider="google", subject="sab-r3", email="sab-r3@example.com",
                                email_verified=True, name="R3")
    _set_signup_ab(app_module, first["id"], "x:y")
    second = _resolve_in_request(app_module, provider="github", subject="sab-r3-gh",
                                 email="SAB-R3@example.com", email_verified=True, name="R3")
    assert second["id"] == first["id"] and _signup_ab(app_module, first["id"]) == "x:y"

    plain = _resolve_in_request(app_module, provider="google", subject="sab-r3n", email="sab-r3n@example.com",
                                email_verified=True, name="R3n")
    _set_signup_ab(app_module, plain["id"], None)
    again = _resolve_in_request(app_module, provider="email", subject="sab-r3n@example.com",
                                email="sab-r3n@example.com", email_verified=True, name="R3n")
    assert again["id"] == plain["id"] and _signup_ab(app_module, plain["id"]) is None


# --- the boot migration ------------------------------------------------------------------------------

def test_ensure_user_columns_adds_signup_ab_to_an_old_users_table(tmp_path, monkeypatch):
    import db
    old = create_engine(f"sqlite:///{(tmp_path / 'old.db').as_posix()}")
    with old.begin() as conn:
        conn.execute(text("CREATE TABLE users (id INTEGER PRIMARY KEY AUTOINCREMENT, google_sub VARCHAR(255), "
                          "email VARCHAR(320), name VARCHAR(255), created_at DATETIME)"))
        conn.execute(text("INSERT INTO users (google_sub, email, name) VALUES ('g:1', 'old@example.com', 'O')"))
    monkeypatch.setattr(db, "engine", old)
    db._ensure_user_columns()
    db._ensure_user_columns()  # idempotent
    cols = {c["name"] for c in inspect(old).get_columns("users")}
    assert {"signup_ab", "token_balance", "unlimited_tokens"} <= cols
    with old.connect() as conn:
        assert conn.execute(text("SELECT signup_ab FROM users")).fetchall() == [(None,)]
    old.dispose()
