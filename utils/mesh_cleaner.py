import bpy

class MESH_OT_merge_by_distance_custom(bpy.types.Operator):
    """Performs a Merge by Distance (remove doubles) on the selected Mesh object"""
    bl_idname = "mesh.merge_by_distance_custom"
    bl_label = "Merge by Distance (Custom)"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        obj = context.active_object
        
        if obj and obj.type == 'MESH':
            # Passa in modalità Edit
            bpy.ops.object.mode_set(mode='EDIT')
            
            # Seleziona tutti i vertici
            bpy.ops.mesh.select_all(action='SELECT')
            
            # Rimuovi i vertici duplicati (vecchio operatore corrispondente a Merge By Distance)
            bpy.ops.mesh.remove_doubles(threshold=0.0001)
            
            # Torna in modalità Oggetto
            bpy.ops.object.mode_set(mode='OBJECT')
            
            self.report({'INFO'}, "Merge by Distance performed correctly!")
            return {'FINISHED'}
        else:
            self.report({'WARNING'}, "No Mesh type object selected!")
            return {'CANCELLED'}
        
classes = (
    MESH_OT_merge_by_distance_custom,
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)

if __name__ == "__main__":
    register()