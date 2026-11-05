"""GitHub issue #1 regression — `transform_card` is counted per EFFECT LIST, not across base + upgrade.

The upgrade effect list is a full replace-on-upgrade list, so the normal shape the generator emits (the upgrade
repeats the transform) carries the op once in each list. The mod's import (ForgedCards.Validate) used to count
base + upgrade TOGETHER and rejected every such card ("at most one 'transform_card' effect per card"). Both
validators now count the two lists independently (like graft_card). Offline, no API key.

Run:  uv run python -m pytest tests/test_github_issue_1.py -q       (from generation/)
"""
from __future__ import annotations

from btsgen.class_forge import point_btsgen_at_mod_contract

point_btsgen_at_mod_contract()

from btsgen.validator import CardValidator                      # noqa: E402

_KNOWN_TARGET = "reckoning"  # same resolvable transform target test_phase_ah uses (committed authored pool)
_MSG = "at most one 'transform_card'"


def _card(cid, effects, *, upgrade=None):
    c = {"id": cid, "name": cid.replace("_", " ").title(), "type": "attack", "rarity": "uncommon",
         "cost": 1, "target": "enemy", "source": "llm", "effects": effects}
    if upgrade is not None:
        c["upgrade"] = {"effects": upgrade}
    return c


def _xf():
    return {"op": "transform_card", "card_id": _KNOWN_TARGET}


def _count_msgs(card) -> tuple[bool, list[str]]:
    r = CardValidator().validate(card)
    return r.ok, [e for e in r.errors if _MSG in e]


def test_one_transform_in_base_and_one_in_upgrade_passes() -> None:
    card = _card("gh1_shape", [{"op": "damage", "amount": 6}, _xf()],
                 upgrade=[{"op": "damage", "amount": 9}, _xf()])
    ok, hits = _count_msgs(card)
    assert hits == [], f"base + upgrade each carrying ONE transform_card must not trip the count rule: {hits}"
    assert ok, f"the normal replace-on-upgrade transform shape should validate: {CardValidator().validate(card).errors}"


def test_two_transforms_in_base_rejected() -> None:
    card = _card("gh1_base2", [{"op": "damage", "amount": 6}, _xf(), _xf()])
    ok, hits = _count_msgs(card)
    assert not ok and hits, "two transform_card in the BASE list must be rejected with the at-most-one message"


def test_two_transforms_in_upgrade_rejected() -> None:
    card = _card("gh1_up2", [{"op": "damage", "amount": 6}, _xf()],
                 upgrade=[{"op": "damage", "amount": 9}, _xf(), _xf()])
    ok, hits = _count_msgs(card)
    assert not ok and hits, "two transform_card in the UPGRADE list must be rejected with the at-most-one message"
