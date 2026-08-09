"""Rotate generated art when the disk runs low: free space by deleting the oldest classes' big art.

Deletes, oldest-first (by class updated_at), the BIG per-class art files (splash.png + sprite.png)
of classes not touched in --keep-days, plus whole art dirs orphaned by pre-cleanup deletes, until
free disk is back above --target-free-gb. relic.png and the small forge-meta JSONs are kept (tiny,
and relic_icon_url is embedded in stored bundles). Pruned classes get splash_hash/sprite_hash
cleared so the site/API stop advertising the art; the mod shows its "?" placeholder for future
imports of an old code (players who already imported keep the copy the game cached at import time).

Run daily by deploy/btsweb-prune.timer (no-op while free space is above target). Manual preview:

    cd web && ../.venv/bin/python tools/prune_forged_art.py --dry-run --target-free-gb 999
"""
from __future__ import annotations

import argparse
import shutil
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

WEB_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(WEB_DIR))  # import the app's db/models; env comes from the service (systemd)

from db import session_scope  # noqa: E402
from models import ForgedClass  # noqa: E402

FORGED_DIR = WEB_DIR / "static" / "forged"
BIG_FILES = ("splash.png", "sprite.png")


def _dir_size(d: Path) -> int:
    return sum(f.stat().st_size for f in d.rglob("*") if f.is_file())


def main() -> int:
    ap = argparse.ArgumentParser(description="rotate forged art when disk is low")
    ap.add_argument("--target-free-gb", type=float, default=5.0,
                    help="prune until at least this much disk is free (default 5)")
    ap.add_argument("--keep-days", type=int, default=30,
                    help="never touch art of classes updated in the last N days (default 30)")
    ap.add_argument("--dry-run", action="store_true", help="report what would be pruned, change nothing")
    args = ap.parse_args()

    if not FORGED_DIR.exists():
        print("nothing to do: no forged-art dir")
        return 0
    free = shutil.disk_usage(FORGED_DIR).free
    target = int(args.target_free_gb * 2**30)
    if free >= target:
        print(f"ok: {free / 2**30:.1f}GB free >= {args.target_free_gb}GB target — nothing pruned")
        return 0

    need = target - free
    freed = 0
    acts: list[str] = []

    with session_scope() as s:
        rows = s.query(ForgedClass.id, ForgedClass.updated_at,
                       ForgedClass.splash_hash, ForgedClass.sprite_hash).all()
        live_ids = {r.id for r in rows}

        # 1) Orphaned dirs (classes deleted before the app cleaned art up): the whole dir goes.
        for d in sorted(FORGED_DIR.iterdir()):
            if freed >= need:
                break
            if d.is_dir() and d.name.isdigit() and int(d.name) not in live_ids:
                size = _dir_size(d)
                acts.append(f"orphan dir {d.name}: {size / 2**20:.1f}MB")
                freed += size
                if not args.dry_run:
                    shutil.rmtree(d, ignore_errors=True)

        # 2) Oldest classes' big art. rows sort oldest-first, so the first row inside keep-days
        #    means everything after it is newer — stop there. (updated_at is naive UTC in the DB.)
        cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=args.keep_days)
        for r in sorted(rows, key=lambda r: r.updated_at or datetime.min):
            if freed >= need:
                break
            if r.updated_at and r.updated_at > cutoff:
                break
            d = FORGED_DIR / str(r.id)
            size = sum((d / f).stat().st_size for f in BIG_FILES if (d / f).exists())
            if size == 0:
                continue
            acts.append(f"class {r.id} (updated {r.updated_at}): {size / 2**20:.1f}MB")
            freed += size
            if not args.dry_run:
                for f in BIG_FILES:
                    (d / f).unlink(missing_ok=True)
                s.query(ForgedClass).filter_by(id=r.id).update(
                    {"splash_hash": None, "sprite_hash": None})

    verb = "would prune" if args.dry_run else "pruned"
    for a in acts:
        print(f"{verb}: {a}")
    print(f"{verb} {len(acts)} item(s), {freed / 2**20:.1f}MB "
          f"(free was {free / 2**30:.2f}GB, target {args.target_free_gb}GB)")
    if freed < need:
        print(f"WARNING: still {(need - freed) / 2**30:.2f}GB short after pruning all eligible art "
              f"(only classes idle >{args.keep_days} days qualify) — grow the disk or lower --keep-days.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
