import bpy
import xml.etree.ElementTree as ET
import math
import os
from bpy_extras.io_utils import ImportHelper
from bpy.props import BoolProperty, StringProperty
from bpy.types import Panel
import re

import logging
log = logging.getLogger(__name__)

import platform
import subprocess

class RCSettings(bpy.types.PropertyGroup):
    rc_executable_path: bpy.props.StringProperty(
        name="RC Executable Path",
        description="Path to Reality Capture executable",
        default="C:\\Program Files\\Capturing Reality\\RealityCapture\\RealityCapture.exe" if platform.system() == "Windows" else "",
        subtype = 'FILE_PATH'    
    ) # type: ignore


    project_path: bpy.props.StringProperty(
        name="Project Path",
        description="Path to the Reality Capture project file",
        default="",
        subtype = 'FILE_PATH'
    ) # type: ignore


    exchange_folder: bpy.props.StringProperty(
        name="Exchange Folder",
        description="Path to the folder for exchanging tiles",
        default="",
        subtype = 'DIR_PATH'

    ) # type: ignore


    max_resolution: bpy.props.IntProperty(
        name="Max Resolution",
        description="Maximum resolution for export",
        default=4096,
        min=1024,
        max=16384
    ) # type: ignore
    detail_levels: bpy.props.IntProperty(
        name="Detail Levels",
        description="Number of detail levels to export",
        default=5,
        min=1,
        max=10
    ) # type: ignore
    texel_size: bpy.props.FloatProperty(
        name="Texel Size",
        description="Desired texel size in Reality Capture",
        default=0.01,
        min=0.001,
        max=1.0
    ) # type: ignore
    texture_resolution: bpy.props.IntProperty(
        name="Texture Resolution",
        description="Maximum texture resolution",
        default=2048,
        min=256,
        max=16384
    ) # type: ignore

class OBJECT_OT_ExportRC(bpy.types.Operator):
    bl_idname = "object.export_rc"
    bl_label = "Export to RC"
    
    def execute(self, context):
        settings = context.scene.rc_settings
        command = [
            settings.rc_executable_path,
            "-project", settings.project_path,
            "-set", "maxResolution", str(settings.max_resolution),
            "-set", "detailLevels", str(settings.detail_levels),
            "-set", "texelSize", str(settings.texel_size),
            "-set", "textureResolution", str(settings.texture_resolution),
            "-export", settings.exchange_folder
        ]
        try:
            subprocess.run(command, check=True)
        except subprocess.CalledProcessError as e:
            self.report({'ERROR'}, f"Failed to execute: {e}")
            return {'CANCELLED'}
        
        self.report({'INFO'}, "Export completed")
        return {'FINISHED'}

class OBJECT_OT_ImportOBJ(bpy.types.Operator):
    bl_idname = "object.import_obj"
    bl_label = "Import OBJ"
    
    def execute(self, context):
        settings = context.scene.rc_settings
        obj_files = [f for f in os.listdir(settings.exchange_folder) if f.endswith('.obj')]
        
        for obj_file in obj_files:
            bpy.ops.import_scene.obj(filepath=os.path.join(settings.exchange_folder, obj_file))
        
        self.report({'INFO'}, "Import completed")
        return {'FINISHED'}

class OBJECT_OT_ExportCleanedOBJ(bpy.types.Operator):
    bl_idname = "object.export_cleaned_obj"
    bl_label = "Export Cleaned OBJ"
    
    def execute(self, context):
        settings = context.scene.rc_settings
        export_path = os.path.join(settings.exchange_folder, "cleaned.obj")
        
        bpy.ops.export_scene.obj(filepath=export_path)
        
        self.report({'INFO'}, f"Cleaned OBJ exported to {export_path}")
        return {'FINISHED'}

class OBJECT_OT_TextureRC(bpy.types.Operator):
    bl_idname = "object.texture_rc"
    bl_label = "Texture in RC"
    
    def execute(self, context):
        settings = context.scene.rc_settings
        command = [
            settings.rc_executable_path,
            "-project", settings.project_path,
            "-set", "texelSize", str(settings.texel_size),
            "-set", "textureResolution", str(settings.texture_resolution),
            "-texture", "all"
        ]
        try:
            subprocess.run(command, check=True)
        except subprocess.CalledProcessError as e:
            self.report({'ERROR'}, f"Failed to execute: {e}")
            return {'CANCELLED'}
        
        self.report({'INFO'}, "Texturization completed")
        return {'FINISHED'}

class OBJECT_OT_organize_lods_to_collections(bpy.types.Operator):
    """Organize selected objects into collections based on their LOD suffix"""
    bl_idname = "organize.lods_to_collections"
    bl_label = "Organize LODs to Collections"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        selected_objects = context.selected_objects
        
        if not selected_objects:
            self.report({'WARNING'}, "No objects selected")
            return {'CANCELLED'}
        
        # Dictionary to track collections and objects
        lod_collections = {}
        
        # First pass: identify all LOD patterns and create collections
        for obj in selected_objects:
            import re
            lod_match = re.search(r'LOD\d+', obj.name)
            
            if lod_match:
                lod_name = lod_match.group()
                
                # Create collection if it doesn't exist
                if lod_name not in lod_collections:
                    if lod_name in bpy.data.collections:
                        lod_collections[lod_name] = bpy.data.collections[lod_name]
                    else:
                        new_collection = bpy.data.collections.new(lod_name)
                        context.scene.collection.children.link(new_collection)
                        lod_collections[lod_name] = new_collection
        
        # Second pass: organize objects
        for obj in selected_objects:
            lod_match = re.search(r'LOD\d+', obj.name)
            
            if lod_match:
                lod_name = lod_match.group()
                target_collection = lod_collections[lod_name]
                
                # Skip if object is already in the target collection
                if obj.name in target_collection.objects:
                    continue
                
                # Get all collections containing this object (except Scene Collection)
                current_collections = []
                for col in bpy.data.collections:
                    if obj.name in col.objects and col != context.scene.collection:
                        current_collections.append(col)
                
                # Add to target collection
                target_collection.objects.link(obj)

                # Remove from ALL other collections (except the Scene Collection)
                for col in bpy.data.collections:
                    if obj.name in col.objects and col != target_collection and col != context.scene.collection:
                        col.objects.unlink(obj)
            else:
                self.report({'INFO'}, f"No LOD pattern found in object: {obj.name}")
        
        if not lod_collections:
            self.report({'WARNING'}, "No LOD patterns found in selected objects")
            return {'CANCELLED'}
        
        self.report({'INFO'}, f"Organized objects into {len(lod_collections)} LOD collections")
        return {'FINISHED'}

class OBJECT_OT_correct_rc_lod_names(bpy.types.Operator):
    """Correct names of imported LOD objs, meshes and materials - works for both old and new naming formats"""
    bl_idname = "correct.rcnames"
    bl_label = "Correct LOD Names (Mesh & Materials)"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        self.rename_lods_reality_capture()
        return {'FINISHED'}
    
    def rename_lods_reality_capture(self):
        # Get all selected objects in the scene
        selected_objects = bpy.context.selected_objects
        
        # Loop through each selected object
        for obj in selected_objects:
            # Check if it's a mesh object
            if obj.type != 'MESH':
                continue
                
            # First determine if the object name contains LOD pattern
            lod_match = re.search(r'LOD\d+', obj.name)
            if not lod_match:
                continue
                
            lod_part = lod_match.group()  # e.g., 'LOD0', 'LOD1', etc.
            
            # CASE 1: Objects with old naming format "__LODx_number"
            old_format_match = re.search(r'(.+?)_(LOD\d+)_(\d+)', obj.name)
            if old_format_match:
                base_name = old_format_match.group(1)  # e.g. "Basilica"
                lod_part = old_format_match.group(2)   # e.g. "LOD0"
                number_part = old_format_match.group(3)  # e.g. "0000001"
                
                # Create the new name in the format desired
                new_name = f"{base_name}_{number_part}_{lod_part}"
                obj.name = new_name
                print(f"Object renamed (old format) to '{new_name}'")
            
            # CASE 2: Objects with new naming format "__number_LODx" but possibly not fixed meshes/materials
            new_format_match = re.search(r'(.+?)_(\d+)_(LOD\d+)', obj.name)
            if new_format_match:
                base_name = new_format_match.group(1)  # e.g. "Basilica"
                number_part = new_format_match.group(2)  # e.g. "0000001"
                lod_part = new_format_match.group(3)   # e.g. "LOD0"
                
                # Object is already correctly named, but we'll process meshes and materials anyway
                print(f"Object already correctly named as '{obj.name}', checking mesh and materials...")
            
            # If neither pattern matched, try a more generic approach for unusual cases
            if not old_format_match and not new_format_match:
                # Split by underscores and try to identify components
                parts = re.split('_+', obj.name)
                
                # Check if we have at least 3 parts and LOD is one of them
                if len(parts) >= 3:
                    # Find which part contains LOD
                    lod_idx = -1
                    number_idx = -1
                    
                    for i, part in enumerate(parts):
                        if 'LOD' in part:
                            lod_idx = i
                        elif part.isdigit():
                            number_idx = i
                    
                    if lod_idx >= 0 and number_idx >= 0:
                        # Construct name from parts, putting LOD at the end
                        base_parts = [p for i, p in enumerate(parts) if i != lod_idx and i != number_idx]
                        base_name = '_'.join(base_parts)
                        number_part = parts[number_idx]
                        lod_part = parts[lod_idx]
                        
                        new_name = f"{base_name}_{number_part}_{lod_part}"
                        obj.name = new_name
                        print(f"Object renamed (generic format) to '{new_name}'")
            
            # Now fix the mesh data name regardless of object name pattern
            if obj.data:
                # Try to match the same patterns in the mesh name
                mesh_old_format = re.search(r'(.+?)_(LOD\d+)_(\d+)', obj.data.name)
                mesh_new_format = re.search(r'(.+?)_(\d+)_(LOD\d+)', obj.data.name)
                
                if mesh_old_format:
                    mesh_base = mesh_old_format.group(1)
                    mesh_lod = mesh_old_format.group(2)
                    mesh_num = mesh_old_format.group(3)
                    obj.data.name = f"{mesh_base}_{mesh_num}_{mesh_lod}"
                    print(f"Mesh renamed to '{obj.data.name}'")
                elif mesh_new_format:
                    # Mesh already has correct format
                    pass
                else:
                    # Use object name as reference, prefix with ME_
                    obj.data.name = f"ME_{obj.name}"
                    print(f"Mesh renamed to 'ME_{obj.name}'")
            
            # Fix the materials
            for slot in obj.material_slots:
                if slot.material:
                    mat_name = slot.material.name
                    
                    # Check material name patterns
                    mat_old_format = re.search(r'(.+?)_(LOD\d+)_(.+)', mat_name)
                    mat_new_format = re.search(r'(.+?)_(.+)_(LOD\d+)', mat_name)
                    
                    if mat_old_format:
                        mat_base = mat_old_format.group(1)  # e.g. "Basilica"
                        mat_lod = mat_old_format.group(2)   # e.g. "LOD0"
                        mat_suffix = mat_old_format.group(3)  # e.g. "u0_v0"
                        
                        new_mat_name = f"{mat_base}_{mat_suffix}_{mat_lod}"
                        slot.material.name = new_mat_name
                        print(f"Material renamed to '{new_mat_name}'")
                    elif mat_new_format:
                        # Material already has correct format
                        pass
                    else:
                        # For materials with unknown format, try a more generic approach
                        if lod_match:
                            # Extract any part that might be position identifiers (u#_v#)
                            uv_match = re.search(r'(u\d+_v\d+)', mat_name)
                            if uv_match:
                                uv_part = uv_match.group(1)
                                # Remove the object name and LOD part from material if present
                                base_part = re.sub(r'_LOD\d+', '', mat_name)
                                base_part = re.sub(r'_' + re.escape(uv_part), '', base_part)
                                
                                new_mat_name = f"{base_part}_{uv_part}_{lod_part}"
                                slot.material.name = new_mat_name
                                print(f"Material renamed (generic) to '{new_mat_name}'")
                            else:
                                # Just add the LOD suffix if no UV part is found
                                if lod_part not in mat_name:
                                    new_mat_name = f"{mat_name}_{lod_part}"
                                    slot.material.name = new_mat_name
                                    print(f"Material renamed (simple) to '{new_mat_name}'")

class ReconstructionRegion:
    def __init__(self, file_path=None):
        self.file_path = file_path
        self.globalCoordinateSystem = ""
        self.globalCoordinateSystemWkt = ""
        self.globalCoordinateSystemName = ""
        self.isGeoreferenced = ""
        self.isLatLon = ""
        self.yawPitchRoll = ""
        self.widthHeightDepth = ""
        self.magic = ""
        self.version = ""
        self.centre = ""
        self.residual = {"R": "", "t": "", "s": "", "ownerId": ""}
        
        if file_path:
            self.read_file(file_path)
    
    def read_file(self, file_path):
        tree = ET.parse(file_path)
        root = tree.getroot()
        
        # Attributi direttamente dall'elemento radice
        self.globalCoordinateSystem = root.attrib.get('globalCoordinateSystem', '')
        self.globalCoordinateSystemWkt = root.attrib.get('globalCoordinateSystemWkt', '')
        self.globalCoordinateSystemName = root.attrib.get('globalCoordinateSystemName', '')
        self.isGeoreferenced = root.attrib.get('isGeoreferenced', '')
        self.isLatLon = root.attrib.get('isLatLon', '')
        
        # I seguenti valori sono letti come testo degli elementi figli
        self.yawPitchRoll = root.find('yawPitchRoll').text if root.find('yawPitchRoll') is not None else ''
        self.widthHeightDepth = root.find('widthHeightDepth').text if root.find('widthHeightDepth') is not None else ''
        
        header = root.find('Header')
        if header is not None:
            self.magic = header.attrib.get('magic', '')
            self.version = header.attrib.get('version', '')
        
        centreEuclid = root.find('CentreEuclid')
        if centreEuclid is not None:
            self.centre = centreEuclid.attrib.get('centre', '')
        
        residual = root.find('Residual')
        if residual is not None:
            self.residual['R'] = residual.attrib.get('R', '')
            self.residual['t'] = residual.attrib.get('t', '')
            self.residual['s'] = residual.attrib.get('s', '')
            self.residual['ownerId'] = residual.attrib.get('ownerId', '')

        centreEuclid = root.find('CentreEuclid/centre')
        if centreEuclid is not None:
            self.centre = centreEuclid.text  # Ottenere il testo dell'elemento, non un attributo


    def write_file(self, file_path=None):
        root = ET.Element("ReconstructionRegion", globalCoordinateSystem=self.globalCoordinateSystem, 
                          globalCoordinateSystemWkt=self.globalCoordinateSystemWkt,
                          globalCoordinateSystemName=self.globalCoordinateSystemName, 
                          isGeoreferenced=self.isGeoreferenced, isLatLon=self.isLatLon)
        
        ET.SubElement(root, "yawPitchRoll").text = self.yawPitchRoll
        ET.SubElement(root, "widthHeightDepth").text = self.widthHeightDepth
        
        ET.SubElement(root, "Header", magic=self.magic, version=self.version)
        ET.SubElement(root, "CentreEuclid", centre=self.centre)
        
        ET.SubElement(root, "Residual", R=self.residual['R'], t=self.residual['t'],
                      s=self.residual['s'], ownerId=self.residual['ownerId'])
        
        tree = ET.ElementTree(root)
        tree.write(file_path if file_path else self.file_path, encoding='utf-8', xml_declaration=True)
        
class ImportReconstructionRegion(bpy.types.Operator, ImportHelper):
    """Imports a ReconstructionRegion and draws it as geometry"""
    bl_idname = "import.reconstruction_region"
    bl_label = "Import Reconstruction Region"
    
    # ImportHelper mixin class uses this
    filename_ext = ".rcbox"

    filter_glob: StringProperty(
        default="*.rcbox",
        options={'HIDDEN'},
        maxlen=255,  # Max internal buffer length, longer would be clamped.
    ) # type: ignore

    apply_shift: BoolProperty(
        name="Apply Shift",
        description="Apply a global shift to the coordinates",
        default=False,
    ) # type: ignore

    def execute(self, context):
        # Assicurati che il percorso del file non sia vuoto
        if not self.filepath:
            self.report({'ERROR'}, "No file selected")
            return {'CANCELLED'}
        # Ottieni il nome del file senza estensione
        mesh_name = os.path.splitext(os.path.basename(self.filepath))[0]
        region = ReconstructionRegion(self.filepath)
        self.create_geometry(context, region, mesh_name)
        self.report({'INFO'}, f"Imported file: {self.filepath}")
        return {'FINISHED'}

    def create_geometry(self, context, region, mesh_name):
        # Estrapolazione delle dimensioni dalla region
        dimensions = [float(x) for x in region.widthHeightDepth.split()]
        #location = [float(x) for x in region.centre.split()[1:]]  # Presupponendo che 'centre' sia in un formato adatto
        #location = [float(x) for x in region.centre.split()]
        
        if region.centre:
            location = [float(x) for x in region.centre.split()]
        else:
            location = [0,0,0]  # Valore di fallback nel caso non ci sia un centro definito
            self.report({'INFO'}, "Error: can't load the location of the rcbox. I assume 0,0,0")



        if self.apply_shift:
                # Applica lo shift ai valori delle coordinate
                shift_x = context.scene.BL_x_shift
                shift_y = context.scene.BL_y_shift
                shift_z = context.scene.BL_z_shift
                
                location = [location[0] - shift_x, location[1] - shift_y, location[2] - shift_z]
    
        # Creazione della mesh
        bpy.ops.mesh.primitive_cube_add(size=2, location=location)
        obj = bpy.context.object
        obj.scale = (dimensions[0] / 2, dimensions[1] / 2, dimensions[2] / 2)  # Blender usa la metà delle dimensioni per i cubi
        obj.name = mesh_name
        # Applicazione della rotazione
        yaw, pitch, roll = [math.radians(float(x)) for x in region.yawPitchRoll.split()]
        # Blender utilizza l'ordine di rotazione XYZ, quindi convertiamo di conseguenza
        #obj.rotation_euler = (roll, pitch, -yaw)
        obj.rotation_euler = (yaw, pitch, -roll)
        # La conversione dipende dall'interpretazione esatta dei valori e dall'orientamento del sistema di coordinate

        # Aggiornamento della scena per riflettere le modifiche
        context.view_layer.update()

class OBJECT_OT_ExportLOD(bpy.types.Operator):
    bl_idname = "object.export_lod"
    bl_label = "Export LOD to Exchange Folder"
    
    def execute(self, context):
        settings = context.scene.rc_settings
        
        # Trova le informazioni del modello
        info_command = [
            settings.rc_executable_path,
            "-load", settings.project_path,
            "-info", "model"
        ]
        try:
            result = subprocess.run(info_command, check=True, capture_output=True, text=True)
        except subprocess.CalledProcessError as e:
            self.report({'ERROR'}, f"Failed to get model info: {e.stderr}")
            return {'CANCELLED'}
        
        # Analizza l'output per trovare il nome del modello
        model_name = None
        for line in result.stdout.splitlines():
            if "Model name:" in line:
                model_name = line.split(":")[1].strip()
                break
        
        if not model_name:
            self.report({'ERROR'}, "Model name could not be determined")
            return {'CANCELLED'}

        # Esporta il modello LOD
        export_command = [
            settings.rc_executable_path,
            "-load", settings.project_path,
            "-selectModel", model_name,
            "-exportLod", os.path.join(settings.exchange_folder, "model.obj")
        ]
        try:
            result = subprocess.run(export_command, check=True, capture_output=True, text=True)
            self.report({'INFO'}, f"LOD Export completed: {result.stdout}")
        except subprocess.CalledProcessError as e:
            self.report({'ERROR'}, f"Failed to execute: {e.stderr}")
            return {'CANCELLED'}
        
        return {'FINISHED'}

class ToolsPanel_dsc_RC:
    bl_label = "Reality Capture Integration"
    bl_idname = "SCENE_PT_rc_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'RC Tools'

    @classmethod
    def poll(cls, context):
        return platform.system() == "Windows"

    def draw(self, context):
        layout = self.layout
        scene = context.scene
        obj = context.object

        settings = context.scene.rc_settings
        
        layout.prop(settings, "rc_executable_path")
        layout.prop(settings, "project_path")
        layout.prop(settings, "exchange_folder")
        layout.prop(settings, "max_resolution")
        layout.prop(settings, "detail_levels")
        layout.prop(settings, "texel_size")
        layout.prop(settings, "texture_resolution")
        
        layout.operator("object.export_lod", text="Export LOD RC->CS")
        layout.operator("object.export_rc", text="Export RC->CS")

        layout.operator("object.import_obj", text="Import OBJ CS->BL")
        layout.operator("object.export_cleaned_obj", text="Export Cleaned OBJ BL->CS")
        layout.operator("object.texture_rc", text="Texture in RC")
        
        layout.separator()
        box = layout.box()
        box.label(text="RealityCapture Tools:")
        row = box.row()
        self.layout.operator("import.reconstruction_region", text="Import Reconstruction Region")
        row = box.row()
        row.operator("correct.rcnames", icon="DECORATE_DRIVER", text='Correct RC Names')
        row = box.row()
        row.operator("organize.lods_to_collections", icon="OUTLINER_COLLECTION", text='Organize LODs to Collections')

class VIEW3D_PT_dsc_Rc_ToolBar(Panel, ToolsPanel_dsc_RC):
    bl_category = "3DSC"
    bl_idname = "VIEW3D_PT_dsc_Rc_ToolBar"
    bl_context = "objectmode"
    bl_options = {'DEFAULT_CLOSED'}
    
def menu_func(self, context):
    self.layout.operator(ImportReconstructionRegion.bl_idname)

classes = [
    VIEW3D_PT_dsc_Rc_ToolBar,
    OBJECT_OT_correct_rc_lod_names,
    ImportReconstructionRegion,
    RCSettings,
    OBJECT_OT_ExportRC,
    OBJECT_OT_ImportOBJ,
    OBJECT_OT_ExportCleanedOBJ,
    OBJECT_OT_TextureRC,
    OBJECT_OT_ExportLOD,
    OBJECT_OT_organize_lods_to_collections
]

def register():
    for cls in classes:
        try:
            bpy.utils.register_class(cls)
        except ValueError:
            log.warning(
                '{} is already registered, now unregister and retry... '.format(cls))
            bpy.utils.unregister_class(cls)
            bpy.utils.register_class(cls)

    bpy.types.TOPBAR_MT_file_import.append(menu_func)
    bpy.types.Scene.rc_settings = bpy.props.PointerProperty(type=RCSettings)


def unregister():
    for cls in classes:
        bpy.utils.unregister_class(cls)

    bpy.types.TOPBAR_MT_file_import.remove(menu_func)
    del bpy.types.Scene.rc_settings

if __name__ == "__main__":
    register()
