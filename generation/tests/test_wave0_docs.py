"""Wave 0 (VOCAB_GAP_REMEDIATION_PLAN W0.1 / W0.2 / W0.3 / W0.10) — the prompt-facing prose no longer tells the
model that supported features don't exist. Offline, no API key.

Run:  uv run python -m tests.test_wave0_docs       (from generation/)
Exits nonzero on any failure. Pure doc-contract checks against the three mod/contract markdown sources the
harness injects into its prompts:

- DESIGN_HEURISTICS.md: no heuristic block names the prototype ops (`from_state` / `multi` / `fuse`) or the
  stale "no whenever-you-lose-HP trigger" note (the `on_hp_lost` hook has existed since gap #9 / Phase P), and
  every archetype id in archetypes.json has a non-empty `archetype-note` (the MAP stage's `balance:` line).
- VOCABULARY.md: the stale "rares need ops not yet supported" line is gone, and the `on_discard` row carries the
  base-game caveat (it fires only from this class's own `discard`/`scry` ops — EffectRunner.FireOnDiscardFor).
- RELIC_VOCABULARY.md: no truncated "There is no" sentence.
"""
from __future__ import annotations

import json
import re
import sys

from btsgen.class_forge import point_btsgen_at_mod_contract

point_btsgen_at_mod_contract()

from btsgen import contract, paths                              # noqa: E402
from btsgen.class_forge import RELIC_VOCAB                      # noqa: E402
from btsgen.frontend import catalog as C                        # noqa: E402

_PASS = 0
_FAIL = 0

_HEURISTIC_KEYS = ("rarity_ladder", "reprint_section", "relic_forms", "loop_discipline", "hp_economy")
_PROTOTYPE_WORDS = ("from_state", "multi", "fuse")
_STALE_HP_PHRASE = 'whenever you lose HP" trigger'


def check(cond: bool, msg: str) -> None:
    global _PASS, _FAIL
    if cond:
        _PASS += 1
    else:
        _FAIL += 1
        print(f"  FAIL: {msg}")


def _archetype_ids() -> list[str]:
    raw = json.loads(C._DATA.read_text(encoding="utf-8"))
    return [str(a["id"]) for a in raw.get("archetypes", [])]


def _heuristic_text() -> str:
    return paths.DESIGN_HEURISTICS.read_text(encoding="utf-8")


def test_heuristics_no_prototype_residue() -> None:
    print("DESIGN_HEURISTICS.md heuristic blocks name no prototype ops:")
    for key in _HEURISTIC_KEYS:
        block = contract._heuristic(key)
        check(bool(block.strip()), f"heuristic block '{key}' must exist and be non-empty")
        for word in _PROTOTYPE_WORDS:
            check(word not in block, f"heuristic '{key}' still names prototype op '{word}'")
        check(_STALE_HP_PHRASE not in block, f"heuristic '{key}' still carries the stale on_hp_lost negation")
    text = _heuristic_text()
    check(_STALE_HP_PHRASE not in text,
          "DESIGN_HEURISTICS.md still says there is no \"whenever you lose HP\" trigger (on_hp_lost exists)")
    # The rarity ladder and reprint rule now point at the mod's real compositional tools.
    ladder = contract._heuristic("rarity_ladder")
    for tool in ("`when`", "`scale`", "`hits`", "`add_trigger`", "`add_card`", "X-cost", "`grow`", "`transform_card`"):
        check(tool in ladder, f"rarity_ladder should name the real tool {tool}")
    reprint = contract._heuristic("reprint_section")
    for tool in ("`when`", "`scale`", "`hits`", "`add_trigger`", "`add_card`", "X-cost", "`grow`", "`transform_card`"):
        check(tool in reprint, f"reprint_section should name the real tool {tool}")


def test_relic_forms_menu() -> None:
    print("relic_forms lists the Bleed payoff (on_hp_lost) and Class-kind boon (forge/channel_orb/summon) forms:")
    forms = contract.relic_forms()
    check("Bleed payoff" in forms, "relic_forms must offer a **Bleed payoff** form")
    check("`on_hp_lost`" in forms, "Bleed payoff form must hook `on_hp_lost`")
    check("Class-kind boon" in forms, "relic_forms must offer a **Class-kind boon** form")
    for op in ("`forge`", "`channel_orb`", "`summon`"):
        check(op in forms, f"Class-kind boon must name {op}")


def test_every_archetype_has_note() -> None:
    print("every archetype id in archetypes.json has a non-empty archetype-note:")
    ids = _archetype_ids()
    check(len(ids) >= 34, f"expected >= 34 archetypes, got {len(ids)}")
    for aid in ids:
        note = contract.archetype_balance_note(aid)
        check(bool(note.strip()), f"archetype '{aid}' has no archetype-note in DESIGN_HEURISTICS.md")
        for word in ("from_state", "fuse"):
            check(word not in note, f"archetype-note '{aid}' names prototype op '{word}'")
    # Notes must not be orphaned either: every archetype-note marker points at a real archetype id.
    noted = set(re.findall(r"<!--\s*archetype-note:\s*([A-Za-z0-9_\-]+)\s*-->", _heuristic_text()))
    noted.discard("ARCHETYPE_ID")  # the file's own "How it works" example marker, not a note
    orphans = sorted(noted - set(ids))
    check(not orphans, f"archetype-note markers with no archetype in archetypes.json: {orphans}")
    # And the catalog surfaces them as the balance line.
    cat = C.load_catalog()
    for aid in ids:
        check(bool(cat.by_id[aid].balance_note.strip()), f"catalog entry '{aid}' has an empty balance_note")


def test_vocabulary_rare_line() -> None:
    print("VOCABULARY.md no longer says build-around rares need unsupported ops:")
    text = paths.VOCABULARY.read_text(encoding="utf-8")
    check("need ops not yet supported" not in text,
          "VOCABULARY.md still says deeper build-around rares need ops not yet supported")
    check("make rares hit hard and wide" not in text, "VOCABULARY.md still tells the model to only make rares hit hard")
    rarity = text[text.index("## Rarity guidance"):]
    for tok in ("`add_trigger`", "`when`", "`scale`", "`transform_card`"):
        check(tok in rarity, f"rarity guidance should point rares at {tok}")
    # New backticked words must all be live vocabulary tokens (the catalog harvests them as buildability tokens).
    live = C.live_vocab_tokens()
    for tok in ("add_trigger", "when", "scale", "transform_card", "forge", "channel_orb", "summon",
                "apply_status_custom", "balance_step"):
        check(tok in live, f"'{tok}' should be a live vocab token")


def test_vocabulary_on_discard_caveat() -> None:
    print("VOCABULARY.md on_discard carries the base-game caveat:")
    text = paths.VOCABULARY.read_text(encoding="utf-8")
    trig = text[text.index("## Triggers"):]
    check("base-game" in trig and "on_discard" in trig, "Triggers section must mention on_discard + base-game")
    caveat = re.search(r"fires ONLY from THIS class's own `discard` / `scry`", trig)
    check(caveat is not None, "on_discard caveat: fires only from THIS class's own `discard` / `scry` ops")
    check("do NOT fire it" in trig, "on_discard caveat must say base-game relic/enemy discards do NOT fire it")


def test_vocabulary_metallicize_plating() -> None:
    print("VOCABULARY.md metallicize row matches STS2 Plating (decays per turn, not on hit):")
    text = paths.VOCABULARY.read_text(encoding="utf-8")
    row = next((l for l in text.splitlines() if l.startswith("| `metallicize`")), "")
    check(bool(row), "metallicize status row must exist")
    check("Permanent." not in row, "metallicize must no longer be described as Permanent (PlatingPower decays)")
    check("Plating" in row, "metallicize row should name STS2 Plating")
    check("PlatingPower" in text, "VOCABULARY.md should record the PlatingPower implementation note")


def test_relic_vocab_no_truncation() -> None:
    print("RELIC_VOCABULARY.md has no truncated 'There is no' line and the summon row is single-minion:")
    text = RELIC_VOCAB.read_text(encoding="utf-8")
    for i, line in enumerate(text.splitlines(), 1):
        check(not line.rstrip().endswith("There is no"), f"RELIC_VOCABULARY.md:{i} ends with a truncated 'There is no'")
    row = next((l for l in text.splitlines() if l.startswith("| `summon`")), "")
    check(bool(row), "relic summon row must exist")
    check("(HP)" in row and "Max HP" in row, "relic summon row must read amount as HP / raise Max HP (single-minion model)")
    check("Summon `amount` of" not in row, "relic summon row still uses the old multi-pet wording")


def main() -> int:
    test_heuristics_no_prototype_residue()
    test_relic_forms_menu()
    test_every_archetype_has_note()
    test_vocabulary_rare_line()
    test_vocabulary_on_discard_caveat()
    test_vocabulary_metallicize_plating()
    test_relic_vocab_no_truncation()
    print(f"\n{_PASS} passed, {_FAIL} failed")
    return 1 if _FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
