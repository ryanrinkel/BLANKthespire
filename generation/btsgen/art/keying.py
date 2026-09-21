"""Chroma-key a flat-backdrop render into an RGBA cut-out.

Why this exists: neither Google Gemini's OpenAI shim nor xAI supports `background="transparent"` —
only the OpenAI GPT Image family (and Sourceful Riverflow on OpenRouter) advertises alpha output. So
for those vendors the SPRITE request asks for the subject on a perfectly flat #00FF00 field
(backends/openai_images.BACKDROP_PROMPT) and this module turns that field into alpha, giving the mod
the same RGBA cut-out it already autocrops, resizes and tweens.

Pure Pillow — a core btsgen dep — and no numpy (btsgen has none). PIL is imported lazily inside the
functions so the art package still imports on a box without Pillow, same rule as art/card.py.

The distance pass is plain Python over the pixel bytes with a per-colour memo: a flat backdrop
collapses to a handful of distinct colours, so a 1024x1536 sprite keys in well under a second, once
per forge, and the code stays readable. Everything after it (erode / blur / darker) is Pillow's C.

Pipeline:
  1. alpha ramp  — 0 below `tolerance * _INNER`, 255 above `tolerance`, linear between, on the RGB
                   euclidean distance to the backdrop colour. The ramp (not a hard threshold) is what
                   eats an anti-aliased fringe instead of leaving a stair-stepped edge.
  2. erode       — MinFilter shrinks the opaque region by `erode` px, so the last ring of
                   backdrop-contaminated pixels goes with it.
  3. feather     — a gaussian blur of the mask, CLAMPED by the eroded mask (ImageChops.darker), so the
                   softening only runs inward and alpha can never bleed back out onto the backdrop.
  4. despill     — on every semi-transparent pixel, pull the backdrop's dominant channel down to the
                   mean of the other two, so the soft edge reads neutral instead of lime.

`key_file(in_path, out_path)` runs the same pipeline over an image already on disk — that is the A/B
harness's entry point (step 4 of docs/plans/BYOK_ART_GEMINI_XAI_PLAN.md compares these against the
procedural placeholder sprite).
"""
from __future__ import annotations

import io
from math import sqrt
from pathlib import Path

# The backdrop the sprite prompt asks for. Bright green is the classic key colour: it is far from
# skin, metal and most costume palettes in RGB space, which is exactly what `tolerance` trades on.
BACKDROP = (0, 255, 0)
# Distance (0..441 in RGB space) at which a pixel becomes fully opaque. 120 keys pure #00FF00 and its
# blends out while leaving a genuinely green costume (which is rarely a pure primary) alone.
DEFAULT_TOLERANCE = 120.0
# Fraction of `tolerance` below which a pixel is fully keyed; between the two it ramps.
_INNER = 0.55


def chroma_key(source, backdrop=BACKDROP, tolerance: float = DEFAULT_TOLERANCE,
               erode: int = 1, feather: float = 1.0, spill: float = 1.0):
    """Key `backdrop` out of an image and return a PIL RGBA Image.

    `source`: encoded image bytes (PNG/JPEG/WebP — whatever the vendor returned), a path, or a PIL
    Image. `tolerance`: RGB distance at which a pixel is fully kept (see DEFAULT_TOLERANCE).
    `erode`: px of opaque region to shave (0 disables). `feather`: gaussian radius of the inward
    alpha softening (0 disables). `spill`: 0..1, how far a semi-transparent pixel's backdrop channel
    is pulled toward the mean of the other two (1.0 = all the way; lower it if a green-costumed
    class loses its edge colour)."""
    from PIL import Image, ImageChops, ImageFilter

    im = _as_image(source).convert("RGB")
    mask = Image.frombytes("L", im.size, _alpha_bytes(im.tobytes(), backdrop, float(tolerance)))
    if erode and int(erode) > 0:
        mask = mask.filter(ImageFilter.MinFilter(2 * int(erode) + 1))
    if feather and float(feather) > 0:
        # darker() clamps the blur by the un-blurred mask: soften inward only, never back onto the
        # backdrop (a plain blur would paint a halo of low alpha over keyed-out pixels).
        mask = ImageChops.darker(mask.filter(ImageFilter.GaussianBlur(float(feather))), mask)
    out = im.convert("RGBA")
    out.putalpha(mask)
    return _despill(out, backdrop, float(spill))


def key_file(in_path, out_path, **kwargs) -> Path:
    """Chroma-key a saved image and write the RGBA PNG to `out_path` (returned). Same kwargs as
    chroma_key — this is how the sprite A/B harness re-keys renders without re-billing a vendor."""
    img = chroma_key(Path(in_path).read_bytes(), **kwargs)
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out, format="PNG")
    return out


def _alpha_bytes(rgb: bytes, backdrop, tolerance: float) -> bytes:
    """One alpha byte per RGB triple: 0 near the backdrop colour, 255 far from it, ramped between.

    Memoised on the colour triple — a flat backdrop is one colour for most of the frame, so the
    Python loop does real work only on the subject and its fringe."""
    br, bg, bb = (int(c) for c in backdrop)
    near = max(tolerance * _INNER, 0.0)
    span = max(tolerance - near, 1e-6)
    memo: dict[bytes, int] = {}
    n = len(rgb) // 3
    out = bytearray(n)
    for i in range(n):
        px = rgb[3 * i:3 * i + 3]
        a = memo.get(px)
        if a is None:
            dr, dg, db = px[0] - br, px[1] - bg, px[2] - bb
            d = sqrt(dr * dr + dg * dg + db * db)
            if d <= near:
                a = 0
            elif d >= tolerance:
                a = 255
            else:
                a = int(255.0 * (d - near) / span)
            memo[px] = a
        out[i] = a
    return bytes(out)


def _despill(im, backdrop, spill: float):
    """Pull the backdrop's dominant channel toward the mean of the other two on every SEMI-transparent
    pixel (0 < alpha < 255) — the fringe the feather just created, which is where the vendor's green
    is still mixed into the subject's colour. Fully opaque pixels (the subject) are never touched, so
    a green robe stays green; only its 1-2px soft edge is neutralised."""
    from PIL import Image

    if spill <= 0:
        return im
    ch = max(range(3), key=lambda i: backdrop[i])
    a_idx, b_idx = [i for i in range(3) if i != ch]
    px = bytearray(im.tobytes())  # RGBA, 4 bytes per pixel
    for i in range(0, len(px), 4):
        alpha = px[i + 3]
        if alpha == 0 or alpha == 255:
            continue
        mean = (px[i + a_idx] + px[i + b_idx]) // 2
        value = px[i + ch]
        if value > mean:
            px[i + ch] = int(value - (value - mean) * min(spill, 1.0))
    return Image.frombytes("RGBA", im.size, bytes(px))


def _as_image(source):
    """bytes / path / PIL Image -> PIL Image (fully loaded, detached from any file handle)."""
    from PIL import Image

    if isinstance(source, (bytes, bytearray, memoryview)):
        im = Image.open(io.BytesIO(bytes(source)))
        im.load()
        return im
    if isinstance(source, (str, Path)):
        with Image.open(source) as im:
            return im.convert("RGB")
    return source
