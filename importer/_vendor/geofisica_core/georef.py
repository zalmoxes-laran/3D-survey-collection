# -*- coding: utf-8 -*-
"""Where a stack is: world files, ``.prj``, and the shift proposal.

Georeferencing is a separate, explicit step:
``local -> rotate(theta) -> + (origin_e, origin_n) -> - (general shift value)``.
Nothing here writes into a scene or a graph.
"""

from __future__ import annotations

import math
import os
import re

from .depth import read_csv_header
from .readers import image_size, scan_stack


# --------------------------------------------------------------------------
# world files (Ilici .tfw and friends)
# --------------------------------------------------------------------------

def read_world_file(path):
    """Read an ESRI world file. Returns ``(px, rot_y, rot_x, py, e0, n0)``."""
    with open(path) as fh:
        vals = [float(x.strip()) for x in fh if x.strip()]
    if len(vals) < 6:
        raise ValueError("%s is not a world file" % path)
    return tuple(vals[:6])


def world_file_for(image_path):
    stem, ext = os.path.splitext(image_path)
    ext = ext.lower()
    cands = {".tif": ".tfw", ".tiff": ".tfw", ".png": ".pgw", ".jpg": ".jgw",
             ".jpeg": ".jgw"}
    for w in (cands.get(ext, ""), ext + "w", ".wld"):
        if w and os.path.isfile(stem + w):
            return stem + w
    return None


def extent_from_world_file(wf, nx, ny):
    """Return ``(x_min, y_min, x_step, y_step)`` of the pixel-centre grid."""
    px, _ry, _rx, py, e0, n0 = read_world_file(wf)
    # e0/n0 are the centre of the top-left pixel; py is normally negative.
    x_min = e0
    y_min = n0 + py * (ny - 1)
    return x_min, y_min, abs(px), abs(py)


# --------------------------------------------------------------------------
# CRS detection
# --------------------------------------------------------------------------

_RE_EPSG_AUTH = re.compile(r'AUTHORITY\s*\[\s*"EPSG"\s*,\s*"?(\d+)"?\s*\]', re.I)
_RE_EPSG_ID = re.compile(r'ID\s*\[\s*"EPSG"\s*,\s*(\d+)\s*\]', re.I)


def prj_file_for(path):
    """Find the ESRI ``.prj`` sitting beside a raster, if any."""
    stem = os.path.splitext(path)[0]
    for cand in (stem + ".prj", stem + ".PRJ"):
        if os.path.isfile(cand):
            return cand
    return None


def epsg_from_prj(path):
    """Read the EPSG code out of a ``.prj``.

    pyproj is optional (bundled with 3DSC, lazy and missing on one build), so
    the fallback reads the AUTHORITY clause straight out of the WKT.
    """
    try:
        with open(path) as fh:
            wkt = fh.read()
    except OSError:
        return None
    try:
        from pyproj import CRS
        code = CRS.from_wkt(wkt).to_epsg()
        if code:
            return int(code)
    except Exception:                                # noqa: BLE001
        pass
    for rx in (_RE_EPSG_ID, _RE_EPSG_AUTH):
        hits = rx.findall(wkt)
        if hits:
            return int(hits[-1])                     # outermost authority last
    return None


def detect_georeference(folder, kind="auto"):
    """What the files themselves say about where they are.

    Returns ``origin_e``, ``origin_n``, ``x_step``, ``y_step``, ``epsg`` and
    ``source``, any of which may be ``None``. A CSV grid starting at 0,0
    (CS07 Tivoli) yields no origin: those files carry no georeference at all
    and the operator has to be told. A raster with a world file (UA Ilici)
    yields one, and a ``.prj`` beside it yields the EPSG too.
    """
    out = {"origin_e": None, "origin_n": None, "x_step": None, "y_step": None,
           "epsg": None, "source": "none"}
    try:
        kind, specs = scan_stack(folder, kind=kind)
    except OSError:
        return out
    if not specs:
        return out
    first = specs[0].path

    if kind == "geotiff":
        from .readers.geotiff import _gt, geotiff_info
        info = geotiff_info(first)
        aff = info.get("affine")
        if aff:
            # the old convention: the CENTRE of the lower-left pixel
            e, n = _gt.pixel_to_crs(aff, 0.5, info["height"] - 0.5)
            out.update(origin_e=float(e), origin_n=float(n), x_step=math.hypot(aff[1], aff[4]),
                       y_step=math.hypot(aff[2], aff[5]),
                       source=os.path.basename(first) + " (" + str(info["georef_source"]) + ")")
        crs = info.get("crs")
        if crs and crs.startswith("EPSG:"):
            out["epsg"] = int(crs.split(":")[1])
            return out
    elif kind == "image_stack":
        wf = world_file_for(first)
        if wf:
            nx, ny = image_size(first)
            x_min, y_min, px, py = extent_from_world_file(wf, nx, ny)
            out.update(origin_e=x_min, origin_n=y_min, x_step=px, y_step=py,
                       source=os.path.basename(wf))
    elif kind == "csv_grid":
        hdr = read_csv_header(first)
        out["x_step"] = hdr.get("x_step")
        out["y_step"] = hdr.get("y_step")
        # a CSV grid may still ship a sidecar world file for the whole folder
        for n in sorted(os.listdir(folder)):
            if n.lower().endswith((".tfw", ".pgw", ".jgw", ".wld")):
                px, _ry, _rx, py, e0, n0 = read_world_file(
                    os.path.join(folder, n))
                out.update(origin_e=e0, origin_n=n0, source=n)
                break

    prj = prj_file_for(first)
    if prj is None:
        for n in sorted(os.listdir(folder)):
            if n.lower().endswith(".prj"):
                prj = os.path.join(folder, n)
                break
    if prj:
        out["epsg"] = epsg_from_prj(prj)
        if out["source"] == "none":
            out["source"] = os.path.basename(prj)
        else:
            out["source"] += " + " + os.path.basename(prj)
    return out


# --------------------------------------------------------------------------
# shift
# --------------------------------------------------------------------------

#: Beyond this distance from the origin, coordinates are projected/absolute
#: rather than local. A survey grid is tens of metres across; a UTM easting is
#: six or seven digits. Blender's single-precision object transforms start
#: visibly jittering a few kilometres out, which is the whole reason 3DSC has
#: a General Shift Value in the first place.
ABSOLUTE_COORD_THRESHOLD = 10000.0


def is_absolute(e, n):
    return (abs(e or 0.0) > ABSOLUTE_COORD_THRESHOLD or
            abs(n or 0.0) > ABSOLUTE_COORD_THRESHOLD)


def propose_shift(e, n, round_to=10.0):
    """A round number just below the dataset origin.

    Rounding down rather than taking the origin itself keeps the shift a
    memorable figure that can be typed into another project by hand, and
    leaves the data at small positive coordinates.
    """
    if not round_to:
        return float(e or 0.0), float(n or 0.0)
    return (math.floor((e or 0.0) / round_to) * round_to,
            math.floor((n or 0.0) / round_to) * round_to)
