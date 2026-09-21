# -*- coding: utf-8 -*-
"""GPR (ground penetrating radar) depth-slice stacks: readers and raster cache.

This module is deliberately **free of ``bpy``** so that it can be unit-tested
and benchmarked outside Blender. Everything that touches the scene lives in
``import_gpr.py``.

Supported inputs
----------------
``csv_grid``
    One CSV per depth slice, a *complete regular grid* in raster order, with
    the header line carrying the cell size and the slice depth, e.g.::

        X ± 0.0500m, Y ± 0.0500m, Z ± 1.9000m, Depth ± 1.9000m, Amplitude
        0.0000, 0.0000, -1.9000, 1.9000,
        0.0500, 0.0000, -1.9000, 1.9000, 20.489

    Cells outside the surveyed polygon carry an **empty** amplitude field;
    they become the no-data mask (alpha 0 in the cached raster). Measured on
    the CS07 CSIC-Tivoli sample: 1492 x 1474 cells per slice, 40% no-data.

``image_stack``
    One image per depth slice, depth encoded in the file name
    (``Slice_-2889mm.jpg``, ``slice_0.100 - 0.200m.png`` ...), optionally with
    an ESRI world file (``.tfw``/``.pgw``/``.jgw``) for the extent. This is the
    form the UA Ilici GEORRADAR sectors already ship in — and also the form
    this module *writes* when it caches a ``csv_grid`` stack, so the two paths
    converge on a single representation.

Coordinates
-----------
A slice is described by a :class:`GridSpec` in the **local** survey frame
(the CSVs start at 0,0). Georeferencing is a separate, explicit step:
``local -> rotate(theta) -> + (origin_e, origin_n) -> - (general shift value)``.
Nothing here writes into a scene; see ``import_gpr.py``.
"""

from __future__ import annotations

import io
import json
import math
import os
import re
import struct
import time
import zlib
from dataclasses import dataclass, field, asdict

try:
    import numpy as np
except ImportError:  # pragma: no cover - Blender always ships numpy
    np = None

NODATA = -9999.0
"""Sentinel substituted for empty amplitude fields before numeric parsing."""

MANIFEST_NAME = "gpr_stack.json"
MANIFEST_VERSION = 1

CSV_EXT = (".csv",)
IMG_EXT = (".png", ".jpg", ".jpeg", ".tif", ".tiff")


# --------------------------------------------------------------------------
# descriptors
# --------------------------------------------------------------------------

@dataclass
class GridSpec:
    """Regular 2D grid in the local survey frame (metres)."""
    nx: int
    ny: int
    x_min: float
    y_min: float
    x_step: float
    y_step: float

    @property
    def x_max(self):
        return self.x_min + (self.nx - 1) * self.x_step

    @property
    def y_max(self):
        return self.y_min + (self.ny - 1) * self.y_step

    @property
    def width(self):
        """Extent of the textured quad: cell centres plus half a cell each side."""
        return self.nx * self.x_step

    @property
    def height(self):
        return self.ny * self.y_step

    def matches(self, other, tol=1e-6):
        return (self.nx == other.nx and self.ny == other.ny
                and abs(self.x_min - other.x_min) < tol
                and abs(self.y_min - other.y_min) < tol
                and abs(self.x_step - other.x_step) < tol
                and abs(self.y_step - other.y_step) < tol)


@dataclass
class SliceSpec:
    """One depth slice, before its raster is read."""
    path: str
    depth_top: float
    depth_bottom: float
    kind: str = "csv_grid"          # csv_grid | image_stack

    @property
    def depth_mid(self):
        return 0.5 * (self.depth_top + self.depth_bottom)

    @property
    def thickness(self):
        return abs(self.depth_bottom - self.depth_top)

    @property
    def label(self):
        return "%.3f-%.3fm" % (self.depth_top, self.depth_bottom)


def document_id(folder, spec):
    """Stable identity of one slice AS A DOCUMENT.

    A single slice is a document; reading several of them produces extractions
    that combine into one proxy (E.D., 2026-09-21). So the identity has to be
    per slice, and has to be the depth band rather than the file name, which
    changes when the geophysicist re-exports the stack.
    """
    stack = os.path.basename(os.path.normpath(folder)) or "gpr"
    return "gpr:%s#d%.3f-%.3fm" % (stack, spec.depth_top, spec.depth_bottom)


@dataclass
class SliceData:
    """A slice with its raster loaded."""
    spec: SliceSpec
    grid: GridSpec
    amp: "np.ndarray"       # (ny, nx) float32, NODATA where unsurveyed
    mask: "np.ndarray"      # (ny, nx) bool, True = valid
    read_seconds: float = 0.0


# --------------------------------------------------------------------------
# depth parsing
# --------------------------------------------------------------------------

_RE_RANGE_M = re.compile(
    r"([-+]?\d+(?:[.,]\d+)?)\s*(?:-|to|_)\s*([-+]?\d+(?:[.,]\d+)?)\s*m", re.I)
_RE_SINGLE_MM = re.compile(r"([-+]?\d+(?:[.,]\d+)?)\s*mm", re.I)
_RE_SINGLE_M = re.compile(r"([-+]?\d+(?:[.,]\d+)?)\s*m\b", re.I)
_RE_HEADER_FIELD = re.compile(
    r"([A-Za-z]+)\s*(?:\xb1|±|\+/-|\+-)?\s*([-+]?\d+(?:\.\d+)?)\s*m?", re.I)


def depth_from_name(name):
    """Return ``(top, bottom)`` in metres, positive downwards, or ``None``.

    Handles ``slice_0.100 - 0.200m.CSV`` (a range) and ``Slice_-2889mm.jpg``
    (a single signed depth in millimetres, as UA Ilici writes them).
    """
    stem = os.path.splitext(os.path.basename(name))[0]
    m = _RE_RANGE_M.search(stem)
    if m:
        a = float(m.group(1).replace(",", "."))
        b = float(m.group(2).replace(",", "."))
        return (min(abs(a), abs(b)), max(abs(a), abs(b)))
    m = _RE_SINGLE_MM.search(stem)
    if m:
        d = abs(float(m.group(1).replace(",", "."))) / 1000.0
        return (d, d)
    m = _RE_SINGLE_M.search(stem)
    if m:
        d = abs(float(m.group(1).replace(",", ".")))
        return (d, d)
    return None


def parse_csv_header(line):
    """Parse ``X ± 0.0500m, Y ± 0.0500m, Z ± 1.9000m, Depth ± 1.9000m, Amplitude``.

    Returns a dict with whichever of ``x_step``, ``y_step``, ``z``, ``depth``
    could be read. The ``±`` is latin-1 (0xB1) in the CS07 sample, so the
    caller decodes with ``latin-1``.
    """
    out = {}
    for part in line.split(","):
        m = _RE_HEADER_FIELD.search(part.strip())
        if not m:
            continue
        key, val = m.group(1).lower(), float(m.group(2))
        if key == "x":
            out["x_step"] = val
        elif key == "y":
            out["y_step"] = val
        elif key == "z":
            out["z"] = val
        elif key == "depth":
            out["depth"] = val
    return out


def read_csv_header(path):
    with open(path, "rb") as fh:
        first = fh.readline()
    return parse_csv_header(first.decode("latin-1", "replace"))


# --------------------------------------------------------------------------
# stack scanning
# --------------------------------------------------------------------------

def scan_stack(folder, kind="auto"):
    """Return ``(kind, [SliceSpec, ...])`` sorted by depth.

    Depth comes from the file name; for CSVs it falls back to the header's
    ``Depth`` field, and finally to the file's index in the sorted listing
    (thickness 0), so a badly named stack still imports in the right order.
    """
    names = sorted(os.listdir(folder))
    csvs = [n for n in names if n.lower().endswith(CSV_EXT)]
    imgs = [n for n in names if n.lower().endswith(IMG_EXT)]
    if kind == "auto":
        kind = "csv_grid" if len(csvs) >= len(imgs) and csvs else "image_stack"
    picked = csvs if kind == "csv_grid" else imgs
    if not picked:
        return kind, []

    specs = []
    for i, n in enumerate(picked):
        p = os.path.join(folder, n)
        rng = depth_from_name(n)
        if rng is None and kind == "csv_grid":
            hdr = read_csv_header(p)
            if "depth" in hdr:
                d = abs(hdr["depth"])
                rng = (d, d)
        if rng is None:
            rng = (float(i), float(i))
        specs.append(SliceSpec(path=p, depth_top=rng[0], depth_bottom=rng[1],
                               kind=kind))
    specs.sort(key=lambda s: (s.depth_mid, s.path))

    # single-depth stacks (Ilici style): derive thickness from the neighbour
    if len(specs) > 1 and all(s.thickness == 0 for s in specs):
        step = abs(specs[1].depth_mid - specs[0].depth_mid)
        for s in specs:
            mid = s.depth_mid           # read before mutating either bound
            s.depth_top = max(0.0, mid - step / 2.0)
            s.depth_bottom = mid + step / 2.0
    return kind, specs


# --------------------------------------------------------------------------
# CSV grid reader
# --------------------------------------------------------------------------

_SENT = (",%d\n" % int(NODATA)).encode("ascii")


def repair_chunk(chunk):
    """Strip CR and fill empty trailing amplitude fields with the sentinel."""
    chunk = chunk.replace(b"\r", b"")
    return chunk.replace(b", \n", _SENT).replace(b",\n", _SENT)


class RepairedReader(io.RawIOBase):
    """A read-only stream that repairs the CSV body on the fly.

    Slurping an 87 MB slice and then running three ``bytes.replace`` passes
    over it costs ~350 MB of transient buffers per slice, on top of whatever
    ``loadtxt`` allocates — measured at ~780 MB above Blender's baseline,
    which is a lot to ask of a machine that is also holding a photogrammetric
    model. Repairing 4 MB at a time keeps that under control at no cost in
    parse time.

    The only tricky part is a chunk boundary landing inside ``", \n"``: the
    last two bytes of each raw chunk are carried over to the next one.
    """

    def __init__(self, fh, chunk=1 << 22, skip_header=True):
        self._fh = fh
        self._chunk = chunk
        self._carry = b""       # raw bytes held back from the previous chunk
        self._out = b""         # repaired bytes not yet handed to the caller
        self._pos = 0
        self._eof = False
        if skip_header:
            self._fh.readline()

    def readable(self):
        return True

    def _fill(self, want):
        """Repair whole lines only: the carry holds the raw partial last line."""
        while not self._eof and len(self._out) - self._pos < want:
            raw = self._fh.read(self._chunk)
            if not raw:
                self._eof = True
                tail = self._carry
                self._carry = b""
                if tail and not tail.endswith(b"\n"):
                    tail += b"\n"
                self._out = self._out[self._pos:] + repair_chunk(tail)
                self._pos = 0
                break
            raw = self._carry + raw
            cut = raw.rfind(b"\n")
            if cut < 0:                      # no complete line yet, read more
                self._carry = raw
                continue
            self._carry = raw[cut + 1:]
            self._out = self._out[self._pos:] + repair_chunk(raw[:cut + 1])
            self._pos = 0

    def read(self, size=-1):
        if size is None or size < 0:
            parts = []
            while True:
                b = self.read(1 << 22)
                if not b:
                    break
                parts.append(b)
            return b"".join(parts)
        self._fill(size)
        out = self._out[self._pos:self._pos + size]
        self._pos += len(out)
        if self._pos > (1 << 23):
            self._out = self._out[self._pos:]
            self._pos = 0
        return out

    def readinto(self, b):
        data = self.read(len(b))
        b[:len(data)] = data
        return len(data)


def read_csv_slice(path, grid=None, want_xy=None):
    """Read one CSV slice into a ``(ny, nx)`` float32 array plus a valid mask.

    ``grid`` short-circuits the X/Y scan: pass the :class:`GridSpec` learnt
    from the first slice of a stack and only the amplitude column is parsed,
    which is the whole point of the fast path. ``want_xy`` forces the scan.
    """
    if np is None:
        raise RuntimeError("numpy is required to read GPR slices")
    t0 = time.time()
    need_xy = grid is None or want_xy
    cols = (0, 1, 4) if need_xy else (4,)
    # float64 on the X/Y scan pass: float32 rounds a 0.05 m step to
    # 0.05000000074, which then drifts across 1492 columns.
    with open(path, "rb") as fh:
        stream = io.BufferedReader(RepairedReader(fh), buffer_size=1 << 20)
        arr = np.loadtxt(stream, delimiter=",", usecols=cols,
                         dtype=np.float64 if need_xy else np.float32)

    if need_xy:
        xs, ys = arr[:, 0], arr[:, 1]
        amp = arr[:, 2].astype(np.float32)
        ux = np.unique(xs)
        uy = np.unique(ys)
        hdr = read_csv_header(path)
        grid = GridSpec(nx=int(ux.size), ny=int(uy.size),
                        x_min=float(ux[0]), y_min=float(uy[0]),
                        x_step=float(hdr.get("x_step") or
                                     (ux[1] - ux[0] if ux.size > 1 else 1.0)),
                        y_step=float(hdr.get("y_step") or
                                     (uy[1] - uy[0] if uy.size > 1 else 1.0)))
        if grid.nx * grid.ny != amp.size:
            raise ValueError(
                "%s is not a complete regular grid: %d x %d cells but %d rows"
                % (os.path.basename(path), grid.nx, grid.ny, amp.size))
    else:
        amp = arr if arr.ndim == 1 else arr[:, 0]
        if amp.size != grid.nx * grid.ny:
            raise ValueError(
                "%s has %d rows, expected %d for the stack grid"
                % (os.path.basename(path), amp.size, grid.nx * grid.ny))
    del arr

    amp = amp.reshape(grid.ny, grid.nx)      # rows vary Y slowest: raster order
    mask = amp != np.float32(NODATA)
    return grid, amp, mask, time.time() - t0


# --------------------------------------------------------------------------
# colour mapping and PNG output (no PIL: Blender does not ship it)
# --------------------------------------------------------------------------

def _viridis_lut():
    """8 anchor colours of viridis, linearly interpolated to 256 entries."""
    anchors = [(68, 1, 84), (72, 40, 120), (62, 74, 137), (49, 104, 142),
               (38, 130, 142), (31, 158, 137), (53, 183, 121), (109, 205, 89),
               (180, 222, 44), (253, 231, 37)]
    lut = np.zeros((256, 3), dtype=np.uint8)
    n = len(anchors) - 1
    for i in range(256):
        t = i / 255.0 * n
        k = min(int(t), n - 1)
        f = t - k
        for c in range(3):
            lut[i, c] = int(round(anchors[k][c] * (1 - f) + anchors[k + 1][c] * f))
    return lut


COLORMAPS = ("GRAY", "GRAY_INV", "VIRIDIS")


def to_rgba8(amp, mask, vmin, vmax, colormap="GRAY"):
    """Map amplitudes to an ``(ny, nx, 4)`` uint8 RGBA array.

    No-data cells get alpha 0, so the irregular footprint of the survey comes
    out of the texture for free — which is the main reason a textured plane
    beats a point cloud or a voxel volume for this data.
    """
    span = float(vmax - vmin) or 1.0
    norm = np.clip((amp - vmin) / span, 0.0, 1.0)
    idx = (norm * 255.0).astype(np.uint8)
    rgba = np.zeros(amp.shape + (4,), dtype=np.uint8)
    if colormap == "VIRIDIS":
        rgba[..., :3] = _viridis_lut()[idx]
    elif colormap == "GRAY_INV":
        rgba[..., 0] = rgba[..., 1] = rgba[..., 2] = 255 - idx
    else:
        rgba[..., 0] = rgba[..., 1] = rgba[..., 2] = idx
    rgba[..., 3] = np.where(mask, 255, 0).astype(np.uint8)
    return rgba


def write_png(path, rgba):
    """Minimal RGBA8 PNG writer (zlib only, no third-party dependency)."""
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


# --------------------------------------------------------------------------
# cache build
# --------------------------------------------------------------------------

def percentile_range(values, lo=2.0, hi=98.0):
    return (float(np.percentile(values, lo)), float(np.percentile(values, hi)))


def build_cache(folder, out_dir=None, colormap="GRAY", normalize="STACK",
                clip_lo=2.0, clip_hi=98.0, limit=0, progress=None,
                sample_cells=200000):
    """Blocking wrapper around :func:`build_cache_steps`."""
    it = build_cache_steps(folder, out_dir, colormap, normalize,
                           clip_lo, clip_hi, limit, sample_cells)
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
                      sample_cells=200000):
    """Convert a CSV slice stack to a cached PNG stack plus a manifest.

    ``normalize``
        ``STACK`` (default) uses one robust range for every slice, so slice to
        slice comparison is meaningful; ``SLICE`` stretches each slice to its
        own range, which shows faint deep anomalies but lies about relative
        amplitude.

    Returns the manifest dict; it is also written to ``gpr_stack.json`` next
    to the PNGs, and is what ``import_gpr`` reads back on a second import.
    """
    kind, specs = scan_stack(folder, kind="csv_grid")
    if not specs:
        raise ValueError("no CSV slices found in %s" % folder)
    if limit:
        specs = specs[:limit]
    out_dir = out_dir or os.path.join(folder, "_3dsc_gpr_cache")
    os.makedirs(out_dir, exist_ok=True)

    t_start = time.time()
    grid = None
    vmin = vmax = None

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
        entries.append({
            "index": i,
            # One slice is one document (E.D., 2026-09-21), so every slice
            # needs an identity that survives a re-export and a rename of the
            # .blend. Depth is that identity: it is what the reading is OF.
            "document_id": document_id(folder, s),
            "source": os.path.relpath(s.path, out_dir),
            "raster": os.path.basename(png),
            "depth_top": s.depth_top,
            "depth_bottom": s.depth_bottom,
            "vmin": vmin, "vmax": vmax,
            "valid_cells": int(mask.sum()),
            "png_bytes": nbytes,
        })
        del amp, mask

    manifest = {
        "manifest_version": MANIFEST_VERSION,
        "generator": "3DSC gpr_core",
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
    }
    with open(os.path.join(out_dir, MANIFEST_NAME), "w") as fh:
        json.dump(manifest, fh, indent=2)
    return manifest


# --------------------------------------------------------------------------


def load_manifest(out_dir):
    p = os.path.join(out_dir, MANIFEST_NAME)
    if not os.path.isfile(p):
        return None
    with open(p) as fh:
        return json.load(fh)


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
# image-stack path (UA Ilici GEORRADAR, and any stack already rasterised)
# --------------------------------------------------------------------------

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


def build_image_manifest(folder, out_dir=None, x_min=0.0, y_min=0.0,
                         x_step=None, y_step=None, limit=0):
    """Describe an already-rasterised slice stack without converting anything.

    Written for the UA Ilici ``GEORRADAR/`` sectors: ``Sector1_Alcudia`` holds
    601 depth slices as JPEGs at 5 mm steps, and the per-sector ``mean_v2.tif``
    ships an ESRI world file. Where a world file exists it wins; otherwise the
    caller supplies the cell size and the local origin.

    The manifest has the same shape as the one :func:`build_cache` writes, so
    the Blender side has exactly one code path for both kinds of stack.
    """
    kind, specs = scan_stack(folder, kind="image_stack")
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
        entries.append({
            "index": i,
            "document_id": document_id(folder, s),
            "source": _ref(s.path),
            "raster": _ref(s.path),
            "depth_top": s.depth_top,
            "depth_bottom": s.depth_bottom,
            "vmin": 0.0, "vmax": 1.0,
            "valid_cells": nx * ny,
            "png_bytes": os.path.getsize(s.path),
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
        "generator": "3DSC gpr_core",
        "kind": "image_stack",
        "source_folder": folder,
        "colormap": "AS_IS",
        "normalize": "AS_IS",
        "world_file": os.path.basename(wf) if wf else "",
        "georef": georef,
        "grid": asdict(GridSpec(nx=nx, ny=ny, x_min=x_min, y_min=y_min,
                                x_step=x_step, y_step=y_step)),
        "slices": entries,
    }
    with open(os.path.join(out_dir, MANIFEST_NAME), "w") as fh:
        json.dump(manifest, fh, indent=2)
    return manifest


# --------------------------------------------------------------------------
# CRS detection and shift proposal
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

    pyproj is already bundled with 3DSC (``scripts/requirements_wheels.txt``)
    so no new dependency is needed, but it is lazy-imported and missing on one
    build (macOS-Intel + Python 3.13), so fall back to reading the AUTHORITY
    clause straight out of the WKT.
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

    if kind == "image_stack":
        wf = world_file_for(first)
        if wf:
            nx, ny = image_size(first)
            x_min, y_min, px, py = extent_from_world_file(wf, nx, ny)
            out.update(origin_e=x_min, origin_n=y_min, x_step=px, y_step=py,
                       source=os.path.basename(wf))
    else:
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
