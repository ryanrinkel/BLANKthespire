"""CLI: generate one card and quarantine it.

    uv run btsgen-generate --type attack --rarity common --cost 1 --theme "block-and-counter"

Offline parts (validator) need no key; this command makes a live Anthropic call and
so needs ANTHROPIC_API_KEY (generation/.env or env). The card lands in
data/generated/cards/ tagged source:"llm" — NOT in the reward pool until you approve it
with `btsgen-review approve <id>`.
"""
from __future__ import annotations

import argparse
import sys

from .contract import Brief
from .pipeline import generate_card


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Generate one BLANK the spire card (LLM, validated, quarantined).")
    ap.add_argument("--type", dest="card_type", default="attack",
                    choices=["attack", "skill", "power"])
    ap.add_argument("--rarity", default="common",
                    choices=["basic", "common", "uncommon", "rare"])
    ap.add_argument("--cost", type=int, default=None, help="target energy cost (omit to let the model choose)")
    ap.add_argument("--theme", default="", help="free-text design nudge")
    ap.add_argument("--model", default=None, help="override the model id")
    ap.add_argument("-n", "--count", type=int, default=1, help="how many cards to generate")
    args = ap.parse_args(argv)

    brief = Brief(card_type=args.card_type, rarity=args.rarity, target_cost=args.cost, theme=args.theme)

    # Build the generator/validator once and reuse across n cards (caches the system prompt).
    from .generator import AnthropicGenerator
    from .validator import CardValidator
    gen = AnthropicGenerator(model=args.model)
    validator = CardValidator()

    failures = 0
    for i in range(args.count):
        if args.count > 1:
            print(f"\n=== card {i + 1}/{args.count} ===")
        res = generate_card(brief, gen=gen, validator=validator)
        for line in res.log:
            print(f"  {line}")
        if res.ok:
            r = res.result
            print(f"  OK  id={res.card['id']!r}  score={r.score:.1f}  attempts={res.attempts}"
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
        print(f"\nReview with:  uv run btsgen-review list")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
