"""CLI: human review of quarantined relics (parallel to cli_review.py).

    uv run btsgen-relic-review list
    uv run btsgen-relic-review show <id>
    uv run btsgen-relic-review approve <id>     # promote into data/relics/ (enters the reward pool)
    uv run btsgen-relic-review reject  <id>     # delete from quarantine

`approve` re-validates against the live engine contract and refuses to clobber an authored relic
id, so the promote step can't silently corrupt the pool.
"""
from __future__ import annotations

import argparse
import json
import sys

from . import paths
from .relic_validator import RelicValidator


def _generated_relics() -> list[tuple[str, dict, dict]]:
    """(id, relic, meta) for every quarantined relic, sorted by id."""
    out = []
    if not paths.GENERATED_RELICS_DIR.exists():
        return out
    for f in sorted(paths.GENERATED_RELICS_DIR.glob("*.json")):
        if f.name.endswith(".meta.json"):
            continue
        relic = json.loads(f.read_text())
        meta_f = paths.GENERATED_RELICS_DIR / f"{f.stem}.meta.json"
        meta = json.loads(meta_f.read_text()) if meta_f.exists() else {}
        out.append((f.stem, relic, meta))
    return out


def _cmd_list(_args) -> int:
    rows = _generated_relics()
    if not rows:
        print("(no quarantined relics in data/generated/relics/)")
        return 0
    print(f"{len(rows)} relic(s) awaiting review:\n")
    for rid, relic, meta in rows:
        score = meta.get("score", "?")
        warn = "  [!]" if meta.get("warnings") else ""
        print(f"  {rid:<24} {relic.get('tier','?'):<9} {relic.get('pool','?'):<7} power~{score}{warn}")
        if relic.get("description"):
            print(f"      {relic['description']}")
        if meta.get("brief"):
            print(f"      brief: {meta['brief']}")
        for w in meta.get("warnings", []):
            print(f"      WARN: {w}")
    print("\napprove:  uv run btsgen-relic-review approve <id>")
    return 0


def _cmd_show(args) -> int:
    f = paths.GENERATED_RELICS_DIR / f"{args.id}.json"
    if not f.exists():
        print(f"no quarantined relic '{args.id}'", file=sys.stderr)
        return 1
    print(f.read_text())
    return 0


def _cmd_approve(args) -> int:
    f = paths.GENERATED_RELICS_DIR / f"{args.id}.json"
    if not f.exists():
        print(f"no quarantined relic '{args.id}'", file=sys.stderr)
        return 1
    relic = json.loads(f.read_text())

    # Re-validate against the live contract before it can enter the pool.
    vr = RelicValidator().validate(relic)
    if not vr.ok:
        print(f"refusing to promote '{args.id}' -- fails validation now:", file=sys.stderr)
        for e in vr.errors:
            print(f"  - {e}", file=sys.stderr)
        return 1

    dest = paths.RELICS_DIR / f"{relic['id']}.json"
    if dest.exists():
        print(f"refusing to promote: data/relics/{relic['id']}.json already exists "
              f"(would overwrite an authored relic)", file=sys.stderr)
        return 1

    dest.write_text(json.dumps(relic, indent=2) + "\n")
    f.unlink()
    (paths.GENERATED_RELICS_DIR / f"{args.id}.meta.json").unlink(missing_ok=True)
    print(f"promoted '{relic['id']}' -> {dest}")
    print("It enters the seeded reward pool on the next ContentDB load (restart/replay the scene).")
    if vr.warnings:
        for w in vr.warnings:
            print(f"  (balance) {w}")
    return 0


def _cmd_reject(args) -> int:
    f = paths.GENERATED_RELICS_DIR / f"{args.id}.json"
    if not f.exists():
        print(f"no quarantined relic '{args.id}'", file=sys.stderr)
        return 1
    f.unlink()
    (paths.GENERATED_RELICS_DIR / f"{args.id}.meta.json").unlink(missing_ok=True)
    print(f"rejected and removed '{args.id}'")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Review LLM-quarantined relics.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list", help="list quarantined relics with power proxies")
    sp = sub.add_parser("show", help="print one quarantined relic's JSON"); sp.add_argument("id")
    sp = sub.add_parser("approve", help="promote a relic into data/relics/"); sp.add_argument("id")
    sp = sub.add_parser("reject", help="delete a relic from quarantine"); sp.add_argument("id")
    args = ap.parse_args(argv)
    return {"list": _cmd_list, "show": _cmd_show, "approve": _cmd_approve, "reject": _cmd_reject}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
