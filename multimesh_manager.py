
import bpy

class OBJECT_OT_unify_meshes(bpy.types.Operator):
    bl_idname = "object.unify_meshes"
    bl_label = "Unify Selected Meshes"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        selected_objects = context.selected_objects
        
        # Filtro per mesh
        mesh_objects = [obj for obj in selected_objects if obj.type == 'MESH']
        if len(mesh_objects) < 2:
            self.report({'WARNING'}, "Select at least two mesh objects.")
            return {'CANCELLED'}
        
        # Deseleziona tutti gli oggetti
        bpy.ops.object.select_all(action='DESELECT')
        
        # Prepara la mesh unificata
        unified_mesh_name = "unimesh_temp_"
        for mesh_obj in mesh_objects:
            mesh_obj.select_set(True)  # Seleziona l'oggetto (aggiornato per Blender 2.8x+)
            context.view_layer.objects.active = mesh_obj  # Imposta come attivo per il vertex group
            unified_mesh_name += mesh_obj.name + "_"
            # Aggiungi ogni oggetto a un vertex group nominato come l'oggetto
            vg = mesh_obj.vertex_groups.new(name=mesh_obj.name)
            vg.add(range(len(mesh_obj.data.vertices)), 1.0, 'ADD')
        
        # Unisci le mesh
        bpy.ops.object.join()
        
        # Rinomina la mesh unificata
        unified_mesh = context.view_layer.objects.active
        unified_mesh.name = unified_mesh_name
        
        self.report({'INFO'}, "Meshes unified into {}".format(unified_mesh_name))
        return {'FINISHED'}

class OBJECT_OT_separate_meshes(bpy.types.Operator):
    bl_idname = "object.separate_meshes"
    bl_label = "Separate Unified Mesh into Original Meshes"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        unified_mesh = context.object
        
        if not unified_mesh or not unified_mesh.name.startswith("unimesh_temp_"):
            self.report({'WARNING'}, "No unified mesh selected or mesh name doesn't start with 'unimesh_temp_'.")
            return {'CANCELLED'}
        
        original_mesh_names = [vg.name for vg in unified_mesh.vertex_groups]

        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_all(action='DESELECT')
        bpy.ops.object.mode_set(mode='OBJECT')

        for name in original_mesh_names:
            vg = unified_mesh.vertex_groups.get(name)
            if vg is None:
                continue
            
            # Seleziona i vertici del gruppo
            bpy.ops.object.mode_set(mode='EDIT')
            bpy.ops.object.vertex_group_set_active(group=name)
            bpy.ops.object.vertex_group_select()
            bpy.ops.mesh.separate(type='SELECTED')
            bpy.ops.object.mode_set(mode='OBJECT')

        # Dopo la separazione, rinomina gli oggetti separati
        separated_meshes = [obj for obj in context.selected_objects if obj != unified_mesh and obj.type == 'MESH']
        for mesh in separated_meshes:
            # Cerca il nome originale basato sul vertex group che ora sarà il nome della mesh
            for name in original_mesh_names:
                if name in mesh.name:
                    mesh.name = name
                    break
            self.remove_unused_materials(mesh)

        bpy.data.objects.remove(unified_mesh)
        self.report({'INFO'}, "Unified mesh separated into original meshes.")
        return {'FINISHED'}


    def remove_unused_materials(self, obj):
        if obj.type != 'MESH':
            return

        mesh = obj.data
        materiali_usati = set()

        # Itera su tutti i poligoni dell'oggetto per trovare i materiali utilizzati
        for poligono in mesh.polygons:
            materiali_usati.add(poligono.material_index)

        # Crea una lista dei materiali non utilizzati
        materiali_non_utilizzati = [mat for idx, mat in enumerate(mesh.materials) if idx not in materiali_usati]

        # Rimuovi i materiali non utilizzati
        for mat in materiali_non_utilizzati:
            # Aggiornato per usare solo l'indice come argomento
            mesh.materials.pop(index=mesh.materials.find(mat.name))
            print(f"Rimosso materiale non utilizzato: {mat.name}")

        # Rimuovere i vertex groups
        for vg in obj.vertex_groups:
            obj.vertex_groups.remove(vg)


classes = [
    OBJECT_OT_unify_meshes,
    OBJECT_OT_separate_meshes
    ]

def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in classes:
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()