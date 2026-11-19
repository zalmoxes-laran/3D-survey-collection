# -*- coding: utf-8 -*-
"""Values to colours: robust ranges and the colour maps of the cache.

Row G2 carries the old maps unchanged (``GRAY``, ``GRAY_INV``, ``VIRIDIS``:
the PNGs are byte for byte the old core's). Row G5 adds the package's ramps
(``data/colors/*.emc``: ``grigio``, ``viridis``, ``hot``, ``jet``, by the
lower-case stem of their file) and the declared ``value_scale``.

The core runs where the package's data folder is not (3DSC embeds only
``code/geofisica_core``), so :data:`RAMPS` holds the four ramps' colour
mappings as the ``.emc`` files say them; a test holds the two equal. Any
other ``.emc`` (a ramp the person chose) is read by :func:`load_emc` and
passed as it is.
"""

from __future__ import annotations

try:
    import numpy as np
except ImportError:  # pragma: no cover - Blender always ships numpy
    np = None


def _viridis_lut():
    """10 anchor colours of viridis, linearly interpolated to 256 entries."""
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


#: the old core's maps (3DSC's panel offers them): upper case, unchanged
COLORMAPS = ("GRAY", "GRAY_INV", "VIRIDIS")

#: the package's ramps (``data/colors/<name>.emc``), the colour mapping as the
#: file says it — positions 0–1 on the normalised range, linear between
RAMPS = {
    "grigio": {"0.000": "#000000", "0.250": "#404040", "0.500": "#808080",
               "0.750": "#bfbfbf", "1.000": "#ffffff"},
    "viridis": {"0.000": "#440154", "0.250": "#3b528b", "0.500": "#21918c",
                "0.750": "#5ec962", "1.000": "#fde725"},
    "hot": {"0.000": "#000000", "0.250": "#b00000", "0.500": "#ff6000",
            "0.750": "#ffd000", "1.000": "#ffffff"},
    "jet": {"0.000": "#00007f", "0.125": "#0000ff", "0.250": "#007fff",
            "0.375": "#00ffff", "0.500": "#7fff7f", "0.625": "#ffff00",
            "0.750": "#ff7f00", "0.875": "#ff0000", "1.000": "#7f0000"},
}

#: the ramp a method's quantity is shown with when nobody chooses
#: (the ``_note`` of each ``.emc``: hot for GPR amplitude, jet for resistivity)
DEFAULT_RAMP = {"gpr": "hot", "ert": "jet", "mag": "grigio"}


class ColorError(ValueError):
    """A ramp or a value scale that cannot be used (said in EN and IT)."""

    def __init__(self, en, it):
        ValueError.__init__(self, en)
        self.en, self.it = en, it


def _hex(c):
    c = str(c).strip().lstrip("#")
    if len(c) != 6:
        raise ColorError("%r is not a colour #rrggbb" % c, "%r non è un colore #rrggbb" % c)
    return tuple(int(c[i:i + 2], 16) for i in (0, 2, 4))


def load_emc(path):
    """A ramp from an ``.emc`` file (``kind`` ``ramp``, ``domain`` ``normalized``):
    ``{"name", "name_it", "color_mapping"}``."""
    import json
    with open(path, encoding="utf-8") as fh:
        doc = json.load(fh)
    if doc.get("kind") != "ramp" or doc.get("domain", "normalized") != "normalized":
        raise ColorError("%s is not a normalised ramp (kind ramp, domain normalized)" % path,
                         "%s non è una rampa normalizzata (kind ramp, domain normalized)" % path)
    return {"name": doc.get("name"), "name_it": doc.get("name_it"),
            "color_mapping": dict(doc["color_mapping"])}


def ramp_mapping(colormap):
    """The colour mapping of ``colormap``: a package ramp's name, an ``.emc``
    read by :func:`load_emc`, or a bare ``{position: "#rrggbb"}``."""
    if isinstance(colormap, dict):
        return dict(colormap.get("color_mapping", colormap))
    key = str(colormap).lower()
    if key not in RAMPS:
        raise ColorError("unknown colour ramp %r (the package has %s)"
                         % (colormap, ", ".join(sorted(RAMPS))),
                         "rampa di colore sconosciuta %r (il pacchetto ha %s)"
                         % (colormap, ", ".join(sorted(RAMPS))))
    return dict(RAMPS[key])


def ramp_lut(colormap):
    """A ramp as a ``(256, 3)`` uint8 table: entry ``i`` is the colour at
    ``i / 255``, linear between the mapping's stops (the ends held)."""
    stops = sorted((float(k), _hex(v)) for k, v in ramp_mapping(colormap).items())
    if not stops:
        raise ColorError("a ramp without colours", "una rampa senza colori")
    pos = np.array([p for p, _ in stops], dtype=np.float64)
    t = np.arange(256, dtype=np.float64) / 255.0
    lut = np.zeros((256, 3), dtype=np.uint8)
    for c in range(3):
        col = np.array([rgb[c] for _, rgb in stops], dtype=np.float64)
        lut[:, c] = np.round(np.interp(t, pos, col)).astype(np.uint8)
    return lut


def to_rgba8(amp, mask, vmin, vmax, colormap="GRAY"):
    """Map values to an ``(ny, nx, 4)`` uint8 RGBA array.

    No-data cells get alpha 0, so the irregular footprint of the survey comes
    out of the texture for free — which is the main reason a textured plane
    beats a point cloud or a voxel volume for this data.

    ``colormap`` — one of the old :data:`COLORMAPS` (exactly as before), a
    package ramp's name (``grigio``, ``viridis``, ``hot``, ``jet``) or an
    ``.emc`` ramp as a dict.
    """
    span = float(vmax - vmin) or 1.0
    norm = np.clip((amp - vmin) / span, 0.0, 1.0)
    idx = (norm * 255.0).astype(np.uint8)
    rgba = np.zeros(amp.shape + (4,), dtype=np.uint8)
    if colormap == "VIRIDIS":
        rgba[..., :3] = _viridis_lut()[idx]
    elif colormap == "GRAY_INV":
        rgba[..., 0] = rgba[..., 1] = rgba[..., 2] = 255 - idx
    elif colormap in (None, "GRAY"):
        rgba[..., 0] = rgba[..., 1] = rgba[..., 2] = idx
    else:
        rgba[..., :3] = ramp_lut(colormap)[idx]
    rgba[..., 3] = np.where(mask, 255, 0).astype(np.uint8)
    return rgba


def percentile_range(values, lo=2.0, hi=98.0):
    return (float(np.percentile(values, lo)), float(np.percentile(values, hi)))


def robust_range(values, lo=2.0, hi=98.0):
    """:func:`percentile_range` that never fails: ``(0, 1)`` when there is no
    value, ``(a, a + 1)`` when the percentiles meet (a flat slice)."""
    if values is None or np.size(values) == 0:
        return (0.0, 1.0)
    a, b = percentile_range(values, lo, hi)
    if b <= a:
        b = a + 1.0
    return (a, b)


def check_value_scale(value_scale):
    """A declared ``value_scale`` checked and normalised, or ``None``.

    ``{"from": [a, b], "to": [c, d], "unit", "source", "confidence"}`` — the
    stored values ``a``…``b`` stand for ``c``…``d`` of the quantity, linearly
    (the Basilica's ERT: 1–255 → 0–3500 Ω·m read off the report's colour
    bar, ``confidence`` ``low``). It is a DECLARATION: the manifest and every
    stamp carry it, the values are never called measured."""
    if not value_scale:
        return None
    vs = dict(value_scale)
    try:
        a, b = (float(x) for x in vs["from"])
        c, d = (float(x) for x in vs["to"])
    except (KeyError, TypeError, ValueError):
        raise ColorError("a value scale needs from [a, b] and to [c, d]",
                         "una scala dei valori vuole from [a, b] e to [c, d]")
    if a == b:
        raise ColorError("a value scale from a single value (%g) maps nothing" % a,
                         "una scala dei valori da un solo valore (%g) non trasforma niente" % a)
    vs["from"], vs["to"] = [a, b], [c, d]
    vs.setdefault("unit", None)
    vs.setdefault("source", None)
    vs.setdefault("confidence", "low")
    vs.setdefault("linear", True)
    return vs


def apply_value_scale(amp, mask, value_scale):
    """The values in the quantity's unit by the declared scale (linear, not
    clipped); nodata cells left as they are. ``value_scale=None`` → ``amp``."""
    vs = check_value_scale(value_scale)
    if vs is None:
        return amp
    (a, b), (c, d) = vs["from"], vs["to"]
    out = amp.astype(np.float64)
    out = np.where(mask, c + (out - a) * (d - c) / (b - a), out)
    return out.astype(np.float32)
