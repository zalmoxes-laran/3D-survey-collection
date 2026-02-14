import bpy

from bpy.types import Panel

from .functions import *
from . import report_data

class View3DCheckPanel:
    bl_label = "Model Inspector"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj is not None and obj.type == 'MESH' and obj.mode in {'OBJECT', 'EDIT'}

class VIEW3D_PT_mesh_analyze(Panel, View3DCheckPanel):
    bl_category = "3DSC"
    bl_idname = "VIEW3D_PT_mesh_analyze"
    bl_context = "objectmode"
    bl_options = {'DEFAULT_CLOSED'}

    _type_to_icon = {
        bmesh.types.BMVert: 'VERTEXSEL',
        bmesh.types.BMEdge: 'EDGESEL',
        bmesh.types.BMFace: 'FACESEL',
    }

    def draw_report(self, context):
        layout = self.layout
        info = report_data.info()

        if info:
            is_edit = context.edit_object is not None

            layout.label(text="Result")
            box = layout.box()
            col = box.column()

            for i, (text, data) in enumerate(info):
                col.label(text=text)


    def draw(self, context):
        layout = self.layout
        scene = context.scene

        # TODO, presets

        layout.label(text="Statistics")
        row = layout.row(align=True)
        #row.operator("mesh.print3d_info_volume", text="Volume")
        row.operator("mesh.info_area", text="Geometry")
        row.operator("mesh.info_texs", text="Textures")
        row.operator("mesh.info_texres", text="MeanRes")
        row = layout.row(align=True)
        row.prop(scene, "e3dsc_stats_strict", text="Strict mode")
        row.prop(scene, "e3dsc_stats_prompt_export", text="Prompt export after MeanRes")
        row = layout.row(align=True)
        row.operator("export_stats.tofile", text="Export Stats", icon='EXPORT')

        self.draw_report(context)

class View3DSegmentationPanel:

    bl_label = "Segmentation"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj is not None and obj.type == 'MESH' and obj.mode in {'OBJECT', 'EDIT'}

class VIEW3D_PT_segmentation_pan(Panel, View3DSegmentationPanel):
    bl_category = "3DSC"
    bl_idname = "VIEW3D_PT_segmentation_pan"
    bl_context = "objectmode"
    bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        layout = self.layout
        scene = context.scene
        cutter_col = bpy.data.collections.get("_cutter")
        cutter_count = len([o for o in cutter_col.objects if o.type == 'MESH']) if cutter_col else 0

        # Cutter setup
        row = layout.row(align=True)
        row.operator("set.cutter", icon="SCULPTMODE_HLT", text='Cutter set')
        row.prop(scene, 'TILE_square_meters', icon='BLENDER', toggle=True, text="m2:")
        op = row.operator("e3dsc.help_popup", text="", icon='QUESTION')
        op.title = "Segmentation - Cutter Set"
        op.text = (
            "Create a cutter grid from the active mesh extent and store cutters in the _cutter collection. "
            "If active object scale is not 1,1,1, the tool asks to apply scale before running."
        )
        op.url = "3DSCstructure.html#segmentation-cutter-set"

        row = layout.row(align=True)
        row.label(text=f"Cutters available: {cutter_count}")
        row.operator("set.clear_cutters", icon='TRASH', text='Delete all cutters')

        row = layout.row(align=True)
        row.prop(scene, "e3dsc_segmentation_preclean", text="Topology pre-clean before cut")
        op = row.operator("e3dsc.help_popup", text="", icon='QUESTION')
        op.title = "Segmentation - Topology Pre-clean"
        op.text = (
            "When enabled, target meshes are cleaned before each cut by merging doubled vertices. "
            "Disable it for faster runs if topology is already clean."
        )
        op.url = "3DSCstructure.html#segmentation-cut-modes"

        row = layout.row(align=True)
        row.enabled = cutter_count > 0
        row.operator("project.segmentationinv", icon="SCULPTMODE_HLT", text='Multi-cutter')
        row.operator("project.segmentation", icon="SCULPTMODE_HLT", text='Mono-cutter')
        op = row.operator("e3dsc.help_popup", text="", icon='QUESTION')
        op.title = "Segmentation - Mono/Multi Cutter"
        op.text = (
            "Multi-cutter (main workflow): active target mesh is cut using selected cutters; "
            "if none are selected, all cutters in _cutter are used automatically.\n"
            "Mono-cutter (advanced/rare): active cutter mesh cuts selected non-cutter meshes."
        )
        op.url = "3DSCstructure.html#segmentation-cut-modes"

        if cutter_count == 0:
            layout.label(text="Create a Cutter set first to enable segmentation.", icon='INFO')

class ToolsPanelExport:
    bl_label = "Exporters"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        layout = self.layout
        scene = context.scene
        active_obj = context.active_object

        row = layout.row(align=True)
        row.scale_y = 0.9
        row.operator("export.coordname", icon="STICKY_UVS_DISABLE", text='Coordinates')
        op = row.operator("e3dsc.help_popup", text="", icon='QUESTION')
        op.title = "Coordinates Export"
        op.text = (
            "Export selected object coordinates to TXT. "
            "Use operator options to include names, rotation/scale, camera-only mode and world shift."
        )
        op.url = "3DSCstructure.html#exporters"

        box = layout.box()

        # Mode buttons (state)
        row = box.row(align=True)
        row.prop(scene, "e3dsc_export_mode", expand=True)

        # Format buttons (state), dependent on mode
        row = box.row(align=True)
        if scene.e3dsc_export_mode == 'SINGLE':
            row.prop(scene, "e3dsc_export_single_format", expand=True)
        else:
            row.prop(scene, "e3dsc_export_multi_format", expand=True)

        # Dynamic action + params
        format_id = scene.e3dsc_export_single_format if scene.e3dsc_export_mode == 'SINGLE' else scene.e3dsc_export_multi_format
        row = box.row(align=True)
        row.scale_y = 0.95

        if scene.e3dsc_export_mode == 'SINGLE':
            if format_id == 'OBJ':
                row.operator("export.object", icon="OBJECT_DATA", text='Export OBJ')
                op = row.operator("e3dsc.help_popup", text="", icon='QUESTION')
                op.title = "Single OBJ Export"
                op.text = "Export the active object as a single OBJ file."
                op.url = "3DSCstructure.html#exporters"
                #row = box.row()
                #row.prop(scene, 'SHIFT_OBJ_on', text="Use Shift (slower, only obj)")
            elif format_id == 'FBX':
                row.operator("fbx.exp", icon="OBJECT_DATA", text='Export FBX')
                op = row.operator("e3dsc.help_popup", text="", icon='QUESTION')
                op.title = "Single FBX Export"
                op.text = "Export the active object as a single FBX file."
                op.url = "3DSCstructure.html#exporters"
            if active_obj is not None:
                box.label(text=f"-> {active_obj.name}.{format_id.lower()}")
            else:
                box.label(text="Select an active object for single-file export.")

        else:
            # Shared batch destination
            row.prop(scene, 'model_export_dir', toggle=True, text='Export to')
            if not scene.model_export_dir:
                box.label(text="-> /[fileformat]/objectname")

            row = box.row(align=True)
            row.scale_y = 0.95
            if format_id == 'OBJ':
                row.operator("obj.exportbatch", icon="DUPLICATE", text='Export OBJ Batch')
                op = row.operator("e3dsc.help_popup", text="", icon='QUESTION')
                op.title = "OBJ Batch Export"
                op.text = (
                    "Export selected objects as individual OBJ files. "
                    #"Use Shift applies world shift only to OBJ workflows."
                )
                op.url = "3DSCstructure.html#exporters"
                #row = box.row()
                #row.prop(scene, 'SHIFT_OBJ_on', text="Use Shift (slower, only obj)")

            elif format_id == 'FBX':
                op_fbx = row.operator("model.exportbatch", icon="DUPLICATE", text='Export FBX Batch')
                op_fbx.export_format = "fbx"
                op = row.operator("e3dsc.help_popup", text="", icon='QUESTION')
                op.title = "FBX Batch Export"
                op.text = (
                    "Export selected objects as FBX files. "
                    "Supports instanced export and collection hierarchy output."
                )
                op.url = "3DSCstructure.html#exporters"
                row = box.row()
                row.prop(scene, 'instanced_export', text="Enable instanced_export (only FBX)")
                row = box.row()
                row.prop(scene, 'collgerarchy_to_foldtree', text="Use collection gerarchy")

            elif format_id == 'GLTF':
                op_gltf = row.operator("model.exportbatch", icon="DUPLICATE", text='Export glTF Batch')
                op_gltf.export_format = "gltf"
                op = row.operator("e3dsc.help_popup", text="", icon='QUESTION')
                op.title = "glTF Batch Export"
                op.text = (
                    "Export selected objects as glTF files with author metadata and texture compression options."
                )
                op.url = "3DSCstructure.html#exporters"
                row = box.row()
                row.prop(scene, 'author_sign_model', toggle=True, text='Author')
                row = box.row(align=True)
                row.prop(scene, 'gltf_export_maxres', toggle=True, text='Max resolution of jpg images')
                row.prop(scene, 'gltf_export_quality', toggle=True, text='Quality of jpg images')
                row = box.row()
                row.prop(scene, 'collgerarchy_to_foldtree', text="Use collection gerarchy")

            elif format_id == 'GLB':
                row.operator("glb.exportbatch", icon="DUPLICATE", text='Export GLB Batch')
                op = row.operator("e3dsc.help_popup", text="", icon='QUESTION')
                op.title = "GLB Batch Export"
                op.text = "Export selected objects as GLB files with author metadata."
                op.url = "3DSCstructure.html#exporters"
                row = box.row()
                row.prop(scene, 'author_sign_model', toggle=True, text='Author')

class ToolsPanelQuickUtils:
    bl_label = "Quick Utils"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        layout = self.layout
        # Quick Utils (miscellanea) tools at root level
        box = layout.box()
        row = box.row(align=True)
        row.operator("mesh.merge_by_distance_custom", icon="PROP_OFF", text='Vertex Merge by Distance')
        op = row.operator("e3dsc.help_popup", text="", icon='QUESTION')
        op.title = "Quick Utils - Vertex Merge by Distance"
        op.text = "Merge vertices that are closer than a threshold to clean selected meshes."
        op.url = "3DSCstructure.html#quick-utils"

        row = box.row(align=True)
        row.operator("rename.ge", icon="FILE_TEXT", text='Rename 4 GameEngines')
        op = row.operator("e3dsc.help_popup", text="", icon='QUESTION')
        op.title = "Quick Utils - Rename 4 GameEngines"
        op.text = "Apply a game-engine oriented naming convention to selected objects."
        op.url = "3DSCstructure.html#quick-utils"

        row = box.row(align=True)
        row.operator("invert.coordinates", icon="DECORATE_DRIVER", text='Invert x and y')
        op = row.operator("e3dsc.help_popup", text="", icon='QUESTION')
        op.title = "Quick Utils - Invert x and y"
        op.text = (
            "Swap X and Y coordinates of selected objects, preserving Z. "
            "Useful when total-station points are imported with swapped XY axes."
        )
        op.url = "3DSCstructure.html#quick-utils"
        box.label(text="Useful for total-station points imported with swapped XY.", icon='INFO')

        box.separator()
        row = box.row()
        row.label(text="Remove selected suffix (if any):")
        row = box.row(align=True)
        op = row.operator("remove.suffixnumber", icon="CANCEL", text='')
        op.suffix = context.window_manager.suffix_num.suffixnum
        row.prop(context.window_manager.suffix_num, 'suffixnum', expand=True)
        help_row = box.row(align=True)
        op = help_row.operator("e3dsc.help_popup", text="", icon='QUESTION')
        op.title = "Quick Utils - Remove Selected Suffix"
        op.text = "Remove selected suffixes (.001/.002/.003) from object names in batch."
        op.url = "3DSCstructure.html#quick-utils"

        box.separator()
        row = box.row(align=True)
        op = row.operator("setmaterial.blend", icon="MESH_CUBE", text='opaque')
        op.blendmode = "OPAQUE"
        op = row.operator("setmaterial.blend", icon="CUBE", text='transparent')
        op.blendmode = "BLEND"
        row = box.row()
        row.operator("set.roughness", icon="DECORATE_DRIVER", text='Roughness 1')
        row = box.row()
        row.operator("set.metalness", icon="DECORATE_DRIVER", text='Metalness 0')
        help_row = box.row(align=True)
        op = help_row.operator("e3dsc.help_popup", text="", icon='QUESTION')
        op.title = "Quick Utils - Batch Material Settings"
        op.text = (
            "Batch update blend mode and PBR values (roughness/metalness) "
            "for materials on selected meshes."
        )
        op.url = "3DSCstructure.html#quick-utils"

        box.separator()
        row = box.row(align=True)
        row.operator("diffuse.principled", icon="DECORATE_DRIVER", text='Diffuse 2 Principled')
        op = row.operator("e3dsc.help_popup", text="", icon='QUESTION')
        op.title = "Quick Utils - Legacy Material Conversion"
        op.text = "Convert legacy diffuse-like materials into Principled BSDF in batch."
        op.url = "3DSCstructure.html#quick-utils"


class ToolsPanel_ccTool:
    bl_label = "Color Correction"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        layout = self.layout
        obj = context.object
        scene = context.scene
        row = layout.row()
        #if bpy.context.scene.render.engine != 'CYCLES':
        #    row.label(text="Please, activate cycles engine !")
        #else:
        if context.active_object:
            if obj.type not in ['MESH']:
                select_a_mesh(layout)
            else:
                diag = cc_scan_selected_materials(context)
                box = layout.box()
                row = box.row(align=True)
                row.label(text="Shared CC node group across selected materials.", icon='LINKED')
                op = row.operator("e3dsc.help_popup", text="", icon='QUESTION')
                op.title = "Color Correction"
                op.text = (
                    "Create a non-destructive color correction setup shared across selected materials. "
                    "Supports renamed nodes by tracing the Base Color graph instead of relying on node names.\n"
                    "Bake writes corrected textures to cc_image targets. "
                    "Apply keeps a backup of the original texture and promotes cc_image as active color input."
                )
                op.url = "3DSCstructure.html#color-correction"
                box.label(text=f"Materials ready: {diag['ready']}  |  Skipped/unsupported: {diag['unsupported']}")

                activeobj = context.active_object
                if get_nodegroupname_from_obj(obj) is None:
                    layout.operator("create.ccsetup", icon="SEQ_HISTOGRAM", text='create cc setup')
                else:
                    #print(node_to_visualize)
                    row = layout.row()
                    layout.operator("removeccnode.material", icon="CANCEL", text='remove cc setup')
                    row = layout.row()

                    nodegroupname = get_nodegroupname_from_obj(obj)
                    row.label(text="cc node: "+ nodegroupname)

                    row = layout.row()
                    row.prop(context.window_manager.interface_vars, 'cc_nodes', expand=True)
                    node_to_visualize = context.window_manager.interface_vars.cc_nodes

                    row = layout.row()

                    if node_to_visualize == 'RGB':
                        node = get_cc_node_in_obj_mat(nodegroupname, 'RGB')
                        row.label(text=node.name)# + nodegroupname)
                        layout.context_pointer_set("node", node)
                        node.draw_buttons_ext(context, layout)

                    if node_to_visualize == 'BC':
                        node = get_cc_node_in_obj_mat(nodegroupname, 'BC')
                        row.label(text=node.name)# + nodegroupname)
                        row = layout.row()
                        row.prop(node.inputs[1], 'default_value', icon='BLENDER', toggle=True, text='Bright')
                        row = layout.row()
                        row.prop(node.inputs[2], 'default_value', icon='BLENDER', toggle=True, text='Contrast')

                    if node_to_visualize == 'HS':
                        node = get_cc_node_in_obj_mat(nodegroupname, 'HS')
                        row.label(text=node.name)# + nodegroupname)
                        row = layout.row()
                        row.prop(node.inputs[0], 'default_value', icon='BLENDER', toggle=True, text='Hue')
                        row = layout.row()
                        row.prop(node.inputs[1], 'default_value', icon='BLENDER', toggle=True, text='Saturation')
                        row = layout.row()
                        row.prop(node.inputs[2], 'default_value', icon='BLENDER', toggle=True, text='Value')


                    row = layout.row()
                    row = layout.row()

                    row.prop(context.window_manager.ccToolViewVar, 'cc_view', expand=True)
                    view_mode = context.window_manager.ccToolViewVar.cc_view

                    row = layout.row()

                    layout.operator("set.cc_view", icon="HIDE_OFF", text='Set view mode')

                    split = layout.split()
                    # First column
                    col = split.column()
                    col.operator("bake.cyclesdiffuse", icon="TPAINT_HLT", text='bake')

                    # Second column, aligned
                    col = split.column(align=True)
                    col.operator("savepaint.cam", icon="WORKSPACE", text='save')
                    row = layout.row()

                    layout.operator("applyccsetup.material", icon="FILE_TICK", text='apply cc')
                    layout.label(text="Apply keeps original texture backup.", icon='INFO')
                row = layout.row()
        else:
            select_a_mesh(layout)

class ToolsPanelTexPatcher:
    bl_label = "Texture mixer"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        layout = self.layout
        obj = context.object
        scene = context.scene
        row = layout.row()
        if bpy.context.scene.render.engine != 'CYCLES':
            row.label(text="Please, activate cycles engine !")
        else:
            row = layout.row()
           # row.label(text="Select one or more source mesh")
           # row = layout.row()
           # row.label(text="+ a destination mesh")
            self.layout.operator("texture.transfer", icon="FULLSCREEN_EXIT", text='Transfer Texture')
            self.layout.operator("applysptexset.material", icon="AUTOMERGE_ON", text='Preview sp tex set')
            self.layout.operator("applyoritexset.material", icon="RECOVER_LAST", text='Use original tex set')
            self.layout.operator("paint.setup", icon="VPAINT_HLT", text='Paint from source')
            if context.object.mode == 'TEXTURE_PAINT':
                row = layout.row()
                row.prop(scene.tool_settings.image_paint, "seam_bleed")
                row = layout.row()
                row.prop(scene.tool_settings.image_paint, "use_occlude")
                row.prop(scene.tool_settings.image_paint, "use_backface_culling")
                row.prop(scene.tool_settings.image_paint, "use_normal_falloff")

                row = layout.row()
                self.layout.operator("exit.setup", icon="OBJECT_DATAMODE", text='Exit paint mode')
            row = layout.row()
            self.layout.operator("savepaint.cam", icon="DISK_DRIVE", text='Save new textures')
            self.layout.operator("remove.sp", icon="CANCEL", text='Remove image source')


##################################################################################################################
###################################### classes ###################################################################
##################################################################################################################

class VIEW3D_PT_Export_ToolBar(Panel, ToolsPanelExport):
    bl_category = "3DSC"
    bl_idname = "VIEW3D_PT_Export_ToolBar"
    bl_context = "objectmode"
    bl_options = {'DEFAULT_CLOSED'}

class VIEW3D_PT_QuickUtils_ToolBar(Panel, ToolsPanelQuickUtils):
    bl_category = "3DSC"
    bl_idname = "VIEW3D_PT_QuickUtils_ToolBar"
    bl_options = {'DEFAULT_CLOSED'}
    bl_order = 30

class VIEW3D_PT_ccTool(Panel, ToolsPanel_ccTool):
    bl_category = "3DSC"
    bl_idname = "VIEW3D_PT_ccTool"
    bl_context = "objectmode"
    bl_options = {'DEFAULT_CLOSED'}

class VIEW3D_PT_TexPatcher(Panel, ToolsPanelTexPatcher):
    bl_category = "3DSC"
    bl_idname = "VIEW3D_PT_TexPatcher"
    bl_options = {'DEFAULT_CLOSED'}


#panorama

class Res_menu(bpy.types.Menu):
    bl_label = "Custom Menu"
    bl_idname = "OBJECT_MT_Res_menu"

    def draw(self, context):
        res_list = context.scene.resolution_list
        idx = 0
        layout = self.layout
        while idx < len(res_list):
            op = layout.operator(
                    "set.pano_res", text=str(res_list[idx].res_num), emboss=False, icon="RIGHTARROW")
            op.res_number = str(res_list[idx].res_num)
            idx +=1

class PANOToolsPanel:
    bl_label = "Panorama suite"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        layout = self.layout
        scene = context.scene
        obj = context.active_object
        resolution_pano = scene.RES_pano

        row = layout.row()
        row.label(text="PANO file")
        row = layout.row()
        row.prop(context.scene, 'PANO_file', toggle = True)
        row = layout.row()
        row.prop(context.scene, 'PANO_dir', toggle = True)
        row = layout.row()
        self.layout.operator("import.pano", icon="GROUP_UVS", text='Read/Refresh PANO file')

        if context.active_object:
            if obj.type not in ['MESH']:
                select_a_mesh(layout)
            else:
                row = layout.row()
                split = layout.split()
                col = split.column()
                col.operator("ubermat_create.pano", icon="MATERIAL", text='')
                col = split.column()
                col.operator("ubermat_update.pano", icon="MATERIAL", text='')
                row = layout.row()

                #split = layout.split()
                #col = split.column()

                if len(scene.resolution_list) > 0:
                    row = layout.row()
                    row.menu(Res_menu.bl_idname, text=str(resolution_pano), icon='COLOR')

                #col.prop(context.scene, 'RES_pano', toggle = True)
                #col = split.column()
                #col.operator("set.panores", icon="NODE_COMPOSITING", text='')
                row = layout.row()

                row = layout.row(align=True)
                split = row.split()
                col = split.column()
                col.label(text="Display mode")
                col = split.column(align=True)

                #col.menu(Res_mode_menu.bl_idname, text=str(context.scene.RES_pano), icon='COLOR')

        row = layout.row()
        layout.alignment = 'LEFT'
        row.template_list("PANO_UL_List", "PANO nodes", scene, "pano_list", scene, "pano_list_index")

        if scene.pano_list_index >= 0 and len(scene.pano_list) > 0:
            current_pano = scene.pano_list[scene.pano_list_index].name
            item = scene.pano_list[scene.pano_list_index]
            row = layout.row()
            row.label(text="Name:")
            row = layout.row()
            row.prop(item, "name", text="")

        if context.active_object:
            if obj.type in ['MESH']:
                if obj.material_slots:
                    if obj.material_slots[0].material.name.endswith('uberpano'):
                        row = layout.row()
                        node = get_cc_node_pano(obj, current_pano)
                        row.label(text=node.name)# + nodegroupname)
                        layout.context_pointer_set("node", node)
                        node.draw_buttons_ext(context, layout)

        row = layout.row()
        self.layout.operator("view.pano", icon="ZOOM_PREVIOUS", text='Inside the Pano')
        row = layout.row()
        self.layout.operator("remove.pano", icon="ERROR", text='Remove the Pano')
        row = layout.row()
        self.layout.operator("align.quad", icon="OUTLINER_OB_FORCE_FIELD", text='Align quad')
        row = layout.row()
        split = layout.split()
        # First column
        col = split.column()
        col.label(text="Lens:")
        col.prop(context.scene, 'PANO_cam_lens', toggle = True)
        # Second column, aligned
        col = split.column(align=True)
        col.label(text="Apply")
        col.operator("set.lens", icon="FILE_TICK", text='SL')

class VIEW3D_PT_SetupPanel(Panel, PANOToolsPanel):
    bl_category = "3DSC"
    bl_idname = "VIEW3D_PT_SetupPanel"
    bl_options = {'DEFAULT_CLOSED'}
