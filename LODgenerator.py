import bpy
import os
import time
from .functions import *
from mathutils import Vector
from bpy.types import Menu, Operator, Panel
import subprocess

# Funzione ricorsiva per impostare come attiva la layer_collection che contiene l'oggetto
def set_active_collection_by_object(obj, layer_coll=None):
    view_layer = bpy.context.view_layer
    if layer_coll is None:
        for lc in view_layer.layer_collection.children:
            found = set_active_collection_by_object(obj, lc)
            if found:
                return found
    else:
        if obj.name in layer_coll.collection.objects:
            view_layer.active_layer_collection = layer_coll
            return layer_coll
        for child in layer_coll.children:
            found = set_active_collection_by_object(obj, child)
            if found:
                return found
    return None

def selectLOD(listobjects, lodnum, basename):
    name2search = basename + '_LOD' + str(lodnum)
    for ob in listobjects:
        if ob.name == name2search:
            objatgivenlod = ob
            return objatgivenlod
        else:
            objatgivenlod = None
    return objatgivenlod

def getChildren(myObject):
    children = []
    for ob in bpy.data.objects:
        if ob.parent == myObject:
            children.append(ob)
    return children

class OBJECT_OT_LOD0(bpy.types.Operator):
    """Set selected objs as LOD0. It creates an additional ATLAS Map"""
    bl_idname = "lod0.creation"
    bl_label = "LOD0"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        selected_objs = bpy.context.selected_objects

        # Create or get LOD0 collection
        if bpy.data.collections.get("LOD0") is None:
            LOD0Col = bpy.data.collections.new("LOD0")
            context.scene.collection.children.link(LOD0Col)
            print('Created LOD0 collection')
        else:
            LOD0Col = bpy.data.collections.get("LOD0")
            print('Found existing LOD0 collection')

        for obj in selected_objs:
            bpy.ops.object.select_all(action='DESELECT')
            obj.select_set(True)
            bpy.context.view_layer.objects.active = obj
            bpy.ops.object.shade_smooth()
            baseobj = obj.name
            if not baseobj.endswith('LOD0'):
                obj.name = baseobj + '_LOD0'
            if len(obj.data.uv_layers) > 1:
                if obj.data.uv_layers[0].name == 'MultiTex' and obj.data.uv_layers[1].name == 'Atlas':
                    pass
            else:
                create_double_UV(obj)
            rename_ge(obj)

            # Move object to LOD0 collection
            # First, find all collections containing this object
            obj_collections = [col for col in bpy.data.collections if obj.name in col.objects]

            # Link to LOD0 collection if not already there
            if obj.name not in LOD0Col.objects:
                LOD0Col.objects.link(obj)
                print(f'Linked "{obj.name}" to LOD0 collection')

            # Unlink from other collections (except LOD0)
            for col in obj_collections:
                if col != LOD0Col:
                    try:
                        col.objects.unlink(obj)
                        print(f'Unlinked "{obj.name}" from collection "{col.name}"')
                    except:
                        pass

        return {'FINISHED'}

#_____________________________________________________________________________

def ratio_for_current_lod(lod, context):
    if lod == 1:
        ratio = context.scene.LOD1_dec_ratio
    if lod == 2:
        ratio = context.scene.LOD2_dec_ratio
    if lod == 3:
        ratio = context.scene.LOD3_dec_ratio
    if lod == 4:
        ratio = context.scene.LOD4_dec_ratio
    return ratio

def tex_res_for_current_lod(lod, context):
    if lod == 1:
        tex_res = context.scene.LOD1_tex_res
    if lod == 2:
        tex_res = context.scene.LOD2_tex_res
    if lod == 3:
        tex_res = context.scene.LOD3_tex_res
    if lod == 4:
        tex_res = context.scene.LOD4_tex_res
    return tex_res

def object_has_alpha_texture(obj):
    if obj is None or obj.type != 'MESH':
        return False
    for mat_slot in obj.material_slots:
        mat = mat_slot.material
        if mat is None or not mat.use_nodes or mat.node_tree is None:
            continue
        for node in mat.node_tree.nodes:
            if node.type == 'TEX_IMAGE' and getattr(node, "image", None) is not None:
                image = node.image
                if getattr(image, "channels", 0) >= 4:
                    return True
    return False

def should_preserve_alpha(scene, source_obj):
    if scene.lod_ignore_source_alpha:
        return False
    if scene.use_alpha:
        return True
    if not scene.lod_auto_preserve_alpha:
        return False
    return object_has_alpha_texture(source_obj)

def configure_material_alpha(mat, bsdf, texImage, scene, use_alpha):
    if not use_alpha:
        mat.blend_method = 'OPAQUE'
        return

    if bsdf.inputs['Alpha'].is_linked:
        for link in list(bsdf.inputs['Alpha'].links):
            mat.node_tree.links.remove(link)
    mat.node_tree.links.new(texImage.outputs['Alpha'], bsdf.inputs['Alpha'])
    mat.blend_method = scene.lod_alpha_mode
    if scene.lod_alpha_mode == 'CLIP':
        mat.alpha_threshold = scene.lod_alpha_clip_threshold

def workflow_uses_normal_maps(scene):
    return scene.lod_generate_normal_maps or scene.lod_workflow_preset == 'CLASSIC_NORMAL'

def update_lod_progress(context, task="", current_obj=0, total_obj=0, current_lod=0, total_lod=0, elapsed=0.0):
    """Update LOD generation progress information"""
    scene = context.scene
    if task:
        scene.lod_progress_current_task = task
    if total_obj > 0:
        scene.lod_progress_current_object = current_obj
        scene.lod_progress_total_objects = total_obj
    if total_lod > 0:
        scene.lod_progress_current_lod = current_lod
        scene.lod_progress_total_lods = total_lod
    if elapsed > 0:
        scene.lod_progress_elapsed_time = elapsed

    # Force UI update for all windows
    for window in context.window_manager.windows:
        for area in window.screen.areas:
            if area.type == 'VIEW_3D':
                area.tag_redraw()

    # Force immediate update with redraw timer
    try:
        bpy.ops.wm.redraw_timer(type='DRAW_WIN_SWAP', iterations=1)
    except:
        pass

def add_to_lod_log(context, message):
    """Add a message to the LOD progress log"""
    scene = context.scene
    if scene.lod_progress_log:
        scene.lod_progress_log += "\n" + message
    else:
        scene.lod_progress_log = message

    # Keep only last 20 lines
    log_lines = scene.lod_progress_log.split('\n')
    if len(log_lines) > 20:
        scene.lod_progress_log = '\n'.join(log_lines[-20:])

    # Force immediate UI redraw for all windows
    for window in context.window_manager.windows:
        for area in window.screen.areas:
            if area.type == 'VIEW_3D':
                area.tag_redraw()

    # Force immediate update with redraw timer
    try:
        bpy.ops.wm.redraw_timer(type='DRAW_WIN_SWAP', iterations=1)
    except:
        pass


def _get_addon_preferences(context):
    addon_key = (__package__ or "").split(".")[0]
    addon = context.preferences.addons.get(addon_key)
    if addon is None:
        return None
    return addon.preferences


LOD_BASE_PRESET_NAME = "Base"
LOD_CLASSIC_PRESET_NAME = "Classic LOD"
LOD_CLASSIC_NORMAL_PRESET_NAME = "Classic LOD + Normal Maps"
LOD_VEGETATION_PRESET_NAME = "Vegetation Alpha Clip"
LOD_CESIUM_ATLAS_PRESET_NAME = "LOD0 Atlas Bake (Cesium)"

WORKFLOW_PRESET_LEGACY_NAMES = {
    LOD_CLASSIC_PRESET_NAME: ["LOD classico"],
    LOD_CLASSIC_NORMAL_PRESET_NAME: ["LOD classico con normal map"],
    LOD_VEGETATION_PRESET_NAME: [],
    LOD_CESIUM_ATLAS_PRESET_NAME: ["Bake Atlas LOD0 (Cesium)"]
}

def _apply_workflow_preset_defaults(preset, workflow_name):
    preset.lod_workflow_preset = workflow_name
    preset.lod_generate_normal_maps = workflow_name == 'CLASSIC_NORMAL'
    preset.lod_normal_map_max_level = max(1, preset.lod_normal_map_max_level)
    # Alpha must stay opt-in by default.
    preset.lod_auto_preserve_alpha = False
    preset.lod_ignore_source_alpha = False
    preset.lod_alpha_mode = 'BLEND'
    preset.lod_alpha_clip_threshold = 0.5

    if workflow_name == 'VEGETATION_ALPHA':
        preset.lod_texture_format = 'PNG'
        preset.lod_use_alpha = True
        preset.lod_auto_preserve_alpha = True
        preset.lod_alpha_mode = 'CLIP'
        preset.lod_alpha_clip_threshold = 0.35
        preset.lod_decimate_borders = True

    if workflow_name == 'CESIUM_ATLAS':
        preset.lod_num = 1
        preset.lod1_dec_ratio = 1.0
        preset.lod_atlas_uv_recalc = True
        preset.lod_texture_format = 'PNG'
        preset.lod_use_alpha = False

def apply_scene_workflow_defaults(scene, workflow_name):
    scene.lod_generate_normal_maps = workflow_name == 'CLASSIC_NORMAL'
    scene.lod_normal_map_max_level = max(1, min(scene.lod_normal_map_max_level, scene.LODnum))
    scene.lod_auto_preserve_alpha = False
    scene.lod_ignore_source_alpha = False
    scene.lod_alpha_mode = 'BLEND'
    scene.lod_alpha_clip_threshold = 0.5

    if workflow_name == 'VEGETATION_ALPHA':
        scene.texture_format = 'PNG'
        scene.use_alpha = True
        scene.lod_auto_preserve_alpha = True
        scene.lod_alpha_mode = 'CLIP'
        scene.lod_alpha_clip_threshold = 0.35
        scene.decimate_borders = True

    if workflow_name == 'CESIUM_ATLAS':
        scene.LODnum = 1
        scene.LOD1_dec_ratio = 1.0
        scene.atlas_uv_recalc = True
        scene.texture_format = 'PNG'
        scene.use_alpha = False
        scene.lod_generate_normal_maps = False

def on_lod_workflow_preset_update(scene, context):
    if scene is None:
        return
    required_attrs = (
        "LODnum", "LOD1_dec_ratio", "atlas_uv_recalc", "texture_format",
        "use_alpha", "lod_generate_normal_maps", "lod_normal_map_max_level",
        "lod_auto_preserve_alpha", "lod_ignore_source_alpha",
        "lod_alpha_mode", "lod_alpha_clip_threshold", "decimate_borders"
    )
    if not all(hasattr(scene, attr) for attr in required_attrs):
        return
    apply_scene_workflow_defaults(scene, scene.lod_workflow_preset)


def _copy_scene_to_preset(scene, preset):
    preset.lod_num = scene.LODnum
    preset.lod1_dec_ratio = scene.LOD1_dec_ratio
    preset.lod2_dec_ratio = scene.LOD2_dec_ratio
    preset.lod3_dec_ratio = scene.LOD3_dec_ratio
    preset.lod4_dec_ratio = scene.LOD4_dec_ratio
    preset.lod1_tex_res = scene.LOD1_tex_res
    preset.lod2_tex_res = scene.LOD2_tex_res
    preset.lod3_tex_res = scene.LOD3_tex_res
    preset.lod4_tex_res = scene.LOD4_tex_res
    preset.lod_workflow_preset = scene.lod_workflow_preset
    preset.lod_generate_normal_maps = scene.lod_generate_normal_maps
    preset.lod_normal_map_max_level = scene.lod_normal_map_max_level
    preset.lod_auto_preserve_alpha = scene.lod_auto_preserve_alpha
    preset.lod_ignore_source_alpha = scene.lod_ignore_source_alpha
    preset.lod_alpha_mode = scene.lod_alpha_mode
    preset.lod_alpha_clip_threshold = scene.lod_alpha_clip_threshold
    preset.lod_pad_on = scene.LOD_pad_on
    preset.lod_use_scene_settings = scene.LOD_use_scene_settings
    preset.lod_atlas_uv_recalc = scene.atlas_uv_recalc
    preset.lod_atlas_uv_algorithm = scene.atlas_uv_algorithm
    preset.lod_texture_format = scene.texture_format
    preset.lod_use_alpha = scene.use_alpha
    preset.lod_decimate_borders = scene.decimate_borders


def _copy_preset_to_scene(scene, preset):
    scene.LODnum = preset.lod_num
    scene.LOD1_dec_ratio = preset.lod1_dec_ratio
    scene.LOD2_dec_ratio = preset.lod2_dec_ratio
    scene.LOD3_dec_ratio = preset.lod3_dec_ratio
    scene.LOD4_dec_ratio = preset.lod4_dec_ratio
    scene.LOD1_tex_res = preset.lod1_tex_res
    scene.LOD2_tex_res = preset.lod2_tex_res
    scene.LOD3_tex_res = preset.lod3_tex_res
    scene.LOD4_tex_res = preset.lod4_tex_res
    scene.lod_workflow_preset = preset.lod_workflow_preset
    scene.lod_generate_normal_maps = preset.lod_generate_normal_maps
    scene.lod_normal_map_max_level = preset.lod_normal_map_max_level
    scene.lod_auto_preserve_alpha = preset.lod_auto_preserve_alpha
    scene.lod_ignore_source_alpha = preset.lod_ignore_source_alpha
    scene.lod_alpha_mode = preset.lod_alpha_mode
    scene.lod_alpha_clip_threshold = preset.lod_alpha_clip_threshold
    scene.LOD_pad_on = preset.lod_pad_on
    scene.LOD_use_scene_settings = preset.lod_use_scene_settings
    scene.atlas_uv_recalc = preset.lod_atlas_uv_recalc
    scene.atlas_uv_algorithm = preset.lod_atlas_uv_algorithm
    scene.texture_format = preset.lod_texture_format
    scene.use_alpha = preset.lod_use_alpha
    scene.decimate_borders = preset.lod_decimate_borders


def _copy_legacy_defaults_to_preset(prefs, preset):
    preset.lod_num = prefs.lod_num
    preset.lod1_dec_ratio = prefs.lod1_dec_ratio
    preset.lod2_dec_ratio = prefs.lod2_dec_ratio
    preset.lod3_dec_ratio = prefs.lod3_dec_ratio
    preset.lod4_dec_ratio = prefs.lod4_dec_ratio
    preset.lod1_tex_res = prefs.lod1_tex_res
    preset.lod2_tex_res = prefs.lod2_tex_res
    preset.lod3_tex_res = prefs.lod3_tex_res
    preset.lod4_tex_res = prefs.lod4_tex_res
    preset.lod_workflow_preset = prefs.lod_workflow_preset
    preset.lod_generate_normal_maps = prefs.lod_generate_normal_maps
    preset.lod_normal_map_max_level = prefs.lod_normal_map_max_level
    preset.lod_auto_preserve_alpha = prefs.lod_auto_preserve_alpha
    preset.lod_ignore_source_alpha = prefs.lod_ignore_source_alpha
    preset.lod_alpha_mode = prefs.lod_alpha_mode
    preset.lod_alpha_clip_threshold = prefs.lod_alpha_clip_threshold
    preset.lod_pad_on = prefs.lod_pad_on
    preset.lod_use_scene_settings = prefs.lod_use_scene_settings
    preset.lod_atlas_uv_recalc = prefs.lod_atlas_uv_recalc
    preset.lod_atlas_uv_algorithm = prefs.lod_atlas_uv_algorithm
    preset.lod_texture_format = prefs.lod_texture_format
    preset.lod_use_alpha = prefs.lod_use_alpha
    preset.lod_decimate_borders = prefs.lod_decimate_borders


def _find_preset_by_name(prefs, preset_name):
    for preset in prefs.lod_presets:
        if preset.name == preset_name:
            return preset
    return None


def _existing_preset_names(prefs):
    return {preset.name for preset in prefs.lod_presets}


def _make_unique_preset_name(prefs, requested_name):
    clean_name = (requested_name or "").strip()
    if not clean_name:
        clean_name = "Preset"
    existing_names = _existing_preset_names(prefs)
    if clean_name not in existing_names:
        return clean_name

    idx = 1
    while True:
        candidate = f"{clean_name}_{idx:02d}"
        if candidate not in existing_names:
            return candidate
        idx += 1


def _ensure_base_preset(prefs):
    base_preset = _find_preset_by_name(prefs, LOD_BASE_PRESET_NAME)
    if base_preset is not None:
        return base_preset

    base_preset = prefs.lod_presets.add()
    base_preset.name = LOD_BASE_PRESET_NAME
    _copy_legacy_defaults_to_preset(prefs, base_preset)
    return base_preset

def _ensure_workflow_preset(prefs, preset_name, workflow_name):
    existing = _find_preset_by_name(prefs, preset_name)
    if existing is not None:
        return existing

    for legacy_name in WORKFLOW_PRESET_LEGACY_NAMES.get(preset_name, []):
        legacy_preset = _find_preset_by_name(prefs, legacy_name)
        if legacy_preset is not None:
            legacy_preset.name = preset_name
            if not legacy_preset.lod_workflow_preset:
                legacy_preset.lod_workflow_preset = workflow_name
            return legacy_preset

    preset = prefs.lod_presets.add()
    preset.name = preset_name
    _copy_legacy_defaults_to_preset(prefs, preset)
    _apply_workflow_preset_defaults(preset, workflow_name)
    return preset


def _get_active_preset(prefs):
    _ensure_base_preset(prefs)
    _ensure_workflow_preset(prefs, LOD_CLASSIC_PRESET_NAME, 'CLASSIC')
    _ensure_workflow_preset(prefs, LOD_CLASSIC_NORMAL_PRESET_NAME, 'CLASSIC_NORMAL')
    _ensure_workflow_preset(prefs, LOD_VEGETATION_PRESET_NAME, 'VEGETATION_ALPHA')
    _ensure_workflow_preset(prefs, LOD_CESIUM_ATLAS_PRESET_NAME, 'CESIUM_ATLAS')
    active_name = (prefs.lod_active_preset or "").strip()
    active_preset = _find_preset_by_name(prefs, active_name)
    if active_preset is None:
        prefs.lod_active_preset = LOD_BASE_PRESET_NAME
        active_preset = _find_preset_by_name(prefs, LOD_BASE_PRESET_NAME)
    return active_preset

class OBJECT_OT_LOD(bpy.types.Operator):
    """Creates the desired LODs and export them as obj(s) in LOD(x) subfolders"""
    bl_idname = "lod.creation"
    bl_label = "LOD"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        start_time = time.time()
        context = bpy.context
        selected_objects = context.selected_objects
        if not selected_objects:
            self.report({'WARNING'}, "No objects selected")
            return {'CANCELLED'}

        ob_tot = len(selected_objects)
        workflow_preset = context.scene.lod_workflow_preset
        is_cesium_atlas_workflow = workflow_preset == 'CESIUM_ATLAS'
        LODnum = 1 if is_cesium_atlas_workflow else context.scene.LODnum
        normal_maps_enabled = workflow_uses_normal_maps(context.scene) and not is_cesium_atlas_workflow
        normal_map_max_level = min(context.scene.lod_normal_map_max_level, LODnum)
        atlas_recalc_enabled = context.scene.atlas_uv_recalc or is_cesium_atlas_workflow
        i_lodbake_counter = 1

        # Initialize progress tracking
        context.scene.lod_progress_active = True
        context.scene.lod_progress_log = ""
        update_lod_progress(context, task="Initializing LOD generation...",
                          current_obj=0, total_obj=ob_tot,
                          current_lod=0, total_lod=LODnum)

        basedir = os.path.dirname(bpy.data.filepath)
        if not basedir:
            context.scene.lod_progress_active = False
            raise Exception("Save the blend file")

        print("Number of LOD(s) to be created is: " + str(LODnum))
        add_to_lod_log(context, f"Starting LOD generation: {LODnum} LOD(s) for {ob_tot} object(s)")
        add_to_lod_log(context, f"Workflow preset: {workflow_preset}")
        if is_cesium_atlas_workflow and not context.scene.atlas_uv_recalc:
            add_to_lod_log(context, "INFO: Cesium workflow forces Atlas UV recalculation")
        last_margin_val = context.scene.render.bake.margin
        
        while i_lodbake_counter <= LODnum:
            if is_cesium_atlas_workflow:
                currentLOD = 'LOD0_ATLAS'
            else:
                currentLOD = 'LOD' + str(i_lodbake_counter)
            subfolder = currentLOD

            # Update progress for current LOD level
            update_lod_progress(context, task=f"Creating {currentLOD}...",
                              current_lod=i_lodbake_counter, total_lod=LODnum)

            if not os.path.exists(os.path.join(basedir, subfolder)):
                os.mkdir(os.path.join(basedir, subfolder))
                print('There is no ' + subfolder + ' folder. Creating one...')
                add_to_lod_log(context, f"Created folder: {subfolder}")
            else:
                print('Found previously created ' + subfolder + ' folder. I will use it')
                add_to_lod_log(context, f"Using existing folder: {subfolder}")

            ob_counter = 1
            print('<<<<<<<<<<<<<< CREATION OF ' + currentLOD + ' >>>>>>>>>>>>>>')
            print('>>>>>> ' + str(ob_tot) + ' objects will be processed')

            for obj_LOD0 in selected_objects:
                start_time_ob = time.time()

                # Update progress for current object
                elapsed_total = time.time() - start_time
                update_lod_progress(context, task=f"Processing {obj_LOD0.name} for {currentLOD}",
                                  current_obj=ob_counter, total_obj=ob_tot,
                                  current_lod=i_lodbake_counter, total_lod=LODnum,
                                  elapsed=elapsed_total)

                print('>>> ' + currentLOD + ' >>>')
                print('>>>>>> processing the object "' + obj_LOD0.name + '" (' + str(ob_counter) + '/' + str(ob_tot) + ')')
                bpy.ops.object.select_all(action='DESELECT')
                obj_LOD0.select_set(True)
                context.view_layer.objects.active = obj_LOD0

                # Imposta come attiva la collezione in cui si trova l'oggetto
                set_active_collection_by_object(obj_LOD0)
                
                obj_LOD0_name = obj_LOD0.name
                if '_LOD0' in obj_LOD0_name:
                    obj_base_name = obj_LOD0_name.replace("_LOD0", "")
                else:
                    obj_base_name = obj_LOD0_name

                # Determine if object has OB_ prefix to maintain consistency
                has_ob_prefix = obj_base_name.startswith('OB_')

                print('Creating new LOD' + str(i_lodbake_counter) + ' object..')
                bpy.ops.object.duplicate(linked=False, mode='TRANSLATION')
                obj_LODnew = context.view_layer.objects.active

                LOD0layerCol = context.view_layer.active_layer_collection
                LOD0Col = bpy.data.collections.get(LOD0layerCol.name)

                if bpy.data.collections.get(currentLOD) is None:
                    currentLODCol = bpy.data.collections.new(currentLOD)
                    currentLODCol.name = currentLOD
                    context.scene.collection.children.link(currentLODCol)
                else:
                    currentLODCol = bpy.data.collections.get(currentLOD)

                currentLODCol.objects.link(obj_LODnew)
                LOD0Col.objects.unlink(obj_LODnew)

                bpy.ops.object.select_all(action='DESELECT')
                context.view_layer.objects.active = obj_LODnew
                obj_LODnew.select_set(True)
                obj_LODnew.name = obj_base_name + "_" + currentLOD
                obj_LODnew_name = obj_LODnew.name

                # Get clean name without OB_ prefix for material and texture naming
                if has_ob_prefix:
                    obj_clean_name = obj_base_name[3:]  # Remove 'OB_' prefix
                else:
                    obj_clean_name = obj_base_name

                for i in range(0, len(bpy.data.objects[obj_LODnew_name].material_slots)):
                    bpy.ops.object.material_slot_remove()

                if len(obj_LODnew.data.uv_layers) > 1 and obj_LODnew.data.uv_layers[1].name == 'Atlas':
                    print('Found Atlas UV mapping layer. I will use it.')
                    uv_layers = obj_LODnew.data.uv_layers
                    uv_layers.remove(uv_layers[0])
                else:
                    print('Creating new UV mapping layer.')
                    create_double_UV(obj_LODnew)

                # Mesh decimation
                if not is_cesium_atlas_workflow and ratio_for_current_lod(i_lodbake_counter, context) < 1:
                    decimate_mesh(context, obj_LODnew, ratio_for_current_lod(i_lodbake_counter, context), currentLOD, context.scene.decimate_borders)

                obj_LOD0.data.uv_layers["MultiTex"].active_render = True

                # Se l'opzione è attiva, ricalcola l'UV mapping dell'Atlas usando l'algoritmo scelto
                if atlas_recalc_enabled:
                    print("Recalculating Atlas UV mapping using algorithm: " + context.scene.atlas_uv_algorithm)
                    if "Atlas" in obj_LODnew.data.uv_layers:
                        obj_LODnew.data.uv_layers.active = obj_LODnew.data.uv_layers["Atlas"]
                    else:
                        new_atlas = obj_LODnew.data.uv_layers.new(name="Atlas")
                        obj_LODnew.data.uv_layers.active = new_atlas
                    bpy.ops.object.mode_set(mode='EDIT')
                    bpy.ops.mesh.select_all(action='SELECT')
                    algo = context.scene.atlas_uv_algorithm
                    if algo == 'SMART':
                        bpy.ops.uv.smart_project(scale_to_bounds=True)
                    elif algo == 'ANGLE':
                        bpy.ops.uv.unwrap(method='ANGLE_BASED', use_limit_boundaries=True)
                    elif algo == 'CONFORMAL':
                        bpy.ops.uv.unwrap(method='CONFORMAL', use_limit_boundaries=True)
                    elif algo == 'MINIMUM':
                        try:
                            bpy.ops.uv.minimize_stretch()
                        except Exception as e:
                            print("Minimum Stretch operator not available, using conformal instead")
                            bpy.ops.uv.unwrap(method='CONFORMAL', use_limit_boundaries=True)
                    else:
                        bpy.ops.uv.smart_project(scale_to_bounds=True)
                    bpy.ops.object.mode_set(mode='OBJECT')


                print('Creating new texture atlas for ' + currentLOD + '....')
                tex_res = tex_res_for_current_lod(i_lodbake_counter, context)
                tex_LODnew_name = "T_" + obj_clean_name + "_" + currentLOD
                preserve_source_alpha = should_preserve_alpha(context.scene, obj_LOD0)
                effective_texture_format = 'PNG' if preserve_source_alpha else context.scene.texture_format
                effective_use_alpha = effective_texture_format == 'PNG' and (context.scene.use_alpha or preserve_source_alpha)

                if preserve_source_alpha and context.scene.texture_format != 'PNG':
                    add_to_lod_log(context, f"INFO: forcing PNG for {obj_LODnew.name} to preserve alpha")

                if effective_texture_format == 'PNG':
                    tempimage = bpy.data.images.new(name=tex_LODnew_name, width=tex_res, height=tex_res, alpha=effective_use_alpha)
                    tempimage.filepath_raw = "//" + subfolder + '/' + tex_LODnew_name + ".png"
                    tempimage.file_format = 'PNG'
                else:
                    tempimage = bpy.data.images.new(name=tex_LODnew_name, width=tex_res, height=tex_res, alpha=False)
                    tempimage.filepath_raw = "//" + subfolder + '/' + tex_LODnew_name + ".jpg"
                    tempimage.file_format = 'JPEG'

                # Annotate current cycles render settings
                to_be_restored_render_engine = context.scene.render.engine
                context.scene.render.engine = 'CYCLES'
                context.scene.cycles.bake_type = 'DIFFUSE'

                if context.scene.LOD_use_scene_settings:
                    context.scene.render.bake.use_pass_direct = True
                    context.scene.render.bake.use_pass_indirect = True
                else:
                    context.scene.render.bake.use_pass_direct = False
                    context.scene.render.bake.use_pass_indirect = False  

                context.scene.render.bake.use_pass_color = True
                context.scene.render.bake.use_selected_to_active = True
                context.scene.render.bake.cage_extrusion = 0.1

                if context.scene.LOD_pad_on:
                    context.scene.render.bake.margin = tex_res_for_current_lod(i_lodbake_counter, context)
                
                if not context.scene.LOD_use_scene_settings:
                    to_restore_samples = context.scene.cycles.samples
                    context.scene.cycles.samples = 1
                    to_restore_bounces = context.scene.cycles.diffuse_bounces
                    context.scene.cycles.diffuse_bounces = 1

                print('Creating custom material for ' + currentLOD + '...')
                bpy.ops.object.select_all(action='DESELECT')
                obj_LODnew.select_set(True)
                context.view_layer.objects.active = obj_LODnew
                # Pass clean name for material to avoid OB_ prefix in material name
                mat, texImage, bsdf = create_material_from_image(context, tempimage, obj_LODnew, False, obj_clean_name + "_" + currentLOD)

                print('Passing color data from LOD0 to ' + currentLOD + '...')
                bpy.ops.object.select_all(action='DESELECT')
                obj_LODnew.select_set(True)
                obj_LOD0.select_set(True)
                context.view_layer.objects.active = obj_LODnew
                mat.node_tree.nodes.active = texImage
                bpy.ops.object.bake(type='DIFFUSE')
                tempimage.save()

                if bsdf.inputs['Base Color'].is_linked:
                    for link in list(bsdf.inputs['Base Color'].links):
                        mat.node_tree.links.remove(link)
                mat.node_tree.links.new(texImage.outputs['Color'], bsdf.inputs['Base Color'])
                configure_material_alpha(mat, bsdf, texImage, context.scene, effective_use_alpha)

                bake_normal_for_this_lod = normal_maps_enabled and i_lodbake_counter <= normal_map_max_level
                if bake_normal_for_this_lod:
                    print('Baking normal map for ' + currentLOD + '...')
                    normal_map_name = "N_" + obj_clean_name + "_" + currentLOD
                    normal_image = bpy.data.images.new(name=normal_map_name, width=tex_res, height=tex_res, alpha=False)
                    normal_image.filepath_raw = "//" + subfolder + '/' + normal_map_name + ".png"
                    normal_image.file_format = 'PNG'
                    try:
                        normal_image.colorspace_settings.name = 'Non-Color'
                    except Exception:
                        pass

                    normal_tex = mat.node_tree.nodes.new('ShaderNodeTexImage')
                    normal_tex.image = normal_image
                    normal_tex.name = "LOD_NormalMap"
                    normal_tex.label = "LOD Normal"
                    normal_tex.interpolation = 'Linear'

                    normal_map_node = mat.node_tree.nodes.new('ShaderNodeNormalMap')
                    normal_map_node.name = "LOD_NormalMap_Node"
                    normal_map_node.label = "LOD Normal Map"

                    mat.node_tree.links.new(normal_tex.outputs['Color'], normal_map_node.inputs['Color'])
                    if bsdf.inputs['Normal'].is_linked:
                        for link in list(bsdf.inputs['Normal'].links):
                            mat.node_tree.links.remove(link)
                    mat.node_tree.links.new(normal_map_node.outputs['Normal'], bsdf.inputs['Normal'])

                    mat.node_tree.nodes.active = normal_tex
                    context.scene.cycles.bake_type = 'NORMAL'
                    context.scene.render.bake.use_selected_to_active = True
                    context.scene.render.bake.cage_extrusion = 0.1
                    try:
                        context.scene.render.bake.normal_space = 'TANGENT'
                    except Exception:
                        pass

                    bpy.ops.object.bake(type='NORMAL')
                    normal_image.save()
                    add_to_lod_log(context, f"INFO: normal map baked for {obj_LODnew.name}")

                if not context.scene.LOD_use_scene_settings:
                    context.scene.cycles.diffuse_bounces = to_restore_bounces
                    context.scene.cycles.samples = to_restore_samples
                    
                context.scene.render.engine = to_be_restored_render_engine

                # Set proper mesh data name using clean name (without OB_ prefix)
                obj_LODnew.data.name = 'ME_' + obj_clean_name + "_" + currentLOD

                bpy.ops.object.select_all(action='DESELECT')
                obj_LODnew.select_set(True)
                context.view_layer.objects.active = obj_LODnew

                print('Saving on obj/mtl file for ' + currentLOD + '...')
                activename = bpy.path.clean_name(obj_LODnew.name)
                fn = os.path.join(basedir, subfolder, activename)
                bpy.ops.wm.obj_export(filepath=fn + ".obj", export_animation=False, forward_axis='Y', up_axis='Z', global_scale=1.0, apply_modifiers=True, export_eval_mode='DAG_EVAL_VIEWPORT', export_selected_objects=True, export_uv=True, export_normals=True, export_materials=True, export_pbr_extensions=False, path_mode='RELATIVE', export_triangulated_mesh=False, export_curves_as_nurbs=False, export_object_groups=False, export_material_groups=False, export_vertex_groups=False, export_smooth_groups=False, smooth_group_bitflags=False)

                obj_time = time.time() - start_time_ob
                print('>>> "' + obj_LODnew.name + '" (' + str(ob_counter) + '/' + str(ob_tot) + ') object baked in ' + str(obj_time) + ' seconds')
                add_to_lod_log(context, f"✓ {obj_LODnew.name} completed in {obj_time:.1f}s")
                ob_counter += 1

            i_lodbake_counter += 1

        # Finalize progress tracking
        end_time = time.time() - start_time
        context.scene.render.bake.margin = last_margin_val

        # Final log entry
        print('<<<<<<< Process done >>>>>>')
        print('>>>' + str(ob_tot) + ' objects processed in ' + str(end_time) + ' seconds')

        minutes = int(end_time // 60)
        seconds = int(end_time % 60)
        add_to_lod_log(context, f"=== Process completed ===")
        add_to_lod_log(context, f"Total: {ob_tot} objects in {minutes}m {seconds}s")

        # Update final progress
        update_lod_progress(context, task="Completed!",
                          current_obj=ob_tot, total_obj=ob_tot,
                          current_lod=LODnum, total_lod=LODnum,
                          elapsed=end_time)

        # Keep progress visible for review but mark as inactive
        context.scene.lod_progress_active = False

        return {'FINISHED'}

def rimuovi_prefisso_ob(stringa):
    if stringa.startswith("OB_"):
        return stringa[3:]
    return stringa

#_______________________________________________________________________________________________

class OBJECT_OT_ExportGroupsLOD(bpy.types.Operator):
    """LOD cluster(s) export to FBX"""
    bl_idname = "exportfbx.grouplod"
    bl_label = "Export Group LOD"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        start_time = time.time()
        if bpy.context.scene.model_export_dir:
            basedir = bpy.path.abspath(os.path.dirname(bpy.context.scene.model_export_dir))
            subfolder = ''
        else:
            basedir = bpy.path.abspath(os.path.dirname(bpy.data.filepath))
            subfolder = 'FBX'
        if not basedir:
            raise Exception("Blend file is not saved")
        ob_counter = 1
        scene = context.scene
        listobjects = context.selected_objects
        for obj in listobjects:
            if obj.type == 'EMPTY':
                if obj.get('fbx_type') is not None:
                    print('Found LOD cluster to export: "' + obj.name + '", object')
                    bpy.ops.object.select_all(action='DESELECT')
                    obj.select_set(True)
                    bpy.context.view_layer.objects.active = obj
                    for ob in getChildren(obj):
                        ob.select_set(True)
                    name = bpy.path.clean_name(obj.name)
                    fn = os.path.join(basedir, name)
                    bpy.ops.export_scene.fbx(filepath= fn + ".fbx", check_existing=True, axis_forward='-Z', axis_up='Y', filter_glob="*.fbx", use_selection=True, global_scale=1.0, apply_unit_scale=True, bake_space_transform=False, object_types={'ARMATURE', 'CAMERA', 'EMPTY', 'LIGHT', 'MESH', 'OTHER'}, use_mesh_modifiers=True, mesh_smooth_type='EDGE', use_mesh_edges=False, use_tspace=False, use_custom_props=False, add_leaf_bones=True, primary_bone_axis='Y', secondary_bone_axis='X', use_armature_deform_only=False, bake_anim=True, bake_anim_use_all_bones=True, bake_anim_use_nla_strips=True, bake_anim_use_all_actions=True, bake_anim_force_startend_keying=True, bake_anim_step=1.0, bake_anim_simplify_factor=1.0, path_mode='RELATIVE', embed_textures=False, batch_mode='OFF', use_batch_own_dir=True, use_metadata=True)
                else:
                    print('The "' + obj.name + '" empty object has not the correct settings to export an FBX - LOD enabled file. I will skip it.')
                    obj.select_set(False)
                    print('>>> Object number ' + str(ob_counter) + ' processed in ' + str(time.time() - start_time) + ' seconds')
                    ob_counter += 1
        end_time = time.time() - start_time
        print('<<<<<<< Process done >>>>>>')
        print('>>>' + str(ob_counter) + ' objects processed in ' + str(end_time) + ' seconds')
        return {'FINISHED'}

#_______________________________________________________________

class OBJECT_OT_RemoveGroupsLOD(bpy.types.Operator):
    """Removes LOD cluster(s)"""
    bl_idname = "remove.grouplod"
    bl_label = "Remove Group LOD"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        listobjects = bpy.context.selected_objects
        bpy.ops.object.select_all(action='DESELECT')
        for obj in listobjects:
            if obj.get('fbx_type') is not None:
                obj.select_set(True)
                bpy.context.view_layer.objects.active = obj
                for ob in getChildren(obj):
                    ob.select_set(True)
                bpy.ops.object.parent_clear(type='CLEAR_KEEP_TRANSFORM')
                bpy.ops.object.select_all(action='DESELECT')
                obj.select_set(True)
                bpy.context.view_layer.objects.active = obj
                bpy.ops.object.delete()
        return {'FINISHED'}

#_______________________________________________________________

class OBJECT_OT_CreateGroupsLOD(bpy.types.Operator):
    """Creates LOD cluster(s): empty objects with nested LODs"""
    bl_idname = "create.grouplod"
    bl_label = "Create Group LOD"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        listobjects = bpy.context.selected_objects
        for obj in listobjects:
            bpy.ops.object.select_all(action='DESELECT')
            obj.select_set(True)
            bpy.context.view_layer.objects.active = obj
            baseobjwithlod = obj.name
            if '_LOD0' in baseobjwithlod:
                baseobj = baseobjwithlod.replace("_LOD0", "")
                print('Found LOD0 object:' + baseobjwithlod)
                local_bbox_center = 0.125 * sum((Vector(b) for b in obj.bound_box), Vector())
                global_bbox_center = obj.matrix_world @ local_bbox_center
                emptyofname = 'GLOD_' + baseobj
                obempty = bpy.data.objects.new(emptyofname, None)
                bpy.context.collection.objects.link(obempty)
                obempty.empty_display_size = 2
                obempty.empty_display_type = 'PLAIN_AXES'
                obempty.location = global_bbox_center
                bpy.ops.object.select_all(action='DESELECT')
                obempty.select_set(True)
                bpy.context.view_layer.objects.active = obempty
                obempty['fbx_type'] = 'LodGroup'
                num = 0
                child = selectLOD(listobjects, num, baseobj)
                print(child)
                print(baseobj)
                print(str(num))
                while child is not None:
                    child.parent = obempty
                    child.matrix_parent_inverse = obempty.matrix_world.inverted()
                    num += 1
                    print(str(num))
                    child = selectLOD(listobjects, num, baseobj)
        return {'FINISHED'}

class OBJECT_OT_changeLOD(bpy.types.Operator):
    """Change LOD for selected objs"""
    bl_idname = "change.lod"
    bl_label = "Change LOD"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        context = bpy.context
        scene = context.scene
        lod_list_clear(context) 
        LOD_target = "LOD" + str(context.scene.setLODnum)
        selection = bpy.context.selected_objects
        LODS = ["LOD0", "LOD1", "LOD2", "LOD3", "LOD4", "LOD5"]
        librerie = []
        lod_list_item_counter = 0
        for objs_to_check in selection:
            current_obj_LOD = objs_to_check.name[-4:]
            if current_obj_LOD == LOD_target or current_obj_LOD not in LODS:
                pass
            else:
                if objs_to_check.library is not None:
                    if objs_to_check.library.name not in librerie:
                        librerie.append(objs_to_check.library.name)
                    scene.lod_list_item.add()
                    scene.lod_list_item[lod_list_item_counter].name = objs_to_check.name
                    scene.lod_list_item[lod_list_item_counter].libreria_lod = objs_to_check.library.name
                    lod_list_item_counter += 1
        for libreria in librerie:
            library_path = bpy.data.libraries[libreria].filepath
            with bpy.data.libraries.load(library_path, link=True) as (data_from, data_to):
                data_to.objects = [name for name in data_from.objects if name.endswith(LOD_target)]
            for object_in_lod_list in scene.lod_list_item:
                if object_in_lod_list.libreria_lod == libreria:
                    current_LOD = object_in_lod_list.name[-4:]
                    target_name = object_in_lod_list.name.replace(current_LOD, LOD_target)
                    found = False
                    for object_in_library in data_to.objects:
                        if object_in_library.name == target_name:
                            found = True
                            # === FIX PER COLLEZIONI ANNIDATE MIGLIORATO ===
                            collection_list_for_current_ob = []
                            for collection in bpy.data.collections:
                                # Usa objects (non all_objects) per controllare solo gli oggetti direttamente nella collezione
                                if object_in_lod_list.name in [obj.name for obj in collection.objects]:
                                    collection_list_for_current_ob.append(collection.name)

                            # Gestisci il linking/unlinking con controllo errori
                            for relevant_collection in collection_list_for_current_ob:
                                try:
                                    # Link il nuovo oggetto alla collezione
                                    bpy.data.collections[relevant_collection].objects.link(bpy.data.objects[target_name])
                                    # Unlink l'oggetto vecchio dalle collezioni che lo contengono direttamente
                                    bpy.data.collections[relevant_collection].objects.unlink(bpy.data.objects[object_in_lod_list.name])
                                except RuntimeError as e:
                                    print(f"Warning: Could not process collection '{relevant_collection}': {e}")
                                    continue
                    if not found:
                        object_clean_name = target_name[:-5]
                        print('The object "' + object_clean_name + '" has no ' + LOD_target + " in library")
        return {'FINISHED'}

class OBJECT_OT_changemeshLOD(bpy.types.Operator):
    """Change LOD for selected objects with linked meshes and update object names (CTRL+SHIFT+ALT+0-4)"""
    bl_idname = "object.change_lod"
    bl_label = "Change LOD"
    bl_options = {"REGISTER", "UNDO"}

    LODS = ["LOD0", "LOD1", "LOD2", "LOD3", "LOD4", "LOD5"]

    def execute(self, context):
        scene = context.scene
        LOD_target = f"LOD{scene.setLODnum}"
        selection = context.selected_objects
        libraries = {obj.data.library.name for obj in selection if obj.type == 'MESH' and obj.data.library}
        for lib_name in libraries:
            self.process_library(lib_name, LOD_target, selection)
        return {'FINISHED'}

    def process_library(self, lib_name, LOD_target, selection):
        library = bpy.data.libraries[lib_name]
        with bpy.data.libraries.load(library.filepath, link=True) as (data_from, data_to):
            data_to.meshes = [name for name in data_from.meshes if name.endswith(LOD_target)]
        for obj in selection:
            if obj.type == 'MESH' and obj.data.library and obj.data.library.name == lib_name:
                current_mesh_name = obj.data.name
                current_LOD = current_mesh_name[-4:]
                if current_LOD in self.LODS and current_LOD != LOD_target:
                    target_mesh_name = current_mesh_name.replace(current_LOD, LOD_target)
                    self.replace_mesh_and_rename_object(obj, target_mesh_name)

    def replace_mesh_and_rename_object(self, obj, target_mesh_name):
        if target_mesh_name in bpy.data.meshes:
            obj.data = bpy.data.meshes[target_mesh_name]
            obj.name = target_mesh_name
            self.report({'INFO'}, f"Object and mesh updated to {target_mesh_name}")
        else:
            self.report({'WARNING'}, f"Mesh {target_mesh_name} not found in library")

    @classmethod
    def poll(cls, context):
        return context.selected_objects and any(obj.type == 'MESH' and obj.data.library for obj in context.selected_objects)

class OBJECT_OT_open_linked_file(bpy.types.Operator):
    """Open the .blend file containing the linked mesh or object of the active object in a new Blender instance"""
    bl_idname = "object.open_linked_file"
    bl_label = "Open Linked File in New Instance"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj and (obj.library or (obj.data and obj.data.library))

    def execute(self, context):
        obj = context.active_object
        if obj.library:
            linked_file = obj.library.filepath
        elif obj.data and obj.data.library:
            linked_file = obj.data.library.filepath
        else:
            self.report({'ERROR'}, "No linked file found for the active object.")
            return {'CANCELLED'}
        linked_file = bpy.path.abspath(linked_file)
        if not os.path.exists(linked_file):
            self.report({'ERROR'}, f"Linked file not found: {linked_file}")
            return {'CANCELLED'}
        blender_exe = bpy.app.binary_path
        try:
            subprocess.Popen([blender_exe, linked_file])
            self.report({'INFO'}, f"Opened linked file in new Blender instance: {linked_file}")
        except Exception as e:
            self.report({'ERROR'}, f"Failed to open new Blender instance: {str(e)}")
            return {'CANCELLED'}
        return {'FINISHED'}

class ToolsPanelLODmanager:
    bl_label = "LOD Manager"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        layout = self.layout
        scene = context.scene

        row = layout.row()
        row.label(text="Change LOD of selected linked objects:")
        row = layout.row()
        split = layout.split()
        col = split.column()
        col.prop(scene, 'setLODnum', icon='BLENDER', toggle=True)
        col = split.column(align=True)
        col.operator("change.lod", text='Set Object LOD')
        col = split.column(align=True)
        col.operator("object.change_lod", text='Set Mesh LOD')
        row = layout.row()
        row.operator("object.open_linked_file", text='Open Linked Source')

class ToolsPanelLODgenerator:
    bl_label = "LOD Generator"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        layout = self.layout
        scene = context.scene

        # Progress information box
        if scene.lod_progress_active:
            box = layout.box()
            box.label(text="LOD Generation Progress", icon='TIME')

            col = box.column(align=True)

            # Current task
            if scene.lod_progress_current_task:
                col.label(text=f"Task: {scene.lod_progress_current_task}")

            # LOD progress
            if scene.lod_progress_total_lods > 0:
                col.label(text=f"LOD: {scene.lod_progress_current_lod}/{scene.lod_progress_total_lods}")

            # Object progress
            if scene.lod_progress_total_objects > 0:
                col.label(text=f"Object: {scene.lod_progress_current_object}/{scene.lod_progress_total_objects}")

            # Elapsed time
            if scene.lod_progress_elapsed_time > 0:
                elapsed_minutes = int(scene.lod_progress_elapsed_time // 60)
                elapsed_seconds = int(scene.lod_progress_elapsed_time % 60)
                col.label(text=f"Elapsed: {elapsed_minutes}m {elapsed_seconds}s")

            col.separator()

        # Recent operations log box (collapsible)
        if scene.lod_progress_log:
            box = layout.box()
            row = box.row()
            row.label(text="Recent Operations", icon='TEXT')

            log_lines = scene.lod_progress_log.split('\n')
            # Show last 5 log entries
            for line in log_lines[-5:]:
                if line.strip():
                    box.label(text=line)

        if context.object:
            step1_box = layout.box()
            step1_box.label(text="Step 1 - Data Preparation", icon='MODIFIER')
            step1_box.label(text="Prepare selected meshes as LOD0 source objects.")
            step1_box.operator("lod0.creation", icon="MESH_UVSPHERE", text='Set as LOD0')

            step2_box = layout.box()
            step2_box.label(text="Step 2 - Presets & Settings", icon='PREFERENCES')

            # Macro section A: workflow preset
            workflow_macro = step2_box.box()
            workflow_macro.label(text="Macro A - Workflow Preset", icon='PRESET')
            workflow_macro.prop(scene, "lod_workflow_preset", text="Workflow")

            # Macro section B: LOD settings preset
            preset_macro = step2_box.box()
            preset_macro.label(text="Macro B - LOD Settings Preset", icon='PRESET')
            preset_row = preset_macro.row(align=True)
            prefs = _get_addon_preferences(context)
            if prefs is None:
                preset_row.label(text="Preset: unavailable", icon='ERROR')
            else:
                active_preset = _get_active_preset(prefs)
                active_name = active_preset.name if active_preset else LOD_BASE_PRESET_NAME
                preset_row.menu("LOD_MT_presets_menu", text=f"Preset: {active_name}", icon='DOWNARROW_HLT')
                preset_row.operator("lod.preset_apply", text="Apply", icon='IMPORT')

            options_box = step2_box.box()
            options_box.label(text="Bake & Material Options", icon='MATERIAL')
            top_opts_row = options_box.row(align=True)
            top_opts_row.prop(scene, 'LOD_pad_on', text="UV Pad")
            top_opts_row.prop(scene, 'decimate_borders', text="Preserve Borders")
            top_opts_row.prop(scene, 'LOD_use_scene_settings', text="Use Scene Lighting")

            uv_row = options_box.row(align=True)
            uv_row.prop(scene, "atlas_uv_recalc", text="Recalculate Atlas UV")
            if scene.atlas_uv_recalc:
                uv_row.prop(scene, "atlas_uv_algorithm", text="Algorithm")

            tex_row = options_box.row(align=True)
            tex_row.prop(scene, "texture_format", text="Texture Format")
            if scene.texture_format == 'PNG':
                tex_row.prop(scene, "use_alpha", text="Use Alpha Channel")

            normal_row = options_box.row(align=True)
            normal_row.prop(scene, "lod_generate_normal_maps", text="Generate Normal Maps")
            if workflow_uses_normal_maps(scene):
                normal_row.prop(scene, "lod_normal_map_max_level", text="Max LOD")

            alpha_row = options_box.row(align=True)
            alpha_row.label(text="Alpha:")
            alpha_row.prop(scene, "lod_auto_preserve_alpha", text="Auto Preserve")
            alpha_row.prop(scene, "lod_ignore_source_alpha", text="Ignore Source")
            if not scene.lod_ignore_source_alpha:
                alpha_row.prop(scene, "lod_alpha_mode", text="")
                if scene.lod_alpha_mode == 'CLIP':
                    alpha_row.prop(scene, "lod_alpha_clip_threshold", text="Clip")

            lod_details_box = step2_box.box()
            lod_details_box.label(text="LOD Details", icon='MOD_SIMPLIFY')
            lod_count_row = lod_details_box.row(align=True)
            lod_count_row.prop(scene, 'LODnum', icon='BLENDER', toggle=True)

            if scene.LODnum >= 1:
                row = lod_details_box.row(align=True)
                row.label(text="LOD 1")
                row.prop(scene, 'LOD1_dec_ratio', icon='BLENDER', toggle=True, text="Geometry")
                row.prop(scene, 'LOD1_tex_res', icon='BLENDER', toggle=True, text="Texture")
            if scene.LODnum >= 2:
                row = lod_details_box.row(align=True)
                row.label(text="LOD 2")
                row.prop(scene, 'LOD2_dec_ratio', icon='BLENDER', toggle=True, text="Geometry")
                row.prop(scene, 'LOD2_tex_res', icon='BLENDER', toggle=True, text="Texture")
            if scene.LODnum >= 3:
                row = lod_details_box.row(align=True)
                row.label(text="LOD 3")
                row.prop(scene, 'LOD3_dec_ratio', icon='BLENDER', toggle=True, text="Geometry")
                row.prop(scene, 'LOD3_tex_res', icon='BLENDER', toggle=True, text="Texture")
            if scene.LODnum >= 4:
                row = lod_details_box.row(align=True)
                row.label(text="LOD 4")
                row.prop(scene, 'LOD4_dec_ratio', icon='BLENDER', toggle=True, text="Geometry")
                row.prop(scene, 'LOD4_tex_res', icon='BLENDER', toggle=True, text="Texture")

            step3_box = layout.box()
            step3_box.label(text="Step 3 - Create LODs", icon='OUTLINER_OB_MESH')
            step3_box.operator("lod.creation", text='Generate LODs', icon='PLAY')

            step4_box = layout.box()
            step4_box.label(text="Step 4 - Cluster & Export", icon='EXPORT')
            cluster_row = step4_box.row(align=True)
            cluster_row.operator("create.grouplod", icon="PRESET", text='Create Clusters')
            cluster_row.operator("remove.grouplod", icon="CANCEL", text='Remove Clusters')
            export_row = step4_box.row()
            export_row.label(text="Cluster Export Folder:")
            export_row = step4_box.row()
            export_row.prop(context.scene, 'model_export_dir', toggle=True, text='Folder')
            step4_box.operator("exportfbx.grouplod", icon="MESH_GRID", text='Export FBX')


class LOD_MT_presets_menu(Menu):
    bl_idname = "LOD_MT_presets_menu"
    bl_label = "LOD Presets"

    def draw(self, context):
        layout = self.layout
        prefs = _get_addon_preferences(context)
        if prefs is None:
            layout.label(text="Addon preferences unavailable", icon='ERROR')
            return

        active_preset = _get_active_preset(prefs)
        active_name = active_preset.name if active_preset else LOD_BASE_PRESET_NAME

        layout.label(text="Select Preset", icon='PRESET')
        for preset in prefs.lod_presets:
            icon = 'CHECKMARK' if preset.name == active_name else 'BLANK1'
            op = layout.operator("lod.preset_set_active", text=preset.name, icon=icon)
            op.preset_name = preset.name

        layout.separator()
        layout.label(text="Actions", icon='PREFERENCES')
        layout.operator("lod.preset_apply", icon='IMPORT')
        layout.operator("lod.preset_save_current_as_new", icon='ADD')
        layout.operator("lod.preset_overwrite_active", icon='FILE_TICK')
        layout.operator("lod.preset_rename_active", icon='GREASEPENCIL')
        layout.operator("lod.preset_duplicate_active", icon='DUPLICATE')

        delete_row = layout.row()
        delete_row.enabled = active_name != LOD_BASE_PRESET_NAME
        delete_row.operator("lod.preset_delete_active", icon='TRASH')


class OBJECT_OT_lod_preset_set_active(Operator):
    bl_idname = "lod.preset_set_active"
    bl_label = "Set Active LOD Preset"
    bl_options = {"INTERNAL"}

    preset_name: bpy.props.StringProperty(name="Preset") # type: ignore

    def execute(self, context):
        prefs = _get_addon_preferences(context)
        if prefs is None:
            self.report({'ERROR'}, "Cannot access addon preferences")
            return {'CANCELLED'}
        preset = _find_preset_by_name(prefs, self.preset_name)
        if preset is None:
            self.report({'ERROR'}, f'Preset "{self.preset_name}" not found')
            return {'CANCELLED'}
        prefs.lod_active_preset = preset.name
        bpy.ops.wm.save_userpref()
        self.report({'INFO'}, f'Active preset: {preset.name}')
        return {'FINISHED'}


class OBJECT_OT_lod_preset_apply(Operator):
    bl_idname = "lod.preset_apply"
    bl_label = "Apply Active to Scene"
    bl_description = "Apply active LOD preset to current scene"

    def execute(self, context):
        prefs = _get_addon_preferences(context)
        if prefs is None:
            self.report({'ERROR'}, "Cannot access addon preferences")
            return {'CANCELLED'}
        preset = _get_active_preset(prefs)
        if preset is None:
            self.report({'ERROR'}, "No active preset available")
            return {'CANCELLED'}
        _copy_preset_to_scene(context.scene, preset)
        self.report({'INFO'}, f'Preset "{preset.name}" applied')
        return {'FINISHED'}


class OBJECT_OT_lod_preset_save_current_as_new(Operator):
    bl_idname = "lod.preset_save_current_as_new"
    bl_label = "Save Current as New..."
    bl_description = "Create a new named LOD preset from current scene settings"

    preset_name: bpy.props.StringProperty(name="Preset Name", default="Preset") # type: ignore

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)

    def draw(self, context):
        self.layout.prop(self, "preset_name")

    def execute(self, context):
        prefs = _get_addon_preferences(context)
        if prefs is None:
            self.report({'ERROR'}, "Cannot access addon preferences")
            return {'CANCELLED'}

        unique_name = _make_unique_preset_name(prefs, self.preset_name)
        new_preset = prefs.lod_presets.add()
        new_preset.name = unique_name
        _copy_scene_to_preset(context.scene, new_preset)
        prefs.lod_active_preset = new_preset.name
        bpy.ops.wm.save_userpref()
        self.report({'INFO'}, f'Preset "{new_preset.name}" created')
        return {'FINISHED'}


class OBJECT_OT_lod_preset_overwrite_active(Operator):
    bl_idname = "lod.preset_overwrite_active"
    bl_label = "Overwrite Active"
    bl_description = "Overwrite active preset with current scene settings"

    def execute(self, context):
        prefs = _get_addon_preferences(context)
        if prefs is None:
            self.report({'ERROR'}, "Cannot access addon preferences")
            return {'CANCELLED'}
        preset = _get_active_preset(prefs)
        if preset is None:
            self.report({'ERROR'}, "No active preset available")
            return {'CANCELLED'}
        _copy_scene_to_preset(context.scene, preset)
        bpy.ops.wm.save_userpref()
        self.report({'INFO'}, f'Preset "{preset.name}" updated')
        return {'FINISHED'}


class OBJECT_OT_lod_preset_rename_active(Operator):
    bl_idname = "lod.preset_rename_active"
    bl_label = "Rename Active..."
    bl_description = "Rename active LOD preset"

    new_name: bpy.props.StringProperty(name="New Name", default="Preset") # type: ignore

    def invoke(self, context, event):
        prefs = _get_addon_preferences(context)
        if prefs is None:
            return {'CANCELLED'}
        preset = _get_active_preset(prefs)
        if preset is not None:
            self.new_name = preset.name
        return context.window_manager.invoke_props_dialog(self)

    def draw(self, context):
        self.layout.prop(self, "new_name")

    def execute(self, context):
        prefs = _get_addon_preferences(context)
        if prefs is None:
            self.report({'ERROR'}, "Cannot access addon preferences")
            return {'CANCELLED'}
        preset = _get_active_preset(prefs)
        if preset is None:
            self.report({'ERROR'}, "No active preset available")
            return {'CANCELLED'}
        if preset.name == LOD_BASE_PRESET_NAME:
            self.report({'WARNING'}, 'Preset "Base" cannot be renamed')
            return {'CANCELLED'}

        unique_name = _make_unique_preset_name(prefs, self.new_name)
        old_name = preset.name
        preset.name = unique_name
        prefs.lod_active_preset = unique_name
        bpy.ops.wm.save_userpref()
        self.report({'INFO'}, f'Preset "{old_name}" renamed to "{unique_name}"')
        return {'FINISHED'}


class OBJECT_OT_lod_preset_duplicate_active(Operator):
    bl_idname = "lod.preset_duplicate_active"
    bl_label = "Duplicate Active"
    bl_description = "Duplicate active LOD preset"

    def execute(self, context):
        prefs = _get_addon_preferences(context)
        if prefs is None:
            self.report({'ERROR'}, "Cannot access addon preferences")
            return {'CANCELLED'}
        preset = _get_active_preset(prefs)
        if preset is None:
            self.report({'ERROR'}, "No active preset available")
            return {'CANCELLED'}

        new_name = _make_unique_preset_name(prefs, preset.name)
        new_preset = prefs.lod_presets.add()
        new_preset.name = new_name

        new_preset.lod_num = preset.lod_num
        new_preset.lod1_dec_ratio = preset.lod1_dec_ratio
        new_preset.lod2_dec_ratio = preset.lod2_dec_ratio
        new_preset.lod3_dec_ratio = preset.lod3_dec_ratio
        new_preset.lod4_dec_ratio = preset.lod4_dec_ratio
        new_preset.lod1_tex_res = preset.lod1_tex_res
        new_preset.lod2_tex_res = preset.lod2_tex_res
        new_preset.lod3_tex_res = preset.lod3_tex_res
        new_preset.lod4_tex_res = preset.lod4_tex_res
        new_preset.lod_workflow_preset = preset.lod_workflow_preset
        new_preset.lod_generate_normal_maps = preset.lod_generate_normal_maps
        new_preset.lod_normal_map_max_level = preset.lod_normal_map_max_level
        new_preset.lod_auto_preserve_alpha = preset.lod_auto_preserve_alpha
        new_preset.lod_ignore_source_alpha = preset.lod_ignore_source_alpha
        new_preset.lod_alpha_mode = preset.lod_alpha_mode
        new_preset.lod_alpha_clip_threshold = preset.lod_alpha_clip_threshold
        new_preset.lod_pad_on = preset.lod_pad_on
        new_preset.lod_use_scene_settings = preset.lod_use_scene_settings
        new_preset.lod_atlas_uv_recalc = preset.lod_atlas_uv_recalc
        new_preset.lod_atlas_uv_algorithm = preset.lod_atlas_uv_algorithm
        new_preset.lod_texture_format = preset.lod_texture_format
        new_preset.lod_use_alpha = preset.lod_use_alpha
        new_preset.lod_decimate_borders = preset.lod_decimate_borders

        prefs.lod_active_preset = new_preset.name
        bpy.ops.wm.save_userpref()
        self.report({'INFO'}, f'Preset duplicated as "{new_preset.name}"')
        return {'FINISHED'}


class OBJECT_OT_lod_preset_delete_active(Operator):
    bl_idname = "lod.preset_delete_active"
    bl_label = "Delete Active"
    bl_description = "Delete active LOD preset"

    def invoke(self, context, event):
        return context.window_manager.invoke_confirm(self, event)

    def execute(self, context):
        prefs = _get_addon_preferences(context)
        if prefs is None:
            self.report({'ERROR'}, "Cannot access addon preferences")
            return {'CANCELLED'}
        preset = _get_active_preset(prefs)
        if preset is None:
            self.report({'ERROR'}, "No active preset available")
            return {'CANCELLED'}
        if preset.name == LOD_BASE_PRESET_NAME:
            self.report({'WARNING'}, 'Preset "Base" cannot be deleted')
            return {'CANCELLED'}

        idx_to_remove = None
        for idx, item in enumerate(prefs.lod_presets):
            if item.name == preset.name:
                idx_to_remove = idx
                break

        if idx_to_remove is None:
            self.report({'ERROR'}, "Preset index not found")
            return {'CANCELLED'}

        removed_name = preset.name
        prefs.lod_presets.remove(idx_to_remove)
        _ensure_base_preset(prefs)
        prefs.lod_active_preset = LOD_BASE_PRESET_NAME
        bpy.ops.wm.save_userpref()
        self.report({'INFO'}, f'Preset "{removed_name}" deleted')
        return {'FINISHED'}


@bpy.app.handlers.persistent
def load_lod_defaults(dummy):
    """Auto-load LOD defaults from AddonPreferences when opening a new file."""
    try:
        context = bpy.context
        scene = context.scene
        if scene is None:
            return
        prefs = _get_addon_preferences(context)
        if prefs is None:
            return
        preset = _get_active_preset(prefs)
        if preset is not None:
            _copy_preset_to_scene(scene, preset)
    except Exception:
        pass


class VIEW3D_PT_LODgenerator(Panel, ToolsPanelLODgenerator):
    bl_category = "3DSC"
    bl_idname = "VIEW3D_PT_LODgenerator"
    bl_context = "objectmode"

class VIEW3D_PT_LODmanager(Panel, ToolsPanelLODmanager):
    bl_category = "3DSC"
    bl_idname = "VIEW3D_PT_LODmanager"
    bl_context = "objectmode"

classes = [
    OBJECT_OT_changemeshLOD,
    OBJECT_OT_changeLOD,
    OBJECT_OT_CreateGroupsLOD,
    OBJECT_OT_RemoveGroupsLOD,
    OBJECT_OT_ExportGroupsLOD,
    OBJECT_OT_LOD,
    OBJECT_OT_LOD0,
    LOD_MT_presets_menu,
    OBJECT_OT_lod_preset_set_active,
    OBJECT_OT_lod_preset_apply,
    OBJECT_OT_lod_preset_save_current_as_new,
    OBJECT_OT_lod_preset_overwrite_active,
    OBJECT_OT_lod_preset_rename_active,
    OBJECT_OT_lod_preset_duplicate_active,
    OBJECT_OT_lod_preset_delete_active,
    VIEW3D_PT_LODgenerator,
    VIEW3D_PT_LODmanager,
    OBJECT_OT_open_linked_file
]

def register():
    for cls in classes:
        bpy.utils.register_class(cls)

    # Register auto-load handler for LOD defaults
    if load_lod_defaults not in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.append(load_lod_defaults)

    bpy.types.Scene.setLODnum = bpy.props.IntProperty(name="LOD Level", default=0, min=0, max=5)
    bpy.types.Scene.LODnum = bpy.props.IntProperty(
        name="LODs",
        default=1,
        min=1,
        max=5,
        description="Enter desired number of LOD (Level of Detail)"
    )
    bpy.types.Scene.LOD1_tex_res = bpy.props.IntProperty(
        name="Resolution Texture of the LOD1",
        default=2048,
        description="Enter the resolution for the texture of the LOD1"
    )
    bpy.types.Scene.LOD2_tex_res = bpy.props.IntProperty(
        name="Resolution Texture of the LOD2",
        default=512,
        description="Enter the resolution for the texture of the LOD2"
    )
    bpy.types.Scene.LOD3_tex_res = bpy.props.IntProperty(
        name="Resolution Texture of the LOD3",
        default=128,
        description="Enter the resolution for the texture of the LOD3"
    )
    bpy.types.Scene.LOD4_tex_res = bpy.props.IntProperty(
        name="Resolution Texture of the LOD4",
        default=64,
        description="Enter the resolution for the texture of the LOD4"
    )
    bpy.types.Scene.LOD_pad_on = bpy.props.BoolProperty(
        name="Padding ratio of the LOD",
        default=True,
        description="Enter the padding ratio for the LOD"
    )
    bpy.types.Scene.LOD_use_scene_settings = bpy.props.BoolProperty(
        name="Using scene settings for bake LOD",
        default=False,
        description="Use scene bake settings for the LOD"
    )
    bpy.types.Scene.lod_workflow_preset = bpy.props.EnumProperty(
        name="LOD Workflow Preset",
        items=[
            ('CLASSIC', "Classic LOD", "Classic LOD generation"),
            ('CLASSIC_NORMAL', "Classic LOD + Normal Maps", "Classic LOD generation with normal maps"),
            ('VEGETATION_ALPHA', "Vegetation Alpha Clip", "LOD workflow for vegetation/foliage alpha materials"),
            ('CESIUM_ATLAS', "LOD0 Atlas Bake (Cesium)", "Prepare a LOD0 atlas for Cesium export")
        ],
        default='CLASSIC',
        update=on_lod_workflow_preset_update,
        description="Preset workflow for LOD generation"
    )
    bpy.types.Scene.lod_generate_normal_maps = bpy.props.BoolProperty(
        name="Generate Normal Maps",
        default=False,
        description="Bake normal maps from LOD0 down to lower LOD levels"
    )
    bpy.types.Scene.lod_normal_map_max_level = bpy.props.IntProperty(
        name="Normal Map Max LOD",
        default=2,
        min=1,
        max=5,
        description="Generate normal maps up to this LOD level"
    )
    bpy.types.Scene.lod_auto_preserve_alpha = bpy.props.BoolProperty(
        name="Auto Preserve Source Alpha",
        default=False,
        description="Detect alpha in source textures and preserve it in baked textures"
    )
    bpy.types.Scene.lod_ignore_source_alpha = bpy.props.BoolProperty(
        name="Ignore Source Alpha",
        default=False,
        description="Ignore alpha detected in source textures"
    )
    bpy.types.Scene.lod_alpha_mode = bpy.props.EnumProperty(
        name="Alpha Mode",
        items=[('BLEND', "Blend", ""), ('CLIP', "Clip", "")],
        default='BLEND',
        description="Alpha mode for generated materials (glTF compatible)"
    )
    bpy.types.Scene.lod_alpha_clip_threshold = bpy.props.FloatProperty(
        name="Alpha Clip Threshold",
        default=0.5,
        min=0.0,
        max=1.0,
        description="Alpha threshold used when alpha mode is Clip"
    )
    # Nuove proprietà per il ricalcolo UV Atlas
    bpy.types.Scene.atlas_uv_recalc = bpy.props.BoolProperty(
        name="Recalculate Atlas UV", default=False,
        description="If enabled, recalculate the Atlas UV mapping"
    )
    bpy.types.Scene.atlas_uv_algorithm = bpy.props.EnumProperty(
        name="UV Algorithm",
        items=[
            ('SMART', "Smart UV (Faster)", ""),
            ('ANGLE', "Angle Based", ""),
            ('CONFORMAL', "Conformal", ""),
            ('MINIMUM', "Minimum Stretch", "")
        ],
        default='SMART',
        description="Select the UV mapping algorithm for the Atlas"
    )
    # Nuove proprietà per il formato texture
    bpy.types.Scene.texture_format = bpy.props.EnumProperty(
        name="Texture Format",
        items=[('JPG', "JPG", ""), ('PNG', "PNG", "")],
        default='JPG',
        description="Choose texture file format"
    )
    bpy.types.Scene.use_alpha = bpy.props.BoolProperty(
        name="Use Alpha", default=False,
        description="If enabled, PNG textures will include an alpha channel"
    )
    bpy.types.Scene.decimate_borders = bpy.props.BoolProperty(
        name="Preserve borders",
        default=False,
        description="If disabled it will not preserve the borders of the mesh"
    )

    # Progress tracking properties
    bpy.types.Scene.lod_progress_active = bpy.props.BoolProperty(
        name="LOD Generation Active",
        default=False,
        description="Indicates if LOD generation is currently running"
    )
    bpy.types.Scene.lod_progress_current_task = bpy.props.StringProperty(
        name="Current Task",
        default="",
        description="Description of current task being executed"
    )
    bpy.types.Scene.lod_progress_current_object = bpy.props.IntProperty(
        name="Current Object",
        default=0,
        description="Index of current object being processed"
    )
    bpy.types.Scene.lod_progress_total_objects = bpy.props.IntProperty(
        name="Total Objects",
        default=0,
        description="Total number of objects to process"
    )
    bpy.types.Scene.lod_progress_current_lod = bpy.props.IntProperty(
        name="Current LOD",
        default=0,
        description="Current LOD level being generated"
    )
    bpy.types.Scene.lod_progress_total_lods = bpy.props.IntProperty(
        name="Total LODs",
        default=0,
        description="Total number of LOD levels to generate"
    )
    bpy.types.Scene.lod_progress_elapsed_time = bpy.props.FloatProperty(
        name="Elapsed Time",
        default=0.0,
        description="Time elapsed since start of LOD generation"
    )
    bpy.types.Scene.lod_progress_log = bpy.props.StringProperty(
        name="Progress Log",
        default="",
        description="Log of completed operations"
    )

    # Apply saved defaults immediately after enabling the addon.
    load_lod_defaults(None)

def unregister():
    # Remove auto-load handler
    if load_lod_defaults in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(load_lod_defaults)

    for cls in classes:
        bpy.utils.unregister_class(cls)
    del bpy.types.Scene.setLODnum
    del bpy.types.Scene.LODnum
    del bpy.types.Scene.LOD1_tex_res
    del bpy.types.Scene.LOD2_tex_res
    del bpy.types.Scene.LOD3_tex_res
    del bpy.types.Scene.LOD4_tex_res
    del bpy.types.Scene.LOD1_dec_ratio
    del bpy.types.Scene.LOD2_dec_ratio
    del bpy.types.Scene.LOD3_dec_ratio
    del bpy.types.Scene.LOD4_dec_ratio
    del bpy.types.Scene.LOD_pad_on
    del bpy.types.Scene.LOD_use_scene_settings
    del bpy.types.Scene.lod_workflow_preset
    del bpy.types.Scene.lod_generate_normal_maps
    del bpy.types.Scene.lod_normal_map_max_level
    del bpy.types.Scene.lod_auto_preserve_alpha
    del bpy.types.Scene.lod_ignore_source_alpha
    del bpy.types.Scene.lod_alpha_mode
    del bpy.types.Scene.lod_alpha_clip_threshold
    del bpy.types.Scene.atlas_uv_recalc
    del bpy.types.Scene.atlas_uv_algorithm
    del bpy.types.Scene.texture_format
    del bpy.types.Scene.use_alpha
    del bpy.types.Scene.decimate_borders
    # Progress tracking properties
    del bpy.types.Scene.lod_progress_active
    del bpy.types.Scene.lod_progress_current_task
    del bpy.types.Scene.lod_progress_current_object
    del bpy.types.Scene.lod_progress_total_objects
    del bpy.types.Scene.lod_progress_current_lod
    del bpy.types.Scene.lod_progress_total_lods
    del bpy.types.Scene.lod_progress_elapsed_time
    del bpy.types.Scene.lod_progress_log

if __name__ == "__main__":
    register()
