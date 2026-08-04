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
# token = one hosted "Use a token" forge (the Ollama ministral/glm mix on our server key). After the
# starter tokens, pricing is donation-based: grant_daily_token below refills an empty balance once per day.
INITIAL_TOKENS = 5


def _utc_today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def grant_daily_token(user: "User") -> bool:
    """Donation-based pricing: every account gets 1 free token per UTC day, granted LAZILY (no cron) the
    first time an empty balance is observed that day — /api/me on page load, and _reserve_token right
    before a forge. Only tops up when the balance is 0, so tokens never accumulate beyond what you hold.
    Call with a session-attached User inside a transaction; returns True if a token was granted."""
    today = _utc_today()
    if user.token_balance > 0 or user.last_free_token_day == today:
        return False
    user.token_balance = 1
    user.last_free_token_day = today
    return True


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
    # The UTC date ("YYYY-MM-DD") this account last received its free daily token (see grant_daily_token).
    # NULL = never granted. Patched into pre-existing DBs by db._ensure_user_columns.
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


class Purchase(Base):
    """One completed Stripe Checkout payment — historically a token pack, now a pay-what-you-want
    donation (price_id="donation", tokens = thank-you tokens granted). The UNIQUE stripe_session_id is the
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
            "tokens": self.tokens,
            "amount_cents": self.amount_cents,
            "currency": self.currency,
            "status": self.status,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
