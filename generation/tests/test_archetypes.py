"""Offline tests for btsgen/data/archetypes.json — the metaphor-tagged archetype catalog (W0.7). No API key needed.

Run:  uv run python -m tests.test_archetypes     (from generation/)
Exits nonzero on any failure. Covers: no two archetypes share a name / description / metaphor string (and no
archetype repeats a metaphor), the file's `buildable` flag agrees with the catalog's live recomputation (every
`buildable:false` names an open gap in VOCABULARY_GAPS.md, every `buildable:true` has none), the optional
`mechanic_kind` field only takes values from the fixed set harness_v2._pool_kind understands, the copy format
('Theme / mechanic' names; one short player-facing description with no op syntax; model-only `build_notes`), and
the `base_synergies` shape plus its path into the MAP and blueprint prompts.
"""
from __future__ import annotations

import json
import re
import sys

from btsgen.class_forge import point_btsgen_at_mod_contract

point_btsgen_at_mod_contract()

from btsgen.frontend import catalog as C  # noqa: E402
from btsgen.frontend import load_catalog  # noqa: E402

_PASS = 0
_FAIL = 0

# The base-vocab subsystems an archetype may declare it needs (W0.9). Kept in lockstep with the `needs` tags the
# exemplar pool uses (orb/status/summon come from class_kind, not from here) and with class_forge's pruning keys.
MECHANIC_KINDS = frozenset({"forge", "balance", "discard", "token", "transform", "exhaust", "retain", "rampage",
                            "tags", "purge"})

# The archetypes whose identity IS a base-vocab subsystem, and the kind each must declare.
EXPECTED_MECHANIC_KIND = {
    "forge_ramp": "forge", "balance_gauge": "balance", "madness_discard": "discard", "token_conjurer": "token",
    "metamorph": "transform", "exhaust_pyre": "exhaust", "retain_hold": "retain", "rampage_grow": "rampage",
    "strike_synergy": "tags", "ascetic_purge": "purge",
}

# Top-level fields whose values are shared by design (strategy leans, gap ids, the subsystem kind).
_SHARED_OK = frozenset({"leans", "gap_refs", "mechanic_kind", "buildable", "vocabulary"})


def check(cond: bool, msg: str) -> None:
    global _PASS, _FAIL
    if cond:
        _PASS += 1
    else:
        _FAIL += 1
        print(f"  FAIL: {msg}")


def _raw() -> list[dict]:
    return json.loads(C._DATA.read_text(encoding="utf-8"))["archetypes"]


# --------------------------------------------------------------- string fields are distinct
def test_no_shared_strings() -> None:
    print("archetypes.json: no two archetypes share a string field value (name / description / metaphor):")
    owners: dict[tuple[str, str], list[str]] = {}
    for a in _raw():
        seen_here: set[str] = set()
        for key, val in a.items():
            if key in _SHARED_OK:
                continue
            vals = [val] if isinstance(val, str) else [v for v in val if isinstance(v, str)] if isinstance(val, list) else []
            for v in vals:
                norm = v.strip().lower()
                check(norm not in seen_here, f"{a['id']}: '{v}' appears twice within the same archetype")
                seen_here.add(norm)
                owners.setdefault((key, norm), []).append(a["id"])
    dupes = {k: v for k, v in owners.items() if len(v) > 1}
    check(not dupes, f"shared string values across archetypes: {dupes}")
    # the five pairs the remediation plan called out are gone for good
    for phrase in ("the blade reforged", "the rising storm", "momentum", "the curse", "the crimson tithe"):
        holders = [ids for (key, norm), ids in owners.items() if key == "metaphors" and norm == phrase]
        check(all(len(h) == 1 for h in holders), f"metaphor '{phrase}' is still shared: {holders}")


# --------------------------------------------------------------- buildable flags tell the truth
def test_buildable_flags_match_live_gaps() -> None:
    print("archetypes.json: `buildable` agrees with the live gap log (false <=> names an open gap):")
    cat = load_catalog()
    gaps = C.gap_status()
    check(bool(gaps), "VOCABULARY_GAPS.md parsed at least one gap status")
    for a in _raw():
        e = cat.by_id.get(a["id"])
        check(e is not None, f"catalog loaded '{a['id']}'")
        if e is None:
            continue
        flag = bool(a.get("buildable", True))
        check(flag == e.buildable,
              f"'{a['id']}' file says buildable={flag} but the live recomputation says {e.buildable} ({e.block_reasons})")
        if not flag:
            open_refs = [r for r in a.get("gap_refs", []) if gaps.get(C._gap_ref_number(r) or -1, "captured") != "done"]
            check(bool(open_refs), f"'{a['id']}' is buildable:false but names no open (non-done) gap: {a.get('gap_refs')}")
    # the four W0.7 flips: their gaps (#21, #6, #1, #16) are done, so the file must say true
    for aid in ("reaper_lifesteal", "countdown_ripen", "balance_gauge", "token_conjurer"):
        raw = next(a for a in _raw() if a["id"] == aid)
        check(raw.get("buildable") is True, f"'{aid}' buildable flag flipped to true")
        check(cat.by_id[aid].buildable, f"'{aid}' resolves BUILDABLE live: {cat.by_id[aid].block_reasons}")


# --------------------------------------------------------------- mechanic_kind
def test_mechanic_kind_values() -> None:
    print("archetypes.json: `mechanic_kind` is optional, from the fixed set, and loaded by the catalog:")
    cat = load_catalog()
    for a in _raw():
        mk = a.get("mechanic_kind")
        if mk is None:
            check(cat.by_id[a["id"]].mechanic_kind == "", f"'{a['id']}' has no mechanic_kind -> catalog entry is ''")
            continue
        check(isinstance(mk, str) and mk in MECHANIC_KINDS, f"'{a['id']}' mechanic_kind '{mk}' not in {sorted(MECHANIC_KINDS)}")
        check(cat.by_id[a["id"]].mechanic_kind == mk, f"catalog carries mechanic_kind for '{a['id']}'")
    for aid, kind in EXPECTED_MECHANIC_KIND.items():
        check(cat.by_id[aid].mechanic_kind == kind, f"'{aid}' declares mechanic_kind '{kind}'")
    # class-kind archetypes are dealt by class_kind, not mechanic_kind; battle_smith's ops are base vocab
    for aid in ("orb_channel", "slot_machine", "summon_swarm", "status_signature", "battle_smith"):
        check(cat.by_id[aid].mechanic_kind == "", f"'{aid}' has no mechanic_kind")


# --------------------------------------------------------------- ops are live vocabulary tokens
def test_ops_are_live_tokens() -> None:
    print("archetypes.json: every `vocabulary.ops` token exists in the live VOCABULARY.md:")
    live = C.live_vocab_tokens()
    check(len(live) > 50, f"live vocabulary parsed ({len(live)} tokens)")
    for a in _raw():
        ops = (a.get("vocabulary") or {}).get("ops") or []
        check(bool(ops), f"'{a['id']}' lists at least one op")
        missing = [o for o in ops if o not in live]
        check(not missing, f"'{a['id']}' ops not in the live vocabulary: {missing}")


# --------------------------------------------------------------- copy format (player-facing vs model-only)
DESC_MAX = 150
_OP_SYNTAX = re.compile(r"[`{}]")


def test_copy_format() -> None:
    print("archetypes.json: names are 'Theme / mechanic', descriptions are one short player-facing line:")
    cat = load_catalog()
    for a in _raw():
        name, desc = a.get("name", ""), a.get("description", "")
        check(" / " in name, f"'{a['id']}' name '{name}' doesn't follow 'Theme / mechanic'")
        check(0 < len(desc) <= DESC_MAX, f"'{a['id']}' description is {len(desc)} chars (1-{DESC_MAX})")
        check(not _OP_SYNTAX.search(desc), f"'{a['id']}' description carries op syntax (backticks/braces): {desc}")
        check(desc[:1].isupper(), f"'{a['id']}' description starts lowercase: {desc}")
        notes = a.get("build_notes")
        check(notes is None or (isinstance(notes, str) and notes.strip()), f"'{a['id']}' build_notes present but empty")
        check(cat.by_id[a["id"]].build_notes == (notes or "").strip(), f"catalog carries build_notes for '{a['id']}'")
    # the MAP prompt shows build notes on their own line, never folded into `engine:`
    block = cat.prompt_block()
    check("    build: " in block, "prompt_block renders a build: line")
    for line in block.splitlines():
        if line.startswith("    engine: "):
            check(len(line) - len("    engine: ") <= DESC_MAX, f"engine line too long: {line[:80]}")


# --------------------------------------------------------------- base-game synergies
_KINDS = frozenset({"relic", "potion", "colorless"})
_TIERS = frozenset({"core", "support"})


def test_base_synergies() -> None:
    print("archetypes.json: `base_synergies` are well-formed and reach the prompts:")
    cat = load_catalog()
    for a in _raw():
        bs = a.get("base_synergies")
        check(isinstance(bs, dict), f"'{a['id']}' has base_synergies")
        if not isinstance(bs, dict):
            continue
        pieces = bs.get("pieces") or []
        check(bool(pieces), f"'{a['id']}' names at least one base-game piece")
        has_core = any(p.get("tier") == "core" for p in pieces)
        seen: set[str] = set()
        for p in pieces + (bs.get("avoid") or []):
            key = f"{p.get('kind')}:{p.get('id')}"
            check(p.get("kind") in _KINDS, f"'{a['id']}' piece {key} has an unknown kind")
            check(bool(p.get("id")) and bool(p.get("name")) and bool(p.get("why")), f"'{a['id']}' piece {key} missing id/name/why")
            check(key not in seen, f"'{a['id']}' lists {key} twice")
            seen.add(key)
        for p in pieces:
            check(p.get("tier") in _TIERS, f"'{a['id']}' piece {p.get('id')} tier '{p.get('tier')}' not in {sorted(_TIERS)}")
        check(bool(bs.get("strengths")) and bool(bs.get("weaknesses")), f"'{a['id']}' lists strengths and weaknesses")
        e = cat.by_id[a["id"]]
        # Summon / Balance have only support pieces (the shared pool barely serves them): no core line, by design.
        check(bool(e.synergy_line()) == has_core, f"catalog renders a core synergy line for '{a['id']}' iff it has core pieces")
        check(("base-game synergies: " in e.notes_for_blueprint()) == has_core,
              f"'{a['id']}' blueprint notes carry the synergy line iff it has core pieces")
    # a hydrated candidate carries the notes, parallel to its ids (the blueprint prompt reads them)
    c = cat.hydrate_candidate({"name": "T", "fantasy": "t", "archetype_ids": ["battle_smith", "retain_hold"]})
    check(len(c.archetype_notes) == 2 and "Apotheosis" in c.archetype_notes[0],
          "hydrated candidate carries per-archetype notes (Battle-smith names the Apotheosis relic)")


def main() -> int:
    test_no_shared_strings()
    test_buildable_flags_match_live_gaps()
    test_mechanic_kind_values()
    test_ops_are_live_tokens()
    test_copy_format()
    test_base_synergies()
    print(f"\n{_PASS} passed, {_FAIL} failed")
    return 1 if _FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
