# -*- coding: utf-8 -*-
"""Depth from a file name, and the header of a CSV slice."""

from __future__ import annotations

import os
import re

_NUM = r"([-+]?\d+(?:[.,]\d+)?)"
_SEP = r"\s*(?:-|to|_)\s*"
#: a band in centimetres (``100-150cm``, the ERT slices of the Basilica Iulia)
#: or millimetres (``0-500mm``): read before metres, whose pattern would take
#: the ``m`` of ``mm`` as metres
_RE_RANGE_CM = re.compile(_NUM + _SEP + _NUM + r"\s*cm", re.I)
_RE_RANGE_MM = re.compile(_NUM + _SEP + _NUM + r"\s*mm", re.I)
_RE_SINGLE_CM = re.compile(_NUM + r"\s*cm", re.I)
_RE_RANGE_M = re.compile(
    r"([-+]?\d+(?:[.,]\d+)?)\s*(?:-|to|_)\s*([-+]?\d+(?:[.,]\d+)?)\s*m", re.I)
_RE_SINGLE_MM = re.compile(r"([-+]?\d+(?:[.,]\d+)?)\s*mm", re.I)
_RE_SINGLE_M = re.compile(r"([-+]?\d+(?:[.,]\d+)?)\s*m\b", re.I)
_RE_HEADER_FIELD = re.compile(
    r"([A-Za-z]+)\s*(?:\xb1|±|\+/-|\+-)?\s*([-+]?\d+(?:\.\d+)?)\s*m?", re.I)


def depth_from_name(name):
    """Return ``(top, bottom)`` in metres, positive downwards, or ``None``.

    Handles ``slice_0.100 - 0.200m.CSV`` (a range), ``Slice_-2889mm.jpg``
    (a single signed depth in millimetres, as UA Ilici writes them) and
    ``100-150cm.ASC`` (a band in centimetres, as the ERT slices of the
    Basilica Iulia are named); a range in millimetres too.
    """
    stem = os.path.splitext(os.path.basename(name))[0]
    for rx, div in ((_RE_RANGE_CM, 100.0), (_RE_RANGE_MM, 1000.0)):
        m = rx.search(stem)
        if m:
            a = abs(float(m.group(1).replace(",", "."))) / div
            b = abs(float(m.group(2).replace(",", "."))) / div
            return (min(a, b), max(a, b))
    m = _RE_RANGE_M.search(stem)
    if m:
        a = float(m.group(1).replace(",", "."))
        b = float(m.group(2).replace(",", "."))
        return (min(abs(a), abs(b)), max(abs(a), abs(b)))
    m = _RE_SINGLE_MM.search(stem)
    if m:
        d = abs(float(m.group(1).replace(",", "."))) / 1000.0
        return (d, d)
    m = _RE_SINGLE_CM.search(stem)
    if m:
        d = abs(float(m.group(1).replace(",", "."))) / 100.0
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
