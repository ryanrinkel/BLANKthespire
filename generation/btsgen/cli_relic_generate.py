"""CLI: generate one relic and quarantine it (parallel to cli_generate.py).

    uv run btsgen-relic-generate --tier common --pool combat --theme "reward blocking"

Offline parts (validator) need no key; this command makes a live Anthropic call and so needs
ANTHROPIC_API_KEY (generation/.env or env). The relic lands in data/generated/relics/ tagged
source:"llm" -- NOT in the reward pool until you approve it with `btsgen-relic-review approve <id>`.
"""
from __future__ import annotations

import argparse
import sys

from . import relic_contract
from .relic_contract import Brief
from .relic_pipeline import generate_relic


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Generate one BLANK the spire relic (LLM, validated, quarantined).")
    ap.add_argument("--tier", default="common", choices=["common", "uncommon", "rare", "boss"])
    ap.add_argument("--pool", default="combat", choices=["combat", "elite", "boss", "shop"])
    ap.add_argument("--theme", default="", help="free-text design nudge")
    ap.add_argument("--model", default=None, help="override the model id")
    ap.add_argument("-n", "--count", type=int, default=1, help="how many relics to generate")
    args = ap.parse_args(argv)

    brief = Brief(tier=args.tier, pool=args.pool, theme=args.theme)

    # Build the generator/validator once and reuse across n relics (caches the system prompt).
    from .generator import AnthropicGenerator
    from .relic_validator import RelicValidator
    gen = AnthropicGenerator(model=args.model, contract_mod=relic_contract)
    validator = RelicValidator()

    failures = 0
    for i in range(args.count):
        if args.count > 1:
            print(f"\n=== relic {i + 1}/{args.count} ===")
        res = generate_relic(brief, gen=gen, validator=validator)
        for line in res.log:
            print(f"  {line}")
        if res.ok:
            r = res.result
            print(f"  OK  id={res.relic['id']!r}  power~{r.score:.1f}  attempts={res.attempts}"
                  + ("  (repaired)" if res.repaired else ""))
            for w in r.warnings:
                print(f"  WARN  {w}")
            print(f"  -> {res.quarantine_path}")
        else:
            failures += 1
            print(f"  FAILED after {res.attempts} attempt(s)")
            if res.result and res.result.errors:
                for e in res.result.errors:
                    print(f"    - {e}")

    if not failures:
        print(f"\nReview with:  uv run btsgen-relic-review list")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
