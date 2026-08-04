"""forge_splash — the public entry. Generate ONE class's splash from forge output.

Contract: best-effort. Returns ImageResult(ok=False, ...) instead of raising, so a missing key, an
unknown backend, or a backend bug can never abort a forge. Writes <id>.splash.<ext> and a
<id>.splash.meta.json sidecar (provenance) beside it; touches nothing the harness owns.

The `_forge_asset` engine here is shared with sprite.py (forge_sprite) — one orchestration, two asset
kinds distinguished by prompt builder, style default, and file infix."""
from __future__ import annotations

import json
from pathlib import Path

from .enrich import enrich_body
from .extract import class_art_from_bundle
from .prompt import splash_prompt
from .registry import get_backend
from .request import ClassArt, ImageRequest, ImageResult, StyleProfile
from .styles import DEFAULT_STYLE


def forge_splash(source, *, backend=None, style: StyleProfile | None = None,
                 out_dir=None, out_path=None, on_event=None) -> ImageResult:
    """`source`: a ClassArt or a forge bundle dict (web forge_to_bundle / pipeline output — this never
    calls the harness). `backend`: a name, an ImageBackend instance, or None (-> env, else 'null').
    `style`: a StyleProfile (default DEFAULT_STYLE). `out_path`: exact output file (the web keys it on
    the DB row id, e.g. static/forged/<id>/splash.png); else `out_dir`/<class_id>.splash.<ext>, default
    the generated-characters quarantine. `on_event(str)`: optional progress sink (SSE/CLI)."""
    return _forge_asset("splash", splash_prompt, source, backend=backend,
                        style=style or DEFAULT_STYLE, out_dir=out_dir, out_path=out_path,
                        on_event=on_event)


def _forge_asset(kind: str, prompt_builder, source, *, backend, style: StyleProfile,
                 out_dir, out_path, on_event) -> ImageResult:
    art = source if isinstance(source, ClassArt) else class_art_from_bundle(source)

    def note(msg: str) -> None:
        if on_event:
            on_event(msg)

    try:
        be = get_backend(backend)
    except KeyError as e:
        note(str(e))
        return ImageResult(ok=False, backend=str(backend), error=str(e))

    if out_path is not None:
        out_path = Path(out_path)
    else:
        if out_dir is None:
            from .. import paths  # lazy: only needed for the default location
            out_dir = paths.GENERATED_CHARACTERS_DIR
        out_path = Path(out_dir) / f"{art.class_id}.{kind}.{style.out_format}"

    body = enrich_body(art, kind, on_event=note)  # None unless BTSGEN_PROMPT_ENRICH is on (then best-effort)
    prompt = prompt_builder(art, style, enriched_body=body)
    req = ImageRequest(prompt=prompt, out_path=out_path, negative=style.negative or None,
                       ref_images=list(style.ref_images), size=style.size, art=art,
                       transparent=style.transparent)

    note(f"{kind}[{be.name}] '{art.name}' -> {out_path.name}")
    if not be.available():
        msg = f"backend '{be.name}' is not available (missing key/config)"
        note(msg)
        return ImageResult(ok=False, backend=be.name, error=msg)

    try:
        res = be.generate(req)
    except Exception as e:  # a backend bug must never crash the caller
        note(f"{kind} backend '{be.name}' raised: {e}")
        return ImageResult(ok=False, backend=be.name, error=f"{type(e).__name__}: {e}")

    if res.ok and res.path:
        _write_sidecar(res, art, style, prompt, enriched=body is not None)
        note(f"{kind} OK -> {res.path}")
    else:
        note(f"{kind} not produced: {res.error}")
    return res


def _write_sidecar(res: ImageResult, art: ClassArt, style: StyleProfile, prompt: str,
                   enriched: bool = False) -> None:
    # <id>.splash.png -> <id>.splash.meta.json (strip the final extension, add .meta.json)
    side = res.path.parent / (res.path.name.rsplit(".", 1)[0] + ".meta.json")
    side.write_text(json.dumps({
        "class_id": art.class_id,
        "file": res.path.name,
        "backend": res.backend,
        "style": style.name,
        "size": [res.width, res.height],
        "cost_usd": res.cost_usd,
        "hue": round(art.hue, 4),
        "enriched": enriched,
        "prompt": prompt,
    }, indent=2) + "\n")
