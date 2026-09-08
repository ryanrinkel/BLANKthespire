"""btsgen-bench — the creative-harness benchmark (docs/plans/DEPLOYMENT_PLAN.md §2.3). CLI only, no web wiring.

Forges a FIXED list of 12 concept sentences (spanning tone and mechanics) on the token path (the Ollama-Cloud
mixture, staged triad front-end) and reports the plan's metrics table from census.py:

    uv run btsgen-bench --fake                      # offline smoke (fake stages + fake cards; no keys)
    uv run btsgen-bench                             # the real thing (needs OLLAMA_API_KEY; costs cents on glm-5.2)
    uv run btsgen-bench --v2 --out docs/plans/HARNESS_BENCH.md   # under BTS_HARNESS_V2=1, written to a file

Run it once BEFORE touching the harness to lock the baseline, then after each fix. The gate in the plan: v2
becomes the default only when every target is met. Each run uses its OWN ledger file (--ledger, default a
temp file) so the bench never pollutes the production recency window — and so the cold-archetype rotation
sees the bench's own earlier forges, exactly as a run of 12 real forges would.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import os
import sys
import tempfile
from collections import Counter
from pathlib import Path

from . import census
from .class_forge import ClassBrief, _CardFake, forge_class, point_btsgen_at_mod_contract

# The fixed concept set: tone spans grim / whimsical / clinical / heroic; mechanics span attrition, burst, engine,
# summons, orbs, discard, transformation, retain, balance, thinning, tags, and self-damage.
CONCEPTS: list[str] = [
    "a patient duelist who holds then strikes",
    "a plague doctor who trades health for knowledge",
    "a storm-calling gambler who channels luck",
    "a gravekeeper who raises one loyal servant and fights through it",
    "a blacksmith whose signature hammer grows heavier every swing",
    "a monk balancing light and dark who is punished at the extremes",
    "a street magician who burns through cards and conjures copies",
    "a librarian who discards forbidden pages for power",
    "a shapeshifter whose cards permanently become other cards mid-run",
    "a siege engineer who rewards fighting crowds",
    "a glass-cannon sprinter who wins the first three turns or dies",
    "a wandering healer who outlasts everything through regeneration",
]

_BASIC_NAMES = {"strike", "defend"}

# The metric rows (label, target) in the plan's order. Labels are stable — tests key on them.
METRIC_ROWS: list[tuple[str, str]] = [
    ("Distinct archetypes used across forges", ">= 22"),
    ("Any archetype in more than 4 of 12 classes", "none"),
    ("Share of cards with the {damage, apply_status} skeleton", "<= 15%"),
    ("Top status as share of all apply_status uses", "no status above 25%"),
    ("Card names repeated verbatim across classes (excluding Strike/Defend)", "zero"),
    ("First-word name collisions across classes (top word)", "no word above 2"),
    ("Coverage-pass injections per class", "<= 1 average; no mechanic in more than 3 of 12"),
    ("Validator pass rate on first attempt", "not more than 5 points below baseline"),
]


def _build_backends(fake: bool, ollama_config: str | None):
    """(card_gen_factory, relic_gen, make_gen, description) for the bench's backend."""
    if fake:
        from .frontend.fakes import _StageFake
        return (lambda: _CardFake()), None, (lambda cm, *, max_tokens: _StageFake(cm)), "fake-offline"
    from . import ollama_mix
    role_map = ollama_mix.load_role_map(ollama_config) if ollama_config else None
    _bp, card_gen_factory, relic_gen, make_gen = ollama_mix.build_ollama_mix(role_map)
    return card_gen_factory, relic_gen, make_gen, "ollama mix:\n" + ollama_mix.describe(role_map)


def forge_concepts(concepts: list[str], *, fake: bool, ollama_config: str | None = None, triad: bool = True,
                   on_event=None) -> list[dict]:
    """Forge every concept; returns [{concept, name, ok, bundle, blueprint, log, stats}]. A failed forge is
    recorded (ok=False) and the run continues — the bench measures the harness, so a whiff is data."""
    from .frontend import BlueprintBuilder, load_catalog
    card_gen_factory, relic_gen, make_gen, _desc = _build_backends(fake, ollama_config)
    catalog = load_catalog()
    out: list[dict] = []
    for i, concept in enumerate(concepts, 1):
        events: list[str] = []
        sink = (lambda m: (events.append(m), on_event and on_event(m))) if on_event else events.append
        fe = BlueprintBuilder(make_gen, catalog=catalog, on_event=sink, auto=True, gap_log_append=None, triad=triad)
        try:
            res = forge_class(ClassBrief(concept=concept), blueprint_gen=None, card_gen_factory=card_gen_factory,
                              relic_gen=relic_gen, fake=False, front_end=fe, triad=triad, on_event=sink)
        except Exception as e:  # noqa: BLE001 — one dead forge must not kill the bench
            out.append({"concept": concept, "name": "", "ok": False, "bundle": None, "blueprint": None,
                        "log": events + [f"forge raised: {e}"], "stats": {}})
            continue
        out.append({"concept": concept, "name": (res.bundle or {}).get("character", {}).get("name", "") if res.bundle else "",
                    "ok": bool(res.ok and res.bundle), "bundle": res.bundle, "blueprint": res.blueprint,
                    "log": events + list(res.log), "stats": dict(res.stats or {})})
        if on_event:
            on_event(f"[bench] {i}/{len(concepts)} {'ok' if out[-1]['ok'] else 'FAILED'}: {concept}")
    return out


def _pool_cards(bundle: dict) -> list[dict]:
    """The measurable cards of a bundle: everything but the two literal basics and any token."""
    cards = []
    for c in (bundle or {}).get("cards") or []:
        if not isinstance(c, dict) or c.get("token"):
            continue
        if str(c.get("rarity", "")).lower() in ("basic", "token") and str(c.get("name", "")).lower() in _BASIC_NAMES:
            continue
        cards.append(c)
    return cards


def compute_metrics(results: list[dict]) -> dict:
    """The plan's metrics over the forged classes (census.py does the card walking)."""
    ok = [r for r in results if r.get("ok") and r.get("bundle")]
    n = len(ok)
    arch_by_class: list[set] = []
    for r in ok:
        bp = r.get("blueprint") or {}
        ids = bp.get("archetype_ids") or [a.get("id") for a in (bp.get("archetypes") or []) if isinstance(a, dict)]
        arch_by_class.append({str(i) for i in ids if i})
    arch_count = Counter(a for s in arch_by_class for a in s)
    distinct = len(arch_count)
    over4 = sorted(a for a, k in arch_count.items() if k > 4)

    total_cards = 0
    da_skeleton = 0
    statuses: Counter = Counter()
    names: Counter = Counter()          # name -> number of CLASSES it appears in
    first_words: Counter = Counter()    # first word -> number of CLASSES it appears in
    for r in ok:
        cards = _pool_cards(r["bundle"])
        seen_names: set[str] = set()
        seen_first: set[str] = set()
        for c in cards:
            total_cards += 1
            cc = census.walk_card(c)
            if set(cc.ops) == {"damage", "apply_status"}:
                da_skeleton += 1
            statuses.update(cc.statuses)
            nm = str(c.get("name", "")).strip()
            if nm and nm.lower() not in _BASIC_NAMES:
                seen_names.add(nm.lower())
                seen_first.add(nm.split()[0].lower())
        names.update(seen_names)
        first_words.update(seen_first)
    repeats = sorted(nm for nm, k in names.items() if k > 1)
    top_word, top_word_n = (first_words.most_common(1)[0] if first_words else ("", 0))
    status_total = sum(statuses.values())
    top_status, top_status_n = (statuses.most_common(1)[0] if statuses else ("", 0))

    inj_per_class = [len(r.get("stats", {}).get("injections") or []) for r in ok]
    inj_mech: Counter = Counter()
    for r in ok:
        inj_mech.update(set(r.get("stats", {}).get("injections") or []))
    inj_avg = (sum(inj_per_class) / n) if n else 0.0
    inj_top, inj_top_n = (inj_mech.most_common(1)[0] if inj_mech else ("", 0))

    attempted = sum(int(r.get("stats", {}).get("cards_attempted") or 0) for r in ok)
    first_ok = sum(int(r.get("stats", {}).get("cards_first_ok") or 0) for r in ok)
    pass_rate = (first_ok / attempted) if attempted else 0.0

    return {
        "classes": n, "failed": len(results) - n, "cards": total_cards,
        "distinct_archetypes": distinct, "archetype_counts": arch_count, "over4": over4,
        "da_skeleton": da_skeleton, "da_share": (da_skeleton / total_cards) if total_cards else 0.0,
        "statuses": statuses, "top_status": top_status, "top_status_share": (top_status_n / status_total) if status_total else 0.0,
        "name_repeats": repeats, "top_first_word": top_word, "top_first_word_n": top_word_n,
        "inj_per_class": inj_per_class, "inj_avg": inj_avg, "inj_top": inj_top, "inj_top_n": inj_top_n,
        "cards_attempted": attempted, "cards_first_ok": first_ok, "first_pass_rate": pass_rate,
    }


def format_report(results: list[dict], m: dict, *, mode: str, harness: str) -> str:
    n = m["classes"]
    rows = [
        (METRIC_ROWS[0][0], f"{m['distinct_archetypes']} (over {n} classes)", METRIC_ROWS[0][1]),
        (METRIC_ROWS[1][0], (", ".join(m["over4"]) if m["over4"] else "none"), METRIC_ROWS[1][1]),
        (METRIC_ROWS[2][0], f"{m['da_share']:.0%} ({m['da_skeleton']}/{m['cards']})", METRIC_ROWS[2][1]),
        (METRIC_ROWS[3][0], (f"{m['top_status']} {m['top_status_share']:.0%}" if m["top_status"] else "n/a"), METRIC_ROWS[3][1]),
        (METRIC_ROWS[4][0], (", ".join(m["name_repeats"]) if m["name_repeats"] else "zero"), METRIC_ROWS[4][1]),
        (METRIC_ROWS[5][0], (f"'{m['top_first_word']}' {m['top_first_word_n']}" if m["top_first_word"] else "n/a"), METRIC_ROWS[5][1]),
        (METRIC_ROWS[6][0], f"{m['inj_avg']:.2f} avg" + (f"; top mechanic '{m['inj_top']}' in {m['inj_top_n']} class(es)" if m["inj_top"] else ""), METRIC_ROWS[6][1]),
        (METRIC_ROWS[7][0], f"{m['first_pass_rate']:.0%} ({m['cards_first_ok']}/{m['cards_attempted']})", METRIC_ROWS[7][1]),
    ]
    out = [f"# Creative harness bench - {harness}", "",
           f"- date: {_dt.datetime.now(_dt.timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
           f"- backend: {mode}", f"- classes forged: {n} of {len(results)}"
           + (f" ({m['failed']} failed)" if m["failed"] else ""), "",
           "| Metric | Value | Target |", "|---|---|---|"]
    out += [f"| {a} | {b} | {c} |" for a, b, c in rows]
    out += ["", "## Per class", "", "| # | Concept | Class | Archetypes | Cards | Injections |", "|---|---|---|---|---|---|"]
    for i, r in enumerate(results, 1):
        bp = r.get("blueprint") or {}
        ids = bp.get("archetype_ids") or [a.get("id") for a in (bp.get("archetypes") or []) if isinstance(a, dict)]
        cards = len(_pool_cards(r["bundle"])) if r.get("bundle") else 0
        inj = ", ".join(r.get("stats", {}).get("injections") or []) or "-"
        name = r.get("name") or ("FAILED" if not r.get("ok") else "?")
        out.append(f"| {i} | {r['concept']} | {name} | {', '.join(str(x) for x in ids)} | {cards} | {inj} |")
    if m["archetype_counts"]:
        out += ["", "## Archetype usage", "",
                ", ".join(f"{a} x{k}" for a, k in m["archetype_counts"].most_common())]
    if m["statuses"]:
        out += ["", "## apply_status uses", "",
                ", ".join(f"{s} x{k}" for s, k in m["statuses"].most_common())]
    return "\n".join(out) + "\n"


def run(concepts: list[str], *, fake: bool, ollama_config: str | None = None, on_event=None) -> tuple[str, dict]:
    """Forge + measure + format. Returns (markdown, metrics)."""
    from . import harness_v2
    results = forge_concepts(concepts, fake=fake, ollama_config=ollama_config, on_event=on_event)
    m = compute_metrics(results)
    harness = "v2 (BTS_HARNESS_V2=1)" if harness_v2.enabled() else "v1 (flag off)"
    return format_report(results, m, mode="fake-offline" if fake else "ollama mix (token path)", harness=harness), m


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Forge the fixed 12-concept set and report the creative-harness metrics.")
    ap.add_argument("--fake", action="store_true", help="offline: fake stages + fake cards (no keys; smoke-test only)")
    ap.add_argument("--v2", action="store_true", help="set BTS_HARNESS_V2=1 for this run")
    ap.add_argument("--concepts", type=int, default=len(CONCEPTS), help="forge only the first N concepts")
    ap.add_argument("--out", default=None, help="also write the markdown report here (e.g. docs/plans/HARNESS_BENCH.md)")
    ap.add_argument("--ledger", default=None, help="ledger file for this run (default: a fresh temp file)")
    ap.add_argument("--ollama-config", default=None, help="role map JSON for the ollama path")
    ap.add_argument("--quiet", action="store_true", help="no per-forge progress on stderr")
    args = ap.parse_args(argv)

    if args.v2:
        os.environ["BTS_HARNESS_V2"] = "1"
    point_btsgen_at_mod_contract()
    if not args.fake:
        from .generator import load_env
        load_env()
        if not os.environ.get("OLLAMA_API_KEY"):
            print("ERROR: OLLAMA_API_KEY is not set (use --fake for an offline smoke run).", file=sys.stderr)
            return 2

    ledger_path = Path(args.ledger) if args.ledger else Path(tempfile.mkdtemp(prefix="btsgen_bench_")) / "bench_ledger.jsonl"
    concepts = CONCEPTS[:max(1, args.concepts)]
    from . import ledger
    progress = None if args.quiet else (lambda m: print(f"  {m}", file=sys.stderr))
    with ledger.ledger_scope(ledger_path):
        report, _m = run(concepts, fake=args.fake, ollama_config=args.ollama_config, on_event=progress)
    print(report)
    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(report, encoding="utf-8")
        print(f"(written to {out})", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
