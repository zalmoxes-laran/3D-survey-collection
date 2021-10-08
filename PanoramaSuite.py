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

import json
import os
import shutil

def panolistitem_to_obj(item_in_list):
    obj = bpy.data.objects[item_in_list.name]
    return obj

def export_panoscene(scene, export_folder, EMviq, nodes, format_file, edges):
    #EM_list_clear(bpy.context, "emviq_error_list")
    edges["."] = []
    for pano in scene.pano_list:
        exec(pano.name+'_node = {}')
        exec(panolistitem_to_obj(pano).location[0])
        exec("nodes['"+pano.name+"'] = "+ pano.name + '_node')
        pano.name
 
        if len(ob.EM_ep_belong_ob) >= 2:
            for ob_tagged in ob.EM_ep_belong_ob:
                for epoch in scene.epoch_list:
                    if ob_tagged.epoch == epoch.name:
                        epochname1_var = epoch.name.replace(" ", "_")
                        epochname_var = epochname1_var.replace(".", "")

                        if EMviq:
                            try:
                                exec(epochname_var+'_node')
                            except NameError:
                                print("well, it WASN'T defined after all!")
                                exec(epochname_var + '_node' + ' = {}')
                                exec(epochname_var + '_urls = []')
                                exec(epochname_var + "_node['urls'] = "+ epochname_var +"_urls")
                                exec("nodes['"+epoch.name+"'] = "+ epochname_var + '_node')

                                edges["."].append(epoch.name)

                            else:
                                print("sure, it was defined.")

                            exec(epochname_var + '_urls.append("'+utente_aton+'/models/'+progetto_aton+'/shared/'+ ob.name + '.gltf")')

                        ob.select_set(False)
    return nodes, edges

def json_writer(base_dir):
    
    pano_scene = {}
    scenegraph = {}
    nodes = {}
    edges = {}
    
    pano_scene['scenegraph'] = scenegraph
    nodes, edges = export_panoscene(scene, base_dir, True, nodes, self.em_export_format, edges)

    scenegraph['nodes'] = nodes

    # encode dict as JSON 
    data = json.dumps(pano_scene, indent=4, ensure_ascii=True)

    #'/users/emanueldemetrescu/Desktop/'
    file_name = os.path.join(base_dir, "config.json")

    # write JSON file
    with open(file_name, 'w') as outfile:
        outfile.write(data + '\n')

    em_file_4_emviq = os.path.join(export_folder, "em.graphml")

    em_file_fixed_path = bpy.path.abspath(scene.EM_file)
    shutil.copyfile(em_file_fixed_path, em_file_4_emviq)


    return


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
            #p0 = p.split('\t')  # use space as separator
            p0 = p.split(' ')  # use space as separator
            print(p0[0])
            ItemName = p0[0]
            pos_x = float(p0[1])-scene.BL_x_shift
            pos_y = float(p0[2])-scene.BL_y_shift
            pos_z = (float(p0[3]))-scene.BL_z_shift
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

            #print(f"Il panorama {just_created_obj.name} ha rotazione z: {e2d(180.0+phi)}")
            #just_created_obj.rotation_euler[0] = e2d(-(omega-90.0))
            #just_created_obj.rotation_euler[1] = e2d(kappa)
            #just_created_obj.rotation_euler[2] = e2d(180.0+phi)

            if omega>0:
                just_created_obj.rotation_euler[1] = e2d((omega-90.0))
            else:
                just_created_obj.rotation_euler[1] = e2d(-(omega-90.0))
            just_created_obj.rotation_euler[0] = e2d(-kappa)
            if omega>0:
                just_created_obj.rotation_euler[2] = e2d(180.0+phi)
            else:
                just_created_obj.rotation_euler[2] = e2d(180-phi)

            uvMapName = 'UVMap'
            obj, uvMap = GetObjectAndUVMap( just_created_obj.name, uvMapName )
            scale = Vector( (-1, 1) )
            pivot = Vector( (0.5, 0.5) )
            ScaleUV( uvMap, scale, pivot )

            #ItemName_res = (remove_extension(ItemName)+"-"+str(scene.RES_pano)+"k.jpg")
            ItemName_res = (remove_extension(ItemName)+".jpg")
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

class ubermat_create(bpy.types.Operator):
    bl_idname = "ubermat_create.pano"
    bl_label = "Create ubermaterial from panoramas"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):

        create_pano_ubermat(True)

        return {'FINISHED'}

class ubermat_update(bpy.types.Operator):
    bl_idname = "ubermat_update.pano"
    bl_label = "Update ubermaterial from panoramas"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):

        create_pano_ubermat(False)
        
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
        #scene.camera = current_camera_obj
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


class SETpanoRES(bpy.types.Operator):
    bl_idname = "set.panores"
    bl_label = "set the res of the panorama"
    bl_options = {"REGISTER", "UNDO"}

    res_number : StringProperty()

    def execute(self, context):
        scene = bpy.context.scene
        active_obj = bpy.context.active_object
        if active_obj.material_slots[0].material.name.endswith('uvuberpano'):
            mat = active_obj.material_slots[0].material
            nodes = mat.node_tree.nodes
            for node in nodes:
                if node.name.startswith('tn_'):
                    nodename = node.name[3:]
                    print(nodename)
                    current_panores_foldername = str(self.res_number)+"k"
                    ItemName_res = (nodename+"-"+str(self.res_number)+"k.jpg")
                    minimum_sChildPath = os.path.join(scene.PANO_dir,current_panores_foldername,ItemName_res)
                    print(minimum_sChildPath)
                    node.image.filepath = minimum_sChildPath
        return {'FINISHED'}