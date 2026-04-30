import bpy

from . import data
from .operators import (
    OBJECT_OT_apply_cesium_preset,
    OBJECT_OT_auto_compute_cesium_settings,
    OBJECT_OT_cesium_zip_output,
    OBJECT_OT_clear_cesium_folder,
    OBJECT_OT_export_cesium_tiles,
    OBJECT_OT_generate_aton_scene_name,
    OBJECT_OT_launch_aton,
    OBJECT_OT_open_aton_browser,
    OBJECT_OT_patch_cesium_output_unlit,
    OBJECT_OT_publish_to_aton,
    OBJECT_OT_rebuild_cesium_parent_tileset,
    OBJECT_OT_strip_cesium_output_unlit,
)
from .ui import VIEW3D_PT_cesium_export


classes = (
    OBJECT_OT_clear_cesium_folder,
    OBJECT_OT_patch_cesium_output_unlit,
    OBJECT_OT_strip_cesium_output_unlit,
    OBJECT_OT_apply_cesium_preset,
    OBJECT_OT_auto_compute_cesium_settings,
    OBJECT_OT_rebuild_cesium_parent_tileset,
    OBJECT_OT_export_cesium_tiles,
    OBJECT_OT_launch_aton,
    OBJECT_OT_open_aton_browser,
    OBJECT_OT_publish_to_aton,
    OBJECT_OT_generate_aton_scene_name,
    OBJECT_OT_cesium_zip_output,
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
