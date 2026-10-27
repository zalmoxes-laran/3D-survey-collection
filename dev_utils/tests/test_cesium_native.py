"""Headless tests of the native split (cesium_exporter), on a small textured
sphere in a temporary folder:

* tileset.json is schema-valid: schema id pattern, no `metadata` on a root
  that has `implicitTiling` (and the Cesium 3d-tiles-validator, when found,
  reports 0 errors);
* 'Use existing OBJ file' (EXISTING_OBJ) exports, and leaves no object behind;
* coarse tiles (root included) respect `cesium_coarse_max_triangles`, also
  the root content of a Single JSON tileset;
* leaves baked from the ORIGINAL textures keep the detail that leaves rebaked
  from a small global atlas lose.

    "/Applications/Blender 520.app/Contents/MacOS/Blender" -b --factory-startup \\
        --python dev_utils/tests/test_cesium_native.py
"""
import bpy, os, sys, re, json, glob, shutil, struct, subprocess, tempfile, traceback

import numpy as np

ADDON = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, ADDON)
import cesium_exporter

FAIL = []
def check(label, cond, extra=""):
    print(("  PASS  " if cond else "  FAIL  ") + label + (f"   {extra}" if extra else ""))
    if not cond:
        FAIL.append(label)

cesium_exporter.register()
scene = bpy.context.scene
tmp = tempfile.mkdtemp(prefix="dsc_native_")

VALIDATOR = os.environ.get("TZ_VALIDATOR") or next(
    (p for p in ["/tmp/ottim/val/node_modules/.bin/3d-tiles-validator"] if os.path.isfile(p)), None)


# ------------------------------------------------------------------ helpers
def glb_read(path):
    b = open(path, "rb").read()
    n = struct.unpack("<I", b[12:16])[0]
    j = json.loads(b[20:20 + n])
    bin_off = 20 + n + 8
    tris = 0
    for m in j.get("meshes", []):
        for pr in m["primitives"]:
            acc = j["accessors"][pr["indices"]] if "indices" in pr else j["accessors"][pr["attributes"]["POSITION"]]
            tris += acc["count"] // 3
    images = []
    for im in j.get("images", []):
        bv = j["bufferViews"][im["bufferView"]]
        o = bin_off + bv.get("byteOffset", 0)
        images.append(b[o:o + bv["byteLength"]])
    return tris, images


def png_stats(data):
    """(side, fraction of 'pure' pixels) of a PNG given as bytes: the source
    is binary block noise (cells of 0 or 1), so a texel that still reads
    < 0.1 or > 0.9 resolves a cell; every resampling through a coarser image
    mixes neighbouring cells into greys."""
    p = os.path.join(tmp, "_probe.png")
    open(p, "wb").write(data)
    img = bpy.data.images.load(p, check_existing=False)
    w, h = img.size[:]
    px = np.empty(w * h * 4, dtype=np.float32)
    img.pixels.foreach_get(px)
    bpy.data.images.remove(img)
    lum = px.reshape(-1, 4)[:, :3].mean(axis=1)
    return w, float(((lum < 0.1) | (lum > 0.9)).mean())


def validate(tileset_json):
    if not VALIDATOR:
        print("  SKIP  validator: not found (set TZ_VALIDATOR)")
        return None
    p = subprocess.run([VALIDATOR, "--tilesetFile", tileset_json], capture_output=True, text=True, timeout=600)
    out = p.stdout + p.stderr
    m = re.search(r'"numErrors":\s*(\d+)', out)
    if not m:
        print(out[:800])
        return -1
    if int(m.group(1)):
        print(out[:2000])
    return int(m.group(1))


def check_tileset_schema(tileset_json, label):
    ts = json.load(open(tileset_json))
    schema = ts.get("schema")
    if schema is not None:
        check(f"{label}: schema id matches [a-zA-Z_][a-zA-Z0-9_]*",
              re.fullmatch(r"[a-zA-Z_][a-zA-Z0-9_]*", schema.get("id", "")) is not None, schema.get("id"))
    root = ts["root"]
    if "implicitTiling" in root:
        check(f"{label}: implicit root carries no metadata", "metadata" not in root)
    if "metadata" in ts:
        check(f"{label}: tileset metadata class is in the schema",
              ts["metadata"]["class"] in (schema or {}).get("classes", {}))
    return ts


# --------------------------------------------------- a sphere with a texture
# Block noise (4x4 px cells, 512 per side): resolved by a leaf baked at the
# original density, averaged away by a 512 px atlas of the whole sphere. Any
# downsampling in between shows as a lower std of the leaf textures.
TEX = 2048
CELL = 4
rng = np.random.default_rng(7)
img = bpy.data.images.new("noise_src", TEX, TEX, alpha=False)
cells = (rng.random((TEX // CELL, TEX // CELL)) > 0.5).astype(np.float32)
noise = np.repeat(np.repeat(cells, CELL, axis=0), CELL, axis=1).ravel()
rgba = np.empty((TEX * TEX, 4), dtype=np.float32)
rgba[:, 0] = noise; rgba[:, 1] = noise; rgba[:, 2] = noise; rgba[:, 3] = 1.0
img.pixels.foreach_set(rgba.ravel())
tex_path = os.path.join(tmp, "noise_src.png")
img.filepath_raw = tex_path
img.file_format = 'PNG'
img.save()

bpy.ops.mesh.primitive_uv_sphere_add(segments=128, ring_count=64, radius=2.0)
sphere = bpy.context.active_object
sphere.name = "NAT_probe"
mat = bpy.data.materials.new("noise_mat")
mat.use_nodes = True
nt = mat.node_tree
tex = nt.nodes.new("ShaderNodeTexImage")
tex.image = img
bsdf = nt.nodes.get("Principled BSDF")
nt.links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
sphere.data.materials.append(mat)

obj_path = os.path.join(tmp, "NAT_obj.obj")
for o in bpy.data.objects:
    o.select_set(False)
sphere.select_set(True)
bpy.ops.wm.obj_export(filepath=obj_path, export_selected_objects=True, export_materials=True,
                      path_mode='ABSOLUTE')
src_faces = len(sphere.data.polygons)


def common_settings(out):
    scene.cesium_output_dir = out
    scene.cesium_create_object_subdir = True
    scene.cesium_coordinates_mode = 'LOCAL_COORDS'
    scene.cesium_archive_mode = 'FOLDER'
    scene.cesium_auto_stitch_parent = False
    scene.cesium_tree_type = 'OCTREE'
    scene.cesium_native_bake_texture_atlas = True
    scene.cesium_native_bake_texture_size = 512     # small on purpose
    scene.cesium_native_bake_margin = 8


def run():
    try:
        return bpy.ops.object.export_cesium_tiles()
    except Exception:
        traceback.print_exc()
        return None


try:
    # ------------------------------------------ 1. EXISTING_OBJ, implicit, LOD
    print("\n== EXISTING_OBJ, implicit tiling, LOD, coarse budget 800 ==")
    out = os.path.join(tmp, "existing")
    common_settings(out)
    scene.cesium_source_mode = 'EXISTING_OBJ'
    scene.cesium_existing_obj_file = obj_path
    scene.cesium_native_hierarchy_layout = 'IMPLICIT_TILING'
    scene.cesium_lod_mode = True
    scene.cesium_lod_auto_params = False
    scene.cesium_lod_strategy = 'REBAKE'
    scene.cesium_native_max_depth = 2
    scene.cesium_native_min_depth = 1
    scene.cesium_features_per_tile = 3000
    scene.cesium_lod_leaf_atlas_size = 512
    scene.cesium_lod_root_atlas_size = 256
    scene.cesium_coarse_max_triangles = 800
    scene.cesium_leaf_texture_source = 'ORIGINAL'
    objs_before = set(o.name for o in bpy.data.objects)
    mats_before = len(bpy.data.materials)
    res = run()
    check("EXISTING_OBJ export finished", res == {'FINISHED'}, str(res))
    folder = os.path.join(out, "NAT_obj")
    tsp = os.path.join(folder, "tileset.json")
    check("tileset.json written", os.path.isfile(tsp))
    check("imported object removed", set(o.name for o in bpy.data.objects) == objs_before,
          str(set(o.name for o in bpy.data.objects) ^ objs_before))
    check("imported materials removed", len(bpy.data.materials) == mats_before,
          f"{mats_before} -> {len(bpy.data.materials)}")
    if os.path.isfile(tsp):
        ts = check_tileset_schema(tsp, "implicit")
        glbs = sorted(glob.glob(os.path.join(folder, "tiles", "**", "*.glb"), recursive=True))
        tiles = {}
        for g in glbs:
            rel = os.path.relpath(g, os.path.join(folder, "tiles")).replace(".glb", "")
            tiles[tuple(int(x) for x in rel.split(os.sep))] = g
        def kids(t):
            l, x, y, z = t
            return [(l + 1, 2 * x + a, 2 * y + b, 2 * z + c) for a in (0, 1) for b in (0, 1) for c in (0, 1)]
        coarse = [t for t in tiles if any(k in tiles for k in kids(t))]
        leaves = [t for t in tiles if t not in coarse]
        root_tris = glb_read(tiles[(0, 0, 0, 0)])[0] if (0, 0, 0, 0) in tiles else None
        check("root tile within 800 triangles", root_tris is not None and root_tris <= 800, str(root_tris))
        worst = max((glb_read(tiles[t])[0] for t in coarse), default=0)
        check("every coarse tile within 800 triangles", worst <= 800, f"{len(coarse)} coarse, max {worst}")
        check("leaves exist", len(leaves) > 0, str(len(leaves)))
        info = open(os.path.join(folder, "native_backend_info.txt")).read()
        check("info: leaf texture source ORIGINAL", "Leaf texture source: ORIGINAL" in info)
        n_err = validate(tsp)
        if n_err is not None:
            check("3d-tiles-validator: 0 errors (implicit)", n_err == 0, str(n_err))

    # ------------------- 2. ORIGINAL vs ATLAS leaves, Single JSON with root
    stds = {}
    sides = {}
    for source in ("ATLAS", "ORIGINAL"):
        print(f"\n== ACTIVE_MESH, Single JSON + root content, leaves from {source} ==")
        out = os.path.join(tmp, "single_" + source.lower())
        common_settings(out)
        scene.cesium_source_mode = 'ACTIVE_MESH'
        scene.cesium_export_selected_meshes = False
        scene.cesium_native_hierarchy_layout = 'SINGLE_JSON'
        scene.cesium_singlejson_add_root_content = True
        scene.cesium_lod_mode = False
        scene.cesium_native_min_depth = 1
        scene.cesium_native_max_depth = 2
        scene.cesium_features_per_tile = 3000
        scene.cesium_coarse_max_triangles = 1000
        scene.cesium_leaf_texture_source = source
        for o in bpy.data.objects:
            o.select_set(False)
        sphere.select_set(True)
        bpy.context.view_layer.objects.active = sphere
        res = run()
        check(f"{source}: export finished", res == {'FINISHED'}, str(res))
        folder = os.path.join(out, "NAT_probe")
        tsp = os.path.join(folder, "tileset.json")
        if not os.path.isfile(tsp):
            check(f"{source}: tileset.json written", False)
            continue
        check_tileset_schema(tsp, f"single json {source}")
        root_tris = glb_read(os.path.join(folder, "Data", "root.glb"))[0]
        check(f"{source}: Single JSON root content within 1000 triangles", root_tris <= 1000,
              f"{root_tris} (source {src_faces} faces)")
        leaf_files = sorted(glob.glob(os.path.join(folder, "Data", "f*.glb")))
        s_list, w_list = [], []
        for lf in leaf_files:
            _, ims = glb_read(lf)
            for im in ims:
                w, sd = png_stats(im)
                w_list.append(w); s_list.append(sd)
        stds[source] = float(np.mean(s_list)) if s_list else 0.0
        sides[source] = w_list
        print(f"  info  {source}: {len(leaf_files)} leaves, texture sides {sorted(set(w_list))}, "
              f"leaf pixels {sum(w * w for w in w_list):,}, pure-cell texels {stds[source]:.3f}")
        n_err = validate(tsp)
        if n_err is not None:
            check(f"3d-tiles-validator: 0 errors (single json {source})", n_err == 0, str(n_err))
    if "ATLAS" in stds and "ORIGINAL" in stds:
        # through a 512 px atlas of the whole sphere the 4 px cells are
        # mixed into greys; from the original image they stay black/white
        check("ORIGINAL leaves keep more source detail than ATLAS leaves",
              stds["ORIGINAL"] > 1.5 * stds["ATLAS"],
              f"pure-cell texels ORIGINAL {stds['ORIGINAL']:.3f} vs ATLAS {stds['ATLAS']:.3f}")
        check("ORIGINAL leaves carry more pixels than the whole global atlas",
              sum(w * w for w in sides["ORIGINAL"]) > 512 * 512,
              f"{sum(w * w for w in sides['ORIGINAL']):,} vs {512 * 512:,}")
    check("nothing left in _cesium_native_tmp",
          bpy.data.collections.get("_cesium_native_tmp") is None
          or len(bpy.data.collections["_cesium_native_tmp"].objects) == 0)
finally:
    shutil.rmtree(tmp, ignore_errors=True)

print("\n" + ("ALL PASS" if not FAIL else "FAILURES:\n  " + "\n  ".join(FAIL)))
sys.exit(1 if FAIL else 0)
