"""List the forges still running in the LIVE database — deploy.sh's drain step (WALK_AWAY_FORGE_PLAN.md 5.1).

    python web/deploy/running_forges.py [--env-file /opt/btsweb/web/.env]

Output (stdout, machine-readable, tab-separated):

    <count>
    <age_minutes>\t<mode>\t<concept, first 60 chars, tabs/newlines flattened>    (one line per running job)

READ-ONLY and standalone on purpose. It never imports web/app.py (whose import-time boot work refunds every
"running" forge — exactly the jobs this script is protecting) and not even web/db.py: db.py's SQLite engine
opens every transaction with BEGIN IMMEDIATE, i.e. it takes the WRITE lock. SQLite is opened with
`mode=ro`; anything else goes through a plain SQLAlchemy engine with the same TLS knobs as db.py.

It always exits 0. An unreachable database prints count 0 plus a warning on stderr, so a drain problem can
never block a deploy (the restart then behaves exactly as before the drain existed). Secrets read from the
env file are never printed.
"""
from __future__ import annotations

import argparse
import os
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

WEB_DIR = Path(__file__).resolve().parents[1]
DEFAULT_ENV_FILE = WEB_DIR / ".env"
CONCEPT_CHARS = 60

_QUERY = "SELECT id, mode, concept, started_at FROM forge_jobs WHERE status = 'running' ORDER BY started_at"


def load_env_file(path) -> None:
    """Tiny KEY=VALUE loader (the systemd EnvironmentFile subset): skips blanks and # comments, strips an
    optional `export ` and matching surrounding quotes, and never overrides a variable already set."""
    try:
        lines = Path(path).read_text(encoding="utf-8").splitlines()
    except OSError:
        return
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if key.startswith("export "):
            key = key[len("export "):].strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        if key and key not in os.environ:
            os.environ[key] = value


def database_url() -> str:
    """Same resolution as web/db.py.database_url()."""
    return os.environ.get("BTSWEB_DATABASE_URL") or f"sqlite:///{(WEB_DIR / 'dev.db').as_posix()}"


def _parse_dt(value):
    if value is None or isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value).strip())
    except ValueError:
        return None


def _sqlite_rows(url: str) -> list[tuple]:
    from sqlalchemy.engine import make_url
    path = make_url(url).database
    if not path or path == ":memory:":
        return []
    if not Path(path).exists():
        raise FileNotFoundError(f"database file not found: {path}")
    conn = sqlite3.connect(f"{Path(path).resolve().as_uri()}?mode=ro", uri=True, timeout=5)
    try:
        return conn.execute(_QUERY).fetchall()
    finally:
        conn.close()


def _server_rows(url: str) -> list[tuple]:
    from sqlalchemy import create_engine, text
    kwargs: dict = {"future": True}
    if url.startswith("mysql"):
        ca = os.environ.get("BTSWEB_DB_SSL_CA")
        if ca:
            kwargs["connect_args"] = {"ssl": {"ca": ca}}
        elif os.environ.get("BTSWEB_DB_SSL", "").strip() in ("1", "true", "yes"):
            kwargs["connect_args"] = {"ssl": {}}
    engine = create_engine(url, **kwargs)
    try:
        with engine.connect() as conn:
            return [tuple(r) for r in conn.execute(text(_QUERY)).fetchall()]
    finally:
        engine.dispose()


def running_jobs(url: str, now: datetime | None = None) -> list[dict]:
    """Every forge_jobs row with status='running', oldest first, as
    {id, mode, concept (<= 60 chars, one line), age_min (int, or None if started_at is unreadable)}.
    started_at is naive UTC (server_default now()). Raises on a database error; main() turns that into 0."""
    rows = _sqlite_rows(url) if url.startswith("sqlite") else _server_rows(url)
    now = now or datetime.now(timezone.utc).replace(tzinfo=None)
    out = []
    for job_id, mode, concept, started_at in rows:
        started = _parse_dt(started_at)
        if started is not None and started.tzinfo is not None:
            started = started.astimezone(timezone.utc).replace(tzinfo=None)
        age = max(0, int((now - started).total_seconds() // 60)) if started else None
        flat = " ".join(str(concept or "").split())
        out.append({"id": str(job_id), "mode": str(mode or "?"), "concept": flat[:CONCEPT_CHARS], "age_min": age})
    return out


def format_report(jobs: list[dict]) -> str:
    lines = [str(len(jobs))]
    for j in jobs:
        age = "?" if j["age_min"] is None else str(j["age_min"])
        lines.append(f"{age}\t{j['mode']}\t{j['concept']}")
    return "\n".join(lines)


def _scrub(msg: str) -> str:
    """Drop the database password from an error message, should a driver ever echo the URL."""
    try:
        from sqlalchemy.engine import make_url
        pw = make_url(database_url()).password
    except Exception:
        pw = None
    return msg.replace(pw, "***") if pw else msg


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--env-file", default=str(DEFAULT_ENV_FILE))
    args = ap.parse_args(argv)
    load_env_file(args.env_file)
    try:
        jobs = running_jobs(database_url())
    except Exception as e:  # never block a deploy on the drain
        print(f"running_forges: could not read forge_jobs ({type(e).__name__}: {_scrub(str(e))[:300]})"
              " - assuming 0 running", file=sys.stderr)
        jobs = []
    print(format_report(jobs))
    return 0


if __name__ == "__main__":
    sys.exit(main())
