"""Player-feedback store + similarity retrieval — the RAG-ish layer of the feedback loop.

Entries are the JSONL records the website / in-game rating buttons append (see web/forge.py
append_card_feedback — that shape is the contract). Two kinds of source, unioned and de-duped:
  paths.FEEDBACK_FILE    the curated, git-tracked log (generation/feedback/card_feedback.jsonl)
  paths.FEEDBACK_EXTRA   live append-only logs (the droplet's web/card_feedback.jsonl), so website
                         ratings steer the NEXT forge with no manual pull-into-git step

Retrieval is deliberately dependency-free: token-overlap scoring with IDF weights over the entry's
name/note/effect-ops text. At feedback-log scale (hundreds to a few thousand entries) that ranks
"similar past designs" plenty well, costs nothing, and runs identically on the droplet and offline.
Swap in embeddings later behind the same retrieve() surface if the corpus ever outgrows it.

Player notes are free text typed on a public website, so they are sanitized (control chars stripped,
whitespace collapsed, length-capped) before they ride any prompt. Everything here is best-effort:
a missing/corrupt log yields empty results, never an error — feedback must never break a forge.
"""
from __future__ import annotations

import json
import math
import re
from collections import Counter
from pathlib import Path

from . import paths

# Canonical flag categories -> the human complaint woven into anti-example lines. Single source of
# truth: contract.py re-exports this for its prompt, and web/forge.py derives its category whitelist
# from it (via contract), so the website and the generator can never drift.
_FEEDBACK_LABELS = {
    "doesnt_work": "did not work as written",
    "overpowered": "overpowered",
    "underpowered": "underpowered",
    "off_theme": "did not match its class fantasy",
    "confusing": "confusing card text",
}

_MAX_NOTE_LEN = 200
_WORD_RE = re.compile(r"[a-z0-9]+")
# Tokens too generic to signal similarity in this domain (card-frame words + tiny glue words).
_STOP = {
    "the", "and", "for", "with", "your", "you", "that", "this", "card", "cards", "class",
    "damage", "deal", "gain", "when", "then", "each", "turn", "per", "one", "all", "self",
    "enemy", "amount", "target", "effects", "not", "its",
}

# load_entries() cache: (per-source (path, mtime, size) tuple) -> parsed entries. Sources are tiny
# JSONL files; the stat-based key means live appends (the website log) invalidate automatically.
_cache: dict = {"key": None, "entries": []}


def _sources() -> list[Path]:
    return [paths.FEEDBACK_FILE, *paths.FEEDBACK_EXTRA]


def _sanitize_note(note) -> str:
    """Free text from the website's 'why' box: strip control characters (no newline smuggling into
    the prompt), collapse whitespace, cap length."""
    s = re.sub(r"[\x00-\x1f\x7f]+", " ", str(note or ""))
    s = re.sub(r"\s+", " ", s).strip()
    return s[:_MAX_NOTE_LEN]


def _cache_key() -> tuple:
    parts = []
    for p in _sources():
        try:
            st = p.stat()
            parts.append((str(p), st.st_mtime_ns, st.st_size))
        except OSError:
            parts.append((str(p), None, None))
    return tuple(parts)


def load_entries() -> list[dict]:
    """All feedback entries across sources, oldest-first, notes sanitized, exact repeats de-duped
    (the curated git file is a pulled copy of the live log, so overlap is the normal case)."""
    key = _cache_key()
    if _cache["key"] == key:
        return _cache["entries"]
    entries: list[dict] = []
    seen: set[tuple] = set()
    for src in _sources():
        try:
            text = src.read_text(encoding="utf-8")
        except OSError:
            continue
        for line in text.splitlines():
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not (isinstance(d, dict) and d.get("category")):
                continue
            d = dict(d)
            d["note"] = _sanitize_note(d.get("note"))
            k = (d.get("ts"), d.get("card_id"), d.get("category"), d.get("name"), d["note"])
            if k in seen:
                continue
            seen.add(k)
            entries.append(d)
    _cache["key"] = key
    _cache["entries"] = entries
    return entries


# --- similarity retrieval -------------------------------------------------------------------------

def _walk_effects(effects, out: list) -> None:
    for e in effects if isinstance(effects, list) else []:
        if not isinstance(e, dict):
            continue
        for f in ("op", "status", "status_name", "orb", "trigger", "scale", "tag", "pole",
                  "summon_name", "card_id", "kind"):
            v = e.get(f)
            if v:
                out.append(str(v))
        w = e.get("when")
        if isinstance(w, dict):
            out.extend(str(w.get(f)) for f in ("kind", "status") if w.get(f))
        _walk_effects(e.get("effects"), out)


def _entry_text(d: dict) -> str:
    card = d.get("card") if isinstance(d.get("card"), dict) else {}
    bits = [d.get("name", ""), str(d.get("card_id", "")).replace(":", " "),
            d.get("character", ""), d.get("note", ""), d.get("element_kind", ""),
            card.get("type", ""), card.get("description", "")]
    _walk_effects(card.get("effects"), bits)
    return " ".join(str(b) for b in bits if b)


def _tokens(text: str) -> set[str]:
    return {t for t in _WORD_RE.findall(str(text or "").lower())
            if len(t) > 2 and t not in _STOP}


def retrieve(query: str, k: int = 6) -> list[dict]:
    """Top-k feedback entries most similar to `query` (a brief/theme/concept text). IDF-weighted
    token overlap; ties break newest-first. Weak matches (under a quarter of the best score) are
    dropped rather than padded — an empty result is a valid answer."""
    entries = load_entries()
    q = _tokens(query)
    if not entries or not q:
        return []
    toks = [_tokens(_entry_text(d)) for d in entries]
    df: Counter = Counter(t for ts in toks for t in set(ts))
    n = len(entries)
    scored = []
    for i, (d, ts) in enumerate(zip(entries, toks)):
        shared = q & ts
        if not shared:
            continue
        scored.append((sum(math.log1p(n / df[t]) for t in shared), i, d))
    if not scored:
        return []
    scored.sort(key=lambda s: (-s[0], -s[1]))
    floor = scored[0][0] * 0.25
    return [d for score, _i, d in scored[:k] if score >= floor]


# --- prompt rendering -------------------------------------------------------------------------------

def render_section(entries: list[dict], *, header: str) -> str:
    """The prompt block for a set of feedback entries: 'great' ratings as examples to emulate,
    everything else as anti-examples with the player's complaint (and their own note, when typed)
    attached. Empty string for no entries."""
    good, bad = [], []
    for d in entries:
        card = d.get("card") if isinstance(d.get("card"), dict) else {}
        effects = json.dumps(card.get("effects", []), separators=(",", ":"))
        line = f"- {d.get('name', '?')} ({d.get('card_id', '?')}, class {d.get('character', '?')}): {effects}"
        note = _sanitize_note(d.get("note"))
        if d.get("category") == "great":
            good.append(line + (f'  [player: "{note}"]' if note else ""))
        else:
            complaint = _FEEDBACK_LABELS.get(str(d.get("category")), str(d.get("category")))
            if note:
                complaint += f' -- "{note}"'
            bad.append(f"{line}  [player flag: {complaint}]")
    if not good and not bad:
        return ""
    out = [f"\n# {header}"]
    if good:
        out.append("Players rated these GREAT — emulate their feel:\n" + "\n".join(good))
    if bad:
        out.append("Players FLAGGED these — anti-examples; do not repeat the flagged problem:\n"
                   + "\n".join(bad))
    return "\n".join(out) + "\n"


def similar_feedback_section(query: str, *, k: int = 6) -> str:
    """Retrieval-flavored prompt block: past player ratings most similar to this brief/concept.
    Empty string when nothing relevant exists. Never raises — feedback must never break a forge."""
    try:
        hits = retrieve(query, k=k)
        if not hits:
            return ""
        return render_section(
            hits, header="PLAYER FEEDBACK ON SIMILAR PAST DESIGNS "
                         "(in-game ratings of past forges; emulate the GREAT, avoid the flagged)")
    except Exception:
        return ""
