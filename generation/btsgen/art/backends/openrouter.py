"""OpenRouter image backend — one key, ~50 image models (Qwen Image, Seedream, FLUX, Nano Banana,
Recraft, GPT Image ...) behind OpenRouter's unified Image API. Lets us A/B image models with an env
flip instead of a new backend per vendor.

Zero new dependencies (stdlib urllib, same shape as openai.py). Env:
    OPENROUTER_API_KEY                 required (the same key the text side's OpenRouter config uses)
    BTSGEN_OPENROUTER_MODEL            splash model, default 'qwen/qwen-image-3'
    BTSGEN_OPENROUTER_SPRITE_MODEL     transparent (sprite) model, default 'openai/gpt-image-2.5-flare'
                                       — only the OpenAI GPT Image family and Sourceful Riverflow
                                       advertise background=transparent on OpenRouter (catalog 2026-09-17)
    BTSGEN_OPENROUTER_RESOLUTION       optional tier: 512 | 1K | 2K | 4K (unset -> provider default)
    BTSGEN_IMAGE_QUALITY               low | medium (default) | high — ignored by models without a knob
Selected with BTSGEN_IMAGE_BACKEND=openrouter; `available()` is false with no key so it degrades to
no art (never blocks a forge). Constructor kwargs override the env so a CLI / A-B harness can pin a
model per call: OpenRouterImageBackend(model="bytedance-seed/seedream-4.5").

Reference images: req.ref_images (from StyleProfile.ref_images) are sent as base64 data URLs in
`input_references` — this is how a house style (e.g. a Slay the Spire look) can be conditioned in.
The provider decides how many it accepts (1..16 by model); we send what we're given.

Request: POST https://openrouter.ai/api/v1/images {model, prompt, aspect_ratio, quality,
output_format:'png', [resolution], [background:'transparent'], [input_references]}.
Response: {"data":[{"b64_json":..., "media_type":"image/png"}], "usage":{"cost": USD}} — cost is
REAL (metered by OpenRouter), unlike openai.py's advisory table."""
from __future__ import annotations

import base64
import json
import math
import os
import struct
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from ..request import ImageRequest, ImageResult

_ENDPOINT = "https://openrouter.ai/api/v1/images"
DEFAULT_MODEL = "qwen/qwen-image-3"
DEFAULT_SPRITE_MODEL = "openai/gpt-image-2.5-flare"

# Ratios every mainstream image model on OpenRouter accepts; a request's pixel size snaps to the nearest.
_RATIOS = {"1:1": 1.0, "3:2": 1.5, "2:3": 2 / 3, "4:3": 4 / 3, "3:4": 0.75, "16:9": 16 / 9, "9:16": 9 / 16}

_MIME = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp"}


class OpenRouterImageBackend:
    name = "openrouter"

    def __init__(self, model: str | None = None, sprite_model: str | None = None,
                 resolution: str | None = None, quality: str | None = None):
        self._model, self._sprite_model = model, sprite_model
        self._resolution, self._quality = resolution, quality

    @staticmethod
    def _key() -> str | None:
        return os.environ.get("OPENROUTER_API_KEY")

    def available(self) -> bool:
        return bool(self._key())

    def model_for(self, req: ImageRequest) -> str:
        if req.transparent:
            return (self._sprite_model or os.environ.get("BTSGEN_OPENROUTER_SPRITE_MODEL")
                    or DEFAULT_SPRITE_MODEL).strip()
        return (self._model or os.environ.get("BTSGEN_OPENROUTER_MODEL") or DEFAULT_MODEL).strip()

    def build_payload(self, req: ImageRequest) -> dict:
        model = self.model_for(req)
        body: dict = {
            "model": model, "prompt": req.prompt, "n": 1,
            "aspect_ratio": nearest_ratio(req.size),
            "quality": (self._quality or os.environ.get("BTSGEN_IMAGE_QUALITY", "medium")).strip().lower(),
            "output_format": "png",
        }
        res = self._resolution or os.environ.get("BTSGEN_OPENROUTER_RESOLUTION", "").strip()
        if res:
            body["resolution"] = res
        if req.transparent:
            body["background"] = "transparent"
        refs = [_data_url(p) for p in req.ref_images if Path(p).is_file()]
        if refs:
            body["input_references"] = [{"type": "image_url", "image_url": {"url": u}} for u in refs]
        return body

    def generate(self, req: ImageRequest) -> ImageResult:
        key = self._key()
        if not key:
            return ImageResult(ok=False, backend=self.name, error="no API key (set OPENROUTER_API_KEY)")
        payload_body = self.build_payload(req)
        model = payload_body["model"]
        body = json.dumps(payload_body).encode("utf-8")
        request = Request(_ENDPOINT, data=body, method="POST", headers={
            "Authorization": f"Bearer {key}", "Content-Type": "application/json",
            "HTTP-Referer": "https://blankthespire.com", "X-Title": "Blank the Spire"})
        try:
            with urlopen(request, timeout=240) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
        except HTTPError as e:
            detail = e.read().decode("utf-8", "replace")[:400] if hasattr(e, "read") else ""
            return ImageResult(ok=False, backend=self.name, model=model, error=f"HTTP {e.code}: {detail}")
        except (URLError, TimeoutError) as e:
            return ImageResult(ok=False, backend=self.name, model=model, error=f"network error: {e}")
        except Exception as e:
            return ImageResult(ok=False, backend=self.name, model=model, error=f"{type(e).__name__}: {e}")

        try:
            item = payload["data"][0]
            img_bytes = base64.b64decode(item["b64_json"])
        except Exception as e:
            err = payload.get("error") if isinstance(payload, dict) else None
            return ImageResult(ok=False, backend=self.name, model=model,
                               error=f"unexpected response shape: {err or e}")
        dims = png_dimensions(img_bytes)
        if dims is None:  # the mod reads PNG only (LoadPngFromBuffer); never mislabel a JPEG/WebP as .png
            mt = item.get("media_type") if isinstance(item, dict) else None
            return ImageResult(ok=False, backend=self.name, model=model,
                               error=f"model returned non-PNG data (media_type={mt}); pick a model with png output")

        try:
            req.out_path.parent.mkdir(parents=True, exist_ok=True)
            req.out_path.write_bytes(img_bytes)
        except OSError as e:
            return ImageResult(ok=False, backend=self.name, model=model, error=f"write failed: {e}")

        cost = None
        usage = payload.get("usage") if isinstance(payload, dict) else None
        if isinstance(usage, dict) and isinstance(usage.get("cost"), (int, float)):
            cost = float(usage["cost"])
        w, h = dims
        return ImageResult(ok=True, backend=self.name, model=model, path=req.out_path,
                           cost_usd=cost, width=w, height=h)


def nearest_ratio(size: tuple[int, int]) -> str:
    """Snap a pixel size to the closest common aspect-ratio tag (compared in log space so 2:3 vs 3:2 is symmetric)."""
    w, h = size
    target = math.log(max(w, 1) / max(h, 1))
    return min(_RATIOS, key=lambda k: abs(math.log(_RATIOS[k]) - target))


def png_dimensions(data: bytes) -> tuple[int, int] | None:
    """(width, height) from a PNG's IHDR, or None if the bytes aren't a PNG."""
    if len(data) < 24 or data[:8] != b"\x89PNG\r\n\x1a\n" or data[12:16] != b"IHDR":
        return None
    w, h = struct.unpack(">II", data[16:24])
    return w, h


def _data_url(path) -> str:
    p = Path(path)
    mime = _MIME.get(p.suffix.lower(), "image/png")
    return f"data:{mime};base64," + base64.b64encode(p.read_bytes()).decode("ascii")
