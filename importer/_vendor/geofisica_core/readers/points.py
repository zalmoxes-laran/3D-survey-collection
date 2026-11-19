# -*- coding: utf-8 -*-
"""Points in a text file, gridded: ``xyzv`` (a volume) and ``xyz_lines`` (a
section written as blocks ``line N``).

Two forms the ERT of the Basilica Iulia ships in besides its matrices:

* ``volumi-ert-specchiati/3D-*.ASC`` — four columns ``X Y Z V`` in E notation,
  CRLF, 0.5–0.7 M rows; ``X`` and ``Z`` are the row and column INDICES of the
  depth slices (0…348, 0…720), ``Y`` takes 2–3 values (the planes). They are
  derived products — the slices thresholded and extruded («specchiati»), 27–147
  levels — so a volume enters as a derived resource, never drawn as a volume
  (domain rule: a plane, not a volume): :func:`read_xyzv` returns one
  :class:`~geofisica_core.grid.SliceData` per distinct plane value, with no
  depth (the ``Y`` of the files does not agree with the slices' names: only
  the person can say what it is) — a product ``<stem>_<axis><value>``.
* ``VERT3-OK.XYZ`` — blocks headed ``line N``, then rows ``x y v``: ``x``
  along the profile (0…92 m), ``y`` the depth (0…9.89 m), ``v`` the value
  (``0`` = nodata). :func:`read_xyz_lines` makes the vertical section the
  matrix reader makes (``x`` along the line, ``y`` = height above ground,
  row 0 the deepest); ``orientation="horizontal"`` reads ``x y v`` blocks as a
  plan instead.

The coordinates are the cell CENTRES; a grid is rebuilt from the distinct
values of each axis (their median step), every point dropped into its cell;
a cell no point reaches is nodata, two points in one cell are counted
(``info.duplicates``: the last wins).
"""

from __future__ import annotations

import io
import os
import re
import time

try:
    import numpy as np
except ImportError:  # pragma: no cover - Blender always ships numpy
    np = None

from ..grid import GridSpec, SliceData, SliceSpec

XYZ_EXT = (".xyz",)
#: the columns of a volume file, in order (a file that orders them otherwise
#: says so with ``columns=``)
XYZV_COLUMNS = ("x", "y", "z", "v")

_RE_BLOCK = re.compile(rb"(?im)^[ \t]*line\b[^\n]*\n?")


def _warn(code, en, it, **params):
    out = {"code": code, "en": en, "it": it}
    out.update(params)
    return out


def _load(raw, path, ncols):
    try:
        m = np.loadtxt(io.BytesIO(raw.replace(b"\r", b"")), dtype=np.float64, ndmin=2)
    except ValueError as exc:
        raise ValueError("%s is not a table of numbers: %s" % (os.path.basename(path), exc))
    if m.shape[1] != ncols:
        raise ValueError("%s has %d columns, %d expected" % (os.path.basename(path), m.shape[1],
                                                             ncols))
    return m


def axis_of(values):
    """``(first, step, n)`` of the regular axis the distinct ``values`` sit on;
    ``step`` 1 for a single value.

    When no value is missing (every step within half of the mean one) the
    axis is the span over the count: values written to three decimals
    (``VERT3-OK.XYZ``: 0.093, 0.186 … 92.000 for a step of 0.09312) would
    otherwise drift into an empty column. With gaps, the median step."""
    u = np.unique(values)
    if u.size < 2:
        return float(u[0]) if u.size else 0.0, 1.0, max(1, int(u.size))
    d = np.diff(u)
    mean = float(u[-1] - u[0]) / (u.size - 1)
    if np.all(np.abs(d - mean) < 0.5 * mean):
        return float(u[0]), mean, int(u.size)
    step = float(np.median(d))
    n = int(round((u[-1] - u[0]) / step)) + 1
    return float(u[0]), step, n


def grid_points(px, py, pv, nodata=0.0, x_axis=None, y_axis=None):
    """Drop points ``(px, py) → pv`` into the grid of their distinct values.

    Returns ``(GridSpec, amp, mask, stats)``: row 0 = the smallest ``y``;
    ``stats`` — ``points``, ``duplicates``, ``empty_cells``. ``x_axis`` /
    ``y_axis`` = ``(first, step, n)`` to impose an axis (the planes of one
    volume share theirs)."""
    x0, sx, nx = x_axis or axis_of(px)
    y0, sy, ny = y_axis or axis_of(py)
    ix = np.rint((px - x0) / sx).astype(np.int64)
    iy = np.rint((py - y0) / sy).astype(np.int64)
    inside = (ix >= 0) & (ix < nx) & (iy >= 0) & (iy < ny)
    ix, iy, v = ix[inside], iy[inside], pv[inside]
    flat = iy * nx + ix
    amp = np.full(ny * nx, -9999.0, dtype=np.float32)
    hit = np.zeros(ny * nx, dtype=bool)
    amp[flat] = v.astype(np.float32)                  # numpy: the last write wins
    hit[flat] = True
    dup = int(flat.size - np.unique(flat).size)
    mask = hit & np.isfinite(amp)
    if nodata is not None:
        mask &= amp != np.float32(nodata)
    amp = np.where(mask, amp, np.float32(-9999.0)).astype(np.float32).reshape(ny, nx)
    grid = GridSpec(nx=nx, ny=ny, x_min=x0, y_min=y0, x_step=sx, y_step=sy)
    stats = {"points": int(pv.size), "outside": int((~inside).sum()), "duplicates": dup,
             "empty_cells": int(ny * nx - hit.sum())}
    return grid, amp, mask.reshape(ny, nx), stats


def xyzv_planes(path, plane="y", columns=XYZV_COLUMNS):
    """The distinct values of the ``plane`` column of a volume file (a scan:
    one spec per plane), read alone."""
    k = columns.index(plane)
    with open(path, "rb") as fh:
        raw = fh.read()
    col = np.loadtxt(io.BytesIO(raw.replace(b"\r", b"")), dtype=np.float64, usecols=(k,),
                     ndmin=1)
    return [float(v) for v in np.unique(col)]


def plane_product(path, plane, value):
    """The product name of one plane of a volume: ``3D-1_y45``."""
    stem = os.path.splitext(os.path.basename(path))[0]
    return "%s_%s%s" % (stem, plane, ("%g" % value).replace("-", "m"))


def read_xyzv(path, plane="y", x="x", y="z", columns=XYZV_COLUMNS, nodata=0.0, row0="bottom",
              only=None):
    """Read a volume of points ``X Y Z V`` as one horizontal plane per distinct
    value of the ``plane`` column; returns a list of :class:`SliceData`.

    ``x``/``y`` — the columns that run along the plane's ``x`` and ``y``;
    ``row0="top"`` when ``y`` grows DOWN, as a row index does (the Basilica's
    volumes: ``plane="y", x="z", y="x", row0="top"`` puts them the way its
    matrices are read). The planes of one file share one grid. ``only`` — a
    plane value: read that one alone. The coordinates are kept as the file
    gives them (indices, in the Basilica): the extent is declared later, as
    for a matrix.
    """
    if np is None:
        raise RuntimeError("numpy is required to read geophysical slices")
    t0 = time.time()
    with open(path, "rb") as fh:
        raw = fh.read()
    m = _load(raw, path, len(columns))
    kp, kx, ky, kv = (columns.index(c) for c in (plane, x, y, "v"))
    x_axis, y_axis = axis_of(m[:, kx]), axis_of(m[:, ky])
    values = np.unique(m[:, kp])
    if only is not None:
        values = values[np.isclose(values, float(only))]
        if not values.size:
            raise ValueError("%s has no plane %s = %g" % (os.path.basename(path), plane, only))
    out = []
    for val in values:
        sel = m[:, kp] == val
        grid, amp, mask, stats = grid_points(m[sel, kx], m[sel, ky], m[sel, kv], nodata,
                                             x_axis, y_axis)
        if row0 == "top":                              # y grew down: mirror to y up
            amp, mask = amp[::-1].copy(), mask[::-1].copy()
            grid = GridSpec(nx=grid.nx, ny=grid.ny, x_min=grid.x_min,
                            y_min=-(grid.y_min + (grid.ny - 1) * grid.y_step),
                            x_step=grid.x_step, y_step=grid.y_step)
        spec = SliceSpec(path=path, depth_top=None, depth_bottom=None, kind="xyzv",
                         product=plane_product(path, plane, val), plane=float(val))
        warnings = []
        if stats["duplicates"]:
            warnings.append(_warn(
                "points_in_one_cell",
                "%s, %s = %g: %d points fell into a cell already taken (the last one kept)."
                % (os.path.basename(path), plane, val, stats["duplicates"]),
                "%s, %s = %g: %d punti in una cella già occupata (tenuto l'ultimo)."
                % (os.path.basename(path), plane, val, stats["duplicates"]), path=path))
        info = dict(stats, plane_axis=plane, plane_value=float(val), columns=list(columns),
                    x=x, y=y, row0=row0, derived=True, valid_cells=int(mask.sum()))
        out.append(SliceData(spec=spec, grid=grid, amp=amp, mask=mask,
                             read_seconds=time.time() - t0, warnings=warnings, info=info))
    return out


def read_xyz_lines(path, spec=None, nodata=0.0, orientation="vertical"):
    """Read a file of blocks ``line N`` + rows ``x y v`` into one :class:`SliceData`.

    ``vertical`` (the Basilica's ``VERT3-OK.XYZ``): ``x`` along the profile,
    ``y`` the depth below ground, positive down → the grid of a section
    (``x`` along the line, ``y`` = −depth, row 0 the deepest), ``depth_top``/
    ``depth_bottom`` = the shallowest and deepest sample. ``horizontal``: the
    rows are ``x y v`` of a plan.
    """
    if np is None:
        raise RuntimeError("numpy is required to read geophysical slices")
    t0 = time.time()
    with open(path, "rb") as fh:
        raw = fh.read()
    blocks = len(_RE_BLOCK.findall(raw))
    m = _load(_RE_BLOCK.sub(b"", raw), path, 3)
    stem = os.path.splitext(os.path.basename(path))[0]
    if orientation == "vertical":
        depth = m[:, 1]
        grid, amp, mask, stats = grid_points(m[:, 0], -depth, m[:, 2], nodata)
        if spec is None:
            from . import line_from_name
            spec = SliceSpec(path=path, depth_top=None, depth_bottom=None, kind="xyz_lines",
                             orientation="vertical", line=line_from_name(path) or stem)
        spec.depth_top, spec.depth_bottom = float(depth.min()), float(depth.max())
    else:
        grid, amp, mask, stats = grid_points(m[:, 0], m[:, 1], m[:, 2], nodata)
        if spec is None:
            spec = SliceSpec(path=path, depth_top=None, depth_bottom=None, kind="xyz_lines",
                             product=stem)
    info = dict(stats, blocks=blocks, orientation=orientation, valid_cells=int(mask.sum()),
                length=grid.nx * grid.x_step)
    warnings = []
    if stats["duplicates"]:
        warnings.append(_warn(
            "points_in_one_cell",
            "%s: %d points fell into a cell already taken (the last one kept)."
            % (os.path.basename(path), stats["duplicates"]),
            "%s: %d punti in una cella già occupata (tenuto l'ultimo)."
            % (os.path.basename(path), stats["duplicates"]), path=path))
    return SliceData(spec=spec, grid=grid, amp=amp, mask=mask, read_seconds=time.time() - t0,
                     warnings=warnings, info=info)


def is_points_file(path, probe=4096):
    """Whether a text file is a table of 3–4 numbers a row (a volume or a set
    of lines) rather than a matrix: the first data row has 3 or 4 fields and
    the file has many more rows than that (a 4 × 4 matrix stays a matrix)."""
    with open(path, "rb") as fh:
        head = fh.read(probe)
    for line in head.splitlines():
        parts = line.split()
        if not parts or parts[0].lower() == b"line":
            continue
        try:
            [float(p) for p in parts]
        except ValueError:
            return False
        return len(parts) in (3, 4) and os.path.getsize(path) > 16 * (len(line) + 1)
    return False
