"""Optional cheap-LLM prompt enrichment — the 'one small call' prompt.py reserved.

Turns a class's raw flavor (name/description/concept/imagery) into a vivid 2-4 sentence visual
description that the image prompt leads with. The template path stays the always-valid fallback:
this returns None on ANY failure (disabled, no key, network, bad response) and the caller keeps the
plain template prompt. It never touches the blueprint/card/relic generation calls.

Opt-in like the image backend itself (no existing flow grows a network call silently):
    BTSGEN_PROMPT_ENRICH        1 | true | on  -> enabled
    BTSGEN_PROMPT_ENRICH_MODEL  default 'gpt-5-mini' (cheap OpenAI text model)
    key: BTSGEN_IMAGE_API_KEY or OPENAI_API_KEY (same key as the image backend)

The LLM writes ONLY the descriptive body. Hard constraints — splash composition (right-third),
sprite cut-out/pose rules, and the style suffix — are appended by the template afterwards, so a
creative model can never talk the image out of its layout contract."""
from __future__ import annotations

import json
import os
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .request import ClassArt

_ENDPOINT = "https://api.openai.com/v1/chat/completions"

_SYSTEM = (
    "You are an art director for a dark-fantasy roguelike deckbuilder. Given a playable class's "
    "flavor notes, write a vivid visual description for an illustrator: the character's look, "
    "costume, props, and signature visual motifs{scene}. 2-4 sentences, at most 90 words, concrete "
    "and paintable. Do NOT mention composition, camera framing, art style, transparency, or "
    "backgrounds being covered by UI — those are specified separately. No text, lettering, or "
    "logos in the scene. Reply with the description only."
)
_SCENE = {
    "splash": ", plus the surrounding environment and mood",
    "sprite": ". Describe the single standing figure only — no environment",
}


def enabled() -> bool:
    return os.environ.get("BTSGEN_PROMPT_ENRICH", "").strip().lower() in ("1", "true", "on")


def _key() -> str | None:
    return os.environ.get("BTSGEN_IMAGE_API_KEY") or os.environ.get("OPENAI_API_KEY")


def enrich_body(art: ClassArt, kind: str, on_event=None) -> str | None:
    """The enriched descriptive body for `kind` ('splash' | 'sprite'), or None -> use the template."""
    if not enabled():
        return None
    key = _key()
    if not key:
        return None

    notes = [f"Class name: {art.name}"]
    if art.description:
        notes.append(f"Description: {art.description}")
    if art.concept:
        notes.append(f"Concept: {art.concept}")
    if art.flavor:
        notes.append("Flavor: " + ", ".join(art.flavor))
    if art.imagery:
        notes.append("Visual motifs: " + ", ".join(art.imagery))
    if not (art.flavor or art.imagery) and art.archetypes:
        notes.append("Mechanical archetypes (deprioritize, flavor only): " + ", ".join(art.archetypes))

    model = os.environ.get("BTSGEN_PROMPT_ENRICH_MODEL", "gpt-5-mini").strip()
    body = json.dumps({
        "model": model,
        "messages": [
            {"role": "system", "content": _SYSTEM.format(scene=_SCENE.get(kind, ""))},
            {"role": "user", "content": "\n".join(notes)},
        ],
        "max_completion_tokens": 2000,  # gpt-5-family reasoning tokens count against this too
    }).encode("utf-8")
    request = Request(_ENDPOINT, data=body, method="POST", headers={
        "Authorization": f"Bearer {key}", "Content-Type": "application/json"})

    def note(msg: str) -> None:
        if on_event:
            on_event(msg)

    try:
        with urlopen(request, timeout=60) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        text = (payload["choices"][0]["message"]["content"] or "").strip()
    except (HTTPError, URLError, TimeoutError) as e:
        note(f"prompt enrichment skipped ({type(e).__name__}) — using template prompt")
        return None
    except Exception as e:
        note(f"prompt enrichment skipped ({type(e).__name__}: {e}) — using template prompt")
        return None

    # A wildly long or empty reply is a model misfire; the template is better than garbage.
    if not text or len(text) > 1200:
        note("prompt enrichment skipped (empty/oversized reply) — using template prompt")
        return None
    return text
