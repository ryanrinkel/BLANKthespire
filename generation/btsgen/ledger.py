"""ledger.py — cross-forge usage ledger + recency signals (Phase N-4).

Append one line per SUCCESSFUL forge to a gitignored JSONL (scratch/forge_ledger.jsonl, or
$BTS_FORGE_LEDGER). At forge start, read the last LEDGER_WINDOW entries and turn them into: a compact
"recently overused" line for the map/compose prompt, a status-focused line for the blueprint brief, and a
per-candidate novelty penalty for the picker (recency-weighted; strictly below the fidelity weight so it
only ever breaks ties among equally-faithful candidates — exactly like distinctiveness does today).

ROBUSTNESS: every read AND write is guarded — a missing / corrupt / unwritable ledger NEVER breaks a
forge (posture precedent: the note() sink guard). scratch/ is gitignored, so the website's read-only rule
is honored (the forge only ever WRITES to this untracked path).
"""
from __future__ import annotations

import contextvars
import json
import os
import time
from collections import Counter
from contextlib import contextmanager
from pathlib import Path

from . import census

LEDGER_WINDOW = 12
_NOVELTY_MAX = 2.0            # picker penalty ceiling; STRICTLY below _FIDELITY_WEIGHT (10.0)
_PAIR_W = 0.8                 # weight of an exact recent pair-repeat
_ARCH_W = 0.3                 # weight of each shared archetype

# Per-forge ledger override. The web layer runs each forge in its OWN thread and wants a PER-USER ledger, but
# os.environ is process-global — mutating it per request would let concurrent forges clobber each other's path
# mid-run. A ContextVar is thread/async-local, so a scope set inside one forge thread is invisible to every
# other. None => fall back to $BTS_FORGE_LEDGER / the default. Set via ledger_scope(); read by ledger_path().
_scope_override: contextvars.ContextVar = contextvars.ContextVar("bts_ledger_override", default=None)


def _base_ledger_path() -> Path:
    """The base ledger file from $BTS_FORGE_LEDGER (or the default scratch path) — IGNORING any per-forge
    scope override. This is the location per-user ledgers are derived from."""
    env = os.environ.get("BTS_FORGE_LEDGER")
    if env:
        return Path(env)
    from .class_forge import REPO
    return REPO / "generation" / "scratch" / "forge_ledger.jsonl"


def ledger_path() -> Path:
    """The ACTIVE ledger file. Precedence: a per-forge scope override (thread/async-local; the web layer sets
    it for per-user ledgers) > $BTS_FORGE_LEDGER > the default scratch path."""
    override = _scope_override.get()
    return Path(override) if override else _base_ledger_path()


def ledger_path_for_user(user_id) -> Path:
    """Per-user ledger path: the base ledger path with a `_u<id>` suffix, so each signed-in user reads/writes
    an ISOLATED recency window (siblings in the same gitignored scratch dir). user_id None/blank => the shared
    base path (CLI / anonymous). The base honors $BTS_FORGE_LEDGER, so that env still governs dir + filename."""
    base = _base_ledger_path()
    if user_id is None or str(user_id) == "":
        return base
    safe = "".join(c if (c.isalnum() or c in "-_") else "_" for c in str(user_id))
    return base.with_name(f"{base.stem}_u{safe}{base.suffix}")


@contextmanager
def ledger_scope(path):
    """Scope every read_window()/record_forge() call inside the block to `path`, for the CURRENT thread/async
    context only (a ContextVar — concurrent forges don't clash). path falsy => no override. Used by the web
    layer to point each forge at its user's ledger."""
    token = _scope_override.set(str(path) if path else None)
    try:
        yield
    finally:
        _scope_override.reset(token)


def _archetype_ids(blueprint) -> list[str]:
    bp = blueprint or {}
    # Prefer the authoritative catalog ids the builder stamps on (bp["archetype_ids"]); the 7B often echoes
    # display NAMES into bp["archetypes"][*].id, which would break id-based recency matching in the picker.
    canon = bp.get("archetype_ids")
    if isinstance(canon, list) and canon:
        return [str(i) for i in canon if i]
    out: list[str] = []
    for a in bp.get("archetypes") or []:
        if isinstance(a, dict) and a.get("id"):
            out.append(str(a["id"]))
        elif isinstance(a, str) and a:
            out.append(a)
    return out


def _class_kind(blueprint) -> str:
    bp = blueprint or {}
    if int(bp.get("orb_slots", 0) or 0) > 0:
        return "orb"
    if bp.get("status_pool"):
        return "status"
    if bp.get("summon_pool"):
        return "summon"
    return "normal"


def record_forge(bundle: dict, blueprint: dict, *, ts: float | None = None) -> bool:
    """Append one ledger line for a successful forge. Returns True on write, False on any failure (never
    raises). The census fields come from census.py so the ledger measures the SAME thing the quotas do."""
    try:
        cen = census.census_bundle(bundle)
        entry = {
            "ts": float(ts if ts is not None else time.time()),
            "name": str((bundle.get("character") or {}).get("name") or (blueprint or {}).get("name") or ""),
            "archetype_ids": _archetype_ids(blueprint),
            "class_kind": _class_kind(blueprint),
            # Phase N-5: the featured-roulette picks (forge_class stamps bp["featured"] with the FINAL ids,
            # theme-aware re-rolls included) — feeds featured_recency() to damp repeats in later rolls.
            "featured": [str(i) for i in ((blueprint or {}).get("featured") or [])],
            "top_ops": [op for op, _ in cen.ops.most_common(6)],
            "statuses_used": sorted(cen.statuses),
            "trigger_kinds": sorted(cen.triggers),
        }
        path = ledger_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, separators=(",", ":")) + "\n")
        return True
    except Exception:
        return False


def read_window(n: int = LEDGER_WINDOW, path: Path | None = None) -> list[dict]:
    """The last `n` ledger entries, oldest->newest. Missing file / blank / corrupt lines are skipped;
    never raises."""
    try:
        p = path or ledger_path()
        if not p.exists():
            return []
        lines = p.read_text(encoding="utf-8").splitlines()
        out: list[dict] = []
        for ln in lines[-(n * 2):]:  # read a little extra so corrupt lines don't shrink the usable window
            ln = ln.strip()
            if not ln:
                continue
            try:
                obj = json.loads(ln)
            except Exception:
                continue
            if isinstance(obj, dict):
                out.append(obj)
        return out[-n:]
    except Exception:
        return []


def _recency_weights(window) -> list[float]:
    """Per-entry weights in (0, 1], oldest smallest -> newest ~1.0 (linear recency decay)."""
    L = len(window)
    return [(k + 1) / L for k in range(L)] if L else []


def pair_penalty(archetype_ids, window) -> float:
    """A novelty penalty in [0, _NOVELTY_MAX]: recency-weighted overlap of this candidate's archetypes/pair
    with the recent window. 0 when nothing overlaps; grows with recent exact-pair repeats and shared
    archetypes; capped so it can only break ties under the fidelity weight."""
    if not window:
        return 0.0
    ids = {str(i) for i in (archetype_ids or [])}
    if not ids:
        return 0.0
    pair = frozenset(ids)
    pair_hits = 0.0
    arch_hits = 0.0
    for w, e in zip(_recency_weights(window), window):
        eids = {str(i) for i in (e.get("archetype_ids") or [])}
        if len(pair) >= 2 and frozenset(eids) == pair:
            pair_hits += w
        arch_hits += w * len(ids & eids)
    return min(_NOVELTY_MAX, _PAIR_W * pair_hits + _ARCH_W * arch_hits)


def featured_recency(window) -> dict:
    """id -> recency-weighted use count of the featured-roulette picks across the window (Phase N-5).
    Feeds featured.themed_roll's lottery damping (weight = 1/(1+count)); entries without a 'featured'
    field (pre-N-5 ledger lines) simply contribute nothing."""
    out: dict = {}
    for w, e in zip(_recency_weights(window or []), window or []):
        for fid in (e.get("featured") or []):
            fid = str(fid)
            out[fid] = out.get(fid, 0.0) + w
    return out


def payload_line(window, *, k: int = 3) -> str:
    """Compact 'recently overused' line for the map/compose prompt (empty string if nothing to say)."""
    if not window:
        return ""
    pairw: Counter = Counter()
    opw: Counter = Counter()
    for w, e in zip(_recency_weights(window), window):
        ids = sorted(str(i) for i in (e.get("archetype_ids") or []))
        if len(ids) >= 2:
            pairw[f"{ids[0]}+{ids[1]}"] += w
        for op in (e.get("top_ops") or []):
            opw[op] += w
    top_pairs = [p for p, _ in pairw.most_common(k)]
    top_ops = [o for o, _ in opw.most_common(k)]
    if not top_pairs and not top_ops:
        return ""
    return ("RECENTLY OVERUSED across the last few forges (prefer FRESH alternatives; do NOT just copy "
            f"these): archetype pairs [{', '.join(top_pairs)}]; ops [{', '.join(top_ops)}].")


def blueprint_status_line(window, *, k: int = 4) -> str:
    """Status-focused recency line for the blueprint brief (empty string if nothing to say)."""
    if not window:
        return ""
    statw: Counter = Counter()
    for w, e in zip(_recency_weights(window), window):
        for s in (e.get("statuses_used") or []):
            statw[s] += w
    top = [s for s, _ in statw.most_common(k)]
    if not top:
        return ""
    return ("\nRECENTLY OVERUSED statuses across recent forges (reach for DIFFERENT ones where the theme "
            f"allows): {', '.join(top)}.")
