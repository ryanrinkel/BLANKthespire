"""OpenAI image backend — the first real cloud image generator.

Zero new dependencies: a single JSON POST via stdlib urllib (cloud backends lazy-load their own client;
this one needs none). Reads the API key from the environment so the SERVER (droplet) pays per forge:
    BTSGEN_IMAGE_API_KEY  (preferred) or OPENAI_API_KEY
    BTSGEN_IMAGE_QUALITY  low | medium (default) | high
    BTSGEN_IMAGE_MODEL    default 'gpt-image-2' (gpt-image-1 retires 2026-10-23; -1.5 also works)
    BTSGEN_IMAGE_SPRITE_MODEL  default 'gpt-image-1.5' — used for TRANSPARENT requests (sprites):
                          gpt-image-2 400s on background=transparent (verified live 2026-07-20)
Selected with BTSGEN_IMAGE_BACKEND=openai. `available()` is false with no key, so it degrades to no
splash (never blocks a forge). Outputs PNG so the mod's LoadPngFromBuffer reads it directly.

Style consistency is via the StyleProfile prompt suffix for now; reference-image conditioning (the
/images/edits endpoint) is a later enhancement — req.ref_images is accepted but unused here."""
from __future__ import annotations

import base64
import json
import os
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from ..request import ImageRequest, ImageResult

_ENDPOINT = "https://api.openai.com/v1/images/generations"

# Rough per-image USD estimates by model (size x quality) for the token-economy meter. Not billed on;
# advisory. gpt-image-2 bills per output token ($30/M vs gpt-image-1's $40/M); its rows scale
# gpt-image-1's published per-image table by 0.75 assuming like token counts. None when unknown.
_COST = {
    "gpt-image-1": {
        ("1024x1024", "low"): 0.011, ("1024x1024", "medium"): 0.042, ("1024x1024", "high"): 0.167,
        ("1536x1024", "low"): 0.016, ("1536x1024", "medium"): 0.063, ("1536x1024", "high"): 0.250,
        ("1024x1536", "low"): 0.016, ("1024x1536", "medium"): 0.063, ("1024x1536", "high"): 0.250,
    },
    "gpt-image-1.5": {  # official per-image table
        ("1024x1024", "low"): 0.009, ("1024x1024", "medium"): 0.034, ("1024x1024", "high"): 0.133,
        ("1536x1024", "low"): 0.013, ("1536x1024", "medium"): 0.050, ("1536x1024", "high"): 0.200,
        ("1024x1536", "low"): 0.013, ("1024x1536", "medium"): 0.050, ("1024x1536", "high"): 0.200,
    },
    "gpt-image-2": {
        ("1024x1024", "low"): 0.008, ("1024x1024", "medium"): 0.032, ("1024x1024", "high"): 0.125,
        ("1536x1024", "low"): 0.012, ("1536x1024", "medium"): 0.047, ("1536x1024", "high"): 0.188,
        ("1024x1536", "low"): 0.012, ("1024x1536", "medium"): 0.047, ("1024x1536", "high"): 0.188,
    },
}

# Models that reject background=transparent (HTTP 400, param 'background'; hit live 2026-07-20).
_NO_TRANSPARENT = {"gpt-image-2"}


class OpenAIImageBackend:
    name = "openai"

    @staticmethod
    def _key() -> str | None:
        return os.environ.get("BTSGEN_IMAGE_API_KEY") or os.environ.get("OPENAI_API_KEY")

    def available(self) -> bool:
        return bool(self._key())

    def generate(self, req: ImageRequest) -> ImageResult:
        key = self._key()
        if not key:
            return ImageResult(ok=False, backend=self.name,
                               error="no API key (set BTSGEN_IMAGE_API_KEY or OPENAI_API_KEY)")

        size = _nearest_size(req.size)
        quality = os.environ.get("BTSGEN_IMAGE_QUALITY", "medium").strip().lower()
        model = os.environ.get("BTSGEN_IMAGE_MODEL", "gpt-image-2").strip()
        if req.transparent and model in _NO_TRANSPARENT:
            model = os.environ.get("BTSGEN_IMAGE_SPRITE_MODEL", "gpt-image-1.5").strip()
        payload_body = {
            "model": model, "prompt": req.prompt, "n": 1,
            "size": size, "quality": quality, "output_format": "png",
        }
        if req.transparent:  # character sprites: cut-out subject on an alpha channel
            payload_body["background"] = "transparent"
        body = json.dumps(payload_body).encode("utf-8")

        request = Request(_ENDPOINT, data=body, method="POST", headers={
            "Authorization": f"Bearer {key}", "Content-Type": "application/json"})
        try:
            with urlopen(request, timeout=180) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
        except HTTPError as e:
            detail = e.read().decode("utf-8", "replace")[:400] if hasattr(e, "read") else ""
            return ImageResult(ok=False, backend=self.name, error=f"HTTP {e.code}: {detail}")
        except (URLError, TimeoutError) as e:
            return ImageResult(ok=False, backend=self.name, error=f"network error: {e}")
        except Exception as e:
            return ImageResult(ok=False, backend=self.name, error=f"{type(e).__name__}: {e}")

        try:
            img_bytes = base64.b64decode(payload["data"][0]["b64_json"])
        except Exception as e:
            return ImageResult(ok=False, backend=self.name, error=f"unexpected response shape: {e}")

        try:
            req.out_path.parent.mkdir(parents=True, exist_ok=True)
            req.out_path.write_bytes(img_bytes)
        except OSError as e:
            return ImageResult(ok=False, backend=self.name, error=f"write failed: {e}")

        w, h = (int(x) for x in size.split("x"))
        return ImageResult(ok=True, backend=self.name, path=req.out_path,
                           cost_usd=_COST.get(model, {}).get((size, quality)), width=w, height=h)


def _nearest_size(size: tuple[int, int]) -> str:
    """The gpt-image family supports 1024x1024 / 1536x1024 / 1024x1536 — snap to the nearest orientation."""
    w, h = size
    if w > h:
        return "1536x1024"
    if h > w:
        return "1024x1536"
    return "1024x1024"
