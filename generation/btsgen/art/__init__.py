"""Pluggable class splash-art generation — a standalone, optional add-on to the forge.

Decoupled by design: this package READS forge output (an in-memory bundle dict, or the on-disk
character.json/meta.json the pipeline quarantines) and writes an image beside it. NOTHING in the
creative harness imports this package, and importing it never triggers generation. Select a backend
with $BTSGEN_IMAGE_BACKEND or forge_splash(backend=...); the default 'null' backend does nothing, so
the whole feature is strictly opt-in and a missing key can never make a class fail to forge.

Swap the image generator by changing one name (env var or arg) — see registry / backends/. Swap the
LOOK (independently of the generator) by passing a different StyleProfile. See SPLASH_ART_PLAN.md.
"""
from .request import ClassArt, ImageRequest, ImageResult, StyleProfile
from .styles import CARD_STYLE, DEFAULT_STYLE, SPRITE_STYLE
from .registry import available_backends, get_backend, register, resolve_backends
from .extract import class_art_from_bundle, class_art_from_disk, hue_from_id
from .prompt import splash_prompt, sprite_prompt
from .splash import forge_splash
from .sprite import forge_sprite
from .card import (CARD_PORTRAIT_SIZE, card_prompt, fit_to_portrait, forge_card_art,
                   portrait_crop_box)

__all__ = [
    "ClassArt", "ImageRequest", "ImageResult", "StyleProfile",
    "DEFAULT_STYLE", "SPRITE_STYLE", "CARD_STYLE", "CARD_PORTRAIT_SIZE",
    "available_backends", "get_backend", "register", "resolve_backends",
    "class_art_from_bundle", "class_art_from_disk", "hue_from_id",
    "splash_prompt", "sprite_prompt", "card_prompt",
    "forge_splash", "forge_sprite", "forge_card_art",
    "portrait_crop_box", "fit_to_portrait",
]
