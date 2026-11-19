# -*- coding: utf-8 -*-
"""3DSC — what the GPR panel decides before Blender draws (no bpy).

The reading of a geophysical stack is the embedded core's
(``_vendor/geofisica_core``, row G6 of the geophysics plan: one source, in
em-profiles). This module holds only the panel's glue, kept out of
``import_gpr.py`` so that it is tested without Blender: which reader a choice
of the panel names, what the person declares for files that say nothing
(the Basilica Iulia's 92 x 50 m slices, the length and depth of each
section, the frame of a capture), where the cache goes, and where each slice
of a manifest sits in the stack's frame (horizontal or vertical, its own grid,
a depth or none).
"""

import json
import os
import re
import subprocess

#: the panel's choice -> the core's reader (``None`` = the core guesses
#: between a volume of points and a file of ``line N`` sections)
CORE_KIND = {
    'CSV': "csv_grid",
    'IMAGES': "image_stack",
    'GEOTIFF': "geotiff",
    'ASCII': "ascii_matrix",
    'POINTS': None,
    'SCREENSHOT': "screenshot",
}

#: the core's reader -> the panel's choice (a folder picked: what it holds)
PANEL_KIND = {
    "csv_grid": 'CSV', "image_stack": 'IMAGES', "geotiff": 'GEOTIFF',
    "ascii_matrix": 'ASCII', "xyzv": 'POINTS', "xyz_lines": 'POINTS',
    "screenshot": 'SCREENSHOT',
}

#: the kinds 3DSC's own cache always built (``build_cache_steps`` /
#: ``build_image_manifest``, cache beside the slices by default); every
#: other one goes through ``build_stack_cache`` (plugins-data, never beside)
LEGACY_KINDS = ('CSV', 'IMAGES')

PRODUCER = "3D Survey Collection"


def parse_pair(text):
    """``"92 x 50"``, ``"-50, 25"``, ``"92;50"`` -> ``(92.0, 50.0)`` (a point
    for decimals); ``None`` when empty; ``ValueError`` when not two numbers."""
    text = str(text or "").strip()
    if not text:
        return None
    nums = re.findall(r"[-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?", text)
    if len(nums) != 2:
        raise ValueError("two numbers expected, not %r" % text)
    return float(nums[0]), float(nums[1])


def parse_numbers(text, n):
    """``n`` numbers from a typed text (``"610, 170, 1303, 715"``), or
    ``None`` when empty; ``ValueError`` when not ``n``."""
    text = str(text or "").strip()
    if not text:
        return None
    nums = re.findall(r"[-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?", text)
    if len(nums) != n:
        raise ValueError("%d numbers expected, not %r" % (n, text))
    return tuple(float(v) for v in nums)


def typed_georef(origin_e, origin_n, epsg="", rotation=0.0):
    """A placement typed in the panel for files that say none (the core's
    ``georef``), or ``None`` when nothing was typed (origin 0, 0, no EPSG)."""
    e, n = float(origin_e or 0.0), float(origin_n or 0.0)
    code = str(epsg or "").strip().upper().replace("EPSG:", "")
    if not (e or n or code):
        return None
    g = {"origin_e": e, "origin_n": n, "rotation": float(rotation or 0.0),
         "source": "typed in 3DSC"}
    if code:
        g["epsg"] = int(code) if code.isdigit() else code
    return g


def parse_sections(text):
    """``"VERT1=50x8; VERT2=92x9"`` -> ``{"VERT1": (50.0, 8.0), ...}``:
    the length along the line and the depth of each vertical section."""
    out = {}
    for item in re.split(r"[;\n]", str(text or "")):
        item = item.strip()
        if not item:
            continue
        if "=" not in item:
            raise ValueError("a section is LINE=LENGTHxDEPTH, not %r" % item)
        line, size = item.split("=", 1)
        out[line.strip().upper()] = parse_pair(size)
    return out


def declared(kind, extent=None, sections=None, section_default=None, frame=None):
    """What the files do not say, as the core's ``declared``: ``f(spec) -> dict``.

    ``extent`` — ``(width, height)`` of a horizontal matrix in metres;
    ``sections`` — ``{line: (length, depth)}``; ``section_default`` — the
    ``(length, depth)`` of a section not in the table; ``frame`` — the frame
    of a stack of captures (the same for every capture)."""
    sections = {k.upper(): v for k, v in (sections or {}).items()}

    def for_spec(spec):
        if kind == "screenshot":
            return {"frame": frame} if frame else {}
        if kind != "ascii_matrix":
            return {}
        if getattr(spec, "orientation", "horizontal") == "vertical":
            size = sections.get(str(spec.line or "").upper()) or section_default
            return {"length": size[0], "depth": size[1]} if size else {}
        return {"extent": tuple(extent)} if extent else {}
    return for_spec


def value_scale(enabled, from_range, to_range, unit, source=""):
    """The declared scale of the values (ERT Basilica: 1-255 -> 0-3500 ohm.m,
    read off a figure: low confidence), or ``None``."""
    if not enabled:
        return None
    vs = {"from": [float(from_range[0]), float(from_range[1])],
          "to": [float(to_range[0]), float(to_range[1])],
          "unit": str(unit or "").strip(), "confidence": "low"}
    if str(source or "").strip():
        vs["source"] = str(source).strip()
    return vs


def is_under(path, folder):
    path, folder = os.path.realpath(path), os.path.realpath(folder)
    return path == folder or path.startswith(folder.rstrip(os.sep) + os.sep)


def cache_dir(stack_kind, source_dir, chosen="", built=""):
    """Where the manifest of the stack is.

    The legacy kinds keep 3DSC's habit (``_3dsc_gpr_cache`` beside the
    slices when none is chosen). The others are cached by the core in
    ``plugins-data/geofisica/cache/<key>/`` (``built``, set after a build) or
    in the chosen folder — never under the slices' folder, which the core
    refuses (OneDrive is read only)."""
    if chosen:
        return chosen
    if stack_kind in LEGACY_KINDS:
        return os.path.join(source_dir, "_3dsc_gpr_cache")
    return built or ""


def _depth_mid(entry):
    top, bot = entry.get("depth_top"), entry.get("depth_bottom")
    if top is None or bot is None:
        return None
    return 0.5 * (float(top) + float(bot))


def slice_object_name(coll_name, entry):
    """The object of a slice: ``<stack>_d<top>`` as before when there is a
    depth; ``<stack>_s<line>`` for a section; ``<stack>_<product>`` else."""
    if entry.get("orientation") == "vertical":
        return "%s_s%s" % (coll_name, entry.get("line") or entry.get("index"))
    if entry.get("depth_top") is not None:
        return "%s_d%06.3f" % (coll_name, entry["depth_top"])
    return "%s_%s" % (coll_name, entry.get("product") or "slice%03d" % entry.get("index", 0))


def same_grid(a, b, tol=1e-6):
    if not a or not b:
        return a == b
    return all(abs(float(a[k]) - float(b[k])) < tol if isinstance(a[k], float) else a[k] == b[k]
               for k in ("nx", "ny", "x_min", "y_min", "x_step", "y_step"))


def slice_layout(entry, head_grid, head_georef=None):
    """Where a manifest's slice sits under the stack's root.

    ``orientation`` — ``horizontal`` (a plane at ``z = -depth``, ``0`` when
    the depth is not known: a product such as Ilici's ``mean_v2``) or
    ``vertical`` (a section: the plane stands on the line, ``x`` along it,
    the grid's ``y`` the height above ground). ``grid`` — the slice's own
    (each Basilica file has its own) or the stack's. ``shared`` — whether the
    stack's one drape mesh serves it. ``offset`` — its georeferenced origin
    minus the stack's, when both are known."""
    grid = entry.get("grid") or head_grid
    orientation = entry.get("orientation") or "horizontal"
    mid = _depth_mid(entry)
    offset = (0.0, 0.0)
    geo = entry.get("georef") or {}
    if head_georef and geo and None not in (geo.get("origin_e"), geo.get("origin_n"),
                                           head_georef.get("origin_e"),
                                           head_georef.get("origin_n")):
        offset = (float(geo["origin_e"]) - float(head_georef["origin_e"]),
                  float(geo["origin_n"]) - float(head_georef["origin_n"]))
    return {
        "orientation": orientation,
        "grid": grid,
        "z": 0.0 if (orientation == "vertical" or mid is None) else -mid,
        "depth_known": mid is not None,
        "shared": orientation == "horizontal" and same_grid(grid, head_grid)
        and offset == (0.0, 0.0),
        "offset": offset,
    }


def quad(grid, orientation="horizontal"):
    """The four corners of a slice's plane in the stack's frame (cell
    centres plus half a cell): on the ground's XY, or standing in XZ."""
    x0 = grid["x_min"] - grid["x_step"] / 2.0
    y0 = grid["y_min"] - grid["y_step"] / 2.0
    w, h = grid["nx"] * grid["x_step"], grid["ny"] * grid["y_step"]
    if orientation == "vertical":
        return [(x0, 0.0, y0), (x0 + w, 0.0, y0), (x0 + w, 0.0, y0 + h), (x0, 0.0, y0 + h)]
    return [(x0, y0, 0.0), (x0 + w, y0, 0.0), (x0 + w, y0 + h, 0.0), (x0, y0 + h, 0.0)]


def document_kind(method, orientation):
    """``gpr_time_slice`` as before for a GPR plane; ``<method>_section`` /
    ``<method>_slice`` otherwise."""
    method = (method or "gpr").lower()
    if orientation == "vertical":
        return "%s_section" % method
    return "gpr_time_slice" if method == "gpr" else "%s_slice" % method


def stack_rotation(typed_deg, georef):
    """The typed azimuth wins; else the georeference's (degrees CCW)."""
    if typed_deg:
        return float(typed_deg)
    return float((georef or {}).get("rotation") or 0.0)


def software_line(folder):
    """3DSC's line in a stamp: name, the version of its manifest, the commit
    (``build_info.json`` in a package, ``git`` in a working copy)."""
    line = {"name": PRODUCER}
    try:
        with open(os.path.join(folder, "blender_manifest.toml"), "r", encoding="utf-8") as fh:
            for raw in fh:
                m = re.match(r'\s*version\s*=\s*"([^"]+)"', raw)
                if m:
                    line["version"] = m.group(1)
                    break
    except OSError:
        pass
    commit = ""
    try:
        with open(os.path.join(folder, "build_info.json"), "r", encoding="utf-8") as fh:
            commit = str(json.load(fh).get("commit") or "")
    except (OSError, ValueError):
        try:
            out = subprocess.run(["git", "-C", folder, "rev-parse", "--short", "HEAD"],
                                 capture_output=True, text=True, timeout=5)
            commit = out.stdout.strip() if out.returncode == 0 else ""
        except (OSError, subprocess.SubprocessError):
            commit = ""
    if commit:
        line["commit"] = commit
    return line


def rgb_from_pixels(pixels, width, height):
    """Blender's float RGBA pixels (row 0 at the bottom) -> ``(h, w, 3)``
    uint8 with row 0 at the top: the decoder the core asks the host for."""
    import numpy as np
    a = np.asarray(pixels, dtype=np.float32).reshape(height, width, -1)[::-1, :, :3]
    return np.clip(np.rint(a * 255.0), 0, 255).astype(np.uint8)
