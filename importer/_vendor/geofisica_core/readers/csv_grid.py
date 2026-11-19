# -*- coding: utf-8 -*-
"""``csv_grid`` — one CSV per depth slice, a complete regular grid in raster order.

The header line carries the cell size and the slice depth, e.g.::

    X ± 0.0500m, Y ± 0.0500m, Z ± 1.9000m, Depth ± 1.9000m, Amplitude
    0.0000, 0.0000, -1.9000, 1.9000,
    0.0500, 0.0000, -1.9000, 1.9000, 20.489

Cells outside the surveyed polygon carry an **empty** amplitude field; they
become the no-data mask (alpha 0 in the cached raster). Measured on the CS07
CSIC-Tivoli sample: 1492 x 1474 cells per slice, 40% no-data.
"""

from __future__ import annotations

import io
import os
import time

try:
    import numpy as np
except ImportError:  # pragma: no cover - Blender always ships numpy
    np = None

from ..depth import read_csv_header
from ..grid import GridSpec

NODATA = -9999.0
"""Sentinel substituted for empty amplitude fields before numeric parsing."""

CSV_EXT = (".csv",)

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

    The only tricky part is a chunk boundary landing inside ``", \\n"``: the
    raw partial last line of each chunk is carried over to the next one.
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
    Returns ``(grid, amp, mask, seconds)``.
    """
    if np is None:
        raise RuntimeError("numpy is required to read geophysical slices")
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
