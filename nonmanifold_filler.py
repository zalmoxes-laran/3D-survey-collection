import bpy
import bmesh
from bpy.types import Operator, Panel
from bpy.props import BoolProperty, FloatProperty, EnumProperty, FloatVectorProperty

class MESH_OT_fill_nonmanifold(Operator):
    """Fill non-manifold edges with faces and apply nodata pattern material"""
    bl_idname = "mesh.fill_nonmanifold"
    bl_label = "Fill and Apply Pattern"
    bl_options = {'REGISTER', 'UNDO'}
    
    fill_type: EnumProperty(
        name="Fill Type",
        description="Type of fill pattern to apply",
        items=[
            ('SOLID', "Solid Color", "Fill with a solid color"),
            ('GRID', "Grid Pattern", "Fill with a grid pattern"),
        ],
        default='SOLID'
    )
    
    solid_color: FloatVectorProperty(
        name="Color",
        description="Solid color for fill",
        subtype='COLOR',
        default=(0.8, 0.8, 0.8, 1.0),
        min=0.0,
        max=1.0,
        size=4
    )
    
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
    
    improve_geometry: BoolProperty(
        name="Improve Geometry",
        description="Beautify and triangulate the filling for better topology",
        default=True
    )
    
    @classmethod
    def poll(cls, context):
        # Check if there's at least one selected mesh object
        return any(obj.type == 'MESH' for obj in context.selected_objects)
    
    def execute(self, context):
        # Store parameters in scene properties
        context.scene.fill_type = self.fill_type
        context.scene.solid_color = self.solid_color
        context.scene.grid_axis = self.grid_axis
        context.scene.grid_scale = self.grid_scale
        context.scene.use_f2_addon = self.use_f2
        context.scene.improve_geometry = self.improve_geometry
        
        # Get active object and selection
        active_obj = context.active_object
        selected_objects = [obj for obj in context.selected_objects if obj.type == 'MESH']
        
        if not selected_objects:
            self.report({'WARNING'}, "No mesh objects selected")
            return {'CANCELLED'}
        
        # Make sure we're in object mode
        if context.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        
        # Process each selected mesh object
        processed_count = 0
        skipped_count = 0
        
        for obj in selected_objects:
            # Set the current object as active
            context.view_layer.objects.active = obj
            
            # Create a unique material name based on the object's name
            material_name = f"nodata_{obj.name}"
            
            # Remove existing material if it exists for this specific object
            self.remove_existing_nodata_material(obj, material_name)
            
            # Create a new material
            nodata_mat = self.create_new_nodata_material(context, material_name)
            
            # Assign the material to the object
            obj.data.materials.append(nodata_mat)
            nodata_slot_index = len(obj.material_slots) - 1
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
                
                # Improve geometry if option is enabled
                if self.improve_geometry:
                    bpy.ops.mesh.quads_convert_to_tris(quad_method='BEAUTY', ngon_method='BEAUTY')
                    bpy.ops.mesh.beautify_fill()
                
                # Assign nodata material to the new faces
                bpy.ops.object.material_slot_assign()
                
                # If F2 is available and enabled, use it for better fill results
                if self.use_f2:
                    try:
                        bpy.ops.mesh.f2()
                        # Ensure the material gets assigned to any new faces created by F2
                        bpy.ops.object.material_slot_assign()
                    except Exception as e:
                        self.report({'WARNING'}, f"F2 addon error for {obj.name}: {str(e)}")
                
                processed_count += 1
            else:
                skipped_count += 1
                # Remove the unused material
                bpy.ops.object.mode_set(mode='OBJECT')
                obj.active_material_index = nodata_slot_index
                bpy.ops.object.material_slot_remove()
                if nodata_mat.users == 0:
                    bpy.data.materials.remove(nodata_mat)
                continue
            
            # Return to object mode before processing the next object
            bpy.ops.object.mode_set(mode='OBJECT')
        
        # Restore the active object if it still exists
        if active_obj:
            # Check if the object is still in the scene
            if active_obj.name in context.view_layer.objects:
                context.view_layer.objects.active = active_obj
        
        # Report results
        fill_type_name = "solid color" if self.fill_type == 'SOLID' else "grid pattern"
        
        if processed_count > 0:
            if skipped_count > 0:
                self.report({'INFO'}, f"Processed {processed_count} objects with {fill_type_name} material. Skipped {skipped_count} objects with no non-manifold edges.")
            else:
                self.report({'INFO'}, f"Processed {processed_count} objects with {fill_type_name} material.")
        else:
            self.report({'INFO'}, "No non-manifold edges found in any of the selected objects")
        
        return {'FINISHED'}
    
    def remove_existing_nodata_material(self, obj, material_name):
        """Remove the existing nodata material from the specific object if it exists"""
        # Check if the material exists
        nodata_mat = bpy.data.materials.get(material_name)
        if nodata_mat:
            # Check if the object is using this material
            for i, slot in enumerate(obj.material_slots):
                if slot.material and slot.material.name == material_name:
                    obj.active_material_index = i
                    bpy.ops.object.material_slot_remove()
            
            # If no other objects are using this material, remove it from the blend file
            if nodata_mat.users == 0:
                bpy.data.materials.remove(nodata_mat)
    
    def create_new_nodata_material(self, context, material_name):
        """Create a new nodata material based on the selected fill type"""
        nodata_mat = bpy.data.materials.new(name=material_name)
        nodata_mat.use_nodes = True
        
        # Get the node tree
        nodes = nodata_mat.node_tree.nodes
        links = nodata_mat.node_tree.links
        
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
        
        # Store the fill type in the material for reference
        nodata_mat["fill_type"] = self.fill_type
        
        if self.fill_type == 'SOLID':
            # For solid color, directly set the emission color
            emission.inputs['Color'].default_value = self.solid_color
            
        elif self.fill_type == 'GRID':
            # Create texture coordinate node
            tex_coord = nodes.new('ShaderNodeTexCoord')
            tex_coord.location = (-600, 0)
            
            # Create wave texture node
            wave_tex = nodes.new('ShaderNodeTexWave')
            wave_tex.name = "Wave Texture"
            wave_tex.location = (-200, 0)
            # Configure wave texture
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
        
        return nodata_mat


class MESH_OT_adjust_nodata_material(Operator):
    """Adjust the pattern of the nodata material for all selected objects"""
    bl_idname = "mesh.adjust_nodata_material"
    bl_label = "Update Pattern"
    bl_options = {'REGISTER', 'UNDO'}
    
    fill_type: EnumProperty(
        name="Fill Type",
        description="Type of fill pattern to apply",
        items=[
            ('SOLID', "Solid Color", "Fill with a solid color"),
            ('GRID', "Grid Pattern", "Fill with a grid pattern"),
        ],
        default='SOLID'
    )
    
    solid_color: FloatVectorProperty(
        name="Color",
        description="Solid color for fill",
        subtype='COLOR',
        default=(0.8, 0.8, 0.8, 1.0),
        min=0.0,
        max=1.0,
        size=4
    )
    
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
        # Check if any selected object has a nodata material
        for obj in context.selected_objects:
            if obj.type == 'MESH':
                for slot in obj.material_slots:
                    if slot.material and slot.material.name.startswith("nodata_"):
                        return True
        return False
    
    def execute(self, context):
        # Store current settings
        context.scene.fill_type = self.fill_type
        context.scene.solid_color = self.solid_color
        context.scene.grid_axis = self.grid_axis
        context.scene.grid_scale = self.grid_scale
        
        # Get active object for restoring later
        active_obj = context.active_object
        selected_objects = [obj for obj in context.selected_objects if obj.type == 'MESH']
        
        if not selected_objects:
            self.report({'WARNING'}, "No mesh objects selected")
            return {'CANCELLED'}
        
        updated_count = 0
        
        # Process each selected mesh object
        for obj in selected_objects:
            # Find the nodata material for this object
            nodata_mat = None
            for slot in obj.material_slots:
                if slot.material and slot.material.name.startswith(f"nodata_{obj.name}"):
                    nodata_mat = slot.material
                    break
            
            if not nodata_mat:
                continue  # Skip objects without nodata material
            
            # Recreate the material
            nodes = nodata_mat.node_tree.nodes
            links = nodata_mat.node_tree.links
            
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
            
            # Store the fill type in the material for reference
            nodata_mat["fill_type"] = self.fill_type
            
            if self.fill_type == 'SOLID':
                # For solid color, directly set the emission color
                emission.inputs['Color'].default_value = self.solid_color
                
            elif self.fill_type == 'GRID':
                # Create texture coordinate node
                tex_coord = nodes.new('ShaderNodeTexCoord')
                tex_coord.location = (-600, 0)
                
                # Create wave texture node
                wave_tex = nodes.new('ShaderNodeTexWave')
                wave_tex.name = "Wave Texture"
                wave_tex.location = (-200, 0)
                # Configure wave texture
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
            
            updated_count += 1
        
        # Restore the active object if it still exists
        if active_obj:
            if active_obj.name in context.view_layer.objects:
                context.view_layer.objects.active = active_obj
        
        # Report results
        fill_type_name = "solid color" if self.fill_type == 'SOLID' else "grid pattern"
        if updated_count > 0:
            self.report({'INFO'}, f"Updated {updated_count} objects with {fill_type_name} material")
        else:
            self.report({'INFO'}, "No nodata materials found to update")
        
        return {'FINISHED'}


class MESH_OT_remove_nodata_patches(Operator):
    """Remove faces with nodata material from all selected objects"""
    bl_idname = "mesh.remove_nodata_patches"
    bl_label = "Remove Patches"
    bl_options = {'REGISTER', 'UNDO'}
    
    @classmethod
    def poll(cls, context):
        # Check if any selected object has a nodata material
        for obj in context.selected_objects:
            if obj.type == 'MESH':
                for slot in obj.material_slots:
                    if slot.material and slot.material.name.startswith("nodata_"):
                        return True
        return False
    
    def execute(self, context):
        # Store the active object for restoring later
        active_obj = context.active_object
        selected_objects = [obj for obj in context.selected_objects if obj.type == 'MESH']
        
        if not selected_objects:
            self.report({'WARNING'}, "No mesh objects selected")
            return {'CANCELLED'}
        
        # Ensure we're in object mode
        if context.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        
        removed_count = 0
        skipped_count = 0
        removed_materials = []
        
        # Process each selected mesh object
        for obj in selected_objects:
            # Set the current object as active
            context.view_layer.objects.active = obj
            
            # Find the nodata material for this object
            nodata_mat = None
            nodata_slot_index = -1
            
            for i, slot in enumerate(obj.material_slots):
                if slot.material and slot.material.name.startswith(f"nodata_{obj.name}"):
                    nodata_mat = slot.material
                    nodata_slot_index = i
                    break
            
            if not nodata_mat:
                skipped_count += 1
                continue  # Skip objects without nodata material
            
            # Switch to edit mode
            bpy.ops.object.mode_set(mode='EDIT')
            
            # Deselect everything
            bpy.ops.mesh.select_all(action='DESELECT')
            
            # Select faces with nodata material
            obj.active_material_index = nodata_slot_index
            bpy.ops.object.material_slot_select()
            
            # Delete the selected faces
            bpy.ops.mesh.delete(type='FACE')
            
            # Return to object mode
            bpy.ops.object.mode_set(mode='OBJECT')
            
            # Remove the material slot
            obj.active_material_index = nodata_slot_index
            bpy.ops.object.material_slot_remove()
            
            # Add to the list of materials to check later
            removed_materials.append(nodata_mat)
            removed_count += 1
        
        # Remove materials that are no longer used
        for mat in removed_materials:
            if mat.users == 0:
                bpy.data.materials.remove(mat)
        
        # Restore the active object if it still exists
        if active_obj:
            if active_obj.name in context.view_layer.objects:
                context.view_layer.objects.active = active_obj
        
        # Report results
        if removed_count > 0:
            if skipped_count > 0:
                self.report({'INFO'}, f"Removed patches from {removed_count} objects. Skipped {skipped_count} objects without nodata materials.")
            else:
                self.report({'INFO'}, f"Removed patches from {removed_count} objects.")
        else:
            self.report({'INFO'}, "No nodata materials found to remove")
        
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
        scene = context.scene
        
        layout.label(text="Fill areas with missing surface data")
        
        # Fill Type dropdown
        layout.prop(scene, "fill_type", text="Fill Type")
        
        # Parameters based on fill type
        if scene.fill_type == 'SOLID':
            layout.prop(scene, "solid_color", text="")
        elif scene.fill_type == 'GRID':
            layout.prop(scene, "grid_axis", text="Axis")
            layout.prop(scene, "grid_scale", text="Scale")
        
        # F2 option
        layout.prop(scene, "use_f2_addon", text="Use F2 Addon")
        
        # Improve geometry option
        layout.prop(scene, "improve_geometry", text="Improve Geometry")
        
        # Fill button
        row = layout.row()
        op = row.operator("mesh.fill_nonmanifold", icon="NODE_MATERIAL")
        op.fill_type = scene.fill_type
        op.solid_color = scene.solid_color
        op.grid_axis = scene.grid_axis
        op.grid_scale = scene.grid_scale
        op.use_f2 = scene.use_f2_addon
        op.improve_geometry = scene.improve_geometry
        
        # Update and Remove
        row = layout.row(align=True)
        op = row.operator("mesh.adjust_nodata_material", icon="FILE_REFRESH", text="Update Pattern")
        op.fill_type = scene.fill_type
        op.solid_color = scene.solid_color
        op.grid_axis = scene.grid_axis
        op.grid_scale = scene.grid_scale
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
    bpy.types.Scene.fill_type = bpy.props.EnumProperty(
        name="Fill Type",
        description="Type of fill pattern to apply",
        items=[
            ('SOLID', "Solid Color", "Fill with a solid color"),
            ('GRID', "Grid Pattern", "Fill with a grid pattern"),
        ],
        default='SOLID'
    )
    
    bpy.types.Scene.solid_color = bpy.props.FloatVectorProperty(
        name="Color",
        description="Solid color for fill",
        subtype='COLOR',
        default=(0.8, 0.8, 0.8, 1.0),
        min=0.0,
        max=1.0,
        size=4
    )
    
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
    
    bpy.types.Scene.improve_geometry = bpy.props.BoolProperty(
        name="Improve Geometry",
        default=True,
        description="Beautify and triangulate the filling for better topology"
    )

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
    
    # Remove properties
    del bpy.types.Scene.fill_type
    del bpy.types.Scene.solid_color
    del bpy.types.Scene.grid_axis
    del bpy.types.Scene.grid_scale
    del bpy.types.Scene.use_f2_addon
    del bpy.types.Scene.improve_geometry

if __name__ == "__main__":
    register()