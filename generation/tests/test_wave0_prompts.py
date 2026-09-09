"""Wave 0 (VOCAB_GAP_REMEDIATION_PLAN W0.4 / W0.5 / W0.6): the prompts stop telling the model that supported
features don't exist, pruned blueprint sections stay discoverable, and the v1 few-shots are real mod cards.

Run:  uv run python -m tests.test_wave0_prompts      (from generation/)
Exits nonzero on any failure. Offline; no API key.
"""
from __future__ import annotations

import contextlib
import os
import re
import sys
from pathlib import Path

from btsgen.class_forge import point_btsgen_at_mod_contract

point_btsgen_at_mod_contract()

from btsgen import class_forge, contract, coverage, harness_v2  # noqa: E402
from btsgen.class_forge import _BlueprintContract  # noqa: E402
from btsgen.frontend import load_catalog  # noqa: E402


@contextlib.contextmanager
def _harness(on: bool):
    old = os.environ.get("BTS_HARNESS_V2")
    if on:
        os.environ["BTS_HARNESS_V2"] = "1"
    else:
        os.environ.pop("BTS_HARNESS_V2", None)
    try:
        yield
    finally:
        if old is None:
            os.environ.pop("BTS_HARNESS_V2", None)
        else:
            os.environ["BTS_HARNESS_V2"] = old


# ---- W0.4: the blueprint prompt no longer contradicts the vocabulary -----------------------------------

def test_blueprint_prompt_has_no_false_negatives() -> None:
    sp = _BlueprintContract(mode="dossier", triad=True)._system_prompt_legacy()
    assert "no conditionals" not in sp, "blueprint prompt still denies `when` gates"
    assert "no state-scaling" not in sp and "no card generation" not in sp
    assert "NO targeted damage or enemy debuffs" not in sp, "trigger payloads CAN target enemies (H4)"
    assert "Noxious Fumes" in sp, "the targeted-payload family should be pitched"
    # the fantasy-translation table routes to distinct shapes first (custom statuses / hp_lost_ge / forge)
    for tok in ("status_pool", "hp_lost_ge", "forge", "target_debuff_count"):
        assert tok in sp.split("Both archetypes must be built")[0], tok
    # the module docstring no longer claims relics are a placeholder
    assert "uses a placeholder" not in (class_forge.__doc__ or "")


# ---- W0.5: pruned subsystems stay discoverable; callers may pin sections -------------------------------

def _also_available_line(prompt: str) -> str:
    paras = [p for p in prompt.split("\n\n") if p.startswith(class_forge._ALSO_AVAILABLE_HEAD)]
    assert len(paras) <= 1, "at most one ALSO AVAILABLE line"
    return paras[0] if paras else ""


def test_pruned_prompt_names_pruned_subsystems() -> None:
    with _harness(True):
        cat = load_catalog()
        ops = set(cat.by_id["retain_hold"].ops) | set(cat.by_id["poison_attrition"].ops) \
            | set(cat.by_id["block_bulwark"].ops)
        pruned = _BlueprintContract(mode="dossier", triad=True, seed=1, selected_ops=ops,
                                    class_kind="normal").system_prompt()
        line = _also_available_line(pruned)
        assert line, "pruned prompt must carry the ALSO AVAILABLE menu"
        for pitch in ("rampage", "corruption", "purge", "metamorph", "forge", "balance", "summon_pool", "status_pool", "orbs"):
            assert pitch in line, pitch
        assert len(line) < 900, ("rule 0.9: the menu is a one-liner, not a paragraph", len(line))
        # a subsystem an archetype selected is pitched in full, not in the menu
        forge_ops = set(cat.by_id["forge_ramp"].ops)
        with_forge = _BlueprintContract(mode="dossier", triad=True, seed=1, selected_ops=forge_ops,
                                        class_kind="normal").system_prompt()
        assert "\n\nTHE FORGE / SIGNATURE-BLADE ARCHETYPE (" in with_forge
        assert "forge + a signature blade" not in _also_available_line(with_forge)
        # nothing pruned -> no menu (orb class with every section's ops selected)
        everything = set()
        for r in class_forge._PRUNABLE_SECTIONS:
            everything |= set(r[1])
        full = _BlueprintContract(mode="dossier", triad=True, seed=1, selected_ops=everything,
                                  class_kind="orb").system_prompt()
        assert not _also_available_line(full)


def test_nominated_sections_survive_pruning() -> None:
    with _harness(True):
        cat = load_catalog()
        ops = set(cat.by_id["retain_hold"].ops)
        plain = _BlueprintContract(mode="dossier", triad=True, seed=1, selected_ops=ops, class_kind="normal")
        pinned = _BlueprintContract(mode="dossier", triad=True, seed=1, selected_ops=ops, class_kind="normal",
                                    nominated_sections=["rampage", "summon"])
        sp_plain, sp_pinned = plain.system_prompt(), pinned.system_prompt()
        assert "\n\nRAMPAGE (" not in sp_plain and "\n\nRAMPAGE (" in sp_pinned
        assert "\n\nTHE SUMMON POOL (" not in sp_plain and "\n\nTHE SUMMON POOL (" in sp_pinned
        assert "rampage (" not in _also_available_line(sp_pinned)
        assert "rampage (" in _also_available_line(sp_plain)


def test_sanitize_nominations_accepts_sections() -> None:
    got = coverage.sanitize_nominations({"sections": ["rampage", "bogus", "Forge", "rampage"]})
    assert got == {"sections": ["rampage", "forge"]}, got
    assert coverage.sanitize_nominations({"sections": "rampage"}) == {}
    # the two SECTION_KEYS sets are kept in lockstep (a literal in coverage.py avoids a circular import)
    assert coverage.SECTION_KEYS == class_forge.SECTION_KEYS, (coverage.SECTION_KEYS ^ class_forge.SECTION_KEYS)
    assert "sections" in coverage.NOMINATION_CATEGORIES and coverage.NOMINATION_MAX["sections"] >= 3


# ---- W0.6: v1 few-shots are mod cards; card prompts name mod ops only ----------------------------------

def test_few_shot_ids_resolve_under_mod_contract() -> None:
    assert contract.few_shot_missing() == [], contract.few_shot_missing()
    for legacy in ("body_slam", "twin_strike", "battle_trance", "anger", "bloodletting", "inflame", "disarm"):
        assert legacy not in contract._FEW_SHOT_IDS, legacy
    assert '"id": "strike"' in contract._exemplars()


_PROTOTYPE_OP_RE = re.compile(r"(?<![a-z_`])(from_state|set_flag|fuse)(?![a-z_])|\(multi,")


def test_card_prompts_name_no_prototype_ops() -> None:
    for flag in (False, True):
        with _harness(flag):
            sp = contract.system_prompt()
            hit = _PROTOTYPE_OP_RE.search(sp)
            assert hit is None, (f"v{'2' if flag else '1'} card prompt names a prototype op", hit.group(0),
                                 sp[max(0, hit.start() - 80):hit.end() + 80])
            assert "reach for them LAST" not in sp
            assert "Poison is this harness's most overused status" not in sp
    with _harness(True):
        assert harness_v2.compositional_clause() in contract.system_prompt()


def test_source_tree_has_no_stale_relic_placeholder_claim() -> None:
    src = Path(class_forge.__file__).read_text(encoding="utf-8")
    assert "Starter relics are NOT generated" not in src


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"ok   {name}")
            except AssertionError as e:
                fails += 1
                print(f"FAIL {name}: {e}")
    sys.exit(1 if fails else 0)
