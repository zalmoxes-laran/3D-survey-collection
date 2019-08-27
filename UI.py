import bpy

from bpy.types import Panel
from bpy.types import Operator
from bpy.types import PropertyGroup

from .functions import *

import os
from bpy_extras.io_utils import ImportHelper

from bpy.props import (BoolProperty,
                       FloatProperty,
                       StringProperty,
                       EnumProperty,
                       CollectionProperty
                       )

class ToolsPanelImport:
    bl_label = "Importers"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'

    def draw(self, context):
        layout = self.layout
        obj = context.object

        ßrow = layout.row()
        self.layout.operator("import_points.txt", icon="STICKY_UVS_DISABLE", text='Coordinates')
        row = layout.row()
        self.layout.operator("import_scene.multiple_objs", icon="DUPLICATE", text='Multiple objs')
        row = layout.row()
        self.layout.operator("import_cam.agixml", icon="DUPLICATE", text='Agisoft xml cams')
 

class ToolsPanelExport:
    bl_label = "Exporters"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'

    def draw(self, context):
        layout = self.layout
        obj = context.object
        row = layout.row()
        if obj is not None:
            self.layout.operator("export.coordname", icon="STICKY_UVS_DISABLE", text='Coordinates')
            row = layout.row()
            #row.label(text=obj.name)
            #row = layout.row()
            #row.label(text="Override")
            #row = layout.row()

            #layout.separator()
            box = layout.box()
            row = box.row()
            row.operator("export.object", icon="OBJECT_DATA", text='One obj')
            row = box.row()
            row.operator("fbx.exp", icon="OBJECT_DATA", text='One fbx UE4')
            row = box.row() 
            row.label(text= "-> "+obj.name + ".obj/.fbx")
            #row = box.row()
            #row.prop(obj, "name", text="")
            box = layout.box()
            row = box.row()
            row.operator("obj.exportbatch", icon="DUPLICATE", text='Several obj')
            row = box.row() 
            row.label(text= "-> /objectname.obj")
            row = box.row()
            row.operator("fbx.exportbatch", icon="DUPLICATE", text='Several fbx UE4')
            row = box.row() 
            row.label(text= "-> /FBX/objectname.fbx")
            #row = layout.row()

#            self.layout.operator("osgt.exportbatch", icon="OBJECT_DATA", text='Exp. several osgt files')
#            row = layout.row()
#            if is_windows():
#                row = layout.row()
#                row.label(text="We are under Windows..")
        else:
            row.label(text="Select object(s) to see tools here.")
            row = layout.row()


class ToolsPanelSHIFT:
    bl_label = "Shifting"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'

    def draw(self, context):
        layout = self.layout
        scene = context.scene
        obj = context.object

        row = layout.row()        
        row.label(text="Shift values:")
        row = layout.row()
#        row.prop(context.scene, 'SRID', toggle = True)
#        row = layout.row() 
        row.prop(context.scene, 'BL_x_shift', toggle = True)
        row = layout.row()  
        row.prop(context.scene, 'BL_y_shift', toggle = True)
        row = layout.row()  
        row.prop(context.scene, 'BL_z_shift', toggle = True)    
        row = layout.row()
#        if scene['crs x'] is not None and scene['crs y'] is not None:
#            if scene['crs x'] > 0 or scene['crs y'] > 0:
#                self.layout.operator("shift_from.blendergis", icon="PASTEDOWN", text='from Bender GIS')


class ToolsPanelQuickUtils:
    bl_label = "Quick Utils"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        layout = self.layout
        obj = context.object
        scene = context.scene
        row = layout.row()
        self.layout.operator("center.mass", icon="DOT", text='Center of Mass')
        row = layout.row()
        self.layout.operator("correct.material", icon="NODE", text='Correct Photoscan mats')
        row = layout.row()
        self.layout.operator("local.texture", icon="TEXTURE", text='Local texture mode ON')
        row = layout.row()

#   Here I need to remove this feature since it is no more usefull
#        self.layout.operator("light.off", icon="LIGHT", text='Deactivate lights')
#        row = layout.row()
        self.layout.operator("create.personalgroups", icon="GROUP", text='Create per-object groups')
        row = layout.row()
        self.layout.operator("remove.alluvexcept1", icon="GROUP", text='Only UV0 will survive')
        row = layout.row()
        self.layout.operator("remove.fromallgroups", icon="LIBRARY_DATA_BROKEN", text='Remove from all groups')
        row = layout.row()
        self.layout.operator("multimaterial.layout", icon="IMGDISPLAY", text='Multimaterial layout')
        row = layout.row()
        self.layout.operator("lod0poly.reducer", icon="IMGDISPLAY", text='LOD0 mesh decimator')
        row = layout.row()
        self.layout.operator("project.segmentation", icon="SCULPTMODE_HLT", text='Mono-cutter')
        row = layout.row()
        self.layout.operator("project.segmentationinv", icon="SCULPTMODE_HLT", text='Multi-cutter')
        row = layout.row()

        self.layout.operator("tiff2png.relink", icon="META_DATA", text='Relink images from tiff to png')
        row = layout.row()

        self.layout.operator("obname.ffn", icon="META_DATA", text='Ren active from namefile')
        row = layout.row()
        self.layout.operator("rename.ge", icon="META_DATA", text='Ren 4 GE')
        row = layout.row()
        row.label(text="Switch engine")
        self.layout.operator("activatenode.material", icon="PMARKER_SEL", text='Activate cycles nodes')
        self.layout.operator("deactivatenode.material", icon="PMARKER", text='De-activate cycles nodes')
        self.layout.operator("bi2cycles.material", icon="PARTICLES", text='Create cycles nodes')
        self.layout.operator("cycles2bi.material", icon="PMARKER", text='Cycles to BI')

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

                # per ora tengo questa riga per eventuale gestione di file provenienti dalla 2.79:
                #self.layout.operator("bi2cycles.material", icon="MOD_PARTICLE_INSTANCE", text='Create cycles nodes')
                
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
            obj = context.object
            obj_selected = context.view_layer.objects.active
            cam_cam = scene.camera.data
            row = layout.row()
            row.label(text="Set up scene", icon='EXPERIMENTAL')
            row = layout.row()
            self.layout.operator("isometric.scene", icon="PLUS", text='Isometric scene')
            self.layout.operator("canon6d.scene", icon="PLUS", text='CANON 6D scene')
            self.layout.operator("nikond3200.scene", icon="PLUS", text='NIKON D3200 scene')
            if obj_selected:
                if obj.type in ['MESH']:
                    pass
                elif obj.type in ['CAMERA']:
                    row = layout.row()
                    row.label(text="Set selected cams as:", icon='PLUS')
                    self.layout.operator("nikond320018mm.camera", icon="PLUS", text='Nikon d3200 18mm')
                    self.layout.operator("canon6d35mm.camera", icon="PLUS", text='Canon6D 35mm')
                    self.layout.operator("canon6d24mm.camera", icon="PLUS", text='Canon6D 24mm')
                    self.layout.operator("canon6d14mm.camera", icon="PLUS", text='Canon6D 14mm')
                    row = layout.row()
                    row.label(text="Visual mode for selected cams:", icon='PLUS')
                    self.layout.operator("better.cameras", icon="PLUS", text='Better Cams')
                    self.layout.operator("nobetter.cameras", icon="PLUS", text='Disable Better Cams')
                    row = layout.row()
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
#                row.label(text=str(is_cam_ob_plane))
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
    bl_label = "Texture patcher"
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
#            row.label(text="Select one or more source mesh")
#            row = layout.row()
#            row.label(text="+ a destination mesh")
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
            self.layout.operator("savepaint.cam", icon="IMAGE_COL", text='Save new textures')
            self.layout.operator("remove.sp", icon="LIBRARY_DATA_BROKEN", text='Remove image source')


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
    bl_context = "objectmode"

#panorama

class PANOToolsPanel:

    bl_label = "Panorama suite"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"

    def draw(self, context):
        layout = self.layout
        scene = context.scene
        obj = context.object
        row = layout.row()
        row.label(text="PANO file")
        row = layout.row()
        row.prop(context.scene, 'PANO_file', toggle = True)
        row = layout.row()
        row.prop(context.scene, 'PANO_dir', toggle = True)
        row = layout.row()
        self.layout.operator("import.pano", icon="GROUP_UVS", text='Read/Refresh PANO file')
        row = layout.row()
#        self.layout.operator("uslist_icon.update", icon="PARTICLE_DATA", text='Only icons refresh')
#        row = layout.row()
        layout.alignment = 'LEFT'
        row.template_list("PANO_UL_List", "PANO nodes", scene, "pano_list", scene, "pano_list_index")
        if scene.pano_list_index >= 0 and len(scene.pano_list) > 0:
            item = scene.pano_list[scene.pano_list_index]
            row = layout.row()
            row.label(text="Name:")
            row = layout.row()
            row.prop(item, "name", text="")
#        if obj.type in ['CAMERA']:
#            obj = context.object
#            row = layout.row()
#            row.label(text="Active camera is: " + obj.name)
#            row = layout.row()
        row = layout.row()
        self.layout.operator("view.pano", icon="ZOOM_PREVIOUS", text='Inside the Pano')
        row = layout.row()
        self.layout.operator("remove.pano", icon="ERROR", text='Remove the Pano')
        
        

        row = layout.row()
        row = layout.row()
        self.layout.operator("align.quad", icon="OUTLINER_OB_FORCE_FIELD", text='Align quad')
        row = layout.row()
        
        split = layout.split()
        # First column
        col = split.column()
        col.label(text="Lens:")
        col.prop(context.scene, 'PANO_cam_lens', toggle = True)
#        col.prop(scene, "frame_start")

        # Second column, aligned
        col = split.column(align=True)
        col.label(text="Apply")
        col.operator("set.lens", icon="FILE_TICK", text='SL')
#        col.prop(scene, "frame_start")

class VIEW3D_PT_SetupPanel(Panel, PANOToolsPanel):
    bl_category = "3DSC"
    bl_idname = "VIEW3D_PT_SetupPanel"
    bl_context = "objectmode"

class REMOVE_pano(bpy.types.Operator):
    bl_idname = "remove.pano"
    bl_label = "Remove selected Pano"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        data = bpy.data
        context = bpy.context
        scene = context.scene
        ob_pano = data.objects[scene.pano_list[scene.pano_list_index].name]
        cam_pano = data.objects['CAM_'+scene.pano_list[scene.pano_list_index].name]
        data.objects.remove(ob_pano)
        data.objects.remove(cam_pano)
        scene.pano_list.remove(scene.pano_list_index)
        scene.pano_list_index = scene.pano_list_index - 1
        return {'FINISHED'}

class VIEW_pano(bpy.types.Operator):
    bl_idname = "view.pano"
    bl_label = "View from the inside of selected Pano"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        data = bpy.data
        context = bpy.context
        scene = context.scene
        pano_list_index = scene.pano_list_index
        current_camera_name = 'CAM_'+scene.pano_list[pano_list_index].name
        current_camera_obj = data.objects[current_camera_name]
        scene.camera = current_camera_obj
        area = next(area for area in bpy.context.screen.areas if area.type == 'VIEW_3D')
        area.spaces[0].region_3d.view_perspective = 'CAMERA'
        current_pano = data.objects[scene.pano_list[pano_list_index].name]
        context.view_layer.objects.active = current_pano
        bpy.ops.object.select_all(action='DESELECT')
#        current_pano.select = True
        return {'FINISHED'}


class VIEW_alignquad(bpy.types.Operator):
    bl_idname = "align.quad"
    bl_label = "align the quad inside the active Pano"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        data = bpy.data
        context = bpy.context
        scene = context.scene
        pano_list_index = scene.pano_list_index
        current_camera_name = 'CAM_'+scene.pano_list[pano_list_index].name
        current_camera_obj = data.objects[current_camera_name]
#        scene.camera = current_camera_obj
        current_pano = data.objects[scene.pano_list[pano_list_index].name]
        object = context.active_object


#        area = next(area for area in bpy.context.screen.areas if area.type == 'VIEW_3D')
#        area.spaces[0].region_3d.view_perspective = 'CAMERA'
#
#        scene.objects.active = current_pano
#        bpy.ops.object.select_all(action='DESELECT')
#        current_pano.select = True
        set_rotation_to_bubble(context,object,current_camera_obj)

        return {'FINISHED'}


class VIEW_setlens(bpy.types.Operator):
    bl_idname = "set.lens"
    bl_label = "set the lens of the camera"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        data = bpy.data
        context = bpy.context
        scene = context.scene
        pano_list_index = scene.pano_list_index
        current_camera_name = 'CAM_'+scene.pano_list[pano_list_index].name
        
         
        current_camera_obj = data.objects[current_camera_name]
        current_camera_obj.data.lens = scene.PANO_cam_lens
#        scene.camera = current_camera_obj
#        current_pano = data.objects[scene.pano_list[pano_list_index].name]
#        object = context.active_object


#        area = next(area for area in bpy.context.screen.areas if area.type == 'VIEW_3D')
#        area.spaces[0].region_3d.view_perspective = 'CAMERA'
#
#        scene.objects.active = current_pano
#        bpy.ops.object.select_all(action='DESELECT')
#        current_pano.select = True
#        set_rotation_to_bubble(context,object,current_camera_obj)

        return {'FINISHED'}





class PANO_import(bpy.types.Operator):
    bl_idname = "import.pano"
    bl_label = "Import Panoramas from file"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        data = bpy.data
        context = bpy.context
        scene = context.scene
        lines_in_file = readfile(scene.PANO_file)
        PANO_list_clear(context)
        pano_list_index_counter = 0

        # Parse the array:
        for p in lines_in_file:
#            p0 = p.split('\t')  # use space as separator
            p0 = p.split(' ')  # use space as separator
            print(p0[0])
            ItemName = p0[0]
            pos_x = float(p0[1])
            pos_y = float(p0[2])
            pos_z = (float(p0[3]))
            rot_x = float(p0[4])
            rot_y = float(p0[5])
            rot_z = float(p0[6])
            for model in data.objects:
                if model.name == remove_extension(ItemName) or model.name == "CAM_"+remove_extension(ItemName):
                    data.objects.remove(model)
            sph = bpy.ops.mesh.primitive_uv_sphere_add(calc_uvs=True, radius=0.2, location=(pos_x,pos_y,pos_z))
            just_created_obj = context.active_object
            just_created_obj.name = remove_extension(ItemName)
            
            just_created_obj.rotation_euler[0] = e2d(rot_x-90.0)
            bpy.ops.object.transform_apply(rotation = True, location = False)

            just_created_obj.rotation_euler[2] = (e2d(rot_y+90.0))*-1
            bpy.ops.object.transform_apply(rotation = True, location = False)

            just_created_obj.rotation_euler[1] = e2d(rot_z)
            bpy.ops.object.transform_apply(rotation = True, location = False)



            uvMapName = 'UVMap'
            obj, uvMap = GetObjectAndUVMap( just_created_obj.name, uvMapName )
            scale = Vector( (-1, 1) )
            pivot = Vector( (0.5, 0.5) )
            ScaleUV( uvMap, scale, pivot )
            
            diffTex, img = create_tex_from_file(ItemName,scene.PANO_dir)
            mat = create_mat(just_created_obj)
            setup_mat_panorama_3DSC(mat.name, img)

            
            #newmat, texImage, bsdf = create_material_from_image(context,img,just_created_obj,True)
            
            #assign_tex2mat(diffTex,newmat)
            scene.pano_list.add()
            scene.pano_list[pano_list_index_counter].name = just_created_obj.name
#            scene.pano_list[pano_list_index_counter].icon = qui possiamo mettere una regola
            flipnormals()
            create_cam(just_created_obj.name,pos_x,pos_y,pos_z)
            pano_list_index_counter += 1
        #scene.update()
        return {'FINISHED'}