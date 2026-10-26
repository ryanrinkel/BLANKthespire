"""Copy web/featured.json into The Archive's database columns (docs/plans/FORGE_FIRST_PLAN.md 5.2, Phase B).

Since Phase B the database is the source of truth for The Archive: a class is in it while
classes.featured_at is set (newest featured first), with classes.featured_word as its tile's board word.
featured.json is only the SEED, and the app already applies it at boot whenever NO class is featured
(app.seed_featured_from_file), so on a normal deploy this script has nothing to do. Run it to apply the file
by hand, or to see what it would do:

    cd web && ../.venv/bin/python tools/migrate_featured.py            # apply while nothing is featured
    cd web && ../.venv/bin/python tools/migrate_featured.py --force    # apply even if something is featured
    cd web && ../.venv/bin/python tools/migrate_featured.py --file other.json

Without --force it is a no-op as soon as any class is featured (idempotent: safe to run twice).
--force applies the file even though The Archive already has classes, but ONLY to rows whose class is not
featured yet (an already-featured class keeps its word and its place). Either way row i of the file gets
featured_at = now - i seconds, so the file's first row is the newest and the order is kept; slugs that no
longer resolve are skipped.

It touches only the classes table (through db.py), and deliberately does not import app.py: the app's
import-time boot work (forge-job reconciliation refunds every "running" forge) must never run beside the
live service. The database comes from BTSWEB_DATABASE_URL, read from web/.env like the app does unless
BTSWEB_NO_DOTENV=1.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

WEB_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(WEB_DIR))

if os.environ.get("BTSWEB_NO_DOTENV", "").strip() not in ("1", "true", "yes"):
    try:
        from dotenv import load_dotenv
        load_dotenv(WEB_DIR / ".env")
    except ImportError:  # the service env may already carry everything
        pass

from db import init_db, seed_featured_from_file, session_scope  # noqa: E402
from models import ForgedClass  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="seed The Archive (classes.featured_at) from featured.json")
    ap.add_argument("--file", default=os.environ.get("BTSWEB_FEATURED_FILE", "").strip()
                    or str(WEB_DIR / "featured.json"),
                    help="the seed file (default: $BTSWEB_FEATURED_FILE, else web/featured.json)")
    ap.add_argument("--force", action="store_true",
                    help="apply even if some class is already featured (only to rows not yet featured)")
    args = ap.parse_args()

    init_db()  # the four Archive columns, if this runs before the app has booted once

    def say(msg, *a):
        print(msg % a if a else msg)

    n = seed_featured_from_file(Path(args.file), force=args.force, warn=say, info=say)
    with session_scope() as s:
        rows = (s.query(ForgedClass.featured_word, ForgedClass.name, ForgedClass.slug)
                .filter(ForgedClass.featured_at.isnot(None))
                .order_by(ForgedClass.featured_at.desc(), ForgedClass.id.desc()).all())
    hint = (" (The Archive already had classes; --force applies the file anyway)"
            if not n and not args.force and rows else "")
    print(f"featured {n} class(es) from {args.file}{hint}")
    print(f"The Archive now holds {len(rows)} class(es), newest first:")
    for word, name, slug in rows:
        print(f"  {word or '-----'}  {name}  /deck/{slug}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
