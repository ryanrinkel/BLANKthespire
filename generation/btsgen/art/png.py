"""Minimal dependency-free PNG encoder (8-bit truecolor RGB).

The art skeleton stays out of the core dependency set (btsgen ships only anthropic + jsonschema), so
the offline 'procedural' backend writes PNGs with the stdlib (zlib + struct) instead of Pillow. Cloud
backends that want WebP / resizing can pull their own deps lazily."""
from __future__ import annotations

import struct
import zlib


def encode_rgb(width: int, height: int, pixels: bytes) -> bytes:
    """Encode raw RGB bytes (length width*height*3, row-major top-to-bottom) into a PNG byte string."""
    return _encode(width, height, pixels, channels=3, colour_type=2)


def encode_rgba(width: int, height: int, pixels: bytes) -> bytes:
    """Encode raw RGBA bytes (length width*height*4) into a PNG byte string — for transparent sprites."""
    return _encode(width, height, pixels, channels=4, colour_type=6)


def _encode(width: int, height: int, pixels: bytes, *, channels: int, colour_type: int) -> bytes:
    if len(pixels) != width * height * channels:
        raise ValueError(f"expected {width * height * channels} bytes, got {len(pixels)}")
    stride = width * channels
    raw = bytearray()
    for y in range(height):
        raw.append(0)  # per-scanline filter type 0 (none)
        raw += pixels[y * stride:(y + 1) * stride]

    def _chunk(tag: bytes, data: bytes) -> bytes:
        body = tag + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF)

    sig = b"\x89PNG\r\n\x1a\n"
    ihdr = struct.pack(">IIBBBBB", width, height, 8, colour_type, 0, 0, 0)
    idat = zlib.compress(bytes(raw), 9)
    return sig + _chunk(b"IHDR", ihdr) + _chunk(b"IDAT", idat) + _chunk(b"IEND", b"")
