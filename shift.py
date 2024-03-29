# -*- coding:utf-8 -*-

import bpy
from .functions import *
from bpy.types import Operator
from bpy_extras.io_utils import ImportHelper
from bpy.props import (StringProperty,
                       )

from bpy.types import Panel
from bpy.types import PropertyGroup
from bpy.types import Menu, UIList

import logging
log = logging.getLogger(__name__)


class ImportCoordinateShift_dsc(Operator, ImportHelper):
    """Tool to import shift coordinates from a txt file"""
    bl_idname = "import_fromfile.shift_valcoor_dsc"  # important since its how bpy.ops.import_file.pano_data is constructed
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
    f = open(filepath, 'r')
    arr = f.readlines()
    print(str(arr))
    data_coordinates = arr[0].split(' ')
    scene['BL_x_shift'] = float(data_coordinates[1])
    scene['BL_y_shift'] = float(data_coordinates[2])
    scene['BL_z_shift'] = float(data_coordinates[3])
    scene['BL_epsg'] = data_coordinates[0].replace('EPSG::', '')
    return {'FINISHED'}


class OBJECT_OT_IMPORT_SHIFT(bpy.types.Operator):
    """Import shift coordinates from a SHIFT txt file"""
    bl_idname = "shiftval_from.txtfile_dsc"
    bl_label = "Import shift coordinates from file"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        bpy.ops.import_fromfile.shift_valcoor_dsc('INVOKE_DEFAULT')
        return {'FINISHED'}


class OBJECT_OT_IMPORT_BG(bpy.types.Operator):
    """Import points as empty objects from a txt file"""
    bl_idname = "shift_from.blendergis_dsc"
    bl_label = "Copy from BlenderGis"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        scene = context.scene
        scene['BL_x_shift'] = scene['crs x']
        scene['BL_y_shift'] = scene['crs y']

        return {'FINISHED'}

class ToolsPanel_dsc_SHIFT:
    bl_label = "Shifting"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    #bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        #addon_updater_ops.check_for_update_background()
        layout = self.layout
        scene = context.scene
        obj = context.object

        row = layout.row()
        row.label(text="Shift values:")
        row.operator("shiftval_from.txtfile_dsc",
                     icon="STICKY_UVS_DISABLE", text='import')
        #row.operator("export.coordshift_dsc",
        #             icon="STICKY_UVS_DISABLE", text='export')
        row = layout.row()
        row.prop(context.scene, 'BL_x_shift', toggle=True)
        row = layout.row()
        row.prop(context.scene, 'BL_y_shift', toggle=True)
        row = layout.row()
        row.prop(context.scene, 'BL_z_shift', toggle=True)
        row = layout.row()
        row.prop(context.scene, 'BL_epsg', toggle=True)
        row = layout.row()

        #addon_updater_ops.update_notice_box_ui(self, context)


class VIEW3D_PT_dsc_Shift_ToolBar(Panel, ToolsPanel_dsc_SHIFT):
    bl_category = "3DSC"
    bl_idname = "VIEW3D_PT_dsc_Shift_ToolBar"
    bl_context = "objectmode"


classes = [
    OBJECT_OT_IMPORT_SHIFT,
    OBJECT_OT_IMPORT_BG,
    ImportCoordinateShift_dsc,
    VIEW3D_PT_dsc_Shift_ToolBar
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

    bpy.types.Scene.BL_epsg = StringProperty(
        name="EPSG",
        default="Not set",
        description="Epsg code"
    )
    bpy.types.Scene.BL_x_shift = FloatProperty(
        name="X shift",
        default=0.0,
        description="Define the shift on the x axis",
    )

    bpy.types.Scene.BL_y_shift = FloatProperty(
        name="Y shift",
        default=0.0,
        description="Define the shift on the y axis",
    )

    bpy.types.Scene.BL_z_shift = FloatProperty(
        name="Z shift",
        default=0.0,
        description="Define the shift on the z axis",
    )


def unregister():
    for cls in classes:
        bpy.utils.unregister_class(cls)
    del bpy.types.Scene.BL_epsg
    del bpy.types.Scene.BL_x_shift
    del bpy.types.Scene.BL_y_shift
    del bpy.types.Scene.BL_z_shift
