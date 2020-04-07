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
