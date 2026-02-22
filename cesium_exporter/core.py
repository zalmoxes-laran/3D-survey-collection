"""Compatibility facade for Cesium exporter internals.

Implementation has been split across dedicated modules for maintainability.
"""

from .glb_unlit import _patch_glb_to_unlit, _patch_output_glbs_to_unlit, _strip_glb_unlit, _strip_output_glbs_unlit
from .implicit import _bitarray_set_once, _implicit_level_offset, _implicit_morton_index, _implicit_total_nodes, _write_subtree_file
from .lod import _cleanup_lod_image_cache, _compute_lod_parameters, _pow2_round, _prepare_lod_image_cache
from .native_bake import _cleanup_native_bake_assets, _native_bake_basecolor_texture, _prepare_base_mesh_object, _rebake_node_texture
from .native_export import _export_node_glb, _native_tree_to_tileset_node, _run_native_implicit_layout, _run_native_split_backend
from .native_tree import _build_face_spatial_data, _build_native_tree, _child_split_bbox, _collect_native_leaves, _collect_native_nodes, _collect_nodes_at_depth, _split_face_ids
from .shared import _add_to_cesium_log, _crs_requires_proj_db, _export_obj, _find_proj_data_dir, _normalize_crs_input, _preserve_selection, _redraw_3d_view, _resolve_coordinates_config, _sanitize_name, _update_cesium_progress
from .stats import _build_gltf_export_kwargs, _collect_mesh_stats, _collect_object_texture_diagnostics, _count_texture_files_in_dir, _count_texture_nodes_on_object, _format_cesium_mesh_stats, _snapshot_output_files, _summarize_generated_files
from .tileset_stitcher import _aabb_from_3dtiles_box, _bbox_diag_len, _bbox_to_box, _bbox_union_from_face_ids, _bbox_union_many, _build_parent_tileset, _normalize_parent_tileset_name, _scan_child_tilesets

__all__ = [
    "_sanitize_name",
    "_preserve_selection",
    "_export_obj",
    "_normalize_crs_input",
    "_find_proj_data_dir",
    "_crs_requires_proj_db",
    "_resolve_coordinates_config",
    "_redraw_3d_view",
    "_update_cesium_progress",
    "_add_to_cesium_log",
    "_snapshot_output_files",
    "_summarize_generated_files",
    "_count_texture_nodes_on_object",
    "_collect_object_texture_diagnostics",
    "_build_gltf_export_kwargs",
    "_count_texture_files_in_dir",
    "_collect_mesh_stats",
    "_format_cesium_mesh_stats",
    "_patch_glb_to_unlit",
    "_patch_output_glbs_to_unlit",
    "_strip_glb_unlit",
    "_strip_output_glbs_unlit",
    "_bbox_union_from_face_ids",
    "_bbox_to_box",
    "_bbox_diag_len",
    "_normalize_parent_tileset_name",
    "_aabb_from_3dtiles_box",
    "_bbox_union_many",
    "_scan_child_tilesets",
    "_build_parent_tileset",
    "_prepare_base_mesh_object",
    "_cleanup_native_bake_assets",
    "_native_bake_basecolor_texture",
    "_rebake_node_texture",
    "_build_face_spatial_data",
    "_split_face_ids",
    "_child_split_bbox",
    "_build_native_tree",
    "_collect_native_leaves",
    "_collect_native_nodes",
    "_collect_nodes_at_depth",
    "_pow2_round",
    "_compute_lod_parameters",
    "_prepare_lod_image_cache",
    "_cleanup_lod_image_cache",
    "_implicit_level_offset",
    "_implicit_total_nodes",
    "_implicit_morton_index",
    "_bitarray_set_once",
    "_write_subtree_file",
    "_export_node_glb",
    "_native_tree_to_tileset_node",
    "_run_native_implicit_layout",
    "_run_native_split_backend",
]
