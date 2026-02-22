import json
import os

import bmesh
import bpy

from .glb_unlit import _patch_glb_to_unlit
from .implicit import (
    _bitarray_set_once,
    _implicit_level_offset,
    _implicit_morton_index,
    _implicit_total_nodes,
    _write_subtree_file,
)
from .lod import _cleanup_lod_image_cache, _compute_lod_parameters, _prepare_lod_image_cache
from .native_bake import _cleanup_native_bake_assets, _native_bake_basecolor_texture, _prepare_base_mesh_object, _rebake_node_texture
from .native_tree import (
    _build_face_spatial_data,
    _build_native_tree,
    _collect_native_leaves,
    _collect_native_nodes,
    _collect_nodes_at_depth,
)
from .shared import _add_to_cesium_log, _preserve_selection
from .stats import _build_gltf_export_kwargs
from .tileset_stitcher import _bbox_diag_len, _bbox_to_box, _bbox_union_from_face_ids


def _export_node_glb(
    context, base_obj, temp_collection, keep_face_ids, filepath,
    force_unlit=False, export_yup=True,
    decimation_ratio=1.0, preserve_borders=True,
    lod_image=None,
    lod_strategy='REBAKE',
    rebake_atlas_size=None,
    rebake_margin_px=8,
    scene=None,
):
    """Export a GLB for a tree node.

    For leaf nodes: decimation_ratio=1.0, lod_image=None (uses full mesh+texture).
    For internal LOD nodes with REBAKE strategy: decimate, re-UV, re-bake from base_obj.
    For internal LOD nodes with legacy behavior: decimation_ratio<1.0, lod_image=downsampled atlas.
    """
    tile_obj = base_obj.copy()
    tile_obj.data = base_obj.data.copy()
    tile_obj_name = tile_obj.name
    tile_mesh_name = tile_obj.data.name
    temp_collection.objects.link(tile_obj)

    # Track rebake artifacts for cleanup
    _rebake_img_name = None
    _rebake_mat_name = None

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

            # 2b) Re-bake texture onto decimated mesh (LODgenerator pattern)
            if lod_strategy == 'REBAKE' and rebake_atlas_size is not None and scene is not None:
                ok_rb, rb_img, rb_mat = _rebake_node_texture(
                    context, scene, base_obj, tile_obj,
                    atlas_size=rebake_atlas_size,
                    margin_px=rebake_margin_px,
                )
                if ok_rb and rb_mat is not None:
                    _rebake_img_name = rb_img.name if rb_img else None
                    _rebake_mat_name = rb_mat.name
                    tile_obj.data.materials.clear()
                    tile_obj.data.materials.append(rb_mat)
                    for poly in tile_obj.data.polygons:
                        poly.material_index = 0
                    tile_obj.data.update()
                    # Skip step 3 (texture swap) — we have a fresh bake
                    lod_image = None

        # 3) Swap texture to LOD-sized atlas if provided (legacy path, skipped if REBAKE succeeded)
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
        # DEBUG: cleanup disabled – keep temp objects in Blender for inspection
        pass
        # obj = bpy.data.objects.get(tile_obj_name)
        # if obj is not None:
        #     try:
        #         bpy.data.objects.remove(obj, do_unlink=True)
        #     except Exception:
        #         pass
        # mesh = bpy.data.meshes.get(tile_mesh_name)
        # if mesh is not None and mesh.users == 0:
        #     try:
        #         bpy.data.meshes.remove(mesh, do_unlink=True)
        #     except Exception:
        #         pass
        # # Cleanup rebake artifacts (material + image created per-node)
        # if _rebake_mat_name:
        #     mat = bpy.data.materials.get(_rebake_mat_name)
        #     if mat is not None and mat.users == 0:
        #         try:
        #             bpy.data.materials.remove(mat, do_unlink=True)
        #         except Exception:
        #             pass
        # if _rebake_img_name:
        #     img = bpy.data.images.get(_rebake_img_name)
        #     if img is not None and img.users == 0:
        #         try:
        #             bpy.data.images.remove(img, do_unlink=True)
        #         except Exception:
        #             pass


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
    lod_strategy = str(getattr(scene, "cesium_lod_strategy", "REBAKE")) if lod_mode else "LEAF_ONLY"
    rebake_margin = int(getattr(scene, "cesium_native_bake_margin", 8))

    for node in nodes:
        level = int(node.get("depth", 0))
        x = int(node.get("grid_x", 0))
        y = int(node.get("grid_y", 0))
        z = int(node.get("grid_z", 0))

        bit_idx = _implicit_level_offset(level, tree_type) + _implicit_morton_index(node, tree_type)
        is_leaf = not node["children"]

        # LEAF_ONLY strategy: skip internal nodes entirely
        if lod_strategy == 'LEAF_ONLY' and not is_leaf:
            if _bitarray_set_once(tile_bits, bit_idx):
                tile_count += 1
            continue

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
        rebake_atlas_sz = None
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
                if lod_strategy == 'REBAKE':
                    rebake_atlas_sz = atlas_sz
                elif lod_image_cache and atlas_sz in lod_image_cache:
                    lod_image = lod_image_cache[atlas_sz]

        ok = _export_node_glb(
            context, base_obj, temp_collection, node["face_ids"], abs_path,
            force_unlit=force_unlit, export_yup=True,
            decimation_ratio=dec_ratio, preserve_borders=preserve_borders,
            lod_image=lod_image,
            lod_strategy=lod_strategy,
            rebake_atlas_size=rebake_atlas_sz,
            rebake_margin_px=rebake_margin,
            scene=scene,
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
        if lod_mode:
            f.write(f"LOD strategy: {lod_strategy}\n")
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
        _add_to_cesium_log(context, f"[NATIVE] {active_obj.name}: bbox=Z_UP, GLB export_yup=ON")

        # Compute in Blender Z-up frame (3D Tiles expects Z-up bounding volumes)
        face_ids, centroids, face_mins, face_maxs = _build_face_spatial_data(
            base_obj.data, to_gltf_yup=False,
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
            lod_strat = str(getattr(scene, "cesium_lod_strategy", "REBAKE"))
            _add_to_cesium_log(
                context,
                f"[LOD] Auto-params: depth={max_depth}, feat/tile={max_faces}, "
                f"levels={len(lod_config['lod_levels'])}, strategy={lod_strat}"
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
        lod_strategy = str(getattr(scene, "cesium_lod_strategy", "REBAKE")) if lod_mode else "LEAF_ONLY"
        rebake_margin = int(getattr(scene, "cesium_native_bake_margin", 8))

        if lod_mode:
            if lod_strategy == 'LEAF_ONLY':
                # LEAF_ONLY: only export leaf nodes (same as non-LOD mode)
                all_nodes = []
                _collect_native_leaves(tree, all_nodes)
            else:
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
            rebake_atlas_sz = None
            if lod_mode and lod_config and not is_leaf:
                level = node["depth"]
                levels_cfg = lod_config.get("lod_levels", [])
                for lc in levels_cfg:
                    if lc["depth"] == level:
                        dec_ratio = lc["decimation_ratio"]
                        atlas_sz = lc["atlas_size"]
                        if lod_strategy == 'REBAKE':
                            rebake_atlas_sz = atlas_sz
                        elif lod_image_cache and atlas_sz in lod_image_cache:
                            lod_image = lod_image_cache[atlas_sz]
                        break

            ok = _export_node_glb(
                context, base_obj, temp_collection, node["face_ids"], abs_path,
                force_unlit=force_unlit, export_yup=True,
                decimation_ratio=dec_ratio, preserve_borders=preserve_borders,
                lod_image=lod_image,
                lod_strategy=lod_strategy,
                rebake_atlas_size=rebake_atlas_sz,
                rebake_margin_px=rebake_margin,
                scene=scene,
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
            if lod_mode:
                f.write(f"LOD strategy: {lod_strategy}\n")
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
        # DEBUG: cleanup disabled – keep base_obj and bake assets for inspection
        pass
        # try:
        #     mesh_data = base_obj.data
        # except Exception:
        #     mesh_data = None
        # try:
        #     bpy.data.objects.remove(base_obj, do_unlink=True)
        # except Exception:
        #     pass
        # try:
        #     if mesh_data is not None and mesh_data.users == 0:
        #         bpy.data.meshes.remove(mesh_data, do_unlink=True)
        # except Exception:
        #     pass
        # if lod_image_cache:
        #     _cleanup_lod_image_cache(lod_image_cache)
        # _cleanup_native_bake_assets(bake_info)
