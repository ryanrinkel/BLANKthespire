"""Offline balance-repair tests — no API key needed.

Run:  uv run python -m tests.test_pipeline_balance_repair     (from generation/)
Exits nonzero on any failure. Covers the two-layer overtuned-card pass in pipeline.generate_card:
layer 1 is one extra repair call asking for the same design with smaller numbers; layer 2 is the
deterministic clamp — whatever survives layer 1 still over the ceiling gets its amounts scaled
down to the budget, so an overtuned card only ships when it has no shrinkable numbers at all.
"""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
from pathlib import Path

from btsgen import paths

# Redirect quarantine output BEFORE building validators/pipelines: pipeline._quarantine and
# CardValidator.known_cards both read paths.GENERATED_DIR at call time.
_TMP = Path(tempfile.mkdtemp(prefix="btsgen_balance_test_"))
paths.GENERATED_DIR = _TMP

from btsgen.contract import Brief                    # noqa: E402
from btsgen.pipeline import generate_card            # noqa: E402
from btsgen.validator import CardValidator           # noqa: E402

_PASS = 0
_FAIL = 0


def check(cond: bool, msg: str) -> None:
    global _PASS, _FAIL
    if cond:
        _PASS += 1
    else:
        _FAIL += 1
        print(f"  FAIL: {msg}")


def _overtuned(cid: str) -> dict:
    """A valid common cost-1 attack scoring 100 against a ~15 ceiling."""
    c = json.loads((paths.CARDS_DIR / "strike.json").read_text())
    c.update(id=cid, name="Overkill", rarity="common", cost=1,
             effects=[{"op": "damage", "amount": 100}])
    c.pop("upgrade", None)
    return c


class _StubGen:
    """Duck-types the generator: first_attempt returns `first`; repair returns `tuned`."""

    def __init__(self, first: dict, tuned: dict | str | None = None) -> None:
        self.model = "stub-offline"
        self._first = first
        self._tuned = tuned
        self.repair_calls: list[str] = []

    def first_attempt(self, brief):
        return json.dumps(self._first), [{"role": "user", "content": brief.describe()}]

    def repair(self, messages, prev_text, errors):
        self.repair_calls.append("; ".join(errors))
        out = self._tuned if isinstance(self._tuned, str) else json.dumps(self._tuned)
        return out, messages


def _run(first: dict, tuned: dict | str | None = None):
    gen = _StubGen(first, tuned)
    res = generate_card(Brief(), gen=gen, validator=CardValidator())
    return res, gen


def _meta(res) -> dict:
    return json.loads(Path(res.quarantine_path).with_suffix("").with_suffix(".meta.json").read_text())


def test_renumbered_repair_accepted() -> None:
    print("overtuned card, correctly renumbered repair -> accepted:")
    tuned = dict(_overtuned("bal_t1"), effects=[{"op": "damage", "amount": 12}])
    res, gen = _run(_overtuned("bal_t1"), tuned)
    check(res.ok, f"pipeline should succeed: {res.log}")
    check(len(gen.repair_calls) == 1 and "overtuned" in gen.repair_calls[0],
          f"expected exactly one balance-repair call, got {gen.repair_calls}")
    check(res.balance_repaired, f"balance_repaired should be True: {res.log}")
    check(res.card["effects"][0]["amount"] == 12, "the tuned numbers should ship")
    check(res.result.score == 12.0, f"sidecar score should be the tuned card's: {res.result.score}")
    br = res.balance_repair
    check(br and br["accepted"] and br["score_before"] == 100.0 and br["score_after"] == 12.0,
          f"balance_repair record wrong: {br}")
    meta = _meta(res)
    check(meta["balance_repaired"] is True and meta["balance_repair"]["accepted"] is True,
          f"meta sidecar should record the accepted repair: {meta}")


def test_redesigned_repair_rejected_then_clamped() -> None:
    print("repair that changes the design -> rejected, the clamp finishes the job:")
    tuned = dict(_overtuned("bal_t2"),
                 effects=[{"op": "damage", "amount": 12}, {"op": "draw", "amount": 1}])
    res, gen = _run(_overtuned("bal_t2"), tuned)
    check(res.ok, "pipeline still succeeds")
    check(res.balance_repair and res.balance_repair["accepted"] is False,
          f"the LLM attempt should be recorded as not accepted: {res.balance_repair}")
    check(res.balance_repaired and res.balance_repair.get("clamped") is True,
          f"the clamp backstop should have fired: {res.log}")
    check(res.card["effects"][0]["op"] == "damage" and len(res.card["effects"]) == 1,
          "the ORIGINAL design ships (redesign discarded), only renumbered")
    check(res.result.score <= 15.0, f"clamped under the ~15 ceiling: {res.result.score}")
    check(not any("power score" in w for w in res.result.warnings),
          f"no over-budget warning after the clamp: {res.result.warnings}")


def test_garbage_repair_rejected_then_clamped() -> None:
    print("unparseable repair -> clamp backstop, ok stays true:")
    res, _gen = _run(_overtuned("bal_t3"), "this is not json {")
    check(res.ok, "pipeline still succeeds")
    check(res.balance_repaired and res.result.score <= 15.0,
          f"the clamp should land the card under budget: {res.log}")
    meta = _meta(res)
    check(meta["balance_repair"]["accepted"] is False and meta["balance_repair"]["clamped"] is True,
          f"meta sidecar should record failed LLM attempt + accepted clamp: {meta}")


def test_cost_bump_accepted_but_not_two() -> None:
    print("repair may raise cost by exactly 1, never more:")
    tuned = dict(_overtuned("bal_t4"), cost=2, effects=[{"op": "damage", "amount": 18}])
    res, _gen = _run(_overtuned("bal_t4"), tuned)
    check(res.balance_repaired and res.card["cost"] == 2,
          f"cost+1 renumbering should be accepted: {res.log}")
    tuned = dict(_overtuned("bal_t5"), cost=3, effects=[{"op": "damage", "amount": 18}])
    res, _gen = _run(_overtuned("bal_t5"), tuned)
    check(res.card["cost"] == 1, f"cost+2 must be rejected: {res.log}")
    check(res.balance_repair["accepted"] is False and res.result.score <= 15.0,
          f"clamp still lands the original-cost card under budget: {res.log}")


def test_llm_improvement_then_clamp_finishes() -> None:
    print("still-over-budget but strictly better -> accepted, then clamped to the ceiling:")
    tuned = dict(_overtuned("bal_t6"), effects=[{"op": "damage", "amount": 20}])
    res, _gen = _run(_overtuned("bal_t6"), tuned)
    check(res.balance_repaired and res.balance_repair["accepted"] is True,
          f"the 100->20 improvement should be accepted: {res.log}")
    check(res.result.score <= 15.0 and res.card["effects"][0]["amount"] <= 15,
          f"the clamp should then finish 20 -> <=15: {res.log}")
    check(not any("power score" in w for w in res.result.warnings),
          f"no residual warning once under budget: {res.result.warnings}")


def test_in_budget_card_untouched() -> None:
    print("a card inside its budget never triggers the pass:")
    fine = dict(_overtuned("bal_t7"), effects=[{"op": "damage", "amount": 9}])
    res, gen = _run(fine, None)
    check(res.ok and not gen.repair_calls, f"no repair call expected: {gen.repair_calls}")
    check(res.balance_repair is None and not res.balance_repaired, "no attempt recorded")


def test_clamp_distributes_across_effects() -> None:
    print("clamp shrinks every score-raising amount, floored at 1:")
    first = dict(_overtuned("bal_t8"),
                 effects=[{"op": "damage", "amount": 30}, {"op": "draw", "amount": 2}])  # score 40
    res, _gen = _run(first, "not json")
    check(res.ok and res.balance_repaired, f"clamp should fire: {res.log}")
    check(res.result.score <= 15.0, f"landed under the ~15 ceiling: {res.result.score}")
    check(res.card["effects"][1]["amount"] == 1, "draw floors at 1, never 0")
    check(res.card["effects"][0]["amount"] < 30, "damage took the rest of the cut")


def test_clamp_out_of_knobs_keeps_warning() -> None:
    print("no shrinkable amounts -> card ships with its warning (honest best-effort):")
    first = dict(_overtuned("bal_t9"),
                 effects=[{"op": "draw", "amount": 1}, {"op": "draw", "amount": 1},
                          {"op": "draw", "amount": 1}, {"op": "draw", "amount": 1}])  # score 20, all floored
    res, _gen = _run(first, "not json")
    check(res.ok and not res.balance_repaired, f"nothing to clamp: {res.log}")
    check(any("power score" in w for w in res.result.warnings),
          f"the over-budget warning must survive: {res.result.warnings}")


def main() -> int:
    try:
        for t in (test_renumbered_repair_accepted, test_redesigned_repair_rejected_then_clamped,
                  test_garbage_repair_rejected_then_clamped, test_cost_bump_accepted_but_not_two,
                  test_llm_improvement_then_clamp_finishes, test_in_budget_card_untouched,
                  test_clamp_distributes_across_effects, test_clamp_out_of_knobs_keeps_warning):
            t()
    finally:
        shutil.rmtree(_TMP, ignore_errors=True)
    print(f"\n{_PASS} passed, {_FAIL} failed")
    return 1 if _FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
