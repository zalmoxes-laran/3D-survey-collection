# -*- coding: utf-8 -*-
"""The descriptors: a grid, a slice, a stack. No numpy needed to describe.

A slice is described in the **local** survey frame; where the frame sits in
the world is a separate block (``georef``), so absolute eastings never enter a
grid (decision of 17–18 Nov 2026: georeference per graph, never on the file).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

#: the methods the package names (``data/vocab/metodi.ttl``); open: a stack of
#: another method is read the same way, the word is what the stack says
METHODS = ("gpr", "ert", "mag")

#: the quantity a method measures when nobody says otherwise
#: (``data/vocab/grandezze.ttl``)
DEFAULT_QUANTITY = {"gpr": "ampiezza", "ert": "resistivita", "mag": "campo_magnetico"}

ORIENTATIONS = ("horizontal", "vertical")


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
    """One slice, before its raster is read.

    ``orientation`` — ``horizontal`` (a depth slice: ``depth_top``…
    ``depth_bottom`` below ground) or ``vertical`` (a section along ``line``,
    the depth down its rows or columns). ``product`` names a slice whose depth
    is not known (UA Ilici's ``mean_v2``): the identity is then the product.
    """
    path: str
    depth_top: Optional[float]
    depth_bottom: Optional[float]
    kind: str = "csv_grid"          # csv_grid | image_stack | … (the reader)
    orientation: str = "horizontal"
    line: Optional[str] = None
    product: Optional[str] = None
    #: the value of the plane a slice of a volume lies on (``xyzv``, row G4)
    plane: Optional[float] = None

    @property
    def depth_known(self):
        return self.depth_top is not None and self.depth_bottom is not None

    @property
    def depth_mid(self):
        if not self.depth_known:
            return 0.0
        return 0.5 * (self.depth_top + self.depth_bottom)

    @property
    def thickness(self):
        if not self.depth_known:
            return 0.0
        return abs(self.depth_bottom - self.depth_top)

    @property
    def label(self):
        if not self.depth_known:
            return self.product or self.line or "slice"
        return "%.3f-%.3fm" % (self.depth_top, self.depth_bottom)


#: the name the plan uses; the same class
Slice = SliceSpec


@dataclass
class SliceData:
    """A slice with its raster loaded.

    The grid is in the slice's **local** frame: for a raster read from a
    GeoTIFF or a matrix of declared extent, the origin is the raster's
    lower-left corner (so the first cell centre is half a step in), row 0 =
    ``y_min``. For a vertical section ``x`` runs along the line and ``y`` is
    the height above ground (``-depth``): row 0 is the deepest.

    ``georef`` — where the local frame sits, as the file says it (``None``
    when it says nothing): ``{origin_e, origin_n`` (the lower-left corner,
    doubles), ``rotation`` (degrees, counter-clockwise), ``epsg``,
    ``source``, ``checks}``. ``warnings`` — what the reader noticed, each
    ``{code, en, it, …}`` (both languages: they reach the interface).
    """
    spec: SliceSpec
    grid: GridSpec
    amp: "np.ndarray"       # (ny, nx) float32, NODATA where unsurveyed  # noqa: F821
    mask: "np.ndarray"      # (ny, nx) bool, True = valid  # noqa: F821
    read_seconds: float = 0.0
    georef: Optional[dict] = None
    warnings: List[dict] = field(default_factory=list)
    info: dict = field(default_factory=dict)


@dataclass
class Stack:
    """A stack of slices: what one acquisition produced (``DTCAcquisitionNode``).

    ``method`` (gpr | ert | mag | …), ``quantity`` (from ``grandezze.ttl``),
    ``unit`` (``"V"``, ``"ohm.m"``, ``"nT"``, or ``None`` = the instrument's
    own), ``value_scale`` — a DECLARED mapping of the stored values to the
    quantity (``{"from": [1, 255], "to": [0, 3500], "unit": "ohm.m",
    "source": …, "confidence": "low"}``), never presented as a measurement.
    """
    folder: str
    kind: str
    slices: List[SliceSpec] = field(default_factory=list)
    name: Optional[str] = None
    method: str = "gpr"
    quantity: Optional[str] = None
    unit: Optional[str] = None
    value_scale: Optional[dict] = None

    def __post_init__(self):
        if self.quantity is None:
            self.quantity = DEFAULT_QUANTITY.get(self.method)

    def describe(self):
        """The stack block of a v2 manifest."""
        return {"name": self.name, "method": self.method, "quantity": self.quantity,
                "unit": self.unit, "value_scale": self.value_scale}
