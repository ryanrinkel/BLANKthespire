"""btsgen-census <paths...> — print the creative-breadth census of forged classes.

Each path is a `.btsc.txt`/`.json` code, a bundle JSON, or a directory of them. Prints a per-class table
plus the aggregate block. Run it over `scratch/overnight-2026-07-06/codes/` to reproduce the §1 baseline
(see btsgen/census.py's module docstring).

    uv run btsgen-census scratch/overnight-2026-07-06/codes/
    uv run btsgen-census scratch/breadth-sweep/*.btsc.txt
"""
from __future__ import annotations

import sys

from . import census


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv:
        print(__doc__)
        return 2
    named: list[tuple[str, census.Census]] = []
    for path in argv:
        for name, bundle in census.load_path(path):
            named.append((name, census.census_bundle(bundle)))
    if not named:
        print("# no decodable classes found")
        return 1
    print(census.format_report(named))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
