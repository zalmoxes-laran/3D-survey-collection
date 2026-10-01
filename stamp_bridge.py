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
lookup here is the same kind of loose coupling: find the enabled add-on whose
module ends in ``em_tools`` and ask it for ``birth_stamp``; nothing is imported
at 3DSC's load time.
"""
from __future__ import annotations

import importlib
import os
import sys

#: the step kinds of the dev26 vocabulary (``dtc_kinds.process``): it has no
#: «export», «LOD» or «tiling», so the nearest are used (proposal for dev28)
KIND_EXPORT = "format_conversion"
KIND_LOD = "decimation"
KIND_TILING = "transformation"

PRODUCER_NAME = "3D Survey Collection"
NO_EMTOOLS = ("not stamped: EM Tools is not installed — the file is written "
              "without a .stamp.json")


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
    for key in keys:
        if key == "em_tools" or key.endswith(".em_tools"):
            try:
                module = importlib.import_module(key + ".birth_stamp")
            except ImportError:
                return None
            return module if hasattr(module, "stamp_blender_export") else None
    return None


def producer(birth_stamp=None):
    """``{name, version, commit}`` of 3DSC, read from its own folder."""
    folder = os.path.dirname(os.path.abspath(__file__))
    if birth_stamp is not None and hasattr(birth_stamp, "software_entry"):
        return birth_stamp.software_entry(PRODUCER_NAME, folder)
    return {"name": PRODUCER_NAME}


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
            dtc_kind=dtc_kind, technique=technique, parameters=parameters,
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
