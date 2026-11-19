# -*- coding: utf-8 -*-
"""The cache of a stack and its manifest (``gpr_stack.json``).

**Manifest v2** (row G2) is v1 with more, never with less: every key the old
3DSC ``gpr_core`` wrote is still there with the same meaning (``grid`` in the
local frame, ``georef`` absolute, ``slices[].raster``/``document_id``…), so a
reader of v1 reads v2. Added:

* ``stack`` — ``name``, ``method``, ``quantity``, ``unit``, ``value_scale``;
* per slice ``geo_id`` (the identity, = ``document_id``), ``orientation``,
  ``stamp`` (the name of the PNG's stamp beside it, or ``None``);
* ``stamped`` — whether the core stamped what it wrote (the manifest itself
  gets ``gpr_stack.json.stamp.json``).

:func:`load_manifest` reads v1 too and returns it as v2 (``upgraded_from``);
:func:`as_v1` reduces a v2 to the old fields — what the golden test compares.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import asdict

try:
    import numpy as np
except ImportError:  # pragma: no cover - Blender always ships numpy
    np = None

from . import stamp as _stamp
from .color import percentile_range, to_rgba8
from .georef import detect_georeference, extent_from_world_file, prj_file_for, epsg_from_prj, world_file_for
from .grid import DEFAULT_QUANTITY, GridSpec, Stack
from .identity import document_id, stack_name
from .png import write_png
from .readers import (compare_extent, frame_grid, image_size, read_csv_slice, same_frame,
                      scan_stack)
from .readers.screenshot import BLACK

MANIFEST_NAME = "gpr_stack.json"
MANIFEST_VERSION = 2

#: the keys a v2 manifest adds to v1, at the top and per slice
V2_KEYS = ("stack", "stamped", "upgraded_from", "frame", "nodata", "checks",
           "warnings")
V2_SLICE_KEYS = ("geo_id", "orientation", "stamp")


def _generator():
    from . import __version__
    return "geofisica_core %s" % __version__


def open_stack(folder, kind="auto", method="gpr", quantity=None, unit=None, value_scale=None,
               name=None):
    """Scan ``folder`` into a :class:`Stack` (the slices sorted by depth)."""
    kind, specs = scan_stack(folder, kind=kind)
    return Stack(folder=folder, kind=kind, slices=specs, name=name or stack_name(folder),
                 method=method, quantity=quantity, unit=unit, value_scale=value_scale)


def _write_manifest(out_dir, manifest):
    path = os.path.join(out_dir, MANIFEST_NAME)
    with open(path, "w") as fh:
        json.dump(manifest, fh, indent=2)
    return path


def build_cache(folder, out_dir=None, colormap="GRAY", normalize="STACK",
                clip_lo=2.0, clip_hi=98.0, limit=0, progress=None,
                sample_cells=200000, **v2):
    """Blocking wrapper around :func:`build_cache_steps`."""
    it = build_cache_steps(folder, out_dir, colormap, normalize,
                           clip_lo, clip_hi, limit, sample_cells, **v2)
    manifest = None
    while True:
        try:
            i, n, name = next(it)
            if progress:
                progress(i, n, name)
        except StopIteration as stop:
            manifest = stop.value
            break
    return manifest


def build_cache_steps(folder, out_dir=None, colormap="GRAY", normalize="STACK",
                      clip_lo=2.0, clip_hi=98.0, limit=0,
                      sample_cells=200000, method="gpr", quantity=None, unit=None,
                      value_scale=None, stamp=True, software=()):
    """Convert a CSV slice stack to a cached PNG stack plus a manifest.

    ``normalize``
        ``STACK`` (default) uses one robust range for every slice, so slice to
        slice comparison is meaningful; ``SLICE`` stretches each slice to its
        own range, which shows faint deep anomalies but lies about relative
        amplitude.
    ``method``, ``quantity``, ``unit``, ``value_scale``
        What the stack measured (manifest v2 ``stack``); ``gpr`` by default.
    ``stamp``
        Write ``<png>.stamp.json`` beside every PNG and beside the manifest
        (G-5); ``software`` — the host's lines (``{"name", "version"}``),
        before the core's own.

    A generator: yields ``(i, n, name)`` per slice; returns the manifest dict,
    also written to ``gpr_stack.json`` next to the PNGs.
    """
    stack = open_stack(folder, kind="csv_grid", method=method, quantity=quantity, unit=unit,
                       value_scale=value_scale)
    specs = stack.slices
    if not specs:
        raise ValueError("no CSV slices found in %s" % folder)
    if limit:
        specs = specs[:limit]
    out_dir = out_dir or os.path.join(folder, "_3dsc_gpr_cache")
    os.makedirs(out_dir, exist_ok=True)

    t_start = time.time()
    grid = None
    vmin = vmax = None
    digests = {}

    if normalize == "STACK":
        # sample a few slices rather than holding the whole stack in RAM
        pick = specs if len(specs) <= 5 else [
            specs[int(round(i * (len(specs) - 1) / 4.0))] for i in range(5)]
        pool = []
        for s in pick:
            grid, amp, mask, _ = read_csv_slice(s.path, grid)
            v = amp[mask]
            if v.size > sample_cells:
                step = max(1, v.size // sample_cells)
                v = v[::step]
            pool.append(v.copy())
            del amp, mask
        allv = np.concatenate(pool)
        vmin, vmax = percentile_range(allv, clip_lo, clip_hi)
        del pool, allv

    entries = []
    t_parse = 0.0
    t_png = 0.0
    t_stamp = 0.0
    for i, s in enumerate(specs):
        yield i, len(specs), os.path.basename(s.path)
        grid, amp, mask, dt = read_csv_slice(s.path, grid)
        t_parse += dt
        if normalize != "STACK":
            v = amp[mask]
            vmin, vmax = percentile_range(v, clip_lo, clip_hi)
        t1 = time.time()
        png = os.path.join(out_dir, "slice_%03d_%s.png" % (i, s.label.replace(" ", "")))
        nbytes = write_png(png, to_rgba8(amp, mask, vmin, vmax, colormap))
        t_png += time.time() - t1
        gid = document_id(folder, s, method)
        stamped = None
        if stamp:
            t2 = time.time()
            _stamp.stamp_artifact(
                png, inputs=[s.path], digests=digests, dtc_kind="format_conversion",
                technique="slice rasterization", software=software, label=gid,
                parameters={"colormap": colormap, "normalize": normalize,
                            "clip_percentiles": [clip_lo, clip_hi], "vmin": vmin, "vmax": vmax,
                            "method": stack.method, "quantity": stack.quantity})
            stamped = os.path.basename(_stamp.stamp_path(png))
            t_stamp += time.time() - t2
        entries.append({
            "index": i,
            # One slice is one document (E.D., 2026-09-21), so every slice
            # needs an identity that survives a re-export and a rename of the
            # .blend. Depth is that identity: it is what the reading is OF.
            "document_id": gid,
            "source": os.path.relpath(s.path, out_dir),
            "raster": os.path.basename(png),
            "depth_top": s.depth_top,
            "depth_bottom": s.depth_bottom,
            "vmin": vmin, "vmax": vmax,
            "valid_cells": int(mask.sum()),
            "png_bytes": nbytes,
            "geo_id": gid,
            "orientation": s.orientation,
            "stamp": stamped,
        })
        del amp, mask

    manifest = {
        "manifest_version": MANIFEST_VERSION,
        "generator": _generator(),
        "kind": "csv_grid",
        "georef": detect_georeference(folder, kind="csv_grid"),
        "source_folder": folder,
        "colormap": colormap,
        "normalize": normalize,
        "clip_percentiles": [clip_lo, clip_hi],
        "grid": asdict(grid),
        "slices": entries,
        "build_seconds": round(time.time() - t_start, 2),
        "parse_seconds": round(t_parse, 2),
        "png_seconds": round(t_png, 2),
        "stack": stack.describe(),
        "stamped": bool(stamp),
    }
    if stamp:
        manifest["stamp_seconds"] = round(t_stamp, 2)
    path = _write_manifest(out_dir, manifest)
    if stamp:
        _stamp.stamp_artifact(
            path, inputs=[s.path for s in specs], digests=digests, dtc_kind="transformation",
            technique="slice stack manifest", software=software, label=stack.name,
            parameters={"kind": "csv_grid", "colormap": colormap, "normalize": normalize,
                        "clip_percentiles": [clip_lo, clip_hi], "method": stack.method,
                        "quantity": stack.quantity, "slices": len(entries)})
    return manifest


def build_image_manifest(folder, out_dir=None, x_min=0.0, y_min=0.0,
                         x_step=None, y_step=None, limit=0, method="gpr", quantity=None,
                         unit=None, value_scale=None, stamp=True, software=()):
    """Describe an already-rasterised slice stack without converting anything.

    Written for the UA Ilici ``GEORRADAR/`` sectors: ``Sector1_Alcudia`` holds
    601 depth slices as JPEGs at 5 mm steps, and the per-sector ``mean_v2.tif``
    ships an ESRI world file. Where a world file exists it wins; otherwise the
    caller supplies the cell size and the local origin.

    The manifest has the same shape as the one :func:`build_cache` writes, so
    the Blender side has exactly one code path for both kinds of stack. The
    images are not rewritten, so nothing but the manifest is stamped (its
    inputs: the images, by digest).
    """
    stack = open_stack(folder, kind="image_stack", method=method, quantity=quantity, unit=unit,
                       value_scale=value_scale)
    specs = stack.slices
    if not specs:
        raise ValueError("no image slices found in %s" % folder)
    if limit:
        specs = specs[:limit]
    out_dir = out_dir or folder
    os.makedirs(out_dir, exist_ok=True)

    nx, ny = image_size(specs[0].path)
    wf = world_file_for(specs[0].path)
    if wf:
        x_min, y_min, px, py = extent_from_world_file(wf, nx, ny)
        x_step, y_step = px, py
    if not x_step or not y_step:
        raise ValueError(
            "no world file beside %s — give the cell size explicitly"
            % os.path.basename(specs[0].path))

    def _ref(path):
        """Relative only when the raster really sits under the cache dir.

        A relpath that climbs out of /tmp is a trap on macOS, where /tmp is a
        symlink to /private/tmp and ``..`` resolves somewhere else entirely.
        """
        real_out = os.path.realpath(out_dir)
        real_p = os.path.realpath(path)
        if os.path.commonpath([real_out, real_p]) == real_out:
            return os.path.relpath(real_p, real_out)
        return real_p

    x_step = round(float(x_step), 6)
    y_step = round(float(y_step), 6)
    entries = []
    for i, s in enumerate(specs):
        gid = document_id(folder, s, method)
        entries.append({
            "index": i,
            "document_id": gid,
            "source": _ref(s.path),
            "raster": _ref(s.path),
            "depth_top": s.depth_top,
            "depth_bottom": s.depth_bottom,
            "vmin": 0.0, "vmax": 1.0,
            "valid_cells": nx * ny,
            "png_bytes": os.path.getsize(s.path),
            "geo_id": gid,
            "orientation": s.orientation,
            "stamp": None,
        })
    # The grid is ALWAYS the local frame, starting near zero; where the raster
    # lives in the world is a separate block. Keeping absolute eastings out of
    # the grid is what lets the Blender side treat both kinds of stack the
    # same way, and what keeps the shift logic in one place.
    georef = {"origin_e": None, "origin_n": None, "x_step": x_step,
              "y_step": y_step, "epsg": None,
              "source": os.path.basename(wf) if wf else "none"}
    if wf:
        georef["origin_e"], georef["origin_n"] = x_min, y_min
        x_min = y_min = 0.0
    prj = prj_file_for(specs[0].path)
    if prj:
        georef["epsg"] = epsg_from_prj(prj)
        georef["source"] = (georef["source"] + " + " +
                            os.path.basename(prj)).lstrip("none + ")

    manifest = {
        "manifest_version": MANIFEST_VERSION,
        "generator": _generator(),
        "kind": "image_stack",
        "source_folder": folder,
        "colormap": "AS_IS",
        "normalize": "AS_IS",
        "world_file": os.path.basename(wf) if wf else "",
        "georef": georef,
        "grid": asdict(GridSpec(nx=nx, ny=ny, x_min=x_min, y_min=y_min,
                                x_step=x_step, y_step=y_step)),
        "slices": entries,
        "stack": stack.describe(),
        "stamped": bool(stamp),
    }
    path = _write_manifest(out_dir, manifest)
    if stamp:
        _stamp.stamp_artifact(
            path, inputs=[s.path for s in specs], dtc_kind="transformation",
            technique="slice stack manifest", software=software, label=stack.name,
            parameters={"kind": "image_stack", "x_step": x_step, "y_step": y_step,
                        "georef_source": georef["source"], "epsg": georef["epsg"],
                        "method": stack.method, "quantity": stack.quantity, "slices": len(entries)})
    return manifest


def _inside(path, folder):
    real_f = os.path.realpath(folder)
    real_p = os.path.realpath(path)
    return os.path.commonpath([real_f, real_p]) == real_f


def build_screenshot_manifest(folder, out_dir, frame, origin=None, epsg=None, rotation=0.0,
                              black=BLACK, limit=0, method="gpr", quantity=None, unit=None,
                              value_scale=None, geotiff=None, measured=None, stamp=True,
                              software=()):
    """Describe a stack of screen captures (``screenshot``) without rewriting one.

    ``frame`` — the plot box, declared once for the stack
    (:func:`~geofisica_core.readers.screenshot.declare_frame` or
    :func:`~geofisica_core.readers.screenshot.measure_frame` with its
    ranges); ``origin`` — ``(E, N)`` of the program's local (0, 0), doubles,
    with its ``epsg`` and ``rotation`` (degrees, counter-clockwise): the
    person reads them in the overlay. ``geotiff`` — a GeoTIFF of the same
    sector: its extent is held against the frame (``checks.geotiff``).
    ``measured`` — frames measured on captures of the stack (by the host,
    which decodes): they must all be the frame (``checks.frames``).

    The manifest has the shape of the others: ``grid`` = the frame in the
    local frame, ``georef`` absolute; v2 adds ``frame`` (the crop in pixels
    the consumer textures with) and ``nodata`` (black ≤ ``black`` and the
    axis lines). Each slice's ``raster`` is the capture itself. ``out_dir``
    is required and must not lie under ``folder`` (the captures' folder is
    read only: OneDrive). The manifest is stamped: its inputs the captures
    by digest, its parameters the frame and the origin.
    """
    if not out_dir:
        raise ValueError("a screenshot stack needs a cache folder of its own")
    if _inside(out_dir, folder):
        raise ValueError("the cache folder %s lies under the captures' folder %s: refused "
                         "(nothing is written beside the source)" % (out_dir, folder))
    stack = open_stack(folder, kind="screenshot", method=method, quantity=quantity, unit=unit,
                       value_scale=value_scale)
    specs = stack.slices
    if not specs:
        raise ValueError("no captures found in %s" % folder)
    if limit:
        specs = specs[:limit]
    if not frame.get("x_range") or not frame.get("y_range"):
        raise ValueError("a frame needs the values at its ticks (x_range, y_range)")
    os.makedirs(out_dir, exist_ok=True)
    t0 = time.time()
    w, h = image_size(specs[0].path)
    if frame.get("image_size") and list(frame["image_size"]) != [w, h]:
        raise ValueError("the frame was measured on a %d × %d capture, %s is %d × %d"
                         % (frame["image_size"][0], frame["image_size"][1],
                            os.path.basename(specs[0].path), w, h))
    grid = frame_grid(frame)
    checks = {}
    warnings = []
    if measured:
        off = [i for i, m in enumerate(measured) if not same_frame(m, frame)]
        checks["frames"] = {"measured": len(measured), "same": len(measured) - len(off),
                            "off": off[:20]}
        if off:
            warnings.append({
                "code": "frame_differs",
                "en": "%d of %d captures do not have the declared plot box." % (len(off),
                                                                             len(measured)),
                "it": "%d schermate su %d non hanno il riquadro dichiarato." % (len(off),
                                                                             len(measured))})
    if geotiff:
        cmp = compare_extent(frame, origin or (0.0, 0.0), geotiff)
        if cmp.get("warning"):
            warnings.append(cmp.pop("warning"))
        checks["geotiff"] = cmp

    def _ref(path):
        return os.path.realpath(path)

    entries = []
    for i, s in enumerate(specs):
        gid = document_id(folder, s, method)
        entries.append({
            "index": i,
            "document_id": gid,
            "source": _ref(s.path),
            "raster": _ref(s.path),
            "depth_top": s.depth_top,
            "depth_bottom": s.depth_bottom,
            "vmin": 0.0, "vmax": 1.0,
            "valid_cells": None,                  # unknown until a capture is decoded
            "png_bytes": os.path.getsize(s.path),
            "geo_id": gid,
            "orientation": s.orientation,
            "stamp": None,
        })
    e, n = (None, None) if origin is None else (float(origin[0]), float(origin[1]))
    georef = {"origin_e": e, "origin_n": n, "x_step": grid.x_step, "y_step": grid.y_step,
              "epsg": epsg, "rotation": float(rotation),
              "source": "declared" if origin is not None else "none"}
    manifest = {
        "manifest_version": MANIFEST_VERSION,
        "generator": _generator(),
        "kind": "screenshot",
        "source_folder": folder,
        "colormap": "AS_IS",
        "normalize": "AS_IS",
        "world_file": "",
        "georef": georef,
        "grid": asdict(grid),
        "slices": entries,
        "stack": stack.describe(),
        "stamped": bool(stamp),
        "frame": {"px": list(frame["px"]), "x_range": list(frame["x_range"]),
                  "y_range": list(frame["y_range"]), "image_size": [w, h]},
        "nodata": {"black_at_most": black, "axes": True},
        "checks": checks,
        "warnings": warnings,
        "build_seconds": round(time.time() - t0, 2),
    }
    path = _write_manifest(out_dir, manifest)
    if stamp:
        t2 = time.time()
        _stamp.stamp_artifact(
            path, inputs=[s.path for s in specs], dtc_kind="transformation",
            technique="screenshot stack manifest", software=software, label=stack.name,
            parameters={"kind": "screenshot", "frame_px": list(frame["px"]),
                        "x_range": list(frame["x_range"]), "y_range": list(frame["y_range"]),
                        "origin": [e, n], "epsg": epsg, "rotation": float(rotation),
                        "black_at_most": black, "method": stack.method,
                        "quantity": stack.quantity, "slices": len(entries)})
        manifest["stamp_seconds"] = round(time.time() - t2, 2)
    return manifest


# --------------------------------------------------------------------------
# reading back, v1 and v2
# --------------------------------------------------------------------------

def upgrade_manifest(manifest):
    """A v1 manifest (the old 3DSC ``gpr_core``) as v2, in memory; a v2 as it is."""
    if not isinstance(manifest, dict) or manifest.get("manifest_version", 1) >= 2:
        return manifest
    m = dict(manifest)
    slices = []
    method = "gpr"
    for e in m.get("slices") or []:
        e = dict(e)
        gid = e.get("document_id")
        if gid and ":" in gid:
            method = gid.split(":", 1)[0]
        e.setdefault("geo_id", gid)
        e.setdefault("orientation", "horizontal")
        e.setdefault("stamp", None)
        slices.append(e)
    m["slices"] = slices
    folder = m.get("source_folder") or ""
    m["stack"] = {"name": stack_name(folder) if folder else None, "method": method,
                  "quantity": DEFAULT_QUANTITY.get(method), "unit": None, "value_scale": None}
    m["stamped"] = False
    m["upgraded_from"] = manifest.get("manifest_version", 1)
    m["manifest_version"] = MANIFEST_VERSION
    return m


def as_v1(manifest):
    """A v2 manifest reduced to the fields of v1 (the old core's, same order)."""
    m = {k: v for k, v in manifest.items() if k not in V2_KEYS and k != "stamp_seconds"}
    m["manifest_version"] = 1
    m["generator"] = "3DSC gpr_core"
    m["slices"] = [{k: v for k, v in e.items() if k not in V2_SLICE_KEYS}
                   for e in manifest.get("slices") or []]
    return m


def load_manifest(out_dir):
    """The manifest in ``out_dir`` as v2 (a v1 is upgraded), or ``None``."""
    p = os.path.join(out_dir, MANIFEST_NAME)
    if not os.path.isfile(p):
        return None
    with open(p) as fh:
        return upgrade_manifest(json.load(fh))
