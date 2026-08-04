"""The default backend: generates nothing. Keeps splash generation strictly opt-in — selecting no
backend (BTSGEN_IMAGE_BACKEND unset) never costs anything and never fails a forge."""
from __future__ import annotations

from ..request import ImageRequest, ImageResult


class NullBackend:
    name = "null"

    def available(self) -> bool:
        return True

    def generate(self, req: ImageRequest) -> ImageResult:
        return ImageResult(
            ok=False, backend=self.name,
            error="image generation is disabled (null backend; set BTSGEN_IMAGE_BACKEND or pass --backend)",
        )
