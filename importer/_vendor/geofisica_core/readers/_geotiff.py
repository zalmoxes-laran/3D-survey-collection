"""A GeoTIFF read without GDAL — its georeference always, its pixels for the
simple encodings (MICRO-GIS-BASE, 6 Nov 2026).

What a raster layer needs to be a RESOURCE is in its tags, not its pixels:
size, the affine from pixel to CRS (ModelTiepoint + ModelPixelScale, or
ModelTransformation, or a world file beside it), the CRS from the GeoKeys
(ProjectedCSTypeGeoKey 3072, else GeographicTypeGeoKey 2048; 32767 is
«user-defined», i.e. not said), PixelIsPoint, GDAL's nodata (42113), and
whether it is a COG (tiled, with overviews, GDAL's «LAYOUT=COG» ghost header).
All read here by hand: classic TIFF and BigTIFF, both byte orders.

The pixels (:func:`read_band`) are read for what a DEM of a site usually is —
one band, uncompressed, Deflate, LZW or PackBits, strips or tiles, the
horizontal predictor — and whatever else is refused with a sentence
(:class:`GeoTiffError`), so a caller with Pillow can take over (EMStudio's
bridge does). :func:`write_geotiff` writes the plainest GeoTIFF there is
(one strip, no compression): what the tests generate, never a product.
"""

from __future__ import annotations

import math
import os
import struct
import zlib
from typing import Any, Dict, List, Optional, Sequence, Tuple

_TYPES = {1: ("B", 1), 2: ("c", 1), 3: ("H", 2), 4: ("I", 4), 5: ("II", 8), 6: ("b", 1),
          7: ("B", 1), 8: ("h", 2), 9: ("i", 4), 10: ("ii", 8), 11: ("f", 4), 12: ("d", 8),
          16: ("Q", 8), 17: ("q", 8), 18: ("Q", 8)}

T_WIDTH, T_HEIGHT, T_BITS, T_COMPRESSION, T_PHOTOMETRIC = 256, 257, 258, 259, 262
T_STRIP_OFFSETS, T_SPP, T_ROWS_PER_STRIP, T_STRIP_COUNTS = 273, 277, 278, 279
T_PLANAR, T_PREDICTOR, T_TILE_W, T_TILE_H, T_TILE_OFFSETS, T_TILE_COUNTS = 284, 317, 322, 323, 324, 325
T_SAMPLE_FORMAT, T_SUBFILE = 339, 254
T_PIXEL_SCALE, T_TIEPOINT, T_TRANSFORM, T_GEOKEYS, T_NODATA = 33550, 33922, 34264, 34735, 42113


class GeoTiffError(ValueError):
    pass


def _read_ifds(fh) -> Tuple[str, List[Dict[int, Any]], bytes]:
    head = fh.read(16)
    if head[:2] == b"II":
        end = "<"
    elif head[:2] == b"MM":
        end = ">"
    else:
        raise GeoTiffError("not a TIFF")
    magic = struct.unpack_from(end + "H", head, 2)[0]
    big = magic == 43
    if magic not in (42, 43):
        raise GeoTiffError("not a TIFF")
    off = struct.unpack_from(end + "Q", head, 8)[0] if big else struct.unpack_from(end + "I", head, 4)[0]
    # GDAL's ghost header right after the TIFF header (a COG says LAYOUT=COG)
    fh.seek(16 if big else 8)
    ghost = fh.read(512)
    ifds: List[Dict[int, Any]] = []
    seen = set()
    while off and off not in seen and len(ifds) < 64:
        seen.add(off)
        fh.seek(off)
        if big:
            n = struct.unpack(end + "Q", fh.read(8))[0]
            esize, vsize = 20, 8
        else:
            n = struct.unpack(end + "H", fh.read(2))[0]
            esize, vsize = 12, 4
        raw = fh.read(n * esize)
        nxt = fh.read(8 if big else 4)
        tags: Dict[int, Any] = {}
        for i in range(n):
            e = raw[i * esize:(i + 1) * esize]
            if big:
                tag, typ, cnt = struct.unpack_from(end + "HHQ", e, 0)
                vfield = e[12:20]
            else:
                tag, typ, cnt = struct.unpack_from(end + "HHI", e, 0)
                vfield = e[8:12]
            if typ not in _TYPES:
                continue
            fmt, size = _TYPES[typ]
            nbytes = size * cnt
            if nbytes <= vsize:
                data = vfield[:nbytes]
            else:
                pos = struct.unpack_from(end + ("Q" if big else "I"), vfield, 0)[0]
                here = fh.tell()
                fh.seek(pos)
                data = fh.read(nbytes)
                fh.seek(here)
            if typ == 2:
                tags[tag] = data.split(b"\x00")[0].decode("latin-1")
            elif typ in (5, 10):
                v = struct.unpack(end + fmt[0] * (2 * cnt), data)
                tags[tag] = [v[2 * k] / v[2 * k + 1] if v[2 * k + 1] else 0.0 for k in range(cnt)]
            else:
                tags[tag] = list(struct.unpack(end + fmt * cnt, data))
        ifds.append(tags)
        if len(nxt) < (8 if big else 4):
            break
        off = struct.unpack(end + ("Q" if big else "I"), nxt)[0]
    return end, ifds, ghost


def _first(tags, tag, default=None):
    v = tags.get(tag)
    if isinstance(v, list):
        return v[0] if v else default
    return default if v is None else v


def _geokeys(tags) -> Dict[int, Any]:
    keys = tags.get(T_GEOKEYS)
    out: Dict[int, Any] = {}
    if not keys or len(keys) < 4:
        return out
    for i in range(keys[3]):
        k, loc, _cnt, val = keys[4 + 4 * i: 8 + 4 * i]
        if loc == 0:
            out[k] = val
    return out


def _world_file(path: str):
    stem = os.path.splitext(path)[0]
    for ext in (".tfw", ".tifw", ".wld", ".TFW"):
        if os.path.exists(stem + ext):
            with open(stem + ext) as fh:
                v = [float(s) for s in fh.read().split()[:6]]
            # a world file names the centre of the top-left pixel
            return (v[4] - v[0] / 2 - v[2] / 2, v[0], v[2], v[5] - v[1] / 2 - v[3] / 2, v[1], v[3])
    return None


def read_geotiff_info(path: str) -> Dict[str, Any]:
    """``{width, height, bands, bits, sample_format, kind, crs, vertical_crs,
    affine, pixel_size, bbox, nodata, compression, tiled, overviews, cog,
    georef_source}``. ``affine`` is ``(x0, a, b, y0, d, e)``: X = x0 + a·col +
    b·row, Y = y0 + d·col + e·row, at the pixel's CORNER. ``kind`` ``dem``
    (one band of 16/32 bits or float) or ``image``."""
    with open(path, "rb") as fh:
        end, ifds, ghost = _read_ifds(fh)
    if not ifds:
        raise GeoTiffError("a TIFF without an image")
    t = ifds[0]
    w, h = int(_first(t, T_WIDTH, 0)), int(_first(t, T_HEIGHT, 0))
    spp = int(_first(t, T_SPP, 1))
    bits = int(_first(t, T_BITS, 1))
    fmt = int(_first(t, T_SAMPLE_FORMAT, 1))
    gk = _geokeys(t)
    code = gk.get(3072) or gk.get(2048)
    crs = f"EPSG:{int(code)}" if code and code != 32767 else None
    vcode = gk.get(4096)
    affine = None
    source = None
    if T_TRANSFORM in t:
        m = t[T_TRANSFORM]
        affine = (m[3], m[0], m[1], m[7], m[4], m[5])
        source = "ModelTransformation"
    elif T_TIEPOINT in t and T_PIXEL_SCALE in t:
        tp, sc = t[T_TIEPOINT], t[T_PIXEL_SCALE]
        i, j, X, Y = tp[0], tp[1], tp[3], tp[4]
        affine = (X - i * sc[0], sc[0], 0.0, Y + j * sc[1], 0.0, -sc[1])
        source = "ModelTiepoint+ModelPixelScale"
    else:
        affine = _world_file(path)
        source = "world file" if affine else None
    if affine and gk.get(1025) == 2:      # PixelIsPoint: the tie is at the pixel's centre
        x0, a, b, y0, d, e = affine
        affine = (x0 - a / 2 - b / 2, a, b, y0 - d / 2 - e / 2, d, e)
    bbox = None
    if affine:
        cs = [pixel_to_crs(affine, c, r) for c, r in ((0, 0), (w, 0), (w, h), (0, h))]
        bbox = [min(p[0] for p in cs), min(p[1] for p in cs), max(p[0] for p in cs), max(p[1] for p in cs)]
    nodata = None
    if T_NODATA in t:
        try:
            nodata = float(str(t[T_NODATA]).strip("\x00 "))
        except ValueError:
            nodata = None
    tiled = T_TILE_OFFSETS in t
    overviews = sum(1 for x in ifds[1:] if int(_first(x, T_SUBFILE, 0)) & 1)
    ghost_cog = b"LAYOUT=COG" in ghost
    kind = "dem" if spp == 1 and (fmt == 3 or bits >= 16) else "image"
    return {"width": w, "height": h, "bands": spp, "bits": bits, "sample_format": fmt,
            "kind": kind, "crs": crs, "vertical_crs": f"EPSG:{int(vcode)}" if vcode and vcode != 32767 else None,
            "affine": list(affine) if affine else None,
            "pixel_size": math.hypot(affine[1], affine[4]) if affine else None,
            "bbox": bbox, "nodata": nodata,
            "compression": int(_first(t, T_COMPRESSION, 1)), "tiled": tiled,
            "overviews": overviews, "cog": bool(tiled and (ghost_cog or overviews)),
            "georef_source": source}


def pixel_to_crs(affine: Sequence[float], col: float, row: float) -> Tuple[float, float]:
    x0, a, b, y0, d, e = affine
    return x0 + a * col + b * row, y0 + d * col + e * row


def crs_to_pixel(affine: Sequence[float], X: float, Y: float) -> Tuple[float, float]:
    x0, a, b, y0, d, e = affine
    det = a * e - b * d
    dx, dy = X - x0, Y - y0
    return (e * dx - b * dy) / det, (-d * dx + a * dy) / det


# ── the pixels ─────────────────────────────────────────────────────────────

def _lzw(data: bytes) -> bytes:
    out = bytearray()
    table = [bytes([i]) for i in range(256)] + [b"", b""]
    width, pos, prev = 9, 0, None
    nbits = len(data) * 8
    while pos + width <= nbits:
        byte, bit = divmod(pos, 8)
        chunk = int.from_bytes(data[byte:byte + 4].ljust(4, b"\x00"), "big")
        code = (chunk >> (32 - bit - width)) & ((1 << width) - 1)
        pos += width
        if code == 256:
            table = table[:258]
            width, prev = 9, None
            continue
        if code == 257:
            break
        if prev is None:
            entry = table[code]
        elif code < len(table):
            entry = table[code]
            table.append(prev + entry[:1])
        else:
            entry = prev + prev[:1]
            table.append(entry)
        out += entry
        prev = entry
        if len(table) + 1 >= (1 << width) and width < 12:
            width += 1
    return bytes(out)


def _packbits(data: bytes) -> bytes:
    out = bytearray()
    i = 0
    while i < len(data):
        n = data[i]
        i += 1
        if n < 128:
            out += data[i:i + n + 1]
            i += n + 1
        elif n > 128:
            out += data[i:i + 1] * (257 - n)
            i += 1
    return bytes(out)


def _decode(raw: bytes, compression: int) -> bytes:
    if compression == 1:
        return raw
    if compression in (8, 32946):
        return zlib.decompress(raw)
    if compression == 5:
        return _lzw(raw)
    if compression == 32773:
        return _packbits(raw)
    raise GeoTiffError(f"compression {compression} is not read here (JPEG, LERC, ZSTD…: Pillow/GDAL)")


def read_band(path: str, band: int = 0) -> Dict[str, Any]:
    """The pixels of one band as rows of floats: ``{width, height, rows,
    nodata}`` — for the encodings in the module's note, else GeoTiffError."""
    info = read_geotiff_info(path)
    with open(path, "rb") as fh:
        end, ifds, _ = _read_ifds(fh)
        t = ifds[0]
        w, h, spp = info["width"], info["height"], info["bands"]
        bits_l = t.get(T_BITS) or [info["bits"]]
        bits = int(bits_l[0])
        if any(int(b) != bits for b in bits_l):
            raise GeoTiffError("bands of different widths are not read here")
        fmt = info["sample_format"]
        code = {(1, 8): "B", (2, 8): "b", (1, 16): "H", (2, 16): "h", (1, 32): "I", (2, 32): "i",
                (3, 32): "f", (3, 64): "d"}.get((fmt, bits))
        if not code:
            raise GeoTiffError(f"samples of {bits} bits, format {fmt}, are not read here")
        planar = int(_first(t, T_PLANAR, 1))
        pred = int(_first(t, T_PREDICTOR, 1))
        if pred == 3:
            raise GeoTiffError("the floating-point predictor is not read here (Pillow/GDAL)")
        comp = info["compression"]
        size = bits // 8
        grid = [[0.0] * w for _ in range(h)]

        def put_block(buf: bytes, bw: int, bh: int, x0: int, y0: int, per: int):
            vals = struct.unpack(end + code * (len(buf) // size), buf[: (len(buf) // size) * size])
            stride = bw * per
            for r in range(bh):
                y = y0 + r
                if y >= h:
                    break
                rowv = list(vals[r * stride:(r + 1) * stride])
                if pred == 2:
                    for k in range(per, len(rowv)):
                        rowv[k] = rowv[k] + rowv[k - per]
                        if code in "BbHhIi":
                            rowv[k] &= (1 << bits) - 1
                for c in range(bw):
                    x = x0 + c
                    if x >= w:
                        break
                    grid[y][x] = float(rowv[c * per + (band if per > 1 else 0)])

        per = spp if planar == 1 else 1
        if T_TILE_OFFSETS in t:
            tw, th = int(_first(t, T_TILE_W)), int(_first(t, T_TILE_H))
            offs, cnts = t[T_TILE_OFFSETS], t[T_TILE_COUNTS]
            across, down = -(-w // tw), -(-h // th)
            base = band * across * down if planar == 2 else 0
            for k in range(across * down):
                fh.seek(offs[base + k])
                put_block(_decode(fh.read(cnts[base + k]), comp), tw, th, (k % across) * tw, (k // across) * th, per)
        else:
            rps = int(_first(t, T_ROWS_PER_STRIP, h))
            offs, cnts = t[T_STRIP_OFFSETS], t[T_STRIP_COUNTS]
            nstrips = -(-h // rps)
            base = band * nstrips if planar == 2 else 0
            for k in range(nstrips):
                fh.seek(offs[base + k])
                put_block(_decode(fh.read(cnts[base + k]), comp), w, min(rps, h - k * rps), 0, k * rps, per)
    return {"width": w, "height": h, "rows": grid, "nodata": info["nodata"], "info": info}


def write_geotiff(path: str, rows: Sequence[Sequence[float]], *, affine: Sequence[float],
                  epsg: Optional[int], nodata: Optional[float] = None, rgb: bool = False,
                  pixel_is_point: bool = False) -> None:
    """The plainest GeoTIFF: one strip, uncompressed, little-endian; float32
    for a DEM, or 8-bit RGB (``rows`` of ``(r, g, b)``) for an image. ``affine``
    as :func:`read_geotiff_info` gives it (north-up: b = d = 0)."""
    h = len(rows)
    w = len(rows[0]) if h else 0
    x0, a, _b, y0, _d, e = affine
    if rgb:
        pix = b"".join(bytes([int(c) for c in px]) for row in rows for px in row)
        spp, bits, sfmt, photo = 3, [8, 8, 8], [1, 1, 1], 2
    else:
        pix = struct.pack("<" + "f" * (w * h), *[float(v) for row in rows for v in row])
        spp, bits, sfmt, photo = 1, [32], [3], 1
    projected = epsg is not None and not (4000 <= int(epsg) < 5000)
    keys = [1, 1, 0, 0]
    entries = [(1024, 0, 1, 1 if projected else 2), (1025, 0, 1, 2 if pixel_is_point else 1)]
    if epsg is not None:
        entries.append((3072 if projected else 2048, 0, 1, int(epsg)))
    keys[3] = len(entries)
    for en in entries:
        keys += list(en)
    tie_x, tie_y = (x0 + a / 2, y0 + e / 2) if pixel_is_point else (x0, y0)
    tags: List[Tuple[int, int, List[Any]]] = [
        (T_WIDTH, 4, [w]), (T_HEIGHT, 4, [h]), (T_BITS, 3, bits), (T_COMPRESSION, 3, [1]),
        (T_PHOTOMETRIC, 3, [photo]), (T_STRIP_OFFSETS, 4, [0]), (T_SPP, 3, [spp]),
        (T_ROWS_PER_STRIP, 4, [h]), (T_STRIP_COUNTS, 4, [len(pix)]), (T_PLANAR, 3, [1]),
        (T_SAMPLE_FORMAT, 3, sfmt), (T_PIXEL_SCALE, 12, [a, -e, 0.0]),
        (T_TIEPOINT, 12, [0.0, 0.0, 0.0, tie_x, tie_y, 0.0]), (T_GEOKEYS, 3, keys)]
    if nodata is not None:
        tags.append((T_NODATA, 2, [str(nodata)]))
    tags.sort()
    fmts = {2: "s", 3: "H", 4: "I", 12: "d"}
    ifd_off = 8
    ifd_len = 2 + 12 * len(tags) + 4
    extra = bytearray()
    extra_base = ifd_off + ifd_len
    entries_b = bytearray()
    payload_values = []
    for tag, typ, vals in tags:
        if typ == 2:
            data = (str(vals[0]) + "\x00").encode("latin-1")
            cnt = len(data)
        else:
            cnt = len(vals)
            data = struct.pack("<" + fmts[typ] * cnt, *vals)
        payload_values.append((tag, typ, cnt, data))

    for tag, typ, cnt, data in payload_values:
        if len(data) <= 4:
            entries_b += struct.pack("<HHI", tag, typ, cnt) + data.ljust(4, b"\x00")
        else:
            entries_b += struct.pack("<HHI", tag, typ, cnt) + struct.pack("<I", extra_base + len(extra))
            extra += data
            if len(extra) % 2:
                extra += b"\x00"
    pix_off = extra_base + len(extra)
    # patch the strip offset now that the pixels' place is known
    out = bytearray(b"II*\x00" + struct.pack("<I", ifd_off))
    ifd = bytearray(struct.pack("<H", len(tags)))
    k = 0
    for tag, typ, cnt, data in payload_values:
        e_ = bytearray(entries_b[k * 12:(k + 1) * 12])
        if tag == T_STRIP_OFFSETS:
            e_[8:12] = struct.pack("<I", pix_off)
        ifd += e_
        k += 1
    ifd += struct.pack("<I", 0)
    out += ifd + extra + pix
    with open(path, "wb") as fh:
        fh.write(bytes(out))
