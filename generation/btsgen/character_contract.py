"""Build the class-blueprint prompt = the contract for WHOLE-CLASS generation.

The character harness is two-stage: (1) one "blueprint" call designs the class — identity,
stats, two synergistic archetypes, and a per-card DESIGN BRIEF list (no effect JSON); then
(2) the existing card/relic pipelines generate each artifact with the blueprint as context,
each validated + repaired independently. This keeps the proven per-card repair loop while
letting the model design the SET as a whole (cross-synergy lives in the blueprint).

The blueprint is harness-internal (validated by BlueprintValidator in python, never shipped
to the engine); only the assembled CharacterData + its cards/relic reach the Godot quarantine.
"""
from __future__ import annotations

import json
from dataclasses import dataclass

from . import paths
from .character_validator import signature_mechanics
from .contract import (declared_status_ids, feedback_section, hp_economy, loop_discipline,
                       rarity_ladder, reprint_section)


@dataclass
class Brief:
    concept: str = ""                 # the player's free-text class concept
    pool_cards_per_archetype: int = 4  # reward-pool cards generated per archetype

    def describe(self) -> str:
        return f"concept: {self.concept}"


# A compact retro-blueprint of the authored Armor Dillo: the few-shot anchor for the FORMAT
# (roles, deck_counts, archetype cross-synergy expressed as briefs, no effect JSON).
_EXAMPLE_BLUEPRINT = {
    "id": "armor_dillo",
    "name": "The Armor Dillo",
    "description": "A defensive bruiser that hoards Block behind permanent plating and burrows underground to weather any blow.",
    "max_hp": 85,
    "max_energy": 3,
    "archetypes": [
        {"id": "bulwark", "name": "Bulwark", "kind": "classic",
         "description": "Permanent Armor makes Block persist between turns; the stacked wall becomes a weapon via block-scaled attacks."},
        {"id": "burrow", "name": "Demolition Burrow", "kind": "novel",
         "description": "Go underground (invulnerable, can't attack) to safely build the wall, plant delayed fuse charges, and let them blow."},
    ],
    "relic": {"name_hint": "Worn Carapace", "theme": "a small defensive boost at the start of each combat"},
    "cards": [
        {"role": "basic_attack", "name_hint": "Strike", "type": "attack", "rarity": "basic",
         "cost": 1, "archetype": None, "deck_count": 4,
         "theme": "the literal Strike starter (synthesized verbatim by the harness)"},
        {"role": "basic_skill", "name_hint": "Defend", "type": "skill", "rarity": "basic",
         "cost": 1, "archetype": None, "deck_count": 4,
         "theme": "the literal Defend starter (synthesized verbatim by the harness)"},
        {"role": "signature", "name_hint": "Burrow", "type": "skill", "rarity": "basic",
         "cost": 1, "archetype": "burrow", "deck_count": 1,
         "theme": "apply burrowed to self: invulnerable through the next enemy turn, but you can't attack this turn"},
        {"role": "signature", "name_hint": "Shell Up", "type": "skill", "rarity": "basic",
         "cost": 1, "archetype": "bulwark", "deck_count": 1, "theme": "a bigger block: the wall-builder signature"},
        {"role": "pool", "name_hint": "Armor Plate", "type": "power", "rarity": "uncommon",
         "cost": 1, "archetype": "bulwark", "deck_count": 0,
         "theme": "gain armor: Block stops resetting each turn (the Barricade enabler)"},
        {"role": "pool", "name_hint": "Crushing Roll", "type": "attack", "rarity": "uncommon",
         "cost": 1, "archetype": "bulwark", "deck_count": 0,
         "theme": "deal damage equal to your current Block (the block-to-offense bridge)"},
        {"role": "pool", "name_hint": "Quick Charge", "type": "skill", "rarity": "common",
         "cost": 1, "archetype": "burrow", "deck_count": 0, "theme": "plant a 1-turn fuse that hits all enemies"},
        {"role": "pool", "name_hint": "Miner's TNT", "type": "skill", "rarity": "uncommon",
         "cost": 1, "archetype": "burrow", "deck_count": 0,
         "theme": "plant a 3-turn fuse that blasts EVERYTHING including you -- burrow to dodge your own bomb"},
    ],
}


def _characters() -> str:
    blocks = []
    for f in sorted(paths.CHARACTERS_DIR.glob("*.json")):
        try:
            blocks.append(json.dumps(json.loads(f.read_text()), indent=2))
        except (json.JSONDecodeError, OSError):
            continue
    return "\n\n".join(blocks)


def _owned_mechanics() -> str:
    """Per-class signature-mechanic lines for the prompt, computed live from the shipped
    card sets (the same map the identity-overlap validator uses), so the rule and the
    check can never disagree."""
    owned: dict[str, list[str]] = {}
    for m, ch in sorted(signature_mechanics().items()):
        kind, name = m.split(":", 1)
        owned.setdefault(ch, []).append(f"{name} ({kind})")
    if not owned:
        return "- (none yet)"
    return "\n".join(f"- {ch}: {', '.join(ms)}" for ch, ms in sorted(owned.items()))


def system_prompt() -> str:
    paths.assert_character_project_present()
    card_vocab = paths.VOCABULARY.read_text(encoding="utf-8")
    relic_vocab = paths.RELIC_VOCABULARY.read_text(encoding="utf-8")
    char_schema = paths.CHARACTER_SCHEMA.read_text(encoding="utf-8")
    statuses = ", ".join(declared_status_ids())
    return f"""You are a CLASS designer for "BLANK the spire", a Slay-the-Spire-like deckbuilder. You design \
a whole new playable class from a player's concept: its identity and stats, TWO deeply synergistic card \
archetypes, a starter relic, and a design brief for every card in its set. You output a single JSON \
"blueprint" — design briefs only, NO card-effect JSON (each card is generated and validated separately \
from your briefs).

THE HARD CONSTRAINT: every mechanic you design must be expressible with the engine's CLOSED vocabulary \
below. There are NO new keywords, statuses, ops, or primitives — the only statuses that exist are: \
{statuses}. If the concept implies a mechanic that doesn't exist, you translate its FANTASY onto \
whichever existing primitives best express it rather than inventing one. A card theme that can't be \
built gets DROPPED by the validator, so design conservatively inside the vocabulary.

MECHANICAL IDENTITY: a mechanic that anchors an existing class's archetype BELONGS to that class. \
Currently owned (computed from the shipped sets):
{_owned_mechanics()}
Do NOT build a new class's archetype on another class's signature mechanic, and don't splash one into \
single cards either, unless the player's concept explicitly asks for that mechanic — the new class \
must feel different to pilot, not be a reskin. Generic currency (damage, block, draw, energy, and the \
shared statuses like weak/vulnerable/frail/strength/dexterity) belongs to everyone; build identity \
from how cards COMBINE it, not from borrowed signatures. The validator flags every use of an owned \
mechanic for human review.

CLASS FANTASY & CREATIVITY: the class must FEEL like its concept through MECHANICS, not just names \
and flavor text. Tag each archetype with a "kind":
- Exactly ONE archetype is "kind": "novel" — INVENT a named, class-defining engine by composing the \
vocabulary's structural primitives in a combination no existing class anchors: `from_state` \
(damage/block/heal whose magnitude reads live state: block, energy, strength, hand_size, \
cards_played_this_turn, hp_lost), `conditional` (predicates on hp/block/energy/hand_size/\
enemy_count/has-status), `multi` with state-scaled times, X-cost cards, `add_card` self-copies and \
card recursion, `lose_hp` as a resource, exhaust timing, or state-scaled status amounts. The novel \
engine IS the archetype: its name should name the mechanic, and every card brief in it must serve \
that engine concretely.
- The OTHER archetype is "kind": "classic" — a proven deckbuilder archetype executed cleanly \
(Strength ramp, big-Block fortress, multi-hit flurry, draw/tempo, energy ramp, self-damage \
recklessness, debuff control...), the familiar on-ramp that makes the novel half readable.
DEBUFF MONOTONY — the failure mode to avoid: past generated classes all collapsed into \
vulnerable/weak spam. Neither archetype may be BUILT on applying vulnerable/weak (unless the \
player's concept explicitly asks for debuff control), and at most a QUARTER of the card briefs may \
involve them. When the concept implies a status that doesn't exist (freeze, poison, burn, charm), \
do NOT default to "apply vulnerable/weak" — translate the fantasy into a composed engine instead; \
that is exactly what the novel archetype is for.

# THE CARD VOCABULARY (what card effects can exist)
{card_vocab}

# THE RELIC VOCABULARY (what the starter relic can do)
{relic_vocab}

{rarity_ladder()}

{reprint_section()}
Briefs are bound by this too: a brief that PLANS one of these lines (e.g. "a power that grants \
+2 Strength" = Inflame) wastes its slot -- the card generator will be steered into a reprint and \
the validator will reject it at uncommon/rare. The classic archetype especially must be executed \
through NEW designs that feel familiar without rebuilding an existing card.

{loop_discipline()}
This binds archetype ENGINES at the brief level: if an archetype's loop closes with fewer than \
three cards, the briefs themselves must price it (energy, HP, exhaust) or widen it.

{hp_economy()}
This binds a self-sacrifice archetype at the brief level: if a brief trades HP for Strength, it \
must keep the loop net-negative on HP -- don't pair a per-turn Strength gain with an equal-or-larger \
per-turn heal in the same class spine, or the bargain has no teeth.

# THE CHARACTER SCHEMA (what the final assembled class must satisfy)
```json
{char_schema}
```

# EXISTING CLASSES (don't overlap their identities; new basics/signatures must be NEW cards, not these)
```json
{_characters()}
```

{feedback_section()}
# THE BLUEPRINT FORMAT (your output — exactly this shape)
This example is the ALREADY-EXISTING Armor Dillo, shown ONLY to anchor the format. Do not reuse its \
archetypes, its signature mechanics (fuse / burrowed / armor), or its themes for a new class.
```json
{json.dumps(_EXAMPLE_BLUEPRINT, indent=2)}
```

# YOUR TASK
Design ONE new class from the player's concept. Requirements:
- Output a SINGLE JSON blueprint object, exactly the format above, and NOTHING else — no prose, no \
markdown fences, no comments.
- Fresh snake_case `id` (not an existing class id), `name` <= 32 chars, `description` <= 200 chars.
- `max_hp` between 60 and 95 (defensive classes higher, glass cannons lower); `max_energy` 3.
- EXACTLY two `archetypes` with snake_case ids, one `"kind": "novel"` and one `"kind": "classic"` \
(see CLASS FANTASY & CREATIVITY above). Each must have a clear mechanical engine, and the two \
must CROSS-SYNERGIZE (cards of one should get better with cards of the other).
- `cards`: exactly ONE `basic_attack` (deck_count 4) and ONE `basic_skill` (deck_count 4). Starting \
decks follow the Slay-the-Spire rule: every class begins with the LITERAL "Strike" (deal 6, upgrade 9) \
and "Defend" (gain 5 Block, upgrade 8) — the harness synthesizes these two verbatim, ignoring your \
name_hint/theme for them, so just write "Strike"/"Defend" and spend NO design effort there. The class's \
flavor and direction live in the ONE or TWO `signature` cards (rarity "basic", deck_count 1 each, the \
class-defining mechanic that hints its archetypes — these are in the starting deck); plus `pool` cards \
(deck_count 0, the reward pool) as the brief requests, tagged with their `archetype` and spanning \
rarities per the RARITY LADDER above: commons enable, uncommons amplify, and EXACTLY ONE RARE PER \
ARCHETYPE as its payoff — the rare's theme must name the build-around engine explicitly (what it \
scales with, what it rewards) and feel like the card the whole archetype is drafted around, not a \
bigger stat line. Signatures may carry an archetype tag too.
- Every card `theme` must be a concrete, mechanically explicit one-line design (numbers optional) that \
the card generator can build from the closed vocabulary. Reference the archetype's engine explicitly.
- `relic`: the starter relic brief — modest power (compare: heal 6 after combat / 4 block at combat \
start), flavored to the class.
- Power discipline: basics are deliberately plain (Strike/Defend tier); the class must not outclass \
the existing ones."""


def user_brief(brief: Brief) -> str:
    n = max(2, int(brief.pool_cards_per_archetype))
    return (
        f"Design a new playable class from this player concept:\n"
        f"\"{brief.concept.strip()}\"\n\n"
        f"Include exactly {n} pool cards per archetype (deck_count 0), plus the basics and signature(s).\n"
        "Return only the JSON blueprint object."
    )


def repair_message(blueprint_text: str, errors: list[str]) -> str:
    bullet = "\n".join(f"- {e}" for e in errors)
    return (
        "That blueprint failed validation:\n"
        f"{bullet}\n\n"
        "Here is what you returned:\n"
        f"{blueprint_text}\n\n"
        "Return a corrected SINGLE JSON blueprint object that fixes every error above and still "
        "matches the concept. Output only the JSON object."
    )
