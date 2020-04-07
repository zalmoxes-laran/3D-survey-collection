import bpy
from . import (
    report_data,
)
import bmesh
from .functions import *
from bpy.types import Operator

class MESH_OT_info_area(Operator):
    bl_idname = "mesh.info_area"
    bl_label = "Info Area"
    bl_description = "report the surface area of the active mesh"

    def execute(self, context):
        scene = context.scene
        unit = scene.unit_settings
        scale = 1.0 if unit.system == 'NONE' else unit.scale_length
        
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
            area_fmt = clean_float(f"{area:.8f}")

        report_data.update((f"Area: {area_fmt}²", None))

        return {'FINISHED'}

class MESH_OT_info_texs(Operator):
    bl_idname = "mesh.info_texs"
    bl_label = "Info Textures"
    bl_description = "report the texture area of the selected meshes"

    def execute(self, context):
        
        selected = context.selected_objects

        tex_list_4096 = 0
        tex_list_2048 = 0
        tex_list_1024 = 0
        tex_list_512 = 0
        material_count = 0

        for ob in selected:
            #print(ob.name)
            for mat in ob.material_slots:
                material_count += 1
                #print(mat.material.name)
                for node in mat.material.node_tree.nodes:
                    if node.type == 'TEX_IMAGE':
                        image_size = node.image.size[0]
                        if image_size == 512:
                            tex_list_512 += 1
                        if image_size == 1024:
                            tex_list_1024 += 1
                        if image_size == 2048:
                            tex_list_2048 += 1
                        if image_size == 4096:
                            tex_list_4096 += 1

        print("Ci sono "+ str(len(selected))+ " oggetti, con "+ str(material_count) +" materiali, di cui " +str(tex_list_512)+" con textures 512 px e "+str(tex_list_1024)+" con textures 1024 px e "+str(tex_list_2048)+" con textures 2048 px e "+ str(tex_list_4096)+" con textures 4096 px" )


        #report_data.update((f"Area: {area_fmt}²", None))

        return {'FINISHED'}
