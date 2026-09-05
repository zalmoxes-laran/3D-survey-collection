import bpy, os, sys, types, importlib.util, tempfile, re
ADDON = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
pkg = types.ModuleType("dsc3_svg"); pkg.__path__ = [ADDON]; sys.modules["dsc3_svg"] = pkg
for sub in ("functions", "render_benchmark", "orthogonal_render"):
    spec = importlib.util.spec_from_file_location(f"dsc3_svg.{sub}", os.path.join(ADDON, f"{sub}.py"))
    m = importlib.util.module_from_spec(spec); sys.modules[f"dsc3_svg.{sub}"] = m; spec.loader.exec_module(m)
orr = sys.modules["dsc3_svg.orthogonal_render"]
orr.register()
scene = bpy.context.scene
FAIL = []
def check(label, cond, extra=""):
    print(("  PASS  " if cond else "  FAIL  ") + label + (f"   {extra}" if extra else ""))
    if not cond: FAIL.append(label)

bpy.ops.mesh.primitive_cube_add(size=0.6, location=(0,0,0.3))
block = bpy.context.active_object; block.name = "ME_B7_LOD0"
bpy.ops.wm.save_as_mainfile(filepath=os.path.join(tempfile.mkdtemp(), "svg.blend"))
bpy.ops.object.setup_orthogonal_render()

scene.ortho_render_engine = 'BLENDER_EEVEE'
scene.ortho_render_samples = 1
for p in ("small","medium","large","xlarge"):
    setattr(scene, f"ortho_render_{p}_resolution", 64)

print("\n== SVG export with versioning ON (the refactor's real risk) ==")
scene.ortho_render_versioning = 'NEW'
bpy.context.view_layer.objects.active = block
bpy.ops.render.orthogonal_views()
out = orr.resolve_output_dir(scene)
check("renders landed in a version folder", out.endswith("_v01") and
      len([f for f in os.listdir(out) if f.endswith(".png")]) == 6, out)

scene.ortho_template_family = 'FIXED_SHEET'
r = bpy.ops.render.create_orthogonal_svg('EXEC_DEFAULT', document_name="tavola_B7",
                                         template_name="FIXED_A3_50cm",
                                         measurement_unit='cm')
check("SVG export returns FINISHED", r == {'FINISHED'}, str(r))
svg = os.path.join(out, "tavola_B7.svg")
check("SVG written next to the renders it used", os.path.exists(svg), svg)
if os.path.exists(svg):
    content = open(svg, encoding="utf-8").read()
    hrefs = re.findall(r'href="([^"]+)"', content)
    pngs = [h for h in hrefs if h.endswith(".png")]
    # Hrefs are written relative to the plate's own folder, so what matters is
    # that they resolve INSIDE the version folder — that is what makes a
    # version self-contained and stops the plate pointing at another version.
    resolved = [os.path.normpath(os.path.join(os.path.dirname(svg), p)) for p in pngs]
    check("plate references exist and live in this version folder",
          bool(resolved) and all(os.path.exists(p) and os.path.dirname(p) == out
                                 for p in resolved),
          [os.path.relpath(p, out) for p in resolved][:3])
    check("plate uses the six views of this version",
          len([p for p in resolved if "ME_B7_LOD0_" in p]) == 6,
          len([p for p in resolved if "ME_B7_LOD0_" in p]))
    m = re.search(r'Scala 1:(\d+)', content)
    check("scale caption present", bool(m), m.group(0) if m else "none")

print("\n== a second version does not confuse the export ==")
bpy.ops.render.orthogonal_views()
out2 = orr.resolve_output_dir(scene)
check("second render made _v02", out2.endswith("_v02"), out2)
r = bpy.ops.render.create_orthogonal_svg('EXEC_DEFAULT', document_name="tavola_B7",
                                         template_name="FIXED_A3_50cm")
check("export follows to the latest version", os.path.exists(os.path.join(out2, "tavola_B7.svg")))

print("\n== SCALE_DPI + FIXED_SCALE end to end ==")
scene.ortho_render_versioning = 'OFF'
scene.ortho_render_res_mode = 'SCALE_DPI'
scene.ortho_template_family = 'FIXED_SCALE'
scene.ortho_render_fixed_scale_denom = '5'
scene.ortho_render_target_dpi = 300
px, note = orr.render_resolution_for(scene, block)
bpy.ops.render.orthogonal_views()
check("render used the derived resolution", scene.render.resolution_x == px,
      f"{scene.render.resolution_x} vs {px}")
r = bpy.ops.render.create_orthogonal_svg('EXEC_DEFAULT', document_name="tavola_5",
                                         template_name="SCALE_1-5_A2_50cm")
check("fixed-scale plate exported", r == {'FINISHED'}, str(r))
plate = os.path.join(orr.resolve_output_dir(scene), "tavola_5.svg")
if os.path.exists(plate):
    c = open(plate, encoding="utf-8").read()
    m = re.search(r'Scala 1:(\d+)', c)
    check("plate says 1:5", m and m.group(1) == "5", m.group(0) if m else "none")

orr.unregister()
print("\n" + ("ALL PASS" if not FAIL else f"{len(FAIL)} FAILURES: " + "; ".join(FAIL)))
