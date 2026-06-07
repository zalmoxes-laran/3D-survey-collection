# -*- coding:utf-8 -*-

import bpy
from .functions import *
from bpy.types import Operator
from bpy_extras.io_utils import ImportHelper
from bpy_extras.io_utils import ExportHelper

from bpy.props import (StringProperty,
                       )

from bpy.types import Panel

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
        scene.BL_x_shift = float(data_coordinates[1])
        scene.BL_y_shift = float(data_coordinates[2])
        scene.BL_z_shift = float(data_coordinates[3])
        scene.BL_epsg = data_coordinates[0].replace('EPSG::', '')
        return {'FINISHED'}

########### 3DSC and Blender GIS interoperability ##############

# Uses BlenderGIS.geoscene.GeoScene API directly (no wm.geoscnProps).
# With setOriginPrj(synch=False) + no updOriginPrj call, origin changes
# never translate existing scene objects — safe on populated scenes.
# The former "scene must be empty" confirmation dialog is no longer needed.

def _set_bgis_origin(scene, epsg, shift_x, shift_y, move_objects=False):
    """Write CRS + projected origin into BlenderGIS via the GeoScene API.

    Parameters
    ----------
    move_objects : bool
        If True, translate top-level objects to follow the new origin
        (BGIS default behaviour). Default False: origin changes without
        touching existing geometry — the typical 3DSC workflow where
        meshes are already imported in local (shifted) coordinates.
    """
    from BlenderGIS.geoscene import GeoScene
    gs = GeoScene(scene)

    # Reset to avoid the crs setter reprojecting an existing origin.
    if gs.hasOriginGeo:
        gs.delOriginGeo()
    if gs.hasOriginPrj and not move_objects:
        gs.delOriginPrj()

    gs.crs = f'EPSG:{epsg}'

    if move_objects and gs.hasOriginPrj:
        gs.updOriginPrj(shift_x, shift_y, updObjLoc=True, synch=False)
    else:
        gs.setOriginPrj(shift_x, shift_y, synch=False)


class OBJECT_OT_IMPORT_DSC(bpy.types.Operator):
    """Copy 3DSC shift values to BlenderGIS (scene objects are NOT moved by default)"""
    bl_idname = "shift_from.dsc"
    bl_label = "Copy shift values to BlenderGis"
    bl_options = {"REGISTER", "UNDO"}

    move_objects: bpy.props.BoolProperty(
        name="Move objects on origin change",
        description=(
            "Translate existing top-level objects to follow the new "
            "origin. OFF by default: safe on populated scenes with "
            "already-imported shifted geometry."
        ),
        default=False,
    )  # type: ignore

    @classmethod
    def poll(cls, context):
        return is_addon_starting_with("BlenderGIS")[0] and context.scene.BL_epsg != "NotSet"

    def execute(self, context):
        scene = context.scene
        try:
            _set_bgis_origin(
                scene,
                scene.BL_epsg,
                scene.BL_x_shift,
                scene.BL_y_shift,
                move_objects=self.move_objects,
            )
        except Exception as e:
            self.report({'ERROR'}, f"Could not write BlenderGIS origin: {e}")
            return {'CANCELLED'}
        self.report({'INFO'}, "BlenderGIS origin updated from 3DSC")
        return {'FINISHED'}


class OBJECT_OT_IMPORT_BG(bpy.types.Operator):
    """Copy BlenderGIS origin + CRS into 3DSC shift values"""
    bl_idname = "shift_from.blendergis"
    bl_label = "Copy shift values from BlenderGis"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return is_addon_starting_with("BlenderGIS")[0]

    def execute(self, context):
        scene = context.scene
        try:
            from BlenderGIS.geoscene import GeoScene
            gs = GeoScene(scene)
            if gs.hasOriginPrj:
                x, y = gs.getOriginPrj()
                scene.BL_x_shift = float(x)
                scene.BL_y_shift = float(y)
            if gs.hasValidCRS:
                crs = gs.crs or ''
                epsg = crs.replace('EPSG:', '').strip()
                if epsg:
                    scene.BL_epsg = epsg
        except Exception as e:
            self.report({'ERROR'}, f"Could not read BlenderGIS origin: {e}")
            return {'CANCELLED'}
        self.report({'INFO'}, "3DSC shift values updated from BlenderGIS")
        return {'FINISHED'}

############## SHIFT Panel ###############
class ToolsPanel_dsc_SHIFT:
    bl_label = "Shifting"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    #bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
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



class VIEW3D_PT_dsc_Shift_ToolBar(Panel, ToolsPanel_dsc_SHIFT):
    bl_category = "3DSC"
    bl_idname = "VIEW3D_PT_dsc_Shift_ToolBar"
    bl_context = "objectmode"
    bl_options = {'DEFAULT_CLOSED'}

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
        epsg = scene.BL_epsg
        x_shift = scene.BL_x_shift
        y_shift = scene.BL_y_shift
        z_shift = scene.BL_z_shift

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

    bpy.types.Scene.BL_epsg = StringProperty(
        name="EPSG",
        default="NotSet",
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
