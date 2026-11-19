# -*- coding: utf-8 -*-
"""The stamp on what the core writes (decision G-5, em-profiles SPEC §6.7).

Every PNG of a cache and every manifest leaves with ``<file>.stamp.json``
beside it, in the format of ``dtcstamp`` (``stamp-format.md``, version 1):
``self`` — the artifact by digest, size and media type; ``from`` — the inputs
by IDENTITY (digest, size, the file name as a courtesy label; never a path);
``how`` — ``dtc_kind``, technique, parameters, the software (the host first
when it names itself, this core last); ``by.at``. No ``by.operator``: by the
format's rule the agent is then the software.

The core runs where ``dtcstamp`` is not (Blender with 3DSC alone: 3DSC
carries no copy of it, ``tests/test_stamp_bridge.py`` there), so the few
lines that write a stamp are here; when ``dtcstamp`` is importable it
validates and writes, and the two give the same record. The identities agree
with ``s3dgraphy.em.stamps``: ``res:`` + uuid5 of the digest in the same
namespace, so the same bytes are the same artifact whoever stamps them.
"""

from __future__ import annotations

import hashlib
import json
import os
import uuid
from datetime import datetime, timezone

try:                                                  # validates and writes when present
    import dtcstamp as _dtc
except ImportError:                                   # pragma: no cover - Blender without it
    _dtc = None

STAMP_VERSION = 1
STAMP_SUFFIX = ".stamp.json"

#: the namespace of ``s3dgraphy.em.stamps`` (MICRO-GEO02): the same digest
#: gives the same ``res:`` id in the core, in a plugin, in a script
_NS = uuid.UUID("7b6f1d1e-5c2a-4f3e-9a51-6e0c8f3f2d47")

_MEDIA = {".png": "image/png", ".json": "application/json", ".jpg": "image/jpeg",
          ".jpeg": "image/jpeg", ".tif": "image/tiff", ".tiff": "image/tiff",
          ".glb": "model/gltf-binary", ".csv": "text/csv"}


class StampError(ValueError):
    """What cannot be stamped (no file, an input that names nothing)."""


def file_digest(path, chunk=1 << 20):
    """``sha256:<hex>`` of a file's bytes, read in blocks."""
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        while True:
            block = fh.read(chunk)
            if not block:
                break
            h.update(block)
    return "sha256:" + h.hexdigest()


def resource_id_for(digest):
    """``res:<uuid5 of the digest>`` — deterministic: two bakes of the same bytes agree."""
    return "res:" + str(uuid.uuid5(_NS, str(digest)))


def now_iso():
    """UTC, second precision, ISO-8601 with a ``Z`` (the format's instant)."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def stamp_path(artifact):
    """``<artifact>.stamp.json``, beside it."""
    return str(artifact) + STAMP_SUFFIX


def _digest(path, digests):
    """The digest of ``path``, remembered in ``digests`` (a stack's sources are
    cited by every PNG and by the manifest: hashed once)."""
    if digests is None:
        return file_digest(path)
    key = os.path.realpath(path)
    if key not in digests:
        digests[key] = file_digest(path)
    return digests[key]


def input_entry(item, digests=None):
    """An input by IDENTITY: a path is hashed (digest, size, its name as a
    label); a mapping is taken as it is (a graph resource's ``resource_id``,
    an acquisition with ``kind``)."""
    if isinstance(item, dict):
        entry = {k: v for k, v in item.items() if v is not None}
        if not (str(entry.get("resource_id") or "").strip() or entry.get("digest")):
            raise StampError("an input names nothing: %r" % (item,))
        if "resource_id" not in entry:
            entry = dict({"resource_id": resource_id_for(entry["digest"])}, **entry)
        return entry
    path = os.fspath(item)
    if not os.path.isfile(path):
        raise StampError("the input %s is not a file" % path)
    digest = _digest(path, digests)
    return {"resource_id": resource_id_for(digest), "digest": digest,
            "size_bytes": os.path.getsize(path), "label": os.path.basename(path)}


#: written beside the core by a host that embeds a copy of it (3DSC's
#: ``scripts/vendor_geofisica_core.py``, row G6): where the copy came from
SOURCE_NAME = "SOURCE.json"


def vendored_source():
    """``SOURCE.json`` beside the core when it is an embedded copy (3DSC:
    ``repo``, ``path``, ``commit``, ``tree_digest``), else ``{}`` (the
    package installed by the extension system, a checkout of em-profiles)."""
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), SOURCE_NAME)
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def core_line():
    """The core's software line: name and version, and the em-profiles
    commit an embedded copy was taken from (the agent of a stamp names the
    exact code)."""
    from . import __version__
    line = {"name": "geofisica_core", "version": __version__}
    commit = str(vendored_source().get("commit") or "")[:7]
    if commit:
        line["commit"] = commit
    return line


def make_stamp(artifact, inputs=(), parameters=None, dtc_kind="format_conversion",
               technique=None, software=(), label=None, description=None, at=None,
               digests=None):
    """The stamp of ``artifact`` as a dict (nothing written)."""
    path = os.fspath(artifact)
    if not os.path.isfile(path):
        raise StampError("the artifact %s is not a file" % path)
    digest = file_digest(path)
    ext = os.path.splitext(path)[1].lower()
    me = {"resource_id": resource_id_for(digest), "digest": digest,
          "digest_covers": "artifact", "packaging": "file",
          "measures": {"size_bytes": os.path.getsize(path)}}
    if ext in _MEDIA:
        me["media_type"] = _MEDIA[ext]
    if ext:
        me["format"] = ext.lstrip(".")
    if label:
        me["label"] = str(label)
    if description:
        me["description"] = str(description)
    how = {"dtc_kind": str(dtc_kind)}
    if technique:
        how["technique"] = str(technique)
    how["parameters"] = dict(parameters or {})
    how["software"] = [dict(s) for s in software] + [core_line()]
    stamp = {"stamp": STAMP_VERSION, "self": me,
             "from": [input_entry(i, digests) for i in inputs], "how": how,
             "by": {"at": at or now_iso()}}
    if _dtc is not None:
        _dtc.validate_stamp(stamp)
    return stamp


def stamp_artifact(artifact, write=True, **fields):
    """Stamp a file the core made: writes ``<artifact>.stamp.json`` and returns the stamp.

    ``inputs`` — paths (hashed) or identities; ``parameters``, ``dtc_kind``,
    ``technique``, ``software`` (the host's lines, before the core's),
    ``label``, ``description``, ``at``, ``digests`` (a dict that remembers
    the digests of inputs already hashed)."""
    stamp = make_stamp(artifact, **fields)
    if write:
        target = stamp_path(artifact)
        if _dtc is not None:
            _dtc.write_stamp(stamp, target)
        else:
            with open(target, "w", encoding="utf-8") as fh:
                json.dump(stamp, fh, ensure_ascii=False, indent=1)
                fh.write("\n")
    return stamp


__all__ = ["SOURCE_NAME", "STAMP_SUFFIX", "StampError", "core_line", "file_digest", "input_entry",
           "make_stamp", "resource_id_for", "stamp_artifact", "stamp_path", "vendored_source"]
