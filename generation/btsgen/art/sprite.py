"""forge_sprite — the class's standing combat model (the in-battle player sprite).

Same best-effort contract and orchestration as forge_splash (see splash._forge_asset); differs only in
the prompt (one whole cut-out figure, facing right), the default style (portrait + transparent), and
the file infix (<id>.sprite.<ext>). The mod consumes the result via the bundle's `sprite_url`:
it autocrops the alpha padding, resizes to its stage height, and drives tween micro-animations."""
from __future__ import annotations

from .prompt import sprite_prompt
from .request import ImageResult, StyleProfile
from .splash import _forge_asset
from .styles import SPRITE_STYLE


def forge_sprite(source, *, backend=None, style: StyleProfile | None = None,
                 out_dir=None, out_path=None, on_event=None) -> ImageResult:
    """`source`: a ClassArt or a forge bundle dict. Best-effort: never raises, ok=False is normal."""
    return _forge_asset("sprite", sprite_prompt, source, backend=backend,
                        style=style or SPRITE_STYLE, out_dir=out_dir, out_path=out_path,
                        on_event=on_event)
