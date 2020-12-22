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
        #scene = context.scene
        context.active_object.select_set(True) 
        selected = context.selected_objects
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
        context.active_object.select_set(True) 
        selected = context.selected_objects
        scene = context.scene

        scene.analysis_list.clear()
        self.res_count = 0
        self.material_count = 0

        for ob in selected:
            res_tex, res_count = info_textures(self, context, ob)

        info = []
        #print("Ci sono "+ str(len(selected))+ " oggetti, con "+ str(material_count) +" materiali, di cui " +str(tex_list_512)+" con textures 512 px e "+str(tex_list_1024)+" con textures 1024 px e "+str(tex_list_2048)+" con textures 2048 px e "+ str(tex_list_4096)+" con textures 4096 px" )
        info.append((f" "+str(len(selected))+" object(s); " + str(self.material_count) +" mats;",None))       
        for res_out in range(len(scene.analysis_list)):
            #print("Resolution "+str(scene.analysis_list[res_out].res_tex)+" has "+str(scene.analysis_list[res_out].res_counter)+" instances")
            info.append((f"Tex. "+str(scene.analysis_list[res_out].res_tex)+": "+str(scene.analysis_list[res_out].res_counter), None))
        report_data.update(*info)
        #report_data.update((f" "+str(len(selected))+" ob; " + str(material_count) +" mats; 512: " +str(tex_list_512)+"; 1024: "+str(tex_list_1024)+"; 2048: "+str(tex_list_2048)+"; 4096: "+ str(tex_list_4096), None))

        return {'FINISHED'}

def info_textures(self, context, ob):
    #print(ob.name)
    scene = context.scene
    for mat in ob.material_slots:
        self.material_count += 1
        #print(mat.material.name)
        for node in mat.material.node_tree.nodes:
            # decisamente da rendere più robusto prendendo il codice dall'addon emtools
            if node.type == 'TEX_IMAGE':
                image_size = node.image.size[0]
                #for current_res in range(len(scene.analysis_list)):
                if self.res_count == 0:
                    context.scene.analysis_list.add()
                    context.scene.analysis_list[self.res_count].res_tex = image_size
                    context.scene.analysis_list[self.res_count].res_counter += 1
                    self.res_count +=1
                else:
                    for current_res in range(len(scene.analysis_list)):
                        if scene.analysis_list[current_res].res_tex == image_size:
                            context.scene.analysis_list[current_res].res_counter += 1
                        else:
                            context.scene.analysis_list.add()
                            self.res_count = len(context.scene.analysis_list)-1
                            context.scene.analysis_list[self.res_count].res_tex = image_size
                            context.scene.analysis_list[self.res_count].res_counter += 1
    return image_size , len(ob.material_slots)

class MESH_OT_info_texres(Operator):
    bl_idname = "mesh.info_texres"
    bl_label = "Info Texture resolution"
    bl_description = "report the mean texture resolution of the selected meshes"

    def execute(self, context):

        context.active_object.select_set(True) 
        selected = context.selected_objects
        scene = context.scene
        total_area = 0.0
        total_polynum = 0
        info = []

        #analyze textures setup
        scene.analysis_list.clear()
        scene.statistics_list.clear()
        self.res_count = 0
        self.material_count = 0
        self.ob_count = 0

        #extract statistics setup
        texture_area = 0.0

        #calculate area
        for obj in selected:
            area = calc_area(obj)
            polynum = len(obj.data.polygons)
            total_area = total_area + area
            total_polynum = total_polynum + polynum
            
            #analyze textures
            res_tex, res_count = info_textures(self, context, obj)
            #print(str(res_tex)+" ripetuta "+str(res_count)+" volte")
            context.scene.statistics_list.add()
            context.scene.statistics_list[self.ob_count].name = obj.name
            #context.scene.statistics_list[self.ob_count].context_col =
            #context.scene.statistics_list[self.ob_count].tiles_num = 
            context.scene.statistics_list[self.ob_count].area_mesh = area
            context.scene.statistics_list[self.ob_count].poly_num = polynum
            context.scene.statistics_list[self.ob_count].poly_res = polynum/area
            context.scene.statistics_list[self.ob_count].res_tex = res_tex
            context.scene.statistics_list[self.ob_count].res_counter = res_count
            context.scene.statistics_list[self.ob_count].uv_ratio = 0.6
            context.scene.statistics_list[self.ob_count].mean_res_tex = 1000/(math.sqrt((res_tex*res_tex*res_count*0.6)/area))
            
            self.ob_count +=1


        area_fmt = check_unit_system_area(total_area)          
        info.append((f"Area tot: {round(total_area,1)}²", None))
        info.append((f"Polygons tot: {total_polynum}", None))
            
        info.append((f" "+str(len(selected))+" object(s); " + str(self.material_count) +" mats;",None))       
        for res_out in range(len(scene.analysis_list)):
            #print("Resolution "+str(scene.analysis_list[res_out].res_tex)+" has "+str(scene.analysis_list[res_out].res_counter)+" instances")
            info.append((f"Tex. "+str(scene.analysis_list[res_out].res_tex)+": "+str(scene.analysis_list[res_out].res_counter), None))

        for unit in context.scene.analysis_list:
            res_unit_area = unit.res_tex * unit.res_tex * unit.res_counter * 0.6
            texture_area = texture_area + res_unit_area
        texture_area = 1000/(math.sqrt(texture_area/total_area))
        mean_poly = total_polynum/total_area
        info.append((f"Mean resolution ", None))
        info.append((f"- Tex: "+str(round(texture_area,2))+" mm/pixel", None))
        info.append((f"- Poly: "+str(round(mean_poly,1))+" poly/m²", None))
        report_data.update(*info)
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