import bpy
from . import (
    report_data,
)
import bmesh
from .functions import *
from bpy.types import Operator
import math

class MESH_OT_info_area(Operator):
    bl_idname = "mesh.info_area"
    bl_label = "Info Area"
    bl_description = "report the surface area of the active mesh"

    # @classmethod
    # def poll(cls, context):
    #     obj = context.active_object
    #     return obj is not None and obj.type == 'MESH' #and obj.mode in {'OBJECT', 'EDIT'}

    def execute(self, context):
        scene = context.scene
        unit = scene.unit_settings
        scale = 1.0 if unit.system == 'NONE' else unit.scale_length
        context.active_object.select_set(True) 
        selected = context.selected_objects
        total_area = 0.0

        for obj in selected:
            #obj = context.active_object

            bm = bmesh_copy_from_object(obj, apply_modifiers=True)
            area = bmesh_calc_area(bm)
            total_area = total_area + area
            bm.free()

        if unit.system == 'METRIC':
            #area_cm = area * (scale ** 2.0) / (0.01 ** 2.0)
            area_cm = total_area# * (scale ** 2.0) / (0.01 ** 2.0)
            #area_fmt = "{} cm".format(clean_float(f"{area_cm:.4f}"))
            area_fmt = "{} m".format(clean_float(f"{area_cm:.4f}"))
        elif unit.system == 'IMPERIAL':
            area_inch = area * (scale ** 2.0) / (0.0254 ** 2.0)
            area_fmt = '{} "'.format(clean_float(f"{area_inch:.4f}"))
        else:
            area_fmt = clean_float(f"{total_area:.8f}")

        report_data.update((f"Area: {area_fmt}²", None))

        return {'FINISHED'}

class MESH_OT_info_texs(Operator):
    bl_idname = "mesh.info_texs"
    bl_label = "Info Textures"
    bl_description = "report the texture area of the selected meshes"

    def execute(self, context):
        context.active_object.select_set(True) 
        selected = context.selected_objects
        scene = context.scene
        scene.analysis_list.clear()
        material_count = 0
        res_count = 0

        for ob in selected:
            #print(ob.name)
            for mat in ob.material_slots:
                material_count += 1
                #print(mat.material.name)
                for node in mat.material.node_tree.nodes:
                    # decisamente da rendere più robusto prendendo il codice dall'addon emtools
                    if node.type == 'TEX_IMAGE':
                        image_size = node.image.size[0]
                        #for current_res in range(len(scene.analysis_list)):
                        if res_count == 0:
                            context.scene.analysis_list.add()
                            context.scene.analysis_list[res_count].res_tex = image_size
                            context.scene.analysis_list[res_count].res_counter += 1
                            res_count +=1
                        else:
                            for current_res in range(len(scene.analysis_list)):
                                if scene.analysis_list[current_res].res_tex == image_size:
                                    context.scene.analysis_list[current_res].res_counter += 1
                                else:
                                    context.scene.analysis_list.add()
                                    res_count = len(context.scene.analysis_list)-1
                                    context.scene.analysis_list[res_count].res_tex = image_size
                                    context.scene.analysis_list[res_count].res_counter += 1

        info = []
        #print("Ci sono "+ str(len(selected))+ " oggetti, con "+ str(material_count) +" materiali, di cui " +str(tex_list_512)+" con textures 512 px e "+str(tex_list_1024)+" con textures 1024 px e "+str(tex_list_2048)+" con textures 2048 px e "+ str(tex_list_4096)+" con textures 4096 px" )
        info.append((f" "+str(len(selected))+" object(s); " + str(material_count) +" mats;",None))       
        for res_out in range(len(scene.analysis_list)):
            #print("Resolution "+str(scene.analysis_list[res_out].res_tex)+" has "+str(scene.analysis_list[res_out].res_counter)+" instances")
            info.append((f"Tex. "+str(scene.analysis_list[res_out].res_tex)+": "+str(scene.analysis_list[res_out].res_counter), None))
        report_data.update(*info)
        #report_data.update((f" "+str(len(selected))+" ob; " + str(material_count) +" mats; 512: " +str(tex_list_512)+"; 1024: "+str(tex_list_1024)+"; 2048: "+str(tex_list_2048)+"; 4096: "+ str(tex_list_4096), None))

        return {'FINISHED'}

class MESH_OT_info_texres(Operator):
    bl_idname = "mesh.info_texres"
    bl_label = "Info Texture resolution"
    bl_description = "report the mean texture resolution of the selected meshes"

    def execute(self, context):
        context.active_object.select_set(True) 
        selected = context.selected_objects
        scene = context.scene
        tot_area = 100
        texture_area = 0.0
        for unit in context.scene.analysis_list:
            res_unit_area = unit.res_tex * unit.res_tex * unit.res_counter * 0.6
            texture_area = texture_area + res_unit_area
        texture_area = 1000/(math.sqrt(texture_area/tot_area))
        #print(str(texture_area))
        report_data.update((f"Mean res : "+str(texture_area)+" mm/pixel", None))
        return {'FINISHED'}