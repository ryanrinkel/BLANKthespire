"""forge — the end-to-end LLM card loop for the BLANK the spire STS2 mod.

    uv run btsgen-forge --type attack --rarity uncommon --theme "block-and-counter"
    uv run btsgen-forge --theme "a cheap aoe opener" --fake     # no API key, proves the pipeline

One command:  brief -> Anthropic (btsgen, CONSTRAINED to the C# EffectRunner's vocabulary) ->
validate/repair -> write JSON into mod/content/cards/ -> codegen C# (cardgen) -> dotnet build ->
deploy into the game's mods/ folder. Restart STS2 to play the new card.

Why a constrained contract: STS2 cards are compiled C#, and our interpreter only runs a subset of
the prototype vocabulary today (damage/block/draw/apply_status[vulnerable|weak]). We point btsgen's
schema+vocabulary at mod/contract/ so the model can only ever emit cards that are actually playable.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
MOD = REPO / "mod"
CONTRACT = MOD / "contract"
CARDS_DIR = MOD / "content" / "cards"
STAGING = MOD / "content" / "_generated"
GEN_CS = MOD / "BlankTheSpireCode" / "Cards" / "Generated"
LOC = MOD / "BlankTheSpire" / "localization" / "eng" / "cards.json"
CSPROJ = MOD / "BlankTheSpire.csproj"
CARDGEN = REPO / "generation" / "btsgen" / "cardgen.py"


def _point_btsgen_at_mod_contract() -> None:
    """Repoint btsgen's paths at the constrained mod contract. MUST run before importing the
    btsgen modules that read paths at import time."""
    os.environ["BTSGEN_CARD_SCHEMA"] = str(CONTRACT / "card.schema.json")
    os.environ["BTSGEN_VOCABULARY"] = str(CONTRACT / "VOCABULARY.md")
    os.environ["BTSGEN_DESIGN_HEURISTICS"] = str(CONTRACT / "DESIGN_HEURISTICS.md")
    os.environ["BTSGEN_STATUSES_DIR"] = str(CONTRACT / "statuses")
    os.environ["BTSGEN_CARDS_DIR"] = str(CARDS_DIR)
    os.environ["BTSGEN_GENERATED_DIR"] = str(STAGING)


class _SupportedOpFake:
    """A keyless, deterministic stand-in for AnthropicGenerator that emits a card using ONLY the
    supported vocabulary (so --fake exercises the whole loop offline). Same duck-typed surface."""

    model = "fake-offline"

    def __init__(self) -> None:
        self._n = 0

    def first_attempt(self, brief):
        self._n += 1
        cost = brief.target_cost if brief.target_cost is not None else 1
        # A deliberately UNIQUE 3-op skeleton (damage + block + draw) so the fake never trips the
        # validator's functional-reprint gate against the authored pool. Forced to an attack shape;
        # the real model honours brief.card_type.
        card = {
            "id": f"forged_{self._n}",
            "name": f"Forged Card {self._n}",
            "type": "attack",
            "rarity": brief.rarity,
            "cost": max(1, cost),
            "target": "enemy",
            "source": "llm",
            "effects": [{"op": "damage", "amount": 8}, {"op": "block", "amount": 5}, {"op": "draw", "amount": 1}],
            "upgrade": {"effects": [{"op": "damage", "amount": 11}, {"op": "block", "amount": 7}, {"op": "draw", "amount": 1}]},
        }
        text = json.dumps(card, indent=2)
        return text, [{"role": "user", "content": "fake"}, {"role": "assistant", "content": text}]

    def repair(self, messages, prev_text, errors):
        return prev_text, messages  # fakes are valid by construction


def _dotnet_exe() -> str:
    override = os.environ.get("DOTNET_EXE")
    if override:
        return override
    per_user = Path.home() / ".dotnet" / "dotnet.exe"
    return str(per_user) if per_user.exists() else "dotnet"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Forge one playable STS2 card via the LLM loop.")
    ap.add_argument("--type", dest="card_type", default="attack", choices=["attack", "skill", "power"])
    ap.add_argument("--rarity", default="common", choices=["basic", "common", "uncommon", "rare"])
    ap.add_argument("--cost", type=int, default=None, help="target energy cost (omit = model chooses)")
    ap.add_argument("--theme", default="", help="free-text design nudge")
    ap.add_argument("--model", default=None, help="override the model id")
    ap.add_argument("--fake", action="store_true", help="use the offline fake generator (no API key)")
    ap.add_argument("--no-build", action="store_true", help="generate + codegen but skip dotnet build")
    args = ap.parse_args(argv)

    _point_btsgen_at_mod_contract()
    STAGING.mkdir(parents=True, exist_ok=True)

    # Imports AFTER env is set (btsgen reads paths at import).
    from .contract import Brief
    from .pipeline import generate_card
    from .validator import CardValidator

    brief = Brief(card_type=args.card_type, rarity=args.rarity, target_cost=args.cost, theme=args.theme)

    if args.fake:
        gen = _SupportedOpFake()
    else:
        from .generator import AnthropicGenerator
        try:
            gen = AnthropicGenerator(model=args.model)
        except RuntimeError as e:
            print(f"ERROR: {e}\n(Use --fake to run the loop without a key.)", file=sys.stderr)
            return 2

    print(f"forging: {brief.describe()}" + ("  [FAKE]" if args.fake else f"  [{gen.model}]"))
    res = generate_card(brief, gen=gen, validator=CardValidator())
    for line in res.log:
        print(f"  {line}")
    if not res.ok:
        print("FAILED — card did not validate.", file=sys.stderr)
        for e in (res.result.errors if res.result else []):
            print(f"  - {e}", file=sys.stderr)
        return 1

    card_id = res.card["id"]
    for w in (res.result.warnings or []):
        print(f"  WARN  {w}")

    # Promote the validated card from staging into the mod's authored card source.
    dest = CARDS_DIR / f"{card_id}.json"
    shutil.copyfile(res.quarantine_path, dest)
    print(f"  promoted -> {dest.relative_to(REPO)}")

    # Codegen all cards -> C# + localization.
    cg = subprocess.run(
        [sys.executable, str(CARDGEN), "--in", str(CARDS_DIR), "--out-cs", str(GEN_CS), "--out-loc", str(LOC)],
        capture_output=True, text=True,
    )
    print("  " + (cg.stdout.strip().splitlines() or ["cardgen done"])[-1])
    if cg.returncode != 0:
        print(cg.stderr, file=sys.stderr)
        return 1

    if args.no_build:
        print(f"\nDONE (no build). New card: {card_id}. Run dotnet build when ready.")
        return 0

    # Build + deploy.
    env = dict(os.environ, DOTNET_ROOT=str(Path(_dotnet_exe()).parent), DOTNET_CLI_TELEMETRY_OPTOUT="1", DOTNET_NOLOGO="1")
    print("  building...")
    b = subprocess.run([_dotnet_exe(), "build", str(CSPROJ), "-c", "Debug"],
                       capture_output=True, text=True, env=env)
    tail = [l for l in b.stdout.splitlines() if "error" in l.lower() or "Build succeeded" in l or "Build FAILED" in l]
    for l in tail[:12]:
        print("  " + l.strip())
    if b.returncode != 0:
        print("BUILD FAILED.", file=sys.stderr)
        return 1

    print(f"\n[OK] Forged and deployed '{card_id}'. Fully quit Slay the Spire 2 and relaunch to play it.")
    print("   (It joins the reward pool at its rarity; it is NOT auto-added to the starting deck.)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
