import os
import re
import site
from contextlib import contextmanager

import bpy


FALLBACK_LOCAL_CRS = "+proj=geocent +datum=WGS84 +units=m +no_defs"


def _sanitize_name(name):
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", name).strip("._-") or "mesh"

@contextmanager
def _preserve_selection(context):
    selected_names = [obj.name for obj in context.selected_objects]
    active_name = context.active_object.name if context.active_object else None
    try:
        yield
    finally:
        bpy.ops.object.select_all(action='DESELECT')
        for name in selected_names:
            obj = bpy.data.objects.get(name)
            if obj is not None:
                obj.select_set(True)
        if active_name:
            active_obj = bpy.data.objects.get(active_name)
            if active_obj is not None:
                context.view_layer.objects.active = active_obj

def _export_obj(filepath, use_selection=True):
    """Export OBJ with compatibility across Blender operator variants."""
    if hasattr(bpy.ops.wm, "obj_export"):
        return bpy.ops.wm.obj_export(
            filepath=filepath,
            export_selected_objects=use_selection,
            export_materials=True,
        )
    if hasattr(bpy.ops.export_scene, "obj"):
        return bpy.ops.export_scene.obj(
            filepath=filepath,
            use_selection=use_selection,
        )
    raise RuntimeError("OBJ exporter operator not available in this Blender build.")

def _normalize_crs_input(crs_value):
    value = (crs_value or "").strip()
    if not value:
        return ""
    if value.upper() == "NOTSET":
        return ""
    if re.fullmatch(r"\d+", value):
        return f"EPSG:{value}"
    return value


# ---------------------------------------------------------------------------
#  PROJ / CRS helpers
# ---------------------------------------------------------------------------

def _find_proj_data_dir():
    for env_name in ("PROJ_LIB", "PROJ_DATA"):
        env_val = os.environ.get(env_name, "").strip()
        if env_val and os.path.exists(os.path.join(env_val, "proj.db")):
            return env_val
    try:
        from pyproj import datadir as pyproj_datadir
        data_dir = pyproj_datadir.get_data_dir()
        if data_dir and os.path.exists(os.path.join(data_dir, "proj.db")):
            return data_dir
    except Exception:
        pass
    for path in ("/opt/homebrew/share/proj", "/usr/local/share/proj"):
        if os.path.exists(os.path.join(path, "proj.db")):
            return path
    roots = []
    try:
        roots.append(site.getusersitepackages())
    except Exception:
        pass
    try:
        roots.extend(site.getsitepackages())
    except Exception:
        pass
    checked = set()
    for root in roots:
        if not root:
            continue
        root = os.path.abspath(root)
        for rel in ("", "share", "share/proj", "pyproj/proj_dir/share/proj"):
            cand = os.path.abspath(os.path.join(root, rel))
            if cand in checked:
                continue
            checked.add(cand)
            if os.path.exists(os.path.join(cand, "proj.db")):
                return cand
    return ""

def _crs_requires_proj_db(crs_value):
    return _normalize_crs_input(crs_value).upper().startswith("EPSG:")

def _resolve_coordinates_config(scene):
    mode = scene.cesium_coordinates_mode

    if mode == 'SHIFT_VALUES':
        crs_value = (
            _normalize_crs_input(getattr(scene, "BL_epsg", ""))
            or _normalize_crs_input(getattr(scene, "cesium_crs", ""))
        )
        if not crs_value:
            return None, "Set EPSG in SHIFT panel (or CRS in Cesium panel) for SHIFT mode."
        offset = (
            float(getattr(scene, "BL_x_shift", 0.0)),
            float(getattr(scene, "BL_y_shift", 0.0)),
            float(getattr(scene, "BL_z_shift", 0.0)),
        )
        return {
            "mode": mode,
            "crs": crs_value,
            "offset": offset,
            "requires_proj": _crs_requires_proj_db(crs_value),
        }, None

    if mode == 'CUSTOM_COORDS':
        crs_value = _normalize_crs_input(getattr(scene, "cesium_crs", ""))
        if not crs_value:
            crs_value = FALLBACK_LOCAL_CRS
        offset = (
            float(scene.cesium_offset_x),
            float(scene.cesium_offset_y),
            float(scene.cesium_offset_z),
        )
        return {
            "mode": mode,
            "crs": crs_value,
            "offset": offset,
            "requires_proj": _crs_requires_proj_db(crs_value),
        }, None

    # LOCAL_COORDS
    return {
        "mode": mode,
        "crs": FALLBACK_LOCAL_CRS,
        "offset": None,
        "requires_proj": False,
    }, None


# ---------------------------------------------------------------------------
#  UI feedback helpers
# ---------------------------------------------------------------------------

def _redraw_3d_view(context):
    try:
        for window in context.window_manager.windows:
            for area in window.screen.areas:
                if area.type == 'VIEW_3D':
                    area.tag_redraw()
        bpy.ops.wm.redraw_timer(type='DRAW_WIN_SWAP', iterations=1)
    except Exception:
        pass

def _update_cesium_progress(context, task="", current_mesh=0, total_meshes=0, elapsed=0.0):
    scene = context.scene
    if task:
        scene.cesium_progress_task = task
    if total_meshes > 0:
        scene.cesium_progress_current_mesh = current_mesh
        scene.cesium_progress_total_meshes = total_meshes
    if elapsed >= 0.0:
        scene.cesium_progress_elapsed = elapsed
    _redraw_3d_view(context)

def _add_to_cesium_log(context, message, max_lines=30):
    scene = context.scene
    msg = (message or "").strip()
    if not msg:
        return
    if scene.cesium_progress_log:
        scene.cesium_progress_log += "\n" + msg
    else:
        scene.cesium_progress_log = msg
    log_lines = scene.cesium_progress_log.split('\n')
    if len(log_lines) > max_lines:
        scene.cesium_progress_log = '\n'.join(log_lines[-max_lines:])
    _redraw_3d_view(context)


# ---------------------------------------------------------------------------
#  File / statistics helpers
# ---------------------------------------------------------------------------
