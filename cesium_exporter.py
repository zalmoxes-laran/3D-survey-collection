"""Cesium 3D Tiles exporter for the 3D Survey Collection addon.

Supports native spatial split (quadtree / octree) with optional hierarchical
LOD decimation.  VTK backend has been removed; all tiling is done natively
within Blender.
"""

import os
import re
import sys
import site
import json
import math
import time
import struct
import shutil
import tempfile
from contextlib import contextmanager

import bpy
import bmesh
from mathutils import Matrix, Vector

# ---------------------------------------------------------------------------
#  Constants
# ---------------------------------------------------------------------------

FALLBACK_LOCAL_CRS = "+proj=geocent +datum=WGS84 +units=m +no_defs"


# ---------------------------------------------------------------------------
#  Small helpers
# ---------------------------------------------------------------------------

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

def _snapshot_output_files(root_dir):
    files = set()
    if not root_dir or not os.path.isdir(root_dir):
        return files
    for current_root, _, names in os.walk(root_dir):
        for name in names:
            abs_path = os.path.join(current_root, name)
            rel = os.path.relpath(abs_path, root_dir).replace("\\", "/")
            files.add(rel)
    return files


def _summarize_generated_files(file_rel_paths):
    glb_count = 0
    b3dm_count = 0
    tileset_count = 0
    subtree_dirs = set()
    subtree_files = 0
    for rel in file_rel_paths:
        low = rel.lower()
        if low.endswith(".glb"):
            glb_count += 1
        elif low.endswith(".b3dm"):
            b3dm_count += 1
        elif low.endswith(".subtree"):
            subtree_files += 1
        elif low.endswith("tileset.json"):
            tileset_count += 1
            if low != "tileset.json":
                subtree_dirs.add(rel.rsplit("/", 1)[0] if "/" in rel else "")
    return {
        "glb": glb_count,
        "b3dm": b3dm_count,
        "tiles": glb_count + b3dm_count,
        "tilesets": tileset_count,
        "subtrees": len([d for d in subtree_dirs if d]) + subtree_files,
    }


# ---------------------------------------------------------------------------
#  Texture diagnostics
# ---------------------------------------------------------------------------

def _count_texture_nodes_on_object(obj):
    textures = set()
    if obj is None:
        return 0
    for slot in obj.material_slots:
        mat = slot.material
        if not mat or not mat.use_nodes or not mat.node_tree:
            continue
        for node in mat.node_tree.nodes:
            if node.type != 'TEX_IMAGE':
                continue
            image = getattr(node, "image", None)
            if image is None:
                continue
            key = bpy.path.abspath(image.filepath) if image.filepath else image.name
            textures.add(key)
    return len(textures)


def _collect_object_texture_diagnostics(obj):
    diag = {
        "uv_maps": 0,
        "materials": 0,
        "image_nodes": 0,
        "texture_images": 0,
        "missing_texture_files": 0,
        "packed_images": 0,
    }
    if obj is None:
        return diag

    mesh = getattr(obj, "data", None)
    if mesh is not None and hasattr(mesh, "uv_layers"):
        try:
            diag["uv_maps"] = len(mesh.uv_layers)
        except Exception:
            pass

    unique_images = set()
    missing_files = set()
    diag["materials"] = len(getattr(obj, "material_slots", []))
    for slot in obj.material_slots:
        mat = slot.material
        if not mat or not mat.use_nodes or not mat.node_tree:
            continue
        for node in mat.node_tree.nodes:
            if node.type != 'TEX_IMAGE':
                continue
            diag["image_nodes"] += 1
            image = getattr(node, "image", None)
            if image is None:
                continue
            key = bpy.path.abspath(image.filepath) if image.filepath else image.name
            unique_images.add(key)
            if getattr(image, "packed_file", None):
                diag["packed_images"] += 1
                continue
            abs_path = bpy.path.abspath(image.filepath) if getattr(image, "filepath", "") else ""
            if abs_path and not os.path.exists(abs_path):
                missing_files.add(abs_path)

    diag["texture_images"] = len(unique_images)
    diag["missing_texture_files"] = len(missing_files)
    return diag


# ---------------------------------------------------------------------------
#  glTF export helpers
# ---------------------------------------------------------------------------

def _build_gltf_export_kwargs(filepath, use_selection=True, export_format='GLB', export_yup=True):
    """Build kwargs for bpy.ops.export_scene.gltf.

    NOTE: export_yup is always True now (GLTF_FRAME enforced).
    """
    kwargs = {
        "filepath": filepath,
        "use_selection": bool(use_selection),
    }

    prop_names = set()
    try:
        prop_names = {p.identifier for p in bpy.ops.export_scene.gltf.get_rna_type().properties}
    except Exception:
        pass

    if export_format is not None and "export_format" in prop_names:
        kwargs["export_format"] = export_format
    if export_yup is not None and "export_yup" in prop_names:
        kwargs["export_yup"] = bool(export_yup)

    forced = (
        ("export_materials", "EXPORT"),
        ("export_texcoords", True),
        ("export_normals", True),
        ("export_colors", True),
        ("export_image_format", "AUTO"),
    )
    for key, value in forced:
        if key in prop_names:
            kwargs[key] = value

    return kwargs


def _count_texture_files_in_dir(path):
    if not path or not os.path.isdir(path):
        return 0
    exts = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".webp", ".bmp", ".exr", ".hdr"}
    count = 0
    for name in os.listdir(path):
        if os.path.splitext(name)[1].lower() in exts:
            count += 1
    return count


# ---------------------------------------------------------------------------
#  Mesh statistics collection
# ---------------------------------------------------------------------------

def _collect_mesh_stats(context, scene, job):
    stats = {
        "faces": 0,
        "vertices": 0,
        "area_m2": 0.0,
        "textures": 0,
        "uv_maps": 0,
        "materials": 0,
        "image_nodes": 0,
        "missing_texture_files": 0,
        "packed_images": 0,
    }
    if job["kind"] == "ACTIVE" and job.get("object") is not None:
        obj = job["object"]
        depsgraph = context.evaluated_depsgraph_get()
        eval_obj = obj.evaluated_get(depsgraph)
        mesh = eval_obj.to_mesh()
        if mesh is None:
            return stats
        try:
            stats["faces"] = len(mesh.polygons)
            stats["vertices"] = len(mesh.vertices)
            local_area = sum(poly.area for poly in mesh.polygons)
            scale_vec = obj.matrix_world.to_scale()
            area_scale = (
                abs(scale_vec.x * scale_vec.y) +
                abs(scale_vec.x * scale_vec.z) +
                abs(scale_vec.y * scale_vec.z)
            ) / 3.0
            world_area_bu2 = local_area * max(area_scale, 1e-9)
            scale_length = float(getattr(scene.unit_settings, "scale_length", 1.0) or 1.0)
            stats["area_m2"] = world_area_bu2 * (scale_length ** 2)
            tex_diag = _collect_object_texture_diagnostics(obj)
            stats["textures"] = tex_diag["texture_images"]
            stats["uv_maps"] = tex_diag["uv_maps"]
            stats["materials"] = tex_diag["materials"]
            stats["image_nodes"] = tex_diag["image_nodes"]
            stats["missing_texture_files"] = tex_diag["missing_texture_files"]
            stats["packed_images"] = tex_diag["packed_images"]
        finally:
            eval_obj.to_mesh_clear()
        return stats

    texture_dir = bpy.path.abspath(getattr(scene, "cesium_texture_base_dir", "")).strip()
    if not texture_dir:
        texture_dir = job.get("intermediate_dir", "")
    stats["textures"] = _count_texture_files_in_dir(texture_dir)
    return stats


def _format_cesium_mesh_stats(obj_name, mesh_stats, file_stats, duration_s):
    return (
        f"{obj_name} | faces {mesh_stats['faces']} | verts {mesh_stats['vertices']} | area {mesh_stats['area_m2']:.2f} m2 | "
        f"textures {mesh_stats['textures']} | uv {mesh_stats['uv_maps']} | missingTex {mesh_stats['missing_texture_files']} | "
        f"tiles {file_stats['tiles']} "
        f"(glb {file_stats['glb']}, b3dm {file_stats['b3dm']}) | subtrees {file_stats['subtrees']} | "
        f"tilesets {file_stats['tilesets']} | {duration_s:.1f}s"
    )


# ---------------------------------------------------------------------------
#  GLB binary patching (unlit)
# ---------------------------------------------------------------------------

def _patch_glb_to_unlit(glb_path):
    try:
        with open(glb_path, "rb") as f:
            data = f.read()
    except Exception:
        return False, "read-failed"

    if len(data) < 12:
        return False, "too-short"
    magic, version, _ = struct.unpack_from("<4sII", data, 0)
    if magic != b"glTF" or version != 2:
        return False, "not-glb2"

    chunks = []
    offset = 12
    while offset + 8 <= len(data):
        chunk_len, chunk_type = struct.unpack_from("<II", data, offset)
        offset += 8
        if offset + chunk_len > len(data):
            return False, "invalid-chunk"
        chunk_data = data[offset:offset + chunk_len]
        offset += chunk_len
        chunks.append((chunk_type, chunk_data))

    json_idx = None
    json_obj = None
    for i, (ctype, cdata) in enumerate(chunks):
        if ctype == 0x4E4F534A:  # JSON
            json_idx = i
            try:
                json_obj = json.loads(cdata.decode("utf-8"))
            except Exception:
                return False, "json-decode-failed"
            break
    if json_idx is None or json_obj is None:
        return False, "json-missing"

    mats = json_obj.get("materials")
    if not isinstance(mats, list) or not mats:
        return True, "no-materials"

    changed = False
    ext_used = json_obj.get("extensionsUsed")
    if not isinstance(ext_used, list):
        ext_used = []
        json_obj["extensionsUsed"] = ext_used
        changed = True
    if "KHR_materials_unlit" not in ext_used:
        ext_used.append("KHR_materials_unlit")
        changed = True

    for mat in mats:
        if not isinstance(mat, dict):
            continue
        ext = mat.get("extensions")
        if not isinstance(ext, dict):
            ext = {}
            mat["extensions"] = ext
            changed = True
        if "KHR_materials_unlit" not in ext:
            ext["KHR_materials_unlit"] = {}
            changed = True
        pbr = mat.get("pbrMetallicRoughness")
        if not isinstance(pbr, dict):
            pbr = {}
            mat["pbrMetallicRoughness"] = pbr
            changed = True
        if pbr.get("metallicFactor", None) != 0.0:
            pbr["metallicFactor"] = 0.0
            changed = True
        if pbr.get("roughnessFactor", None) != 1.0:
            pbr["roughnessFactor"] = 1.0
            changed = True

    if not changed:
        return True, "unchanged"

    json_bytes = json.dumps(json_obj, separators=(",", ":")).encode("utf-8")
    while len(json_bytes) % 4 != 0:
        json_bytes += b" "
    chunks[json_idx] = (0x4E4F534A, json_bytes)

    total_len = 12 + sum(8 + len(cdata) for _, cdata in chunks)
    out = bytearray()
    out += struct.pack("<4sII", b"glTF", 2, total_len)
    for ctype, cdata in chunks:
        out += struct.pack("<II", len(cdata), ctype)
        out += cdata

    try:
        with open(glb_path, "wb") as f:
            f.write(out)
    except Exception:
        return False, "write-failed"
    return True, "patched"


def _patch_output_glbs_to_unlit(output_dir):
    patched = 0
    failed = 0
    if not output_dir or not os.path.isdir(output_dir):
        return patched, failed
    for root, _, names in os.walk(output_dir):
        for name in names:
            if not name.lower().endswith(".glb"):
                continue
            ok, _ = _patch_glb_to_unlit(os.path.join(root, name))
            if ok:
                patched += 1
            else:
                failed += 1
    return patched, failed


def _strip_glb_unlit(glb_path):
    try:
        with open(glb_path, "rb") as f:
            data = f.read()
    except Exception:
        return False, "read-failed"

    if len(data) < 12:
        return False, "too-short"
    magic, version, _ = struct.unpack_from("<4sII", data, 0)
    if magic != b"glTF" or version != 2:
        return False, "not-glb2"

    chunks = []
    offset = 12
    while offset + 8 <= len(data):
        chunk_len, chunk_type = struct.unpack_from("<II", data, offset)
        offset += 8
        if offset + chunk_len > len(data):
            return False, "invalid-chunk"
        chunk_data = data[offset:offset + chunk_len]
        offset += chunk_len
        chunks.append((chunk_type, chunk_data))

    json_idx = None
    json_obj = None
    for i, (ctype, cdata) in enumerate(chunks):
        if ctype == 0x4E4F534A:  # JSON
            json_idx = i
            try:
                json_obj = json.loads(cdata.decode("utf-8"))
            except Exception:
                return False, "json-decode-failed"
            break
    if json_idx is None or json_obj is None:
        return False, "json-missing"

    changed = False
    for ext_key in ("extensionsUsed", "extensionsRequired"):
        ext_list = json_obj.get(ext_key)
        if isinstance(ext_list, list) and "KHR_materials_unlit" in ext_list:
            ext_list[:] = [x for x in ext_list if x != "KHR_materials_unlit"]
            changed = True
            if not ext_list:
                json_obj.pop(ext_key, None)

    mats = json_obj.get("materials")
    if isinstance(mats, list):
        for mat in mats:
            if not isinstance(mat, dict):
                continue
            ext = mat.get("extensions")
            if isinstance(ext, dict) and "KHR_materials_unlit" in ext:
                ext.pop("KHR_materials_unlit", None)
                changed = True
                if not ext:
                    mat.pop("extensions", None)

    if not changed:
        return True, "unchanged"

    json_bytes = json.dumps(json_obj, separators=(",", ":")).encode("utf-8")
    while len(json_bytes) % 4 != 0:
        json_bytes += b" "
    chunks[json_idx] = (0x4E4F534A, json_bytes)

    total_len = 12 + sum(8 + len(cdata) for _, cdata in chunks)
    out = bytearray()
    out += struct.pack("<4sII", b"glTF", 2, total_len)
    for ctype, cdata in chunks:
        out += struct.pack("<II", len(cdata), ctype)
        out += cdata

    try:
        with open(glb_path, "wb") as f:
            f.write(out)
    except Exception:
        return False, "write-failed"
    return True, "stripped"


def _strip_output_glbs_unlit(output_dir):
    stripped = 0
    failed = 0
    if not output_dir or not os.path.isdir(output_dir):
        return stripped, failed
    for root, _, names in os.walk(output_dir):
        for name in names:
            if not name.lower().endswith(".glb"):
                continue
            ok, _ = _strip_glb_unlit(os.path.join(root, name))
            if ok:
                stripped += 1
            else:
                failed += 1
    return stripped, failed


# ---------------------------------------------------------------------------
#  Bounding-box helpers
# ---------------------------------------------------------------------------

def _bbox_union_from_face_ids(face_ids, face_mins, face_maxs):
    first = face_ids[0]
    min_x, min_y, min_z = face_mins[first]
    max_x, max_y, max_z = face_maxs[first]
    for face_id in face_ids[1:]:
        fmin = face_mins[face_id]
        fmax = face_maxs[face_id]
        min_x = min(min_x, fmin[0])
        min_y = min(min_y, fmin[1])
        min_z = min(min_z, fmin[2])
        max_x = max(max_x, fmax[0])
        max_y = max(max_y, fmax[1])
        max_z = max(max_z, fmax[2])
    return (min_x, min_y, min_z), (max_x, max_y, max_z)


def _bbox_to_box(bbox):
    (min_x, min_y, min_z), (max_x, max_y, max_z) = bbox
    cx = (min_x + max_x) * 0.5
    cy = (min_y + max_y) * 0.5
    cz = (min_z + max_z) * 0.5
    hx = max((max_x - min_x) * 0.5, 1e-6)
    hy = max((max_y - min_y) * 0.5, 1e-6)
    hz = max((max_z - min_z) * 0.5, 1e-6)
    return [cx, cy, cz, hx, 0.0, 0.0, 0.0, hy, 0.0, 0.0, 0.0, hz]


def _bbox_diag_len(bbox):
    (min_x, min_y, min_z), (max_x, max_y, max_z) = bbox
    return math.sqrt((max_x - min_x) ** 2 + (max_y - min_y) ** 2 + (max_z - min_z) ** 2)


def _normalize_parent_tileset_name(name):
    value = os.path.basename((name or "").strip())
    if not value:
        value = "tileset.json"
    if not value.lower().endswith(".json"):
        value += ".json"
    return value


def _aabb_from_3dtiles_box(box_vals):
    if not isinstance(box_vals, (list, tuple)) or len(box_vals) != 12:
        return None
    try:
        vals = [float(v) for v in box_vals]
    except Exception:
        return None
    cx, cy, cz = vals[0], vals[1], vals[2]
    x_axis = vals[3:6]
    y_axis = vals[6:9]
    z_axis = vals[9:12]
    ex = abs(x_axis[0]) + abs(y_axis[0]) + abs(z_axis[0])
    ey = abs(x_axis[1]) + abs(y_axis[1]) + abs(z_axis[1])
    ez = abs(x_axis[2]) + abs(y_axis[2]) + abs(z_axis[2])
    return ((cx - ex, cy - ey, cz - ez), (cx + ex, cy + ey, cz + ez))


def _bbox_union_many(bboxes):
    if not bboxes:
        return None
    min_x, min_y, min_z = bboxes[0][0]
    max_x, max_y, max_z = bboxes[0][1]
    for bbox in bboxes[1:]:
        (bx0, by0, bz0), (bx1, by1, bz1) = bbox
        min_x = min(min_x, bx0)
        min_y = min(min_y, by0)
        min_z = min(min_z, bz0)
        max_x = max(max_x, bx1)
        max_y = max(max_y, by1)
        max_z = max(max_z, bz1)
    return ((min_x, min_y, min_z), (max_x, max_y, max_z))


# ---------------------------------------------------------------------------
#  Parent tileset stitcher
# ---------------------------------------------------------------------------

def _scan_child_tilesets(output_root, parent_name):
    parent_abs = os.path.abspath(os.path.join(output_root, parent_name))
    entries = []
    for entry in sorted(os.listdir(output_root)):
        child_dir = os.path.join(output_root, entry)
        if not os.path.isdir(child_dir):
            continue
        child_tileset = os.path.join(child_dir, "tileset.json")
        if not os.path.isfile(child_tileset):
            continue
        if os.path.abspath(child_tileset) == parent_abs:
            continue
        entries.append((entry, child_tileset, f"{entry}/tileset.json"))
    return entries


def _build_parent_tileset(output_root, parent_name):
    parent_name = _normalize_parent_tileset_name(parent_name)
    if not output_root or not os.path.isdir(output_root):
        return False, "Output folder does not exist.", "", 0, 0

    child_entries = _scan_child_tilesets(output_root, parent_name)
    if not child_entries:
        return False, "No child tilesets found in output subfolders.", "", 0, 0

    children = []
    bboxes = []
    child_errors = []
    skipped = 0

    for _, child_tileset_path, child_uri in child_entries:
        try:
            with open(child_tileset_path, "r", encoding="utf-8") as f:
                child_data = json.load(f)
        except Exception:
            skipped += 1
            continue

        root = child_data.get("root")
        if not isinstance(root, dict):
            skipped += 1
            continue
        bounding_volume = root.get("boundingVolume", {})
        box_vals = bounding_volume.get("box")
        bbox = _aabb_from_3dtiles_box(box_vals)
        if bbox is None:
            skipped += 1
            continue

        child_error = float(child_data.get("geometricError", root.get("geometricError", 0.0)) or 0.0)
        children.append(
            {
                "boundingVolume": {"box": box_vals},
                "geometricError": max(child_error, 0.0),
                "refine": "REPLACE",
                "content": {"uri": child_uri},
            }
        )
        bboxes.append(bbox)
        child_errors.append(max(child_error, 0.0))

    if not children:
        return False, "Child tilesets found, but none had a valid root boundingVolume.box.", "", 0, skipped

    union_bbox = _bbox_union_many(bboxes)
    if union_bbox is None:
        return False, "Unable to compute parent bounding volume.", "", 0, skipped

    max_child_error = max(child_errors) if child_errors else 0.0
    root_error = max(max_child_error, max(_bbox_diag_len(union_bbox), 1.0))
    parent_tileset = {
        "asset": {"version": "1.1"},
        "geometricError": root_error,
        "root": {
            "boundingVolume": {"box": _bbox_to_box(union_bbox)},
            "geometricError": root_error,
            "refine": "REPLACE",
            "children": children,
        },
    }

    parent_path = os.path.join(output_root, parent_name)
    with open(parent_path, "w", encoding="utf-8") as f:
        json.dump(parent_tileset, f, indent=2)

    return True, f"Parent tileset rebuilt with {len(children)} child tileset(s).", parent_path, len(children), skipped


# ---------------------------------------------------------------------------
#  Mesh preparation / cleanup helpers
# ---------------------------------------------------------------------------

def _prepare_base_mesh_object(context, active_obj, offset):
    temp_collection = bpy.data.collections.get("_cesium_native_tmp")
    if temp_collection is None:
        temp_collection = bpy.data.collections.new("_cesium_native_tmp")
        context.scene.collection.children.link(temp_collection)

    base_obj = active_obj.copy()
    base_obj.data = active_obj.data.copy()
    temp_collection.objects.link(base_obj)

    base_obj.data.transform(active_obj.matrix_world)
    if offset is not None:
        base_obj.data.transform(Matrix.Translation(Vector(offset)))
    base_obj.matrix_world = Matrix.Identity(4)

    return base_obj, temp_collection


def _cleanup_native_bake_assets(bake_info):
    if not isinstance(bake_info, dict):
        return

    for mat_name in bake_info.get("temp_materials", []) or []:
        mat = bpy.data.materials.get(mat_name)
        if mat is not None and mat.users == 0:
            try:
                bpy.data.materials.remove(mat, do_unlink=True)
            except Exception:
                pass

    baked_mat_name = bake_info.get("baked_material", "")
    if baked_mat_name:
        mat = bpy.data.materials.get(baked_mat_name)
        if mat is not None and mat.users == 0:
            try:
                bpy.data.materials.remove(mat, do_unlink=True)
            except Exception:
                pass

    baked_img_name = bake_info.get("baked_image", "")
    if baked_img_name:
        img = bpy.data.images.get(baked_img_name)
        if img is not None and img.users == 0:
            try:
                bpy.data.images.remove(img, do_unlink=True)
            except Exception:
                pass


# ===========================================================================
#  BLOCK B: Bake + Spatial + Tree Building + LOD
# ===========================================================================

# ---------------------------------------------------------------------------
#  Texture atlas baking (Cycles)
# ---------------------------------------------------------------------------

def _native_bake_basecolor_texture(context, scene, base_obj, atlas_size, margin_px):
    bake_info = {
        "enabled": True,
        "applied": False,
        "atlas_size": int(atlas_size),
        "margin_px": int(margin_px),
        "source_texture_images": 0,
        "source_image_nodes": 0,
        "temp_materials": [],
        "baked_material": "",
        "baked_image": "",
    }

    mesh = getattr(base_obj, "data", None)
    if mesh is None or len(mesh.polygons) == 0:
        return False, "Mesh is empty, cannot bake textures.", bake_info

    diag = _collect_object_texture_diagnostics(base_obj)
    bake_info["source_texture_images"] = int(diag.get("texture_images", 0))
    bake_info["source_image_nodes"] = int(diag.get("image_nodes", 0))
    if bake_info["source_texture_images"] <= 0:
        return True, "No source texture images found: bake skipped.", bake_info

    local_materials = []
    for idx, slot in enumerate(base_obj.material_slots):
        mat = slot.material
        if mat is None:
            continue
        mat_copy = mat.copy()
        mat_copy.name = f"__CesiumBakeSrc_{_sanitize_name(base_obj.name)}_{idx:03d}"
        slot.material = mat_copy
        local_materials.append(mat_copy)
        bake_info["temp_materials"].append(mat_copy.name)

    if not local_materials:
        return True, "No materials on source mesh: bake skipped.", bake_info

    uv_layer = mesh.uv_layers.get("__CesiumBakeUV")
    if uv_layer is None:
        uv_layer = mesh.uv_layers.new(name="__CesiumBakeUV")
    mesh.uv_layers.active = uv_layer
    if hasattr(uv_layer, "active_render"):
        uv_layer.active_render = True

    image_name = f"__CesiumBakeAtlas_{_sanitize_name(base_obj.name)}"
    bake_image = bpy.data.images.new(
        name=image_name,
        width=int(atlas_size),
        height=int(atlas_size),
        alpha=True,
        float_buffer=False,
    )
    bake_image.generated_color = (1.0, 1.0, 1.0, 1.0)
    bake_info["baked_image"] = bake_image.name

    target_nodes = []
    for mat in local_materials:
        if not mat.use_nodes:
            mat.use_nodes = True
        nt = mat.node_tree
        if nt is None:
            continue
        for node in nt.nodes:
            node.select = False
        tex_node = nt.nodes.new("ShaderNodeTexImage")
        tex_node.name = "__CesiumBakeTarget"
        tex_node.label = "Cesium Bake Target"
        tex_node.image = bake_image
        tex_node.select = True
        nt.nodes.active = tex_node
        target_nodes.append(tex_node)

    if not target_nodes:
        return False, "No valid material node trees available for bake.", bake_info

    previous_engine = scene.render.engine
    previous_bake_margin = int(getattr(scene.render.bake, "margin", int(margin_px)))
    previous_bake_use_clear = bool(getattr(scene.render.bake, "use_clear", True))
    previous_bake_selected_to_active = bool(getattr(scene.render.bake, "use_selected_to_active", False))
    previous_cycles_samples = None
    if hasattr(scene, "cycles"):
        previous_cycles_samples = int(getattr(scene.cycles, "samples", 1))

    try:
        with _preserve_selection(context):
            if getattr(context, "mode", "OBJECT") != 'OBJECT':
                bpy.ops.object.mode_set(mode='OBJECT')
            bpy.ops.object.select_all(action='DESELECT')
            base_obj.hide_set(False)
            base_obj.hide_viewport = False
            base_obj.hide_render = False
            base_obj.select_set(True)
            context.view_layer.objects.active = base_obj

            bpy.ops.object.mode_set(mode='EDIT')
            bpy.ops.mesh.select_all(action='SELECT')
            bpy.ops.uv.smart_project(angle_limit=66.0, island_margin=0.02)
            bpy.ops.object.mode_set(mode='OBJECT')

            scene.render.engine = 'CYCLES'
            scene.render.bake.margin = int(margin_px)
            scene.render.bake.use_clear = True
            if hasattr(scene.render.bake, "use_selected_to_active"):
                scene.render.bake.use_selected_to_active = False
            if previous_cycles_samples is not None:
                scene.cycles.samples = 1

            result = bpy.ops.object.bake(
                type='DIFFUSE',
                pass_filter={'COLOR'},
                use_clear=True,
                margin=int(margin_px),
            )
            if 'FINISHED' not in result:
                return False, "Bake operator failed.", bake_info
    except Exception as exc:
        return False, f"Bake failed: {exc}", bake_info
    finally:
        try:
            if getattr(context, "mode", "OBJECT") != 'OBJECT':
                bpy.ops.object.mode_set(mode='OBJECT')
        except Exception:
            pass
        try:
            scene.render.engine = previous_engine
        except Exception:
            pass
        try:
            scene.render.bake.margin = previous_bake_margin
            scene.render.bake.use_clear = previous_bake_use_clear
            if hasattr(scene.render.bake, "use_selected_to_active"):
                scene.render.bake.use_selected_to_active = previous_bake_selected_to_active
        except Exception:
            pass
        if previous_cycles_samples is not None:
            try:
                scene.cycles.samples = previous_cycles_samples
            except Exception:
                pass

    try:
        bake_image.pack()
    except Exception:
        pass

    baked_mat = bpy.data.materials.new(name=f"CesiumBaked_{_sanitize_name(base_obj.name)}")
    baked_mat.use_nodes = True
    nt = baked_mat.node_tree
    nt.nodes.clear()
    out_node = nt.nodes.new("ShaderNodeOutputMaterial")
    bsdf_node = nt.nodes.new("ShaderNodeBsdfPrincipled")
    tex_node = nt.nodes.new("ShaderNodeTexImage")
    tex_node.image = bake_image
    tex_node.location = (-500, 0)
    bsdf_node.location = (-250, 0)
    out_node.location = (20, 0)
    if "Metallic" in bsdf_node.inputs:
        bsdf_node.inputs["Metallic"].default_value = 0.0
    if "Roughness" in bsdf_node.inputs:
        bsdf_node.inputs["Roughness"].default_value = 1.0
    if "Color" in tex_node.outputs and "Base Color" in bsdf_node.inputs:
        nt.links.new(tex_node.outputs["Color"], bsdf_node.inputs["Base Color"])
    if "Alpha" in tex_node.outputs and "Alpha" in bsdf_node.inputs:
        nt.links.new(tex_node.outputs["Alpha"], bsdf_node.inputs["Alpha"])
    if "BSDF" in bsdf_node.outputs and "Surface" in out_node.inputs:
        nt.links.new(bsdf_node.outputs["BSDF"], out_node.inputs["Surface"])

    bake_info["baked_material"] = baked_mat.name
    mesh.materials.clear()
    mesh.materials.append(baked_mat)
    for poly in mesh.polygons:
        poly.material_index = 0
    mesh.update()

    for mat_name in list(bake_info.get("temp_materials", [])):
        mat = bpy.data.materials.get(mat_name)
        if mat is not None and mat.users == 0:
            try:
                bpy.data.materials.remove(mat, do_unlink=True)
            except Exception:
                pass

    bake_info["applied"] = True
    return True, f"Baked {bake_info['source_texture_images']} source texture(s) to {int(atlas_size)}px atlas.", bake_info


# ---------------------------------------------------------------------------
#  Spatial data + tree building
# ---------------------------------------------------------------------------

def _build_face_spatial_data(mesh, to_gltf_yup=True):
    """Build per-face centroids and bounding boxes.

    to_gltf_yup is always True (GLTF_FRAME enforced).
    """
    verts = []
    for v in mesh.vertices:
        co = v.co.copy()
        if to_gltf_yup:
            co = Vector((co.x, co.z, -co.y))
        verts.append(co)
    centroids = {}
    face_mins = {}
    face_maxs = {}
    face_ids = []

    for poly in mesh.polygons:
        vidx = poly.vertices
        xs = [verts[i].x for i in vidx]
        ys = [verts[i].y for i in vidx]
        zs = [verts[i].z for i in vidx]
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)
        min_z, max_z = min(zs), max(zs)
        centroids[poly.index] = (
            sum(xs) / len(xs),
            sum(ys) / len(ys),
            sum(zs) / len(zs),
        )
        face_mins[poly.index] = (min_x, min_y, min_z)
        face_maxs[poly.index] = (max_x, max_y, max_z)
        face_ids.append(poly.index)

    return face_ids, centroids, face_mins, face_maxs


def _split_face_ids(face_ids, centroids, bbox, tree_type):
    (min_x, min_y, min_z), (max_x, max_y, max_z) = bbox
    mid_x = (min_x + max_x) * 0.5
    mid_y = (min_y + max_y) * 0.5
    mid_z = (min_z + max_z) * 0.5

    bins = {}
    groups = []
    if tree_type == 'OCTREE':
        for fid in face_ids:
            cx, cy, cz = centroids[fid]
            ix = 1 if cx >= mid_x else 0
            iy = 1 if cy >= mid_y else 0
            iz = 1 if cz >= mid_z else 0
            slot = ix + (iy * 2) + (iz * 4)
            bins.setdefault(slot, []).append(fid)
        for slot in range(8):
            vals = bins.get(slot)
            if vals:
                groups.append((slot, vals))
    else:
        for fid in face_ids:
            cx, cy, _ = centroids[fid]
            ix = 1 if cx >= mid_x else 0
            iy = 1 if cy >= mid_y else 0
            slot = ix + (iy * 2)
            bins.setdefault(slot, []).append(fid)
        for slot in range(4):
            vals = bins.get(slot)
            if vals:
                groups.append((slot, vals))

    return groups


def _child_split_bbox(parent_bbox, slot, tree_type):
    (min_x, min_y, min_z), (max_x, max_y, max_z) = parent_bbox
    mid_x = (min_x + max_x) * 0.5
    mid_y = (min_y + max_y) * 0.5
    mid_z = (min_z + max_z) * 0.5

    ix = slot & 1
    iy = (slot >> 1) & 1
    iz = (slot >> 2) & 1

    cmin_x = mid_x if ix else min_x
    cmax_x = max_x if ix else mid_x
    cmin_y = mid_y if iy else min_y
    cmax_y = max_y if iy else mid_y

    if tree_type == 'OCTREE':
        cmin_z = mid_z if iz else min_z
        cmax_z = max_z if iz else mid_z
    else:
        cmin_z = min_z
        cmax_z = max_z

    return (cmin_x, cmin_y, cmin_z), (cmax_x, cmax_y, cmax_z)


def _build_native_tree(
    face_ids, depth, tree_type, max_faces, min_depth, max_depth,
    centroids, face_mins, face_maxs,
    path_code="", grid_x=0, grid_y=0, grid_z=0, split_bbox=None,
):
    bbox = _bbox_union_from_face_ids(face_ids, face_mins, face_maxs)
    node = {
        "depth": depth,
        "path_code": path_code,
        "grid_x": int(grid_x),
        "grid_y": int(grid_y),
        "grid_z": int(grid_z),
        "bbox": bbox,
        "face_ids": face_ids,
        "children": [],
    }

    should_split = (depth < max_depth) and (depth < min_depth or len(face_ids) > max_faces)
    if not should_split:
        return node

    split_basis_bbox = split_bbox if split_bbox is not None else bbox
    split_groups = _split_face_ids(face_ids, centroids, split_basis_bbox, tree_type)
    if len(split_groups) <= 1:
        return node

    for slot, group in split_groups:
        child_x = (grid_x * 2) + (slot & 1)
        child_y = (grid_y * 2) + ((slot >> 1) & 1)
        if tree_type == 'OCTREE':
            child_z = (grid_z * 2) + ((slot >> 2) & 1)
        else:
            child_z = grid_z
        child_split_bbox = _child_split_bbox(split_basis_bbox, slot, tree_type) if split_bbox is not None else None
        child = _build_native_tree(
            face_ids=group,
            depth=depth + 1,
            tree_type=tree_type,
            max_faces=max_faces,
            min_depth=min_depth,
            max_depth=max_depth,
            centroids=centroids,
            face_mins=face_mins,
            face_maxs=face_maxs,
            path_code=f"{path_code}{slot}",
            grid_x=child_x,
            grid_y=child_y,
            grid_z=child_z,
            split_bbox=child_split_bbox,
        )
        node["children"].append(child)

    return node


def _collect_native_leaves(node, out):
    if not node["children"]:
        out.append(node)
        return
    for child in node["children"]:
        _collect_native_leaves(child, out)


def _collect_native_nodes(node, out):
    out.append(node)
    for child in node.get("children", []):
        _collect_native_nodes(child, out)


def _collect_nodes_at_depth(node, depth, out):
    if node["depth"] == depth:
        out.append(node)
        return
    for child in node.get("children", []):
        _collect_nodes_at_depth(child, depth, out)


# ---------------------------------------------------------------------------
#  LOD auto-parametrization
# ---------------------------------------------------------------------------

def _pow2_round(x):
    """Round x up to the nearest power of 2, clamped to [64, 8192]."""
    if x <= 64:
        return 64
    p = 64
    while p < x and p < 8192:
        p *= 2
    return p


def _compute_lod_parameters(total_faces, area_m2, max_tex_res, tree_type, scene):
    """Compute LOD depth and per-level decimation/atlas parameters.

    Args:
        total_faces: total polygon count of the mesh
        area_m2: surface area in square metres
        max_tex_res: maximum texture resolution of source images (pixels, e.g. 4096)
        tree_type: 'OCTREE' or 'QUADTREE'
        scene: Blender scene (for user overrides)

    Returns:
        dict with 'max_depth', 'features_per_tile', 'lod_levels' list
    """
    auto_params = bool(getattr(scene, "cesium_lod_auto_params", True))
    leaf_atlas = int(getattr(scene, "cesium_lod_leaf_atlas_size", 1024))
    root_atlas = int(getattr(scene, "cesium_lod_root_atlas_size", 256))

    if auto_params:
        # Auto depth: balance texture resolution with atlas size
        # mean_res_tex_m is in mm/pixel from qualitycheck; convert to m/pixel
        if area_m2 > 0 and max_tex_res > 0:
            bbox_side_estimate = math.sqrt(area_m2)
            # How many leaf_atlas-sized tiles we need per axis?
            tiles_per_axis = max(bbox_side_estimate * 1000.0 / (leaf_atlas * 1.0), 1.0)  # rough
            if tree_type == 'OCTREE':
                max_depth = max(1, min(int(math.ceil(math.log2(tiles_per_axis))), 8))
            else:
                max_depth = max(1, min(int(math.ceil(math.log2(tiles_per_axis))), 10))
        else:
            max_depth = 4

        # Features per tile: target ~8000 faces per leaf
        branching = 8 if tree_type == 'OCTREE' else 4
        features_per_tile = max(2000, int(total_faces / max(branching ** max_depth, 1)))
        features_per_tile = min(features_per_tile, 25000)
    else:
        max_depth = int(getattr(scene, "cesium_native_max_depth", 6))
        features_per_tile = int(scene.cesium_features_per_tile)

    # Build per-level config
    levels = []
    for d in range(max_depth + 1):
        t = d / max(max_depth, 1)  # 0.0 = root, 1.0 = leaf
        # Exponential interpolation for atlas size
        atlas_size = _pow2_round(root_atlas * ((leaf_atlas / max(root_atlas, 1)) ** t))
        atlas_size = max(root_atlas, min(atlas_size, leaf_atlas))
        # Decimation ratio: leaf=1.0, root=small fraction
        if d == max_depth:
            decimation_ratio = 1.0
        else:
            # Ratio decreases as we go up the tree
            decimation_ratio = max(0.01, (atlas_size / leaf_atlas) ** 2)
        levels.append({
            "depth": d,
            "decimation_ratio": round(decimation_ratio, 4),
            "atlas_size": int(atlas_size),
        })

    return {
        "max_depth": max_depth,
        "features_per_tile": features_per_tile,
        "lod_levels": levels,
    }


def _prepare_lod_image_cache(source_image, lod_config):
    """Create downsampled copies of the baked atlas for each LOD level.

    Returns dict {atlas_size_px: bpy.types.Image}.
    """
    cache = {}
    if source_image is None:
        return cache

    source_w = source_image.size[0]
    source_h = source_image.size[1]
    if source_w == 0 or source_h == 0:
        return cache

    # The source image is the leaf atlas (largest)
    cache[source_w] = source_image

    needed_sizes = set()
    for level in lod_config.get("lod_levels", []):
        sz = int(level["atlas_size"])
        if sz != source_w and sz > 0:
            needed_sizes.add(sz)

    for sz in sorted(needed_sizes, reverse=True):
        img_name = f"__CesiumLOD_{sz}px"
        existing = bpy.data.images.get(img_name)
        if existing is not None:
            try:
                bpy.data.images.remove(existing, do_unlink=True)
            except Exception:
                pass

        # Copy the source image pixels and scale down
        lod_img = source_image.copy()
        lod_img.name = img_name
        lod_img.scale(sz, sz)
        try:
            lod_img.pack()
        except Exception:
            pass
        cache[sz] = lod_img

    return cache


def _cleanup_lod_image_cache(cache, keep_source=True):
    """Remove LOD images from bpy.data.images."""
    if not cache:
        return
    for sz, img in list(cache.items()):
        if keep_source and not img.name.startswith("__CesiumLOD_"):
            continue
        if img is not None and img.users == 0:
            try:
                bpy.data.images.remove(img, do_unlink=True)
            except Exception:
                pass


# ===========================================================================
#  BLOCK C: Implicit Tiling, Export, Main Pipeline
# ===========================================================================

# ---------------------------------------------------------------------------
#  Implicit tiling helpers (Morton codes, subtree files)
# ---------------------------------------------------------------------------

def _implicit_level_offset(level, tree_type):
    if level <= 0:
        return 0
    if tree_type == 'OCTREE':
        return ((8 ** level) - 1) // 7
    return ((4 ** level) - 1) // 3


def _implicit_total_nodes(level_count, tree_type):
    return _implicit_level_offset(level_count, tree_type)


def _implicit_morton_index(node, tree_type):
    depth = int(node.get("depth", 0))
    x = int(node.get("grid_x", 0))
    y = int(node.get("grid_y", 0))
    z = int(node.get("grid_z", 0))

    morton = 0
    if tree_type == 'OCTREE':
        for bit in range(depth - 1, -1, -1):
            slot = ((x >> bit) & 1) + (((y >> bit) & 1) << 1) + (((z >> bit) & 1) << 2)
            morton = (morton << 3) + slot
    else:
        for bit in range(depth - 1, -1, -1):
            slot = ((x >> bit) & 1) + (((y >> bit) & 1) << 1)
            morton = (morton << 2) + slot
    return morton


def _bitarray_set_once(bitarr, bit_idx):
    byte_idx = bit_idx // 8
    mask = 1 << (bit_idx % 8)
    old = bitarr[byte_idx]
    if old & mask:
        return False
    bitarr[byte_idx] = old | mask
    return True


def _write_subtree_file(subtree_path, tile_bits, tile_count, content_bits, content_count):
    streams = []
    stream_map = {}
    stream_offsets = []
    cursor = 0

    for bits in (tile_bits, content_bits):
        key = bytes(bits)
        idx = stream_map.get(key)
        if idx is None:
            idx = len(streams)
            stream_map[key] = idx
            streams.append(key)
            stream_offsets.append(cursor)
            cursor += len(key)

    buffer_views = []
    for i, blob in enumerate(streams):
        buffer_views.append({
            "buffer": 0,
            "byteOffset": stream_offsets[i],
            "byteLength": len(blob),
        })

    tile_view_idx = stream_map[bytes(tile_bits)]
    content_view_idx = stream_map[bytes(content_bits)]
    bin_blob = b"".join(streams)

    subtree_json = {
        "buffers": [{"byteLength": len(bin_blob)}],
        "bufferViews": buffer_views,
        "tileAvailability": {
            "bitstream": tile_view_idx,
            "availableCount": int(tile_count),
        },
        "contentAvailability": [{
            "bitstream": content_view_idx,
            "availableCount": int(content_count),
        }],
        "childSubtreeAvailability": {
            "constant": 0,
            "availableCount": 0,
        },
    }

    json_blob = json.dumps(subtree_json, separators=(",", ":")).encode("utf-8")
    while len(json_blob) % 8 != 0:
        json_blob += b" "
    while len(bin_blob) % 8 != 0:
        bin_blob += b"\x00"

    os.makedirs(os.path.dirname(subtree_path), exist_ok=True)
    with open(subtree_path, "wb") as f:
        f.write(struct.pack("<4sIQQ", b"subt", 1, len(json_blob), len(bin_blob)))
        f.write(json_blob)
        f.write(bin_blob)


# ---------------------------------------------------------------------------
#  GLB export for a single node (leaf or internal with LOD)
# ---------------------------------------------------------------------------

def _export_node_glb(
    context, base_obj, temp_collection, keep_face_ids, filepath,
    force_unlit=False, export_yup=True,
    decimation_ratio=1.0, preserve_borders=True,
    lod_image=None,
):
    """Export a GLB for a tree node.

    For leaf nodes: decimation_ratio=1.0, lod_image=None (uses full mesh+texture).
    For internal LOD nodes: decimation_ratio<1.0, lod_image=downsampled atlas.
    """
    tile_obj = base_obj.copy()
    tile_obj.data = base_obj.data.copy()
    tile_obj_name = tile_obj.name
    tile_mesh_name = tile_obj.data.name
    temp_collection.objects.link(tile_obj)

    try:
        # 1) Keep only faces belonging to this node
        keep_set = set(keep_face_ids)
        bm = bmesh.new()
        bm.from_mesh(tile_obj.data)
        bm.faces.ensure_lookup_table()
        to_delete = [f for f in bm.faces if f.index not in keep_set]
        if to_delete:
            bmesh.ops.delete(bm, geom=to_delete, context='FACES')
        bm.to_mesh(tile_obj.data)
        bm.free()
        tile_obj.data.update()

        if len(tile_obj.data.polygons) == 0:
            return False

        # 2) Apply decimation if ratio < 1.0 (LOD internal node)
        if decimation_ratio < 0.999 and len(tile_obj.data.polygons) > 10:
            with _preserve_selection(context):
                bpy.ops.object.select_all(action='DESELECT')
                tile_obj.select_set(True)
                context.view_layer.objects.active = tile_obj

                # Preserve border edges via vertex group
                if preserve_borders:
                    bpy.ops.object.mode_set(mode='EDIT')
                    bpy.ops.mesh.select_all(action='DESELECT')
                    bpy.ops.mesh.select_mode(type="VERT")
                    bpy.ops.mesh.select_non_manifold()
                    bpy.ops.object.vertex_group_add()
                    bpy.ops.object.vertex_group_assign()
                    bpy.ops.object.mode_set(mode='OBJECT')

                    mod = tile_obj.modifiers.new("Decimate", type='DECIMATE')
                    mod.ratio = max(decimation_ratio, 0.01)
                    if tile_obj.vertex_groups:
                        mod.vertex_group = tile_obj.vertex_groups[0].name
                        mod.invert_vertex_group = True
                else:
                    mod = tile_obj.modifiers.new("Decimate", type='DECIMATE')
                    mod.ratio = max(decimation_ratio, 0.01)

                bpy.ops.object.modifier_apply(modifier="Decimate")

            if len(tile_obj.data.polygons) == 0:
                return False

        # 3) Swap texture to LOD-sized atlas if provided
        if lod_image is not None:
            for slot in tile_obj.material_slots:
                mat = slot.material
                if mat is None or not mat.use_nodes or mat.node_tree is None:
                    continue
                for node in mat.node_tree.nodes:
                    if node.type == 'TEX_IMAGE' and node.image is not None:
                        node.image = lod_image

        # 4) Export as GLB
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        with _preserve_selection(context):
            bpy.ops.object.select_all(action='DESELECT')
            tile_obj.select_set(True)
            context.view_layer.objects.active = tile_obj
            result = bpy.ops.export_scene.gltf(
                **_build_gltf_export_kwargs(
                    filepath=filepath,
                    use_selection=True,
                    export_format='GLB',
                    export_yup=export_yup,
                )
            )
        ok = 'FINISHED' in result
        if ok and force_unlit:
            _patch_glb_to_unlit(filepath)
        return ok
    finally:
        obj = bpy.data.objects.get(tile_obj_name)
        if obj is not None:
            try:
                bpy.data.objects.remove(obj, do_unlink=True)
            except Exception:
                pass
        mesh = bpy.data.meshes.get(tile_mesh_name)
        if mesh is not None and mesh.users == 0:
            try:
                bpy.data.meshes.remove(mesh, do_unlink=True)
            except Exception:
                pass


# ---------------------------------------------------------------------------
#  Tileset JSON generation
# ---------------------------------------------------------------------------

def _native_tree_to_tileset_node(node, root_error, base_depth=0, external_subtree_map=None):
    tile = {
        "boundingVolume": {"box": _bbox_to_box(node["bbox"])},
        "geometricError": 0.0,
    }

    local_depth = max(node["depth"] - base_depth, 0)
    node_key = id(node)
    if external_subtree_map and node_key in external_subtree_map:
        tile["geometricError"] = root_error / (2 ** max(local_depth, 0))
        tile["refine"] = "REPLACE"
        tile["content"] = {"uri": external_subtree_map[node_key]}
        return tile

    uri = node.get("uri")
    if uri:
        tile["content"] = {"uri": uri}

    if node["children"]:
        tile["geometricError"] = root_error / (2 ** max(local_depth, 0))
        tile["refine"] = "REPLACE"
        tile["children"] = [
            _native_tree_to_tileset_node(
                child,
                root_error=root_error,
                base_depth=base_depth,
                external_subtree_map=external_subtree_map,
            )
            for child in node["children"]
        ]
    return tile


# ---------------------------------------------------------------------------
#  Implicit tiling layout
# ---------------------------------------------------------------------------

def _run_native_implicit_layout(
    context, scene, base_obj, temp_collection, tree, output_dir,
    tree_type, bake_info=None, lod_mode=False, lod_config=None, lod_image_cache=None,
):
    def _uri_join(*parts):
        return "/".join([p.strip("/\\") for p in parts if p])

    nodes = []
    _collect_native_nodes(tree, nodes)
    nodes = [n for n in nodes if n.get("face_ids")]
    if not nodes:
        return False, "Implicit layout: no nodes generated for export."

    max_depth = max(int(n.get("depth", 0)) for n in nodes)
    available_levels = max_depth + 1
    total_nodes = _implicit_total_nodes(available_levels, tree_type)
    if total_nodes > 200_000_000:
        return False, (
            f"Implicit layout too deep ({available_levels} levels -> {total_nodes} availability bits). "
            "Reduce max depth or increase features-per-tile."
        )

    tile_bits = bytearray((total_nodes + 7) // 8)
    content_bits = bytearray((total_nodes + 7) // 8)
    tile_count = 0
    content_count = 0

    force_unlit = bool(getattr(scene, "cesium_force_unlit_materials", False))
    preserve_borders = bool(getattr(scene, "cesium_lod_preserve_borders", True))

    for node in nodes:
        level = int(node.get("depth", 0))
        x = int(node.get("grid_x", 0))
        y = int(node.get("grid_y", 0))
        z = int(node.get("grid_z", 0))

        bit_idx = _implicit_level_offset(level, tree_type) + _implicit_morton_index(node, tree_type)
        if _bitarray_set_once(tile_bits, bit_idx):
            tile_count += 1

        if tree_type == 'OCTREE':
            rel_uri = _uri_join("tiles", str(level), str(x), str(y), f"{z}.glb")
            tile_label = f"{level}/{x}/{y}/{z}"
        else:
            rel_uri = _uri_join("tiles", str(level), str(x), f"{y}.glb")
            tile_label = f"{level}/{x}/{y}"
        abs_path = os.path.join(output_dir, rel_uri)

        # Determine LOD parameters for this node
        dec_ratio = 1.0
        lod_image = None
        is_leaf = not node["children"]
        if lod_mode and lod_config and not is_leaf:
            # Find config for this level
            levels_cfg = lod_config.get("lod_levels", [])
            level_cfg = None
            for lc in levels_cfg:
                if lc["depth"] == level:
                    level_cfg = lc
                    break
            if level_cfg:
                dec_ratio = level_cfg["decimation_ratio"]
                atlas_sz = level_cfg["atlas_size"]
                if lod_image_cache and atlas_sz in lod_image_cache:
                    lod_image = lod_image_cache[atlas_sz]

        ok = _export_node_glb(
            context, base_obj, temp_collection, node["face_ids"], abs_path,
            force_unlit=force_unlit, export_yup=True,
            decimation_ratio=dec_ratio, preserve_borders=preserve_borders,
            lod_image=lod_image,
        )
        if not ok:
            return False, f"Implicit layout: failed exporting tile {tile_label}."

        if _bitarray_set_once(content_bits, bit_idx):
            content_count += 1

    if tree_type == 'OCTREE':
        subtree_rel = _uri_join("subtrees", "0", "0", "0", "0.subtree")
        content_uri_template = "tiles/{level}/{x}/{y}/{z}.glb"
        subtree_uri_template = "subtrees/{level}/{x}/{y}/{z}.subtree"
        subtree_note = "subtrees/0/0/0/0.subtree"
    else:
        subtree_rel = _uri_join("subtrees", "0", "0", "0.subtree")
        content_uri_template = "tiles/{level}/{x}/{y}.glb"
        subtree_uri_template = "subtrees/{level}/{x}/{y}.subtree"
        subtree_note = "subtrees/0/0/0.subtree"
    _write_subtree_file(
        os.path.join(output_dir, subtree_rel),
        tile_bits, tile_count, content_bits, content_count,
    )

    root_error = max(_bbox_diag_len(tree["bbox"]), 1.0)
    root_tile_error = max(root_error / (2 ** max(available_levels, 1)), 0.0)
    subdivision = "OCTREE" if tree_type == 'OCTREE' else "QUADTREE"
    root_box = _bbox_to_box(tree["bbox"])
    tileset = {
        "asset": {
            "version": "1.1",
            "extras": {
                "ion": {"georeferenced": False, "movable": True},
            },
        },
        "schema": {
            "id": "cesium-tiling-pipeline",
            "classes": {
                "tile": {
                    "properties": {
                        "tightBoundingBox": {
                            "name": "Tight Bounding Box",
                            "type": "SCALAR",
                            "componentType": "FLOAT64",
                            "array": True,
                            "count": 12,
                            "semantic": "TILE_BOUNDING_BOX",
                        }
                    }
                }
            },
        },
        "geometricError": root_error,
        "root": {
            "boundingVolume": {"box": root_box},
            "metadata": {
                "class": "tile",
                "properties": {"tightBoundingBox": root_box},
            },
            "geometricError": root_tile_error,
            "refine": "REPLACE",
            "content": {"uri": content_uri_template},
            "implicitTiling": {
                "subdivisionScheme": subdivision,
                "subtreeLevels": available_levels,
                "availableLevels": available_levels,
                "subtrees": {"uri": subtree_uri_template},
            },
        },
    }
    with open(os.path.join(output_dir, "tileset.json"), "w", encoding="utf-8") as f:
        json.dump(tileset, f, indent=2)

    note_path = os.path.join(output_dir, "native_backend_info.txt")
    with open(note_path, "w", encoding="utf-8") as f:
        f.write("Backend: NATIVE_SPLIT\n")
        f.write("3D Tiles version: 1.1\n")
        f.write(f"Tree type: {tree_type}\n")
        f.write("Bounding volume frame: GLTF_FRAME\n")
        f.write("GLB export Y-up: True\n")
        f.write("Hierarchy layout: IMPLICIT_TILING\n")
        f.write(f"LOD mode: {bool(lod_mode)}\n")
        f.write(f"Available levels: {available_levels}\n")
        f.write(f"Total tiles generated: {len(nodes)}\n")
        f.write(f"Total nodes with content: {content_count}\n")
        f.write("Root content exported: True\n")
        f.write(f"Subtree availability bits: {total_nodes}\n")
        f.write(f"Subtree file: {subtree_note}\n")
        if isinstance(bake_info, dict):
            f.write(f"Texture bake enabled: {bool(bake_info.get('enabled', False))}\n")
            f.write(f"Texture bake applied: {bool(bake_info.get('applied', False))}\n")
            if bake_info.get("enabled"):
                f.write(f"Bake atlas size: {int(bake_info.get('atlas_size', 0))}\n")
                f.write(f"Bake margin px: {int(bake_info.get('margin_px', 0))}\n")
                f.write(f"Bake source texture images: {int(bake_info.get('source_texture_images', 0))}\n")
        if lod_config:
            f.write(f"LOD max depth: {lod_config.get('max_depth', 0)}\n")
            f.write(f"LOD features per tile: {lod_config.get('features_per_tile', 0)}\n")
            for lc in lod_config.get("lod_levels", []):
                f.write(f"  Level {lc['depth']}: ratio={lc['decimation_ratio']}, atlas={lc['atlas_size']}px\n")

    return True, f"Implicit tiling completed ({len(nodes)} tiles, {available_levels} levels, LOD={bool(lod_mode)})."


# ---------------------------------------------------------------------------
#  Main native split backend
# ---------------------------------------------------------------------------

def _run_native_split_backend(context, scene, active_obj, output_dir, input_format, coords_cfg):
    def _uri_join(*parts):
        return "/".join([p.strip("/\\") for p in parts if p])

    data_root = "Data"
    lod_mode = bool(getattr(scene, "cesium_lod_mode", False))

    bake_info = {
        "enabled": bool(getattr(scene, "cesium_native_bake_texture_atlas", True)),
        "applied": False,
        "atlas_size": int(getattr(scene, "cesium_native_bake_texture_size", 2048)),
        "margin_px": int(getattr(scene, "cesium_native_bake_margin", 8)),
        "source_texture_images": 0,
        "source_image_nodes": 0,
        "temp_materials": [],
        "baked_material": "",
        "baked_image": "",
    }

    base_obj, temp_collection = _prepare_base_mesh_object(context, active_obj, coords_cfg["offset"])
    lod_image_cache = None
    try:
        _add_to_cesium_log(context, f"[NATIVE] {active_obj.name}: bbox=GLTF_FRAME, GLB export_yup=ON")

        # Always compute in GLTF Y-up frame
        face_ids, centroids, face_mins, face_maxs = _build_face_spatial_data(
            base_obj.data, to_gltf_yup=True,
        )
        if not face_ids:
            return False, "Active mesh has no faces."

        if bake_info["enabled"]:
            ok_bake, bake_msg, bake_result = _native_bake_basecolor_texture(
                context=context, scene=scene, base_obj=base_obj,
                atlas_size=bake_info["atlas_size"], margin_px=bake_info["margin_px"],
            )
            bake_info.update(bake_result or {})
            if not ok_bake:
                return False, f"Native bake failed: {bake_msg}"
            _add_to_cesium_log(context, f"[NATIVE] {active_obj.name}: {bake_msg}")
        else:
            _add_to_cesium_log(context, f"[NATIVE] {active_obj.name}: texture bake disabled.")

        max_faces = int(scene.cesium_features_per_tile)
        min_depth = int(scene.cesium_native_min_depth)
        max_depth = int(scene.cesium_native_max_depth)
        tree_type = scene.cesium_tree_type

        # LOD auto-parametrization
        lod_config = None
        if lod_mode:
            # Get max texture resolution from source
            max_tex_res = bake_info.get("atlas_size", 2048)
            area_m2 = sum(poly.area for poly in base_obj.data.polygons)
            lod_config = _compute_lod_parameters(
                total_faces=len(face_ids),
                area_m2=area_m2,
                max_tex_res=max_tex_res,
                tree_type=tree_type,
                scene=scene,
            )
            # Override depth/features from LOD config
            max_depth = lod_config["max_depth"]
            max_faces = lod_config["features_per_tile"]
            _add_to_cesium_log(
                context,
                f"[LOD] Auto-params: depth={max_depth}, feat/tile={max_faces}, "
                f"levels={len(lod_config['lod_levels'])}"
            )

            # Prepare LOD image cache
            if bake_info.get("applied") and bake_info.get("baked_image"):
                source_img = bpy.data.images.get(bake_info["baked_image"])
                if source_img is not None:
                    lod_image_cache = _prepare_lod_image_cache(source_img, lod_config)
                    _add_to_cesium_log(
                        context,
                        f"[LOD] Image cache: {len(lod_image_cache)} sizes "
                        f"({', '.join(str(s) for s in sorted(lod_image_cache.keys()))})"
                    )

        min_depth = min(min_depth, max_depth)

        use_regular_implicit_grid = scene.cesium_native_hierarchy_layout == 'IMPLICIT_TILING'
        root_split_bbox = (
            _bbox_union_from_face_ids(face_ids, face_mins, face_maxs)
            if use_regular_implicit_grid
            else None
        )

        tree = _build_native_tree(
            face_ids=face_ids, depth=0, tree_type=tree_type,
            max_faces=max_faces, min_depth=min_depth, max_depth=max_depth,
            centroids=centroids, face_mins=face_mins, face_maxs=face_maxs,
            path_code="", split_bbox=root_split_bbox,
        )

        if scene.cesium_native_hierarchy_layout == 'IMPLICIT_TILING':
            return _run_native_implicit_layout(
                context=context, scene=scene, base_obj=base_obj,
                temp_collection=temp_collection, tree=tree,
                output_dir=output_dir, tree_type=tree_type,
                bake_info=bake_info,
                lod_mode=lod_mode, lod_config=lod_config,
                lod_image_cache=lod_image_cache,
            )

        # ----- EXTERNAL_SUBTILESETS or SINGLE_JSON -----
        force_unlit = bool(getattr(scene, "cesium_force_unlit_materials", False))
        preserve_borders = bool(getattr(scene, "cesium_lod_preserve_borders", True))

        external_subtree_map = {}
        subtree_nodes = []
        subtree_folder_map = {}
        if scene.cesium_native_hierarchy_layout == 'EXTERNAL_SUBTILESETS':
            split_depth = int(scene.cesium_native_subtileset_split_depth)
            split_depth = max(1, min(split_depth, max_depth))
            _collect_nodes_at_depth(tree, split_depth, subtree_nodes)
            subtree_nodes = [n for n in subtree_nodes if n.get("children")]

            subtree_counter = 1
            for subtree in subtree_nodes:
                code = subtree.get("path_code", "") or f"{subtree_counter}"
                subtree_folder = _uri_join(data_root, f"c{code}")
                subtree_counter += 1
                subtree_folder_map[id(subtree)] = subtree_folder
                external_subtree_map[id(subtree)] = _uri_join(subtree_folder, "tileset.json")

            for subtree in subtree_nodes:
                subtree_leaves = []
                _collect_native_leaves(subtree, subtree_leaves)
                folder = subtree_folder_map.get(id(subtree))
                for leaf in subtree_leaves:
                    leaf["_subtree_folder"] = folder

        # Collect all nodes to export (LOD mode: all nodes; else: only leaves)
        if lod_mode:
            all_nodes = []
            _collect_native_nodes(tree, all_nodes)
            all_nodes = [n for n in all_nodes if n.get("face_ids")]
        else:
            all_nodes = []
            _collect_native_leaves(tree, all_nodes)

        if not all_nodes:
            return False, "No nodes generated for native split."

        tile_counter = 1
        for node in all_nodes:
            is_leaf = not node["children"]
            tile_id = str(tile_counter)
            tile_counter += 1

            # Determine file path
            subtree_folder = node.get("_subtree_folder")
            prefix = "f" if is_leaf else "n"
            if subtree_folder:
                disk_rel_uri = _uri_join(subtree_folder, f"{prefix}{tile_id}.glb")
                node["uri"] = f"{prefix}{tile_id}.glb"
            else:
                disk_rel_uri = _uri_join(data_root, f"{prefix}{tile_id}.glb")
                node["uri"] = disk_rel_uri
            abs_path = os.path.join(output_dir, disk_rel_uri)

            # LOD parameters for this node
            dec_ratio = 1.0
            lod_image = None
            if lod_mode and lod_config and not is_leaf:
                level = node["depth"]
                levels_cfg = lod_config.get("lod_levels", [])
                for lc in levels_cfg:
                    if lc["depth"] == level:
                        dec_ratio = lc["decimation_ratio"]
                        atlas_sz = lc["atlas_size"]
                        if lod_image_cache and atlas_sz in lod_image_cache:
                            lod_image = lod_image_cache[atlas_sz]
                        break

            ok = _export_node_glb(
                context, base_obj, temp_collection, node["face_ids"], abs_path,
                force_unlit=force_unlit, export_yup=True,
                decimation_ratio=dec_ratio, preserve_borders=preserve_borders,
                lod_image=lod_image,
            )
            if not ok:
                return False, f"Failed exporting tile {prefix}{tile_id}."

        # Root content for SINGLE_JSON
        if (
            scene.cesium_native_hierarchy_layout == 'SINGLE_JSON'
            and bool(getattr(scene, "cesium_singlejson_add_root_content", True))
            and not lod_mode  # in LOD mode, root already has content
        ):
            root_uri = _uri_join(data_root, "root.glb")
            root_abs_path = os.path.join(output_dir, root_uri)
            ok = _export_node_glb(
                context, base_obj, temp_collection, face_ids, root_abs_path,
                force_unlit=force_unlit, export_yup=True,
            )
            if not ok:
                return False, "Failed exporting single-JSON root content tile."
            tree["uri"] = root_uri

        root_error = max(_bbox_diag_len(tree["bbox"]), 1.0)
        if scene.cesium_native_hierarchy_layout == 'EXTERNAL_SUBTILESETS':
            for subtree in subtree_nodes:
                subtree_root_error = max(_bbox_diag_len(subtree["bbox"]), 1.0)
                subtree_tile = _native_tree_to_tileset_node(
                    subtree, root_error=subtree_root_error,
                    base_depth=subtree["depth"], external_subtree_map=None,
                )
                subtree_folder = subtree_folder_map.get(id(subtree), "")
                subtree_json_path = os.path.join(output_dir, subtree_folder, "tileset.json")
                os.makedirs(os.path.dirname(subtree_json_path), exist_ok=True)
                with open(subtree_json_path, "w", encoding="utf-8") as subf:
                    json.dump(
                        {"asset": {"version": "1.1"}, "geometricError": subtree_root_error, "root": subtree_tile},
                        subf, indent=2,
                    )

        tileset = {
            "asset": {"version": "1.1"},
            "geometricError": root_error,
            "root": _native_tree_to_tileset_node(
                tree, root_error=root_error, base_depth=0,
                external_subtree_map=external_subtree_map,
            ),
        }

        tileset_path = os.path.join(output_dir, "tileset.json")
        with open(tileset_path, "w", encoding="utf-8") as f:
            json.dump(tileset, f, indent=2)

        leaves = []
        _collect_native_leaves(tree, leaves)
        note_path = os.path.join(output_dir, "native_backend_info.txt")
        with open(note_path, "w", encoding="utf-8") as f:
            f.write("Backend: NATIVE_SPLIT\n")
            f.write("3D Tiles version: 1.1\n")
            f.write(f"Tree type: {tree_type}\n")
            f.write("Bounding volume frame: GLTF_FRAME\n")
            f.write("GLB export Y-up: True\n")
            f.write(f"Hierarchy layout: {scene.cesium_native_hierarchy_layout}\n")
            f.write(f"LOD mode: {bool(lod_mode)}\n")
            f.write(f"Min depth: {min_depth}\n")
            f.write(f"Max depth: {max_depth}\n")
            if scene.cesium_native_hierarchy_layout == 'EXTERNAL_SUBTILESETS':
                f.write(f"Subtileset split depth: {scene.cesium_native_subtileset_split_depth}\n")
            else:
                f.write(f"Single JSON root content: {bool(getattr(scene, 'cesium_singlejson_add_root_content', True))}\n")
            f.write(f"Max faces per leaf: {max_faces}\n")
            f.write(f"Total exported nodes: {len(all_nodes)}\n")
            f.write(f"Leaf nodes: {len(leaves)}\n")
            f.write(f"Texture bake enabled: {bool(bake_info.get('enabled', False))}\n")
            f.write(f"Texture bake applied: {bool(bake_info.get('applied', False))}\n")
            if bake_info.get("enabled"):
                f.write(f"Bake atlas size: {int(bake_info.get('atlas_size', 0))}\n")
                f.write(f"Bake margin px: {int(bake_info.get('margin_px', 0))}\n")
                f.write(f"Bake source texture images: {int(bake_info.get('source_texture_images', 0))}\n")
            if lod_config:
                f.write(f"LOD max depth: {lod_config.get('max_depth', 0)}\n")
                f.write(f"LOD features per tile: {lod_config.get('features_per_tile', 0)}\n")
                for lc in lod_config.get("lod_levels", []):
                    f.write(f"  Level {lc['depth']}: ratio={lc['decimation_ratio']}, atlas={lc['atlas_size']}px\n")

        return True, f"Native split completed ({len(all_nodes)} tiles, LOD={bool(lod_mode)})."
    finally:
        try:
            mesh_data = base_obj.data
        except Exception:
            mesh_data = None
        try:
            bpy.data.objects.remove(base_obj, do_unlink=True)
        except Exception:
            pass
        try:
            if mesh_data is not None and mesh_data.users == 0:
                bpy.data.meshes.remove(mesh_data, do_unlink=True)
        except Exception:
            pass
        _cleanup_native_bake_assets(bake_info)
        if lod_image_cache:
            _cleanup_lod_image_cache(lod_image_cache)


# ===========================================================================
#  BLOCK D: Operators
# ===========================================================================

class OBJECT_OT_clear_cesium_folder(bpy.types.Operator):
    """Empty output folder contents without deleting the folder itself."""
    bl_idname = "object.clear_cesium_folder"
    bl_label = "Clear Cesium Folder"
    bl_options = {'REGISTER'}

    target: bpy.props.EnumProperty(
        name="Target folder",
        items=[
            ('OUTPUT', 'Output folder', 'Clear output folder contents'),
        ],
        default='OUTPUT',
    )  # type: ignore

    def invoke(self, context, event):
        return context.window_manager.invoke_confirm(self, event)

    def execute(self, context):
        scene = context.scene
        folder = bpy.path.abspath(scene.cesium_output_dir).strip()

        if not folder:
            self.report({'ERROR'}, "Set a valid output folder first.")
            return {'CANCELLED'}
        if not os.path.exists(folder):
            try:
                os.makedirs(folder, exist_ok=True)
            except Exception as exc:
                self.report({'ERROR'}, f"Cannot create output folder `{folder}`: {exc}")
                return {'CANCELLED'}
            self.report({'INFO'}, "Output folder was missing and has been created empty.")
            return {'FINISHED'}
        if not os.path.isdir(folder):
            self.report({'ERROR'}, f"Output path is not a folder: {folder}")
            return {'CANCELLED'}

        removed = 0
        first_error = None
        for name in os.listdir(folder):
            path = os.path.join(folder, name)
            try:
                if os.path.isdir(path) and not os.path.islink(path):
                    shutil.rmtree(path)
                else:
                    os.remove(path)
                removed += 1
            except Exception as exc:
                if first_error is None:
                    first_error = f"{name}: {exc}"

        if first_error:
            self.report({'WARNING'}, f"Cleared {removed} item(s). Some entries were skipped ({first_error}).")
        else:
            self.report({'INFO'}, f"Cleared {removed} item(s) from output folder.")
        return {'FINISHED'}


class OBJECT_OT_patch_cesium_output_unlit(bpy.types.Operator):
    """Patch all GLB tiles in output folder to KHR_materials_unlit."""
    bl_idname = "object.patch_cesium_output_unlit"
    bl_label = "Patch Output GLBs to Unlit"
    bl_options = {'REGISTER'}

    def execute(self, context):
        scene = context.scene
        output_root = bpy.path.abspath(scene.cesium_output_dir).strip()
        if not output_root:
            self.report({'ERROR'}, "Set a valid output folder first.")
            return {'CANCELLED'}
        if not os.path.isdir(output_root):
            self.report({'ERROR'}, f"Output folder not found: {output_root}")
            return {'CANCELLED'}

        patched, failed = _patch_output_glbs_to_unlit(output_root)
        if patched == 0 and failed == 0:
            self.report({'WARNING'}, "No GLB files found in output folder.")
            return {'CANCELLED'}
        if failed > 0:
            self.report({'WARNING'}, f"Patched {patched} GLB file(s), failed on {failed}.")
        else:
            self.report({'INFO'}, f"Patched {patched} GLB file(s) to unlit.")
        return {'FINISHED'}


class OBJECT_OT_strip_cesium_output_unlit(bpy.types.Operator):
    """Remove KHR_materials_unlit from all GLB tiles in output folder."""
    bl_idname = "object.strip_cesium_output_unlit"
    bl_label = "Remove Unlit from Output GLBs"
    bl_options = {'REGISTER'}

    def execute(self, context):
        scene = context.scene
        output_root = bpy.path.abspath(scene.cesium_output_dir).strip()
        if not output_root:
            self.report({'ERROR'}, "Set a valid output folder first.")
            return {'CANCELLED'}
        if not os.path.isdir(output_root):
            self.report({'ERROR'}, f"Output folder not found: {output_root}")
            return {'CANCELLED'}

        stripped, failed = _strip_output_glbs_unlit(output_root)
        if stripped == 0 and failed == 0:
            self.report({'WARNING'}, "No GLB files found in output folder.")
            return {'CANCELLED'}
        if failed > 0:
            self.report({'WARNING'}, f"Processed {stripped} GLB file(s), failed on {failed}.")
        else:
            self.report({'INFO'}, f"Removed unlit extension from {stripped} GLB file(s).")
        return {'FINISHED'}


class OBJECT_OT_apply_cesium_preset(bpy.types.Operator):
    """Apply quick tiling presets."""
    bl_idname = "object.apply_cesium_preset"
    bl_label = "Apply Cesium Preset"
    bl_options = {'REGISTER'}

    def execute(self, context):
        scene = context.scene
        preset = scene.cesium_quick_preset
        scene.cesium_native_bake_texture_atlas = True
        scene.cesium_native_bake_margin = 8

        if preset == 'LOD_HIERARCHY':
            scene.cesium_features_per_tile = 8000
            scene.cesium_native_min_depth = 2
            scene.cesium_native_max_depth = 6
            scene.cesium_tree_type = 'OCTREE'
            scene.cesium_native_hierarchy_layout = 'IMPLICIT_TILING'
            scene.cesium_lod_mode = True
            scene.cesium_lod_auto_params = True
            scene.cesium_native_bake_texture_size = 2048
            scene.cesium_force_unlit_materials = False
        elif preset == 'BALANCED':
            scene.cesium_features_per_tile = 8000
            scene.cesium_native_min_depth = 2
            scene.cesium_native_max_depth = 8
            scene.cesium_tree_type = 'QUADTREE'
            scene.cesium_native_hierarchy_layout = 'EXTERNAL_SUBTILESETS'
            scene.cesium_native_subtileset_split_depth = 2
            scene.cesium_lod_mode = False
            scene.cesium_native_bake_texture_size = 2048
            scene.cesium_force_unlit_materials = False
        else:  # LOW_DETAIL
            scene.cesium_features_per_tile = 25000
            scene.cesium_native_min_depth = 1
            scene.cesium_native_max_depth = 6
            scene.cesium_tree_type = 'QUADTREE'
            scene.cesium_native_hierarchy_layout = 'SINGLE_JSON'
            scene.cesium_lod_mode = False
            scene.cesium_native_bake_texture_size = 2048
            scene.cesium_force_unlit_materials = False

        self.report({'INFO'}, f"Applied preset: {preset}")
        return {'FINISHED'}


class OBJECT_OT_rebuild_cesium_parent_tileset(bpy.types.Operator):
    """Build or refresh a parent tileset.json that references child tilesets in output subfolders."""
    bl_idname = "object.rebuild_cesium_parent_tileset"
    bl_label = "Rebuild Parent Tileset"
    bl_options = {'REGISTER'}

    def execute(self, context):
        scene = context.scene
        output_root = bpy.path.abspath(scene.cesium_output_dir).strip()
        parent_name = _normalize_parent_tileset_name(scene.cesium_parent_tileset_name)

        if not output_root:
            self.report({'ERROR'}, "Set a valid output directory.")
            return {'CANCELLED'}
        if not os.path.isdir(output_root):
            self.report({'ERROR'}, f"Output folder not found: {output_root}")
            return {'CANCELLED'}

        ok, msg, parent_path, _, skipped = _build_parent_tileset(output_root, parent_name)
        if not ok:
            self.report({'WARNING'}, msg)
            return {'CANCELLED'}

        if skipped > 0:
            self.report({'WARNING'}, f"{msg} Skipped {skipped} invalid child tileset(s). Parent: {parent_path}")
        else:
            self.report({'INFO'}, f"{msg} Parent: {parent_path}")
        return {'FINISHED'}


class OBJECT_OT_export_cesium_tiles(bpy.types.Operator):
    bl_idname = "object.export_cesium_tiles"
    bl_label = "Export Cesium 3D Tiles"
    bl_description = "Export selected mesh(es) to Cesium 3D Tiles with optional LOD hierarchy"
    bl_options = {'REGISTER'}

    def execute(self, context):
        scene = context.scene
        source_mode = scene.cesium_source_mode
        output_root = bpy.path.abspath(scene.cesium_output_dir).strip()
        auto_stitch_parent = bool(scene.cesium_auto_stitch_parent)
        parent_name = _normalize_parent_tileset_name(scene.cesium_parent_tileset_name)

        if not output_root:
            self.report({'ERROR'}, "Set a valid output directory.")
            return {'CANCELLED'}

        coords_cfg, cfg_error = _resolve_coordinates_config(scene)
        if cfg_error:
            self.report({'ERROR'}, cfg_error)
            return {'CANCELLED'}

        # Build job list
        jobs = []
        if source_mode == 'ACTIVE_MESH':
            selected_meshes = [obj for obj in context.selected_objects if obj and obj.type == 'MESH']
            active_obj = context.active_object
            if scene.cesium_export_selected_meshes:
                mesh_objects = selected_meshes
                if not mesh_objects:
                    self.report({'ERROR'}, "Select at least one mesh object.")
                    return {'CANCELLED'}
            else:
                if active_obj is None or active_obj.type != 'MESH':
                    self.report({'ERROR'}, "Select an active mesh object.")
                    return {'CANCELLED'}
                mesh_objects = [active_obj]

            if len(mesh_objects) > 1 and not scene.cesium_create_object_subdir:
                self.report(
                    {'ERROR'},
                    "Enable 'Create object subfolder' to export multiple meshes without overwriting tilesets.",
                )
                return {'CANCELLED'}

            for mesh_obj in mesh_objects:
                obj_name = _sanitize_name(mesh_obj.name)
                output_dir = os.path.join(output_root, obj_name) if scene.cesium_create_object_subdir else output_root
                jobs.append({
                    "kind": "ACTIVE",
                    "object": mesh_obj,
                    "obj_name": obj_name,
                    "input_format": 'GLB',
                    "output_dir": output_dir,
                })
        else:
            existing_obj_path = bpy.path.abspath(scene.cesium_existing_obj_file).strip()
            if not existing_obj_path:
                self.report({'ERROR'}, "Set a valid OBJ file path.")
                return {'CANCELLED'}
            if not os.path.exists(existing_obj_path):
                self.report({'ERROR'}, f"OBJ file not found: {existing_obj_path}")
                return {'CANCELLED'}
            obj_name = _sanitize_name(os.path.splitext(os.path.basename(existing_obj_path))[0])
            output_dir = os.path.join(output_root, obj_name) if scene.cesium_create_object_subdir else output_root
            jobs.append({
                "kind": "EXISTING_OBJ",
                "object": None,
                "obj_name": obj_name,
                "input_format": 'OBJ',
                "output_dir": output_dir,
                "input_file": existing_obj_path,
            })

        total_jobs = len(jobs)
        start_time = time.time()
        scene.cesium_progress_active = True
        scene.cesium_progress_task = "Initializing Cesium export..."
        scene.cesium_progress_current_mesh = 0
        scene.cesium_progress_total_meshes = total_jobs
        scene.cesium_progress_elapsed = 0.0
        scene.cesium_progress_log = ""
        scene.cesium_progress_last_stats = ""
        _update_cesium_progress(context, task="Initializing...", current_mesh=0, total_meshes=total_jobs, elapsed=0.0)
        _add_to_cesium_log(context, f"Starting Cesium export for {total_jobs} mesh(es)")
        _add_to_cesium_log(context, "Backend: NATIVE_SPLIT")
        _add_to_cesium_log(context, "TEMP folder not used (direct-to-output mode).")
        if getattr(scene, "cesium_native_bake_texture_atlas", True):
            _add_to_cesium_log(
                context,
                f"Native bake atlas: ON ({int(getattr(scene, 'cesium_native_bake_texture_size', 2048))} px, "
                f"margin {int(getattr(scene, 'cesium_native_bake_margin', 8))} px)"
            )
        else:
            _add_to_cesium_log(context, "Native bake atlas: OFF")

        def _cancel_with_progress(message):
            _add_to_cesium_log(context, f"[ERR] {message}")
            _update_cesium_progress(
                context, task="Failed",
                current_mesh=scene.cesium_progress_current_mesh,
                total_meshes=total_jobs, elapsed=time.time() - start_time,
            )
            self.report({'ERROR'}, message)
            return {'CANCELLED'}

        successful_jobs = 0
        try:
            for mesh_idx, job in enumerate(jobs, start=1):
                obj_name = job["obj_name"]
                output_dir = job["output_dir"]
                os.makedirs(output_dir, exist_ok=True)

                mesh_stats = _collect_mesh_stats(context, scene, job)
                _update_cesium_progress(
                    context, task=f"Processing mesh: {obj_name}",
                    current_mesh=mesh_idx, total_meshes=total_jobs,
                    elapsed=time.time() - start_time,
                )
                _add_to_cesium_log(
                    context,
                    f"-> {obj_name}: faces {mesh_stats['faces']}, area {mesh_stats['area_m2']:.2f} m2, "
                    f"textures {mesh_stats['textures']}, uv {mesh_stats['uv_maps']}"
                )

                before_files = _snapshot_output_files(output_dir)
                mesh_start = time.time()

                if job["kind"] != "ACTIVE" or job["object"] is None:
                    return _cancel_with_progress("Native split currently supports only 'Export active mesh' source mode.")
                ok, msg = _run_native_split_backend(
                    context=context, scene=scene,
                    active_obj=job["object"], output_dir=output_dir,
                    input_format=job["input_format"], coords_cfg=coords_cfg,
                )
                if not ok:
                    return _cancel_with_progress(f"{obj_name}: {msg}")

                after_files = _snapshot_output_files(output_dir)
                generated_stats = _summarize_generated_files(after_files - before_files)
                if generated_stats["tiles"] == 0 and generated_stats["tilesets"] == 0:
                    generated_stats = _summarize_generated_files(after_files)
                mesh_duration = time.time() - mesh_start
                stats_line = _format_cesium_mesh_stats(obj_name, mesh_stats, generated_stats, mesh_duration)
                scene.cesium_progress_last_stats = stats_line
                _add_to_cesium_log(context, f"[OK] {stats_line}")

                successful_jobs += 1
                _update_cesium_progress(
                    context, task=f"Completed mesh: {obj_name}",
                    current_mesh=mesh_idx, total_meshes=total_jobs,
                    elapsed=time.time() - start_time,
                )

            _add_to_cesium_log(context, "No intermediate files generated.")

            if auto_stitch_parent and total_jobs > 1:
                if not scene.cesium_create_object_subdir:
                    self.report({'WARNING'}, "Auto-stitch skipped: enable 'Create object subfolder'.")
                    _add_to_cesium_log(context, "[WARN] Auto-stitch skipped (enable Create object subfolder).")
                else:
                    ok, msg, parent_path, _, skipped = _build_parent_tileset(output_root, parent_name)
                    if ok:
                        if skipped > 0:
                            self.report({'WARNING'}, f"{msg} Skipped {skipped} invalid child tileset(s).")
                            _add_to_cesium_log(context, f"[WARN] Parent rebuilt with skipped children ({skipped}).")
                        else:
                            self.report({'INFO'}, f"{msg} Parent: {parent_path}")
                            _add_to_cesium_log(context, f"[OK] Parent tileset updated: {parent_path}")
                    else:
                        self.report({'WARNING'}, f"Auto-stitch skipped: {msg}")
                        _add_to_cesium_log(context, f"[WARN] Auto-stitch skipped: {msg}")
            elif auto_stitch_parent and total_jobs <= 1:
                _add_to_cesium_log(context, "Auto-stitch skipped: single mesh does not need parent tileset.")

            total_elapsed = time.time() - start_time
            mins = int(total_elapsed // 60)
            secs = int(total_elapsed % 60)
            _update_cesium_progress(
                context, task="Completed",
                current_mesh=successful_jobs, total_meshes=total_jobs,
                elapsed=total_elapsed,
            )
            _add_to_cesium_log(context, f"=== Completed: {successful_jobs}/{total_jobs} mesh(es) in {mins}m {secs}s ===")
            self.report({'INFO'}, f"Cesium export completed for {successful_jobs} mesh(es).")
            return {'FINISHED'}
        finally:
            scene.cesium_progress_active = False
            _redraw_3d_view(context)


# ===========================================================================
#  BLOCK E: UI Panel + register / unregister
# ===========================================================================

class VIEW3D_PT_cesium_export(bpy.types.Panel):
    bl_label = "Cesium 3D Tiles"
    bl_idname = "VIEW3D_PT_cesium_export"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = '3DSC'
    bl_context = "objectmode"
    bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        layout = self.layout
        scene = context.scene
        active_obj = context.active_object
        source_mode = scene.cesium_source_mode

        # ---- Progress section ----
        if scene.cesium_progress_active or scene.cesium_progress_log or scene.cesium_progress_last_stats:
            box_prog = layout.box()
            box_prog.label(text="Export Progress", icon='TIME')
            col = box_prog.column(align=True)
            if scene.cesium_progress_task:
                col.label(text=f"Task: {scene.cesium_progress_task}")
            if scene.cesium_progress_total_meshes > 0:
                col.label(text=f"Mesh: {scene.cesium_progress_current_mesh}/{scene.cesium_progress_total_meshes}")
            if scene.cesium_progress_elapsed > 0.0:
                elapsed_m = int(scene.cesium_progress_elapsed // 60)
                elapsed_s = int(scene.cesium_progress_elapsed % 60)
                col.label(text=f"Elapsed: {elapsed_m}m {elapsed_s}s")

            if scene.cesium_progress_last_stats:
                box_stats = layout.box()
                box_stats.label(text="Last Mesh Stats", icon='INFO')
                for line in scene.cesium_progress_last_stats.split('\n')[-3:]:
                    if line.strip():
                        box_stats.label(text=line)

            if scene.cesium_progress_log:
                box_log = layout.box()
                box_log.label(text="Recent Operations", icon='TEXT')
                for line in scene.cesium_progress_log.split('\n')[-6:]:
                    if line.strip():
                        box_log.label(text=line)

        # ---- Source ----
        box_source = layout.box()
        box_source.label(text="Source")
        box_source.prop(scene, "cesium_source_mode")
        if source_mode == 'ACTIVE_MESH':
            box_source.prop(scene, "cesium_export_selected_meshes")
            selected_mesh_count = len([obj for obj in context.selected_objects if obj and obj.type == 'MESH'])
            if scene.cesium_export_selected_meshes:
                box_source.label(text=f"Selected meshes: {selected_mesh_count}", icon='INFO')
                if not scene.cesium_create_object_subdir and selected_mesh_count > 1:
                    box_source.label(text="Enable 'Create object subfolder' for multi-mesh export.", icon='ERROR')
            else:
                box_source.label(text="Workflow: 1 mesh at a time", icon='INFO')
            if active_obj is not None and active_obj.type == 'MESH':
                box_source.label(text=f"Active mesh: {active_obj.name}", icon='MESH_DATA')
            else:
                box_source.label(text="No active mesh selected", icon='ERROR')
        else:
            box_source.prop(scene, "cesium_existing_obj_file")
            box_source.label(text="Use an existing OBJ + MTL/texture set on disk.", icon='INFO')

        # ---- Output path ----
        box = layout.box()
        box.label(text="Output")
        row = box.row(align=True)
        row.prop(scene, "cesium_output_dir")
        op = row.operator("object.clear_cesium_folder", text="", icon='TRASH')
        op.target = 'OUTPUT'
        box.prop(scene, "cesium_create_object_subdir")

        # ---- Quick Setup ----
        box = layout.box()
        box.label(text="Quick Setup")
        row = box.row(align=True)
        row.prop(scene, "cesium_quick_preset")
        row.operator("object.apply_cesium_preset", text="Apply")

        # ---- Tiling ----
        box = layout.box()
        box.label(text="Tiling")
        box.prop(scene, "cesium_tree_type")
        box.prop(scene, "cesium_lod_mode")

        if scene.cesium_lod_mode:
            box.prop(scene, "cesium_lod_auto_params")
            if not scene.cesium_lod_auto_params:
                box.prop(scene, "cesium_native_max_depth")
                box.prop(scene, "cesium_features_per_tile")
                box.prop(scene, "cesium_lod_leaf_atlas_size")
                box.prop(scene, "cesium_lod_root_atlas_size")
            box.prop(scene, "cesium_lod_preserve_borders")
        else:
            box.prop(scene, "cesium_native_min_depth")
            box.prop(scene, "cesium_native_max_depth")
            box.prop(scene, "cesium_features_per_tile")

        # ---- Texture ----
        box = layout.box()
        box.label(text="Texture")
        box.prop(scene, "cesium_native_bake_texture_atlas")
        bake_row = box.row(align=True)
        bake_row.enabled = bool(scene.cesium_native_bake_texture_atlas)
        bake_row.prop(scene, "cesium_native_bake_texture_size")
        bake_row.prop(scene, "cesium_native_bake_margin")

        # ---- Hierarchy Layout ----
        box = layout.box()
        box.label(text="Hierarchy Layout")
        box.prop(scene, "cesium_native_hierarchy_layout")
        if scene.cesium_native_hierarchy_layout == 'EXTERNAL_SUBTILESETS':
            box.prop(scene, "cesium_native_subtileset_split_depth")
        elif scene.cesium_native_hierarchy_layout == 'SINGLE_JSON':
            box.prop(scene, "cesium_singlejson_add_root_content")

        # ---- Coordinates ----
        box = layout.box()
        box.label(text="Coordinates")
        box.prop(scene, "cesium_coordinates_mode")
        if scene.cesium_coordinates_mode == 'SHIFT_VALUES':
            box.label(text=f"SHIFT EPSG: {getattr(scene, 'BL_epsg', 'NotSet')}")
            box.label(
                text=f"SHIFT XYZ: {getattr(scene, 'BL_x_shift', 0.0):.3f}, "
                     f"{getattr(scene, 'BL_y_shift', 0.0):.3f}, "
                     f"{getattr(scene, 'BL_z_shift', 0.0):.3f}"
            )
            box.prop(scene, "cesium_crs", text="CRS override")
        elif scene.cesium_coordinates_mode == 'CUSTOM_COORDS':
            box.prop(scene, "cesium_crs")
            row = box.row(align=True)
            row.prop(scene, "cesium_offset_x", text="X")
            row.prop(scene, "cesium_offset_y", text="Y")
            row.prop(scene, "cesium_offset_z", text="Z")

        # ---- Multi-mesh Stitcher (collapsible) ----
        box_stitch = layout.box()
        stitch_header = box_stitch.row(align=True)
        stitch_icon = 'TRIA_DOWN' if scene.cesium_show_stitcher else 'TRIA_RIGHT'
        stitch_header.prop(scene, "cesium_show_stitcher", text="", emboss=False, icon=stitch_icon)
        stitch_header.label(text="Multi-mesh Stitcher")
        if scene.cesium_show_stitcher:
            stitch = box_stitch.box()
            stitch.prop(scene, "cesium_auto_stitch_parent")
            stitch.prop(scene, "cesium_parent_tileset_name")
            stitch.operator("object.rebuild_cesium_parent_tileset", icon='FILE_REFRESH')

        # ---- Advanced (collapsible) ----
        box_adv = layout.box()
        adv_header = box_adv.row(align=True)
        adv_icon = 'TRIA_DOWN' if scene.cesium_show_advanced else 'TRIA_RIGHT'
        adv_header.prop(scene, "cesium_show_advanced", text="", emboss=False, icon=adv_icon)
        adv_header.label(text="Advanced")
        if scene.cesium_show_advanced:
            adv = box_adv.box()
            adv.prop(scene, "cesium_force_unlit_materials")
            row = adv.row(align=True)
            row.operator("object.patch_cesium_output_unlit", icon='SHADING_TEXTURE')
            row.operator("object.strip_cesium_output_unlit", icon='X')

        # ---- Export button ----
        layout.operator("object.export_cesium_tiles", icon='EXPORT')


# ---------------------------------------------------------------------------
#  Classes tuple
# ---------------------------------------------------------------------------

classes = (
    OBJECT_OT_clear_cesium_folder,
    OBJECT_OT_patch_cesium_output_unlit,
    OBJECT_OT_strip_cesium_output_unlit,
    OBJECT_OT_apply_cesium_preset,
    OBJECT_OT_rebuild_cesium_parent_tileset,
    OBJECT_OT_export_cesium_tiles,
    VIEW3D_PT_cesium_export,
)


# ---------------------------------------------------------------------------
#  register / unregister
# ---------------------------------------------------------------------------

def register():
    for cls in classes:
        bpy.utils.register_class(cls)

    S = bpy.types.Scene

    # Source
    S.cesium_source_mode = bpy.props.EnumProperty(
        name="Source mode",
        items=[
            ('ACTIVE_MESH', 'Export active mesh', 'Export active mesh first, then convert'),
            ('EXISTING_OBJ', 'Use existing OBJ file', 'Convert an OBJ already present on disk'),
        ],
        default='ACTIVE_MESH',
    )
    S.cesium_export_selected_meshes = bpy.props.BoolProperty(
        name="Export selected meshes",
        default=False,
        description="Export all selected mesh objects (each in its own output subfolder)",
    )
    S.cesium_existing_obj_file = bpy.props.StringProperty(
        name="Existing OBJ file",
        subtype='FILE_PATH',
        default="",
        description="Path to an existing .obj file to convert directly",
    )

    # Output
    S.cesium_output_dir = bpy.props.StringProperty(
        name="Tiles output folder",
        subtype='DIR_PATH',
        default="",
        description="Destination folder for Cesium 3D Tiles output",
    )
    S.cesium_create_object_subdir = bpy.props.BoolProperty(
        name="Create object subfolder",
        default=True,
        description="Write tiles into an object-name subfolder under output path",
    )

    # Quick Setup
    S.cesium_quick_preset = bpy.props.EnumProperty(
        name="Quick preset",
        items=[
            ('LOD_HIERARCHY', 'LOD Hierarchy', 'Octree with hierarchical LOD decimation (recommended)'),
            ('BALANCED', 'Balanced', 'Quadtree, no LOD, external sub-tilesets'),
            ('LOW_DETAIL', 'Low Detail', 'Fewer tiles, larger features per tile'),
        ],
        default='LOD_HIERARCHY',
    )

    # Tiling
    S.cesium_tree_type = bpy.props.EnumProperty(
        name="Tree type",
        items=[
            ('QUADTREE', 'Quadtree', 'Best for wide horizontal scenes'),
            ('OCTREE', 'Octree', 'Best for volumetric scenes'),
        ],
        default='QUADTREE',
    )
    S.cesium_features_per_tile = bpy.props.IntProperty(
        name="Features per tile",
        default=8000,
        min=100,
        description="Approximate face budget per leaf tile",
    )
    S.cesium_native_min_depth = bpy.props.IntProperty(
        name="Min tree depth",
        default=2,
        min=0,
        max=20,
        description="Force at least this depth before stopping",
    )
    S.cesium_native_max_depth = bpy.props.IntProperty(
        name="Max tree depth",
        default=8,
        min=1,
        max=20,
        description="Maximum recursion depth for quadtree/octree",
    )

    # LOD
    S.cesium_lod_mode = bpy.props.BoolProperty(
        name="Hierarchical LOD",
        default=False,
        description="Generate LOD content at every tree level with decimation + scaled textures",
    )
    S.cesium_lod_auto_params = bpy.props.BoolProperty(
        name="Auto-parametrize",
        default=True,
        description="Automatically compute depth, features/tile, and atlas sizes from mesh stats",
    )
    S.cesium_lod_leaf_atlas_size = bpy.props.IntProperty(
        name="Leaf atlas size",
        default=1024,
        min=256,
        max=4096,
        description="Texture atlas size for leaf (highest detail) tiles",
    )
    S.cesium_lod_root_atlas_size = bpy.props.IntProperty(
        name="Root atlas size",
        default=256,
        min=64,
        max=2048,
        description="Texture atlas size for root (lowest detail) tile",
    )
    S.cesium_lod_preserve_borders = bpy.props.BoolProperty(
        name="Preserve mesh borders",
        default=True,
        description="Protect non-manifold edges from decimation (prevents tile seams)",
    )

    # Texture
    S.cesium_native_bake_texture_atlas = bpy.props.BoolProperty(
        name="Bake textures to atlas",
        default=True,
        description="Bake source materials into a single atlas before split export",
    )
    S.cesium_native_bake_texture_size = bpy.props.IntProperty(
        name="Bake atlas size",
        default=2048,
        min=512,
        max=16384,
        description="Texture atlas size for bake step (used as leaf size when LOD is off)",
    )
    S.cesium_native_bake_margin = bpy.props.IntProperty(
        name="Bake margin px",
        default=8,
        min=0,
        max=64,
        description="Pixel margin between UV islands in baked atlas",
    )

    # Hierarchy Layout
    S.cesium_native_hierarchy_layout = bpy.props.EnumProperty(
        name="Hierarchy layout",
        items=[
            ('SINGLE_JSON', 'Single JSON', 'One root tileset.json containing full hierarchy'),
            ('EXTERNAL_SUBTILESETS', 'External sub-tilesets', 'Split hierarchy into referenced sub-tileset files'),
            ('IMPLICIT_TILING', 'Implicit tiling', 'Massenzio-style implicit tiling: tiles/ + subtrees/'),
        ],
        default='SINGLE_JSON',
    )
    S.cesium_singlejson_add_root_content = bpy.props.BoolProperty(
        name="Add root content tile",
        default=True,
        description="Write a root GLB tile for viewers that require root content",
    )
    S.cesium_native_subtileset_split_depth = bpy.props.IntProperty(
        name="Subtileset split depth",
        default=2,
        min=1,
        max=20,
        description="Depth at which subtrees are emitted as external tileset files",
    )

    # Coordinates
    S.cesium_coordinates_mode = bpy.props.EnumProperty(
        name="Coordinates mode",
        items=[
            ('SHIFT_VALUES', 'Use SHIFT values', 'Use EPSG and XYZ from SHIFT panel'),
            ('LOCAL_COORDS', 'Use local coordinates', 'No CRS/offset transform'),
            ('CUSTOM_COORDS', 'Use custom coordinates', 'Custom XYZ and optional CRS override'),
        ],
        default='SHIFT_VALUES',
    )
    S.cesium_crs = bpy.props.StringProperty(
        name="CRS",
        default="",
        description="Input CRS (e.g. EPSG:32632). If empty, SHIFT panel EPSG is used.",
    )
    S.cesium_offset_x = bpy.props.FloatProperty(name="Offset X", default=0.0)
    S.cesium_offset_y = bpy.props.FloatProperty(name="Offset Y", default=0.0)
    S.cesium_offset_z = bpy.props.FloatProperty(name="Offset Z", default=0.0)

    # Stitcher
    S.cesium_show_stitcher = bpy.props.BoolProperty(name="Show stitcher", default=False)
    S.cesium_auto_stitch_parent = bpy.props.BoolProperty(
        name="Auto-update parent tileset",
        default=True,
        description="Rebuild parent tileset JSON after each export",
    )
    S.cesium_parent_tileset_name = bpy.props.StringProperty(
        name="Parent tileset filename",
        default="tileset.json",
        description="Filename for the parent tileset in the output folder",
    )

    # Advanced
    S.cesium_show_advanced = bpy.props.BoolProperty(name="Show advanced", default=False)
    S.cesium_force_unlit_materials = bpy.props.BoolProperty(
        name="Force unlit materials",
        default=False,
        description="Post-process GLB tiles to add KHR_materials_unlit",
    )
    S.cesium_texture_base_dir = bpy.props.StringProperty(
        name="Texture base dir (optional)",
        subtype='DIR_PATH',
        default="",
        description="Optional texture base directory for OBJ-based workflows",
    )

    # Progress
    S.cesium_progress_active = bpy.props.BoolProperty(default=False)
    S.cesium_progress_task = bpy.props.StringProperty(default="")
    S.cesium_progress_current_mesh = bpy.props.IntProperty(default=0)
    S.cesium_progress_total_meshes = bpy.props.IntProperty(default=0)
    S.cesium_progress_elapsed = bpy.props.FloatProperty(default=0.0)
    S.cesium_progress_log = bpy.props.StringProperty(default="")
    S.cesium_progress_last_stats = bpy.props.StringProperty(default="")


def unregister():
    S = bpy.types.Scene

    props_to_delete = [
        "cesium_source_mode",
        "cesium_export_selected_meshes",
        "cesium_existing_obj_file",
        "cesium_output_dir",
        "cesium_create_object_subdir",
        "cesium_quick_preset",
        "cesium_tree_type",
        "cesium_features_per_tile",
        "cesium_native_min_depth",
        "cesium_native_max_depth",
        "cesium_lod_mode",
        "cesium_lod_auto_params",
        "cesium_lod_leaf_atlas_size",
        "cesium_lod_root_atlas_size",
        "cesium_lod_preserve_borders",
        "cesium_native_bake_texture_atlas",
        "cesium_native_bake_texture_size",
        "cesium_native_bake_margin",
        "cesium_native_hierarchy_layout",
        "cesium_singlejson_add_root_content",
        "cesium_native_subtileset_split_depth",
        "cesium_coordinates_mode",
        "cesium_crs",
        "cesium_offset_x",
        "cesium_offset_y",
        "cesium_offset_z",
        "cesium_show_stitcher",
        "cesium_auto_stitch_parent",
        "cesium_parent_tileset_name",
        "cesium_show_advanced",
        "cesium_force_unlit_materials",
        "cesium_texture_base_dir",
        "cesium_progress_active",
        "cesium_progress_task",
        "cesium_progress_current_mesh",
        "cesium_progress_total_meshes",
        "cesium_progress_elapsed",
        "cesium_progress_log",
        "cesium_progress_last_stats",
    ]

    for prop in props_to_delete:
        try:
            delattr(S, prop)
        except Exception:
            pass

    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()
