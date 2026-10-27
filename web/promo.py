"""Sign-up events: a time-boxed window in which every NEW account starts with N free hosted-forge tokens.

This is a deliberate, temporary exception to pricing v3, under which an account starts with NOTHING
(models.INITIAL_TOKENS = 0) and the only ways to forge are your own API key or a donation thank-you. An event
is run by the operator for a fixed window with a hard cap on how many accounts it pays for, so its worst-case
cost is known up front: max_grants x tokens_per_signup hosted forges. See docs/plans/SIGNUP_EVENTS_PLAN.md.

Rules (kept in this module so auth stays readable):
  * Only a brand-new account qualifies (auth._resolve_identity rule 4). A repeat sign-in, or a second sign-in
    method that links to an existing account (rules 1-3), is not a signup and gets nothing.
  * At most one event is active at a time: create/edit refuse overlapping windows (see overlapping()).
  * Once `max_grants` accounts have been granted, later signups still get an account, just no tokens.

Datetimes are naive UTC, the convention every DateTime column here follows (auth._utc_naive).
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import func

from models import Promotion, PromoGrant

log = logging.getLogger(__name__)

TOKENS_PER_SIGNUP_MAX = 10     # sanity ceiling: a typo must not hand every signup a fortune
MAX_GRANTS_MAX = 10_000        # same, for the cap
LABEL_MAX = 120


def _now() -> datetime:
    """Naive UTC now. A function so tests can move the clock."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def iso_utc(dt: datetime | None) -> str | None:
    """A naive-UTC column value as an explicit-offset ISO string, so a browser countdown cannot mistake it
    for local time."""
    return dt.replace(tzinfo=timezone.utc).isoformat() if dt is not None else None


def grant_count(s, promo_id: int) -> int:
    return int(s.query(func.count(PromoGrant.id)).filter(PromoGrant.promo_id == promo_id).scalar() or 0)


def status_of(promo: Promotion, granted: int, now: datetime | None = None) -> str:
    """scheduled | live | capped | ended. "ended" wins over everything (End now, or the window ran out);
    "capped" means inside the window but the grant budget is spent."""
    now = now or _now()
    if promo.ended_at is not None or now >= promo.ends_at:
        return "ended"
    if now < promo.starts_at:
        return "scheduled"
    if granted >= promo.max_grants:
        return "capped"
    return "live"


def active_promotion(s, now: datetime | None = None) -> Promotion | None:
    """The event currently paying out, or None: inside its window, not ended early, and under its cap.
    Overlap is refused at create/edit time, so there is at most one; the newest wins if that ever slips."""
    now = now or _now()
    rows = (s.query(Promotion)
            .filter(Promotion.starts_at <= now, Promotion.ends_at > now, Promotion.ended_at.is_(None))
            .order_by(Promotion.id.desc()).all())
    for p in rows:
        if grant_count(s, p.id) < p.max_grants:
            return p
    return None


def grant_signup_bonus(s, user, now: datetime | None = None) -> PromoGrant | None:
    """Give a JUST-CREATED account the active event's tokens, inside the caller's session + transaction.

    Must never break sign-in: everything runs in a SAVEPOINT, so a failure rolls back exactly the grant (no
    half-written row, no balance bump without its PromoGrant) and the account is still created, just without
    the bonus. The cap check (count, then insert) is race-free on SQLite because every transaction takes the
    write lock at BEGIN (db._sqlite_begin: BEGIN IMMEDIATE), so two signups cannot both read "one slot left".
    On MySQL two concurrent signups could overshoot the cap by one; prod is SQLite, so that is accepted."""
    now = now or _now()
    try:
        with s.begin_nested():
            promo = active_promotion(s, now)
            if promo is None:
                return None
            tokens = int(promo.tokens_per_signup)
            # Whole seconds: ForgeJob.started_at / Purchase.created_at come from CURRENT_TIMESTAMP (second
            # resolution), and the "forged / donated after the grant" stats compare against this.
            grant = PromoGrant(promo_id=promo.id, user_id=user.id, tokens=tokens,
                               created_at=now.replace(microsecond=0))
            s.add(grant)
            user.token_balance = int(user.token_balance or 0) + tokens
            s.flush()
        log.info("sign-up event #%s granted %s token(s) to new user %s", promo.id, tokens, user.id)
        return grant
    except Exception:  # never let a promo bug cost someone their sign-in
        log.exception("sign-up event grant failed for new user %s; continuing without a bonus", user.id)
        return None


# --- admin input -----------------------------------------------------------------------------------------

class PromoInputError(ValueError):
    """A 400 with a human-readable message."""


def parse_when(raw, field: str) -> datetime:
    """ISO 8601 WITH an offset ("2026-11-01T18:00:00+00:00", "...Z") -> naive UTC. A naive string is
    refused: "18:00" in whose timezone is exactly the ambiguity that starts an event an hour early."""
    if not isinstance(raw, str) or not raw.strip():
        raise PromoInputError(f"{field} is required (ISO 8601 with an offset, e.g. 2026-11-01T18:00:00Z)")
    text = raw.strip()
    if text.endswith(("Z", "z")):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        raise PromoInputError(f"{field} is not a valid ISO 8601 date-time") from None
    if dt.tzinfo is None:
        raise PromoInputError(f"{field} must include a timezone offset (e.g. Z or -05:00)")
    return dt.astimezone(timezone.utc).replace(tzinfo=None)


def _int_field(body: dict, field: str, lo: int, hi: int, default=None) -> int:
    raw = body.get(field, default)
    if raw is None:
        raise PromoInputError(f"{field} is required")
    if isinstance(raw, bool) or not isinstance(raw, (int, str)):
        raise PromoInputError(f"{field} must be a whole number")
    try:
        n = int(str(raw).strip())
    except ValueError:
        raise PromoInputError(f"{field} must be a whole number") from None
    if not lo <= n <= hi:
        raise PromoInputError(f"{field} must be between {lo} and {hi}")
    return n


def parse_promo_body(body, now: datetime | None = None) -> dict:
    """Validate a create/edit body -> {label, tokens_per_signup, starts_at, ends_at, max_grants}.
    Raises PromoInputError. Every field is required except tokens_per_signup (default 1)."""
    if not isinstance(body, dict):
        raise PromoInputError("send a JSON object")
    now = now or _now()
    label = body.get("label")
    label = label.strip() if isinstance(label, str) else ""
    if not label:
        raise PromoInputError("label is required")
    if len(label) > LABEL_MAX:
        raise PromoInputError(f"label must be at most {LABEL_MAX} characters")
    out = {
        "label": label,
        "tokens_per_signup": _int_field(body, "tokens_per_signup", 1, TOKENS_PER_SIGNUP_MAX, default=1),
        "max_grants": _int_field(body, "max_grants", 0, MAX_GRANTS_MAX),
        "starts_at": parse_when(body.get("starts_at"), "starts_at"),
        "ends_at": parse_when(body.get("ends_at"), "ends_at"),
    }
    if out["ends_at"] <= out["starts_at"]:
        raise PromoInputError("ends_at must be after starts_at")
    if out["ends_at"] <= now:
        raise PromoInputError("ends_at is already in the past")
    return out


def overlapping(s, starts_at: datetime, ends_at: datetime, *, exclude_id: int | None = None,
                now: datetime | None = None) -> Promotion | None:
    """Another not-yet-ended event whose window overlaps [starts_at, ends_at), or None. Ended events (End
    now, or a window that already ran out) never block."""
    now = now or _now()
    q = s.query(Promotion).filter(Promotion.ended_at.is_(None), Promotion.ends_at > now,
                                  Promotion.starts_at < ends_at, Promotion.ends_at > starts_at)
    if exclude_id is not None:
        q = q.filter(Promotion.id != exclude_id)
    return q.order_by(Promotion.id).first()
