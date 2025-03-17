import bpy
import bmesh
from bpy.types import Operator, Panel
from bpy.props import BoolProperty, FloatProperty, EnumProperty, FloatVectorProperty
import time

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
        active_obj_name = active_obj.name if active_obj else None
        
        # Process objects one by one
        selected_objects = [obj for obj in context.selected_objects if obj.type == 'MESH']
        
        if not selected_objects:
            self.report({'WARNING'}, "No mesh objects selected")
            return {'CANCELLED'}
        
        # Make sure we're in object mode
        if context.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        
        processed_count = 0
        skipped_count = 0
        
        # First, create all materials (while in Object mode)
        materials_map = {}
        for obj in selected_objects:
            # Create a unique material name based on the object's name
            material_name = f"nodata_{obj.name}"
            print(f"Creating material '{material_name}' for object '{obj.name}'")
            
            # Remove any existing material with this name
            existing_mat = bpy.data.materials.get(material_name)
            if existing_mat:
                bpy.data.materials.remove(existing_mat)
            
            # Create new material
            nodata_mat = self.create_new_nodata_material(context, material_name)
            materials_map[obj.name] = nodata_mat
        
        # Now process each object individually
        for obj in selected_objects:
            print(f"\n\nProcessing object: {obj.name}")
            
            # Set the current object as active and deselect others
            bpy.ops.object.select_all(action='DESELECT')
            obj.select_set(True)
            context.view_layer.objects.active = obj
            
            # Get the material created for this object
            nodata_mat = materials_map.get(obj.name)
            if not nodata_mat:
                print(f"  Error: No material found for {obj.name}")
                skipped_count += 1
                continue
            
            # Add material to object
            if nodata_mat.name not in [slot.material.name if slot.material else "" for slot in obj.material_slots]:
                obj.data.materials.append(nodata_mat)
            
            # Get the index of the nodata material
            nodata_slot_index = -1
            for i, slot in enumerate(obj.material_slots):
                if slot.material and slot.material.name == nodata_mat.name:
                    nodata_slot_index = i
                    break
            
            if nodata_slot_index == -1:
                print(f"  Error: Material slot not found for {obj.name}")
                skipped_count += 1
                continue
            
            # Set the nodata material as active
            obj.active_material_index = nodata_slot_index
            
            # Switch to edit mode
            bpy.ops.object.mode_set(mode='EDIT')
            
            # Set selection mode to edges
            bpy.ops.mesh.select_mode(type='EDGE')
            
            # Select non-manifold edges
            bpy.ops.mesh.select_all(action='DESELECT')
            bpy.ops.mesh.select_non_manifold()
            
            # Get bmesh to check if we have selected edges
            me = obj.data
            bm = bmesh.from_edit_mesh(me)
            bm.select_flush(True)
            
            # Count selected edges
            selected_edges_count = len([e for e in bm.edges if e.select])
            print(f"  Selected non-manifold edges: {selected_edges_count}")
            
            if selected_edges_count > 0:
                try:
                    # Remember which edge indices were selected
                    selected_edge_indices = []
                    for i, e in enumerate(bm.edges):
                        if e.select:
                            # Store indices, not edges
                            selected_edge_indices.append(i)
                    
                    # Fill using edge_face_add
                    bpy.ops.mesh.edge_face_add()
                    print(f"  Created faces from edges")
                    
                    # Improve geometry if option is enabled
                    if self.improve_geometry:
                        bpy.ops.mesh.quads_convert_to_tris(quad_method='BEAUTY', ngon_method='BEAUTY')
                        bpy.ops.mesh.beautify_fill()
                        print(f"  Improved geometry")
                    
                    # After modifying the mesh, we need to update bmesh
                    bmesh.update_edit_mesh(me)
                    
                    # The BMesh may have changed, so we select faces in a different way
                    # Switch to face select mode
                    bpy.ops.mesh.select_mode(type='FACE')
                    
                    # Select all faces
                    bpy.ops.mesh.select_all(action='SELECT')
                    
                    # Invert the selection (select unassigned faces)
                    bpy.ops.object.material_slot_select()
                    bpy.ops.mesh.select_all(action='INVERT')
                    
                    # Assign material to selected faces (which are the newly created ones)
                    bpy.ops.object.material_slot_assign()
                    print(f"  Assigned material to new faces")
                    
                    # Use F2 addon if available and enabled
                    if self.use_f2:
                        try:
                            bpy.ops.mesh.f2()
                            # Re-select and assign material to any new faces
                            bpy.ops.mesh.select_all(action='DESELECT')
                            bpy.ops.object.material_slot_select()
                            bpy.ops.mesh.select_all(action='INVERT')
                            bpy.ops.object.material_slot_assign()
                        except Exception as e:
                            print(f"  F2 addon error: {str(e)}")
                    
                    processed_count += 1
                    print(f"  Successfully processed {obj.name}")
                    
                except Exception as e:
                    print(f"  Error during processing: {str(e)}")
                    # Continue to the next object
                    bpy.ops.object.mode_set(mode='OBJECT')
                    skipped_count += 1
                    continue
            else:
                print(f"  No non-manifold edges found in {obj.name}")
                skipped_count += 1
                # Clean up unused material
                bpy.ops.object.mode_set(mode='OBJECT')
                if nodata_mat.users == 1:  # Only used by this object
                    obj.active_material_index = nodata_slot_index
                    bpy.ops.object.material_slot_remove()
                    bpy.data.materials.remove(nodata_mat)
                continue
            
            # Return to object mode before processing the next object
            bpy.ops.object.mode_set(mode='OBJECT')
        
        # Restore original active object and selection
        bpy.ops.object.select_all(action='DESELECT')
        for obj in selected_objects:
            obj.select_set(True)
        
        if active_obj_name and active_obj_name in bpy.data.objects:
            context.view_layer.objects.active = bpy.data.objects[active_obj_name]
        
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
        active_obj_name = active_obj.name if active_obj else None
        
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
        
        # Restore original active object and selection
        if active_obj_name and active_obj_name in bpy.data.objects:
            context.view_layer.objects.active = bpy.data.objects[active_obj_name]
        
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
        active_obj_name = active_obj.name if active_obj else None
        
        selected_objects = [obj for obj in context.selected_objects if obj.type == 'MESH']
        
        if not selected_objects:
            self.report({'WARNING'}, "No mesh objects selected")
            return {'CANCELLED'}
        
        # Ensure we're in object mode
        if context.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        
        removed_count = 0
        skipped_count = 0
        materials_to_remove = []
        
        # Process each selected mesh object individually
        for obj in selected_objects:
            # Process one object at a time
            bpy.ops.object.select_all(action='DESELECT')
            obj.select_set(True)
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
                print(f"No nodata material found for {obj.name}")
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
            if nodata_mat not in materials_to_remove:
                materials_to_remove.append(nodata_mat)
            
            removed_count += 1
        
        # Remove materials that are no longer used
        for mat in materials_to_remove:
            if mat.users == 0:
                bpy.data.materials.remove(mat)
        
        # Restore original selection
        bpy.ops.object.select_all(action='DESELECT')
        for obj in selected_objects:
            obj.select_set(True)
        
        # Restore original active object
        if active_obj_name and active_obj_name in bpy.data.objects:
            context.view_layer.objects.active = bpy.data.objects[active_obj_name]
        
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