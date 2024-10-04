import bpy
import os
import time
from .functions import *
from mathutils import Vector
from bpy.types import Panel
import subprocess


def selectLOD(listobjects, lodnum, basename):
    name2search = basename + '_LOD' + str(lodnum)
    for ob in listobjects:
        if ob.name == name2search:
            objatgivenlod = ob
            return objatgivenlod
        else:
            objatgivenlod = None
    return objatgivenlod

def getChildren(myObject):
    children = []
    for ob in bpy.data.objects:
        if ob.parent == myObject:
            children.append(ob)
    return children

class OBJECT_OT_LOD0(bpy.types.Operator):
    """Set selected objs as LOD0. It creates an additional ATLAS Map"""
    bl_idname = "lod0.creation"
    bl_label = "LOD0"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        selected_objs = bpy.context.selected_objects
        for obj in bpy.context.selected_objects:
            bpy.ops.object.select_all(action='DESELECT')
            obj.select_set(True)
            bpy.context.view_layer.objects.active = obj
            bpy.ops.object.shade_smooth()
            baseobj = obj.name
            if not baseobj.endswith('LOD0'):
                obj.name = baseobj + '_LOD0'
            if len(obj.data.uv_layers) > 1:
                if obj.data.uv_layers[0].name =='MultiTex' and obj.data.uv_layers[1].name =='Atlas':
                    pass
            else:
                create_double_UV(obj)
            rename_ge(obj)            
        return {'FINISHED'}

#_____________________________________________________________________________

def ratio_for_current_lod(lod,context):
    if lod == 1:
        ratio = context.scene.LOD1_dec_ratio
    if lod == 2:
        ratio = context.scene.LOD2_dec_ratio
    if lod == 3:
        ratio = context.scene.LOD3_dec_ratio
    return ratio

def tex_res_for_current_lod(lod,context):
    if lod == 1:
        tex_res = context.scene.LOD1_tex_res
    if lod == 2:
        tex_res = context.scene.LOD2_tex_res
    if lod == 3:
        tex_res = context.scene.LOD3_tex_res
    return tex_res

class OBJECT_OT_LOD(bpy.types.Operator):
    """Creates the desired LODs and export them as obj(s) in LOD(x) subfolders"""
    bl_idname = "lod.creation"
    bl_label = "LOD"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        start_time = time.time()
        context = bpy.context
        selected_objects = context.selected_objects
        ob_tot = len(selected_objects)
        LODnum = context.scene.LODnum
        i_lodbake_counter = 1

        #context.view_layer.active_layer_collection = bpy.data.collections.get('LOD0')

        basedir = os.path.dirname(bpy.data.filepath)
        if not basedir:
            raise Exception("Save the blend file")
        # si prende il numero di LOD impostato e i parametri base per LOD ovvero tex_res e decimation_ratio
        # iniziamo con un contatore i_lodbake_counter che parte da 0

        print("Number of LOD(s) to be created is: " + str(LODnum))
        last_margin_val = context.scene.render.bake.margin
        # si producono ciclicamente i livelli di dettaglio ad esaurire i LOD richiesti dall'utente nell'UI (normalmente da 1 a 3 LOD)
        while i_lodbake_counter <= LODnum:
            currentLOD = 'LOD' + str(i_lodbake_counter)
            subfolder = currentLOD

            if not os.path.exists(os.path.join(basedir, subfolder)):
                os.mkdir(os.path.join(basedir, subfolder))
                print('There is no '+ subfolder +' folder. Creating one...')
            else:
                print('Found previously created '+ subfolder +' folder. I will use it')

            ob_counter = 1

            print('<<<<<<<<<<<<<< CREATION OF '+ currentLOD +' >>>>>>>>>>>>>>')
            print('>>>>>> '+str(ob_tot)+' objects will be processed')

            for obj_LOD0 in selected_objects:

                start_time_ob = time.time()

                print('>>> '+ currentLOD + ' >>>')
                print('>>>>>> processing the object ""'+ obj_LOD0.name+'"" ('+str(ob_counter)+'/'+str(ob_tot)+')')
                bpy.ops.object.select_all(action='DESELECT')
                obj_LOD0.select_set(True)
                context.view_layer.objects.active = obj_LOD0
                obj_LOD0_name = obj_LOD0.name
                if '_LOD0' in obj_LOD0_name:
                    obj_base_name = obj_LOD0_name.replace("_LOD0", "")
                else:
                    obj_base_name = obj_LOD0_name

                print('Creating new LOD'+ str(i_lodbake_counter) +' object..')
                bpy.ops.object.duplicate(linked=False, mode='TRANSLATION')
                obj_LODnew = context.view_layer.objects.active

                LOD0layerCol = context.view_layer.active_layer_collection
                LOD0Col = bpy.data.collections.get(LOD0layerCol.name)

                if bpy.data.collections.get(currentLOD) is None:
                    currentLODCol = bpy.data.collections.new(currentLOD)
                    currentLODCol.name = currentLOD
                    context.scene.collection.children.link(currentLODCol)
                else:
                    currentLODCol = bpy.data.collections.get(currentLOD)

                # link the object to collection
                currentLODCol.objects.link(obj_LODnew)
                # unlink from previous collection
                LOD0Col.objects.unlink(obj_LODnew)

                bpy.ops.object.select_all(action='DESELECT')
                context.view_layer.objects.active = obj_LODnew
                obj_LODnew.select_set(True)
                obj_LODnew.name = obj_base_name + "_" + currentLOD
                obj_LODnew_name = obj_LODnew.name

                for i in range(0,len(bpy.data.objects[obj_LODnew_name].material_slots)):
                    bpy.ops.object.material_slot_remove()

                if obj_LODnew.data.uv_layers[1] and obj_LODnew.data.uv_layers[1].name =='Atlas':
                    print('Found Atlas UV mapping layer. I will use it.')
                    uv_layers = obj_LODnew.data.uv_layers
                    uv_layers.remove(uv_layers[0])
                else:
                    print('Creating new UV mapping layer.')
                    create_double_UV(obj_LODnew)

                obj_LOD0.data.uv_layers["MultiTex"].active_render = True

                # mesh decimation
                decimate_mesh(context,obj_LODnew,ratio_for_current_lod(i_lodbake_counter,context),currentLOD)

                # now the mesh is decimated
                #------------------------------------------------------------------

                print('Creating new texture atlas for ' + currentLOD + '....')
                tex_res = tex_res_for_current_lod(i_lodbake_counter,context)
                tex_LODnew_name = "T_"+ obj_LODnew_name
                tempimage = bpy.data.images.new(name=tex_LODnew_name, width=tex_res, height=tex_res, alpha=False)
                tempimage.filepath_raw = "//"+subfolder+'/'+tex_LODnew_name+".jpg"
                filepathimage = "//"+subfolder+'/'+tex_LODnew_name+".jpg"
                tempimage.file_format = 'JPEG'

                # annotate current cycles render settings to maintain things clean
                #--------------------------------------------------------------

                to_be_restored_render_engine = context.scene.render.engine
                context.scene.render.engine = 'CYCLES'
                context.scene.cycles.bake_type = 'DIFFUSE'

                if context.scene.LOD_use_scene_settings:
                    context.scene.render.bake.use_pass_direct = True
                    context.scene.render.bake.use_pass_indirect = True
                else:
                    context.scene.render.bake.use_pass_direct = False
                    context.scene.render.bake.use_pass_indirect = False  

                context.scene.render.bake.use_pass_color = True
                context.scene.render.bake.use_selected_to_active = True
                context.scene.render.bake.cage_extrusion = 0.1

                if context.scene.LOD_pad_on:
                    custommargin = "context.scene.render.bake.margin = context.scene.LOD"+str(i_lodbake_counter)+"_tex_res"
                    exec(custommargin)
                
                if not context.scene.LOD_use_scene_settings:
                    to_restore_samples = context.scene.cycles.samples
                    context.scene.cycles.samples = 1

                    to_restore_bounces = context.scene.cycles.diffuse_bounces
                    context.scene.cycles.diffuse_bounces = 1

                # creating a new material
                #--------------------------------------------------------------
                print('Creating custom material for '+ currentLOD +'...')
                bpy.ops.object.select_all(action='DESELECT')
                obj_LODnew.select_set(True)
                context.view_layer.objects.active = obj_LODnew
                mat, texImage, bsdf = create_material_from_image(context,tempimage,obj_LODnew,False)

                # baking textures
                #--------------------------------------------------------------
                print('Passing color data from LOD0 to '+ currentLOD + '...')

                bpy.ops.object.select_all(action='DESELECT')
                obj_LODnew.select_set(True)
                obj_LOD0.select_set(True)
                obj_LOD0_LODnew_selected = context.selected_objects
                context.view_layer.objects.active = obj_LODnew
                bpy.ops.object.bake(type='DIFFUSE')
                tempimage.save()

                # annotate current cycles render settings to maintain things clean
                #-----------------------------------------------------------------
                if not context.scene.LOD_use_scene_settings:
                    context.scene.cycles.diffuse_bounces = to_restore_bounces
                    context.scene.cycles.samples = to_restore_samples
                    
                context.scene.render.engine = to_be_restored_render_engine

                mat.node_tree.links.new(bsdf.inputs['Base Color'], texImage.outputs['Color'])
                
                if obj_LODnew.name.startswith('OB_'):
                    obj_LODnew.name= rimuovi_prefisso_ob(obj_LODnew.name)

                obj_LODnew.data.name = 'ME_' + obj_LODnew.name

                # select only the just created LOD obj

                bpy.ops.object.select_all(action='DESELECT')
                obj_LODnew.select_set(True)
                context.view_layer.objects.active = obj_LODnew

                # Saving on obj/mtl file for currentLOD
                #-----------------------------------------------------------------
                print('Saving on obj/mtl file for '+ currentLOD +'...')
                activename = bpy.path.clean_name(obj_LODnew.name)
                fn = os.path.join(basedir, subfolder, activename)
                bpy.ops.wm.obj_export(filepath=fn + ".obj", check_existing=True, filter_blender=False, filter_backup=False, filter_image=False, filter_movie=False, filter_python=False, filter_font=False, filter_sound=False, filter_text=False, filter_archive=False, filter_btx=False, filter_collada=False, filter_alembic=False, filter_usd=False, filter_obj=False, filter_volume=False, filter_folder=True, filter_blenlib=False, filemode=8, display_type='DEFAULT', sort_method='DEFAULT', export_animation=False, start_frame=-2147483648, end_frame=2147483647, forward_axis='Y', up_axis='Z', global_scale=1.0, apply_modifiers=True, export_eval_mode='DAG_EVAL_VIEWPORT', export_selected_objects=True, export_uv=True, export_normals=True, export_colors=False, export_materials=True, export_pbr_extensions=False, path_mode='RELATIVE', export_triangulated_mesh=False, export_curves_as_nurbs=False, export_object_groups=False, export_material_groups=False, export_vertex_groups=False, export_smooth_groups=False, smooth_group_bitflags=False, filter_glob='*.obj;*.mtl')
                #bpy.ops.export_scene.obj(filepath=fn + ".obj", use_selection=True, axis_forward='Y', axis_up='Z', path_mode='RELATIVE')

                print('>>> "'+obj_LODnew.name+'" ('+str(ob_counter)+'/'+ str(ob_tot) +') object baked in '+str(time.time() - start_time_ob)+' seconds')
                ob_counter += 1

            i_lodbake_counter += 1
        end_time = time.time() - start_time
        context.scene.render.bake.margin = last_margin_val

        print('<<<<<<< Process done >>>>>>')
        print('>>>'+str(ob_tot)+' objects processed in '+str(end_time)+' seconds')
        return {'FINISHED'}

def rimuovi_prefisso_ob(stringa):
    if stringa.startswith("OB_"):
        return stringa[3:]  # Rimuovi i primi 3 caratteri (OB_)
    return stringa

#_______________________________________________________________________________________________

class OBJECT_OT_ExportGroupsLOD(bpy.types.Operator):
    """LOD cluster(s) export to FBX"""
    bl_idname = "exportfbx.grouplod"
    bl_label = "Export Group LOD"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        start_time = time.time()

        if bpy.context.scene.model_export_dir:
            basedir = bpy.path.abspath(os.path.dirname(bpy.context.scene.model_export_dir))
            subfolder = ''
        else:
            basedir = bpy.path.abspath(os.path.dirname(bpy.data.filepath))
            subfolder = 'FBX'

        #basedir = os.path.dirname(bpy.data.filepath)
        if not basedir:
            raise Exception("Blend file is not saved")
        ob_counter = 1
        scene = context.scene
        listobjects = context.selected_objects
        for obj in listobjects:
            if obj.type == 'EMPTY':
                if obj.get('fbx_type') is not None:
                    print('Found LOD cluster to export: "'+obj.name+'", object')
                    bpy.ops.object.select_all(action='DESELECT')
                    obj.select_set(True)
                    bpy.context.view_layer.objects.active = obj
                    for ob in getChildren(obj):
                        ob.select_set(True)
                    name = bpy.path.clean_name(obj.name)
                    fn = os.path.join(basedir, name)
                    bpy.ops.export_scene.fbx(filepath= fn + ".fbx", check_existing=True, axis_forward='-Z', axis_up='Y', filter_glob="*.fbx", use_selection=True, global_scale=1.0, apply_unit_scale=True, bake_space_transform=False, object_types={'ARMATURE', 'CAMERA', 'EMPTY', 'LIGHT', 'MESH', 'OTHER'}, use_mesh_modifiers=True, mesh_smooth_type='EDGE', use_mesh_edges=False, use_tspace=False, use_custom_props=False, add_leaf_bones=True, primary_bone_axis='Y', secondary_bone_axis='X', use_armature_deform_only=False, bake_anim=True, bake_anim_use_all_bones=True, bake_anim_use_nla_strips=True, bake_anim_use_all_actions=True, bake_anim_force_startend_keying=True, bake_anim_step=1.0, bake_anim_simplify_factor=1.0, path_mode='RELATIVE', embed_textures=False, batch_mode='OFF', use_batch_own_dir=True, use_metadata=True)
                else:
                    print('The "' + obj.name + '" empty object has not the correct settings to export an FBX - LOD enabled file. I will skip it.')
                    obj.select_set(False)
                    print('>>> Object number '+str(ob_counter)+' processed in '+str(time.time() - start_time)+' seconds')
                    ob_counter += 1

        end_time = time.time() - start_time
        print('<<<<<<< Process done >>>>>>')
        print('>>>'+str(ob_counter)+' objects processed in '+str(end_time)+' seconds')

        return {'FINISHED'}

#_______________________________________________________________


class OBJECT_OT_RemoveGroupsLOD(bpy.types.Operator):
    """Removes LOD cluster(s)"""
    bl_idname = "remove.grouplod"
    bl_label = "Remove Group LOD"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        listobjects = bpy.context.selected_objects
        bpy.ops.object.select_all(action='DESELECT')
        for obj in listobjects:
            if obj.get('fbx_type') is not None:
                obj.select_set(True)
                bpy.context.view_layer.objects.active = obj
                for ob in getChildren(obj):
                    ob.select_set(True)
                bpy.ops.object.parent_clear(type='CLEAR_KEEP_TRANSFORM')
                bpy.ops.object.select_all(action='DESELECT')
                obj.select_set(True)
                bpy.context.view_layer.objects.active = obj
                bpy.ops.object.delete()
        return {'FINISHED'}

#_______________________________________________________________


class OBJECT_OT_CreateGroupsLOD(bpy.types.Operator):
    """Creates LOD cluster(s): empty objects with nested LODs"""
    bl_idname = "create.grouplod"
    bl_label = "Create Group LOD"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        listobjects = bpy.context.selected_objects
        for obj in listobjects:
            bpy.ops.object.select_all(action='DESELECT')
            obj.select_set(True)
            bpy.context.view_layer.objects.active = obj
            baseobjwithlod = obj.name

            if '_LOD0' in baseobjwithlod:
                baseobj = baseobjwithlod.replace("_LOD0", "")
                print('Found LOD0 object:' + baseobjwithlod)
                local_bbox_center = 0.125 * sum((Vector(b) for b in obj.bound_box), Vector())
                global_bbox_center = obj.matrix_world @ local_bbox_center
                emptyofname = 'GLOD_' + baseobj
                obempty = bpy.data.objects.new( emptyofname, None )
                bpy.context.collection.objects.link(obempty)

                obempty.empty_display_size = 2
                obempty.empty_display_type = 'PLAIN_AXES'
                obempty.location = global_bbox_center
                bpy.ops.object.select_all(action='DESELECT')
                obempty.select_set(True)
                bpy.context.view_layer.objects.active = obempty
                obempty['fbx_type'] = 'LodGroup'

                num = 0
                child = selectLOD(listobjects, num, baseobj)
                print(child)
                print(baseobj)
                print(str(num))
                while child is not None:
                    child.parent = obempty
                    child.matrix_parent_inverse = obempty.matrix_world.inverted()
                    #oldway to do this:
                    #bpy.ops.object.select_all(action='DESELECT')
                    #child.select_set(True)
                    #obempty.select_set(True)
                    #bpy.context.view_layer.objects.active = obempty
                    #bpy.ops.object.parent_set(type='OBJECT', keep_transform=False)
                    num += 1
                    print(str(num))
                    child = selectLOD(listobjects, num, baseobj)
        return {'FINISHED'}

class OBJECT_OT_changeLOD(bpy.types.Operator):
    """Change LOD for selected objs"""
    bl_idname = "change.lod"
    bl_label = "Change LOD"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):

        context = bpy.context
        scene = context.scene
        #collection = context.collection

        lod_list_clear(context) 

        LOD_target = "LOD"+str(context.scene.setLODnum)

        selection = bpy.context.selected_objects

        #bpy.ops.object.select_all(action='DESELECT')

        LODS = ["LOD0", "LOD1", "LOD2", "LOD3", "LOD4", "LOD5"]

        librerie = []

        lod_list_item_counter = 0

        for objs_to_check in selection:
            current_obj_LOD = objs_to_check.name[-4:]
            #object_clean_name = objs_to_check.name[:-4]
            if current_obj_LOD == LOD_target or current_obj_LOD not in LODS:
                pass
            else:
                if objs_to_check.library is not None:
                    if objs_to_check.library.name not in librerie:
                        librerie.append(objs_to_check.library.name)
                    #print("L'oggetto "+objs_to_check.name + " appartiene alla libreria " + objs_to_check.library.name)
                    #objs_to_check.select_set(True)
                    scene.lod_list_item.add()
                    scene.lod_list_item[lod_list_item_counter].name = objs_to_check.name
                    scene.lod_list_item[lod_list_item_counter].libreria_lod = objs_to_check.library.name
                    lod_list_item_counter +=1
                    #print("oggetto aggiunto: "+scene.lod_list_item[lod_list_item_counter].name)

        for libreria in librerie:
            
            library_path = bpy.data.libraries[libreria].filepath

            with bpy.data.libraries.load(library_path, link=True) as (data_from, data_to):
                #data_to.objects = [target_name]#data.objects[target_name] #[name for name in data_from.objects if name.endswith("_LOD0")]
                data_to.objects = [name for name in data_from.objects if name.endswith(LOD_target)]
            
            for object_in_lod_list in scene.lod_list_item:
                #print(object_in_lod_list.name)
                #print("nella lista: "+object_in_lod_list.libreria_lod)
                #print("nella libreria: "+libreria)
                if object_in_lod_list.libreria_lod == libreria:
                    #print("ho trovato oggetto che ha la medesima libreria")
                    current_LOD = object_in_lod_list.name[-4:]
                   
                    #object_clean_name = object_in_library[:-4]
                    target_name = object_in_lod_list.name.replace(current_LOD, LOD_target)
                    
                    found = False
                    for object_in_library in data_to.objects:
                        if object_in_library.name == target_name:
                            found = True
                            collection_list_for_current_ob = []
                            for collection in bpy.data.collections:
                                for obj in collection.all_objects:
                                    if obj.name == object_in_lod_list.name:
                                        
                                        collection_list_for_current_ob.append(collection.name)
                                        
                            for relevant_collection in collection_list_for_current_ob:
                                bpy.data.collections[relevant_collection].objects.link(bpy.data.objects[target_name])
                                bpy.data.collections[relevant_collection].objects.unlink(bpy.data.objects[object_in_lod_list.name])
                    if not found:
                        object_clean_name = target_name[:-5]
                        print('The object "'+object_clean_name+'" has no '+ LOD_target+" in library")

        return {'FINISHED'}


class OBJECT_OT_changemeshLOD(bpy.types.Operator):
    """Change LOD for selected objects with linked meshes and update object names"""
    bl_idname = "object.change_lod"
    bl_label = "Change LOD"
    bl_options = {"REGISTER", "UNDO"}

    LODS = ["LOD0", "LOD1", "LOD2", "LOD3", "LOD4", "LOD5"]

    def execute(self, context):
        scene = context.scene
        LOD_target = f"LOD{scene.setLODnum}"

        selection = context.selected_objects
        libraries = {obj.data.library.name for obj in selection if obj.type == 'MESH' and obj.data.library}

        for lib_name in libraries:
            self.process_library(lib_name, LOD_target, selection)

        return {'FINISHED'}

    def process_library(self, lib_name, LOD_target, selection):
        library = bpy.data.libraries[lib_name]
        with bpy.data.libraries.load(library.filepath, link=True) as (data_from, data_to):
            data_to.meshes = [name for name in data_from.meshes if name.endswith(LOD_target)]

        for obj in selection:
            if obj.type == 'MESH' and obj.data.library and obj.data.library.name == lib_name:
                current_mesh_name = obj.data.name
                current_LOD = current_mesh_name[-4:]
                if current_LOD in self.LODS and current_LOD != LOD_target:
                    target_mesh_name = current_mesh_name.replace(current_LOD, LOD_target)
                    self.replace_mesh_and_rename_object(obj, target_mesh_name)

    def replace_mesh_and_rename_object(self, obj, target_mesh_name):
        if target_mesh_name in bpy.data.meshes:
            obj.data = bpy.data.meshes[target_mesh_name]
            # Rinomina l'oggetto per corrispondere al nome della nuova mesh
            obj.name = target_mesh_name
            self.report({'INFO'}, f"Object and mesh updated to {target_mesh_name}")
        else:
            self.report({'WARNING'}, f"Mesh {target_mesh_name} not found in library")

    @classmethod
    def poll(cls, context):
        return context.selected_objects and any(obj.type == 'MESH' and obj.data.library for obj in context.selected_objects)



class OBJECT_OT_open_linked_file(bpy.types.Operator):
    """Open the .blend file containing the linked mesh or object of the active object in a new Blender instance"""
    bl_idname = "object.open_linked_file"
    bl_label = "Open Linked File in New Instance"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj and (obj.library or (obj.data and obj.data.library))

    def execute(self, context):
        obj = context.active_object
        
        if obj.library:
            linked_file = obj.library.filepath
        elif obj.data and obj.data.library:
            linked_file = obj.data.library.filepath
        else:
            self.report({'ERROR'}, "No linked file found for the active object.")
            return {'CANCELLED'}

        # Ensure the file path is absolute
        linked_file = bpy.path.abspath(linked_file)

        if not os.path.exists(linked_file):
            self.report({'ERROR'}, f"Linked file not found: {linked_file}")
            return {'CANCELLED'}

        # Get the path to the Blender executable
        blender_exe = bpy.app.binary_path

        # Open the linked file in a new Blender instance
        try:
            subprocess.Popen([blender_exe, linked_file])
            self.report({'INFO'}, f"Opened linked file in new Blender instance: {linked_file}")
        except Exception as e:
            self.report({'ERROR'}, f"Failed to open new Blender instance: {str(e)}")
            return {'CANCELLED'}

        return {'FINISHED'}


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

        col = split.column(align=True)
        col.operator("object.change_lod", text='set mesh LOD')

        row = layout.row()
        row.operator("object.open_linked_file", text='Open linked source')
  

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
            col.prop(scene, 'LOD_pad_on', text="Pad")
            col = split.column(align=True)
            col.prop(scene, 'LOD_use_scene_settings', text="Scene light")
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
            row.prop(context.scene, 'model_export_dir', toggle = True, text='folder')
            self.layout.operator("exportfbx.grouplod", icon="MESH_GRID", text='FBX')

class VIEW3D_PT_LODgenerator(Panel, ToolsPanelLODgenerator):
    bl_category = "3DSC"
    bl_idname = "VIEW3D_PT_LODgenerator"
    bl_context = "objectmode"

class VIEW3D_PT_LODmanager(Panel, ToolsPanelLODmanager):
    bl_category = "3DSC"
    bl_idname = "VIEW3D_PT_LODmanager"
    bl_context = "objectmode"


classes = [
    OBJECT_OT_changemeshLOD,
    OBJECT_OT_changeLOD,
    OBJECT_OT_CreateGroupsLOD,
    OBJECT_OT_RemoveGroupsLOD,
    OBJECT_OT_ExportGroupsLOD,
    OBJECT_OT_LOD,
    OBJECT_OT_LOD0,
    VIEW3D_PT_LODgenerator,
    VIEW3D_PT_LODmanager,
    OBJECT_OT_open_linked_file
]

def register():
    for cls in classes:
        bpy.utils.register_class(cls)

    bpy.types.Scene.setLODnum = bpy.props.IntProperty(name="LOD Level", default=0, min=0, max=5)

    bpy.types.Scene.LODnum = IntProperty(
        name = "LODs",
        default = 1,
        min = 1,
        max = 5,
        description = "Enter desired number of LOD (Level of Detail)"
        )

    bpy.types.Scene.LOD1_tex_res = IntProperty(
        name = "Resolution Texture of the LOD1",
        default = 2048,
        description = "Enter the resolution for the texture of the LOD1")

    bpy.types.Scene.LOD2_tex_res = IntProperty(
        name = "Resolution Texture of the LOD2",
        default = 512,
        description = "Enter the resolution for the texture of the LOD2"
        )

    bpy.types.Scene.LOD3_tex_res = IntProperty(
        name = "Resolution Texture of the LOD3",
        default = 128,
        description = "Enter the resolution for the texture of the LOD3"
        )

    bpy.types.Scene.LOD_pad_on = BoolProperty(
        name = "Padding ratio of the LOD",
        default = True,
        description = "Enter the paddin ratio for the LOD"
        )

    bpy.types.Scene.LOD_use_scene_settings = BoolProperty(
        name = "Using scene settings for bake LOD",
        default = False,
        description = "Enter the paddin ratio for the LOD"
        )


def unregister():
    for cls in classes:
        bpy.utils.unregister_class(cls)
    del bpy.types.Scene.setLODnum
    del bpy.types.Scene.LODnum
    del bpy.types.Scene.LOD1_tex_res
    del bpy.types.Scene.LOD2_tex_res
    del bpy.types.Scene.LOD3_tex_res
    del bpy.types.Scene.LOD1_dec_ratio
    del bpy.types.Scene.LOD2_dec_ratio
    del bpy.types.Scene.LOD3_dec_ratio
    del bpy.types.Scene.LOD_pad_on
    del bpy.types.Scene.LOD_use_scene_settings


if __name__ == "__main__":
    register()