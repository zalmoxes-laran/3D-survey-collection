"""The sign «master not stamped» in 3DSC (MICRO-TIMBRA-MASTER, 6 Nov 2026).

E.D. (30 Oct 2026): in every tool — EMStudio, EM Tools, 3DSC — a master file
that arrives must be SEEN when it is not stamped, with a gesture to stamp it
there; and the two kinds of master are told apart: **very high resolution**
(dense geometry, often with no texture) and **complete** (textured).

The rule is s3Dgraphy's (``s3dgraphy.resources.master_stamp``). 3DSC carries
neither s3dgraphy nor dtcstamp (``tests/test_stamp_bridge.py``: no copy of
dtcstamp lives here), so the few questions a row asks are answered here, in
the same words — ``tests/test_master_mark.py`` checks the answers agree with
s3Dgraphy's when it is on this machine:

* :func:`looks_like_master` — a 3D file in a ``master/`` folder (the
  convention of the design), or whose name says it (``…_master``, ``…_VHR``,
  ``…_highres``); a version (``name@use``) never is;
* :func:`is_stamped` — a ``<file>.stamp.json`` beside it;
* :func:`kind` — textured → ``complete``, untextured → ``very_high_resolution``;
* :func:`mark` — what the panel draws: ``{state, label, gesture}``.

The stamp itself is written by EM Tools (``stamp_bridge.stamp_master``).
No ``bpy`` here.
"""
from __future__ import annotations

import json
import os
import re
import struct

VERY_HIGH_RESOLUTION = "very_high_resolution"
COMPLETE = "complete"
KIND_LABELS = {VERY_HIGH_RESOLUTION: "very high resolution", COMPLETE: "complete"}
MODEL_EXTENSIONS = (".obj", ".ply", ".glb", ".gltf", ".fbx", ".stl", ".dae", ".abc",
                    ".usd", ".usdz", ".usdc", ".x3d", ".wrl", ".e57", ".las", ".laz", ".pts", ".xyz")
MASTER_FOLDERS = ("master", "_master", "masters")
_NAME_RE = re.compile(r"(^|[^a-z])(master|vhr|highres|hi-?res|very[_ -]?high)([^a-z]|$)", re.I)
#: the custom property an import writes on the objects it made: the file
SOURCE_PROP = "3dsc_source_file"


def is_model(path):
    return os.path.splitext(str(path or ""))[1].lower() in MODEL_EXTENSIONS


def looks_like_master(path):
    if not is_model(path):
        return False
    parts = [p.lower() for p in re.split(r"[\\/]+", str(path))]
    if any(p in MASTER_FOLDERS for p in parts[:-1]):
        return True
    stem = os.path.splitext(parts[-1])[0] if parts else ""
    return bool(_NAME_RE.search(stem)) and "@" not in stem


def stamp_path_for(path):
    """``<file>.stamp.json`` beside it — dtcstamp's name for a plain file name."""
    path = os.path.abspath(str(path).rstrip("/\\"))
    return path + ".stamp.json"


def is_stamped(path):
    return os.path.isfile(stamp_path_for(path))


def is_textured(path):
    """Whether a mesh file carries a texture; None when not known."""
    ext = os.path.splitext(path)[1].lower()
    try:
        if ext == ".obj":
            base, mtls = os.path.dirname(path), []
            with open(path, "rb") as fh:
                for i, line in enumerate(fh):
                    if line.startswith(b"mtllib"):
                        mtls.append(line[6:].strip().decode("utf-8", "replace"))
                    elif i > 200000:
                        break
            seen = False
            for m in mtls:
                p = os.path.join(base, m)
                if os.path.isfile(p):
                    seen = True
                    with open(p, "r", encoding="utf-8", errors="replace") as fh:
                        if any(re.match(r"\s*map_(Kd|Ka|Ks|d|bump|Bump)\b", ln) for ln in fh):
                            return True
            return False if (seen or not mtls) else None
        if ext in (".glb", ".gltf"):
            with open(path, "rb") as fh:
                head = fh.read(12)
                if head[:4] == b"glTF":
                    n, _kind = struct.unpack("<II", fh.read(8))
                    doc = json.loads(fh.read(n))
                else:
                    fh.seek(0)
                    doc = json.loads(fh.read())
            return bool(doc.get("images") or doc.get("textures"))
        if ext == ".ply":
            with open(path, "rb") as fh:
                for _ in range(200):
                    low = fh.readline().strip().lower()
                    if low.startswith(b"comment texturefile") or b"texcoord" in low:
                        return True
                    if low == b"end_header" or not low:
                        return False
        if ext in (".e57", ".las", ".laz", ".pts", ".xyz"):
            return False
    except (OSError, ValueError, struct.error):
        return None
    return None


def kind(path):
    t = is_textured(path)
    return COMPLETE if t is True else (VERY_HIGH_RESOLUTION if t is False else None)


def mark(path):
    """The sign of a file, or None when it is not a master.
    → ``{state, kind, label, gesture}``."""
    if not looks_like_master(path):
        return None
    k = kind(path)
    stamped = is_stamped(path)
    label = ("master stamped" if stamped else "⚠ master not stamped") + \
        (f" · {KIND_LABELS[k]}" if k else "")
    return {"state": "stamped" if stamped else "unstamped", "kind": k, "label": label,
            "gesture": None if stamped else "stamp_master"}
