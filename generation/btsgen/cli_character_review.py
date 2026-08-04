"""CLI: human review of quarantined class BUNDLES (character + its cards + starter relic).

    uv run btsgen-character-review list
    uv run btsgen-character-review show <id>
    uv run btsgen-character-review approve <id>   # promote the WHOLE bundle into data/
    uv run btsgen-character-review reject  <id>   # delete the WHOLE bundle from quarantine

A bundle promotes or dies atomically: `approve` re-validates every artifact against the live
engine contract, refuses to clobber anything authored, and only then moves character ->
data/characters/, cards -> data/cards/, relic -> data/relics/. An unreviewed bundle is still
playable in-game (ContentDB loads quarantined bundles, tagged unreviewed); approve makes it
permanent, reject removes it.
"""
from __future__ import annotations

import argparse
import json
import sys

from . import paths
from .character_validator import CharacterValidator
from .relic_validator import RelicValidator
from .validator import CardValidator


def _bundles() -> list[tuple[str, dict, dict]]:
    """(id, character, meta) for every quarantined class, sorted by id."""
    out = []
    if not paths.GENERATED_CHARACTERS_DIR.exists():
        return out
    for f in sorted(paths.GENERATED_CHARACTERS_DIR.glob("*.json")):
        if f.name.endswith(".meta.json"):
            continue
        ch = json.loads(f.read_text())
        meta_f = paths.GENERATED_CHARACTERS_DIR / f"{f.stem}.meta.json"
        meta = json.loads(meta_f.read_text()) if meta_f.exists() else {}
        out.append((f.stem, ch, meta))
    return out


def _bundle_paths(ch: dict, meta: dict) -> dict:
    """Quarantine paths for every artifact in the bundle (cards/relic from the manifest)."""
    return {
        "cards": [paths.GENERATED_DIR / f"{cid}.json" for cid in meta.get("cards", [])],
        "relic": paths.GENERATED_RELICS_DIR / f"{meta.get('relic', ch.get('starting_relic'))}.json",
        "character": paths.GENERATED_CHARACTERS_DIR / f"{ch['id']}.json",
    }


def _cmd_list(_args) -> int:
    rows = _bundles()
    if not rows:
        print("(no quarantined classes in data/generated/characters/)")
        return 0
    print(f"{len(rows)} class bundle(s) awaiting review:\n")
    for cid, ch, meta in rows:
        nwarn = sum(len(v) for v in meta.get("warnings", {}).values())
        flag = "  [!]" if nwarn or meta.get("skipped") else ""
        print(f"  {cid:<20} {ch.get('name','?'):<24} hp {ch.get('max_hp','?'):<4}"
              f" deck {len(ch.get('starting_deck', [])):<3} set {len(meta.get('cards', [])):<3}"
              f" relic {meta.get('relic','?')}{flag}")
        if ch.get("description"):
            print(f"      {ch['description']}")
        if meta.get("concept"):
            print(f"      concept: {meta['concept']}")
        for what, warns in meta.get("warnings", {}).items():
            for w in warns:
                print(f"      WARN [{what}] {w}")
        if meta.get("skipped"):
            print(f"      skipped pool card(s): {', '.join(meta['skipped'])}")
    print("\napprove:  uv run btsgen-character-review approve <id>")
    return 0


def _cmd_show(args) -> int:
    f = paths.GENERATED_CHARACTERS_DIR / f"{args.id}.json"
    if not f.exists():
        print(f"no quarantined class '{args.id}'", file=sys.stderr)
        return 1
    ch = json.loads(f.read_text())
    meta_f = paths.GENERATED_CHARACTERS_DIR / f"{args.id}.meta.json"
    meta = json.loads(meta_f.read_text()) if meta_f.exists() else {}
    print(f.read_text())
    print("--- bundle ---")
    for cid in meta.get("cards", []):
        cf = paths.GENERATED_DIR / f"{cid}.json"
        if cf.exists():
            c = json.loads(cf.read_text())
            eff = json.dumps(c.get("effects", []), separators=(",", ":"))
            print(f"  card  {cid:<24} {c.get('cost')}E {c.get('type'):<7} {c.get('rarity'):<9}"
                  f" {c.get('archetype','-'):<12} {eff}")
        else:
            print(f"  card  {cid:<24} MISSING from quarantine")
    rid = meta.get("relic", ch.get("starting_relic"))
    rf = paths.GENERATED_RELICS_DIR / f"{rid}.json"
    if rf.exists():
        r = json.loads(rf.read_text())
        print(f"  relic {rid:<24} {r.get('description','')}")
    else:
        print(f"  relic {rid:<24} MISSING from quarantine")
    return 0


def _cmd_approve(args) -> int:
    f = paths.GENERATED_CHARACTERS_DIR / f"{args.id}.json"
    if not f.exists():
        print(f"no quarantined class '{args.id}'", file=sys.stderr)
        return 1
    ch = json.loads(f.read_text())
    meta_f = paths.GENERATED_CHARACTERS_DIR / f"{args.id}.meta.json"
    if not meta_f.exists():
        print(f"'{args.id}' has no bundle manifest (.meta.json); refusing a blind promote", file=sys.stderr)
        return 1
    meta = json.loads(meta_f.read_text())
    bp = _bundle_paths(ch, meta)

    # 1. every artifact must still exist + validate against the live contract
    missing = [str(p) for p in bp["cards"] + [bp["relic"]] if not p.exists()]
    if missing:
        print("refusing to promote -- bundle artifacts missing from quarantine:", file=sys.stderr)
        for m in missing:
            print(f"  - {m}", file=sys.stderr)
        return 1
    card_v, relic_v, char_v = CardValidator(), RelicValidator(), CharacterValidator()
    failures = []
    for p in bp["cards"]:
        vr = card_v.validate(json.loads(p.read_text()))
        if not vr.ok:
            failures += [f"card {p.stem}: {e}" for e in vr.errors]
    vr = relic_v.validate(json.loads(bp["relic"].read_text()))
    if not vr.ok:
        failures += [f"relic {bp['relic'].stem}: {e}" for e in vr.errors]
    vr = char_v.validate(ch)
    if not vr.ok:
        failures += [f"character: {e}" for e in vr.errors]
    if failures:
        print(f"refusing to promote '{args.id}' -- fails validation now:", file=sys.stderr)
        for e in failures:
            print(f"  - {e}", file=sys.stderr)
        return 1

    # 2. nothing may clobber authored content
    moves = [(p, paths.CARDS_DIR / p.name) for p in bp["cards"]]
    moves.append((bp["relic"], paths.RELICS_DIR / bp["relic"].name))
    moves.append((f, paths.CHARACTERS_DIR / f.name))
    clobbers = [str(dest) for _, dest in moves if dest.exists()]
    if clobbers:
        print("refusing to promote -- would overwrite existing content:", file=sys.stderr)
        for c in clobbers:
            print(f"  - {c}", file=sys.stderr)
        return 1

    # 3. move the whole bundle
    for src, dest in moves:
        dest.write_text(src.read_text())
        src.unlink()
        src.with_name(src.stem + ".meta.json").unlink(missing_ok=True)
    print(f"promoted class '{ch['id']}' ({ch.get('name')}) -> data/characters/ "
          f"with {len(bp['cards'])} cards + relic '{meta.get('relic')}'")
    print("It is a permanent class on the next ContentDB load (restart/replay the scene).")
    return 0


def _cmd_reject(args) -> int:
    f = paths.GENERATED_CHARACTERS_DIR / f"{args.id}.json"
    if not f.exists():
        print(f"no quarantined class '{args.id}'", file=sys.stderr)
        return 1
    ch = json.loads(f.read_text())
    meta_f = paths.GENERATED_CHARACTERS_DIR / f"{args.id}.meta.json"
    meta = json.loads(meta_f.read_text()) if meta_f.exists() else {}
    bp = _bundle_paths(ch, meta)
    removed = 0
    for p in bp["cards"] + [bp["relic"], bp["character"]]:
        if p.exists():
            p.unlink()
            removed += 1
        p.with_name(p.stem + ".meta.json").unlink(missing_ok=True)
    meta_f.unlink(missing_ok=True)
    print(f"rejected '{args.id}': removed {removed} artifact(s) from quarantine")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Review LLM-quarantined class bundles.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list", help="list quarantined class bundles")
    sp = sub.add_parser("show", help="print one bundle (character + cards + relic)"); sp.add_argument("id")
    sp = sub.add_parser("approve", help="promote the whole bundle into data/"); sp.add_argument("id")
    sp = sub.add_parser("reject", help="delete the whole bundle from quarantine"); sp.add_argument("id")
    args = ap.parse_args(argv)
    return {"list": _cmd_list, "show": _cmd_show, "approve": _cmd_approve, "reject": _cmd_reject}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
