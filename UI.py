import bpy

from bpy.types import Panel
from bpy.types import Operator
from bpy.types import PropertyGroup


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

        row = layout.row()
        self.layout.operator("import_scene.multiple_objs", icon="WORLD_DATA", text='Import multiple objs')
        row = layout.row()
        self.layout.operator("import_points.txt", icon="WORLD_DATA", text='Import txt points')

class ToolsPanelExport:
    bl_label = "Exporters"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'

    def draw(self, context):
        layout = self.layout
        obj = context.object
        row = layout.row()
        if obj is not None:
            self.layout.operator("export.coordname", icon="WORLD_DATA", text='Coordinates')
            row = layout.row()
            row.label(text="Active object is: " + obj.name)
            row = layout.row()
            row.label(text="Override")
            row = layout.row()
            row.prop(obj, "name")
            row = layout.row()
            self.layout.operator("export.object", icon="OBJECT_DATA", text='Exp. one obj')
            row = layout.row()
            row.label(text="Resulting file: " + obj.name + ".obj")
            row = layout.row()
            self.layout.operator("obj.exportbatch", icon="OBJECT_DATA", text='Exp. several obj')
            row = layout.row()
            self.layout.operator("fbx.exportbatch", icon="OBJECT_DATA", text='Exp. several fbx UE4')
            row = layout.row()
            self.layout.operator("fbx.exp", icon="OBJECT_DATA", text='Exp. fbx UE4')
            row = layout.row()
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
        row = layout.row()

        scn = context.scene

        self.layout.operator("lod0.creation", icon="MESH_UVSPHERE", text='LOD 0 (set as)')
        row = layout.row()

        layout.prop(scn, 'LODnum', icon='BLENDER', toggle=True)

        self.layout.operator("lod.creation", icon="MESH_UVSPHERE", text='LOD generation')
        row = layout.row()

        #row = layout.row()
        row.label(text="Select LOD0 objs")
        
        row = layout.row()
        if obj:
            row.label(text="Resulting files: ")
            row = layout.row()
            row.label(text= "LOD1/LOD2_"+ obj.name + ".obj" )
            row = layout.row()
        self.layout.operator("create.grouplod", icon="QUESTION", text='Create LOD cluster(s)')
        row = layout.row()
        self.layout.operator("remove.grouplod", icon="CANCEL", text='Remove LOD cluster(s)')
        row = layout.row()
        self.layout.operator("exportfbx.grouplod", icon="MESH_GRID", text='FBX Export LOD cluster(s)')
        row = layout.row()


class ToolsPanel_ccTool:
    bl_label = "Color Correction tool (cycles)"
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
            if scene.objects.active:
                if obj.type not in ['MESH']:
                    select_a_mesh(layout)
                else:    
                    row.label(text="Step by step procedure")
                    row = layout.row()
                    row.label(text="for selected object(s):")
                    self.layout.operator("bi2cycles.material", icon="SMOOTH", text='Create cycles nodes')
                    self.layout.operator("create.ccnode", icon="ASSET_MANAGER", text='Create correction node')
                    
                    activeobj = scene.objects.active
                    if get_nodegroupname_from_obj(obj) is not None:
#                    layout = self.layout
                        row = self.layout.row()
                        row.prop(context.window_manager.interface_vars, 'cc_nodes', expand=True)
                        nodegroupname = get_nodegroupname_from_obj(obj)
                        node_to_visualize = context.window_manager.interface_vars.cc_nodes
                        if node_to_visualize == 'RGB':
                            node = get_cc_node_in_obj_mat(nodegroupname, "RGB")
                        if node_to_visualize == 'BC':
                            node = get_cc_node_in_obj_mat(nodegroupname, "BC")
                        if node_to_visualize == 'HS':
                            node = get_cc_node_in_obj_mat(nodegroupname, "HS")               
                        row = layout.row()
                        row.label(text="Active cc node: "+node_to_visualize)# + nodegroupname)
                        row = layout.row()
                        row.label(text=nodegroupname)
                        # set "node" context pointer for the panel layout
                        layout.context_pointer_set("node", node)

                        if hasattr(node, "draw_buttons_ext"):
                            node.draw_buttons_ext(context, layout)
                        elif hasattr(node, "draw_buttons"):
                            node.draw_buttons(context, layout)

                        # XXX this could be filtered further to exclude socket types which don't have meaningful input values (e.g. cycles shader)
#                        value_inputs = [socket for socket in node.inputs if socket.enabled and not socket.is_linked]
#                        if value_inputs:
#                            layout.separator()
#                            layout.label("Inputs:")
#                            for socket in value_inputs:
#                                row = layout.row()
#                                socket.draw(context, row, node, iface_(socket.name, socket.bl_rna.translation_context))                    
#                    
                    
                    self.layout.operator("create.newset", icon="FILE_TICK", text='Create new texture set')
                    row = layout.row()
                    self.layout.operator("bake.cyclesdiffuse", icon="TPAINT_HLT", text='Bake CC to texture set')
                    row = layout.row()
                    self.layout.operator("savepaint.cam", icon="IMAGE_COL", text='Save new textures')
                    self.layout.operator("applynewtexset.material", icon="AUTOMERGE_ON", text='Use new tex set')
                    self.layout.operator("applyoritexset.material", icon="RECOVER_LAST", text='Use original tex set')
                    
                    self.layout.operator("removeccnode.material", icon="CANCEL", text='remove cc node')
                    self.layout.operator("removeorimage.material", icon="CANCEL", text='remove ori image')
                    row = layout.row() 
            else:
                select_a_mesh(layout)


class ToolsPanelPhotogrTool:
    bl_label = "Photogrammetry tool"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        layout = self.layout
        scene = context.scene
        cam_ob = None
        cam_ob = scene.camera

        if scene.render.engine != 'BLENDER_RENDER':
            row = layout.row()
            row.label(text="Please, activate BI engine !")
        elif cam_ob is None:
            row = layout.row()
            row.label(text="Please, add a Cam to see tools here")
            
        else:
            obj = context.object
            obj_selected = scene.objects.active
            cam_cam = scene.camera.data
            row = layout.row()
            row.label(text="Set up scene", icon='RADIO')
            row = layout.row()
            self.layout.operator("isometric.scene", icon="RENDER_REGION", text='Isometric scene')
            self.layout.operator("canon6d.scene", icon="RENDER_REGION", text='CANON 6D scene')
            self.layout.operator("nikond3200.scene", icon="RENDER_REGION", text='NIKON D3200 scene')
            if scene.objects.active:
                if obj.type in ['MESH']:
                    pass
                elif obj.type in ['CAMERA']:
                    row = layout.row()
                    row.label(text="Set selected cams as:", icon='RENDER_STILL')
                    self.layout.operator("nikond320018mm.camera", icon="RENDER_REGION", text='Nikon d3200 18mm')
                    self.layout.operator("canon6d35mm.camera", icon="RENDER_REGION", text='Canon6D 35mm')
                    self.layout.operator("canon6d24mm.camera", icon="RENDER_REGION", text='Canon6D 24mm')
                    self.layout.operator("canon6d14mm.camera", icon="RENDER_REGION", text='Canon6D 14mm')
                    row = layout.row()
                    row.label(text="Visual mode for selected cams:", icon='NODE_SEL')
                    self.layout.operator("better.cameras", icon="NODE_SEL", text='Better Cams')
                    self.layout.operator("nobetter.cameras", icon="NODE_SEL", text='Disable Better Cams')
                    row = layout.row()
                    row = layout.row()
                else:
                    row = layout.row()
                    row.label(text="Please select a mesh or a cam", icon='OUTLINER_DATA_CAMERA')
 
            row = layout.row()
            row.label(text="Painting Toolbox", icon='TPAINT_HLT')
            row = layout.row()
            row.label(text="Folder with undistorted images:")
            row = layout.row()
            row.prop(context.scene, 'BL_undistorted_path', toggle = True)
            row = layout.row()

            if cam_ob is not None:
                row.label(text="Active Cam: " + cam_ob.name)
                self.layout.operator("object.createcameraimageplane", icon="IMAGE_COL", text='Photo to camera')
                row = layout.row()
                row = layout.row()
                row.prop(cam_cam, "lens")
                row = layout.row()
                is_cam_ob_plane = check_children_plane(cam_ob)
#                row.label(text=str(is_cam_ob_plane))
                if is_cam_ob_plane:
                    if obj.type in ['MESH']:
                        row.label(text="Active object: " + obj.name)
                        self.layout.operator("paint.cam", icon="IMAGE_COL", text='Paint active from cam')
                else:
                    row = layout.row()
                    row.label(text="Please, set a photo to camera", icon='TPAINT_HLT')
                
                self.layout.operator("applypaint.cam", icon="IMAGE_COL", text='Apply paint')
                self.layout.operator("savepaint.cam", icon="IMAGE_COL", text='Save modified texs')
                row = layout.row()
            else:
                row.label(text="!!! Import some cams to start !!!")


class ToolsPanelTexPatcher:
    bl_label = "Texture patcher (Cycles)"
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