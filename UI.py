import bpy

from bpy.types import Panel
from bpy.types import Operator
from bpy.types import PropertyGroup


import os
from bpy_extras.io_utils import ImportHelper

from bpy.props import (BoolProperty,
                       FloatProperty,
                       StringProperty,
                       EnumProperty,
                       CollectionProperty
                       )

class ToolsPanelImport:
    bl_label = "Importers"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'

    def draw(self, context):
        layout = self.layout
        obj = context.object

        row = layout.row()
        self.layout.operator("import_scene.multiple_objs", icon="WORLD_DATA", text='Import multiple objs')
        row = layout.row()
        self.layout.operator("import_points.txt", icon="WORLD_DATA", text='Import txt points')

class ToolsPanelExport:
    bl_label = "Exporters"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'

    def draw(self, context):
        layout = self.layout
        obj = context.object
        row = layout.row()
        if obj is not None:
            self.layout.operator("export.coordname", icon="WORLD_DATA", text='Coordinates')
            row = layout.row()
            row.label(text="Active object is: " + obj.name)
            row = layout.row()
            row.label(text="Override")
            row = layout.row()
            row.prop(obj, "name")
            row = layout.row()
            self.layout.operator("export.object", icon="OBJECT_DATA", text='Exp. one obj')
            row = layout.row()
            row.label(text="Resulting file: " + obj.name + ".obj")
            row = layout.row()
            self.layout.operator("obj.exportbatch", icon="OBJECT_DATA", text='Exp. several obj')
            row = layout.row()
            self.layout.operator("fbx.exportbatch", icon="OBJECT_DATA", text='Exp. several fbx UE4')
            row = layout.row()
            self.layout.operator("fbx.exp", icon="OBJECT_DATA", text='Exp. fbx UE4')
            row = layout.row()
            self.layout.operator("osgt.exportbatch", icon="OBJECT_DATA", text='Exp. several osgt files')
            row = layout.row()
#            if is_windows():
#                row = layout.row()
#                row.label(text="We are under Windows..")
        else:
            row.label(text="Select object(s) to see tools here.")
            row = layout.row()


class VIEW3D_PT_Import_ToolBar(Panel, ToolsPanelImport):
    bl_category = "3DSC"
    bl_idname = "VIEW3D_PT_Import_ToolBar"
    bl_context = "objectmode"

class VIEW3D_PT_Export_ToolBar(Panel, ToolsPanelExport):
    bl_category = "3DSC"
    bl_idname = "VIEW3D_PT_Export_ToolBar"
    bl_context = "objectmode"
