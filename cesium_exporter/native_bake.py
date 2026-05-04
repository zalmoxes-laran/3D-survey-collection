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

    # Capture the source UV layer name BEFORE we override the active layer.
    # The materials we are about to bake from sample their textures against
    # the mesh's active UV by default; if we silently switch the active layer
    # to __CesiumBakeUV (smart-projected), every source ShaderNodeTexImage
    # will read at the wrong UV, baking random pixels into the atlas.
    source_uv_name = None
    if mesh.uv_layers and mesh.uv_layers.active:
        candidate = mesh.uv_layers.active.name
        if candidate != "__CesiumBakeUV":
            source_uv_name = candidate
    if source_uv_name is None:
        for uv in mesh.uv_layers:
            if uv.name != "__CesiumBakeUV":
                source_uv_name = uv.name
                break
    bake_info["source_uv_layer"] = source_uv_name or ""

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
    # Pre-fill the atlas with a neutral grey. Smart UV Project leaves gaps
    # between UV islands; the bake margin only paints a few px around each
    # island. If the bake operator is left with use_clear=True (default),
    # those gaps stay pure black and any face whose UV samples fall in
    # them appears black at render time. With a neutral grey pre-fill
    # combined with use_clear=False below, the gap regions stay grey
    # instead of black — much less visually intrusive when sampled.
    _GAP_FILL = (0.5, 0.5, 0.5, 1.0)
    bake_image.generated_color = _GAP_FILL
    n_pixels = int(atlas_size) * int(atlas_size)
    bake_image.pixels = list(_GAP_FILL) * n_pixels
    try:
        bake_image.update()
    except Exception:
        pass
    bake_info["baked_image"] = bake_image.name
    bake_info["gap_fill"] = list(_GAP_FILL)

    target_nodes = []
    pinned_source_tex_nodes = 0
    for mat in local_materials:
        if not mat.use_nodes:
            mat.use_nodes = True
        nt = mat.node_tree
        if nt is None:
            continue
        # Pin every existing source ShaderNodeTexImage to the original UV
        # layer via an explicit ShaderNodeUVMap. Otherwise, once we make
        # __CesiumBakeUV the active layer, the source images would be
        # sampled against smart-projected coordinates, contaminating the
        # bake with pixels from outside the original UV islands.
        if source_uv_name:
            existing_image_nodes = [n for n in nt.nodes if n.type == 'TEX_IMAGE']
            for tex_image_node in existing_image_nodes:
                vec_in = tex_image_node.inputs.get("Vector")
                if vec_in is None or vec_in.is_linked:
                    continue
                uvmap_node = nt.nodes.new("ShaderNodeUVMap")
                uvmap_node.name = "__CesiumBakeSourceUV"
                uvmap_node.label = "Cesium Bake Source UV"
                uvmap_node.uv_map = source_uv_name
                uvmap_node.location = (
                    tex_image_node.location.x - 220,
                    tex_image_node.location.y,
                )
                nt.links.new(uvmap_node.outputs["UV"], vec_in)
                pinned_source_tex_nodes += 1

        for node in nt.nodes:
            node.select = False
        tex_node = nt.nodes.new("ShaderNodeTexImage")
        tex_node.name = "__CesiumBakeTarget"
        tex_node.label = "Cesium Bake Target"
        tex_node.image = bake_image
        tex_node.select = True
        nt.nodes.active = tex_node
        target_nodes.append(tex_node)
    bake_info["pinned_source_tex_nodes"] = pinned_source_tex_nodes

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
            # Bulletproof deselection
            for obj in bpy.data.objects:
                try:
                    obj.select_set(False)
                except Exception:
                    pass
            base_obj.hide_set(False)
            base_obj.hide_viewport = False
            base_obj.hide_render = False
            base_obj.select_set(True)
            context.view_layer.objects.active = base_obj

            bpy.ops.object.mode_set(mode='EDIT')
            bpy.ops.mesh.select_all(action='SELECT')
            # UV algorithm choice — matches LODgenerator's atlas_uv_algorithm.
            # bpy.ops.uv.unwrap variants (ANGLE_BASED / CONFORMAL) can fail
            # poll() in headless contexts; we try them but fall back to
            # smart_project (always works headless) on any failure.
            algo = 'SMART'
            if scene is not None:
                algo = str(getattr(scene, "cesium_uv_algorithm", "SMART")).upper()

            def _unwrap_smart_fallback():
                bpy.ops.uv.smart_project(
                    angle_limit=math.radians(66),
                    margin_method='SCALED',
                    rotate_method='AXIS_ALIGNED_Y',
                    island_margin=0.0,
                    area_weight=0.0,
                    correct_aspect=True,
                    scale_to_bounds=True,
                )

            try:
                if algo == 'ANGLE':
                    bpy.ops.uv.unwrap(method='ANGLE_BASED')
                elif algo == 'CONFORMAL':
                    bpy.ops.uv.unwrap(method='CONFORMAL')
                elif algo == 'MINIMUM':
                    bpy.ops.uv.unwrap(method='CONFORMAL')
                    try:
                        bpy.ops.uv.minimize_stretch(iterations=64, blend=0.0)
                    except Exception:
                        pass
                else:  # SMART
                    _unwrap_smart_fallback()
            except Exception as e:
                print(f"[UV] {algo} unwrap failed ({e}); falling back to SMART")
                try:
                    _unwrap_smart_fallback()
                except Exception as e2:
                    print(f"[UV] SMART fallback also failed: {e2}")
            bpy.ops.object.mode_set(mode='OBJECT')

            # Scale the bake margin with atlas size: an 8 px margin on a
            # 2048 atlas is too thin (~0.4% of side) and leaves visible
            # black gaps between UV islands. Floor to atlas_size/64 (so
            # 1024 -> >=16, 2048 -> >=32).
            effective_margin = max(int(margin_px), int(atlas_size) // 64)
            bake_info["effective_margin_px"] = effective_margin

            scene.render.engine = 'CYCLES'
            scene.render.bake.margin = effective_margin
            # use_clear=False keeps the grey pre-fill we wrote into
            # bake_image.pixels in unbaked regions, so faces sampling
            # outside UV islands render grey instead of pure black.
            scene.render.bake.use_clear = False
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
                use_clear=False,
                use_selected_to_active=False,
                margin_type='ADJACENT_FACES',
                margin=effective_margin,
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

    # The glTF exporter assigns TEXCOORD slots in storage order, NOT by
    # active_render. If the source mesh has a pre-existing UV layer (typical
    # for OBJ imports), it stays at index 0 and becomes TEXCOORD_0 in the
    # GLB, while __CesiumBakeUV ends at index 1 (TEXCOORD_1). Since
    # baseColorTexture defaults to TEXCOORD_0, the rendered atlas would be
    # sampled with the wrong UVs (visible as "patchwork" of colours).
    # Drop every other UV layer so __CesiumBakeUV is the sole layer.
    extras = [uv.name for uv in mesh.uv_layers if uv.name != "__CesiumBakeUV"]
    for uv_name in extras:
        uv_to_remove = mesh.uv_layers.get(uv_name)
        if uv_to_remove is not None:
            mesh.uv_layers.remove(uv_to_remove)
    bake_info["removed_extra_uv_layers"] = len(extras)

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
            # Bulletproof deselection
            for obj in bpy.data.objects:
                try:
                    obj.select_set(False)
                except Exception:
                    pass
            tile_obj.select_set(True)
            context.view_layer.objects.active = tile_obj

            bpy.ops.object.mode_set(mode='EDIT')
            bpy.ops.mesh.select_all(action='SELECT')
            # UV algorithm choice — matches LODgenerator's atlas_uv_algorithm.
            # bpy.ops.uv.unwrap variants (ANGLE_BASED / CONFORMAL) can fail
            # poll() in headless contexts; we try them but fall back to
            # smart_project (always works headless) on any failure.
            algo = 'SMART'
            if scene is not None:
                algo = str(getattr(scene, "cesium_uv_algorithm", "SMART")).upper()

            def _unwrap_smart_fallback():
                bpy.ops.uv.smart_project(
                    angle_limit=math.radians(66),
                    margin_method='SCALED',
                    rotate_method='AXIS_ALIGNED_Y',
                    island_margin=0.0,
                    area_weight=0.0,
                    correct_aspect=True,
                    scale_to_bounds=True,
                )

            try:
                if algo == 'ANGLE':
                    bpy.ops.uv.unwrap(method='ANGLE_BASED')
                elif algo == 'CONFORMAL':
                    bpy.ops.uv.unwrap(method='CONFORMAL')
                elif algo == 'MINIMUM':
                    bpy.ops.uv.unwrap(method='CONFORMAL')
                    try:
                        bpy.ops.uv.minimize_stretch(iterations=64, blend=0.0)
                    except Exception:
                        pass
                else:  # SMART
                    _unwrap_smart_fallback()
            except Exception as e:
                print(f"[UV] {algo} unwrap failed ({e}); falling back to SMART")
                try:
                    _unwrap_smart_fallback()
                except Exception as e2:
                    print(f"[UV] SMART fallback also failed: {e2}")
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
        # Settings mirror LODgenerator.py (validated visually) — three key
        # differences from the previous implementation:
        #   - margin: was 8 px; now ≈ atlas_size (full-atlas bleed). Eliminates
        #     visible seams along UV island borders that produced the dark
        #     "shards" we used to see in v3..v8.
        #   - cage_extrusion: was 0.01 (tight); now 0.1 (matches LODgen).
        #     Lets bake rays reach the source through small displacements,
        #     killing the purple "no_diffuse_hit" artifacts on backface-
        #     adjacent faces.
        #   - use_pass_color explicit, direct/indirect explicitly off.
        scene.render.engine = 'CYCLES'
        # Margin: full-atlas bleed (LODgen pattern). Capped to atlas size.
        effective_margin = max(int(margin_px), int(atlas_size))
        scene.render.bake.margin = effective_margin
        scene.render.bake.use_clear = True
        if hasattr(scene.render.bake, "margin_type"):
            scene.render.bake.margin_type = 'ADJACENT_FACES'
        if hasattr(scene.render.bake, "use_selected_to_active"):
            scene.render.bake.use_selected_to_active = True
        # cage_extrusion 0.1 (LODgen value). Old 0.01 was too tight and
        # caused 'no_diffuse_hit' purple/blue artifacts on faces with
        # slightly displaced normals.
        if hasattr(scene.render.bake, "cage_extrusion"):
            scene.render.bake.cage_extrusion = 0.1
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

            # Bulletproof deselection: loop over ALL objects, not just
            # the operator which may skip hidden/non-selectable ones.
            for obj in bpy.data.objects:
                try:
                    obj.select_set(False)
                except Exception:
                    pass

            # Ensure ONLY base_obj and tile_obj are visible and selected
            for obj in (base_obj, tile_obj):
                obj.hide_set(False)
                obj.hide_viewport = False
                obj.hide_render = False

            # Select source (base_obj) and set target (tile_obj) as active
            # EXACTLY 2 objects: base_obj=selected source, tile_obj=active target
            base_obj.select_set(True)
            tile_obj.select_set(True)
            context.view_layer.objects.active = tile_obj

            # NB: explicit kwargs to bpy.ops.object.bake OVERRIDE scene
            # settings — must mirror the scene values we set above.
            # cage_extrusion 0.1 + margin=atlas_size (LODgenerator pattern).
            result = bpy.ops.object.bake(
                type='DIFFUSE',
                pass_filter={'COLOR'},
                use_clear=True,
                use_selected_to_active=True,
                cage_extrusion=0.1,
                max_ray_distance=0.0,
                use_cage=False,
                margin_type='ADJACENT_FACES',
                margin=effective_margin,
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
