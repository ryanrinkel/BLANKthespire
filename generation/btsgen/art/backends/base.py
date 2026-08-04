"""The backend contract — the whole pluggable point. Add a backend by writing a class with these
three members and registering it (see ../registry.py)."""
from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from ..request import ImageRequest, ImageResult


@runtime_checkable
class ImageBackend(Protocol):
    """name:        stable id, selected via $BTSGEN_IMAGE_BACKEND or forge_splash(backend=...).
    available():    cheap check that the backend can run (keys/config present); gated before generate().
    generate(req):  produce the image; return ImageResult(ok=...). MUST NOT raise for EXPECTED failures
                    (missing key, API error, write error) — return ok=False with an error string. The
                    orchestrator also wraps generate() so an unexpected raise degrades to ok=False."""
    name: str

    def available(self) -> bool: ...

    def generate(self, req: "ImageRequest") -> "ImageResult": ...
