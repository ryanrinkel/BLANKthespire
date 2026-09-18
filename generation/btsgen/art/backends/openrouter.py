"""OpenRouter image backend — one key, ~50 image models (Qwen Image, Seedream, FLUX, Nano Banana,
Recraft, GPT Image ...) behind OpenRouter's unified Image API. Lets us A/B image models with an env
flip instead of a new backend per vendor.

Zero new dependencies (stdlib urllib, same shape as openai.py). Model and quality resolve PER ASSET
KIND (req.kind: splash | sprite | card) — one splash costs $0.004, a class's 34 cards cost $0.13, so
they are separate knobs. Env:
    OPENROUTER_API_KEY                 required (the same key the text side's OpenRouter config uses)
    BTSGEN_OPENROUTER_MODEL            splash model, default 'openai/gpt-5-image-mini'
                                       (was qwen/qwen-image-3 until 2026-09-18; the E2E legs Ryan judged
                                       used mini@low and Qwen is still one env flip away)
    BTSGEN_OPENROUTER_SPRITE_MODEL     transparent (sprite) model, default 'openai/gpt-image-2.5-flare'
                                       — only the OpenAI GPT Image family and Sourceful Riverflow
                                       advertise background=transparent on OpenRouter (catalog 2026-09-17)
    BTSGEN_OPENROUTER_CARD_MODEL       card model, default 'openai/gpt-5-image-mini'
    BTSGEN_OPENROUTER_CARD_MODELS      the per-image FALLBACK LADDER for cards, a comma list of
                                       'model[@quality]', default
                                       'openai/gpt-5-image-mini@low,black-forest-labs/flux.2-klein-4b'.
                                       The first entry is retried ONCE on a transient fault (one
                                       transient OpenAI 502 in 105 images in the E2E), then the next
                                       model is tried; FLUX.2 Klein is 3 s, PNG, $0.015, any ratio.
                                       Unset -> the ladder is just BTSGEN_OPENROUTER_CARD_MODEL.
    BTSGEN_OPENROUTER_RESOLUTION       optional tier: 512 | 1K | 2K | 4K (unset -> provider default)
    BTSGEN_IMAGE_QUALITY               splash quality, low (default) | medium | high — ignored by
                                       models without a knob
    BTSGEN_IMAGE_SPRITE_QUALITY        sprite quality (unset -> the splash quality)
    BTSGEN_IMAGE_CARD_QUALITY          card quality, default 'low' (also the ladder's default when an
                                       entry carries no @quality suffix)
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
# 2026-09-18 A/B: gpt-5-image-mini @ low, 3:2 is the best value of the catalog (32/32 ok, $0.0038/image,
# ~11 s) and is what the whole-class E2E runs Ryan judged used — for splashes AND cards.
DEFAULT_MODEL = "openai/gpt-5-image-mini"
DEFAULT_SPRITE_MODEL = "openai/gpt-image-2.5-flare"
DEFAULT_CARD_MODEL = "openai/gpt-5-image-mini"
DEFAULT_CARD_MODELS = "openai/gpt-5-image-mini@low,black-forest-labs/flux.2-klein-4b"
DEFAULT_QUALITY = "low"
DEFAULT_CARD_QUALITY = "low"
_MAX_CARD_ATTEMPTS = 4  # hard bound: a stuck vendor must cost seconds, not a forge

_KINDS = ("splash", "sprite", "card")

# Ratios every mainstream image model on OpenRouter accepts; a request's pixel size snaps to the nearest.
_RATIOS = {"1:1": 1.0, "3:2": 1.5, "2:3": 2 / 3, "4:3": 4 / 3, "3:4": 0.75, "16:9": 16 / 9, "9:16": 9 / 16}

_MIME = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp"}


class OpenRouterImageBackend:
    name = "openrouter"

    def __init__(self, model: str | None = None, sprite_model: str | None = None,
                 resolution: str | None = None, quality: str | None = None,
                 card_model: str | None = None):
        self._model, self._sprite_model, self._card_model = model, sprite_model, card_model
        self._resolution, self._quality = resolution, quality

    @staticmethod
    def _key() -> str | None:
        return os.environ.get("OPENROUTER_API_KEY")

    def available(self) -> bool:
        return bool(self._key())

    def model_for(self, req: ImageRequest) -> str:
        kind = kind_of(req)
        if kind == "sprite":
            return (self._sprite_model or os.environ.get("BTSGEN_OPENROUTER_SPRITE_MODEL")
                    or DEFAULT_SPRITE_MODEL).strip()
        if kind == "card":
            # a ctor-pinned `model` still wins for cards (the A/B harness pins one model per run)
            return (self._card_model or self._model or os.environ.get("BTSGEN_OPENROUTER_CARD_MODEL")
                    or DEFAULT_CARD_MODEL).strip()
        return (self._model or os.environ.get("BTSGEN_OPENROUTER_MODEL") or DEFAULT_MODEL).strip()

    def quality_for(self, req: ImageRequest) -> str:
        if self._quality:
            return self._quality.strip().lower()
        kind = kind_of(req)
        if kind == "sprite":  # unset -> fall through to the splash quality
            q = os.environ.get("BTSGEN_IMAGE_SPRITE_QUALITY", "").strip()
            if q:
                return q.lower()
        elif kind == "card":
            return (os.environ.get("BTSGEN_IMAGE_CARD_QUALITY", "").strip()
                    or DEFAULT_CARD_QUALITY).lower()
        return (os.environ.get("BTSGEN_IMAGE_QUALITY", "").strip() or DEFAULT_QUALITY).lower()

    def attempt_plan(self, req: ImageRequest) -> list[tuple[str, str]]:
        """The ordered [(model, quality), ...] this request may burn, primary model first.

        splash/sprite: exactly one attempt (unchanged). card: the BTSGEN_OPENROUTER_CARD_MODELS ladder
        with the FIRST entry duplicated — that duplicate is the retry-once slot and is SKIPPED unless
        the preceding failure was transient (see _transient). Hard-bounded by _MAX_CARD_ATTEMPTS so a
        misconfigured ladder can never loop."""
        if kind_of(req) != "card":
            return [(self.model_for(req), self.quality_for(req))]
        pinned = (self._card_model or self._model or "").strip()
        raw = os.environ.get("BTSGEN_OPENROUTER_CARD_MODELS", "").strip()
        if pinned:
            entries = [pinned]                       # a ctor pin IS the ladder (the A/B harness path)
        elif raw:
            entries = _split(raw)
        else:
            entries = _split(DEFAULT_CARD_MODELS)
            first = os.environ.get("BTSGEN_OPENROUTER_CARD_MODEL", "").strip()
            if first and entries:
                entries[0] = first  # the single-model env swaps the ladder's PRIMARY, keeping the net
        plan: list[tuple[str, str]] = []
        for e in entries:
            model, _, q = e.partition("@")
            model = model.strip()
            if model:
                plan.append((model, (q.strip() or self.quality_for(req)).lower()))
        if not plan:
            plan = [(self.model_for(req), self.quality_for(req))]
        plan.insert(1, plan[0])  # retry-once slot for the primary model (skipped on a hard failure)
        return plan[:_MAX_CARD_ATTEMPTS]

    def build_payload(self, req: ImageRequest, model: str | None = None,
                      quality: str | None = None) -> dict:
        model = model or self.model_for(req)
        body: dict = {
            "model": model, "prompt": req.prompt, "n": 1,
            "aspect_ratio": nearest_ratio(req.size),
            "quality": (quality or self.quality_for(req)).strip().lower(),
            "output_format": "png",
        }
        res = self._resolution or os.environ.get("BTSGEN_OPENROUTER_RESOLUTION", "").strip()
        if res:
            body["resolution"] = res
        if req.transparent:
            body["background"] = "transparent"
        elif kind_of(req) == "card" and model.startswith("openai/"):
            # gpt-5-image-mini hands back ~half-transparent cut-outs when nothing is asked (measured
            # 2026-09-18); a card portrait is an opaque scene like the shipped STS art. Only the OpenAI
            # family knows the param (FLUX would 400 on it and it is the fallback rung).
            bg = os.environ.get("BTSGEN_IMAGE_CARD_BACKGROUND", "opaque").strip().lower()
            if bg and bg != "auto":
                body["background"] = bg
        refs = [_data_url(p) for p in req.ref_images if Path(p).is_file()]
        if refs:
            body["input_references"] = [{"type": "image_url", "image_url": {"url": u}} for u in refs]
        return body

    def generate(self, req: ImageRequest) -> ImageResult:
        key = self._key()
        if not key:
            return ImageResult(ok=False, backend=self.name, error="no API key (set OPENROUTER_API_KEY)")
        plan = self.attempt_plan(req)
        res: ImageResult | None = None
        for i, (model, quality) in enumerate(plan):
            # a duplicated entry is the retry-once slot: only worth paying for after a TRANSIENT fault
            if i and plan[i] == plan[i - 1] and not _transient(res):
                continue
            res = self._one(req, key, model, quality)
            if res.ok:
                return res
        return res or ImageResult(ok=False, backend=self.name, error="no image model configured")

    def _one(self, req: ImageRequest, key: str, model: str, quality: str) -> ImageResult:
        payload_body = self.build_payload(req, model=model, quality=quality)
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

        cost = metered_cost(payload)
        w, h = dims
        return ImageResult(ok=True, backend=self.name, model=model, path=req.out_path,
                           cost_usd=cost, width=w, height=h)


def metered_cost(payload) -> float | None:
    """The REAL USD OpenRouter billed for this image, or None. Unlike openai.py's advisory rate table
    this is what the account is actually charged (the 2026-09 A/B found the rate tables 30-45% low),
    so the ledger records it verbatim. OpenRouter has shipped the number under three shapes; accept
    all of them and never guess when it is absent."""
    if not isinstance(payload, dict):
        return None
    usage = payload.get("usage")
    for holder, keys in ((usage, ("cost", "total_cost")), (payload, ("cost", "total_cost"))):
        if isinstance(holder, dict):
            for k in keys:
                v = holder.get(k)
                if isinstance(v, (int, float)) and not isinstance(v, bool):
                    return float(v)
    details = usage.get("cost_details") if isinstance(usage, dict) else None
    if isinstance(details, dict):
        total = sum(v for v in details.values() if isinstance(v, (int, float)) and not isinstance(v, bool))
        if total:
            return float(total)
    return None


def kind_of(req: ImageRequest) -> str:
    """The asset kind a backend keys its model/quality on: 'splash' | 'sprite' | 'card'. Falls back to
    req.transparent for any caller that builds an ImageRequest without a kind (pre-2026-09-18 shape)."""
    kind = (getattr(req, "kind", "") or "").strip().lower()
    if kind not in _KINDS:
        kind = "sprite" if req.transparent else "splash"
    elif kind == "splash" and req.transparent:
        kind = "sprite"  # a transparent splash is a sprite; only some models do alpha
    return kind


def _split(raw: str) -> list[str]:
    return [e.strip() for e in str(raw).split(",") if e.strip()]


def _transient(res: ImageResult | None) -> bool:
    """Is this failure worth retrying the SAME model for? 5xx / 408 / 429 / transport faults are;
    a 400, a missing model, or a non-PNG body will fail identically the second time."""
    if res is None or res.ok:
        return False
    err = res.error or ""
    if err.startswith("network error") or err.startswith("TimeoutError"):
        return True
    if err.startswith("HTTP "):
        code = err[5:8]
        return code.startswith("5") or code in ("408", "429")
    return False


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
