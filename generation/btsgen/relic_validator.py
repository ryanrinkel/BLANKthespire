"""Validator-in-the-loop for relics (parallel to validator.py for cards).

Three checks, mirroring the engine gate:
1. Schema shape + closed vocabulary (triggers/conditions/targets/ops/stats + recursion)
   -> jsonschema against relic.schema.json.
2. Reference integrity (a hook's apply_status.status / add_card.card_id resolve) -> reuses the
   card known-id sets and effect walk (relic hook effects ARE card effects now).
3. Balance -> a COARSE tier-band heuristic. A relic's value is "per combat / whole run", not
   "per play", so the card score does NOT transfer; this is a deliberately rough SURFACER for
   human review, never the final judge. It estimates per-hook effect value (reusing the card
   effect weights) times a trigger-frequency factor, plus a heavy weight for passive modifiers,
   and warns when a relic is wildly out of band for its tier. Warnings only — never a reject.

NOTE we do NOT port the card "cheap permanent buff" tripwire: relics are *supposed* to grant
permanent per-combat buffs (Vajra gives permanent Strength every fight and is a fine common).
"""
from __future__ import annotations

import json

from jsonschema import Draft202012Validator

from . import paths
from .validator import CardValidator, ValidationResult

# Rough per-tier power ceilings for the surfacer. Calibrated so the authored corpus sits inside
# its band (boss energy relics score ~20; commons sit in single digits).
_TIER_CEILING = {"starter": 999.0, "common": 13.0, "uncommon": 24.0, "rare": 40.0, "boss": 60.0}

# How often a trigger pays out over a fight (rough). turn_start/turn_end recur every turn, so they
# are worth several combat_start payouts; once_per_combat collapses any trigger to a single payout.
_TRIGGER_FREQ = {
    "combat_start": 1.0, "combat_end": 1.0, "attacked": 1.5, "turn_start": 3.0, "turn_end": 3.0,
    "on_hp_lost": 1.5,  # Phase P: reactive, situational — payouts land only on your own HP-loss turns (~attacked)
}


class RelicValidator:
    """Loads the relic schema once; reuses a CardValidator for the shared id-sets + effect scoring."""

    def __init__(self) -> None:
        paths.assert_relic_project_present()
        schema = json.loads(paths.RELIC_SCHEMA.read_text())
        self._schema_validator = Draft202012Validator(schema)
        # The card validator already loads known statuses, known card ids, and the effect scorer.
        self._cards = CardValidator()
        self.known_statuses = self._cards.known_statuses
        self.known_cards = self._cards.known_cards
        # authored + already-quarantined relic ids, for the pipeline's unique-id check
        self.known_relics = (CardValidator._ids_in(paths.RELICS_DIR)
                             | CardValidator._ids_in(paths.GENERATED_RELICS_DIR))

    # -- public ------------------------------------------------------------
    def validate(self, relic: dict) -> ValidationResult:
        errors = self._schema_errors(relic)
        if isinstance(relic, dict):
            errors += self._ref_errors(relic)
            if not relic.get("hooks") and not relic.get("modifiers"):
                errors.append("relic has neither 'hooks' nor 'modifiers' (it would do nothing)")
        if errors:
            return ValidationResult(ok=False, errors=errors)
        score = self.score_relic(relic)
        return ValidationResult(ok=True, warnings=self.balance_warnings(relic, score), score=score)

    # -- 1. schema ---------------------------------------------------------
    def _schema_errors(self, relic) -> list[str]:
        out: list[str] = []
        for e in sorted(self._schema_validator.iter_errors(relic), key=lambda e: list(e.path)):
            loc = "/".join(str(p) for p in e.path) or "(root)"
            out.append(f"schema [{loc}]: {e.message}")
        return out

    # -- 2. reference integrity -------------------------------------------
    def _ref_errors(self, relic: dict) -> list[str]:
        out: list[str] = []
        cards_ok = self.known_cards

        def walk(effects, path: str) -> None:
            if not isinstance(effects, list):
                return
            for i, eff in enumerate(effects):
                if not isinstance(eff, dict):
                    continue
                p = f"{path}[{i}]"
                op = eff.get("op")
                if op == "apply_status":
                    s = eff.get("status")
                    if isinstance(s, str) and s not in self.known_statuses:
                        out.append(f"{p}: unknown status '{s}' (not in data/statuses/)")
                elif op == "add_card":
                    c = eff.get("card_id")
                    if isinstance(c, str) and c not in cards_ok:
                        out.append(f"{p}: add_card references unknown card '{c}'")
                elif op == "multi":
                    walk(eff.get("effects"), f"{p}.effects")
                elif op == "conditional":
                    walk(eff.get("then"), f"{p}.then")
                    walk(eff.get("else"), f"{p}.else")

        for i, hook in enumerate(relic.get("hooks", []) or []):
            if isinstance(hook, dict):
                walk(hook.get("effects"), f"hooks[{i}].effects")
        return out

    # -- 3. balance (coarse tier-band surfacer) ---------------------------
    def score_relic(self, relic: dict) -> float:
        total = 0.0
        for hook in relic.get("hooks", []) or []:
            if not isinstance(hook, dict):
                continue
            hook_value = sum(self._cards._score_effect(e) for e in hook.get("effects", []) or [])
            freq = 1.0 if hook.get("once_per_combat") else _TRIGGER_FREQ.get(hook.get("trigger"), 1.0)
            total += hook_value * freq
        for m in relic.get("modifiers", []) or []:
            total += self._modifier_value(m)
        return total

    @staticmethod
    def _modifier_value(m) -> float:
        if not isinstance(m, dict):
            return 0.0
        amt = m.get("amount", 0)
        amt = float(amt) if isinstance(amt, (int, float)) and not isinstance(amt, bool) else 0.0
        stat = m.get("stat")
        if stat == "max_energy":
            return 20.0 * amt        # an extra energy/turn is run-defining (boss-tier)
        if stat == "attack_base":
            return amt * (1.0 if m.get("when") == "first_attack" else 3.0)
        return 0.0

    def balance_warnings(self, relic: dict, score: float | None = None) -> list[str]:
        if score is None:
            score = self.score_relic(relic)
        tier = relic.get("tier", "common")
        ceiling = _TIER_CEILING.get(tier, 24.0)
        if score > ceiling:
            return [f"power proxy {score:.1f} exceeds ~{ceiling:.0f} for tier '{tier}' "
                    f"(coarse heuristic -- review by hand)"]
        return []
