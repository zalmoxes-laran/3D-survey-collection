import bpy
import bmesh
from bpy.types import Operator, Panel
from bpy.props import BoolProperty, FloatProperty

class MESH_OT_fill_nonmanifold(Operator):
    """Fill non-manifold edges with faces and apply nodata material"""
    bl_idname = "mesh.fill_nonmanifold"
    bl_label = "Fill Non-Manifold Edges"
    bl_options = {'REGISTER', 'UNDO'}
    
    create_material: BoolProperty(
        name="Create Material",
        description="Create a new nodata material if it doesn't exist",
        default=True
    )
    
    metallic: FloatProperty(
        name="Metallic",
        description="Metallic value for nodata material",
        default=0.0,
        min=0.0,
        max=1.0
    )
    
    roughness: FloatProperty(
        name="Roughness",
        description="Roughness value for nodata material",
        default=0.5, 
        min=0.0,
        max=1.0
    )
    
    use_f2: BoolProperty(
        name="Use F2 addon",
        description="Use F2 addon for better fill results if available",
        default=True
    )
    
    @classmethod
    def poll(cls, context):
        return context.active_object is not None and context.active_object.type == 'MESH'
    
    def execute(self, context):
        obj = context.active_object
        
        # Ensure we're in object mode
        if obj.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        
        # Create or get the 'nodata' material
        nodata_mat = self.get_or_create_nodata_material(context)
        
        # Assign the material to the object if not already assigned
        if nodata_mat.name not in [slot.material.name for slot in obj.material_slots if slot.material]:
            obj.data.materials.append(nodata_mat)
        
        # Get the slot index for the nodata material
        nodata_slot_index = -1
        for i, slot in enumerate(obj.material_slots):
            if slot.material and slot.material.name == nodata_mat.name:
                nodata_slot_index = i
                break
        
        # Set the active material slot to nodata material
        if nodata_slot_index >= 0:
            obj.active_material_index = nodata_slot_index
        
        # Switch to edit mode and select edges
        bpy.ops.object.mode_set(mode='EDIT')
        
        # Set selection mode to edges
        bpy.ops.mesh.select_mode(type='EDGE')
        
        # Select non-manifold edges
        bpy.ops.mesh.select_all(action='DESELECT')
        bpy.ops.mesh.select_non_manifold()
        
        # Get the mesh data in bmesh to check if we have selected edges
        me = obj.data
        bm = bmesh.from_edit_mesh(me)
        selected_edges_count = len([e for e in bm.edges if e.select])
        
        if selected_edges_count > 0:
            # Fill using edge_face_add (standard Blender operation)
            bpy.ops.mesh.edge_face_add()
            
            # Assign nodata material to the new faces
            bpy.ops.object.material_slot_assign()
            
            # If F2 is available and enabled, use it for better fill results
            if self.use_f2:
                try:
                    bpy.ops.mesh.f2()
                    # Ensure the material gets assigned to any new faces created by F2
                    bpy.ops.object.material_slot_assign()
                except:
                    self.report({'WARNING'}, "F2 addon not available or error occurred")
            
            self.report({'INFO'}, f"Filled non-manifold edges and applied nodata material")
        else:
            self.report({'INFO'}, "No non-manifold edges found")
        
        # Stay in edit mode as per user's normal workflow
        
        return {'FINISHED'}
    
    def get_or_create_nodata_material(self, context):
        # Check if nodata material already exists
        nodata_mat = bpy.data.materials.get("nodata")
        
        if nodata_mat is None and self.create_material:
            # Create a new material
            nodata_mat = bpy.data.materials.new(name="nodata")
            nodata_mat.use_nodes = True
            
            # Get the Principled BSDF node
            principled_bsdf = nodata_mat.node_tree.nodes.get('Principled BSDF')
            if principled_bsdf:
                # Set base color to a distinctive color (red in this case)
                principled_bsdf.inputs['Base Color'].default_value = (1.0, 0.0, 0.0, 1.0)
                principled_bsdf.inputs['Metallic'].default_value = self.metallic
                principled_bsdf.inputs['Roughness'].default_value = self.roughness
        
        return nodata_mat

class VIEW3D_PT_nonmanifold_filler(Panel):
    bl_label = "NonManifold Filler"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "3DSC"
    bl_idname = "VIEW3D_PT_nonmanifold_filler"
    bl_context = "objectmode"
    bl_options = {'DEFAULT_CLOSED'}
    
    def draw(self, context):
        layout = self.layout
        
        row = layout.row()
        row.operator("mesh.fill_nonmanifold", icon="EDGESEL")
        
        # Optional settings
        box = layout.box()
        box.label(text="Options:")
        box.prop(context.scene, "nodata_color", text="Nodata Color")
        box.prop(context.scene, "use_f2_addon", text="Use F2 Addon")

# Aggiungi queste classi alla lista classes nel modulo mesh_cleaner
classes = [
    MESH_OT_fill_nonmanifold,
    VIEW3D_PT_nonmanifold_filler,
]

# Funzioni register() e unregister()
def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    
    # Registrazione delle proprietà della scena
    bpy.types.Scene.nodata_color = bpy.props.FloatVectorProperty(
        name="Nodata Color",
        subtype='COLOR',
        default=(1.0, 0.0, 0.0),
        min=0.0,
        max=1.0,
        description="Color to use for nodata material"
    )
    
    bpy.types.Scene.use_f2_addon = bpy.props.BoolProperty(
        name="Use F2 Addon",
        default=True,
        description="Use F2 addon for better fill results if available"
    )

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
    
    # Rimozione delle proprietà della scena
    del bpy.types.Scene.nodata_color
    del bpy.types.Scene.use_f2_addon

if __name__ == "__main__":
    register()