"""How many textures, and how large, each level of detail needs — pure Python.

The arithmetic behind ``headless.make_lod_set``, kept free of ``bpy`` so it is
tested with plain pytest (tests/test_lod_plan.py). It writes down the rules
3DSC already follows elsewhere:

* **texel density of the original** — ``cesium_exporter.native_bake.
  _original_texel_atlas_size``: the pixels a mesh needs to keep the density
  it has in its source textures are the sum over its faces of (UV area of the
  face) x (pixels of its material's image) x 1.3 (packing overhead of a fresh
  UV layout); the side is that square root rounded to the NEAREST power of two
  and clamped to [256, 4096];
* **face-count fallback** — ``native_export._auto_atlas_size_for_tile``: with
  no UV map or no image, 16 px per face, side rounded UP to a power of two;
* **texture and geometry go together** — ``cesium_exporter.lod.
  _compute_lod_parameters``: a level that keeps ``ratio`` of the triangles has
  ``ratio = (atlas_side / leaf_side)²``, i.e. it needs ``ratio`` of the pixels.
  The default chain halves the side at each level: ratios 1, 1/4, 1/16 …;
* **one atlas per object per level** — ``LODgenerator`` (``LOD<n>_tex_res``):
  an explicit size per level gives exactly one texture of that size.

What is new here is only the split: when the pixels a level needs do not fit
one ``max_texture_size`` atlas (an Unreal/web budget, 4096 by default), the
level gets ``round(pixels / max²)`` atlases of ``max_texture_size`` (at least
2, at most ``max_textures``) instead of a single clamped one that would lose
density.
"""
from __future__ import annotations

import math
import re

#: the texel rules of cesium_exporter (native_bake / native_export)
PACKING_OVERHEAD = 1.3
PX_PER_FACE = 16
MIN_TEXTURE_SIZE = 256
MAX_TEXTURE_SIZE = 4096
MAX_TEXTURES = 16

_LOD_SUFFIX_RE = re.compile(r'_LOD\d+.*$', re.IGNORECASE)


def base_name(name):
    """``OB_PODIO_LOD1`` -> ``OB_PODIO`` (as ``multi_lod._strip_lod_suffix``);
    a name without ``_LOD<n>`` is returned as it is."""
    return _LOD_SUFFIX_RE.sub('', name or '').rstrip('._-') or (name or 'mesh')


def level_ratios(levels=3):
    """The triangle ratio of each level, the first one the source density.

    ``levels`` is the number of levels (``3`` -> ``[1.0, 0.25, 0.0625]``: the
    texture side halves at each level) or the ratios themselves (each in
    (0, 1], e.g. ``[1.0, 0.5, 0.1]`` — LODgenerator's own chain)."""
    if isinstance(levels, bool):
        raise ValueError("levels: a number of levels or a list of ratios")
    if isinstance(levels, int):
        if levels < 1:
            raise ValueError("levels must be >= 1")
        return [0.25 ** i for i in range(levels)]
    ratios = [float(r) for r in levels]
    if not ratios or any(not (0.0 < r <= 1.0) for r in ratios):
        raise ValueError(f"levels: every ratio must be in (0, 1], got {ratios}")
    return ratios


def pow2_nearest(x):
    """Nearest power of two (as ``_original_texel_atlas_size`` rounds)."""
    return 2 ** int(round(math.log2(max(float(x), 1.0))))


def pow2_up(x):
    """Smallest power of two >= x (as ``_auto_atlas_size_for_tile`` rounds)."""
    size = 1
    while size < x:
        size *= 2
    return size


def textures_for_pixels(pixels, max_size=MAX_TEXTURE_SIZE, min_size=MIN_TEXTURE_SIZE,
                        max_textures=MAX_TEXTURES, rounding="nearest"):
    """``(count, side)`` of the square power-of-two atlases holding ``pixels``.

    One atlas while the rounded side fits ``max_size``; otherwise
    ``round(pixels / max_size²)`` atlases of ``max_size`` (at least 2, at
    most ``max_textures``: with ``max_textures=1`` one clamped atlas)."""
    if max_size < min_size:
        raise ValueError("max_size must be >= min_size")
    pixels = float(pixels or 0.0)
    if pixels <= 0:
        return 1, int(min_size)
    side = math.sqrt(pixels)
    side = pow2_up(side) if rounding == "up" else pow2_nearest(side)
    if side <= max_size:
        return 1, int(max(min_size, side))
    count = max(2, int(round(pixels / float(max_size) ** 2)))
    return int(max(1, min(max_textures, count))), int(max_size)


def plan_lod_set(source_triangles, source_pixels=None, levels=3,
                 max_texture_size=MAX_TEXTURE_SIZE, min_texture_size=MIN_TEXTURE_SIZE,
                 max_textures=MAX_TEXTURES, texture_px=None):
    """One entry per level: ``{level, ratio, triangles, pixels, textures,
    texture_px, rule}``.

    ``source_triangles``: triangles of the source mesh.
    ``source_pixels``: its texel budget in the original textures
    (``native_bake._original_texel_pixels``, overhead included), or None when
    it has no UV map or image — then 16 px per face of each level.
    ``texture_px``: an int, or one int per level, fixes the side and gives one
    texture per level (LODgenerator's ``LOD<n>_tex_res``)."""
    ratios = level_ratios(levels)
    if texture_px is not None and not isinstance(texture_px, int):
        texture_px = [int(t) for t in texture_px]
        if len(texture_px) != len(ratios):
            raise ValueError("texture_px: one size per level")
    plan = []
    for level, ratio in enumerate(ratios):
        triangles = max(1, int(round(int(source_triangles) * ratio)))
        if texture_px is not None:
            side = texture_px if isinstance(texture_px, int) else texture_px[level]
            pixels, count, rule = float(side) ** 2, 1, "fixed"
        elif source_pixels:
            pixels = float(source_pixels) * ratio
            count, side = textures_for_pixels(pixels, max_texture_size, min_texture_size,
                                              max_textures, rounding="nearest")
            rule = "texel_density"
        else:
            pixels = float(triangles * PX_PER_FACE)
            count, side = textures_for_pixels(pixels, max_texture_size, min_texture_size,
                                              max_textures, rounding="up")
            rule = "face_count"
        plan.append({"level": level, "ratio": ratio, "triangles": triangles,
                     "pixels": int(round(pixels)), "textures": int(count),
                     "texture_px": int(side), "rule": rule})
    return plan


def split_by_weight(keys, weights, parts):
    """Group index (0..parts-1) of each element: elements sorted by ``keys``
    (a coordinate along the longest axis), cut into ``parts`` consecutive
    runs of about equal total ``weights`` — slabs of equal surface, one per
    atlas. Zero total weight counts every element as 1."""
    n = len(keys)
    if parts <= 1 or n == 0:
        return [0] * n
    weights = [max(0.0, float(w)) for w in weights]
    total = sum(weights)
    if total <= 0:
        weights, total = [1.0] * n, float(n)
    groups = [0] * n
    acc = 0.0
    for i in sorted(range(n), key=keys.__getitem__):
        w = weights[i]
        groups[i] = min(parts - 1, int((acc + w / 2.0) / total * parts))
        acc += w
    return groups
