"""Headless test of ``headless.make_lod_set`` / ``rebake_atlas`` — the API a
``blender -b`` runner (EMStudio's sidecar) calls.

Needs 3D Survey Collection ENABLED in the Blender profile (the module is found
the way a runner finds it: by scanning sys.modules), so no --factory-startup::

    BLENDER_USER_RESOURCES=/tmp/<profile> "/Applications/Blender 520.app/Contents/MacOS/Blender" \\
        -b --python dev_utils/tests/test_headless_lod.py --python-exit-code 1

Without arguments it builds a textured UV sphere (block noise) and checks:
the progress/result line formats; 3 levels with decreasing triangles and
texture sides; a level forced over ``max_texture_size`` split into several
atlases, each with its own material and image; glb files with no Draco /
meshopt / KTX2 and JPEG images; ``rebake_atlas``; nothing left in the .blend;
a missing source answered by an ``ok: false`` line.

With ``HEADLESS_SOURCE=<mesh file>`` (and optionally ``HEADLESS_OUT``,
``HEADLESS_LEVELS=3``) it only runs make_lod_set on that file and prints the
result: the run on real data.
"""
import contextlib, io, json, os, struct, sys, tempfile, time, traceback

import bpy
import numpy as np

FAIL = []


def check(label, cond, extra=""):
    print(("  PASS  " if cond else "  FAIL  ") + label + (f"   {extra}" if extra else ""))
    if not cond:
        FAIL.append(label)


def find_3dsc_headless():
    for name, mod in list(sys.modules.items()):
        if name.endswith(".headless") and hasattr(mod, "make_lod_set"):
            return mod
    raise RuntimeError("3D Survey Collection is not enabled in this Blender")


def glb_json(path):
    b = open(path, "rb").read()
    n = struct.unpack("<I", b[12:16])[0]
    return json.loads(b[20:20 + n])


def glb_uv_spans(path):
    """(u span, v span) of TEXCOORD_0 of each primitive, read from the BIN chunk."""
    b = open(path, "rb").read()
    n = struct.unpack("<I", b[12:16])[0]
    j = json.loads(b[20:20 + n])
    bin_off = 20 + n + 8
    spans = []
    for m in j.get("meshes", []):
        for pr in m["primitives"]:
            acc = j["accessors"][pr["attributes"]["TEXCOORD_0"]]
            bv = j["bufferViews"][acc["bufferView"]]
            o = bin_off + bv.get("byteOffset", 0) + acc.get("byteOffset", 0)
            uv = np.frombuffer(b, dtype=np.float32, count=acc["count"] * 2, offset=o).reshape(-1, 2)
            spans.append(tuple(round(float(x), 2) for x in uv.max(axis=0) - uv.min(axis=0)))
    return spans


def glb_image_rgb(path, tmp):
    """Pixels (N x 3, display values) of the first image of a glb."""
    b = open(path, "rb").read()
    n = struct.unpack("<I", b[12:16])[0]
    j = json.loads(b[20:20 + n])
    bv = j["bufferViews"][j["images"][0]["bufferView"]]
    o = 20 + n + 8 + bv.get("byteOffset", 0)
    p = os.path.join(tmp, "_probe.jpg")
    open(p, "wb").write(b[o:o + bv["byteLength"]])
    img = bpy.data.images.load(p, check_existing=False)
    img.colorspace_settings.name = 'Non-Color'
    px = np.empty(img.size[0] * img.size[1] * 4, dtype=np.float32)
    img.pixels.foreach_get(px)
    bpy.data.images.remove(img)
    return px.reshape(-1, 4)[:, :3]


def glb_triangles(j):
    tris = 0
    for m in j.get("meshes", []):
        for pr in m["primitives"]:
            tris += j["accessors"][pr["indices"]]["count"] // 3
    return tris


def run_captured(fn, *a, **kw):
    buf = io.StringIO()
    err = None
    with contextlib.redirect_stdout(buf):
        try:
            res = fn(*a, **kw)
        except Exception as exc:                    # noqa: BLE001
            res, err = None, exc
    lines = buf.getvalue().splitlines()
    prog = [json.loads(l[len("3DSC-PROGRESS "):]) for l in lines if l.startswith("3DSC-PROGRESS ")]
    results = [json.loads(l[len("3DSC-RESULT "):]) for l in lines if l.startswith("3DSC-RESULT ")]
    return res, err, prog, results


def textured_sphere(tmp):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=96, ring_count=48, radius=1.0)
    obj = bpy.context.active_object
    obj.name = "Probe_LOD0"
    rng = np.random.default_rng(1)
    cells = rng.integers(0, 2, size=(64, 64)).astype(np.float32)
    px = np.kron(cells, np.ones((16, 16), dtype=np.float32))     # 1024²
    rgba = np.stack([px, 1 - px, np.full_like(px, 0.5), np.ones_like(px)], axis=-1)
    img = bpy.data.images.new("noise", 1024, 1024)
    img.pixels.foreach_set(rgba.ravel())
    img.filepath_raw = os.path.join(tmp, "noise.png")
    img.file_format = 'PNG'
    img.save()
    mat = bpy.data.materials.new("M_noise")
    mat.use_nodes = True
    nt = mat.node_tree
    tex = nt.nodes.new("ShaderNodeTexImage")
    tex.image = img
    nt.links.new(tex.outputs["Color"], nt.nodes["Principled BSDF"].inputs["Base Color"])
    obj.data.materials.append(mat)
    return obj


def main():
    hl = find_3dsc_headless()
    print("module:", hl.__name__, "api", hl.API_VERSION)

    source = os.environ.get("HEADLESS_SOURCE")
    if source:
        out = os.environ.get("HEADLESS_OUT") or tempfile.mkdtemp(prefix="dsc_headless_")
        levels = int(os.environ.get("HEADLESS_LEVELS", "3"))
        t0 = time.time()
        res = hl.make_lod_set(source, out, levels=levels)      # lines go to stdout
        print("WALL", round(time.time() - t0, 2))
        for o in res["outputs"]:
            j = glb_json(o["path"])
            print("GLB", os.path.basename(o["path"]), "tris", glb_triangles(j),
                  "images", len(j.get("images", [])),
                  "mime", sorted({i.get("mimeType") for i in j.get("images", [])}),
                  "ext", j.get("extensionsUsed", []))
        return

    tmp = tempfile.mkdtemp(prefix="dsc_headless_")
    src = textured_sphere(tmp)
    src_tris = sum(len(p.vertices) - 2 for p in src.data.polygons)
    before = {k: len(getattr(bpy.data, k)) for k in ("objects", "meshes", "materials", "images",
                                                     "collections")}

    # --- 1. three levels from an object of the open .blend
    out = os.path.join(tmp, "lods")
    res, err, prog, results = run_captured(hl.make_lod_set, src.name, out, levels=3)
    check("make_lod_set runs", err is None, repr(err))
    check("one 3DSC-RESULT line, ok", len(results) == 1 and results[0]["ok"] is True)
    check("progress: start..done, done counts up to total",
          prog and prog[0]["stage"] == "start" and prog[-1]["stage"] == "done"
          and prog[-1]["done"] == prog[-1]["total"] == 3 + 5 * 3
          and [p["done"] for p in prog] == list(range(len(prog))),
          [p["stage"] for p in prog])
    check("progress stages per level",
          [p["stage"] for p in prog if p.get("level") == 1]
          == ["decimate", "unwrap", "bake", "export", "stamp"])
    outs = res["outputs"] if res else []
    check("3 outputs named <base>_LOD<n>.glb",
          [os.path.basename(o["path"]) for o in outs] == ["Probe_LOD0.glb", "Probe_LOD1.glb",
                                                           "Probe_LOD2.glb"])
    keys = {"path", "level", "triangles", "textures", "texture_px", "bytes", "stamp"}
    check("output fields", all(keys <= set(o) for o in outs))
    tris = [o["triangles"] for o in outs]
    check("triangles decrease ~ 1 : 1/4 : 1/16",
          tris and tris[0] == src_tris and abs(tris[1] / src_tris - 0.25) < 0.05
          and abs(tris[2] / src_tris - 0.0625) < 0.03, tris)
    sides = [o["texture_px"] for o in outs]
    check("texture side halves per level", sides and sides[0] == 2 * sides[1] == 4 * sides[2],
          sides)
    for o in outs:
        j = glb_json(o["path"])
        ext = set(j.get("extensionsUsed", []))
        check(f"LOD{o['level']}: glb tris == reported, 1 JPEG, no Draco/meshopt/KTX2",
              glb_triangles(j) == o["triangles"] and len(j.get("images", [])) == 1
              and j["images"][0].get("mimeType") == "image/jpeg"
              and not ext & {"KHR_draco_mesh_compression", "EXT_meshopt_compression",
                             "KHR_texture_basisu"}
              and o["bytes"] == os.path.getsize(o["path"]),
              f"{glb_triangles(j)} {[i.get('mimeType') for i in j.get('images', [])]} {ext}")
    # the bake carries the source colour: R = noise, G = 1 - noise, B = 0.5
    rgb = glb_image_rgb(outs[0]["path"], tmp) if outs else None
    if rgb is not None:
        b_med = float(np.median(rgb[:, 2]))
        rg = float(np.mean(np.abs(rgb[:, 0] + rgb[:, 1] - 1.0)))
        check("LOD0 atlas is the source colour (B ~ 0.5, R + G ~ 1)",
              0.4 < b_med < 0.6 and rg < 0.2, f"B median {b_med:.3f}, |R+G-1| {rg:.3f}")
    check("stamp state reported", all(o["stamp"] in ("stamped", "revised", "unchanged",
                                                     "no_emtools") for o in outs),
          [o["stamp"] for o in outs])
    after = {k: len(getattr(bpy.data, k)) for k in before}
    check("nothing left in the .blend", after == before, f"{before} -> {after}")

    # --- 2. a level that does not fit one atlas: several atlases
    res2, err2, _, _ = run_captured(hl.make_lod_set, src.name, os.path.join(tmp, "split"),
                                    levels=[1.0], max_texture_size=256, min_texture_size=64)
    o = res2["outputs"][0] if res2 else {}
    check("split level runs", err2 is None, repr(err2))
    j = glb_json(o["path"]) if o else {}
    check("split: textures > 1, as many images and materials in the glb",
          o.get("textures", 0) > 1 and len(j.get("images", [])) == o["textures"]
          and len(j.get("materials", [])) == o["textures"], f"{o.get('textures')} textures")
    # each slab has its own 0-1 layout: the UVs of every primitive span the square
    spans = glb_uv_spans(o["path"]) if o else []
    check("split: every atlas used over its whole square", spans and all(
        a > 0.9 or b > 0.9 for a, b in spans), spans)

    # --- 3. rebake_atlas from a FILE source (OBJ written here)
    bpy.ops.object.select_all(action='DESELECT')
    src.select_set(True)
    bpy.context.view_layer.objects.active = src
    obj_path = os.path.join(tmp, "probe.obj")
    bpy.ops.wm.obj_export(filepath=obj_path, export_selected_objects=True,
                          export_materials=True, path_mode='ABSOLUTE')
    before = {k: len(getattr(bpy.data, k)) for k in before}
    res3, err3, prog3, results3 = run_captured(hl.rebake_atlas, obj_path,
                                               os.path.join(tmp, "atlas", "probe_atlas.glb"),
                                               size=512)
    check("rebake_atlas runs", err3 is None, repr(err3))
    o = res3["outputs"][0] if res3 else {}
    j = glb_json(o["path"]) if o else {}
    check("rebake_atlas: one 512 atlas, same triangles",
          o.get("texture_px") == 512 and o.get("textures") == 1
          and glb_triangles(j) == src_tris and len(j.get("images", [])) == 1, o)
    after = {k: len(getattr(bpy.data, k)) for k in before}
    check("file source imported and removed", after == before, f"{before} -> {after}")

    # --- 4. a failure is a line, then the exception
    res4, err4, _, results4 = run_captured(hl.make_lod_set, "/nowhere/missing.obj",
                                           os.path.join(tmp, "x"))
    check("missing source: ok:false line and ValueError",
          isinstance(err4, ValueError) and results4 and results4[-1]["ok"] is False
          and "error" in results4[-1], results4)
    print("tmp:", tmp)


try:
    main()
except Exception:
    traceback.print_exc()
    FAIL.append("exception")
print("ALL PASS" if not FAIL else f"FAILED: {FAIL}")
if FAIL:
    sys.exit(1)
