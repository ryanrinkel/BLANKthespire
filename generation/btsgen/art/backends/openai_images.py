"""Generic OpenAI-shaped /images/generations backend — ONE class, one preset row per vendor.

Google Gemini (through its OpenAI compatibility shim) and xAI both speak the OpenAI images request
with a top-level `aspect_ratio` and `response_format: "b64_json"`, so they are a single backend plus
a preset table (base URL, per-kind default model, per-image price, ratio whitelist, env names).
Adding Together — or any other OpenAI-shaped image host — later is one more PRESETS row, not a new
module.

Why it exists: BYOK. Since 56586c6 a bring-your-own-key forge makes its art on the USER's key or not
at all; this extends that to Gemini and xAI keys, so those users get the complete pack (splash,
sprite, one portrait per card) billed to them. The website builds
`OpenAIImagesBackend("gemini", api_key=<the user's key>)` per forge. Server-side both presets are
registered unconditionally and are inert (`available()` False) until the preset's env key is set, so
registering them can never block a forge.

Env (per preset; {PREFIX} is BTSGEN_GEMINI or BTSGEN_XAI):
    GEMINI_API_KEY / XAI_API_KEY   server-side key. A ctor `api_key=` (the BYOK path) beats it.
    {PREFIX}_MODEL                 splash model   (default gemini-2.5-flash-image / grok-imagine-image)
    {PREFIX}_SPRITE_MODEL          sprite model   (same defaults)
    {PREFIX}_CARD_MODEL            card model     (same defaults)
Selected with BTSGEN_IMAGE_BACKEND=gemini (or xai), or by passing the instance.

PRICES ARE A TABLE, NOT METERED. Gemini's shim returns no usage block and xAI bills a flat rate per
image, so `ImageResult.cost_usd` is this module's list-price ESTIMATE — advisory, like
backends/openai.py, and unlike backends/openrouter.py which records what the vendor actually billed.
Read off the vendors' pricing pages 2026-09-20. Full pack (2 + 34 images): Gemini $1.404, xAI $0.72.

NOT VERIFIED AGAINST A LIVE KEY — no Gemini or xAI key exists here; step 0 of
docs/plans/BYOK_ART_GEMINI_XAI_PLAN.md is the one real call per vendor that confirms all of this:
  * that `aspect_ratio` is honored as a TOP-LEVEL JSON field on both hosts. Gemini's docs call it an
    "extra_body" field, which is the OpenAI SDK's name for exactly that; `size` is also accepted and
    documented to map onto aspect_ratio, so `size` is the fallback if this is wrong.
  * WHICH aspect_ratio tags each vendor accepts. RATIOS below is a conservative whitelist and a tag a
    vendor rejects is an HTTP 400 — xAI's accepted set could not be confirmed from its docs at all.
  * the returned media type (Gemini may return PNG or JPEG; xAI is likely JPEG). Harmless either way:
    unlike openrouter.py, which rejects non-PNG, this backend normalizes through Pillow.
  * the two Gemini models priced on Google's page but NOT confirmed routable on the shim
    (gemini-3.1-flash-lite-image, gemini-3.1-flash-image). They sit in the price table so an env
    override is priced; they are not defaults.
  * whether the response ever carries a usage/cost block (assumed not: `returns_usage=False`).

Neither vendor supports `background="transparent"`, so SPRITES ARE CHROMA-KEYED: a transparent
request appends BACKDROP_PROMPT (a flat #00FF00 field) and art/keying.py turns that field into alpha
before the file is written. The mod's alpha autocrop does the rest.

Request:  POST {base_url}/images/generations
          {"model": ..., "prompt": ..., "n": 1, "response_format": "b64_json", "aspect_ratio": ...}
Response: {"data": [{"b64_json": ...}]} — a `url`-only item is fetched once as a fallback.
"""
from __future__ import annotations

import base64
import io
import json
import os
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from ..request import ImageRequest, ImageResult
from .openrouter import kind_of, nearest_ratio  # one definition of 'what kind' / 'which ratio tag'

_KINDS = ("splash", "sprite", "card")
# The ratio each asset kind is drawn at. The mod's splash box and card portrait box are both
# landscape-3:2-ish and the sprite is a tall cut-out; this map is authoritative because a 16:9 splash
# on these two vendors is untested (see nearest_ratio fallback in ratio_for_kind).
_KIND_RATIOS = {"splash": "3:2", "card": "3:2", "sprite": "2:3"}
_ENV_SUFFIX = {"splash": "_MODEL", "sprite": "_SPRITE_MODEL", "card": "_CARD_MODEL"}
# Conservative whitelist shared by both presets: the tags the OpenAI images shape has always used and
# that both vendors' docs mention. STEP 0 MUST CONFIRM these per vendor — an unaccepted tag is a 400.
RATIOS = ("1:1", "3:2", "2:3", "4:3", "3:4", "16:9", "9:16")
_TIMEOUT = 240

BACKDROP_PROMPT = (
    " The entire background is a perfectly flat, solid bright green (#00FF00) field — nothing else in"
    " the background: no scenery, no gradient, no ground plane, no cast shadow, no green anywhere on"
    " the character itself."
)


@dataclass(frozen=True)
class ImagesPreset:
    """One vendor row. `models` maps kind -> default model id; `prices` maps model id -> list USD per
    image; `ratios` is the aspect_ratio whitelist; `env_prefix` names the three model env overrides
    and `env_key` the server-side API-key variable."""
    name: str
    base_url: str
    models: dict
    prices: dict
    ratios: tuple
    env_prefix: str
    env_key: str
    label: str
    returns_usage: bool = False

    @property
    def endpoint(self) -> str:
        return self.base_url.rstrip("/") + "/images/generations"

    def model_for_kind(self, kind: str) -> str:
        """The model this preset uses for `kind` right now: {PREFIX}_{,SPRITE_,CARD_}MODEL, else the
        preset default. (The backend's own ctor pins sit ON TOP of this — see model_for.)"""
        kind = kind if kind in _KINDS else "splash"
        env = os.environ.get(self.env_prefix + _ENV_SUFFIX[kind], "").strip()
        return (env or self.models[kind]).strip()

    def price_for_model(self, model: str) -> float | None:
        """List USD per image, or None for a model we have no published price for (the ledger then
        records no cost rather than a guess)."""
        value = self.prices.get((model or "").strip())
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return float(value)
        return None

    def ratio_for_kind(self, kind: str, size=None) -> str:
        """The kind's ratio tag when this vendor accepts it, else the nearest tag it does accept to
        the requested pixel size (openrouter.nearest_ratio, same log-space snap)."""
        want = _KIND_RATIOS.get(kind, "3:2")
        if want in self.ratios:
            return want
        return nearest_ratio(tuple(size or (1024, 1024)), allowed=self.ratios)


PRESETS: dict[str, ImagesPreset] = {
    # The shim only documents two image models; flash-image is the cheap complete default. The two
    # 3.1 rows are priced on Google's pricing page but NOT confirmed routable here (see docstring).
    "gemini": ImagesPreset(
        name="gemini",
        base_url="https://generativelanguage.googleapis.com/v1beta/openai",
        models={k: "gemini-2.5-flash-image" for k in _KINDS},
        prices={
            "gemini-2.5-flash-image": 0.039,
            "gemini-3-pro-image-preview": 0.134,
            "gemini-3.1-flash-lite-image": 0.0336,
            "gemini-3.1-flash-image": 0.067,
        },
        ratios=RATIOS,
        env_prefix="BTSGEN_GEMINI",
        env_key="GEMINI_API_KEY",
        label="Google Gemini",
    ),
    # grok-imagine-image at $0.02 is the cheapest complete pack of any vendor we support; -2.0 and
    # -quality are env-selectable upgrades.
    "xai": ImagesPreset(
        name="xai",
        base_url="https://api.x.ai/v1",
        models={k: "grok-imagine-image" for k in _KINDS},
        prices={
            "grok-imagine-image": 0.02,
            "grok-imagine-image-2.0": 0.04,
            "grok-imagine-image-quality": 0.05,
        },
        ratios=RATIOS,
        env_prefix="BTSGEN_XAI",
        env_key="XAI_API_KEY",
        label="xAI",
    ),
}


class OpenAIImagesBackend:
    """An ImageBackend (see backends/base.py) for one PRESETS row. `preset` may be the row or its
    name. Constructor model pins beat the env, exactly like OpenRouterImageBackend, so an A/B harness
    can hold a model for one run."""

    def __init__(self, preset, api_key: str | None = None, model: str | None = None,
                 card_model: str | None = None, sprite_model: str | None = None):
        self.preset = preset if isinstance(preset, ImagesPreset) else PRESETS[str(preset).strip().lower()]
        self.name = self.preset.name
        self._model, self._card_model, self._sprite_model = model, card_model, sprite_model
        # An explicit key (a BYOK user's, held for one forge) beats the server's env key.
        self._api_key = (api_key or "").strip() or None

    def _key(self) -> str | None:
        return self._api_key or os.environ.get(self.preset.env_key)

    def available(self) -> bool:
        return bool(self._key())

    def model_for(self, req: ImageRequest) -> str:
        """ctor pin > env override > preset default, resolved per asset kind (same three-way split as
        backends/openrouter.py: a splash is one image, a class's cards are 34)."""
        kind = kind_of(req)
        if kind == "sprite":
            pinned = self._sprite_model
        elif kind == "card":
            pinned = self._card_model or self._model  # a ctor `model` still wins for cards
        else:
            pinned = self._model
        return ((pinned or "").strip() or self.preset.model_for_kind(kind))

    def price_for(self, req: ImageRequest) -> float | None:
        """The preset's LIST price for this request's model, or None when unpriced. Advisory — see
        the module docstring; neither vendor meters cost in the response."""
        return self.preset.price_for_model(self.model_for(req))

    def build_payload(self, req: ImageRequest) -> dict:
        prompt = req.prompt
        if req.transparent:  # no background=transparent on these hosts; we key the green out below
            prompt = prompt.rstrip() + BACKDROP_PROMPT
        return {
            "model": self.model_for(req),
            "prompt": prompt,
            "n": 1,
            "response_format": "b64_json",
            "aspect_ratio": self.preset.ratio_for_kind(kind_of(req), req.size),
        }

    def generate(self, req: ImageRequest) -> ImageResult:
        model = self.model_for(req)
        key = self._key()
        if not key:
            return ImageResult(ok=False, backend=self.name, model=model,
                               error=f"no API key (set {self.preset.env_key})")
        body = json.dumps(self.build_payload(req)).encode("utf-8")
        request = Request(self.preset.endpoint, data=body, method="POST", headers={
            "Authorization": f"Bearer {key}", "Content-Type": "application/json"})
        try:
            with urlopen(request, timeout=_TIMEOUT) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
        except HTTPError as e:
            detail = e.read().decode("utf-8", "replace")[:400] if hasattr(e, "read") else ""
            return ImageResult(ok=False, backend=self.name, model=model, error=f"HTTP {e.code}: {detail}")
        except (URLError, TimeoutError) as e:
            return ImageResult(ok=False, backend=self.name, model=model, error=f"network error: {e}")
        except Exception as e:
            return ImageResult(ok=False, backend=self.name, model=model, error=f"{type(e).__name__}: {e}")

        raw, err = _image_bytes(payload)
        if raw is None:
            return ImageResult(ok=False, backend=self.name, model=model, error=err)
        try:
            png, (w, h) = _to_png(raw, transparent=bool(req.transparent))
        except Exception as e:
            return ImageResult(ok=False, backend=self.name, model=model,
                               error=f"could not decode image: {type(e).__name__}: {e}")
        try:
            req.out_path.parent.mkdir(parents=True, exist_ok=True)
            req.out_path.write_bytes(png)
        except OSError as e:
            return ImageResult(ok=False, backend=self.name, model=model, error=f"write failed: {e}")
        return ImageResult(ok=True, backend=self.name, model=model, path=req.out_path,
                           cost_usd=self.price_for(req), width=w, height=h)


def estimate_pack(preset_name: str, n_cards: int) -> dict:
    """What one COMPLETE pack (splash + sprite + `n_cards` portraits) costs on this vendor's key, at
    the models the current env/defaults would actually use. The website's /api/forge-estimate calls
    this so the user sees the bill before pushing go — one source of truth, no price table in the
    browser. Unpriced models contribute 0 and show as None in `per_image_usd`."""
    preset = preset_name if isinstance(preset_name, ImagesPreset) else PRESETS[str(preset_name).strip().lower()]
    cards = max(int(n_cards), 0)
    counts = {"splash": 1, "sprite": 1, "card": cards}
    models = {kind: preset.model_for_kind(kind) for kind in _KINDS}
    per_image = {kind: preset.price_for_model(models[kind]) for kind in _KINDS}
    total = sum((per_image[kind] or 0.0) * counts[kind] for kind in _KINDS)
    return {
        "images": 2 + cards,
        "per_image_usd": per_image,
        "total_usd": round(total, 6),  # 36 x 0.039 in binary float is 1.4040000000000001
        "models": models,
    }


def _image_bytes(payload) -> tuple[bytes | None, str | None]:
    """The image bytes out of an OpenAI-images response: b64_json, else a one-shot fetch of `url`
    (xAI's docs show both shapes). Returns (None, error) rather than raising."""
    try:
        item = payload["data"][0]
    except Exception:
        err = payload.get("error") if isinstance(payload, dict) else None
        return None, f"unexpected response shape: {err or payload}"[:400]
    if not isinstance(item, dict):
        return None, f"unexpected response shape: data[0] is {type(item).__name__}"
    b64 = item.get("b64_json")
    if b64:
        try:
            return base64.b64decode(b64), None
        except Exception as e:
            return None, f"undecodable b64_json: {type(e).__name__}: {e}"
    url = item.get("url")
    if url:
        try:
            with urlopen(url, timeout=_TIMEOUT) as resp:
                return resp.read(), None
        except Exception as e:
            return None, f"image url fetch failed: {type(e).__name__}: {e}"
    return None, "unexpected response shape: data[0] has neither b64_json nor url"


def _to_png(raw: bytes, transparent: bool) -> tuple[bytes, tuple[int, int]]:
    """Normalize whatever the vendor returned (PNG / JPEG / WebP) to a PNG the mod's
    LoadPngFromBuffer reads, and report the DECODED dimensions rather than trusting the request.
    `transparent` runs the chroma key (art/keying.py) and writes RGBA."""
    from PIL import Image  # lazy: the art package must import without Pillow

    with Image.open(io.BytesIO(raw)) as src:
        src.load()
        size = src.size
        if transparent:
            from ..keying import chroma_key
            out = chroma_key(src)
        else:
            out = src.convert("RGB")  # these vendors never return alpha on a normal request
        buf = io.BytesIO()
        out.save(buf, format="PNG")
    return buf.getvalue(), size
