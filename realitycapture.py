import bpy
import xml.etree.ElementTree as ET
import math
import os
from bpy_extras.io_utils import ImportHelper
from bpy.props import BoolProperty, StringProperty, EnumProperty
from bpy.types import Operator


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
            self.report({'ERROR'}, "Nessun file selezionato")
            return {'CANCELLED'}
        # Ottieni il nome del file senza estensione
        mesh_name = os.path.splitext(os.path.basename(self.filepath))[0]
        region = ReconstructionRegion(self.filepath)
        self.create_geometry(context, region, mesh_name)
        self.report({'INFO'}, f"File importato: {self.filepath}")
        return {'FINISHED'}

    def create_geometry(self, context, region, mesh_name):
        # Estrapolazione delle dimensioni dalla region
        dimensions = [float(x) for x in region.widthHeightDepth.split()]
        #location = [float(x) for x in region.centre.split()[1:]]  # Presupponendo che 'centre' sia in un formato adatto
        location = [float(x) for x in region.centre.split()]

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


def menu_func(self, context):
    self.layout.operator(ImportReconstructionRegion.bl_idname)

def register():
    bpy.utils.register_class(ImportReconstructionRegion)
    bpy.types.TOPBAR_MT_file_import.append(menu_func)

def unregister():
    bpy.utils.unregister_class(ImportReconstructionRegion)
    bpy.types.TOPBAR_MT_file_import.remove(menu_func)

if __name__ == "__main__":
    register()






