import bpy
import os
import time
from .functions import *

import nodeitems_utils
from bpy.types import Header, Menu, Panel


class OBJECT_OT_removeccnode(bpy.types.Operator):
    """Remove cc node for selected objects"""
    bl_idname = "removeccnode.material"
    bl_label = "Remove  cycles cc node for selected object"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        for obj in bpy.context.selected_objects:
            for matslot in obj.material_slots:
                mat = matslot.material
                remove_node(mat, "cc_node")
        return {'FINISHED'}
    
class OBJECT_OT_removeorimage(bpy.types.Operator):
    """Remove oiginal image for selected objects"""
    bl_idname = "removeorimage.material"
    bl_label = "Remove oiginal image for selected objects"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        for obj in bpy.context.selected_objects:
            for matslot in obj.material_slots:
                mat = matslot.material
                remove_ori_image(mat)
        return {'FINISHED'}


class OBJECT_OT_createccnode(bpy.types.Operator):
    """Create a color correction node for selected objects"""
    bl_idname = "create.ccnode"
    bl_label = "Create cycles materials for selected object"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):

        bpy.context.scene.render.engine = 'CYCLES'
        active_object_name = context.active_object.name
        cc_nodegroup = create_correction_nodegroup(active_object_name)
        for obj in bpy.context.selected_objects:
            for matslot in obj.material_slots:
                mat = matslot.material
                cc_node_to_mat(mat,cc_nodegroup)

        return {'FINISHED'}

#-------------------------------------------------------------

class OBJECT_OT_createnewset(bpy.types.Operator):
    """Create new texture set for corrected mats"""
    bl_idname = "create.newset"
    bl_label = "Create new texture set for corrected mats (cc_ + previous tex name)"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        bpy.context.scene.render.engine = 'CYCLES'
        for obj in bpy.context.selected_objects:
            for matslot in obj.material_slots:
                mat = matslot.material
                create_new_tex_set(mat,"cc_image")
        return {'FINISHED'}

#-------------------------------------------------------------


class OBJECT_OT_bakecyclesdiffuse(bpy.types.Operator):
    """Color correction to new texture set"""
    bl_idname = "bake.cyclesdiffuse"
    bl_label = "Transfer new color correction to a new texture set"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        bake_tex_set("cc")
        
        return {'FINISHED'}

####-----------------------------------------------------------


class OBJECT_OT_applyoritexset(bpy.types.Operator):
    """Use original textures in mats"""
    bl_idname = "applyoritexset.material"
    bl_label = "Use original textures in mats"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):

        bpy.context.scene.render.engine = 'CYCLES'

        for obj in bpy.context.selected_objects:
            for matslot in obj.material_slots:
                mat = matslot.material
                set_texset(mat, "original")
                
        return {'FINISHED'}
    
class OBJECT_OT_applynewtexset(bpy.types.Operator):
    """Use new textures in mats"""
    bl_idname = "applynewtexset.material"
    bl_label = "Use new textures in mats"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):

        bpy.context.scene.render.engine = 'CYCLES'

        for obj in bpy.context.selected_objects:
            for matslot in obj.material_slots:
                mat = matslot.material
                set_texset(mat, "cc_image")
                
        return {'FINISHED'}