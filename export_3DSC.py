import bpy
import os
from .functions import *

import bpy
import math

from bpy_extras.io_utils import ExportHelper
from bpy.props import StringProperty, BoolProperty, EnumProperty
from bpy.types import Operator

def check_if_scalable(image_block):
    is_scalable = False
    if image_block.size[0] > bpy.context.scene.gltf_export_maxres and image_block.size[1] > bpy.context.scene.gltf_export_maxres:
        is_scalable =True
    if bpy.context.scene.gltf_export_quality < 100:
        is_scalable =True
    return is_scalable

def image_compression(dir_path):
    # create new image or just find your image in bpy.data
    scene = bpy.context.scene
    temp_image_format = scene.render.image_settings.file_format
    temp_image_quality = scene.render.image_settings.quality
    scene.render.image_settings.file_format = 'JPEG'
    scene.render.image_settings.quality = scene.gltf_export_quality
    for entry in os.listdir(dir_path):
        if os.path.isfile(os.path.join(dir_path, entry)):
            if entry.lower().endswith('.jpg') or entry.lower().endswith('.png'):
                print(f'inizio a comprimere {entry}')
                image_file_path = bpy.path.abspath(os.path.join(dir_path, entry))
                image_dblock = bpy.data.images.load(image_file_path)
                print(f"l'immagine importata ha lato {str(image_dblock.size[0])}")
                if check_if_scalable(image_dblock):
                    
                    image_dblock.scale(scene.gltf_export_maxres,scene.gltf_export_maxres)
                    print(f"l'immagine importata ha ora lato {str(image_dblock.size[0])}")
                    print(f"ho compresso {image_dblock.name} con path {image_dblock.filepath}")
                    #image_dblock.filepath = image_file_path
                    image_dblock.update()

                    image_dblock.save_render(image_file_path,scene= bpy.context.scene)

    scene.render.image_settings.file_format = temp_image_format 
    scene.render.image_settings.quality = temp_image_quality 
    return 


############## from here operators to export text ########################


class OBJECT_OT_ExportButtonName(bpy.types.Operator):
    bl_idname = "export.coordname"
    bl_label = "Export coord name"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):

        bpy.ops.export_test.some_data('INVOKE_DEFAULT')
            
        return {'FINISHED'}

def write_some_data(context, filepath, shift, rot, cam, nam):
    print("running write some data...")
    
    selection = bpy.context.selected_objects
    bpy.ops.object.select_all(action='DESELECT')


    f = open(filepath, 'w', encoding='utf-8')
        
    #file = open(fn + ".txt", 'w')

    # write selected objects coordinate
    for obj in selection:
        obj.select_set(True)

        x_coor = obj.location[0]
        y_coor = obj.location[1]
        z_coor = obj.location[2]
        
        if rot == True or cam == True:
            rotation_grad_x = math.degrees(obj.rotation_euler[0])
            rotation_grad_y = math.degrees(obj.rotation_euler[1])
            rotation_grad_z = math.degrees(obj.rotation_euler[2])

        if shift == True:
            shift_x = context.scene.BL_x_shift
            shift_y = context.scene.BL_y_shift
            shift_z = context.scene.BL_z_shift
            x_coor = x_coor+shift_x
            y_coor = y_coor+shift_y
            z_coor = z_coor+shift_z

        # Generate UV sphere at x = lon and y = lat (and z = 0 )

        if rot == True:
            if nam == True:
                f.write("%s %s %s %s %s %s %s\n" % (obj.name, x_coor, y_coor, z_coor, rotation_grad_x, rotation_grad_y, rotation_grad_z))
            else:    
                f.write("%s %s %s %s %s %s\n" % (x_coor, y_coor, z_coor, rotation_grad_x, rotation_grad_y, rotation_grad_z))
        if cam == True:
            if obj.type == 'CAMERA':
                f.write("%s %s %s %s %s %s %s %s\n" % (obj.name, x_coor, y_coor, z_coor, rotation_grad_x, rotation_grad_y, rotation_grad_z, obj.data.lens))        
        if rot == False and cam == False:
            if nam == True:
                f.write("%s %s %s %s\n" % (obj.name, x_coor, y_coor, z_coor))
            else:
                f.write("%s %s %s\n" % (x_coor, y_coor, z_coor))
        
    f.close()    
    

    return {'FINISHED'}

class ExportCoordinates(Operator, ExportHelper):
    """This appears in the tooltip of the operator and in the generated docs"""
    bl_idname = "export_test.some_data"  # important since its how bpy.ops.import_test.some_data is constructed
    bl_label = "Export Coordinate Data"

    # ExportHelper mixin class uses this
    filename_ext = ".txt"

    filter_glob: StringProperty(
            default="*.txt",
            options={'HIDDEN'},
            maxlen=255,  # Max internal buffer length, longer would be clamped.
            )

    # List of operator properties, the attributes will be assigned
    # to the class instance from the operator settings before calling.

    nam: BoolProperty(
            name="Add names of objects",
            description="This tool includes name",
            default=True,
            )

    rot: BoolProperty(
            name="Add coordinates of rotation",
            description="This tool includes name, position and rotation",
            default=False,
            )

    cam: BoolProperty(
            name="Export only cams",
            description="This tool includes name, position, rotation and focal lenght",
            default=False,
            )

    shift: BoolProperty(
            name="World shift coordinates",
            description="Shift coordinates using the General Shift Value (GSV)",
            default=False,
            )

    def execute(self, context):
        return write_some_data(context, self.filepath, self.shift, self.rot, self.cam, self.nam)

# Only needed if you want to add into a dynamic menu
def menu_func_export(self, context):
    self.layout.operator(ExportCoordinates.bl_idname, text="Text Export Operator")

############## from here operators to export geometry ########################

class OBJECT_OT_ExportObjButton(bpy.types.Operator):
    bl_idname = "export.object"
    bl_label = "Export object"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):

        basedir = os.path.dirname(bpy.data.filepath)

        if not basedir:
            raise Exception("Save the blend file")

        activename = bpy.path.clean_name(bpy.context.active_object.name)
        fn = os.path.join(basedir, activename)

        if context.scene.SHIFT_OBJ_on:
                x_shift = context.scene.BL_x_shift
                y_shift = context.scene.BL_y_shift
                z_shift = context.scene.BL_z_shift
        else:
                x_shift = 0.0
                y_shift = 0.0
                z_shift = 0.0  

        # write active object in obj format
        bpy.ops.export_scene.obj(filepath=fn + ".obj", use_selection=True, axis_forward='Y', axis_up='Z', path_mode='RELATIVE', global_shift_x = x_shift, global_shift_y = y_shift, global_shift_z = z_shift)
        return {'FINISHED'}

class OBJECT_OT_gltfexportbatch(bpy.types.Operator):
    bl_idname = "gltf.exportbatch"
    bl_label = "Gltf export batch"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):

        #basedir = 'F:\LOD1'
        copyright = context.scene.author_sign_model #"CC-BY-NC E.Demetrescu"
        draco_compression = 6

        if bpy.context.scene.FBX_export_dir:
            basedir = os.path.dirname(bpy.context.scene.FBX_export_dir)
            #subfolder = ''
        else:
            basedir = os.path.dirname(bpy.data.filepath)
            #subfolder = 'FBX'

        if not basedir:
            raise Exception("Blend file is not saved")

        selection = bpy.context.selected_objects
        bpy.ops.object.select_all(action='DESELECT')

        for obj in selection:
            obj.select_set(True)
            name = bpy.path.clean_name(obj.name)
            namefile = name + ".gltf"
            file_path = os.path.join(basedir, namefile)
            bpy.ops.export_scene.gltf(export_format='GLTF_SEPARATE', ui_tab='GENERAL', export_copyright=copyright, export_image_format='AUTO', export_texture_dir='', export_texcoords=True, export_normals=True, export_draco_mesh_compression_enable=True, export_draco_mesh_compression_level=draco_compression, export_draco_position_quantization=14, export_draco_normal_quantization=10, export_draco_texcoord_quantization=12, export_draco_generic_quantization=12, export_tangents=False, export_materials='EXPORT', export_colors=False, export_cameras=False, use_selection=True, export_extras=False, export_yup=True, export_apply=True, export_animations=False, export_frame_range=False, export_frame_step=1, export_force_sampling=False, export_nla_strips=False, export_def_bones=False, export_current_frame=False, export_skins=False, export_all_influences=False, export_morph=True, export_morph_normal=False, export_morph_tangent=False, export_lights=False, export_displacement=False, will_save_settings=False, filepath=file_path, check_existing=False)#, filter_glob='*.glb;*.gltf')
            obj.select_set(False)
        
        image_compression(basedir)

        return {'FINISHED'}

class OBJECT_OT_glbexportbatch(bpy.types.Operator):
    bl_idname = "glb.exportbatch"
    bl_label = "Glb export batch"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):

        #basedir = 'F:\LOD1'
        copyright = context.scene.author_sign_model #"CC-BY-NC E.Demetrescu"
        draco_compression = 6


        if bpy.context.scene.FBX_export_dir:
            basedir = os.path.dirname(bpy.context.scene.FBX_export_dir)
            #subfolder = ''
        else:
            basedir = os.path.dirname(bpy.data.filepath)
            #subfolder = 'FBX'

        if not basedir:
            raise Exception("Blend file is not saved")

        selection = bpy.context.selected_objects
        bpy.ops.object.select_all(action='DESELECT')

        for obj in selection:
            obj.select_set(True)
            name = bpy.path.clean_name(obj.name)
            namefile = name + ".glb"
            file_path = os.path.join(basedir, namefile)
            bpy.ops.export_scene.gltf(export_format='GLB', ui_tab='GENERAL', export_copyright=copyright, export_image_format='AUTO', export_texture_dir='', export_texcoords=True, export_normals=True, export_draco_mesh_compression_enable=False, export_draco_mesh_compression_level=draco_compression, export_draco_position_quantization=14, export_draco_normal_quantization=10, export_draco_texcoord_quantization=12, export_draco_generic_quantization=12, export_tangents=False, export_materials='EXPORT', export_colors=False, export_cameras=False, use_selection=True, export_extras=False, export_yup=True, export_apply=True, export_animations=True, export_frame_range=False, export_frame_step=1, export_force_sampling=False, export_nla_strips=False, export_def_bones=False, export_current_frame=False, export_skins=False, export_all_influences=False, export_morph=True, export_morph_normal=False, export_morph_tangent=False, export_lights=False, export_displacement=False, will_save_settings=False, filepath=file_path, check_existing=False)#, filter_glob='*.glb;*.gltf')
            obj.select_set(False)
        return {'FINISHED'}

class OBJECT_OT_objexportbatch(bpy.types.Operator):
    bl_idname = "obj.exportbatch"
    bl_label = "Obj export batch"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):

        if bpy.context.scene.FBX_export_dir:
            basedir = os.path.dirname(bpy.context.scene.FBX_export_dir)
            #subfolder = ''
        else:
            basedir = os.path.dirname(bpy.data.filepath)
            #subfolder = 'FBX'

        if not basedir:
            raise Exception("Blend file is not saved")

        if context.scene.SHIFT_OBJ_on:
                x_shift = context.scene.BL_x_shift
                y_shift = context.scene.BL_y_shift
                z_shift = context.scene.BL_z_shift
        else:
                x_shift = 0.0
                y_shift = 0.0
                z_shift = 0.0    

        selection = bpy.context.selected_objects
        bpy.ops.object.select_all(action='DESELECT')

        for obj in selection:
            obj.select_set(True)
            name = bpy.path.clean_name(obj.name)
            fn = os.path.join(basedir, name)
            bpy.ops.export_scene.obj(filepath=str(fn + '.obj'), use_selection=True, axis_forward='Y', axis_up='Z', path_mode='RELATIVE', global_shift_x = x_shift, global_shift_y = y_shift, global_shift_z = z_shift)
            obj.select_set(False)
        return {'FINISHED'}

#_______________________________________________________________________________________________________________

class OBJECT_OT_fbxexp(bpy.types.Operator):
    bl_idname = "fbx.exp"
    bl_label = "Fbx export UE4"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        basedir = os.path.dirname(bpy.data.filepath)
        subfolder = 'FBX'
        if not os.path.exists(os.path.join(basedir, subfolder)):
            os.mkdir(os.path.join(basedir, subfolder))
            print('There is no FBX folder. Creating one...')
        else:
            print('Found previously created FBX folder. I will use it')
        if not basedir:
            raise Exception("Save the blend file")
        obj = bpy.context.active_object
        name = bpy.path.clean_name(obj.name)
        fn = os.path.join(basedir, subfolder, name)
        bpy.ops.export_scene.fbx(filepath = fn + ".fbx", check_existing=True, filter_glob="*.fbx", use_selection=True, use_active_collection=False, global_scale=1.0, apply_unit_scale=True, apply_scale_options='FBX_SCALE_NONE', bake_space_transform=False, object_types={'MESH'}, use_mesh_modifiers=True, use_mesh_modifiers_render=True, mesh_smooth_type='OFF', use_mesh_edges=False, use_tspace=False, use_custom_props=False, add_leaf_bones=True, primary_bone_axis='Y', secondary_bone_axis='X', use_armature_deform_only=False, armature_nodetype='NULL', bake_anim=False, bake_anim_use_all_bones=True, bake_anim_use_nla_strips=True, bake_anim_use_all_actions=True, bake_anim_force_startend_keying=True, bake_anim_step=1.0, bake_anim_simplify_factor=1.0, path_mode='AUTO', embed_textures=False, batch_mode='OFF', use_batch_own_dir=True, use_metadata=True, axis_forward='-Z', axis_up='Y')

        return {'FINISHED'}

#_______________________________________________________________________________________________________________

def createfolder(basedir, foldername):
    if not os.path.exists(os.path.join(basedir, foldername)):
        os.mkdir(os.path.join(basedir, foldername))
        print('There is no '+ foldername +' folder. Creating one...')
    else:
        print('Found previously created FBX folder. I will use it')
    if not basedir:
        raise Exception("Save the blend file before to export")

class OBJECT_OT_fbxexportbatch(bpy.types.Operator):
    bl_idname = "fbx.exportbatch"
    bl_label = "Fbx export batch UE4"
    bl_options = {"REGISTER", "UNDO"}

    #export_format : StringProperty()

    def execute(self, context):
        #print(self.export_format)
        scene = context.scene

        if scene.FBX_export_dir:
            basedir = os.path.dirname(scene.FBX_export_dir)
            subfolder = ''
        else:
            basedir = os.path.dirname(bpy.data.filepath)
            subfolder = self.export_format
        
        createfolder(basedir, subfolder)
        subfolderpath = os.path.join(basedir, subfolder)

        if scene.instanced_export:
            #annotate the name of the active object (for instanced mode only)
            active_object = context.active_object
            file_instance_matrix_name = active_object.name+"-inst.txt"
            file_instance_matrix_path = os.path.join(subfolderpath, file_instance_matrix_name)
            #calling function to write instanced data to disk
            write_some_data(context, file_instance_matrix_path, scene.SHIFT_OBJ_on,
                    True, False, False)
            bpy.ops.object.select_all(action='DESELECT')
            active_object.select_set(True)
            
            
        else:
            selection = bpy.context.selected_objects
            bpy.ops.object.select_all(action='DESELECT')

            for obj in selection:
                obj.select_set(True)
                colfolder = obj.users_collection[0].name
                createfolder(subfolderpath, colfolder)
                name = bpy.path.clean_name(obj.name)
                fn = os.path.join(basedir, subfolder, colfolder, name)
                #print(fn)
                #if self.export_format == "FBX":
                print(f"Provo ad esportare il formato FBX in {fn} .fbx")
                bpy.ops.export_scene.fbx(filepath = fn+".fbx", check_existing = True, filter_glob = '*.fbx', use_selection = True, use_active_collection = False, global_scale = 1.0, apply_unit_scale = True, apply_scale_options = 'FBX_SCALE_NONE', use_space_transform = True, bake_space_transform = False, object_types = {'MESH'}, use_mesh_modifiers = True, use_mesh_modifiers_render = True, mesh_smooth_type = 'OFF', use_subsurf = False, use_mesh_edges = False, use_tspace = False, use_custom_props = False, add_leaf_bones = False, primary_bone_axis = 'Y', secondary_bone_axis = 'X', use_armature_deform_only = False, armature_nodetype = 'NULL', bake_anim = False, bake_anim_use_all_bones = False, bake_anim_use_nla_strips = False, bake_anim_use_all_actions = False, bake_anim_force_startend_keying = False, bake_anim_step = 1.0, bake_anim_simplify_factor = 1.0, path_mode = 'COPY', embed_textures = True, batch_mode = 'OFF', use_batch_own_dir = True, use_metadata = True, axis_forward = '-Z', axis_up ='Y')

                obj.select_set(False)
        return {'FINISHED'}

class OBJECT_OT_osgtexportbatch(bpy.types.Operator):
    bl_idname = "osgt.exportbatch"
    bl_label = "osgt export batch"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):

        basedir = os.path.dirname(bpy.data.filepath)
        if not basedir:
            raise Exception("Blend file is not saved")
        bpy.ops.osg.export(SELECTED=True)
        return {'FINISHED'}


