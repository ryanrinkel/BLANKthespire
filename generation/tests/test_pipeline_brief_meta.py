"""pipeline.generate_card checks the card's `type` / `rarity` against the brief (Jev plan section 5: the card stage
never did). A mismatch joins the attempt-1 errors so the ONE existing repair call fixes it; a repaired card that
still mismatches fails like any other validation error. Opt-in per brief (Brief.enforce_type_rarity) — Brief()'s
attack/common defaults are placeholders — and fakes that pick their type from the theme are exempt.
"""
from __future__ import annotations

import json

from btsgen.class_forge import point_btsgen_at_mod_contract

point_btsgen_at_mod_contract()

from btsgen.contract import Brief  # noqa: E402
from btsgen.pipeline import _brief_mismatch, generate_card  # noqa: E402
from btsgen.validator import CardValidator  # noqa: E402


def _card(ctype: str, rarity: str = "common") -> dict:
    if ctype == "attack":
        return {"id": "bm_card", "name": "Brief Meta", "type": "attack", "rarity": rarity, "cost": 1,
                "target": "enemy", "effects": [{"op": "damage", "amount": 6},
                                                {"op": "apply_status", "status": "weak", "amount": 1}]}
    return {"id": "bm_card", "name": "Brief Meta", "type": "skill", "rarity": rarity, "cost": 1,
            "target": "self", "effects": [{"op": "block", "amount": 6}, {"op": "draw", "amount": 1}]}


class _Gen:
    model = "stub-offline"

    def __init__(self, first: dict, repaired: dict | None = None) -> None:
        self._first, self._repaired = first, repaired
        self.repair_errors: list[list[str]] = []

    def first_attempt(self, brief):
        t = json.dumps(self._first)
        return t, [{"role": "user", "content": "brief"}, {"role": "assistant", "content": t}]

    def repair(self, messages, prev_text, errors):
        self.repair_errors.append(list(errors))
        t = json.dumps(self._repaired if self._repaired is not None else self._first)
        return t, messages + [{"role": "assistant", "content": t}]


def _brief(**kw) -> Brief:
    return Brief(card_type=kw.pop("card_type", "skill"), rarity=kw.pop("rarity", "common"), target_cost=1,
                 theme="brief meta test", enforce_type_rarity=kw.pop("enforce", True))


def test_matching_card_passes_untouched():
    gen = _Gen(_card("skill"))
    res = generate_card(_brief(), gen=gen, validator=CardValidator())
    assert res.ok and not res.repaired, res.log
    assert gen.repair_errors == []
    assert res.card["type"] == "skill"


def test_type_mismatch_triggers_the_single_repair_with_that_error():
    gen = _Gen(_card("attack"), repaired=_card("skill"))
    res = generate_card(_brief(), gen=gen, validator=CardValidator())
    assert res.ok and res.repaired, res.log
    assert len(gen.repair_errors) == 1
    assert "card 'type' must be 'skill' (the brief's type); got 'attack'" in gen.repair_errors[0]
    assert res.card["type"] == "skill"
    assert any("must be 'skill'" in e for e in res.all_errors)


def test_rarity_mismatch_still_wrong_after_repair_fails_the_card():
    gen = _Gen(_card("skill", rarity="common"))  # the repair echoes the same card
    res = generate_card(_brief(rarity="uncommon"), gen=gen, validator=CardValidator())
    assert not res.ok and res.card is None
    assert gen.repair_errors and "card 'rarity' must be 'uncommon' (the brief's rarity); got 'common'" \
        in gen.repair_errors[0]
    assert res.result is not None and any("rarity" in e for e in res.result.errors)


def test_opt_in_placeholder_and_exempt_fakes():
    # not opted in (Brief() defaults are placeholders): an attack-shaped card under a skill brief ships
    gen = _Gen(_card("attack"))
    res = generate_card(_brief(enforce=False), gen=gen, validator=CardValidator())
    assert res.ok and not res.repaired
    # a brief value outside the schema enum (free text / template placeholder) is never enforced
    assert _brief_mismatch(Brief(card_type="attack|skill|power", rarity="...", enforce_type_rarity=True),
                           _card("skill")) == []
    # a fake that picks its type from the theme is exempt

    class _Exempt(_Gen):
        brief_meta_exempt = True
    gen2 = _Exempt(_card("attack"))
    res2 = generate_card(_brief(), gen=gen2, validator=CardValidator())
    assert res2.ok and not res2.repaired
