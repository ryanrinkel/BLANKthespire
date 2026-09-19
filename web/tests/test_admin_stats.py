"""The operator dashboard (/api/admin/stats), the BYOK cost estimate (/api/forge-estimate), and the admin
flag on /api/me. conftest pins BTSWEB_UNLIMITED_EMAILS=unlimited@example.com and sets no
BTSWEB_ADMIN_EMAILS, so the unlimited list IS the admin list here — exactly the prod default."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from conftest import H, login, seed_tokens, sse_events

ADMIN = "unlimited@example.com"


def _naive_utc(offset_days: float = 0.0) -> datetime:
    return (datetime.now(timezone.utc) - timedelta(days=offset_days)).replace(tzinfo=None)


def _user_id(app_module, email: str) -> int:
    from models import User
    with app_module.session_scope() as s:
        return s.query(User).filter_by(email=email).one().id


def _seed(app_module, user_id: int, forge_id: str, *, mode="token", status="done", token_kind="free",
          refunded=0, age_days=0.0, provider="hosted", model="glm-5.2", ok=1, cost=None,
          calls=3, inp=1000, out=200, cached=300):
    """One forge attempt + its usage row, written straight through the session (no forge required)."""
    from models import ForgeJob, ForgeUsage
    when = _naive_utc(age_days)
    with app_module.session_scope() as s:
        s.add(ForgeJob(id=forge_id, user_id=user_id, mode=mode, token_kind=token_kind, status=status,
                       refunded=refunded, concept="seeded", started_at=when))
        s.add(ForgeUsage(user_id=user_id, forge_id=forge_id, mode=mode, provider=provider, model=model,
                         role="cards", calls=calls, input_tokens=inp, output_tokens=out,
                         cached_tokens=cached, est_cost_micros=cost, ok=ok, token_kind=token_kind,
                         created_at=when))


def _clear(app_module):
    """Empty the two ledgers so a test can assert on exactly what it seeds."""
    from models import ForgeJob, ForgeUsage
    with app_module.session_scope() as s:
        s.query(ForgeUsage).delete()
        s.query(ForgeJob).delete()


# --- who may look ---------------------------------------------------------------------------------------

def test_non_admin_is_forbidden(client):
    login(client, "nobody@example.com")
    r = client.get("/api/admin/stats")
    assert r.status_code == 403 and r.get_json() == {"error": "forbidden"}


def test_signed_out_is_401(client):
    client.post("/logout", headers=H)
    assert client.get("/api/admin/stats").status_code == 401


def test_me_carries_the_admin_flag(client):
    assert login(client, "nobody@example.com")["admin"] is False
    assert login(client, ADMIN)["admin"] is True


# --- the payload ----------------------------------------------------------------------------------------

def test_admin_gets_the_documented_shape(client, app_module):
    login(client, ADMIN)
    body = client.get("/api/admin/stats").get_json()
    assert set(body) == {"days", "since", "forges", "users", "daily", "hosted", "models", "providers",
                         "donations"}
    assert body["days"] == 30 and isinstance(body["since"], str)
    assert set(body["forges"]) == {"total", "ok", "failed", "refunded", "by_mode", "by_token_kind"}
    assert set(body["forges"]["by_mode"]) == {"token", "byok", "fake"}
    assert set(body["forges"]["by_token_kind"]) == {"free", "paid", "unlimited"}
    assert set(body["users"]) == {"forgers", "accounts"} and body["users"]["accounts"] >= 1
    assert set(body["hosted"]) == {"forges", "calls", "input_tokens", "cached_tokens", "output_tokens",
                                   "est_cost_usd"}
    assert set(body["donations"]) == {"count", "amount_cents", "tokens"}
    assert isinstance(body["daily"], list) and isinstance(body["models"], list)
    assert isinstance(body["providers"], list)


def test_days_parameter_is_clamped_to_the_allowed_windows(client, app_module):
    login(client, ADMIN)
    for asked, expect in ((7, 7), (30, 30), (90, 90), (0, 0), (5, 30), ("banana", 30), (-1, 30)):
        body = client.get(f"/api/admin/stats?days={asked}").get_json()
        assert body["days"] == expect
    assert client.get("/api/admin/stats?days=0").get_json()["since"] is None


def test_counts_reflect_seeded_jobs_and_usage(client, app_module):
    login(client, ADMIN)
    _clear(app_module)
    uid = _user_id(app_module, ADMIN)
    other = _user_id(app_module, login(client, "second@example.com")["email"])
    login(client, ADMIN)
    _seed(app_module, uid, "a" * 32, mode="token", token_kind="free", cost=1_500_000)
    _seed(app_module, uid, "b" * 32, mode="token", status="failed", token_kind="paid", refunded=1,
          ok=0, cost=500_000)
    _seed(app_module, other, "c" * 32, mode="byok", token_kind=None, provider="api.openai.com",
          model="gpt-5", calls=7, inp=90, out=9, cached=0)
    _seed(app_module, uid, "d" * 32, mode="token", token_kind="unlimited", age_days=120, cost=None)

    body = client.get("/api/admin/stats?days=30").get_json()
    f = body["forges"]
    assert (f["total"], f["ok"], f["failed"], f["refunded"]) == (3, 2, 1, 1)   # the 120-day row is outside
    assert f["by_mode"] == {"token": 2, "byok": 1, "fake": 0}
    assert f["by_token_kind"] == {"free": 1, "paid": 1, "unlimited": 0}
    assert body["users"]["forgers"] == 2

    h = body["hosted"]
    assert h["forges"] == 2 and h["calls"] == 6 and h["input_tokens"] == 2000
    assert h["cached_tokens"] == 600 and h["output_tokens"] == 400
    assert h["est_cost_usd"] == 2.0                      # 1.5 + 0.5 USD of est_cost_micros

    assert {p["provider"]: p["forges"] for p in body["providers"]} == {"hosted": 2, "api.openai.com": 1}
    top = body["models"][0]
    assert (top["model"], top["provider"], top["mode"], top["forges"]) == ("glm-5.2", "hosted", "token", 2)
    assert {(m["model"], m["forges"]) for m in body["models"]} == {("glm-5.2", 2), ("gpt-5", 1)}

    days = {d["day"]: d for d in body["daily"]}
    today = _naive_utc().strftime("%Y-%m-%d")
    assert days[today]["token"] == 2 and days[today]["byok"] == 1
    assert [d["day"] for d in body["daily"]] == sorted(days)    # ascending

    # all time picks up the 120-day-old unlimited forge too
    everything = client.get("/api/admin/stats?days=0").get_json()
    assert everything["forges"]["total"] == 4
    assert everything["forges"]["by_token_kind"]["unlimited"] == 1
    assert everything["since"] is None
    _clear(app_module)


def test_hosted_cost_is_null_when_nothing_was_priced(client, app_module):
    login(client, ADMIN)
    _clear(app_module)
    _seed(app_module, _user_id(app_module, ADMIN), "e" * 32, cost=None)
    assert client.get("/api/admin/stats").get_json()["hosted"]["est_cost_usd"] is None
    _clear(app_module)


def test_donations_count_only_paid_purchases(client, app_module):
    from models import Purchase
    login(client, ADMIN)
    uid = _user_id(app_module, ADMIN)
    with app_module.session_scope() as s:
        s.query(Purchase).delete()
        s.add(Purchase(user_id=uid, stripe_session_id="cs_paid_1", price_id="donation", tokens=5,
                       amount_cents=500, status="paid", created_at=_naive_utc()))
        s.add(Purchase(user_id=uid, stripe_session_id="cs_refunded_1", price_id="donation", tokens=3,
                       amount_cents=300, status="refunded", created_at=_naive_utc()))
        s.add(Purchase(user_id=uid, stripe_session_id="cs_old_1", price_id="donation", tokens=9,
                       amount_cents=900, status="paid", created_at=_naive_utc(200)))
    body = client.get("/api/admin/stats?days=30").get_json()
    assert body["donations"] == {"count": 1, "amount_cents": 500, "tokens": 5}
    assert client.get("/api/admin/stats?days=0").get_json()["donations"]["count"] == 2
    with app_module.session_scope() as s:
        s.query(Purchase).delete()


# --- the BYOK estimate ----------------------------------------------------------------------------------

def test_forge_estimate_falls_back_on_an_empty_ledger(client, app_module):
    login(client, "estimate@example.com")
    _clear(app_module)
    body = client.get("/api/forge-estimate").get_json()
    assert body == {"forges_sampled": 0, "calls": 53, "input_tokens": 1_370_000,
                    "cached_tokens": 720_000, "output_tokens": 28_000, "fallback": True}


def test_forge_estimate_requires_login(client):
    client.post("/logout", headers=H)
    assert client.get("/api/forge-estimate").status_code == 401


def test_forge_estimate_averages_successful_forges(client, app_module):
    login(client, "estimate2@example.com")
    _clear(app_module)
    uid = _user_id(app_module, "estimate2@example.com")
    # two successful forges (the second has two rows, which must sum into ONE forge), plus a failed one
    # that must not be sampled at all.
    _seed(app_module, uid, "1" * 32, calls=10, inp=100, out=10, cached=50)
    _seed(app_module, uid, "2" * 32, calls=4, inp=40, out=6, cached=10)
    with app_module.session_scope() as s:
        from models import ForgeUsage
        s.add(ForgeUsage(user_id=uid, forge_id="2" * 32, mode="token", provider="hosted", model="gemma4:31b",
                         role="brainstorm", calls=6, input_tokens=60, output_tokens=4, cached_tokens=10, ok=1,
                         created_at=_naive_utc()))
    _seed(app_module, uid, "3" * 32, ok=0, status="failed", calls=999, inp=999, out=999, cached=999)

    body = client.get("/api/forge-estimate").get_json()
    assert body["fallback"] is False and body["forges_sampled"] == 2
    assert (body["calls"], body["input_tokens"], body["output_tokens"], body["cached_tokens"]) == (10, 100, 10, 35)
    _clear(app_module)


# --- the forge itself -----------------------------------------------------------------------------------

def test_the_web_forge_is_always_staged(client, app_module, stub_forge):
    """No request body can turn the staged creative front-end off any more."""
    login(client, "staged@example.com")
    for body in ({"concept": "x", "mode": "fake"},
                 {"concept": "x", "mode": "fake", "staged": False},
                 {"concept": "x", "mode": "fake", "staged": False, "triad": False}):
        assert sse_events(client.post("/api/forge-class", json=body, headers=H))[-1][0] == "result"
        assert stub_forge.calls[-1]["staged"] is True
    assert stub_forge.calls[-1]["triad"] is False   # triad still opts out; staged does not


def test_usage_rows_and_result_carry_the_provider_and_totals(client, app_module, stub_forge):
    from models import ForgeUsage
    login(client, "prov@example.com")
    seed_tokens(app_module, "prov@example.com", 1)
    ev = sse_events(client.post("/api/forge-class", headers=H, json={
        "concept": "x", "mode": "byok",
        "key": {"base_url": "https://API.OpenAI.com/v1", "api_key": "sk-x", "model": "gpt"}}))
    saved = ev[-1][1]
    # the stub meters two calls: 1000+500 in, 200+100 out, 300 cached
    assert saved["usage"] == {"calls": 2, "input_tokens": 1500, "cached_tokens": 300, "output_tokens": 300}
    with app_module.session_scope() as s:
        rows = s.query(ForgeUsage).filter_by(class_id=saved["id"]).all()
    assert rows and all(r.provider == "api.openai.com" for r in rows)

    ev = sse_events(client.post("/api/forge-class", json={"concept": "y", "mode": "token"}, headers=H))
    with app_module.session_scope() as s:
        rows = s.query(ForgeUsage).filter_by(class_id=ev[-1][1]["id"]).all()
    assert rows and all(r.provider == "hosted" for r in rows)
