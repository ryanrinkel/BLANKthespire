"""Zero-cost, dependency-free placeholder backend.

Tints from the structured ClassArt (its hue, derived from the class id) rather than the prompt text,
so every class gets a distinct, deterministic image with no network call. Two modes:
  * opaque (splash): a dark, hue-tinted abstract gradient backdrop.
  * transparent (sprite, req.transparent): a simple hue-robed humanoid figure on alpha — the same
    little mage the sprite spike staged, so the mod's autocrop/resize/tween path is exercised for real.
Good enough to stand in until a real image backend is wired (and for keyless dev)."""
from __future__ import annotations

import colorsys
import math

from ..png import encode_rgb, encode_rgba
from ..request import ImageRequest, ImageResult


class ProceduralBackend:
    name = "procedural"

    def available(self) -> bool:
        return True

    def generate(self, req: ImageRequest) -> ImageResult:
        hue = (req.art.hue if req.art else 0.0) % 1.0
        try:
            if req.transparent:
                # The figure is painted at its native canvas (fast, pure Python); consumers autocrop +
                # resize anyway, so req.size is advisory here.
                w, h = _FIGURE_W, _FIGURE_H
                data = encode_rgba(w, h, _render_figure(hue))
            else:
                w, h = req.size
                if w < 1 or h < 1:
                    return ImageResult(ok=False, backend=self.name, error=f"bad size {req.size}")
                data = encode_rgb(w, h, _render_backdrop(w, h, hue))
            req.out_path.parent.mkdir(parents=True, exist_ok=True)
            req.out_path.write_bytes(data)
        except OSError as e:
            return ImageResult(ok=False, backend=self.name, error=f"write failed: {e}")
        return ImageResult(ok=True, backend=self.name, path=req.out_path,
                           cost_usd=0.0, width=w, height=h)


def _render_backdrop(width: int, height: int, hue: float) -> bytes:
    """A dark, hue-tinted backdrop with a soft central bloom — abstract, not a portrait."""
    cx, cy = width / 2.0, height * 0.42
    maxd = math.hypot(max(cx, width - cx), max(cy, height - cy)) or 1.0
    buf = bytearray(width * height * 3)
    i = 0
    for y in range(height):
        vy = y / (height - 1) if height > 1 else 0.0
        base_v = 0.15 + 0.24 * vy  # dark at the top, a touch lighter toward the bottom
        for x in range(width):
            d = math.hypot(x - cx, y - cy) / maxd
            glow = 1.0 - d
            if glow < 0.0:
                glow = 0.0
            v = base_v + 0.38 * glow * glow
            s = 0.55 * (0.6 + 0.4 * glow)
            r, g, b = colorsys.hsv_to_rgb(hue, s if s < 1.0 else 1.0, v if v < 1.0 else 1.0)
            buf[i] = int(r * 255)
            buf[i + 1] = int(g * 255)
            buf[i + 2] = int(b * 255)
            i += 3
    return bytes(buf)


# --- the transparent placeholder figure (sprite mode) ---------------------------------------------

_FIGURE_W, _FIGURE_H = 460, 600  # feet on the bottom edge


def _render_figure(hue: float) -> bytes:
    """A robed staff-bearer, robe tinted by the class hue, dark outline, transparent background."""
    def hsv(s: float, v: float) -> tuple[int, int, int]:
        r, g, b = colorsys.hsv_to_rgb(hue, s, v)
        return int(r * 255), int(g * 255), int(b * 255)

    robe = hsv(0.62, 0.50)
    robe_dark = hsv(0.66, 0.38)
    accent = _accent_for(hue)
    skin = (232, 195, 154)
    wood = (107, 74, 47)
    dark = (35, 52, 58)

    p = _Painter(_FIGURE_W, _FIGURE_H)
    # back-to-front: robe, belt, feet, staff arm, head, face, staff + orb (held in front)
    p.trapezoid(165, 585, 215, 58, 122, robe)
    p.trapezoid(298, 322, 215, 74, 80, accent)                 # belt
    p.ellipse(178, 586, 34, 14, dark)                          # feet
    p.ellipse(252, 586, 34, 14, dark)
    p.capsule(255, 235, 336, 302, 16, robe_dark)               # arm reaching for the staff
    p.circle(340, 308, 13, skin)                               # hand
    p.circle(215, 118, 52, skin)                               # head
    p.trapezoid(62, 120, 215, 40, 58, robe)                    # hood top
    p.circle(228, 118, 5, dark)                                # eyes (facing right, toward the enemies)
    p.circle(250, 121, 5, dark)
    p.capsule(352, 74, 332, 562, 7, wood)                      # staff
    p.circle(356, 58, 26, accent)                              # staff orb
    p.circle(350, 52, 10, (255, 236, 170))                     # orb glint
    p.outline(dark=(28, 43, 51))
    return bytes(p.pix)


def _accent_for(hue: float) -> tuple[int, int, int]:
    """A warm accent offset from the robe hue (belt/orb) — reads as trim, not camouflage."""
    r, g, b = colorsys.hsv_to_rgb((hue + 0.45) % 1.0, 0.72, 0.92)
    return int(r * 255), int(g * 255), int(b * 255)


class _Painter:
    """Tiny RGBA shape rasterizer (bbox loops — the canvas is small, this stays fast)."""

    def __init__(self, w: int, h: int):
        self.w, self.h = w, h
        self.pix = bytearray(w * h * 4)

    def put(self, x: int, y: int, rgb: tuple[int, int, int]) -> None:
        if 0 <= x < self.w and 0 <= y < self.h:
            i = (y * self.w + x) * 4
            self.pix[i:i + 4] = bytes((*rgb, 255))

    def circle(self, cx: float, cy: float, r: float, rgb) -> None:
        for y in range(int(cy - r), int(cy + r) + 2):
            for x in range(int(cx - r), int(cx + r) + 2):
                if (x - cx) ** 2 + (y - cy) ** 2 <= r * r:
                    self.put(x, y, rgb)

    def ellipse(self, cx: float, cy: float, rx: float, ry: float, rgb) -> None:
        for y in range(int(cy - ry), int(cy + ry) + 2):
            for x in range(int(cx - rx), int(cx + rx) + 2):
                if ((x - cx) / rx) ** 2 + ((y - cy) / ry) ** 2 <= 1.0:
                    self.put(x, y, rgb)

    def capsule(self, x1: float, y1: float, x2: float, y2: float, r: float, rgb) -> None:
        dx, dy = x2 - x1, y2 - y1
        ll = dx * dx + dy * dy
        for y in range(int(min(y1, y2) - r), int(max(y1, y2) + r) + 2):
            for x in range(int(min(x1, x2) - r), int(max(x1, x2) + r) + 2):
                t = 0.0 if ll == 0 else max(0.0, min(1.0, ((x - x1) * dx + (y - y1) * dy) / ll))
                px, py = x1 + t * dx, y1 + t * dy
                if (x - px) ** 2 + (y - py) ** 2 <= r * r:
                    self.put(x, y, rgb)

    def trapezoid(self, y0: float, y1: float, cx: float, hw0: float, hw1: float, rgb) -> None:
        for y in range(int(y0), int(y1) + 1):
            f = (y - y0) / (y1 - y0)
            hw = hw0 + (hw1 - hw0) * f
            for x in range(int(cx - hw), int(cx + hw) + 1):
                self.put(x, y, rgb)

    def outline(self, dark: tuple[int, int, int]) -> None:
        """Any transparent pixel within 2px (Chebyshev) of paint turns dark — a clean silhouette edge."""
        edge: list[tuple[int, int]] = []
        for y in range(self.h):
            for x in range(self.w):
                if self.pix[(y * self.w + x) * 4 + 3] == 0 and self._near_paint(x, y):
                    edge.append((x, y))
        for x, y in edge:
            self.put(x, y, dark)

    def _near_paint(self, x: int, y: int) -> bool:
        for oy in range(-2, 3):
            for ox in range(-2, 3):
                nx, ny = x + ox, y + oy
                if 0 <= nx < self.w and 0 <= ny < self.h and self.pix[(ny * self.w + nx) * 4 + 3] == 255:
                    return True
        return False
