"""The data types every backend speaks. Kept dependency-free (stdlib dataclasses only)."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ClassArt:
    """Normalized 'what to draw' for one class, extracted from a forge bundle or the on-disk
    character.json/meta.json. The prompt builder and backends consume THIS, never the raw bundle —
    so nothing in the art package depends on the creative harness's internals."""
    class_id: str
    name: str
    description: str = ""
    concept: str = ""
    archetypes: list[str] = field(default_factory=list)
    # Layered-by-role flavor (staged front-end): `flavor` = the flavor-facet names, `imagery` = concrete visual
    # motifs to dress the splash in. When present the prompt leads with these instead of the MECHANICAL archetype
    # names (which misdirect the art — e.g. a soccer class rendered as a "gambler" from a slot_machine archetype).
    flavor: list[str] = field(default_factory=list)
    imagery: list[str] = field(default_factory=list)
    hue: float = 0.0  # 0..1; derived from the class id (no pool-colour field exists upstream yet)


@dataclass
class StyleProfile:
    """The consistency lever. Swap profiles to A/B a look (prompt suffix, references, size, format)
    WITHOUT touching backends or the harness. A future styles/ dir can hold several; styles.py ships
    one default."""
    name: str = "default"
    prompt_suffix: str = ""
    negative: str = ""
    ref_images: list[Path] = field(default_factory=list)  # style references (cloud backends)
    size: tuple[int, int] = (1024, 576)
    out_format: str = "png"  # png (procedural, stdlib) | webp (cloud backends — smaller, plan default)
    transparent: bool = False  # cut-out subject on alpha (character sprites) vs a full-bleed scene (splash)


@dataclass
class ImageRequest:
    """One concrete request handed to a backend. Carries both the text `prompt` (cloud backends) and
    the structured `art` (the procedural backend tints from art.hue — no NLP needed)."""
    prompt: str
    out_path: Path
    negative: str | None = None
    ref_images: list[Path] = field(default_factory=list)
    size: tuple[int, int] = (1024, 576)
    seed: int | None = None
    art: ClassArt | None = None
    transparent: bool = False  # request an alpha-channel cut-out (openai: background=transparent)


@dataclass
class ImageResult:
    """A backend's verdict. ok=False is normal (disabled/missing-key/error) — callers must handle it,
    never assume a path. cost_usd lets the token economy meter real backends."""
    ok: bool
    backend: str
    path: Path | None = None
    cost_usd: float | None = None
    width: int | None = None
    height: int | None = None
    error: str | None = None
