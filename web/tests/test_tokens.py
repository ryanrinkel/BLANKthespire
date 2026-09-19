"""Token accounting under pricing v3: accounts start empty, a hosted forge spends one paid token, a failed
forge gives it back, the 402 path, the global daily kill-switch, and the usage ledger."""
from __future__ import annotations

from conftest import H, login, seed_tokens, sse_events


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

def test_spend_token_is_paid_only():
    from models import User, spend_token
    u = User(google_sub="x", token_balance=2)
    assert spend_token(u) == "paid" and u.token_balance == 1
    assert spend_token(u) == "paid" and u.token_balance == 0
    assert spend_token(u) is None            # empty: nothing to spend, the caller 402s
    assert u.token_balance == 0
    # No day stamp is written any more — the column is legacy and stays untouched.
    assert u.last_free_token_day is None


def test_unspend_restores_only_paid_tokens():
    from models import User, spend_token, unspend_token
    u = User(google_sub="x", token_balance=2)
    spend_token(u)
    unspend_token(u, "paid")
    assert u.token_balance == 2
    # A historical job row stamped "free" (pre-v3) must not mint a token that never left a balance.
    unspend_token(u, "free", day="2026-09-08")
    assert u.token_balance == 2


def test_new_account_has_zero_tokens(client, app_module):
    from models import INITIAL_TOKENS
    assert INITIAL_TOKENS == 0
    me = login(client, "fresh@example.com")
    assert me["token_balance"] == 0
    assert _user(app_module, "fresh@example.com").token_balance == 0


def test_me_reports_the_balance_and_nothing_free(client, app_module):
    login(client, "me@example.com")
    seed_tokens(app_module, "me@example.com", 3)
    me = client.get("/api/me").get_json()["user"]
    assert me["token_balance"] == 3 and me["unlimited"] is False
    assert "free_token_available" not in me


# --- the forge route ----------------------------------------------------------------------------------

def _forge(client, mode="token", **extra):
    body = {"concept": "a plague doctor", "mode": mode, **extra}
    return client.post("/api/forge-class", json=body, headers=H)


def test_token_forge_spends_a_paid_token(client, app_module, stub_forge):
    login(client, "spend@example.com")
    seed_tokens(app_module, "spend@example.com", 2)
    ev = sse_events(_forge(client))
    assert ev[0][0] == "progress" and ev[0][1]["token_balance"] == 1   # charged up front
    assert "free_token_available" not in ev[0][1]
    assert ev[-1][0] == "result" and ev[-1][1]["token_balance"] == 1 and ev[-1][1]["slug"]
    assert ev[-1][1]["share_url"].endswith("/deck/" + ev[-1][1]["slug"])  # the public share page
    ev2 = sse_events(_forge(client))
    assert ev2[-1][0] == "result" and ev2[-1][1]["token_balance"] == 0
    assert stub_forge.calls[-1]["ollama_mix"] is True
    # ...and now there is nothing left: the third forge is a 402, not a free one.
    assert _forge(client).status_code == 402


def test_failed_forge_refunds_a_paid_token(client, app_module, stub_forge):
    login(client, "refundpaid@example.com")
    seed_tokens(app_module, "refundpaid@example.com", 3)
    stub_forge.error = "boom"
    ev = sse_events(_forge(client))
    assert ev[0][1]["token_balance"] == 2       # charged up front
    assert ev[-1][1]["token_balance"] == 3      # refunded on the error event
    stub_forge.error = None


def test_402_when_nothing_to_spend(client, app_module, stub_forge):
    login(client, "broke@example.com")          # a fresh account: zero tokens, nothing to fall back on
    r = _forge(client)
    assert r.status_code == 402
    body = r.get_json()
    assert body["token_balance"] == 0 and "free_token_available" not in body
    assert "out of tokens" in body["error"]


def test_global_daily_cap_turns_forges_away(client, app_module, stub_forge, monkeypatch):
    """The one surviving guardrail: a budget kill-switch on the whole hosted path (0 = off in tests)."""
    login(client, "capped@example.com")
    seed_tokens(app_module, "capped@example.com", 5)
    monkeypatch.setattr(app_module.token_limiter, "daily_cap", 1)
    assert sse_events(_forge(client))[-1][0] == "result"
    r = _forge(client)
    assert r.status_code == 429 and "daily limit" in r.get_json()["error"]
    assert _user(app_module, "capped@example.com").token_balance == 4   # the refused forge cost nothing


def test_unlimited_accounts_never_spend(client, app_module, stub_forge):
    login(client, "unlimited@example.com")
    _set(app_module, "unlimited@example.com", token_balance=1)
    for _ in range(3):
        assert sse_events(_forge(client))[-1][0] == "result"
    assert _user(app_module, "unlimited@example.com").token_balance == 1


def test_byok_forge_spends_nothing(client, app_module, stub_forge):
    login(client, "byok@example.com")
    seed_tokens(app_module, "byok@example.com", 2)
    ev = sse_events(_forge(client, mode="anthropic", key={"api_key": "sk-ant-test", "model": "claude-x"}))
    assert ev[-1][0] == "result" and "token_balance" not in ev[-1][1]
    assert _user(app_module, "byok@example.com").token_balance == 2


def test_byok_forges_with_an_empty_balance(client, app_module, stub_forge):
    """The promoted path in v3: no tokens is no obstacle at all when you bring your own key."""
    login(client, "keyonly@example.com")
    ev = sse_events(_forge(client, mode="byok",
                           key={"base_url": "https://api.openai.com/v1", "api_key": "sk-x", "model": "gpt"}))
    assert ev[-1][0] == "result"
    assert _user(app_module, "keyonly@example.com").token_balance == 0


def test_usage_ledger_records_rows_and_cost(client, app_module, stub_forge):
    from models import ForgeUsage
    login(client, "usage@example.com")
    seed_tokens(app_module, "usage@example.com", 1)
    ev = sse_events(_forge(client))
    class_id = ev[-1][1]["id"]
    with app_module.session_scope() as s:
        rows = s.query(ForgeUsage).filter_by(class_id=class_id).all()
        by = {(r.role, r.model): r for r in rows}
    assert set(by) == {("cards", "glm-5.2"), ("structure", "z-ai/glm-5.2")}
    r = by[("cards", "glm-5.2")]
    assert (r.input_tokens, r.output_tokens, r.cached_tokens, r.calls) == (1000, 200, 300, 1)
    # Ollama's per-token list (the flat plan ended 2026-08-31): 700 uncached in @ $1.40/M + 200 out @
    # $4.40/M + 300 cached @ $0.26/M = $0.001938. Nothing metered these calls, so the real-cost column is NULL.
    assert r.est_cost_micros == 1938 and r.metered_cost_micros is None
    assert r.token_kind == "paid" and r.mode == "token" and r.ok == 1
    # OpenRouter glm-5.2: 500 in @ $0.5544/M + 100 out @ $1.7424/M = $0.000451
    assert by[("structure", "z-ai/glm-5.2")].est_cost_micros == 451


def test_byok_usage_rows_carry_no_cost(client, app_module, stub_forge):
    from models import ForgeUsage
    login(client, "usagebyok@example.com")
    ev = sse_events(_forge(client, mode="byok",
                           key={"base_url": "https://api.openai.com/v1", "api_key": "sk-x", "model": "gpt"}))
    class_id = ev[-1][1]["id"]
    with app_module.session_scope() as s:
        rows = s.query(ForgeUsage).filter_by(class_id=class_id).all()
    assert rows and all(r.est_cost_micros is None and r.mode == "byok" for r in rows)
