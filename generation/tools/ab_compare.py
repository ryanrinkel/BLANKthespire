"""A/B the creative harness: forge the SAME concept twice — once all-Anthropic (the current path), once via
the Ollama-Cloud per-role mixture — and write a side-by-side report to generation/scratch/ab_<slug>.md.

    cd generation
    uv run python tools/ab_compare.py --concept "a frost mage who freezes then shatters"
    uv run python tools/ab_compare.py --concept "..." --ollama-config ollama_roles.json --only ollama

Both legs run the STAGED creative front-end (cloud->cluster->map->compose->relic-intent->blueprint) so the
only variable is the backend. We capture per-leg wall-clock, token usage, repair churn, final card count,
skipped briefs, and the BTSC code (paste either in-game to compare feel). Cost is token-based; edit PRICES
below with current per-million rates (Anthropic) — Ollama Cloud bills on its own plan, shown as tokens.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

from btsgen.class_forge import (REPO, ClassBrief, _BlueprintContract, _RelicContract, forge_class,
                                point_btsgen_at_mod_contract)

# Approximate per-MILLION-token prices (USD). EDIT to match current rates; Ollama Cloud is plan-based, so we
# leave it at 0 and report raw tokens instead. Used only for the headline $ estimate in the report.
PRICES = {
    "claude-opus-4-8": {"in": 5.0, "out": 25.0},  # approximate — confirm against the console
}


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_") or "concept"


_RARITY_ORDER = {"basic": 0, "common": 1, "uncommon": 2, "rare": 3}


def _card_row(c: dict) -> dict:
    """Pull the comparable fields off a finished bundle card (name/type/rarity/cost + a short text/effect blurb)."""
    text = c.get("text") or c.get("description") or ""
    if not text:  # fall back to a terse op summary so cards are still comparable
        ops = [str(e.get("op", "")) for e in (c.get("effects") or []) if isinstance(e, dict)]
        text = " · ".join(o for o in ops if o)
    return {"name": c.get("name", "?"), "type": c.get("type", "?"), "rarity": c.get("rarity", "?"),
            "cost": c.get("cost", "?"), "text": text}


def _render_card_list(o: dict) -> str:
    if not o["card_list"]:
        return f"### {o['name']} — cards\n\n_(no cards — leg {('failed' if not o['ok'] else 'empty')})_\n"
    rows = sorted(o["card_list"], key=lambda r: (_RARITY_ORDER.get(r["rarity"], 9), str(r["name"]).lower()))
    head = (f"### {o['name']} — {o['class_name']} ({o['max_hp']} HP, {len(rows)} cards"
            f"{', relic: ' + o['relic'] if o['relic'] else ''})\n\n"
            "| # | card | type | rarity | cost | text / effects |\n"
            "|---|------|------|--------|------|----------------|\n")
    lines = []
    for i, r in enumerate(rows, 1):
        txt = str(r["text"]).replace("|", "/")[:90]
        lines.append(f"| {i} | {r['name']} | {r['type']} | {r['rarity']} | {r['cost']} | {txt} |")
    return head + "\n".join(lines) + "\n"


def _cost(model: str, tin: int, tout: int) -> float | None:
    p = PRICES.get(model)
    return None if not p else (tin / 1e6) * p["in"] + (tout / 1e6) * p["out"]


def _run_leg(name: str, build_generators, brief) -> dict:
    """build_generators() -> (blueprint_gen, card_factory, relic_gen, make_gen). Runs the staged forge and
    returns a result dict (never raises — a failed leg is reported, not fatal, so the other leg still lands)."""
    from btsgen.frontend import BlueprintBuilder, load_catalog

    log: list[str] = []
    usage: list[tuple[int, int]] = []  # (input_tokens, output_tokens) per call
    out = {"name": name, "ok": False, "error": None, "log": log, "seconds": 0.0,
           "in_tokens": 0, "out_tokens": 0, "calls": 0, "repairs": 0,
           "cards": 0, "skipped": [], "code": None, "model_label": "", "class_name": None,
           "card_list": [], "relic": None, "max_hp": None}
    t0 = time.perf_counter()
    try:
        bp_gen, card_factory, relic_gen, make_gen, model_label = build_generators(usage)
        out["model_label"] = model_label
        fe = BlueprintBuilder(make_gen, catalog=load_catalog(), on_event=log.append, auto=True)
        res = forge_class(brief, blueprint_gen=bp_gen, card_gen_factory=card_factory,
                          relic_gen=relic_gen, front_end=fe, on_event=log.append)
        if not res.ok or res.bundle is None:
            out["error"] = res.log[-1] if res.log else "no result"
        else:
            from btsgen.bts1 import encode_class
            out["ok"] = True
            out["class_name"] = res.bundle["character"]["name"]
            out["max_hp"] = res.bundle["character"].get("max_hp")
            out["cards"] = len(res.bundle["cards"])
            out["card_list"] = [_card_row(c) for c in res.bundle["cards"]]
            rel = res.bundle.get("relic")
            out["relic"] = rel.get("name") if isinstance(rel, dict) else None
            out["skipped"] = list(res.skipped or [])
            out["code"] = encode_class(json.dumps(res.bundle, separators=(",", ":")))
    except Exception as e:  # noqa: BLE001 — one leg failing must not sink the comparison
        out["error"] = f"{type(e).__name__}: {e}"
    out["seconds"] = round(time.perf_counter() - t0, 1)
    out["calls"] = len(usage)
    out["in_tokens"] = sum(u[0] for u in usage)
    out["out_tokens"] = sum(u[1] for u in usage)
    out["repairs"] = sum(1 for ln in log if "repair" in ln.lower())
    return out


def _anthropic_builder(model: str):
    def build(usage: list):
        from btsgen import contract
        from btsgen.generator import DEFAULT_MODEL, AnthropicGenerator, load_env
        load_env()
        import os
        resolved = model or os.environ.get("BTSGEN_MODEL", DEFAULT_MODEL)  # so the cost lookup + label are real
        on_usage = lambda u: usage.append((getattr(u, "input_tokens", 0), getattr(u, "output_tokens", 0)))  # noqa: E731
        # One-shot blueprint contract pinned to the classic 2-archetype mode (triad lives in the staged front-end).
        bp = AnthropicGenerator(model=resolved, contract_mod=_BlueprintContract(triad=False), max_tokens=48000, on_usage=on_usage)
        relic = AnthropicGenerator(model=resolved, contract_mod=_RelicContract(), max_tokens=6000, on_usage=on_usage)
        card_factory = lambda: AnthropicGenerator(model=resolved, on_usage=on_usage)  # noqa: E731
        make_gen = lambda cm, *, max_tokens: AnthropicGenerator(  # noqa: E731
            model=resolved, contract_mod=cm, max_tokens=max_tokens, on_usage=on_usage)
        return bp, card_factory, relic, make_gen, resolved
    return build


def _ollama_builder(role_map: dict | None):
    def build(usage: list):
        from btsgen import ollama_mix
        on_usage = lambda u: usage.append((int(u.get("prompt_tokens", 0)), int(u.get("completion_tokens", 0))))  # noqa: E731
        bp, cf, rg, mg = ollama_mix.build_ollama_mix(role_map, on_usage=on_usage)
        return bp, cf, rg, mg, "ollama mix\n" + ollama_mix.describe(role_map)
    return build


def _fmt_leg(o: dict) -> str:
    cost = _cost((o["model_label"] or "").splitlines()[0].strip(), o["in_tokens"], o["out_tokens"]) \
        if o["name"] == "anthropic" else None
    cost_s = f"${cost:.3f}" if cost is not None else "(plan-based / n/a)"
    status = "OK" if o["ok"] else f"FAILED — {o['error']}"
    return (
        f"### {o['name']}\n\n"
        f"- **status:** {status}\n"
        f"- **models:** {o['model_label']}\n"
        f"- **wall-clock:** {o['seconds']}s\n"
        f"- **LLM calls:** {o['calls']}  (**repairs:** {o['repairs']})\n"
        f"- **tokens:** {o['in_tokens']:,} in / {o['out_tokens']:,} out  → est. cost {cost_s}\n"
        f"- **class:** {o['class_name'] or '—'}  |  **cards:** {o['cards']}  |  "
        f"**skipped briefs:** {', '.join(o['skipped']) or 'none'}\n"
    )


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="A/B the creative harness: Anthropic vs Ollama-mix on one concept.")
    ap.add_argument("--concept", required=True, help="the class concept, free text")
    ap.add_argument("--pool-per-archetype", type=int, default=4)
    ap.add_argument("--anthropic-model", default=None, help="override the Anthropic model (default: .env / opus)")
    ap.add_argument("--ollama-config", default=None, help="role map JSON (default: built-in mix)")
    ap.add_argument("--only", choices=["anthropic", "ollama"], default=None, help="run just one leg")
    ap.add_argument("--out", default=None, help="report path (default: scratch/ab_<slug>.md)")
    args = ap.parse_args(argv)

    point_btsgen_at_mod_contract()
    brief = ClassBrief(concept=args.concept, pool_cards_per_archetype=max(2, args.pool_per_archetype))
    role_map = None
    if args.ollama_config:
        from btsgen import ollama_mix
        role_map = ollama_mix.load_role_map(args.ollama_config)

    legs: list[dict] = []
    if args.only != "ollama":
        print("=== leg: anthropic ===")
        legs.append(_run_leg("anthropic", _anthropic_builder(args.anthropic_model), brief))
    if args.only != "anthropic":
        print("=== leg: ollama ===")
        legs.append(_run_leg("ollama", _ollama_builder(role_map), brief))

    report = [f"# A/B forge — {args.concept!r}\n", "## Summary\n"]
    report.append("| leg | status | secs | calls | repairs | tokens(out) | cards |")
    report.append("|-----|--------|------|-------|---------|-------------|-------|")
    for o in legs:
        report.append(f"| {o['name']} | {'OK' if o['ok'] else 'FAIL'} | {o['seconds']} | {o['calls']} | "
                      f"{o['repairs']} | {o['out_tokens']:,} | {o['cards']} |")
    report.append("")
    for o in legs:
        report.append(_fmt_leg(o))
    report.append("\n## Card lists\n")
    for o in legs:
        report.append(_render_card_list(o))
    for o in legs:
        report.append(f"\n## {o['name']} — progress log\n\n```\n" + "\n".join(o["log"]) + "\n```\n")
        if o["code"]:
            report.append(f"## {o['name']} — BTSC code (paste in-game)\n\n```\n{o['code']}\n```\n")

    out = Path(args.out) if args.out else (REPO / "generation" / "scratch" / f"ab_{_slug(args.concept)}.md")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(report), encoding="utf-8")
    print(f"\n[OK] wrote {out}")
    for o in legs:
        print(f"  {o['name']:9s} {'OK ' if o['ok'] else 'FAIL'} {o['seconds']}s  "
              f"{o['calls']} calls / {o['repairs']} repairs  {o['out_tokens']:,} out-tok  {o['cards']} cards")
    return 0


if __name__ == "__main__":
    sys.exit(main())
