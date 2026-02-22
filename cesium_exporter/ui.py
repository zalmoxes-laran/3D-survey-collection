import bpy


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
            box.prop(scene, "cesium_lod_strategy")
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

        # ---- Progress section (shown below Export button during/after export) ----
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
