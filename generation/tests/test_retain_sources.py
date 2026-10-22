"""Retain-source coherence (2026-10-22) — the card-level validator rule. Offline.

Run:  uv run python -m tests.test_retain_sources       (from generation/)
`when: retained_last_turn` reads whether THIS card was held into the turn, so (like the Phase BD grow_held /
held_discount payoffs) it needs `retain` on the same effect list; base and upgrade lists are checked independently.
A trigger's `when` already rejects retained_last_turn as play-local. The class-level quota (cards_retained /
retained_last_turn readers vs Retain sources) lives in test_coverage.py.
"""
from __future__ import annotations

import sys

from btsgen.class_forge import point_btsgen_at_mod_contract

point_btsgen_at_mod_contract()

from btsgen.validator import CardValidator  # noqa: E402

_PASS = 0
_FAIL = 0
_MSG = "'when: retained_last_turn' needs 'retain' on the same card"


def check(cond: bool, msg: str) -> None:
    global _PASS, _FAIL
    if cond:
        _PASS += 1
    else:
        _FAIL += 1
        print(f"  FAIL: {msg}")


def _card(effects, upgrade=None, ctype="skill", target="self", cost=0):
    c = {"id": "rs_t", "name": "RS", "type": ctype, "rarity": "common", "cost": cost, "target": target,
         "effects": effects}
    if upgrade is not None:
        c["upgrade"] = {"effects": upgrade}
    return c


_V = None


def _errs(card) -> list[str]:
    global _V
    if _V is None:
        _V = CardValidator()
    return _V.validate(card).errors


def _hit(card) -> bool:
    return any(_MSG in e for e in _errs(card))


GATED = {"op": "draw", "amount": 1, "when": {"kind": "retained_last_turn"}}
RET = {"op": "retain"}


def test_retained_last_turn_needs_retain() -> None:
    print("retained_last_turn needs retain on the same list:")
    bare = _card([{"op": "block", "amount": 4}, GATED])
    check(_hit(bare), f"no retain -> error: {_errs(bare)}")
    ok = _card([RET, {"op": "block", "amount": 4}, GATED])
    check(not _hit(ok), f"with retain -> no coherence error: {_errs(ok)}")
    check(not _errs(ok), f"the retain version validates clean: {_errs(ok)}")


def test_upgrade_list_independent() -> None:
    print("base and upgrade lists are checked independently:")
    up_missing = _card([RET, {"op": "block", "amount": 4}, GATED], upgrade=[{"op": "block", "amount": 6}, GATED])
    check(_hit(up_missing), f"upgrade list without retain -> error: {_errs(up_missing)}")
    both = _card([RET, {"op": "block", "amount": 4}, GATED], upgrade=[RET, {"op": "block", "amount": 6}, GATED])
    check(not _hit(both), f"retain on both lists -> no error: {_errs(both)}")
    base_missing = _card([{"op": "block", "amount": 4}, GATED], upgrade=[RET, {"op": "block", "amount": 6}, GATED])
    check(_hit(base_missing), f"base list without retain -> error even if the upgrade retains: {_errs(base_missing)}")


def test_trigger_when_still_play_local() -> None:
    print("a trigger's `when: retained_last_turn` is rejected by the existing play-local rule (not duplicated):")
    trig = _card([{"op": "add_trigger", "trigger": "turn_start", "when": {"kind": "retained_last_turn"},
                   "effects": [{"op": "block", "amount": 3}]}], ctype="power")
    errs = _errs(trig)
    check(any("a trigger's 'when' can't use retained_last_turn" in e for e in errs), f"play-local rejection: {errs}")
    check(not any(_MSG in e for e in errs), f"the coherence rule does not double-report a trigger when: {errs}")
    pay = _card([{"op": "add_trigger", "trigger": "turn_start",
                  "effects": [{"op": "block", "amount": 3, "when": {"kind": "retained_last_turn"}}]}], ctype="power")
    perrs = _errs(pay)
    check(bool(perrs), f"a payload-effect retained_last_turn is rejected too: {perrs}")


def test_unrelated_cards_untouched() -> None:
    print("cards without the gate are unaffected:")
    check(not _hit(_card([{"op": "block", "amount": 5}])), "a plain block card")
    scaled = _card([{"op": "add_trigger", "trigger": "turn_end",
                     "effects": [{"op": "block", "amount": 1, "scale": "cards_retained"}]}], ctype="power", cost=1)
    check(not _hit(scaled), f"a cards_retained power (class-level quota, not card-level): {_errs(scaled)}")


def main() -> int:
    test_retained_last_turn_needs_retain()
    test_upgrade_list_independent()
    test_trigger_when_still_play_local()
    test_unrelated_cards_untouched()
    print(f"\n{_PASS} passed, {_FAIL} failed")
    return 1 if _FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
