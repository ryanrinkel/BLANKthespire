"""Billing: donation math + presets, donate validation, webhook idempotency, refund clawback, history."""
from __future__ import annotations

import logging

from conftest import H, login

LOG = logging.getLogger("test-billing")


def _user_id(app_module, email):
    from models import User
    with app_module.session_scope() as s:
        return s.query(User).filter_by(email=email).one().id


def _balance(app_module, uid):
    from models import User
    with app_module.session_scope() as s:
        return s.query(User).filter_by(id=uid).one().token_balance


def _paid_session(sid, uid, tokens, cents, pid="donation", intent=None):
    return {"id": sid, "payment_status": "paid", "payment_intent": intent or f"pi_{sid}",
            "amount_total": cents, "currency": "usd", "client_reference_id": str(uid),
            "metadata": {"user_id": str(uid), "tokens": str(tokens), "price_id": pid}}


def _event(etype, obj):
    return {"type": etype, "data": {"object": obj}}


def test_thank_you_tokens_are_one_per_dollar_plus_tier_bonus():
    import billing
    assert billing.TOKENS_PER_DOLLAR == 1
    assert billing.BONUS_TIERS == [(1000, 10), (2000, 20), (5000, 30)]
    # base: one per WHOLE dollar, cents never round up
    assert billing.tokens_for(100) == 1
    assert billing.tokens_for(350) == 3
    assert billing.tokens_for(99) == 0
    assert billing.tokens_for(999) == 9          # just under the first tier: no bonus
    # +10% from $10, +20% from $20, +30% from $50 — the bonus floors too
    assert billing.tokens_for(1000) == 11
    assert billing.tokens_for(1500) == 16        # 15 + floor(1.5)
    assert billing.tokens_for(1999) == 20        # 19 + floor(1.9)
    assert billing.tokens_for(2000) == 24
    assert billing.tokens_for(3500) == 42
    assert billing.tokens_for(4999) == 58        # 49 + floor(9.8)
    assert billing.tokens_for(5000) == 65
    assert billing.tokens_for(10000) == 130


def test_preset_env_parsing_skips_junk_and_falls_back():
    import billing
    assert billing._parse_presets("500, junk, 300, 10, 99999999") == [500, 300]
    assert billing._parse_presets("") == []
    assert billing.PRESETS  # never empty: falls back to DEFAULT_PRESETS
    assert all(billing.MIN_DONATION_CENTS <= p <= billing.MAX_DONATION_CENTS for p in billing.PRESETS)


def test_billing_probe_and_donate_when_disabled(client):
    login(client)
    b = client.get("/api/billing").get_json()
    assert b["enabled"] is False and b["tokens_per_dollar"] == 1
    assert b["min_cents"] == 100 and b["max_cents"] == 50000 and b["presets"]
    # the tiers reach the UI even with billing off, so it can advertise them
    assert b["bonus_tiers"] == [{"min_cents": 1000, "pct": 10},
                                {"min_cents": 2000, "pct": 20},
                                {"min_cents": 5000, "pct": 30}]
    assert "packs" not in b                                            # the pack era is gone from the API
    assert client.post("/api/donate", json={"amount_cents": 500}, headers=H).status_code == 503
    assert client.post("/api/checkout", json={"pack": "pack_5"}, headers=H).status_code == 404
    assert client.post("/webhook/stripe", data=b"{}").status_code == 503


def test_credit_is_idempotent_across_both_delivery_paths(client, app_module):
    import billing
    login(client, "donor@example.com")
    uid = _user_id(app_module, "donor@example.com")
    sess = _paid_session("cs_a1", uid, 10, 1000)
    assert billing._credit_purchase(sess) == (True, 15)
    assert billing._credit_purchase(sess) == (False, 15)          # second delivery: no double credit
    billing.handle_stripe_event(_event("checkout.session.completed", sess), LOG)
    assert _balance(app_module, uid) == 15
    hist = client.get("/api/purchases").get_json()["purchases"]
    assert len(hist) == 1 and hist[0]["tokens"] == 10 and hist[0]["kind"] == "donation"
    assert hist[0]["amount_cents"] == 1000 and hist[0]["status"] == "paid"


def test_pack_era_rows_still_show_in_history(client, app_module):
    """Purchases made while token packs were live (2026-09-08..16) keep their price_id and stay visible."""
    import billing
    login(client, "legacy@example.com")
    uid = _user_id(app_module, "legacy@example.com")
    billing._credit_purchase(_paid_session("cs_old", uid, 11, 1000, pid="pack_11"))
    hist = client.get("/api/purchases").get_json()["purchases"]
    assert hist[0]["kind"] == "pack" and hist[0]["tokens"] == 11


def test_unpaid_or_foreign_sessions_are_ignored(app_module, client):
    import billing
    login(client, "ignored@example.com")
    uid = _user_id(app_module, "ignored@example.com")
    obj = _paid_session("cs_unpaid", uid, 5, 500)
    obj["payment_status"] = "unpaid"
    billing.handle_stripe_event(_event("checkout.session.completed", obj), LOG)
    obj2 = _paid_session("cs_nometa", uid, 5, 500)
    obj2["metadata"] = {}
    billing.handle_stripe_event(_event("checkout.session.completed", obj2), LOG)
    billing.handle_stripe_event(_event("some.other.event", {}), LOG)
    assert _balance(app_module, uid) == 5


def test_refund_claws_back_only_unspent_tokens(client, app_module):
    import billing
    from models import Purchase
    login(client, "refunder@example.com")
    uid = _user_id(app_module, "refunder@example.com")
    billing._credit_purchase(_paid_session("cs_r1", uid, 20, 2000, intent="pi_r1"))
    assert _balance(app_module, uid) == 25
    # spend most of it, then refund: only what is left can come back
    from models import User
    with app_module.session_scope() as s:
        s.query(User).filter_by(id=uid).one().token_balance = 10
    billing.handle_stripe_event(_event("charge.refunded", {"payment_intent": "pi_r1"}), LOG)
    assert _balance(app_module, uid) == 0
    with app_module.session_scope() as s:
        assert s.query(Purchase).filter_by(stripe_payment_intent="pi_r1").one().status == "refunded"
    # a second refund event for the same intent is a no-op
    with app_module.session_scope() as s:
        s.query(User).filter_by(id=uid).one().token_balance = 7
    billing.handle_stripe_event(_event("charge.refunded", {"payment_intent": "pi_r1"}), LOG)
    assert _balance(app_module, uid) == 7
    assert client.get("/api/purchases").get_json()["purchases"][0]["status"] == "refunded"


def test_refund_of_unknown_intent_is_harmless():
    import billing
    assert billing._refund_purchase("pi_nope") is None
