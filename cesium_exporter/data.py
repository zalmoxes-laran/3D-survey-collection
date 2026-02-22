import bpy


def register():
    S = bpy.types.Scene

    # Source
    S.cesium_source_mode = bpy.props.EnumProperty(
        name="Source mode",
        items=[
            ('ACTIVE_MESH', 'Export active mesh', 'Export active mesh first, then convert'),
            ('EXISTING_OBJ', 'Use existing OBJ file', 'Convert an OBJ already present on disk'),
        ],
        default='ACTIVE_MESH',
    )
    S.cesium_export_selected_meshes = bpy.props.BoolProperty(
        name="Export selected meshes",
        default=False,
        description="Export all selected mesh objects (each in its own output subfolder)",
    )
    S.cesium_existing_obj_file = bpy.props.StringProperty(
        name="Existing OBJ file",
        subtype='FILE_PATH',
        default="",
        description="Path to an existing .obj file to convert directly",
    )

    # Output
    S.cesium_output_dir = bpy.props.StringProperty(
        name="Tiles output folder",
        subtype='DIR_PATH',
        default="",
        description="Destination folder for Cesium 3D Tiles output",
    )
    S.cesium_create_object_subdir = bpy.props.BoolProperty(
        name="Create object subfolder",
        default=True,
        description="Write tiles into an object-name subfolder under output path",
    )

    # Quick Setup
    S.cesium_quick_preset = bpy.props.EnumProperty(
        name="Quick preset",
        items=[
            ('LOD_HIERARCHY', 'LOD Hierarchy', 'Octree with hierarchical LOD decimation (recommended)'),
            ('BALANCED', 'Balanced', 'Quadtree, no LOD, external sub-tilesets'),
            ('LOW_DETAIL', 'Low Detail', 'Fewer tiles, larger features per tile'),
        ],
        default='LOD_HIERARCHY',
    )

    # Tiling
    S.cesium_tree_type = bpy.props.EnumProperty(
        name="Tree type",
        items=[
            ('QUADTREE', 'Quadtree', 'Best for wide horizontal scenes'),
            ('OCTREE', 'Octree', 'Best for volumetric scenes'),
        ],
        default='QUADTREE',
    )
    S.cesium_features_per_tile = bpy.props.IntProperty(
        name="Features per tile",
        default=8000,
        min=100,
        description="Approximate face budget per leaf tile",
    )
    S.cesium_native_min_depth = bpy.props.IntProperty(
        name="Min tree depth",
        default=2,
        min=0,
        max=20,
        description="Force at least this depth before stopping",
    )
    S.cesium_native_max_depth = bpy.props.IntProperty(
        name="Max tree depth",
        default=8,
        min=1,
        max=20,
        description="Maximum recursion depth for quadtree/octree",
    )

    # LOD
    S.cesium_lod_mode = bpy.props.BoolProperty(
        name="Hierarchical LOD",
        default=False,
        description="Generate LOD content at every tree level with decimation + scaled textures",
    )
    S.cesium_lod_auto_params = bpy.props.BoolProperty(
        name="Auto-parametrize",
        default=True,
        description="Automatically compute depth, features/tile, and atlas sizes from mesh stats",
    )
    S.cesium_lod_leaf_atlas_size = bpy.props.IntProperty(
        name="Leaf atlas size",
        default=1024,
        min=256,
        max=4096,
        description="Texture atlas size for leaf (highest detail) tiles",
    )
    S.cesium_lod_root_atlas_size = bpy.props.IntProperty(
        name="Root atlas size",
        default=256,
        min=64,
        max=2048,
        description="Texture atlas size for root (lowest detail) tile",
    )
    S.cesium_lod_preserve_borders = bpy.props.BoolProperty(
        name="Preserve mesh borders",
        default=True,
        description="Protect non-manifold edges from decimation (prevents tile seams)",
    )

    # Texture
    S.cesium_native_bake_texture_atlas = bpy.props.BoolProperty(
        name="Bake textures to atlas",
        default=True,
        description="Bake source materials into a single atlas before split export",
    )
    S.cesium_native_bake_texture_size = bpy.props.IntProperty(
        name="Bake atlas size",
        default=2048,
        min=512,
        max=16384,
        description="Texture atlas size for bake step (used as leaf size when LOD is off)",
    )
    S.cesium_native_bake_margin = bpy.props.IntProperty(
        name="Bake margin px",
        default=8,
        min=0,
        max=64,
        description="Pixel margin between UV islands in baked atlas",
    )

    # Hierarchy Layout
    S.cesium_native_hierarchy_layout = bpy.props.EnumProperty(
        name="Hierarchy layout",
        items=[
            ('SINGLE_JSON', 'Single JSON', 'One root tileset.json containing full hierarchy'),
            ('EXTERNAL_SUBTILESETS', 'External sub-tilesets', 'Split hierarchy into referenced sub-tileset files'),
            ('IMPLICIT_TILING', 'Implicit tiling', 'Massenzio-style implicit tiling: tiles/ + subtrees/'),
        ],
        default='SINGLE_JSON',
    )
    S.cesium_singlejson_add_root_content = bpy.props.BoolProperty(
        name="Add root content tile",
        default=True,
        description="Write a root GLB tile for viewers that require root content",
    )
    S.cesium_native_subtileset_split_depth = bpy.props.IntProperty(
        name="Subtileset split depth",
        default=2,
        min=1,
        max=20,
        description="Depth at which subtrees are emitted as external tileset files",
    )

    # Coordinates
    S.cesium_coordinates_mode = bpy.props.EnumProperty(
        name="Coordinates mode",
        items=[
            ('SHIFT_VALUES', 'Use SHIFT values', 'Use EPSG and XYZ from SHIFT panel'),
            ('LOCAL_COORDS', 'Use local coordinates', 'No CRS/offset transform'),
            ('CUSTOM_COORDS', 'Use custom coordinates', 'Custom XYZ and optional CRS override'),
        ],
        default='SHIFT_VALUES',
    )
    S.cesium_crs = bpy.props.StringProperty(
        name="CRS",
        default="",
        description="Input CRS (e.g. EPSG:32632). If empty, SHIFT panel EPSG is used.",
    )
    S.cesium_offset_x = bpy.props.FloatProperty(name="Offset X", default=0.0)
    S.cesium_offset_y = bpy.props.FloatProperty(name="Offset Y", default=0.0)
    S.cesium_offset_z = bpy.props.FloatProperty(name="Offset Z", default=0.0)

    # Stitcher
    S.cesium_show_stitcher = bpy.props.BoolProperty(name="Show stitcher", default=False)
    S.cesium_auto_stitch_parent = bpy.props.BoolProperty(
        name="Auto-update parent tileset",
        default=True,
        description="Rebuild parent tileset JSON after each export",
    )
    S.cesium_parent_tileset_name = bpy.props.StringProperty(
        name="Parent tileset filename",
        default="tileset.json",
        description="Filename for the parent tileset in the output folder",
    )

    # Advanced
    S.cesium_show_advanced = bpy.props.BoolProperty(name="Show advanced", default=False)
    S.cesium_force_unlit_materials = bpy.props.BoolProperty(
        name="Force unlit materials",
        default=False,
        description="Post-process GLB tiles to add KHR_materials_unlit",
    )
    S.cesium_texture_base_dir = bpy.props.StringProperty(
        name="Texture base dir (optional)",
        subtype='DIR_PATH',
        default="",
        description="Optional texture base directory for OBJ-based workflows",
    )

    # Progress
    S.cesium_progress_active = bpy.props.BoolProperty(default=False)
    S.cesium_progress_task = bpy.props.StringProperty(default="")
    S.cesium_progress_current_mesh = bpy.props.IntProperty(default=0)
    S.cesium_progress_total_meshes = bpy.props.IntProperty(default=0)
    S.cesium_progress_elapsed = bpy.props.FloatProperty(default=0.0)
    S.cesium_progress_log = bpy.props.StringProperty(default="")
    S.cesium_progress_last_stats = bpy.props.StringProperty(default="")


def unregister():
    S = bpy.types.Scene

    props_to_delete = [
        "cesium_source_mode",
        "cesium_export_selected_meshes",
        "cesium_existing_obj_file",
        "cesium_output_dir",
        "cesium_create_object_subdir",
        "cesium_quick_preset",
        "cesium_tree_type",
        "cesium_features_per_tile",
        "cesium_native_min_depth",
        "cesium_native_max_depth",
        "cesium_lod_mode",
        "cesium_lod_auto_params",
        "cesium_lod_leaf_atlas_size",
        "cesium_lod_root_atlas_size",
        "cesium_lod_preserve_borders",
        "cesium_native_bake_texture_atlas",
        "cesium_native_bake_texture_size",
        "cesium_native_bake_margin",
        "cesium_native_hierarchy_layout",
        "cesium_singlejson_add_root_content",
        "cesium_native_subtileset_split_depth",
        "cesium_coordinates_mode",
        "cesium_crs",
        "cesium_offset_x",
        "cesium_offset_y",
        "cesium_offset_z",
        "cesium_show_stitcher",
        "cesium_auto_stitch_parent",
        "cesium_parent_tileset_name",
        "cesium_show_advanced",
        "cesium_force_unlit_materials",
        "cesium_texture_base_dir",
        "cesium_progress_active",
        "cesium_progress_task",
        "cesium_progress_current_mesh",
        "cesium_progress_total_meshes",
        "cesium_progress_elapsed",
        "cesium_progress_log",
        "cesium_progress_last_stats",
    ]

    for prop in props_to_delete:
        try:
            delattr(S, prop)
        except Exception:
            pass
