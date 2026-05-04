import bpy


def register():
    S = bpy.types.Scene

    # Source
    S.cesium_source_mode = bpy.props.EnumProperty(
        name="Source mode",
        items=[
            ('ACTIVE_MESH', 'Export active mesh', 'Export active mesh first, then convert'),
            ('EXISTING_OBJ', 'Use existing OBJ file', 'Convert an OBJ already present on disk'),
            ('MULTI_LOD_SET', 'Multi-LOD set (LODgenerator output)',
             'Use a pre-baked LOD set (objects named *_LOD0, *_LOD1, ...). '
             'Skips the per-tile rebake entirely — each LOD level is clipped '
             'into octree cells preserving its existing material/atlas. '
             'Recommended workflow when LODgenerator was already used.'),
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
    S.cesium_tile_refine_mode = bpy.props.EnumProperty(
        name="Refine mode",
        items=[
            ('REPLACE', 'Replace (default)',
             "Children replace the parent when refined. Network-efficient but "
             "produces visible gaps along tile boundaries during LOD transitions"),
            ('ADD', 'Add (parent stays under children)',
             "Parent tile remains rendered while children load on top. Eliminates "
             "inter-tile gaps and 'flying triangles' but costs ~30% more bandwidth "
             "and increases GPU overdraw"),
        ],
        default='REPLACE',
        description=(
            "How the loader transitions between LOD levels. Switch to ADD if "
            "you see floating triangles or seams between tiles in ATON."
        ),
    )
    S.cesium_lod_strategy = bpy.props.EnumProperty(
        name="LOD Strategy",
        items=[
            ('REBAKE', 'Re-bake per level',
             'Decimate + re-UV + re-bake texture from source mesh (correct, recommended)'),
            ('LEAF_ONLY', 'Leaf-only tiles',
             'Only leaf nodes get content; faster but no progressive LOD geometry'),
        ],
        default='REBAKE',
        description="How internal (non-leaf) LOD nodes handle texture mapping",
    )
    S.cesium_per_tile_bake_enabled = bpy.props.BoolProperty(
        name="Per-tile bake (auto-sized atlas)",
        default=True,
        description=(
            "Each tile gets its own focused atlas baked from the source mesh "
            "(instead of all tiles embedding the same global atlas). Atlas size "
            "is auto-computed from the tile's face count (~16 px/face). "
            "This is the architecturally correct way to use 3D Tiles: small, "
            "high-resolution per-tile textures rather than a single huge global one. "
            "Disable for legacy global-atlas behavior."
        ),
    )
    S.cesium_uv_algorithm = bpy.props.EnumProperty(
        name="UV algorithm",
        items=[
            ('SMART',     'Smart UV Project',
             'smart_project — fast but tends to create many small UV islands'),
            ('ANGLE',     'Angle-Based unwrap',
             'unwrap(ANGLE_BASED) — best general-purpose, fewer islands'),
            ('CONFORMAL', 'Conformal unwrap',
             'unwrap(CONFORMAL) — preserves angles, minimal stretch'),
            ('MINIMUM',   'Minimum Stretch',
             'minimize_stretch on conformal seed — best quality, slowest'),
        ],
        default='SMART',
        description=(
            "Algorithm used to lay out UV islands on the target tile mesh "
            "before bake. Mirrors LODgenerator's choice. SMART is the safest "
            "headless default; ANGLE_BASED often produces fewer/better islands "
            "but can fail bpy.ops.uv.unwrap.poll() in headless contexts."
        ),
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
    # Per-section collapse toggles (numbered settings sub-panels)
    S.cesium_show_section_source = bpy.props.BoolProperty(default=True)
    S.cesium_show_section_output = bpy.props.BoolProperty(default=True)
    S.cesium_show_section_quicksetup = bpy.props.BoolProperty(default=True)
    S.cesium_show_section_tiling = bpy.props.BoolProperty(default=False)
    S.cesium_show_section_texture = bpy.props.BoolProperty(default=False)
    S.cesium_show_section_hierarchy = bpy.props.BoolProperty(default=False)
    S.cesium_show_section_coordinates = bpy.props.BoolProperty(default=False)

    S.cesium_keep_temp_objects = bpy.props.BoolProperty(
        name="Keep debug temporaries",
        default=False,
        description=(
            "After export, keep the per-tile copies and bake artifacts in "
            "the Blender scene (under the `_cesium_native_tmp` collection) "
            "for inspection. Default OFF — temporaries are cleaned up "
            "automatically once the export completes"
        ),
    )
    S.cesium_root_transform_yup_for_threejs = bpy.props.BoolProperty(
        name="Bake Y-up rotation into root.transform",
        default=False,
        description=(
            "Write a 180 deg X rotation into the produced tileset.json "
            "root.transform so Y-up viewers (Three.js, ATON) display the "
            "asset right-side-up out of the box. Default ON — the empirical "
            "value compensates the 'head-down' flip caused by the Blender "
            "Z-up + export_yup + 3d-tiles-renderer loader chain. Turn off "
            "if you prefer to leave the tileset frame-neutral and let the "
            "consuming scene apply its own orientation transform"
        ),
    )

    # ATON Integration (collapsible, closed by default)
    S.cesium_show_aton = bpy.props.BoolProperty(
        name="Show ATON integration",
        default=False,
    )
    S.cesium_aton_path = bpy.props.StringProperty(
        name="ATON folder",
        subtype='DIR_PATH',
        default="",
        description="Local install of ATON (the folder that contains package.json)",
    )
    S.cesium_aton_url = bpy.props.StringProperty(
        name="ATON URL",
        default="http://localhost:8080",
        description="Base URL where ATON is reachable (default: http://localhost:8080)",
    )
    S.cesium_aton_user = bpy.props.StringProperty(
        name="Scene user",
        default="cesium_dev",
        description="First path component of the ATON scene URL (e.g. 'cesium_dev' in /s/cesium_dev/<scene>)",
    )
    S.cesium_aton_scene_name = bpy.props.StringProperty(
        name="Scene name",
        default="",
        description="Second path component of the ATON scene URL. Empty = use the active mesh name (sanitised)",
    )
    S.cesium_aton_open_browser = bpy.props.BoolProperty(
        name="Open browser after publish",
        default=True,
        description="After copying the tileset to ATON's collections folder, open the scene URL in the system browser",
    )
    S.cesium_aton_overwrite = bpy.props.BoolProperty(
        name="Overwrite existing",
        default=True,
        description="If a tileset with the same name already exists in ATON's collections folder, replace it",
    )
    S.cesium_aton_error_target = bpy.props.FloatProperty(
        name="Error target (px)",
        default=5.0,
        min=0.5,
        max=50.0,
        description=(
            "Screen-space error target for the 3D Tiles loader (lower = more "
            "aggressive refine = more tiles fetched from network, sharper "
            "result; higher = fewer tiles, blurrier). ATON's default is 20. "
            "Written into scene.json so the page applies it automatically"
        ),
    )
    S.cesium_aton_yup_rotation = bpy.props.EnumProperty(
        name="Y-up rotation",
        items=[
            ('NONE',    "Identity",           "Do not add a rotation in scene.json (tileset is already viewer-ready)"),
            ('XNEG90',  "-90° X (Z-up→Y-up)", "Rotate -π/2 around X. Standard for Blender Z-up content rendered in a Y-up scene"),
            ('XPOS90',  "+90° X",             "Rotate +π/2 around X. Mirror of -90° X"),
            ('X180',    "180° X (flip Y+Z)",  "Rotate π around X. Use when the model appears head-down with identity"),
            ('Y180',    "180° Y (yaw 180°)",  "Rotate π around Y. Pure yaw flip; use after another rotation if cardinal direction is wrong"),
        ],
        default='XNEG90',
        description=(
            "Rotation written into the ATON scene.json `transform.rotation` "
            "field for the published node. The value depends on the source "
            "mesh convention. Most Blender Z-up workflows want -90° X"
        ),
    )
    S.cesium_zip_output = bpy.props.BoolProperty(
        name="Also save zip",
        default=False,
        description="After export, write a zipped copy of the output folder next to it (.zip)",
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
        "cesium_tile_refine_mode",
        "cesium_lod_strategy",
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
        "cesium_root_transform_yup_for_threejs",
        "cesium_keep_temp_objects",
        "cesium_show_section_source",
        "cesium_show_section_output",
        "cesium_show_section_quicksetup",
        "cesium_show_section_tiling",
        "cesium_show_section_texture",
        "cesium_show_section_hierarchy",
        "cesium_show_section_coordinates",
        "cesium_show_aton",
        "cesium_aton_path",
        "cesium_aton_url",
        "cesium_aton_user",
        "cesium_aton_scene_name",
        "cesium_aton_open_browser",
        "cesium_aton_overwrite",
        "cesium_aton_yup_rotation",
        "cesium_aton_error_target",
        "cesium_zip_output",
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
