# -*- coding: utf-8 -*-
"""3DSC — import of GPR depth-slice stacks (georadar).

Representation
--------------
A depth slice is a **textured plane**, not a point cloud and not a volume.
The reason is in the data: the CS07 Tivoli slices are complete regular grids
(1492 x 1474 cells at 5 cm), i.e. rasters that happen to be written out as
CSV. One plane plus one 2D texture costs 4 vertices and ~1 MB on disk, where
the same slice as a mesh would cost 2.2 million vertices; 40 of them would
cost 88 million. The 40% of cells with no amplitude (outside the surveyed
polygon) become alpha 0 in the texture, so the irregular footprint of the
survey is free instead of needing explicit culling.

The intermediate form is a PNG stack plus a JSON manifest, which is also the
form the UA Ilici GEORRADAR sectors already ship in — so the CSV reader and
the image reader converge on one representation.

Semantic boundary
-----------------
This importer stops at the **documentary** level. It creates georeferenced
slices and tags them with provenance; it does not create stratigraphic units.
Turning an amplitude blob into an entity is an archaeological act, and in the
Extended Matrix it produces a USD — a documentary stratigraphic unit, the
deferred-observation category (EMWgeo v.0, Ronchi, Limongiello, Demetrescu &
Ferdani, *Sensors* 23/5, 2769, 2023). ``GPR_OT_tag_anomaly`` writes onto a
proxy the provenance an archaeologist's USD will need; it writes no node and
no edge.
"""

import json
import math
import os
import time

import bpy
from bpy.types import Operator, Panel
from bpy.props import (BoolProperty, EnumProperty, FloatProperty, IntProperty,
                       StringProperty, PointerProperty)
from bpy.types import PropertyGroup
from bpy_extras.io_utils import ImportHelper

from . import gpr_core as core

import logging
log = logging.getLogger(__name__)

STACK_ID_PROP = "gpr_stack_id"
SLICE_IDX_PROP = "gpr_slice_index"


# --------------------------------------------------------------------------
# scene state
# --------------------------------------------------------------------------

def _slice_image(ob):
    if not ob.data.materials or ob.data.materials[0] is None:
        return None
    for n in ob.data.materials[0].node_tree.nodes:
        if n.type == 'TEX_IMAGE' and n.image:
            return n.image
    return None


def _update_visible_slice(self, context):
    """Show the requested slices and drop the pixel buffers of the hidden ones.

    Blender decodes an image the first time it is drawn and then keeps it:
    the 601-slice UA Ilici stack costs 4.0 GB resident if every slice is left
    visible (measured), against ~360 MB for the scene itself. Freeing the
    buffers on the way out is what makes a deep stack usable; Blender
    re-decodes a slice in a few milliseconds when it comes back.
    """
    stack = _active_stack(context)
    if stack is None:
        return
    mode = self.slice_display
    idx = self.slice_index
    for ob in stack.children:
        if SLICE_IDX_PROP not in ob:
            continue
        i = ob[SLICE_IDX_PROP]
        if mode == 'ALL':
            vis = True
        elif mode == 'ONE':
            vis = (i == idx)
        else:  # UP_TO
            vis = (i <= idx)
        ob.hide_viewport = not vis
        ob.hide_render = not vis
        if not vis and mode != 'ALL':
            img = _slice_image(ob)
            if img is not None:
                try:
                    img.buffers_free()
                except Exception:               # noqa: BLE001
                    pass


class GPRSettings(PropertyGroup):
    stack_kind: EnumProperty(
        name="Slices are",
        items=[('CSV', "CSV grids", "One CSV per depth slice, a complete "
                                    "regular grid (CS07 CSIC-Tivoli)"),
               ('IMAGES', "Images", "Already rasterised slices, depth in the "
                                    "file name (UA Ilici GEORRADAR)")],
        default='CSV')  # type: ignore
    img_cell_size: FloatProperty(
        name="Cell size", default=0.05, min=1e-4, precision=4,
        description="Pixel size in metres, used when no world file sits "
                    "beside the images")  # type: ignore
    source_dir: StringProperty(
        name="Slice folder", subtype='DIR_PATH',
        description="Folder holding the CSV (or image) depth slices")  # type: ignore
    cache_dir: StringProperty(
        name="Cache", subtype='DIR_PATH',
        description="Where the PNG raster cache and gpr_stack.json live. "
                    "Empty = a '_3dsc_gpr_cache' folder beside the slices")  # type: ignore
    colormap: EnumProperty(
        name="Colormap",
        items=[('GRAY', "Grayscale", "High amplitude = white"),
               ('GRAY_INV', "Grayscale inverted", "High amplitude = black"),
               ('VIRIDIS', "Viridis", "Perceptually uniform colour ramp")],
        default='GRAY')  # type: ignore
    normalize: EnumProperty(
        name="Normalisation",
        items=[('STACK', "Whole stack", "One range for every slice: slices "
                                        "stay comparable with each other"),
               ('SLICE', "Per slice", "Each slice stretched to its own range: "
                                      "shows faint deep anomalies but "
                                      "misrepresents relative amplitude")],
        default='STACK')  # type: ignore
    clip_lo: FloatProperty(name="Clip low %", default=2.0, min=0.0, max=49.0)  # type: ignore
    clip_hi: FloatProperty(name="Clip high %", default=98.0, min=51.0, max=100.0)  # type: ignore
    limit: IntProperty(name="Max slices", default=0, min=0,
                       description="0 = every slice")  # type: ignore

    # georeferencing of the local survey frame
    origin_e: FloatProperty(name="Origin E", default=0.0, precision=3,
                            description="CRS easting of the local (0,0) cell")  # type: ignore
    origin_n: FloatProperty(name="Origin N", default=0.0, precision=3,
                            description="CRS northing of the local (0,0) cell")  # type: ignore
    rotation_deg: FloatProperty(name="Grid azimuth", default=0.0,
                                description="Rotation of the survey grid, "
                                            "degrees CCW from CRS east")  # type: ignore
    ground_z: FloatProperty(name="Ground Z", default=0.0, precision=3,
                            description="Absolute elevation of depth 0 "
                                        "(the surface the GPR walked on)")  # type: ignore
    use_shift: BoolProperty(
        name="Apply 3DSC shift (GSV)", default=True,
        description="Subtract the scene's General Shift Value, as every other "
                    "3DSC importer does")  # type: ignore

    slice_display: EnumProperty(
        name="Show",
        items=[('ALL', "All", "Every slice"),
               ('ONE', "One", "Only the current slice"),
               ('UP_TO', "Down to", "Every slice down to the current one")],
        default='ALL', update=_update_visible_slice)  # type: ignore
    slice_index: IntProperty(name="Slice", default=0, min=0,
                             update=_update_visible_slice)  # type: ignore
    active_stack: StringProperty(name="Active stack")  # type: ignore

    progress_text: StringProperty(name="Progress", default="")  # type: ignore


def _active_stack(context):
    name = context.scene.gpr_settings.active_stack
    ob = bpy.data.objects.get(name)
    if ob is not None:
        return ob
    ob = context.active_object
    while ob is not None:
        if STACK_ID_PROP in ob and ob.type == 'EMPTY':
            return ob
        ob = ob.parent
    return None


def _cache_dir(settings):
    src = bpy.path.abspath(settings.source_dir)
    if settings.cache_dir:
        return bpy.path.abspath(settings.cache_dir)
    return os.path.join(src, "_3dsc_gpr_cache")


# --------------------------------------------------------------------------
# cache build (modal: one slice per timer tick, the UI stays alive)
# --------------------------------------------------------------------------

class GPR_OT_build_cache(Operator):
    """Convert the CSV slice stack to a cached PNG stack + manifest"""
    bl_idname = "gpr.build_cache"
    bl_label = "Build raster cache"
    bl_options = {"REGISTER"}

    _timer = None
    _iter = None
    _manifest = None
    _t0 = 0.0

    @classmethod
    def poll(cls, context):
        return context.scene.gpr_settings.stack_kind == 'CSV' and \
            bool(context.scene.gpr_settings.source_dir)

    def execute(self, context):
        s = context.scene.gpr_settings
        src = bpy.path.abspath(s.source_dir)
        if not os.path.isdir(src):
            self.report({'ERROR'}, "Slice folder does not exist: %s" % src)
            return {'CANCELLED'}
        try:
            self._iter = core.build_cache_steps(
                src, _cache_dir(s), colormap=s.colormap, normalize=s.normalize,
                clip_lo=s.clip_lo, clip_hi=s.clip_hi, limit=s.limit)
        except Exception as exc:                     # noqa: BLE001
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}
        self._t0 = time.time()
        wm = context.window_manager
        self._timer = wm.event_timer_add(0.01, window=context.window)
        wm.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def modal(self, context, event):
        if event.type == 'ESC':
            return self._finish(context, cancelled=True)
        if event.type != 'TIMER':
            return {'PASS_THROUGH'}
        s = context.scene.gpr_settings
        try:
            i, n, name = next(self._iter)
            s.progress_text = "slice %d/%d  %s" % (i + 1, n, name)
            for area in context.screen.areas:
                area.tag_redraw()
            return {'RUNNING_MODAL'}
        except StopIteration as stop:
            self._manifest = stop.value
            return self._finish(context)
        except Exception as exc:                     # noqa: BLE001
            self.report({'ERROR'}, str(exc))
            return self._finish(context, cancelled=True)

    def _finish(self, context, cancelled=False):
        wm = context.window_manager
        if self._timer:
            wm.event_timer_remove(self._timer)
            self._timer = None
        s = context.scene.gpr_settings
        if cancelled:
            s.progress_text = "cancelled"
            return {'CANCELLED'}
        m = self._manifest or {}
        s.progress_text = ""
        self.report({'INFO'}, "GPR cache: %d slices in %.1f s (parse %.1f s)"
                    % (len(m.get("slices", [])), time.time() - self._t0,
                       m.get("parse_seconds", 0.0)))
        return {'FINISHED'}


# --------------------------------------------------------------------------
# scene building
# --------------------------------------------------------------------------

def _slice_material(name, image):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    mat.blend_method = 'BLEND'
    nt = mat.node_tree
    nt.nodes.clear()
    tex = nt.nodes.new('ShaderNodeTexImage')
    tex.image = image
    tex.interpolation = 'Closest'          # a cell is a measurement, not a blur
    tex.extension = 'CLIP'
    tex.location = (-600, 0)
    emit = nt.nodes.new('ShaderNodeEmission')
    emit.inputs['Strength'].default_value = 1.0
    emit.location = (-300, 100)
    transp = nt.nodes.new('ShaderNodeBsdfTransparent')
    transp.location = (-300, -150)
    mix = nt.nodes.new('ShaderNodeMixShader')
    mix.location = (-80, 0)
    out = nt.nodes.new('ShaderNodeOutputMaterial')
    out.location = (150, 0)
    nt.links.new(tex.outputs['Color'], emit.inputs['Color'])
    nt.links.new(tex.outputs['Alpha'], mix.inputs['Fac'])
    nt.links.new(transp.outputs['BSDF'], mix.inputs[1])
    nt.links.new(emit.outputs['Emission'], mix.inputs[2])
    nt.links.new(mix.outputs['Shader'], out.inputs['Surface'])
    return mat


def _make_plane(name, width, height, collection):
    me = bpy.data.meshes.new(name)
    hw, hh = width / 2.0, height / 2.0
    me.from_pydata([(-hw, -hh, 0), (hw, -hh, 0), (hw, hh, 0), (-hw, hh, 0)],
                   [], [(0, 1, 2, 3)])
    me.update()
    uv = me.uv_layers.new(name="UVMap")
    for i, co in enumerate([(0, 0), (1, 0), (1, 1), (0, 1)]):
        uv.data[i].uv = co
    ob = bpy.data.objects.new(name, me)
    collection.objects.link(ob)
    return ob


class GPR_OT_build_image_manifest(Operator):
    """Describe an already-rasterised slice stack, converting nothing"""
    bl_idname = "gpr.build_image_manifest"
    bl_label = "Read image stack"
    bl_options = {"REGISTER"}

    @classmethod
    def poll(cls, context):
        return context.scene.gpr_settings.stack_kind == 'IMAGES' and \
            bool(context.scene.gpr_settings.source_dir)

    def execute(self, context):
        s = context.scene.gpr_settings
        src = bpy.path.abspath(s.source_dir)
        try:
            m = core.build_image_manifest(
                src, _cache_dir(s), x_step=s.img_cell_size,
                y_step=s.img_cell_size, limit=s.limit)
        except Exception as exc:                     # noqa: BLE001
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}
        g = m["grid"]
        self.report({'INFO'}, "%d image slices, %dx%d px @ %.3f m%s"
                    % (len(m["slices"]), g["nx"], g["ny"], g["x_step"],
                       ", world file" if m.get("world_file") else ""))
        return {'FINISHED'}


class GPR_OT_import_stack(Operator):
    """Build the slice planes in the scene from the cached raster stack"""
    bl_idname = "gpr.import_stack"
    bl_label = "Import GPR stack"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return bool(context.scene.gpr_settings.source_dir)

    def execute(self, context):
        scene = context.scene
        s = scene.gpr_settings
        cache = _cache_dir(s)
        manifest = core.load_manifest(cache)
        if manifest is None:
            self.report({'ERROR'},
                        "No gpr_stack.json in %s — build the cache first" % cache)
            return {'CANCELLED'}

        g = manifest["grid"]
        width = g["nx"] * g["x_step"]
        height = g["ny"] * g["y_step"]

        # local (0,0) cell centre -> CRS -> Blender
        sx = scene.BL_x_shift if s.use_shift else 0.0
        sy = scene.BL_y_shift if s.use_shift else 0.0
        sz = scene.BL_z_shift if s.use_shift else 0.0
        ox = s.origin_e - sx
        oy = s.origin_n - sy
        theta = math.radians(s.rotation_deg)

        stack_name = os.path.basename(os.path.normpath(
            bpy.path.abspath(s.source_dir))) or "GPR"
        coll_name = "GPR_%s" % stack_name
        coll = bpy.data.collections.get(coll_name)
        if coll is None:
            coll = bpy.data.collections.new(coll_name)
            scene.collection.children.link(coll)

        root = bpy.data.objects.get(coll_name)
        if root is None:
            root = bpy.data.objects.new(coll_name, None)
            root.empty_display_type = 'PLAIN_AXES'
            root.empty_display_size = max(width, height) / 4.0
            coll.objects.link(root)
        root.location = (ox, oy, s.ground_z - sz)
        root.rotation_euler = (0.0, 0.0, theta)
        root[STACK_ID_PROP] = coll_name

        # provenance that an archaeologist's USD will point back to
        root["gpr_source_folder"] = manifest.get("source_folder", "")
        root["gpr_manifest"] = os.path.join(cache, core.MANIFEST_NAME)
        root["gpr_crs"] = "EPSG:%s" % scene.BL_epsg if scene.BL_epsg != "NotSet" else ""
        root["gpr_origin_e"] = s.origin_e
        root["gpr_origin_n"] = s.origin_n
        root["gpr_rotation_deg"] = s.rotation_deg
        root["gpr_ground_z"] = s.ground_z
        root["gpr_shift_applied"] = (sx, sy, sz)
        root["gpr_cell_size"] = (g["x_step"], g["y_step"])
        root["gpr_grid"] = (g["nx"], g["ny"])
        root["gpr_colormap"] = manifest.get("colormap", "")
        root["gpr_normalize"] = manifest.get("normalize", "")
        root["emwgeo_version"] = "0"
        root["em_interpretation_target"] = "USD"

        made = 0
        for entry in manifest["slices"]:
            ref = entry["raster"]
            img_path = ref if os.path.isabs(ref) else os.path.join(cache, ref)
            if not os.path.isfile(img_path):
                log.warning("missing raster %s", img_path)
                continue
            img = bpy.data.images.get(entry["raster"])
            if img is None or bpy.path.abspath(img.filepath) != img_path:
                img = bpy.data.images.load(img_path, check_existing=True)
            name = "%s_d%06.3f" % (coll_name, entry["depth_top"])
            ob = bpy.data.objects.get(name)
            if ob is None:
                ob = _make_plane(name, width, height, coll)
            ob.parent = root
            # the plane sits at the middle of its depth band, below ground
            ob.location = (width / 2.0 + g["x_min"] - g["x_step"] / 2.0,
                           height / 2.0 + g["y_min"] - g["y_step"] / 2.0,
                           -0.5 * (entry["depth_top"] + entry["depth_bottom"]))
            ob.data.materials.clear()
            ob.data.materials.append(
                _slice_material("%s_mat" % name, img))
            ob[SLICE_IDX_PROP] = entry["index"]
            ob["gpr_depth_top"] = entry["depth_top"]
            ob["gpr_depth_bottom"] = entry["depth_bottom"]
            ob["gpr_amplitude_range"] = (entry["vmin"], entry["vmax"])
            ob["gpr_valid_cells"] = entry["valid_cells"]
            ob["gpr_source_file"] = entry["source"]
            ob[STACK_ID_PROP] = coll_name
            made += 1

        s.active_stack = coll_name
        s.slice_index = min(s.slice_index, max(0, made - 1))
        if made > 60 and s.slice_display == 'ALL':
            # a deep stack left fully visible will decode every raster;
            # 601 Ilici slices measured at 4.0 GB resident
            s.slice_display = 'ONE'
            self.report({'WARNING'},
                        "%d slices: switched to single-slice display to keep "
                        "the texture memory bounded" % made)
        _update_visible_slice(s, context)
        self.report({'INFO'}, "GPR: %d slice planes, grid %dx%d @ %.3f m"
                    % (made, g["nx"], g["ny"], g["x_step"]))
        return {'FINISHED'}


class GPR_OT_set_source(Operator, ImportHelper):
    """Pick the folder holding the depth slices"""
    bl_idname = "gpr.set_source"
    bl_label = "Select slice folder"

    directory: StringProperty(subtype='DIR_PATH')  # type: ignore
    filter_glob: StringProperty(default="*.csv;*.CSV;*.png;*.jpg;*.tif",
                                options={'HIDDEN'})  # type: ignore

    def execute(self, context):
        context.scene.gpr_settings.source_dir = self.directory
        kind, specs = core.scan_stack(self.directory)
        if specs:
            self.report({'INFO'}, "%d %s slices, %.2f–%.2f m"
                        % (len(specs), kind, specs[0].depth_top,
                           specs[-1].depth_bottom))
        else:
            self.report({'WARNING'}, "No slices found in that folder")
        return {'FINISHED'}


# --------------------------------------------------------------------------
# the semantic hand-off — provenance only, no graph
# --------------------------------------------------------------------------

class GPR_OT_tag_anomaly(Operator):
    """Tag the selected objects as read off this GPR stack.

    Writes provenance custom properties only. Creating the stratigraphic unit
    — a USD, per EMWgeo v.0 — and wiring it into the Extended Matrix graph
    stays with the archaeologist and the EM tools: interpreting an amplitude
    blob as an entity is not something an importer is entitled to do.
    """
    bl_idname = "gpr.tag_anomaly"
    bl_label = "Tag selection as read from GPR"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return bool(context.selected_objects) and _active_stack(context)

    def execute(self, context):
        root = _active_stack(context)
        n = 0
        for ob in context.selected_objects:
            if ob is root or SLICE_IDX_PROP in ob:
                continue
            ob["em_suggested_type"] = "USD"
            ob["em_extracted_from"] = root.name
            ob["em_source_manifest"] = root.get("gpr_manifest", "")
            ob["em_source_crs"] = root.get("gpr_crs", "")
            ob["emwgeo_version"] = "0"
            ob["gpr_depth_range"] = (
                ob.location.z - ob.dimensions.z / 2.0,
                ob.location.z + ob.dimensions.z / 2.0)
            ob["em_note"] = ("Read off GPR amplitude; type and graph edges to "
                             "be assigned by the interpreter (EMWgeo v.0)")
            n += 1
        self.report({'INFO'}, "%d object(s) tagged; no EM node was created" % n)
        return {'FINISHED'}


# --------------------------------------------------------------------------
# UI
# --------------------------------------------------------------------------

class VIEW3D_PT_dsc_GPR(Panel):
    bl_category = "3DSC"
    bl_label = "GPR slices"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_context = "objectmode"
    bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        layout = self.layout
        s = context.scene.gpr_settings

        col = layout.column(align=True)
        row = col.row(align=True)
        row.prop(s, "source_dir", text="")
        row.operator("gpr.set_source", icon='FILE_FOLDER', text="")
        col.prop(s, "cache_dir", text="Cache")
        col.prop(s, "stack_kind", expand=True)

        box = layout.box()
        box.label(text="Raster cache", icon='IMAGE_DATA')
        if s.stack_kind == 'CSV':
            box.prop(s, "colormap")
            box.prop(s, "normalize")
        if s.stack_kind == 'CSV':
            r = box.row(align=True)
            r.prop(s, "clip_lo")
            r.prop(s, "clip_hi")
        box.prop(s, "limit")
        if s.stack_kind == 'CSV':
            box.operator("gpr.build_cache", icon='FILE_REFRESH')
        else:
            box.prop(s, "img_cell_size")
            box.operator("gpr.build_image_manifest", icon='FILE_REFRESH')
        if s.progress_text:
            box.label(text=s.progress_text, icon='TIME')

        box = layout.box()
        box.label(text="Georeferencing", icon='WORLD')
        box.prop(s, "origin_e")
        box.prop(s, "origin_n")
        box.prop(s, "rotation_deg")
        box.prop(s, "ground_z")
        box.prop(s, "use_shift")
        if s.use_shift:
            sub = box.column(align=True)
            sub.enabled = False
            sub.label(text="GSV: %.2f  %.2f  %.2f  EPSG:%s"
                           % (context.scene.BL_x_shift, context.scene.BL_y_shift,
                              context.scene.BL_z_shift, context.scene.BL_epsg))
        box.operator("gpr.import_stack", icon='IMPORT')

        root = _active_stack(context)
        if root is not None:
            box = layout.box()
            box.label(text=root.name, icon='OUTLINER_OB_EMPTY')
            box.prop(s, "slice_display", expand=True)
            if s.slice_display != 'ALL':
                box.prop(s, "slice_index")
            box.separator()
            box.operator("gpr.tag_anomaly", icon='TAG')
            sub = box.column()
            sub.scale_y = 0.7
            sub.label(text="Anomalies become USD only when you say so.")


classes = [
    GPRSettings,
    GPR_OT_build_cache,
    GPR_OT_build_image_manifest,
    GPR_OT_import_stack,
    GPR_OT_set_source,
    GPR_OT_tag_anomaly,
    VIEW3D_PT_dsc_GPR,
]


def register():
    for cls in classes:
        try:
            bpy.utils.register_class(cls)
        except ValueError:
            bpy.utils.unregister_class(cls)
            bpy.utils.register_class(cls)
    bpy.types.Scene.gpr_settings = PointerProperty(type=GPRSettings)


def unregister():
    for cls in reversed(classes):
        try:
            bpy.utils.unregister_class(cls)
        except RuntimeError:
            pass
    if hasattr(bpy.types.Scene, "gpr_settings"):
        del bpy.types.Scene.gpr_settings
