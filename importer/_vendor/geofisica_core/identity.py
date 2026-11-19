# -*- coding: utf-8 -*-
"""The identity of a slice AS A DOCUMENT.

A single slice is a document; reading several of them produces extractions
that combine into one proxy (E.D., 2026-09-21). So the identity has to be per
slice, and has to be what the reading is OF — the depth band — rather than the
file name, which changes when the geophysicist re-exports the stack:

* ``<method>:<stack>#d<top>-<bottom>m`` — a horizontal slice of known depth
  (``gpr:`` exactly as 3DSC has always written it: Blender scenes carry it as
  ``em_document_id``);
* ``<method>:<stack>#s<line>`` — a vertical section along a line;
* ``<method>:<stack>#<product>`` — a slice whose depth is not known (UA Ilici
  ``mean_v2``): the product names it until a depth is given.
"""

from __future__ import annotations

import os
import re

_SAFE = re.compile(r"[^A-Za-z0-9._-]+")


def stack_name(folder):
    """The stack's name: its folder's name (``gpr`` for a nameless folder)."""
    return os.path.basename(os.path.normpath(folder)) or "gpr"


def _token(text):
    return _SAFE.sub("_", str(text)).strip("_") or "x"


def geo_id(method, stack, spec):
    """The identity of ``spec`` in the stack named ``stack`` measured by ``method``."""
    method = (method or "gpr").lower()
    if spec.orientation == "vertical" and spec.line:
        return "%s:%s#s%s" % (method, stack, _token(spec.line))
    if spec.depth_known:
        return "%s:%s#d%.3f-%.3fm" % (method, stack, spec.depth_top, spec.depth_bottom)
    return "%s:%s#%s" % (method, stack, _token(spec.product or os.path.splitext(
        os.path.basename(spec.path))[0]))


def document_id(folder, spec, method="gpr"):
    """Stable identity of one slice: :func:`geo_id` with the folder's name as the stack.

    The name and the default are the old ``gpr_core.document_id``'s: a GPR
    stack gives byte for byte the identity it always gave.
    """
    return geo_id(method, stack_name(folder), spec)
