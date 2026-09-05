# Ortho render tests

Headless regression tests for `orthogonal_render.py`. They run against a real
Blender, on a factory-startup scene in a temporary folder — they never touch an
open project.

```bash
"/Applications/Blender 510.app/Contents/MacOS/Blender" -b --factory-startup \
    --python dev_utils/tests/test_orthogonal_render.py
"/Applications/Blender 510.app/Contents/MacOS/Blender" -b --factory-startup \
    --python dev_utils/tests/test_orthogonal_render_svg.py
```

Each script prints one PASS/FAIL line per check and ends with `ALL PASS` or the
list of failures.

`test_orthogonal_render.py` covers the light rig (raking geometry, key/fill
ratio, keyframes on all six poses including intensity), the migration of a
legacy rig, skip-existing, output-folder versioning and the B/W pass.
`test_orthogonal_render_svg.py` covers the SVG export against the versioned
output folder and the scale+DPI resolution mode.

Two things they deliberately assert, because both have already been broken
once:

* `matrix_world` is only recomputed on depsgraph evaluation — call
  `bpy.context.view_layer.update()` before reading it, or a "did it move?"
  check silently compares against the identity matrix.
* F-curves are read through `orthogonal_render.action_fcurves()`. Blender 5.x
  has no `Action.fcurves`; the curves live in the channelbag of the slot.
