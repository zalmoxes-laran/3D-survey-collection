"""Headless entry points of 3D Survey Collection, for ``blender -b`` scripts.

A stable, documented API for callers that drive Blender without its UI (the
EMStudio sidecar runs ``blender -b --python <runner>``): LOD sets for game
engines (Unreal, Blender) and one-atlas rebakes, written as .glb files.

    make_lod_set(source, out_dir, levels=3, *, max_texture_size=4096,
                 min_texture_size=256, max_textures=16, texture_px=None,
                 name=None, image_format="JPEG", jpeg_quality=90,
                 island_margin=0.0, decimate_borders=True, stamp=True,
                 emit=True, normal_map=False) -> dict
    rebake_atlas(source, out_path, size=None, *, max_texture_size=4096,
                 min_texture_size=256, image_format="JPEG", jpeg_quality=90,
                 island_margin=0.0, stamp=True, emit=True) -> dict
    plan(source, levels=3, ...) -> list          (what make_lod_set would do)

``source``: a path to a mesh file (.obj .glb .gltf .fbx .ply .stl — imported,
used, then removed: the open .blend is left as it was), the name of an object
of the open .blend, or a ``bpy.types.Object``. A file with several meshes is
joined into one. No saved .blend is needed: nothing is written beside it,
textures travel inside the .glb.

**Per level** (``lod_plan.plan_lod_set`` — the rules of the Cesium exporter):
the source is copied and decimated to ``ratio`` of its triangles (borders kept,
as LODgenerator's ``decimate_borders``), given a fresh Smart-UV atlas layout,
and its colour is baked from the source (Cycles, selected-to-active, 1
sample, colour pass only, cage 0.1, full-atlas margin — ``native_bake.
_rebake_node_texture``). The pixels a level needs are those the source has in
its original textures (``native_bake._original_texel_pixels``) times
``ratio``; when they do not fit one ``max_texture_size`` atlas the level gets
several (the faces are cut into slabs of equal surface along the longest
axis, one material + atlas per slab). Each level is written as
``<out_dir>/<name>_LOD<n>.glb``: plain glTF 2.0, embedded JPEG (or PNG)
textures, no Draco, no meshopt, no KTX2, Y-up — what the Unreal glTF importer
reads. When EM Tools is enabled each .glb gets its ``.stamp.json``
(``stamp_bridge``); when it is not, the result says so (``stamp:
"no_emtools"``).

**Machine-readable stdout** (one JSON object per line, flushed):

    3DSC-PROGRESS {"stage": "bake", "level": 1, "done": 7, "total": 17}
    3DSC-RESULT {"ok": true, "api": 1, "op": "make_lod_set", ...,
                 "outputs": [{"path", "level", "ratio", "triangles",
                              "textures", "texture_px", "bytes", "stamp"}]}

stages: ``start``, ``load``, ``plan``, then per level ``decimate``,
``unwrap``, ``bake``, ``export``, ``stamp``, and ``done``. ``done``/``total``
count steps. On failure the last line is ``3DSC-RESULT {"ok": false,
"error": "...", "stage": "..."}`` and the exception is raised again (run
Blender with ``--python-exit-code 1`` to get a non-zero exit status).

**Finding this module from a runner.** The add-on's module name depends on
how it is installed (``bl_ext.<repo>.<package>``: ``bl_ext.user_default.
dsc_tools``, ``bl_ext.vscode_development.3D-survey-collection`` …), so look
it up instead of importing it by name::

    import sys
    def find_3dsc_headless():
        for name, mod in list(sys.modules.items()):
            if name.endswith(".headless") and hasattr(mod, "make_lod_set"):
                return mod
        raise RuntimeError("3D Survey Collection is not enabled in this Blender")

The add-on imports this module when it is enabled, so the scan finds it.
Run Blender WITHOUT ``--factory-startup`` (it disables user add-ons); with
a separate profile, ``BLENDER_USER_RESOURCES=<dir> blender -b --python
runner.py --python-exit-code 1``, where ``<dir>/extensions/<repo>/<package>``
holds the add-on and ``<dir>/config/userpref.blend`` has it enabled. To
enable it once in such a profile::

    blender -b --python-expr "import addon_utils, bpy; \\
        addon_utils.enable('bl_ext.user_default.dsc_tools', default_set=True); \\
        bpy.ops.wm.save_userpref()"

(or ``blender -c extension install-file -r user_default -e dsc_tools.zip``
for a built package). ``API_VERSION`` changes only if a signature or a line
format changes incompatibly.
"""
from __future__ import annotations

import json
import math
import os
import sys
import time

import bpy

from . import lod_plan
from . import stamp_bridge

API_VERSION = 1
PROGRESS_PREFIX = "3DSC-PROGRESS "
RESULT_PREFIX = "3DSC-RESULT "

_IMPORTERS = {
    ".obj": lambda p: bpy.ops.wm.obj_import(filepath=p, use_split_objects=False,
                                            use_split_groups=False),
    ".glb": lambda p: bpy.ops.import_scene.gltf(filepath=p),
    ".gltf": lambda p: bpy.ops.import_scene.gltf(filepath=p),
    ".fbx": lambda p: bpy.ops.import_scene.fbx(filepath=p),
    ".ply": lambda p: bpy.ops.wm.ply_import(filepath=p),
    ".stl": lambda p: bpy.ops.wm.stl_import(filepath=p),
}
_TMP_COLLECTION = "__3dsc_headless"


# --------------------------------------------------------------- stdout lines

def _line(prefix, payload, emit=True):
    if emit:
        sys.stdout.write(prefix + json.dumps(payload, separators=(", ", ": ")) + "\n")
        sys.stdout.flush()


class _Progress:
    def __init__(self, total, emit):
        self.done, self.total, self.emit, self.stage = 0, int(total), emit, "start"
        _line(PROGRESS_PREFIX, {"stage": "start", "done": 0, "total": self.total}, emit)

    def step(self, stage, **extra):
        self.stage = stage
        self.done = min(self.total, self.done + 1)
        _line(PROGRESS_PREFIX, dict({"stage": stage}, **extra, done=self.done,
                                    total=self.total), self.emit)


# ------------------------------------------------------------------- the scene

def _tmp_collection():
    col = bpy.data.collections.get(_TMP_COLLECTION)
    if col is None:
        col = bpy.data.collections.new(_TMP_COLLECTION)
    scene = bpy.context.scene
    if col.name not in scene.collection.children:
        scene.collection.children.link(col)
    return col


class _Scratch:
    """Every datablock made here, removed at the end (also on failure)."""

    def __init__(self):
        self.before = {k: set(getattr(bpy.data, k)) for k in
                       ("objects", "meshes", "materials", "images", "collections")}

    def cleanup(self, keep=()):
        keep = set(keep)
        for kind in ("objects", "meshes", "materials", "images", "collections"):
            coll = getattr(bpy.data, kind)
            for block in [b for b in coll if b not in self.before[kind] and b not in keep]:
                try:
                    coll.remove(block, do_unlink=True)
                except Exception:                   # noqa: BLE001 — already gone
                    pass


def _select_only(objs, active):
    for o in bpy.context.view_layer.objects:
        try:
            o.select_set(False)
        except Exception:                           # noqa: BLE001 — not selectable
            pass
    for o in objs:
        o.hide_set(False)
        o.hide_viewport = False
        o.hide_render = False
        o.select_set(True)
    bpy.context.view_layer.objects.active = active


def _object_mode():
    if bpy.context.object is not None and bpy.context.object.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')


def _resolve_source(source):
    """(object, imported) — the mesh object to work from, and whether it was
    imported here (then it is removed at the end)."""
    if isinstance(source, bpy.types.Object):
        obj = source
    elif isinstance(source, (str, os.PathLike)) and os.path.isfile(os.fspath(source)):
        path = os.path.abspath(os.fspath(source))
        ext = os.path.splitext(path)[1].lower()
        if ext not in _IMPORTERS:
            raise ValueError(f"unsupported source format {ext!r} ({sorted(_IMPORTERS)})")
        _object_mode()
        before = set(bpy.data.objects)
        res = _IMPORTERS[ext](path)
        if 'FINISHED' not in res:
            raise RuntimeError(f"import failed: {path}")
        meshes = [o for o in bpy.data.objects if o not in before and o.type == 'MESH']
        if not meshes:
            raise ValueError(f"no mesh in {path}")
        if len(meshes) > 1:
            _select_only(meshes, meshes[0])
            bpy.ops.object.join()
        obj = meshes[0]
        if obj.parent is not None:                  # glTF importers may parent
            mw = obj.matrix_world.copy()
            obj.parent = None
            obj.matrix_world = mw
        obj.name = os.path.splitext(os.path.basename(path))[0]
        return obj, True
    elif isinstance(source, str) and source in bpy.data.objects:
        obj = bpy.data.objects[source]
    else:
        raise ValueError(f"source is neither a mesh file nor an object of this .blend: {source!r}")
    if obj.type != 'MESH':
        raise ValueError(f"{obj.name!r} is not a mesh")
    return obj, False


def _triangles(mesh):
    import numpy as np
    n = len(mesh.polygons)
    if n == 0:
        return 0
    lt = np.empty(n, dtype=np.int32)
    mesh.polygons.foreach_get("loop_total", lt)
    return int((lt - 2).sum())


def _source_pixels(obj):
    from .cesium_exporter.native_bake import _original_texel_pixels
    try:
        return _original_texel_pixels(obj.data)
    except Exception:                               # noqa: BLE001 — face-count fallback
        return None


# ---------------------------------------------------------------- one level

def _copy_for_level(src, name, col):
    obj = src.copy()
    obj.data = src.data.copy()
    obj.name = name
    obj.data.name = "ME_" + name
    obj.animation_data_clear()
    for c in list(obj.users_collection):
        c.objects.unlink(obj)
    col.objects.link(obj)
    obj.modifiers.clear()
    obj.vertex_groups.clear()
    obj.data.materials.clear()
    return obj


def _decimate(obj, ratio, target_tris, keep_borders):
    """Decimate modifier evaluated into the mesh (no edit mode, no ops)."""
    import bmesh
    if ratio >= 0.999:
        return
    mod = obj.modifiers.new("Decimate", type='DECIMATE')
    mod.ratio = max(float(ratio), 0.0001)
    if keep_borders:
        bm = bmesh.new()
        bm.from_mesh(obj.data)
        border = [v.index for v in bm.verts if any(not e.is_manifold for e in v.link_edges)]
        bm.free()
        if border:
            group = obj.vertex_groups.new(name="__3dsc_border")
            group.add(border, 1.0, 'REPLACE')
            mod.vertex_group = group.name
            mod.invert_vertex_group = True
    _apply_modifiers(obj)
    # protected borders can keep a level above its budget: a second pass
    # without them brings it in (native_export does the same)
    n = _triangles(obj.data)
    if keep_borders and n > target_tris * 1.1:
        mod = obj.modifiers.new("Decimate", type='DECIMATE')
        mod.ratio = max(float(target_tris) / float(n), 0.0001)
        _apply_modifiers(obj)
    obj.vertex_groups.clear()


def _apply_modifiers(obj):
    depsgraph = bpy.context.evaluated_depsgraph_get()
    old = obj.data
    new = bpy.data.meshes.new_from_object(obj.evaluated_get(depsgraph),
                                          preserve_all_data_layers=True, depsgraph=depsgraph)
    new.name = old.name
    obj.modifiers.clear()
    obj.data = new
    if old.users == 0:
        bpy.data.meshes.remove(old)


def _face_groups(mesh, parts):
    """Slab index of each face: equal surface per slab along the longest axis."""
    import numpy as np
    n = len(mesh.polygons)
    if parts <= 1 or n == 0:
        return np.zeros(n, dtype=np.int32)
    centers = np.empty(n * 3, dtype=np.float64)
    mesh.polygons.foreach_get("center", centers)
    centers = centers.reshape(n, 3)
    area = np.empty(n, dtype=np.float64)
    mesh.polygons.foreach_get("area", area)
    axis = int(np.argmax(centers.max(axis=0) - centers.min(axis=0)))
    order = np.argsort(centers[:, axis], kind="stable")
    w = area[order]
    if w.sum() <= 0:
        w = np.ones_like(w)
    mid = np.cumsum(w) - w / 2.0
    groups = np.empty(n, dtype=np.int32)
    groups[order] = np.minimum(parts - 1, (mid / w.sum() * parts).astype(np.int32))
    return groups


def _unwrap(obj, groups, parts, island_margin):
    """A fresh UV map, the only one: each group packed in its own 0-1 square."""
    import bmesh
    import numpy as np
    mesh = obj.data
    while mesh.uv_layers:
        mesh.uv_layers.remove(mesh.uv_layers[0])
    uv = mesh.uv_layers.new(name="UVMap")
    mesh.uv_layers.active = uv
    _select_only([obj], obj)
    bpy.ops.object.mode_set(mode='EDIT')
    try:
        bm = bmesh.from_edit_mesh(mesh)
        bm.select_mode = {'FACE'}
        bm.faces.ensure_lookup_table()
        for g in range(parts):
            members = np.flatnonzero(groups == g) if parts > 1 else range(len(bm.faces))
            if len(members) == 0:
                continue
            for f in bm.faces:
                f.select_set(False)
            for i in members:
                bm.faces[int(i)].select_set(True)
            bm.select_flush_mode()
            bmesh.update_edit_mesh(mesh, loop_triangles=False, destructive=False)
            bpy.ops.uv.smart_project(angle_limit=math.radians(66), margin_method='SCALED',
                                     rotate_method='AXIS_ALIGNED_Y',
                                     island_margin=float(island_margin), area_weight=0.0,
                                     correct_aspect=True, scale_to_bounds=True)
    finally:
        bpy.ops.object.mode_set(mode='OBJECT')
    return uv


def _bake_materials(obj, name, groups, parts, side, normal_map=False):
    """One material + one atlas image per group; polygons get their group.
    ``normal_map``: a second image per group (non-colour data) for the
    tangent-space normals, wired through a Normal Map node once baked."""
    mesh = obj.data
    mesh.materials.clear()
    images, nodes, normals = [], [], []
    for g in range(parts):
        suffix = f"_{g}" if parts > 1 else ""
        img = bpy.data.images.new(f"T_{name}{suffix}", width=int(side), height=int(side),
                                  alpha=False, float_buffer=False)
        mat = bpy.data.materials.new(f"M_{name}{suffix}")
        mat.use_nodes = True
        nt = mat.node_tree
        nt.nodes.clear()
        out = nt.nodes.new("ShaderNodeOutputMaterial")
        bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
        tex = nt.nodes.new("ShaderNodeTexImage")
        tex.image = img
        tex.location, bsdf.location, out.location = (-500, 0), (-250, 0), (20, 0)
        nt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
        if "Metallic" in bsdf.inputs:
            bsdf.inputs["Metallic"].default_value = 0.0
        if "Roughness" in bsdf.inputs:
            bsdf.inputs["Roughness"].default_value = 1.0
        for node in nt.nodes:
            node.select = False
        tex.select = True
        nt.nodes.active = tex
        if normal_map:
            nimg = bpy.data.images.new(f"N_{name}{suffix}", width=int(side), height=int(side),
                                       alpha=False, float_buffer=False)
            nimg.colorspace_settings.name = "Non-Color"
            ntex = nt.nodes.new("ShaderNodeTexImage")
            ntex.image = nimg
            ntex.location = (-500, -300)
            nmap = nt.nodes.new("ShaderNodeNormalMap")
            nmap.location = (-250, -300)
            images.append(nimg)
            normals.append((nt, ntex, nmap, bsdf))
        mesh.materials.append(mat)
        images.append(img)
        nodes.append((nt, tex, bsdf))
    mesh.polygons.foreach_set("material_index", groups.astype("int32"))
    mesh.update()
    if normal_map:
        return images, nodes, normals
    return images, nodes


def _bake_normals(src, obj, side, normals):
    """MICRO-PREPARA-DIAGNOSI (E.D., 30 Oct 2026) · the tangent-space normals of
    the full mesh ``src`` baked onto the decimated ``obj`` (selected-to-active,
    the cage of the colour bake), so the lighter level keeps the relief it lost.
    The normal images become the active nodes, then the Normal Map nodes are
    wired into the BSDF (the glTF exporter writes them as ``normalTexture``)."""
    for nt, ntex, _nmap, _bsdf in normals:
        for node in nt.nodes:
            node.select = False
        ntex.select = True
        nt.nodes.active = ntex
    scene = bpy.context.scene
    saved = {"engine": scene.render.engine, "samples": scene.cycles.samples}
    try:
        scene.render.engine = 'CYCLES'
        scene.cycles.samples = 1
        _select_only([src, obj], obj)
        res = bpy.ops.object.bake(type='NORMAL', normal_space='TANGENT', use_clear=True,
                                  use_selected_to_active=True, cage_extrusion=0.1,
                                  max_ray_distance=0.0, use_cage=False,
                                  margin_type='ADJACENT_FACES', margin=int(side))
        if 'FINISHED' not in res:
            raise RuntimeError("Cycles normal bake failed")
    finally:
        scene.render.engine = saved["engine"]
        scene.cycles.samples = saved["samples"]
    for nt, ntex, nmap, bsdf in normals:
        nt.links.new(ntex.outputs["Color"], nmap.inputs["Color"])
        nt.links.new(nmap.outputs["Normal"], bsdf.inputs["Normal"])


def _bake(src, obj, side):
    """Colour of ``src`` onto ``obj``'s active image nodes — the settings of
    ``native_bake._rebake_node_texture`` (and LODgenerator)."""
    scene = bpy.context.scene
    saved = {"engine": scene.render.engine, "samples": scene.cycles.samples,
             "bounces": scene.cycles.diffuse_bounces}
    try:
        scene.render.engine = 'CYCLES'
        scene.cycles.samples = 1
        scene.cycles.diffuse_bounces = 1
        bake = scene.render.bake
        bake.use_pass_direct = False
        bake.use_pass_indirect = False
        bake.use_pass_color = True
        _select_only([src, obj], obj)
        res = bpy.ops.object.bake(type='DIFFUSE', pass_filter={'COLOR'}, use_clear=True,
                                  use_selected_to_active=True, cage_extrusion=0.1,
                                  max_ray_distance=0.0, use_cage=False,
                                  margin_type='ADJACENT_FACES', margin=int(side))
        if 'FINISHED' not in res:
            raise RuntimeError("Cycles bake failed")
    finally:
        scene.render.engine = saved["engine"]
        scene.cycles.samples = saved["samples"]
        scene.cycles.diffuse_bounces = saved["bounces"]


def _gltf_kwargs(path, image_format, jpeg_quality):
    wanted = {
        "filepath": path, "export_format": 'GLB', "use_selection": True,
        "export_apply": True, "export_yup": True,
        "export_texcoords": True, "export_normals": True, "export_materials": 'EXPORT',
        # 'AUTO' writes the packed bake as PNG; 'JPEG' re-encodes it
        "export_image_format": 'JPEG' if image_format == "JPEG" else 'AUTO',
        "export_jpeg_quality": int(jpeg_quality), "export_image_quality": int(jpeg_quality),
        "export_draco_mesh_compression_enable": False,
        "export_animations": False, "export_skins": False, "export_morph": False,
        "export_extras": False, "export_cameras": False, "export_lights": False,
    }
    try:
        names = {p.identifier for p in bpy.ops.export_scene.gltf.get_rna_type().properties}
    except Exception:                               # noqa: BLE001 — pass all
        return wanted
    return {k: v for k, v in wanted.items() if k in names}


def _export(obj, path, image_format, jpeg_quality):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    _select_only([obj], obj)
    res = bpy.ops.export_scene.gltf(**_gltf_kwargs(path, image_format, jpeg_quality))
    if 'FINISHED' not in res or not os.path.isfile(path):
        raise RuntimeError(f"glTF export failed: {path}")


def _make_level(src, entry, name, path, col, progress, *, island_margin, keep_borders,
                image_format, jpeg_quality, stamp, stamp_parameters, gesture,
                normal_map=False):
    level = entry["level"]
    obj = _copy_for_level(src, name, col)
    _decimate(obj, entry["ratio"], entry["triangles"], keep_borders)
    progress.step("decimate", level=level, triangles=_triangles(obj.data))
    parts, side = entry["textures"], entry["texture_px"]
    groups = _face_groups(obj.data, parts)
    _unwrap(obj, groups, parts, island_margin)
    progress.step("unwrap", level=level, textures=parts)
    normals = []
    if normal_map:
        images, nodes, normals = _bake_materials(obj, name, groups, parts, side, True)
    else:
        images, nodes = _bake_materials(obj, name, groups, parts, side)
    for nt, tex, _bsdf in nodes:
        for node in nt.nodes:
            node.select = False
        tex.select = True
        nt.nodes.active = tex
    _bake(src, obj, side)
    if normals:
        _bake_normals(src, obj, side, normals)
    for img in images:
        img.pack()
    for nt, tex, bsdf in nodes:
        nt.links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
    progress.step("bake", level=level, textures=parts, texture_px=side,
                  normal_map=bool(normals))
    _export(obj, path, image_format, jpeg_quality)
    progress.step("export", level=level, path=path)
    state, res = "off", None
    if stamp:
        res = stamp_bridge.stamp(
            path, objects=[obj, src], dtc_kind=gesture,
            technique=(f"LOD generation (level {level}: decimate {entry['ratio']:g} + "
                       f"{parts} x {side}px atlas bake)" if gesture == stamp_bridge.KIND_LOD
                       else f"texture rebake ({parts} x {side}px atlas)"),
            parameters=dict(stamp_parameters, level=level, ratio=entry["ratio"],
                            textures=parts, texture_px=side, rule=entry["rule"],
                            normal_map=bool(normals)),
            context=bpy.context)
        state = res.get("state", "failed")
        progress.step("stamp", level=level, state=state)
    else:
        progress.step("stamp", level=level, state="off")
    return {"path": path, "level": level, "ratio": entry["ratio"],
            "triangles": _triangles(obj.data), "textures": parts, "texture_px": side,
            "texture_rule": entry["rule"], "bytes": os.path.getsize(path),
            "normal_map": bool(normals), "stamp": state}, res


# ------------------------------------------------------------------ public API

def plan(source, levels=3, *, max_texture_size=lod_plan.MAX_TEXTURE_SIZE,
         min_texture_size=lod_plan.MIN_TEXTURE_SIZE, max_textures=lod_plan.MAX_TEXTURES,
         texture_px=None):
    """What ``make_lod_set`` would make, without making it: one dict per
    level (``lod_plan.plan_lod_set``). A file source is imported and removed."""
    scratch = _Scratch()
    try:
        src, _ = _resolve_source(source)
        return lod_plan.plan_lod_set(_triangles(src.data), _source_pixels(src), levels,
                                     max_texture_size, min_texture_size, max_textures,
                                     texture_px)
    finally:
        scratch.cleanup()


def _run(op, source, jobs_for, progress_total, emit, stamp, extra_result):
    t0 = time.time()
    progress = _Progress(progress_total, emit)
    scratch = _Scratch()
    outputs, stamps, shown = [], [], None
    try:
        _object_mode()
        src, imported = _resolve_source(source)
        if not imported:                            # an object of the open .blend
            try:
                shown = (src, src.hide_get(), src.hide_viewport, src.hide_render)
            except RuntimeError:                    # not in this view layer
                shown = None
        progress.step("load", source=src.name, triangles=_triangles(src.data))
        entries, names_paths = jobs_for(src)
        progress.step("plan", levels=[{k: e[k] for k in ("level", "ratio", "triangles",
                                                         "textures", "texture_px", "rule")}
                                      for e in entries])
        col = _tmp_collection()
        for entry, (name, path, kw) in zip(entries, names_paths):
            out, res = _make_level(src, entry, name, path, col, progress, stamp=stamp, **kw)
            outputs.append(out)
            stamps.append(res)
        line = stamp_bridge.report_line(stamps) if stamp else ""
        result = dict({"ok": True, "api": API_VERSION, "op": op,
                       "source": os.fspath(source) if not isinstance(source, bpy.types.Object)
                       else source.name,
                       "seconds": round(time.time() - t0, 2), "outputs": outputs,
                       "stamp_note": line or ""}, **extra_result)
        progress.step("done")
        _line(RESULT_PREFIX, result, emit)
        return result
    except Exception as exc:
        _line(RESULT_PREFIX, {"ok": False, "api": API_VERSION, "op": op,
                              "error": f"{type(exc).__name__}: {exc}",
                              "stage": progress.stage, "outputs": outputs}, emit)
        raise
    finally:
        try:
            _object_mode()
        except Exception:                           # noqa: BLE001
            pass
        scratch.cleanup()
        if shown is not None:
            obj, hidden, hide_viewport, hide_render = shown
            try:
                obj.hide_set(hidden)
                obj.hide_viewport, obj.hide_render = hide_viewport, hide_render
            except Exception:                       # noqa: BLE001 — not in this view layer
                pass


def make_lod_set(source, out_dir, levels=3, *, max_texture_size=lod_plan.MAX_TEXTURE_SIZE,
                 min_texture_size=lod_plan.MIN_TEXTURE_SIZE, max_textures=lod_plan.MAX_TEXTURES,
                 texture_px=None, name=None, image_format="JPEG", jpeg_quality=90,
                 island_margin=0.0, decimate_borders=True, stamp=True, emit=True,
                 normal_map=False):
    """Decimate, rebake and export ``source`` as a set of .glb levels.

    ``levels``: number of levels (3 -> ratios 1, 1/4, 1/16) or the triangle
    ratios themselves (level 0 first). ``max_texture_size`` bounds every atlas
    side (a level needing more pixels gets several atlases, up to
    ``max_textures``); ``texture_px`` (int or one per level) forces one atlas
    of that side per level. ``name``: file base, default the source name
    without its ``_LOD<n>`` suffix -> ``<out_dir>/<name>_LOD<n>.glb`` (existing
    files are overwritten). ``image_format``: "JPEG" or "PNG". ``normal_map``:
    each decimated level (ratio < 1) also gets a tangent-space normal map baked
    from the full source, one per atlas, same side (EM Tools' «Prepare for a
    use» asks it for an object over its profile's budget). Returns the dict
    printed on the ``3DSC-RESULT`` line."""
    if image_format not in ("JPEG", "PNG"):
        raise ValueError("image_format must be 'JPEG' or 'PNG' (Unreal reads both)")
    ratios = lod_plan.level_ratios(levels)
    out_dir = os.path.abspath(os.fspath(out_dir))

    def jobs_for(src):
        entries = lod_plan.plan_lod_set(_triangles(src.data), _source_pixels(src), ratios,
                                        max_texture_size, min_texture_size, max_textures,
                                        texture_px)
        base = name or lod_plan.base_name(src.name)
        params = {"api": "headless.make_lod_set", "source": src.name,
                  "levels": [e["ratio"] for e in entries],
                  "max_texture_size": int(max_texture_size)}
        jobs = [(f"{base}_LOD{e['level']}",
                 os.path.join(out_dir, f"{base}_LOD{e['level']}.glb"),
                 {"island_margin": island_margin, "keep_borders": decimate_borders,
                  "image_format": image_format, "jpeg_quality": jpeg_quality,
                  "stamp_parameters": params, "gesture": stamp_bridge.KIND_LOD,
                  "normal_map": bool(normal_map) and e["ratio"] < 0.999})
                for e in entries]
        return entries, jobs

    return _run("make_lod_set", source, jobs_for, 3 + 5 * len(ratios), emit, stamp,
                {"out_dir": out_dir})


def rebake_atlas(source, out_path, size=None, *, max_texture_size=lod_plan.MAX_TEXTURE_SIZE,
                 min_texture_size=lod_plan.MIN_TEXTURE_SIZE, image_format="JPEG",
                 jpeg_quality=90, island_margin=0.0, stamp=True, emit=True):
    """All the textures of one object rebaked into ONE atlas, same geometry,
    written as ``out_path`` (.glb). ``size``: the atlas side; None -> the side
    that keeps the original texel density (nearest power of two, clamped to
    [min_texture_size, max_texture_size]). Returns the ``3DSC-RESULT`` dict."""
    if image_format not in ("JPEG", "PNG"):
        raise ValueError("image_format must be 'JPEG' or 'PNG' (Unreal reads both)")
    out_path = os.path.abspath(os.fspath(out_path))

    def jobs_for(src):
        tris = _triangles(src.data)
        if size:
            entry = lod_plan.plan_lod_set(tris, None, [1.0], texture_px=int(size))[0]
        else:
            entry = lod_plan.plan_lod_set(tris, _source_pixels(src), [1.0], max_texture_size,
                                          min_texture_size, max_textures=1)[0]
        stem = os.path.splitext(os.path.basename(out_path))[0]
        return [entry], [(stem, out_path,
                          {"island_margin": island_margin, "keep_borders": True,
                           "image_format": image_format, "jpeg_quality": jpeg_quality,
                           "stamp_parameters": {"api": "headless.rebake_atlas",
                                                "source": src.name},
                           "gesture": stamp_bridge.KIND_EXPORT})]

    return _run("rebake_atlas", source, jobs_for, 3 + 5, emit, stamp, {"out_path": out_path})
