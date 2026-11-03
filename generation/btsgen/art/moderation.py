"""Content-safety fallbacks shared by every asset kind (splash / sprite / card).

2026-11-01, class 97 ("Umbreon, the Red Cloaked"): the chain openrouter,openai sent the SAME prompt to
gpt-image-2 on OpenRouter and then to OpenAI direct; both answered HTTP 400 "rejected by the safety
system" and the class shipped with no splash. Two vendors behind ONE moderation layer are not a fallback
for a moderation block. So when every tier fails AND the failure reads as moderation, splash._forge_asset
climbs two extra rungs (cards keep their own flavor-strip retry, see card.py):

  rung 1  the ORIGINAL prompt on a non-OpenAI model via OpenRouter on the SERVER's key — FLUX.2 Klein by
          default ($0.015, ~3 s, PNG, any ratio; already the card ladder's net). The player's concept
          survives intact. Server chain only (backend=None): a BYOK forge never touches the server's key.
  rung 2  a NEUTRAL prompt (no class name, no verbatim concept, no forge description — see
          prompt.splash_prompt(neutral=True)) on the forge's own chain, BYOK included.

Env:
    BTSGEN_MODERATION_FALLBACK_MODEL   rung-1 model id, default 'black-forest-labs/flux.2-klein-4b';
                                       '' / 'off' / 'none' / '0' disables rung 1 (rung 2 still runs)."""
from __future__ import annotations

import os

_MODERATION_MARKERS = ("moderation", "flagged", "safety", "content policy", "blocked this request",
                       "content_policy", "safety_violations", "rejected by the safety")

FALLBACK_MODEL_ENV = "BTSGEN_MODERATION_FALLBACK_MODEL"
DEFAULT_FALLBACK_MODEL = "black-forest-labs/flux.2-klein-4b"
_OFF = ("", "off", "none", "0", "false", "no")


def looks_moderated(error) -> bool:
    """Whether a backend error reads like a content-safety block rather than a transport/param fault."""
    e = str(error or "").lower()
    return any(m in e for m in _MODERATION_MARKERS)


def fallback_model() -> str | None:
    """The rung-1 model id, or None when switched off. UNSET means the default; set-but-empty means off."""
    raw = os.environ.get(FALLBACK_MODEL_ENV)
    if raw is None:
        return DEFAULT_FALLBACK_MODEL
    raw = raw.strip()
    return None if raw.lower() in _OFF else raw


def fallback_backend():
    """An OpenRouter backend PINNED to the rung-1 model for every kind, on the server's env key, or None
    (rung 1 off). The caller still gates on .available() (no OPENROUTER_API_KEY -> skipped)."""
    model = fallback_model()
    if not model:
        return None
    from .backends.openrouter import OpenRouterImageBackend  # lazy, like the registry
    return OpenRouterImageBackend(model=model, sprite_model=model, card_model=model)


__all__ = ["looks_moderated", "fallback_model", "fallback_backend", "DEFAULT_FALLBACK_MODEL",
           "FALLBACK_MODEL_ENV"]
