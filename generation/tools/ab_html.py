"""Render two (or more) `ab_compare.py` markdown reports as ONE side-by-side HTML page.

    cd generation
    uv run python tools/ab_html.py scratch/ab_clockmaker_baseline.md scratch/ab_clockmaker_kimi3.md \
        --labels "baseline (gemma+glm)" "kimi-k3 designer" --out scratch/ab_clockmaker_compare.html

Each input file is a report written by tools/ab_compare.py (one or more legs). The page shows a metrics
strip, the two card lists column-by-column grouped by rarity (card names that appear in BOTH decks are
highlighted), and collapsible progress logs + copy-button BTSC codes. Pure stdlib; the HTML is standalone
(no network, inline CSS/JS) so it opens from file:// anywhere.
"""
from __future__ import annotations

import argparse
import html
import re
import sys
from pathlib import Path

_RARITY_ORDER = {"basic": 0, "common": 1, "uncommon": 2, "rare": 3}


def _parse_report(path: Path) -> list[dict]:
    """Pull every leg out of one ab_compare report. Returns [{title, stats{}, cards[], log, code}]."""
    text = path.read_text(encoding="utf-8")

    # --- leg stat blocks: "### <name>\n\n- **status:** ..." bullets. A value may span extra lines
    # (the ollama-mix `models` banner is multi-line), so parse line-by-line with continuations. ---
    legs: list[dict] = []
    for m in re.finditer(r"^### (?P<name>\S+)\n\n(?P<body>(?:(?!#).*\n?)+)", text, re.M):
        stats: dict[str, str] = {}
        key = None
        for line in m.group("body").splitlines():
            b = re.match(r"- \*\*(?P<k>[^:*]+):\*\*\s*(?P<v>.*)", line)
            if b:
                key = b.group("k").strip()
                stats[key] = b.group("v").strip()
                # a bullet may carry several "**k:** v  |  **k:** v" pairs
                for extra in re.finditer(r"\*\*(?P<k>[^:*]+):\*\*\s*(?P<v>[^|]+)", b.group("v")):
                    stats[extra.group("k").strip()] = extra.group("v").strip()
            elif key and line.startswith((" ", "\t")):
                stats[key] += "\n" + line.rstrip()
            else:
                key = None
        if "status" in stats:
            legs.append({"name": m.group("name"), "stats": stats, "cards": [], "log": "", "code": "",
                         "header": ""})
    if not legs:
        raise SystemExit(f"{path}: no leg blocks found — is this an ab_compare report?")

    # --- card lists: "### <name> — <Class> (...)" + a markdown table ---
    for m in re.finditer(
            r"^### (?P<name>\S+) — (?P<hdr>.+)\n\n\| # \| card .*\n\|[-| ]+\n(?P<rows>(?:\|.*\n?)+)",
            text, re.M):
        leg = next((l for l in legs if l["name"] == m.group("name")), None)
        if leg is None:
            continue
        leg["header"] = m.group("hdr").strip()
        for row in m.group("rows").strip().splitlines():
            cells = [c.strip() for c in row.strip().strip("|").split("|")]
            if len(cells) >= 6:
                leg["cards"].append({"name": cells[1], "type": cells[2], "rarity": cells[3],
                                     "cost": cells[4], "text": cells[5]})

    # --- fenced blocks: "## <name> — progress log" / "## <name> — BTSC code ..." ---
    for m in re.finditer(r"^## (?P<name>\S+) — (?P<kind>progress log|BTSC code)[^\n]*\n+```\n(?P<body>.*?)```",
                         text, re.M | re.S):
        leg = next((l for l in legs if l["name"] == m.group("name")), None)
        if leg is not None:
            leg["log" if m.group("kind") == "progress log" else "code"] = m.group("body").strip()

    concept = re.search(r"^# A/B forge — (.+)$", text, re.M)
    for l in legs:
        l["concept"] = concept.group(1).strip("'\"") if concept else ""
    return legs


_TYPE_CLASS = {"attack": "t-attack", "skill": "t-skill", "power": "t-power"}

_STAT_ROWS = [  # (stats key from ab_compare, display label)
    ("status", "status"), ("wall-clock", "wall-clock"), ("LLM calls", "LLM calls"),
    ("repairs", "repairs"), ("tokens", "tokens in/out"), ("class", "class"),
    ("cards", "cards"), ("skipped briefs", "skipped briefs"), ("models", "models"),
]


def _enrich_from_code(leg: dict) -> None:
    """Decode the leg's BTSC bundle and swap each card's terse op summary for the REAL in-game text
    (cardgen.describe is kept in lockstep with the mod's C# ForgedCards.Describe), plus flavor + upgrade
    text. Best-effort: any failure leaves the markdown-table text as-is."""
    if not leg.get("code"):
        return
    try:
        import json as _json

        from btsgen import bts1
        from btsgen.cardgen import describe
        bundle = _json.loads(bts1.decode(leg["code"])[0])
        by_name = {c.get("name", "").lower(): c for c in bundle.get("cards", [])}
        for row in leg["cards"]:
            c = by_name.get(row["name"].lower())
            if not c:
                continue
            tgt = c.get("target", "")
            row["text"] = describe(c.get("effects") or [], tgt)
            row["flavor"] = c.get("flavor") or ""
            up = (c.get("upgrade") or {}).get("effects")
            row["uptext"] = describe(up, tgt) if up else ""
    except Exception as e:  # noqa: BLE001 — the viewer must still render without btsgen / on a bad code
        print(f"[warn] could not enrich cards from BTSC code: {type(e).__name__}: {e}")


def _card_html(c: dict, dup: bool) -> str:
    tcls = _TYPE_CLASS.get(c["type"].lower(), "t-other")
    name = html.escape(c["name"]) + (' <span class="dup" title="a card with this name is in both decks">both</span>' if dup else "")
    up = (f'<div class="cup"><span class="uplbl">upgrade:</span> {html.escape(c["uptext"])}</div>'
          if c.get("uptext") and c["uptext"] != c["text"] else "")
    flavor = f'<div class="cflavor">{html.escape(c["flavor"])}</div>' if c.get("flavor") else ""
    return (f'<div class="card {tcls}"><div class="chead"><span class="cname">{name}</span>'
            f'<span class="ccost">{html.escape(str(c["cost"]))}</span></div>'
            f'<div class="cmeta">{html.escape(c["type"])}</div>'
            f'<div class="ctext">{html.escape(c["text"])}</div>{up}{flavor}</div>')


def _column_html(leg: dict, label: str, dups: set[str]) -> str:
    stats = leg["stats"]
    rows = "".join(
        f'<tr><th>{html.escape(disp)}</th><td>{html.escape(stats.get(key, "—"))}</td></tr>'
        for key, disp in _STAT_ROWS if key != "models")
    models = html.escape(stats.get("models", "—")).replace("\n", "<br>")
    rows += f'<tr><th>models</th><td class="models">{models}</td></tr>'

    by_rarity: dict[str, list[dict]] = {}
    for c in leg["cards"]:
        by_rarity.setdefault(c["rarity"].lower(), []).append(c)
    groups = []
    for rar in sorted(by_rarity, key=lambda r: _RARITY_ORDER.get(r, 9)):
        cards = "".join(_card_html(c, c["name"].lower() in dups)
                        for c in sorted(by_rarity[rar], key=lambda c: c["name"].lower()))
        groups.append(f'<h3 class="rarity r-{html.escape(rar)}">{html.escape(rar)} '
                      f'<span class="count">×{len(by_rarity[rar])}</span></h3><div class="cards">{cards}</div>')
    cards_html = "".join(groups) or '<p class="empty">(no cards — leg failed?)</p>'

    log = html.escape(leg["log"]) or "(no log captured)"
    code = html.escape(leg["code"])
    code_block = (f'<details><summary>BTSC code (paste in-game)</summary>'
                  f'<button class="copy" onclick="copyCode(this)">copy</button>'
                  f'<pre class="code">{code}</pre></details>') if code else ""
    return f"""<section class="col">
  <h2>{html.escape(label)}</h2>
  <p class="chdr">{html.escape(leg["header"] or "")}</p>
  <table class="stats">{rows}</table>
  {cards_html}
  <details><summary>progress log</summary><pre>{log}</pre></details>
  {code_block}
</section>"""


_PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<title>A/B forge — {title}</title>
<style>
  :root {{ color-scheme: dark; }}
  body {{ margin: 0; padding: 1.2rem; background: #14161d; color: #d8dae2;
         font: 14px/1.45 "Segoe UI", system-ui, sans-serif; }}
  h1 {{ font-size: 1.25rem; margin: 0 0 .2rem; }} .concept {{ color: #9aa0b4; margin: 0 0 1rem; }}
  .grid {{ display: grid; grid-template-columns: repeat({ncols}, minmax(0, 1fr)); gap: 1.2rem;
           align-items: start; }}
  .col {{ background: #1b1e28; border: 1px solid #2a2e3d; border-radius: 10px; padding: 1rem; }}
  .col > h2 {{ margin: 0 0 .3rem; font-size: 1.05rem; color: #ffd479; }}
  .chdr {{ color: #9aa0b4; margin: 0 0 .8rem; font-size: .85rem; }}
  table.stats {{ border-collapse: collapse; width: 100%; margin-bottom: 1rem; font-size: .85rem; }}
  table.stats th {{ text-align: left; color: #8b91a7; font-weight: 500; padding: .15rem .6rem .15rem 0;
                    white-space: nowrap; vertical-align: top; }}
  table.stats td {{ padding: .15rem 0; }} td.models {{ font-family: Consolas, monospace; font-size: .78rem; }}
  h3.rarity {{ margin: .9rem 0 .4rem; font-size: .8rem; text-transform: uppercase; letter-spacing: .08em; }}
  .r-basic {{ color: #b7bdd1; }} .r-common {{ color: #cfd6e4; }} .r-uncommon {{ color: #6fd3ff; }}
  .r-rare {{ color: #ffd479; }} .count {{ color: #6b7188; font-weight: 400; }}
  .cards {{ display: grid; gap: .45rem; }}
  .card {{ border: 1px solid #2a2e3d; border-left-width: 4px; border-radius: 7px; padding: .45rem .6rem;
           background: #20242f; }}
  .t-attack {{ border-left-color: #e06c5b; }} .t-skill {{ border-left-color: #5bb8e0; }}
  .t-power {{ border-left-color: #b48ce0; }} .t-other {{ border-left-color: #7a8095; }}
  .chead {{ display: flex; justify-content: space-between; gap: .5rem; }}
  .cname {{ font-weight: 600; }} .ccost {{ color: #ffd479; font-weight: 600; }}
  .cmeta {{ font-size: .72rem; color: #8b91a7; text-transform: uppercase; letter-spacing: .06em; }}
  .ctext {{ font-size: .85rem; margin-top: .2rem; color: #c3c7d4; }}
  .cup {{ font-size: .78rem; margin-top: .25rem; color: #8fd08f; }}
  .uplbl {{ color: #5f8f5f; text-transform: uppercase; font-size: .68rem; letter-spacing: .06em; }}
  .cflavor {{ font-size: .75rem; margin-top: .25rem; color: #7d8296; font-style: italic; }}
  .dup {{ background: #3d3420; color: #ffd479; border: 1px solid #6b5a2a; border-radius: 4px;
          font-size: .68rem; padding: 0 .3rem; vertical-align: middle; }}
  details {{ margin-top: 1rem; }} summary {{ cursor: pointer; color: #9aa0b4; }}
  pre {{ background: #14161d; border: 1px solid #2a2e3d; border-radius: 7px; padding: .6rem;
         overflow: auto; max-height: 24rem; font-size: .75rem; white-space: pre-wrap;
         word-break: break-all; }}
  button.copy {{ margin: .4rem 0; background: #2a2e3d; color: #d8dae2; border: 1px solid #3a3f52;
                 border-radius: 5px; padding: .2rem .7rem; cursor: pointer; }}
  button.copy:active {{ background: #3a3f52; }}
  .empty {{ color: #8b91a7; }}
  .note {{ background: #1f2433; border: 1px solid #34405e; border-radius: 8px; padding: .6rem .9rem;
           margin: 0 0 1.1rem; color: #b9c2dc; font-size: .88rem; max-width: 70rem; }}
  @media (max-width: 900px) {{ .grid {{ grid-template-columns: 1fr; }} }}
</style></head><body>
<h1>A/B forge comparison</h1>
<p class="concept">concept: {concept}</p>
{note}
<div class="grid">
{columns}
</div>
<script>
function copyCode(btn) {{
  navigator.clipboard.writeText(btn.nextElementSibling.textContent)
    .then(() => {{ btn.textContent = "copied!"; setTimeout(() => btn.textContent = "copy", 1500); }});
}}
</script>
</body></html>
"""


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Side-by-side HTML for ab_compare reports.")
    ap.add_argument("reports", nargs="+", help="ab_*.md files (each contributes its legs, in order)")
    ap.add_argument("--labels", nargs="*", default=None,
                    help="one label per column (default: <filestem>:<legname>)")
    ap.add_argument("--note", default=None,
                    help="free-text callout rendered under the header (e.g. a cost estimate); newlines kept")
    ap.add_argument("--out", default=None, help="output .html (default: alongside the first report)")
    args = ap.parse_args(argv)

    cols: list[tuple[str, dict]] = []
    for p in args.reports:
        path = Path(p)
        for leg in _parse_report(path):
            _enrich_from_code(leg)
            cols.append((f"{path.stem}:{leg['name']}", leg))
    if args.labels:
        if len(args.labels) != len(cols):
            raise SystemExit(f"--labels got {len(args.labels)} labels but there are {len(cols)} columns")
        cols = [(lab, leg) for lab, (_, leg) in zip(args.labels, cols)]

    # card names present in MORE THAN ONE column get the "both" badge
    from collections import Counter
    counts = Counter(c["name"].lower() for _, leg in cols for c in {x["name"].lower(): x for x in leg["cards"]}.values())
    dups = {n for n, k in counts.items() if k > 1}

    columns = "\n".join(_column_html(leg, label, dups) for label, leg in cols)
    concept = next((leg["concept"] for _, leg in cols if leg.get("concept")), "")
    note = (f'<div class="note">{html.escape(args.note).replace(chr(10), "<br>")}</div>'
            if args.note else "")
    page = _PAGE.format(title=html.escape(concept or "report"), ncols=len(cols),
                        concept=html.escape(concept or "?"), columns=columns, note=note)

    out = Path(args.out) if args.out else Path(args.reports[0]).with_suffix("").parent / (
        Path(args.reports[0]).stem + "_compare.html")
    out.write_text(page, encoding="utf-8")
    print(f"[OK] wrote {out} ({len(cols)} columns)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
