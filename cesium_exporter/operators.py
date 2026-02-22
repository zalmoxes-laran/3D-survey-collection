import os
import shutil
import time

import bpy

from .core import (
    _add_to_cesium_log,
    _build_parent_tileset,
    _collect_mesh_stats,
    _format_cesium_mesh_stats,
    _normalize_parent_tileset_name,
    _patch_output_glbs_to_unlit,
    _redraw_3d_view,
    _resolve_coordinates_config,
    _run_native_split_backend,
    _sanitize_name,
    _snapshot_output_files,
    _strip_output_glbs_unlit,
    _summarize_generated_files,
    _update_cesium_progress,
)


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
