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

from models import INITIAL_TOKENS, Base

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
        # WAL lets the 8 gthread workers read while a write is in flight (no "database is locked"
        # under concurrency), and is what Litestream replicates from. synchronous=NORMAL is the
        # recommended (and still durable-on-app-crash) pairing with WAL; busy_timeout makes any
        # residual writer contention wait instead of erroring.
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA synchronous=NORMAL")
        cur.execute("PRAGMA busy_timeout=5000")
        cur.close()

SessionLocal = sessionmaker(bind=engine, expire_on_commit=False, future=True)


def _ensure_user_columns() -> None:
    """Tiny forward-only migration (no Alembic): add columns introduced after the original schema to an
    existing `users` table. create_all() only CREATES missing tables — it never ALTERs an existing one — so
    a column added to the model later (token_balance) must be patched in here. Idempotent + safe on every boot
    for both SQLite (dev) and MySQL (prod); existing rows are backfilled to the default by the column default."""
    insp = inspect(engine)
    if "users" not in insp.get_table_names():
        return  # create_all will make it fresh with the column already present
    cols = {c["name"] for c in insp.get_columns("users")}
    if "token_balance" not in cols:
        with engine.begin() as conn:
            conn.execute(text(
                f"ALTER TABLE users ADD COLUMN token_balance INTEGER NOT NULL DEFAULT {int(INITIAL_TOKENS)}"))
    if "last_free_token_day" not in cols:
        # Donation-based pricing: the UTC day each account last got its free daily token. NULL (the
        # backfill for existing rows) = never granted, so everyone is eligible immediately.
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE users ADD COLUMN last_free_token_day VARCHAR(10)"))


def _ensure_class_columns() -> None:
    """Same tiny forward-only migration as _ensure_user_columns, for the `classes` table: add the
    splash_hash (Track 2 splash art) and sprite_hash (combat-model sprite) columns to DBs created
    before them. Idempotent; SQLite + MySQL."""
    insp = inspect(engine)
    if "classes" not in insp.get_table_names():
        return  # create_all will make it fresh with the columns already present
    cols = {c["name"] for c in insp.get_columns("classes")}
    for col in ("splash_hash", "sprite_hash"):
        if col not in cols:
            with engine.begin() as conn:
                conn.execute(text(f"ALTER TABLE classes ADD COLUMN {col} VARCHAR(64)"))


def init_db() -> None:
    """Create tables if absent, then patch in any later-added columns. Safe to call on every boot."""
    Base.metadata.create_all(engine)
    _ensure_user_columns()
    _ensure_class_columns()


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
