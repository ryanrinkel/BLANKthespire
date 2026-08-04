"""A deterministic offline stand-in for AnthropicGenerator (no API key, no network).

Used by `--fake` on the character CLI and by the offline test suites to exercise the FULL
generate -> validate -> quarantine -> review -> ingest path end-to-end for free. Emits
boring-but-valid content derived from the brief; same duck-typed surface as the real
generator (.model, first_attempt(), repair()).
"""
from __future__ import annotations

import json

from . import character_contract, contract, relic_contract


class FakeGenerator:
    """Contract-aware canned generator. One instance per contract, like the real one."""

    def __init__(self, contract_mod=None) -> None:
        self.model = "fake-offline"
        self._contract = contract_mod or contract
        self._n = 0  # per-instance card counter -> unique ids

    # -- AnthropicGenerator surface -----------------------------------------
    def first_attempt(self, brief) -> tuple[str, list[dict]]:
        text = json.dumps(self._make(brief), indent=2)
        return text, [{"role": "user", "content": "fake"}, {"role": "assistant", "content": text}]

    def repair(self, messages, prev_text, errors) -> tuple[str, list[dict]]:
        # Fakes are valid by construction; a repair request means a validator regression —
        # return the same object so the failure surfaces instead of masking it.
        return prev_text, messages

    # -- canned content ------------------------------------------------------
    def _make(self, brief) -> dict:
        if self._contract is character_contract:
            return self._blueprint(brief)
        if self._contract is relic_contract:
            return self._relic(brief)
        return self._card(brief)

    def _card(self, brief) -> dict:
        self._n += 1
        cost = brief.target_cost if brief.target_cost is not None else 1
        card = {
            "id": f"fake_{brief.card_type}_{self._n}",
            "name": f"Fake {brief.card_type.capitalize()} {self._n}",
            "type": brief.card_type,
            "rarity": brief.rarity,
            "cost": max(0, cost),
            "source": "llm",
        }
        # Compositions chosen to dodge the validator's functional-reprint gate: none of
        # these effect skeletons exists in the authored pool (plain damage-6 / block-5 /
        # +2-Strength fakes WERE reprints of Strike/Defend/Inflame and got rejected).
        if brief.card_type == "attack":
            card["target"] = "enemy"
            card["effects"] = [{"op": "damage", "amount": 5},
                               {"op": "apply_status", "status": "frail", "amount": 1}]
        elif brief.card_type == "power":
            card["target"] = "self"
            card["effects"] = [{"op": "apply_status", "status": "dexterity", "amount": 1},
                               {"op": "apply_status", "status": "strength", "amount": 1}]
        else:
            card["target"] = "self"
            card["effects"] = [{"op": "block", "amount": 4}, {"op": "heal", "amount": 2}]
        return card

    def _relic(self, brief) -> dict:
        return {
            "id": "fake_carapace",
            "name": "Fake Carapace",
            "tier": brief.tier,
            "pool": brief.pool,
            "description": "At the start of each combat, gain 3 Block.",
            "source": "llm",
            "hooks": [{"trigger": "combat_start", "effects": [{"op": "block", "amount": 3}]}],
        }

    def _blueprint(self, brief) -> dict:
        per = max(2, int(brief.pool_cards_per_archetype))
        pool = []
        for arch in ("alpha", "beta"):
            for i in range(per):
                pool.append({
                    "role": "pool", "name_hint": f"{arch.capitalize()} Move {i + 1}",
                    "type": "attack" if i % 2 == 0 else "skill",
                    "rarity": "common" if i < per - 1 else "rare",
                    "cost": 1, "archetype": arch, "deck_count": 0,
                    "theme": f"a simple {arch} effect (plain damage or block)",
                })
        return {
            "id": "test_subject",
            "name": "The Test Subject",
            "description": "A deterministic fake class used to exercise the generation pipeline offline.",
            "max_hp": 75,
            "max_energy": 3,
            "archetypes": [
                {"id": "alpha", "name": "Alpha", "kind": "classic", "description": "Plain damage."},
                {"id": "beta", "name": "Beta", "kind": "novel", "description": "Plain block."},
            ],
            "relic": {"name_hint": "Fake Carapace", "theme": "a small block at combat start"},
            "cards": [
                {"role": "basic_attack", "name_hint": "Test Strike", "type": "attack", "rarity": "basic",
                 "cost": 1, "archetype": None, "deck_count": 4, "theme": "plain 6 damage"},
                {"role": "basic_skill", "name_hint": "Test Guard", "type": "skill", "rarity": "basic",
                 "cost": 1, "archetype": None, "deck_count": 4, "theme": "plain 5 block"},
                {"role": "signature", "name_hint": "Test Protocol", "type": "skill", "rarity": "basic",
                 "cost": 1, "archetype": "beta", "deck_count": 1, "theme": "a bigger block"},
                {"role": "signature", "name_hint": "Test Smash", "type": "attack", "rarity": "basic",
                 "cost": 1, "archetype": "alpha", "deck_count": 1, "theme": "a bigger hit"},
            ] + pool,
        }
