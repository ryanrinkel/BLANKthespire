"""CLI: human review of quarantined cards (PRD §10.3 step 5).

    uv run btsgen-review list
    uv run btsgen-review show <id>
    uv run btsgen-review approve <id>     # promote into data/cards/ (enters the reward pool)
    uv run btsgen-review reject  <id>     # delete from quarantine

`approve` re-validates against the live engine contract and refuses to clobber an
authored card id, so the promote step can't silently corrupt the pool.
"""
from __future__ import annotations

import argparse
import json
import sys

from . import paths
from .validator import CardValidator


def _generated_cards() -> list[tuple[str, dict, dict]]:
    """(id, card, meta) for every quarantined card, sorted by id."""
    out = []
    if not paths.GENERATED_DIR.exists():
        return out
    for f in sorted(paths.GENERATED_DIR.glob("*.json")):
        if f.name.endswith(".meta.json"):
            continue
        card = json.loads(f.read_text())
        meta_f = paths.GENERATED_DIR / f"{f.stem}.meta.json"
        meta = json.loads(meta_f.read_text()) if meta_f.exists() else {}
        out.append((f.stem, card, meta))
    return out


def _cmd_list(_args) -> int:
    rows = _generated_cards()
    if not rows:
        print("(no quarantined cards in data/generated/cards/)")
        return 0
    print(f"{len(rows)} card(s) awaiting review:\n")
    for cid, card, meta in rows:
        score = meta.get("score", "?")
        warn = "  [!]" if meta.get("warnings") else ""
        print(f"  {cid:<22} {card.get('type','?'):<7} {card.get('rarity','?'):<9} "
              f"cost {card.get('cost','?')!s:<3} score {score}{warn}")
        if meta.get("brief"):
            print(f"      brief: {meta['brief']}")
        for w in meta.get("warnings", []):
            print(f"      WARN: {w}")
    print("\napprove:  uv run btsgen-review approve <id>")
    return 0


def _cmd_show(args) -> int:
    f = paths.GENERATED_DIR / f"{args.id}.json"
    if not f.exists():
        print(f"no quarantined card '{args.id}'", file=sys.stderr)
        return 1
    print(f.read_text())
    return 0


def _cmd_approve(args) -> int:
    f = paths.GENERATED_DIR / f"{args.id}.json"
    if not f.exists():
        print(f"no quarantined card '{args.id}'", file=sys.stderr)
        return 1
    card = json.loads(f.read_text())

    # Re-validate against the live contract before it can enter the pool.
    vr = CardValidator().validate(card)
    if not vr.ok:
        print(f"refusing to promote '{args.id}' — fails validation now:", file=sys.stderr)
        for e in vr.errors:
            print(f"  - {e}", file=sys.stderr)
        return 1

    dest = paths.CARDS_DIR / f"{card['id']}.json"
    if dest.exists():
        print(f"refusing to promote: data/cards/{card['id']}.json already exists "
              f"(would overwrite an authored card)", file=sys.stderr)
        return 1

    dest.write_text(json.dumps(card, indent=2) + "\n")
    f.unlink()
    (paths.GENERATED_DIR / f"{args.id}.meta.json").unlink(missing_ok=True)
    print(f"promoted '{card['id']}' -> {dest}")
    print("It enters the seeded reward pool on the next ContentDB load (restart/replay the scene).")
    if vr.warnings:
        for w in vr.warnings:
            print(f"  (balance) {w}")
    return 0


def _cmd_reject(args) -> int:
    f = paths.GENERATED_DIR / f"{args.id}.json"
    if not f.exists():
        print(f"no quarantined card '{args.id}'", file=sys.stderr)
        return 1
    f.unlink()
    (paths.GENERATED_DIR / f"{args.id}.meta.json").unlink(missing_ok=True)
    print(f"rejected and removed '{args.id}'")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Review LLM-quarantined cards.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list", help="list quarantined cards with scores")
    sp = sub.add_parser("show", help="print one quarantined card's JSON"); sp.add_argument("id")
    sp = sub.add_parser("approve", help="promote a card into data/cards/"); sp.add_argument("id")
    sp = sub.add_parser("reject", help="delete a card from quarantine"); sp.add_argument("id")
    args = ap.parse_args(argv)
    return {"list": _cmd_list, "show": _cmd_show, "approve": _cmd_approve, "reject": _cmd_reject}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
