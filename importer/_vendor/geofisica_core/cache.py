# -*- coding: utf-8 -*-
"""The slice cache of ANY stack (row G5 of the geophysics plan).

:func:`build_stack_cache` reads every slice of a stack with its reader
(:func:`~geofisica_core.readers.read_slice`: CSV, GeoTIFF, ASCII matrix and
section, plane of a volume, ``line N`` section, screen capture), maps the
values to colours — the declared ``value_scale`` first, then a robust range,
then a ramp of the package (``.emc``) — and writes one PNG per slice plus a
manifest v2 into a cache folder of its own:

* the cache lives in ``plugins-data/geofisica/cache/<key>/`` (the plugin's
  own state, ``S3DGRAPHY_PLUGINS_DATA_DIR`` or ``~/.s3dgraphy/plugins-data``),
  ``<key>`` = a digest of the sources' bytes and of the parameters: the same
  data drawn the same way land in the same folder wherever they are read
  from; a folder under the stack's own folder is REFUSED (nothing is ever
  written beside the source: OneDrive is read only);
* the manifest keeps ``grid`` in the local frame and ``georef`` absolute
  (doubles, to the millimetre and beyond), per slice too — every file of the
  Basilica's ERT has a grid of its own;
* PNGs and manifest are deterministic: the same sources and parameters give
  the same bytes (the times of the build are returned, never written);
* every PNG and the manifest leave with ``<file>.stamp.json`` (G-5):
  ``format_conversion`` per PNG with the ramp, the range, the percentiles
  and the ``value_scale`` as parameters, ``from`` = the source file by
  digest plus the acquisition (a graph identity) when the caller names it.

3DSC's :func:`~geofisica_core.manifest.build_cache_steps` (CSV only, the old
layout) is untouched: the golden PNGs of the old core stay its.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import asdict

try:
    import numpy as np
except ImportError:  # pragma: no cover - Blender always ships numpy
    np = None

from . import stamp as _stamp
from .color import (COLORMAPS, DEFAULT_RAMP, apply_value_scale, check_value_scale,
                    ramp_mapping, robust_range, to_rgba8)
from .grid import Stack
from .identity import _token, document_id, stack_name
from .manifest import MANIFEST_NAME, MANIFEST_VERSION, _generator, _inside
from .png import write_png
from .readers import guess_kind, read_slice, same_values_warning, scan_stack, values_digest

#: the plugin whose state folder holds the cache
PLUGIN_ID = "geofisica"
DATA_ENV = "S3DGRAPHY_PLUGINS_DATA_DIR"
NORMALIZE = ("STACK", "SLICE", "FIXED")


class CacheError(ValueError):
    """What stops a cache, in EN and IT (it reaches the interface)."""

    def __init__(self, en, it):
        ValueError.__init__(self, en)
        self.en, self.it = en, it


def plugins_data_dir():
    """``plugins-data`` as ``s3dgraphy.em.plugins`` names it (the environment wins)."""
    env = os.environ.get(DATA_ENV)
    return os.path.expanduser(env) if env else os.path.join(
        os.path.expanduser("~"), ".s3dgraphy", "plugins-data")


def cache_root():
    """``plugins-data/geofisica/cache``."""
    return os.path.join(plugins_data_dir(), PLUGIN_ID, "cache")


def check_cache_dir(out_dir, folder):
    """Refuse a cache folder that lies under the stack's folder (or is it)."""
    if _inside(out_dir, folder):
        raise CacheError(
            "the cache folder %s lies under the stack's folder %s: refused (nothing is "
            "written beside the source)" % (out_dir, folder),
            "la cartella della cache %s sta dentro la cartella della pila %s: rifiutata "
            "(accanto alla sorgente non si scrive niente)" % (out_dir, folder))


def _jsonable(value):
    """Tuples to lists, numpy scalars to floats: what a manifest and a stamp hold."""
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if np is not None and isinstance(value, np.generic):
        return value.item()
    return value


def _colormap_name(colormap):
    if isinstance(colormap, dict):
        return colormap.get("name") or "emc"
    return str(colormap)


def _declared_for(declared, spec):
    if declared is None:
        return {}
    if callable(declared):
        return dict(declared(spec) or {})
    return dict(declared)


def cache_key(source_digests, parameters):
    """24 hex of a digest over the sources' digests (in order) and the parameters."""
    h = hashlib.sha256()
    h.update(json.dumps({"sources": list(source_digests), "parameters": _jsonable(parameters)},
                        sort_keys=True, ensure_ascii=True).encode("ascii"))
    return h.hexdigest()[:24]


def _georef_block(georef):
    """A slice's or a declared georef with the origin as doubles (or ``None``)."""
    if not georef:
        return None
    g = dict(georef)
    for k in ("origin_e", "origin_n", "rotation"):
        if g.get(k) is not None:
            g[k] = float(g[k])
    g.setdefault("rotation", 0.0)
    return _jsonable(g)


def _reusable(out_dir, key):
    path = os.path.join(out_dir, MANIFEST_NAME)
    if not os.path.isfile(path):
        return None
    try:
        with open(path, encoding="utf-8") as fh:
            m = json.load(fh)
    except (OSError, ValueError):
        return None
    if m.get("cache_key") != key:
        return None
    for e in m.get("slices") or []:
        png = os.path.join(out_dir, e.get("raster") or "")
        if not os.path.isfile(png) or _stamp.file_digest(png) != e.get("png_digest"):
            return None
        if m.get("stamped") and not os.path.isfile(_stamp.stamp_path(png)):
            return None
    return m


def build_stack_cache(folder, kind=None, out_dir=None, colormap=None, normalize="STACK",
                      clip_lo=2.0, clip_hi=98.0, value_range=None, value_scale=None,
                      declared=None, georef=None, decode=None, method="gpr", quantity=None,
                      unit=None, name=None, acquisition=None, limit=0, sample_cells=200000,
                      stamp=True, software=(), at=None, reuse=True, progress=None):
    """Read the stack in ``folder``, write its PNG cache and manifest; return the manifest.

    ``kind`` — the reader (:data:`~geofisica_core.readers.KINDS`; ``None`` =
    :func:`~geofisica_core.readers.guess_kind`). ``declared`` — what the
    files do not say (a dict for every slice, or ``f(spec) -> dict``: the
    Basilica's extent of the slices and length/depth of each section; a
    capture's ``frame``). ``georef`` — a declared placement
    ``{origin_e, origin_n, epsg, rotation, source}`` for files that say
    none (wins over the files'). ``decode(path) -> (h, w, 3)`` — the host's
    image decoder, required for captures (the core has none).

    Colour: ``value_scale`` (declared, :func:`~geofisica_core.color.check_value_scale`)
    first; then ``normalize`` — ``STACK`` (one robust range for every
    slice: comparable), ``SLICE`` (each its own: a folder mixing two
    quantities, Ilici's ``mean_v2``/``sqmean_v2``) or ``FIXED``
    (``value_range``, in the scaled unit: the report's whole colour bar);
    then ``colormap`` — a package ramp's name, an ``.emc`` dict, or an old
    :data:`~geofisica_core.color.COLORMAPS` name (``None`` = the method's
    default: hot for GPR, jet for ERT). A capture keeps its own colours.

    ``out_dir`` — ``None`` = ``plugins-data/geofisica/cache/<key>/``; under
    ``folder`` refused. ``acquisition`` — the graph identity (or a list) of
    the acquisition the files came from, cited by every stamp. ``reuse`` — a
    cache already there with the same key and intact PNGs is returned as it
    is (``reused`` true). ``at`` — the stamps' instant (tests).

    The returned manifest is the one written plus ``timing`` (seconds of
    reading, colouring, writing, stamping) and ``reused``: the file holds
    nothing that changes between two builds.
    """
    if np is None:
        raise CacheError("numpy is required to build a slice cache",
                         "per costruire la cache delle fette serve numpy")
    t_start = time.time()
    folder = os.fspath(folder)
    kind = kind or guess_kind(folder)
    if kind is None:
        raise CacheError("nothing in %s is a geophysical slice" % folder,
                         "in %s non c'è nessuna fetta geofisica" % folder)
    if normalize not in NORMALIZE:
        raise CacheError("normalize is one of %s, not %r" % (", ".join(NORMALIZE), normalize),
                         "normalize è uno tra %s, non %r" % (", ".join(NORMALIZE), normalize))
    if normalize == "FIXED" and not value_range:
        raise CacheError("a FIXED normalisation needs its value_range",
                         "una normalizzazione FIXED vuole il suo value_range")
    if kind == "image_stack":
        raise CacheError("pictures are drawn as they are: build_image_manifest describes them",
                         "le immagini si disegnano come sono: le descrive build_image_manifest")
    if kind == "screenshot" and decode is None:
        raise CacheError("screen captures are decoded by the host: give decode",
                         "le schermate le decodifica l'host: serve decode")
    vs = check_value_scale(value_scale)
    method = (method or "gpr").lower()
    if colormap is None:
        colormap = DEFAULT_RAMP.get(method, "grigio")
    if not (isinstance(colormap, str) and colormap in COLORMAPS):
        ramp_mapping(colormap)                         # an unknown ramp fails here, early
    scanned_kind, specs = scan_stack(folder, kind=kind)
    if not specs:
        raise CacheError("no slices of kind %s in %s" % (kind, folder),
                         "nessuna fetta di tipo %s in %s" % (kind, folder))
    if limit:
        specs = specs[:limit]
    stack = Stack(folder=folder, kind=kind, slices=specs, name=name or stack_name(folder),
                  method=method, quantity=quantity, unit=unit or (vs or {}).get("unit"),
                  value_scale=vs)

    digests = {}
    sources = [_stamp._digest(s.path, digests) for s in specs]
    decl = [_jsonable(_declared_for(declared, s)) for s in specs]
    parameters = {
        "kind": kind, "colormap": _colormap_name(colormap),
        "ramp": None if (isinstance(colormap, str) and colormap in COLORMAPS)
        else ramp_mapping(colormap),
        "normalize": normalize, "clip_percentiles": [float(clip_lo), float(clip_hi)],
        "value_range": [float(v) for v in value_range] if value_range else None,
        "value_scale": vs, "declared": decl, "georef": _georef_block(georef),
        "planes": [s.plane for s in specs], "method": method,
        "quantity": stack.quantity, "unit": stack.unit, "core": _generator()}
    key = cache_key(sources, parameters)
    out_dir = os.fspath(out_dir) if out_dir else os.path.join(cache_root(), key)
    check_cache_dir(out_dir, folder)
    if reuse:
        old = _reusable(out_dir, key)
        if old is not None:
            # the key holds the bytes, not the names: a file renamed or a stack
            # moved reuses the cache, and the manifest returned says where the
            # sources are NOW (the file on disk is not rewritten)
            old["source_folder"] = os.path.realpath(folder)
            for e, s in zip(old.get("slices") or [], specs):
                e["source"] = os.path.realpath(s.path)
            old["reused"] = True
            old["timing"] = {"total": round(time.time() - t_start, 3)}
            return old
    os.makedirs(out_dir, exist_ok=True)

    timing = {"read": 0.0, "color": 0.0, "png": 0.0, "stamp": 0.0}

    def _read(i, s):
        t0 = time.time()
        opts = _declared_for(declared, s)
        if s.kind == "screenshot":
            opts["rgb"] = decode(s.path)
        data = read_slice(s, **opts)
        timing["read"] += time.time() - t0
        return data

    def _values(data):
        return apply_value_scale(data.amp, data.mask, vs) if vs else data.amp

    # one robust range for the stack: every slice when few, five spread out
    # when many (a 3 GB CSV stack is not held in memory)
    vmin = vmax = None
    if normalize == "FIXED":
        vmin, vmax = float(value_range[0]), float(value_range[1])
    elif normalize == "STACK" and kind != "screenshot":
        pick = list(range(len(specs))) if len(specs) <= 16 else \
            sorted({int(round(i * (len(specs) - 1) / 4.0)) for i in range(5)})
        pool = []
        for i in pick:
            data = _read(i, specs[i])
            v = _values(data)[data.mask]
            if v.size > sample_cells:
                v = v[::max(1, v.size // sample_cells)]
            pool.append(np.asarray(v, dtype=np.float64))
            del data
        vmin, vmax = robust_range(np.concatenate(pool) if pool else None, clip_lo, clip_hi)
        del pool

    entries = []
    warnings = []
    seen = {}
    first_grid = first_georef = None
    for i, s in enumerate(specs):
        if progress:
            progress(i, len(specs), os.path.basename(s.path))
        data = _read(i, s)
        warnings += list(data.warnings or [])
        vd = values_digest(data)
        if vd in seen:
            warnings.append(same_values_warning(s.path, seen[vd]))
        else:
            seen[vd] = s.path
        t1 = time.time()
        if kind == "screenshot":
            rgba = data.info["rgba"][::-1]               # row 0 = y_min, as write_png wants
            lo, hi = 0.0, 1.0
        else:
            vals = _values(data)
            if normalize == "SLICE":
                lo, hi = robust_range(vals[data.mask], clip_lo, clip_hi)
            else:
                lo, hi = vmin, vmax
            rgba = to_rgba8(vals, data.mask, lo, hi, colormap)
        timing["color"] += time.time() - t1
        gid = document_id(folder, s, method)
        t2 = time.time()
        png = os.path.join(out_dir, "slice_%03d_%s.png" % (i, _token(s.label)))
        nbytes = write_png(png, rgba)
        timing["png"] += time.time() - t2
        png_digest = _stamp.file_digest(png)
        grid = asdict(data.grid)
        sgeoref = _georef_block(georef) or _georef_block(data.georef)
        if first_grid is None:
            first_grid, first_georef = grid, sgeoref
        stamped = None
        if stamp:
            t3 = time.time()
            inputs = [s.path] + _acquisitions(acquisition)
            _stamp.stamp_artifact(
                png, inputs=inputs, digests=digests, dtc_kind="format_conversion",
                technique="slice rasterization", software=software, label=gid, at=at,
                parameters=_jsonable({
                    "kind": kind, "colormap": parameters["colormap"], "ramp": parameters["ramp"],
                    "normalize": normalize, "clip_percentiles": [clip_lo, clip_hi],
                    "vmin": lo, "vmax": hi, "value_scale": vs, "declared": decl[i],
                    "method": method, "quantity": stack.quantity, "unit": stack.unit,
                    "orientation": s.orientation, "plane": s.plane}))
            stamped = os.path.basename(_stamp.stamp_path(png))
            timing["stamp"] += time.time() - t3
        entries.append(_jsonable({
            "index": i,
            "document_id": gid,
            "source": os.path.realpath(s.path),
            "raster": os.path.basename(png),
            "depth_top": s.depth_top,
            "depth_bottom": s.depth_bottom,
            "vmin": lo, "vmax": hi,
            "valid_cells": int(data.mask.sum()),
            "png_bytes": nbytes,
            "geo_id": gid,
            "orientation": s.orientation,
            "stamp": stamped,
            "line": s.line,
            "product": s.product,
            "plane": s.plane,
            "grid": grid,
            "georef": sgeoref,
            "source_digest": sources[i],
            "png_digest": png_digest,
        }))
        del data

    manifest = {
        "manifest_version": MANIFEST_VERSION,
        "generator": _generator(),
        "kind": kind,
        "georef": first_georef,
        "source_folder": os.path.realpath(folder),
        "colormap": parameters["colormap"],
        "ramp": parameters["ramp"],
        "normalize": "AS_IS" if kind == "screenshot" else normalize,
        "clip_percentiles": [float(clip_lo), float(clip_hi)],
        "value_range": parameters["value_range"],
        "grid": first_grid,
        "slices": entries,
        "stack": stack.describe(),
        "stamped": bool(stamp),
        "cache_key": key,
        "acquisition": _acquisitions(acquisition) or None,
        "warnings": _jsonable(warnings),
    }
    path = os.path.join(out_dir, MANIFEST_NAME)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    if stamp:
        t3 = time.time()
        _stamp.stamp_artifact(
            path, inputs=[s.path for s in specs] + _acquisitions(acquisition), digests=digests,
            dtc_kind="transformation", technique="slice stack manifest", software=software,
            label=stack.name, at=at,
            parameters=_jsonable(dict(parameters, slices=len(entries), cache_key=key)))
        timing["stamp"] += time.time() - t3
    timing = {k: round(v, 3) for k, v in timing.items()}
    timing["total"] = round(time.time() - t_start, 3)
    manifest["timing"] = timing
    manifest["reused"] = False
    return manifest


def _acquisitions(acquisition):
    if not acquisition:
        return []
    if isinstance(acquisition, dict):
        return [dict(acquisition)]
    if isinstance(acquisition, str):
        return [{"resource_id": acquisition, "kind": "acquisition"}]
    return [dict(a) if isinstance(a, dict) else {"resource_id": str(a), "kind": "acquisition"}
            for a in acquisition]


__all__ = ["CacheError", "DATA_ENV", "NORMALIZE", "PLUGIN_ID", "build_stack_cache", "cache_key",
           "cache_root", "check_cache_dir", "plugins_data_dir"]
