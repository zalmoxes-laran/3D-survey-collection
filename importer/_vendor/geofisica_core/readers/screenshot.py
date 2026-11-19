# -*- coding: utf-8 -*-
"""``screenshot`` — a stack of screen captures of the GPR program, one per depth.

UA Ilici ``Sector1_Alcudia``: 601 JPEGs ``Slice_-1504mm.jpg`` (1918 × 878,
RGB), each the program's whole window — axes, legend «A (V)» 0–4, overlaid
text («Slice: n», «UTM: … / XYZ: …», «Picked Point …») — around a plot whose
box is THE SAME in every capture. So one **frame** declared once for the stack
turns pixels into metres:

* ``px = [left, top, right, bottom]`` — the pixels of the axis ticks at the
  ends of the two axes (Alcudia: columns 610 and 1303, rows 170 and 715);
* ``x_range``, ``y_range`` — the values written at those ticks (Alcudia:
  −50…25 m, −22…37 m), in the program's local frame;
* the origin of that frame in the world, declared too (the overlay says
  «UTM 701712.245; 4234859.678» at «XYZ −94.496; 35.597»: the local (0, 0)
  is 701806.741 E, 4234824.081 N, EPSG:25830, no rotation). Reading the
  overlay would need OCR: the person reads it once and declares it.

:func:`measure_frame` finds the ticks in a decoded capture (an
``(h, w, 3)`` array: the host decodes — Blender with its images, the bridge
with Pillow; the core has no JPEG decoder, and needs none to DESCRIBE the
stack: the captures are never rewritten). :func:`frame_grid` gives the grid
of the frame; :func:`crop_rgba` cuts the plot out of a capture with black (and
the two axis lines) as nodata — for the cache, when one is made (row G5).
:func:`compare_extent` holds the frame against a GeoTIFF of the same sector
(Ilici's ``Sector 1/mean_v2.tif``): the same ground, within half a metre.
"""

from __future__ import annotations

import os

try:
    import numpy as np
except ImportError:  # pragma: no cover - Blender always ships numpy
    np = None

from ..grid import GridSpec, SliceData

#: a pixel whose brightest channel is at most this is «not surveyed» (the
#: plot's black background; JPEG noise reaches 5 there)
BLACK = 10
#: the axes and ticks are drawn light grey to white
WHITE = 150
#: a tick is at least this long, perpendicular to its axis
TICK = 4


def _warn(code, en, it, **params):
    out = {"code": code, "en": en, "it": it}
    out.update(params)
    return out


def measure_frame(rgb, x_range=None, y_range=None, white=WHITE, tick=TICK):
    """Find the plot box of a capture by its axes and ticks.

    The x axis is the row with most light pixels, the y axis the column; a
    tick is a run of ``tick`` light pixels below the x axis (right of the
    y axis) or left of the y axis (above the x axis), where the axis itself is
    drawn (overlaid text beside the axis's line is not a tick). Returns
    ``{px: [left, top, right, bottom], x_ticks, y_ticks, image_size, x_range,
    y_range}`` (the ranges as given: the numbers at the ticks are text).
    Raises ``ValueError`` when no axes are found.
    """
    a = np.asarray(rgb)
    if a.ndim != 3 or a.shape[2] < 3:
        raise ValueError("a capture is an (h, w, 3) array")
    light = np.minimum(np.minimum(a[..., 0], a[..., 1]), a[..., 2]) > white
    h, w = light.shape
    row = int(np.argmax(light.sum(axis=1)))
    col = int(np.argmax(light.sum(axis=0)))
    if light[row].sum() < w // 10 or light[:, col].sum() < h // 10:
        raise ValueError("no plot axes found in the capture")
    below = light[row + 1:row + 1 + tick, :]
    x_ticks = [int(c) for c in np.where(below.all(axis=0) & light[row])[0] if c >= col] \
        if below.shape[0] == tick else []
    left = light[:, max(0, col - tick):col]
    y_ticks = [int(r) for r in np.where(left.all(axis=1) & light[:, col])[0] if r <= row] \
        if left.shape[1] == tick else []
    if len(x_ticks) < 2 or len(y_ticks) < 2:
        raise ValueError("the plot's ticks were not found (%d on x, %d on y)"
                         % (len(x_ticks), len(y_ticks)))
    return {"px": [x_ticks[0], y_ticks[0], x_ticks[-1], y_ticks[-1]],
            "x_ticks": x_ticks, "y_ticks": y_ticks, "image_size": [w, h],
            "x_range": list(x_range) if x_range else None,
            "y_range": list(y_range) if y_range else None}


def declare_frame(px, x_range, y_range, image_size=None):
    """A frame from numbers alone (the person's, or a measure kept)."""
    left, top, right, bottom = (int(v) for v in px)
    if right <= left or bottom <= top:
        raise ValueError("a frame is [left, top, right, bottom] with right > left, bottom > top")
    return {"px": [left, top, right, bottom], "x_range": [float(v) for v in x_range],
            "y_range": [float(v) for v in y_range],
            "image_size": list(image_size) if image_size else None}


def frame_grid(frame):
    """The grid of a frame in the program's local frame (metres): the pixel of
    the left tick is the centre of the first cell at ``x_range[0]``, the pixel
    of the bottom tick the centre of row 0 at ``y_range[0]``."""
    left, top, right, bottom = frame["px"]
    (x0, x1), (y0, y1) = frame["x_range"], frame["y_range"]
    sx = (x1 - x0) / float(right - left)
    sy = (y1 - y0) / float(bottom - top)
    return GridSpec(nx=right - left + 1, ny=bottom - top + 1, x_min=x0, y_min=y0,
                    x_step=sx, y_step=sy)


def same_frame(a, b, tol=0):
    """Whether two measured frames are the same box (``tol`` pixels)."""
    return all(abs(p - q) <= tol for p, q in zip(a["px"], b["px"]))


def crop_rgba(rgb, frame, black=BLACK, axes=True):
    """The plot of a capture as ``(ny, nx, 4)`` uint8 RGBA, row 0 = the TOP (an
    image, ready for a PNG); black (brightest channel ≤ ``black``) and, with
    ``axes``, the two axis lines (the left column, the bottom row) are alpha 0."""
    left, top, right, bottom = frame["px"]
    a = np.asarray(rgb)[top:bottom + 1, left:right + 1, :3]
    if a.shape[0] != bottom - top + 1 or a.shape[1] != right - left + 1:
        raise ValueError("the capture (%d × %d) is smaller than its frame"
                         % (np.asarray(rgb).shape[1], np.asarray(rgb).shape[0]))
    valid = a.max(axis=2) > black
    if axes:
        valid[:, 0] = False
        valid[-1, :] = False
    out = np.zeros(a.shape[:2] + (4,), dtype=np.uint8)
    out[..., :3] = a
    out[..., 3] = np.where(valid, 255, 0)
    return out


def read_screenshot_slice(spec, frame, rgb=None, black=BLACK, axes=True):
    """One capture as a :class:`SliceData`: ``amp`` = the brightness of the plot
    (0–1, the colour is not inverted to volts: D-4 of the plan), ``mask`` =
    not black, row 0 = ``y_min`` (south); the RGBA crop in ``info["rgba"]``.
    ``rgb`` — the capture decoded BY THE HOST (Blender with its images, the
    bridge with Pillow): the core has no image decoder, Pillow included."""
    if rgb is None:
        raise ValueError("%s: a capture must be decoded by the host and given as rgb"
                         % os.path.basename(spec.path))
    rgba = crop_rgba(rgb, frame, black, axes)
    flipped = rgba[::-1]
    mask = flipped[..., 3] > 0
    amp = np.where(mask, flipped[..., :3].max(axis=2) / np.float32(255.0),
                   np.float32(-9999.0)).astype(np.float32)
    return SliceData(spec=spec, grid=frame_grid(frame), amp=amp, mask=mask,
                     info={"rgba": rgba, "valid_cells": int(mask.sum()), "black": black})


def frame_extent(frame, origin=(0.0, 0.0)):
    """``[x_min, y_min, x_max, y_max]`` of the frame's box (cell edges), plus
    ``origin`` (the local (0, 0) in the world, doubles)."""
    g = frame_grid(frame)
    e, n = float(origin[0]), float(origin[1])
    return [e + g.x_min - g.x_step / 2, n + g.y_min - g.y_step / 2,
            e + g.x_min + (g.nx - 0.5) * g.x_step, n + g.y_min + (g.ny - 0.5) * g.y_step]


def compare_extent(frame, origin, geotiff, tol=0.5):
    """Hold a screenshot stack against a GeoTIFF of the same sector.

    The plot box is the program's choice of round axes around the survey;
    the GeoTIFF's raster is the survey's own box: each of its edges must lie
    within ``tol`` metres of the frame's (Alcudia against ``Sector
    1/mean_v2.tif``: 0.28, 0.46, 0.13 m inside on the west, south and east,
    0.15 m outside on the north). Returns ``{agrees, edges: [left, bottom,
    right, top] (metres inside; negative = outside), tol, geotiff, warning?}``."""
    from .geotiff import read_geotiff_slice
    d = read_geotiff_slice(geotiff)
    gr = d.georef or {}
    if gr.get("origin_e") is None:
        raise ValueError("%s is not georeferenced" % os.path.basename(geotiff))
    g = d.grid
    gx0 = gr["origin_e"] + g.x_min - g.x_step / 2
    gy0 = gr["origin_n"] + g.y_min - g.y_step / 2
    gx1, gy1 = gx0 + g.nx * g.x_step, gy0 + g.ny * g.y_step
    fx0, fy0, fx1, fy1 = frame_extent(frame, origin)
    edges = [round(gx0 - fx0, 3), round(gy0 - fy0, 3), round(fx1 - gx1, 3), round(fy1 - gy1, 3)]
    ok = all(-tol <= v <= tol for v in edges)
    out = {"agrees": ok, "edges": edges, "tol": tol, "geotiff": os.path.basename(geotiff)}
    if not ok:
        out["warning"] = _warn(
            "frame_off_geotiff",
            "The frame of the captures and %s differ by more than %.2f m on one edge (%s): "
            "check the declared axes and origin." % (out["geotiff"], tol, edges),
            "Il riquadro delle schermate e %s differiscono di più di %.2f m su un lato (%s): "
            "controllare gli assi e l'origine dichiarati." % (out["geotiff"], tol, edges))
    return out
