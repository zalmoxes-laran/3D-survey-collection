import bpy
import math
from .functions import areamesh


class OBJECT_PT_subdivision_panel(bpy.types.Panel):
    """Pannello per l'addon Subdivision Surface basato sul rapporto facce/superficie"""
    bl_label = "Mesh Preprocessing for Cesium"
    bl_idname = "OBJECT_PT_subdivision_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = '3DSC'

    def draw(self, context):
        layout = self.layout

        row = layout.row()
        row.label(text="Set target poly/area ratio:")
        
        row = layout.row()
        row.prop(context.scene, "subdivision_ratio_min", text="min")
        row.prop(context.scene, "subdivision_ratio_max", text="max")
        row.operator("object.apply_subdivision", text="Apply")
        

class OBJECT_OT_apply_subdivision(bpy.types.Operator):
    """Applica Subdivision Surface agli oggetti selezionati"""
    bl_idname = "object.apply_subdivision"
    bl_label = "Applica Subdivision"

    def execute(self, context):
        
        ratio_min = context.scene.subdivision_ratio_min
        ratio_max = context.scene.subdivision_ratio_max

        # Ottieni una lista degli oggetti attualmente selezionati nella scena
        selected_objects = bpy.context.selected_objects

        # Itera su ogni oggetto selezionato
        for obj in selected_objects:
            # Calcola il livello di suddivisione per l'oggetto corrente
            subdivision_level = self.calculate_subdivision_level(obj, ratio_min, ratio_max)

            # Aggiungi un modificatore di Subdivision Surface all'oggetto
            modifier = obj.modifiers.new(name="Subdivision", type='SUBSURF')
            # Imposta il numero di iterazioni di suddivisione
            modifier.levels = subdivision_level
            modifier.subdivision_type = 'SIMPLE'

        # Applica i modificatori per rendere le modifiche permanenti a tutti gli oggetti selezionati
        bpy.ops.object.select_all(action='DESELECT')
        for obj in selected_objects:
            obj.select_set(True)
            bpy.context.view_layer.objects.active = obj
            bpy.ops.object.modifier_apply(modifier='Subdivision')
            obj.select_set(False)

        return {'FINISHED'}

    def calculate_subdivision_level(self, obj, ratio_min, ratio_max):
        
        # Calcola il rapporto tra il numero di facce e la superficie dell'oggetto
        num_faces = len(obj.data.polygons)
        #surface_area = sum(f.area for f in obj.data.polygons)
        surface_area = areamesh(obj)
        current_ratio = num_faces / surface_area
        
        # Controlla se il rapporto attuale è inferiore al rapporto inserito dall'utente
        if current_ratio < ratio_min:
            # Calcola il livello di suddivisione
            subdivision_level = math.ceil(math.log(ratio_min * (surface_area / num_faces), 4))
            resulting_faces = num_faces * (4**subdivision_level)
            resulting_ratio = resulting_faces / surface_area
            if resulting_ratio > ratio_max:
                subdivision_level -= 1
            return subdivision_level
        else:
            return 0  # Nessuna suddivisione necessaria

def register():
    bpy.utils.register_class(OBJECT_PT_subdivision_panel)
    bpy.utils.register_class(OBJECT_OT_apply_subdivision)
    bpy.types.Scene.subdivision_ratio_min = bpy.props.FloatProperty(name="Rapporto min facce/superficie", default=5000)
    bpy.types.Scene.subdivision_ratio_max = bpy.props.FloatProperty(name="Rapporto max facce/superficie", default=15000)

def unregister():
    bpy.utils.unregister_class(OBJECT_PT_subdivision_panel)
    bpy.utils.unregister_class(OBJECT_OT_apply_subdivision)
    del bpy.types.Scene.subdivision_ratio_min
    del bpy.types.Scene.subdivision_ratio_max

if __name__ == "__main__":
    register()
    
