import os

import bpy


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
