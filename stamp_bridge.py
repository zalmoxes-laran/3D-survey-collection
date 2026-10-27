"""The stamp born with the file, through EM Tools — or not at all.

E.D. (1 Oct 2026): «laddove Blender CREA asset nuovi, li può già timbrare».
3D Survey Collection creates files (LODs, glTF/glb/OBJ/FBX batches, Cesium
tilesets, .3tz) but does not carry dtcstamp: **no copy of dtcstamp lives in
3DSC**. When EM Tools is installed, its ``birth_stamp.stamp_blender_export``
writes the ``.stamp.json`` beside the file; when it is not, the file is written
without a stamp and the operator's report says so.

Measured before this module (1 Oct 2026): 3DSC called nothing of EM Tools —
zero imports, zero lookups. EM Tools reads 3DSC only through scene properties
(``georef_manager/dsc_adapter.py``, ``hasattr(scene, 'BL_x_shift')``). The
lookup here is the same kind of loose coupling: find the enabled add-on that
is EM Tools — module ending in ``em_tools``, or a package whose
``blender_manifest.toml`` says ``id = "em_tools"`` (a development link like
``bl_ext.vscode_development.EM-blender-tools``) — and ask it for
``birth_stamp``; nothing is imported at 3DSC's load time.
"""
from __future__ import annotations

import importlib
import os
import sys

#: the GESTURE of each export (s3Dgraphy dev28, ``dtc_kinds.process``, E.D.
#: 1 Oct 2026): ``lod_generation`` for a LOD, ``tiling`` for a tileset,
#: ``packing`` for a .3tz, ``export`` for the rest. Which word the stamp
#: carries is EM Tools' to say (``birth_stamp.resolve_kind``): the bundled
#: s3dgraphy before dev28 lacks these, and there the dev27 equivalents are
#: written, the gesture staying in ``technique``.
KIND_EXPORT = "export"
KIND_LOD = "lod_generation"
KIND_TILING = "tiling"
KIND_PACKING = "packing"

#: the dev27 equivalents, for an EM Tools too old to resolve a gesture itself
_BEFORE_DEV28 = {KIND_EXPORT: "format_conversion", KIND_LOD: "decimation",
                 KIND_TILING: "transformation", KIND_PACKING: "format_conversion"}

PRODUCER_NAME = "3D Survey Collection"
NO_EMTOOLS = ("not stamped: EM Tools is not installed — the file is written "
              "without a .stamp.json")


#: the ``id`` of EM Tools in its ``blender_manifest.toml``: the add-on is
#: recognised by it, whatever folder (hence add-on key) it is installed under
EMTOOLS_ID = "em_tools"


def manifest_id(folder):
    """The top-level ``id`` of ``<folder>/blender_manifest.toml``, or None
    (no manifest, unreadable, no id). Read line by line up to the first
    ``[table]``: no TOML parser needed, the id is a plain string."""
    if not folder:
        return None
    path = os.path.join(folder, "blender_manifest.toml")
    try:
        with open(path, "r", encoding="utf-8") as fh:
            for raw in fh:
                line = raw.strip()
                if line.startswith("["):
                    return None
                if line.startswith("id") and "=" in line:
                    key, value = line.split("=", 1)
                    if key.strip() != "id":
                        continue
                    value = value.split("#", 1)[0].strip()
                    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
                        return value[1:-1]
                    return None
    except OSError:
        return None
    return None


def _addon_folder(key):
    """The folder of the add-on package ``key`` without importing it: the
    loaded module's, else the one its spec points at."""
    module = sys.modules.get(key)
    path = getattr(module, "__file__", None) if module is not None else None
    if path:
        return os.path.dirname(os.path.abspath(path))
    try:
        import importlib.util
        spec = importlib.util.find_spec(key)
    except (ImportError, ValueError, AttributeError):
        return None
    if spec is None:
        return None
    locations = list(spec.submodule_search_locations or [])
    if locations:
        return locations[0]
    return os.path.dirname(spec.origin) if spec.origin else None


def addon_key_for(addon_id, keys):
    """The add-on key (module name) among ``keys`` whose package is the add-on
    ``addon_id``: the key itself or its last part when they match (legacy
    ``em_tools``, an extension ``bl_ext.<repo>.em_tools``), else the key whose
    folder carries a ``blender_manifest.toml`` with that ``id`` — a
    development link such as ``bl_ext.vscode_development.EM-blender-tools``.
    None when no enabled add-on is it."""
    keys = list(keys)
    for key in keys:
        if key == addon_id or key.endswith("." + addon_id):
            return key
    for key in keys:
        if manifest_id(_addon_folder(key)) == addon_id:
            return key
    return None


def emtools_birth_stamp():
    """EM Tools' ``birth_stamp`` module, or None (not installed, disabled, or
    too old to have it)."""
    for name, module in list(sys.modules.items()):
        if name.endswith(".birth_stamp") and hasattr(module, "stamp_blender_export"):
            return module
    try:
        import bpy
        keys = list(bpy.context.preferences.addons.keys())
    except Exception:                               # noqa: BLE001 — no preferences
        return None
    key = addon_key_for(EMTOOLS_ID, keys)
    if key is None:
        return None
    try:
        module = importlib.import_module(key + ".birth_stamp")
    except ImportError:
        return None
    return module if hasattr(module, "stamp_blender_export") else None


def producer(birth_stamp=None):
    """``{name, version, commit}`` of 3DSC, read from its own folder."""
    folder = os.path.dirname(os.path.abspath(__file__))
    if birth_stamp is not None and hasattr(birth_stamp, "software_entry"):
        return birth_stamp.software_entry(PRODUCER_NAME, folder)
    return {"name": PRODUCER_NAME}


def kind_for(module, gesture):
    """The word the stamp carries for a gesture: EM Tools' answer when it has
    ``resolve_kind`` (it knows the vocabulary it bundles), else the dev27
    equivalent — an EM Tools from before dev28 knows only those."""
    resolve = getattr(module, "resolve_kind", None) if module is not None else None
    if callable(resolve):
        return resolve(gesture)
    return _BEFORE_DEV28.get(gesture, gesture)


def stamp(path, *, objects=None, dtc_kind=KIND_EXPORT, technique="",
          parameters=None, parents=None, label=None, context=None):
    """Stamp one exported file, folder or archive. Returns EM Tools' result
    (``state``: stamped / revised / unchanged / failed / off), or
    ``{state: "no_emtools", line}`` when EM Tools is not there. Never raises."""
    module = emtools_birth_stamp()
    if module is None:
        return {"state": "no_emtools", "line": NO_EMTOOLS, "stamp_path": "", "stamp": None}
    try:
        return module.stamp_blender_export(
            path, objects=[o for o in (objects or []) if o is not None],
            dtc_kind=kind_for(module, dtc_kind), technique=technique, parameters=parameters,
            producer=producer(module), parents=parents, label=label,
            context=context)
    except Exception as exc:                        # noqa: BLE001 — a stamp never stops an export
        return {"state": "failed", "line": f"not stamped: {exc}", "stamp_path": "",
                "stamp": None}


def report_line(results):
    """One line for the operator: EM Tools' count, or why nothing was stamped."""
    results = [r for r in results if r]
    if not results:
        return ""
    if all(r["state"] == "no_emtools" for r in results):
        return f"{len(results)} file(s) " + NO_EMTOOLS
    if all(r["state"] == "off" for r in results):
        return results[0]["line"]
    module = emtools_birth_stamp()
    if module is not None and hasattr(module, "report_line"):
        return module.report_line([r for r in results
                                   if r["state"] in ("stamped", "revised", "unchanged", "failed")])
    return ""


def report(operator, results):
    """Say it in Blender: one INFO line on the operator (WARNING when a stamp
    failed), and the same line in the console."""
    line = report_line(results)
    if not line:
        return line
    print(f"[3DSC stamp] {line}")
    level = 'WARNING' if any(r and r["state"] == "failed" for r in results) else 'INFO'
    try:
        operator.report({level}, line)
    except Exception:                               # noqa: BLE001 — no operator to report on
        pass
    return line
