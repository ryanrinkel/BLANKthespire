"""CLI: generate a WHOLE CLASS (character + card set + starter relic) into quarantine.

    uv run btsgen-character-generate --concept "a frost mage that freezes enemies solid"

This is the most expensive command in the harness: one blueprint call plus one call per
card/relic (a default class is ~13 calls). Needs ANTHROPIC_API_KEY (generation/.env or env).
`--fake` swaps in the offline deterministic generator — no key, no cost — which exercises
the identical validate/quarantine/review path (used by tests and the in-game smoke flow).

On success the LAST line printed is `BUNDLE <class_id>` — a machine-readable handle the
in-game forge parses. Review/promote with `uv run btsgen-character-review`.
"""
from __future__ import annotations

import argparse
import sys

from .character_contract import Brief
from .character_pipeline import generate_character


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Generate a whole BLANK the spire class (LLM, validated, quarantined).")
    ap.add_argument("--concept", required=True, help="free-text player concept for the class")
    ap.add_argument("--model", default=None, help="override the model id")
    ap.add_argument("--pool-cards", type=int, default=4, help="reward-pool cards per archetype (default 4)")
    ap.add_argument("--fake", action="store_true", help="offline deterministic generator (no API key/cost)")
    args = ap.parse_args(argv)

    concept = args.concept.strip()
    if not concept:
        print("--concept must not be empty", file=sys.stderr)
        return 1

    brief = Brief(concept=concept, pool_cards_per_archetype=args.pool_cards)
    res = generate_character(brief, model=args.model, fake=args.fake, on_event=print)

    if not res.ok:
        print("FAILED: the class bundle was not generated (see log above)", file=sys.stderr)
        return 1

    ch = res.character
    print(f"\nOK  {ch['name']} ({ch['id']})  hp {ch['max_hp']}  deck {len(ch['starting_deck'])} cards"
          f"  set {len(res.card_ids)} cards  relic '{res.relic_id}'")
    for what, warns in res.warnings.items():
        for w in warns:
            print(f"  WARN [{what}] {w}")
    if res.skipped:
        print(f"  skipped pool card(s): {', '.join(res.skipped)}")

    # Orthogonal art step (splash + combat sprite) — same as the web forge does. Respects
    # BTSGEN_IMAGE_BACKEND (unset -> 'null' -> no-op, so --fake / keyless runs never hit an image API);
    # best-effort, never changes the exit status. Kept BEFORE the machine-read BUNDLE line (stays last).
    from .art import forge_splash, forge_sprite
    art_source = {"character": res.character, "blueprint": res.blueprint, "concept": concept}
    for kind, forge in (("splash", forge_splash), ("sprite", forge_sprite)):
        ares = forge(art_source, on_event=print)
        if ares.ok:
            print(f"  {kind} [{ares.backend}] -> {ares.path}"
                  + (f" (~${ares.cost_usd:.3f})" if ares.cost_usd else ""))

    print(f"\nReview with:  uv run btsgen-character-review list")
    print(f"BUNDLE {ch['id']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
