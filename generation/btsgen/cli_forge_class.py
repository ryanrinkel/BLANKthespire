"""CLI: forge a whole CLASS -> a BTSC import code (the command behind the P3 website's generate endpoint).

    uv run btsgen-forge-class --concept "a frost mage who freezes then shatters" --fake   # offline, no key
    uv run btsgen-forge-class --concept "..."                    # DEFAULT: Ollama-Cloud mixture (OLLAMA_API_KEY in .env)
    uv run btsgen-forge-class --concept "..." --anthropic        # force the Anthropic path (ANTHROPIC key in .env)
    uv run btsgen-forge-class --concept "..." --base-url https://api.openai.com/v1 \
        --api-key sk-... --model gpt-4o                                                     # BYOK (any OpenAI-compatible)

--staged runs the associative creative front-end (cloud->cluster->map->compose->relic-intent) instead of the
single one-shot blueprint call — more creative, same downstream safety (the bp it produces is identical). It is
autonomous by default (picks the most distinctive BUILDABLE candidate); --checkpoint asks you to pick.

Staged forges build a three-archetype TRIAD class by default (graduated 2026-08-17); --pair opts back into
the classic two-archetype flow (--triad is the explicit no-op complement). The one-shot path is always a
classic pair — triad lives in the staged front-end.

On success it writes a `.btsc.txt` code file (hand it to the importer / paste it in-game) and prints a summary.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

from .class_forge import (ClassBrief, REPO, _BlueprintContract, _CardFake, _RelicContract, forge_class,
                          point_btsgen_at_mod_contract, triad_enabled)


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
    tri = ap.add_mutually_exclusive_group()
    tri.add_argument("--triad", action="store_true",
                     help="three-archetype triad class (the default; explicit no-op for clarity)")
    tri.add_argument("--pair", action="store_true",
                     help="opt out of the triad default: forge a classic TWO-archetype class")
    ap.add_argument("--base-url", default=None, help="OpenAI-compatible base URL (BYOK)")
    ap.add_argument("--api-key", default=None, help="API key for the BYOK endpoint")
    ap.add_argument("--model", default=None, help="model id (BYOK, or override the Anthropic model)")
    ap.add_argument("--ollama", action="store_true",
                    help="Ollama-Cloud path: per-role model mixture (needs OLLAMA_API_KEY); implies --staged. "
                         "This is the DEFAULT when OLLAMA_API_KEY is set and no other backend is chosen.")
    ap.add_argument("--ollama-config", default=None,
                    help="with the ollama path: role map JSON (see ollama_roles.example.json)")
    ap.add_argument("--anthropic", action="store_true",
                    help="force the Anthropic (Claude) path even when OLLAMA_API_KEY is set")
    ap.add_argument("--out", default=None, help="output .btsc.txt path (default: scratch/<name>.btsc.txt)")
    args = ap.parse_args(argv)

    point_btsgen_at_mod_contract()

    # Default backend (release): the Ollama-Cloud mixture, whenever its key is available and the user didn't
    # explicitly pick another path. --anthropic / --fake / BYOK flags all opt out.
    if not (args.fake or args.ollama or args.anthropic or args.base_url or args.api_key):
        from .generator import load_env
        load_env()
        if os.environ.get("OLLAMA_API_KEY"):
            args.ollama = True

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
        # One-shot blueprint contract pinned to the classic 2-archetype mode (triad lives in the staged front-end).
        blueprint_gen = OpenAICompatGenerator(args.base_url, args.api_key, args.model,
                                              contract_mod=_BlueprintContract(triad=False), max_tokens=8000)
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
            blueprint_gen = AnthropicGenerator(model=args.model, contract_mod=_BlueprintContract(triad=False), max_tokens=48000)
            relic_gen = AnthropicGenerator(model=args.model, contract_mod=_RelicContract(), max_tokens=6000)
        except RuntimeError as e:
            print(f"ERROR: {e}\n(Use --fake to run without a key, or pass --base-url/--api-key/--model.)", file=sys.stderr)
            return 2
        card_gen_factory = lambda: AnthropicGenerator(model=args.model)  # noqa: E731
        make_gen = lambda contract_mod, *, max_tokens: AnthropicGenerator(  # noqa: E731
            model=args.model, contract_mod=contract_mod, max_tokens=max_tokens)

    # Triad is the DEFAULT (graduated 2026-08-17): --pair opts out, --triad is the explicit no-op complement,
    # no flag reads the env (triad_enabled; BTS_TRIAD=0 is the kill-switch). Triad lives in the staged
    # front-end — the one-shot path (contracts pinned triad=False above) stays a classic 2-archetype forge.
    triad_flag = False if args.pair else (True if args.triad else None)
    is_triad = triad_enabled(triad_flag) and bool(args.staged)
    if triad_enabled(triad_flag) and not args.staged:
        print("note: the one-shot path has no triad prompt — forging a classic 2-archetype class "
              "(add --staged for a triad).")

    # Opt into the staged creative front-end (CLI-first, autonomous by default).
    front_end = None
    if args.staged:
        from .frontend import BlueprintBuilder, append_vocab_gaps, load_catalog
        auto = not args.checkpoint
        front_end = BlueprintBuilder(make_gen, catalog=load_catalog(), on_event=lambda m: print(f"  {m}"),
                                     auto=auto, checkpoint=None if auto else _stdin_checkpoint,
                                     gap_log_append=append_vocab_gaps, triad=is_triad)

    brief = ClassBrief(concept=args.concept, pool_cards_per_archetype=args.pool_per_archetype)
    staged_tag = "  [STAGED · TRIAD]" if is_triad else "  [STAGED · PAIR]"
    mode = "  [FAKE]" if args.fake else (staged_tag if args.staged else "")
    print(f"forging class: {brief.concept!r}{mode}")
    # When --staged, the front-end branch must run (fake=True would short-circuit it); offline-ness lives in the
    # fake make_gen/_CardFake instead. So only pass fake=True on the NON-staged path.
    from .frontend import append_vocab_gaps as _card_gap_sink  # card-stage vocab-demand capture (same file)
    res = forge_class(brief, blueprint_gen=blueprint_gen, card_gen_factory=card_gen_factory,
                      relic_gen=relic_gen, fake=(args.fake and front_end is None), front_end=front_end,
                      triad=is_triad, gap_log_append=None if args.fake else _card_gap_sink)
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
