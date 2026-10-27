import json
import math
import os

import bmesh
import bpy


def _auto_atlas_size_for_tile(face_count, target_px_per_face=16, min_size=256, max_size=4096):
    """Pick a power-of-2 atlas size for a tile, sized to its face count.

    target_px_per_face: approximate texel budget per face after margin overhead.
    16 is a good balance — enough resolution to avoid sample bleed, low enough
    to keep tile files small (the whole point of pulverizing the octree).

    Examples (target=16):
        face_count=  5_000 -> 256  (60k px / 12 px/face)
        face_count= 10_000 -> 512  (262k px / 26 px/face)
        face_count= 30_000 -> 1024 (1M px / 35 px/face)
        face_count= 60_000 -> 1024 (1M px / 17 px/face)
        face_count=100_000 -> 2048 (4M px / 41 px/face)
        face_count=486_000 -> 4096 (16M px / 34 px/face)
    """
    if face_count <= 0:
        return min_size
    pixels_needed = face_count * target_px_per_face
    side = int(math.ceil(math.sqrt(pixels_needed)))
    size = 1
    while size < side:
        size *= 2
    return max(min_size, min(max_size, size))

# Schema id of the tileset-level metadata (3D Tiles 1.1 pattern
# [a-zA-Z_][a-zA-Z0-9_]*). Readers of older tilesets may meet the legacy id.
TILESET_SCHEMA_ID = "cesium_tiling_pipeline"
LEGACY_TILESET_SCHEMA_IDS = ("cesium-tiling-pipeline",)


def _coarse_budget(scene):
    """Budget of the coarse (non-leaf) tiles and leaf texture cap, from the
    scene: kwargs for `_export_node_glb`."""
    return {
        "max_triangles": int(getattr(scene, "cesium_coarse_max_triangles", 50000) or 0),
        "max_texture_size": int(getattr(scene, "cesium_coarse_max_texture_size", 2048) or 0),
        "leaf_max_texture_size": int(getattr(scene, "cesium_leaf_max_texture_size", 4096) or 4096),
    }


def _triangle_count(mesh):
    """Triangles of a mesh once triangulated (what the GLB will carry)."""
    try:
        import numpy as np
        n = len(mesh.polygons)
        if n == 0:
            return 0
        lt = np.empty(n, dtype=np.int32)
        mesh.polygons.foreach_get("loop_total", lt)
        return int((lt - 2).sum())
    except Exception:
        return sum(len(p.vertices) - 2 for p in mesh.polygons)


from .glb_unlit import _patch_glb_to_unlit
from .implicit import (
    _bitarray_set_once,
    _implicit_level_offset,
    _implicit_morton_index,
    _implicit_total_nodes,
    _write_subtree_file,
)
from .lod import _cleanup_lod_image_cache, _compute_lod_parameters, _prepare_lod_image_cache
from .native_bake import (
    _cleanup_native_bake_assets,
    _drop_unused_material_slots,
    _native_bake_basecolor_texture,
    _original_texel_atlas_size,
    _prepare_base_mesh_object,
    _rebake_node_texture,
)
from .native_tree import (
    _build_face_spatial_data,
    _build_native_tree,
    _collect_native_leaves,
    _collect_native_nodes,
    _collect_nodes_at_depth,
)
from .octree_clip import _clip_bm_to_bbox, _clip_quadtree_bm_to_bbox
from .shared import _add_to_cesium_log, _preserve_selection
from .stats import _collect_object_texture_diagnostics
from .stats import _build_gltf_export_kwargs
from .tileset_stitcher import _bbox_diag_len, _bbox_to_box, _bbox_union_from_face_ids


# Empirically determined fix for "head-down" rendering in ATON Three.js
# Y-up scene. The Blender Z-up data path + `export_yup=True` glTF + the
# 3d-tiles-renderer loader's own implicit rotation compose to a net
# offset that flips the model upside-down. A 180° rotation around the
# X axis (column-major flat) baked into root.transform compensates for
# this and makes the asset right-side-up out of the box.
#
# Encoded:
#   X stays, Y -> -Y, Z -> -Z
#
# Per the geo-referencing phase, this constant will be replaced by the
# ENU->ECEF + ECEF translation matrix derived from `EPSG:<code> X Y Z`
# in SHIFT.txt — the current rotation will then be folded into that
# composite transform if still empirically required.
_LOCAL_FIX_FLIP_TRANSFORM = [
    1.0,  0.0,  0.0, 0.0,   # col 0
    0.0, -1.0,  0.0, 0.0,   # col 1
    0.0,  0.0, -1.0, 0.0,   # col 2
    0.0,  0.0,  0.0, 1.0,   # col 3
]
# Backwards-compat alias (older code referenced this name)
_LOCAL_ZUP_TO_YUP_TRANSFORM = _LOCAL_FIX_FLIP_TRANSFORM


def _export_node_glb(
    context, base_obj, temp_collection, keep_face_ids, filepath,
    force_unlit=False, export_yup=True,
    decimation_ratio=1.0, preserve_borders=True,
    lod_image=None,
    lod_strategy='REBAKE',
    rebake_atlas_size=None,
    rebake_margin_px=8,
    scene=None,
    cell_bbox=None,
    tree_type='OCTREE',
    is_leaf=False,
    texture_source_obj=None,
    max_triangles=0,
    max_texture_size=0,
    leaf_max_texture_size=4096,
):
    """Export a GLB for a tree node.

    For leaf nodes: decimation_ratio=1.0, lod_image=None (uses full mesh+texture).
    For internal LOD nodes with REBAKE strategy: decimate, re-UV, re-bake from base_obj.
    For internal LOD nodes with legacy behavior: decimation_ratio<1.0, lod_image=downsampled atlas.

    Leaf texture source: when ``is_leaf`` and ``texture_source_obj`` is given
    (a copy of the source mesh with its ORIGINAL materials and UVs, the same
    faces in the same order as ``base_obj``), the tile is cut from it and baked
    directly from the original images into a fresh per-tile atlas sized to the
    original texel density (capped at ``leaf_max_texture_size``). The global
    atlas of ``base_obj`` is then only used for coarse tiles.

    Returns True (written), False (failed) or None (nothing of the node
    left inside its cell after clipping: no content to write).

    Coarse tiles (not ``is_leaf``): ``max_triangles`` > 0 caps the triangle
    count (decimating further when the level ratio is not enough), and
    ``max_texture_size`` > 0 caps the side of their baked atlas.
    """
    use_original = bool(is_leaf and texture_source_obj is not None)
    cut_src = texture_source_obj if use_original else base_obj
    tile_obj = cut_src.copy()
    tile_obj.data = cut_src.data.copy()
    tile_obj_name = tile_obj.name
    tile_mesh_name = tile_obj.data.name
    temp_collection.objects.link(tile_obj)

    keep_temp = bool(getattr(scene, "cesium_keep_temp_objects", False)) if scene is not None else False

    # Track rebake artifacts for cleanup
    _rebake_img_name = None
    _rebake_mat_name = None
    _direct_bake_info = None

    try:
        # 1) Keep only faces belonging to this node, then geometrically clip
        # the result to the cell bbox so faces that protrude outside (because
        # the octree split is by face bbox-overlap, not by geometric cutting)
        # are split at the cell boundaries. This is the missing ingredient
        # for a "real" octree: each tile's geometry is fully contained in
        # its cell. Refs: Cesium Ion / 3DTilesIndex output.
        keep_set = set(keep_face_ids)
        bm = bmesh.new()
        bm.from_mesh(tile_obj.data)
        bm.faces.ensure_lookup_table()
        to_delete = [f for f in bm.faces if f.index not in keep_set]
        if to_delete:
            bmesh.ops.delete(bm, geom=to_delete, context='FACES')
        n_before_clip = len(bm.faces)
        if cell_bbox is not None and n_before_clip > 0:
            if tree_type == 'QUADTREE':
                _clip_quadtree_bm_to_bbox(bm, cell_bbox)
            else:
                _clip_bm_to_bbox(bm, cell_bbox)
            n_after_clip = len(bm.faces)
            if n_after_clip != n_before_clip:
                print(f"[CLIP] {tile_obj.name}: {n_before_clip} -> {n_after_clip} faces "
                      f"(geometric clip at cell bbox boundaries)")
        bm.to_mesh(tile_obj.data)
        bm.free()
        tile_obj.data.update()

        if len(tile_obj.data.polygons) == 0:
            # Nothing of the node is left inside its cell (a few faces that
            # only touched it): no content, not an error.
            return None

        # 2) Apply decimation if ratio < 1.0 (LOD internal node). A coarse
        # tile also respects the triangle budget `max_triangles`: the ratio
        # is lowered so that the decimated tile fits in it.
        n_tris = _triangle_count(tile_obj.data)
        if not is_leaf and max_triangles and n_tris > int(max_triangles):
            budget_ratio = float(max_triangles) / float(n_tris)
            if budget_ratio < decimation_ratio:
                print(f"[BUDGET] {tile_obj.name}: {n_tris} tris > {int(max_triangles)}, "
                      f"ratio {decimation_ratio:.4f} -> {budget_ratio:.4f}")
                decimation_ratio = budget_ratio
        if decimation_ratio < 0.999 and len(tile_obj.data.polygons) > 10:
            with _preserve_selection(context):
                # Bulletproof deselection
                for obj in bpy.data.objects:
                    try:
                        obj.select_set(False)
                    except Exception:
                        pass
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

                # The protected borders can keep the tile above its budget
                # (a cell clipped on six sides has many border vertices):
                # a second pass, without the protection, brings it in.
                if not is_leaf and max_triangles:
                    n_after = _triangle_count(tile_obj.data)
                    if n_after > int(max_triangles):
                        mod = tile_obj.modifiers.new("Decimate", type='DECIMATE')
                        mod.ratio = max(float(max_triangles) / float(n_after) * 0.98, 0.0001)
                        bpy.ops.object.modifier_apply(modifier="Decimate")
                        print(f"[BUDGET] {tile_obj.name}: border-preserving pass left {n_after} tris, "
                              f"second pass -> {_triangle_count(tile_obj.data)}")

            if len(tile_obj.data.polygons) == 0:
                return None

        # 2b) Per-tile re-bake: each tile gets its own small atlas baked from
        # base_obj. This is the whole point of an octree + tile system —
        # individual tiles carry their own focused texture instead of all
        # embedding the same global atlas. Fires for every tile (leaf or
        # decimated) when scene.cesium_per_tile_bake_enabled is True.
        # Independent of lod_strategy: per-tile bake is correct for both
        # LOD-off (every leaf gets its own atlas) and LOD-on (every level
        # gets its own atlas at its decimation density).
        per_tile_bake = (
            scene is not None
            and bool(getattr(scene, "cesium_per_tile_bake_enabled", True))
        )
        if use_original and len(tile_obj.data.polygons) > 0:
            # Leaf from the ORIGINAL textures: no ray casting, no global
            # atlas in between — the tile's own materials are baked onto a
            # fresh UV layout, sampling the source images through their own
            # UV map. Only the materials this tile uses stay on it, so
            # Cycles loads only their images.
            _drop_unused_material_slots(tile_obj.data)
            leaf_size = _original_texel_atlas_size(
                tile_obj.data, max_size=int(leaf_max_texture_size or 4096))
            if leaf_size is None:
                leaf_size = _auto_atlas_size_for_tile(
                    len(tile_obj.data.polygons), max_size=int(leaf_max_texture_size or 4096))
            # Full-atlas bleed, as in the rebake: the empty UV space takes
            # the colour of the nearest island instead of the grey fill, so
            # no grey creeps into the island borders at coarser mip levels.
            ok_d, msg_d, _direct_bake_info = _native_bake_basecolor_texture(
                context=context, scene=scene, base_obj=tile_obj,
                atlas_size=leaf_size, margin_px=max(int(rebake_margin_px), int(leaf_size)),
            )
            if ok_d and _direct_bake_info.get("applied"):
                _rebake_img_name = _direct_bake_info.get("baked_image") or None
                _rebake_mat_name = _direct_bake_info.get("baked_material") or None
                lod_image = None
                per_tile_bake = False
                print(f"[LEAF-ORIGINAL] {tile_obj.name}: faces={len(tile_obj.data.polygons)}, "
                      f"atlas={leaf_size}px from original textures")
            else:
                print(f"[LEAF-ORIGINAL] {tile_obj.name}: not applied ({msg_d}); "
                      f"falling back to the global-atlas rebake")
        if per_tile_bake and len(tile_obj.data.polygons) > 0:
            actual_atlas_size = rebake_atlas_size
            if actual_atlas_size is None or actual_atlas_size <= 0:
                actual_atlas_size = _auto_atlas_size_for_tile(len(tile_obj.data.polygons))
            if not is_leaf and max_texture_size and actual_atlas_size > int(max_texture_size):
                actual_atlas_size = int(max_texture_size)
            print(f"[REBAKE] {tile_obj.name}: faces={len(tile_obj.data.polygons)}, "
                  f"atlas={actual_atlas_size}px (auto={rebake_atlas_size is None}) "
                  f"decimated={'yes' if decimation_ratio < 0.999 else 'no'}")
            ok_rb, rb_img, rb_mat = _rebake_node_texture(
                context, scene, base_obj, tile_obj,
                atlas_size=actual_atlas_size,
                margin_px=rebake_margin_px,
            )
            if ok_rb and rb_mat is not None:
                _rebake_img_name = rb_img.name if rb_img else None
                _rebake_mat_name = rb_mat.name
                tile_obj.data.materials.clear()
                tile_obj.data.materials.append(rb_mat)
                for poly in tile_obj.data.polygons:
                    poly.material_index = 0
                # Keep only the rebake UV map: the glTF exporter writes UV
                # maps in storage order, so the source map would ride along
                # as an unused TEXCOORD_0 (the validator flags it).
                rb_uv = tile_obj.data.uv_layers.active
                if rb_uv is not None:
                    rb_uv_name = rb_uv.name
                    for uv_name in [u.name for u in tile_obj.data.uv_layers if u.name != rb_uv_name]:
                        tile_obj.data.uv_layers.remove(tile_obj.data.uv_layers[uv_name])
                tile_obj.data.update()
                # Skip step 3 (texture swap) — we have a fresh bake
                lod_image = None
                print(f"[REBAKE] {tile_obj.name}: OK -> mat={rb_mat.name}, img={rb_img.name if rb_img else 'None'}")
            else:
                print(f"[REBAKE] {tile_obj.name}: FAILED (ok={ok_rb}, mat={rb_mat}); "
                      f"falling back to global atlas")

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
            # Bulletproof deselection — only tile_obj must be exported
            for obj in bpy.data.objects:
                try:
                    obj.select_set(False)
                except Exception:
                    pass
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
        # By default cleanup all per-tile temporaries from the Blender
        # scene so the user does not see the `_cesium_native_tmp`
        # collection bloat with thousands of objects after a multi-tile
        # export. The `cesium_keep_temp_objects` scene property (default
        # OFF, exposed under Advanced) keeps them around for debugging.
        if not keep_temp:
            obj_to_del = bpy.data.objects.get(tile_obj_name)
            if obj_to_del is not None:
                try:
                    bpy.data.objects.remove(obj_to_del, do_unlink=True)
                except Exception:
                    pass
            mesh_to_del = bpy.data.meshes.get(tile_mesh_name)
            if mesh_to_del is not None and mesh_to_del.users == 0:
                try:
                    bpy.data.meshes.remove(mesh_to_del, do_unlink=True)
                except Exception:
                    pass
            if _rebake_mat_name:
                mat = bpy.data.materials.get(_rebake_mat_name)
                if mat is not None and mat.users == 0:
                    try:
                        bpy.data.materials.remove(mat, do_unlink=True)
                    except Exception:
                        pass
            if _rebake_img_name:
                img = bpy.data.images.get(_rebake_img_name)
                if img is not None and img.users == 0:
                    try:
                        bpy.data.images.remove(img, do_unlink=True)
                    except Exception:
                        pass
            if _direct_bake_info:
                _cleanup_native_bake_assets(_direct_bake_info)

        # The original fragments below are kept commented as a quick
        # reference for what used to be debug-disabled. Do not remove.
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

def _native_tree_to_tileset_node(node, root_error, base_depth=0, external_subtree_map=None,
                                  refine_mode="REPLACE"):
    tile = {
        "boundingVolume": {"box": _bbox_to_box(node["bbox"])},
        "geometricError": 0.0,
    }

    local_depth = max(node["depth"] - base_depth, 0)
    node_key = id(node)
    if external_subtree_map and node_key in external_subtree_map:
        tile["geometricError"] = root_error / (2 ** max(local_depth, 0))
        tile["refine"] = refine_mode
        tile["content"] = {"uri": external_subtree_map[node_key]}
        return tile

    uri = node.get("uri")
    if uri:
        tile["content"] = {"uri": uri}

    if node["children"]:
        tile["geometricError"] = root_error / (2 ** max(local_depth, 0))
        tile["refine"] = refine_mode
        tile["children"] = [
            _native_tree_to_tileset_node(
                child,
                root_error=root_error,
                base_depth=base_depth,
                external_subtree_map=external_subtree_map,
                refine_mode=refine_mode,
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
    texture_source_obj=None,
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
    budget = _coarse_budget(scene)

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
        print(f"[TILE] {tile_label}: is_leaf={is_leaf}, faces={len(node['face_ids'])}, depth={level}")
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
            cell_bbox=node.get("cell_bbox"),
            tree_type=tree_type,
            is_leaf=is_leaf,
            texture_source_obj=texture_source_obj,
            **budget,
        )
        if ok is None:
            print(f"[TILE] {tile_label}: empty after clipping, no content")
            continue
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

    # Geometric error policy
    # ----------------------
    # 3D Tiles spec: a tile's geometricError is "the error introduced by
    # rendering this tile instead of its children". The viewer compares
    # `screenSpaceError = geometricError * pixels_per_world_unit` against
    # its `errorTarget`; when it exceeds the target, children are loaded.
    #
    # Two values matter for the viewer's refine behaviour:
    #   - tileset.geometricError (top-level): below this SSE the asset is
    #     considered "out of view"; if too low, the asset is dropped at
    #     ordinary view distances
    #   - tileset.root.geometricError: the SSE budget of the root tile.
    #     For implicit tiling, every level n has implicit error
    #     `root_error / 2^n`, so the root_error directly controls how
    #     soon the loader starts refining downwards.
    #
    # Old buggy formula: `root_tile_error = bbox_diag / 2^max_depth`.
    # That made the root error 30-100× smaller than it should be — the
    # loader was "happy" with the root and never refined.
    #
    # New formula: take the bbox diagonal as a sensible "tile level 0"
    # error in metres; divide it by 2 just so the root is a bit smaller
    # than the bbox itself (children are then 1/4, 1/8 ... of the diag).
    # The Basilica reference dataset hand-tuned its root error to ~10 %
    # of bbox diag; ours is ~50 % which biases towards refining sooner,
    # matching what an interactive ATON workflow expects.
    bbox_diag = max(_bbox_diag_len(tree["bbox"]), 1.0)
    root_tile_error = bbox_diag * 0.5
    # Top-level error stays high so the asset is visible at any distance.
    root_error = max(bbox_diag * 100.0, 10000.0)

    refine_mode = str(getattr(scene, "cesium_tile_refine_mode", "REPLACE")).upper()
    if refine_mode not in ("REPLACE", "ADD"):
        refine_mode = "REPLACE"

    subdivision = "OCTREE" if tree_type == 'OCTREE' else "QUADTREE"
    root_box = _bbox_to_box(tree["bbox"])
    tileset = {
        "asset": {
            "version": "1.1",
            "extras": {
                "ion": {"georeferenced": False, "movable": True},
            },
        },
        # 3D Tiles 1.1: a schema id matches [a-zA-Z_][a-zA-Z0-9_]*, and a
        # tile with `implicitTiling` may not carry `metadata`. The tight box
        # of the whole content is therefore tileset-level metadata (class
        # `tileset`); until dev16 it was `cesium-tiling-pipeline` / class
        # `tile` on the implicit root, which the validator rejected.
        "schema": {
            "id": TILESET_SCHEMA_ID,
            "classes": {
                "tileset": {
                    "properties": {
                        "tightBoundingBox": {
                            "name": "Tight Bounding Box",
                            "description": "Oriented box (3D Tiles `box`) of the whole content.",
                            "type": "SCALAR",
                            "componentType": "FLOAT64",
                            "array": True,
                            "count": 12,
                        }
                    }
                }
            },
        },
        "metadata": {
            "class": "tileset",
            "properties": {"tightBoundingBox": root_box},
        },
        "geometricError": root_error,
        "root": {
            "boundingVolume": {"box": root_box},
            "geometricError": root_tile_error,
            "refine": refine_mode,
            "content": {"uri": content_uri_template},
            "implicitTiling": {
                "subdivisionScheme": subdivision,
                "subtreeLevels": available_levels,
                "availableLevels": available_levels,
                "subtrees": {"uri": subtree_uri_template},
            },
        },
    }
    if getattr(scene, "cesium_root_transform_yup_for_threejs", False):
        tileset["root"]["transform"] = list(_LOCAL_ZUP_TO_YUP_TRANSFORM)
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
        f.write(f"Coarse tile max triangles: {int(getattr(scene, 'cesium_coarse_max_triangles', 50000))}\n")
        f.write(f"Coarse tile max texture: {int(getattr(scene, 'cesium_coarse_max_texture_size', 2048))}\n")
        if isinstance(bake_info, dict):
            f.write(f"Leaf texture source: {bake_info.get('leaf_texture_source', 'ATLAS')}\n")
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
    pristine_obj = None
    texture_source_obj = None
    try:
        _add_to_cesium_log(context, f"[NATIVE] {active_obj.name}: bbox=Z_UP, GLB export_yup=ON")

        # Reverted to Blender Z-up bbox frame. Empirical investigation
        # showed the 3d-tiles-renderer (NASA-AMMOS, used by ATON) applies
        # a rotation when loading the glTF tile content, so simply
        # aligning bbox with content does not eliminate the apparent
        # 90 deg rotation the user observes. The orientation correction
        # is therefore left to the consumer scene descriptor (e.g.
        # ATON scene.json with transform.rotation), and identified
        # empirically per viewer.
        face_ids, centroids, face_mins, face_maxs = _build_face_spatial_data(
            base_obj.data, to_gltf_yup=False,
        )
        if not face_ids:
            return False, "Active mesh has no faces."

        # Leaf texture source. ORIGINAL (default): the leaves are baked from
        # the source materials and images, at the texel density they have
        # there; the global atlas only feeds the coarse tiles. ATLAS: every
        # tile is rebaked from the global atlas (until dev16 the only way —
        # a leaf could not be sharper than that one atlas).
        leaf_source = str(getattr(scene, "cesium_leaf_texture_source", "ORIGINAL"))
        per_tile_bake = bool(getattr(scene, "cesium_per_tile_bake_enabled", True))
        has_images = int(_collect_object_texture_diagnostics(base_obj).get("texture_images", 0)) > 0
        use_original = per_tile_bake and leaf_source == 'ORIGINAL' and has_images
        layout = scene.cesium_native_hierarchy_layout
        coarse_content = (
            (lod_mode and str(getattr(scene, "cesium_lod_strategy", "REBAKE")) != 'LEAF_ONLY')
            or (not lod_mode and layout == 'SINGLE_JSON'
                and bool(getattr(scene, "cesium_singlejson_add_root_content", True)))
        )
        if use_original and bake_info["enabled"] and not coarse_content:
            # No coarse tile to feed: the atlas would be baked for nothing.
            bake_info["enabled"] = False
            _add_to_cesium_log(context, f"[NATIVE] {active_obj.name}: global atlas skipped "
                                        "(leaves bake from the original textures, no coarse tiles).")
        if use_original and bake_info["enabled"]:
            # The atlas bake replaces base_obj's materials and UVs: keep a
            # pristine copy (same faces, same order) as the leaves' source.
            pristine_obj = base_obj.copy()
            pristine_obj.data = base_obj.data.copy()
            pristine_obj.name = f"{base_obj.name}__original"
            temp_collection.objects.link(pristine_obj)

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
        if use_original:
            if pristine_obj is not None and bake_info.get("applied"):
                texture_source_obj = pristine_obj
            else:
                # No atlas on base_obj: it still has the original materials.
                texture_source_obj = base_obj
            _add_to_cesium_log(context, f"[NATIVE] {active_obj.name}: leaves bake from the original textures.")
        bake_info["leaf_texture_source"] = "ORIGINAL" if use_original else "ATLAS"

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
                texture_source_obj=texture_source_obj,
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
        budget = _coarse_budget(scene)

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
                cell_bbox=node.get("cell_bbox"),
                tree_type=tree_type,
                is_leaf=is_leaf,
                texture_source_obj=texture_source_obj,
                **budget,
            )
            if ok is None:
                node.pop("uri", None)
                continue
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
                rebake_margin_px=rebake_margin,
                scene=scene, is_leaf=False, **budget,
            )
            if ok is False:
                return False, "Failed exporting single-JSON root content tile."
            if ok:
                tree["uri"] = root_uri

        # Geometric error policy — same rationale as the implicit-tiling
        # branch. `tree_root_error` is the error budget at the topmost
        # tile, halved for each level by `_native_tree_to_tileset_node`.
        # `top_level_error` is the file-wide cutoff; we keep it very high
        # so the asset is visible at any view distance.
        bbox_diag = max(_bbox_diag_len(tree["bbox"]), 1.0)
        tree_root_error = bbox_diag * 0.5
        top_level_error = max(bbox_diag * 100.0, 10000.0)

        refine_mode = str(getattr(scene, "cesium_tile_refine_mode", "REPLACE")).upper()
        if refine_mode not in ("REPLACE", "ADD"):
            refine_mode = "REPLACE"

        if scene.cesium_native_hierarchy_layout == 'EXTERNAL_SUBTILESETS':
            for subtree in subtree_nodes:
                sub_bbox_diag = max(_bbox_diag_len(subtree["bbox"]), 1.0)
                sub_root_error = sub_bbox_diag * 0.5
                sub_top_error = max(sub_bbox_diag * 100.0, 10000.0)
                subtree_tile = _native_tree_to_tileset_node(
                    subtree, root_error=sub_root_error,
                    base_depth=subtree["depth"], external_subtree_map=None,
                    refine_mode=refine_mode,
                )
                subtree_folder = subtree_folder_map.get(id(subtree), "")
                subtree_json_path = os.path.join(output_dir, subtree_folder, "tileset.json")
                os.makedirs(os.path.dirname(subtree_json_path), exist_ok=True)
                with open(subtree_json_path, "w", encoding="utf-8") as subf:
                    json.dump(
                        {"asset": {"version": "1.1"}, "geometricError": sub_top_error, "root": subtree_tile},
                        subf, indent=2,
                    )

        tileset_root = _native_tree_to_tileset_node(
            tree, root_error=tree_root_error, base_depth=0,
            external_subtree_map=external_subtree_map,
            refine_mode=refine_mode,
        )
        if getattr(scene, "cesium_root_transform_yup_for_threejs", False):
            tileset_root["transform"] = list(_LOCAL_ZUP_TO_YUP_TRANSFORM)
        tileset = {
            "asset": {"version": "1.1"},
            "geometricError": top_level_error,
            "root": tileset_root,
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
            f.write(f"Leaf texture source: {bake_info.get('leaf_texture_source', 'ATLAS')}\n")
            f.write(f"Coarse tile max triangles: {int(getattr(scene, 'cesium_coarse_max_triangles', 50000))}\n")
            f.write(f"Coarse tile max texture: {int(getattr(scene, 'cesium_coarse_max_texture_size', 2048))}\n")
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
        # End-of-job cleanup. The `cesium_keep_temp_objects` scene
        # property (default OFF, exposed under Advanced) preserves
        # temporaries for debugging — useful when inspecting why a bake
        # produced unexpected output.
        keep_temp = bool(getattr(scene, "cesium_keep_temp_objects", False))
        if not keep_temp:
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
            if pristine_obj is not None:
                try:
                    pristine_mesh = pristine_obj.data
                    bpy.data.objects.remove(pristine_obj, do_unlink=True)
                    if pristine_mesh is not None and pristine_mesh.users == 0:
                        bpy.data.meshes.remove(pristine_mesh, do_unlink=True)
                except Exception:
                    pass
            if lod_image_cache:
                _cleanup_lod_image_cache(lod_image_cache)
            _cleanup_native_bake_assets(bake_info)
            # Drop the temp collection itself if empty
            try:
                tc = bpy.data.collections.get("_cesium_native_tmp")
                if tc is not None and len(tc.objects) == 0:
                    bpy.data.collections.remove(tc)
            except Exception:
                pass
