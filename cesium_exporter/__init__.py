import bpy

from . import data
from .operators import (
    OBJECT_OT_apply_cesium_preset,
    OBJECT_OT_clear_cesium_folder,
    OBJECT_OT_export_cesium_tiles,
    OBJECT_OT_patch_cesium_output_unlit,
    OBJECT_OT_rebuild_cesium_parent_tileset,
    OBJECT_OT_strip_cesium_output_unlit,
)
from .ui import VIEW3D_PT_cesium_export


classes = (
    OBJECT_OT_clear_cesium_folder,
    OBJECT_OT_patch_cesium_output_unlit,
    OBJECT_OT_strip_cesium_output_unlit,
    OBJECT_OT_apply_cesium_preset,
    OBJECT_OT_rebuild_cesium_parent_tileset,
    OBJECT_OT_export_cesium_tiles,
    VIEW3D_PT_cesium_export,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    data.register()


def unregister():
    data.unregister()
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
