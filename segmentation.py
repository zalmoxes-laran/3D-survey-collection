import bpy
import time
import bmesh
import math
from .functions import *



class OBJECT_OT_setcutter(bpy.types.Operator):
    """Segment (projecting) a series of selected elements using an active mesh"""
    bl_idname = "set.cutter"
    bl_label = "Segment (projecting) a series of selected elements using an active mesh"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        scene = context.scene
        side = int(math.sqrt(scene.TILE_square_meters))
        create_cutter_series("cutter", side, side)
        return {'FINISHED'}

class OBJECT_OT_projectsegmentation(bpy.types.Operator):
    """Segment (projecting) a series of selected elements using an active mesh"""
    bl_idname = "project.segmentation"
    bl_label = "Segment (projecting) a series of selected elements using an active mesh"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        context = bpy.context
        start_time = time.time()
        ob_counter = 1

        data = bpy.data
        ob_cutting = context.active_object
        #ob_cutting = data.objects.get("secante")
        ob_to_cut = context.selected_objects
        ob_tot = (len(ob_to_cut)-1)
        bpy.ops.object.select_all(action='DESELECT')
        for ob in ob_to_cut:
            if ob == ob_cutting:
                pass
            else:
                start_time_ob = time.time()
                print('>>> CUTTING >>>')
                print('>>>>>> the object is going to be cutted: ""' +
                      ob.name+'"" ('+str(ob_counter)+'/'+str(ob_tot)+')')
                ob_cutting.select_set(True)
                #context.scene.objects.active = ob
                context.view_layer.objects.active = ob
                ob.select_set(True)
                bpy.ops.object.editmode_toggle()
                bpy.ops.mesh.knife_project(cut_through=True)
                try:
                    bpy.ops.mesh.separate(type='SELECTED')
                except:
                    pass
                bpy.ops.mesh.select_all(action='DESELECT')
                bpy.ops.object.editmode_toggle()
                print('>>> "'+ob.name+'" ('+str(ob_counter)+'/' + str(ob_tot) +
                      ') object cutted in '+str(time.time() - start_time_ob)+' seconds')
                ob_counter += 1
                bpy.ops.object.select_all(action='DESELECT')
        end_time = time.time() - start_time
        print('<<<<<<< Process done >>>>>>')
        print('>>>'+str(ob_tot)+' objects processed in '+str(end_time)+' seconds')
        return {'FINISHED'}


class OBJECT_OT_projectsegmentationinversed(bpy.types.Operator):
    """Segment (projecting) an active mesh using a series of selected elements"""
    bl_idname = "project.segmentationinv"
    bl_label = "Segment (projecting) an active mesh using a series of selected elements"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        context = bpy.context
        start_time = time.time()
        ob_counter = 1
        data = bpy.data
        ob_to_cut = context.active_object
        #ob_cutting = data.objects.get("secante")
        ob_cutting = context.selected_objects
        ob_tot = (len(ob_cutting)-1)
        bpy.ops.object.select_all(action='DESELECT')

        for ob in ob_cutting:
            if ob == ob_to_cut:
                pass
            else:
                start_time_ob = time.time()
                print('>>> CUTTING >>>')
                print('>>>>>> the object "' + ob.name + '" ('+str(ob_counter) +
                      '/'+str(ob_tot)+') is cutting the object' + ob_to_cut.name)
                
                #context.scene.objects.active = ob_to_cut
                context.view_layer.objects.active = ob_to_cut
                ob_to_cut.select_set(True)
                bpy.ops.object.editmode_toggle()
                ob.select_set(True)
                bpy.ops.mesh.knife_project(cut_through=True)
                try:
                    bpy.ops.mesh.separate(type='SELECTED')
                except:
                    pass
                bpy.ops.mesh.select_all(action='DESELECT')
                bpy.ops.object.editmode_toggle()
                print('>>> "'+ob.name+'" ('+str(ob_counter)+'/' + str(ob_tot) +
                      ') object used to cut in '+str(time.time() - start_time_ob)+' seconds')
                ob_counter += 1
                bpy.ops.object.select_all(action='DESELECT')
        end_time = time.time() - start_time
        print('<<<<<<< Process done >>>>>>')
        print('>>>'+str(ob_tot)+' objects processed in '+str(end_time)+' seconds')
        return {'FINISHED'}
