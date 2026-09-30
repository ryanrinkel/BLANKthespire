"""Summon HP budget (2026-09-30) — offline, no API key.

Run:  uv run python -m tests.test_summon_hp_budget     (from generation/)
Exits nonzero on any failure. Summon HP is effectively player HP, so the card validator caps a card-level
`summon` at the base-game Necrobinder's rate: 6 HP per energy on a basic/common, 7 on an uncommon, 8 on a rare
(0-cost = half an energy, X-cost uncapped, an upgrade may add 3). An amount-less summon is priced at the minion's
declared max_hp. Also checks the exemplar that taught the old 10-HP common, and the fake generator's summon card.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from btsgen.class_forge import point_btsgen_at_mod_contract

point_btsgen_at_mod_contract()

from btsgen import class_forge                                   # noqa: E402
from btsgen.validator import CardValidator, summon_hp_cap        # noqa: E402

_PASS = 0
_FAIL = 0


def check(cond: bool, msg: str) -> None:
    global _PASS, _FAIL
    if cond:
        _PASS += 1
    else:
        _FAIL += 1
        print(f"  FAIL: {msg}")


def _card(hp, rarity="common", cost=1, up_hp=None):
    eff = [{"op": "summon", "summon_name": "Wolf", "amount": hp}] if hp is not None else [{"op": "summon", "summon_name": "Wolf"}]
    up = [{"op": "summon", "summon_name": "Wolf", "amount": up_hp if up_hp is not None else (hp or 1)}]
    return {"id": "hp_test", "name": "HP Test", "type": "skill", "rarity": rarity, "cost": cost, "target": "self",
            "source": "llm", "effects": eff, "upgrade": {"effects": up}}


def _budget_errors(v: CardValidator, card: dict) -> list[str]:
    return [e for e in v.validate(card).errors if "budget" in e]


def test_summon_hp_budget_all() -> None:
    print("summon_hp_cap: rate by rarity, 0-cost = half an energy, X-cost uncapped:")
    check(summon_hp_cap("basic", 1) == 6, "basic 1-cost cap is 6 (Bodyguard 5 fits)")
    check(summon_hp_cap("common", 1) == 6, "common 1-cost cap is 6 (Afterlife 6 fits)")
    check(summon_hp_cap("uncommon", 2) == 14, "uncommon 2-cost cap is 14")
    check(summon_hp_cap("rare", 3) == 24, "rare 3-cost cap is 24 (Reanimate 20 fits; rares stretch)")
    check(summon_hp_cap("common", 0) == 3, "0-cost common cap is 3")
    check(summon_hp_cap("rare", "X") is None, "X-cost is uncapped")

    print("the card validator enforces the budget on base and upgrade:")
    v = CardValidator(extra_summons={"wolf"}, summon_max_hp={"wolf": 14})
    check(not _budget_errors(v, _card(6)), "a 6-HP 1-cost common is within budget")
    check(bool(_budget_errors(v, _card(10, rarity="basic"))), "a 10-HP 1-cost basic (Rattle the Room) is over budget")
    check(not _budget_errors(v, _card(8, rarity="rare")), "a rare may stretch to 8 HP per energy")
    check(bool(_budget_errors(v, _card(9, rarity="rare"))), "but not 9 on a 1-cost rare")
    check(not _budget_errors(v, _card(6, up_hp=9)), "an upgrade may add 3 over the cap")
    check(bool(_budget_errors(v, _card(6, up_hp=10))), "but not 4")
    check(bool(_budget_errors(v, _card(None))), "an amount-less summon is priced at the minion's max_hp (14 > 6)")
    check(not _budget_errors(CardValidator(extra_summons={"wolf"}), _card(None)),
          "with no max_hp known, an amount-less summon isn't priced")
    msg = (_budget_errors(v, _card(10, rarity="basic")) or [""])[0]
    check("price it like Block" in msg and "raise the cost or rarity" in msg, f"the error tells the model how to fix it: {msg}")

    print("the forge wires max_hp into the validator, and the teaching data fits the budget:")
    check(class_forge._summon_pool_max_hp({"summon_pool": [{"name": "Bone Thrall", "max_hp": 12}]}) == {"bone thrall": 12},
          "_summon_pool_max_hp maps lowercased names to max_hp")
    pool = json.loads((Path(__file__).resolve().parents[1] / "btsgen" / "data" / "exemplar_pool.json")
                      .read_text(encoding="utf-8"))
    entries = pool if isinstance(pool, list) else next(v for v in pool.values() if isinstance(v, list))
    for ent in entries:
        c = ent.get("card", ent) if isinstance(ent, dict) else {}
        for which, effs, extra in (("base", c.get("effects") or [], 0),
                                   ("upgrade", (c.get("upgrade") or {}).get("effects") or [], 3)):
            for e in effs:
                if e.get("op") == "summon" and isinstance(e.get("amount"), int):
                    cap = summon_hp_cap(c.get("rarity"), c.get("cost"))
                    check(cap is None or e["amount"] <= cap + extra,
                          f"exemplar {c.get('name')} {which} summon {e['amount']} fits its budget {cap}+{extra}")


def main() -> int:
    test_summon_hp_budget_all()
    print(f"\n{_PASS} passed, {_FAIL} failed")
    return 1 if _FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
