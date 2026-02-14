import bpy
from . import (
    report_data,
)
import bmesh
from .functions import *
from bpy.types import Operator
import math

from bpy_extras.io_utils import ExportHelper


class MESH_OT_info_area(Operator):
    bl_idname = "mesh.info_area"
    bl_label = "Info Area"
    bl_description = "report the surface area of the active mesh"

    # @classmethod
    # def poll(cls, context):
    #     obj = context.active_object
    #     return obj is not None and obj.type == 'MESH' #and obj.mode in {'OBJECT', 'EDIT'}

    def execute(self, context):
        selected = [obj for obj in context.selected_objects if obj.type == 'MESH']
        if not selected and context.active_object and context.active_object.type == 'MESH':
            selected = [context.active_object]
        if not selected:
            self.report({'ERROR'}, "Select at least one mesh object")
            return {'CANCELLED'}
        info = []
        total_area = 0.0
        tot_polynum = 0.0

        for obj in selected:
            area = calc_area(obj)
            total_area = total_area + area
            polynum = len(obj.data.polygons)
            tot_polynum = tot_polynum + polynum
            
        area_fmt = check_unit_system_area(total_area)

        info.append((f"Area: {round(total_area,1)}²", None))
        info.append((f"Polygons: {str(tot_polynum)}", None))
        report_data.update(*info)
        return {'FINISHED'}

def tex_num_calc(x_res_a_terra,tex,ratio):
    #x_res_a_terra = 12
    #tex = 4096
    #ratio = 0.6
    numtex = pow((10000 / x_res_a_terra), 2) / (tex*tex*ratio) #10066329.6
    print(str(numtex))
    numtex_round = round(numtex,0)
    print(str(numtex_round))
    if numtex_round == 0:
        fact = 1/numtex
        texnum_def = 1
    else:
        fact = numtex/numtex_round
        texnum_def = numtex_round
    print(str(fact))
    mq_corretto = round(100*fact,1)
    print("Alla risoluzione di "+str(x_res_a_terra)+" px/mm, servono "+str(texnum_def)+" texture "+str(tex)+" pxs. per "+str(mq_corretto)+" m2")
    return texnum_def, mq_corretto, 

def calc_area(obj):
    bm = bmesh_copy_from_object(obj, apply_modifiers=True)
    area = bmesh_calc_area(bm)
    bm.free()
    return area

def check_unit_system_area(total_area):

    unit = bpy.context.scene.unit_settings
    scale = 1.0 if unit.system == 'NONE' else unit.scale_length

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
    return area_fmt

class MESH_OT_info_texs(Operator):
    bl_idname = "mesh.info_texs"
    bl_label = "Info Textures"
    bl_description = "report the texture area of the selected meshes"

    def execute(self, context):
        selected = [obj for obj in context.selected_objects if obj.type == 'MESH']
        if not selected and context.active_object and context.active_object.type == 'MESH':
            selected = [context.active_object]
        if not selected:
            self.report({'ERROR'}, "Select at least one mesh object")
            return {'CANCELLED'}
        scene = context.scene
        strict = bool(getattr(scene, "e3dsc_stats_strict", False))

        scene.analysis_list.clear()
        resolution_map = {}
        material_count = 0
        missing_materials = 0
        missing_textures = 0

        for ob in selected:
            tex_stats = info_textures(context, ob)
            material_count += tex_stats["material_count"]
            missing_materials += tex_stats["missing_materials"]
            missing_textures += tex_stats["materials_without_textures"]
            for res_tex, count in tex_stats["res_map"].items():
                resolution_map[res_tex] = resolution_map.get(res_tex, 0) + count

        if strict and (missing_materials > 0 or missing_textures > 0):
            self.report(
                {'ERROR'},
                f"Strict mode: missing materials={missing_materials}, materials without textures={missing_textures}"
            )
            return {'CANCELLED'}

        for res_tex in sorted(resolution_map.keys()):
            scene.analysis_list.add()
            idx = len(scene.analysis_list) - 1
            scene.analysis_list[idx].res_tex = int(res_tex)
            scene.analysis_list[idx].res_counter = int(resolution_map[res_tex])

        info = []
        info.append((f" {len(selected)} object(s); {material_count} mats;", None))
        for res_out in range(len(scene.analysis_list)):
            info.append((f"Tex. {scene.analysis_list[res_out].res_tex}: {scene.analysis_list[res_out].res_counter}", None))
        if missing_materials > 0 or missing_textures > 0:
            info.append((f"Skipped: no material={missing_materials}, no texture={missing_textures}", None))
        report_data.update(*info)

        return {'FINISHED'}

def info_textures(context, ob):
    result = {
        "material_count": 0,
        "missing_materials": 0,
        "materials_without_textures": 0,
        "res_map": {},
        "object_res_tex": 0,
        "object_tex_count": 0,
    }
    if ob is None or ob.type != 'MESH':
        return result

    if len(ob.material_slots) == 0:
        result["missing_materials"] += 1
        return result

    max_res = 0
    tex_nodes_count = 0
    for slot in ob.material_slots:
        result["material_count"] += 1
        mat = slot.material
        if mat is None or not mat.use_nodes or mat.node_tree is None:
            result["missing_materials"] += 1
            continue

        has_image_node = False
        for node in mat.node_tree.nodes:
            if node.type == 'TEX_IMAGE' and node.image is not None:
                has_image_node = True
                size = int(node.image.size[0]) if node.image.size else 0
                if size > 0:
                    result["res_map"][size] = result["res_map"].get(size, 0) + 1
                    max_res = max(max_res, size)
                    tex_nodes_count += 1
        if not has_image_node:
            result["materials_without_textures"] += 1

    result["object_res_tex"] = max_res
    result["object_tex_count"] = tex_nodes_count
    return result

class MESH_OT_info_texres(Operator):
    bl_idname = "mesh.info_texres"
    bl_label = "Info Texture resolution"
    bl_description = "report the mean texture resolution of the selected meshes"

    def execute(self, context):
        selected = [obj for obj in context.selected_objects if obj.type == 'MESH']
        if not selected and context.active_object and context.active_object.type == 'MESH':
            selected = [context.active_object]
        if not selected:
            self.report({'ERROR'}, "Select at least one mesh object")
            return {'CANCELLED'}
        scene = context.scene
        strict = bool(getattr(scene, "e3dsc_stats_strict", False))
        prompt_export = bool(getattr(scene, "e3dsc_stats_prompt_export", False))
        total_area = 0.0
        total_polynum = 0
        info = []

        #analyze textures setup
        scene.analysis_list.clear()
        scene.statistics_list.clear()
        self.ob_count = 0

        #extract statistics setup
        texture_area = 0.0
        resolution_map = {}
        material_count = 0
        missing_materials = 0
        missing_textures = 0

        #calculate area
        for obj in selected:
            area = calc_area(obj)
            polynum = len(obj.data.polygons)
            total_area = total_area + area
            total_polynum = total_polynum + polynum
            
            #analyze textures
            tex_stats = info_textures(context, obj)
            material_count += tex_stats["material_count"]
            missing_materials += tex_stats["missing_materials"]
            missing_textures += tex_stats["materials_without_textures"]
            for res_tex, count in tex_stats["res_map"].items():
                resolution_map[res_tex] = resolution_map.get(res_tex, 0) + count

            context.scene.statistics_list.add()
            context.scene.statistics_list[self.ob_count].name = obj.name
            context.scene.statistics_list[self.ob_count].area_mesh = area
            context.scene.statistics_list[self.ob_count].poly_num = polynum
            context.scene.statistics_list[self.ob_count].poly_res = (polynum / area) if area > 0 else 0
            context.scene.statistics_list[self.ob_count].res_tex = tex_stats["object_res_tex"]
            context.scene.statistics_list[self.ob_count].res_counter = tex_stats["object_tex_count"]
            context.scene.statistics_list[self.ob_count].uv_ratio = 0.6
            if area > 0 and tex_stats["object_res_tex"] > 0 and tex_stats["object_tex_count"] > 0:
                context.scene.statistics_list[self.ob_count].mean_res_tex = 1000 / (
                    math.sqrt((tex_stats["object_res_tex"] * tex_stats["object_res_tex"] * tex_stats["object_tex_count"] * 0.6) / area)
                )
            else:
                context.scene.statistics_list[self.ob_count].mean_res_tex = 0
            
            self.ob_count +=1

        if strict and (missing_materials > 0 or missing_textures > 0):
            self.report(
                {'ERROR'},
                f"Strict mode: missing materials={missing_materials}, materials without textures={missing_textures}"
            )
            return {'CANCELLED'}

        for res_tex in sorted(resolution_map.keys()):
            scene.analysis_list.add()
            idx = len(scene.analysis_list) - 1
            scene.analysis_list[idx].res_tex = int(res_tex)
            scene.analysis_list[idx].res_counter = int(resolution_map[res_tex])

        area_fmt = check_unit_system_area(total_area)          
        info.append((f"Area tot: {round(total_area,1)}²", None))
        info.append((f"Polygons tot: {total_polynum}", None))
            
        info.append((f" {len(selected)} object(s); {material_count} mats;",None))
        for res_out in range(len(scene.analysis_list)):
            info.append((f"Tex. {scene.analysis_list[res_out].res_tex}: {scene.analysis_list[res_out].res_counter}", None))

        for unit in scene.analysis_list:
            res_unit_area = unit.res_tex * unit.res_tex * unit.res_counter * 0.6
            texture_area = texture_area + res_unit_area
        texture_area = 1000/(math.sqrt(texture_area/total_area)) if texture_area > 0 and total_area > 0 else 0
        mean_poly = total_polynum/total_area if total_area > 0 else 0
        info.append((f"Mean resolution ", None))
        info.append((f"- Tex: "+str(round(texture_area,2))+" mm/pixel", None))
        info.append((f"- Poly: "+str(round(mean_poly,1))+" poly/m²", None))
        if missing_materials > 0 or missing_textures > 0:
            info.append((f"Skipped: no material={missing_materials}, no texture={missing_textures}", None))
        report_data.update(*info)
        if prompt_export:
            bpy.ops.export_stats.tofile('INVOKE_DEFAULT')

        return {'FINISHED'}

class ExportStatistics(Operator, ExportHelper):
    """This appears in the tooltip of the operator and in the generated docs"""
    bl_idname = "export_stats.tofile"  # important since its how bpy.ops.import_test.some_data is constructed
    bl_label = "Export statistics to file"

    # ExportHelper mixin class uses this
    filename_ext = ".csv"

    filter_glob: StringProperty(
            default="*.csv",
            options={'HIDDEN'},
            maxlen=255,  # Max internal buffer length, longer would be clamped.
            )

    # List of operator properties, the attributes will be assigned
    # to the class instance from the operator settings before calling.

    groups: BoolProperty(
            name="add collection name",
            description="Add collection name from viewport (usefull to cluser grooups)",
            default=True,
            )

    @classmethod
    def poll(cls, context):
        return hasattr(context.scene, "statistics_list") and len(context.scene.statistics_list) > 0

    def execute(self, context):
        return write_stats_on_disk(context, self.filepath, self.groups)

def write_stats_on_disk(context, filepath, groups):
    print("writing statistics data on disk...")
    
    f = open(filepath, 'w', encoding='utf-8')
    cnt = 0
    stlst = context.scene.statistics_list
    # write selected objects coordinate
    f.write("%s; %s; %s; %s; %s; %s; %s; %s\n" % ("name", "area mesh", "tris number", "tris/m", "tex res", "tex n.", "uv ratio", "pixel/mm"))
    while cnt < len(stlst):
        f.write("%s; %s; %s; %s; %s; %s; %s; %s\n" % (stlst[cnt].name, round(stlst[cnt].area_mesh,2), round(stlst[cnt].poly_num,2), round(stlst[cnt].poly_res,2), stlst[cnt].res_tex, stlst[cnt].res_counter, round(stlst[cnt].uv_ratio,1), round(stlst[cnt].mean_res_tex,2)))
        cnt +=1
    f.close()    

    return {'FINISHED'}
