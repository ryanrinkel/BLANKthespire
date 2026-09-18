"""forge_splash — the public entry. Generate ONE class's splash from forge output.

Contract: best-effort. Returns ImageResult(ok=False, ...) instead of raising, so a missing key, an
unknown backend, or a backend bug can never abort a forge. Writes <id>.splash.<ext> and a
<id>.splash.meta.json sidecar (provenance) beside it; touches nothing the harness owns.

The `_forge_asset` engine here is shared with sprite.py (forge_sprite) and card.py (forge_card_art) —
one orchestration, three asset kinds distinguished by prompt builder, style default, and file infix.
It also owns the BACKEND CHAIN: $BTSGEN_IMAGE_BACKEND may list tiers ('openrouter,openai')."""
from __future__ import annotations

import json
from pathlib import Path

from .enrich import enrich_body
from .extract import class_art_from_bundle
from .prompt import splash_prompt
from .registry import resolve_backends
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
                 out_dir, out_path, on_event, stem_suffix: str | None = None,
                 enrich: bool = True, postprocess=None) -> ImageResult:
    """`backend` may name a CHAIN ('openrouter,openai', or a list): each available backend is tried in
    order and the first ok result wins, so one vendor's outage costs a retry instead of the art. Only
    when every tier fails does this return ok=False (with the tiers' errors joined).

    `stem_suffix` extends the default filename (<id>.card.<card_id>.png — card art is per card);
    `enrich=False` skips the optional LLM prompt enrichment entirely (cards: 34 calls, little gain);
    `postprocess(res, note)` runs on a successful result BEFORE the sidecar is written, so the sidecar
    records the shipped file's dimensions (card art is cropped to the mod's portrait box)."""
    art = source if isinstance(source, ClassArt) else class_art_from_bundle(source)

    def note(msg: str) -> None:
        if on_event:
            on_event(msg)

    try:
        chain = resolve_backends(backend)
    except KeyError as e:
        note(str(e))
        return ImageResult(ok=False, backend=str(backend), error=str(e))

    if out_path is not None:
        out_path = Path(out_path)
    else:
        if out_dir is None:
            from .. import paths  # lazy: only needed for the default location
            out_dir = paths.GENERATED_CHARACTERS_DIR
        stem = f"{art.class_id}.{kind}" + (f".{stem_suffix}" if stem_suffix else "")
        out_path = Path(out_dir) / f"{stem}.{style.out_format}"

    # None unless BTSGEN_PROMPT_ENRICH is on (then best-effort); never for cards.
    body = enrich_body(art, kind, on_event=note) if enrich else None
    prompt = prompt_builder(art, style, enriched_body=body)
    req = ImageRequest(prompt=prompt, out_path=out_path, negative=style.negative or None,
                       ref_images=list(style.ref_images), size=style.size, art=art,
                       transparent=style.transparent, kind=kind)

    note(f"{kind}[{','.join(b.name for b in chain)}] '{art.name}' -> {out_path.name}")
    res: ImageResult | None = None
    errors: list[str] = []
    for be in chain:
        if not be.available():
            msg = f"backend '{be.name}' is not available (missing key/config)"
            note(msg)
            errors.append(msg)
            res = ImageResult(ok=False, backend=be.name, error=msg)
            continue
        try:
            res = be.generate(req)
        except Exception as e:  # a backend bug must never crash the caller
            note(f"{kind} backend '{be.name}' raised: {e}")
            errors.append(f"{be.name}: {type(e).__name__}: {e}")
            res = ImageResult(ok=False, backend=be.name, error=f"{type(e).__name__}: {e}")
            continue
        if res.ok and res.path:
            break
        errors.append(f"{be.name}: {res.error}")
        note(f"{kind} backend '{be.name}' failed: {res.error}")

    if res is None:  # an empty chain can only come from a caller passing []
        return ImageResult(ok=False, backend=str(backend), error="no image backend selected")
    if res.ok and res.path:
        if postprocess is not None:
            postprocess(res, note)
        _write_sidecar(res, art, style, prompt, enriched=body is not None)
        note(f"{kind} OK -> {res.path}")
        return res
    if len(errors) > 1:  # one line naming every tier that refused, in order
        res.error = " | ".join(errors)
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
        "model": res.model,
        "style": style.name,
        "size": [res.width, res.height],
        "cost_usd": res.cost_usd,
        "hue": round(art.hue, 4),
        "enriched": enriched,
        "prompt": prompt,
    }, indent=2) + "\n")
