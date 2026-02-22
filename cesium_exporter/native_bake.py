import math

import bpy
from mathutils import Matrix, Vector

from .shared import _preserve_selection, _sanitize_name
from .stats import _collect_object_texture_diagnostics


def _prepare_base_mesh_object(context, active_obj, offset):
    temp_collection = bpy.data.collections.get("_cesium_native_tmp")
    if temp_collection is None:
        temp_collection = bpy.data.collections.new("_cesium_native_tmp")
        context.scene.collection.children.link(temp_collection)

    base_obj = active_obj.copy()
    base_obj.data = active_obj.data.copy()
    temp_collection.objects.link(base_obj)

    base_obj.data.transform(active_obj.matrix_world)
    if offset is not None:
        base_obj.data.transform(Matrix.Translation(Vector(offset)))
    base_obj.matrix_world = Matrix.Identity(4)

    return base_obj, temp_collection

def _cleanup_native_bake_assets(bake_info):
    if not isinstance(bake_info, dict):
        return

    for mat_name in bake_info.get("temp_materials", []) or []:
        mat = bpy.data.materials.get(mat_name)
        if mat is not None and mat.users == 0:
            try:
                bpy.data.materials.remove(mat, do_unlink=True)
            except Exception:
                pass

    baked_mat_name = bake_info.get("baked_material", "")
    if baked_mat_name:
        mat = bpy.data.materials.get(baked_mat_name)
        if mat is not None and mat.users == 0:
            try:
                bpy.data.materials.remove(mat, do_unlink=True)
            except Exception:
                pass

    baked_img_name = bake_info.get("baked_image", "")
    if baked_img_name:
        img = bpy.data.images.get(baked_img_name)
        if img is not None and img.users == 0:
            try:
                bpy.data.images.remove(img, do_unlink=True)
            except Exception:
                pass


# ===========================================================================
#  BLOCK B: Bake + Spatial + Tree Building + LOD
# ===========================================================================

# ---------------------------------------------------------------------------
#  Texture atlas baking (Cycles)
# ---------------------------------------------------------------------------

def _native_bake_basecolor_texture(context, scene, base_obj, atlas_size, margin_px):
    bake_info = {
        "enabled": True,
        "applied": False,
        "atlas_size": int(atlas_size),
        "margin_px": int(margin_px),
        "source_texture_images": 0,
        "source_image_nodes": 0,
        "temp_materials": [],
        "baked_material": "",
        "baked_image": "",
    }

    mesh = getattr(base_obj, "data", None)
    if mesh is None or len(mesh.polygons) == 0:
        return False, "Mesh is empty, cannot bake textures.", bake_info

    diag = _collect_object_texture_diagnostics(base_obj)
    bake_info["source_texture_images"] = int(diag.get("texture_images", 0))
    bake_info["source_image_nodes"] = int(diag.get("image_nodes", 0))
    if bake_info["source_texture_images"] <= 0:
        return True, "No source texture images found: bake skipped.", bake_info

    local_materials = []
    for idx, slot in enumerate(base_obj.material_slots):
        mat = slot.material
        if mat is None:
            continue
        mat_copy = mat.copy()
        mat_copy.name = f"__CesiumBakeSrc_{_sanitize_name(base_obj.name)}_{idx:03d}"
        slot.material = mat_copy
        local_materials.append(mat_copy)
        bake_info["temp_materials"].append(mat_copy.name)

    if not local_materials:
        return True, "No materials on source mesh: bake skipped.", bake_info

    uv_layer = mesh.uv_layers.get("__CesiumBakeUV")
    if uv_layer is None:
        uv_layer = mesh.uv_layers.new(name="__CesiumBakeUV")
    mesh.uv_layers.active = uv_layer
    if hasattr(uv_layer, "active_render"):
        uv_layer.active_render = True

    image_name = f"__CesiumBakeAtlas_{_sanitize_name(base_obj.name)}"
    bake_image = bpy.data.images.new(
        name=image_name,
        width=int(atlas_size),
        height=int(atlas_size),
        alpha=True,
        float_buffer=False,
    )
    bake_image.generated_color = (1.0, 1.0, 1.0, 1.0)
    bake_info["baked_image"] = bake_image.name

    target_nodes = []
    for mat in local_materials:
        if not mat.use_nodes:
            mat.use_nodes = True
        nt = mat.node_tree
        if nt is None:
            continue
        for node in nt.nodes:
            node.select = False
        tex_node = nt.nodes.new("ShaderNodeTexImage")
        tex_node.name = "__CesiumBakeTarget"
        tex_node.label = "Cesium Bake Target"
        tex_node.image = bake_image
        tex_node.select = True
        nt.nodes.active = tex_node
        target_nodes.append(tex_node)

    if not target_nodes:
        return False, "No valid material node trees available for bake.", bake_info

    previous_engine = scene.render.engine
    previous_bake_margin = int(getattr(scene.render.bake, "margin", int(margin_px)))
    previous_bake_use_clear = bool(getattr(scene.render.bake, "use_clear", True))
    previous_bake_selected_to_active = bool(getattr(scene.render.bake, "use_selected_to_active", False))
    previous_cycles_samples = None
    previous_diffuse_bounces = None
    if hasattr(scene, "cycles"):
        previous_cycles_samples = int(getattr(scene.cycles, "samples", 1))
        previous_diffuse_bounces = int(getattr(scene.cycles, "diffuse_bounces", 4))

    try:
        with _preserve_selection(context):
            if getattr(context, "mode", "OBJECT") != 'OBJECT':
                bpy.ops.object.mode_set(mode='OBJECT')
            bpy.ops.object.select_all(action='DESELECT')
            base_obj.hide_set(False)
            base_obj.hide_viewport = False
            base_obj.hide_render = False
            base_obj.select_set(True)
            context.view_layer.objects.active = base_obj

            bpy.ops.object.mode_set(mode='EDIT')
            bpy.ops.mesh.select_all(action='SELECT')
            bpy.ops.uv.smart_project(
                angle_limit=math.radians(66),       # 66° in radianti
                margin_method='SCALED',
                rotate_method='AXIS_ALIGNED_Y',
                island_margin=0.0,
                area_weight=0.0,
                correct_aspect=True,
                scale_to_bounds=True,
            )
            bpy.ops.object.mode_set(mode='OBJECT')

            scene.render.engine = 'CYCLES'
            scene.render.bake.margin = int(margin_px)
            scene.render.bake.use_clear = True
            if hasattr(scene.render.bake, "margin_type"):
                scene.render.bake.margin_type = 'ADJACENT_FACES'
            if hasattr(scene.render.bake, "use_selected_to_active"):
                scene.render.bake.use_selected_to_active = False
            if previous_cycles_samples is not None:
                scene.cycles.samples = 1
            if previous_diffuse_bounces is not None:
                scene.cycles.diffuse_bounces = 1

            result = bpy.ops.object.bake(
                type='DIFFUSE',
                pass_filter={'COLOR'},
                use_clear=True,
                use_selected_to_active=False,
                margin_type='ADJACENT_FACES',
                margin=int(margin_px),
            )
            if 'FINISHED' not in result:
                return False, "Bake operator failed.", bake_info
    except Exception as exc:
        return False, f"Bake failed: {exc}", bake_info
    finally:
        try:
            if getattr(context, "mode", "OBJECT") != 'OBJECT':
                bpy.ops.object.mode_set(mode='OBJECT')
        except Exception:
            pass
        try:
            scene.render.engine = previous_engine
        except Exception:
            pass
        try:
            scene.render.bake.margin = previous_bake_margin
            scene.render.bake.use_clear = previous_bake_use_clear
            if hasattr(scene.render.bake, "use_selected_to_active"):
                scene.render.bake.use_selected_to_active = previous_bake_selected_to_active
        except Exception:
            pass
        if previous_cycles_samples is not None:
            try:
                scene.cycles.samples = previous_cycles_samples
            except Exception:
                pass
        if previous_diffuse_bounces is not None:
            try:
                scene.cycles.diffuse_bounces = previous_diffuse_bounces
            except Exception:
                pass

    try:
        bake_image.pack()
    except Exception:
        pass

    baked_mat = bpy.data.materials.new(name=f"CesiumBaked_{_sanitize_name(base_obj.name)}")
    baked_mat.use_nodes = True
    nt = baked_mat.node_tree
    nt.nodes.clear()
    out_node = nt.nodes.new("ShaderNodeOutputMaterial")
    bsdf_node = nt.nodes.new("ShaderNodeBsdfPrincipled")
    tex_node = nt.nodes.new("ShaderNodeTexImage")
    tex_node.image = bake_image
    tex_node.location = (-500, 0)
    bsdf_node.location = (-250, 0)
    out_node.location = (20, 0)
    if "Metallic" in bsdf_node.inputs:
        bsdf_node.inputs["Metallic"].default_value = 0.0
    if "Roughness" in bsdf_node.inputs:
        bsdf_node.inputs["Roughness"].default_value = 1.0
    if "Color" in tex_node.outputs and "Base Color" in bsdf_node.inputs:
        nt.links.new(tex_node.outputs["Color"], bsdf_node.inputs["Base Color"])
    # NOTE: Alpha NOT linked – bake is pure diffuse color, alpha would corrupt the output
    if "BSDF" in bsdf_node.outputs and "Surface" in out_node.inputs:
        nt.links.new(bsdf_node.outputs["BSDF"], out_node.inputs["Surface"])

    bake_info["baked_material"] = baked_mat.name
    mesh.materials.clear()
    mesh.materials.append(baked_mat)
    for poly in mesh.polygons:
        poly.material_index = 0
    mesh.update()

    for mat_name in list(bake_info.get("temp_materials", [])):
        mat = bpy.data.materials.get(mat_name)
        if mat is not None and mat.users == 0:
            try:
                bpy.data.materials.remove(mat, do_unlink=True)
            except Exception:
                pass

    bake_info["applied"] = True
    return True, f"Baked {bake_info['source_texture_images']} source texture(s) to {int(atlas_size)}px atlas.", bake_info


# ---------------------------------------------------------------------------
#  Per-node re-bake (LOD decimation UV fix)
# ---------------------------------------------------------------------------

_rebake_counter = 0


def _rebake_node_texture(context, scene, base_obj, tile_obj, atlas_size, margin_px=8):
    """Re-bake texture from base_obj onto tile_obj after decimation.

    Follows the LODgenerator.py pattern (decimate -> re-UV -> re-bake):
    1. UV-unwrap tile_obj with Smart UV Project (fresh UV layout)
    2. Create a new blank image at atlas_size
    3. Set up Cycles selected-to-active bake (base_obj -> tile_obj)
    4. Build material with the baked image

    Args:
        context: Blender context
        scene: Blender scene
        base_obj: Original high-res mesh (bake source, has baked atlas + correct UVs)
        tile_obj: Decimated tile mesh (bake target, UVs are broken from decimation)
        atlas_size: Target texture resolution (width=height, in pixels)
        margin_px: Bake margin in pixels

    Returns:
        (success: bool, image: bpy.types.Image | None, material: bpy.types.Material | None)
    """
    global _rebake_counter
    _rebake_counter += 1

    tile_mesh = tile_obj.data
    if tile_mesh is None or len(tile_mesh.polygons) == 0:
        return False, None, None

    # Unique names for this tile's rebake artifacts
    suffix = f"_rb{_rebake_counter}"
    uv_name = f"__CesiumRebakeUV{suffix}"
    img_name = f"__CesiumRebake{suffix}"
    mat_name = f"__CesiumRebakeMat{suffix}"

    # Save render state
    prev_engine = scene.render.engine
    prev_margin = int(getattr(scene.render.bake, "margin", margin_px))
    prev_use_clear = bool(getattr(scene.render.bake, "use_clear", True))
    prev_sel_to_active = bool(getattr(scene.render.bake, "use_selected_to_active", False))
    prev_cage_extrusion = float(getattr(scene.render.bake, "cage_extrusion", 0.0))
    prev_cycles_samples = None
    prev_diffuse_bounces = None
    if hasattr(scene, "cycles"):
        prev_cycles_samples = int(getattr(scene.cycles, "samples", 1))
        prev_diffuse_bounces = int(getattr(scene.cycles, "diffuse_bounces", 4))

    rebake_image = None
    rebake_mat = None

    try:
        # --- 1) Create fresh UV layout on the decimated tile mesh ---
        uv_layer = tile_mesh.uv_layers.get(uv_name)
        if uv_layer is None:
            uv_layer = tile_mesh.uv_layers.new(name=uv_name)
        tile_mesh.uv_layers.active = uv_layer
        if hasattr(uv_layer, "active_render"):
            uv_layer.active_render = True

        with _preserve_selection(context):
            if getattr(context, "mode", "OBJECT") != 'OBJECT':
                bpy.ops.object.mode_set(mode='OBJECT')
            bpy.ops.object.select_all(action='DESELECT')
            tile_obj.select_set(True)
            context.view_layer.objects.active = tile_obj

            bpy.ops.object.mode_set(mode='EDIT')
            bpy.ops.mesh.select_all(action='SELECT')
            bpy.ops.uv.smart_project(
                angle_limit=math.radians(66),       # 66° in radianti
                margin_method='SCALED',
                rotate_method='AXIS_ALIGNED_Y',
                island_margin=0.0,
                area_weight=0.0,
                correct_aspect=True,
                scale_to_bounds=True,
            )
            bpy.ops.object.mode_set(mode='OBJECT')

        # --- 2) Create blank target image ---
        rebake_image = bpy.data.images.new(
            name=img_name,
            width=int(atlas_size),
            height=int(atlas_size),
            alpha=True,
            float_buffer=False,
        )
        rebake_image.generated_color = (1.0, 1.0, 1.0, 1.0)

        # --- 3) Create bake-target material on tile_obj ---
        rebake_mat = bpy.data.materials.new(name=mat_name)
        rebake_mat.use_nodes = True
        nt = rebake_mat.node_tree
        nt.nodes.clear()

        out_node = nt.nodes.new("ShaderNodeOutputMaterial")
        bsdf_node = nt.nodes.new("ShaderNodeBsdfPrincipled")
        tex_node = nt.nodes.new("ShaderNodeTexImage")
        tex_node.image = rebake_image
        tex_node.location = (-500, 0)
        bsdf_node.location = (-250, 0)
        out_node.location = (20, 0)

        if "BSDF" in bsdf_node.outputs and "Surface" in out_node.inputs:
            nt.links.new(bsdf_node.outputs["BSDF"], out_node.inputs["Surface"])

        # Set the tex node as active (bake target)
        for node in nt.nodes:
            node.select = False
        tex_node.select = True
        nt.nodes.active = tex_node

        # Assign material to tile_obj
        tile_mesh.materials.clear()
        tile_mesh.materials.append(rebake_mat)
        for poly in tile_mesh.polygons:
            poly.material_index = 0
        tile_mesh.update()

        # --- 4) Configure Cycles and bake selected-to-active ---
        scene.render.engine = 'CYCLES'
        scene.render.bake.margin = int(margin_px)
        scene.render.bake.use_clear = True
        if hasattr(scene.render.bake, "margin_type"):
            scene.render.bake.margin_type = 'ADJACENT_FACES'
        if hasattr(scene.render.bake, "use_selected_to_active"):
            scene.render.bake.use_selected_to_active = True
        # No cage, minimal extrusion (0.01) as per tested manual settings
        if hasattr(scene.render.bake, "cage_extrusion"):
            scene.render.bake.cage_extrusion = 0.01
        if hasattr(scene.render.bake, "use_cage"):
            scene.render.bake.use_cage = False
        if hasattr(scene.render.bake, "max_ray_distance"):
            scene.render.bake.max_ray_distance = 0.0
        if prev_cycles_samples is not None:
            scene.cycles.samples = 1
        if prev_diffuse_bounces is not None:
            scene.cycles.diffuse_bounces = 1

        # Bake pass settings: color only, no direct/indirect lighting
        if hasattr(scene.render.bake, "use_pass_direct"):
            scene.render.bake.use_pass_direct = False
        if hasattr(scene.render.bake, "use_pass_indirect"):
            scene.render.bake.use_pass_indirect = False
        if hasattr(scene.render.bake, "use_pass_color"):
            scene.render.bake.use_pass_color = True

        with _preserve_selection(context):
            if getattr(context, "mode", "OBJECT") != 'OBJECT':
                bpy.ops.object.mode_set(mode='OBJECT')
            bpy.ops.object.select_all(action='DESELECT')

            # Ensure both objects are visible
            for obj in (base_obj, tile_obj):
                obj.hide_set(False)
                obj.hide_viewport = False
                obj.hide_render = False

            # Select source (base_obj) and set target (tile_obj) as active
            # LODgenerator pattern: lines 685-688
            tile_obj.select_set(True)
            base_obj.select_set(True)
            context.view_layer.objects.active = tile_obj

            result = bpy.ops.object.bake(
                type='DIFFUSE',
                pass_filter={'COLOR'},
                use_clear=True,
                use_selected_to_active=True,
                cage_extrusion=0.01,
                max_ray_distance=0.0,
                use_cage=False,
                margin_type='ADJACENT_FACES',
                margin=int(margin_px),
            )
            if 'FINISHED' not in result:
                return False, None, None

        # --- 5) Pack the baked image ---
        try:
            rebake_image.pack()
        except Exception:
            pass

        # --- 6) Wire up the final material ---
        if "Color" in tex_node.outputs and "Base Color" in bsdf_node.inputs:
            nt.links.new(tex_node.outputs["Color"], bsdf_node.inputs["Base Color"])
        if "Metallic" in bsdf_node.inputs:
            bsdf_node.inputs["Metallic"].default_value = 0.0
        if "Roughness" in bsdf_node.inputs:
            bsdf_node.inputs["Roughness"].default_value = 1.0

        return True, rebake_image, rebake_mat

    except Exception:
        return False, None, None

    finally:
        # Restore render state
        try:
            if getattr(context, "mode", "OBJECT") != 'OBJECT':
                bpy.ops.object.mode_set(mode='OBJECT')
        except Exception:
            pass
        try:
            scene.render.engine = prev_engine
        except Exception:
            pass
        try:
            scene.render.bake.margin = prev_margin
            scene.render.bake.use_clear = prev_use_clear
            if hasattr(scene.render.bake, "use_selected_to_active"):
                scene.render.bake.use_selected_to_active = prev_sel_to_active
            if hasattr(scene.render.bake, "cage_extrusion"):
                scene.render.bake.cage_extrusion = prev_cage_extrusion
        except Exception:
            pass
        if prev_cycles_samples is not None:
            try:
                scene.cycles.samples = prev_cycles_samples
            except Exception:
                pass
        if prev_diffuse_bounces is not None:
            try:
                scene.cycles.diffuse_bounces = prev_diffuse_bounces
            except Exception:
                pass


# ---------------------------------------------------------------------------
#  Spatial data + tree building
# ---------------------------------------------------------------------------
