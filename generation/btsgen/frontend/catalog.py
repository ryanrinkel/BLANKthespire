"""The metaphor-tagged archetype catalog — the heart of the MAP stage.

Loads `btsgen/data/archetypes.json` and RECOMPUTES each archetype's `buildable` flag against the
LIVE constrained contract (`mod/contract/VOCABULARY.md`) and the gap log (`VOCABULARY_GAPS.md`), so
the flag auto-flips as the vocabulary roadmap ships — an archetype is buildable iff every op it needs
is in the live vocabulary AND every gap it references is marked `done`. This is the "cards that work"
guardrail: the autonomous picker prefers buildable archetypes, so the front-end never quietly designs
a class around a mechanic the engine can't run.

The catalog is also the only thing the front-end WRITES: `append_vocab_gaps()` logs off-vocabulary
concepts the map stage surfaces, so the gap log stays a first-class roadmap input.
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

from ..contract import archetype_balance_note
from .dossier import Candidate

# Catalog ships as package data next to this module (btsgen/data/). Resolve via __file__ so it travels
# with editable + source installs; fall back to the repo root for non-editable installs.
_DATA = Path(__file__).resolve().parent.parent / "data" / "archetypes.json"


def _repo_root() -> Path:
    from ..class_forge import REPO
    return REPO


def _vocabulary_path() -> Path:
    """The CONSTRAINED mod contract vocabulary (what the engine can actually run). Prefer the env override
    the forge sets (BTSGEN_VOCABULARY), else mod/contract/VOCABULARY.md under the repo root."""
    env = os.environ.get("BTSGEN_VOCABULARY")
    if env and Path(env).exists():
        return Path(env)
    return _repo_root() / "mod" / "contract" / "VOCABULARY.md"


def _gap_log_path() -> Path:
    return _repo_root() / "VOCABULARY_GAPS.md"


_TOKEN_RE = re.compile(r"`([a-z][a-z0-9_]*)`")


def live_vocab_tokens() -> set[str]:
    """Every backtick-quoted token in the live VOCABULARY.md — the set of ops/statuses/conditions the
    engine actually supports. Buildability checks an archetype's ops against this."""
    try:
        text = _vocabulary_path().read_text(encoding="utf-8")
    except OSError:
        return set()
    return set(_TOKEN_RE.findall(text))


_GAP_HEADER_RE = re.compile(r"^###\s+(\d+)\.", re.MULTILINE)
_GAP_TITLE_RE = re.compile(r"^###\s+(\d+)\.\s*(.+?)\s*$", re.MULTILINE)

# Short function-words to ignore when comparing gap titles for near-duplicates. Kept small on purpose:
# aggressive stopword lists make more titles look alike, which risks the false-positive dedup the
# demand-signal rule warns is worse than a duplicate.
_GAP_TITLE_STOPWORDS = frozenset({
    "a", "an", "the", "of", "and", "or", "in", "on", "to", "for", "with", "by",
    "its", "as", "run", "track", "axis", "system",
})


def _normalize_gap_title(title: str) -> str:
    """Lowercase, drop punctuation, collapse whitespace — the canonical form title matching compares."""
    t = re.sub(r"[^a-z0-9\s]", " ", str(title).lower())
    return re.sub(r"\s+", " ", t).strip()


def _gap_title_tokens(title: str) -> set[str]:
    return {w for w in _normalize_gap_title(title).split() if w and w not in _GAP_TITLE_STOPWORDS}


def _gap_titles_match(a: str, b: str) -> bool:
    """Conservative near-duplicate test between two gap titles. True only on a strong signal:
    identical normalized form, one wholly contained in the other (length-guarded), or a high
    significant-token overlap. Deliberately biased toward MISSING dupes over inventing them."""
    na, nb = _normalize_gap_title(a), _normalize_gap_title(b)
    if not na or not nb:
        return False
    if na == nb:
        return True
    short, long = sorted((na, nb), key=len)
    if len(short) >= 10 and short in long:
        return True
    ta, tb = _gap_title_tokens(a), _gap_title_tokens(b)
    if not ta or not tb:
        return False
    shared = ta & tb
    # need at least two shared meaningful words AND a majority overlap (Jaccard >= 0.6)
    return len(shared) >= 2 and len(shared) / len(ta | tb) >= 0.6


def _parse_gap_titles(text: str) -> list[tuple[int, str]]:
    """(number, title) for every gap header in the log, in file order."""
    out: list[tuple[int, str]] = []
    for m in _GAP_TITLE_RE.finditer(text):
        try:
            out.append((int(m.group(1)), m.group(2).strip()))
        except ValueError:
            continue
    return out


def _credit_gap_demand(text: str, num: int, surfaced_by: str) -> str:
    """Record a demand-signal credit on gap `num` instead of appending a duplicate: insert/bump a
    `- **Demand:**` line inside that gap's block. The original counts as the first surfacing, so the
    first credit reads ×2. Idempotent in shape (later credits bump the count and append the source)."""
    lines = text.splitlines()
    hdr_i = next((i for i, ln in enumerate(lines)
                  if re.match(rf"^###\s+{num}\.", ln)), None)
    if hdr_i is None:
        return text
    end = next((j for j in range(hdr_i + 1, len(lines))
                if re.match(r"^###\s+\d+\.", lines[j])), len(lines))
    block = lines[hdr_i:end]
    src = surfaced_by.strip() or "staged front-end"
    dem_i = next((k for k in range(len(block))
                  if block[k].lstrip().startswith("- **Demand:**")), None)
    if dem_i is not None:
        m = re.search(r"×(\d+)", block[dem_i])
        newk = (int(m.group(1)) if m else 1) + 1
        block[dem_i] = re.sub(r"×\d+", f"×{newk}", block[dem_i]).rstrip() + f"; {src}"
    else:
        block.insert(1, f"- **Demand:** ×2 — re-surfaced by: {src}")
    lines[hdr_i:end] = block
    return "\n".join(lines) + ("\n" if text.endswith("\n") else "")


def gap_status() -> dict[int, str]:
    """Map each VOCABULARY_GAPS.md gap number -> its Status: value (captured/planned/building/done/rejected).
    A gap with no parseable status is treated as 'captured'."""
    try:
        text = _gap_log_path().read_text(encoding="utf-8")
    except OSError:
        return {}
    out: dict[int, str] = {}
    # split on the gap headers, keep the number with the body that follows it
    parts = re.split(r"^###\s+(\d+)\.", text, flags=re.MULTILINE)
    # parts = [preamble, num1, body1, num2, body2, ...]
    for i in range(1, len(parts) - 1, 2):
        try:
            num = int(parts[i])
        except ValueError:
            continue
        body = parts[i + 1]
        m = re.search(r"\*\*Status:\*\*\s*\**\s*([a-z]+)", body, re.IGNORECASE)
        out[num] = (m.group(1).lower() if m else "captured")
    return out


def _gap_ref_number(ref: str) -> int | None:
    m = re.search(r"#(\d+)", str(ref))
    return int(m.group(1)) if m else None


def resolve_buildability(ops, gap_refs, live_tokens: set[str], gaps: dict[int, str]) -> tuple[bool, list[str]]:
    """An archetype/candidate is buildable iff every op it needs is in the live vocabulary AND every gap it
    references is `done`. Returns (buildable, blocking_reasons)."""
    reasons: list[str] = []
    for op in ops or []:
        if op not in live_tokens:
            reasons.append(f"op '{op}' not in live vocabulary")
    for ref in gap_refs or []:
        num = _gap_ref_number(ref)
        if num is None:
            continue
        status = gaps.get(num, "captured")
        if status != "done":
            reasons.append(f"gap #{num} is '{status}' (needs vocab)")
    return (not reasons), reasons


@dataclass
class ArchetypeEntry:
    id: str
    name: str
    description: str
    metaphors: list[str]
    ops: list[str]
    class_kind: str
    gap_refs: list[str]
    buildable: bool = True
    block_reasons: list[str] = field(default_factory=list)
    balance_note: str = ""
    # Strategy LEANS (aggro/control/combo): the game plans this engine naturally serves. Hints for the
    # compose stage's strategic_lines — an archetype leans toward strategies but never owns one.
    leans: list[str] = field(default_factory=list)


# class_kind precedence when a candidate fuses two archetypes: a special pool dominates a normal one.
_KIND_PRIORITY = {"orb": 3, "summon": 2, "status": 1, "normal": 0}

# O-3: length cap for a strategic line's optional free-text "idiom" (texture tag). Free text, never
# enum-validated — a few words is plenty; we cap rather than reject (7B-safe).
IDIOM_MAXLEN = 32


class ArchetypeCatalog:
    def __init__(self, entries: list[ArchetypeEntry]) -> None:
        self.entries = entries
        self.by_id = {e.id: e for e in entries}

    # -- the MAP-stage prompt block (the catalog the LLM matches clusters against) -----------------
    def prompt_block(self) -> str:
        lines: list[str] = []
        for e in self.entries:
            tag = "BUILDABLE" if e.buildable else f"NEEDS-VOCAB ({'; '.join(e.block_reasons) or 'gap'})"
            lines.append(f"- {e.id} | {e.name} [{tag}] (class_kind: {e.class_kind})")
            lines.append(f"    engine: {e.description}")
            lines.append(f"    metaphors: {', '.join(e.metaphors)}")
            if e.leans:
                lines.append(f"    leans: {', '.join(e.leans)}")
            if e.balance_note:
                lines.append(f"    balance: {e.balance_note}")
        return "\n".join(lines)

    def buildable_ids(self) -> set[str]:
        return {e.id for e in self.entries if e.buildable}

    # -- turn a raw compose-stage candidate dict into a hydrated Candidate -------------------------
    def hydrate_candidate(self, raw: dict) -> Candidate:
        ids = list(raw.get("archetype_ids") or raw.get("archetypes") or [])[:2]
        known = [self.by_id[i] for i in ids if i in self.by_id]
        unknown = [i for i in ids if i not in self.by_id]
        descs = [self.by_id[i].description if i in self.by_id else "" for i in ids]
        # class_kind = the dominant pool kind among the (known) archetypes
        class_kind = "normal"
        if known:
            class_kind = max((e.class_kind for e in known), key=lambda k: _KIND_PRIORITY.get(k, 0))
        # buildable = all referenced archetypes buildable AND no unknown ids
        all_buildable = bool(known) and all(e.buildable for e in known) and not unknown
        gap_refs: list[str] = []
        for e in known:
            gap_refs += [g for g in e.gap_refs if g not in gap_refs]
        block_reasons: list[str] = []
        for e in known:
            if not e.buildable:
                block_reasons.append(f"{e.id}: {'; '.join(e.block_reasons)}")
        for i in unknown:
            block_reasons.append(f"unknown archetype id '{i}'")
        try:
            max_hp = int(raw.get("suggested_max_hp", raw.get("max_hp", 72)) or 72)
        except (TypeError, ValueError):
            max_hp = 72
        # strategic lines (normalized): the 2-3 game plans the pool must support; validated upstream.
        # O-3: an optional free-text "idiom" (texture tag for how the line FEELS) rides along — never
        # enum-validated, just length-capped here (7B-safe: we cap, we never reject over it).
        lines: list[dict] = []
        for l in (raw.get("strategic_lines") or []):
            if not isinstance(l, dict):
                continue
            s = str(l.get("strategy", "")).strip().lower()
            if s:
                lines.append({"strategy": s, "line": str(l.get("line", "")).strip(),
                              "win_condition": str(l.get("win_condition", "")).strip(),
                              "idiom": str(l.get("idiom", "")).strip()[:IDIOM_MAXLEN]})
        return Candidate(
            name=str(raw.get("name", "")).strip(),
            fantasy=str(raw.get("fantasy", raw.get("description", ""))).strip(),
            archetype_ids=list(ids),
            archetype_descs=descs,
            core_loop=str(raw.get("core_loop", "")).strip(),
            weakness=str(raw.get("weakness", "")).strip(),
            tension=str(raw.get("tension", "")).strip(),
            strategic_lines=lines,
            class_kind=class_kind,
            suggested_max_hp=max(60, min(95, max_hp)),
            buildable=all_buildable,
            gap_refs=gap_refs,
            block_reasons=block_reasons,
        )


def load_catalog(path: Path | None = None) -> ArchetypeCatalog:
    """Read archetypes.json and recompute every entry's buildability against the live vocabulary + gap log."""
    p = path or _DATA
    if not p.exists():
        # non-editable install fallback: package data under the repo
        alt = _repo_root() / "generation" / "btsgen" / "data" / "archetypes.json"
        p = alt if alt.exists() else p
    raw = json.loads(p.read_text(encoding="utf-8"))
    live = live_vocab_tokens()
    gaps = gap_status()
    entries: list[ArchetypeEntry] = []
    for a in raw.get("archetypes", []):
        ops = list((a.get("vocabulary") or {}).get("ops") or [])
        kind = str((a.get("vocabulary") or {}).get("class_kind", "normal")).strip().lower() or "normal"
        gap_refs = list(a.get("gap_refs") or [])
        buildable, reasons = resolve_buildability(ops, gap_refs, live, gaps)
        entries.append(ArchetypeEntry(
            id=str(a["id"]), name=str(a.get("name", a["id"])),
            description=str(a.get("description", "")), metaphors=list(a.get("metaphors") or []),
            ops=ops, class_kind=kind, gap_refs=gap_refs, buildable=buildable, block_reasons=reasons,
            # Per-archetype balance note lives in the single design-heuristics source, keyed by id —
            # NOT in archetypes.json (which keeps only the mechanical fields).
            balance_note=archetype_balance_note(str(a["id"])),
            leans=[str(s).strip().lower() for s in (a.get("leans") or [])],
        ))
    return ArchetypeCatalog(entries)


def append_vocab_gaps(entries: list[dict]) -> int:
    """Append off-vocabulary concepts the map stage surfaced to VOCABULARY_GAPS.md as `captured` blocks.
    Each entry: {title, surfaced_by, fantasy, sketch}. Returns the number of NEW gaps appended.

    Near-duplicate titles do NOT append a fresh block: they credit a demand-count on the existing gap
    instead (the manual #1/#30/#32/#33 pattern, automated). The match test is conservative on purpose —
    suppressing a genuinely new gap is worse than logging a duplicate."""
    if not entries:
        return 0
    path = _gap_log_path()
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return 0
    existing_titles = _parse_gap_titles(text)  # (num, title), grows as we append within this batch
    nums = [n for n, _ in existing_titles]
    next_num = (max(nums) + 1) if nums else 1
    blocks: list[str] = []
    for e in entries:
        title = str(e.get("title", "")).strip() or "Untitled gap"
        surfaced = str(e.get("surfaced_by", "staged front-end")).strip()
        match = next((n for n, t in existing_titles if _gap_titles_match(title, t)), None)
        if match is not None:
            text = _credit_gap_demand(text, match, surfaced)
            continue
        block = (
            f"\n### {next_num}. {title}\n"
            f"- **Surfaced by:** {surfaced or 'staged front-end'}\n"
            f"- **Fantasy it serves:** {str(e.get('fantasy', '')).strip()}\n"
            f"- **Mechanic sketch:** {str(e.get('sketch', '')).strip()}\n"
            f"- **Buildable today?** No — surfaced as off-vocabulary by the map stage.\n"
            f"- **Priority:** unset (triage).\n"
            f"- **Status:** captured\n"
        )
        blocks.append(block)
        existing_titles.append((next_num, title))  # so a later dup in THIS batch dedups too
        next_num += 1
    path.write_text(text.rstrip() + "\n" + "".join(blocks), encoding="utf-8")
    return len(blocks)
