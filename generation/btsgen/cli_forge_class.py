"""CLI: forge a whole CLASS -> a BTSC import code (the command behind the P3 website's generate endpoint).

    uv run btsgen-forge-class --concept "a frost mage who freezes then shatters" --fake   # offline, no key
    uv run btsgen-forge-class --concept "..."                                              # our Anthropic key (.env)
    uv run btsgen-forge-class --concept "..." --staged                                     # staged creative front-end
    uv run btsgen-forge-class --concept "..." --base-url https://api.openai.com/v1 \
        --api-key sk-... --model gpt-4o                                                     # BYOK (any OpenAI-compatible)

--staged runs the associative creative front-end (cloud->cluster->map->compose->relic-intent) instead of the
single one-shot blueprint call — more creative, same downstream safety (the bp it produces is identical). It is
autonomous by default (picks the most distinctive BUILDABLE candidate); --checkpoint asks you to pick.

On success it writes a `.btsc.txt` code file (hand it to the importer / paste it in-game) and prints a summary.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from .class_forge import (ClassBrief, REPO, _BlueprintContract, _CardFake, _RelicContract, forge_class,
                          point_btsgen_at_mod_contract)


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_") or "class"


def _stdin_checkpoint(candidates, dossier):
    """Interactive candidate pick (only used with --checkpoint). Reads a number from stdin."""
    print("\nFront-end composed these candidate classes:")
    for i, c in enumerate(candidates, 1):
        print(f"  [{i}] " + c.preview().replace("\n", "\n      "))
    while True:
        sel = input(f"Pick a candidate [1-{len(candidates)}]: ").strip()
        if sel.isdigit() and 1 <= int(sel) <= len(candidates):
            return candidates[int(sel) - 1]
        print("  (enter a valid number)")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Forge a whole playable class via the LLM loop -> a BTSC code.")
    ap.add_argument("--concept", required=True, help="the class concept, free text")
    ap.add_argument("--pool-per-archetype", type=int, default=4, help="pool cards per archetype")
    ap.add_argument("--fake", action="store_true", help="offline fake generator (no API key)")
    ap.add_argument("--staged", action="store_true",
                    help="run the staged creative front-end (cloud->cluster->map->compose->relic-intent)")
    ap.add_argument("--checkpoint", action="store_true",
                    help="with --staged: pause to pick a candidate (default: autonomous)")
    ap.add_argument("--auto", action="store_true",
                    help="with --staged: autonomous candidate pick (the default; explicit no-op for clarity)")
    ap.add_argument("--base-url", default=None, help="OpenAI-compatible base URL (BYOK)")
    ap.add_argument("--api-key", default=None, help="API key for the BYOK endpoint")
    ap.add_argument("--model", default=None, help="model id (BYOK, or override the Anthropic model)")
    ap.add_argument("--ollama", action="store_true",
                    help="parallel Ollama-Cloud path: per-role model mixture (needs OLLAMA_API_KEY); implies --staged")
    ap.add_argument("--ollama-config", default=None,
                    help="with --ollama: path to a role map JSON (see ollama_roles.example.json)")
    ap.add_argument("--out", default=None, help="output .btsc.txt path (default: scratch/<name>.btsc.txt)")
    args = ap.parse_args(argv)

    point_btsgen_at_mod_contract()

    # Build (a) the one-shot blueprint generator + relic generator + card-generator factory AND (b) a `make_gen`
    # closure the staged front-end uses to spin up a generator for any stage (same backend, swapped contract).
    if args.fake:
        from .frontend.fakes import _StageFake
        blueprint_gen = None
        relic_gen = None
        card_gen_factory = lambda: _CardFake()  # noqa: E731
        make_gen = lambda contract_mod, *, max_tokens: _StageFake(contract_mod)  # noqa: E731
    elif args.ollama:
        # Parallel Ollama-Cloud path: a per-role model mixture (brainstorm on a small/permissive model, cards
        # coded by a strong model). Same generator tuple as every other backend, so downstream is untouched.
        from . import ollama_mix
        role_map = ollama_mix.load_role_map(args.ollama_config) if args.ollama_config else None
        try:
            blueprint_gen, card_gen_factory, relic_gen, make_gen = ollama_mix.build_ollama_mix(role_map)
        except RuntimeError as e:
            print(f"ERROR: {e}", file=sys.stderr)
            return 2
        args.staged = True  # the Ollama mixture only makes sense through the staged creative front-end
        print("ollama mix:\n" + ollama_mix.describe(role_map))
    elif args.base_url or args.api_key:
        if not (args.base_url and args.api_key and args.model):
            print("ERROR: BYOK needs --base-url, --api-key, and --model together.", file=sys.stderr)
            return 2
        from . import contract
        from .generator import OpenAICompatGenerator
        blueprint_gen = OpenAICompatGenerator(args.base_url, args.api_key, args.model,
                                              contract_mod=_BlueprintContract(), max_tokens=8000)
        relic_gen = OpenAICompatGenerator(args.base_url, args.api_key, args.model,
                                          contract_mod=_RelicContract(), max_tokens=4000)
        card_gen_factory = lambda: OpenAICompatGenerator(  # noqa: E731
            args.base_url, args.api_key, args.model, contract_mod=contract, max_tokens=4000)
        # 300s (vs the 180s default), matching the Ollama path: the front-end's heavy stages (map/compose,
        # reframed blueprint) can sit a long time before the first streamed chunk when the provider is loaded.
        make_gen = lambda contract_mod, *, max_tokens: OpenAICompatGenerator(  # noqa: E731
            args.base_url, args.api_key, args.model, contract_mod=contract_mod, max_tokens=max_tokens,
            timeout=300)
    else:
        from .generator import AnthropicGenerator
        try:
            # 48000: headroom for adaptive thinking + full-blueprint repair (one shared budget; truncation
            # there yields unparseable JSON). Under every current Claude output cap (Haiku/Sonnet 64K, Opus 128K).
            blueprint_gen = AnthropicGenerator(model=args.model, contract_mod=_BlueprintContract(), max_tokens=48000)
            relic_gen = AnthropicGenerator(model=args.model, contract_mod=_RelicContract(), max_tokens=6000)
        except RuntimeError as e:
            print(f"ERROR: {e}\n(Use --fake to run without a key, or pass --base-url/--api-key/--model.)", file=sys.stderr)
            return 2
        card_gen_factory = lambda: AnthropicGenerator(model=args.model)  # noqa: E731
        make_gen = lambda contract_mod, *, max_tokens: AnthropicGenerator(  # noqa: E731
            model=args.model, contract_mod=contract_mod, max_tokens=max_tokens)

    # Opt into the staged creative front-end (CLI-first, autonomous by default).
    front_end = None
    if args.staged:
        from .frontend import BlueprintBuilder, append_vocab_gaps, load_catalog
        auto = not args.checkpoint
        front_end = BlueprintBuilder(make_gen, catalog=load_catalog(), on_event=lambda m: print(f"  {m}"),
                                     auto=auto, checkpoint=None if auto else _stdin_checkpoint,
                                     gap_log_append=append_vocab_gaps)

    brief = ClassBrief(concept=args.concept, pool_cards_per_archetype=args.pool_per_archetype)
    mode = "  [FAKE]" if args.fake else ("  [STAGED]" if args.staged else "")
    print(f"forging class: {brief.concept!r}{mode}")
    # When --staged, the front-end branch must run (fake=True would short-circuit it); offline-ness lives in the
    # fake make_gen/_CardFake instead. So only pass fake=True on the NON-staged path.
    res = forge_class(brief, blueprint_gen=blueprint_gen, card_gen_factory=card_gen_factory,
                      relic_gen=relic_gen, fake=(args.fake and front_end is None), front_end=front_end)
    for line in res.log:
        print(f"  {line}")
    if not res.ok or res.bundle is None:
        print("FAILED — class did not generate.", file=sys.stderr)
        return 1

    from .bts1 import encode_class
    bundle_text = json.dumps(res.bundle, separators=(",", ":"))
    code = encode_class(bundle_text)

    name = res.bundle["character"]["name"]
    out = Path(args.out) if args.out else (REPO / "generation" / "scratch" / f"{_slug(name)}.btsc.txt")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(code, encoding="utf-8")

    cards = res.bundle["cards"]
    deck = sum(d["count"] for d in res.bundle["character"]["starting_deck"])
    print(f"\n[OK] Forged class '{name}': {len(cards)} cards, {deck}-card starting deck.")
    from .class_forge import archetype_display
    archs = archetype_display(res.blueprint)
    if archs:
        print("   built around: " + "; ".join(
            (a["title"] or a["name"] or a["id"]) + (f" — {a['pitch'] or a['description']}"
                                                    if (a["pitch"] or a["description"]) else "")
            for a in archs))
    if res.skipped:
        print(f"   (skipped {len(res.skipped)} card brief(s): {', '.join(res.skipped)})")
    print(f"   BTSC code ({len(code)} chars) -> {out}")
    print("   Paste it in-game: mod settings -> Import a class code -> Import -> Restart.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
