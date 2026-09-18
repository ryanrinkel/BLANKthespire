"""forge_card_art — one illustration per CARD, the third asset kind (splash / sprite / card).

Same best-effort contract and orchestration as forge_splash (see splash._forge_asset); differs in
four ways:

  * the PROMPT is "mechanical": it leads with the card's own name and type as the literal subject
    (the A/B winner — "Jack in Iron, an attack card" draws the card, not another class portrait),
    then the card's own description/flavor/pitch line, then the class look (verbatim player concept
    + flavor/imagery motifs), then the single-subject framing rule, then the shared style suffix;
  * ENRICHMENT IS OFF (34 extra LLM calls per class for little gain) — the template path always;
  * the render is 1536x1024 (3:2 — the only landscape ratio the OpenAI image family accepts on
    OpenRouter) and is then CENTER-CROPPED + resized to the mod's 1000x760 portrait box (~1.32:1)
    with Pillow. Only the big file ships; the game scales it for the 250x190 slot;
  * the output file is per card: <class_id>.card.<card_id>.<ext> (the web passes out_path itself).

The web orchestrator calls this once per card from a small thread pool and reads ok / path / error /
cost_usd / model / backend off the result (cost_usd is REAL on the openrouter backend — see
backends/openrouter.py — and advisory on openai)."""
from __future__ import annotations

import os
from pathlib import Path

from .prompt import _append_concept, _append_theme
from .request import ClassArt, ImageResult, StyleProfile
from .styles import CARD_STYLE

# The mod's big card-portrait slot (Cards/Forged): 1000x760 (~1.3158:1); the small slot is 250x190,
# the same ratio, and the game downscales the big file for it.
CARD_PORTRAIT_SIZE = (1000, 760)

_TYPE_WORD = {"attack": "attack", "skill": "skill", "power": "power"}
# The card's own prose, most specific first; the first non-empty ones become the description line.
_FLAVOR_KEYS = ("description", "text", "flavor", "pitch")


def forge_card_art(source, card: dict, *, backend=None, style: StyleProfile | None = None,
                   out_dir=None, out_path=None, on_event=None,
                   portrait_size: tuple[int, int] | None = CARD_PORTRAIT_SIZE) -> ImageResult:
    """Generate ONE card's illustration. Best-effort: never raises; ok=False is normal (no key, no
    backend, API error) and the mod falls back to its per-type doodle for that card.

    `source`: a ClassArt (build it ONCE per class with class_art_from_bundle and reuse it across the
    pool — it is read-only) or a forge bundle dict. `card`: the card dict from the bundle
    (id/name/type/... — only name/type and the prose keys are read). `backend`: a name, a comma list
    ("openrouter,openai"), a list of names/instances, or None (-> $BTSGEN_IMAGE_BACKEND, else
    'null'). `out_path`: exact output file (the web uses static/forged/<id>/cards/<card_id>.png);
    else `out_dir`/<class_id>.card.<card_id>.<ext>. `portrait_size`: crop+resize target, or None to
    keep the raw render.

    Returns an ImageResult: .ok, .path, .error, .cost_usd (metered on openrouter), .model, .backend,
    .width/.height (of the FINAL file)."""
    from .splash import _forge_asset  # lazy: splash imports nothing from here, keep it that way

    style = style or CARD_STYLE
    card = card if isinstance(card, dict) else {}
    card_id = str(card.get("id") or card.get("name") or "card").strip() or "card"

    def build(art: ClassArt, st: StyleProfile, enriched_body: str | None = None) -> str:
        return card_prompt(art, card, st)

    def post(res: ImageResult, note) -> None:
        if portrait_size and res.path:
            fit_to_portrait(res.path, portrait_size, on_event=note)
            dims = image_size(res.path)
            if dims:
                res.width, res.height = dims

    return _forge_asset("card", build, source, backend=backend, style=style, out_dir=out_dir,
                        out_path=out_path, on_event=on_event, stem_suffix=_slug(card_id),
                        enrich=False, postprocess=post)


def card_prompt(art: ClassArt, card: dict, style: StyleProfile) -> str:
    """The "mechanical prompt" shape from the 2026-09-18 A/B: the CARD is the subject, the class is
    only the look. Leads with name + type, ends with the style suffix."""
    name = str((card or {}).get("name") or (card or {}).get("id") or "Card").strip() or "Card"
    kind = _TYPE_WORD.get(str((card or {}).get("type") or "").strip().lower(), "")
    lead = f'{"an" if kind[:1] in "aeiou" else "a"} {kind} card'.replace("  ", " ") if kind else "a card"
    parts = [
        f'Card illustration for "{name}", {lead} in a dark-fantasy deckbuilder. '
        f'The card\'s name is the subject: draw "{name}" itself, literally.'
    ]
    line = card_flavor_line(card)
    if line:
        parts.append(line)
    _append_concept(parts, art)   # the player's verbatim concept, always
    _append_theme(parts, art)     # flavor / imagery motifs (falls back to archetypes)
    parts.append(
        "Single focal subject filling the frame, strong readable silhouette against a simple "
        "atmospheric background, no character text, no lettering, no card frame or border."
    )
    if style.prompt_suffix:
        parts.append(style.prompt_suffix)
    return " ".join(p.strip() for p in parts if p and p.strip())


def card_flavor_line(card: dict) -> str:
    """The card's own prose (description / text / flavor / pitch), de-duplicated, as one line."""
    seen: list[str] = []
    for k in _FLAVOR_KEYS:
        v = str((card or {}).get(k) or "").strip()
        if v and v.lower() not in [s.lower() for s in seen]:
            seen.append(v)
    if not seen:
        return ""
    return " ".join(s if s.endswith((".", "!", "?")) else s + "." for s in seen)


# --- post-process: 3:2 render -> the mod's portrait box -------------------------------------------

def portrait_crop_box(size: tuple[int, int],
                      target: tuple[int, int] = CARD_PORTRAIT_SIZE) -> tuple[int, int, int, int]:
    """The largest centered `target`-ratio rectangle inside `size`, as a PIL box (left, top, right,
    bottom). Pure math — testable with no Pillow and no backend. A 3:2 render (1536x1024) loses a
    sliver from each side; a taller-than-target render loses top and bottom instead."""
    w, h = int(size[0]), int(size[1])
    tw, th = int(target[0]), int(target[1])
    if w < 1 or h < 1 or tw < 1 or th < 1:
        raise ValueError(f"bad crop geometry: size={size} target={target}")
    ratio = tw / th
    if w / h > ratio:            # source is WIDER than the box: trim left/right
        cw, ch = int(round(h * ratio)), h
    else:                        # source is taller (or equal): trim top/bottom
        cw, ch = w, int(round(w / ratio))
    cw, ch = min(cw, w), min(ch, h)
    left, top = (w - cw) // 2, (h - ch) // 2
    return left, top, left + cw, top + ch


def fit_to_portrait(path, target: tuple[int, int] = CARD_PORTRAIT_SIZE, on_event=None) -> bool:
    """Center-crop + resize the image at `path` to `target`, in place, as PNG. True on success.

    Alpha is PRESERVED: gpt-5-image-mini often returns the card subject as a cut-out on transparent
    even though nothing asked for it (measured 2026-09-18), and a cut-out over the card's own frame
    reads fine — flattening it onto black would not.

    $BTSGEN_CARD_ART_COLORS (default 256; "0" = off) quantizes to N<=256 colours before saving. Measured
    on the live smoke render: 763 KB lossless vs 304 KB at 256 colours, visually indistinguishable on
    this cel-shaded art. On by default because 34 lossless portraits are ~26 MB per class and the mod
    downloads cards.zip on the game's UI thread at import.

    Best-effort like everything else in this package: a missing Pillow or an unreadable file leaves
    the raw render in place and returns False (art at the wrong ratio still beats no art)."""
    def note(msg: str) -> None:
        if on_event:
            on_event(msg)

    try:
        from PIL import Image  # lazy: the art package must import without Pillow
    except ImportError:
        note("card art: Pillow not installed — shipping the raw render (add pillow>=10)")
        return False
    p = Path(path)
    try:
        with Image.open(p) as im:
            im.load()
            box = portrait_crop_box(im.size, target)
            out = im.convert("RGBA" if "A" in im.getbands() else "RGB")
            out = out.crop(box).resize((int(target[0]), int(target[1])), Image.LANCZOS)
            out = _quantize(out, _colour_cap(), note)
            out.save(p, format="PNG", optimize=True)
        return True
    except Exception as e:  # a Pillow bug must never fail a forge
        note(f"card art: post-process skipped ({type(e).__name__}: {e})")
        return False


DEFAULT_CARD_ART_COLORS = 256  # 34 lossless portraits are ~26 MB per class; the mod downloads that on the UI thread


def _colour_cap() -> int:
    """$BTSGEN_CARD_ART_COLORS: unset/garbage/out of range -> the 256 default; "0" switches quantization off."""
    raw = os.environ.get("BTSGEN_CARD_ART_COLORS", "").strip()
    if not raw:
        return DEFAULT_CARD_ART_COLORS
    try:
        n = int(raw)
    except ValueError:
        return DEFAULT_CARD_ART_COLORS
    if n == 0:
        return 0
    return n if 2 <= n <= 256 else DEFAULT_CARD_ART_COLORS


def _quantize(im, colors: int, note):
    """RGB(A) -> a `colors`-entry palette image. Median-cut + Floyd-Steinberg dithering, which on this
    cel-shaded art is indistinguishable from the 24-bit original (Pillow's FASTOCTREE, the only method
    that takes RGBA directly, visibly bands the shadows) — so an alpha image is quantized on its RGB
    and given back a BINARY transparency in one reserved palette slot."""
    if not colors:
        return im
    from PIL import Image
    try:
        if "A" not in im.getbands():
            return im.quantize(colors=colors, method=Image.MEDIANCUT, dither=Image.FLOYDSTEINBERG)
        pal = im.convert("RGB").quantize(colors=max(colors - 1, 2), method=Image.MEDIANCUT,
                                         dither=Image.FLOYDSTEINBERG)
        # The reserved index must EXIST in the palette: PIL trims the tRNS table to the palette's
        # length (which is however many colours quantize actually USED, not what we asked for), so a
        # transparency index one past the end is dropped and the image ships fully opaque.
        entries = list(pal.getpalette() or [])
        clear = min(len(entries) // 3, 255)
        pal.putpalette(entries[:clear * 3] + [0, 0, 0])
        pal.paste(clear, mask=im.getchannel("A").point(lambda a: 255 if a < 128 else 0))
        pal.info["transparency"] = clear
        return pal
    except Exception as e:
        note(f"card art: quantize skipped ({type(e).__name__}: {e})")
        return im


def image_size(path) -> tuple[int, int] | None:
    """(width, height) of a PNG on disk, header-only, no Pillow needed."""
    from .backends.openrouter import png_dimensions
    try:
        return png_dimensions(Path(path).read_bytes()[:64])
    except OSError:
        return None


def _slug(text: str) -> str:
    keep = [c if (c.isalnum() or c in "-_") else "_" for c in text]
    return "".join(keep)[:64] or "card"


__all__ = ["CARD_STYLE", "CARD_PORTRAIT_SIZE", "forge_card_art", "card_prompt", "card_flavor_line",
           "portrait_crop_box", "fit_to_portrait", "image_size"]
