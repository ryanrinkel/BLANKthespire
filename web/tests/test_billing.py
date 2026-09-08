"""Billing: pack math, checkout validation, webhook idempotency, refund clawback, purchase history."""
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


def _paid_session(sid, uid, tokens, cents, pid="pack_5", intent=None):
    return {"id": sid, "payment_status": "paid", "payment_intent": intent or f"pi_{sid}",
            "amount_total": cents, "currency": "usd", "client_reference_id": str(uid),
            "metadata": {"user_id": str(uid), "tokens": str(tokens), "price_id": pid}}


def _event(etype, obj):
    return {"type": etype, "data": {"object": obj}}


def test_packs_have_no_single_token_pack_and_discount_with_size():
    import billing
    packs = billing.pack_catalog()
    assert [p["tokens"] for p in packs] == [5, 11, 24, 65]
    assert packs[0] == {"id": "pack_5", "tokens": 5, "amount_cents": 500, "currency": "usd",
                        "per_token_cents": 100.0}
    assert packs[1]["amount_cents"] == 1000
    per = [p["amount_cents"] / p["tokens"] for p in packs]
    assert per == sorted(per, reverse=True) and per[-1] < 100   # bigger packs are cheaper per token
    assert billing.find_pack("pack_1") is None


def test_pack_env_parsing_skips_junk_and_falls_back():
    import billing
    assert billing._parse_packs("11:1000, junk, 5:500, 3:10") == [(5, 500), (11, 1000)]
    assert billing._parse_packs("") == billing.DEFAULT_PACKS


def test_billing_probe_and_checkout_when_disabled(client):
    login(client)
    b = client.get("/api/billing").get_json()
    assert b["enabled"] is False and b["donations"] is False and len(b["packs"]) == 4
    assert client.post("/api/checkout", json={"pack": "pack_5"}, headers=H).status_code == 503
    assert client.post("/api/donate", json={"amount_cents": 500}, headers=H).status_code == 404
    assert client.post("/webhook/stripe", data=b"{}").status_code == 503


def test_credit_is_idempotent_across_both_delivery_paths(client, app_module):
    import billing
    login(client, "buyer@example.com")
    uid = _user_id(app_module, "buyer@example.com")
    sess = _paid_session("cs_a1", uid, 11, 1000, "pack_11")
    assert billing._credit_purchase(sess) == (True, 16)
    assert billing._credit_purchase(sess) == (False, 16)          # second delivery: no double credit
    billing.handle_stripe_event(_event("checkout.session.completed", sess), LOG)
    assert _balance(app_module, uid) == 16
    hist = client.get("/api/purchases").get_json()["purchases"]
    assert len(hist) == 1 and hist[0]["tokens"] == 11 and hist[0]["kind"] == "pack"
    assert hist[0]["amount_cents"] == 1000 and hist[0]["status"] == "paid"


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
    billing._credit_purchase(_paid_session("cs_r1", uid, 24, 2000, "pack_24", intent="pi_r1"))
    assert _balance(app_module, uid) == 29
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
