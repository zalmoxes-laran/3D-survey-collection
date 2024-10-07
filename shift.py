# -*- coding:utf-8 -*-

import bpy
from .functions import *
from bpy.types import Operator
from bpy_extras.io_utils import ImportHelper
from bpy_extras.io_utils import ExportHelper

from bpy.props import (StringProperty,
                       )

from bpy.types import Panel
from bpy.types import PropertyGroup
from bpy.types import Menu, UIList

import logging
log = logging.getLogger(__name__)

################## Import shift coordinates ####################

class OBJECT_OT_IMPORT_SHIFT(bpy.types.Operator):
    """Import shift coordinates from a SHIFT txt file"""
    bl_idname = "shiftval_from.txtfile_dsc"
    bl_label = "Import shift coordinates from file"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        bpy.ops.import_fromfile.shift_valcoor_dsc('INVOKE_DEFAULT')
        return {'FINISHED'}

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
    ) # type: ignore

    def execute(self, context):
        return self.read_shift_data(context, self.filepath)

    def read_shift_data(self, context, filepath):
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

########### 3DSC and Blender GIS interoperability ##############

# This operator is made up of three parts in order to handle the user's choice of whether or not to go ahead when explaining that this setup must be done at the beginning and with the scene empty because it may affect the objects in the scene

# 1
class OBJECT_OT_IMPORT_DSC(bpy.types.Operator):
    """Install and/or enable Blender GIS to activate this button"""
    bl_idname = "shift_from.dsc"
    bl_label = "Copy shift values to BlenderGis"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return is_addon_starting_with("BlenderGIS")[0] and context.scene.BL_epsg != "Not set"    

    def execute(self, context):
        # Chiamata all'operatore di conferma
        message_for_user = "Scene should be empty: do I proceed?"
        bpy.ops.wm.confirm_window_3dsc_bgis('INVOKE_DEFAULT', message=message_for_user)
        return {'FINISHED'}

# 2
class ConfirmWindow3DScToBGIS(bpy.types.Operator):
    """Show a confirmation window before performing the operation"""
    bl_idname = "wm.confirm_window_3dsc_bgis"
    bl_label = "Transaction Confirmation"

    # Proprietà per il messaggio personalizzato
    message: bpy.props.StringProperty() # type: ignore

    def execute(self, context):
        # Chiamata all'operatore di esecuzione
        bpy.ops.object.execute_after_confirmation_3dsc_bgis()
        return {'FINISHED'}

    def invoke(self, context, event):
        wm = context.window_manager
        # Mostra il dialogo personalizzato con il messaggio
        return wm.invoke_props_dialog(self)

    def draw(self, context):
        self.layout.label(text=self.message)

# 3
class OBJECT_OT_ExecuteAfterConfirmation_3dsc_BGIS(bpy.types.Operator):
    """Executes after user confirmation"""
    bl_idname = "object.execute_after_confirmation_3dsc_bgis"
    bl_label = "Execute After User Confirmation"

    def execute(self, context):
        scene = context.scene
        context.window_manager.confirm_window_result_3dsc = True

        if context.window_manager.confirm_window_result_3dsc:
        # conditional to be used in conjunction with the dialogue box
            
            # retrieve the path to Blender GIS variables
            addon_name = is_addon_starting_with("BlenderGIS")[1]
            prefs = bpy.context.preferences.addons[addon_name].preferences

            # Set the new value of predefCrs
            new_crs = 'EPSG:'+scene['BL_epsg']
            prefs.predefCrs = new_crs
            #bpy.ops.geoscene.set_crs('INVOKE_DEFAULT', new_crs=new_crs)

            bpy.data.window_managers['WinMan'].geoscnProps.displayOriginPrj = True
            bpy.data.window_managers["WinMan"].geoscnProps.crsx = scene['BL_x_shift']
            bpy.data.window_managers["WinMan"].geoscnProps.crsy = scene['BL_y_shift']

            print("Executing action after user confirmation")
            # Make sure to reset the flag for future verification
            context.window_manager.confirm_window_result_3dsc = False
        else:
            self.report({'INFO'}, "Operation not confirmed by the user")
        return {'FINISHED'}

class OBJECT_OT_IMPORT_BG(bpy.types.Operator):
    """Install and/or enable Blender GIS to activate this button"""
    bl_idname = "shift_from.blendergis"
    bl_label = "Copy shift values from BlenderGis"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return is_addon_starting_with("BlenderGIS")[0]    

    def execute(self, context):
        scene = context.scene
        scene['BL_x_shift'] = bpy.data.window_managers["WinMan"].geoscnProps.crsx
        scene['BL_y_shift'] = bpy.data.window_managers["WinMan"].geoscnProps.crsy
        return {'FINISHED'}

############## SHIFT Panel ###############
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
                     icon="IMPORT", text='')
        row.operator("export_tofile.shift_valcoor_dsc",
                     icon="EXPORT", text='')

        row = layout.row()
        row.prop(context.scene, 'BL_x_shift', toggle=True)
        row = layout.row()
        row.prop(context.scene, 'BL_y_shift', toggle=True)
        row = layout.row()
        row.prop(context.scene, 'BL_z_shift', toggle=True)
        row = layout.row()
        row.prop(context.scene, 'BL_epsg', toggle=True)
        row = layout.row()

        row.label(text="Blender GIS connection:")
        row = layout.row()

        row.operator("shift_from.blendergis",
                     icon="URL", text='GIS->3DSC')
        
        row.operator("shift_from.dsc",
                     icon="URL", text='3DSC->GIS')

        #addon_updater_ops.update_notice_box_ui(self, context)


class VIEW3D_PT_dsc_Shift_ToolBar(Panel, ToolsPanel_dsc_SHIFT):
    bl_category = "3DSC"
    bl_idname = "VIEW3D_PT_dsc_Shift_ToolBar"
    bl_context = "objectmode"


class ExportCoordinateShift_dsc(Operator, ExportHelper):
    """Tool to export shift coordinates to a txt file"""
    bl_idname = "export_tofile.shift_valcoor_dsc"
    bl_label = "Export shift values"

    # ExportHelper mixin class uses this
    filename_ext = ".txt"

    filter_glob: StringProperty(
        default="*.txt",
        options={'HIDDEN'},
        maxlen=255,
    ) # type: ignore

    def execute(self, context):
        return self.write_shift_data(context, self.filepath)

    def write_shift_data(self, context, filepath):
        scene = context.scene
        epsg = scene.get('BL_epsg', 'Not set')
        x_shift = scene.get('BL_x_shift', 0.0)
        y_shift = scene.get('BL_y_shift', 0.0)
        z_shift = scene.get('BL_z_shift', 0.0)
        
        with open(filepath, 'w') as f:
            f.write(f"EPSG::{epsg} {x_shift} {y_shift} {z_shift}\n")
        
        return {'FINISHED'}


classes = [
    OBJECT_OT_IMPORT_SHIFT,
    OBJECT_OT_IMPORT_BG,
    OBJECT_OT_IMPORT_DSC,
    ImportCoordinateShift_dsc,
    VIEW3D_PT_dsc_Shift_ToolBar,
    ExportCoordinateShift_dsc,
    OBJECT_OT_ExecuteAfterConfirmation_3dsc_BGIS,
    ConfirmWindow3DScToBGIS
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
