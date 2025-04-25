"""
Operators for METS metadata exporter.
Contains Blender operators for user actions like loading metadata, analyzing models, etc.
"""

import bpy
from bpy.types import Operator
import os

from . import utils

# -----------------------------------------------------------------------------
# UI List Classes
# -----------------------------------------------------------------------------

class METS_UL_TextureList(bpy.types.UIList):
    """UI list for textures."""
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname):
        if self.layout_type in {'DEFAULT', 'COMPACT'}:
            row = layout.row()
            row.label(text=item.name, icon='TEXTURE')
            row.label(text=item.type)
            row.label(text=os.path.basename(item.filepath))
        elif self.layout_type in {'GRID'}:
            layout.alignment = 'CENTER'
            layout.label(text=item.name, icon='TEXTURE')

# -----------------------------------------------------------------------------
# Operators
# -----------------------------------------------------------------------------

class METS_OT_AddTextureFile(Operator):
    """Add a texture file to the texture list."""
    bl_idname = "mets.add_texture_file"
    bl_label = "Add Texture File"
    bl_options = {'REGISTER', 'UNDO'}
    
    def execute(self, context):
        scene = context.scene
        texture_files = scene.mets_texture_files
        
        item = texture_files.add()
        item.name = f"Texture_{len(texture_files)}"
        
        return {'FINISHED'}

class METS_OT_RemoveTextureFile(Operator):
    """Remove a texture file from the texture list."""
    bl_idname = "mets.remove_texture_file"
    bl_label = "Remove Texture File"
    bl_options = {'REGISTER', 'UNDO'}
    
    def execute(self, context):
        scene = context.scene
        texture_files = scene.mets_texture_files
        index = scene.mets_texture_file_index
        
        if index >= 0 and index < len(texture_files):
            texture_files.remove(index)
            scene.mets_texture_file_index = min(index, len(texture_files) - 1)
        
        return {'FINISHED'}

class METS_OT_LoadTexturesFromMaterials(Operator):
    """Load textures from selected object materials."""
    bl_idname = "mets.load_textures_from_materials"
    bl_label = "Load Textures from Materials"
    bl_options = {'REGISTER', 'UNDO'}
    
    def execute(self, context):
        scene = context.scene
        texture_files = scene.mets_texture_files
        
        # Clear existing textures
        texture_files.clear()
        
        # Get selected objects or active object
        objects = context.selected_objects
        if not objects and context.active_object:
            objects = [context.active_object]
        
        # Process materials from objects
        for obj in objects:
            if obj.type != 'MESH':
                continue
                
            for slot in obj.material_slots:
                if not slot.material or not slot.material.use_nodes:
                    continue
                    
                for node in slot.material.node_tree.nodes:
                    if node.type == 'TEX_IMAGE' and node.image:
                        # Check if this texture is already in the list
                        texture_exists = False
                        for tex in texture_files:
                            if tex.name == node.image.name:
                                texture_exists = True
                                break
                                
                        if not texture_exists:
                            item = texture_files.add()
                            item.name = node.image.name
                            item.filepath = bpy.path.abspath(node.image.filepath)
                            
                            # Try to determine texture type from node connections
                            tex_type = "diffuse"  # Default
                            for output in node.outputs:
                                for link in output.links:
                                    if link.to_socket.name in ['Base Color', 'Color']:
                                        tex_type = "diffuse"
                                    elif link.to_socket.name in ['Normal', 'Normal Map']:
                                        tex_type = "normal"
                                    elif link.to_socket.name in ['Roughness']:
                                        tex_type = "roughness"
                                    elif link.to_socket.name in ['Metallic']:
                                        tex_type = "metallic"
                                    elif link.to_socket.name in ['Displacement']:
                                        tex_type = "displacement"
                            
                            item.type = tex_type
        
        self.report({'INFO'}, f"Loaded {len(texture_files)} textures from materials")
        return {'FINISHED'}

class METS_OT_LoadIdentificationFromObject(Operator):
    """Load identification metadata from object name and custom properties."""
    bl_idname = "mets.load_identification_from_object"
    bl_label = "Load Identification from Object"
    bl_options = {'REGISTER', 'UNDO'}
    
    def execute(self, context):
        obj = context.active_object
        if not obj:
            self.report({'ERROR'}, "No active object")
            return {'CANCELLED'}
        
        ident_props = context.scene.mets_identification
        
        # Set title from object name
        ident_props.title = obj.name
        
        # Try to extract other properties from custom properties
        if 'creator' in obj:
            ident_props.creator = str(obj['creator'])
        
        if 'date' in obj:
            ident_props.date = str(obj['date'])
        
        if 'description' in obj:
            ident_props.description = str(obj['description'])
        
        if 'subject' in obj:
            ident_props.subject = str(obj['subject'])
        
        if 'type' in obj:
            ident_props.type = str(obj['type'])
        
        if 'format' in obj:
            ident_props.format = str(obj['format'])
        
        if 'identifier' in obj:
            ident_props.identifier = str(obj['identifier'])
        
        if 'relation' in obj:
            ident_props.relation = str(obj['relation'])
        
        self.report({'INFO'}, f"Loaded identification metadata from {obj.name}")
        return {'FINISHED'}

class METS_OT_LoadTechnicalFromObject(Operator):
    """Load technical metadata from object."""
    bl_idname = "mets.load_technical_from_object"
    bl_label = "Load Technical from Object"
    bl_options = {'REGISTER', 'UNDO'}
    
    def execute(self, context):
        obj = context.active_object
        if not obj:
            self.report({'ERROR'}, "No active object")
            return {'CANCELLED'}
        
        tech_props = context.scene.mets_technical
        
        # Try to determine acquisition method from object name
        tech_props.acquisition_method = utils.get_acquisition_method_from_name(obj.name)
        
        # Try to extract other properties from custom properties
        if 'device_manufacturer' in obj:
            tech_props.device_manufacturer = str(obj['device_manufacturer'])
        
        if 'device_model' in obj:
            tech_props.device_model = str(obj['device_model'])
        
        if 'software' in obj:
            tech_props.software = str(obj['software'])
        
        if 'software_version' in obj:
            tech_props.software_version = str(obj['software_version'])
        
        if 'operator' in obj:
            tech_props.operator = str(obj['operator'])
        
        if 'image_count' in obj:
            tech_props.image_count = int(obj['image_count'])
        
        if 'scan_count' in obj:
            tech_props.scan_count = int(obj['scan_count'])
        
        if 'focal_length' in obj:
            tech_props.focal_length = str(obj['focal_length'])
        
        if 'aperture' in obj:
            tech_props.aperture = str(obj['aperture'])
        
        if 'iso' in obj:
            tech_props.iso = str(obj['iso'])
        
        if 'lighting' in obj:
            tech_props.lighting = str(obj['lighting'])
        
        self.report({'INFO'}, f"Loaded technical metadata from {obj.name}")
        return {'FINISHED'}

class METS_OT_StoreMetadataToObject(Operator):
    """Store current metadata settings to the active object."""
    bl_idname = "mets.store_metadata_to_object"
    bl_label = "Store Metadata to Object"
    bl_options = {'REGISTER', 'UNDO'}
    
    def execute(self, context):
        obj = context.active_object
        if not obj:
            self.report({'ERROR'}, "No active object")
            return {'CANCELLED'}
        
        # Store identification metadata
        ident_props = context.scene.mets_identification
        obj['title'] = ident_props.title
        obj['creator'] = ident_props.creator
        obj['date'] = ident_props.date
        obj['description'] = ident_props.description
        obj['subject'] = ident_props.subject
        obj['type'] = ident_props.type
        obj['format'] = ident_props.format
        obj['identifier'] = ident_props.identifier
        obj['relation'] = ident_props.relation
        
        # Store technical metadata
        tech_props = context.scene.mets_technical
        obj['acquisition_method'] = tech_props.acquisition_method
        obj['device_manufacturer'] = tech_props.device_manufacturer
        obj['device_model'] = tech_props.device_model
        obj['software'] = tech_props.software
        obj['software_version'] = tech_props.software_version
        obj['operator'] = tech_props.operator
        obj['image_count'] = tech_props.image_count
        obj['scan_count'] = tech_props.scan_count
        obj['focal_length'] = tech_props.focal_length
        obj['aperture'] = tech_props.aperture
        obj['iso'] = tech_props.iso
        obj['lighting'] = tech_props.lighting
        
        # Store source metadata
        source_props = context.scene.mets_source
        obj['current_location'] = source_props.current_location
        obj['institutional_id'] = source_props.institutional_id
        obj['conservation_state'] = source_props.conservation_state
        obj['materials'] = source_props.materials
        
        # Store rights metadata
        rights_props = context.scene.mets_rights
        obj['rights_holder'] = rights_props.rights_holder
        obj['rights_holder_contact'] = rights_props.rights_holder_contact
        obj['license_url'] = rights_props.license_url
        obj['rights_statement'] = rights_props.rights_statement
        
        self.report({'INFO'}, f"Stored metadata to {obj.name}")
        return {'FINISHED'}

class METS_OT_AnalyzeTexelDensity(Operator):
    """Calculate texel density for selected objects."""
    bl_idname = "mets.analyze_texel_density"
    bl_label = "Analyze Texel Density"
    bl_options = {'REGISTER', 'UNDO'}
    
    def execute(self, context):
        # Get selected objects or active object
        objects = context.selected_objects
        if not objects:
            if context.active_object and context.active_object.type == 'MESH':
                objects = [context.active_object]
        
        # Filter for mesh objects
        mesh_objects = [obj for obj in objects if obj.type == 'MESH']
        
        if not mesh_objects:
            self.report({'ERROR'}, "No mesh objects selected")
            return {'CANCELLED'}
        
        # Calculate texel density for each object
        report_text = "Texel Density Analysis:\n"
        for obj in mesh_objects:
            # Use 4K textures as baseline
            texel_density = utils.calculate_texel_density(obj, 4096, 4096)
            report_text += f"{obj.name}: {texel_density:.2f} texels/m²\n"
            
            # Store in object custom property
            obj['texel_density'] = texel_density
        
        # Show report
        self.report({'INFO'}, report_text)
        return {'FINISHED'}

class METS_OT_AnalyzeUVEfficiency(Operator):
    """Calculate UV mapping efficiency for selected objects."""
    bl_idname = "mets.analyze_uv_efficiency"
    bl_label = "Analyze UV Efficiency"
    bl_options = {'REGISTER', 'UNDO'}
    
    def execute(self, context):
        # Get selected objects or active object
        objects = context.selected_objects
        if not objects:
            if context.active_object and context.active_object.type == 'MESH':
                objects = [context.active_object]
        
        # Filter for mesh objects with UV maps
        mesh_objects = [obj for obj in objects if obj.type == 'MESH' and obj.data.uv_layers]
        
        if not mesh_objects:
            self.report({'ERROR'}, "No mesh objects with UV maps selected")
            return {'CANCELLED'}
        
        # Calculate UV efficiency for each object
        report_text = "UV Efficiency Analysis:\n"
        for obj in mesh_objects:
            efficiency = utils.calculate_uv_efficiency(obj)
            report_text += f"{obj.name}: {efficiency:.1%}\n"
            
            # Store in object custom property
            obj['uv_efficiency'] = efficiency
        
        # Show report
        self.report({'INFO'}, report_text)
        return {'FINISHED'}

class METS_OT_CalculateMeshStats(Operator):
    """Calculate detailed mesh statistics for the active object."""
    bl_idname = "mets.calculate_mesh_stats"
    bl_label = "Calculate Mesh Statistics"
    bl_options = {'REGISTER', 'UNDO'}
    
    def execute(self, context):
        obj = context.active_object
        if not obj or obj.type != 'MESH':
            self.report({'ERROR'}, "No active mesh object")
            return {'CANCELLED'}
        
        # Calcola statistiche e memorizzale nell'oggetto
        stats = utils.get_mesh_statistics(obj)
        
        # Memorizza i risultati nell'oggetto
        obj['triangle_count'] = stats['triangle_count']
        obj['uv_count'] = stats['uv_count']
        obj['uv_efficiency'] = stats['uv_efficiency']
        obj['surface_area'] = stats['surface_area']
        obj['triangles_per_sqm'] = stats['triangles_per_sqm']
        obj['mets_stats_calculated'] = True
        
        self.report({'INFO'}, f"Calculated mesh statistics for {obj.name}")
        return {'FINISHED'}

# -----------------------------------------------------------------------------
# Registration
# -----------------------------------------------------------------------------

# List of classes for registration
classes = [
    METS_UL_TextureList,
    METS_OT_AddTextureFile,
    METS_OT_RemoveTextureFile,
    METS_OT_LoadTexturesFromMaterials,
    METS_OT_LoadIdentificationFromObject,
    METS_OT_LoadTechnicalFromObject,
    METS_OT_StoreMetadataToObject,
    METS_OT_AnalyzeTexelDensity,
    METS_OT_AnalyzeUVEfficiency,
    METS_OT_CalculateMeshStats
]

def register():
    for cls in classes:
        bpy.utils.register_class(cls)

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)

if __name__ == "__main__":
    register()