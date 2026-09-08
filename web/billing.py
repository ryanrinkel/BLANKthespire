"""Stripe token packs (Checkout hosted redirect) + purchase history.

Pricing (see docs/plans/DEPLOYMENT_PLAN.md §3): forging is FREE with your own API key; otherwise every account
gets ONE free token per UTC day (models.free_token_available — tracked separately from the paid balance, so
buyers never lose it), and paid tokens come in packs that never expire. Packs are defined HERE (PACKS below),
smallest first, and priced with ad-hoc `price_data` on the Checkout Session — no Stripe Price objects, so test
and live modes need no separate ids and re-pricing is a deploy, not a dashboard edit. There is deliberately no
single-token pack: Stripe's $0.30 + 2.9% would eat a third of a $1 sale.

Shape: the browser POSTs /api/checkout {pack} → we create a Stripe Checkout Session and redirect the user to
Stripe's hosted page (no card data ever touches this server). Credit lands via TWO paths that share one
idempotent function: the /webhook/stripe endpoint (source of truth — fires even if the user never returns)
and GET /api/checkout-status (the success-redirect fallback, so the balance updates the moment the user lands
back on /app). purchases.stripe_session_id is UNIQUE, so double delivery can never double-credit. The token
count is frozen in the session's metadata at checkout, so re-pricing can't mis-credit an in-flight purchase.

Config (all env; billing silently disables without them — dev boots keyless, the UI hides the buy flow):
    STRIPE_SECRET_KEY        sk_test_... / sk_live_...
    STRIPE_WEBHOOK_SECRET    whsec_...  (the CLI's secret locally; the dashboard endpoint's secret in prod)
    BTSWEB_TOKEN_PACKS       "5:500,11:1000,24:2000,65:5000" — tokens:cents, overrides PACKS (optional)
    BTSWEB_STRIPE_TAX        1 → enable Stripe Tax on the session (tokens are a digital good). Register in
                             the Stripe dashboard (Tax settings + origin address) BEFORE turning this on, or
                             session creation fails.
    BTSWEB_DONATIONS         1 → keep the legacy pay-what-you-want /api/donate route live (no thank-you tokens
                             any more). Off by default; dormant for one release as the rollback path.

Refunds: tokens are purchases, so `charge.refunded` marks the Purchase row "refunded" AND claws back the
purchase's still-unspent tokens (min(pack tokens, current balance) — spent tokens are gone). The 14-day
refund window for unspent tokens is policy (terms.html); refunds themselves are operator-initiated in the
Stripe dashboard.
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
STRIPE_TAX = os.environ.get("BTSWEB_STRIPE_TAX", "").strip() in ("1", "true", "yes")
DONATIONS_ENABLED = os.environ.get("BTSWEB_DONATIONS", "").strip() in ("1", "true", "yes")

# The buyable packs: (tokens, price in cents), smallest first. $1/token is the headline; bigger packs discount.
DEFAULT_PACKS: list[tuple[int, int]] = [
    (5, 500),      # $1.00 / token — the minimum checkout
    (11, 1000),    # $0.91 / token
    (24, 2000),    # $0.83 / token
    (65, 5000),    # $0.77 / token
]

# Legacy donation knobs (only live with BTSWEB_DONATIONS=1). Thank-you tokens are gone: tokens are now sold,
# and mixing gifts with sales muddies both the Workshop compliance framing and refund accounting.
TOKENS_PER_DOLLAR = 0
MIN_DONATION_CENTS = 100
MAX_DONATION_CENTS = 50000


def _parse_packs(raw: str) -> list[tuple[int, int]]:
    """"5:500,11:1000" → [(5, 500), (11, 1000)] sorted by tokens. Malformed entries are skipped, not fatal;
    an empty/invalid result falls back to DEFAULT_PACKS."""
    packs: list[tuple[int, int]] = []
    for part in (raw or "").split(","):
        part = part.strip()
        if not part or ":" not in part:
            continue
        t, _, c = part.partition(":")
        try:
            tokens, cents = int(t.strip()), int(c.strip())
        except ValueError:
            continue
        if tokens > 0 and cents >= 50:  # Stripe's floor is $0.50
            packs.append((tokens, cents))
    return sorted(packs) or list(DEFAULT_PACKS)


PACKS: list[tuple[int, int]] = _parse_packs(os.environ.get("BTSWEB_TOKEN_PACKS", ""))


def pack_id(tokens: int) -> str:
    return f"pack_{int(tokens)}"


def pack_catalog() -> list[dict]:
    """The packs as the UI and /api/checkout see them: {id, tokens, amount_cents, currency, per_token_cents}."""
    return [{"id": pack_id(t), "tokens": t, "amount_cents": c, "currency": "usd",
             "per_token_cents": round(c / t, 1)} for t, c in PACKS]


def find_pack(pid: str) -> dict | None:
    return next((p for p in pack_catalog() if p["id"] == pid), None)


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
    """Record the purchase and add its tokens in ONE transaction; idempotent via the UNIQUE session id. Token
    count comes from the session's metadata (frozen at checkout time), never recomputed from PACKS — re-pricing
    can't mis-credit an in-flight purchase. Returns (credited_now, token_balance)."""
    user_id = int(sess["metadata"]["user_id"])
    tokens = int(sess["metadata"]["tokens"])
    try:
        with session_scope() as s:
            s.add(Purchase(
                user_id=user_id,
                stripe_session_id=sess["id"],
                stripe_payment_intent=_sget(sess, "payment_intent"),
                price_id=_sget(_sget(sess, "metadata") or {}, "price_id", ""),
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
    """Mark the purchase refunded and claw back its unspent tokens: min(tokens, balance), never below zero.
    Idempotent — a second charge.refunded for the same intent finds the row already refunded and does nothing.
    Returns (tokens_clawed, new_balance) or None if no purchase matches."""
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
        app.logger.info("billing disabled (set STRIPE_SECRET_KEY to enable token packs)")

    @app.route("/api/billing")
    @require_login
    def api_billing():
        """Pricing config for the UI. {enabled: false} hides the buy flow (keyless dev) but still lists the
        packs so the pricing copy can render."""
        return jsonify({
            "enabled": billing_enabled(),
            "packs": pack_catalog(),
            "currency": "usd",
            "donations": DONATIONS_ENABLED and billing_enabled(),
        })

    def _checkout_session(user: dict, *, name: str, amount_cents: int, tokens: int, price_id: str,
                          donate: bool = False):
        kwargs = dict(
            mode="payment",
            line_items=[{
                "price_data": {
                    "currency": "usd",
                    "unit_amount": amount_cents,
                    "product_data": {"name": name},
                    **({"tax_behavior": "inclusive"} if STRIPE_TAX else {}),
                },
                "quantity": 1,
            }],
            client_reference_id=str(user["id"]),
            metadata={"user_id": str(user["id"]), "tokens": str(tokens), "price_id": price_id},
            customer_email=user.get("email") or None,
            success_url=f"{public_base}/app?purchase=success&session_id={{CHECKOUT_SESSION_ID}}",
            cancel_url=f"{public_base}/app?purchase=cancel",
        )
        if donate:
            kwargs["submit_type"] = "donate"
        if STRIPE_TAX:
            kwargs["automatic_tax"] = {"enabled": True}
        return stripe.checkout.Session.create(**kwargs)

    @app.route("/api/checkout", methods=["POST"])
    @require_login
    def api_checkout():
        """Create a Checkout Session for one token pack and hand back its hosted-page URL."""
        if not billing_enabled():
            return jsonify({"error": "token purchases aren't available right now."}), 503
        user = current_user()
        pid = str((request.get_json(silent=True) or {}).get("pack") or "").strip()
        pack = find_pack(pid)
        if pack is None:
            return jsonify({"error": "unknown token pack."}), 400
        try:
            sess = _checkout_session(
                user, name=f"{pack['tokens']} forge tokens — BLANK the spire",
                amount_cents=pack["amount_cents"], tokens=pack["tokens"], price_id=pack["id"])
        except Exception as e:
            app.logger.warning("stripe checkout create failed: %s", e)
            return jsonify({"error": "couldn't start checkout — try again in a minute."}), 502
        return jsonify({"url": sess.url})

    @app.route("/api/donate", methods=["POST"])
    @require_login
    def api_donate():
        """LEGACY pay-what-you-want donation (no tokens granted). Dormant unless BTSWEB_DONATIONS=1."""
        if not (billing_enabled() and DONATIONS_ENABLED):
            return jsonify({"error": "donations aren't available — tokens are sold in packs now."}), 404
        user = current_user()
        try:
            amount_cents = int((request.get_json(silent=True) or {}).get("amount_cents", 0))
        except (TypeError, ValueError):
            amount_cents = 0
        if not (MIN_DONATION_CENTS <= amount_cents <= MAX_DONATION_CENTS):
            return jsonify({"error": f"donations can be ${MIN_DONATION_CENTS // 100} to "
                                     f"${MAX_DONATION_CENTS // 100}."}), 400
        tokens = (amount_cents // 100) * TOKENS_PER_DOLLAR
        try:
            sess = _checkout_session(user, name="Donation — BLANK the spire", amount_cents=amount_cents,
                                     tokens=tokens, price_id="donation", donate=True)
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
            return jsonify({"error": "token purchases aren't available right now."}), 503
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
                logger.info("stripe refund: intent %s — clawed back %s unspent tokens, balance now %s",
                            pi, res[0], res[1])
