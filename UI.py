import bpy
import mathutils

from bpy.types import Panel
from bpy.types import Operator
from bpy.types import PropertyGroup
from bpy.types import Menu, UIList

from .functions import *
from . import report_data
from . import addon_updater_ops

import os
from bpy_extras.io_utils import ImportHelper, axis_conversion

from bpy.props import (BoolProperty,
                       FloatProperty,
                       StringProperty,
                       EnumProperty,
                       CollectionProperty
                       )


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
                # if is_edit and data and data[1]:
                #     bm_type, _bm_array = data
                #     col.operator("mesh.print3d_select_report", text=text,
                #                  icon=self._type_to_icon[bm_type],).index = i
                # else:
                #     col.label(text=text)

    def draw(self, context):
        layout = self.layout

        # TODO, presets

        layout.label(text="Statistics")
        row = layout.row(align=True)
        #row.operator("mesh.print3d_info_volume", text="Volume")
        row.operator("mesh.info_area", text="Area")
        row.operator("mesh.info_texs", text="TexStats")
        row.operator("mesh.info_texres", text="MeanRes")

        self.draw_report(context)

class ToolsPanelImport:
    bl_label = "Importers"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'

    def draw(self, context):
        layout = self.layout
        obj = context.object

        row = layout.row()
        self.layout.operator("import_points.txt", icon="STICKY_UVS_DISABLE", text='Coordinates')
        row = layout.row()
        self.layout.operator("import_scene.multiple_objs", icon="DUPLICATE", text='Multiple objs')
        row = layout.row()
        self.layout.operator("import_cam.agixml", icon="DUPLICATE", text='Agisoft xml cams')

class ToolsPanelExport:
    bl_label = "Exporters"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        layout = self.layout
        obj = context.object
        row = layout.row()
        if obj is not None:
            self.layout.operator("export.coordname", icon="STICKY_UVS_DISABLE", text='Coordinates')
            row = layout.row()

            box = layout.box()
            row = box.row()
            row.label(text= "Export object(s) in one file:")
            row = box.row()
            row.operator("export.object", icon="OBJECT_DATA", text='obj')
            #row = box.row()
            row.operator("fbx.exp", icon="OBJECT_DATA", text='fbx')
            row = box.row()
            row.label(text= "-> "+obj.name + ".obj/.fbx")

            box = layout.box()
            row = box.row()
            row.label(text= "Export objects in several files:")
            row = box.row()
            row.operator("obj.exportbatch", icon="DUPLICATE", text='obj')
            row.operator("fbx.exportbatch", icon="DUPLICATE", text='fbx')
            row = box.row()
            if not bpy.context.scene.FBX_export_dir:
                row.label(text= "-> /objectname.obj")
                row = box.row()
                row.label(text= "-> /FBX/objectname.fbx")
            row = box.row()
            row.prop(context.scene, 'FBX_export_dir', toggle = True, text='Export to')
        else:
            row.label(text="Select object(s) to see tools here.")
            row = layout.row()

class ToolsPanelSHIFT:
    bl_label = "Shifting"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    #bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        addon_updater_ops.check_for_update_background()
        layout = self.layout
        scene = context.scene
        obj = context.object

        row = layout.row()
        row.label(text="Shift values:")
        row = layout.row()
        #row.prop(context.scene, 'SRID', toggle = True)
        #row = layout.row()
        row.prop(context.scene, 'BL_x_shift', toggle = True)
        row = layout.row()
        row.prop(context.scene, 'BL_y_shift', toggle = True)
        row = layout.row()
        row.prop(context.scene, 'BL_z_shift', toggle = True)
        row = layout.row()
        #if scene['crs x'] is not None and scene['crs y'] is not None:
        #    if scene['crs x'] > 0 or scene['crs y'] > 0:
        #        self.layout.operator("shift_from.blendergis", icon="PASTEDOWN", text='from Bender GIS')

        addon_updater_ops.update_notice_box_ui(self, context)

class ToolsPanelQuickUtils:
    bl_label = "Quick Utils"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        layout = self.layout
        obj = context.object
        scene = context.scene

        # row = layout.row()
        # self.layout.operator("center.mass", icon="DOT", text='Center of Mass')
        # row = layout.row()
        # self.layout.operator("correct.material", icon="NODE", text='Correct Photoscan mats')
        # row = layout.row()
        # self.layout.operator("local.texture", icon="TEXTURE", text='Local texture mode ON')
        # row = layout.row()
        # self.layout.operator("create.personalgroups", icon="GROUP", text='Create per-object groups')
        # row = layout.row()
        # self.layout.operator("remove.alluvexcept1", icon="GROUP", text='Only UV0 will survive')
        # row = layout.row()
        # self.layout.operator("remove.fromallgroups", icon="LIBRARY_DATA_BROKEN", text='Remove from all groups')
        # row = layout.row()
        # self.layout.operator("multimaterial.layout", icon="IMGDISPLAY", text='Multimaterial layout')
        # row = layout.row()
        # self.layout.operator("lod0poly.reducer", icon="IMGDISPLAY", text='LOD0 mesh decimator')
        row = layout.row()
        row.operator("project.segmentation", icon="SCULPTMODE_HLT", text='Mono-cutter')
        #row = layout.row()
        row.operator("project.segmentationinv", icon="SCULPTMODE_HLT", text='Multi-cutter')
        #row = layout.row()

        self.layout.operator("circum.center", icon="PROP_OFF", text='CircumCenter')
        #row = layout.row()

        # self.layout.operator("tiff2png.relink", icon="META_DATA", text='Relink images from tiff to png')
        # row = layout.row()
        self.layout.operator("rename.ge", icon="FILE_TEXT", text='Ren 4 GE')
        # self.layout.operator("obname.ffn", icon="META_DATA", text='Ren active from namefile')
        box = layout.box()
        row = box.row()
        #row = layout.row()
        row.label(text="Remove selected suffix (if any):")
        row = box.row()
        op = row.operator("remove.suffixnumber", icon="CANCEL", text='')
        op.suffix = context.window_manager.suffix_num.suffixnum
        #row = layout.row()
        row.prop(context.window_manager.suffix_num, 'suffixnum', expand=True)
        # row = layout.row()
        # row.label(text="Switch engine")
        # self.layout.operator("activatenode.material", icon="PMARKER_SEL", text='Activate cycles nodes')
        # self.layout.operator("deactivatenode.material", icon="PMARKER", text='De-activate cycles nodes')
        # self.layout.operator("bi2cycles.material", icon="PARTICLES", text='Create cycles nodes')
        # self.layout.operator("cycles2bi.material", icon="PMARKER", text='Cycles to BI')

class ToolsPanelLODmanager:
    bl_label = "LOD manager"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        layout = self.layout
        obj = context.object
        scene = context.scene

        row = layout.row()
        row.label(text="Change LOD of selected linked objects:")
        row = layout.row()

        split = layout.split()
        # First column
        col = split.column()
        col.prop(scene, 'setLODnum', icon='BLENDER', toggle=True)
        # Second column, aligned
        col = split.column(align=True)
        col.operator("change.lod", text='set LOD')
        #self.layout.operator("change.lod", icon="MESH_UVSPHERE", text='set LOD')

class ToolsPanelLODgenerator:
    bl_label = "LOD generator"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        layout = self.layout
        obj = context.object
        scene = context.scene

        if obj:#.type==['MESH']:
            self.layout.operator("lod0.creation", icon="MESH_UVSPHERE", text='LOD 0 (set as)')
            row = layout.row()

            split = layout.split()
            # First column
            col = split.column()
            col.prop(scene, 'LODnum', icon='BLENDER', toggle=True)
            # Second column, aligned
            col = split.column(align=True)
            #col.operator("lod.creation", icon="MOD_MULTIRES", text='')
            col.operator("lod.creation", text='generate')
            if scene.LODnum >= 1:
                split = layout.split()
                # First column
                col = split.column()
                col.label(text="Geometry")
                #col.label(text="ratio")
                col.prop(scene, 'LOD1_dec_ratio', icon='BLENDER', toggle=True, text="")
                # Second column, aligned
                col = split.column()
                col.label(text="Texture")
                #col.label(text="resolution")
                col.prop(scene, 'LOD1_tex_res', icon='BLENDER', toggle=True, text="")
                if scene.LODnum >= 2:
                    split = layout.split()
                    # First column
                    col = split.column()
                    col.prop(scene, 'LOD2_dec_ratio', icon='BLENDER', toggle=True, text="")
                    col = split.column()
                    # Second column, aligned
                    col.prop(scene, 'LOD2_tex_res', icon='BLENDER', toggle=True, text="")
                    if scene.LODnum >= 3:
                        split = layout.split()
                        # First column
                        col = split.column()
                        col.prop(scene, 'LOD3_dec_ratio', icon='BLENDER', toggle=True, text="")
                        col = split.column()
                        # Second column, aligned
                        col.prop(scene, 'LOD3_tex_res', icon='BLENDER', toggle=True, text="")

            row = layout.row()
            row.label(text="LOD clusters")

            split = layout.split()
            # First column
            col = split.column()
            col.operator("create.grouplod", icon="PRESET", text='')
            # Second column, aligned
            col = split.column(align=True)
            col.operator("remove.grouplod", icon="CANCEL", text='')

            row = layout.row()
            row.label(text="LOD cluster(s) export:")
            row = layout.row()
            row.prop(context.scene, 'FBX_export_dir', toggle = True, text='folder')
            self.layout.operator("exportfbx.grouplod", icon="MESH_GRID", text='FBX')

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
                row = layout.row()
        else:
            select_a_mesh(layout)

class Camera_menu(bpy.types.Menu):
    bl_label = "Custom Menu"
    bl_idname = "OBJECT_MT_Camera_menu"

    def draw(self, context):
        camera_type_list = context.scene.camera_list
        idx = 0
        layout = self.layout
        while idx < len(camera_type_list):
            op = layout.operator(
                    "set_camera.type", text=camera_type_list[idx].name_cam, emboss=False, icon="RIGHTARROW")
            op.name_cam = camera_type_list[idx].name_cam
            idx +=1

class ToolsPanelPhotogrTool:
    bl_label = "Photogrammetry paint"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        layout = self.layout
        scene = context.scene
        cam_ob = None
        cam_ob = scene.camera


        if cam_ob is None:
            row = layout.row()
            row.label(text="Please, add a Cam to see tools here")

        else:
            camera_type = context.scene.camera_type
            obj = context.object
            obj_selected = context.view_layer.objects.active
            cam_cam = scene.camera.data
            row = layout.row()
            op = row.operator("set_background.cam", icon="FILE_TICK", text='BG Cam')
            op.name_cam = "Camera"
            row = layout.row()
            row.label(text="Set up scene", icon='EXPERIMENTAL')
            #row.prop(scene, 'LODnum', icon='BLENDER', toggle=True)
            row = layout.row()
            split = row.split()
            col = split.column()
            col.operator("xmlcam.parse", icon="FILE_TICK", text='Refresh')
            col = split.column()
            col.prop(scene, 'camera_lens', icon='BLENDER', toggle=True, text='Lens')

            if camera_type is not 'Not set':
                row = layout.row()
                row.menu(Camera_menu.bl_idname, text=camera_type, icon='COLOR')

            if obj_selected:
                if obj.type in ['MESH']:
                    pass
                elif obj.type in ['CAMERA']:
                    row = layout.row()
                    row.label(text="Visual mode:", icon='PLUS')
                    row = layout.row()
                    split = row.split()
                    col = split.column()
                    col.operator("better.cameras", icon="PLUS", text='Better Cams')
                    col = split.column()
                    col.operator("nobetter.cameras", icon="PLUS", text='Disable Better Cams')
                    row = layout.row()
                else:
                    row = layout.row()
                    row.label(text="Please select a mesh or a cam", icon='PLUS')

            row = layout.row()
            row.label(text="Painting Toolbox", icon='PLUS')
            row = layout.row()
            row.label(text="Folder with undistorted images:")
            row = layout.row()
            row.prop(context.scene, 'BL_undistorted_path', toggle = True)
            row = layout.row()

            if cam_ob is not None:
                row.label(text="Active Cam: " + cam_ob.name)
                self.layout.operator("object.createcameraimageplane", icon="PLUS", text='Photo to camera')
                row = layout.row()
                row = layout.row()
                row.prop(cam_cam, "lens")
                row = layout.row()
                is_cam_ob_plane = check_children_plane(cam_ob)
               # row.label(text=str(is_cam_ob_plane))
                if is_cam_ob_plane:
                    if obj.type in ['MESH']:
                        row.label(text="Active object: " + obj.name)
                        self.layout.operator("paint.cam", icon="PLUS", text='Paint active from cam')
                else:
                    row = layout.row()
                    row.label(text="Please, set a photo to camera", icon='TPAINT_HLT')

                self.layout.operator("applypaint.cam", icon="PLUS", text='Apply paint')
                self.layout.operator("savepaint.cam", icon="PLUS", text='Save modified texs')
                row = layout.row()
            else:
                row.label(text="!!! Import some cams to start !!!")

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

class VIEW3D_PT_Import_ToolBar(Panel, ToolsPanelImport):
    bl_category = "3DSC"
    bl_idname = "VIEW3D_PT_Import_ToolBar"
    bl_context = "objectmode"

class VIEW3D_PT_Export_ToolBar(Panel, ToolsPanelExport):
    bl_category = "3DSC"
    bl_idname = "VIEW3D_PT_Export_ToolBar"
    bl_context = "objectmode"

class VIEW3D_PT_Shift_ToolBar(Panel, ToolsPanelSHIFT):
    bl_category = "3DSC"
    bl_idname = "VIEW3D_PT_Shift_ToolBar"
    bl_context = "objectmode"

class VIEW3D_PT_QuickUtils_ToolBar(Panel, ToolsPanelQuickUtils):
    bl_category = "3DSC"
    bl_idname = "VIEW3D_PT_QuickUtils_ToolBar"
    bl_context = "objectmode"

class VIEW3D_PT_LODgenerator(Panel, ToolsPanelLODgenerator):
    bl_category = "3DSC"
    bl_idname = "VIEW3D_PT_LODgenerator"
    bl_context = "objectmode"

class VIEW3D_PT_LODmanager(Panel, ToolsPanelLODmanager):
    bl_category = "3DSC"
    bl_idname = "VIEW3D_PT_LODmanager"
    bl_context = "objectmode"

class VIEW3D_PT_ccTool(Panel, ToolsPanel_ccTool):
    bl_category = "3DSC"
    bl_idname = "VIEW3D_PT_ccTool"
    bl_context = "objectmode"

class VIEW3D_PT_PhotogrTool(Panel, ToolsPanelPhotogrTool):
    bl_category = "3DSC"
    bl_idname = "VIEW3D_PT_PhotogrTool"
    bl_context = "objectmode"

class VIEW3D_PT_TexPatcher(Panel, ToolsPanelTexPatcher):
    bl_category = "3DSC"
    bl_idname = "VIEW3D_PT_TexPatcher"
    #bl_context = "objectmode"

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
    #bl_context = "objectmode"
