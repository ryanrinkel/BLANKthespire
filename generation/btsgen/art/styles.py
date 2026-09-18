"""Shipped StyleProfile(s). The DEFAULT is the consistency anchor real backends share; add more here
(or a styles/ dir) and select per-forge to A/B looks without touching backend code."""
from __future__ import annotations

from .request import StyleProfile

DEFAULT_STYLE = StyleProfile(
    name="default",
    # 2026-09-17 A/B (five prod prompts, Qwen Image 3): DESCRIBING the look in words reproduces the game's
    # own cel-shaded ink-line style; merely naming Slay the Spire changed nothing, and attaching STS2
    # portraits as references matched this but bled their characters/text into the output.
    prompt_suffix=(
        "Art style: bold stylized game illustration in the manner of Slay the Spire's character art — "
        "confident dark ink outlines, flat cel-shaded color blocks with light painterly texture, simplified "
        "graphic shapes, a saturated limited palette with one bold accent color, and a moody dark-fantasy "
        "atmosphere with a strong silhouette read. Not photorealistic, not painterly-realistic. "
        "Style only: no lettering or text anywhere, no UI, no card frame."
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
        "Art style: bold stylized game illustration in the manner of Slay the Spire's character art — "
        "confident dark ink outlines, flat cel-shaded color blocks with light painterly texture, simplified "
        "graphic shapes, a saturated limited palette; the same style family as the class splash. "
        "Not photorealistic. Strong readable silhouette, grounded stance, crisp clean cut-out edges, "
        "clear material detail on costume and props. No lettering or text anywhere."
    ),
    negative=(
        "background, scenery, ground plane, cast shadow, text, watermark, ui, hud, frame, logo, "
        "signature, border, multiple characters, cropped limbs"
    ),
    size=(1024, 1536),
    out_format="png",
    transparent=True,
)

# One illustration per CARD (art/card.py). Deliberately the SAME prompt suffix object as DEFAULT_STYLE so a
# class's splash, sprite and 34 card portraits read as one artwork — a card style that drifts from the splash
# is the failure mode this profile exists to prevent. 1536x1024 snaps to "3:2", the only landscape ratio the
# OpenAI image family accepts on OpenRouter (4:3 is rejected); the renders are then cropped to the mod's
# 1000x760 portrait box. The negative is tighter than DEFAULT's: a card portrait sits INSIDE a frame the game
# draws, so any painted frame/border/lettering is a defect.
CARD_STYLE = StyleProfile(
    name="card",
    prompt_suffix=DEFAULT_STYLE.prompt_suffix,
    negative="text, lettering, watermark, ui, card frame, border, logo",
    size=(1536, 1024),
    out_format="png",
)
