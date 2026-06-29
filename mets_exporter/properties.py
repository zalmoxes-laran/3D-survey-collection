"""
Property groups for METS metadata exporter.
Defines the data structures for storing metadata.
"""

import bpy
from bpy.props import (
    StringProperty,
    BoolProperty,
    EnumProperty,
    IntProperty,
    FloatProperty,
    PointerProperty,
    CollectionProperty
)
from bpy.types import PropertyGroup

# -----------------------------------------------------------------------------
# Property Groups
# -----------------------------------------------------------------------------

class METSIdentificationProperties(PropertyGroup):
    """Property group for identification metadata."""
    title: StringProperty(
        name="Title",
        description="Title of the 3D model",
        default=""
    )
    
    creator: StringProperty(
        name="Creator",
        description="Creator of the 3D model",
        default=""
    )
    
    date: StringProperty(
        name="Date",
        description="Date of creation (e.g., 'II secolo d.C.' or '2023-04-15')",
        default=""
    )
    
    description: StringProperty(
        name="Description",
        description="Description of the 3D model",
        default=""
    )
    
    subject: StringProperty(
        name="Subject",
        description="Subject keywords (semicolon separated)",
        default=""
    )
    
    type: StringProperty(
        name="Type",
        description="Type of object (e.g., Statua, Vaso)",
        default=""
    )
    
    format: StringProperty(
        name="Format",
        description="Material format (e.g., Marmo, Bronzo)",
        default=""
    )
    
    identifier: StringProperty(
        name="Identifier",
        description="Institutional identifier",
        default=""
    )
    
    relation: StringProperty(
        name="Relation",
        description="Collection relation (e.g., 'Collezione di Sculture Romane')",
        default=""
    )

class METSSourceProperties(PropertyGroup):
    """Property group for source metadata."""
    current_location: StringProperty(
        name="Current Location",
        description="Current physical location of the object",
        default=""
    )
    
    institutional_id: StringProperty(
        name="Institutional ID",
        description="Institutional inventory ID",
        default=""
    )
    
    conservation_state: StringProperty(
        name="Conservation State",
        description="Description of the conservation state",
        default=""
    )
    
    materials: StringProperty(
        name="Materials",
        description="Materials of the physical object",
        default=""
    )

class METSTechnicalProperties(PropertyGroup):
    """Property group for technical metadata."""
    acquisition_method: EnumProperty(
        name="Acquisition Method",
        description="Method used to acquire the 3D model",
        items=[
            ('Fotogrammetria', "Fotogrammetria", "Photogrammetry"),
            ('Scansione Laser', "Scansione Laser", "Laser Scanning"),
            ('Structured Light', "Structured Light", "Structured Light Scanning"),
            ('CT Scan', "CT Scan", "Computed Tomography Scanning"),
            ('Modellazione Manuale', "Modellazione Manuale", "Manual Modeling"),
            ('Procedural Modeling', "Procedural Modeling", "Procedural Modeling")
        ],
        default='Fotogrammetria'
    )
    
    device_manufacturer: StringProperty(
        name="Device Manufacturer",
        description="Manufacturer of the acquisition device",
        default=""
    )
    
    device_model: StringProperty(
        name="Device Model",
        description="Model of the acquisition device",
        default=""
    )
    
    software: StringProperty(
        name="Software",
        description="Software used for processing",
        default="Blender"
    )
    
    software_version: StringProperty(
        name="Software Version",
        description="Version of the software",
        default=bpy.app.version_string
    )
    
    operator: StringProperty(
        name="Operator",
        description="Name of the operator",
        default=""
    )
    
    image_count: IntProperty(
        name="Image Count",
        description="Number of images used for photogrammetry",
        default=0,
        min=0
    )
    
    scan_count: IntProperty(
        name="Scan Count",
        description="Number of scans for laser scanning",
        default=0,
        min=0
    )
    
    focal_length: StringProperty(
        name="Focal Length",
        description="Camera focal length (e.g., '50mm')",
        default=""
    )
    
    aperture: StringProperty(
        name="Aperture",
        description="Camera aperture (e.g., 'f/8')",
        default=""
    )
    
    iso: StringProperty(
        name="ISO",
        description="Camera ISO setting",
        default=""
    )
    
    lighting: StringProperty(
        name="Lighting",
        description="Lighting setup used during acquisition",
        default=""
    )

class METSRightsProperties(PropertyGroup):
    """Property group for rights metadata."""
    rights_holder: StringProperty(
        name="Rights Holder",
        description="Name of the rights holder",
        default=""
    )
    
    rights_holder_contact: StringProperty(
        name="Rights Holder Contact",
        description="Email of the rights holder",
        default=""
    )
    
    license_url: StringProperty(
        name="License URL",
        description="URL to the license",
        default="https://w3id.org/italia/controlled-vocabulary/licences/B117_BCS"
    )
    
    rights_statement: StringProperty(
        name="Rights Statement",
        description="Rights statement URL",
        default="http://rightsstatements.org/vocab/NoC-OKLR/1.0/"
    )

class METSExportSettings(PropertyGroup):
    """Property group for export settings."""
    export_path: StringProperty(
        name="Export Path",
        description="Path to export the METS XML file",
        default="//",
        subtype='DIR_PATH',
        # Blender 4.5+ flags blend-relative ("//") paths red unless opted in.
        options={'PATH_SUPPORTS_BLEND_RELATIVE'} if bpy.app.version >= (4, 5, 0) else set()
    )
    
    file_name: StringProperty(
        name="File Name",
        description="Name of the METS XML file",
        default="METS_3D_Export.xml"
    )
    
    object_name: StringProperty(
        name="Object Name",
        description="Object to export (empty for active)",
        default=""
    )
    
    use_selection: BoolProperty(
        name="Use Selection",
        description="Export metadata for selected objects",
        default=True
    )
    
    include_checksum: BoolProperty(
        name="Include Checksum",
        description="Calculate and include file checksums",
        default=False
    )
    
    mets_profile: StringProperty(
        name="METS Profile",
        description="METS profile identifier",
        default="METS ECO-MiC 1.2"
    )
    
    mets_objid: StringProperty(
        name="METS Object ID",
        description="METS object identifier",
        default="METS_3DSC_EXPORT"
    )

class METSTextureFileItem(PropertyGroup):
    """Property group for texture file items in the texture list."""
    name: StringProperty(
        name="Name",
        description="Texture name",
        default=""
    )
    
    filepath: StringProperty(
        name="File Path",
        description="Path to the texture file",
        default=""
    )
    
    type: EnumProperty(
        name="Type",
        description="Texture type",
        items=[
            ('diffuse', "Diffuse", "Diffuse/Color texture"),
            ('normal', "Normal", "Normal map"),
            ('displacement', "Displacement", "Displacement map"),
            ('roughness', "Roughness", "Roughness map"),
            ('metallic', "Metallic", "Metallic map"),
            ('ambient_occlusion', "Ambient Occlusion", "Ambient Occlusion map"),
            ('emissive', "Emissive", "Emissive map")
        ],
        default='diffuse'
    )

# -----------------------------------------------------------------------------
# Registration
# -----------------------------------------------------------------------------

# List of classes for registration
classes = [
    METSIdentificationProperties,
    METSSourceProperties,
    METSTechnicalProperties,
    METSRightsProperties,
    METSExportSettings,
    METSTextureFileItem,
]

def register():
    # Register classes
    for cls in classes:
        bpy.utils.register_class(cls)
    
    # Register properties
    bpy.types.Scene.mets_identification = PointerProperty(type=METSIdentificationProperties)
    bpy.types.Scene.mets_source = PointerProperty(type=METSSourceProperties)
    bpy.types.Scene.mets_technical = PointerProperty(type=METSTechnicalProperties)
    bpy.types.Scene.mets_rights = PointerProperty(type=METSRightsProperties)
    bpy.types.Scene.mets_export_settings = PointerProperty(type=METSExportSettings)
    
    # Texture files list
    bpy.types.Scene.mets_texture_files = CollectionProperty(type=METSTextureFileItem)
    bpy.types.Scene.mets_texture_file_index = IntProperty(name="Texture Index", default=0)

def unregister():
    # Unregister properties
    del bpy.types.Scene.mets_identification
    del bpy.types.Scene.mets_source
    del bpy.types.Scene.mets_technical
    del bpy.types.Scene.mets_rights
    del bpy.types.Scene.mets_export_settings
    del bpy.types.Scene.mets_texture_files
    del bpy.types.Scene.mets_texture_file_index
    
    # Unregister classes
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)

if __name__ == "__main__":
    register()