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
from mathutils import Vector
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
GROUND_FLAG = "dsc_photogrammetric_ground"


def _as_float(text, default=0.0):
    """Parse a coordinate typed as text.

    Blender's ``FloatProperty`` is single precision: a UTM easting of
    701606.558 lands on the nearest representable float, up to 3 cm away,
    which is worse than the 5 cm cell of the Tivoli grid. Absolute coordinates
    are therefore held as text and parsed to a Python double; only the
    *shifted* result — a small number — is ever written into a Blender
    transform. That is the precision argument for the shift, on top of the
    viewport jitter one.
    """
    try:
        return float(str(text).strip().replace(",", "."))
    except (TypeError, ValueError):
        return default


def _ground_poll(self, ob):
    return ob is not None and ob.type == 'MESH'


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
        name="Slices", subtype='DIR_PATH',
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
        name="Normalise",
        items=[('STACK', "Whole stack", "One range for every slice: slices "
                                        "stay comparable with each other"),
               ('SLICE', "Per slice", "Each slice stretched to its own range: "
                                      "shows faint deep anomalies but "
                                      "misrepresents relative amplitude")],
        default='STACK')  # type: ignore
    clip_lo: FloatProperty(name="Clip lo %", default=2.0, min=0.0, max=49.0)  # type: ignore
    clip_hi: FloatProperty(name="Clip hi %", default=98.0, min=51.0, max=100.0)  # type: ignore
    limit: IntProperty(name="Max slices", default=0, min=0,
                       description="0 = every slice")  # type: ignore

    # Georeferencing of the local survey frame. E/N are TEXT, not floats:
    # Blender's FloatProperty is single precision and quantises a UTM easting
    # to ~3 cm, which is worse than the 5 cm cell of the Tivoli grid. Only the
    # shifted result — a small number — ever reaches a Blender transform.
    origin_e: StringProperty(
        name="Origin E", default="0",
        description="CRS easting of the local (0,0) cell. Read from a world "
                    "file when there is one")  # type: ignore
    origin_n: StringProperty(
        name="Origin N", default="0",
        description="CRS northing of the local (0,0) cell")  # type: ignore
    shift_round_to: FloatProperty(
        name="Round shift to", default=10.0, min=0.0,
        description="The proposed shift is rounded down to a multiple of this. "
                    "A round figure is exactly representable as a float and "
                    "can be retyped into another project by hand")  # type: ignore

    # photogrammetric walking surface
    ground_object: PointerProperty(
        type=bpy.types.Object, poll=_ground_poll, name="Ground",
        description="The photogrammetric walking surface the slices hang "
                    "below. Declare it with the button, so the drape is "
                    "traceable to the photogrammetric document")  # type: ignore
    drape_mode: EnumProperty(
        name="Drape",
        items=[('FLAT', "Flat", "One horizontal plane per slice: correct only "
                                "where the ground is level"),
               ('GRID', "Grid on ground", "A regular grid over the slice "
                                          "extent, dropped onto the declared "
                                          "ground surface"),
               ('GEOMETRY', "Ground geometry", "A decimated duplicate of the "
                                               "ground mesh itself, when its "
                                               "own topology matters")],
        default='FLAT')  # type: ignore
    drape_resolution: IntProperty(
        name="Grid", default=128, min=2, max=1024,
        description="Cells per side of the drape grid. 128 gives ~16k rays "
                    "and ~16k faces, shared by every slice in the stack")  # type: ignore
    decimate_target: IntProperty(
        name="Max triangles", default=200000, min=100,
        description="Triangle budget for the duplicated ground geometry - "
                    "Decimate works on triangles, not quads. The declared "
                    "ground object is never modified")  # type: ignore
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


class GPR_OT_mark_ground(Operator):
    """Declare the active mesh as the photogrammetric walking surface"""
    bl_idname = "gpr.mark_ground"
    bl_label = "Declare as photogrammetric ground"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        ob = context.active_object
        return ob is not None and ob.type == 'MESH'

    def execute(self, context):
        ob = context.active_object
        ob[GROUND_FLAG] = True
        ob["dsc_ground_faces"] = len(ob.data.polygons)
        context.scene.gpr_settings.ground_object = ob
        self.report({'INFO'},
                    "%s declared as photogrammetric ground (%d faces)"
                    % (ob.name, len(ob.data.polygons)))
        return {'FINISHED'}


def _sample_ground_z(gev, mw, mwi, wx, wy, top, span):
    """World Z of the ground under (wx, wy), or None if it is not there."""
    o = mwi @ Vector((wx, wy, top))
    d = (mwi @ Vector((wx, wy, top - 1.0))) - o
    if d.length == 0.0:
        return None
    d.normalize()
    hit, loc, _nor, _idx = gev.ray_cast(o, d, distance=span)
    if not hit:
        return None
    return (mw @ loc).z


def _extent(g):
    """Quad corner and size of a slice, in the local survey frame."""
    x0 = g["x_min"] - g["x_step"] / 2.0
    y0 = g["y_min"] - g["y_step"] / 2.0
    return x0, y0, g["nx"] * g["x_step"], g["ny"] * g["y_step"]


def _planar_uv(me, x0, y0, w, h):
    while me.uv_layers:
        me.uv_layers.remove(me.uv_layers[0])
    uvl = me.uv_layers.new(name="UVMap")
    for poly in me.polygons:
        for li in poly.loop_indices:
            co = me.vertices[me.loops[li].vertex_index].co
            uvl.data[li].uv = ((co.x - x0) / w, (co.y - y0) / h)


def _build_flat_mesh(name, g):
    x0, y0, w, h = _extent(g)
    me = bpy.data.meshes.new(name)
    me.from_pydata([(x0, y0, 0), (x0 + w, y0, 0),
                    (x0 + w, y0 + h, 0), (x0, y0 + h, 0)], [], [(0, 1, 2, 3)])
    me.update()
    _planar_uv(me, x0, y0, w, h)
    return me, {"mode": "FLAT", "faces": 1, "misses": 0}


def _build_grid_drape(context, name, root, ground, g, res):
    """A regular grid over the slice extent, dropped onto the ground.

    This is the paper's construction (*Sensors* 23/5 2769: shrinkwrap limited
    to the Z axis, with an offset equal to the slice depth, on a subdivided
    plane) done once and baked rather than as live modifiers on every slice.
    Two reasons. The drape resolution becomes a number the user can see and
    choose, instead of a subdivision count whose cost is hidden — the paper's
    10 subdivisions are about a million faces *per slice*. And because the
    offset between slices is a pure Z translation, the baked mesh can be
    **shared** by the whole stack: N slices cost one mesh, not N.
    """
    dg = context.evaluated_depsgraph_get()
    gev = ground.evaluated_get(dg)
    mw = ground.matrix_world
    mwi = mw.inverted()
    zs = [(mw @ Vector(c)).z for c in ground.bound_box]
    top, bottom = max(zs) + 1.0, min(zs) - 1.0
    span = top - bottom

    x0, y0, w, h = _extent(g)
    n = max(2, int(res)) + 1
    rmw = root.matrix_world
    rmwi = rmw.inverted()

    raw = []
    hits = []
    for j in range(n):
        v = j / (n - 1.0)
        for i in range(n):
            u = i / (n - 1.0)
            wp = rmw @ Vector((x0 + u * w, y0 + v * h, 0.0))
            z = _sample_ground_z(gev, mw, mwi, wp.x, wp.y, top, span)
            raw.append((wp.x, wp.y, z))
            if z is not None:
                hits.append(z)
    if not hits:
        raise ValueError(
            "the slice extent does not overlap '%s' — check the "
            "georeferencing origin before draping" % ground.name)
    fill = sum(hits) / len(hits)
    misses = sum(1 for _x, _y, z in raw if z is None)

    verts = [tuple(rmwi @ Vector((x, y, fill if z is None else z)))
             for x, y, z in raw]
    faces = []
    for j in range(n - 1):
        for i in range(n - 1):
            a = j * n + i
            faces.append((a, a + 1, a + n + 1, a + n))
    me = bpy.data.meshes.new(name)
    me.from_pydata(verts, [], faces)
    me.update()
    _planar_uv(me, x0, y0, w, h)
    return me, {"mode": "GRID", "faces": len(faces), "misses": misses,
                "resolution": n - 1}


def _build_geometry_drape(context, name, root, ground, g, max_faces):
    """Duplicate the ground geometry itself, decimated to a face budget.

    For when the terrain's own topology matters — a breakline a regular grid
    would cut across. The duplicate is always decimated to the budget and
    always made from a copy: the declared ground object is never modified, and
    a 20-million-face photogrammetric mesh is never duplicated once per slice,
    because the result is one shared mesh whatever the stack depth.
    """
    dg = context.evaluated_depsgraph_get()
    src = bpy.data.meshes.new_from_object(ground.evaluated_get(dg))
    # Decimate COLLAPSE works on triangles, so the budget has to be counted in
    # triangles too: measured, a 490k-quad ground with a 50k budget came out
    # at 89.7k because the ratio was taken against the quad count.
    src.calc_loop_triangles()
    n_src = len(src.loop_triangles)
    tmp = bpy.data.objects.new("_3dsc_gpr_drape_tmp", src)
    tmp.matrix_world = ground.matrix_world
    context.scene.collection.objects.link(tmp)
    try:
        if max_faces and n_src > max_faces:
            mod = tmp.modifiers.new("3dsc_decimate", 'DECIMATE')
            mod.decimate_type = 'COLLAPSE'
            mod.ratio = float(max_faces) / float(n_src)
        context.view_layer.update()
        dg = context.evaluated_depsgraph_get()
        out = bpy.data.meshes.new_from_object(tmp.evaluated_get(dg))
    finally:
        bpy.data.objects.remove(tmp, do_unlink=True)
        bpy.data.meshes.remove(src)
    out.name = name
    out.transform(root.matrix_world.inverted() @ ground.matrix_world)
    x0, y0, w, h = _extent(g)
    _planar_uv(out, x0, y0, w, h)
    out.calc_loop_triangles()
    return out, {"mode": "GEOMETRY", "faces": len(out.loop_triangles),
                 "misses": 0, "source_faces": n_src}


def _build_drape(context, name, root, settings, g):
    ground = settings.ground_object
    if settings.drape_mode == 'FLAT' or ground is None:
        return _build_flat_mesh(name, g)
    if settings.drape_mode == 'GEOMETRY':
        return _build_geometry_drape(context, name, root, ground, g,
                                     settings.decimate_target)
    return _build_grid_drape(context, name, root, ground, g,
                             settings.drape_resolution)


class GPR_OT_import_stack(Operator):
    """Build the slice geometry in the scene from the cached raster stack"""
    bl_idname = "gpr.import_stack"
    bl_label = "Import GPR stack"
    bl_options = {"REGISTER", "UNDO"}

    shift_e: FloatProperty(name="Shift E", default=0.0, precision=2)  # type: ignore
    shift_n: FloatProperty(name="Shift N", default=0.0, precision=2)  # type: ignore
    shift_z: FloatProperty(name="Shift Z", default=0.0, precision=2)  # type: ignore
    write_shift: BoolProperty(
        name="Write into the scene shift (GSV)", default=True,
        description="Store these values as the scene's General Shift Value, "
                    "so every other 3DSC importer lands on the same origin")  # type: ignore
    dataset_epsg: StringProperty(name="Dataset EPSG", default="")  # type: ignore
    origin_note: StringProperty(default="")  # type: ignore
    epsg_note: StringProperty(default="")  # type: ignore
    situation: StringProperty(default="")  # type: ignore

    @classmethod
    def poll(cls, context):
        return bool(context.scene.gpr_settings.source_dir)

    # -- is the user going to have to be asked? ----------------------------

    def _assess(self, context):
        scene = context.scene
        s = scene.gpr_settings
        manifest = core.load_manifest(_cache_dir(s)) or {}
        geo = manifest.get("georef") or {}
        if not geo.get("origin_e") and not geo.get("epsg"):
            try:
                geo = core.detect_georeference(bpy.path.abspath(s.source_dir))
            except Exception:                        # noqa: BLE001
                geo = geo or {}

        e, n = geo.get("origin_e"), geo.get("origin_n")
        declared = e is None or n is None
        if declared:
            e, n = _as_float(s.origin_e), _as_float(s.origin_n)

        ds_epsg = geo.get("epsg")
        self.dataset_epsg = str(ds_epsg) if ds_epsg else ""
        scene_epsg = scene.BL_epsg if scene.BL_epsg != "NotSet" else ""
        has_shift = bool(scene.BL_x_shift or scene.BL_y_shift or
                         scene.BL_z_shift) or bool(scene_epsg)

        absolute = core.is_absolute(e, n)
        mismatch = bool(ds_epsg and scene_epsg and str(ds_epsg) != scene_epsg)

        self.shift_e, self.shift_n = core.propose_shift(e, n, s.shift_round_to)
        self.shift_z = scene.BL_z_shift
        self.origin_note = ("E %.3f  N %.3f   (%s)"
                            % (e, n, "typed by hand" if declared
                               else geo.get("source", "file")))
        if mismatch:
            self.epsg_note = ("dataset EPSG:%s vs scene EPSG:%s - the scene "
                              "shift was not made for this system"
                              % (ds_epsg, scene_epsg))
        elif ds_epsg and scene_epsg:
            self.epsg_note = "EPSG:%s on both sides" % ds_epsg
        elif ds_epsg:
            self.epsg_note = ("dataset declares EPSG:%s, the scene has none "
                              "yet" % ds_epsg)
        else:
            self.epsg_note = "no EPSG declared by the files"

        if absolute and not has_shift:
            self.situation = 'ASK_SHIFT'
        elif mismatch:
            # a CRS clash is a warning, not an invitation to re-origin the
            # scene: leave the existing shift alone unless the user ticks the
            # box in the dialog
            self.situation = 'ASK_EPSG'
            self.shift_e = scene.BL_x_shift
            self.shift_n = scene.BL_y_shift
            self.write_shift = False
        else:
            self.situation = 'USE_SCENE' if absolute else 'LOCAL'
            self.shift_e = scene.BL_x_shift
            self.shift_n = scene.BL_y_shift
            self.write_shift = False
        return e, n

    def invoke(self, context, event):
        try:
            self._assess(context)
        except Exception as exc:                     # noqa: BLE001
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}
        if self.situation in ('ASK_SHIFT', 'ASK_EPSG'):
            return context.window_manager.invoke_props_dialog(self, width=480)
        return self.execute(context)

    def draw(self, context):
        layout = self.layout
        col = layout.column()
        if self.situation == 'ASK_SHIFT':
            col.label(text="This dataset is in absolute coordinates.",
                      icon='WORLD')
            info = ["Origin: " + self.origin_note,
                    self.epsg_note,
                    "Blender transforms are single precision: a few km out,",
                    "the scene starts to jitter. Shift it near the origin."]
        else:
            col.label(text="The scene already has a shift, but the CRS does "
                           "not match.", icon='ERROR')
            info = ["Origin: " + self.origin_note,
                    self.epsg_note,
                    "Importing as-is will put the data in the wrong place."]
        box = col.box()
        box.scale_y = 0.75
        for line in info:
            box.label(text=line)
        col.separator()
        col.label(text="Shift to apply - edit it if you want another origin:")
        r = col.row(align=True)
        r.prop(self, "shift_e")
        r.prop(self, "shift_n")
        col.prop(self, "shift_z")
        col.prop(self, "write_shift")

    # -- build -------------------------------------------------------------

    def execute(self, context):
        scene = context.scene
        s = scene.gpr_settings
        cache = _cache_dir(s)
        manifest = core.load_manifest(cache)
        if manifest is None:
            self.report({'ERROR'},
                        "No gpr_stack.json in %s - build the cache first"
                        % cache)
            return {'CANCELLED'}
        if not self.situation:
            try:
                self._assess(context)
            except Exception as exc:                 # noqa: BLE001
                self.report({'ERROR'}, str(exc))
                return {'CANCELLED'}

        if self.write_shift:
            scene.BL_x_shift = self.shift_e
            scene.BL_y_shift = self.shift_n
            scene.BL_z_shift = self.shift_z
            if self.dataset_epsg and scene.BL_epsg == "NotSet":
                scene.BL_epsg = self.dataset_epsg

        geo = manifest.get("georef") or {}
        origin_e, origin_n = geo.get("origin_e"), geo.get("origin_n")
        if origin_e is None or origin_n is None:
            origin_e, origin_n = _as_float(s.origin_e), _as_float(s.origin_n)

        g = manifest["grid"]
        # The GSV translates ABSOLUTE coordinates into scene coordinates, so
        # it is only subtracted from an absolute origin. Subtracting it from a
        # dataset that is already local (Tivoli starts at 0,0) would fling the
        # stack 700 km the other way — measured, before this guard.
        absolute = core.is_absolute(float(origin_e), float(origin_n))
        sx = scene.BL_x_shift if (s.use_shift and absolute) else 0.0
        sy = scene.BL_y_shift if (s.use_shift and absolute) else 0.0
        sz = scene.BL_z_shift if s.use_shift else 0.0
        ox = float(origin_e) - float(sx)
        oy = float(origin_n) - float(sy)
        theta = math.radians(s.rotation_deg)
        draping = (s.drape_mode != 'FLAT' and s.ground_object is not None)

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
            coll.objects.link(root)
        root.empty_display_size = max(g["nx"] * g["x_step"],
                                      g["ny"] * g["y_step"]) / 4.0
        # when draping, the mesh carries the surface elevation, so the empty
        # stays on the scene's ground plane and ground_z is not used
        root.location = (ox, oy, 0.0 if draping else (s.ground_z - sz))
        root.rotation_euler = (0.0, 0.0, theta)
        root[STACK_ID_PROP] = coll_name
        context.view_layer.update()

        # ONE mesh for the whole stack: the offset between slices is a pure Z
        # translation, so every slice object points at the same datablock
        mesh_name = "%s_drape" % coll_name
        old = bpy.data.meshes.get(mesh_name)
        if old is not None:
            old.name = mesh_name + "_old"
        try:
            drape_mesh, drape_info = _build_drape(context, mesh_name, root, s, g)
        except Exception as exc:                     # noqa: BLE001
            if old is not None:
                old.name = mesh_name
            self.report({'ERROR'}, "Drape failed: %s" % exc)
            return {'CANCELLED'}
        if old is not None:
            old.user_clear()
            bpy.data.meshes.remove(old)
        if not drape_mesh.materials:
            drape_mesh.materials.append(None)

        root["gpr_source_folder"] = manifest.get("source_folder", "")
        root["gpr_manifest"] = os.path.join(cache, core.MANIFEST_NAME)
        root["gpr_crs"] = ("EPSG:%s" % scene.BL_epsg
                           if scene.BL_epsg != "NotSet" else "")
        root["gpr_origin_e"] = "%.6f" % float(origin_e)
        root["gpr_origin_n"] = "%.6f" % float(origin_n)
        root["gpr_georef_source"] = geo.get("source", "typed by hand")
        root["gpr_rotation_deg"] = s.rotation_deg
        root["gpr_shift_applied"] = (sx, sy, sz)
        root["gpr_cell_size"] = (g["x_step"], g["y_step"])
        root["gpr_grid"] = (g["nx"], g["ny"])
        root["gpr_colormap"] = manifest.get("colormap", "")
        root["gpr_normalize"] = manifest.get("normalize", "")
        root["gpr_drape_mode"] = drape_info["mode"]
        root["gpr_drape_faces"] = drape_info["faces"]
        root["gpr_ground_ref"] = s.ground_object.name if draping else ""
        root["gpr_ground_declared"] = bool(
            draping and s.ground_object.get(GROUND_FLAG))
        root["emwgeo_version"] = "0"
        root["em_interpretation_target"] = "USD"

        made = 0
        for entry in manifest["slices"]:
            ref = entry["raster"]
            img_path = ref if os.path.isabs(ref) else os.path.join(cache, ref)
            if not os.path.isfile(img_path):
                log.warning("missing raster %s", img_path)
                continue
            img = bpy.data.images.load(img_path, check_existing=True)
            name = "%s_d%06.3f" % (coll_name, entry["depth_top"])
            ob = bpy.data.objects.get(name)
            if ob is None:
                ob = bpy.data.objects.new(name, drape_mesh)
                coll.objects.link(ob)
            else:
                ob.data = drape_mesh
            ob.parent = root
            ob.location = (0.0, 0.0,
                           -0.5 * (entry["depth_top"] + entry["depth_bottom"]))
            # material on the OBJECT, not on the shared mesh
            if ob.material_slots:
                ob.material_slots[0].link = 'OBJECT'
                ob.material_slots[0].material = _slice_material(
                    "%s_mat" % name, img)
            ob[SLICE_IDX_PROP] = entry["index"]
            # one slice = one document: the identity lives on the slice, not
            # on the stack, because that is the grain at which extraction
            # happens (E.D., 2026-09-21)
            ob["em_document_id"] = entry.get(
                "document_id",
                "gpr:%s#d%.3f-%.3fm" % (stack_name, entry["depth_top"],
                                        entry["depth_bottom"]))
            ob["em_document_kind"] = "gpr_time_slice"
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
            s.slice_display = 'ONE'
            self.report({'WARNING'},
                        "%d slices: switched to single-slice display to keep "
                        "the texture memory bounded" % made)
        _update_visible_slice(s, context)

        msg = "GPR: %d slices, %s drape (%d faces, one shared mesh)" % (
            made, drape_info["mode"].lower(), drape_info["faces"])
        if drape_info.get("misses"):
            msg += ", %d grid points off the ground" % drape_info["misses"]
        if self.situation == 'USE_SCENE':
            msg += " - scene shift reused, " + self.epsg_note
        elif self.situation == 'LOCAL':
            msg += " - local coordinates, scene shift not applied"
            if scene.BL_x_shift or scene.BL_y_shift:
                self.report({'WARNING'},
                            "The scene has a shift but this stack has no "
                            "georeference: it sits at the scene origin. Type "
                            "the survey origin to place it.")
        self.report({'INFO'}, msg)
        self.situation = ""
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
    """Record which slice documents the selected proxies were read from.

    One slice is one document; reading several of them produces extractions
    that combine into one proxy (E.D., 2026-09-21). So what gets written here
    is the LIST of slice documents that were on screen, not the name of the
    stack — the stack is an acquisition, not a source you read.

    Downstream that list is the difference between an ``ExtractorNode``
    (``source``, one document) and a ``CombinerNode`` (``sources``, several),
    which is why the count is recorded rather than inferred later.

    Provenance only: no node, no edge. Reading an amplitude blob as a wall is
    the archaeologist's act, and the USD it becomes is theirs to declare.
    """
    bl_idname = "gpr.tag_anomaly"
    bl_label = "Tag selection as read from GPR"
    bl_options = {"REGISTER", "UNDO"}

    use_visible: BoolProperty(
        name="Use the slices on screen", default=True,
        description="Record the slices currently visible as the documents "
                    "this reading came from. Turn off to record the whole "
                    "stack instead")  # type: ignore

    @classmethod
    def poll(cls, context):
        return bool(context.selected_objects) and _active_stack(context)

    def execute(self, context):
        root = _active_stack(context)
        slices = [o for o in root.children if SLICE_IDX_PROP in o]
        if self.use_visible:
            read = [o for o in slices if not o.hide_viewport]
        else:
            read = slices
        if not read:
            self.report({'ERROR'},
                        "No slice is visible: show the ones you read the "
                        "anomaly on, so the documents can be recorded")
            return {'CANCELLED'}
        read.sort(key=lambda o: o[SLICE_IDX_PROP])

        doc_ids = [o.get("em_document_id", o.name) for o in read]
        tops = [o["gpr_depth_top"] for o in read]
        bots = [o["gpr_depth_bottom"] for o in read]

        n = 0
        for ob in context.selected_objects:
            if ob is root or SLICE_IDX_PROP in ob:
                continue
            ob["em_suggested_type"] = "USD"
            # IDProperty arrays hold numbers, not strings: join and count
            ob["em_document_ids"] = "\n".join(doc_ids)
            ob["em_document_count"] = len(doc_ids)
            ob["em_extraction"] = ("combiner" if len(doc_ids) > 1
                                   else "extractor")
            ob["em_read_depth_span"] = (min(tops), max(bots))
            ob["em_acquisition"] = root.name
            ob["em_source_manifest"] = root.get("gpr_manifest", "")
            ob["em_source_crs"] = root.get("gpr_crs", "")
            ob["emwgeo_version"] = "0"
            ob["em_note"] = (
                "Read off %d GPR time-slice document(s), %.2f-%.2f m; the "
                "extraction(s) and the USD are the interpreter's to declare "
                "(EMWgeo v.0)" % (len(doc_ids), min(tops), max(bots)))
            n += 1
        self.report(
            {'INFO'},
            "%d proxy/proxies tagged against %d slice document(s) (%s); "
            "no EM node was created"
            % (n, len(doc_ids),
               "combiner" if len(doc_ids) > 1 else "extractor"))
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
        r = box.row(align=True)
        r.prop(s, "origin_e", text="E")
        r.prop(s, "origin_n", text="N")
        box.prop(s, "rotation_deg")
        box.prop(s, "shift_round_to")
        box.prop(s, "use_shift")
        if s.use_shift:
            sub = box.column(align=True)
            sub.enabled = False
            sub.label(text="GSV: %.2f  %.2f  %.2f  EPSG:%s"
                           % (context.scene.BL_x_shift, context.scene.BL_y_shift,
                              context.scene.BL_z_shift, context.scene.BL_epsg))
        box = layout.box()
        box.label(text="Depth reference", icon='MOD_SHRINKWRAP')
        box.prop(s, "drape_mode", expand=True)
        if s.drape_mode == 'FLAT':
            box.prop(s, "ground_z")
        else:
            box.prop(s, "ground_object")
            g_ob = s.ground_object
            if g_ob is None:
                box.label(text="Select a mesh and declare it below",
                          icon='INFO')
            elif not g_ob.get(GROUND_FLAG):
                box.label(text="not declared as photogrammetric ground",
                          icon='ERROR')
            else:
                sub = box.column()
                sub.scale_y = 0.7
                sub.label(text="declared ground, %d faces"
                               % len(g_ob.data.polygons))
            if s.drape_mode == 'GRID':
                box.prop(s, "drape_resolution")
            else:
                box.prop(s, "decimate_target")
            sub = box.column()
            sub.scale_y = 0.7
            sub.label(text="One shared mesh for the whole stack.")
        box.operator("gpr.mark_ground", icon='CHECKMARK')

        layout.operator("gpr.import_stack", icon='IMPORT')

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
            sub.label(text="One slice = one document. A proxy read on")
            sub.label(text="several becomes a combiner. USD is yours.")


classes = [
    GPRSettings,
    GPR_OT_build_cache,
    GPR_OT_build_image_manifest,
    GPR_OT_mark_ground,
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
