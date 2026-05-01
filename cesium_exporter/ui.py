import bpy


def _section(layout, scene, prop_name, title, icon='NONE'):
    """Render a collapsible section header. Returns the inner box if expanded,
    None otherwise. The triangle toggle is bound to the given scene boolean.
    """
    box = layout.box()
    head = box.row(align=True)
    expanded = bool(getattr(scene, prop_name, False))
    head.prop(scene, prop_name, text="", emboss=False,
              icon='TRIA_DOWN' if expanded else 'TRIA_RIGHT')
    if icon != 'NONE':
        head.label(text=title, icon=icon)
    else:
        head.label(text=title)
    return box.box() if expanded else None


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

        # Workflow at a glance: settings  →  export  →  preview / deliver
        head = layout.row()
        head.alignment = 'CENTER'
        head.label(text="1. Settings   →   2. Export   →   3. Preview / Deliver", icon='SETTINGS')

        # ====================================================================
        # STEP 1 — settings (numbered, individually collapsible sub-sections)
        # ====================================================================

        # 1.1  Source ----------------------------------------------------------
        sec = _section(layout, scene, "cesium_show_section_source",
                       "1.1  Source", icon='OUTLINER_OB_MESH')
        if sec is not None:
            sec.prop(scene, "cesium_source_mode")
            if source_mode == 'ACTIVE_MESH':
                sec.prop(scene, "cesium_export_selected_meshes")
                selected_mesh_count = len([o for o in context.selected_objects if o and o.type == 'MESH'])
                if scene.cesium_export_selected_meshes:
                    sec.label(text=f"Selected meshes: {selected_mesh_count}", icon='INFO')
                    if not scene.cesium_create_object_subdir and selected_mesh_count > 1:
                        sec.label(text="Enable 'Create object subfolder' for multi-mesh export.", icon='ERROR')
                else:
                    sec.label(text="Workflow: 1 mesh at a time", icon='INFO')
                if active_obj is not None and active_obj.type == 'MESH':
                    sec.label(text=f"Active mesh: {active_obj.name}", icon='MESH_DATA')
                else:
                    sec.label(text="No active mesh selected", icon='ERROR')
            else:
                sec.prop(scene, "cesium_existing_obj_file")
                sec.label(text="Use an existing OBJ + MTL/texture set on disk.", icon='INFO')

        # 1.2  Output ----------------------------------------------------------
        sec = _section(layout, scene, "cesium_show_section_output",
                       "1.2  Output", icon='FILE_FOLDER')
        if sec is not None:
            row = sec.row(align=True)
            row.prop(scene, "cesium_output_dir")
            op = row.operator("object.clear_cesium_folder", text="", icon='TRASH')
            op.target = 'OUTPUT'
            sec.prop(scene, "cesium_create_object_subdir")

        # 1.3  Quick Setup -----------------------------------------------------
        sec = _section(layout, scene, "cesium_show_section_quicksetup",
                       "1.3  Quick Setup (presets / auto-tune)", icon='AUTO')
        if sec is not None:
            row = sec.row(align=True)
            row.prop(scene, "cesium_quick_preset", text="")
            row.operator("object.apply_cesium_preset", text="Apply preset")
            sec.operator("object.auto_compute_cesium_settings",
                         text="Auto-tune from active mesh", icon='SETTINGS')

        # 1.4  Tiling ----------------------------------------------------------
        sec = _section(layout, scene, "cesium_show_section_tiling",
                       "1.4  Tiling (octree / LOD)", icon='MOD_LATTICE')
        if sec is not None:
            sec.prop(scene, "cesium_tree_type")
            sec.prop(scene, "cesium_tile_refine_mode")
            sec.prop(scene, "cesium_lod_mode")
            if scene.cesium_lod_mode:
                sec.prop(scene, "cesium_lod_strategy")
                sec.prop(scene, "cesium_lod_auto_params")
                if not scene.cesium_lod_auto_params:
                    sec.prop(scene, "cesium_native_max_depth")
                    sec.prop(scene, "cesium_features_per_tile")
                    sec.prop(scene, "cesium_lod_leaf_atlas_size")
                    sec.prop(scene, "cesium_lod_root_atlas_size")
                sec.prop(scene, "cesium_lod_preserve_borders")
            else:
                sec.prop(scene, "cesium_native_min_depth")
                sec.prop(scene, "cesium_native_max_depth")
                sec.prop(scene, "cesium_features_per_tile")

        # 1.5  Texture ---------------------------------------------------------
        sec = _section(layout, scene, "cesium_show_section_texture",
                       "1.5  Texture", icon='TEXTURE')
        if sec is not None:
            sec.prop(scene, "cesium_native_bake_texture_atlas")
            row = sec.row(align=True)
            row.enabled = bool(scene.cesium_native_bake_texture_atlas)
            row.prop(scene, "cesium_native_bake_texture_size")
            row.prop(scene, "cesium_native_bake_margin")

        # 1.6  Hierarchy Layout ------------------------------------------------
        sec = _section(layout, scene, "cesium_show_section_hierarchy",
                       "1.6  Hierarchy Layout", icon='OUTLINER')
        if sec is not None:
            sec.prop(scene, "cesium_native_hierarchy_layout")
            if scene.cesium_native_hierarchy_layout == 'EXTERNAL_SUBTILESETS':
                sec.prop(scene, "cesium_native_subtileset_split_depth")
            elif scene.cesium_native_hierarchy_layout == 'SINGLE_JSON':
                sec.prop(scene, "cesium_singlejson_add_root_content")

        # 1.7  Coordinates -----------------------------------------------------
        sec = _section(layout, scene, "cesium_show_section_coordinates",
                       "1.7  Coordinates (local / georef)", icon='WORLD')
        if sec is not None:
            sec.prop(scene, "cesium_coordinates_mode")
            if scene.cesium_coordinates_mode == 'SHIFT_VALUES':
                sec.label(text=f"SHIFT EPSG: {getattr(scene, 'BL_epsg', 'NotSet')}")
                sec.label(
                    text=f"SHIFT XYZ: {getattr(scene, 'BL_x_shift', 0.0):.3f}, "
                         f"{getattr(scene, 'BL_y_shift', 0.0):.3f}, "
                         f"{getattr(scene, 'BL_z_shift', 0.0):.3f}"
                )
                sec.prop(scene, "cesium_crs", text="CRS override")
            elif scene.cesium_coordinates_mode == 'CUSTOM_COORDS':
                sec.prop(scene, "cesium_crs")
                row = sec.row(align=True)
                row.prop(scene, "cesium_offset_x", text="X")
                row.prop(scene, "cesium_offset_y", text="Y")
                row.prop(scene, "cesium_offset_z", text="Z")

        # ---- Multi-mesh Stitcher (collapsible) ------------------------------
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

        # ---- Advanced (collapsible) -----------------------------------------
        box_adv = layout.box()
        adv_header = box_adv.row(align=True)
        adv_icon = 'TRIA_DOWN' if scene.cesium_show_advanced else 'TRIA_RIGHT'
        adv_header.prop(scene, "cesium_show_advanced", text="", emboss=False, icon=adv_icon)
        adv_header.label(text="Advanced")
        if scene.cesium_show_advanced:
            adv = box_adv.box()
            adv.prop(scene, "cesium_force_unlit_materials")
            adv.prop(scene, "cesium_root_transform_yup_for_threejs")
            adv.prop(scene, "cesium_keep_temp_objects")
            row = adv.row(align=True)
            row.operator("object.patch_cesium_output_unlit", icon='SHADING_TEXTURE')
            row.operator("object.strip_cesium_output_unlit", icon='X')

        # ====================================================================
        # STEP 2 — produce the tileset
        # ====================================================================
        layout.separator()
        layout.operator("object.export_cesium_tiles", text="2.  Export Cesium 3D Tiles", icon='EXPORT')

        # Progress (live)
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

        # ====================================================================
        # STEP 3 — preview & deliver (post-export)
        # ====================================================================
        layout.separator()
        head3 = layout.row()
        head3.alignment = 'CENTER'
        head3.label(text="3.  Preview / Deliver", icon='WORLD')

        # 3.1  Preview in ATON (collapsible, default closed) ------------------
        box_aton = layout.box()
        aton_header = box_aton.row(align=True)
        aton_icon = 'TRIA_DOWN' if scene.cesium_show_aton else 'TRIA_RIGHT'
        aton_header.prop(scene, "cesium_show_aton", text="", emboss=False, icon=aton_icon)
        aton_header.label(text="3.1  Preview in ATON", icon='WORLD')
        if scene.cesium_show_aton:
            aton = box_aton.box()
            aton.label(text="ATON local server", icon='URL')
            aton.prop(scene, "cesium_aton_path")
            aton.prop(scene, "cesium_aton_url")
            row = aton.row(align=True)
            row.operator("object.launch_aton", text="Launch", icon='PLAY')
            row.operator("object.open_aton_browser", text="Open URL", icon='URL')

            aton.separator()
            aton.label(text="Publish current export", icon='WORLD_DATA')
            aton.prop(scene, "cesium_aton_user")
            row_n = aton.row(align=True)
            row_n.prop(scene, "cesium_aton_scene_name")
            row_n.operator("object.generate_aton_scene_name",
                           text="", icon='FILE_REFRESH')
            aton.prop(scene, "cesium_aton_yup_rotation")
            aton.prop(scene, "cesium_aton_error_target")
            row_p = aton.row(align=True)
            row_p.prop(scene, "cesium_aton_open_browser", text="Open browser")
            row_p.prop(scene, "cesium_aton_overwrite", text="Overwrite")
            aton.operator("object.publish_to_aton",
                          text="Publish + view in ATON", icon='EXPORT')

        # 3.2  Deliver (zip) --------------------------------------------------
        box_zip = layout.box()
        box_zip.label(text="3.2  Deliver tileset", icon='FILE_ARCHIVE')
        box_zip.prop(scene, "cesium_zip_output", text="Auto-zip after export")
        box_zip.operator("object.cesium_zip_output", text="Save zip now", icon='FILE_NEW')
