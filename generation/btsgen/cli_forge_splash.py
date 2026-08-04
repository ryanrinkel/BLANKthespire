"""CLI: generate a forged class's art from its already-quarantined files (separate from forging).

Reads <id>.json (+ <id>.meta.json) the character pipeline wrote and drops <id>.splash.<ext> /
<id>.sprite.<ext> beside them. Default backend is 'null' (does nothing) — pass --backend procedural
for a zero-cost placeholder, or a cloud backend once one is wired.

    uv run btsgen-forge-splash <class_id> --backend procedural            # the select-screen splash
    uv run btsgen-forge-splash <class_id> --kind sprite --backend openai  # the standing combat sprite
    uv run btsgen-forge-splash <class_id> --kind both --backend openai
"""
from __future__ import annotations

import argparse

from .art import class_art_from_disk, forge_splash, forge_sprite


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Generate a forged class's art (splash and/or combat sprite; decoupled from forging).")
    ap.add_argument("class_id", help="the forged class id (matches <id>.json in the characters dir)")
    ap.add_argument("--kind", choices=("splash", "sprite", "both"), default="splash",
                    help="which asset(s) to generate (default: splash)")
    ap.add_argument("--backend", default=None,
                    help="image backend name (default: $BTSGEN_IMAGE_BACKEND, else 'null'). Try 'procedural'.")
    ap.add_argument("--out-dir", default=None,
                    help="output dir for the art (default: the generated-characters quarantine)")
    ap.add_argument("--characters-dir", default=None,
                    help="where to read <id>.json (default: same quarantine)")
    args = ap.parse_args(argv)

    try:
        art = class_art_from_disk(args.class_id, characters_dir=args.characters_dir)
    except FileNotFoundError:
        print(f"ERROR: no character '{args.class_id}' found (looked for {args.class_id}.json).")
        return 2

    forges = {"splash": [forge_splash], "sprite": [forge_sprite], "both": [forge_splash, forge_sprite]}
    rc = 0
    for forge in forges[args.kind]:
        res = forge(art, backend=args.backend, out_dir=args.out_dir, on_event=print)
        if res.ok:
            print(f"OK [{res.backend}] -> {res.path} ({res.width}x{res.height})")
        else:
            print(f"FAIL [{res.backend}]: {res.error}")
            rc = 1
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
