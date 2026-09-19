"""Stripe donations (fixed tiers, card fee passed through) + donation history.

Pricing is DONATION-BASED and, since v3 (2026-09-18), has no free tier at all on our models: forging is FREE
and UNLIMITED with your own API key, and the hosted path spends tokens received as a thank-you for a
donation. Nothing is sold and there are no custom amounts — DONATION_TIERS below is the whole price list,
id -> (net cents the project receives, thank-you tokens), in display order.

The donor is charged the GROSS, not the net: Stripe keeps 2.9% + 30c of every charge, so a $5 donation would
otherwise arrive as $4.56. gross_for() solves for the smallest charge that still nets the tier amount, and
the Checkout Session carries TWO line items — the donation at net and "Card processing fee" at the
difference — so Stripe's own page and receipt show the split instead of one mystery number. The rates live
in env so a Stripe price change is a config edit, not a deploy of this file.

Shape: the browser POSTs /api/donate with a tier id → we create a Stripe Checkout Session and redirect the
user to Stripe's hosted page (no card data ever touches this server). Credit lands via TWO paths that share
one idempotent function: the /webhook/stripe endpoint (source of truth — fires even if the user never
returns) and GET /api/checkout-status (the success-redirect fallback, so the balance updates the moment the
user lands back on /app). purchases.stripe_session_id is UNIQUE, so double delivery can never double-credit.
The token count is frozen in the session's metadata at checkout, so editing DONATION_TIERS can't mis-credit
an in-flight donation.

Config (all env; billing silently disables without the key — dev boots keyless, the UI hides the donate flow):
    STRIPE_SECRET_KEY        sk_test_... / sk_live_...
    STRIPE_WEBHOOK_SECRET    whsec_...  (the CLI's secret locally; the dashboard endpoint's secret in prod)
    STRIPE_FEE_PCT           percentage Stripe keeps, default "2.9" (their US card rate)
    STRIPE_FEE_FIXED_CENTS   per-charge fixed fee, default "30"

Refunds: `charge.refunded` marks the Purchase row "refunded" AND claws back that donation's still-unspent
thank-you tokens (min(tokens, current balance) — spent tokens are gone). The refund is of the GROSS, fee
included (terms.html says so); Purchase.amount_cents is that gross. Refunds are operator-initiated in the
Stripe dashboard; the 14-day window is policy. Rows from the pay-what-you-want era (price_id "donation") and
the retired pack era ("pack_N") keep their price_id, carry no net_cents, and still show in history.
"""
from __future__ import annotations

import math
import os

from flask import jsonify, request
from sqlalchemy.exc import IntegrityError

from auth import current_user, require_login
from db import session_scope
from models import Purchase, User

STRIPE_SECRET_KEY = os.environ.get("STRIPE_SECRET_KEY", "").strip()
STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET", "").strip()

# The stripe-python module, bound by init_billing once a key is configured (None when billing is off). It is
# a module global rather than an init_billing local so the routes resolve it at call time — which is also
# what lets the test suite stand a stub in its place without a live key.
_stripe = None

# The ENTIRE price list: tier id -> (net cents the project receives, thank-you tokens). Dict order is
# display order in the UI. No custom amounts — a free-text box invites $0.50 gifts that Stripe's fixed 30c
# eats, and fixed buttons are what the donate UI and /api/donate both speak. Up to $10 the tokens are priced
# above cost (memory: ~$0.93 metered per hosted forge); $10 and above is one token per dollar, break-even.
DONATION_TIERS: dict[str, tuple[int, int]] = {
    "t3": (300, 2),
    "t5": (500, 4),
    "t10": (1000, 10),
    "t20": (2000, 20),
    "t50": (5000, 50),
}

# Stripe's cut, in env so a rate change is a config edit. Defaults are their US card rate (2.9% + 30c);
# international cards and currency conversion cost more and we eat that difference by design.
STRIPE_FEE_PCT = float(os.environ.get("STRIPE_FEE_PCT", "2.9"))
STRIPE_FEE_FIXED_CENTS = int(os.environ.get("STRIPE_FEE_FIXED_CENTS", "30"))


def gross_for(net_cents: int) -> int:
    """The smallest whole-cent charge that still nets `net_cents` after Stripe's cut: solve
    gross - (gross * pct + fixed) = net, then round UP so rounding never eats into the donation. With the
    default rates: 300 -> 340, 500 -> 546, 1000 -> 1061, 2000 -> 2091, 5000 -> 5181."""
    return math.ceil((int(net_cents) + STRIPE_FEE_FIXED_CENTS) / (1 - STRIPE_FEE_PCT / 100))


def fee_for(net_cents: int) -> int:
    """The pass-through "Card processing fee" line item: what the donor pays on top of the tier amount."""
    return gross_for(net_cents) - int(net_cents)


def tier_info(tier_id: str) -> dict | None:
    """One tier as the UI and /api/donate need it, or None for an unknown id (the 400 path)."""
    row = DONATION_TIERS.get(tier_id)
    if row is None:
        return None
    net, tokens = row
    return {"id": tier_id, "net_cents": net, "fee_cents": fee_for(net), "gross_cents": gross_for(net),
            "tokens": tokens}


def billing_enabled() -> bool:
    return bool(STRIPE_SECRET_KEY)


def _sget(obj, key, default=None):
    """dict.get for Stripe payloads. stripe-python v15 objects are indexable but are NOT dicts (no .get —
    attribute access on a missing key raises), while webhook payloads we build in tests ARE plain dicts.
    This reads a key from either shape, returning `default` for missing keys or explicit nulls."""
    try:
        val = obj[key]
    except (KeyError, TypeError, IndexError):
        return default
    return default if val is None else val


def _net_cents_of(meta) -> int | None:
    """The donation half of a v3 checkout, from the session metadata. None for anything that predates the
    two-line-item session (pack era, pay-what-you-want donations) or carries junk — history then simply
    shows no fee split rather than inventing one."""
    raw = _sget(meta or {}, "net_cents")
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def _credit_purchase(sess) -> tuple[bool, int]:
    """Record the donation and add its thank-you tokens in ONE transaction; idempotent via the UNIQUE session
    id. Token count comes from the session's metadata (frozen at checkout time), never recomputed — editing
    DONATION_TIERS can't mis-credit an in-flight donation. amount_cents is the GROSS Stripe actually charged
    (donation + card fee); net_cents is the donation line alone. Returns (credited_now, token_balance)."""
    user_id = int(sess["metadata"]["user_id"])
    tokens = int(sess["metadata"]["tokens"])
    meta = _sget(sess, "metadata") or {}
    try:
        with session_scope() as s:
            s.add(Purchase(
                user_id=user_id,
                stripe_session_id=sess["id"],
                stripe_payment_intent=_sget(sess, "payment_intent"),
                price_id=_sget(meta, "price_id", "donation"),
                tokens=tokens,
                amount_cents=int(_sget(sess, "amount_total", 0)),
                net_cents=_net_cents_of(meta),
                currency=_sget(sess, "currency", "usd"),
                status="paid",
            ))
            s.flush()  # a duplicate session id raises HERE — before the balance moves
            u = s.query(User).filter_by(id=user_id).one()
            u.token_balance += tokens
            return True, int(u.token_balance)
    except IntegrityError:
        # Already credited by the other delivery path — just report the current balance.
        with session_scope() as s:
            u = s.query(User).filter_by(id=user_id).one_or_none()
            return False, int(u.token_balance) if u is not None else 0


def _refund_purchase(payment_intent: str) -> tuple[int, int] | None:
    """Mark the donation refunded and claw back its unspent thank-you tokens: min(tokens, balance), never
    below zero. Idempotent — a second charge.refunded for the same intent finds the row already refunded and
    does nothing. Returns (tokens_clawed, new_balance) or None if no row matches."""
    with session_scope() as s:
        row = s.query(Purchase).filter_by(stripe_payment_intent=payment_intent).one_or_none()
        if row is None:
            return None
        if row.status == "refunded":
            u = s.query(User).filter_by(id=row.user_id).one_or_none()
            return 0, int(u.token_balance) if u is not None else 0
        row.status = "refunded"
        u = s.query(User).filter_by(id=row.user_id).one_or_none()
        if u is None:
            return 0, 0
        clawed = max(0, min(int(row.tokens), int(u.token_balance)))
        u.token_balance -= clawed
        return clawed, int(u.token_balance)


def init_billing(app) -> None:
    """Register billing routes. With no Stripe config, only the (disabled) /api/billing probe is live — the app
    boots and forges exactly as before."""
    public_base = os.environ.get("BTSWEB_PUBLIC_URL", "https://blankthespire.com").rstrip("/")

    global _stripe
    if billing_enabled():
        import stripe  # lazy: the dependency is only required once billing is actually configured
        stripe.api_key = STRIPE_SECRET_KEY
        _stripe = stripe
        if not os.environ.get("BTSWEB_PUBLIC_URL") and app.debug:
            app.logger.warning(
                "Stripe is configured but BTSWEB_PUBLIC_URL is unset — checkout success/cancel will "
                "redirect to %s, not this dev server.", public_base)
    else:
        _stripe = None
        app.logger.info("billing disabled (set STRIPE_SECRET_KEY to enable donations)")

    @app.route("/api/billing")
    @require_login
    def api_billing():
        """Donation config for the UI: the tier buttons, in display order, each with its gross/fee split so
        the page never does the fee arithmetic itself. The tiers ship even when {enabled: false} (keyless
        dev) so the UI can still describe them; only the donate flow is hidden."""
        return jsonify({
            "enabled": billing_enabled(),
            "currency": "usd",
            "tiers": [tier_info(tid) for tid in DONATION_TIERS],
        })

    @app.route("/api/donate", methods=["POST"])
    @require_login
    def api_donate():
        """Create a fixed-tier Checkout Session and hand back its hosted-page URL. The body is {"tier": "t5"}
        and nothing else — a legacy amount_cents body names no tier and so lands on the 400 below, which is
        what we want: a stale tab must not be able to name its own price."""
        if not billing_enabled():
            return jsonify({"error": "donations aren't available right now."}), 503
        user = current_user()
        tier_id = str((request.get_json(silent=True) or {}).get("tier", "") or "").strip()
        tier = tier_info(tier_id)
        if tier is None:
            return jsonify({"error": "pick one of the donation amounts."}), 400
        net, fee, tokens = tier["net_cents"], tier["fee_cents"], tier["tokens"]
        try:
            sess = _stripe.checkout.Session.create(
                mode="payment",
                submit_type="donate",  # Stripe's hosted button reads "Donate" instead of "Pay"
                # Two line items so Stripe's own page and receipt show the split instead of one number the
                # donor has to reverse-engineer. They sum to gross_for(net).
                line_items=[{
                    "price_data": {
                        "currency": "usd",
                        "unit_amount": net,
                        "product_data": {"name": "Donation — BLANK the spire"},
                    },
                    "quantity": 1,
                }, {
                    "price_data": {
                        "currency": "usd",
                        "unit_amount": fee,
                        "product_data": {"name": "Card processing fee"},
                    },
                    "quantity": 1,
                }],
                client_reference_id=str(user["id"]),
                metadata={"user_id": str(user["id"]), "tokens": str(tokens), "price_id": tier_id,
                          "net_cents": str(net)},
                customer_email=user.get("email") or None,
                success_url=f"{public_base}/app?purchase=success&session_id={{CHECKOUT_SESSION_ID}}",
                cancel_url=f"{public_base}/app?purchase=cancel",
            )
        except Exception as e:
            app.logger.warning("stripe donation checkout create failed: %s", e)
            return jsonify({"error": "couldn't start checkout — try again in a minute."}), 502
        return jsonify({"url": sess.url})

    @app.route("/webhook/stripe", methods=["POST"])
    def stripe_webhook():
        """Stripe → us. NO login (Stripe isn't a browser session); the signature check IS the auth."""
        if not billing_enabled():
            return jsonify({"error": "billing disabled"}), 503
        try:
            event = _stripe.Webhook.construct_event(
                request.get_data(), request.headers.get("Stripe-Signature", ""), STRIPE_WEBHOOK_SECRET)
        except Exception:
            return jsonify({"error": "bad signature"}), 400
        handle_stripe_event(event, app.logger)
        return jsonify({"received": True})

    @app.route("/api/checkout-status")
    @require_login
    def api_checkout_status():
        """Success-redirect fallback: verify the session with Stripe and credit it NOW if the webhook hasn't
        already — so the user's balance is right the moment they land back on /app."""
        if not billing_enabled():
            return jsonify({"error": "donations aren't available right now."}), 503
        user = current_user()
        session_id = (request.args.get("session_id") or "").strip()
        if not session_id:
            return jsonify({"error": "session_id is required"}), 400
        try:
            sess = _stripe.checkout.Session.retrieve(session_id)
        except Exception:
            return jsonify({"error": "unknown checkout session"}), 404
        if _sget(sess, "client_reference_id") != str(user["id"]):
            return jsonify({"error": "not your checkout session"}), 403
        credited = False
        balance = None
        if _sget(sess, "payment_status") == "paid":
            credited, balance = _credit_purchase(sess)
        return jsonify({
            "status": _sget(sess, "payment_status"),
            "credited": credited,
            "tokens": int(_sget(_sget(sess, "metadata") or {}, "tokens", 0)),
            "token_balance": balance,
        })

    @app.route("/api/purchases")
    @require_login
    def api_purchases():
        user = current_user()
        with session_scope() as s:
            rows = (s.query(Purchase)
                    .filter_by(user_id=user["id"])
                    .order_by(Purchase.created_at.desc(), Purchase.id.desc())
                    .all())
            return jsonify({"purchases": [p.summary() for p in rows]})


def handle_stripe_event(event, logger) -> None:
    """The webhook's business logic, split out so tests can drive it with plain-dict events and no signature.
    Unknown event types are ignored."""
    etype = _sget(event, "type", "")
    obj = _sget(_sget(event, "data") or {}, "object") or {}
    if etype in ("checkout.session.completed", "checkout.session.async_payment_succeeded"):
        if _sget(obj, "payment_status") == "paid" and _sget(_sget(obj, "metadata") or {}, "user_id"):
            credited, bal = _credit_purchase(obj)
            logger.info("stripe webhook %s: session %s credited=%s balance=%s",
                        etype, _sget(obj, "id"), credited, bal)
    elif etype == "charge.refunded":
        pi = _sget(obj, "payment_intent")
        if pi:
            res = _refund_purchase(pi)
            if res is not None:
                logger.info("stripe refund: intent %s — clawed back %s unspent thank-you tokens, balance now %s",
                            pi, res[0], res[1])
