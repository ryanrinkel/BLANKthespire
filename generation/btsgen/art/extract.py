"""Turn forge OUTPUT into a ClassArt — the only place the art package touches the harness's shapes.

Two sources, same result:
  * class_art_from_bundle(dict)  — the in-memory forge result (web forge_to_bundle / pipeline), which
                                   carries the richer `blueprint` (archetype names) + `character`.
  * class_art_from_disk(id)      — the quarantined <id>.json (+ <id>.meta.json for concept/archetypes),
                                   so a splash can be (re)generated long after the forge, no harness call.
Neither mutates its input."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .request import ClassArt


def class_art_from_bundle(bundle: dict) -> ClassArt:
    char = bundle.get("character") or {}
    bp = bundle.get("blueprint") or {}
    archetypes: list[str] = []
    for a in bp.get("archetypes", []) or []:
        if isinstance(a, dict):
            archetypes.append(a.get("name") or a.get("id"))
        elif isinstance(a, str):
            archetypes.append(a)
    cid = str(char.get("id") or bp.get("id") or "forged_class")
    skin = bp.get("skin") or {}
    return ClassArt(
        class_id=cid,
        name=str(char.get("name") or bp.get("name") or cid),
        description=str(char.get("description") or bp.get("description") or ""),
        concept=str(bundle.get("concept") or bp.get("concept") or ""),
        archetypes=[a for a in archetypes if a],
        flavor=[str(x) for x in (skin.get("flavor") or [])],
        imagery=[str(x) for x in (skin.get("imagery") or [])],
        hue=hue_from_id(cid),
    )


def class_art_from_disk(class_id: str, characters_dir: Path | str | None = None) -> ClassArt:
    from .. import paths  # lazy: importing the art package must not require the Godot project
    d = Path(characters_dir) if characters_dir else paths.GENERATED_CHARACTERS_DIR
    char = json.loads((d / f"{class_id}.json").read_text())
    meta: dict = {}
    mp = d / f"{class_id}.meta.json"
    if mp.exists():
        meta = json.loads(mp.read_text())
    cid = str(char.get("id", class_id))
    skin = meta.get("skin") or {}
    return ClassArt(
        class_id=cid,
        name=str(char.get("name", class_id)),
        description=str(char.get("description", "")),
        concept=str(meta.get("concept", "")),
        archetypes=[str(a) for a in (meta.get("archetypes") or [])],
        flavor=[str(x) for x in (skin.get("flavor") or [])],
        imagery=[str(x) for x in (skin.get("imagery") or [])],
        hue=hue_from_id(cid),
    )


def hue_from_id(class_id: str) -> float:
    """Deterministic 0..1 hue from the class id. Stand-in until an upstream pool-colour field exists
    (see SPLASH_ART_PLAN.md) — same class always gets the same tint; different ids almost always differ."""
    return hashlib.sha1(class_id.encode("utf-8")).digest()[0] / 255.0
