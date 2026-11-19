# -*- coding: utf-8 -*-
"""A minimal RGBA8 PNG writer (zlib only: Blender does not ship PIL)."""

from __future__ import annotations

import os
import struct
import zlib

try:
    import numpy as np
except ImportError:  # pragma: no cover - Blender always ships numpy
    np = None


def write_png(path, rgba):
    """Write ``rgba`` (``(ny, nx, 4)`` uint8, row 0 = ``y_min``) to ``path``; return its size."""
    ny, nx = rgba.shape[0], rgba.shape[1]
    # PNG rows run top to bottom; our grid row 0 is y_min, so flip.
    body = np.zeros((ny, nx * 4 + 1), dtype=np.uint8)
    body[:, 1:] = rgba[::-1].reshape(ny, nx * 4)
    raw = body.tobytes()

    def chunk(tag, data):
        c = struct.pack(">I", len(data)) + tag + data
        return c + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    ihdr = struct.pack(">IIBBBBB", nx, ny, 8, 6, 0, 0, 0)
    with open(path, "wb") as fh:
        fh.write(b"\x89PNG\r\n\x1a\n")
        fh.write(chunk(b"IHDR", ihdr))
        fh.write(chunk(b"IDAT", zlib.compress(raw, 6)))
        fh.write(chunk(b"IEND", b""))
    return os.path.getsize(path)
