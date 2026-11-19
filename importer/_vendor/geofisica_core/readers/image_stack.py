# -*- coding: utf-8 -*-
"""``image_stack`` — one image per slice, the depth in the file name.

``Slice_-2889mm.jpg``, ``slice_0.100 - 0.200m.png`` …, optionally with an
ESRI world file (``.tfw``/``.pgw``/``.jgw``) for the extent. This is the form
the UA Ilici GEORRADAR sectors ship in — and the form the cache writes when
it rasterises a ``csv_grid`` stack, so the two paths converge.
"""

from __future__ import annotations

import struct

IMG_EXT = (".png", ".jpg", ".jpeg", ".tif", ".tiff")


def image_size(path):
    """Return ``(width, height)`` from a PNG/JPEG/TIFF header, without PIL.

    Blender does not ship Pillow, and reading 601 Ilici JPEGs just to learn
    their size would be absurd; the header is enough.
    """
    with open(path, "rb") as fh:
        head = fh.read(32)
        if head[:8] == b"\x89PNG\r\n\x1a\n":
            w, h = struct.unpack(">II", head[16:24])
            return int(w), int(h)
        if head[:2] == b"\xff\xd8":                      # JPEG: scan for SOFn
            fh.seek(2)
            while True:
                b = fh.read(1)
                if not b:
                    break
                if b != b"\xff":
                    continue
                marker = fh.read(1)
                while marker == b"\xff":
                    marker = fh.read(1)
                m = marker[0]
                if m in (0xD8, 0xD9) or 0xD0 <= m <= 0xD7:
                    continue
                ln = struct.unpack(">H", fh.read(2))[0]
                if 0xC0 <= m <= 0xCF and m not in (0xC4, 0xC8, 0xCC):
                    data = fh.read(5)
                    h, w = struct.unpack(">HH", data[1:5])
                    return int(w), int(h)
                fh.seek(ln - 2, 1)
            raise ValueError("no SOF marker in %s" % path)
        if head[:2] in (b"II", b"MM"):                   # TIFF
            end = "<" if head[:2] == b"II" else ">"
            off = struct.unpack(end + "I", head[4:8])[0]
            fh.seek(off)
            n = struct.unpack(end + "H", fh.read(2))[0]
            w = h = None
            for _ in range(n):
                tag, typ, _cnt = struct.unpack(end + "HHI", fh.read(8))
                raw = fh.read(4)
                val = struct.unpack(end + "H", raw[:2])[0] if typ == 3 else \
                    struct.unpack(end + "I", raw)[0]
                if tag == 256:
                    w = val
                elif tag == 257:
                    h = val
            if w and h:
                return int(w), int(h)
            raise ValueError("no ImageWidth/Length in %s" % path)
    raise ValueError("unrecognised image format: %s" % path)
