import os
import re
import sys
import site
import importlib
import json
import tempfile
import subprocess
import shutil
from contextlib import contextmanager
import math

import bpy
import bmesh
from mathutils import Matrix, Vector


VTK_REQUIRED_MIN = (9, 2, 0)
VTK_REQUIRED_MAX_EXCLUSIVE = (10, 0, 0)
VTK_REQUIRED_SYMBOLS = (
    "vtkGLTFReader",
    "vtkOBJReader",
    "vtkCesium3DTilesWriter",
)
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


def _parse_version_tuple(version_str):
    nums = re.findall(r"\d+", str(version_str))
    major = int(nums[0]) if len(nums) > 0 else 0
    minor = int(nums[1]) if len(nums) > 1 else 0
    patch = int(nums[2]) if len(nums) > 2 else 0
    return (major, minor, patch)


def _format_tuple(v):
    return f"{v[0]}.{v[1]}.{v[2]}"


def _normalize_crs_input(crs_value):
    value = (crs_value or "").strip()
    if not value:
        return ""
    if value.upper() == "NOTSET":
        return ""
    if re.fullmatch(r"\d+", value):
        return f"EPSG:{value}"
    return value


def _find_proj_data_dir():
    # 1) Respect already configured environment
    for env_name in ("PROJ_LIB", "PROJ_DATA"):
        env_val = os.environ.get(env_name, "").strip()
        if env_val and os.path.exists(os.path.join(env_val, "proj.db")):
            return env_val

    # 2) pyproj data dir (most reliable on pip installs)
    try:
        from pyproj import datadir as pyproj_datadir
        data_dir = pyproj_datadir.get_data_dir()
        if data_dir and os.path.exists(os.path.join(data_dir, "proj.db")):
            return data_dir
    except Exception:
        pass

    # 3) Common system paths (macOS/Homebrew)
    for path in (
        "/opt/homebrew/share/proj",
        "/usr/local/share/proj",
    ):
        if os.path.exists(os.path.join(path, "proj.db")):
            return path

    # 4) Best effort in current python site-packages
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
    # EPSG references require PROJ database lookup.
    return _normalize_crs_input(crs_value).upper().startswith("EPSG:")


def _resolve_coordinates_config(scene):
    mode = scene.cesium_vtk_coordinates_mode

    if mode == 'SHIFT_VALUES':
        crs_value = (
            _normalize_crs_input(getattr(scene, "BL_epsg", ""))
            or _normalize_crs_input(getattr(scene, "cesium_vtk_crs", ""))
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
        crs_value = _normalize_crs_input(getattr(scene, "cesium_vtk_crs", ""))
        if not crs_value:
            crs_value = FALLBACK_LOCAL_CRS
        offset = (
            float(scene.cesium_vtk_offset_x),
            float(scene.cesium_vtk_offset_y),
            float(scene.cesium_vtk_offset_z),
        )
        return {
            "mode": mode,
            "crs": crs_value,
            "offset": offset,
            "requires_proj": _crs_requires_proj_db(crs_value),
        }, None

    # LOCAL_COORDS: no georeference transform, optional custom shift not applied
    return {
        "mode": mode,
        "crs": FALLBACK_LOCAL_CRS,
        "offset": None,
        "requires_proj": False,
    }, None


def check_vtk_requirements():
    info = {
        "is_installed": False,
        "version": None,
        "errors": [],
        "warnings": [],
        "supports_tree_type": False,
        "supports_merge_tile_poly_data": False,
        "supports_merged_texture_width": False,
    }
    try:
        import vtk
    except ImportError as exc:
        info["errors"].append(f"vtk import failed: {exc}")
        return False, info
    except Exception as exc:
        info["errors"].append(f"vtk import error: {exc}")
        return False, info

    info["is_installed"] = True

    version_str = ""
    try:
        version_str = vtk.vtkVersion.GetVTKVersion()
    except Exception:
        version_str = getattr(vtk, "__version__", "unknown")
    info["version"] = version_str

    version_tuple = _parse_version_tuple(version_str)
    if version_tuple < VTK_REQUIRED_MIN or version_tuple >= VTK_REQUIRED_MAX_EXCLUSIVE:
        info["errors"].append(
            f"vtk version {version_str} not in required range "
            f"[{_format_tuple(VTK_REQUIRED_MIN)}, {_format_tuple(VTK_REQUIRED_MAX_EXCLUSIVE)})"
        )

    for symbol in VTK_REQUIRED_SYMBOLS:
        if not hasattr(vtk, symbol):
            info["errors"].append(f"Missing vtk symbol: {symbol}")

    try:
        writer = vtk.vtkCesium3DTilesWriter()
        info["supports_tree_type"] = hasattr(writer, "SetTreeType")
        info["supports_merge_tile_poly_data"] = hasattr(writer, "SetMergeTilePolyData")
        info["supports_merged_texture_width"] = hasattr(writer, "SetMergedTextureWidth")
        if not info["supports_tree_type"]:
            info["warnings"].append("Tree algorithm is not exposed by this vtk build (Quadtree/Octree UI has no effect).")
    except Exception:
        pass

    if not _find_proj_data_dir():
        info["warnings"].append("proj.db not found (install pyproj to enable EPSG CRS transforms).")

    return len(info["errors"]) == 0, info


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
    return [
        cx, cy, cz,
        hx, 0.0, 0.0,
        0.0, hy, 0.0,
        0.0, 0.0, hz,
    ]


def _bbox_diag_len(bbox):
    (min_x, min_y, min_z), (max_x, max_y, max_z) = bbox
    return math.sqrt((max_x - min_x) ** 2 + (max_y - min_y) ** 2 + (max_z - min_z) ** 2)


def _prepare_base_mesh_object(context, active_obj, offset):
    temp_collection = bpy.data.collections.get("_cesium_native_tmp")
    if temp_collection is None:
        temp_collection = bpy.data.collections.new("_cesium_native_tmp")
        context.scene.collection.children.link(temp_collection)

    base_obj = active_obj.copy()
    base_obj.data = active_obj.data.copy()
    temp_collection.objects.link(base_obj)

    # Bake object transform into mesh coordinates.
    base_obj.data.transform(active_obj.matrix_world)
    if offset is not None:
        base_obj.data.transform(Matrix.Translation(Vector(offset)))
    base_obj.matrix_world = Matrix.Identity(4)

    return base_obj, temp_collection


def _build_face_spatial_data(mesh):
    verts = [v.co.copy() for v in mesh.vertices]
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
    if tree_type == 'OCTREE':
        for fid in face_ids:
            cx, cy, cz = centroids[fid]
            ix = 1 if cx >= mid_x else 0
            iy = 1 if cy >= mid_y else 0
            iz = 1 if cz >= mid_z else 0
            key = (ix, iy, iz)
            bins.setdefault(key, []).append(fid)
    else:
        for fid in face_ids:
            cx, cy, _ = centroids[fid]
            ix = 1 if cx >= mid_x else 0
            iy = 1 if cy >= mid_y else 0
            key = (ix, iy)
            bins.setdefault(key, []).append(fid)

    return [vals for vals in bins.values() if vals]


def _build_native_tree(face_ids, depth, tree_type, max_faces, max_depth, centroids, face_mins, face_maxs):
    bbox = _bbox_union_from_face_ids(face_ids, face_mins, face_maxs)
    node = {
        "depth": depth,
        "bbox": bbox,
        "face_ids": face_ids,
        "children": [],
    }

    if depth >= max_depth or len(face_ids) <= max_faces:
        return node

    split_groups = _split_face_ids(face_ids, centroids, bbox, tree_type)
    if len(split_groups) <= 1:
        return node

    for group in split_groups:
        child = _build_native_tree(
            face_ids=group,
            depth=depth + 1,
            tree_type=tree_type,
            max_faces=max_faces,
            max_depth=max_depth,
            centroids=centroids,
            face_mins=face_mins,
            face_maxs=face_maxs,
        )
        node["children"].append(child)

    return node


def _collect_native_leaves(node, out):
    if not node["children"]:
        out.append(node)
        return
    for child in node["children"]:
        _collect_native_leaves(child, out)


def _export_leaf_glb(context, base_obj, temp_collection, keep_face_ids, filepath):
    tile_obj = base_obj.copy()
    tile_obj.data = base_obj.data.copy()
    tile_obj_name = tile_obj.name
    tile_mesh_name = tile_obj.data.name
    temp_collection.objects.link(tile_obj)

    try:
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

        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        with _preserve_selection(context):
            bpy.ops.object.select_all(action='DESELECT')
            tile_obj.select_set(True)
            context.view_layer.objects.active = tile_obj
            result = bpy.ops.export_scene.gltf(
                filepath=filepath,
                use_selection=True,
                export_format='GLB',
            )
        return 'FINISHED' in result
    finally:
        # Robust cleanup: object may already be unlinked by Blender internals.
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


def _native_tree_to_tileset_node(node, root_error):
    tile = {
        "boundingVolume": {"box": _bbox_to_box(node["bbox"])},
        "geometricError": 0.0,
    }

    if node["children"]:
        depth = node["depth"]
        tile["geometricError"] = root_error / (2 ** max(depth, 0))
        tile["refine"] = "REPLACE"
        tile["children"] = [_native_tree_to_tileset_node(child, root_error) for child in node["children"]]
    else:
        uri = node.get("uri")
        if uri:
            tile["content"] = {"uri": uri}

    return tile


def _run_native_split_backend(context, scene, active_obj, output_dir, input_format, coords_cfg):
    if input_format == 'OBJ':
        texture_mode = "obj"
    else:
        texture_mode = "gltf"

    base_obj, temp_collection = _prepare_base_mesh_object(context, active_obj, coords_cfg["offset"])
    try:
        face_ids, centroids, face_mins, face_maxs = _build_face_spatial_data(base_obj.data)
        if not face_ids:
            return False, "Active mesh has no faces."

        max_faces = int(scene.cesium_vtk_features_per_tile)
        max_depth = int(scene.cesium_native_max_depth)
        tree_type = scene.cesium_vtk_tree_type

        tree = _build_native_tree(
            face_ids=face_ids,
            depth=0,
            tree_type=tree_type,
            max_faces=max_faces,
            max_depth=max_depth,
            centroids=centroids,
            face_mins=face_mins,
            face_maxs=face_maxs,
        )

        leaves = []
        _collect_native_leaves(tree, leaves)
        if not leaves:
            return False, "No leaves generated for native split."

        tile_counter = 1
        for leaf in leaves:
            tile_id = str(tile_counter)
            tile_counter += 1
            uri = f"{tile_id}/{tile_id}.glb"
            abs_path = os.path.join(output_dir, uri)
            ok = _export_leaf_glb(context, base_obj, temp_collection, leaf["face_ids"], abs_path)
            if not ok:
                return False, f"Failed exporting leaf tile {tile_id}."
            leaf["uri"] = uri

        root_error = max(_bbox_diag_len(tree["bbox"]), 1.0)
        tileset = {
            "asset": {"version": "1.0"},
            "geometricError": root_error,
            "root": _native_tree_to_tileset_node(tree, root_error),
        }

        tileset_path = os.path.join(output_dir, "tileset.json")
        with open(tileset_path, "w", encoding="utf-8") as f:
            json.dump(tileset, f, indent=2)

        note_path = os.path.join(output_dir, "native_backend_info.txt")
        with open(note_path, "w", encoding="utf-8") as f:
            f.write("Backend: NATIVE_SPLIT\n")
            f.write(f"Tree type: {tree_type}\n")
            f.write(f"Max depth: {max_depth}\n")
            f.write(f"Max faces per leaf: {max_faces}\n")
            f.write(f"Leaves: {len(leaves)}\n")
            f.write(f"Texture mode: {texture_mode}\n")

        return True, f"Native split completed ({len(leaves)} leaf tiles)."
    finally:
        try:
            bpy.data.meshes.remove(base_obj.data, do_unlink=True)
        except Exception:
            pass
        try:
            bpy.data.objects.remove(base_obj, do_unlink=True)
        except Exception:
            pass


def _run_vtk_conversion_subprocess(payload, output_dir):
    script = r"""
import json
import os
import sys
import traceback

def _find_proj_db(vtk_module, payload_proj_dir):
    candidates = []
    if payload_proj_dir:
        candidates.append(payload_proj_dir)
    for env_name in ("PROJ_LIB", "PROJ_DATA"):
        env_val = os.environ.get(env_name, "").strip()
        if env_val:
            candidates.append(env_val)

    try:
        from pyproj import datadir as pyproj_datadir
        p = pyproj_datadir.get_data_dir()
        if p:
            candidates.append(p)
    except Exception:
        pass

    candidates.extend([
        "/opt/homebrew/share/proj",
        "/usr/local/share/proj",
    ])

    roots = []
    try:
        roots.append(os.path.dirname(vtk_module.__file__))
    except Exception:
        pass
    try:
        import vtkmodules
        roots.append(os.path.dirname(vtkmodules.__file__))
    except Exception:
        pass
    for root in roots:
        if not root:
            continue
        root = os.path.abspath(root)
        candidates.extend([
            root,
            os.path.abspath(os.path.join(root, "..")),
            os.path.abspath(os.path.join(root, "share")),
            os.path.abspath(os.path.join(root, "share/proj")),
            os.path.abspath(os.path.join(root, "../share")),
            os.path.abspath(os.path.join(root, "../share/proj")),
            os.path.abspath(os.path.join(root, "vtkmodules/share/proj")),
        ])

    checked = set()
    for cand in candidates:
        if not cand:
            continue
        cand = os.path.abspath(cand)
        if cand in checked:
            continue
        checked.add(cand)
        if os.path.exists(os.path.join(cand, "proj.db")):
            return cand
    return None


def main():
    payload = json.loads(sys.argv[1])
    import vtk

    input_file = payload["input_file"]
    input_format = payload["input_format"]
    output_dir = payload["output_dir"]
    tree_type = payload["tree_type"]
    features_per_tile = int(payload["features_per_tile"])
    texture_dir = payload.get("texture_dir", "")
    crs = payload.get("crs", "")
    proj_data_dir = payload.get("proj_data_dir", "")
    offset = payload.get("offset", None)
    merge_tile_poly_data = bool(payload.get("merge_tile_poly_data", False))
    merged_texture_width = int(payload.get("merged_texture_width", 4096))

    proj_path = _find_proj_db(vtk, proj_data_dir)
    if proj_path:
        os.environ.setdefault("PROJ_LIB", proj_path)
        os.environ.setdefault("PROJ_DATA", proj_path)
        print("DEBUG PROJ path:", proj_path)
    else:
        print("DEBUG PROJ path: not found")

    if input_format == "OBJ":
        reader = vtk.vtkOBJReader()
    else:
        reader = vtk.vtkGLTFReader()
    reader.SetFileName(input_file)
    reader.Update()

    writer = vtk.vtkCesium3DTilesWriter()
    dbg_methods = sorted([
        m for m in dir(writer)
        if any(tag in m for tag in ("Tree", "Feature", "Texture", "Input", "Crs", "CRS", "Projection", "EPSG"))
    ])
    print("DEBUG writer methods:")
    for m in dbg_methods:
        print("  -", m)
    sys.stdout.flush()

    if hasattr(writer, "SetInputType"):
        writer_cls = vtk.vtkCesium3DTilesWriter
        mesh_enum = getattr(writer_cls, "Mesh", None)
        if mesh_enum is None:
            mesh_enum = getattr(writer_cls, "MESH", None)
        if mesh_enum is not None:
            writer.SetInputType(mesh_enum)

    writer.SetInputConnection(reader.GetOutputPort())
    writer.SetDirectoryName(output_dir)

    if offset and hasattr(writer, "SetOffset"):
        writer.SetOffset(float(offset[0]), float(offset[1]), float(offset[2]))

    if hasattr(writer, "SetCRS") and crs:
        writer.SetCRS(crs)

    if hasattr(writer, "SetContentGLTF"):
        writer.SetContentGLTF(True)
    if hasattr(writer, "SetContentGLTFSaveGLB"):
        writer.SetContentGLTFSaveGLB(True)
    if hasattr(writer, "SetSaveTiles"):
        writer.SetSaveTiles(True)
    if hasattr(writer, "SetSaveTextures"):
        writer.SetSaveTextures(True)

    if hasattr(writer, "SetTreeType"):
        writer_cls = vtk.vtkCesium3DTilesWriter
        if tree_type == "QUADTREE":
            enum_val = getattr(writer_cls, "QUADTREE", None)
        else:
            enum_val = getattr(writer_cls, "OCTREE", None)
        if enum_val is not None:
            writer.SetTreeType(enum_val)

    if hasattr(writer, "SetNumberOfFeaturesPerTile"):
        writer.SetNumberOfFeaturesPerTile(features_per_tile)
    if hasattr(writer, "SetMergeTilePolyData"):
        writer.SetMergeTilePolyData(merge_tile_poly_data)
    if hasattr(writer, "SetMergedTextureWidth"):
        writer.SetMergedTextureWidth(merged_texture_width)

    if texture_dir and hasattr(writer, "SetTextureBaseDirectory"):
        writer.SetTextureBaseDirectory(texture_dir)

    writer.Write()
    return 0

if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except Exception:
        traceback.print_exc()
        raise SystemExit(2)
"""

    with tempfile.NamedTemporaryFile(mode="w", suffix="_vtk_tiles.py", delete=False, encoding="utf-8") as handle:
        handle.write(script)
        script_path = handle.name

    try:
        cmd = [sys.executable, script_path, json.dumps(payload)]
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=3600,
        )
    finally:
        try:
            os.remove(script_path)
        except OSError:
            pass

    log_path = os.path.join(output_dir, "vtk_conversion.log")
    try:
        with open(log_path, "w", encoding="utf-8") as log_file:
            log_file.write("Command:\n")
            log_file.write(" ".join(cmd))
            log_file.write("\n\n--- STDOUT ---\n")
            log_file.write(result.stdout or "")
            log_file.write("\n--- STDERR ---\n")
            log_file.write(result.stderr or "")
            log_file.write("\n")
    except OSError:
        log_path = ""

    return result.returncode, (result.stdout or ""), (result.stderr or ""), log_path


class OBJECT_OT_reload_vtk_modules(bpy.types.Operator):
    """Reload Python module paths and retry vtk import."""
    bl_idname = "cesium_vtk.reload_modules"
    bl_label = "Reload Python Paths"

    def execute(self, context):
        try:
            site.main()
            if "vtk" in sys.modules:
                importlib.reload(sys.modules["vtk"])
            ok, info = check_vtk_requirements()
            if ok:
                self.report({'INFO'}, f"vtk ready (version: {info['version']})")
            else:
                details = "; ".join(info["errors"]) if info["errors"] else "unknown error"
                self.report({'WARNING'}, f"vtk still unavailable: {details}")
            return {'FINISHED'}
        except Exception as exc:
            self.report({'ERROR'}, f"Error reloading Python paths: {exc}")
            return {'CANCELLED'}


class OBJECT_OT_clear_cesium_vtk_folder(bpy.types.Operator):
    """Empty working/output folder contents without deleting the folder itself."""
    bl_idname = "object.clear_cesium_vtk_folder"
    bl_label = "Clear Cesium Folder"
    bl_options = {'REGISTER'}

    target: bpy.props.EnumProperty(
        name="Target folder",
        items=[
            ('WORK', 'Working folder', 'Clear working folder contents'),
            ('OUTPUT', 'Output folder', 'Clear output folder contents'),
        ],
        default='WORK',
    ) # type: ignore

    def invoke(self, context, event):
        return context.window_manager.invoke_confirm(self, event)

    def execute(self, context):
        scene = context.scene
        folder = (
            bpy.path.abspath(scene.cesium_vtk_work_dir).strip()
            if self.target == 'WORK'
            else bpy.path.abspath(scene.cesium_vtk_output_dir).strip()
        )
        target_name = "working" if self.target == 'WORK' else "output"

        if not folder:
            self.report({'ERROR'}, f"Set a valid {target_name} folder first.")
            return {'CANCELLED'}
        if not os.path.isdir(folder):
            self.report({'ERROR'}, f"{target_name.title()} folder does not exist: {folder}")
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
            self.report({'INFO'}, f"Cleared {removed} item(s) from {target_name} folder.")
        return {'FINISHED'}


class OBJECT_OT_apply_cesium_vtk_preset(bpy.types.Operator):
    """Apply quick tiling presets."""
    bl_idname = "object.apply_cesium_vtk_preset"
    bl_label = "Apply Cesium Preset"
    bl_options = {'REGISTER'}

    def execute(self, context):
        scene = context.scene
        preset = scene.cesium_vtk_quick_preset

        if preset == 'PYRAMID_AGGRESSIVE':
            scene.cesium_vtk_features_per_tile = 3000
            scene.cesium_vtk_merge_tile_poly_data = False
            scene.cesium_vtk_merged_texture_width = 2048
            scene.cesium_vtk_tree_type = 'QUADTREE'
        elif preset == 'BALANCED':
            scene.cesium_vtk_features_per_tile = 8000
            scene.cesium_vtk_merge_tile_poly_data = False
            scene.cesium_vtk_merged_texture_width = 4096
            scene.cesium_vtk_tree_type = 'QUADTREE'
        else:  # FEW_TILES
            scene.cesium_vtk_features_per_tile = 25000
            scene.cesium_vtk_merge_tile_poly_data = True
            scene.cesium_vtk_merged_texture_width = 4096
            scene.cesium_vtk_tree_type = 'OCTREE'

        self.report({'INFO'}, f"Applied preset: {preset}")
        return {'FINISHED'}


class OBJECT_OT_export_cesium_vtk_tiles(bpy.types.Operator):
    bl_idname = "object.export_cesium_vtk_tiles"
    bl_label = "Export Cesium 3D Tiles (VTK)"
    bl_description = "Export active mesh to an intermediate file and convert it to Cesium 3D Tiles"
    bl_options = {'REGISTER'}

    def execute(self, context):
        scene = context.scene
        source_mode = scene.cesium_vtk_source_mode
        backend = scene.cesium_tiles_backend
        output_root = bpy.path.abspath(scene.cesium_vtk_output_dir).strip()
        work_dir = bpy.path.abspath(scene.cesium_vtk_work_dir).strip()

        if not output_root:
            self.report({'ERROR'}, "Set a valid output directory.")
            return {'CANCELLED'}

        req_info = {"supports_tree_type": False, "supports_merged_texture_width": False}
        if backend == 'VTK':
            requirements_ok, req_info = check_vtk_requirements()
            if not requirements_ok:
                details = "; ".join(req_info["errors"]) if req_info["errors"] else "unknown error"
                self.report({'ERROR'}, f"VTK requirements not met: {details}")
                return {'CANCELLED'}

        active_obj = context.active_object
        generated_intermediate = False

        if source_mode == 'ACTIVE_MESH':
            if active_obj is None or active_obj.type != 'MESH':
                self.report({'ERROR'}, "Select an active mesh object.")
                return {'CANCELLED'}
            if not work_dir:
                self.report({'ERROR'}, "Set a valid working directory.")
                return {'CANCELLED'}
            obj_name = _sanitize_name(active_obj.name)
            intermediate_dir = os.path.join(work_dir, obj_name)
            input_format = scene.cesium_vtk_intermediate_format
            generated_intermediate = True
        else:
            existing_obj_path = bpy.path.abspath(scene.cesium_vtk_existing_obj_file).strip()
            if not existing_obj_path:
                self.report({'ERROR'}, "Set a valid OBJ file path.")
                return {'CANCELLED'}
            if not os.path.exists(existing_obj_path):
                self.report({'ERROR'}, f"OBJ file not found: {existing_obj_path}")
                return {'CANCELLED'}
            if os.path.splitext(existing_obj_path)[1].lower() != ".obj":
                self.report({'ERROR'}, "Only .obj files are supported in 'Existing OBJ file' mode.")
                return {'CANCELLED'}
            obj_name = _sanitize_name(os.path.splitext(os.path.basename(existing_obj_path))[0])
            intermediate_dir = os.path.dirname(existing_obj_path)
            input_format = 'OBJ'

        output_dir = os.path.join(output_root, obj_name) if scene.cesium_vtk_create_object_subdir else output_root
        os.makedirs(output_dir, exist_ok=True)

        coords_cfg, cfg_error = _resolve_coordinates_config(scene)
        if cfg_error:
            self.report({'ERROR'}, cfg_error)
            return {'CANCELLED'}

        # Native backend: real quadtree/octree split in Blender space.
        if backend == 'NATIVE_SPLIT':
            if source_mode != 'ACTIVE_MESH':
                self.report({'ERROR'}, "Native split backend currently supports only 'Export active mesh' source mode.")
                return {'CANCELLED'}
            if active_obj is None or active_obj.type != 'MESH':
                self.report({'ERROR'}, "Select an active mesh object.")
                return {'CANCELLED'}

            ok, msg = _run_native_split_backend(
                context=context,
                scene=scene,
                active_obj=active_obj,
                output_dir=output_dir,
                input_format=input_format,
                coords_cfg=coords_cfg,
            )
            if not ok:
                self.report({'ERROR'}, msg)
                return {'CANCELLED'}

            self.report({'INFO'}, msg)
            return {'FINISHED'}

        if source_mode == 'ACTIVE_MESH':
            os.makedirs(intermediate_dir, exist_ok=True)
            if input_format == 'GLB':
                input_file = os.path.join(intermediate_dir, f"{obj_name}.glb")
                export_format = 'GLB'
            elif input_format == 'OBJ':
                input_file = os.path.join(intermediate_dir, f"{obj_name}.obj")
                export_format = None
            else:
                input_file = os.path.join(intermediate_dir, f"{obj_name}.gltf")
                export_format = 'GLTF_SEPARATE'

            with _preserve_selection(context):
                bpy.ops.object.select_all(action='DESELECT')
                active_obj.select_set(True)
                context.view_layer.objects.active = active_obj

                if input_format == 'OBJ':
                    result = _export_obj(
                        filepath=input_file,
                        use_selection=True,
                    )
                else:
                    result = bpy.ops.export_scene.gltf(
                        filepath=input_file,
                        use_selection=True,
                        export_format=export_format,
                    )
                if 'FINISHED' not in result:
                    self.report({'ERROR'}, "Intermediate export failed.")
                    return {'CANCELLED'}
        else:
            input_file = bpy.path.abspath(scene.cesium_vtk_existing_obj_file).strip()

        texture_dir = ""
        if input_format == 'OBJ':
            texture_dir = bpy.path.abspath(scene.cesium_vtk_texture_base_dir).strip()
            if not texture_dir:
                texture_dir = intermediate_dir

        proj_data_dir = _find_proj_data_dir()
        if coords_cfg["requires_proj"] and not proj_data_dir:
            self.report(
                {'ERROR'},
                "proj.db not found. Install `vtk_cesium` requirements (includes pyproj) and restart Blender.",
            )
            return {'CANCELLED'}

        payload = {
            "input_file": input_file,
            "input_format": input_format,
            "output_dir": output_dir,
            "tree_type": scene.cesium_vtk_tree_type,
            "features_per_tile": scene.cesium_vtk_features_per_tile,
            "merge_tile_poly_data": scene.cesium_vtk_merge_tile_poly_data,
            "merged_texture_width": scene.cesium_vtk_merged_texture_width,
            "texture_dir": texture_dir,
            "crs": coords_cfg["crs"],
            "proj_data_dir": proj_data_dir,
            "offset": coords_cfg["offset"],
        }
        try:
            return_code, stdout_txt, stderr_txt, log_path = _run_vtk_conversion_subprocess(payload, output_dir)
        except subprocess.TimeoutExpired:
            self.report({'ERROR'}, "VTK conversion timed out after 1 hour.")
            return {'CANCELLED'}
        except Exception as exc:
            self.report({'ERROR'}, f"Failed to start VTK conversion subprocess: {exc}")
            return {'CANCELLED'}

        if return_code != 0:
            if return_code < 0:
                signal_num = -return_code
                msg = f"VTK subprocess crashed with signal {signal_num}."
            else:
                msg = f"VTK subprocess failed with exit code {return_code}."
            if log_path:
                msg += f" See log: {log_path}"
            elif stderr_txt:
                msg += f" Error: {stderr_txt[:220]}"
            self.report({'ERROR'}, msg)
            return {'CANCELLED'}

        tileset_path = os.path.join(output_dir, "tileset.json")
        if not os.path.exists(tileset_path):
            self.report({'WARNING'}, f"Conversion completed, but `{tileset_path}` was not found.")
        else:
            self.report({'INFO'}, f"Tileset created: {tileset_path}")

        if scene.cesium_vtk_cleanup_intermediate and generated_intermediate:
            try:
                for file_name in os.listdir(intermediate_dir):
                    file_path = os.path.join(intermediate_dir, file_name)
                    if os.path.isfile(file_path):
                        os.remove(file_path)
            except Exception:
                self.report({'WARNING'}, "Intermediate files were kept (cleanup failed).")
        elif scene.cesium_vtk_cleanup_intermediate and not generated_intermediate:
            self.report({'INFO'}, "Cleanup skipped: external OBJ source is not deleted.")

        return {'FINISHED'}


class VIEW3D_PT_cesium_vtk_export(bpy.types.Panel):
    bl_label = "Cesium VTK Tiles"
    bl_idname = "VIEW3D_PT_cesium_vtk_export"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = '3DSC'
    bl_context = "objectmode"
    bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        layout = self.layout
        scene = context.scene
        active_obj = context.active_object
        source_mode = scene.cesium_vtk_source_mode
        backend = scene.cesium_tiles_backend
        requirements_ok, req_info = check_vtk_requirements() if backend == 'VTK' else (True, {"warnings": []})

        box_backend = layout.box()
        box_backend.label(text="Backend")
        box_backend.prop(scene, "cesium_tiles_backend", text="")
        if backend == 'NATIVE_SPLIT':
            box_backend.label(text="Native split backend: quadtree/octree is fully controlled here.", icon='CHECKMARK')
            box_backend.label(text="This mode does not use vtkCesium3DTilesWriter.", icon='INFO')

        if backend == 'VTK':
            box_req = layout.box()
            box_req.label(text="VTK Dependency Check")
            if requirements_ok:
                box_req.label(text=f"vtk version: {req_info['version']}", icon='CHECKMARK')
                for warn in req_info.get("warnings", [])[:2]:
                    box_req.label(text=warn, icon='INFO')
                if any("proj.db not found" in w for w in req_info.get("warnings", [])):
                    row = box_req.row(align=True)
                    op = row.operator("install_3dsc_missing.modules", icon="IMPORT", text="Install pyproj (proj.db)")
                    op.is_install = True
                    op.list_modules_to_install = "pyproj_cesium"
                    row.operator("cesium_vtk.reload_modules", icon="FILE_REFRESH", text="Reload Python Paths")
            else:
                box_req.label(text="vtk requirements are not satisfied", icon='ERROR')
                for err in req_info["errors"][:4]:
                    box_req.label(text=err)
                box_req.label(
                    text=(
                        f"Required: vtk >= {_format_tuple(VTK_REQUIRED_MIN)} and "
                        f"< {_format_tuple(VTK_REQUIRED_MAX_EXCLUSIVE)}"
                    )
                )
                row = layout.row(align=True)
                row.operator("cesium_vtk.reload_modules", icon="FILE_REFRESH", text="Reload Python Paths")
                op = row.operator("install_3dsc_missing.modules", icon="IMPORT", text="Install vtk module")
                op.is_install = True
                op.list_modules_to_install = "vtk_cesium"
                row = layout.row(align=True)
                op = row.operator("install_3dsc_missing.modules", icon="TRASH", text="Uninstall vtk module")
                op.is_install = False
                op.list_modules_to_install = "vtk_cesium"
                info_box = layout.box()
                info_box.label(text="Tip: restart Blender after install/uninstall.")
                return

        box_source = layout.box()
        box_source.label(text="Source")
        box_source.prop(scene, "cesium_vtk_source_mode")
        if source_mode == 'ACTIVE_MESH':
            box_source.label(text="Workflow: 1 mesh at a time", icon='INFO')
            if active_obj is not None and active_obj.type == 'MESH':
                box_source.label(text=f"Active mesh: {active_obj.name}", icon='MESH_DATA')
            else:
                box_source.label(text="No active mesh selected", icon='ERROR')
        else:
            box_source.prop(scene, "cesium_vtk_existing_obj_file")
            box_source.label(text="Use an existing OBJ + MTL/texture set on disk.", icon='INFO')

        box = layout.box()
        box.label(text="Paths")
        if source_mode == 'ACTIVE_MESH':
            row = box.row(align=True)
            row.prop(scene, "cesium_vtk_work_dir")
            op = row.operator("object.clear_cesium_vtk_folder", text="", icon='TRASH')
            op.target = 'WORK'
        row = box.row(align=True)
        row.prop(scene, "cesium_vtk_output_dir")
        op = row.operator("object.clear_cesium_vtk_folder", text="", icon='TRASH')
        op.target = 'OUTPUT'

        show_texture_dir = (
            source_mode == 'EXISTING_OBJ'
            or (source_mode == 'ACTIVE_MESH' and scene.cesium_vtk_intermediate_format == 'OBJ')
        )
        if show_texture_dir:
            box.prop(scene, "cesium_vtk_texture_base_dir")
            box.label(text="Useful for OBJ/MTL when textures are in a separate folder.", icon='INFO')
        else:
            box.label(text="Texture base dir is usually not needed for GLTF/GLB.", icon='INFO')
        box.prop(scene, "cesium_vtk_create_object_subdir")

        box = layout.box()
        box.label(text="Conversion Parameters")
        row = box.row(align=True)
        row.prop(scene, "cesium_vtk_quick_preset")
        row.operator("object.apply_cesium_vtk_preset", text="Apply")
        box.prop(scene, "cesium_vtk_coordinates_mode")
        if scene.cesium_vtk_coordinates_mode == 'SHIFT_VALUES':
            box.label(text=f"SHIFT EPSG: {getattr(scene, 'BL_epsg', 'NotSet')}")
            box.label(text=f"SHIFT XYZ: {getattr(scene, 'BL_x_shift', 0.0):.3f}, {getattr(scene, 'BL_y_shift', 0.0):.3f}, {getattr(scene, 'BL_z_shift', 0.0):.3f}")
            box.prop(scene, "cesium_vtk_crs", text="CRS override")
        elif scene.cesium_vtk_coordinates_mode == 'CUSTOM_COORDS':
            box.prop(scene, "cesium_vtk_crs")
            row = box.row(align=True)
            row.prop(scene, "cesium_vtk_offset_x", text="Coord X")
            row.prop(scene, "cesium_vtk_offset_y", text="Coord Y")
            row.prop(scene, "cesium_vtk_offset_z", text="Coord Z")
            box.label(text="CRS optional: if empty, geocentric fallback is used.", icon='INFO')
        else:
            box.label(text="Local coordinates mode uses geocentric fallback CRS.", icon='INFO')
        if source_mode == 'ACTIVE_MESH':
            box.prop(scene, "cesium_vtk_intermediate_format")
        else:
            box.label(text="Intermediate format: OBJ (fixed)")
        row = box.row()
        row.enabled = (backend == 'NATIVE_SPLIT') or req_info.get("supports_tree_type", False)
        row.prop(scene, "cesium_vtk_tree_type")
        if backend == 'VTK' and not req_info.get("supports_tree_type", False):
            box.label(text="Tree algorithm not available in this vtk build.", icon='INFO')
        box.prop(scene, "cesium_vtk_features_per_tile")
        if backend == 'NATIVE_SPLIT':
            box.prop(scene, "cesium_native_max_depth")
        box.prop(scene, "cesium_vtk_merge_tile_poly_data")
        row = box.row()
        row.enabled = (backend == 'NATIVE_SPLIT') or req_info.get("supports_merged_texture_width", False)
        row.prop(scene, "cesium_vtk_merged_texture_width")
        row = box.row()
        row.enabled = source_mode == 'ACTIVE_MESH'
        row.prop(scene, "cesium_vtk_cleanup_intermediate")

        layout.operator("object.export_cesium_vtk_tiles", icon='EXPORT')


classes = (
    OBJECT_OT_reload_vtk_modules,
    OBJECT_OT_clear_cesium_vtk_folder,
    OBJECT_OT_apply_cesium_vtk_preset,
    OBJECT_OT_export_cesium_vtk_tiles,
    VIEW3D_PT_cesium_vtk_export,
)


def register():
    ok, info = check_vtk_requirements()
    if ok:
        print(f"Cesium VTK: vtk ready (version {info['version']})")
    else:
        errs = "; ".join(info["errors"]) if info["errors"] else "unknown reason"
        print(f"Cesium VTK: vtk requirements not met: {errs}")

    for cls in classes:
        bpy.utils.register_class(cls)

    bpy.types.Scene.cesium_tiles_backend = bpy.props.EnumProperty(
        name="Tiles backend",
        items=[
            ('NATIVE_SPLIT', 'Native Split', 'Split mesh directly in Blender and build tileset.json hierarchy'),
            ('VTK', 'VTK Writer', 'Use vtkCesium3DTilesWriter backend'),
        ],
        default='NATIVE_SPLIT',
    )
    bpy.types.Scene.cesium_vtk_source_mode = bpy.props.EnumProperty(
        name="Source mode",
        items=[
            ('ACTIVE_MESH', 'Export active mesh', 'Export active mesh first, then convert'),
            ('EXISTING_OBJ', 'Use existing OBJ file', 'Convert an OBJ already present on disk'),
        ],
        default='ACTIVE_MESH',
    )
    bpy.types.Scene.cesium_vtk_existing_obj_file = bpy.props.StringProperty(
        name="Existing OBJ file",
        subtype='FILE_PATH',
        default="",
        description="Path to an existing .obj file to convert directly",
    )
    bpy.types.Scene.cesium_vtk_work_dir = bpy.props.StringProperty(
        name="Working folder",
        subtype='DIR_PATH',
        default="",
        description="Folder used for intermediate exports with textures",
    )
    bpy.types.Scene.cesium_vtk_output_dir = bpy.props.StringProperty(
        name="Tiles output folder",
        subtype='DIR_PATH',
        default="",
        description="Destination folder for Cesium 3D Tiles output",
    )
    bpy.types.Scene.cesium_vtk_texture_base_dir = bpy.props.StringProperty(
        name="Texture base dir (optional)",
        subtype='DIR_PATH',
        default="",
        description="Optional texture base directory passed to vtkCesium3DTilesWriter",
    )
    bpy.types.Scene.cesium_vtk_crs = bpy.props.StringProperty(
        name="CRS",
        default="",
        description="Input CRS (e.g. EPSG:32632). If empty, SHIFT panel EPSG is used.",
    )
    bpy.types.Scene.cesium_vtk_coordinates_mode = bpy.props.EnumProperty(
        name="Coordinates mode",
        items=[
            ('SHIFT_VALUES', 'Use SHIFT values', 'Use EPSG and XYZ from SHIFT panel'),
            ('LOCAL_COORDS', 'Use local coordinates', 'Do not apply CRS/offset transform'),
            ('CUSTOM_COORDS', 'Use custom coordinates', 'Use custom XYZ and optional CRS override'),
        ],
        default='SHIFT_VALUES',
    )
    bpy.types.Scene.cesium_vtk_offset_x = bpy.props.FloatProperty(
        name="Offset X",
        default=0.0,
    )
    bpy.types.Scene.cesium_vtk_offset_y = bpy.props.FloatProperty(
        name="Offset Y",
        default=0.0,
    )
    bpy.types.Scene.cesium_vtk_offset_z = bpy.props.FloatProperty(
        name="Offset Z",
        default=0.0,
    )
    bpy.types.Scene.cesium_vtk_intermediate_format = bpy.props.EnumProperty(
        name="Intermediate format",
        items=[
            ('GLB', 'GLB', 'Export one binary glTF file before conversion'),
            ('GLTF', 'glTF + Textures', 'Export glTF with external texture files before conversion'),
            ('OBJ', 'OBJ + MTL', 'Export OBJ with material file before conversion'),
        ],
        default='GLTF',
    )
    bpy.types.Scene.cesium_vtk_tree_type = bpy.props.EnumProperty(
        name="Tree algorithm",
        items=[
            ('QUADTREE', 'Quadtree', 'Best for wide horizontal scenes'),
            ('OCTREE', 'Octree', 'Best for volumetric scenes'),
        ],
        default='QUADTREE',
    )
    bpy.types.Scene.cesium_vtk_features_per_tile = bpy.props.IntProperty(
        name="Features per tile",
        default=20000,
        min=100,
        description="Approximate complexity budget per generated tile",
    )
    bpy.types.Scene.cesium_native_max_depth = bpy.props.IntProperty(
        name="Max tree depth",
        default=8,
        min=1,
        max=20,
        description="Maximum recursion depth for Native Split quadtree/octree",
    )
    bpy.types.Scene.cesium_vtk_quick_preset = bpy.props.EnumProperty(
        name="Quick preset",
        items=[
            ('PYRAMID_AGGRESSIVE', 'Aggressive hierarchy', 'More/smaller tiles, deeper tree'),
            ('BALANCED', 'Balanced', 'Good default for medium scenes'),
            ('FEW_TILES', 'Few tiles', 'Larger tiles, less hierarchy'),
        ],
        default='BALANCED',
    )
    bpy.types.Scene.cesium_vtk_merge_tile_poly_data = bpy.props.BoolProperty(
        name="Merge tile polydata",
        default=False,
        description="If enabled, writer may merge geometries while tiling (can reduce tile granularity)",
    )
    bpy.types.Scene.cesium_vtk_merged_texture_width = bpy.props.IntProperty(
        name="Merged texture width",
        default=4096,
        min=256,
        description="Texture atlas width used by vtkCesium3DTilesWriter when merge mode is active",
    )
    bpy.types.Scene.cesium_vtk_cleanup_intermediate = bpy.props.BoolProperty(
        name="Delete intermediate files",
        default=False,
        description="Delete exported GLB/GLTF/OBJ files after VTK conversion",
    )
    bpy.types.Scene.cesium_vtk_create_object_subdir = bpy.props.BoolProperty(
        name="Create object subfolder",
        default=True,
        description="Write tiles into an object-name subfolder under output path",
    )


def unregister():
    del bpy.types.Scene.cesium_tiles_backend
    del bpy.types.Scene.cesium_vtk_source_mode
    del bpy.types.Scene.cesium_vtk_existing_obj_file
    del bpy.types.Scene.cesium_vtk_work_dir
    del bpy.types.Scene.cesium_vtk_output_dir
    del bpy.types.Scene.cesium_vtk_texture_base_dir
    del bpy.types.Scene.cesium_vtk_crs
    del bpy.types.Scene.cesium_vtk_coordinates_mode
    del bpy.types.Scene.cesium_vtk_offset_x
    del bpy.types.Scene.cesium_vtk_offset_y
    del bpy.types.Scene.cesium_vtk_offset_z
    del bpy.types.Scene.cesium_vtk_intermediate_format
    del bpy.types.Scene.cesium_vtk_tree_type
    del bpy.types.Scene.cesium_vtk_features_per_tile
    del bpy.types.Scene.cesium_native_max_depth
    del bpy.types.Scene.cesium_vtk_quick_preset
    del bpy.types.Scene.cesium_vtk_merge_tile_poly_data
    del bpy.types.Scene.cesium_vtk_merged_texture_width
    del bpy.types.Scene.cesium_vtk_cleanup_intermediate
    del bpy.types.Scene.cesium_vtk_create_object_subdir

    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()
