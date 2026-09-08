"""Token accounting: free-daily-first precedence, UTC rollover, reserve/refund of the right kind, the 402 path,
the per-IP free-forge cap, and the usage ledger."""
from __future__ import annotations

from conftest import H, login, sse_events


def _today():
    from models import _utc_today
    return _utc_today()


def _user(app_module, email):
    from models import User
    with app_module.session_scope() as s:
        return s.query(User).filter_by(email=email).one()


def _set(app_module, email, **fields):
    from models import User
    with app_module.session_scope() as s:
        u = s.query(User).filter_by(email=email).one()
        for k, v in fields.items():
            setattr(u, k, v)


# --- the model-level rules ------------------------------------------------------------------------------

def test_free_token_is_spent_before_paid_and_paid_is_untouched():
    from models import User, spend_token, free_token_available
    u = User(google_sub="x", token_balance=9)
    assert free_token_available(u, today="2026-09-08")
    assert spend_token(u, today="2026-09-08") == "free"
    assert u.token_balance == 9            # a buyer holding 9 tokens still got the free one
    assert not free_token_available(u, today="2026-09-08")
    assert spend_token(u, today="2026-09-08") == "paid"
    assert u.token_balance == 8


def test_free_token_returns_after_utc_rollover():
    from models import User, spend_token
    u = User(google_sub="x", token_balance=0)
    assert spend_token(u, today="2026-09-08") == "free"
    assert spend_token(u, today="2026-09-08") is None   # nothing left today
    assert spend_token(u, today="2026-09-09") == "free"  # tomorrow: free again, balance still 0
    assert u.token_balance == 0


def test_unspend_restores_the_right_kind():
    from models import User, spend_token, unspend_token, free_token_available
    u = User(google_sub="x", token_balance=2)
    spend_token(u, today="2026-09-08")
    unspend_token(u, "free", day="2026-09-08")
    assert free_token_available(u, today="2026-09-08")
    spend_token(u, today="2026-09-08")
    assert spend_token(u, today="2026-09-08") == "paid" and u.token_balance == 1
    unspend_token(u, "paid", day="2026-09-08")
    assert u.token_balance == 2
    # A refund of a "free" token after the day rolled over must NOT clear the new day's stamp.
    u.last_free_token_day = "2026-09-09"
    unspend_token(u, "free", day="2026-09-08")
    assert u.last_free_token_day == "2026-09-09"


def test_me_reports_free_flag_and_paid_balance(client):
    me = login(client, "me@example.com")
    assert me["token_balance"] == 5 and me["free_token_available"] is True and me["unlimited"] is False


# --- the forge route ----------------------------------------------------------------------------------

def _forge(client, mode="token", **extra):
    body = {"concept": "a plague doctor", "mode": mode, **extra}
    return client.post("/api/forge-class", json=body, headers=H)


def test_token_forge_spends_free_first_then_paid(client, app_module, stub_forge):
    login(client, "spend@example.com")
    ev = sse_events(_forge(client))
    assert ev[0][0] == "progress" and ev[0][1]["free_token_available"] is False
    assert ev[0][1]["token_balance"] == 5
    assert ev[-1][0] == "result" and ev[-1][1]["token_balance"] == 5 and ev[-1][1]["slug"]
    assert ev[-1][1]["share_url"].endswith("/api/deck/" + ev[-1][1]["slug"])
    ev2 = sse_events(_forge(client))
    assert ev2[-1][0] == "result" and ev2[-1][1]["token_balance"] == 4
    assert ev2[-1][1]["free_token_available"] is False
    assert stub_forge.calls[-1]["ollama_mix"] is True


def test_failed_forge_refunds_the_free_token(client, app_module, stub_forge):
    login(client, "refund@example.com")
    stub_forge.error = "endpoint exploded"
    ev = sse_events(_forge(client))
    assert ev[-1][0] == "error" and "exploded" in ev[-1][1]["error"]
    assert ev[-1][1]["free_token_available"] is True and ev[-1][1]["token_balance"] == 5
    stub_forge.error = None
    # ...and the free-forge IP cap was un-counted too (cap is 2 in tests): two more free forges still fit.
    assert sse_events(_forge(client))[-1][0] == "result"


def test_failed_forge_refunds_a_paid_token(client, app_module, stub_forge):
    login(client, "refundpaid@example.com")
    _set(app_module, "refundpaid@example.com", last_free_token_day=_today(), token_balance=3)
    stub_forge.error = "boom"
    ev = sse_events(_forge(client))
    assert ev[0][1]["token_balance"] == 2       # charged up front
    assert ev[-1][1]["token_balance"] == 3      # refunded on the error event
    stub_forge.error = None


def test_402_when_nothing_to_spend(client, app_module, stub_forge):
    login(client, "broke@example.com")
    _set(app_module, "broke@example.com", last_free_token_day=_today(), token_balance=0)
    r = _forge(client)
    assert r.status_code == 402
    assert r.get_json()["free_token_available"] is False


def test_unlimited_accounts_never_spend(client, app_module, stub_forge):
    login(client, "unlimited@example.com")
    _set(app_module, "unlimited@example.com", token_balance=1)
    for _ in range(3):
        assert sse_events(_forge(client))[-1][0] == "result"
    u = _user(app_module, "unlimited@example.com")
    assert u.token_balance == 1 and u.last_free_token_day is None


def test_byok_forge_spends_nothing(client, app_module, stub_forge):
    login(client, "byok@example.com")
    ev = sse_events(_forge(client, mode="anthropic", key={"api_key": "sk-ant-test", "model": "claude-x"}))
    assert ev[-1][0] == "result" and "token_balance" not in ev[-1][1]
    u = _user(app_module, "byok@example.com")
    assert u.token_balance == 5 and u.last_free_token_day is None


def test_per_ip_cap_limits_free_forges_but_not_paid(app_module, stub_forge):
    # Three accounts on one address: the third FREE forge is refused (cap=2), a paid forge is not.
    c1, c2, c3 = (app_module.app.test_client() for _ in range(3))
    login(c1, "farm1@example.com"); login(c2, "farm2@example.com"); login(c3, "farm3@example.com")
    assert sse_events(_forge(c1))[-1][0] == "result"
    assert sse_events(_forge(c2))[-1][0] == "result"
    r = _forge(c3)
    assert r.status_code == 429 and "free forges" in r.get_json()["error"]
    _set(app_module, "farm3@example.com", last_free_token_day=_today(), token_balance=2)
    assert sse_events(_forge(c3))[-1][0] == "result"   # paid: not IP-capped


def test_usage_ledger_records_rows_and_cost(client, app_module, stub_forge):
    from models import ForgeUsage
    login(client, "usage@example.com")
    ev = sse_events(_forge(client))
    class_id = ev[-1][1]["id"]
    with app_module.session_scope() as s:
        rows = s.query(ForgeUsage).filter_by(class_id=class_id).all()
        by = {(r.role, r.model): r for r in rows}
    assert set(by) == {("cards", "glm-5.2"), ("structure", "z-ai/glm-5.2")}
    r = by[("cards", "glm-5.2")]
    assert (r.input_tokens, r.output_tokens, r.cached_tokens, r.calls) == (1000, 200, 300, 1)
    assert r.est_cost_micros == 0                       # Ollama flat plan: priced at zero
    assert r.token_kind == "free" and r.mode == "token" and r.ok == 1
    # OpenRouter overflow slug is priced: 500 in @ $0.49/M + 100 out @ $1.56/M = $0.000401
    assert by[("structure", "z-ai/glm-5.2")].est_cost_micros == 401


def test_byok_usage_rows_carry_no_cost(client, app_module, stub_forge):
    from models import ForgeUsage
    login(client, "usagebyok@example.com")
    ev = sse_events(_forge(client, mode="byok",
                           key={"base_url": "https://api.openai.com/v1", "api_key": "sk-x", "model": "gpt"}))
    class_id = ev[-1][1]["id"]
    with app_module.session_scope() as s:
        rows = s.query(ForgeUsage).filter_by(class_id=class_id).all()
    assert rows and all(r.est_cost_micros is None and r.mode == "byok" for r in rows)
