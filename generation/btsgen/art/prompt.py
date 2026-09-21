"""Build the image prompt from a class.

The optional cheap-LLM call the plan allowed lives in enrich.py: when it produces an
`enriched_body`, that text REPLACES the raw description/concept/theme lines here — but the
composition/cut-out constraints and the style suffix are always template-appended, and the no-LLM
path (enriched_body=None) remains the valid fallback. Never touches blueprint/card/relic calls."""
from __future__ import annotations

from .request import ClassArt, StyleProfile


def splash_prompt(art: ClassArt, style: StyleProfile, enriched_body: str | None = None) -> str:
    parts = [f'Splash art for "{art.name}", a playable class in a dark-fantasy deckbuilder.']
    _append_concept(parts, art)
    if enriched_body:
        parts.append(enriched_body)
    else:
        if art.description:
            parts.append(art.description)
        if art.concept:
            parts.append(f"Concept: {art.concept}.")
        _append_theme(parts, art)
    # In-game the splash is a full-bleed character-select background and the menu UI covers the left
    # ~two-thirds of the screen — only the right third reads clearly. gpt-image-1 has no layout
    # controls, so composition is steered entirely by this prompt text.
    parts.append(
        "Composition: an off-center rule-of-thirds layout with the subject placed in the RIGHT "
        "third of the frame, facing inward toward the left. The left two-thirds are quiet atmospheric "
        "background (mist, scenery, mood) with no focal elements, no second character, and nothing "
        "important, as that area will be covered by menu UI. Keep the ENTIRE character inside the "
        "frame with clear margin — the top and the base of the subject must sit well inside the edges, "
        "and nothing important may touch the top or bottom 12% of the frame, which can be cropped "
        "on different screen shapes."
    )
    if style.prompt_suffix:
        parts.append(style.prompt_suffix)
    return " ".join(p.strip() for p in parts if p and p.strip())


def sprite_prompt(art: ClassArt, style: StyleProfile, enriched_body: str | None = None) -> str:
    """The combat-model sprite: one whole subject, cut out on alpha, facing right (the player side faces
    its enemies to the right in battle; the mod handles cropping/scaling/animation).

    Subject-NEUTRAL on purpose (2026-09-21): the old wording ("character ... head to feet, standing ... feet near
    the bottom") made a Sherman tank render as a bipedal mech — the model grew legs to satisfy "feet". A class
    can be a person, a creature, a vehicle, a machine or an object, so the pose/framing clause names the subject's
    top and base generically and forbids anthropomorphizing."""
    parts = [f'Full-body combat sprite of "{art.name}", the playable class of a dark-fantasy deckbuilder.']
    _append_concept(parts, art)
    if enriched_body:
        parts.append(enriched_body)
    else:
        if art.description:
            parts.append(art.description)
        if art.concept:
            parts.append(f"Concept: {art.concept}.")
        _append_theme(parts, art)
    parts.append(
        "Exactly one subject, shown whole from its top to its base (a person from head to feet, a vehicle from "
        "turret to treads, a creature from crown to paws), in an idle battle-ready pose, facing right in "
        "three-quarter view, its base resting near the bottom edge of the frame. Draw the subject as what it is: "
        "if it is a vehicle, machine, animal, monster or object, do NOT anthropomorphize it — no added legs, arms, "
        "torso or face it does not have, and no humanoid stand-in."
    )
    parts.append(
        "Isolated on a fully transparent background: no scenery, no ground plane, no cast shadow, "
        "no text, no frame."
    )
    if style.prompt_suffix:
        parts.append(style.prompt_suffix)
    return " ".join(p.strip() for p in parts if p and p.strip())


def _append_concept(parts: list[str], art: ClassArt) -> None:
    """The player's own words, verbatim, ALWAYS — before any description/enrichment. A forge abstracts
    "Truman from the Truman Show" into "a man who rewrites himself mid-scene"; the image must still draw
    Truman. Named subjects (real or fictional) are to be depicted literally and recognizably."""
    c = (art.concept or "").strip()
    if c:
        parts.append(f'The player asked for: "{c}". Depict exactly that subject, literally and recognizably '
                     "(if it names a specific person, character, creature or thing, draw that one, with its "
                     "canonical look, costume and props), not a generic stand-in.")


def _append_theme(parts: list[str], art: ClassArt) -> None:
    # Prefer FLAVOR motifs (the subject's dress) over MECHANICAL archetype names — the archetypes describe the
    # engine ("Gambler / RNG jackpot"), which misdirects the image away from the theme. Fall back to archetypes
    # for concept-mode forges / older bundles that carry no skin.
    if art.imagery or art.flavor:
        if art.flavor:
            parts.append("Evoke " + ", ".join(art.flavor) + ".")
        if art.imagery:
            parts.append("Visual motifs: " + ", ".join(art.imagery) + ".")
    elif art.archetypes:
        parts.append("Themes: " + ", ".join(art.archetypes) + ".")
