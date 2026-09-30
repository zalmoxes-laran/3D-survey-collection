import bpy, os, sys, json, shutil, subprocess, tempfile, traceback, zipfile

ADDON = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
# cesium_exporter only uses relative imports inside itself: load it as a
# top-level package, without the rest of the add-on.
sys.path.insert(0, ADDON)
import cesium_exporter
from cesium_exporter import archive_3tz as tz

FAIL = []
def check(label, cond, extra=""):
    print(("  PASS  " if cond else "  FAIL  ") + label + (f"   {extra}" if extra else ""))
    if not cond:
        FAIL.append(label)

cesium_exporter.register()
scene = bpy.context.scene
check("archive props registered",
      scene.cesium_archive_mode == 'FOLDER' and scene.cesium_archive_verify is True,
      f"{scene.cesium_archive_mode}/{scene.cesium_archive_verify}")

# ---------------------------------------------------------------- a small mesh
bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=4, radius=2.0)
obj = bpy.context.active_object
obj.name = "TZ_probe"
obj.select_set(True)

scene.cesium_source_mode = 'ACTIVE_MESH'
scene.cesium_export_selected_meshes = False
scene.cesium_create_object_subdir = True
scene.cesium_coordinates_mode = 'LOCAL_COORDS'
scene.cesium_native_hierarchy_layout = 'SINGLE_JSON'
scene.cesium_native_bake_texture_atlas = False
scene.cesium_lod_mode = False
scene.cesium_native_min_depth = 1
scene.cesium_native_max_depth = 2
scene.cesium_features_per_tile = 500
scene.cesium_auto_stitch_parent = False

tmp = tempfile.mkdtemp(prefix="dsc_3tz_")
REPORT = {}


def run_export(mode, out_root):
    scene.cesium_output_dir = out_root
    scene.cesium_archive_mode = mode
    try:
        res = bpy.ops.object.export_cesium_tiles()
    except Exception:
        traceback.print_exc()
        return None
    return res


try:
    # ------------------------------------------------ Folder + .3tz
    print("\n== export with Archive = Folder + .3tz ==")
    root = os.path.join(tmp, "both")
    res = run_export('FOLDER_3TZ', root)
    folder = os.path.join(root, "TZ_probe")
    arc = folder + ".3tz"
    check("export finished", res == {'FINISHED'}, str(res))
    check("folder kept", os.path.isfile(os.path.join(folder, "tileset.json")))
    check(".3tz next to the folder, same name", os.path.isfile(arc), arc)
    if os.path.isfile(arc):
        v = tz.verify_3tz(arc, folder)
        check("verify_3tz against the folder", v["ok"], "; ".join(v["errors"][:3]))
        with zipfile.ZipFile(arc) as zf:
            names = zf.namelist()
        check("index is the last entry", names[-1] == tz.INDEX_NAME)
        REPORT["folder_3tz"] = {"entries": v["entries"], "bytes": os.path.getsize(arc),
                                "sha256": tz.sha256_file(arc)}
        # the log carries files, bytes, time and sha256
        log = scene.cesium_progress_log
        check("log line has files/bytes/sha256",
              "files" in log and "bytes" in log and REPORT["folder_3tz"]["sha256"] in log)
        # same folder, packed again by the standalone operator path: same sha
        again = os.path.join(tmp, "again.3tz")
        r2 = tz.write_3tz(folder, again)
        check("repacking the folder gives the same sha256",
              r2["sha256"] == REPORT["folder_3tz"]["sha256"], r2["sha256"][:16])

        # validator on the archive, if npx is reachable
        validator = os.environ.get("TZ_VALIDATOR") or shutil.which("npx")
        if validator:
            cmd = ([validator] if os.environ.get("TZ_VALIDATOR") else [validator, "--no-install", "3d-tiles-validator"])
            cmd += ["--tilesetFile", arc]
            try:
                p = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
                out = p.stdout + p.stderr
                REPORT["validator"] = {
                    "zip_index_valid": "Zip index is valid" in out,
                    "head": out[:600],
                }
                check("3d-tiles-validator: Zip index is valid", "Zip index is valid" in out,
                      out.splitlines()[0] if out else "")
            except Exception as exc:
                REPORT["validator"] = {"error": str(exc)}
                print(f"  SKIP  validator: {exc}")
        else:
            print("  SKIP  validator: npx not found")

    # ------------------------------------------------ Only .3tz
    print("\n== export with Archive = Only .3tz ==")
    root = os.path.join(tmp, "only")
    res = run_export('ONLY_3TZ', root)
    folder = os.path.join(root, "TZ_probe")
    arc = folder + ".3tz"
    check("export finished", res == {'FINISHED'}, str(res))
    check(".3tz written", os.path.isfile(arc))
    check("no tileset folder left", not os.path.exists(folder))
    leftovers = [n for n in os.listdir(root) if n.endswith(".tmp")] if os.path.isdir(root) else []
    check("temporary folder removed", not leftovers, str(leftovers))
    if os.path.isfile(arc):
        v = tz.verify_3tz(arc)
        check("verify_3tz (spec only)", v["ok"], "; ".join(v["errors"][:3]))
        REPORT["only_3tz"] = {"entries": v["entries"], "bytes": os.path.getsize(arc),
                              "sha256": tz.sha256_file(arc)}

    # ------------------------------------------------ Folder (unchanged)
    print("\n== export with Archive = Folder ==")
    root = os.path.join(tmp, "folder")
    res = run_export('FOLDER', root)
    check("export finished", res == {'FINISHED'}, str(res))
    check("no .3tz written", not os.path.exists(os.path.join(root, "TZ_probe.3tz")))

    # ------------------------------------------------ standalone operator
    print("\n== operator: Pack a tileset into .3tz ==")
    src = os.path.join(root, "TZ_probe")
    res = bpy.ops.object.cesium_pack_3tz(directory=src + os.sep, verify=True)
    check("operator finished", res == {'FINISHED'}, str(res))
    check("operator wrote the .3tz next to the folder", os.path.isfile(src + ".3tz"))
    bad = os.path.join(tmp, "no_tileset")
    os.makedirs(bad, exist_ok=True)
    try:
        res = bpy.ops.object.cesium_pack_3tz(directory=bad + os.sep)
    except RuntimeError as exc:                    # report ERROR raises in background
        res = {'CANCELLED'}
    check("operator refuses a folder without tileset.json", res == {'CANCELLED'}, str(res))
    ext = os.environ.get("TZ_EXTERNAL_TILESET")
    if ext and os.path.isdir(ext):
        # a foreign generator's tileset, copied first: never write inside the source
        dst = os.path.join(tmp, "external", os.path.basename(ext.rstrip("/")))
        shutil.copytree(ext, dst)
        res = bpy.ops.object.cesium_pack_3tz(directory=dst + os.sep)
        check("operator packs a foreign tileset", res == {'FINISHED'}, str(res))
        if os.path.isfile(dst + ".3tz"):
            REPORT["external"] = {"sha256": tz.sha256_file(dst + ".3tz"),
                                  "bytes": os.path.getsize(dst + ".3tz")}
finally:
    report_path = os.environ.get("TZ_REPORT_JSON")
    if report_path:
        with open(report_path, "w") as fh:
            json.dump(REPORT, fh, indent=2)
    shutil.rmtree(tmp, ignore_errors=True)

print("\n" + ("ALL PASS" if not FAIL else "FAILURES:\n  " + "\n  ".join(FAIL)))
sys.exit(1 if FAIL else 0)
