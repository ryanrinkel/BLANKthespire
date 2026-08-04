"""Build the relic generation prompt = the contract (parallel to contract.py for cards).

System prompt = RELIC_VOCABULARY.md + relic.schema.json + the authored relics as few-shot.
User message = the brief (tier / pool / theme).

A relic is now fully data-driven: `hooks` (trigger -> effects drawn from the SAME closed card
effect vocabulary) + `modifiers` (passive stat bonuses). The model composes from the enumerated
vocabulary only; it never writes code. As with cards, the recursive `effect` schema can't be forced
via structured-outputs, so the contract is carried in the prompt and enforced afterward by RelicValidator.
"""
from __future__ import annotations

import json
from dataclasses import dataclass

from . import paths
from .contract import declared_status_ids, hp_economy

# Few-shot exemplars: ALL authored relics. They are tiny and together span every trigger
# (combat_start/turn_start/turn_end/combat_end/attacked), condition (victory/hp_below_half),
# target override (all_enemies), once_per_combat, raw damage, and both modifier stats — plus
# Philosopher's Stone, which carries a modifier AND a hook.
_FEW_SHOT_IDS = [
    "burning_blood", "vajra", "anchor", "bag_of_marbles", "bag_of_preparation",
    "blood_vial", "oddly_smooth_stone", "lantern", "mercury_hourglass",
    "meat_on_the_bone", "bronze_scales", "centennial_puzzle", "akabeko",
    "energy_core", "philosophers_stone",
]


@dataclass
class Brief:
    tier: str = "common"     # common | uncommon | rare | boss | starter (starter only for class bundles)
    pool: str = "combat"     # combat | elite | boss | shop | starter
    theme: str = ""          # free-text flavor/mechanical nudge, e.g. "reward aggression"
    context: str = ""        # extra design context (e.g. the new class this starter relic belongs to)

    def describe(self) -> str:
        parts = [f"tier: {self.tier}", f"pool: {self.pool}"]
        if self.theme:
            parts.append(f"theme: {self.theme}")
        return ", ".join(parts)


def _exemplars() -> str:
    blocks = []
    for rid in _FEW_SHOT_IDS:
        f = paths.RELICS_DIR / f"{rid}.json"
        if f.exists():
            blocks.append(json.dumps(json.loads(f.read_text()), indent=2))
    return "\n\n".join(blocks)


def system_prompt() -> str:
    paths.assert_relic_project_present()
    vocab = paths.RELIC_VOCABULARY.read_text()
    schema = paths.RELIC_SCHEMA.read_text()
    return f"""You are a relic designer for "BLANK the spire", a Slay-the-Spire-like deckbuilder for a \
single Ironclad-like Strength/Block character. You compose relics as JSON, drawn ONLY from a closed \
vocabulary: a relic is `hooks` (a trigger plus a list of effects from the closed CARD effect \
vocabulary) and/or `modifiers` (passive stat bonuses). You never invent triggers, conditions, ops, \
stats, statuses, or targets — if a mechanic isn't expressible with the vocabulary below, you pick a \
different design that is.

# THE RELIC VOCABULARY (authoring reference: triggers, conditions, targets, modifiers; effects reuse the card ops)
{vocab}

# THE JSON SCHEMA (the hard contract — your output is validated against this)
```json
{schema}
```

# EXEMPLAR RELICS (authored; match this style and power level)
```json
{_exemplars()}
```

{hp_economy()}
For a relic the loop is PER COMBAT / PER TURN: if a hook loses HP to grant Strength, a turn_end (or \
other) heal in the SAME relic must not refund as much HP as the loss -- a relic that does \
`turn_start: lose_hp 1 + strength 1` and `turn_end: heal 2` is the canonical failure (net +1 HP and \
free permanent Strength every turn). Drop the heal, shrink it below the loss, or charge >=3 HP per \
Strength so the bleed is real.

# YOUR TASK
Design ONE new relic matching the brief. Requirements:
- Output a SINGLE JSON object, schema-valid, and NOTHING else — no prose, no markdown fences, no comments.
- Use a fresh, unique snake_case `id` and a short human `name`. Do NOT reuse an exemplar id.
- Compose `hooks`/`modifiers` only from the vocabulary; reference only declared statuses \
({", ".join(declared_status_ids())}) and existing card ids.
- If the brief carries a class context, design for THAT class (e.g. its starter relic) instead of \
the Ironclad.
- Set the `tier` and `pool` from the brief, and write a one-line `description` that matches the mechanics EXACTLY.
- Set `"source": "llm"`.
- Use `"raw": true` on a `damage` effect for FIXED relic damage (thorns / per-turn ticks) so it does \
not scale with Strength. Remember a cheap permanent buff at combat start is power-tier (see the vocab note).
- Aim for the power level implied by the tier — common relics are small, boss relics are run-defining.
- Give it a clear mechanical identity."""


def user_brief(brief: Brief) -> str:
    msg = f"Design a relic with — {brief.describe()}.\n"
    if brief.context:
        msg += f"\n{brief.context}\n"
    msg += "Return only the JSON object."
    return msg


def repair_message(relic_text: str, errors: list[str]) -> str:
    bullet = "\n".join(f"- {e}" for e in errors)
    return (
        "That relic failed validation:\n"
        f"{bullet}\n\n"
        "Here is what you returned:\n"
        f"{relic_text}\n\n"
        "Return a corrected SINGLE JSON object that fixes every error above and still "
        "matches the brief. Output only the JSON object."
    )
