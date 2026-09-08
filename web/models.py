"""ORM models for the P3 site: users, their forged classes, and denormalized per-card rows.

BYOK API keys appear in NO table by design — only generated *content* (classes, cards, codes) is persisted.
JSON blobs are stored as TEXT (portable across SQLite-for-dev and MySQL-for-prod).
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


# Free tokens every account starts with (new sign-ins, and backfilled to existing rows on migration). One
# token = one hosted "Use a token" forge (the Ollama gemma/glm mix on our server key). Beyond the starter
# grant, pricing is: one FREE token per UTC day for everyone (tracked separately from the paid balance, see
# free_token_available / spend_token below), and paid token packs (billing.PACKS) that never expire.
INITIAL_TOKENS = 5


def _utc_today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def free_token_available(user: "User", today: str | None = None) -> bool:
    """True if this account has not yet spent its free daily token today (UTC). The free token lives
    OUTSIDE token_balance: it is a once-per-day right, not a balance credit, so holding paid tokens never
    forfeits it (the old "top up only when empty" rule punished buyers). last_free_token_day is the UTC day it
    was last SPENT (NULL = never)."""
    return user.last_free_token_day != (today or _utc_today())


def spend_token(user: "User", today: str | None = None) -> str | None:
    """Spend ONE token for a hosted forge, free-first: if today's free token is unspent, stamp the day and
    return "free"; else decrement the paid balance and return "paid"; else return None (nothing to spend —
    caller 402s). Call with a session-attached User inside a transaction so the read+write are atomic."""
    today = today or _utc_today()
    if free_token_available(user, today):
        user.last_free_token_day = today
        return "free"
    if user.token_balance > 0:
        user.token_balance -= 1
        return "paid"
    return None


def unspend_token(user: "User", kind: str, day: str | None = None) -> None:
    """Give back a token reserved by spend_token (the forge failed). "paid" -> +1 balance. "free" -> clear the
    day stamp, but only if it still names the day that was stamped (a rollover mid-forge means today's free
    token is untouched already, and clearing a fresh stamp would hand out two)."""
    if kind == "paid":
        user.token_balance += 1
    elif kind == "free":
        if user.last_free_token_day == (day or _utc_today()):
            user.last_free_token_day = None


def grant_daily_token(user: "User") -> bool:
    """RETIRED (kept for import compatibility): the free daily token is no longer a balance top-up. It is
    tracked as a once-per-day spend right (free_token_available) so paid balances never block it."""
    return False


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    google_sub: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    email: Mapped[str] = mapped_column(String(320), default="")
    name: Mapped[str] = mapped_column(String(255), default="")
    # Spendable balance for the hosted token path. server_default seeds DB-created rows; the boot migration
    # (db._ensure_user_columns) adds + backfills this column on databases that predate it.
    token_balance: Mapped[int] = mapped_column(
        Integer, default=INITIAL_TOKENS, server_default=str(INITIAL_TOKENS), nullable=False)
    # The UTC date ("YYYY-MM-DD") this account last SPENT its free daily token (see spend_token). NULL = never.
    # Patched into pre-existing DBs by db._ensure_user_columns. (Under the retired donation model this was the
    # day the free token was GRANTED into the balance - same meaning, "today's free token is used up", so no
    # data migration is needed.)
    last_free_token_day: Mapped[str | None] = mapped_column(String(10), default=None, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    classes: Mapped[list["ForgedClass"]] = relationship(
        back_populates="user", cascade="all, delete-orphan")


class ForgedClass(Base):
    __tablename__ = "classes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(255), default="")
    concept: Mapped[str] = mapped_column(Text, default="")
    vocab_version: Mapped[int] = mapped_column(Integer, default=2)
    bundle_json: Mapped[str] = mapped_column(Text)   # the full {kind, character, cards[], relic?, splash_url?}
    code: Mapped[str] = mapped_column(Text)           # the BTSC import code (carries splash_url once generated)
    # Cache-bust / existence markers for the generated art on disk (web/static/forged/<id>/splash.png and
    # sprite.png — the standing combat model). NULL = not generated. Added after the original schema →
    # patched in by db._ensure_class_columns on existing DBs.
    splash_hash: Mapped[str | None] = mapped_column(String(64), default=None, nullable=True)
    sprite_hash: Mapped[str | None] = mapped_column(String(64), default=None, nullable=True)
    # Unguessable public handle for /api/deck/<slug> sharing (the numeric id is enumerable and stays
    # internal). 22 url-safe chars = 128 bits. Backfilled onto existing rows by db._ensure_class_columns.
    slug: Mapped[str | None] = mapped_column(String(32), default=None, nullable=True, unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now())

    user: Mapped[User] = relationship(back_populates="classes")
    cards: Mapped[list["ForgedCard"]] = relationship(
        back_populates="cls", cascade="all, delete-orphan", order_by="ForgedCard.ordinal")

    def summary(self) -> dict:
        """List-view shape (no heavy bundle)."""
        return {
            "id": self.id,
            "name": self.name,
            "concept": self.concept,
            "card_count": len(self.cards),
            "vocab_version": self.vocab_version,
            "slug": self.slug,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    def detail(self) -> dict:
        """Full shape: identity + cards + code, for the result view / re-open."""
        import json
        bundle = json.loads(self.bundle_json)
        d = {
            **self.summary(),
            "character": bundle.get("character"),
            "cards": bundle.get("cards", []),
            "relic": bundle.get("relic"),
            "archetypes": bundle.get("archetypes") or [],  # [] for classes forged before this was stored
            "code": self.code,
            "splash_hash": self.splash_hash,  # app layer turns these into absolute *_url fields
            "sprite_hash": self.sprite_hash,
        }
        # The emoji relic icon has no hash column; its URL lives in the bundle (stamped post-forge).
        if bundle.get("relic_icon_url"):
            d["relic_icon_url"] = bundle["relic_icon_url"]
        return d


class ForgedCard(Base):
    """Denormalized per-card rows — cheap now, enables future gallery/search without reparsing bundles."""
    __tablename__ = "cards"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    class_id: Mapped[int] = mapped_column(ForeignKey("classes.id", ondelete="CASCADE"), index=True)
    card_json: Mapped[str] = mapped_column(Text)
    ordinal: Mapped[int] = mapped_column(Integer, default=0)

    cls: Mapped[ForgedClass] = relationship(back_populates="cards")


def new_slug() -> str:
    """A fresh 22-char url-safe random slug (128 bits) for ForgedClass.slug."""
    import secrets
    return secrets.token_urlsafe(16)


class Purchase(Base):
    """One completed Stripe Checkout payment — a token pack (price_id = the pack id, e.g. "pack_11"), or a
    legacy pay-what-you-want donation (price_id="donation"). The UNIQUE stripe_session_id is the
    idempotency guard: the webhook and the synchronous /api/checkout-status fallback both funnel through
    billing._credit_purchase, and a second delivery of the same session hits the constraint and credits
    nothing. Doubles as the user-facing purchase history (a brand-new table — created by create_all on
    boot, no _ensure_* migration needed)."""
    __tablename__ = "purchases"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    # 191 keeps the unique index inside MySQL/utf8mb4 key limits; Stripe session ids are ~66 chars.
    stripe_session_id: Mapped[str] = mapped_column(String(191), unique=True, index=True)
    stripe_payment_intent: Mapped[str | None] = mapped_column(String(255), default=None, nullable=True)
    price_id: Mapped[str] = mapped_column(String(255), default="")
    tokens: Mapped[int] = mapped_column(Integer)               # tokens granted by this purchase
    amount_cents: Mapped[int] = mapped_column(Integer, default=0)
    currency: Mapped[str] = mapped_column(String(8), default="usd")
    status: Mapped[str] = mapped_column(String(32), default="paid")  # "paid" | "refunded"
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    def summary(self) -> dict:
        """History-list shape for /api/purchases."""
        return {
            "id": self.id,
            "kind": "donation" if self.price_id == "donation" else "pack",
            "tokens": self.tokens,
            "amount_cents": self.amount_cents,
            "currency": self.currency,
            "status": self.status,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class ForgeUsage(Base):
    """One row per (forge, role, model): the LLM tokens a forge consumed, fed from btsgen's on_usage callback.
    This is what turns "margin holds" into a fact — cost per hosted forge vs the price of a token. Rows for
    BYOK forges carry no cost (the user's provider bills them) but still record volume. Brand-new table:
    created by create_all on boot, no _ensure_* migration needed."""
    __tablename__ = "forge_usage"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True,
                                                nullable=True)
    class_id: Mapped[int | None] = mapped_column(Integer, default=None, nullable=True)  # None if the forge failed
    forge_id: Mapped[str] = mapped_column(String(32), index=True)  # groups the rows of one forge
    mode: Mapped[str] = mapped_column(String(16), default="token")  # token | byok | anthropic | fake
    token_kind: Mapped[str | None] = mapped_column(String(10), default=None, nullable=True)  # free|paid|unlimited
    role: Mapped[str] = mapped_column(String(32), default="")   # brainstorm | structure | cards | ...
    model: Mapped[str] = mapped_column(String(128), default="")
    calls: Mapped[int] = mapped_column(Integer, default=0)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cached_tokens: Mapped[int] = mapped_column(Integer, default=0)
    # Micro-dollars (1e-6 USD) so the column stays an integer; NULL = not ours to pay (BYOK) or unknown model.
    est_cost_micros: Mapped[int | None] = mapped_column(Integer, default=None, nullable=True)
    ok: Mapped[int] = mapped_column(Integer, default=1)  # 1 = the forge succeeded
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class ForgeJob(Base):
    """One row per forge attempt, written when the token is reserved and settled exactly once when the forge
    finishes — by the worker thread, NOT the SSE stream, so a browser that disconnects mid-forge still gets its
    class saved (or its token refunded). Rows still "running" at boot are casualties of a restart and are
    refunded by app._reconcile_forge_jobs. Brand-new table: created by create_all, no migration needed."""
    __tablename__ = "forge_jobs"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)  # the forge id (uuid hex)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    mode: Mapped[str] = mapped_column(String(16), default="token")
    token_kind: Mapped[str | None] = mapped_column(String(10), default=None, nullable=True)  # free|paid|unlimited
    token_day: Mapped[str | None] = mapped_column(String(10), default=None, nullable=True)   # UTC day reserved
    concept: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(16), default="running", index=True)  # running|done|failed
    refunded: Mapped[int] = mapped_column(Integer, default=0)
    class_id: Mapped[int | None] = mapped_column(Integer, default=None, nullable=True)
    error: Mapped[str] = mapped_column(String(500), default="")
    started_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, default=None, nullable=True)
