# -*- coding: utf-8 -*-
"""``ascii_matrix`` — a matrix of numbers in a text file, one row per line.

The form the ERT of the Basilica Iulia ships in (``sezioni-2D/*.ASC``):
**no header**, values separated by spaces, LF; integers 0–255 (the colour
index of the report's figures, not Ω·m: the stack declares a ``value_scale``
for that, row G5); ``0`` on the border = nodata; a grid of its own for every
file (340–350 rows × 720–722 columns for the depth slices, so a stack cannot
assume one grid). Nothing in the file says where it is or how big: the extent
is DECLARED at import (92 × 50 m, from the report), the orientation too.

* a horizontal slice (:func:`read_ascii_matrix`) — by default the columns run
  along the first extent (``x``) and row 0 is the TOP of the picture, as in
  an image: the reader flips it so that row 0 = ``y_min``;
* a vertical section (:func:`read_ascii_section`, ``VERT-1-OK.ASC`` …) — the
  rows run ALONG the profile from its start, the columns DOWN from the
  surface (measured against the report's figures, p. 11): the reader turns it
  into ``x`` along the line and ``y`` = height above ground (``-depth``).

An ESRI ASCII grid (``ncols``/``nrows``/``xllcorner``/``cellsize``/
``NODATA_value``) is read too: then the header gives the extent, the corner
and the nodata, and a ``.prj`` beside gives the EPSG.
"""

from __future__ import annotations

import io
import os
import time

try:
    import numpy as np
except ImportError:  # pragma: no cover - Blender always ships numpy
    np = None

from ..grid import GridSpec, SliceData, SliceSpec

ASCII_EXT = (".asc",)

_ESRI_KEYS = ("ncols", "nrows", "xllcorner", "yllcorner", "xllcenter", "yllcenter",
              "cellsize", "dx", "dy", "nodata_value")


def _warn(code, en, it, **params):
    out = {"code": code, "en": en, "it": it}
    out.update(params)
    return out


def _read(path):
    """``(matrix float32 (rows, cols), esri header dict or None)``."""
    with open(path, "rb") as fh:
        raw = fh.read()
    head = {}
    lines = raw.split(b"\n")
    skip = 0
    for line in lines[:8]:
        parts = line.strip().split()
        if len(parts) == 2 and parts[0].decode("latin-1").lower() in _ESRI_KEYS:
            head[parts[0].decode("latin-1").lower()] = float(parts[1])
            skip += 1
        else:
            break
    body = b"\n".join(lines[skip:]).replace(b"\r", b"")
    try:
        m = np.loadtxt(io.BytesIO(body), dtype=np.float64, ndmin=2)
    except ValueError as exc:
        raise ValueError("%s is not a matrix of numbers (rows of different lengths?): %s"
                         % (os.path.basename(path), exc))
    return m.astype(np.float32), (head or None)


def _steps(n_x, n_y, extent, step):
    if extent is not None:
        return float(extent[0]) / n_x, float(extent[1]) / n_y, True
    if step is not None:
        if isinstance(step, (int, float)):
            return float(step), float(step), True
        return float(step[0]), float(step[1]), True
    return 1.0, 1.0, False


def _no_extent_warning(path, what_en, what_it):
    return _warn(
        "extent_not_declared",
        "%s says nothing about its size: %s 1 unit per cell until an extent is declared."
        % (os.path.basename(path), what_en),
        "%s non dice quanto è grande: %s 1 unità per cella finché non si dichiara l'estensione."
        % (os.path.basename(path), what_it), path=path)


def read_ascii_matrix(path, spec=None, extent=None, step=None, nodata=0.0, row0="top",
                      transpose=False):
    """Read a horizontal slice from a text matrix into a :class:`SliceData`.

    ``extent`` = ``(width, height)`` in metres of the whole matrix (the
    Basilica: ``(92, 50)``) or ``step`` = the cell size; neither → 1 unit per
    cell and a warning. ``transpose`` when the rows, not the columns, run
    along ``x``. ``row0`` — ``"top"`` (an image: the first line is the far
    side) or ``"bottom"``. ``nodata`` — the value that means «not surveyed»
    (``0`` in the Basilica files; ``None`` = none). Pixels need not be square.
    """
    if np is None:
        raise RuntimeError("numpy is required to read geophysical slices")
    t0 = time.time()
    if spec is None:
        spec = SliceSpec(path=path, depth_top=None, depth_bottom=None, kind="ascii_matrix")
    m, head = _read(path)
    warnings = []
    georef = None
    if head:
        if "nodata_value" in head:
            nodata = head["nodata_value"]
        ny, nx = m.shape
        cs = head.get("cellsize")
        sx, sy = (cs, cs) if cs else (head.get("dx", 1.0), head.get("dy", 1.0))
        if "xllcorner" in head:
            ox, oy = head["xllcorner"], head["yllcorner"]
        else:
            ox, oy = head.get("xllcenter", 0.0) - sx / 2, head.get("yllcenter", 0.0) - sy / 2
        from ..georef import epsg_from_prj, prj_file_for
        prj = prj_file_for(path)
        georef = {"origin_e": float(ox), "origin_n": float(oy), "rotation": 0.0,
                  "epsg": epsg_from_prj(prj) if prj else None,
                  "source": "ESRI ASCII header" + (" + " + os.path.basename(prj) if prj else ""),
                  "checks": {}}
        declared = True
        row0 = "top"                                     # ESRI grids run north to south
    else:
        if transpose:
            m = m.T
        ny, nx = m.shape
        sx, sy, declared = _steps(nx, ny, extent, step)
        if not declared:
            warnings.append(_no_extent_warning(path, "placed at", "collocata a"))
    amp = np.ascontiguousarray(m[::-1]) if row0 == "top" else m
    mask = np.isfinite(amp)
    if nodata is not None:
        mask &= amp != np.float32(nodata)
    amp = np.where(mask, amp, np.float32(-9999.0)).astype(np.float32)
    grid = GridSpec(nx=nx, ny=ny, x_min=0.5 * sx, y_min=0.5 * sy, x_step=sx, y_step=sy)
    info = {"rows": int(m.shape[0]), "cols": int(m.shape[1]), "nodata": nodata,
            "extent_declared": declared, "square_pixels": abs(sx - sy) <= 1e-9 * max(sx, sy),
            "valid_cells": int(mask.sum()), "header": head}
    return SliceData(spec=spec, grid=grid, amp=amp, mask=mask, read_seconds=time.time() - t0,
                     georef=georef, warnings=warnings, info=info)


def read_ascii_section(path, spec=None, length=None, depth=None, nodata=0.0, along="rows",
                       reverse=False, surface="start"):
    """Read a vertical section from a text matrix into a :class:`SliceData`.

    ``length`` (metres along the profile) and ``depth`` (metres below ground
    of the last cell) are declared: the Basilica's VERT2/3/4 are 92 × 9 m,
    VERT1/5/6 50 × 8 m. ``along`` — ``"rows"`` (the Basilica: one line per
    position along the profile) or ``"columns"``; ``reverse`` when the
    profile runs from its end; ``surface`` — ``"start"`` when the first
    cell of the depth axis is at ground level. The grid: ``x`` along the
    line from 0 to ``length``, ``y`` = height above ground from ``-depth`` to
    0 (row 0 the deepest, so a PNG has the surface on top).
    """
    if np is None:
        raise RuntimeError("numpy is required to read geophysical slices")
    t0 = time.time()
    m, _head = _read(path)
    rows, cols = m.shape
    if along == "rows":
        m = m.T                                   # now rows = depth, columns = along
    if reverse:
        m = m[:, ::-1]
    if surface == "start":
        m = m[::-1]                               # row 0 = the deepest
    ny, nx = m.shape
    warnings = []
    declared = length is not None and depth is not None
    sx = float(length) / nx if length is not None else 1.0
    sy = float(depth) / ny if depth is not None else 1.0
    if not declared:
        warnings.append(_warn(
            "section_not_declared",
            "%s: the length of the profile and its depth are not declared: 1 unit per cell."
            % os.path.basename(path),
            "%s: lunghezza del profilo e profondità non dichiarate: 1 unità per cella."
            % os.path.basename(path), path=path))
    if spec is None:
        spec = SliceSpec(path=path, depth_top=None, depth_bottom=None, kind="ascii_matrix",
                         orientation="vertical",
                         line=os.path.splitext(os.path.basename(path))[0])
    if declared:
        spec.depth_top, spec.depth_bottom = 0.0, ny * sy
    amp = np.ascontiguousarray(m)
    mask = np.isfinite(amp)
    if nodata is not None:
        mask &= amp != np.float32(nodata)
    amp = np.where(mask, amp, np.float32(-9999.0)).astype(np.float32)
    grid = GridSpec(nx=nx, ny=ny, x_min=0.5 * sx, y_min=-ny * sy + 0.5 * sy,
                    x_step=sx, y_step=sy)
    info = {"rows": int(rows), "cols": int(cols), "nodata": nodata, "extent_declared": declared, "length": nx * sx,
            "depth": ny * sy, "valid_cells": int(mask.sum())}
    return SliceData(spec=spec, grid=grid, amp=amp, mask=mask, read_seconds=time.time() - t0,
                     georef=None, warnings=warnings, info=info)
