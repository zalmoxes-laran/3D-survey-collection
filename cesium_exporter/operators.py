import datetime
import json
import math
import os
import shutil
import subprocess
import time
import uuid
import webbrowser
import zipfile
from pathlib import Path

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


def _resolve_aton_scene_name(scene, fallback="basilica"):
    name = (scene.cesium_aton_scene_name or "").strip()
    if name:
        return _sanitize_name(name)
    obj = bpy.context.active_object
    if obj is not None and obj.type == "MESH":
        return _sanitize_name(obj.name)
    return _sanitize_name(fallback)


def _generate_scene_name():
    """Compose a scene id in ATON style: `<YYYY-MM-DD>_<UUID8>`.

    The UUID8 is the first 8 hex characters of a fresh UUID4 — collision
    probability negligible at the volumes typical of an interactive
    publishing workflow, and short enough to be readable in URLs.
    """
    date_str = datetime.date.today().strftime("%Y-%m-%d")
    uid = uuid.uuid4().hex[:8]
    return f"{date_str}_{uid}"


_YUP_ROTATION_RADIANS = {
    'NONE':   None,
    'XNEG90': [-math.pi / 2.0, 0.0, 0.0],
    'XPOS90': [ math.pi / 2.0, 0.0, 0.0],
    'X180':   [ math.pi,       0.0, 0.0],
    'Y180':   [0.0, math.pi, 0.0],
}


def _validate_aton_path(path):
    if not path:
        return False, "ATON folder not set"
    p = Path(path)
    if not p.is_dir():
        return False, f"Not a folder: {p}"
    if not (p / "package.json").exists():
        return False, f"Not an ATON install (no package.json): {p}"
    return True, ""


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
            scene.cesium_lod_strategy = 'REBAKE'
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

        # Switch viewport to wireframe to save memory and speed up bake
        _add_to_cesium_log(context, "Switching viewport to wireframe for performance...")
        for area in context.screen.areas:
            if area.type == 'VIEW_3D':
                for space in area.spaces:
                    if space.type == 'VIEW_3D':
                        space.shading.type = 'WIREFRAME'
        _redraw_3d_view(context)

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

            # Optional zip after export
            if getattr(scene, "cesium_zip_output", False):
                try:
                    bpy.ops.object.cesium_zip_output()
                except Exception as exc:
                    _add_to_cesium_log(context, f"[WARN] Zip step failed: {exc}")

            return {'FINISHED'}
        finally:
            scene.cesium_progress_active = False
            _redraw_3d_view(context)


# ===========================================================================
#  ATON integration operators
# ===========================================================================

class OBJECT_OT_launch_aton(bpy.types.Operator):
    """Start the local ATON server (npm start) detached from Blender."""
    bl_idname = "object.launch_aton"
    bl_label = "Launch ATON server"
    bl_options = {'REGISTER'}

    def execute(self, context):
        scene = context.scene
        aton_path = bpy.path.abspath(scene.cesium_aton_path).strip()
        ok, msg = _validate_aton_path(aton_path)
        if not ok:
            self.report({'ERROR'}, msg)
            return {'CANCELLED'}

        # Detach so Blender does not become the parent waiting for it.
        try:
            subprocess.Popen(
                ["npm", "start"],
                cwd=aton_path,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
        except FileNotFoundError:
            self.report({'ERROR'}, "`npm` not found in PATH. Install Node.js or set PATH for Blender.")
            return {'CANCELLED'}
        except Exception as exc:
            self.report({'ERROR'}, f"Failed to launch ATON: {exc}")
            return {'CANCELLED'}

        url = (scene.cesium_aton_url or "http://localhost:8080").rstrip("/")
        self.report({'INFO'}, f"ATON launched. It usually takes a few seconds; URL: {url}")
        return {'FINISHED'}


class OBJECT_OT_open_aton_browser(bpy.types.Operator):
    """Open the configured ATON URL in the system browser."""
    bl_idname = "object.open_aton_browser"
    bl_label = "Open ATON in browser"
    bl_options = {'REGISTER'}

    def execute(self, context):
        scene = context.scene
        url = (scene.cesium_aton_url or "http://localhost:8080").rstrip("/")
        webbrowser.open(url)
        self.report({'INFO'}, f"Opened {url}")
        return {'FINISHED'}


class OBJECT_OT_publish_to_aton(bpy.types.Operator):
    """Copy the produced tileset into ATON's collections folder, generate
    a minimal scene.json, and open the scene URL in the browser."""
    bl_idname = "object.publish_to_aton"
    bl_label = "Publish to ATON"
    bl_options = {'REGISTER'}

    def execute(self, context):
        scene = context.scene
        aton_path = bpy.path.abspath(scene.cesium_aton_path).strip()
        ok, msg = _validate_aton_path(aton_path)
        if not ok:
            self.report({'ERROR'}, msg)
            return {'CANCELLED'}

        output_root = bpy.path.abspath(scene.cesium_output_dir).strip()
        if not output_root or not os.path.isdir(output_root):
            self.report({'ERROR'}, "Set a valid Cesium output folder first")
            return {'CANCELLED'}

        # If output_root contains the produced tileset directly, that's
        # what we publish. If it contains object subfolders (one per
        # active mesh), we look for the active mesh's subfolder.
        candidate = Path(output_root)
        if not (candidate / "tileset.json").exists():
            obj = context.active_object
            if obj is not None and obj.type == "MESH":
                sub = candidate / _sanitize_name(obj.name)
                if (sub / "tileset.json").exists():
                    candidate = sub
        if not (candidate / "tileset.json").exists():
            self.report({'ERROR'}, f"No tileset.json found under {candidate}")
            return {'CANCELLED'}

        user = (scene.cesium_aton_user or "cesium_dev").strip() or "cesium_dev"
        scene_name = _resolve_aton_scene_name(scene)

        aton_root = Path(aton_path)
        coll_dir = aton_root / "data" / "collections" / user / scene_name
        scene_dir = aton_root / "data" / "scenes" / user / scene_name

        # Collections: tileset payload
        if coll_dir.exists():
            if not scene.cesium_aton_overwrite:
                self.report({'ERROR'}, f"Already exists: {coll_dir}. Enable 'Overwrite' to replace.")
                return {'CANCELLED'}
            shutil.rmtree(coll_dir)
        coll_dir.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(candidate, coll_dir)

        # Scene descriptor with sensible defaults
        scene_dir.mkdir(parents=True, exist_ok=True)
        node = {"urls": f"{user}/{scene_name}/tileset.json"}
        rot_choice = getattr(scene, "cesium_aton_yup_rotation", 'XNEG90')
        rot = _YUP_ROTATION_RADIANS.get(rot_choice)
        if rot is not None:
            node["transform"] = {"rotation": rot}
        error_target = float(getattr(scene, "cesium_aton_error_target", 5.0))
        scene_json = {
            "visibility": 1,
            "title": scene_name,
            "environment": {
                "mainpano": {"url": "samples/pano/defsky-grass.jpg", "rotation": 0.0},
                "mainlightx": {"direction": [-0.1, -1, -1], "shadows": False},
            },
            "scenegraph": {
                "nodes": {scene_name: node},
                "edges": {".": [scene_name]},
            },
            # ATON does not yet have a built-in scene.json parser key for
            # the 3D Tiles loader error target. We surface the desired
            # value here under `extras` so a future ATON hook can pick it
            # up; meanwhile, the user can run
            #   `ATON.MRes.setTSetsErrorTarget(<value>)`
            # from DevTools console once the scene loads.
            "extras": {
                "cesium": {"errorTarget": error_target},
            },
        }
        with open(scene_dir / "scene.json", "w", encoding="utf-8") as f:
            json.dump(scene_json, f, indent=2)

        url = (scene.cesium_aton_url or "http://localhost:8080").rstrip("/")
        full = f"{url}/s/{user}/{scene_name}"

        if scene.cesium_aton_open_browser:
            webbrowser.open(full)

        msg = f"Published to {coll_dir.name}. URL: {full}"
        _add_to_cesium_log(context, msg)
        self.report({'INFO'}, msg)
        return {'FINISHED'}


class OBJECT_OT_generate_aton_scene_name(bpy.types.Operator):
    """Generate a unique scene name (timestamp + 6-hex UUID suffix)."""
    bl_idname = "object.generate_aton_scene_name"
    bl_label = "Generate scene name"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        scene = context.scene
        scene.cesium_aton_scene_name = _generate_scene_name()
        self.report({'INFO'}, f"Generated: {scene.cesium_aton_scene_name}")
        return {'FINISHED'}


class OBJECT_OT_auto_compute_cesium_settings(bpy.types.Operator):
    """Heuristic auto-tune of Cesium tiling parameters from the active mesh.

    Strategy:
      - target ~3000 polys per leaf tile (good balance for HTTP delivery)
      - max_depth = ceil(log2(poly_count / target_leaf))
      - QUADTREE if mesh is largely planar (vertical extent < 25% of largest
        horizontal extent), OCTREE otherwise
      - leaf atlas size scales with poly count: <100k→512, <1M→1024, ≥1M→2048
      - root atlas size = leaf atlas / 4 (capped at 256 minimum)

    The aim is to keep individual GLBs under ~1 MB so the asset streams
    well over the network. The user can still override afterwards.
    """
    bl_idname = "object.auto_compute_cesium_settings"
    bl_label = "Auto-tune from mesh"
    bl_options = {'REGISTER', 'UNDO'}

    target_leaf_polys: bpy.props.IntProperty(  # type: ignore
        name="Target polys per leaf",
        default=10000,
        min=200,
        max=200000,
        description="Polygon budget per leaf tile. Higher = fewer/larger tiles, less inter-tile artefacts (recommended 8k-15k)",
    )
    max_depth_cap: bpy.props.IntProperty(  # type: ignore
        name="Max octree depth (cap)",
        default=5,
        min=2,
        max=8,
        description="Hard upper bound on octree depth. Lower values reduce LOD seams between tiles at the cost of less aggressive culling for very large meshes",
    )

    def execute(self, context):
        scene = context.scene
        obj = context.active_object
        if obj is None or obj.type != "MESH":
            self.report({'ERROR'}, "Select an active mesh first")
            return {'CANCELLED'}

        depsgraph = context.evaluated_depsgraph_get()
        eval_obj = obj.evaluated_get(depsgraph)
        mesh = eval_obj.to_mesh()
        if mesh is None or len(mesh.polygons) == 0:
            self.report({'ERROR'}, "Active mesh is empty")
            return {'CANCELLED'}

        try:
            poly_count = len(mesh.polygons)

            # World bbox via vertex iteration (cheap)
            mw = obj.matrix_world
            xs, ys, zs = [], [], []
            for v in mesh.vertices:
                wv = mw @ v.co
                xs.append(wv.x); ys.append(wv.y); zs.append(wv.z)
            ext_x = max(xs) - min(xs) if xs else 0.0
            ext_y = max(ys) - min(ys) if ys else 0.0
            ext_z = max(zs) - min(zs) if zs else 0.0
            ext_horiz = max(ext_x, ext_y)
            planar = ext_horiz > 0.0 and (ext_z / ext_horiz) < 0.25

            # Depth from polys: how many octree halvings to hit target leaf
            target = max(200, int(self.target_leaf_polys))
            ratio = max(1.0, poly_count / float(target))
            # OCTREE roughly halves polys per level; QUADTREE quarters them.
            # Empirically clamp to [2, 8].
            if planar:
                levels = math.ceil(math.log(ratio, 4))
            else:
                levels = math.ceil(math.log(ratio, 2))
            max_depth = max(2, min(int(levels), int(self.max_depth_cap)))

            # Atlas sizes scale with poly count (not bbox — texture detail
            # matters more than physical size for streaming density)
            if poly_count >= 1_000_000:
                leaf_atlas = 2048
            elif poly_count >= 100_000:
                leaf_atlas = 1024
            else:
                leaf_atlas = 512
            root_atlas = max(256, leaf_atlas // 4)

            # Apply
            scene.cesium_features_per_tile = target
            scene.cesium_native_min_depth = 1
            scene.cesium_native_max_depth = max_depth
            scene.cesium_tree_type = 'QUADTREE' if planar else 'OCTREE'
            scene.cesium_native_bake_texture_size = leaf_atlas
            scene.cesium_native_bake_margin = max(8, leaf_atlas // 64)
            scene.cesium_lod_mode = True
            scene.cesium_lod_auto_params = False
            scene.cesium_lod_leaf_atlas_size = leaf_atlas
            scene.cesium_lod_root_atlas_size = root_atlas
            scene.cesium_lod_strategy = 'REBAKE'
            scene.cesium_native_hierarchy_layout = 'IMPLICIT_TILING'

            # Estimate leaf tile size to warn about over-heavy tiles
            est_leaf_kb = leaf_atlas * leaf_atlas * 4 / 1024 / 4  # rough: 1024² PNG ~256 KB
            warn = ""
            if est_leaf_kb > 500:
                warn = f" [warn: leaf ~{est_leaf_kb:.0f}KB/tile, >500KB; consider smaller atlas]"

            msg = (
                f"polys={poly_count:,}, "
                f"bbox≈{ext_x:.1f}×{ext_y:.1f}×{ext_z:.1f}m, "
                f"{'QUADTREE' if planar else 'OCTREE'} depth={max_depth} (cap {self.max_depth_cap}), "
                f"leaf_atlas={leaf_atlas}, root_atlas={root_atlas}, "
                f"target_polys={target}{warn}"
            )
            _add_to_cesium_log(context, f"[AUTO] {msg}")
            self.report({'INFO'}, f"Auto-tune: {msg}")
            return {'FINISHED'}
        finally:
            try:
                eval_obj.to_mesh_clear()
            except Exception:
                pass


class OBJECT_OT_cesium_zip_output(bpy.types.Operator):
    """Write a zipped copy of the Cesium output folder next to it."""
    bl_idname = "object.cesium_zip_output"
    bl_label = "Save zip"
    bl_options = {'REGISTER'}

    def execute(self, context):
        scene = context.scene
        output_root = bpy.path.abspath(scene.cesium_output_dir).strip()
        if not output_root or not os.path.isdir(output_root):
            self.report({'ERROR'}, "Set a valid Cesium output folder first")
            return {'CANCELLED'}

        src = Path(output_root)
        zip_path = src.with_name(src.name + ".zip")
        # Replace existing zip silently
        if zip_path.exists():
            zip_path.unlink()
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for r, _, files in os.walk(src):
                for f in files:
                    p = Path(r) / f
                    zf.write(p, p.relative_to(src.parent))

        size_mb = zip_path.stat().st_size / (1024 * 1024)
        msg = f"Saved {zip_path.name} ({size_mb:.1f} MB)"
        _add_to_cesium_log(context, msg)
        self.report({'INFO'}, msg)
        return {'FINISHED'}
