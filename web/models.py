"""ORM models for the P3 site: users, their forged classes, and denormalized per-card rows.

BYOK API keys appear in NO table by design — only generated *content* (classes, cards, codes) is persisted.
JSON blobs are stored as TEXT (portable across SQLite-for-dev and MySQL-for-prod).
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


# Tokens an account starts with: NONE (pricing v3, 2026-09-18). One token = one hosted "Use a token" forge
# on our server key. There is no free token of any kind any more — neither a starter grant nor the old one
# per UTC day. The two ways to forge are: bring your own API key (free, unlimited, billed by your provider)
# or spend a token received as a thank-you for a fixed-amount donation (billing.DONATION_TIERS). Nothing is
# sold. Balances granted under the older models (starter 5s, per-dollar thank-yous, the retired 2026-09-08..16
# token packs) are left exactly as they are — v3 stops granting, it never claws back.
INITIAL_TOKENS = 0


def _utc_today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def spend_token(user: "User", today: str | None = None) -> str | None:
    """Spend ONE token for a hosted forge: decrement the balance and return "paid", or None when the balance
    is empty (caller 402s). `today` is accepted and ignored — it dated the retired free daily token, and the
    callers still pass it. Call with a session-attached User inside a transaction so the read+write are
    atomic (two concurrent forges must not both spend the last token)."""
    if user.token_balance > 0:
        user.token_balance -= 1
        return "paid"
    return None


def unspend_token(user: "User", kind: str, day: str | None = None) -> None:
    """Give back a token reserved by spend_token (the forge failed): "paid" -> +1 balance. Anything else is a
    no-op — historical ForgeJob rows still carry token_kind="free" from the retired free daily token, and
    reconciling one of those at boot must not mint a token that never existed in the balance."""
    if kind == "paid":
        user.token_balance += 1


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # LEGACY column. Sign-in resolves through the `identities` table (auth._resolve_identity); nothing
    # reads google_sub after db._ensure_identities backfilled from it. It stays because it is NOT NULL
    # UNIQUE on prod MySQL and our no-Alembic boot migrations cannot relax nullability across engines —
    # so new rows are still given a unique value, f"{provider}:{subject}", while rows created before the
    # identities table keep their raw Google sub.
    google_sub: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    email: Mapped[str] = mapped_column(String(320), default="")
    name: Mapped[str] = mapped_column(String(255), default="")
    # Spendable balance for the hosted token path. server_default seeds DB-created rows; the boot migration
    # (db._ensure_user_columns) adds + backfills this column on databases that predate it.
    token_balance: Mapped[int] = mapped_column(
        Integer, default=INITIAL_TOKENS, server_default=str(INITIAL_TOKENS), nullable=False)
    # LEGACY column, dead since pricing v3 (2026-09-18): the UTC date this account last spent the retired free
    # daily token. Nothing reads or writes it any more. It stays because prod is MySQL with no Alembic and our
    # forward-only boot migrations cannot drop a column cleanly across engines; db._ensure_user_columns keeps
    # ADDing it to old databases, which is harmless.
    last_free_token_day: Mapped[str | None] = mapped_column(String(10), default=None, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    classes: Mapped[list["ForgedClass"]] = relationship(
        back_populates="user", cascade="all, delete-orphan")
    identities: Mapped[list["Identity"]] = relationship(
        back_populates="user", cascade="all, delete-orphan")


class Identity(Base):
    """One sign-in method owned by a user: (provider, subject) -> users.id. A user can own several
    (Google today; Discord/GitHub/email later), which is what lets someone sign in a different way and
    keep their tokens and classes. `email` is whatever the provider reported (lowercased, "" if none)
    and is kept here for display/debugging only — the account email that gates unlimited forging lives
    on users.email and is written ONLY from a provider-VERIFIED address (see auth._resolve_identity)."""
    __tablename__ = "identities"
    __table_args__ = (UniqueConstraint("provider", "subject", name="uq_identities_provider_subject"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    provider: Mapped[str] = mapped_column(String(16))   # google | discord | github | email | dev
    subject: Mapped[str] = mapped_column(String(255))   # the provider's stable id for this person
    email: Mapped[str] = mapped_column(String(320), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    user: Mapped[User] = relationship(back_populates="identities")


class LoginLink(Base):
    """One emailed magic link: a single-use, 15-minute sign-in ticket for `email`.

    Only sha256(token) is stored — the raw token (secrets.token_urlsafe(32)) exists in the email and
    nowhere else, so a database dump is not a stack of live sign-in links. `used_at` is what makes a link
    single-use; `ip` is the address that asked for it (abuse forensics). Rows are swept after 24 h by
    auth's start route. Datetimes are naive UTC (see auth._utc_naive): DateTime columns come back naive
    from both SQLite and MySQL, so one convention avoids aware/naive comparisons."""
    __tablename__ = "login_links"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(320), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    ip: Mapped[str] = mapped_column(String(64), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    used_at: Mapped[datetime | None] = mapped_column(DateTime, default=None, nullable=True)


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
    # Same marker for the per-card portrait pack (web/static/forged/<id>/cards.zip — ONE zip per class,
    # not ~34 URLs, so the mod's import does one download instead of one per card). NULL = not generated;
    # a PARTIAL pack (budget/cost cap hit mid-run) still gets a hash — the mod falls back per missing card.
    card_art_hash: Mapped[str | None] = mapped_column(String(64), default=None, nullable=True)
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
            "card_art_hash": self.card_art_hash,
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
    """One completed Stripe Checkout payment — a fixed-tier donation (price_id = the tier id, e.g. "t5"), a
    legacy pay-what-you-want donation (price_id="donation"), or a token pack from the retired pack era
    (price_id="pack_11"). The UNIQUE stripe_session_id is the idempotency guard: the webhook and the
    synchronous /api/checkout-status fallback both funnel through billing._credit_purchase, and a second
    delivery of the same session hits the constraint and credits nothing. Doubles as the user-facing
    purchase history."""
    __tablename__ = "purchases"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    # 191 keeps the unique index inside MySQL/utf8mb4 key limits; Stripe session ids are ~66 chars.
    stripe_session_id: Mapped[str] = mapped_column(String(191), unique=True, index=True)
    stripe_payment_intent: Mapped[str | None] = mapped_column(String(255), default=None, nullable=True)
    price_id: Mapped[str] = mapped_column(String(255), default="")
    tokens: Mapped[int] = mapped_column(Integer)               # tokens granted by this purchase
    amount_cents: Mapped[int] = mapped_column(Integer, default=0)   # GROSS: what the card was actually charged
    # What the project keeps after Stripe's cut — the donation line item, without the pass-through card fee
    # (pricing v3). NULL on every row that predates the two-line-item checkout (pack era, pay-what-you-want
    # donations), which is why the history renders a fee split only when it is present. Added after the table
    # existed ⇒ patched in by db._ensure_purchase_columns.
    net_cents: Mapped[int | None] = mapped_column(Integer, default=None, nullable=True)
    currency: Mapped[str] = mapped_column(String(8), default="usd")
    status: Mapped[str] = mapped_column(String(32), default="paid")  # "paid" | "refunded"
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    def summary(self) -> dict:
        """History-list shape for /api/purchases. amount_cents is the gross charge; net_cents/fee_cents are
        the v3 split (both None for pre-v3 rows, which carried no fee line item)."""
        net = int(self.net_cents) if self.net_cents is not None else None
        return {
            "id": self.id,
            "kind": "donation" if self._is_donation() else "pack",
            "tokens": self.tokens,
            "amount_cents": self.amount_cents,
            "net_cents": net,
            "fee_cents": (int(self.amount_cents) - net) if net is not None else None,
            "currency": self.currency,
            "status": self.status,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

    def _is_donation(self) -> bool:
        """Everything except a retired token pack is a donation: "donation" (the pay-what-you-want era), a
        v3 tier id ("t5", including the retired $20/$50 ones) or a custom gift. billing is imported lazily — it imports this module, so a top-level import would
        be a cycle."""
        pid = self.price_id or ""
        if pid == "donation":
            return True
        try:
            from billing import DONATION_PRICE_IDS
        except Exception:  # pragma: no cover — billing is always importable in practice
            return False
        return pid in DONATION_PRICE_IDS


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
    token_kind: Mapped[str | None] = mapped_column(String(10), default=None, nullable=True)  # paid|unlimited
    # ("free" on rows written before pricing v3 retired the free daily token.)
    # brainstorm | structure | cards | ... for LLM calls, and "art:splash" / "art:sprite" / "art:cards" for
    # the image rows (one per asset kind per forge; token columns 0, cost in metered_cost_micros). Anything
    # that only wants the LLM numbers filters role NOT LIKE 'art:%' (see app.forge_estimate).
    role: Mapped[str] = mapped_column(String(32), default="")
    model: Mapped[str] = mapped_column(String(128), default="")
    # WHERE the call went, never WHAT it was authenticated with: "hosted" (our Ollama mix), "anthropic", or
    # for BYOK the hostname of the user's base_url ("api.openai.com", ...). Keys are never stored anywhere.
    # Added after the table existed ⇒ patched in by db._ensure_forge_usage_columns.
    provider: Mapped[str] = mapped_column(String(64), default="")
    calls: Mapped[int] = mapped_column(Integer, default=0)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cached_tokens: Mapped[int] = mapped_column(Integer, default=0)
    # Micro-dollars (1e-6 USD) so the column stays an integer; NULL = not ours to pay (BYOK) or unknown model.
    # est_cost_micros is our RATE-TABLE guess (app.MODEL_PRICES x tokens). metered_cost_micros is what the
    # provider actually billed, reported per call by OpenRouter (usage:{include:true} -> usage.cost) and by
    # the image backends (ImageResult.cost_usd) — NULL when no call on the row carried one (Ollama never
    # does). Measured 2026-09-18: the rate table undercounts a real forge by 30-45%, so anything summing
    # money prefers metered when present and falls back to est per row. Added after the table existed ⇒
    # patched in by db._ensure_forge_usage_columns.
    est_cost_micros: Mapped[int | None] = mapped_column(Integer, default=None, nullable=True)
    metered_cost_micros: Mapped[int | None] = mapped_column(Integer, default=None, nullable=True)
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
    token_kind: Mapped[str | None] = mapped_column(String(10), default=None, nullable=True)  # paid|unlimited
    # ("free" on rows written before pricing v3 retired the free daily token.)
    token_day: Mapped[str | None] = mapped_column(String(10), default=None, nullable=True)   # UTC day reserved
    concept: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(16), default="running", index=True)  # running|done|failed
    refunded: Mapped[int] = mapped_column(Integer, default=0)
    class_id: Mapped[int | None] = mapped_column(Integer, default=None, nullable=True)
    error: Mapped[str] = mapped_column(String(500), default="")
    started_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, default=None, nullable=True)
