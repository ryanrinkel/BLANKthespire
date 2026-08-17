"""Offline tests for card-stage vocab-demand mining (2026-08-16) — no API key, no network.

Run:  uv run python -m tests.test_vocab_demand     (from generation/)
Exits nonzero on any failure. Covers: validator.vocab_misses extracting (kind, token) reaches from
validation-error strings (op / when-kind / scale / status; shape noise and garbage tokens excluded;
deduped), real end-to-end error text from CardValidator on a card that reaches for a missing op, and
pipeline.generate_card keeping all_errors across attempts EVEN when the repair succeeds — the property
the whole capture rides on (a reach counts even when the model then settles for a legal card).
"""
from __future__ import annotations

import json
import sys

from btsgen.class_forge import point_btsgen_at_mod_contract

point_btsgen_at_mod_contract()

from btsgen.pipeline import generate_card  # noqa: E402
from btsgen.validator import CardValidator, vocab_misses  # noqa: E402

_PASS = 0
_FAIL = 0


def check(cond: bool, msg: str) -> None:
    global _PASS, _FAIL
    if cond:
        _PASS += 1
    else:
        _FAIL += 1
        print(f"  FAIL: {msg}")


def test_extraction_patterns() -> None:
    print("vocab_misses(): pulls (kind, token) reaches out of error strings, skips shape noise:")
    errs = [
        "schema [effects/0/op]: 'steal_gold' is not one of ['damage', 'block', 'draw']",
        "schema [effects/1/when/kind]: 'discard_pile_ge' is not one of ['turn_at_least', 'draw_pile_empty']",
        "unsupported scale 'cards_in_hand' (one of damage_dealt_unblocked/target_debuff_count).",
        "effects[0]: unknown status 'burn' (not in data/statuses/)",
        "schema [effects/2/scale]: 'gold_spent' is not one of ['forged', 'x']",
        # shape/balance noise — a model MISUSING an existing token is not demand:
        "two effects both declare 'Damage' — a card may use each value only once",
        "power score 31.0 exceeds ~26.6 for cost 1 / uncommon",
        "schema [target]: 'everyone' is not one of ['self', 'enemy', 'all_enemies']",  # not a vocab surface
        # garbage-shaped tokens are not demand either:
        "schema [effects/0/op]: 'Deal 6 damage!!' is not one of ['damage', 'block']",
        # a duplicate reach must not double-count:
        "schema [effects/3/op]: 'steal_gold' is not one of ['damage', 'block', 'draw']",
    ]
    got = vocab_misses(errs)
    check(("op", "steal_gold") in got, "an op-enum reach must be captured")
    check(("condition", "discard_pile_ge") in got, "a when-kind reach must be captured")
    check(("scale", "cards_in_hand") in got, "a text-form scale reach must be captured")
    check(("scale", "gold_spent") in got, "a schema-form scale reach must be captured")
    check(("status", "burn") in got, "a status reach must be captured")
    check(len(got) == 5, f"shape noise / target enums / garbage / dupes must be excluded (got {got})")
    check(vocab_misses([]) == [] and vocab_misses(None) == [], "empty input is a clean no-op")


def test_real_validator_error_text() -> None:
    print("a real CardValidator run produces error text vocab_misses can mine:")
    v = CardValidator()
    card = {"id": "vd_test", "name": "VD Test", "type": "attack", "rarity": "uncommon", "cost": 1,
            "target": "enemy", "source": "llm",
            "effects": [{"op": "steal_gold", "amount": 3}]}
    vr = v.validate(card)
    check(not vr.ok, "the missing-op card must fail validation")
    got = vocab_misses(vr.errors)
    check(("op", "steal_gold") in got,
          f"the real schema error text must yield the reach (errors: {vr.errors[:2]})")


class _StubGen:
    """Duck-typed generator: attempt 1 reaches for a missing op, the repair settles legal."""
    model = "stub"

    def __init__(self):
        self._bad = json.dumps({"id": "vd_stub", "name": "VD Stub", "type": "attack", "rarity": "common",
                                "cost": 1, "target": "enemy",
                                "effects": [{"op": "steal_gold", "amount": 3}]})
        self._good = json.dumps({"id": "vd_stub", "name": "VD Stub", "type": "attack", "rarity": "common",
                                 "cost": 1, "target": "enemy",
                                 "effects": [{"op": "damage", "amount": 6}]})

    def first_attempt(self, brief):
        return self._bad, [{"role": "user", "content": "brief"}, {"role": "assistant", "content": self._bad}]

    def repair(self, messages, prev_text, errors):
        return self._good, messages + [{"role": "assistant", "content": self._good}]


def test_pipeline_keeps_reaches_across_successful_repair() -> None:
    print("generate_card keeps attempt-1 errors on all_errors even when the repair succeeds:")
    from btsgen.contract import Brief
    res = generate_card(Brief(card_type="attack", rarity="common", target_cost=1, theme="steal their gold"),
                        gen=_StubGen(), validator=CardValidator())
    check(res.ok, f"the repaired card must ship: {res.log}")
    got = vocab_misses(res.all_errors)
    check(("op", "steal_gold") in got,
          f"the attempt-1 reach must survive a successful repair (all_errors: {res.all_errors[:2]})")


def main() -> int:
    test_extraction_patterns()
    test_real_validator_error_text()
    test_pipeline_keeps_reaches_across_successful_repair()
    print(f"\n{_PASS} passed, {_FAIL} failed")
    return 1 if _FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
