"""Stripe donations (pay-what-you-want Checkout) + donation history.

Pricing is DONATION-BASED (restored 2026-09-16; token packs ran 2026-09-08..16 and were retired): forging is
FREE with your own API key, and every account gets ONE free token per UTC day on the hosted models
(models.free_token_available — tracked separately from the balance, so a donor's thank-you tokens never
block it). Donations are optional support; as a thank-you, each whole dollar donated grants one bonus token
(TOKENS_PER_DOLLAR below — set to 0 to make donations pure).

Shape: the browser POSTs /api/donate with an amount → we create a Stripe Checkout Session and redirect the
user to Stripe's hosted page (no card data ever touches this server). Credit lands via TWO paths that share
one idempotent function: the /webhook/stripe endpoint (source of truth — fires even if the user never
returns) and GET /api/checkout-status (the success-redirect fallback, so the balance updates the moment the
user lands back on /app). purchases.stripe_session_id is UNIQUE, so double delivery can never double-credit.
The token count is frozen in the session's metadata at checkout, so changing TOKENS_PER_DOLLAR can't
mis-credit an in-flight donation.

Config (all env; billing silently disables without them — dev boots keyless, the UI hides the donate flow):
    STRIPE_SECRET_KEY        sk_test_... / sk_live_...
    STRIPE_WEBHOOK_SECRET    whsec_...  (the CLI's secret locally; the dashboard endpoint's secret in prod)
    BTSWEB_DONATION_PRESETS  "300,500,1000" — suggested amounts in CENTS shown by the UI (optional).

Refunds: `charge.refunded` marks the Purchase row "refunded" AND claws back that donation's still-unspent
thank-you tokens (min(tokens, current balance) — spent tokens are gone). Refunds are operator-initiated in
the Stripe dashboard; the 14-day window is policy (terms.html). Rows from the retired pack era keep their
price_id ("pack_N") and still show in history as purchases.
"""
from __future__ import annotations

import os

from flask import jsonify, request
from sqlalchemy.exc import IntegrityError

from auth import current_user, require_login
from db import session_scope
from models import Purchase, User

STRIPE_SECRET_KEY = os.environ.get("STRIPE_SECRET_KEY", "").strip()
STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET", "").strip()

TOKENS_PER_DOLLAR = 1        # thank-you tokens per whole dollar donated
MIN_DONATION_CENTS = 100     # Stripe's floor is $0.50; $1 keeps the fee overhead sane
MAX_DONATION_CENTS = 50000   # fat-finger guard


def _parse_presets(raw: str) -> list[int]:
    """"300,500,1000" → [300, 500, 1000] (cents). Malformed/out-of-range entries are skipped, not fatal."""
    presets: list[int] = []
    for part in (raw or "").split(","):
        try:
            n = int(part.strip())
        except ValueError:
            continue
        if MIN_DONATION_CENTS <= n <= MAX_DONATION_CENTS:
            presets.append(n)
    return presets


DEFAULT_PRESETS = [300, 500, 1000]
PRESETS = _parse_presets(os.environ.get("BTSWEB_DONATION_PRESETS", "")) or list(DEFAULT_PRESETS)


def tokens_for(amount_cents: int) -> int:
    """Thank-you tokens for a donation: one per WHOLE dollar (a $3.50 gift is 3 tokens)."""
    return (int(amount_cents) // 100) * TOKENS_PER_DOLLAR


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


def _credit_purchase(sess) -> tuple[bool, int]:
    """Record the donation and add its thank-you tokens in ONE transaction; idempotent via the UNIQUE session
    id. Token count comes from the session's metadata (frozen at checkout time), never recomputed — changing
    TOKENS_PER_DOLLAR can't mis-credit an in-flight donation. Returns (credited_now, token_balance)."""
    user_id = int(sess["metadata"]["user_id"])
    tokens = int(sess["metadata"]["tokens"])
    try:
        with session_scope() as s:
            s.add(Purchase(
                user_id=user_id,
                stripe_session_id=sess["id"],
                stripe_payment_intent=_sget(sess, "payment_intent"),
                price_id=_sget(_sget(sess, "metadata") or {}, "price_id", "donation"),
                tokens=tokens,
                amount_cents=int(_sget(sess, "amount_total", 0)),
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

    if billing_enabled():
        import stripe  # lazy: the dependency is only required once billing is actually configured
        stripe.api_key = STRIPE_SECRET_KEY
        if not os.environ.get("BTSWEB_PUBLIC_URL") and app.debug:
            app.logger.warning(
                "Stripe is configured but BTSWEB_PUBLIC_URL is unset — checkout success/cancel will "
                "redirect to %s, not this dev server.", public_base)
    else:
        stripe = None
        app.logger.info("billing disabled (set STRIPE_SECRET_KEY to enable donations)")

    @app.route("/api/billing")
    @require_login
    def api_billing():
        """Donation config for the UI. {enabled: false} hides the donate flow (keyless dev)."""
        return jsonify({
            "enabled": billing_enabled(),
            "presets": PRESETS,
            "min_cents": MIN_DONATION_CENTS,
            "max_cents": MAX_DONATION_CENTS,
            "tokens_per_dollar": TOKENS_PER_DOLLAR,
            "currency": "usd",
        })

    @app.route("/api/donate", methods=["POST"])
    @require_login
    def api_donate():
        """Create a pay-what-you-want Checkout Session and hand back its hosted-page URL."""
        if not billing_enabled():
            return jsonify({"error": "donations aren't available right now."}), 503
        user = current_user()
        try:
            amount_cents = int((request.get_json(silent=True) or {}).get("amount_cents", 0))
        except (TypeError, ValueError):
            amount_cents = 0
        if not (MIN_DONATION_CENTS <= amount_cents <= MAX_DONATION_CENTS):
            return jsonify({"error": f"donations can be ${MIN_DONATION_CENTS // 100} to "
                                     f"${MAX_DONATION_CENTS // 100}."}), 400
        tokens = tokens_for(amount_cents)
        try:
            sess = stripe.checkout.Session.create(
                mode="payment",
                submit_type="donate",  # Stripe's hosted button reads "Donate" instead of "Pay"
                line_items=[{
                    "price_data": {
                        "currency": "usd",
                        "unit_amount": amount_cents,
                        "product_data": {"name": "Donation — BLANK the spire"},
                    },
                    "quantity": 1,
                }],
                client_reference_id=str(user["id"]),
                metadata={"user_id": str(user["id"]), "tokens": str(tokens), "price_id": "donation"},
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
            event = stripe.Webhook.construct_event(
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
            sess = stripe.checkout.Session.retrieve(session_id)
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
