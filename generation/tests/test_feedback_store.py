"""Offline tests for feedback_store — the similarity-retrieval (RAG-ish) feedback layer.

Run:  uv run python -m tests.test_feedback_store     (from generation/)
Exits nonzero on any failure. Covers load_entries() (multi-source union + de-dupe + note
sanitization), retrieve() ranking, similar_feedback_section() rendering + its guards, and the
user_brief / blueprint-brief fold-in points.
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

from btsgen import contract, feedback_store, paths

_PASS = 0
_FAIL = 0


def check(cond: bool, msg: str) -> None:
    global _PASS, _FAIL
    if cond:
        _PASS += 1
    else:
        _FAIL += 1
        print(f"  FAIL: {msg}")


def _entry(card_id: str, category: str, note: str = "", *, name: str | None = None,
           effects: list | None = None, character: str = "test_class", ts: str = "t0") -> str:
    return json.dumps({
        "ts": ts, "card_id": card_id,
        "name": name or card_id.replace("_", " ").title(),
        "character": character, "category": category,
        "card": {"effects": effects if effects is not None else [{"op": "damage", "amount": 6}]},
        "note": note,
    })


def main() -> int:
    real_file, real_extra = paths.FEEDBACK_FILE, paths.FEEDBACK_EXTRA
    try:
        with tempfile.TemporaryDirectory() as td:
            paths.FEEDBACK_FILE = Path(td) / "curated.jsonl"
            paths.FEEDBACK_EXTRA = [Path(td) / "live.jsonl"]

            print("load_entries — empty / malformed / union / de-dupe / sanitization:")
            check(feedback_store.load_entries() == [], "no files -> no entries")
            check(feedback_store.similar_feedback_section("poison venom") == "",
                  "no entries -> empty section")

            dup = _entry("poison_fang", "great", "love the venom ramp", ts="t1")
            paths.FEEDBACK_FILE.write_text("not json\n" + dup + "\n")
            paths.FEEDBACK_EXTRA[0].write_text(dup + "\n" + _entry(
                "iron_wall", "overpowered", "40 block  for \x01\x02one\nenergy", ts="t2",
                effects=[{"op": "block", "amount": 40}]) + "\n")
            entries = feedback_store.load_entries()
            check(len(entries) == 2, f"union de-dupes the pulled copy (got {len(entries)})")
            note = next(d["note"] for d in entries if d["card_id"] == "iron_wall")
            check("\x01" not in note and "\n" not in note and "40 block for one energy" == note,
                  f"notes are sanitized (got {note!r})")
            long = _entry("chatter", "confusing", "x" * 999, ts="t3")
            paths.FEEDBACK_EXTRA[0].write_text(paths.FEEDBACK_EXTRA[0].read_text() + long + "\n")
            entries = feedback_store.load_entries()
            check(max(len(d["note"]) for d in entries) <= 200, "notes are length-capped")

            print("retrieve — ranks by topical overlap:")
            hits = feedback_store.retrieve("a poison venom ramp attack", k=2)
            check(bool(hits) and hits[0]["card_id"] == "poison_fang",
                  f"venom query retrieves the venom rating first (got {[d['card_id'] for d in hits]})")
            check(all(d["card_id"] != "iron_wall" for d in hits),
                  "an unrelated block rating is not padded in")
            check(feedback_store.retrieve("zzz qqq unrelated nonsense") == [],
                  "no topical overlap -> no hits")

            print("similar_feedback_section — rendering:")
            s = feedback_store.similar_feedback_section("poison venom fang")
            check("PLAYER FEEDBACK ON SIMILAR PAST DESIGNS" in s, "section header renders")
            check('[player: "love the venom ramp"]' in s, "great note rides the line")
            s2 = feedback_store.similar_feedback_section("huge block wall of iron")
            check("iron_wall" in s2 and "[player flag: overpowered" in s2,
                  "flags render as anti-examples")

            print("fold-in points — card brief + blueprint brief:")
            brief = contract.Brief(card_type="attack", theme="a venom fang poison strike")
            ub = contract.user_brief(brief)
            check("PLAYER FEEDBACK ON SIMILAR PAST DESIGNS" in ub and "poison_fang" in ub,
                  "user_brief folds in similar ratings")
            check(ub.rstrip().endswith("Return only the JSON object."),
                  "user_brief still ends with the output instruction")
            bare = contract.user_brief(contract.Brief(card_type="skill", theme="zzz qqq nonsense"))
            check("PLAYER FEEDBACK" not in bare, "no relevant ratings -> brief untouched")

            from btsgen.class_forge import ClassBrief, _BlueprintContract
            bp = _BlueprintContract(triad=False).user_brief(ClassBrief(concept="a venomous poison snake fang duelist"))
            check("PLAYER FEEDBACK ON SIMILAR PAST DESIGNS" in bp,
                  "blueprint concept brief folds in similar ratings")

            print("feedback_section (recency window) reads both sources:")
            s = contract.feedback_section()
            check("iron_wall" in s and "poison_fang" in s,
                  "recency section sees curated + live entries")
    finally:
        paths.FEEDBACK_FILE, paths.FEEDBACK_EXTRA = real_file, real_extra
    print(f"\n{_PASS} passed, {_FAIL} failed")
    return 1 if _FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
