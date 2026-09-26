"""Phase 1 A/B of docs/plans/JEV_EVALUATION_PLAN.md: whole forges with the card-stage vocab gate off vs on.

Each forge runs the website's own hosted path (web/forge.py forge_to_bundle, ollama_mix=True, staged, triad)
in its OWN process, because $BTS_VOCAB_GATE is read when the card generator is built. The route is pinned to the
metered OpenRouter tier (OLLAMA_API_KEY blanked -> the cards/structure roles promote to openrouter-glm53), so
every call reports its real USD cost and cached-token count. Isolation: quarantine, recency ledger (one fresh
user id per run) and captured-gap log all go under scratch/gate_forge_ab/, never _class_gen or web/.

    uv run python tools/gate_forge_ab.py run --arm off --concept "a cowboy gunslinger" --tag off1
    uv run python tools/gate_forge_ab.py launch --arms off,heuristic,jev --n 3 --concept "a cowboy gunslinger"
    uv run python tools/gate_forge_ab.py summarize

PAIRED mode (removes the class-kind confound: every arm designs cards for the SAME blueprint):
    uv run python tools/gate_forge_ab.py capture --concept "a plague doctor" --tag plague   # front end only
    uv run python tools/gate_forge_ab.py paired --arms off,heuristic,jev                    # every bp x arm
    uv run python tools/gate_forge_ab.py summarize --paired
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

GEN = Path(__file__).resolve().parents[1]
REPO = GEN.parent
OUT = GEN / "scratch" / "gate_forge_ab"
ARMS = ("off", "heuristic", "jev", "heuristic_whole", "jev_whole")


class _Captured(Exception):
    pass


def _patch_frontend(replay: dict | None = None, capture_to: Path | None = None) -> None:
    """Replay a saved blueprint (the card stage then runs on a byte-identical class), or capture the one the
    real staged front end builds and stop the forge before any card is designed."""
    import copy
    from btsgen import frontend
    real = frontend.BlueprintBuilder

    class Patched(real):
        def build(self, brief):
            if replay is not None:
                return copy.deepcopy(replay)
            bp = super().build(brief)
            capture_to.write_text(json.dumps(bp, indent=1), encoding="utf-8")
            raise _Captured(str(capture_to))

    frontend.BlueprintBuilder = Patched


def run(arm: str, concept: str, tag: str, bp_file: str | None = None, capture: bool = False) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    mode, _, schema = arm.partition("_")          # "jev" = jev + split schema (1b); "jev_whole" = Phase 1a
    os.environ["BTS_VOCAB_GATE"] = mode
    os.environ["BTS_VOCAB_GATE_SCHEMA"] = schema or "split"
    os.environ["BTS_HARNESS_V2"] = "1"
    os.environ["OLLAMA_API_KEY"] = ""          # pin the metered OpenRouter route (see module doc)
    os.environ["BTSGEN_GENERATED_DIR"] = str(OUT / "quarantine" / tag)
    os.environ["BTS_FORGE_LEDGER"] = str(OUT / "ledger.jsonl")
    sys.path.insert(0, str(REPO / "web"))
    import forge as webforge  # noqa: E402  (web/forge.py: sets BTS_REPO_ROOT, points btsgen at the mod contract)
    from btsgen import paths
    # point_btsgen_at_mod_contract() (run by that import) resets GENERATED_DIR to scratch/_class_gen, the Phase 0
    # ground-truth set; send this forge's quarantine writes to its own folder instead.
    paths.GENERATED_DIR = OUT / "quarantine" / tag

    gaps = OUT / f"{tag}.gaps.jsonl"

    def gap_sink(entries):
        with gaps.open("a", encoding="utf-8") as fh:
            for e in entries:
                fh.write(json.dumps(e) + "\n")
        return len(entries)

    webforge._append_captured_gaps = gap_sink
    if capture:
        (OUT / "bp").mkdir(exist_ok=True)
        _patch_frontend(capture_to=OUT / "bp" / f"{tag}.json")
    elif bp_file:
        bp = json.loads(Path(bp_file).read_text(encoding="utf-8"))
        _patch_frontend(replay=bp)
    meter = webforge.UsageMeter()
    t0 = time.time()
    out = {"arm": arm, "concept": concept, "tag": tag}
    try:
        b = webforge.forge_to_bundle(concept, ollama_mix=True, staged=True, triad=True, on_usage=meter,
                                     user_id=f"gate_ab_{tag}")
        out.update(ok=True, log=b["log"], skipped=b["skipped"], cards=b["cards"],
                   character=b["character"].get("name") if isinstance(b.get("character"), dict) else None)
    except _Captured as e:
        print(f"captured blueprint -> {e}")
        return
    except Exception as e:  # noqa: BLE001 — record, the summary counts failed forges
        out.update(ok=False, error=f"{type(e).__name__}: {e}"[:600])
    out["secs"] = round(time.time() - t0, 1)
    out["usage"] = meter.rows()
    if bp_file:
        out["bp"] = Path(bp_file).stem
    (OUT / f"{tag}.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(json.dumps({k: out.get(k) for k in ("arm", "tag", "ok", "secs", "error")}))


def paired(arms: list[str]) -> None:
    """Every captured blueprint x every arm, all in parallel, results tagged p_<bp>_<arm>."""
    procs = []
    for bpf in sorted((OUT / "bp").glob("*.json")):
        for arm in arms:
            tag = f"p_{bpf.stem}_{arm}"
            if (OUT / f"{tag}.json").exists():
                continue
            log = (OUT / f"{tag}.stdout.txt").open("w", encoding="utf-8")
            procs.append((tag, subprocess.Popen([sys.executable, __file__, "run", "--arm", arm, "--concept", "(replay)",
                                                 "--tag", tag, "--bp", str(bpf)], cwd=GEN, stdout=log,
                                                stderr=subprocess.STDOUT)))
    for tag, p in procs:
        p.wait()
        print(tag, "exit", p.returncode)


def launch(arms: list[str], n: int, concept: str) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    procs = []
    for i in range(1, n + 1):
        for arm in arms:
            tag = f"{arm}{i}"
            if (OUT / f"{tag}.json").exists():
                continue
            log = (OUT / f"{tag}.stdout.txt").open("w", encoding="utf-8")
            procs.append((tag, subprocess.Popen([sys.executable, __file__, "run", "--arm", arm, "--concept",
                                                 concept, "--tag", tag], cwd=GEN, stdout=log,
                                                stderr=subprocess.STDOUT)))
    for tag, p in procs:
        p.wait()
        print(tag, "exit", p.returncode)


_GATE_NOTE = re.compile(r"vocab gate \[(\w+)\]: (\d+) card prompt\(s\) at (\d+)% of the full prompt; (\d+) sent full "
                        r"\((\d+) Jev failure\(s\)\); (\d+) valid first try")
_CARD_OK = re.compile(r"card \d+/\d+: .* ready ")
_CARD_FAIL = re.compile(r"card \d+ \(.*\): failed, skipped")


def summarize(paired_only: bool = False) -> None:
    rows = []
    for f in sorted(OUT.glob("p_*.json" if paired_only else "*.json")):
        try:
            rows.append(json.loads(f.read_text(encoding="utf-8")))
        except Exception:
            continue
    by: dict[str, list] = {}
    for r in rows:
        by.setdefault(r["arm"], []).append(r)
    lines = ["| arm | forges ok | avg $ / forge | cards role $ | gate $ | card input tok | cached share | "
             "card calls | cards ok / failed | gated prompt % | full sends | mins |", "|" + "---|" * 12]
    for arm in ARMS:
        rs = by.get(arm) or []
        if not rs:
            continue
        ok = [r for r in rs if r.get("ok")]
        tot = cards_cost = gate_cost = cin = ccached = ccalls = 0.0
        for r in ok:
            for u in r["usage"]:
                c = u.get("cost_usd") or 0.0
                tot += c
                if u["role"] == "cards":
                    cards_cost += c
                    cin += u["input_tokens"]
                    ccached += u["cached_tokens"]
                    ccalls += u["calls"]
                if u["role"] == "gate":
                    gate_cost += c
        k = max(1, len(ok))
        good = sum(1 for r in ok for line in r["log"] if _CARD_OK.search(line))
        bad = sum(1 for r in ok for line in r["log"] if _CARD_FAIL.search(line))
        pct = full = ""
        notes = [m for r in ok for line in r["log"] for m in [_GATE_NOTE.search(line)] if m]
        if notes:
            pct = f"{sum(int(m.group(3)) for m in notes) / len(notes):.0f}%"
            full = str(sum(int(m.group(4)) for m in notes))
        lines.append(f"| {arm} | {len(ok)}/{len(rs)} | {tot / k:.3f} | {cards_cost / k:.3f} | {gate_cost / k:.4f} | "
                     f"{cin / k:,.0f} | {100 * ccached / max(1, cin):.0f}% | {ccalls / k:.1f} | {good}/{bad} | "
                     f"{pct or '-'} | {full or '-'} | {sum(r['secs'] for r in ok) / k / 60:.1f} |")
    if paired_only:
        lines += ["", _first_try_table(rows)]
    text = "\n".join(lines)
    (OUT / ("summary_paired.md" if paired_only else "summary.md")).write_text(text + "\n", encoding="utf-8")
    print(text)
    for r in rows:
        if not r.get("ok"):
            print(f"FAILED {r['tag']}: {r.get('error')}")


def _first_try_table(rows: list[dict]) -> str:
    """Per blueprint x arm: cards, repaired cards (from the quarantine metas), and the repair causes."""
    out = ["| blueprint | arm | cards | repaired | $ forge | card input tok |", "|---|---|---|---|---|---|"]
    for r in sorted(rows, key=lambda r: (r.get("bp") or "", ARMS.index(r["arm"]))):
        metas = [json.loads(m.read_text(encoding="utf-8"))
                 for m in (OUT / "quarantine" / r["tag"]).glob("*.meta.json")]
        rep = sum(1 for m in metas if m.get("repaired"))
        cost = sum(u.get("cost_usd") or 0 for u in r.get("usage", []))
        cin = sum(u["input_tokens"] for u in r.get("usage", []) if u["role"] == "cards")
        out.append(f"| {r.get('bp')} | {r['arm']} | {len(metas)} | {rep} | {cost:.3f} | {cin:,} |")
    return "\n".join(out)


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("run")
    a.add_argument("--arm", choices=ARMS, required=True)
    a.add_argument("--concept", required=True)
    a.add_argument("--tag", required=True)
    a.add_argument("--bp", default=None, help="replay this captured blueprint")
    c = sub.add_parser("capture")
    c.add_argument("--concept", required=True)
    c.add_argument("--tag", required=True)
    pr = sub.add_parser("paired")
    pr.add_argument("--arms", default="off,heuristic,jev")
    b = sub.add_parser("launch")
    b.add_argument("--arms", default="off,heuristic,jev")
    b.add_argument("--n", type=int, default=3)
    b.add_argument("--concept", required=True)
    sm = sub.add_parser("summarize")
    sm.add_argument("--paired", action="store_true")
    args = ap.parse_args()
    if args.cmd == "run":
        run(args.arm, args.concept, args.tag, bp_file=args.bp)
    elif args.cmd == "capture":
        run("off", args.concept, f"cap_{args.tag}", capture=True)
    elif args.cmd == "paired":
        paired(args.arms.split(","))
    elif args.cmd == "launch":
        launch(args.arms.split(","), args.n, args.concept)
    else:
        summarize(paired_only=args.paired)


if __name__ == "__main__":
    main()
