"""Phase AG — upgrade-cost channel (VOCABULARY_GAPS #39) — offline, no API key.

Run:  uv run python -m tests.test_phase_ag       (from generation/)
Exits nonzero on any failure. Exercises the mod-contract validator (an upgrade that LOWERS cost accepts; a
cost RAISE / a cost on an X-cost card / an out-of-range cost reject) and the signature-blade emission
(upgrade drops 2 -> 1). Mirrors the C# ForgedCards / CardSpec / DataCard changes (vocab v37).
"""
from __future__ import annotations

import sys

from btsgen.class_forge import point_btsgen_at_mod_contract, _synthesize_blade

point_btsgen_at_mod_contract()

from btsgen import bts1        # noqa: E402
from btsgen.validator import CardValidator  # noqa: E402

_PASS = 0
_FAIL = 0


def check(cond: bool, msg: str) -> None:
    global _PASS, _FAIL
    if cond:
        _PASS += 1
    else:
        _FAIL += 1
        print(f"  FAIL: {msg}")


def _card(cost, up_cost, base_effects=None, up_effects=None, **kw):
    base = {"id": "ag_test", "name": "AG Test", "type": "attack", "rarity": "uncommon",
            "cost": cost, "target": "enemy", "source": "llm",
            "effects": base_effects or [{"op": "damage", "amount": 8}]}
    up = {"effects": up_effects or [{"op": "damage", "amount": 12}]}
    if up_cost is not None:
        up["cost"] = up_cost
    base["upgrade"] = up
    base.update(kw)
    return base


def test_version() -> None:
    print("Phase AG vocab stamp is at least v37:")
    check(bts1.VOCAB_VERSION >= 37, f"bts1.VOCAB_VERSION must be >= 37 (Phase AG), got {bts1.VOCAB_VERSION}")


def test_accepts(v: CardValidator) -> None:
    print("an upgrade that lowers cost validates:")
    lower = _card(cost=2, up_cost=1)
    check(v.validate(lower).ok, f"upgrade cost 2->1 should validate: {v.validate(lower).errors}")
    same = _card(cost=2, up_cost=2)
    check(v.validate(same).ok, f"upgrade cost 2->2 should validate: {v.validate(same).errors}")


def test_rejects(v: CardValidator) -> None:
    print("invalid upgrade costs are rejected:")

    def bad(card, why):
        check(not v.validate(card).ok, why)

    bad(_card(cost=1, up_cost=2), "upgrade cost raise 1->2 must reject")
    bad(_card(cost=3, up_cost=4), "upgrade cost 4 (out of range) must reject")
    bad(_card(cost="X", up_cost=1,
              base_effects=[{"op": "damage", "amount": 5, "scale": "x"}],
              up_effects=[{"op": "damage", "amount": 7, "scale": "x"}]),
        "upgrade cost on an X-cost card must reject")


def test_blade_emission() -> None:
    print("the signature blade's upgrade drops cost 2 -> 1:")
    blade = _synthesize_blade({"name_hint": "Test Blade"})
    check(blade.get("cost") == 2, f"blade base cost should be 2: {blade.get('cost')}")
    check(blade.get("upgrade", {}).get("cost") == 1, f"blade upgrade.cost should be 1: {blade.get('upgrade')}")


def main() -> int:
    v = CardValidator()
    test_version()
    test_accepts(v)
    test_rejects(v)
    test_blade_emission()
    print(f"\n{_PASS} passed, {_FAIL} failed")
    return 1 if _FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
