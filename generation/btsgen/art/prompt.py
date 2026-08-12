"""Build the image prompt from a class.

The optional cheap-LLM call the plan allowed lives in enrich.py: when it produces an
`enriched_body`, that text REPLACES the raw description/concept/theme lines here — but the
composition/cut-out constraints and the style suffix are always template-appended, and the no-LLM
path (enriched_body=None) remains the valid fallback. Never touches blueprint/card/relic calls."""
from __future__ import annotations

from .request import ClassArt, StyleProfile


def splash_prompt(art: ClassArt, style: StyleProfile, enriched_body: str | None = None) -> str:
    parts = [f'Splash art for "{art.name}", a playable class in a dark-fantasy deckbuilder.']
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
        "Composition: an off-center rule-of-thirds layout with the character standing in the RIGHT "
        "third of the frame, facing inward toward the left. The left two-thirds are quiet atmospheric "
        "background (mist, scenery, mood) with no focal elements, no second character, and nothing "
        "important, as that area will be covered by menu UI. Keep the ENTIRE character inside the "
        "frame with clear margin — the top of the head and the feet must sit well inside the edges, "
        "and nothing important may touch the top or bottom 12% of the frame, which can be cropped "
        "on different screen shapes."
    )
    if style.prompt_suffix:
        parts.append(style.prompt_suffix)
    return " ".join(p.strip() for p in parts if p and p.strip())


def sprite_prompt(art: ClassArt, style: StyleProfile, enriched_body: str | None = None) -> str:
    """The standing combat-model sprite: one whole figure, cut out on alpha, facing right (the player
    side faces its enemies to the right in battle; the mod handles cropping/scaling/animation)."""
    parts = [f'Full-body character sprite of "{art.name}", the playable hero of a dark-fantasy deckbuilder.']
    if enriched_body:
        parts.append(enriched_body)
    else:
        if art.description:
            parts.append(art.description)
        if art.concept:
            parts.append(f"Concept: {art.concept}.")
        _append_theme(parts, art)
    parts.append(
        "Exactly one character, whole body visible from head to feet, standing combat-idle pose, "
        "facing right in three-quarter view, feet near the bottom edge of the frame."
    )
    parts.append(
        "Isolated on a fully transparent background: no scenery, no ground plane, no cast shadow, "
        "no text, no frame."
    )
    if style.prompt_suffix:
        parts.append(style.prompt_suffix)
    return " ".join(p.strip() for p in parts if p and p.strip())


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
