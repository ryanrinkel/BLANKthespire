"""Shipped StyleProfile(s). The DEFAULT is the consistency anchor real backends share; add more here
(or a styles/ dir) and select per-forge to A/B looks without touching backend code."""
from __future__ import annotations

from .request import StyleProfile

DEFAULT_STYLE = StyleProfile(
    name="default",
    prompt_suffix=(
        "Painterly digital illustration in the manner of AAA game key art: confident visible "
        "brushwork, dramatic rim lighting, strong silhouette read, cinematic color grading with "
        "deep shadows and one bold accent color, moody dark-fantasy atmosphere — character splash "
        "art for a Slay-the-Spire-like roguelike deckbuilder. Detailed, expressive face; "
        "atmospheric background depth with volumetric light. No text, no UI, no card frame."
    ),
    negative="text, watermark, ui, hud, card frame, logo, signature, border",
    size=(1024, 576),
    out_format="png",
)

# The standing combat model (the in-battle player sprite): a single cut-out figure on alpha. Portrait
# orientation + transparent so the mod can autocrop, resize to its ~300px stage height, and tween it.
# Same painterly family as DEFAULT_STYLE so a class's sprite and splash read as one artwork.
SPRITE_STYLE = StyleProfile(
    name="sprite",
    prompt_suffix=(
        "Painterly digital illustration with confident brushwork and dramatic rim lighting, "
        "dark-fantasy character art in the same style family as the class splash, for a "
        "Slay-the-Spire-like roguelike deckbuilder. Strong readable silhouette, grounded stance, "
        "crisp clean cut-out edges, rich material detail on costume and props."
    ),
    negative=(
        "background, scenery, ground plane, cast shadow, text, watermark, ui, hud, frame, logo, "
        "signature, border, multiple characters, cropped limbs"
    ),
    size=(1024, 1536),
    out_format="png",
    transparent=True,
)
