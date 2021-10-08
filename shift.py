import bpy
from .functions import *
from bpy.types import Operator
from bpy_extras.io_utils import ImportHelper
from bpy.props import (BoolProperty,
                       FloatProperty,
                       IntProperty,
                       StringProperty,
                       EnumProperty,
                       CollectionProperty
                       )

class ImportCoordinateShift(Operator, ImportHelper):
    """Tool to import shift coordinates from a txt file"""
    bl_idname = "import_fromfile.shift_valcoor"  # important since its how bpy.ops.import_file.pano_data is constructed
    bl_label = "Import positions"

    # ImportHelper mixin class uses this
    filename_ext = ".txt"

    filter_glob: StringProperty(
            default="*.txt",
            options={'HIDDEN'},
            maxlen=255,  # Max internal buffer length, longer would be clamped.
            )

    def execute(self, context):
        return read_shift_data(context, self.filepath)

def read_shift_data(context, filepath):
    scene = context.scene
    f=open(filepath,'r')
    arr=f.readlines()
    print(str(arr))
    data_coordinates = arr[0].split(' ')
    scene['BL_x_shift'] = float(data_coordinates[1])
    scene['BL_y_shift'] = float(data_coordinates[2])
    scene['BL_z_shift'] = float(data_coordinates[3])
    scene['BL_epsg'] = data_coordinates[0].replace('EPSG::', '')
    return {'FINISHED'}

class OBJECT_OT_IMPORTUNSHIFT(bpy.types.Operator):
    """Import shift coordinates from a SHIFT txt file"""
    bl_idname = "shiftval_from.txtfile"
    bl_label = "Import shift coordinates from file"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        bpy.ops.import_fromfile.shift_valcoor('INVOKE_DEFAULT')
        return {'FINISHED'}    

class OBJECT_OT_IMPORTPOINTS(bpy.types.Operator):
    """Import points as empty objects from a txt file"""
    bl_idname = "shift_from.blendergis"
    bl_label = "Copy from BlenderGis"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        scene = context.scene
        scene['BL_x_shift'] = scene['crs x']
        scene['BL_y_shift'] = scene['crs y']

        return {'FINISHED'}