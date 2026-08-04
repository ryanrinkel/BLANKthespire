"""One-shot generator for the per-card-TYPE placeholder portraits (attack/skill/power).

Matches the shipped card.png doodle style (bold stroke on black) but gives each card type its own
glyph + tint so a hand of generated cards reads at a glance:
    attack -> sword / blade (red)      card_attack.png
    skill  -> ring / guard (blue)      card_skill.png
    power  -> radiant burst (purple)   card_power.png

Writes 1000x760 originals into images/card_portraits/big/ and 4x box-downsampled 250x190 copies into
images/card_portraits/ (the two sizes DataCard's BigCardImagePath()/CardImagePath() expect).
Dependency-free: reuses generation/btsgen/art/png.py (stdlib PNG encoder).

Run from the repo root:  python3 mod/tools/gen_placeholder_card_art.py
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "generation"))

from btsgen.art.png import encode_rgb  # noqa: E402  (path bootstrap above)

W, H = 1000, 760  # big portrait; small is exactly /4
OUT_DIR = REPO / "mod" / "BlankTheSpire" / "images" / "card_portraits"


def seg_dist(px: float, py: float, ax: float, ay: float, bx: float, by: float) -> float:
    """Distance from point P to segment AB."""
    vx, vy = bx - ax, by - ay
    wx, wy = px - ax, py - ay
    t = max(0.0, min(1.0, (wx * vx + wy * vy) / (vx * vx + vy * vy)))
    return math.hypot(px - (ax + t * vx), py - (ay + t * vy))


def paint(shapes, colour) -> bytes:
    """Render shapes (list of (dist_fn, stroke_radius)) as soft-edged strokes of `colour` on black."""
    r, g, b = colour
    buf = bytearray(W * H * 3)
    for y in range(H):
        row = y * W * 3
        for x in range(W):
            a = 0.0
            for dist_fn, rad in shapes:
                d = dist_fn(x, y)
                a = max(a, min(1.0, max(0.0, (rad - d) / (rad * 0.18))))  # soft edge
                if a >= 1.0:
                    break
            if a > 0.0:
                i = row + x * 3
                buf[i] = int(r * a)
                buf[i + 1] = int(g * a)
                buf[i + 2] = int(b * a)
    return bytes(buf)


def stroke(ax, ay, bx, by, rad):
    return (lambda x, y: seg_dist(x, y, ax, ay, bx, by), rad)


def ring(cx, cy, radius, rad):
    return (lambda x, y: abs(math.hypot(x - cx, y - cy) - radius), rad)


def downsample4(big: bytes) -> bytes:
    """4x4 box-average 1000x760 RGB -> 250x190 RGB."""
    w, h = W // 4, H // 4
    out = bytearray(w * h * 3)
    for y in range(h):
        for x in range(w):
            sums = [0, 0, 0]
            for dy in range(4):
                base = ((y * 4 + dy) * W + x * 4) * 3
                for dx in range(4):
                    i = base + dx * 3
                    sums[0] += big[i]
                    sums[1] += big[i + 1]
                    sums[2] += big[i + 2]
            o = (y * w + x) * 3
            out[o] = sums[0] // 16
            out[o + 1] = sums[1] // 16
            out[o + 2] = sums[2] // 16
    return bytes(out)


def main() -> None:
    cx, cy = W / 2, H / 2
    art = {
        # attack: a sword — blade with a thinner tip, crossguard, grip, pommel dot.
        # (Was crossed slashes; players read the X as "can't play this card".)
        "card_attack.png": ([stroke(375, 520, 745, 150, 40),   # blade
                             stroke(745, 150, 790, 105, 18),   # tapered tip
                             stroke(304, 449, 446, 591, 26),   # crossguard
                             stroke(375, 520, 280, 615, 22),   # grip
                             ring(265, 630, 0, 26)],           # pommel
                            (235, 90, 75)),
        # skill: a guard ring with a small inner dot
        "card_skill.png": ([ring(cx, cy, 235, 32),
                            ring(cx, cy, 12, 26)], (95, 160, 235)),
        # power: a six-ray radiant burst
        "card_power.png": ([stroke(cx, cy - 265, cx, cy + 265, 30),
                            stroke(cx - 232, cy - 132, cx + 232, cy + 132, 30),
                            stroke(cx - 232, cy + 132, cx + 232, cy - 132, 30),
                            ring(cx, cy, 68, 30)], (185, 110, 235)),
    }
    (OUT_DIR / "big").mkdir(parents=True, exist_ok=True)
    for name, (shapes, colour) in art.items():
        big = paint(shapes, colour)
        (OUT_DIR / "big" / name).write_bytes(encode_rgb(W, H, big))
        small = downsample4(big)
        (OUT_DIR / name).write_bytes(encode_rgb(W // 4, H // 4, small))
        print(f"wrote {OUT_DIR / 'big' / name} + small")


if __name__ == "__main__":
    main()
