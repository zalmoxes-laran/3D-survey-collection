import bpy
import mathutils

from bpy.types import Panel
from bpy.types import Operator
from bpy.types import PropertyGroup

from .functions import *

import os
from bpy_extras.io_utils import ImportHelper, axis_conversion

from bpy.props import (BoolProperty,
                       FloatProperty,
                       StringProperty,
                       EnumProperty,
                       CollectionProperty
                       )

class PANO_import(bpy.types.Operator):
    bl_idname = "import.pano"
    bl_label = "Import Panoramas from file"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        data = bpy.data
        context = bpy.context
        scene = context.scene
        #minimum_sChildPath, folder_list = read_pano_dir(context)
        read_pano_dir(context)
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
            omega = float(p0[4])
            phi = float(p0[5])
            kappa = float(p0[6])

            for model in data.objects:
                if model.name == remove_extension(ItemName) or model.name == "CAM_"+remove_extension(ItemName):
                    data.objects.remove(model)
            sph = bpy.ops.mesh.primitive_uv_sphere_add(calc_uvs=True, radius=0.2, location=(pos_x,pos_y,pos_z))
            just_created_obj = context.active_object
            just_created_obj.name = remove_extension(ItemName)
            just_created_obj.rotation_euler[2] = e2d(-90.0)
            bpy.ops.object.transform_apply(rotation = True, location = False)
            
            just_created_obj.rotation_euler[0] = e2d(-(omega-90.0))
            just_created_obj.rotation_euler[1] = e2d(kappa)
            just_created_obj.rotation_euler[2] = e2d(180.0+phi)

            uvMapName = 'UVMap'
            obj, uvMap = GetObjectAndUVMap( just_created_obj.name, uvMapName )
            scale = Vector( (-1, 1) )
            pivot = Vector( (0.5, 0.5) )
            ScaleUV( uvMap, scale, pivot )

            ItemName_res = (remove_extension(ItemName)+"-"+str(scene.RES_pano)+"k.jpg")
            current_panores_foldername = str(scene.RES_pano)+"k"
            
            minimum_sChildPath = os.path.join(scene.PANO_dir,current_panores_foldername)

            diffTex, img = create_tex_from_file(ItemName_res,minimum_sChildPath)
            mat = create_mat(just_created_obj)
            setup_mat_panorama_3DSC(mat.name, img)
           
            scene.pano_list.add()
            scene.pano_list[pano_list_index_counter].name = just_created_obj.name
            
            flipnormals()
            create_cam(just_created_obj.name,pos_x,pos_y,pos_z)
            pano_list_index_counter += 1
        #scene.update()
        return {'FINISHED'}

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