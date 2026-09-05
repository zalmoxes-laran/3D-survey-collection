import bpy, os, sys, math, tempfile, traceback

ADDON = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.dirname(ADDON))

# Import the module as part of a throwaway package so its relative imports work.
import importlib.util, types
pkg = types.ModuleType("dsc3_test")
pkg.__path__ = [ADDON]
sys.modules["dsc3_test"] = pkg
for sub in ("functions", "render_benchmark", "orthogonal_render"):
    spec = importlib.util.spec_from_file_location(f"dsc3_test.{sub}",
                                                  os.path.join(ADDON, f"{sub}.py"))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[f"dsc3_test.{sub}"] = mod
    spec.loader.exec_module(mod)
orr = sys.modules["dsc3_test.orthogonal_render"]

FAIL = []
def check(label, cond, extra=""):
    print(("  PASS  " if cond else "  FAIL  ") + label + (f"   {extra}" if extra else ""))
    if not cond:
        FAIL.append(label)

print("\n== register ==")
orr.register()
scene = bpy.context.scene
check("props registered", hasattr(scene, "ortho_render_skip_existing")
      and hasattr(scene, "ortho_render_versioning")
      and hasattr(scene, "ortho_render_res_mode")
      and hasattr(scene, "ortho_render_target_dpi"))
check("defaults are backward compatible",
      scene.ortho_render_versioning == 'OFF'
      and scene.ortho_render_skip_existing is False
      and scene.ortho_render_res_mode == 'BUCKET',
      f"{scene.ortho_render_versioning}/{scene.ortho_render_skip_existing}/{scene.ortho_render_res_mode}")

# ---------------------------------------------------------------- setup
print("\n== Setup Orthogonal Render on a 1.2 m block ==")
bpy.ops.mesh.primitive_cube_add(size=1.2, location=(0, 0, 0.6))
block = bpy.context.active_object
block.name = "ME_B1_LOD0"

blend = os.path.join(tempfile.mkdtemp(), "ortho_test.blend")
bpy.ops.wm.save_as_mainfile(filepath=blend)

r = bpy.ops.object.setup_orthogonal_render()
check("setup returns FINISHED", r == {'FINISHED'}, str(r))

cam = bpy.data.objects.get("OrthoRenderCamera")
check("camera exists and is ortho", cam is not None and cam.data.type == 'ORTHO')
check("6 markers", len(scene.timeline_markers) == 6, str(len(scene.timeline_markers)))

# ---------------------------------------------------------------- rig
print("\n== light rig ==")
pairs = orr.rig_light_objects()
check("three lamps", len(pairs) == 3, [o.name for _s, o in pairs])
names = {o.name for _s, o in pairs}
check("rim renamed (no '-Back')", "OrthoRender_TriLamp-Rim" in names
      and "OrthoRender_TriLamp-Back" not in names, sorted(names))
check("all parented to camera", all(o.parent is cam for _s, o in pairs))

for spec, o in pairs:
    ocurves = orr.action_fcurves(o.animation_data)
    dcurves = orr.action_fcurves(o.data.animation_data)
    obj_keys = sorted({fc.data_path for fc in ocurves})
    dat_keys = sorted({fc.data_path for fc in dcurves})
    nframes = len(ocurves[0].keyframe_points) if ocurves else 0
    print(f"    {o.name:28s} obj={obj_keys} data={dat_keys} keys/curve={nframes}")
    check(f"{spec['role']} keys location+rotation", set(obj_keys) >= {"location", "rotation_euler"})
    check(f"{spec['role']} keys energy (per-view intensity)", "energy" in dat_keys)
    check(f"{spec['role']} keyed on all 6 poses", nframes == 6, nframes)

check("no migration needed on a fresh rig", orr.rig_migration_issues() == [],
      orr.rig_migration_issues())

# geometry: is the key actually raking, and is it behind the framed face?
key_spec = next(s for s in orr.TRILAMP_RIG if s["role"] == "KEY")
check("key incidence is grazing (>65 deg)",
      orr.trilamp_incidence_deg(key_spec) > 65,
      f"{orr.trilamp_incidence_deg(key_spec):.1f} deg")
rim_spec = next(s for s in orr.TRILAMP_RIG if s["role"] == "RIM")
check("rim is behind the subject (>90 deg)",
      orr.trilamp_incidence_deg(rim_spec) > 90,
      f"{orr.trilamp_incidence_deg(rim_spec):.1f} deg")
energies = {s["role"]: o.data.energy for s, o in pairs}
check("key is the strongest lamp", energies["KEY"] > energies["FILL"] and energies["KEY"] > energies["RIM"],
      {k: round(v, 1) for k, v in energies.items()})
check("fill is well below key", energies["FILL"] < energies["KEY"] * 0.4,
      f"fill/key={energies['FILL']/energies['KEY']:.2f}")

# key light must sit BEHIND the framed face, i.e. deeper than the camera
scene.frame_set(1)
key_obj = next(o for s, o in pairs if s["role"] == "KEY")
depsgraph = bpy.context.evaluated_depsgraph_get()
kw = key_obj.evaluated_get(depsgraph).matrix_world.translation
cw = cam.evaluated_get(depsgraph).matrix_world.translation
subject = bpy.data.objects["OrthoRenderTarget"].matrix_world.translation
check("key lamp is closer to the subject than the camera is",
      (kw - subject).length < (cw - subject).length,
      f"key={(kw-subject).length:.2f}m cam={(cw-subject).length:.2f}m")

print("\n== per-view light editing survives ==")
scene.frame_set(3)
key_obj.data.energy = 12345.0
key_obj.location.x -= 0.5
r = bpy.ops.render.ortho_key_lights_here()
check("key-lights-here returns FINISHED", r == {'FINISHED'}, str(r))
scene.frame_set(1)
e_frame1 = key_obj.data.energy
scene.frame_set(3)
e_frame3 = key_obj.data.energy
check("frame 3 keeps the edited intensity", abs(e_frame3 - 12345.0) < 1e-3, e_frame3)
check("frame 1 is untouched", abs(e_frame1 - 12345.0) > 1.0, e_frame1)

print("\n== migration of a legacy rig ==")
# Rebuild the "before" state: bare Luci.blend names, no keys, unparented.
for _s, o in orr.rig_light_objects():
    bpy.data.objects.remove(o, do_unlink=True)
legacy = {}
for nm, kind, loc in (("Key", 'POINT', (1.0, 2.0, 3.0)),
                      ("Fill", 'POINT', (-2.5, 0.5, 1.0)),
                      ("Back", 'AREA', (0.0, 4.0, -1.5))):
    d = bpy.data.lights.new(nm, type=kind)
    o = bpy.data.objects.new(nm, d)
    scene.collection.objects.link(o)
    o.location = loc
    o.rotation_euler = (0.3, -0.2, 1.1)
    legacy[nm] = o
# matrix_world is only recomputed on depsgraph evaluation: without this the
# "before" matrices would all read as the identity.
bpy.context.view_layer.update()
world_before = {nm: o.matrix_world.copy() for nm, o in legacy.items()}
found = orr.rig_light_objects()
check("legacy names are recognised, not duplicated", len(found) == 3, [o.name for _s, o in found])
issues = orr.rig_migration_issues()
check("migration is detected", len(issues) > 0, f"{len(issues)} issues")
r = bpy.ops.render.ortho_migrate_light_rig()
check("migrate returns FINISHED", r == {'FINISHED'}, str(r))
after = orr.rig_light_objects()
check("renamed to canonical", {o.name for _s, o in after} ==
      {s["name"] for s in orr.TRILAMP_RIG}, sorted(o.name for _s, o in after))
check("migration left nothing to fix", orr.rig_migration_issues() == [],
      orr.rig_migration_issues())
scene.frame_set(1)
bpy.context.view_layer.update()
moved = []
for old_name, mw in world_before.items():
    spec = next(s for s in orr.TRILAMP_RIG if old_name in s.get("legacy_names", ()))
    o = bpy.data.objects[spec["name"]]
    dpos = (o.matrix_world.translation - mw.translation).length
    drot = max(abs(a - b) for a, b in zip(o.matrix_world.to_euler(), mw.to_euler()))
    if dpos > 1e-4 or drot > 1e-4:
        moved.append((old_name, round(dpos, 4), round(drot, 4)))
check("migration did NOT move the lamps", not moved, moved)
rig_lamps = [o.name for o in bpy.data.objects
             if o.type == 'LIGHT' and o.name.startswith("OrthoRender_TriLamp")]
check("no fourth rig lamp created", len(rig_lamps) == 3, rig_lamps)

print("\n== resolution: buckets vs scale+dpi ==")
scene.ortho_render_res_mode = 'BUCKET'
px_bucket, _ = orr.render_resolution_for(scene, block)
scene.ortho_render_res_mode = 'SCALE_DPI'
scene.ortho_template_family = 'FIXED_SCALE'
scene.ortho_render_fixed_scale_denom = '5'
scene.ortho_render_target_dpi = 600
px_scale, note = orr.render_resolution_for(scene, block)
span = orr.render_span_for(scene, block)
expected = int(round(span * 1000.0 / 5 / 25.4 * 600))
check("1:5 @600dpi matches the arithmetic", px_scale == expected, f"{px_scale} vs {expected}")
print(f"    bucket={px_bucket}px  scale+dpi={px_scale}px  span={span:.3f}m  note={note}")
scene.ortho_render_fixed_scale_denom = '1'
px_1to1, note_1to1 = orr.render_resolution_for(scene, block)
check("1:1 is capped with a warning", px_1to1 == orr.MAX_RENDER_PX and note_1to1,
      f"{px_1to1} / {note_1to1}")
denoms = [i[0] for i in orr.fixed_scale_denom_items(None, bpy.context)]
check("scale menu offers 1:1 1:5 1:10 1:20", {"1", "5", "10", "20"} <= set(denoms), denoms)

print("\n== output folder versioning ==")
scene.ortho_render_res_mode = 'BUCKET'
scene.ortho_render_versioning = 'OFF'
base = orr.output_dir_base(scene)
check("OFF resolves to the plain folder", orr.resolve_output_dir(scene) == base, base)
scene.ortho_render_versioning = 'NEW'
p1 = orr.resolve_output_dir(scene, create=True)
check("NEW creates _v01", p1.endswith("_v01") and os.path.isdir(p1), p1)
p2 = orr.resolve_output_dir(scene, create=True)
check("NEW again creates _v02", p2.endswith("_v02"), p2)
scene.ortho_render_versioning = 'LATEST'
p3 = orr.resolve_output_dir(scene)
check("LATEST reads the newest version", p3 == p2, f"{p3} vs {p2}")
scene.ortho_render_versioning = 'NEW'
check("a READ never invents a new version", orr.resolve_output_dir(scene) == p2,
      orr.resolve_output_dir(scene))
check("label announces the next folder", "_v03 (new)" in orr.output_dir_label(scene),
      orr.output_dir_label(scene))

print("\n== render 6 views, then skip-existing ==")
scene.ortho_render_versioning = 'OFF'
scene.ortho_render_engine = 'BLENDER_EEVEE'
scene.ortho_render_samples = 1
scene.ortho_render_small_resolution = 64
scene.ortho_render_medium_resolution = 64
scene.ortho_render_large_resolution = 64
scene.ortho_render_xlarge_resolution = 64
bpy.context.view_layer.objects.active = block
block.select_set(True)
r = bpy.ops.render.orthogonal_views()
check("render returns FINISHED", r == {'FINISHED'}, str(r))
out = orr.resolve_output_dir(scene)
pngs = sorted(f for f in os.listdir(out) if f.endswith(".png"))
check("six PNGs written", len(pngs) == 6, pngs)

os.remove(os.path.join(out, f"{block.name}_TO.png"))
mtimes = {f: os.path.getmtime(os.path.join(out, f))
          for f in os.listdir(out) if f.endswith(".png")}
scene.ortho_render_skip_existing = True
r = bpy.ops.render.orthogonal_views()
check("skip-existing render returns FINISHED", r == {'FINISHED'}, str(r))
pngs2 = sorted(f for f in os.listdir(out) if f.endswith(".png"))
check("the deleted view came back", len(pngs2) == 6, pngs2)
touched = [f for f, t in mtimes.items()
           if os.path.getmtime(os.path.join(out, f)) != t]
check("the five surviving views were NOT re-rendered", not touched, touched)

print("\n== B/W pass ==")
before_energy = {o.name: o.data.energy for _s, o in orr.rig_light_objects()}
before_look = (scene.view_settings.view_transform, scene.view_settings.look,
               scene.render.image_settings.color_mode)
scene.ortho_render_skip_existing = False
r = bpy.ops.render.orthogonal_views_bw()
check("B/W pass returns FINISHED", r == {'FINISHED'}, str(r))
bwdir = os.path.join(out, "bw")
bws = sorted(os.listdir(bwdir)) if os.path.isdir(bwdir) else []
check("six _BW files in bw/", len([f for f in bws if f.endswith(".png")]) == 6, bws)
after_look = (scene.view_settings.view_transform, scene.view_settings.look,
              scene.render.image_settings.color_mode)
check("colour management restored", before_look == after_look, f"{before_look} -> {after_look}")
after_energy = {o.name: o.data.energy for _s, o in orr.rig_light_objects()}
check("light energies restored", before_energy == after_energy,
      f"{before_energy} -> {after_energy}")
check("no F-curve left muted",
      not any(fc.mute for _s, o in orr.rig_light_objects()
              for fc in orr.action_fcurves(o.data.animation_data)))

print("\n== panels draw without error ==")
for cls in (orr.VIEW3D_PT_orthogonal_render, orr.VIEW3D_PT_ortho_framing_sizing,
            orr.VIEW3D_PT_ortho_resolution, orr.VIEW3D_PT_ortho_quality):
    check(f"{cls.__name__} registered", cls.is_registered)

orr.unregister()
check("unregister clean", not hasattr(bpy.context.scene, "ortho_render_skip_existing"))

print("\n" + "=" * 60)
print(("ALL PASS" if not FAIL else f"{len(FAIL)} FAILURES: " + "; ".join(FAIL)))
print("=" * 60)
