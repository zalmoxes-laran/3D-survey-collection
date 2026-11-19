"""Headless smoke of the geophysics import on the embedded core (row G6).

    "/Applications/Blender 520.app/Contents/MacOS/Blender" -b --factory-startup \\
        --python-exit-code 1 --python dev_utils/tests/test_geofisica_import.py

Loads ``importer/import_gpr.py`` (and the core embedded in
``importer/_vendor``) without the rest of the add-on, on a factory-startup
scene, everything written in a temporary folder (``S3DGRAPHY_PLUGINS_DATA_DIR``
there too). Synthetic stacks: a CSV stack (3DSC's own cache, draped on a
declared ground), an ASCII stack Basilica-like (two slices with their own
grids, one section standing upright, a declared value scale), GeoTIFF
rasters (EPSG:25830, the scene shift proposed and applied), screen captures
decoded by Blender. With ``GEO_BASILICA=<folder of sezioni-2D>`` the real
Basilica Iulia files too (read only; the cache in the temporary folder).
Prints PASS/FAIL per check and ends with ``ALL PASS`` or the failures.
"""
import importlib
import importlib.util
import json
import math
import os
import shutil
import sys
import tempfile
import time
import traceback
import types

import bpy
import numpy as np

ADDON = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
TMP = tempfile.mkdtemp(prefix="dsc_geo_")
os.environ["S3DGRAPHY_PLUGINS_DATA_DIR"] = os.path.join(TMP, "plugins-data")

# the importer package alone, under a parent that does not run the add-on's __init__
pkg = types.ModuleType("dsc_smoke")
pkg.__path__ = [ADDON]
sys.modules["dsc_smoke"] = pkg
gpr = importlib.import_module("dsc_smoke.importer.import_gpr")
core = gpr.core

FAIL = []
TIMES = {}


def check(label, cond, extra=""):
    print(("  PASS  " if cond else "  FAIL  ") + label + (f"   {extra}" if extra else ""))
    if not cond:
        FAIL.append(label)


# the scene shift the 3DSC add-on registers (shift.py), here without it
S = bpy.types.Scene
for name in ("BL_x_shift", "BL_y_shift", "BL_z_shift"):
    if not hasattr(S, name):
        setattr(S, name, bpy.props.FloatProperty(name=name, default=0.0))
if not hasattr(S, "BL_epsg"):
    S.BL_epsg = bpy.props.StringProperty(name="BL_epsg", default="NotSet")
gpr.register()
scene = bpy.context.scene
s = scene.gpr_settings


def stamp_of(path):
    with open(path + ".stamp.json", "r", encoding="utf-8") as fh:
        return json.load(fh)


def slices_of(root):
    return sorted([o for o in root.children if gpr.SLICE_IDX_PROP in o],
                  key=lambda o: o[gpr.SLICE_IDX_PROP])


def write_csv_stack(folder, nx=24, ny=16, step=0.05):
    os.makedirs(folder)
    for k, (top, bot) in enumerate(((0.0, 0.1), (0.1, 0.2), (0.2, 0.3))):
        d = 0.5 * (top + bot)
        lines = ["X \xb1 %.4fm, Y \xb1 %.4fm, Z \xb1 %.4fm, Depth \xb1 %.4fm, Amplitude"
                 % (step, step, -d, d)]
        for j in range(ny):
            for i in range(nx):
                inside = ((i - nx / 2) / (nx / 2)) ** 2 + ((j - ny / 2) / (ny / 2)) ** 2 <= 1
                lines.append("%.4f, %.4f, %.4f, %.4f," % (i * step, j * step, -d, d)
                             + (" %.3f" % (10 + k + i * 0.5 + math.sin(j)) if inside else ""))
        with open(os.path.join(folder, "slice_%.3f - %.3fm.CSV" % (top, bot)), "wb") as fh:
            fh.write(("\r\n".join(lines) + "\r\n").encode("latin-1"))


def write_ascii_stack(folder):
    os.makedirs(folder)
    a = np.zeros((10, 18), dtype=int)
    a[1:9, 1:17] = np.arange(16 * 8).reshape(8, 16) % 254 + 1
    np.savetxt(os.path.join(folder, "100-150cm.ASC"), a, fmt="%d")
    np.savetxt(os.path.join(folder, "250-300cm.ASC"), a[:, :-2], fmt="%d")   # its own grid
    np.savetxt(os.path.join(folder, "VERT-1-OK.ASC"), a.T[:, :6], fmt="%d")


def write_geotiffs(folder, e0=701756.963, n0=4234861.282, step=0.1):
    from importlib import import_module
    gt = import_module(core.__name__ + ".readers._geotiff")
    os.makedirs(folder)
    nod = -3.4028234663852886e38
    rows = [[(nod if (i + j) % 11 == 0 else float(400 + i * j)) for i in range(20)]
            for j in range(12)]
    for name in ("mean_v2.tif", "sqmean_v2.tif"):
        gt.write_geotiff(os.path.join(folder, name), rows, affine=(e0, step, 0.0, n0, 0.0, -step),
                         epsg=25830, nodata=nod)
        rows = [[v * v if v != nod else v for v in r] for r in rows]


def write_captures(folder, w=80, h=50):
    os.makedirs(folder)
    for depth_mm in (0, 5):
        img = bpy.data.images.new("cap", w, h, alpha=False)
        px = np.zeros((h, w, 4), dtype=np.float32)
        px[..., 3] = 1.0
        px[10:40, 15:70, 0] = 0.9 - 0.2 * depth_mm / 5.0   # the plot (bottom-up rows)
        px[10:40, 15:70, 1] = 0.3 + 0.1 * depth_mm / 5.0
        img.pixels.foreach_set(px.ravel())
        img.filepath_raw = os.path.join(folder, "Slice_%05dmm.png" % -depth_mm
                                        if depth_mm else "Slice_00000mm.png")
        img.file_format = 'PNG'
        img.save()
        bpy.data.images.remove(img)


try:
    # ------------------------------------------------------------ CSV (legacy)
    print("\n== CSV stack, 3DSC's cache, draped on a declared ground ==")
    src = os.path.join(TMP, "Tivoli")
    write_csv_stack(src)
    s.stack_kind = 'CSV'
    s.source_dir = src
    s.cache_dir = ""
    bpy.ops.gpr.set_source(directory=src + os.sep)
    check("set_source keeps CSV", s.stack_kind == 'CSV', s.stack_kind)
    cache = gpr._cache_dir(s)
    t0 = time.time()
    m = core.build_cache(src, cache, colormap="GRAY", software=gpr._software())
    TIMES["csv_cache"] = round(time.time() - t0, 3)
    check("CSV cache beside the slices as before", cache.endswith("_3dsc_gpr_cache")
          and os.path.isfile(os.path.join(cache, core.MANIFEST_NAME)))
    st = stamp_of(os.path.join(cache, m["slices"][0]["raster"]))
    sw = st["how"]["software"]
    check("stamp names 3DSC first", sw[0]["name"] == "3D Survey Collection" and "version" in sw[0],
          str(sw[0]))
    lock = json.load(open(os.path.join(ADDON, "scripts", "geofisica_core.lock.json")))
    check("stamp names the core and its em-profiles commit",
          sw[-1].get("name") == "geofisica_core" and sw[-1].get("commit") == lock["commit"][:7],
          str(sw[-1]))
    bpy.ops.mesh.primitive_plane_add(size=4.0, location=(0.6, 0.4, 2.0))
    ground = bpy.context.active_object
    bpy.ops.gpr.mark_ground()
    s.drape_mode = 'GRID'
    s.drape_resolution = 8
    res = bpy.ops.gpr.import_stack()
    check("import CSV stack", res == {'FINISHED'}, str(res))
    root = bpy.data.objects.get("GPR_Tivoli")
    obs = slices_of(root) if root else []
    check("three slices, one shared drape mesh", len(obs) == 3
          and len({o.data.name for o in obs}) == 1, str([o.data.name for o in obs]))
    check("gpr: identity unchanged", obs and obs[0]["em_document_id"] == "gpr:Tivoli#d0.000-0.100m",
          obs[0]["em_document_id"] if obs else "")
    check("drape on the ground (z = 2)", obs and abs(
        max((root.matrix_world @ v.co).z for v in obs[0].data.vertices) - 2.0) < 1e-3)
    s.drape_mode = 'FLAT'

    # ------------------------------------------------------------ ASCII (new)
    print("\n== ASCII matrices + a section, Basilica-like, core cache ==")
    src = os.path.join(TMP, "Basilica")
    write_ascii_stack(src)
    s.source_dir = src
    bpy.ops.gpr.set_source(directory=src + os.sep)
    check("set_source guesses ASCII", s.stack_kind == 'ASCII', s.stack_kind)
    s.method = 'ert'
    s.colormap = 'AUTO'
    s.extent = "92 x 50"
    s.sections = "VERT1=50x8"
    s.use_value_scale = True
    s.vs_source = "figure colour bar"
    s.origin_e, s.origin_n = "0", "0"
    res = bpy.ops.gpr.build_stack_cache()
    check("build_stack_cache ASCII", res == {'FINISHED'}, str(res))
    check("cache in plugins-data, not beside", s.built_cache.startswith(
        os.environ["S3DGRAPHY_PLUGINS_DATA_DIR"]) and not os.path.exists(
        os.path.join(src, "_3dsc_gpr_cache")), s.built_cache)
    m = core.load_manifest(s.built_cache)
    check("jet for ERT, scale declared", m["colormap"] == "jet"
          and m["stack"]["value_scale"]["unit"] == "ohm.m")
    res = bpy.ops.gpr.import_stack()
    check("import ASCII stack", res == {'FINISHED'}, str(res))
    root = bpy.data.objects.get("ERT_Basilica")
    obs = slices_of(root) if root else []
    ids = [o["em_document_id"] for o in obs]
    check("ert: identities", ids == ["ert:Basilica#d1.000-1.500m", "ert:Basilica#d2.500-3.000m",
                                     "ert:Basilica#sVERT1"], str(ids))
    if len(obs) == 3:
        w0 = max(v.co.x for v in obs[0].data.vertices) - min(v.co.x for v in obs[0].data.vertices)
        check("slice 1 is 92 m wide", abs(w0 - 92.0) < 1e-3, "%.3f" % w0)
        check("slice 2 has a plane of its own", obs[1].data != obs[0].data)
        sec = obs[2]
        zs = [v.co.z for v in sec.data.vertices]
        xs = [v.co.x for v in sec.data.vertices]
        check("the section stands: 50 m along, 8 m down",
              abs(max(xs) - min(xs) - 50.0) < 1e-3 and abs(min(zs) + 8.0) < 1e-3
              and abs(max(zs)) < 1e-3, "x %.2f z %.2f..%.2f" % (max(xs) - min(xs), min(zs), max(zs)))
        check("section kind and line", sec["em_document_kind"] == "ert_section"
              and sec["geo_line"] == "VERT1")
        check("slices at -depth", abs(obs[0].location.z + 1.25) < 1e-6
              and abs(obs[1].location.z + 2.75) < 1e-6)
        check("each slice names its stamp", all(os.path.isfile(o["geo_stamp"]) for o in obs))
    check("value scale on the stack", json.loads(root["geo_value_scale"])["to"] == [0.0, 3500.0])

    # ------------------------------------------------------------ GeoTIFF (new)
    print("\n== GeoTIFF, EPSG:25830, the shift ==")
    src = os.path.join(TMP, "Sector 1")
    write_geotiffs(src)
    s.source_dir = src
    s.method = 'gpr'
    s.use_value_scale = False
    s.normalize = 'SLICE'
    bpy.ops.gpr.set_source(directory=src + os.sep)
    check("set_source guesses GEOTIFF", s.stack_kind == 'GEOTIFF', s.stack_kind)
    res = bpy.ops.gpr.build_stack_cache()
    check("build_stack_cache GeoTIFF", res == {'FINISHED'}, str(res))
    # a shift passed by a script is the one written, not the one proposed (701750:
    # row G16 c, MICRO-GEO15 asked 701800 / 4234800 and the scene got 701750)
    op_res = bpy.ops.gpr.import_stack('EXEC_DEFAULT', shift_e=701700.0, shift_n=4234800.0,
                                      write_shift=True)
    check("import GeoTIFF stack", op_res == {'FINISHED'}, str(op_res))
    root = bpy.data.objects.get("GPR_Sector 1")
    obs = slices_of(root) if root else []
    ids = [o["em_document_id"] for o in obs]
    check("products, no invented depth", ids == ["gpr:Sector 1#mean_v2", "gpr:Sector 1#sqmean_v2"]
          and all("gpr_depth_top" not in o for o in obs) and all(o.location.z == 0 for o in obs),
          str(ids))
    check("the shift passed written, EPSG taken", abs(scene.BL_x_shift - 701700.0) < 1e-6
          and abs(scene.BL_y_shift - 4234800.0) < 1e-6 and scene.BL_epsg == "25830",
          "%s %s %s" % (scene.BL_x_shift, scene.BL_y_shift, scene.BL_epsg))
    check("origin kept to the millimetre on the root", root["gpr_origin_e"] == "701756.963000",
          root["gpr_origin_e"])
    check("root at origin - shift", abs(root.location.x - 56.963) < 1e-2, "%.4f" % root.location.x)

    # ------------------------------------------------------------ captures (new)
    print("\n== screen captures, decoded by Blender ==")
    src = os.path.join(TMP, "Sector1_Alcudia")
    write_captures(src)
    s.source_dir = src
    s.stack_kind = 'SCREENSHOT'
    bpy.ops.gpr.set_source(directory=src + os.sep)
    check("set_source keeps SCREENSHOT", s.stack_kind == 'SCREENSHOT', s.stack_kind)
    s.frame_x, s.frame_y = "-5, 5", "-2, 2"
    s.frame_px = "15, 10, 69, 39"
    s.origin_e, s.origin_n, s.epsg = "701806.741", "4234824.081", "25830"
    res = bpy.ops.gpr.build_stack_cache()
    check("build_stack_cache captures", res == {'FINISHED'}, str(res))
    m = core.load_manifest(s.built_cache)
    check("no false «same values» on two captures", not m["warnings"], str(m["warnings"])[:120])
    check("captures placed at the typed origin", m and abs(m["georef"]["origin_e"] - 701806.741) < 1e-6
          and m["georef"]["epsg"] == 25830, str(m and m["georef"]))
    res = bpy.ops.gpr.import_stack('EXEC_DEFAULT', write_shift=False)
    check("import captures", res == {'FINISHED'}, str(res))
    root = bpy.data.objects.get("GPR_Sector1_Alcudia")
    obs = slices_of(root) if root else []
    check("two capture slices, 5 mm apart", len(obs) == 2, str(len(obs)))

    # ------------------------------------------------------------ the real Basilica
    real = os.environ.get("GEO_BASILICA")
    if real and os.path.isdir(real):
        print("\n== the real Basilica Iulia (read only) ==")
        before = {n: os.path.getmtime(os.path.join(real, n)) for n in os.listdir(real)}
        s.source_dir = real
        bpy.ops.gpr.set_source(directory=real.rstrip(os.sep) + os.sep)
        s.method, s.colormap, s.normalize = 'ert', 'AUTO', 'STACK'
        s.extent = "92 x 50"
        s.sections = "VERT1=50x8; VERT2=92x9; VERT3=92x9; VERT4=92x9; VERT5=50x8; VERT6=50x8"
        s.use_value_scale = True
        s.vs_source = "risultati-fori.pdf p. 5"
        s.origin_e, s.origin_n, s.epsg = "0", "0", ""
        s.cache_dir = os.path.join(TMP, "basilica-cache")
        t0 = time.time()
        res = bpy.ops.gpr.build_stack_cache()
        TIMES["basilica_cache"] = round(time.time() - t0, 3)
        check("Basilica cached", res == {'FINISHED'}, str(res))
        t0 = time.time()
        res = bpy.ops.gpr.import_stack()
        TIMES["basilica_import"] = round(time.time() - t0, 3)
        root = bpy.data.objects.get("ERT_" + os.path.basename(os.path.normpath(real)))
        obs = slices_of(root) if root else []
        check("12 documents in the scene", len(obs) == 12, str(len(obs)))
        check("6 sections standing", sum(o["geo_orientation"] == "vertical" for o in obs) == 6)
        after = {n: os.path.getmtime(os.path.join(real, n)) for n in os.listdir(real)}
        check("source folder untouched", before == after)
        s.cache_dir = ""
except Exception:
    traceback.print_exc()
    FAIL.append("exception")
finally:
    print("TIMES", json.dumps(TIMES))
    shutil.rmtree(TMP, ignore_errors=True)

print("\nALL PASS" if not FAIL else "\nFAILURES: " + ", ".join(FAIL))
if FAIL:
    sys.exit(1)
