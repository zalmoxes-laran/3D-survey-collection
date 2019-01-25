import bpy
import os
import time
from .functions import *
from mathutils import Vector

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
    bl_idname = "lod0.b2osg"
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
                mesh = obj.data
                mesh.uv_layers.active_index = 0
                multitex_uvmap = mesh.uv_layers.active
                multitex_uvmap_name = multitex_uvmap.name
                multitex_uvmap.name = 'MultiTex'
                atlas_uvmap = mesh.uv_layers.new()
                atlas_uvmap.name = 'Atlas'
                mesh.uv_layers.active_index = 1
                bpy.ops.object.editmode_toggle()
                bpy.ops.mesh.select_all(action='SELECT')
                bpy.ops.mesh.remove_doubles()
                bpy.ops.uv.select_all(action='SELECT')
                bpy.ops.uv.pack_islands(margin=0.001)
                bpy.ops.object.editmode_toggle()
                mesh.uv_layers.active_index = 0

        return {'FINISHED'}

#_____________________________________________________________________________

class OBJECT_OT_BAKE(bpy.types.Operator):
    bl_idname = "bake.b2osg"
    bl_label = "bake"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        context = bpy.context
        start_time = time.time()
        basedir = os.path.dirname(bpy.data.filepath)
        subfolder = 'BAKE'
        if not os.path.exists(os.path.join(basedir, subfolder)):
            os.mkdir(os.path.join(basedir, subfolder))
            print('There is no BAKE folder. Creating one...')
        else:
            print('Found previously created BAKE folder. I will use it')
        if not basedir:
            raise Exception("Save the blend file")

        ob_counter = 1
        ob_tot = len(bpy.context.selected_objects)
        print('<<<<<<<<<<<<<< CREATION OF BAKE >>>>>>>>>>>>>>')
        print('>>>>>> '+str(ob_tot)+' objects will be processed')

        for obj in bpy.context.selected_objects:
            obj.data.uv_layers["MultiTex"].active_render = True
            start_time_ob = time.time()
            print('>>> BAKE >>>')
            print('>>>>>> processing the object ""'+ obj.name+'"" ('+str(ob_counter)+'/'+str(ob_tot)+')')
            bpy.ops.object.select_all(action='DESELECT')
            obj.select_set(True)
            bpy.context.view_layer.objects.active = obj
            baseobjwithlod = obj.name
            if '_LOD0' in baseobjwithlod:
                baseobj = baseobjwithlod.replace("_LOD0", "")
            else:
                baseobj = baseobjwithlod
            print('Creating new BAKE object..')
            bpy.ops.object.duplicate_move(OBJECT_OT_duplicate={"linked":False, "mode":'TRANSLATION'}, TRANSFORM_OT_translate={"value":(0, 0, 0), "constraint_axis":(False, False, False), "constraint_orientation":'GLOBAL', "mirror":False, "proportional":'DISABLED', "proportional_edit_falloff":'SMOOTH', "proportional_size":1, "snap":False, "snap_target":'CLOSEST', "snap_point":(0, 0, 0), "snap_align":False, "snap_normal":(0, 0, 0), "gpencil_strokes":False, "texture_space":False, "remove_on_cancel":False, "release_confirm":False})

            for obj in bpy.context.selected_objects:
                obj.name = baseobj + "_BAKE"
                newobj = obj
            for obj in bpy.context.selected_objects:
                lod1name = obj.name
            for i in range(0,len(bpy.data.objects[lod1name].material_slots)):
                bpy.ops.object.material_slot_remove()

            if obj.data.uv_layers[1] and obj.data.uv_layers[1].name =='Atlas':
                print('Found Atlas UV mapping layer. I will use it.')
                uv_layers = obj.data.uv_layers
                uv_layers = obj.data.uv_layers
                uv_layers.remove(uv_layers[0])
            else:
                print('Creating new UV mapping layer.')
                bpy.ops.object.editmode_toggle()
                bpy.ops.mesh.select_all(action='SELECT')
                bpy.ops.mesh.remove_doubles()
                bpy.ops.uv.select_all(action='SELECT')
                bpy.ops.uv.pack_islands(margin=0.001)
                bpy.ops.object.editmode_toggle()

#            decimate_mesh(context,obj,0.5,'BAKE')


    # procedura di semplificazione mesh
    
    # ora mesh semplificata
    #------------------------------------------------------------------


            bpy.ops.object.select_all(action='DESELECT')
            oggetto = bpy.data.objects[lod1name]
            oggetto.select = True
            print('Creating new texture atlas for BAKE....')

            tempimage = bpy.data.images.new(name=lod1name, width=2048, height=2048, alpha=False)
            tempimage.filepath_raw = "//"+subfolder+'/'+lod1name+".jpg"
            tempimage.file_format = 'JPEG'

            for uv_face in oggetto.data.uv_layers.active.data:
                uv_face.image = tempimage

            #--------------------------------------------------------------
            print('Passing color data from original to BAKE...')
            bpy.context.scene.render.engine = 'BLENDER_RENDER'
            bpy.context.scene.render.use_bake_selected_to_active = True
            bpy.context.scene.render.bake_type = 'TEXTURE'

            object = bpy.data.objects[baseobjwithlod]
            object.select = True

            bpy.context.scene.objects.active = bpy.data.objects[lod1name]
            #--------------------------------------------------------------

            bpy.ops.object.bake_image()
            tempimage.save()

            print('Creating custom material for BAKE...')
            bpy.ops.object.select_all(action='DESELECT')
            oggetto = bpy.data.objects[lod1name]
            oggetto.select = True
            bpy.context.scene.objects.active = oggetto
            bpy.ops.view3d.texface_to_material()
            oggetto.active_material.name = 'M_'+ oggetto.name
            oggetto.data.name = 'SM_' + oggetto.name
    #        basedir = os.path.dirname(bpy.data.filepath)

            print('Saving on obj/mtl file for BAKE...')
            activename = bpy.path.clean_name(bpy.context.scene.objects.active.name)
            fn = os.path.join(basedir, subfolder, activename)
            bpy.ops.export_scene.obj(filepath=fn + ".obj", use_selection=True, axis_forward='Y', axis_up='Z', path_mode='RELATIVE')

            bpy.ops.object.move_to_layer(layers=(False, False, False, False, False, False, False, False, False, False, False, True, False, False, False, False, False, False, False, False))
            print('>>> "'+obj.name+'" ('+str(ob_counter)+'/'+ str(ob_tot) +') object baked in '+str(time.time() - start_time_ob)+' seconds')
            ob_counter += 1

        bpy.context.scene.layers[11] = True
        bpy.context.scene.layers[0] = False
        end_time = time.time() - start_time
        print('<<<<<<< Process done >>>>>>')
        print('>>>'+str(ob_tot)+' objects processed in '+str(end_time)+' seconds')
        return {'FINISHED'}

        return {'FINISHED'}


#_____________________________________________________________________________


def ratio_for_current_lod(lod,context):
    if lod == 1:
        ratio = context.scene.LOD1_dec_ratio
    if lod == 2:
        ratio = context.scene.LOD2_dec_ratio
    return ratio

def tex_res_for_current_lod(lod,context):
    if lod == 1:
        tex_res = context.scene.LOD1_tex_res
    if lod == 2:
        tex_res = context.scene.LOD2_tex_res
    return tex_res

class OBJECT_OT_LOD(bpy.types.Operator):
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

        basedir = os.path.dirname(bpy.data.filepath)
        if not basedir:
            raise Exception("Save the blend file")
        # si prende il numero di LOD impostato e i parametri base per LOD ovvero tex_res e decimation_ratio
        # iniziamo con un contatore i_lodbake_counter che parte da 0
        
        print("Number of LOD(s) to be created is: " + str(LODnum))

        # si producono ciclicamente i livelli di dettaglio ad esaurire i LOD richiesti dall'utente nell'UI (normalmente da 1 a 3 LOD)
        while i_lodbake_counter <= LODnum:
            currentLOD = 'LOD' + str(i_lodbake_counter)
            subfolder = currentLOD
            #print(subfolder)
            
            if not os.path.exists(os.path.join(basedir, subfolder)):
                os.mkdir(os.path.join(basedir, subfolder))
                print('There is no '+ subfolder +' folder. Creating one...')
            else:
                print('Found previously created '+ subfolder +' folder. I will use it')

            ob_counter = 1
            
            print('<<<<<<<<<<<<<< CREATION OF '+ currentLOD +' >>>>>>>>>>>>>>')
            print('>>>>>> '+str(ob_tot)+' objects will be processed')

            for obj_LOD0 in selected_objects:
                
                #da ricontrollare !!!!!!!!!!!!!!!!!!!!!!!!!!
                obj_LOD0.data.uv_layers["MultiTex"].active_render = True
                #da ricontrollare !!!!!!!!!!!!!!!!!!!!!!!!!!
                
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
                bpy.ops.object.duplicate_move(OBJECT_OT_duplicate={"linked":False, "mode":'TRANSLATION'}, TRANSFORM_OT_translate={"value":(0, 0, 0), "constraint_axis":(False, False, False), "constraint_orientation":'GLOBAL', "mirror":False, "proportional":'DISABLED', "proportional_edit_falloff":'SMOOTH', "proportional_size":1, "snap":False, "snap_target":'CLOSEST', "snap_point":(0, 0, 0), "snap_align":False, "snap_normal":(0, 0, 0), "gpencil_strokes":False, "texture_space":False, "remove_on_cancel":False, "release_confirm":False})
                obj_LODnew = context.view_layer.objects.active

                bpy.ops.object.select_all(action='DESELECT')
                context.view_layer.objects.active = obj_LODnew
                obj_LODnew.select_set(True)
                obj_LODnew.name = obj_base_name + "_" + currentLOD
                obj_LODnew_name = obj_LODnew.name
#                print('Il modello appena creato in LOD1 è '+str(obj_LODnew_name))

                for i in range(0,len(bpy.data.objects[obj_LODnew_name].material_slots)):
                    bpy.ops.object.material_slot_remove()

                if obj_LODnew.data.uv_layers[1] and obj_LODnew.data.uv_layers[1].name =='Atlas':
                    print('Found Atlas UV mapping layer. I will use it.')
                    uv_layers = obj_LODnew.data.uv_layers
                    uv_layers = obj_LODnew.data.uv_layers
                    uv_layers.remove(uv_layers[0])
                else:
                    print('Creating new UV mapping layer.')
                    bpy.ops.object.editmode_toggle()
                    bpy.ops.mesh.select_all(action='SELECT')
                    bpy.ops.mesh.remove_doubles()
                    bpy.ops.uv.select_all(action='SELECT')
                    bpy.ops.uv.pack_islands(margin=0.001)
                    bpy.ops.object.editmode_toggle()
                
                # mesh decimation
                decimate_mesh(context,obj_LODnew,ratio_for_current_lod(i_lodbake_counter,context),currentLOD)

        # now the mesh is decimated
        #------------------------------------------------------------------

                #bpy.ops.object.select_all(action='DESELECT')
                #obj_LODnew.select_set(True)
                print('Creating new texture atlas for ' + currentLOD + '....')

                tempimage = bpy.data.images.new(name=lod_obj_name, width=tex_res_for_current_lod(i_lodbake,context), height=tex_res_for_current_lod(context,i_lodbake), alpha=False)
                tempimage.filepath_raw = "//"+subfolder+'/'+lod_obj_name+".jpg"
                tempimage.file_format = 'JPEG'
 #               print('La immagine creata temporanea si chiama: ' + tempimage.name)

                for uv_face in oggetto.data.uv_layers.active.data:
                    uv_face.image = tempimage

                
                #--------------------------------------------------------------
                print('Passing color data from LOD0 to '+ currentLOD + '...')
                bpy.context.scene.render.engine = 'BLENDER_RENDER'
                bpy.context.scene.render.use_bake_selected_to_active = True
                bpy.context.scene.render.bake_type = 'TEXTURE'

                object = bpy.data.objects[baseobjwithlod]
                object.select = True

                bpy.context.scene.objects.active = bpy.data.objects[lod_obj_name]
                #--------------------------------------------------------------

                bpy.ops.object.bake_image()
                tempimage.save()

                print('Creating custom material for '+ currentLOD +'...')
                bpy.ops.object.select_all(action='DESELECT')
                oggetto = bpy.data.objects[lod_obj_name]
                oggetto.select = True
                bpy.context.scene.objects.active = oggetto
                bpy.ops.view3d.texface_to_material()
                oggetto.active_material.name = 'M_'+ oggetto.name
                oggetto.data.name = 'SM_' + oggetto.name
        #        basedir = os.path.dirname(bpy.data.filepath)

                print('Saving on obj/mtl file for '+ currentLOD +'...')
                activename = bpy.path.clean_name(obj_LODnew.name)
                fn = os.path.join(basedir, subfolder, activename)
                bpy.ops.export_scene.obj(filepath=fn + ".obj", use_selection=True, axis_forward='Y', axis_up='Z', path_mode='RELATIVE')

                #bpy.ops.object.move_to_layer(layers=(False, False, False, False, False, False, False, False, False, False, False, True, False, False, False, False, False, False, False, False))
                print('>>> "'+obj_LODnew.name+'" ('+str(ob_counter)+'/'+ str(ob_tot) +') object baked in '+str(time.time() - start_time_ob)+' seconds')
                ob_counter += 1

            i_lodbake_counter += 1
        #context.scene.layers[11] = True
        #context.scene.layers[0] = False
        end_time = time.time() - start_time
        print('<<<<<<< Process done >>>>>>')
        print('>>>'+str(ob_tot)+' objects processed in '+str(end_time)+' seconds')
        return {'FINISHED'}

#______________________________________



class OBJECT_OT_ExportGroupsLOD(bpy.types.Operator):
    bl_idname = "exportfbx.grouplod"
    bl_label = "Export Group LOD"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        start_time = time.time()
        basedir = os.path.dirname(bpy.data.filepath)
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
                    bpy.ops.export_scene.fbx(filepath= fn + ".fbx", check_existing=True, axis_forward='-Z', axis_up='Y', filter_glob="*.fbx", version='BIN7400', ui_tab='MAIN', use_selection=True, global_scale=1.0, apply_unit_scale=True, bake_space_transform=False, object_types={'ARMATURE', 'CAMERA', 'EMPTY', 'LAMP', 'MESH', 'OTHER'}, use_mesh_modifiers=True, mesh_smooth_type='EDGE', use_mesh_edges=False, use_tspace=False, use_custom_props=False, add_leaf_bones=True, primary_bone_axis='Y', secondary_bone_axis='X', use_armature_deform_only=False, bake_anim=True, bake_anim_use_all_bones=True, bake_anim_use_nla_strips=True, bake_anim_use_all_actions=True, bake_anim_force_startend_keying=True, bake_anim_step=1.0, bake_anim_simplify_factor=1.0, use_anim=True, use_anim_action_all=True, use_default_take=True, use_anim_optimize=True, anim_optimize_precision=6.0, path_mode='RELATIVE', embed_textures=False, batch_mode='OFF', use_batch_own_dir=True, use_metadata=True)
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
                global_bbox_center = obj.matrix_world * local_bbox_center
                emptyofname = 'GLOD_' + baseobj
                obempty = bpy.data.objects.new( emptyofname, None )
                bpy.context.scene.objects.link( obempty )
                obempty.empty_draw_size = 2
                obempty.empty_draw_type = 'PLAIN_AXES'
                obempty.location = global_bbox_center
                bpy.ops.object.select_all(action='DESELECT')
                obempty.select = True
                bpy.context.scene.objects.active = obempty
                obempty['fbx_type'] = 'LodGroup'
#                bpy.ops.wm.properties_edit(data_path="object", property="Fbx_Type", value="LodGroup", min=0, max=1, use_soft_limits=False, soft_min=0, soft_max=1, description="")

                num = 0
                child = selectLOD(listobjects, num, baseobj)
                while child is not None:
                    bpy.ops.object.select_all(action='DESELECT')
                    child.select = True
                    obempty.select = True
                    bpy.context.scene.objects.active = obempty
                    bpy.ops.object.parent_set(type='OBJECT', keep_transform=False)
#                    child.parent= obempty
#                    child.location.x = child.location.x - obempty.location.x
#                    child.location.y = child.location.y - obempty.location.y
                    num += 1
                    child = selectLOD(listobjects, num, baseobj)
        return {'FINISHED'}

