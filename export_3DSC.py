import bpy
import os
from .functions import *

import bpy
import math

from bpy_extras.io_utils import ExportHelper
from bpy.props import StringProperty, BoolProperty, EnumProperty
from bpy.types import Operator

import shutil


class ExportConvert3DTiles(bpy.types.Operator):
    """Esporta e converte oggetti selezionati in 3D Tiles"""
    bl_idname = "object.export_convert_3dtiles"
    bl_label = "Esporta e Converti in 3D Tiles"

    @classmethod
    def poll(cls, context):
        
        #scene = context.scene
        is_active_button = False
        prefs = context.preferences.addons.get(__package__, None)
        if prefs.preferences.is_external_module:# and scene.EMdb_xlsx_filepath is not None:
            is_active_button = True
        return is_active_button

    def execute(self, context):
        #from py3dtiles.convert import convert
        from py3dtiles import convert as convert_to_3dtiles
        try:
            # Seleziona una cartella di destinazione (questo è solo un placeholder)
            
            dest_folder = context.scene.model_export_dir
            temp_folder = os.path.join(dest_folder, "temp")
            print(temp_folder)

            # Crea una cartella temporanea
            os.makedirs(temp_folder, exist_ok=True)

            # Esporta ogni oggetto selezionato in glTF
            for obj in bpy.context.selected_objects:
                self.export_gltf(obj, temp_folder)
                print(obj)

            # Converti i file glTF in 3D Tiles
            self.convert_to_3dtiles_files(temp_folder, dest_folder)

            # Rimuovi la cartella temporanea
            #shutil.rmtree(temp_folder)

        except OSError as e:
            self.report({'ERROR'}, "Errore nel file system: " + str(e))
            # Pulisci i file temporanei in caso di errore
            if os.path.exists(temp_folder):
                shutil.rmtree(temp_folder)
            return {'CANCELLED'}

        return {'FINISHED'}

    def export_gltf(self, obj, temp_folder):
        # Salva il nome originale dell'oggetto e imposta il nome del file
        original_name = obj.name
        obj.name = "TempExport"
        #file_path = os.path.join(temp_folder, obj.name + ".gltf")
        file_path = os.path.join(temp_folder, obj.name + ".ply")

        # Esporta l'oggetto in glTF
        #bpy.ops.export_scene.gltf(filepath=file_path, use_selection=True, export_format='GLTF_SEPARATE')

        # work-around via ply in attesa che sviluppino la nuova libreria py3dtiles con supporto gltf
        bpy.ops.wm.ply_export(filepath=file_path, export_selected_objects=True)


        # Ripristina il nome originale
        obj.name = original_name

    def convert_to_3dtiles_files(self, input_folder, output_folder):
        # Usa py3dtiles per convertire ogni file glTF in 3D Tiles
        for file in os.listdir(input_folder):
            #if file.endswith(".gltf"):
            if file.endswith(".ply"):
                from py3dtiles.convert import convert as convert_to_3dtiles
                input_path = os.path.join(input_folder, file)
                output_path = os.path.join(output_folder, os.path.splitext(file)[0] + "_3DTiles")
                convert_to_3dtiles([input_path], output_path, 'batched')
                #convert(input=input_path, output=output_path, format='3dtiles')


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
            scale_grad_x = obj.scale[0]
            scale_grad_y = obj.scale[1]
            scale_grad_z = obj.scale[2]

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
                f.write("%s %s %s %s %s %s %s %s %s %s\n" % (obj.name, x_coor, y_coor, z_coor, rotation_grad_x, rotation_grad_y, rotation_grad_z, scale_grad_x, scale_grad_y, scale_grad_z))
            else:
                f.write("%s %s %s %s %s %s %s %s %s\n" % (x_coor, y_coor, z_coor, rotation_grad_x, rotation_grad_y, rotation_grad_z, scale_grad_x, scale_grad_y, scale_grad_z))
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
            ) # type: ignore

    # List of operator properties, the attributes will be assigned
    # to the class instance from the operator settings before calling.

    nam: BoolProperty(
            name="Add names of objects",
            description="This tool includes name",
            default=True,
            ) # type: ignore

    rot: BoolProperty(
            name="Add rotation and scale",
            description="This tool includes name, position, rotation and scale",
            default=False,
            ) # type: ignore

    cam: BoolProperty(
            name="Export only cams",
            description="This tool includes name, position, rotation and focal lenght",
            default=False,
            ) # type: ignore

    shift: BoolProperty(
            name="World shift coordinates",
            description="Shift coordinates using the General Shift Value (GSV)",
            default=False,
            ) # type: ignore

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
        #bpy.ops.export_scene.obj(filepath=fn + ".obj", use_selection=True, axis_forward='Y', axis_up='Z', path_mode='RELATIVE', global_shift_x = x_shift, global_shift_y = y_shift, global_shift_z = z_shift)

        bpy.ops.wm.obj_export(filepath=fn + ".obj", check_existing=True, filter_blender=False, filter_backup=False, filter_image=False, filter_movie=False, filter_python=False, filter_font=False, filter_sound=False, filter_text=False, filter_archive=False, filter_btx=False, filter_collada=False, filter_alembic=False, filter_usd=False, filter_obj=False, filter_volume=False, filter_folder=True, filter_blenlib=False, filemode=8, display_type='DEFAULT', sort_method='DEFAULT', export_animation=False, start_frame=-2147483648, end_frame=2147483647, forward_axis='Y', up_axis='Z', global_scale=1.0, apply_modifiers=True, export_eval_mode='DAG_EVAL_VIEWPORT', export_selected_objects=True, export_uv=True, export_normals=True, export_colors=False, export_materials=True, export_pbr_extensions=False, path_mode='RELATIVE', export_triangulated_mesh=False, export_curves_as_nurbs=False, export_object_groups=False, export_material_groups=False, export_vertex_groups=False, export_smooth_groups=False, smooth_group_bitflags=False, filter_glob='*.obj;*.mtl')
        return {'FINISHED'}

class OBJECT_OT_gltfexportbatch(bpy.types.Operator):
    bl_idname = "gltf.exportbatch"
    bl_label = "Gltf export batch"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        scene = context.scene
        #basedir = 'F:\LOD1'
        copyright = context.scene.author_sign_model #"CC-BY-NC E.Demetrescu"
        draco_compression = 6

        basedir = bpy.path.abspath(bpy.context.scene.model_export_dir) if bpy.context.scene.model_export_dir else bpy.path.abspath(os.path.dirname(bpy.data.filepath))

        if not basedir:
            raise Exception("Blend file is not saved")

        selection = bpy.context.selected_objects
        bpy.ops.object.select_all(action='DESELECT')

        for obj in selection:
            obj.select_set(True)
            name = bpy.path.clean_name(obj.name)
            namefile = name + ".gltf"
            file_path = os.path.join(basedir, namefile)
            bpy.ops.export_scene.gltf(export_format='GLTF_SEPARATE', ui_tab='GENERAL', export_copyright=copyright, export_image_format='AUTO', export_texture_dir='', export_texcoords=True, export_normals=True, export_draco_mesh_compression_enable=True, export_draco_mesh_compression_level=draco_compression, export_draco_position_quantization=14, export_draco_normal_quantization=10, export_draco_texcoord_quantization=12, export_draco_generic_quantization=12, export_tangents=False, export_materials='EXPORT', export_colors=False, export_cameras=False, use_selection=True, export_extras=False, export_yup=True, export_apply=True, export_animations=False, export_frame_range=False, export_frame_step=1, export_force_sampling=False, export_nla_strips=False, export_def_bones=False, export_current_frame=False, export_skins=False, export_all_influences=False, export_morph=True, export_morph_normal=False, export_morph_tangent=False, export_lights=False,  will_save_settings=False, filepath=file_path, check_existing=False)#, filter_glob='*.glb;*.gltf')
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


        basedir = bpy.path.abspath(bpy.context.scene.model_export_dir) if bpy.context.scene.model_export_dir else bpy.path.abspath(os.path.dirname(bpy.data.filepath))

        if not basedir:
            raise Exception("Blend file is not saved")

        selection = bpy.context.selected_objects
        bpy.ops.object.select_all(action='DESELECT')

        for obj in selection:
            obj.select_set(True)
            name = bpy.path.clean_name(obj.name)
            namefile = name + ".glb"
            file_path = os.path.join(basedir, namefile)
            bpy.ops.export_scene.gltf(export_format='GLB', ui_tab='GENERAL', export_copyright=copyright, export_image_format='AUTO', export_texture_dir='', export_texcoords=True, export_normals=True, export_draco_mesh_compression_enable=False, export_draco_mesh_compression_level=draco_compression, export_draco_position_quantization=14, export_draco_normal_quantization=10, export_draco_texcoord_quantization=12, export_draco_generic_quantization=12, export_tangents=False, export_materials='EXPORT', export_colors=False, export_cameras=False, use_selection=True, export_extras=False, export_yup=True, export_apply=True, export_animations=True, export_frame_range=False, export_frame_step=1, export_force_sampling=False, export_nla_strips=False, export_def_bones=False, export_current_frame=False, export_skins=False, export_all_influences=False, export_morph=True, export_morph_normal=False, export_morph_tangent=False, export_lights=False,  will_save_settings=False, filepath=file_path, check_existing=False)#, filter_glob='*.glb;*.gltf')
            obj.select_set(False)
        return {'FINISHED'}

class OBJECT_OT_objexportbatch(bpy.types.Operator):
    bl_idname = "obj.exportbatch"
    bl_label = "Obj export batch"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        basedir = bpy.path.abspath(bpy.context.scene.model_export_dir) if bpy.context.scene.model_export_dir else bpy.path.abspath(os.path.dirname(bpy.data.filepath))

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
            #bpy.ops.export_scene.obj(filepath=str(fn + '.obj'), use_selection=True, axis_forward='Y', axis_up='Z', path_mode='RELATIVE', global_shift_x = x_shift, global_shift_y = y_shift, global_shift_z = z_shift)
            #bpy.ops.export_scene.obj(filepath=str(fn + '.obj'), use_selection=True, axis_forward='Y', axis_up='Z', path_mode='RELATIVE')
            bpy.ops.wm.obj_export(filepath=fn + ".obj", check_existing=True, filter_blender=False, filter_backup=False, filter_image=False, filter_movie=False, filter_python=False, filter_font=False, filter_sound=False, filter_text=False, filter_archive=False, filter_btx=False, filter_collada=False, filter_alembic=False, filter_usd=False, filter_obj=False, filter_volume=False, filter_folder=True, filter_blenlib=False, filemode=8, display_type='DEFAULT', sort_method='DEFAULT', export_animation=False, start_frame=-2147483648, end_frame=2147483647, forward_axis='Y', up_axis='Z', global_scale=1.0, apply_modifiers=True, export_eval_mode='DAG_EVAL_VIEWPORT', export_selected_objects=True, export_uv=True, export_normals=True, export_colors=False, export_materials=True, export_pbr_extensions=False, path_mode='RELATIVE', export_triangulated_mesh=False, export_curves_as_nurbs=False, export_object_groups=False, export_material_groups=False, export_vertex_groups=False, export_smooth_groups=False, smooth_group_bitflags=False, filter_glob='*.obj;*.mtl')
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

        if scene.model_export_dir:
            basedir = bpy.path.abspath(os.path.dirname(scene.model_export_dir))
            subfolder = ''
        else:
            basedir = bpy.path.abspath(os.path.dirname(bpy.data.filepath))
            subfolder = 'FBX'
        
        createfolder(basedir, subfolder)
        subfolderpath = os.path.join(basedir, subfolder)

        if scene.instanced_export:
            #annotate the name of the active object (for instanced mode only)
            active_object = context.active_object
            
            # This part will incapsulate the file + file-inst in a single Folder
            colfolder = active_object.users_collection[0].name
            createfolder(subfolderpath, colfolder)

            # selecting a brand new name for the instanced file
            name = bpy.path.clean_name(active_object.name)
            fn = os.path.join(subfolderpath, colfolder, name)

            # defining the paths for the new files
            file_instance_matrix_path = fn+"-inst.txt"
            file_instance_fbx_path = fn+".fbx"

            #calling function to write file-inst to disk
            # write_some_data(context, filepath, shift, rot, cam, nam)
            write_some_data(context, file_instance_matrix_path, scene.SHIFT_OBJ_on, True, False, False)
            
            bpy.ops.object.select_all(action='DESELECT')
            active_object.select_set(True)

            # store present matrix of the ative object 
            obj_location_x = active_object.location[0]
            obj_location_y = active_object.location[1]
            obj_location_z = active_object.location[2]
            obj_rot_x = active_object.rotation_euler[0]
            obj_rot_y = active_object.rotation_euler[1]
            obj_rot_z = active_object.rotation_euler[2]
            obj_scale_x = active_object.scale[0]
            obj_scale_y = active_object.scale[1]
            obj_scale_z = active_object.scale[2]

            #set to zero the loc rot and to one the scale
            active_object.location = [0.0,0.0,0.0]
            active_object.rotation_euler = [0.0,0.0,0.0]
            active_object.scale = [1.0,1.0,1.0]

            bpy.ops.export_scene.fbx(filepath=file_instance_fbx_path, check_existing=True, filter_glob='*.fbx', use_selection=True, use_active_collection=False, global_scale=1.0, apply_unit_scale=True, apply_scale_options='FBX_SCALE_NONE', use_space_transform=True, bake_space_transform=False, object_types={
                                     'MESH', 'EMPTY'}, use_mesh_modifiers=True, use_mesh_modifiers_render=True, mesh_smooth_type='EDGE', use_subsurf=False, use_mesh_edges=False, use_tspace=False, use_custom_props=False, add_leaf_bones=False, primary_bone_axis='Y', secondary_bone_axis='X', use_armature_deform_only=False, armature_nodetype='NULL', bake_anim=False, bake_anim_use_all_bones=False, bake_anim_use_nla_strips=False, bake_anim_use_all_actions=False, bake_anim_force_startend_keying=False, bake_anim_step=1.0, bake_anim_simplify_factor=1.0, path_mode='COPY', embed_textures=True, batch_mode='OFF', use_batch_own_dir=True, use_metadata=True, axis_forward='-Z', axis_up='Y')
            
            #restore the original values to the object
            active_object.location = [obj_location_x,obj_location_y,obj_location_z]
            active_object.rotation_euler =[obj_rot_x,obj_rot_y,obj_rot_z]
            active_object.scale =[obj_scale_x,obj_scale_y,obj_scale_z]
             
        else:
            selection = bpy.context.selected_objects
            bpy.ops.object.select_all(action='DESELECT')

            for obj in selection:
                obj.select_set(True)
                name = bpy.path.clean_name(obj.name)

                #check if the collection gerarchy is enabled
                if scene.collgerarchy_to_foldtree:
                    colfolder = obj.users_collection[0].name
                    createfolder(subfolderpath, colfolder)    
                    fn = os.path.join(basedir, subfolder, colfolder, name)
                else:
                    fn = os.path.join(basedir, subfolder, name)

                print(f"Provo ad esportare il formato FBX in {fn} .fbx")
                bpy.ops.export_scene.fbx(filepath = fn+".fbx", check_existing = True, filter_glob = '*.fbx', use_selection = True, use_active_collection = False, global_scale = 1.0, apply_unit_scale = True, apply_scale_options = 'FBX_SCALE_NONE', use_space_transform = True, bake_space_transform = False, object_types = {'MESH','EMPTY'}, use_mesh_modifiers = True, use_mesh_modifiers_render = True, mesh_smooth_type = 'EDGE', use_subsurf = False, use_mesh_edges = False, use_tspace = False, use_custom_props = False, add_leaf_bones = False, primary_bone_axis = 'Y', secondary_bone_axis = 'X', use_armature_deform_only = False, armature_nodetype = 'NULL', bake_anim = False, bake_anim_use_all_bones = False, bake_anim_use_nla_strips = False, bake_anim_use_all_actions = False, bake_anim_force_startend_keying = False, bake_anim_step = 1.0, bake_anim_simplify_factor = 1.0, path_mode = 'COPY', embed_textures = True, batch_mode = 'OFF', use_batch_own_dir = True, use_metadata = True, axis_forward = '-Z', axis_up ='Y')

                obj.select_set(False)
        return {'FINISHED'}

'''
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
'''

class OBJECT_OT_exportbatch(bpy.types.Operator):
    bl_idname = "model.exportbatch"
    bl_label = "Objects export batch"
    bl_options = {"REGISTER", "UNDO"}

    export_format : StringProperty() # type: ignore

    def execute(self, context):
        #print(self.export_format)
        scene = context.scene

        copyright = context.scene.author_sign_model #"CC-BY-NC E.Demetrescu"
        draco_compression = 6

        if scene.model_export_dir:
            basedir = bpy.path.abspath(os.path.dirname(scene.model_export_dir))
            subfolder = ''
        else:
            basedir = bpy.path.abspath(os.path.dirname(bpy.data.filepath))
            subfolder = self.export_format

        if not basedir:
            raise Exception("Blend file is not saved")
        
        createfolder(basedir, subfolder)
        subfolderpath = os.path.join(basedir, subfolder)

        if scene.instanced_export:
            #annotate the name of the active object (for instanced mode only)
            active_object = context.active_object
            
            # This part will incapsulate the file + file-inst in a single Folder
            colfolder = active_object.users_collection[0].name
            createfolder(subfolderpath, colfolder)

            # selecting a brand new name for the instanced file
            name = bpy.path.clean_name(active_object.name)
            fn = os.path.join(subfolderpath, colfolder, name)

            # defining the paths for the new files
            file_instance_matrix_path = fn+"-inst.txt"
            file_instance_path = fn+"."+self.export_format

            #calling function to write file-inst to disk
            # write_some_data(context, filepath, shift, rot, cam, nam)
            write_some_data(context, file_instance_matrix_path, scene.SHIFT_OBJ_on, True, False, False)
            
            bpy.ops.object.select_all(action='DESELECT')
            active_object.select_set(True)

            # store present matrix of the ative object 
            obj_location_x = active_object.location[0]
            obj_location_y = active_object.location[1]
            obj_location_z = active_object.location[2]
            obj_rot_x = active_object.rotation_euler[0]
            obj_rot_y = active_object.rotation_euler[1]
            obj_rot_z = active_object.rotation_euler[2]
            obj_scale_x = active_object.scale[0]
            obj_scale_y = active_object.scale[1]
            obj_scale_z = active_object.scale[2]

            #set to zero the loc rot and to one the scale
            active_object.location = [0.0,0.0,0.0]
            active_object.rotation_euler = [0.0,0.0,0.0]
            active_object.scale = [1.0,1.0,1.0]

            if self.export_format == "fbx":
                bpy.ops.export_scene.fbx(filepath=file_instance_path, check_existing=True, filter_glob='*.fbx', use_selection=True, use_active_collection=False, global_scale=1.0, apply_unit_scale=True, apply_scale_options='FBX_SCALE_NONE', use_space_transform=True, bake_space_transform=False, object_types={'MESH', 'EMPTY'}, use_mesh_modifiers=True, use_mesh_modifiers_render=True, mesh_smooth_type='EDGE', use_subsurf=False, use_mesh_edges=False, use_tspace=False, use_custom_props=False, add_leaf_bones=False, primary_bone_axis='Y', secondary_bone_axis='X', use_armature_deform_only=False, armature_nodetype='NULL', bake_anim=False, bake_anim_use_all_bones=False, bake_anim_use_nla_strips=False, bake_anim_use_all_actions=False, bake_anim_force_startend_keying=False, bake_anim_step=1.0, bake_anim_simplify_factor=1.0, path_mode='COPY', embed_textures=True, batch_mode='OFF', use_batch_own_dir=True, use_metadata=True, axis_forward='-Z', axis_up='Y')
            elif self.export_format == "gltf":
                bpy.ops.export_scene.gltf(export_format='GLTF_SEPARATE', ui_tab='GENERAL', export_copyright=copyright, export_image_format='AUTO', export_texture_dir='', export_texcoords=True, export_normals=True, export_draco_mesh_compression_enable=True, export_draco_mesh_compression_level=draco_compression, export_draco_position_quantization=14, export_draco_normal_quantization=10, export_draco_texcoord_quantization=12, export_draco_generic_quantization=12, export_tangents=False, export_materials='EXPORT', export_colors=False, export_cameras=False, use_selection=True, export_extras=False, export_yup=True, export_apply=True, export_animations=False, export_frame_range=False, export_frame_step=1, export_force_sampling=False, export_nla_strips=False, export_def_bones=False, export_current_frame=False, export_skins=False, export_all_influences=False, export_morph=True, export_morph_normal=False, export_morph_tangent=False, export_lights=False, will_save_settings=False, filepath=file_instance_path, check_existing=False)
            #restore the original values to the object
            active_object.location = [obj_location_x,obj_location_y,obj_location_z]
            active_object.rotation_euler =[obj_rot_x,obj_rot_y,obj_rot_z]
            active_object.scale =[obj_scale_x,obj_scale_y,obj_scale_z]
             
        else:
            selection = bpy.context.selected_objects
            bpy.ops.object.select_all(action='DESELECT')

            for obj in selection:
                obj.select_set(True)
                name = bpy.path.clean_name(obj.name)

                #check if the collection gerarchy is enabled
                if scene.collgerarchy_to_foldtree:
                    colfolder = obj.users_collection[0].name
                    createfolder(subfolderpath, colfolder)    
                    fn = os.path.join(basedir, subfolder, colfolder, name)
                else:
                    fn = os.path.join(basedir, subfolder, name)

                # defining the paths for the new files
                #file_instance_matrix_path = fn+"-inst.txt"
                file_instance_path = fn+"."+self.export_format

                if self.export_format == "fbx":
                    print(f"Provo ad esportare il formato FBX in {fn} .fbx")
                    bpy.ops.export_scene.fbx(filepath = fn+".fbx", check_existing = True, filter_glob = '*.fbx', use_selection = True, use_active_collection = False, global_scale = 1.0, apply_unit_scale = True, apply_scale_options = 'FBX_SCALE_NONE', use_space_transform = True, bake_space_transform = False, object_types = {'MESH','EMPTY'}, use_mesh_modifiers = True, use_mesh_modifiers_render = True, mesh_smooth_type = 'EDGE', use_subsurf = False, use_mesh_edges = False, use_tspace = False, use_custom_props = False, add_leaf_bones = False, primary_bone_axis = 'Y', secondary_bone_axis = 'X', use_armature_deform_only = False, armature_nodetype = 'NULL', bake_anim = False, bake_anim_use_all_bones = False, bake_anim_use_nla_strips = False, bake_anim_use_all_actions = False, bake_anim_force_startend_keying = False, bake_anim_step = 1.0, bake_anim_simplify_factor = 1.0, path_mode = 'COPY', embed_textures = True, batch_mode = 'OFF', use_batch_own_dir = True, use_metadata = True, axis_forward = '-Z', axis_up ='Y')
                elif self.export_format == "gltf":
                    bpy.ops.export_scene.gltf(export_format='GLTF_SEPARATE', ui_tab='GENERAL', export_copyright=copyright, export_image_format='AUTO', export_texture_dir='', export_texcoords=True, export_normals=True, export_draco_mesh_compression_enable=True, export_draco_mesh_compression_level=draco_compression, export_draco_position_quantization=14, export_draco_normal_quantization=10, export_draco_texcoord_quantization=12, export_draco_generic_quantization=12, export_tangents=False, export_materials='EXPORT', export_colors=False, export_cameras=False, use_selection=True, export_extras=False, export_yup=True, export_apply=True, export_animations=False, export_frame_range=False, export_frame_step=1, export_force_sampling=False, export_nla_strips=False, export_def_bones=False, export_current_frame=False, export_skins=False, export_all_influences=False, export_morph=True, export_morph_normal=False, export_morph_tangent=False, export_lights=False,  will_save_settings=False, filepath=file_instance_path, check_existing=False)
                obj.select_set(False)

        return {'FINISHED'}
    
#SETUP MENU
#####################################################################

classes = [
    ExportConvert3DTiles]

def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in classes:
        bpy.utils.unregister_class(cls)
