"""Draws kustos.ico: the logbook's emblem (dithered concentric rings, ink on
paper) at the sizes Windows uses. Standard library only: each size is a PNG
written by hand, and the .ico simply holds the PNGs.

    python tools/make_icon.py        -> kustos.ico next to _kustos.py
"""
import math
import struct
import zlib
from pathlib import Path

PAPER = (233, 227, 209, 255)
INK = (38, 36, 31, 255)
CLEAR = (0, 0, 0, 0)
SIZES = (16, 24, 32, 48, 64, 128, 256)


def pixel(x, y, n):
    """The colour of pixel (x, y) in an n×n icon."""
    c = (n - 1) / 2
    corner = n * 0.18                       # rounded square
    dx = max(0.0, abs(x - c) - (c - corner))
    dy = max(0.0, abs(y - c) - (c - corner))
    if dx * dx + dy * dy > corner * corner:
        return CLEAR
    if n >= 32 and (x in (1, n - 2) or y in (1, n - 2)) and dx == dy == 0:
        return INK                          # a thin frame, like the title page
    r = math.hypot(x - c, y - c) / (n / 2)
    # rings, outermost to innermost: light, medium and heavy dither, then the hole
    if r > 0.86:
        return PAPER
    if r > 0.66:
        return INK if (x + y) % 4 == 0 and x % 2 == 0 else PAPER
    if r > 0.46:
        return INK if (x + y) % 2 == 0 and y % 2 == 0 else PAPER
    if r > 0.24:
        return INK if (x + y) % 2 == 0 else PAPER
    if r > 0.16:
        return INK
    return PAPER


def png(n):
    rows = b"".join(b"\x00" + b"".join(bytes(pixel(x, y, n)) for x in range(n)) for y in range(n))

    def chunk(kind, data):
        return (struct.pack(">I", len(data)) + kind + data
                + struct.pack(">I", zlib.crc32(kind + data) & 0xffffffff))

    return (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", struct.pack(">IIBBBBB", n, n, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(rows, 9))
            + chunk(b"IEND", b""))


def ico(sizes=SIZES):
    images = [png(n) for n in sizes]
    head = struct.pack("<HHH", 0, 1, len(images))
    offset = 6 + 16 * len(images)
    entries = b""
    for n, data in zip(sizes, images):
        entries += struct.pack("<BBBBHHII", n % 256, n % 256, 0, 0, 1, 32, len(data), offset)
        offset += len(data)
    return head + entries + b"".join(images)


if __name__ == "__main__":
    out = Path(__file__).resolve().parent.parent / "kustos.ico"
    out.write_bytes(ico())
    print(f"{out.name}: {out.stat().st_size} bytes, sizes {', '.join(map(str, SIZES))}")
