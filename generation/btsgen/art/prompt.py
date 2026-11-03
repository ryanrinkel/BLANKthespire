"""Build the image prompt from a class.

The optional cheap-LLM call the plan allowed lives in enrich.py: when it produces an
`enriched_body`, that text REPLACES the raw description/concept/theme lines here — but the
composition/cut-out constraints and the style suffix are always template-appended, and the no-LLM
path (enriched_body=None) remains the valid fallback. Never touches blueprint/card/relic calls."""
from __future__ import annotations

from .request import ClassArt, StyleProfile


def splash_prompt(art: ClassArt, style: StyleProfile, enriched_body: str | None = None,
                  neutral: bool = False) -> str:
    """`neutral=True` is the moderation fallback's last rung (see moderation.py / _append_body): no class
    name, no verbatim concept, no forge-written description, no enrichment — only the theme motifs, the
    composition rule and the style suffix."""
    if neutral:
        parts = ["Splash art for an original playable hero class in a dark-fantasy deckbuilder."]
    else:
        parts = [f'Splash art for "{art.name}", a playable class in a dark-fantasy deckbuilder.']
    _append_body(parts, art, enriched_body, neutral)
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


def sprite_prompt(art: ClassArt, style: StyleProfile, enriched_body: str | None = None,
                  neutral: bool = False) -> str:
    """The combat-model sprite: one whole subject, cut out on alpha, facing right (the player side faces
    its enemies to the right in battle; the mod handles cropping/scaling/animation).

    Subject-NEUTRAL on purpose (2026-09-21): the old wording ("character ... head to feet, standing ... feet near
    the bottom") made a Sherman tank render as a bipedal mech — the model grew legs to satisfy "feet". A class
    can be a person, a creature, a vehicle, a machine or an object, so the pose/framing clause names the subject's
    top and base generically and forbids anthropomorphizing. `neutral=True`: see splash_prompt."""
    if neutral:
        parts = ["Full-body combat sprite of an original playable hero class of a dark-fantasy deckbuilder."]
    else:
        parts = [f'Full-body combat sprite of "{art.name}", the playable class of a dark-fantasy deckbuilder.']
    _append_body(parts, art, enriched_body, neutral)
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


def _append_body(parts: list[str], art: ClassArt, enriched_body: str | None, neutral: bool) -> None:
    """The "what to draw" middle of the splash/sprite prompt.

    NEUTRAL (the moderation fallback's rung 2 — both vendors already refused the full prompt): drop every
    line that carries the player's own words or a proper noun — the verbatim concept, the "Concept:" echo,
    the forge-written description (it routinely repeats the class name and the concept's nouns, e.g. a
    Pokemon name) and any LLM enrichment (written FROM the concept). Keep only the flavor / imagery motifs
    (archetype names when the bundle has no skin): the theme still reads, the triggering subject does not."""
    if neutral:
        _append_theme(parts, art)
        return
    _append_concept(parts, art)
    if enriched_body:
        parts.append(enriched_body)
    else:
        if art.description:
            parts.append(art.description)
        if art.concept:
            parts.append(f"Concept: {art.concept}.")
        _append_theme(parts, art)


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
