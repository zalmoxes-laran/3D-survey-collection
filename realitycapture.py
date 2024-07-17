import bpy
import xml.etree.ElementTree as ET
import math
import os
from bpy_extras.io_utils import ImportHelper
from bpy.props import BoolProperty, StringProperty, EnumProperty
from bpy.types import Operator, Panel
import re

import logging
log = logging.getLogger(__name__)

import bpy
import os
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



class OBJECT_OT_correct_rc_lod_names(bpy.types.Operator):
    """Correct names of imported LOD objs"""
    bl_idname = "correct.rcnames"
    bl_label = "__LODx_number to __number_LODx"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        self.rename_lods_reality_capture()
        return {'FINISHED'}
    
    def rename_lods_reality_capture(self):
        # Ottieni tutti gli oggetti selezionati nella scena
        selected_objects = bpy.context.selected_objects
        
        # Ciclo su ogni oggetto selezionato
        for obj in selected_objects:
            # Usa una regex per dividere il nome in base a singoli o doppi underscore
            parts = re.split('_+', obj.name)  # Questo divide il nome sia per singoli che per multipli underscore

            # Verifica che ci siano almeno tre parti e che una di esse contenga 'LOD'
            if len(parts) > 2 and 'LOD' in parts[1]:
                # Estrai il numero di LOD (es. 'LOD0') e il numero finale
                lod_part = parts[1]  # 'LOD0', 'LOD1', ecc.
                number_part = parts[2]  # '0000000', ecc.

                # Ricostruisci il nome nel formato desiderato
                new_name = f"{parts[0]}_{number_part}_{lod_part}"

                # Assegna il nuovo nome all'oggetto
                obj.name = new_name
                print(f"Rinominato in '{new_name}'")


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
    """Importa una ReconstructionRegion e la disegna come geometria"""
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
            self.report({'INFO'}, f"Error: can't load the location of the rcbox. I assume 0,0,0")



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
        #addon_updater_ops.check_for_update_background()
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
        


        row = layout.row()
        self.layout.operator("import.reconstruction_region", text="Import Reconstruction Region")
        row = layout.row()
        row.operator("correct.rcnames", icon="DECORATE_DRIVER", text='Correct rc names')




class VIEW3D_PT_dsc_Rc_ToolBar(Panel, ToolsPanel_dsc_RC):
    bl_category = "3DSC"
    bl_idname = "VIEW3D_PT_dsc_Rc_ToolBar"
    bl_context = "objectmode"



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
    OBJECT_OT_ExportLOD
]


def register():
    for cls in classes:
        try:
            bpy.utils.register_class(cls)
        except ValueError as e:
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






