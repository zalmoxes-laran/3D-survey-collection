# -*- coding: utf-8 -*-
"""``geotiff`` — one float (or 16-bit) GeoTIFF per slice, georeferenced by its tags.

The form of the UA Ilici GEORRADAR sectors: ``mean_v2.tif``/``sqmean_v2.tif``,
float32, one band, uncompressed, ``GDAL_NODATA = -3.4028235e38``, EPSG:25830
in the GeoKeys, a ``.tfw`` beside (pixel centre) and a tiepoint inside (pixel
corner): half a pixel apart, which is the same place.

The tags are read by ``_geotiff.py``, a byte-for-byte copy of s3dgraphy's
own reader (``s3dgraphy.gis.geotiff``; a test compares the digests): the core
never imports s3dgraphy, so Blender and 3DSC read the same way as EMStudio.
The pixels with numpy, straight from the strips, for the plain encodings
(none, Deflate), and through the copy's ``read_band`` for the others. No
GDAL, no Pillow.
"""

from __future__ import annotations

import math
import os
import time

try:
    import numpy as np
except ImportError:  # pragma: no cover - Blender always ships numpy
    np = None

from . import _geotiff as _gt

from ..grid import GridSpec, SliceData, SliceSpec

GEOTIFF_EXT = (".tif", ".tiff")

#: the largest int16: an amplitude that reaches it was clipped by the
#: instrument's export (UA Ilici sectors 5-1 and 7), not measured
SATURATION = 32767.0

#: beyond this a tiepoint and a world file are said to disagree (metres)
TFW_TOLERANCE = 1e-3


def _warn(code, en, it, **params):
    out = {"code": code, "en": en, "it": it}
    out.update(params)
    return out


def geotiff_info(path):
    """The tags of a GeoTIFF (``s3dgraphy.gis.geotiff.read_geotiff_info``)."""
    return _gt.read_geotiff_info(path)


def is_value_raster(path):
    """True for a GeoTIFF of values (one band, 16 bits or more, or float), the
    form a geophysical slice comes in — not an RGB picture of one."""
    try:
        return geotiff_info(path)["kind"] == "dem"
    except Exception:                                 # noqa: BLE001
        return False


def _pixels(path, info):
    """``(h, w)`` float32, row 0 = the TOP row as stored."""
    w, h = info["width"], info["height"]
    with open(path, "rb") as fh:
        end, ifds, _ = _gt._read_ifds(fh)
        t = ifds[0]
        bits, fmt = info["bits"], info["sample_format"]
        code = {(1, 8): "u1", (2, 8): "i1", (1, 16): "u2", (2, 16): "i2", (1, 32): "u4",
                (2, 32): "i4", (3, 32): "f4", (3, 64): "f8"}.get((fmt, bits))
        plain = (code and info["bands"] == 1 and info["compression"] in (1, 8, 32946)
                 and not info["tiled"]
                 and int(_gt._first(t, _gt.T_PREDICTOR, 1)) == 1)
        if plain:
            dt = np.dtype(end + code)
            rps = int(_gt._first(t, _gt.T_ROWS_PER_STRIP, h))
            offs, cnts = t[_gt.T_STRIP_OFFSETS], t[_gt.T_STRIP_COUNTS]
            parts = []
            for k in range(-(-h // rps)):
                fh.seek(offs[k])
                raw = _gt._decode(fh.read(cnts[k]), info["compression"])
                rows = min(rps, h - k * rps)
                parts.append(np.frombuffer(raw, dtype=dt, count=rows * w))
            return np.concatenate(parts).reshape(h, w).astype(np.float32)
    band = _gt.read_band(path)
    return np.asarray(band["rows"], dtype=np.float32)


def _tfw_check(path, affine, w, h):
    """Compare the world file beside the GeoTIFF (if any) with the tags.

    A world file names the CENTRE of the top-left pixel; the tags (tiepoint +
    scale, already turned into a corner affine) the corner. Same place → the
    offset is ~0. Exactly half a pixel off → the world file was written at
    the corner, a known mistake."""
    from ..georef import read_world_file, world_file_for
    wf = world_file_for(path)
    if not wf:
        return {"tfw": None}, []
    px, ry, rx, py, e0, n0 = read_world_file(wf)
    cx, cy = _gt.pixel_to_crs(affine, 0.5, 0.5)
    off = math.hypot(e0 - cx, n0 - cy)
    checks = {"tfw": os.path.basename(wf), "tfw_offset_m": round(off, 6),
              "tfw_agrees": off <= TFW_TOLERANCE}
    warns = []
    if off > TFW_TOLERANCE:
        half = 0.5 * math.hypot(px, py)
        hint_en = " (half a pixel: the world file names the corner, not the centre)" \
            if abs(off - half) <= TFW_TOLERANCE else ""
        hint_it = " (mezzo pixel: il world file nomina l'angolo, non il centro)" \
            if hint_en else ""
        warns.append(_warn(
            "tfw_disagrees",
            "%s and the GeoTIFF's own tags disagree by %.3f m%s; the tags are used."
            % (os.path.basename(wf), off, hint_en),
            "%s e i tag del GeoTIFF differiscono di %.3f m%s; si usano i tag."
            % (os.path.basename(wf), off, hint_it),
            path=path, offset_m=off))
    return checks, warns


def read_geotiff_slice(path, spec=None):
    """Read one GeoTIFF slice into a :class:`SliceData`.

    The grid is local (origin = the raster's lower-left corner, steps = the
    pixel size), ``georef`` carries the corner's absolute coordinates as
    doubles, the rotation, the EPSG and how the tags and the world file
    agree. Nodata (``GDAL_NODATA``, and anything not finite) is masked;
    cells at the int16 ceiling (32767) are counted and reported.
    """
    if np is None:
        raise RuntimeError("numpy is required to read geophysical slices")
    t0 = time.time()
    if spec is None:
        spec = SliceSpec(path=path, depth_top=None, depth_bottom=None, kind="geotiff",
                         product=os.path.splitext(os.path.basename(path))[0])
    info = geotiff_info(path)
    w, h = info["width"], info["height"]
    top = _pixels(path, info)
    amp = np.ascontiguousarray(top[::-1])                 # row 0 = y_min
    mask = np.isfinite(amp)
    nodata = info.get("nodata")
    if nodata is not None:
        mask &= amp != np.float32(nodata)
    warnings = []
    georef = None
    x_step = y_step = 1.0
    aff = info.get("affine")
    if aff:
        x0, a, b, y0, d, e = aff
        x_step, y_step = math.hypot(a, d), math.hypot(b, e)
        ox, oy = _gt.pixel_to_crs(aff, 0.0, float(h))     # the lower-left corner
        crs = info.get("crs")
        checks, tw = _tfw_check(path, aff, w, h)
        warnings += tw
        georef = {"origin_e": float(ox), "origin_n": float(oy),
                  "rotation": math.degrees(math.atan2(d, a)),
                  "epsg": int(crs.split(":")[1]) if crs and crs.startswith("EPSG:") else None,
                  "source": info.get("georef_source"), "checks": checks}
    else:
        warnings.append(_warn(
            "no_georeference",
            "%s says nothing about where it is: placed in a local frame, 1 unit per pixel."
            % os.path.basename(path),
            "%s non dice dove si trova: collocato in un frame locale, 1 unità per pixel."
            % os.path.basename(path), path=path))
    grid = GridSpec(nx=w, ny=h, x_min=0.5 * x_step, y_min=0.5 * y_step,
                    x_step=x_step, y_step=y_step)
    saturated = int(np.count_nonzero(mask & (amp == np.float32(SATURATION))))
    if saturated:
        share = saturated / float(max(1, int(mask.sum())))
        warnings.append(_warn(
            "saturated",
            "%s: %d cells (%.2f %%) at %d, the int16 ceiling: clipped by the export, not measured."
            % (os.path.basename(path), saturated, 100 * share, int(SATURATION)),
            "%s: %d celle (%.2f %%) a %d, il tetto di int16: tagliate dall'esportazione, non misurate."
            % (os.path.basename(path), saturated, 100 * share, int(SATURATION)),
            path=path, value=SATURATION, cells=saturated, share=share))
    amp = np.where(mask, amp, np.float32(-9999.0)).astype(np.float32)
    meta = {"bits": info["bits"], "sample_format": info["sample_format"],
            "compression": info["compression"], "nodata": nodata, "saturated": saturated,
            "valid_cells": int(mask.sum())}
    return SliceData(spec=spec, grid=grid, amp=amp, mask=mask, read_seconds=time.time() - t0,
                     georef=georef, warnings=warnings, info=meta)
