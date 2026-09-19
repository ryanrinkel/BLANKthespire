"""Billing v3: the fixed tier table, the Stripe fee pass-through, tier-only /api/donate, the two-line-item
checkout session, webhook idempotency, refund clawback, and history (including pre-v3 rows)."""
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


def _paid_session(sid, uid, tokens, cents, pid="donation", intent=None, net=None):
    meta = {"user_id": str(uid), "tokens": str(tokens), "price_id": pid}
    if net is not None:
        meta["net_cents"] = str(net)
    return {"id": sid, "payment_status": "paid", "payment_intent": intent or f"pi_{sid}",
            "amount_total": cents, "currency": "usd", "client_reference_id": str(uid), "metadata": meta}


def _event(etype, obj):
    return {"type": etype, "data": {"object": obj}}


# --- the tier table + fee math -------------------------------------------------------------------------

def test_tier_table_maps_ids_to_tokens():
    import billing
    assert {tid: tokens for tid, (_net, tokens) in billing.DONATION_TIERS.items()} == {
        "t3": 2, "t5": 4, "t10": 10, "t20": 20, "t50": 50}
    assert [net for net, _t in billing.DONATION_TIERS.values()] == [300, 500, 1000, 2000, 5000]
    assert list(billing.DONATION_TIERS) == ["t3", "t5", "t10", "t20", "t50"]   # dict order = display order
    assert billing.tier_info("nope") is None
    assert billing.tier_info("t5") == {"id": "t5", "net_cents": 500, "fee_cents": 46,
                                       "gross_cents": 546, "tokens": 4}


def test_gross_for_nets_the_tier_after_stripes_cut():
    import billing
    assert [billing.gross_for(n) for n in (300, 500, 1000, 2000, 5000)] == [340, 546, 1061, 2091, 5181]
    assert [billing.fee_for(n) for n in (300, 500, 1000, 2000, 5000)] == [40, 46, 61, 91, 181]
    # the point of the exercise: after 2.9% + 30c, what lands is at least the tier amount
    for net in (300, 500, 1000, 2000, 5000):
        gross = billing.gross_for(net)
        assert gross - round(gross * 0.029 + 30) >= net


def test_gross_for_follows_a_changed_fee_config(monkeypatch):
    import billing
    monkeypatch.setattr(billing, "STRIPE_FEE_PCT", 5.0)
    monkeypatch.setattr(billing, "STRIPE_FEE_FIXED_CENTS", 50)
    assert billing.gross_for(1000) == 1106          # ceil(1050 / 0.95)
    assert billing.fee_for(1000) == 106
    assert billing.tier_info("t10")["gross_cents"] == 1106
    # a zero-fee world charges exactly the donation
    monkeypatch.setattr(billing, "STRIPE_FEE_PCT", 0.0)
    monkeypatch.setattr(billing, "STRIPE_FEE_FIXED_CENTS", 0)
    assert billing.gross_for(500) == 500 and billing.fee_for(500) == 0


# --- the routes ----------------------------------------------------------------------------------------

def test_billing_probe_ships_the_tiers_even_when_disabled(client):
    login(client)
    b = client.get("/api/billing").get_json()
    assert b["enabled"] is False and b["currency"] == "usd"
    assert [t["id"] for t in b["tiers"]] == ["t3", "t5", "t10", "t20", "t50"]
    assert b["tiers"][1] == {"id": "t5", "net_cents": 500, "fee_cents": 46,
                            "gross_cents": 546, "tokens": 4}
    for t in b["tiers"]:
        assert t["net_cents"] + t["fee_cents"] == t["gross_cents"]
    # the retired knobs are gone from the API
    assert "presets" not in b and "tokens_per_dollar" not in b and "bonus_tiers" not in b
    assert "packs" not in b
    assert client.post("/api/donate", json={"tier": "t5"}, headers=H).status_code == 503
    assert client.post("/api/checkout", json={"pack": "pack_5"}, headers=H).status_code == 404
    assert client.post("/webhook/stripe", data=b"{}").status_code == 503


def test_donate_rejects_missing_unknown_and_legacy_bodies(client, stripe_stub):
    login(client, "picky@example.com")
    for body in ({}, {"tier": ""}, {"tier": "t7"}, {"tier": "pack_5"}, {"amount_cents": 500}):
        r = client.post("/api/donate", json=body, headers=H)
        assert r.status_code == 400, body
        assert r.get_json()["error"] == "pick one of the donation amounts."
    assert stripe_stub.sessions == []          # nothing reached Stripe


def test_donate_creates_a_two_line_item_session(client, app_module, stripe_stub):
    login(client, "giver@example.com")
    uid = _user_id(app_module, "giver@example.com")
    r = client.post("/api/donate", json={"tier": "t5"}, headers=H)
    assert r.status_code == 200 and r.get_json()["url"] == "https://stripe.test/c/cs_stub1"
    kw = stripe_stub.sessions[-1]
    assert kw["mode"] == "payment" and kw["submit_type"] == "donate"
    items = kw["line_items"]
    assert [i["price_data"]["product_data"]["name"] for i in items] == [
        "Donation — BLANK the spire", "Card processing fee"]
    assert [i["price_data"]["unit_amount"] for i in items] == [500, 46]
    assert sum(i["price_data"]["unit_amount"] for i in items) == 546   # == gross_for(500)
    assert all(i["quantity"] == 1 and i["price_data"]["currency"] == "usd" for i in items)
    assert kw["metadata"] == {"user_id": str(uid), "tokens": "4", "price_id": "t5", "net_cents": "500"}
    assert kw["client_reference_id"] == str(uid) and kw["customer_email"] == "giver@example.com"
    assert kw["success_url"] == ("http://testserver/app?purchase=success"
                                 "&session_id={CHECKOUT_SESSION_ID}")
    assert kw["cancel_url"] == "http://testserver/app?purchase=cancel"


# --- crediting, refunds, history -----------------------------------------------------------------------

def test_credit_stores_gross_and_net_and_reports_the_fee(client, app_module):
    import billing
    login(client, "split@example.com")
    uid = _user_id(app_module, "split@example.com")
    # what Stripe reports back for a t5 checkout: amount_total is the GROSS the card paid
    assert billing._credit_purchase(_paid_session("cs_t5", uid, 4, 546, pid="t5", net=500)) == (True, 4)
    row = client.get("/api/purchases").get_json()["purchases"][0]
    assert row["kind"] == "donation" and row["tokens"] == 4
    assert (row["amount_cents"], row["net_cents"], row["fee_cents"]) == (546, 500, 46)


def test_credit_is_idempotent_across_both_delivery_paths(client, app_module):
    import billing
    login(client, "donor@example.com")
    uid = _user_id(app_module, "donor@example.com")
    sess = _paid_session("cs_a1", uid, 10, 1061, pid="t10", net=1000)
    assert billing._credit_purchase(sess) == (True, 10)
    assert billing._credit_purchase(sess) == (False, 10)          # second delivery: no double credit
    billing.handle_stripe_event(_event("checkout.session.completed", sess), LOG)
    assert _balance(app_module, uid) == 10
    hist = client.get("/api/purchases").get_json()["purchases"]
    assert len(hist) == 1 and hist[0]["tokens"] == 10 and hist[0]["kind"] == "donation"
    assert hist[0]["amount_cents"] == 1061 and hist[0]["status"] == "paid"


def test_pack_era_rows_still_show_in_history(client, app_module):
    """Purchases made while token packs were live (2026-09-08..16), and pay-what-you-want donations from
    before the fixed tiers, keep their price_id, report no fee split, and stay visible."""
    import billing
    login(client, "legacy@example.com")
    uid = _user_id(app_module, "legacy@example.com")
    billing._credit_purchase(_paid_session("cs_old", uid, 11, 1000, pid="pack_11"))
    billing._credit_purchase(_paid_session("cs_pwyw", uid, 5, 500, pid="donation"))
    hist = {p["kind"]: p for p in client.get("/api/purchases").get_json()["purchases"]}
    assert hist["pack"]["tokens"] == 11
    assert hist["donation"]["tokens"] == 5
    for row in hist.values():
        assert row["net_cents"] is None and row["fee_cents"] is None


def test_unpaid_or_foreign_sessions_are_ignored(app_module, client):
    import billing
    login(client, "ignored@example.com")
    uid = _user_id(app_module, "ignored@example.com")
    obj = _paid_session("cs_unpaid", uid, 5, 546, pid="t5", net=500)
    obj["payment_status"] = "unpaid"
    billing.handle_stripe_event(_event("checkout.session.completed", obj), LOG)
    obj2 = _paid_session("cs_nometa", uid, 5, 546)
    obj2["metadata"] = {}
    billing.handle_stripe_event(_event("checkout.session.completed", obj2), LOG)
    billing.handle_stripe_event(_event("some.other.event", {}), LOG)
    assert _balance(app_module, uid) == 0


def test_refund_claws_back_only_unspent_tokens(client, app_module):
    import billing
    from models import Purchase, User
    login(client, "refunder@example.com")
    uid = _user_id(app_module, "refunder@example.com")
    billing._credit_purchase(_paid_session("cs_r1", uid, 20, 2091, pid="t20", net=2000, intent="pi_r1"))
    assert _balance(app_module, uid) == 20
    # spend most of it, then refund: only what is left can come back
    with app_module.session_scope() as s:
        s.query(User).filter_by(id=uid).one().token_balance = 5
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
