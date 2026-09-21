"""Billing v3: the fixed tier table, the custom whole-dollar amount, the Stripe fee pass-through,
/api/donate (tier OR custom, never both), the two-line-item checkout session, webhook idempotency, refund
clawback, and history (including pre-v3 rows and the retired $20/$50 tiers)."""
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
        "t3": 2, "t5": 4, "t10": 10}
    assert [net for net, _t in billing.DONATION_TIERS.values()] == [300, 500, 1000]
    assert list(billing.DONATION_TIERS) == ["t3", "t5", "t10"]   # dict order = display order
    assert billing.tier_info("nope") is None
    # the tiers retired on 2026-09-21 can't be bought any more...
    assert billing.tier_info("t20") is None and billing.tier_info("t50") is None
    assert billing.tier_info("t5") == {"id": "t5", "net_cents": 500, "fee_cents": 46,
                                       "gross_cents": 546, "tokens": 4}
    # ...but history still knows their rows (and custom gifts) were donations, not retired token packs
    for pid in ("t3", "t10", "t20", "t50", "custom"):
        assert pid in billing.DONATION_PRICE_IDS
    assert "t20" not in billing.DONATION_TIERS and "pack_5" not in billing.DONATION_PRICE_IDS


def test_gross_for_nets_the_tier_after_stripes_cut():
    import billing
    assert [billing.gross_for(n) for n in (300, 500, 1000, 1100, 50000)] == [340, 546, 1061, 1164, 51525]
    assert [billing.fee_for(n) for n in (300, 500, 1000, 1100, 50000)] == [40, 46, 61, 64, 1525]
    # the point of the exercise: after 2.9% + 30c, what lands is at least the donation amount
    for net in (300, 500, 1000, 1100, 2500, 50000):
        gross = billing.gross_for(net)
        assert gross - round(gross * 0.029 + 30) >= net


def test_gross_for_follows_a_changed_fee_config(monkeypatch):
    import billing
    monkeypatch.setattr(billing, "STRIPE_FEE_PCT", 5.0)
    monkeypatch.setattr(billing, "STRIPE_FEE_FIXED_CENTS", 50)
    assert billing.gross_for(1000) == 1106          # ceil(1050 / 0.95)
    assert billing.fee_for(1000) == 106
    assert billing.tier_info("t10")["gross_cents"] == 1106
    assert billing.custom_info(11)["gross_cents"] == 1211   # ceil(1150 / 0.95) — custom uses the same math
    # a zero-fee world charges exactly the donation
    monkeypatch.setattr(billing, "STRIPE_FEE_PCT", 0.0)
    monkeypatch.setattr(billing, "STRIPE_FEE_FIXED_CENTS", 0)
    assert billing.gross_for(500) == 500 and billing.fee_for(500) == 0


# --- the custom amount ---------------------------------------------------------------------------------

def test_custom_info_is_one_token_per_whole_dollar_inside_the_bounds():
    import billing
    assert (billing.CUSTOM_MIN_DOLLARS, billing.CUSTOM_MAX_DOLLARS,
            billing.CUSTOM_TOKENS_PER_DOLLAR) == (11, 500, 1)
    # the floor: ceil((1100 + 30) / 0.971) == 1164
    assert billing.custom_info(11) == {"id": "custom", "net_cents": 1100, "fee_cents": 64,
                                       "gross_cents": 1164, "tokens": 11}
    assert billing.custom_info(25) == {"id": "custom", "net_cents": 2500, "fee_cents": 106,
                                       "gross_cents": 2606, "tokens": 25}
    assert billing.custom_info(500)["tokens"] == 500 and billing.custom_info(500)["net_cents"] == 50000
    for info in (billing.custom_info(11), billing.custom_info(25), billing.custom_info(500)):
        assert info["net_cents"] + info["fee_cents"] == info["gross_cents"]


def test_custom_info_refuses_anything_but_a_whole_dollar_int_in_range():
    import billing
    for bad in (10, 0, -25, 501, 5000, 25.5, 25.0, "25", "", True, False, None, [25], {"dollars": 25}):
        assert billing.custom_info(bad) is None, bad


# --- the routes ----------------------------------------------------------------------------------------

def test_billing_probe_ships_the_tiers_even_when_disabled(client):
    login(client)
    b = client.get("/api/billing").get_json()
    assert b["enabled"] is False and b["currency"] == "usd"
    assert [t["id"] for t in b["tiers"]] == ["t3", "t5", "t10"]
    assert b["tiers"][1] == {"id": "t5", "net_cents": 500, "fee_cents": 46,
                            "gross_cents": 546, "tokens": 4}
    for t in b["tiers"]:
        assert t["net_cents"] + t["fee_cents"] == t["gross_cents"]
    # the retired knobs are gone from the API (tokens_per_dollar now lives INSIDE "custom", not at the top)
    assert "presets" not in b and "tokens_per_dollar" not in b and "bonus_tiers" not in b
    assert "packs" not in b
    assert client.post("/api/donate", json={"tier": "t5"}, headers=H).status_code == 503
    assert client.post("/api/donate", json={"custom_dollars": 25}, headers=H).status_code == 503
    assert client.post("/api/donate", json={"custom_dollars": 2}, headers=H).status_code == 503
    assert client.post("/api/checkout", json={"pack": "pack_5"}, headers=H).status_code == 404
    assert client.post("/webhook/stripe", data=b"{}").status_code == 503


def test_billing_probe_ships_the_custom_amount_rule(client):
    """The page previews the charge for a typed amount with the same formula gross_for uses, so the fee
    rates ship alongside the bounds. The server still recomputes everything at checkout."""
    import billing
    login(client)
    b = client.get("/api/billing").get_json()
    assert b["custom"] == {"min_dollars": 11, "max_dollars": 500, "tokens_per_dollar": 1,
                           "fee_pct": billing.STRIPE_FEE_PCT, "fee_fixed_cents": billing.STRIPE_FEE_FIXED_CENTS}
    assert (b["custom"]["fee_pct"], b["custom"]["fee_fixed_cents"]) == (2.9, 30)
    # the published rates reproduce the server's own arithmetic
    import math
    c = b["custom"]
    for dollars in (11, 25, 500):
        preview = math.ceil((dollars * 100 + c["fee_fixed_cents"]) / (1 - c["fee_pct"] / 100))
        assert preview == billing.custom_info(dollars)["gross_cents"]
    # the custom floor sits just above the top fixed tier
    assert c["min_dollars"] == max(net for net, _t in billing.DONATION_TIERS.values()) // 100 + 1


def test_donate_rejects_missing_unknown_and_legacy_bodies(client, stripe_stub):
    login(client, "picky@example.com")
    for body in ({}, {"tier": ""}, {"tier": "t7"}, {"tier": "pack_5"}, {"amount_cents": 500},
                 {"tier": "t20"}, {"tier": "t50"}):        # the retired tiers are unbuyable now
        r = client.post("/api/donate", json=body, headers=H)
        assert r.status_code == 400, body
        assert r.get_json()["error"] == "pick one of the donation amounts."
    assert stripe_stub.sessions == []          # nothing reached Stripe


def test_donate_rejects_custom_amounts_outside_the_rule(client, stripe_stub):
    login(client, "fussy@example.com")
    for body in ({"custom_dollars": 10}, {"custom_dollars": 501}, {"custom_dollars": 25.5},
                 {"custom_dollars": "25"}, {"custom_dollars": True}, {"custom_dollars": None},
                 {"custom_dollars": 0}, {"custom_dollars": -25}):
        r = client.post("/api/donate", json=body, headers=H)
        assert r.status_code == 400, body
        assert r.get_json()["error"] == "custom amounts are whole dollars from $11 to $500."
    # naming both a tier and an amount is a confused client, not a donation
    r = client.post("/api/donate", json={"tier": "t5", "custom_dollars": 25}, headers=H)
    assert r.status_code == 400
    assert r.get_json()["error"] == "send either a tier or a custom amount, not both."
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


def test_donate_creates_a_custom_amount_session(client, app_module, stripe_stub):
    """A custom gift is the same two-line-item session as a tier: the donation at the typed whole dollars,
    the card fee on top, and the token count (one per dollar) frozen in the metadata."""
    login(client, "custom@example.com")
    uid = _user_id(app_module, "custom@example.com")
    r = client.post("/api/donate", json={"custom_dollars": 25}, headers=H)
    assert r.status_code == 200 and r.get_json()["url"] == "https://stripe.test/c/cs_stub1"
    kw = stripe_stub.sessions[-1]
    assert kw["mode"] == "payment" and kw["submit_type"] == "donate"
    items = kw["line_items"]
    assert [i["price_data"]["product_data"]["name"] for i in items] == [
        "Donation — BLANK the spire", "Card processing fee"]
    assert [i["price_data"]["unit_amount"] for i in items] == [2500, 106]
    assert sum(i["price_data"]["unit_amount"] for i in items) == 2606   # == gross_for(2500)
    assert all(i["quantity"] == 1 and i["price_data"]["currency"] == "usd" for i in items)
    assert kw["metadata"] == {"user_id": str(uid), "tokens": "25", "price_id": "custom",
                              "net_cents": "2500"}
    assert kw["client_reference_id"] == str(uid) and kw["customer_email"] == "custom@example.com"
    # the bounds themselves go through
    assert client.post("/api/donate", json={"custom_dollars": 11}, headers=H).status_code == 200
    assert stripe_stub.sessions[-1]["metadata"]["tokens"] == "11"
    assert [i["price_data"]["unit_amount"] for i in stripe_stub.sessions[-1]["line_items"]] == [1100, 64]
    assert client.post("/api/donate", json={"custom_dollars": 500}, headers=H).status_code == 200
    assert stripe_stub.sessions[-1]["metadata"]["tokens"] == "500"


def test_custom_donation_credits_and_shows_as_a_donation(client, app_module):
    """A "custom" price_id is a donation in history, not a retired token pack — and the tokens come from
    the metadata, so the credit path never has to know the amount rule."""
    import billing
    login(client, "custompaid@example.com")
    uid = _user_id(app_module, "custompaid@example.com")
    assert billing._credit_purchase(
        _paid_session("cs_custom", uid, 25, 2606, pid="custom", net=2500)) == (True, 25)
    row = client.get("/api/purchases").get_json()["purchases"][0]
    assert row["kind"] == "donation" and row["tokens"] == 25
    assert (row["amount_cents"], row["net_cents"], row["fee_cents"]) == (2606, 2500, 106)


def test_retired_tier_rows_still_read_as_donations(client, app_module):
    """$20/$50 donations made before 2026-09-21 outlive their tier ids: history must not relabel them
    "pack" just because the buttons are gone."""
    import billing
    login(client, "retired@example.com")
    uid = _user_id(app_module, "retired@example.com")
    billing._credit_purchase(_paid_session("cs_t20_old", uid, 20, 2091, pid="t20", net=2000))
    billing._credit_purchase(_paid_session("cs_t50_old", uid, 50, 5181, pid="t50", net=5000))
    hist = client.get("/api/purchases").get_json()["purchases"]
    assert {p["tokens"] for p in hist} == {20, 50}
    assert all(p["kind"] == "donation" for p in hist)


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
