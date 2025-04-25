"""
User interface components for METS metadata exporter.
Contains all panels for the 3D Survey Collection addon.
"""

import bpy
from bpy.types import Panel
from . import utils

# -----------------------------------------------------------------------------
# UI Panels
# -----------------------------------------------------------------------------

class METS_PT_ExportPanel(Panel):
    """Panel for exporting METS metadata for 3D models."""
    bl_label = "METS Metadata Export"
    bl_idname = "METS_PT_ExportPanel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = '3DSC'
    bl_options = {'DEFAULT_CLOSED'}
    
    def draw(self, context):
        layout = self.layout
        scene = context.scene
        
        # Export settings
        box = layout.box()
        box.label(text="Export Settings", icon='EXPORT')
        
        export_settings = scene.mets_export_settings
        box.prop(export_settings, "export_path")
        box.prop(export_settings, "file_name")
        row = box.row()
        row.prop(export_settings, "use_selection")
        row.prop(export_settings, "include_checksum")
        
        # METS specific settings
        box.prop(export_settings, "mets_profile")
        box.prop(export_settings, "mets_objid")
        
        # Export button
        layout.separator()
        row = layout.row()
        row.scale_y = 1.5
        row.operator("mets.export_mets", icon='FILE_TICK')
        
        # Help text
        layout.separator()
        help_box = layout.box()
        help_box.label(text="About METS Export", icon='HELP')
        col = help_box.column(align=True)
        col.label(text="This tool exports METS metadata for 3D models")
        col.label(text="It includes technical, descriptive, rights, and")
        col.label(text="source metadata according to the METS standard")
        col.label(text="Used in cultural heritage and digital preservation")

class METS_PT_IdentificationPanel(Panel):
    """Panel for identification metadata."""
    bl_label = "Identification Metadata"
    bl_idname = "METS_PT_IdentificationPanel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = '3DSC'
    bl_parent_id = "METS_PT_ExportPanel"
    bl_options = {'DEFAULT_CLOSED'}
    
    def draw(self, context):
        layout = self.layout
        scene = context.scene
        ident_props = scene.mets_identification
        
        # Object selector (if not using selection)
        if not scene.mets_export_settings.use_selection:
            layout.prop(scene.mets_export_settings, "object_name")
        
        # Identification metadata
        col = layout.column(align=True)
        col.prop(ident_props, "title")
        col.prop(ident_props, "creator")
        col.prop(ident_props, "date")
        
        layout.separator()
        col = layout.column(align=True)
        col.prop(ident_props, "description")
        col.prop(ident_props, "subject")
        
        layout.separator()
        col = layout.column(align=True)
        col.prop(ident_props, "type")
        col.prop(ident_props, "format")
        col.prop(ident_props, "identifier")
        col.prop(ident_props, "relation")
        
        # Load from object button
        layout.separator()
        row = layout.row()
        row.operator("mets.load_identification_from_object", icon='FILE_REFRESH')

class METS_PT_SourcePanel(Panel):
    """Panel for source metadata."""
    bl_label = "Source Metadata"
    bl_idname = "METS_PT_SourcePanel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = '3DSC'
    bl_parent_id = "METS_PT_ExportPanel"
    bl_options = {'DEFAULT_CLOSED'}
    
    def draw(self, context):
        layout = self.layout
        scene = context.scene
        source_props = scene.mets_source
        
        col = layout.column(align=True)
        col.prop(source_props, "current_location")
        col.prop(source_props, "institutional_id")
        
        layout.separator()
        col = layout.column(align=True)
        col.prop(source_props, "conservation_state")
        col.prop(source_props, "materials")

class METS_PT_TechnicalPanel(Panel):
    """Panel for technical metadata."""
    bl_label = "Technical Metadata"
    bl_idname = "METS_PT_TechnicalPanel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = '3DSC'
    bl_parent_id = "METS_PT_ExportPanel"
    bl_options = {'DEFAULT_CLOSED'}
    
    def draw(self, context):
        layout = self.layout
        scene = context.scene
        tech_props = scene.mets_technical
        
        # Active object stats
        if context.active_object and context.active_object.type == 'MESH':
            obj = context.active_object
            stats = utils.get_mesh_statistics(obj)
            
            box = layout.box()
            box.label(text=f"Active Object: {obj.name}", icon='MESH_DATA')
            



            # pulsante per calcolare le statistiche su richiesta
            row = box.row()
            row.operator("mets.calculate_mesh_stats", icon='FILE_REFRESH')
            
            # Mostra statistiche di base che sono veloci da recuperare
            col = box.column(align=True)
            col.label(text=f"Vertices: {len(obj.data.vertices):,}")
            col.label(text=f"Faces: {len(obj.data.polygons):,}")
            
            # statistiche avanzate solo se sono state già calcolate
            if 'mets_stats_calculated' in obj:
                col.label(text=f"Triangles: {obj.get('triangle_count', 0):,}")
                
                if obj.get('uv_count', 0) > 0:
                    col.label(text=f"UV Coordinates: {obj.get('uv_count', 0):,}")
                    col.label(text=f"UV Efficiency: {obj.get('uv_efficiency', 0) * 100:.1f}%")
                
                col.label(text=f"Surface Area: {obj.get('surface_area', 0):.2f} m²")
                col.label(text=f"Triangles/m²: {obj.get('triangles_per_sqm', 0):.2f}")
                
            # Object dimensions
            width, height, depth = utils.get_obj_dimensions(obj)
            box.label(text=f"Dimensions (cm): {width:.1f} × {height:.1f} × {depth:.1f}")
        
        # Acquisition method
        layout.separator()
        layout.label(text="Acquisition", icon='CAMERA_DATA')
        layout.prop(tech_props, "acquisition_method")
        
        # Show relevant fields based on acquisition method
        if tech_props.acquisition_method != 'Modellazione Manuale':
            col = layout.column(align=True)
            col.prop(tech_props, "device_manufacturer")
            col.prop(tech_props, "device_model")
            
            # Photogrammetry specific
            if tech_props.acquisition_method == 'Fotogrammetria':
                box = layout.box()
                box.label(text="Photography Settings", icon='OUTLINER_OB_CAMERA')
                
                col = box.column(align=True)
                col.prop(tech_props, "image_count")
                col.prop(tech_props, "focal_length")
                col.prop(tech_props, "aperture")
                col.prop(tech_props, "iso")
            
            # Scanning specific
            elif tech_props.acquisition_method in ['Scansione Laser', 'Structured Light']:
                box = layout.box()
                box.label(text="Scanning Settings", icon='LIGHT_DATA')
                
                col = box.column(align=True)
                col.prop(tech_props, "scan_count")
            
            # Lighting for all methods
            layout.prop(tech_props, "lighting")
        
        # Processing software
        layout.separator()
        layout.label(text="Processing", icon='MODIFIER_DATA')
        col = layout.column(align=True)
        col.prop(tech_props, "software")
        col.prop(tech_props, "software_version")
        col.prop(tech_props, "operator")
        
        # Load from object button
        layout.separator()
        row = layout.row()
        row.operator("mets.load_technical_from_object", icon='FILE_REFRESH')

class METS_PT_RightsPanel(Panel):
    """Panel for rights metadata."""
    bl_label = "Rights Metadata"
    bl_idname = "METS_PT_RightsPanel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = '3DSC'
    bl_parent_id = "METS_PT_ExportPanel"
    bl_options = {'DEFAULT_CLOSED'}
    
    def draw(self, context):
        layout = self.layout
        scene = context.scene
        rights_props = scene.mets_rights
        
        col = layout.column(align=True)
        col.prop(rights_props, "rights_holder")
        col.prop(rights_props, "rights_holder_contact")
        
        layout.separator()
        col = layout.column(align=True)
        col.prop(rights_props, "license_url")
        col.prop(rights_props, "rights_statement")

class METS_PT_TexturesPanel(Panel):
    """Panel for texture files."""
    bl_label = "Texture Files"
    bl_idname = "METS_PT_TexturesPanel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = '3DSC'
    bl_parent_id = "METS_PT_ExportPanel"
    bl_options = {'DEFAULT_CLOSED'}
    
    def draw(self, context):
        layout = self.layout
        scene = context.scene
        
        row = layout.row()
        row.template_list("METS_UL_TextureList", "", scene, "mets_texture_files", scene, "mets_texture_file_index")
        
        col = row.column(align=True)
        col.operator("mets.add_texture_file", icon='ADD', text="")
        col.operator("mets.remove_texture_file", icon='REMOVE', text="")
        col.operator("mets.load_textures_from_materials", icon='FILE_REFRESH', text="")
        
        # Show selected texture properties
        if scene.mets_texture_files and scene.mets_texture_file_index >= 0:
            texture = scene.mets_texture_files[scene.mets_texture_file_index]
            
            layout.separator()
            box = layout.box()
            col = box.column(align=True)
            col.prop(texture, "name")
            col.prop(texture, "type")
            col.prop(texture, "filepath")

class METS_PT_ToolsPanel(Panel):
    """Panel for metadata tools."""
    bl_label = "Metadata Tools"
    bl_idname = "METS_PT_ToolsPanel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = '3DSC'
    bl_parent_id = "METS_PT_ExportPanel"
    bl_options = {'DEFAULT_CLOSED'}
    
    def draw(self, context):
        layout = self.layout
        
        # Store metadata in object
        box = layout.box()
        box.label(text="Store/Load Metadata", icon='FILE_BLEND')
        
        row = box.row(align=True)
        row.operator("mets.store_metadata_to_object", icon='EXPORT')
        
        # Analyze section
        layout.separator()
        box = layout.box()
        box.label(text="Analysis Tools", icon='VIEWZOOM')
        
        col = box.column(align=True)
        col.label(text="Calculate mesh statistics:")
        row = col.row(align=True)
        row.operator("mets.analyze_texel_density", icon='UV_DATA')
        row.operator("mets.analyze_uv_efficiency", icon='UV')

# -----------------------------------------------------------------------------
# Registration
# -----------------------------------------------------------------------------

# List of classes for registration
classes = [
    METS_PT_ExportPanel,
    METS_PT_IdentificationPanel,
    METS_PT_SourcePanel,
    METS_PT_TechnicalPanel,
    METS_PT_RightsPanel,
    METS_PT_TexturesPanel,
    METS_PT_ToolsPanel,
]

def register():
    for cls in classes:
        bpy.utils.register_class(cls)

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)

if __name__ == "__main__":
    register()