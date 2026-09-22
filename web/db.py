"""Engine + session plumbing. SQLite for local dev; cPanel MySQL in prod via BTSWEB_DATABASE_URL.

    sqlite (default, dev):  sqlite:///<web>/dev.db
    mysql  (prod, cPanel):  mysql+pymysql://user:pass@host/dbname
"""
from __future__ import annotations

import os
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.orm import sessionmaker

from models import INITIAL_TOKENS, Base, new_slug

WEB_DIR = Path(__file__).resolve().parent


def database_url() -> str:
    url = os.environ.get("BTSWEB_DATABASE_URL")
    if url:
        return url
    return f"sqlite:///{(WEB_DIR / 'dev.db').as_posix()}"


_url = database_url()
# SQLite needs check_same_thread off for Flask's threaded dev server; pool_pre_ping keeps MySQL alive.
_engine_kwargs: dict = {"pool_pre_ping": True, "future": True}
if _url.startswith("sqlite"):
    _engine_kwargs["connect_args"] = {"check_same_thread": False}
elif _url.startswith("mysql"):
    # DO Managed MySQL requires TLS. Point BTSWEB_DB_SSL_CA at the downloaded CA cert (verified TLS),
    # or set BTSWEB_DB_SSL=1 to use TLS without CA verification.
    _ca = os.environ.get("BTSWEB_DB_SSL_CA")
    if _ca:
        _engine_kwargs["connect_args"] = {"ssl": {"ca": _ca}}
    elif os.environ.get("BTSWEB_DB_SSL", "").strip() in ("1", "true", "yes"):
        _engine_kwargs["connect_args"] = {"ssl": {}}

engine = create_engine(_url, **_engine_kwargs)

if _url.startswith("sqlite"):
    @event.listens_for(engine, "connect")
    def _sqlite_pragmas(dbapi_conn, _record):
        # WAL lets the gthread workers read while a write is in flight (and is what Litestream
        # replicates from). synchronous=NORMAL is the recommended (still durable-on-app-crash)
        # pairing with WAL; busy_timeout makes writer contention wait instead of erroring.
        dbapi_conn.isolation_level = None  # take over BEGIN ourselves (see _sqlite_begin)
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA synchronous=NORMAL")
        cur.execute("PRAGMA busy_timeout=5000")
        cur.close()

    @event.listens_for(engine, "begin")
    def _sqlite_begin(conn):
        # BEGIN IMMEDIATE: take the write lock at transaction start. A session that reads first
        # and INSERTs later (e.g. _persist_class) would otherwise upgrade its deferred read
        # transaction mid-flight — and if another connection wrote in between, SQLite returns
        # SQLITE_BUSY *immediately* (the busy handler is bypassed by design: the read snapshot is
        # stale and retrying could never succeed). Verified live: 3 forges persisting at once all
        # failed "database is locked" under deferred BEGIN; with IMMEDIATE they queue on
        # busy_timeout. Cost: transactions serialize — fine at this scale (all writes are ~ms).
        conn.exec_driver_sql("BEGIN IMMEDIATE")

SessionLocal = sessionmaker(bind=engine, expire_on_commit=False, future=True)


def _ensure_user_columns() -> None:
    """Tiny forward-only migration (no Alembic): add columns introduced after the original schema to an
    existing `users` table. create_all() only CREATES missing tables — it never ALTERs an existing one — so
    a column added to the model later (token_balance, unlimited_tokens) must be patched in here. Idempotent +
    safe on every boot for both SQLite (dev) and MySQL (prod); existing rows are backfilled to the default by
    the column default."""
    insp = inspect(engine)
    if "users" not in insp.get_table_names():
        return  # create_all will make it fresh with the column already present
    cols = {c["name"] for c in insp.get_columns("users")}
    if "token_balance" not in cols:
        with engine.begin() as conn:
            conn.execute(text(
                f"ALTER TABLE users ADD COLUMN token_balance INTEGER NOT NULL DEFAULT {int(INITIAL_TOKENS)}"))
    if "last_free_token_day" not in cols:
        # LEGACY: the free daily token is gone (pricing v3) and nothing reads this column any more. The ALTER
        # stays because the model still declares the column — prod MySQL has it and dropping it across
        # engines without Alembic isn't worth the risk — so a fresh-ish DB must still get it. Harmless.
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE users ADD COLUMN last_free_token_day VARCHAR(10)"))
    if "unlimited_tokens" not in cols:
        # The operator-granted unlimited flag (User.unlimited_tokens). Everyone who existed before it defaults
        # to 0 — i.e. nothing changes for them: unlimited stays whatever BTSWEB_UNLIMITED_EMAILS already said.
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE users ADD COLUMN unlimited_tokens INTEGER NOT NULL DEFAULT 0"))


def _ensure_class_columns() -> None:
    """Same tiny forward-only migration as _ensure_user_columns, for the `classes` table: add the
    splash_hash (Track 2 splash art), sprite_hash (combat-model sprite) and card_art_hash (the per-card
    portrait zip) columns to DBs created before them. Idempotent; SQLite + MySQL."""
    insp = inspect(engine)
    if "classes" not in insp.get_table_names():
        return  # create_all will make it fresh with the columns already present
    cols = {c["name"] for c in insp.get_columns("classes")}
    for col in ("splash_hash", "sprite_hash", "card_art_hash"):
        if col not in cols:
            with engine.begin() as conn:
                conn.execute(text(f"ALTER TABLE classes ADD COLUMN {col} VARCHAR(64)"))
    if "slug" not in cols:
        # Unguessable share handle (/api/deck/<slug>). Add the column, then give every existing row a slug so
        # old classes stay shareable, then add the unique index (MySQL can't add a UNIQUE column with NULLs
        # filled in the same statement across engines, so it's three steps).
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE classes ADD COLUMN slug VARCHAR(32)"))
        _backfill_slugs()
        with engine.begin() as conn:
            conn.execute(text("CREATE UNIQUE INDEX ix_classes_slug ON classes (slug)"))


def _ensure_purchase_columns() -> None:
    """Same tiny forward-only migration as _ensure_class_columns, for the `purchases` table: add `net_cents`
    (the donation line alone, without the pass-through card fee — pricing v3) to DBs created before it.
    Nullable with no default on purpose: rows from the pack / pay-what-you-want eras really do have no net,
    and NULL is what makes Purchase.summary() omit the fee split for them. Idempotent; SQLite + MySQL."""
    insp = inspect(engine)
    if "purchases" not in insp.get_table_names():
        return  # create_all will make it fresh with the column already present
    cols = {c["name"] for c in insp.get_columns("purchases")}
    if "net_cents" not in cols:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE purchases ADD COLUMN net_cents INTEGER"))


def _ensure_forge_usage_columns() -> None:
    """Same tiny forward-only migration as _ensure_class_columns, for the `forge_usage` table: add the
    `provider` column (where the call went — "hosted" / "anthropic" / a BYOK hostname) and
    `metered_cost_micros` (what the provider actually billed, vs the rate-table est_cost_micros) to DBs
    created before them. Idempotent; SQLite + MySQL."""
    insp = inspect(engine)
    if "forge_usage" not in insp.get_table_names():
        return  # create_all will make it fresh with the column already present
    cols = {c["name"] for c in insp.get_columns("forge_usage")}
    if "provider" not in cols:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE forge_usage ADD COLUMN provider VARCHAR(64) DEFAULT ''"))
    if "metered_cost_micros" not in cols:
        # Nullable with no default: existing rows stay NULL = "nobody metered this", which is exactly
        # what they are (they predate usage:{include:true}), so the readers fall back to est_cost_micros.
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE forge_usage ADD COLUMN metered_cost_micros INTEGER"))


def _backfill_slugs() -> None:
    """Give every class row without a slug a fresh random one (idempotent; safe on every boot)."""
    with engine.begin() as conn:
        ids = [r[0] for r in conn.execute(text("SELECT id FROM classes WHERE slug IS NULL")).fetchall()]
        for cid in ids:
            conn.execute(text("UPDATE classes SET slug = :slug WHERE id = :id"), {"slug": new_slug(), "id": cid})


def _ensure_identities() -> None:
    """Backfill `identities` from the legacy users.google_sub so accounts made before sign-in providers
    existed resolve exactly like new ones (auth._resolve_identity looks users up by identity, never by
    google_sub). `dev:<x>` (the local bypass) -> provider "dev", subject <x>; anything else is a raw Google
    sub. Idempotent — only users with no identity row are touched — so it is safe on every boot, and it is
    plain SQL so SQLite and MySQL behave the same."""
    insp = inspect(engine)
    names = set(insp.get_table_names())
    if "users" not in names or "identities" not in names:
        return
    with engine.begin() as conn:
        rows = conn.execute(text(
            "SELECT u.id, u.google_sub, u.email FROM users u "
            "LEFT JOIN identities i ON i.user_id = u.id WHERE i.id IS NULL")).fetchall()
        for uid, sub, email in rows:
            sub = sub or ""
            provider, subject = ("dev", sub[4:]) if sub.startswith("dev:") else ("google", sub)
            conn.execute(
                text("INSERT INTO identities (user_id, provider, subject, email) "
                     "VALUES (:uid, :provider, :subject, :email)"),
                {"uid": uid, "provider": provider, "subject": subject, "email": (email or "").strip().lower()})


def init_db() -> None:
    """Create tables if absent, then patch in any later-added columns. Safe to call on every boot."""
    Base.metadata.create_all(engine)
    _ensure_user_columns()
    _ensure_class_columns()
    _ensure_purchase_columns()
    _ensure_forge_usage_columns()
    _backfill_slugs()  # rows inserted by code paths that predate the slug (belt and braces)
    _ensure_identities()  # every user needs an identity row before the first sign-in of this boot


def db_ping() -> bool:
    """One trivial round-trip; False if the database is unreachable (used by /healthz)."""
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


@contextmanager
def session_scope():
    """Transactional scope — commit on success, rollback on error, always close."""
    s = SessionLocal()
    try:
        yield s
        s.commit()
    except Exception:
        s.rollback()
        raise
    finally:
        s.close()
