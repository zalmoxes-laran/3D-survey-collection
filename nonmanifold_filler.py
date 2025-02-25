import bpy
import bmesh
from bpy.types import Operator, Panel
from bpy.props import BoolProperty, FloatProperty, EnumProperty

class MESH_OT_fill_nonmanifold(Operator):
    """Fill non-manifold edges with faces and apply nodata grid pattern material"""
    bl_idname = "mesh.fill_nonmanifold"
    bl_label = "Fill and Apply Grid Pattern"
    bl_options = {'REGISTER', 'UNDO'}
    
    grid_axis: EnumProperty(
        name="Grid Axis",
        description="Axis for grid pattern",
        items=[
            ('X', "X Axis", "Create grid along X axis"),
            ('Y', "Y Axis", "Create grid along Y axis"),
            ('Z', "Z Axis", "Create grid along Z axis"),
        ],
        default='Y'
    )
    
    grid_scale: FloatProperty(
        name="Grid Scale",
        description="Scale of the grid pattern",
        default=5.0,
        min=0.1,
        max=20.0
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
        
        # Create or update the 'nodata' material
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
                except Exception as e:
                    self.report({'WARNING'}, f"F2 addon error: {str(e)}")
            
            self.report({'INFO'}, f"Filled non-manifold edges and applied grid pattern material")
        else:
            self.report({'INFO'}, "No non-manifold edges found")
        
        # Always return to object mode
        bpy.ops.object.mode_set(mode='OBJECT')
        
        return {'FINISHED'}
    
    def get_or_create_nodata_material(self, context):
        # Check if nodata material already exists
        nodata_mat = bpy.data.materials.get("nodata")
        
        # If material doesn't exist, create it
        if not nodata_mat:
            nodata_mat = bpy.data.materials.new(name="nodata")
            nodata_mat.use_nodes = True
            self.recreate_material_nodes(nodata_mat)
        # If it exists but our axis or scale changed, update it
        elif (context.scene.grid_axis != self.grid_axis or 
              context.scene.grid_scale != self.grid_scale):
            self.recreate_material_nodes(nodata_mat)
        
        return nodata_mat
    
    def recreate_material_nodes(self, material):
        """Recreate the material node setup from scratch"""
        nodes = material.node_tree.nodes
        links = material.node_tree.links
        
        # Clear all nodes
        nodes.clear()
        
        # Create output node
        output = nodes.new('ShaderNodeOutputMaterial')
        output.location = (600, 0)
        
        # Create emission node for shadeless look
        emission = nodes.new('ShaderNodeEmission')
        emission.location = (400, 0)
        emission.inputs['Strength'].default_value = 1.0  # Make it shadeless
        
        # Link emission to output
        links.new(emission.outputs['Emission'], output.inputs['Surface'])
        
        # Create texture coordinate node
        tex_coord = nodes.new('ShaderNodeTexCoord')
        tex_coord.location = (-600, 0)
        
        # Create wave texture node
        wave_tex = nodes.new('ShaderNodeTexWave')
        wave_tex.name = "Wave Texture"
        wave_tex.location = (-200, 0)
        # Settaggi specifici come nell'immagine
        wave_tex.wave_type = 'BANDS'
        wave_tex.bands_direction = self.grid_axis
        wave_tex.wave_profile = 'SIN'
        wave_tex.inputs['Scale'].default_value = self.grid_scale
        wave_tex.inputs['Distortion'].default_value = 0.0
        wave_tex.inputs['Detail'].default_value = 0.0
        wave_tex.inputs['Detail Scale'].default_value = 0.0
        wave_tex.inputs['Detail Roughness'].default_value = 0.0
        wave_tex.inputs['Phase Offset'].default_value = 0.0
        
        # Link texture coordinate to wave texture
        links.new(tex_coord.outputs['Generated'], wave_tex.inputs['Vector'])
        
        # Create color ramp for the pattern
        color_ramp = nodes.new('ShaderNodeValToRGB')
        color_ramp.location = (0, 0)
        color_ramp.color_ramp.elements[0].position = 0.48
        color_ramp.color_ramp.elements[0].color = (1.0, 1.0, 1.0, 1.0)  # White
        color_ramp.color_ramp.elements[1].position = 0.52
        color_ramp.color_ramp.elements[1].color = (0.0, 0.0, 0.0, 1.0)  # Black
        
        # Link wave texture to color ramp
        links.new(wave_tex.outputs['Color'], color_ramp.inputs['Fac'])
        
        # Link color ramp to emission
        links.new(color_ramp.outputs['Color'], emission.inputs['Color'])


class MESH_OT_adjust_nodata_material(Operator):
    """Adjust the grid pattern of the nodata material"""
    bl_idname = "mesh.adjust_nodata_material"
    bl_label = "Update Grid"
    bl_options = {'REGISTER', 'UNDO'}
    
    grid_axis: EnumProperty(
        name="Grid Axis",
        description="Axis for grid pattern",
        items=[
            ('X', "X Axis", "Create grid along X axis"),
            ('Y', "Y Axis", "Create grid along Y axis"),
            ('Z', "Z Axis", "Create grid along Z axis"),
        ],
        default='Y'
    )
    
    grid_scale: FloatProperty(
        name="Grid Scale",
        description="Scale of the grid pattern",
        default=5.0,
        min=0.1,
        max=20.0
    )
    
    @classmethod
    def poll(cls, context):
        return bpy.data.materials.get("nodata") is not None
    
    def execute(self, context):
        # Get the nodata material
        nodata_mat = bpy.data.materials.get("nodata")
        
        if not nodata_mat:
            self.report({'ERROR'}, "Nodata material not found")
            return {'CANCELLED'}
        
        # Update the material
        nodes = nodata_mat.node_tree.nodes
        wave_tex = nodes.get("Wave Texture")
        
        if wave_tex:
            wave_tex.bands_direction = self.grid_axis
            wave_tex.inputs['Scale'].default_value = self.grid_scale
            
            # Update the scene properties to match
            context.scene.grid_axis = self.grid_axis
            context.scene.grid_scale = self.grid_scale
            
            self.report({'INFO'}, f"Updated grid pattern settings")
        else:
            self.report({'ERROR'}, "Wave Texture node not found in nodata material")
            return {'CANCELLED'}
        
        return {'FINISHED'}


class MESH_OT_remove_nodata_patches(Operator):
    """Remove faces with nodata material"""
    bl_idname = "mesh.remove_nodata_patches"
    bl_label = "Remove Patches"
    bl_options = {'REGISTER', 'UNDO'}
    
    @classmethod
    def poll(cls, context):
        return context.active_object is not None and context.active_object.type == 'MESH'
    
    def execute(self, context):
        obj = context.active_object
        
        # Ensure we're in object mode
        if obj.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        
        # Get the nodata material
        nodata_mat = bpy.data.materials.get("nodata")
        
        if not nodata_mat:
            self.report({'INFO'}, "No nodata material found")
            return {'CANCELLED'}
        
        # Find the material index
        nodata_slot_index = -1
        for i, slot in enumerate(obj.material_slots):
            if slot.material and slot.material.name == nodata_mat.name:
                nodata_slot_index = i
                break
        
        if nodata_slot_index == -1:
            self.report({'INFO'}, "No nodata material assigned to this object")
            return {'CANCELLED'}
        
        # Switch to edit mode
        bpy.ops.object.mode_set(mode='EDIT')
        
        # Deselect everything
        bpy.ops.mesh.select_all(action='DESELECT')
        
        # Select faces with nodata material (metodo corretto)
        obj.active_material_index = nodata_slot_index
        bpy.ops.object.material_slot_select()
        
        # Delete the selected faces
        bpy.ops.mesh.delete(type='FACE')
        
        # Return to object mode
        bpy.ops.object.mode_set(mode='OBJECT')
        
        self.report({'INFO'}, "Removed patches with nodata material")
        
        return {'FINISHED'}


class VIEW3D_PT_nonmanifold_filler(Panel):
    bl_label = "3D Model Patch Tool"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "3DSC"
    bl_idname = "VIEW3D_PT_nonmanifold_filler"
    bl_context = "objectmode"
    bl_options = {'DEFAULT_CLOSED'}
    
    def draw(self, context):
        layout = self.layout
        
        layout.label(text="Fill areas with missing surface data")
        
        # Create Patch section
        row = layout.row()
        row.prop(context.scene, "grid_axis", text="Axis")
        row = layout.row()
        row.prop(context.scene, "grid_scale", text="Scale")
        row = layout.row()
        row.prop(context.scene, "use_f2_addon", text="Use F2 Addon")
        row = layout.row()
        row.operator("mesh.fill_nonmanifold", icon="GRID", text="Fill and Apply Grid Pattern")
        
        # Adjust and Remove - on the same row
        row = layout.row(align=True)
        op = row.operator("mesh.adjust_nodata_material", icon="NODE_MATERIAL", text="Update Grid")
        op.grid_axis = context.scene.grid_axis
        op.grid_scale = context.scene.grid_scale
        row.operator("mesh.remove_nodata_patches", icon="TRASH", text="Remove Patches")

# Classes for registration
classes = [
    MESH_OT_fill_nonmanifold,
    MESH_OT_adjust_nodata_material,
    MESH_OT_remove_nodata_patches,
    VIEW3D_PT_nonmanifold_filler,
]

def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    
    # Register properties
    bpy.types.Scene.grid_axis = bpy.props.EnumProperty(
        name="Grid Axis",
        description="Axis for grid pattern",
        items=[
            ('X', "X Axis", "Create grid along X axis"),
            ('Y', "Y Axis", "Create grid along Y axis"),
            ('Z', "Z Axis", "Create grid along Z axis"),
        ],
        default='Y'
    )
    
    bpy.types.Scene.grid_scale = bpy.props.FloatProperty(
        name="Grid Scale",
        description="Scale of the grid pattern",
        default=5.0,
        min=0.1,
        max=20.0
    )
    
    bpy.types.Scene.use_f2_addon = bpy.props.BoolProperty(
        name="Use F2 Addon",
        default=True,
        description="Use F2 addon for better fill results if available"
    )

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
    
    # Remove properties
    del bpy.types.Scene.grid_axis
    del bpy.types.Scene.grid_scale
    del bpy.types.Scene.use_f2_addon

if __name__ == "__main__":
    register()