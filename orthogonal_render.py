import bpy
import os
import re
import math
from mathutils import Vector, Matrix
from bpy.props import EnumProperty, IntProperty, StringProperty, BoolProperty, FloatProperty
from bpy.types import Panel, Operator
from .functions import make_path_relative
from . import render_benchmark

# Constants
SIZE_CATEGORIES = [
    ("SMALL", "Small (≤ 50cm)", "Objects up to 50cm", 0.5),
    ("MEDIUM", "Medium (≤ 1m)", "Objects between 50cm and 1m", 1.0),
    ("LARGE", "Large (≤ 2m)", "Objects between 1m and 2m", 2.0),
    ("XLARGE", "Extra Large (> 2m)", "Objects larger than 2m", 3.0)
]

# Camera positions for the six standard views. The tuple is
# (code, label, description, direction, rotation) where `direction` is the
# offset from the target to the camera. NOTE: Right/Left and Top/Bottom were
# previously on the wrong side (e.g. "Top" sat BELOW the object looking up),
# which swapped those views in the layout (Rachele/Tommaso feedback). Fixed so
# each labelled view is shot from the correct side: Right = +X, Left = -X,
# Top = above (+Z) looking down, Bottom = below (-Z) looking up.
CAMERA_POSITIONS = [
    ("FR", "Front", "Front view", (0, -1, 0), (0, 0, 0)),
    ("BA", "Back", "Back view", (0, 1, 0), (0, 0, math.pi)),
    ("RI", "Right", "Right view (+X)", (1, 0, 0), (0, 0, math.pi/2)),
    ("LE", "Left", "Left view (-X)", (-1, 0, 0), (0, 0, -math.pi/2)),
    ("TO", "Top", "Top view (above, looking down)", (0, 0, 1), (math.pi/2, 0, 0)),
    ("BO", "Bottom", "Bottom view (below, looking up)", (0, 0, -1), (-math.pi/2, 0, 0))
]

RESOLUTION_PRESETS = [
    ("LOW", "Low (2000x2000)", "2000x2000 pixels", 2000),
    ("MED", "Medium (4000x4000)", "4000x4000 pixels", 4000),
    ("HIGH", "High (6000x6000)", "6000x6000 pixels", 6000)
]

# True-scale denominators, agreed with Rachele/Tommaso: small pieces print at
# 1:10, medium/large at 1:20; a piece that would overflow its layout box climbs
# the ladder to the first round scale that fits (1:25, 1:50, ...).
SCALE_LADDER = [10, 20, 25, 50, 100, 200, 500, 1000]

# Candidate real-world total lengths (metres) for the graphic scale bar,
# 1-2-2.5-5 series: the largest one that fits the template's bar space is used.
SCALE_BAR_LENGTHS_M = [0.1, 0.2, 0.25, 0.5, 1, 2, 2.5, 5, 10, 20, 25, 50, 100, 200, 500]

# 1x1 fully transparent PNG (data URI). Used for the logo slot when no logo is
# set, so nothing shows — an empty href would render a broken-image box.
TRANSPARENT_PNG_URI = (
    "data:image/png;base64,"
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
)

# ---------------------------------------------------------------------------
# Three-point "TriLamp" light rig
#
# The rig descends from Rachele's reference Luci.blend, but it is no longer
# stored as raw camera-space vectors: those were impossible to reason about and
# hid the fact that the key light was almost frontal (~24 degrees off the face
# normal), so it produced no raking light at all. Each lamp is now described by
# three angles around the SUBJECT:
#
#   azimuth   degrees around the vertical axis, measured from the camera axis.
#             0 = between camera and subject (frontal), +/-90 = at the subject's
#             own depth (fully raking on the framed face), >90 = behind it.
#   elevation degrees above the horizontal plane through the subject.
#   distance  distance from the subject centre, in units of the object size.
#
# The incidence angle on the framed face follows from those two angles
# (see `trilamp_incidence_deg`): 0 = flat frontal light, 90 = perfectly
# grazing. Key sits at ~76 degrees, which is what "radente" actually means.
#
# `ratio` is the lamp's power relative to the key, corrected for its distance,
# so the printed ratios (key 1.00, fill 0.20, rim 0.35) are the ratios that
# actually reach the stone rather than raw wattages. The old rig had the FILL
# as the brightest lamp of the three (250 W against the key's 150 W).
#
# Positions are computed in CAMERA space and applied with
# matrix_parent_inverse = Identity, so the rig orbits rigidly with the viewpoint
# and every view — including the 180-degree-rolled Bottom — is lit from the same
# image-relative direction. Location, rotation AND energy are keyframed on every
# pose so a single view can be re-lit by hand.
#
# `legacy_names` lets an existing scene be adopted instead of duplicated: the
# rim lamp used to be called "-Back", and rigs appended straight from
# Luci.blend carry the bare names Key/Fill/Back.
# ---------------------------------------------------------------------------
LIGHT_RIG_COLLECTION = "OrthoRender_Lights"
LIGHT_RIG_SIZE_REF = 1.0  # meters: object size the reference rig was tuned for
LIGHT_RIG_KEY_ENERGY = 200.0  # watts for the key on a LIGHT_RIG_SIZE_REF object

TRILAMP_RIG = [
    {
        "name": "OrthoRender_TriLamp-Key",
        "legacy_names": ("Key", "OrthoRender_TriLamp-Key"),
        "role": "KEY",
        "type": "POINT",
        "color": (1.0, 1.0, 1.0),
        # Raking: pushed back almost to the subject's own depth, low over it.
        "azimuth": -75.0,
        "elevation": 20.0,
        "distance": 1.8,
        "ratio": 1.0,
    },
    {
        "name": "OrthoRender_TriLamp-Fill",
        "legacy_names": ("Fill", "OrthoRender_TriLamp-Fill"),
        "role": "FILL",
        "type": "POINT",
        "color": (1.0, 1.0, 1.0),
        # Opposite side, high-ish, deliberately weak: it opens the shadows the
        # key carves without flattening them.
        "azimuth": 45.0,
        "elevation": 10.0,
        "distance": 2.2,
        "ratio": 0.20,
    },
    {
        "name": "OrthoRender_TriLamp-Rim",
        # "-Back" is the pre-1.7.0-dev.16 name; "Back" comes from Luci.blend.
        "legacy_names": ("OrthoRender_TriLamp-Back", "Back", "OrthoRender_TriLamp-Rim"),
        "role": "RIM",
        "type": "AREA",
        "color": (1.0, 1.0, 1.0),
        # Genuinely behind the subject (azimuth > 90), so it detaches the
        # silhouette from the transparent film instead of lighting the face.
        "azimuth": 150.0,
        "elevation": 35.0,
        "distance": 2.0,
        "ratio": 0.35,
        "shape": "SQUARE",
        "size": 1.0,
        "size_y": 0.25,
    },
]

# Channels keyframed on every pose. Object-level channels are keyed on the
# light OBJECT, data-level ones on the light DATA (energy lives on the data,
# which is why per-view intensity was not adjustable before dev.16).
LIGHT_OBJECT_CHANNELS = ("location", "rotation_euler")
LIGHT_DATA_CHANNELS = ("energy", "color")
LIGHT_DATA_AREA_CHANNELS = ("size", "size_y")


def trilamp_incidence_deg(spec):
    """Angle between the lamp direction and the framed face's normal, degrees.

    0 = flat frontal light, 90 = perfectly grazing, >90 = behind the subject.
    Depends only on the two angles, not on the object size.
    """
    az = math.radians(spec["azimuth"])
    el = math.radians(spec["elevation"])
    return math.degrees(math.acos(max(-1.0, min(1.0, math.cos(el) * math.cos(az)))))


def trilamp_pose(spec, max_dim, camera_distance):
    """Camera-space (location, rotation_euler) for one rig lamp.

    Camera convention: +X right, +Y up, -Z toward the subject; the subject
    centre sits at (0, 0, -camera_distance). The lamp is placed on the sphere
    around that centre described by the spec's angles, then aimed back at it
    (which only matters for the AREA rim, but is harmless for the points).
    """
    az = math.radians(spec["azimuth"])
    el = math.radians(spec["elevation"])
    d = spec["distance"] * max(max_dim, 1e-4)
    subject = Vector((0.0, 0.0, -camera_distance))
    offset = Vector((
        d * math.cos(el) * math.sin(az),
        d * math.sin(el),
        d * math.cos(el) * math.cos(az),
    ))
    location = subject + offset
    rotation = (subject - location).normalized().to_track_quat('-Z', 'Y').to_euler()
    return location, rotation


def trilamp_energy(spec, factor):
    """Watts for one lamp on an object `factor` times the reference size.

    `ratio` is the share of the key's illumination that should reach the
    subject, so the raw power is corrected by the inverse-square distance
    penalty of the lamp's own standoff. Power then scales with factor**2 to
    keep the irradiance constant as the object grows.
    """
    key = next((s for s in TRILAMP_RIG if s.get("role") == "KEY"), TRILAMP_RIG[0])
    dist_penalty = (spec["distance"] / key["distance"]) ** 2
    return LIGHT_RIG_KEY_ENERGY * spec["ratio"] * dist_penalty * factor * factor


def find_rig_light(spec):
    """Return the scene light object for a rig spec, canonical name first.

    Looking up the legacy names is what stops the tool from silently building a
    fourth lamp next to a rig that came from an older 3DSC or straight from
    Luci.blend.
    """
    obj = bpy.data.objects.get(spec["name"])
    if obj is not None and obj.type == 'LIGHT':
        return obj
    for legacy in spec.get("legacy_names", ()):
        obj = bpy.data.objects.get(legacy)
        if obj is not None and obj.type == 'LIGHT':
            return obj
    return None


def rig_light_objects():
    """Every rig lamp currently in the file, as (spec, object) pairs."""
    out = []
    for spec in TRILAMP_RIG:
        obj = find_rig_light(spec)
        if obj is not None:
            out.append((spec, obj))
    return out


def action_fcurves(anim_data):
    """Every F-curve of an ID's active action, across Blender's two action APIs.

    Blender 4.4 replaced the flat `Action.fcurves` list with slotted actions and
    5.0 removed the old attribute outright: on Blender 5.x the curves only exist
    inside the channelbag of the slot the datablock is assigned to. Reading them
    the old way raises AttributeError on exactly the version 3DSC targets, so
    everything that inspects keyframes goes through here.
    """
    if anim_data is None or anim_data.action is None:
        return []
    action = anim_data.action

    legacy = getattr(action, "fcurves", None)
    if legacy is not None:  # Blender <= 4.3
        return list(legacy)

    slot = getattr(anim_data, "action_slot", None)
    if slot is None:
        return []
    curves = []
    for layer in action.layers:
        for strip in layer.strips:
            channelbag = getattr(strip, "channelbag", None)
            if channelbag is None:
                continue
            bag = channelbag(slot)
            if bag is not None:
                curves.extend(bag.fcurves)
    return curves


def _has_fcurve(anim_data, data_path):
    return any(fc.data_path == data_path for fc in action_fcurves(anim_data))


def rig_migration_issues():
    """What is wrong with the rig already in this file, in plain sentences.

    Returns a list of (object_name, issue) pairs; empty means the rig is
    already in the shape the tool expects. This is what the panel uses to
    decide whether to offer the migration button, and it is deliberately
    read-only: a scene from the Basilica Iulia sessions must be diagnosed
    without being touched.
    """
    issues = []
    camera = bpy.data.objects.get("OrthoRenderCamera")
    for spec, obj in rig_light_objects():
        if obj.name != spec["name"]:
            issues.append((obj.name, f"named '{obj.name}', expected '{spec['name']}'"))
        if camera is not None and obj.parent is not camera:
            issues.append((obj.name, "not parented to OrthoRenderCamera"))
        for path in LIGHT_OBJECT_CHANNELS:
            if not _has_fcurve(obj.animation_data, path):
                issues.append((obj.name, f"no keyframes on {path}"))
        for path in LIGHT_DATA_CHANNELS:
            if not _has_fcurve(obj.data.animation_data, path):
                issues.append((obj.name, f"no keyframes on data.{path}"))
    return issues


def rig_light_channels(light_obj):
    """(object_paths, data_paths) that this lamp should carry keys on."""
    data_paths = list(LIGHT_DATA_CHANNELS)
    if light_obj.data.type == 'AREA':
        data_paths += list(LIGHT_DATA_AREA_CHANNELS)
    return list(LIGHT_OBJECT_CHANNELS), data_paths


def missing_rig_channels(light_obj):
    """The subset of `rig_light_channels` that has no F-curve yet.

    Computed ONCE before keying, never inside the frame loop: the first
    insert creates the curve, so a per-frame test would key frame 1 and
    silently skip the other five.
    """
    obj_paths, data_paths = rig_light_channels(light_obj)
    return (
        [p for p in obj_paths if not _has_fcurve(light_obj.animation_data, p)],
        [p for p in data_paths if not _has_fcurve(light_obj.data.animation_data, p)],
    )


def keyframe_rig_light(light_obj, frame, obj_paths=None, data_paths=None):
    """Key one rig lamp on `frame`, transform and data channels alike.

    Pass explicit channel lists to key only some of them (the migration keys
    only what is missing, so existing manual work survives untouched).
    """
    default_obj, default_data = rig_light_channels(light_obj)
    for path in (default_obj if obj_paths is None else obj_paths):
        light_obj.keyframe_insert(data_path=path, frame=frame)
    for path in (default_data if data_paths is None else data_paths):
        try:
            light_obj.data.keyframe_insert(data_path=path, frame=frame)
        except (TypeError, RuntimeError) as e:
            # size_y only exists on rectangular area lights, etc.
            print(f"[ortho] could not key {light_obj.name}.data.{path}: {e}")


# ---------------------------------------------------------------------------
# Output folder resolution
#
# The output folder is read from five places (render, SVG poll, SVG export,
# panel state, and the render itself). They MUST all go through
# `resolve_output_dir`, or versioning silently splits them apart: the render
# writes into _v03 while the SVG export keeps looking for PNGs in _v02.
#
# Version folders are siblings of the base folder — //ortho_renders/ becomes
# //ortho_renders_v01/ — so nothing is nested and the base stays readable.
# Reads always resolve to the LATEST existing version; only a render with
# mode 'NEW' ever creates the next one, which then becomes the latest. That
# way no hidden "current version" state has to be stored in the scene.
# ---------------------------------------------------------------------------

OUTPUT_VERSION_RE = re.compile(r'_v(\d{2,})$')


def output_dir_base(scene):
    """Absolute, separator-free base output folder (no version suffix)."""
    raw = getattr(scene, "ortho_render_output_path", "") or "//ortho_renders/"
    base = bpy.path.abspath(raw)
    return base.rstrip("/\\") or base


def existing_output_versions(base):
    """Version numbers of the `<base>_vNN` folders that already exist."""
    parent = os.path.dirname(base)
    leaf = os.path.basename(base)
    if not leaf or not os.path.isdir(parent):
        return []
    versions = []
    for entry in os.listdir(parent):
        if not entry.startswith(leaf + "_v"):
            continue
        m = OUTPUT_VERSION_RE.search(entry)
        if m and os.path.isdir(os.path.join(parent, entry)):
            versions.append(int(m.group(1)))
    return sorted(versions)


def resolve_output_dir(scene, create=False):
    """Where this scene's ortho renders live right now.

    `create=True` marks the write path (the Render operator): only then may a
    new version folder come into existence.
    """
    base = output_dir_base(scene)
    mode = getattr(scene, "ortho_render_versioning", 'OFF')
    if mode == 'OFF':
        if create:
            os.makedirs(base, exist_ok=True)
        return base

    versions = existing_output_versions(base)
    if mode == 'NEW' and create:
        number = (versions[-1] + 1) if versions else 1
    else:
        number = versions[-1] if versions else 1
    path = f"{base}_v{number:02d}"
    if create:
        os.makedirs(path, exist_ok=True)
    return path


def output_dir_label(scene):
    """Short, human description of where the next render will land."""
    mode = getattr(scene, "ortho_render_versioning", 'OFF')
    if mode == 'OFF':
        return os.path.basename(output_dir_base(scene)) or "."
    base = output_dir_base(scene)
    versions = existing_output_versions(base)
    if mode == 'NEW':
        number = (versions[-1] + 1) if versions else 1
        return f"{os.path.basename(base)}_v{number:02d} (new)"
    number = versions[-1] if versions else 1
    return f"{os.path.basename(base)}_v{number:02d}"


def view_image_path(scene, obj_name, code, output_path=None):
    """Full path of one rendered view, extension included.

    The extension comes from `scene.render.file_extension` rather than a
    hardcoded '.png', so the skip-existing check keeps working if the output
    format is ever changed.
    """
    if output_path is None:
        output_path = resolve_output_dir(scene)
    return os.path.join(output_path, f"{obj_name}_{code}{scene.render.file_extension}")


def ortho_pose_frames(scene):
    """The six frames the views live on, from the timeline markers.

    Falls back to the scene frame range when the markers are missing, so the
    helpers still do something sensible on a half-built scene.
    """
    frames = []
    for code, _, _, _, _ in CAMERA_POSITIONS:
        marker = scene.timeline_markers.get(code)
        if marker is not None:
            frames.append(marker.frame)
    if not frames:
        frames = list(range(scene.frame_start, scene.frame_end + 1))
    return sorted(set(frames))


def choose_true_scale(max_dim_m, ortho_scale_m, box_mm, small_cutoff=0.5):
    """Pick the metric scale denominator and printed size for a view.

    Shared by the SVG export and the dialog preview so both always agree.
    Policy (Rachele/Tommaso): 1:10 for pieces up to `small_cutoff`, 1:20
    above; climb the round-scale ladder if the OBJECT footprint would not fit
    the layout box. Returns (denom, printed_mm, warning). `printed_mm` is the
    printed size of the rendered frame (= ortho_scale, margin included); the
    template clip-path trims any overflow. `box_mm` is the template box side.
    """
    preferred = 10 if max_dim_m <= small_cutoff else 20
    denom = None
    for d in SCALE_LADDER:
        if d >= preferred and max_dim_m * 1000.0 / d <= box_mm:
            denom = d
            break
    warning = None
    if denom is None:
        denom = SCALE_LADDER[-1]
        warning = (f"Object overflows the layout box even at 1:{denom} — "
                   "check the object dimensions")
    printed_mm = ortho_scale_m * 1000.0 / denom
    return denom, printed_mm, warning


def clean_display_name(name):
    """Strip 3D Survey Collection typed prefixes/suffixes for display.

    3DSC-managed objects carry typed affixes — a type prefix (OB_ objects,
    ME_ meshes) and an LOD suffix (_LOD0.._LODn, optionally with Blender's
    '.001' duplicate tag). The tavola should show the bare identifier, e.g.
    'ME_B1_LOD0' -> 'B1'. Names without these affixes are returned unchanged,
    so this is safe on non-3DSC objects.
    """
    if not name:
        return name
    n = re.sub(r'\.\d{3}$', '', name)          # Blender '.001' duplicate tag
    n = re.sub(r'_LOD\d+$', '', n, flags=re.IGNORECASE)  # _LOD<n> suffix
    n = re.sub(r'^(?:OB|ME)_', '', n)          # type prefix
    return n or name


def object_max_dim(obj):
    """Largest world-space bounding-box side of a mesh object, in meters."""
    corners = [obj.matrix_world @ Vector(c) for c in obj.bound_box]
    xs = [c.x for c in corners]
    ys = [c.y for c in corners]
    zs = [c.z for c in corners]
    return max(max(xs) - min(xs), max(ys) - min(ys), max(zs) - min(zs))


def size_category_for(scene, max_dim_m):
    """Return the size-category id for an object's largest side (meters)."""
    if max_dim_m <= getattr(scene, "ortho_render_small_cutoff", 0.8):
        return 'SMALL'
    if max_dim_m <= getattr(scene, "ortho_render_medium_cutoff", 1.0):
        return 'MEDIUM'
    if max_dim_m <= getattr(scene, "ortho_render_large_cutoff", 2.0):
        return 'LARGE'
    return 'XLARGE'


# Cache for the dynamic fixed-scale enum. Blender stores char* pointers from
# EnumProperty items callbacks, so the returned list MUST stay referenced (a
# local would be garbage-collected and corrupt the menu) — keep it here.
_FIXED_SCALE_ENUM_CACHE = []


def fixed_scale_denom_items(self, context):
    """Enum items for the fixed-scale menu.

    Two sources, merged: the scales that actually have SCALE_1-N_* templates
    installed (so the menu grows by itself when a template is dropped into a
    folder — no code change for a new paper/scale), plus a baseline set that is
    always offered because the RESOLUTION can honour any scale even when no
    plate template exists for it yet. Entries without a template say so in
    their tooltip, and the export reports it rather than failing silently.
    """
    with_template = set()
    for path in get_template_search_paths():
        if os.path.isdir(path):
            for f in os.listdir(path):
                m = re.match(r'^SCALE_1-(\d+)_.*\.svg$', f)
                if m:
                    with_template.add(int(m.group(1)))
    denoms = with_template | set(BASELINE_SCALE_DENOMS)
    items = []
    for d in sorted(denoms):
        if d in with_template:
            desc = f"Fixed scale 1:{d} — plate templates installed"
        else:
            desc = (f"Fixed scale 1:{d} — no SCALE_1-{d}_* plate template installed; "
                    "renders will be at this scale but the SVG layout needs one")
        items.append((str(d), f"1:{d}", desc))
    _FIXED_SCALE_ENUM_CACHE.clear()
    _FIXED_SCALE_ENUM_CACHE.extend(items)
    return _FIXED_SCALE_ENUM_CACHE


def _fmt_len(m):
    """Format a length in the friendliest unit (cm under 1 m, else m)."""
    return f"{m * 100:.0f} cm" if m < 1.0 else f"{m:g} m"


def size_category_label(scene, category):
    """Human label for a size category built from the LIVE thresholds, so it
    always matches the editable Size thresholds (the old hardcoded '≤ 50cm'
    strings drifted from the real cutoffs)."""
    small = getattr(scene, "ortho_render_small_cutoff", 0.8)
    medium = getattr(scene, "ortho_render_medium_cutoff", 1.0)
    large = getattr(scene, "ortho_render_large_cutoff", 2.0)
    return {
        'SMALL': f"Small (≤ {_fmt_len(small)})",
        'MEDIUM': f"Medium (≤ {_fmt_len(medium)})",
        'LARGE': f"Large (≤ {_fmt_len(large)})",
        'XLARGE': f"X-Large (> {_fmt_len(large)})",
    }.get(category, category)


def resolution_for_category(scene, category):
    """Return the render resolution (px) configured for a size category."""
    return {
        'SMALL': getattr(scene, "ortho_render_small_resolution", 2000),
        'MEDIUM': getattr(scene, "ortho_render_medium_resolution", 4000),
        'LARGE': getattr(scene, "ortho_render_large_resolution", 6000),
        'XLARGE': getattr(scene, "ortho_render_xlarge_resolution", 8000),
    }.get(category, 2000)


def read_template_box_mm(template_path):
    """Return the (smallest) image_view box side in mm of an SVG template,
    or None if the file cannot be read or has no image_view boxes."""
    try:
        with open(template_path, 'r', encoding='utf-8') as f:
            svg = f.read()
    except OSError:
        return None
    sides = []
    for i in range(1, 7):
        m = re.search(r'<image\b[^>]*?(?<![-\w])id="image_view%d"[^>]*?>' % i, svg, re.DOTALL)
        if not m:
            continue
        tag = m.group(0)
        vals = []
        for a in ("width", "height"):
            am = re.search(r'(?<![-\w])%s="([^"]+)"' % a, tag)
            if am:
                try:
                    vals.append(float(am.group(1)))
                except ValueError:
                    pass
        if len(vals) == 2:
            sides.append(min(vals))
    return min(sides) if sides else None


# ---------------------------------------------------------------------------
# Render resolution
#
# Two ways of deciding how many pixels a view gets:
#
#   BUCKET     the historical behaviour — one fixed resolution per size
#              bucket (2000/4000/6000/8000). Simple, but the printed dot
#              density is whatever falls out of it, which is why 1:5 plates
#              were being produced by rendering at 1:10 and doubling the
#              image by hand in Inkscape.
#   SCALE_DPI  the resolution is DERIVED from the drawing scale and a target
#              DPI, so the PNG carries exactly the dots the plate needs and
#              nothing has to be resampled downstream.
#
# The rendered PNG spans the camera's ortho_scale (NOT the object size: the
# frame margin is inside the image and the template clips it), so the printed
# width is ortho_scale * 1000 / denominator millimetres. That is the number
# the DPI applies to — see apply_true_scale, which prints exactly that.
# ---------------------------------------------------------------------------

MAX_RENDER_PX = 16000  # a 1:1 metre-wide block at 300 dpi asks for ~13000 px

# Scales always offered in the fixed-scale menu, whether or not a matching
# template ships. The resolution can honour any of them; the plate can only be
# laid out if a SCALE_1-<n>_* template exists, and the export says so.
BASELINE_SCALE_DENOMS = [1, 2, 5, 10, 20, 25, 50]


# Memo for default_sheet_box_mm: this is read from disk, and the panel asks
# for it on every redraw. Keyed on the search paths, so adding a template
# folder invalidates it; a template edited in place needs a Blender restart,
# which is an acceptable trade for not stat-ing the disk 60 times a second.
_SHEET_BOX_CACHE = {}


def default_sheet_box_mm(scene=None):
    """Side of the view box on the standard A3 sheet, in mm.

    Read from an installed FIXED_A3_* template so it follows the templates
    instead of a hardcoded number; falls back to 80 mm (the shipped geometry)
    when none can be read.
    """
    paths = tuple(get_template_search_paths())
    if paths in _SHEET_BOX_CACHE:
        return _SHEET_BOX_CACHE[paths]

    box_mm = 80.0
    for path in paths:
        if not os.path.isdir(path):
            continue
        found = None
        for f in sorted(os.listdir(path)):
            if f.startswith("FIXED_A3_") and f.endswith(".svg"):
                found = read_template_box_mm(os.path.join(path, f))
                if found:
                    break
        if found:
            box_mm = found
            break

    _SHEET_BOX_CACHE[paths] = box_mm
    return box_mm


def print_scale_denominator(scene, max_dim_m, ortho_scale_m):
    """The denominator the plate will actually be drawn at.

    Mirrors apply_true_scale so the resolution is computed for the SAME scale
    the export will print — otherwise the DPI promise is a lie.
    """
    family = getattr(scene, "ortho_template_family", 'FIXED_SHEET')
    if family == 'FIXED_SCALE':
        try:
            return int(getattr(scene, "ortho_render_fixed_scale_denom", '10'))
        except (TypeError, ValueError):
            return 10
    if family == 'LEGACY':
        return 10
    small_cutoff = getattr(scene, "ortho_render_small_cutoff", 0.8)
    denom, _printed_mm, _warning = choose_true_scale(
        max_dim_m, ortho_scale_m, default_sheet_box_mm(scene), small_cutoff)
    return denom


def compute_render_resolution(span_m, scale_denom=10, dpi=300):
    """Pixels per side so that `span_m` printed at 1:scale_denom holds `dpi`.

    `span_m` is the metric width of the rendered frame (the camera ortho
    scale), not the object size.
    """
    image_mm = span_m * 1000.0 / max(scale_denom, 1)
    return int(round(image_mm / 25.4 * dpi))


def render_span_for(scene, obj):
    """Metres spanned by one rendered view — the camera ortho scale."""
    camera = bpy.data.objects.get("OrthoRenderCamera")
    if camera is not None and camera.type == 'CAMERA' and camera.data.ortho_scale > 0:
        return float(camera.data.ortho_scale)
    return object_max_dim(obj) * getattr(scene, "ortho_render_frame_margin", 1.1)


def render_resolution_for(scene, obj):
    """(pixels per side, warning or None) for the current settings."""
    if getattr(scene, "ortho_render_res_mode", 'BUCKET') != 'SCALE_DPI':
        return resolution_for_category(scene, size_category_for(scene, object_max_dim(obj))), None

    max_dim = object_max_dim(obj)
    span = render_span_for(scene, obj)
    denom = print_scale_denominator(scene, max_dim, span)
    dpi = getattr(scene, "ortho_render_target_dpi", 300)
    px = compute_render_resolution(span, denom, dpi)

    note = None
    if px > MAX_RENDER_PX:
        note = (f"1:{denom} at {dpi} dpi asks for {px} px per side; capped at "
                f"{MAX_RENDER_PX} px (~{int(round(MAX_RENDER_PX * 25.4 / (span * 1000.0 / denom)))} dpi). "
                "Lower the DPI or choose a smaller scale.")
        px = MAX_RENDER_PX
    elif px < 500:
        note = f"1:{denom} at {dpi} dpi gives only {px} px per side; raised to 500 px."
        px = 500
    return px, note


def get_text_dimensions(text, font, draw=None):
    """Get text dimensions in a way that works with any PIL version"""
    try:
        # Nuove versioni di PIL
        if hasattr(font, "getbbox"):
            bbox = font.getbbox(text)
            return bbox[2] - bbox[0], bbox[3] - bbox[1]
        # Versione di transizione
        elif hasattr(font, "getsize"):
            return font.getsize(text)
        # Metodo più vecchio con ImageDraw 
        elif draw and hasattr(draw, "textsize"):
            return draw.textsize(text, font=font)
        # Ancora più recente (se cambia l'API in futuro)
        elif hasattr(font, "getlength"):
            return font.getlength(text), font.getsize_multiline("X")[1]
        else:
            # Fallback
            return len(text) * 20, 40
    except Exception as e:
        print(f"Error getting text dimensions: {e}")
        # Fallback a valori ragionevoli
        return len(text) * 20, 40


class OBJECT_OT_setup_orthogonal_render(Operator):
    """Setup orthogonal rendering for the selected object with standardized views"""
    bl_idname = "object.setup_orthogonal_render"
    bl_label = "Setup Orthogonal Render"
    bl_options = {'REGISTER', 'UNDO'}
    
    @classmethod
    def poll(cls, context):
        return context.active_object is not None and context.active_object.type == 'MESH'
    
    def execute(self, context):
        obj = context.active_object
        scene = context.scene
        
        # Get the object's bounding box dimensions
        bbox_dims = self.get_object_bbox_dimensions(obj)
        max_dim = max(bbox_dims)
        
        # Determine the size category
        size_category = self.determine_size_category(max_dim, context)
        scene.ortho_render_size_category = size_category
        
        # Set appropriate resolution based on size
        self.set_resolution_from_size(size_category, context)
        
        # Create camera if it doesn't exist
        camera = self.ensure_camera(context)
        
        # Set the camera to orthographic and frame it to the ACTUAL object
        # size (+ margin). Using a fixed per-category scale made tall/large
        # objects fall outside the frame (e.g. a 3.18m column in the 3.0m
        # XLARGE preset) and made the "Size categories" cutoffs change the
        # camera size in confusing ways. The categories now only drive
        # resolution; framing follows the real bounding box.
        camera.data.type = 'ORTHO'
        margin = getattr(scene, "ortho_render_frame_margin", 1.1)
        ortho_scale = max_dim * margin
        camera.data.ortho_scale = ortho_scale
        
        # Create an empty as a target at the object's center
        target = self.create_target_empty(obj, context)
        
        # Set camera constraint to track to the empty
        self.setup_camera_constraints(camera, target)
        
        # Position camera for each view and set keyframes
        self.setup_camera_positions(camera, target, obj, context)

        # Create the three-point light rig parented to the camera. IMPORTANT:
        # if the rig already exists we do NOT rebuild it by default — rebuilding
        # resets each light's position/energy/keyframes and would silently throw
        # away any manual lighting the user has done. It is only (re)built when
        # missing, or when the user explicitly ticks "Rebuild light rig".
        light_msg = ""
        if getattr(scene, "ortho_render_create_lights", True):
            rig_exists = bool(rig_light_objects())
            if rig_exists and not getattr(scene, "ortho_render_rebuild_lights", False):
                light_msg = ", light rig kept (tick 'Rebuild light rig' to reset)"
            else:
                max_dim = max(self.get_object_bbox_dimensions(obj))
                n_lights = self.setup_light_rig(camera, max_dim, context)
                light_msg = f", {n_lights} lights"

        # Restore to the first pose
        scene.frame_set(scene.frame_start)

        # Set render settings
        self.setup_render_settings(context)

        self.report({'INFO'}, f"Orthogonal render setup complete. Object size: {size_category}, ortho scale: {ortho_scale:.2f}m{light_msg}")
        return {'FINISHED'}
    
    def get_object_bbox_dimensions(self, obj):
        # Get the object's bounding box in world space
        bbox_corners = [obj.matrix_world @ Vector(corner) for corner in obj.bound_box]
        
        # Calculate the dimensions
        min_x = min(corner.x for corner in bbox_corners)
        max_x = max(corner.x for corner in bbox_corners)
        min_y = min(corner.y for corner in bbox_corners)
        max_y = max(corner.y for corner in bbox_corners)
        min_z = min(corner.z for corner in bbox_corners)
        max_z = max(corner.z for corner in bbox_corners)
        
        width = max_x - min_x
        depth = max_y - min_y
        height = max_z - min_z
        
        return (width, depth, height)
    
    def determine_size_category(self, max_dimension, context):
        """Determine the size category based on the maximum dimension"""
        
        # Get the size category cutoffs from the properties
        small_cutoff = context.scene.ortho_render_small_cutoff
        medium_cutoff = context.scene.ortho_render_medium_cutoff
        large_cutoff = context.scene.ortho_render_large_cutoff
        
        if max_dimension <= small_cutoff:
            return 'SMALL'
        elif max_dimension <= medium_cutoff:
            return 'MEDIUM'
        elif max_dimension <= large_cutoff:
            return 'LARGE'
        else:
            return 'XLARGE'
    
    def set_resolution_from_size(self, size_category, context):
        """Set rendering resolution based on the size category"""
        scene = context.scene
        
        # Map size categories to resolution presets
        resolution_mapping = {
            'SMALL': scene.ortho_render_small_resolution,
            'MEDIUM': scene.ortho_render_medium_resolution,
            'LARGE': scene.ortho_render_large_resolution,
            'XLARGE': scene.ortho_render_xlarge_resolution
        }
        
        # Get the resolution value from the preset
        resolution = resolution_mapping.get(size_category, 2000)
        
        # Set render resolution
        scene.render.resolution_x = resolution
        scene.render.resolution_y = resolution
        scene.render.resolution_percentage = 100
    
    def ensure_camera(self, context):
        """Create a camera if it doesn't exist, or use the existing one"""
        camera_name = "OrthoRenderCamera"
        
        # Check if the camera already exists
        if camera_name in bpy.data.objects:
            camera = bpy.data.objects[camera_name]
        else:
            # Create new camera
            camera_data = bpy.data.cameras.new(camera_name)
            camera = bpy.data.objects.new(camera_name, camera_data)
            context.collection.objects.link(camera)
        
        # Set as active camera
        context.scene.camera = camera
        return camera
    
    def create_target_empty(self, obj, context):
        """Create an empty object as a target for the camera at the bounding box center"""
        target_name = "OrthoRenderTarget"
        
        # Calculate the center of the bounding box in world space
        bbox_corners = [obj.matrix_world @ Vector(corner) for corner in obj.bound_box]
        bbox_center = sum(bbox_corners, Vector()) / 8  # Average of all 8 corners
        
        # Check if the target already exists
        if target_name in bpy.data.objects:
            target = bpy.data.objects[target_name]
            # Update location to the bounding box center
            target.location = bbox_center
        else:
            # Create new empty
            target = bpy.data.objects.new(target_name, None)
            target.empty_display_type = 'PLAIN_AXES'
            target.empty_display_size = 0.2
            target.location = bbox_center
            context.collection.objects.link(target)
        
        return target
    
    def setup_camera_constraints(self, camera, target):
        """Remove any tracking constraint from the camera.

        Poses are baked as keyframed rotations (see setup_camera_positions)
        instead of a TRACK_TO constraint: the constraint always forces the
        same up-vector, which makes a per-pose roll (needed for the Bottom
        view) impossible. Clearing here also cleans cameras created by older
        versions of the setup.
        """
        camera.constraints.clear()
    
    def setup_camera_positions(self, camera, target, obj, context):
        """Set up camera positions for each standard view"""
        # Get object dimensions for calculating distance
        bbox_dims = self.get_object_bbox_dimensions(obj)
        max_dim = max(bbox_dims)
        
        # Calculate camera distance (this might need adjusting based on ortho scale)
        camera_distance = max_dim * 2.5

        # Make sure the clip range covers the object at that distance, so large
        # objects are not clipped away.
        camera.data.clip_start = min(camera.data.clip_start, max(max_dim * 0.01, 0.001))
        camera.data.clip_end = max(camera.data.clip_end, camera_distance * 2.0 + max_dim)

        # Clear any existing animation data
        if camera.animation_data:
            camera.animation_data_clear()
        
        # Set up animation data
        scene = context.scene
        scene.frame_start = 1
        scene.frame_end = len(CAMERA_POSITIONS)
        
        for i, (code, name, desc, direction, rotation) in enumerate(CAMERA_POSITIONS, 1):
            # Set the current frame
            scene.frame_set(i)

            # Position the camera
            camera.location = target.location + Vector(direction) * camera_distance

            # Aim at the target (baked, so single poses can be tuned). For
            # Bottom, roll 180° about the view axis so the underside prints
            # N-up like the Top view (E/W mirrored — the true view from below),
            # as decided with Emanuele/Rachele. The lights are parented to the
            # camera, so they roll with it and keep the same image-relative
            # direction on every view — no per-pose light compensation needed.
            look = (target.location - camera.location).normalized()
            mat = look.to_track_quat('-Z', 'Y').to_matrix().to_4x4()
            if code == "BO":
                mat = mat @ Matrix.Rotation(math.pi, 4, 'Z')
            camera.rotation_euler = mat.to_euler()

            # Insert keyframes
            camera.keyframe_insert(data_path="location", frame=i)
            camera.keyframe_insert(data_path="rotation_euler", frame=i)
            
            # Name the marker
            if scene.timeline_markers.find(code) == -1:
                marker = scene.timeline_markers.new(code, frame=i)
            else:
                scene.timeline_markers[code].frame = i
    
    def _get_light_rig_collection(self, context):
        """Return (creating if needed) the collection that holds the rig lights."""
        coll = bpy.data.collections.get(LIGHT_RIG_COLLECTION)
        if coll is None:
            coll = bpy.data.collections.new(LIGHT_RIG_COLLECTION)
            context.scene.collection.children.link(coll)
        return coll

    def setup_light_rig(self, camera, max_dim, context):
        """Create/refresh the three-point light rig parented to the camera.

        Lamps are placed from the angular spec (see TRILAMP_RIG) so the key is
        genuinely raking and the fill is genuinely subordinate. Distances scale
        linearly with the object size and energies with its square
        (inverse-square law), using LIGHT_RIG_SIZE_REF as the reference.

        Location, rotation AND the data-level channels (energy, colour, and the
        area size for the rim) are keyframed on every pose, so any single view
        can be re-lit — including its intensity, which before dev.16 lived on an
        unkeyframed light datablock and could only be changed globally.

        This REBUILDS: it is only reached when the rig is missing or when the
        user explicitly asked for a rebuild. Adopting an existing rig without
        disturbing it is RENDER_OT_ortho_migrate_light_rig's job.
        """
        scene = context.scene
        factor = max(max_dim, 1e-4) / LIGHT_RIG_SIZE_REF
        camera_distance = max_dim * 2.5  # must match setup_camera_positions
        coll = self._get_light_rig_collection(context)
        identity = Matrix.Identity(4)

        light_objs = []
        for spec in TRILAMP_RIG:
            # Adopt an existing lamp under any of its known names rather than
            # creating a duplicate, then normalise the name.
            light_obj = find_rig_light(spec)
            if light_obj is None:
                light_data = bpy.data.lights.new(spec["name"], type=spec["type"])
                light_obj = bpy.data.objects.new(spec["name"], light_data)
            # Claim the canonical name only if it is free: forcing it would
            # make Blender push a '.001' onto whatever unrelated object is
            # already holding it.
            clash = bpy.data.objects.get(spec["name"])
            if clash is None or clash is light_obj:
                light_obj.name = spec["name"]
                light_obj.data.name = spec["name"]
            light_data = light_obj.data

            # Link into the rig collection (and nowhere else)
            for c in list(light_obj.users_collection):
                c.objects.unlink(light_obj)
            coll.objects.link(light_obj)

            # Light data
            light_data.type = spec["type"]
            light_data.color = spec["color"]
            light_data.energy = trilamp_energy(spec, factor)
            if spec["type"] == 'AREA':
                light_data.shape = spec.get("shape", 'SQUARE')
                light_data.size = spec.get("size", 1.0) * factor
                if "size_y" in spec:
                    light_data.size_y = spec.get("size_y", 1.0) * factor

            # Clear any previous animation so re-running gives a clean rig
            if light_obj.animation_data:
                light_obj.animation_data_clear()
            if light_data.animation_data:
                light_data.animation_data_clear()

            # Parent to the camera with local transform == the computed pose
            light_obj.parent = camera
            light_obj.matrix_parent_inverse = identity
            light_obj.rotation_mode = 'XYZ'
            light_obj.location, light_obj.rotation_euler = trilamp_pose(
                spec, max_dim, camera_distance)
            light_objs.append(light_obj)

        # Keyframe the local transform and the data channels on every pose.
        # The rig keeps its base camera-relative pose on every frame (Bottom
        # included): because the lights orbit with the camera, each view is lit
        # from the same image-relative direction, so no per-pose compensation is
        # needed — the keys exist so the user can BREAK that uniformity on a
        # single view when a face needs different light.
        for i in range(scene.frame_start, scene.frame_end + 1):
            scene.frame_set(i)
            for light_obj, spec in zip(light_objs, TRILAMP_RIG):
                light_obj.location, light_obj.rotation_euler = trilamp_pose(
                    spec, max_dim, camera_distance)
                light_obj.data.energy = trilamp_energy(spec, factor)
                keyframe_rig_light(light_obj, i)

        return len(light_objs)

    def setup_render_settings(self, context):
        """Set up render engine, sampling and transparency for ortho renders."""
        scene = context.scene

        apply_ortho_render_quality(scene)

        # Transparency + PNG RGBA output
        scene.render.film_transparent = True
        scene.render.image_settings.file_format = 'PNG'
        scene.render.image_settings.color_mode = 'RGBA'
        scene.render.image_settings.compression = 0  # No compression

        # Output path template
        if not scene.ortho_render_output_path:
            scene.ortho_render_output_path = "//ortho_renders/"
        scene.render.filepath = resolve_output_dir(scene)


class RENDER_OT_ortho_migrate_light_rig(Operator):
    """Adopt an existing light rig: rename, re-parent and add the missing keyframes

    For scenes built before 1.7.0-dev.16, or whose rig was appended by hand from
    Rachele's Luci.blend. Those lamps follow the camera but hold no keyframes of
    their own, so a single view cannot be re-lit — and Setup deliberately leaves
    an existing rig alone, which means the scene never repairs itself.

    This adopts what is already there WITHOUT moving it: lamps keep their exact
    world pose, their energy and their colour. Only the missing pieces are
    added — the canonical name, the parenting to the render camera, and
    keyframes on the six poses for the channels that have none.
    """
    bl_idname = "render.ortho_migrate_light_rig"
    bl_label = "Migrate Light Rig"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return bool(rig_light_objects())

    def execute(self, context):
        scene = context.scene
        camera = bpy.data.objects.get("OrthoRenderCamera")
        if camera is None:
            self.report({'ERROR'}, "No OrthoRenderCamera in the file. "
                                   "Run Setup Orthogonal Render first.")
            return {'CANCELLED'}

        pairs = rig_light_objects()
        if not pairs:
            self.report({'INFO'}, "No TriLamp rig found — nothing to migrate.")
            return {'CANCELLED'}

        frames = ortho_pose_frames(scene)
        original_frame = scene.frame_current
        identity = Matrix.Identity(4)
        coll = bpy.data.collections.get(LIGHT_RIG_COLLECTION)
        if coll is None:
            coll = bpy.data.collections.new(LIGHT_RIG_COLLECTION)
            scene.collection.children.link(coll)

        renamed, reparented, keyed = [], [], []

        # Everything below happens on the first pose: the camera is animated,
        # so "the lamp's world pose" only means something at a definite frame.
        scene.frame_set(frames[0])

        for spec, light_obj in pairs:
            # 1. canonical name (the rim used to be called "-Back")
            if light_obj.name != spec["name"]:
                clash = bpy.data.objects.get(spec["name"])
                if clash is not None and clash is not light_obj:
                    self.report({'WARNING'},
                                f"'{light_obj.name}' not renamed: '{spec['name']}' "
                                "is already taken by another object")
                else:
                    renamed.append(f"{light_obj.name} -> {spec['name']}")
                    light_obj.name = spec["name"]
                    light_obj.data.name = spec["name"]

            # 2. live in the rig collection
            if coll not in list(light_obj.users_collection):
                for c in list(light_obj.users_collection):
                    c.objects.unlink(light_obj)
                coll.objects.link(light_obj)

            # 3. parent to the camera KEEPING the world pose. Solving the local
            #    matrix by hand (instead of letting Blender store a
            #    parent-inverse) keeps the rig's identity-parent-inverse
            #    convention, so a later Rebuild starts from a clean slate.
            if light_obj.parent is not camera:
                world = light_obj.matrix_world.copy()
                light_obj.parent = camera
                light_obj.matrix_parent_inverse = identity
                local = camera.matrix_world.inverted() @ world
                loc, rot, scale = local.decompose()
                light_obj.rotation_mode = 'XYZ'
                light_obj.location = loc
                light_obj.rotation_euler = rot.to_euler('XYZ')
                light_obj.scale = scale
                reparented.append(light_obj.name)

            # 4. keyframe only what is missing, on all six poses
            obj_paths, data_paths = missing_rig_channels(light_obj)
            if obj_paths or data_paths:
                for frame in frames:
                    scene.frame_set(frame)
                    keyframe_rig_light(light_obj, frame, obj_paths, data_paths)
                keyed.append(f"{light_obj.name} ({len(obj_paths) + len(data_paths)} ch)")
                scene.frame_set(frames[0])

        scene.frame_set(original_frame)

        parts = []
        if renamed:
            parts.append("renamed " + ", ".join(renamed))
        if reparented:
            parts.append("re-parented " + ", ".join(reparented))
        if keyed:
            parts.append("keyframed " + ", ".join(keyed))
        if not parts:
            self.report({'INFO'}, "Light rig was already up to date — nothing changed.")
        else:
            self.report({'INFO'}, "Light rig migrated: " + "; ".join(parts))
        return {'FINISHED'}


class RENDER_OT_ortho_key_lights_here(Operator):
    """Record the current light positions and intensities on THIS view

    The manual way is to select the three lamps and press I over the viewport,
    then repeat it on the light data for the intensity. This does both, on the
    current frame only, for every lamp of the rig.
    """
    bl_idname = "render.ortho_key_lights_here"
    bl_label = "Key Lights on This View"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return bool(rig_light_objects())

    def execute(self, context):
        scene = context.scene
        frame = scene.frame_current
        pairs = rig_light_objects()
        if not pairs:
            self.report({'ERROR'}, "No TriLamp rig found.")
            return {'CANCELLED'}

        for _spec, light_obj in pairs:
            keyframe_rig_light(light_obj, frame)

        view = None
        for code, name, _, _, _ in CAMERA_POSITIONS:
            marker = scene.timeline_markers.get(code)
            if marker is not None and marker.frame == frame:
                view = name
                break
        where = f"the {view} view" if view else f"frame {frame}"
        self.report({'INFO'}, f"{len(pairs)} lights keyed on {where}.")
        return {'FINISHED'}


class RENDER_OT_orthogonal_views(Operator):
    """Render orthogonal views of the selected object"""
    bl_idname = "render.orthogonal_views"
    bl_label = "Render Orthogonal Views"
    bl_options = {'REGISTER'}
    
    @classmethod
    def poll(cls, context):
        # Check if blend file is saved
        if not bpy.data.filepath:
            return False
            
        return (context.scene.camera is not None and 
                "OrthoRenderCamera" in bpy.data.objects and 
                context.active_object is not None)
    
    def execute(self, context):
        obj = context.active_object
        scene = context.scene
        
        # Check that camera and timeline markers are set up
        if "OrthoRenderCamera" not in bpy.data.objects:
            self.report({'ERROR'}, "Orthogonal camera setup not found. Please run Setup Orthogonal Render first.")
            return {'CANCELLED'}
        
        if len(scene.timeline_markers) < len(CAMERA_POSITIONS):
            self.report({'ERROR'}, "Camera positions not set up correctly. Please run Setup Orthogonal Render first.")
            return {'CANCELLED'}
        
        # Resolve (and, in 'New version' mode, create) the output folder. This
        # is the only call site allowed to pass create=True.
        output_path = resolve_output_dir(scene, create=True)
        
        # Re-apply the current quality and resolution so the Render button is
        # WYSIWYG: changing Samples/Engine/Denoise/Device or a Resolution value
        # in the panel takes effect on the next Render, WITHOUT re-running Setup
        # (which would rebuild the light rig and discard manual light tweaks).
        # The light rig and the camera framing are NOT touched here — only Setup
        # builds those.
        apply_ortho_render_quality(scene)
        if obj.type == 'MESH':
            res, res_note = render_resolution_for(scene, obj)
            scene.render.resolution_x = res
            scene.render.resolution_y = res
            scene.render.resolution_percentage = 100
            if res_note:
                self.report({'WARNING'}, res_note)

        # Store original frame for restoring later
        original_frame = scene.frame_current

        # Stamp the camera scale actually used for these renders on the object:
        # the SVG export computes the printed size from THIS value, so tavole
        # stay correct even if the camera is later re-set-up on another piece
        # (a stale camera scale silently printed wrong scales in multi-piece
        # sessions — Rachele's 1:20/1:50 report).
        camera = bpy.data.objects["OrthoRenderCamera"]
        obj["_3dsc_render_ortho_scale"] = float(camera.data.ortho_scale)

        # Skip-existing is enforced here by hand, NOT through
        # scene.render.use_overwrite: that flag is only honoured by the
        # animation path (bpy.ops.render.render(animation=True)) and is
        # silently ignored by write_still, so a checkbox wired straight to it
        # would look like a broken feature. The flag is still mirrored, so the
        # Output properties tab agrees with our panel.
        skip_existing = getattr(scene, "ortho_render_skip_existing", False)
        scene.render.use_overwrite = not skip_existing

        rendered, skipped = 0, []

        # Render each view
        for code, name, desc, _, _ in CAMERA_POSITIONS:
            # Find the marker
            marker = scene.timeline_markers.get(code)
            if not marker:
                continue

            target = view_image_path(scene, obj.name, code, output_path)
            if skip_existing and os.path.exists(target):
                skipped.append(name)
                continue

            # Set the frame to the marker position
            scene.frame_set(marker.frame)

            # Set the output file path (Blender appends the extension)
            scene.render.filepath = os.path.splitext(target)[0]

            # Render the view
            bpy.ops.render.render(write_still=True)
            rendered += 1

            self.report({'INFO'}, f"Rendered {name} view to {scene.render.filepath}")

        # Restore original frame
        scene.frame_set(original_frame)

        where = os.path.basename(output_path) or output_path
        if skipped:
            self.report({'INFO'},
                        f"{rendered} views rendered to {where}; "
                        f"{len(skipped)} already on disk and kept ({', '.join(skipped)}). "
                        "Delete a file to regenerate just that view.")
        else:
            self.report({'INFO'}, f"All {rendered} orthogonal views rendered to {output_path}")
        return {'FINISHED'}


# ---------------------------------------------------------------------------
# Black & white pass
#
# An ALTERNATIVE pass, not a change to the main lighting: the colour rig stays
# exactly as the user left it, keyframes included. The pass borrows the rig for
# the duration of the render, pushing the key and the rim up and the fill down
# so the tooling on the stone reads as relief rather than as colour, writes into
# its own subfolder with a _BW suffix, and puts everything back.
#
# Per-view light tuning is preserved: the keyed energy is read off the F-curve
# for each pose and multiplied by the gain, rather than being replaced by a flat
# value. The curves have to be muted while rendering, because the depsgraph
# re-evaluates them on every frame and would otherwise undo the gain.
# ---------------------------------------------------------------------------

BW_LIGHT_GAIN = {"KEY": 1.6, "FILL": 0.35, "RIM": 1.5}

# The looks Blender offers depend on the active view transform, and
# "AgX - Greyscale" only exists under AgX — so the pass sets the transform
# itself instead of hoping the scene is already on it. Both are restored.
BW_VIEW_TRANSFORM = "AgX"

# Tried in order; the first one Blender accepts wins. A greyscale look keeps
# the render RGBA (so the transparent background survives for the layout); if
# none is available we fall back to a BW file format, which costs the alpha.
BW_LOOK_CANDIDATES = (
    "AgX - Greyscale",
    "Greyscale",
    "AgX - High Contrast",
    "High Contrast",
    "AgX - Punchy",
    "Punchy",
)
BW_GREYSCALE_LOOKS = ("AgX - Greyscale", "Greyscale")


def _try_set_look(view_settings, candidates):
    """Set the first look Blender accepts. Returns the name used, or None."""
    for look in candidates:
        try:
            view_settings.look = look
            return look
        except (TypeError, ValueError):
            continue
    return None


class RENDER_OT_orthogonal_views_bw(Operator):
    """Render an extra black & white pass, tonemapped for reading the stone working

    An alternative pass, not a change to the setup: the main light rig and all
    its keyframes are left exactly as they are. Files land in a 'bw' subfolder
    with a _BW suffix, so the colour plate and the B/W plate can coexist.
    """
    bl_idname = "render.orthogonal_views_bw"
    bl_label = "Render B/W Pass"
    bl_options = {'REGISTER'}

    @classmethod
    def poll(cls, context):
        if not bpy.data.filepath:
            return False
        return (context.scene.camera is not None and
                "OrthoRenderCamera" in bpy.data.objects and
                context.active_object is not None)

    def execute(self, context):
        scene = context.scene
        obj = context.active_object

        if "OrthoRenderCamera" not in bpy.data.objects:
            self.report({'ERROR'}, "Orthogonal camera setup not found. "
                                   "Please run Setup Orthogonal Render first.")
            return {'CANCELLED'}
        if len(scene.timeline_markers) < len(CAMERA_POSITIONS):
            self.report({'ERROR'}, "Camera positions not set up correctly. "
                                   "Please run Setup Orthogonal Render first.")
            return {'CANCELLED'}

        output_path = os.path.join(resolve_output_dir(scene, create=True), "bw")
        os.makedirs(output_path, exist_ok=True)

        apply_ortho_render_quality(scene)
        if obj.type == 'MESH':
            res, res_note = render_resolution_for(scene, obj)
            scene.render.resolution_x = res
            scene.render.resolution_y = res
            scene.render.resolution_percentage = 100
            if res_note:
                self.report({'WARNING'}, res_note)

        view_settings = scene.view_settings
        saved = {
            "frame": scene.frame_current,
            "view_transform": view_settings.view_transform,
            "look": view_settings.look,
            "color_mode": scene.render.image_settings.color_mode,
            "filepath": scene.render.filepath,
            "use_overwrite": scene.render.use_overwrite,
        }
        pairs = rig_light_objects()
        saved_energy = {o.name: o.data.energy for _spec, o in pairs}
        muted_curves = []

        skip_existing = getattr(scene, "ortho_render_skip_existing", False)
        scene.render.use_overwrite = not skip_existing
        rendered, skipped = 0, []
        look = None

        try:
            try:
                view_settings.view_transform = BW_VIEW_TRANSFORM
            except (TypeError, ValueError):
                pass  # exotic OCIO config: keep whatever the scene has
            look = _try_set_look(view_settings, BW_LOOK_CANDIDATES)
            if look not in BW_GREYSCALE_LOOKS:
                # No greyscale look on this build: force a greyscale FILE, and
                # say out loud that the alpha channel is the price.
                scene.render.image_settings.color_mode = 'BW'
                self.report({'WARNING'},
                            "No greyscale look available — writing 8-bit BW files, "
                            "which drop the transparent background.")

            # Read the keyed energies BEFORE muting, then mute so the depsgraph
            # cannot undo the gain at render time.
            per_frame_energy = {}
            for _spec, light_obj in pairs:
                data = light_obj.data
                curve = next((fc for fc in action_fcurves(data.animation_data)
                               if fc.data_path == "energy"), None)
                for frame in ortho_pose_frames(scene):
                    base = curve.evaluate(frame) if curve is not None else data.energy
                    per_frame_energy[(light_obj.name, frame)] = base
                if curve is not None and not curve.mute:
                    curve.mute = True
                    muted_curves.append(curve)

            for code, name, _desc, _dir, _rot in CAMERA_POSITIONS:
                marker = scene.timeline_markers.get(code)
                if not marker:
                    continue

                target = os.path.join(
                    output_path,
                    f"{obj.name}_{code}_BW{scene.render.file_extension}")
                if skip_existing and os.path.exists(target):
                    skipped.append(name)
                    continue

                scene.frame_set(marker.frame)
                for spec, light_obj in pairs:
                    gain = BW_LIGHT_GAIN.get(spec.get("role", ""), 1.0)
                    base = per_frame_energy.get((light_obj.name, marker.frame),
                                                light_obj.data.energy)
                    light_obj.data.energy = base * gain

                scene.render.filepath = os.path.splitext(target)[0]
                bpy.ops.render.render(write_still=True)
                rendered += 1

        finally:
            for curve in muted_curves:
                curve.mute = False
            for _spec, light_obj in pairs:
                if light_obj.name in saved_energy:
                    light_obj.data.energy = saved_energy[light_obj.name]
            view_settings.view_transform = saved["view_transform"]
            try:
                view_settings.look = saved["look"]
            except (TypeError, ValueError):
                pass
            scene.render.image_settings.color_mode = saved["color_mode"]
            scene.render.filepath = saved["filepath"]
            scene.render.use_overwrite = saved["use_overwrite"]
            scene.frame_set(saved["frame"])

        tone = f"{saved['view_transform']} -> {look}" if look else "greyscale file output"
        msg = f"B/W pass ({tone}): {rendered} views written to {output_path}"
        if skipped:
            msg += f"; {len(skipped)} already on disk and kept ({', '.join(skipped)})"
        self.report({'INFO'}, msg)
        return {'FINISHED'}


class RENDER_OT_create_orthogonal_svg(Operator):
    """Create an SVG file with the orthogonal renders"""
    bl_idname = "render.create_orthogonal_svg"
    bl_label = "Create SVG Layout"
    bl_options = {'REGISTER'}
    
    document_name: StringProperty(
        name="Document Name",
        description="Name of the SVG document",
        default="orthogonal_renders"
    ) # type: ignore
    
    project_title: StringProperty(
        name="Project Title",
        description="Title of the project",
        default=""
    ) # type: ignore
    
    measurement_unit: EnumProperty(
        name="Measurement Unit",
        description="Unit for dimensions",
        items=[('cm', "Centimeters", "Use centimeters"),
               ('m', "Meters", "Use meters"),
               ('mm', "Millimeters", "Use millimeters")],
        default='cm'
    ) # type: ignore
    
    template_name: StringProperty(
        name="Template Name",
        description="Name of the SVG template file to use (without extension)",
        default="MASTER_1m"
    ) # type: ignore

    # Aggiungere questa variabile come attributo della classe
    last_checked_paths = []  # Per tenere traccia dei percorsi controllati durante la ricerca

    # Dinamicamente popolare la lista dei template disponibili
    def get_available_templates(self, context):
        import re
        templates_dict = {}  # Per evitare duplicati

        # Get the current family filter
        family = context.scene.ortho_template_family if hasattr(context.scene, 'ortho_template_family') else 'LEGACY'

        # Percorsi possibili in cui cercare i template (user folders first)
        possible_paths = get_template_search_paths()

        for path in possible_paths:
            if os.path.exists(path):
                for file in os.listdir(path):
                    if not file.endswith(".svg"):
                        continue
                    name = os.path.splitext(file)[0]

                    # Determine which family this template belongs to
                    if name.startswith('FIXED_'):
                        tmpl_family = 'FIXED_SHEET'
                    elif name.startswith('SCALE_'):
                        tmpl_family = 'FIXED_SCALE'
                    else:
                        tmpl_family = 'LEGACY'

                    # Filter by selected family
                    if tmpl_family != family:
                        continue

                    # Extract scale info for sorting and description
                    if tmpl_family == 'FIXED_SHEET':
                        # Pattern: FIXED_A3_50cm or FIXED_A3_50cm_compact
                        m = re.search(r'FIXED_A3_(\d+)(cm|m)(?:_compact)?$', name)
                        if m:
                            val = float(m.group(1))
                            unit = m.group(2)
                            scale_meters = val / 100 if unit == 'cm' else val
                            compact = '_compact' in name
                            description = f"A3 {m.group(1)}{unit}" + (" compact" if compact else "")
                        else:
                            scale_meters = 1.0
                            description = name
                    elif tmpl_family == 'FIXED_SCALE':
                        # Pattern: SCALE_1-10_A2_1m
                        m = re.search(r'SCALE_1-(\d+)_A(\d)_(\d+)(cm|m)$', name)
                        if m:
                            denom = int(m.group(1))
                            paper = f"A{m.group(2)}"
                            val = float(m.group(3))
                            unit = m.group(4)
                            scale_meters = val / 100 if unit == 'cm' else val
                            description = f"1:{denom} {paper} {m.group(3)}{unit}"
                        else:
                            scale_meters = 1.0
                            description = name
                    else:
                        # Legacy: MASTER_*
                        scale_match = re.search(r'(\d+(?:\.\d+)?)(m|cm|mm)$', name, re.IGNORECASE)
                        if scale_match:
                            sv = float(scale_match.group(1))
                            su = scale_match.group(2).lower()
                            scale_meters = sv / 100 if su == 'cm' else (sv / 1000 if su == 'mm' else sv)
                            description = f"Legacy {scale_match.group(1)}{su}"
                        else:
                            scale_meters = 1.0
                            description = f"Legacy: {name}"

                    if name not in templates_dict:
                        templates_dict[name] = (name, name, description, scale_meters)

        # Sort by scale and build final list
        templates = sorted(templates_dict.values(), key=lambda x: x[3])
        templates = [(t[0], t[1], t[2]) for t in templates]

        if not templates:
            templates.append(("MASTER_1m", "MASTER_1m", "Default template (1:1m)"))

        return templates
    
    template_select: EnumProperty(
        name="Template",
        description="Select SVG template to use",
        items=get_available_templates,
    )
    
    auto_select_template: BoolProperty(
        name="Auto-select Template",
        description="Automatically select the best template based on object size",
        default=True
    )
    
    open_file: BoolProperty(
        name="Open SVG After Export",
        description="Open the SVG file with the default application after export",
        default=False
    ) # type: ignore

    open_folder: BoolProperty(
        name="Open Folder After Export",
        description="Open the folder containing the exported file",
        default=True
    ) # type: ignore

    create_pdf: BoolProperty(
        name="Create PDF",
        description="Also create a PDF version of the SVG (requires Inkscape or similar)",
        default=False
    ) # type: ignore

    true_scale: BoolProperty(
        name="True Metric Scale",
        description="Print the views at a true metric scale (1:10 for small pieces, 1:20 for "
                    "medium/large, climbing to 1:25, 1:50... if the piece would overflow its box) "
                    "instead of stretching them to fill the box. Updates the scale bar and the "
                    "'Scala 1:x' labels accordingly",
        default=True
    ) # type: ignore


    @classmethod
    def poll(cls, context):
        # Check if the blend file is saved
        if not bpy.data.filepath:
            return False
        
        output_path = resolve_output_dir(context.scene)
        
        # Check if output directory exists and contains rendered images
        if not os.path.exists(output_path):
            return False
        
        # Check if we have a camera and target set up
        return "OrthoRenderCamera" in bpy.data.objects and context.active_object is not None
    
    def invoke(self, context, event):
        # Set default name based on active object, cleaned of 3DSC typed
        # prefixes/suffixes (ME_B1_LOD0 -> B1) for the document and title.
        if context.active_object:
            clean = clean_display_name(context.active_object.name)
            self.document_name = clean
            self.project_title = clean
        
        # Determina automaticamente il template migliore basato sulla dimensione
        if self.auto_select_template:
            obj = context.active_object
            if obj:
                bbox_dims = self.get_object_dimensions(obj)
                max_dim = max(bbox_dims)
                family = context.scene.ortho_template_family if hasattr(context.scene, 'ortho_template_family') else 'LEGACY'

                if family == 'FIXED_SHEET':
                    if max_dim <= 0.5:
                        target = "FIXED_A3_50cm"
                    elif max_dim <= 1.0:
                        target = "FIXED_A3_1m"
                    else:
                        target = "FIXED_A3_2m"
                    self.template_select = target if self.template_exists(target) else "MASTER_1m"

                elif family == 'FIXED_SCALE':
                    # Fixed scale, paper adapts: keep the user's chosen scale and
                    # pick the smallest sheet that fits the piece at that scale.
                    denom = int(getattr(context.scene, "ortho_render_fixed_scale_denom", '10'))
                    target, _box, _warn = self.pick_fixed_scale_template(denom, max_dim)
                    self.template_select = target if target else "MASTER_1m"

                else:  # LEGACY
                    if max_dim <= 0.5:
                        self.template_select = "MASTER_50cm" if self.template_exists("MASTER_50cm") else "MASTER_1m"
                    elif max_dim <= 1.0:
                        self.template_select = "MASTER_1m"
                    elif max_dim <= 2.0:
                        self.template_select = "MASTER_2m" if self.template_exists("MASTER_2m") else "MASTER_1m"
                    else:
                        self.template_select = "MASTER_5m" if self.template_exists("MASTER_5m") else "MASTER_1m"
        
        return context.window_manager.invoke_props_dialog(self)
    
    def template_exists(self, template_name):
        """Verifica se esiste un template con il nome specificato"""
        template_paths = self.find_template_paths(template_name)
        return len(template_paths) > 0
    
    def find_template_paths(self, template_name):        
        """Find all possible paths for a given template"""
        template_paths = []
        self.last_checked_paths = []  # Resetta la lista

        # Possible paths (user resource folders first, bundled last)
        possible_paths = get_template_search_paths()

        # Log possible paths
        print("Cercando template SVG in:")
        for path in possible_paths:
            if os.path.exists(path):
                full_path = os.path.join(path, f"{template_name}.svg")
                self.last_checked_paths.append(full_path)
                if os.path.exists(full_path):
                    template_paths.append(full_path)
                    print(f"✓ Trovato template: {full_path}")
                else:
                    print(f"✗ Template non trovato: {full_path}")
            else:
                print(f"✗ Cartella non esistente: {path}")
        
        return template_paths
    
    def draw(self, context):
        layout = self.layout
        
        box = layout.box()
        box.label(text="SVG Document Settings")
        box.prop(self, "document_name")
        box.prop(self, "project_title")
        
        box = layout.box()
        box.label(text="Object Measurements")
        box.prop(self, "measurement_unit")
        
        family = getattr(context.scene, "ortho_template_family", 'FIXED_SHEET')
        box = layout.box()
        box.label(text="Template Selection")
        box.prop(context.scene, "ortho_template_family", text="Mode")
        if family == 'FIXED_SCALE':
            box.prop(context.scene, "ortho_render_fixed_scale_denom", text="Fixed scale")
        box.prop(self, "auto_select_template")

        if not self.auto_select_template:
            box.prop(self, "template_select", text="Sheet")
        else:
            # Mostra il template selezionato automaticamente
            box.label(text=f"Selected sheet: {self.template_select}")
        # In 'Scale fixed' mode the drawing is always at the chosen metric scale,
        # so the True-Scale toggle is not offered (it would be meaningless).
        if family != 'FIXED_SCALE':
            box.prop(self, "true_scale")

        # Live preview: tell the user WHAT they will get before generating,
        # instead of only discovering the scale from the tavola afterwards.
        self._draw_scale_preview(context, box)


        box = layout.box()
        box.label(text="Post-Export Options")
        box.prop(self, "open_file")
        box.prop(self, "open_folder")
        box.prop(self, "create_pdf")
        
        # Mostra avvisi per problemi comuni
        if not bpy.data.filepath:
            box = layout.box()
            box.label(text="Warning: Blend file not saved", icon='ERROR')
            box.label(text="Please save your file first")
        
        # Verifica se il template esiste
        template_paths = self.find_template_paths(self.template_select)
        if not template_paths:
            box = layout.box()
            box.label(text=f"Template '{self.template_select}' not found", icon='ERROR')
            box.label(text="Check the svg_templates folder")
    
    def _draw_scale_preview(self, context, layout):
        """Show the resulting scale / printed size / resolution in the dialog."""
        obj = context.active_object
        if obj is None:
            return
        col = layout.column(align=True)

        dims = self.get_object_dimensions(obj)
        max_dim = max(dims)
        unit = "cm" if max_dim < 1.0 else "m"
        shown = max_dim * (100.0 if unit == "cm" else 1.0)
        col.label(text=f"Object size: {shown:.1f} {unit} (largest side)", icon='FIXED_SIZE')

        res = context.scene.render.resolution_x
        col.label(text=f"Render resolution: {res}×{res} px", icon='IMAGE_DATA')

        family = getattr(context.scene, "ortho_template_family", 'FIXED_SHEET')

        if family == 'FIXED_SCALE':
            # Fixed scale, paper adapts: scale is the user's choice; report the
            # sheet auto-pick picks and whether it fits.
            denom = int(getattr(context.scene, "ortho_render_fixed_scale_denom", '10'))
            name, box_mm, warning = self.pick_fixed_scale_template(denom, max_dim)
            obj_mm = max_dim * 1000.0 / denom
            if name is None:
                wr = col.row(); wr.alert = True
                wr.label(text=warning or f"No sheet for 1:{denom}", icon='ERROR')
                return
            paper = name.split('_')[2] if len(name.split('_')) > 2 else "?"
            col.label(text=f"Result: fixed 1:{denom}  ·  object prints {obj_mm:.0f} mm  ·  "
                           f"sheet {paper} (box {box_mm:.0f} mm)", icon='SNAP_INCREMENT')
            if warning:
                wr = col.row(); wr.alert = True
                wr.label(text="Overflows the largest available sheet", icon='ERROR')
            return

        if not self.true_scale:
            col.label(text="True scale OFF: views fill the box (arbitrary scale)",
                      icon='INFO')
            return

        # Resolve the same inputs apply_true_scale() uses.
        ortho_scale = float(obj.get("_3dsc_render_ortho_scale", 0.0) or 0.0)
        if ortho_scale <= 0:
            cam = bpy.data.objects.get("OrthoRenderCamera")
            if cam and cam.type == 'CAMERA' and cam.data.ortho_scale > 0:
                ortho_scale = cam.data.ortho_scale
            else:
                ortho_scale = max_dim * getattr(context.scene, "ortho_render_frame_margin", 1.1)

        paths = self.find_template_paths(self.template_select)
        box_mm = read_template_box_mm(paths[0]) if paths else None
        if box_mm is None:
            col.label(text="True scale not available for this sheet (legacy)",
                      icon='INFO')
            return

        small_cutoff = getattr(context.scene, "ortho_render_small_cutoff", 0.8)
        denom, printed_mm, warning = choose_true_scale(max_dim, ortho_scale, box_mm, small_cutoff)
        obj_mm = max_dim * 1000.0 / denom
        col.label(text=f"Result: A3  ·  scale 1:{denom}  ·  object prints {obj_mm:.0f} mm "
                       f"in a {box_mm:.0f} mm box", icon='SNAP_INCREMENT')
        if warning:
            wr = col.row()
            wr.alert = True
            wr.label(text="Object overflows even at the smallest scale", icon='ERROR')

    def execute(self, context):
        if not bpy.data.filepath:
            self.report({'ERROR'}, "Please save your blend file first")
            return {'CANCELLED'}
        
        obj = context.active_object
        output_path = resolve_output_dir(context.scene)
        
        # If output directory doesn't exist, create it
        if not os.path.exists(output_path):
            os.makedirs(output_path, exist_ok=True)
        
        # Get paths for each view based on defined positions
        camera_positions = [
            ("FR", "Front", "Front view (Y+)"),
            ("BA", "Back", "Back view (Y-)"),
            ("RI", "Right", "Right view (X+)"),
            ("LE", "Left", "Left view (X-)"),
            ("TO", "Top", "Top view (Z+)"),
            ("BO", "Bottom", "Bottom view (Z-)")
        ]
        
        image_paths = {}
        for i, (code, name, _) in enumerate(camera_positions):
            img_path = os.path.join(output_path, f"{obj.name}_{code}.png")
            if os.path.exists(img_path):
                image_paths[i+1] = img_path
            else:
                self.report({'WARNING'}, f"Missing render for {name} view. File not found: {img_path}")
                image_paths[i+1] = ""
        
        # Get object dimensions
        dimensions = self.get_object_dimensions(obj)
        formatted_dimensions = self.format_dimensions(dimensions, self.measurement_unit)
        
        # Find the SVG template
        template_paths = self.find_template_paths(self.template_select)

        if not template_paths:
            self.report({'ERROR'}, f"Template '{self.template_select}' not found. Operation cancelled.")
            return {'CANCELLED'}

        # Use the first template found
        template_path = template_paths[0]
        
        # Create the output path for the SVG file
        svg_output_path = os.path.join(output_path, f"{self.document_name}.svg")
        
        # Copy the template file directly to destination instead of loading it in memory first
        try:
            import shutil
            shutil.copy(template_path, svg_output_path)
            print(f"Template copied from {template_path} to {svg_output_path}")
        except Exception as e:
            self.report({'ERROR'}, f"Error copying template file: {e}")
            return {'CANCELLED'}
        #return {'FINISHED'}
        # Now read the copied file for replacements
        try:
            with open(svg_output_path, 'r', encoding='utf-8') as f:
                svg_content = f.read()
                print(f"Read {len(svg_content)} bytes from copied template")
        except Exception as e:
            self.report({'ERROR'}, f"Error reading copied template: {e}")
            return {'CANCELLED'}
        
        # Handle placeholder for missing images
        placeholder_path = os.path.join(os.path.dirname(svg_output_path), "placeholder.png")
        if not os.path.exists(placeholder_path):
            self.create_placeholder_image(placeholder_path)
        
        # Make all required replacements
        #svg_content = svg_content.replace('_3dscnamedocument.svg', f"{self.document_name}.svg")
        svg_content = svg_content.replace('_3dsctitolo', self.project_title)
        # The block caption shows the cleaned 3DSC identifier (ME_B1_LOD0 -> B1);
        # obj.name stays raw everywhere it must match the rendered PNG files.
        svg_content = svg_content.replace('_3dscnomeblocco', clean_display_name(obj.name))
        svg_content = svg_content.replace('_3dscmisure', formatted_dimensions)
        # Location caption (Sara's request): bottom-left under the silhouette;
        # empty string simply leaves the slot blank.
        svg_content = svg_content.replace('_3dscluogo', getattr(context.scene, "ortho_render_location", "") or "")
        
        # Replace image references
        for i in range(1, 7):
            if i in image_paths and image_paths[i] and os.path.exists(image_paths[i]):
                print(f"Using actual image for view {i}: {image_paths[i]}")
                current_image_relative_path = make_path_relative(image_paths[i], output_path)
                svg_content = svg_content.replace(f'_ref_image{i}', current_image_relative_path)
                #svg_content = svg_content.replace(f'_ref_image{i}', f'file:///{image_paths[i]}')
            else:
                print(f"Using placeholder for view {i}")
                placeholder_relative_path = make_path_relative(placeholder_path, output_path)
                svg_content = svg_content.replace(f'_ref_image{i}', placeholder_relative_path)
                #svg_content = svg_content.replace(f'_ref_image{i}', placeholder_path)
        
        # Handle special images
        #special_images = [
        #    ('_image7', '_ref_image7'),
        #    ('_image_8', '_ref_image_8')
        #]
        #for img_tag, ref_tag in special_images:
        #    svg_content = svg_content.replace(img_tag, placeholder_path)
        #    svg_content = svg_content.replace(ref_tag, placeholder_path)
        
        # Handle logo. Resolution order:
        #   1) the logo image chosen in the panel (scene.ortho_render_logo_path)
        #   2) a "logo.png" dropped in any template search folder (user/EM-home/bundled)
        #   3) nothing -> leave blank (do NOT fall back to the view placeholder,
        #      which would print the grey "View Not Rendered" image in the logo box)
        logo_src = ""
        prop_logo = context.scene.ortho_render_logo_path
        if prop_logo:
            abs_logo = bpy.path.abspath(prop_logo)
            if os.path.exists(abs_logo):
                logo_src = abs_logo
        if not logo_src:
            for p in get_template_search_paths():
                cand = os.path.join(p, "logo.png")
                if os.path.exists(cand):
                    logo_src = cand
                    break
        if logo_src:
            svg_content = svg_content.replace('_ref_logo', make_path_relative(logo_src, output_path))
        else:
            # No logo: use a 1x1 transparent PNG, NOT an empty href — an empty
            # href renders as a broken-image "red X" box in Inkscape/PDF export.
            svg_content = svg_content.replace('_ref_logo', TRANSPARENT_PNG_URI)

        # True metric scale: shrink the views to their exact printed size and
        # make the scale bar / 'Scala 1:x' labels truthful. Always applied in
        # 'Scale fixed' mode (the scale is the whole point there); in 'A3 fixed'
        # mode it is opt-in via the True Metric Scale checkbox.
        family = getattr(context.scene, "ortho_template_family", 'FIXED_SHEET')
        scale_denom = None
        if self.true_scale or family == 'FIXED_SCALE':
            svg_content, scale_denom, scale_warning = self.apply_true_scale(context, svg_content, obj)
            if scale_warning:
                self.report({'WARNING'}, scale_warning)


        # Write back the modified content
        try:
            with open(svg_output_path, 'w', encoding='utf-8') as f:
                f.write(svg_content)
                print(f"Modified SVG written back with {len(svg_content)} bytes")
        except Exception as e:
            self.report({'ERROR'}, f"Error writing modified SVG: {e}")
            return {'CANCELLED'}
        
        # Create PDF if requested
        pdf_output_path = None
        if self.create_pdf:
            pdf_output_path = os.path.join(output_path, f"{self.document_name}.pdf")
            pdf_created = self.create_pdf_from_svg(svg_output_path, pdf_output_path)
            if not pdf_created:
                self.report({'WARNING'}, "Could not create PDF. Inkscape may not be installed.")

        # Open the file if requested
        if self.open_file:
            try:
                import subprocess
                if os.name == 'nt':  # Windows
                    os.startfile(svg_output_path)
                elif os.name == 'posix':  # Linux or Mac
                    # macOS uses 'open', Linux uses 'xdg-open'
                    import platform
                    if platform.system() == 'Darwin':  # macOS
                        subprocess.Popen(['open', svg_output_path])
                    else:  # Linux
                        subprocess.Popen(['xdg-open', svg_output_path])
            except Exception as e:
                self.report({'WARNING'}, f"Could not open file: {e}")

        # Open folder if requested
        if self.open_folder:
            try:
                import subprocess
                if os.name == 'nt':  # Windows
                    os.startfile(output_path)
                elif os.name == 'posix':  # Linux or Mac
                    import platform
                    if platform.system() == 'Darwin':  # macOS
                        subprocess.Popen(['open', output_path])
                    else:  # Linux
                        subprocess.Popen(['xdg-open', output_path])
            except Exception as e:
                self.report({'WARNING'}, f"Could not open folder: {e}")

        success_msg = f"SVG created successfully at {svg_output_path}"
        if scale_denom:
            success_msg += f" (scale 1:{scale_denom})"
        if pdf_output_path and os.path.exists(pdf_output_path):
            success_msg += f" and PDF at {pdf_output_path}"

        self.report({'INFO'}, success_msg)
        return {'FINISHED'}
    
    def get_object_dimensions(self, obj):
        """Get the object's bounding box dimensions in world space"""
        bbox_corners = [obj.matrix_world @ Vector(corner) for corner in obj.bound_box]
        
        # Calculate the dimensions
        min_x = min(corner.x for corner in bbox_corners)
        max_x = max(corner.x for corner in bbox_corners)
        min_y = min(corner.y for corner in bbox_corners)
        max_y = max(corner.y for corner in bbox_corners)
        min_z = min(corner.z for corner in bbox_corners)
        max_z = max(corner.z for corner in bbox_corners)
        
        width = max_x - min_x
        depth = max_y - min_y
        height = max_z - min_z

        return (depth, width, height)

    # ---- True metric scale ------------------------------------------------
    # The templates place each view as an 80 mm (50 mm compact) square image
    # that the render stretches to fill, so the printed scale was arbitrary.
    # These helpers shrink each view to its exact printed size for a round
    # scale denominator and rebuild the graphic scale bar to match.

    @staticmethod
    def _get_attr(tag, name):
        """Numeric value of an XML attribute inside an already-matched tag."""
        m = re.search(r'(?<![-\w])%s="([^"]+)"' % name, tag)
        try:
            return float(m.group(1)) if m else None
        except ValueError:
            return None

    @staticmethod
    def _edit_tag_attrs(svg_content, elem_id, attrs):
        """Rewrite attributes of the (unique) element whose id == elem_id."""
        m = re.search(r'<(?:image|rect|text)\b[^>]*?(?<![-\w])id="%s"[^>]*?>' % re.escape(elem_id),
                      svg_content, re.DOTALL)
        if not m:
            return svg_content
        tag = m.group(0)
        for name, value in attrs.items():
            tag = re.sub(r'(?<![-\w])%s="[^"]*"' % name, '%s="%s"' % (name, value), tag)
        return svg_content[:m.start()] + tag + svg_content[m.end():]

    @staticmethod
    def _edit_text_content(svg_content, elem_id, new_text):
        """Replace the text content of the <text> element with the given id."""
        pattern = re.compile(r'(<text\b[^>]*?(?<![-\w])id="%s"[^>]*?>)[^<]*(</text>)' % re.escape(elem_id),
                             re.DOTALL)
        return pattern.sub(lambda m: m.group(1) + new_text + m.group(2), svg_content, count=1)

    def fixed_scale_templates(self, denom):
        """List (template_name, box_mm) for the 'Scale fixed' sheets available at
        1:denom, sorted by box size (smallest paper first)."""
        pat = re.compile(r'^SCALE_1-%d_.*\.svg$' % denom)
        found = {}
        for path in get_template_search_paths():
            if not os.path.isdir(path):
                continue
            for f in os.listdir(path):
                if pat.match(f):
                    name = os.path.splitext(f)[0]
                    if name not in found:
                        box = read_template_box_mm(os.path.join(path, f))
                        if box:
                            found[name] = box
        return sorted(found.items(), key=lambda kv: kv[1])

    def pick_fixed_scale_template(self, denom, max_dim):
        """Choose the smallest 'Scale fixed' sheet that fits the piece at 1:denom.

        Returns (template_name or None, box_mm or None, warning). Falls back to
        the largest available sheet (with a warning) if none is big enough."""
        candidates = self.fixed_scale_templates(denom)
        if not candidates:
            return None, None, f"No 'Scale fixed' template exists for 1:{denom}"
        needed_mm = max_dim * 1000.0 / denom
        for name, box in candidates:
            if box + 1e-6 >= needed_mm:
                return name, box, None
        name, box = candidates[-1]  # largest we have
        return name, box, (f"Piece needs {needed_mm:.0f} mm at 1:{denom}, but the largest "
                           f"available sheet box is {box:.0f} mm — it will overflow")

    def apply_true_scale(self, context, svg_content, obj):
        """Resize the six view images so they print at a true metric scale.

        Two modes (scene.ortho_template_family):
          * FIXED_SHEET — the sheet is fixed (A3); solve the denominator on the
            round-scale ladder so the piece fits the box.
          * FIXED_SCALE — the denominator is fixed (ortho_render_fixed_scale_denom);
            the paper was chosen to fit (see pick_fixed_scale_template).
        Same image-resize / scale-bar / label code either way — only the source
        of `denom` differs.

        Returns (svg_content, denominator, warning): denominator is None when
        the template has no image_view boxes (nothing was changed); warning is
        a message to report, or None.
        """
        scene = context.scene
        max_dim = max(self.get_object_dimensions(obj))

        # Metres spanned by each (square) rendered PNG = the camera ortho
        # scale used for the renders. Prefer the value stamped on the object
        # at render time (the live camera may have been re-set-up on another
        # piece since); fall back to the camera, then the framing formula.
        ortho_scale = float(obj.get("_3dsc_render_ortho_scale", 0.0) or 0.0)
        if ortho_scale <= 0:
            cam = bpy.data.objects.get("OrthoRenderCamera")
            if cam and cam.type == 'CAMERA' and cam.data.ortho_scale > 0:
                ortho_scale = cam.data.ortho_scale
            else:
                ortho_scale = max_dim * getattr(scene, "ortho_render_frame_margin", 1.1)
        if ortho_scale <= 0:
            return svg_content, None, "Camera ortho scale is zero — true scale skipped"

        # Collect the view boxes from the template (compact templates use a
        # smaller box, so read the geometry instead of hardcoding 80 mm).
        boxes = {}
        for i in range(1, 7):
            m = re.search(r'<image\b[^>]*?(?<![-\w])id="image_view%d"[^>]*?>' % i,
                          svg_content, re.DOTALL)
            if not m:
                continue
            vals = {a: self._get_attr(m.group(0), a) for a in ("x", "y", "width", "height")}
            if None not in vals.values():
                boxes[i] = vals
        if not boxes:
            return svg_content, None, ("Template has no 'image_viewN' boxes — "
                                       "views were left at arbitrary scale")

        box_mm = min(min(b["width"], b["height"]) for b in boxes.values())

        family = getattr(scene, "ortho_template_family", 'FIXED_SHEET')
        if family == 'FIXED_SCALE':
            # Fixed scale, paper adapts: the denominator is the user's choice;
            # the sheet was picked to fit. Warn if the object still overflows.
            denom = int(getattr(scene, "ortho_render_fixed_scale_denom", '10'))
            printed_mm = ortho_scale * 1000.0 / denom
            obj_mm = max_dim * 1000.0 / denom
            warning = None
            if obj_mm > box_mm + 1e-6:
                warning = (f"Object prints {obj_mm:.0f} mm at 1:{denom} but the sheet box is "
                           f"{box_mm:.0f} mm — pick a larger paper or a smaller scale")
        else:
            # A3 fixed, scale adapts: solve the denominator to fit the box.
            small_cutoff = getattr(scene, "ortho_render_small_cutoff", 0.8)
            denom, printed_mm, warning = choose_true_scale(max_dim, ortho_scale, box_mm, small_cutoff)

        # Shrink each view to its printed size, centred in its original box.
        for i, b in boxes.items():
            svg_content = self._edit_tag_attrs(svg_content, f"image_view{i}", {
                "x": f"{b['x'] + (b['width'] - printed_mm) / 2.0:.4f}",
                "y": f"{b['y'] + (b['height'] - printed_mm) / 2.0:.4f}",
                "width": f"{printed_mm:.4f}",
                "height": f"{printed_mm:.4f}",
            })

        svg_content = self._rebuild_scale_bar(svg_content, denom)

        # The 'Scala 1:x' captions are static text in the templates (layer
        # Scala + cartiglio): rewrite whatever number they carry.
        svg_content = re.sub(r'Scala 1:[\d.,]+', f'Scala 1:{denom}', svg_content)

        return svg_content, denom, warning

    def _rebuild_scale_bar(self, svg_content, denom):
        """Rebuild the 5-segment graphic scale bar (rect18-22, labels
        text22-27) so it shows a round real-world length at 1:denom. Templates
        without that structure are left untouched (the text label still gets
        updated by the caller)."""
        m = re.search(r'<rect\b[^>]*?(?<![-\w])id="rect18"[^>]*?>', svg_content, re.DOTALL)
        if not m:
            return svg_content
        x0 = self._get_attr(m.group(0), "x")
        seg_w = self._get_attr(m.group(0), "width")
        if x0 is None or seg_w is None:
            return svg_content
        bar_space_mm = seg_w * 5.0

        # Largest nice real length whose printed size fits the original bar.
        real_m = SCALE_BAR_LENGTHS_M[0]
        for r in reversed(SCALE_BAR_LENGTHS_M):
            if r * 1000.0 / denom <= bar_space_mm + 1e-6:
                real_m = r
                break
        seg_mm = real_m * 1000.0 / denom / 5.0

        for i in range(5):
            svg_content = self._edit_tag_attrs(svg_content, f"rect{18 + i}", {
                "x": f"{x0 + i * seg_mm:.4f}",
                "width": f"{seg_mm:.4f}",
            })

        # Rachele's templates label bars up to 1 m in cm ("0..100 cm"),
        # longer ones in m ("0..2 m").
        unit, factor = ("cm", 100.0) if real_m <= 1.0 else ("m", 1.0)
        for i in range(6):
            value = real_m * factor * i / 5.0
            label = f"{value:g}" if i < 5 else f"{value:g} {unit}"
            svg_content = self._edit_tag_attrs(svg_content, f"text{22 + i}",
                                               {"x": f"{x0 + i * seg_mm:.4f}"})
            svg_content = self._edit_text_content(svg_content, f"text{22 + i}", label)
        # The end label is end-anchored in the templates; with a bar shorter
        # than the original it would back into the previous label, so centre
        # it on the bar end instead.
        m = re.search(r'<text\b[^>]*?(?<![-\w])id="text27"[^>]*?>', svg_content, re.DOTALL)
        if m:
            tag = m.group(0).replace('text-anchor:end', 'text-anchor:middle')
            svg_content = svg_content[:m.start()] + tag + svg_content[m.end():]

        # Keep the 'Scala 1:x' caption centred under the resized bar.
        svg_content = self._edit_tag_attrs(svg_content, "text28",
                                           {"x": f"{x0 + 2.5 * seg_mm:.4f}"})
        return svg_content


    def format_dimensions(self, dimensions, unit):
        """Format dimensions with the proper unit"""
        if unit == 'm':
            # Convert from meters to meters (no change)
            formatted = f"{dimensions[0]:.2f} x {dimensions[1]:.2f} x {dimensions[2]:.2f} m"
        elif unit == 'cm':
            # Convert from meters to centimeters
            dim_cm = [d * 100 for d in dimensions]
            formatted = f"{dim_cm[0]:.1f} x {dim_cm[1]:.1f} x {dim_cm[2]:.1f} cm"
        elif unit == 'mm':
            # Convert from meters to millimeters
            dim_mm = [d * 1000 for d in dimensions]
            formatted = f"{int(dim_mm[0])} x {int(dim_mm[1])} x {int(dim_mm[2])} mm"
        else:
            formatted = f"{dimensions[0]:.2f} x {dimensions[1]:.2f} x {dimensions[2]:.2f}"
        
        return formatted
    
    def create_pdf_from_svg(self, svg_path, pdf_path):
        """Create a PDF from SVG using available tools"""
        try:
            import subprocess
            import platform

            # Try different conversion methods
            converters = []

            if platform.system() == 'Darwin':  # macOS
                # Try Inkscape (common installation paths on macOS)
                converters.extend([
                    ['/Applications/Inkscape.app/Contents/MacOS/inkscape', svg_path, '--export-filename=' + pdf_path],
                    ['/usr/local/bin/inkscape', svg_path, '--export-filename=' + pdf_path],
                    ['inkscape', svg_path, '--export-filename=' + pdf_path],
                ])
            elif platform.system() == 'Windows':
                converters.extend([
                    ['inkscape', svg_path, '--export-filename=' + pdf_path],
                    ['C:\\Program Files\\Inkscape\\bin\\inkscape.exe', svg_path, '--export-filename=' + pdf_path],
                ])
            else:  # Linux
                converters.extend([
                    ['inkscape', svg_path, '--export-filename=' + pdf_path],
                    ['rsvg-convert', '-f', 'pdf', '-o', pdf_path, svg_path],
                    ['cairosvg', svg_path, '-o', pdf_path],
                ])

            # Try each converter
            for converter in converters:
                try:
                    result = subprocess.run(converter, capture_output=True, timeout=30)
                    if result.returncode == 0 and os.path.exists(pdf_path):
                        print(f"PDF created successfully using {converter[0]}")
                        return True
                except (subprocess.TimeoutExpired, FileNotFoundError):
                    continue

            return False

        except Exception as e:
            print(f"Error creating PDF: {e}")
            return False

    def create_placeholder_image(self, placeholder_path):
        """Create a placeholder image at the specified path"""
        try:
            # Only import PIL if we need to create the placeholder
            from PIL import Image, ImageDraw, ImageFont
            
            # Create the directory if it doesn't exist
            os.makedirs(os.path.dirname(placeholder_path), exist_ok=True)
            
            # Create a simple placeholder image
            width, height = 800, 800
            image = Image.new('RGBA', (width, height), (50, 50, 50, 255))
            draw = ImageDraw.Draw(image)
            
            # Draw a grid pattern
            grid_spacing = 50
            color1 = (60, 60, 60, 255)
            color2 = (40, 40, 40, 255)
            
            for x in range(0, width, grid_spacing):
                for y in range(0, height, grid_spacing):
                    if (x // grid_spacing + y // grid_spacing) % 2 == 0:
                        draw.rectangle([x, y, x + grid_spacing, y + grid_spacing], fill=color1)
                    else:
                        draw.rectangle([x, y, x + grid_spacing, y + grid_spacing], fill=color2)
            
            # Draw diagonal lines
            draw.line((0, 0, width, height), fill=(100, 100, 100), width=5)
            draw.line((0, height, width, 0), fill=(100, 100, 100), width=5)
            
            # Draw a message in the center
            try:
                # Try to use a font if available
                font = ImageFont.truetype("arial.ttf", 40)
            except OSError:
                # Fallback to default
                font = ImageFont.load_default()
                
            text = "View Not Rendered"
            
            # Get text dimensions (compatible with any PIL version)
            text_width, text_height = get_text_dimensions(text, font, draw)
            text_position = ((width - text_width) // 2, (height - text_height) // 2)
            
            # Draw text with shadow
            draw.text((text_position[0]+2, text_position[1]+2), text, font=font, fill=(0, 0, 0, 255))
            draw.text(text_position, text, font=font, fill=(200, 200, 200, 255))
            
            # Save the image
            image.save(placeholder_path)
            print(f"Created placeholder image at {placeholder_path}")
            
        except Exception as e:
            print(f"Error creating placeholder image: {e}")
            # Create a simple fallback if PIL is not available
            try:
                if not os.path.exists(placeholder_path):
                    # Create a simple numpy array and save it with matplotlib
                    import numpy as np
                    import matplotlib.pyplot as plt
                    
                    arr = np.zeros((800, 800, 3))
                    for i in range(800):
                        for j in range(800):
                            if (i//50 + j//50) % 2 == 0:
                                arr[i, j] = [0.2, 0.2, 0.2]
                            else:
                                arr[i, j] = [0.15, 0.15, 0.15]
                    
                    # Add diagonal lines
                    for i in range(800):
                        arr[i, i] = [0.4, 0.4, 0.4]
                        arr[i, 799-i] = [0.4, 0.4, 0.4]
                    
                    plt.imsave(placeholder_path, arr)
                    print(f"Created fallback placeholder image at {placeholder_path}")
            except Exception:
                print("Could not create placeholder image")


def get_addon_path():
    """Return the addon root directory.

    orthogonal_render.py lives at the addon root, so the directory containing
    this file IS the addon root. Using __file__ works regardless of the addon
    folder name or install location (legacy addon dir or bl_ext extension
    namespace) — unlike the old hardcoded "3D-survey-collection" path lookup.
    """
    return os.path.dirname(os.path.realpath(__file__))


# ---------------------------------------------------------------------------
# Template folder resolution
#
# Templates can live in several places. They are searched in priority order;
# the first folder that contains a given template name wins, so user/resource
# folders override the bundled ones. The bundled folder inside the addon is
# always the last-resort fallback and ships with the extension.
#
# The ExtendedMatrix home folder (~/ExtendedMatrix/3D Survey Collection/...) is
# part of the wider EM ecosystem and is NEVER created automatically on install
# — the user creates it manually from the addon preferences. Extra resource
# folders (including cloud/Drive paths) are added by the user to a list in the
# addon preferences.
# ---------------------------------------------------------------------------

def get_em_home_base():
    """~/ExtendedMatrix — shared root for the Extended Matrix tool ecosystem."""
    return os.path.join(os.path.expanduser("~"), "ExtendedMatrix")


def get_3dsc_home():
    """~/ExtendedMatrix/3D Survey Collection — this tool's home subfolder."""
    return os.path.join(get_em_home_base(), "3D Survey Collection")


def get_em_home_templates():
    """The SVG templates folder inside the EM home (manually created)."""
    return os.path.join(get_3dsc_home(), "svg_templates")


def get_addon_prefs():
    """Return this addon's preferences, or None if unavailable."""
    try:
        return bpy.context.preferences.addons[__package__].preferences
    except (KeyError, AttributeError):
        return None


def get_user_template_folders():
    """Absolute paths of the user-configured resource folders (in order)."""
    folders = []
    prefs = get_addon_prefs()
    if prefs is not None:
        for item in getattr(prefs, "svg_template_folders", []):
            raw = (item.path or "").strip()
            if not raw:
                continue
            folders.append(os.path.normpath(bpy.path.abspath(raw)))
    return folders


def get_template_search_paths():
    """Ordered list of folders to search for SVG templates.

    Priority (first wins on name collision):
      1. User resource folders from preferences (incl. cloud/Drive)
      2. ExtendedMatrix home folder (~/ExtendedMatrix/3D Survey Collection)
      3. Folders next to the saved .blend (project-local)
      4. Bundled folder inside the addon (always present, fallback)
    """
    paths = list(get_user_template_folders())
    paths.append(get_em_home_templates())

    if bpy.data.filepath:
        blend_dir = os.path.dirname(bpy.data.filepath)
        paths.append(os.path.join(blend_dir, "svg_templates"))
        paths.append(os.path.join(blend_dir, "3DSC", "svg_templates"))

    paths.append(os.path.join(get_addon_path(), "svg_templates"))

    # De-duplicate while preserving order
    seen = set()
    ordered = []
    for p in paths:
        norm = os.path.normpath(p)
        if norm and norm not in seen:
            seen.add(norm)
            ordered.append(norm)
    return ordered


# ---------------------------------------------------------------------------
# Render engine settings + render-time estimation
#
# The generic, reusable benchmark/estimator lives in render_benchmark.py (so
# future tools — sections, perspective scenes — and other EM addons can reuse
# it). Here we only keep the ortho-specific glue: apply the panel's quality
# props, and call the estimator with the 6 ortho views as frame count.
# ---------------------------------------------------------------------------

def apply_ortho_render_quality(scene):
    """Apply engine/samples/denoise/device from the scene props. Returns engine."""
    engine = getattr(scene, "ortho_render_engine", 'CYCLES')
    if engine not in ('CYCLES', 'BLENDER_EEVEE'):
        engine = 'CYCLES'
    scene.render.engine = engine

    samples = getattr(scene, "ortho_render_samples", 128)
    denoise = getattr(scene, "ortho_render_denoise", True)

    if engine == 'CYCLES':
        scene.cycles.samples = samples
        scene.cycles.use_denoising = denoise
        device = getattr(scene, "ortho_render_device", 'AUTO')
        if device in ('GPU', 'CPU'):
            # 'GPU' only takes effect if a compute device is configured in
            # Preferences > System; otherwise Cycles falls back to CPU.
            try:
                scene.cycles.device = device
            except Exception as e:
                print(f"[ortho] could not set Cycles device: {e}")
        # 'AUTO' leaves the user's configured device untouched.
    else:  # BLENDER_EEVEE
        try:
            scene.eevee.taa_render_samples = samples
        except Exception as e:
            print(f"[ortho] could not set EEVEE samples: {e}")
    return engine


def estimate_render_seconds(scene):
    """Estimate seconds to render all 6 ortho views at the current settings.

    Thin wrapper over the reusable render_benchmark module. Returns None if
    there is no calibration for the current engine+device yet.
    """
    engine = getattr(scene, "ortho_render_engine", 'CYCLES')
    mpx = (scene.render.resolution_x * scene.render.resolution_y) / 1e6
    samples = getattr(scene, "ortho_render_samples", 128)
    denoise = getattr(scene, "ortho_render_denoise", False) if engine == 'CYCLES' else False
    device_setting = getattr(scene, "ortho_render_device", 'AUTO')
    return render_benchmark.estimate(scene, engine, device_setting, mpx, samples,
                                     denoise, len(CAMERA_POSITIONS))


class RENDER_OT_ortho_benchmark(Operator):
    """Benchmark this machine with cross-tests and save a render-time model

    Runs a few small cross-test renders (varying samples, resolution and, for
    Cycles, denoise) plus a discarded warm-up to absorb first-launch GPU kernel
    compilation. The fitted model is saved per engine+device in
    ~/ExtendedMatrix and shared across the EM tools. Re-run after changing
    engine/device or when working on a much heavier/lighter scene.
    """
    bl_idname = "render.ortho_benchmark"
    bl_label = "Benchmark Render Speed"
    bl_options = {'REGISTER'}

    @classmethod
    def poll(cls, context):
        return context.scene.camera is not None

    def execute(self, context):
        scene = context.scene
        if scene.camera is None:
            self.report({'ERROR'}, "No active camera. Run Setup Orthogonal Render first.")
            return {'CANCELLED'}

        engine = apply_ortho_render_quality(scene)  # sets engine/device/samples/denoise
        device_setting = getattr(scene, "ortho_render_device", 'AUTO')
        # Record the rendered subject (a mesh), not whatever is active — after
        # Setup the active object is often the camera.
        subject = context.active_object
        if subject is None or subject.type != 'MESH':
            subject = next((o for o in context.selected_objects if o.type == 'MESH'), None)
        rec, total_measured = render_benchmark.run_benchmark(
            scene, device_setting,
            frame=(scene.frame_start or None),
            obj=subject,
        )
        # restore the panel's chosen samples/denoise (run_benchmark varied them)
        apply_ortho_render_quality(scene)

        est = estimate_render_seconds(scene)
        dev = render_benchmark.effective_device(scene, device_setting) if engine == 'CYCLES' else 'GPU'
        warm = rec.get("kernel_warmup", 0.0)
        warm_note = f" (+{warm:.0f}s kernel load on first render)" if warm >= 1.0 else ""
        self.report(
            {'INFO'},
            f"Benchmark done ({engine}/{dev}, {total_measured:.1f}s of tests). "
            f"Estimated {len(CAMERA_POSITIONS)} views: {render_benchmark.format_duration(est)}{warm_note}"
        )
        return {'FINISHED'}


class RENDER_OT_open_templates_folder(Operator):
    """Open the bundled SVG templates folder (read-only reference inside the addon)"""
    bl_idname = "render.open_templates_folder"
    bl_label = "Open Bundled Templates Folder"
    bl_options = {'REGISTER'}

    def execute(self, context):
        # Get addon directory
        addon_dir = get_addon_path()
        templates_path = os.path.join(addon_dir, "svg_templates")

        # Create folder if it doesn't exist
        if not os.path.exists(templates_path):
            try:
                os.makedirs(templates_path, exist_ok=True)
                self.report({'INFO'}, f"Created templates folder at {templates_path}")
            except Exception as e:
                self.report({'ERROR'}, f"Could not create templates folder: {e}")
                return {'CANCELLED'}

        # Open the folder
        try:
            import subprocess
            import platform

            if os.name == 'nt':  # Windows
                os.startfile(templates_path)
            elif os.name == 'posix':  # Linux or Mac
                if platform.system() == 'Darwin':  # macOS
                    subprocess.Popen(['open', templates_path])
                else:  # Linux
                    subprocess.Popen(['xdg-open', templates_path])

            self.report({'INFO'}, f"Opened templates folder: {templates_path}")
        except Exception as e:
            self.report({'ERROR'}, f"Could not open folder: {e}")
            return {'CANCELLED'}

        return {'FINISHED'}


def _open_in_file_browser(path):
    """Open a folder in the OS file browser. Returns (ok, error)."""
    try:
        import subprocess
        import platform
        if os.name == 'nt':
            os.startfile(path)
        elif platform.system() == 'Darwin':
            subprocess.Popen(['open', path])
        else:
            subprocess.Popen(['xdg-open', path])
        return True, None
    except Exception as e:
        return False, str(e)


class RENDER_UL_template_folders(bpy.types.UIList):
    """List of user-configured SVG template resource folders."""

    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        abspath = os.path.normpath(bpy.path.abspath(item.path)) if item.path else ""
        exists = bool(abspath) and os.path.isdir(abspath)
        row = layout.row(align=True)
        row.prop(item, "path", text="", emboss=False,
                 icon='FILE_FOLDER' if exists else 'ERROR')


class RENDER_OT_add_template_folder(Operator):
    """Add a folder to the SVG template resource list (can be a cloud/Drive path)"""
    bl_idname = "render.add_template_folder"
    bl_label = "Add Template Folder"
    bl_options = {'REGISTER'}

    def execute(self, context):
        prefs = get_addon_prefs()
        if prefs is None:
            self.report({'ERROR'}, "Could not access addon preferences")
            return {'CANCELLED'}
        prefs.svg_template_folders.add()
        prefs.svg_template_folders_index = len(prefs.svg_template_folders) - 1
        return {'FINISHED'}


class RENDER_OT_remove_template_folder(Operator):
    """Remove the selected folder from the SVG template resource list"""
    bl_idname = "render.remove_template_folder"
    bl_label = "Remove Template Folder"
    bl_options = {'REGISTER'}

    def execute(self, context):
        prefs = get_addon_prefs()
        if prefs is None:
            self.report({'ERROR'}, "Could not access addon preferences")
            return {'CANCELLED'}
        idx = prefs.svg_template_folders_index
        if 0 <= idx < len(prefs.svg_template_folders):
            prefs.svg_template_folders.remove(idx)
            prefs.svg_template_folders_index = max(0, idx - 1)
        return {'FINISHED'}


class RENDER_OT_create_em_home_folder(Operator):
    """Create the ExtendedMatrix home templates folder and add it to the list

    Creates ~/ExtendedMatrix/3D Survey Collection/svg_templates (part of the
    Extended Matrix ecosystem), registers it as a resource folder, and opens it.
    Nothing is created automatically on install — this is an explicit user action.
    """
    bl_idname = "render.create_em_home_templates_folder"
    bl_label = "Create ExtendedMatrix Home Folder"
    bl_options = {'REGISTER'}

    def execute(self, context):
        prefs = get_addon_prefs()
        if prefs is None:
            self.report({'ERROR'}, "Could not access addon preferences")
            return {'CANCELLED'}

        path = get_em_home_templates()
        try:
            os.makedirs(path, exist_ok=True)
        except Exception as e:
            self.report({'ERROR'}, f"Could not create folder: {e}")
            return {'CANCELLED'}

        # Add to the resource list if not already present
        norm = os.path.normpath(path)
        existing = {os.path.normpath(bpy.path.abspath(i.path))
                    for i in prefs.svg_template_folders if i.path}
        if norm not in existing:
            item = prefs.svg_template_folders.add()
            item.path = path
            prefs.svg_template_folders_index = len(prefs.svg_template_folders) - 1

        ok, err = _open_in_file_browser(path)
        if not ok:
            self.report({'WARNING'}, f"Folder created at {path} but could not open it: {err}")
        else:
            self.report({'INFO'}, f"ExtendedMatrix home templates folder ready: {path}")
        return {'FINISHED'}


class VIEW3D_PT_orthogonal_render(Panel):
    """Panel for orthogonal rendering setup"""
    bl_label = "Orthogonal Render"
    bl_idname = "VIEW3D_PT_orthogonal_render"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "3DSC"
    bl_options = {'DEFAULT_CLOSED'}
    
    def draw(self, context):
        layout = self.layout
        scene = context.scene

        # Object selection guards
        if context.active_object is None:
            layout.label(text="Select an object to render", icon='ERROR')
            return
        if context.active_object.type != 'MESH':
            layout.label(text="Selected object must be a mesh", icon='ERROR')
            return

        # --- WORKFLOW (top): the three steps in order ---------------------
        box = layout.box()
        box.label(text=f"Object: {context.active_object.name}", icon='OBJECT_DATA')

        if not bpy.data.filepath:
            row = box.row()
            row.alert = True
            row.label(text="Save the .blend first!", icon='ERROR')
        row = box.row(align=True)
        row.label(text="Output:")
        row.prop(scene, "ortho_render_output_path", text="")
        box.prop(scene, "ortho_render_versioning", text="Versioning")
        box.prop(scene, "ortho_render_skip_existing")
        if scene.ortho_render_versioning != 'OFF':
            sub = box.row()
            sub.enabled = False
            sub.label(text=f"Next render → {output_dir_label(scene)}", icon='FILE_FOLDER')

        # Step 1 — Setup
        col = layout.column(align=True)
        col.label(text="1 · Camera setup", icon='CAMERA_DATA')
        row = col.row(align=True)
        row.scale_y = 1.5
        row.operator("object.setup_orthogonal_render", text="Setup Orthogonal Render",
                     icon='CAMERA_DATA')

        # A rig inherited from an older 3DSC (or appended by hand from
        # Luci.blend) follows the camera but holds no keyframes of its own, and
        # Setup deliberately leaves an existing rig alone — so the scene never
        # repairs itself. Say so here, where it is noticed, not in a sub-panel.
        issues = rig_migration_issues()
        if issues:
            warn = col.box()
            warn.label(text="Light rig needs migrating", icon='ERROR')
            note = warn.column(align=True)
            note.scale_y = 0.8
            for name, issue in issues[:4]:
                note.label(text=f"· {name}: {issue}")
            if len(issues) > 4:
                note.label(text=f"· …and {len(issues) - 4} more")
            warn.operator("render.ortho_migrate_light_rig", icon='FILE_REFRESH',
                          text="Migrate Light Rig")

        # Step 2 — Render (only once the camera exists)
        if "OrthoRenderCamera" in bpy.data.objects:
            col = layout.column(align=True)
            col.label(text="2 · Render views", icon='RENDER_STILL')
            row = col.row(align=True)
            row.scale_y = 1.5
            row.operator("render.orthogonal_views", text="Render 6 Views",
                         icon='RENDER_STILL')
            col.operator("render.orthogonal_views_bw", text="Render B/W Pass",
                         icon='IMAGE_ZDEPTH')

            # Engine / samples / device used to live only in a collapsed
            # sub-panel, which is how a whole afternoon got rendered on the CPU
            # without anyone noticing. They are now visible where the Render
            # button is, and editable from here.
            quality = col.box()
            qrow = quality.row(align=True)
            qrow.prop(scene, "ortho_render_engine", text="")
            qrow.prop(scene, "ortho_render_samples", text="Samples")
            if scene.ortho_render_engine == 'CYCLES':
                drow = quality.row(align=True)
                drow.prop(scene, "ortho_render_device", text="Device")
                drow.prop(scene, "ortho_render_denoise", text="Denoise")
                if scene.ortho_render_device == 'GPU' and not render_benchmark.cycles_gpu_available():
                    alert = quality.row()
                    alert.alert = True
                    alert.label(text="No GPU configured (Preferences > System) — will run on CPU",
                                icon='ERROR')
                elif scene.ortho_render_device == 'CPU':
                    alert = quality.row()
                    alert.alert = True
                    alert.label(text="Forced to CPU — expect slow renders", icon='ERROR')

            res_px, res_note = None, None
            if context.active_object.type == 'MESH':
                res_px, res_note = render_resolution_for(scene, context.active_object)
            if hasattr(scene, "ortho_render_size_category") and scene.ortho_render_size_category:
                label = size_category_label(scene, scene.ortho_render_size_category)
                shown = res_px if res_px else scene.render.resolution_x
                if scene.ortho_render_res_mode == 'SCALE_DPI':
                    span = render_span_for(scene, context.active_object)
                    denom = print_scale_denominator(
                        scene, object_max_dim(context.active_object), span)
                    col.label(text=f"1:{denom} @ {scene.ortho_render_target_dpi} dpi  ·  "
                                   f"{shown}×{shown} px", icon='INFO')
                else:
                    col.label(text=f"Size: {label}  ·  {shown}×{shown} px", icon='INFO')
            if res_note:
                alert = col.row()
                alert.alert = True
                alert.label(text=res_note, icon='ERROR')

        # Step 3 — SVG layout export
        box = layout.box()
        box.label(text="3 · SVG Layout Export", icon='FILE_IMAGE')
        box.prop(scene, "ortho_template_family", text="Mode")
        if scene.ortho_template_family == 'FIXED_SCALE':
            box.prop(scene, "ortho_render_fixed_scale_denom", text="Fixed scale")
        box.prop(scene, "ortho_render_logo_path", text="Logo")
        box.prop(scene, "ortho_render_location", text="Location")

        template_exists = bool(ensure_svg_templates_folder())
        has_saved_blend = bool(bpy.data.filepath)
        has_renders = False
        if not template_exists:
            box.label(text="SVG template not found", icon='ERROR')
            box.label(text="Please install the template files")
        elif not has_saved_blend:
            box.label(text="Save file before exporting SVG", icon='ERROR')
        else:
            output_path = resolve_output_dir(context.scene)
            if os.path.exists(output_path) and context.active_object:
                front_view = view_image_path(context.scene, context.active_object.name,
                                             "FR", output_path)
                has_renders = os.path.exists(front_view)
            if not has_renders:
                box.label(text="Render the views before creating the SVG", icon='INFO')

        row = box.row(align=True)
        row.scale_y = 1.2
        row.enabled = bool(template_exists and has_saved_blend and has_renders)
        row.operator("render.create_orthogonal_svg", text="Create SVG Layout",
                     icon='OUTLINER_OB_FONT')

        # Templates management
        box = layout.box()
        row = box.row(align=True)
        row.operator("render.open_templates_folder", icon='FOLDER_REDIRECT',
                     text="Open Templates Folder")

        # The fine-grained configuration lives in the collapsible sub-panels
        # below (Framing & Sizing, Resolution, Render Quality). Sensible
        # defaults mean most users never open them.


class _OrthoSubPanel(Panel):
    """Base for the collapsible configuration sub-panels."""
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "3DSC"
    bl_parent_id = "VIEW3D_PT_orthogonal_render"
    bl_options = {'DEFAULT_CLOSED'}


class VIEW3D_PT_ortho_framing_sizing(_OrthoSubPanel):
    bl_label = "Framing & Sizing"
    bl_idname = "VIEW3D_PT_ortho_framing_sizing"

    def draw(self, context):
        layout = self.layout
        scene = context.scene

        layout.prop(scene, "ortho_render_frame_margin", text="Frame Margin")

        col = layout.column(align=True)
        col.label(text="Size thresholds (meters):", icon='DRIVER_DISTANCE')
        col.prop(scene, "ortho_render_small_cutoff", text="Small (≤)")
        col.prop(scene, "ortho_render_medium_cutoff", text="Medium (≤)")
        col.prop(scene, "ortho_render_large_cutoff", text="Large (≤)")
        # X-Large is the open bucket above the Large threshold — no editable
        # value (it has no upper bound), shown read-only so all four are visible.
        xl = col.row()
        xl.enabled = False
        xl.label(text=f"X-Large (>): {_fmt_len(getattr(scene, 'ortho_render_large_cutoff', 2.0))}")
        note = layout.column(align=True)
        note.scale_y = 0.8
        note.label(text="Thresholds pick the render resolution.", icon='INFO')
        note.label(text="'Small' is also the 1:10 ↔ 1:20 scale boundary.")
        note.label(text="Frame Margin: re-run Setup + Render.", icon='FILE_REFRESH')
        note.label(text="Thresholds: re-run Render (Step 2).")


class VIEW3D_PT_ortho_resolution(_OrthoSubPanel):
    bl_label = "Resolution"
    bl_idname = "VIEW3D_PT_ortho_resolution"

    def draw(self, context):
        layout = self.layout
        scene = context.scene

        layout.prop(scene, "ortho_render_res_mode", text="From")

        if scene.ortho_render_res_mode == 'SCALE_DPI':
            layout.prop(scene, "ortho_render_target_dpi", text="Target DPI")
            info = layout.column(align=True)
            info.scale_y = 0.8
            family = scene.ortho_template_family
            if family == 'FIXED_SCALE':
                info.label(text="Scale comes from Step 3 · Fixed scale.", icon='INFO')
            elif family == 'FIXED_SHEET':
                info.label(text="Scale is solved for the A3 box, same as", icon='INFO')
                info.label(text="the export — set it in Step 3 · Mode.")
            else:
                info.label(text="Legacy templates: assumed 1:10.", icon='INFO')

            obj = context.active_object
            if obj is not None and obj.type == 'MESH':
                span = render_span_for(scene, obj)
                denom = print_scale_denominator(scene, object_max_dim(obj), span)
                px, note = render_resolution_for(scene, obj)
                preview = layout.column(align=True)
                preview.label(text=f"1:{denom}  ·  {span * 1000.0 / denom:.0f} mm printed  ·  "
                                   f"{px}×{px} px", icon='IMAGE_DATA')
                if note:
                    alert = preview.row()
                    alert.alert = True
                    alert.label(text=note, icon='ERROR')
            layout.label(text=f"Hard cap: {MAX_RENDER_PX} px per side.", icon='INFO')
        else:
            col = layout.column(align=True)
            col.prop(scene, "ortho_render_small_resolution", text="Small")
            col.prop(scene, "ortho_render_medium_resolution", text="Medium")
            col.prop(scene, "ortho_render_large_resolution", text="Large")
            col.prop(scene, "ortho_render_xlarge_resolution", text="X-Large")
            note = layout.column(align=True)
            note.scale_y = 0.8
            note.label(text="One value per size bucket (X-Large = above the", icon='INFO')
            note.label(text="Large threshold).")

            # What the chosen bucket is really worth in print terms. Without
            # this the two modes cannot be compared, and switching to
            # 'Drawing scale + DPI' at 300 dpi looks like a bug rather than
            # like the deliberate downgrade it would be.
            obj = context.active_object
            if obj is not None and obj.type == 'MESH':
                span = render_span_for(scene, obj)
                denom = print_scale_denominator(scene, object_max_dim(obj), span)
                px = resolution_for_category(scene, size_category_for(scene, object_max_dim(obj)))
                printed_mm = span * 1000.0 / max(denom, 1)
                if printed_mm > 0:
                    eff_dpi = px * 25.4 / printed_mm
                    note.label(text=f"This bucket = {px} px = ~{eff_dpi:.0f} dpi at 1:{denom}.",
                               icon='IMAGE_DATA')

        note = layout.column(align=True)
        note.scale_y = 0.8
        note.label(text="Re-run Render (Step 2) to apply.", icon='FILE_REFRESH')


class VIEW3D_PT_ortho_quality(_OrthoSubPanel):
    bl_label = "Render Quality & Lighting"
    bl_idname = "VIEW3D_PT_ortho_quality"

    def draw(self, context):
        layout = self.layout
        scene = context.scene

        layout.prop(scene, "ortho_render_engine")
        layout.prop(scene, "ortho_render_samples")
        is_cycles = scene.ortho_render_engine == 'CYCLES'
        if is_cycles:
            layout.prop(scene, "ortho_render_denoise")
            layout.prop(scene, "ortho_render_device")
            if scene.ortho_render_device == 'GPU' and not render_benchmark.cycles_gpu_available():
                layout.label(text="No GPU configured (Preferences > System) — will use CPU",
                             icon='ERROR')

        est = estimate_render_seconds(scene)
        row = layout.row()
        if est is not None:
            dev = f" ({render_benchmark.effective_device(scene, scene.ortho_render_device)})" if is_cycles else ""
            row.label(text=f"Est. {len(CAMERA_POSITIONS)} views: "
                           f"~{render_benchmark.format_duration(est)}{dev}", icon='TIME')
            rec = render_benchmark.get_record(scene, scene.ortho_render_engine, scene.ortho_render_device)
            warm = rec.get("kernel_warmup", 0.0)
            if warm >= 1.0:
                layout.label(text=f"+ ~{int(round(warm))}s on the first render after launch "
                                  "(kernel load)", icon='INFO')
        else:
            row.label(text="Run benchmark for these settings", icon='QUESTION')
        layout.operator("render.ortho_benchmark", icon='PREVIEW_RANGE')

        layout.separator()
        layout.label(text="Light rig (Key / Fill / Rim)", icon='LIGHT_POINT')
        layout.prop(scene, "ortho_render_create_lights")
        rig_exists = bool(rig_light_objects())
        if rig_exists:
            layout.prop(scene, "ortho_render_rebuild_lights")

        issues = rig_migration_issues()
        if issues:
            warn = layout.box()
            warn.label(text="Rig from an older setup", icon='ERROR')
            wnote = warn.column(align=True)
            wnote.scale_y = 0.8
            for name, issue in issues[:6]:
                wnote.label(text=f"· {name}: {issue}")
            if len(issues) > 6:
                wnote.label(text=f"· …and {len(issues) - 6} more")
            warn.operator("render.ortho_migrate_light_rig", icon='FILE_REFRESH',
                          text="Migrate Light Rig")

        if rig_exists:
            layout.operator("render.ortho_key_lights_here", icon='KEYFRAME_HLT',
                            text="Key Lights on This View")

        # The angles are the whole point of the rig, so show them: "radente"
        # is the incidence number, not an adjective.
        geo = layout.column(align=True)
        geo.scale_y = 0.8
        for spec in TRILAMP_RIG:
            geo.label(text=f"{spec['role'].title()}: incidence "
                           f"{trilamp_incidence_deg(spec):.0f}°  ·  "
                           f"power ×{spec['ratio']:.2f}")

        note = layout.column(align=True)
        note.scale_y = 0.8
        note.label(text="Samples/Engine/Denoise/Device re-apply on", icon='INFO')
        note.label(text="Render — no need to re-run Setup.")
        if rig_exists:
            note.label(text="Existing lights are kept; Setup won't reset")
            note.label(text="them unless 'Rebuild light rig' is on.")
            note.label(text="Move a lamp, then Key Lights on This View")
            note.label(text="to change one view only.")


# Function to make sure the SVG template folder exists and create it if not
def ensure_svg_templates_folder():
    """Return True if at least one SVG template is available in any search path.

    The bundled folder inside the addon always exists and ships with templates,
    so this normally returns True. User/EM-home/project folders are checked too,
    with user folders taking priority. Nothing is created automatically here.
    """
    possible_paths = get_template_search_paths()

    # Log paths
    print("Checking template folders in:")
    for path in possible_paths:
        print(f"  - {path}")

    # Find existing paths
    existing_paths = [p for p in possible_paths if os.path.exists(p)]

    # Check if any svg template exists
    has_template = False
    for path in existing_paths:
        template_files = [f for f in os.listdir(path) if f.endswith(".svg")]
        if template_files:
            has_template = True
            print(f"Found template(s) in {path}: {', '.join(template_files)}")
            break
    
    return has_template


def register():
    bpy.utils.register_class(OBJECT_OT_setup_orthogonal_render)
    bpy.utils.register_class(RENDER_OT_orthogonal_views)
    bpy.utils.register_class(RENDER_OT_orthogonal_views_bw)
    bpy.utils.register_class(RENDER_OT_ortho_migrate_light_rig)
    bpy.utils.register_class(RENDER_OT_ortho_key_lights_here)
    bpy.utils.register_class(RENDER_OT_create_orthogonal_svg)
    bpy.utils.register_class(RENDER_OT_ortho_benchmark)
    bpy.utils.register_class(RENDER_OT_open_templates_folder)
    bpy.utils.register_class(RENDER_UL_template_folders)
    bpy.utils.register_class(RENDER_OT_add_template_folder)
    bpy.utils.register_class(RENDER_OT_remove_template_folder)
    bpy.utils.register_class(RENDER_OT_create_em_home_folder)
    bpy.utils.register_class(VIEW3D_PT_orthogonal_render)
    # Child sub-panels must be registered after their parent.
    bpy.utils.register_class(VIEW3D_PT_ortho_framing_sizing)
    bpy.utils.register_class(VIEW3D_PT_ortho_resolution)
    bpy.utils.register_class(VIEW3D_PT_ortho_quality)

    # Register properties
    bpy.types.Scene.ortho_render_size_category = EnumProperty(
        items=[(id, name, desc) for id, name, desc, _ in SIZE_CATEGORIES],
        name="Size Category",
        description="Size category of the object"
    )
    
    # Size cutoffs
    bpy.types.Scene.ortho_render_small_cutoff = FloatProperty(
        name="Small Cutoff",
        description="Objects up to this size (meters) count as 'small'. This has TWO "
                    "effects: it selects the Small render resolution, AND it is the "
                    "boundary for the true metric scale — small pieces print at 1:10, "
                    "larger ones at 1:20 (climbing further if they overflow the sheet). "
                    "Default 0.8 m = the largest piece that fits an A3 box at 1:10",
        default=0.8,
        min=0.1,
        max=10.0,
        unit='LENGTH'
    )
    
    bpy.types.Scene.ortho_render_medium_cutoff = FloatProperty(
        name="Medium Cutoff",
        description="Maximum size for medium objects (meters)",
        default=1.0,
        min=0.1,
        max=10.0,
        unit='LENGTH'
    )
    
    bpy.types.Scene.ortho_render_large_cutoff = FloatProperty(
        name="Large Cutoff",
        description="Maximum size for large objects (meters)",
        default=2.0,
        min=0.1,
        max=10.0,
        unit='LENGTH'
    )
    
    # Resolution settings
    bpy.types.Scene.ortho_render_small_resolution = IntProperty(
        name="Small Resolution",
        description="Resolution for small objects (pixels)",
        default=2000,
        min=500,
        max=10000
    )
    
    bpy.types.Scene.ortho_render_medium_resolution = IntProperty(
        name="Medium Resolution",
        description="Resolution for medium objects (pixels)",
        default=4000,
        min=500,
        max=10000
    )
    
    bpy.types.Scene.ortho_render_large_resolution = IntProperty(
        name="Large Resolution",
        description="Resolution for large objects (pixels)",
        default=6000,
        min=500,
        max=10000
    )
    
    bpy.types.Scene.ortho_render_xlarge_resolution = IntProperty(
        name="X-Large Resolution",
        description="Resolution for extra large objects (pixels)",
        default=8000,
        min=500,
        max=10000
    )
    
    bpy.types.Scene.ortho_render_output_path = StringProperty(
        name="Output Path",
        description="Path to save rendered images",
        default="//ortho_renders/",
        subtype='DIR_PATH',
        # Blender 4.5+ flags blend-relative ("//") paths red unless the
        # property opts in. The option does not exist before 4.5.
        options={'PATH_SUPPORTS_BLEND_RELATIVE'} if bpy.app.version >= (4, 5, 0) else set()
    )

    bpy.types.Scene.ortho_render_skip_existing = BoolProperty(
        name="Don't overwrite existing",
        description="Skip views whose image file is already on disk and render only the "
                    "missing ones. Delete a single view's file to regenerate just that "
                    "view. Off = every Render redoes all six",
        default=False
    )

    bpy.types.Scene.ortho_render_versioning = EnumProperty(
        name="Versioning",
        description="How the output folder is versioned. Version folders are siblings of "
                    "the output folder (ortho_renders_v01, _v02...). Reads always use the "
                    "latest existing version, so the SVG export never looks in the wrong one",
        items=[
            ('OFF', "No versioning",
             "Write straight into the output folder (the behaviour of every earlier version)"),
            ('LATEST', "Write into latest version",
             "Reuse the highest existing _vNN folder, creating _v01 if there is none"),
            ('NEW', "Create new version",
             "Each Render creates the next _vNN folder and leaves the previous ones alone"),
        ],
        default='OFF'
    )

    bpy.types.Scene.ortho_render_res_mode = EnumProperty(
        name="Resolution from",
        description="How the render resolution is decided",
        items=[
            ('BUCKET', "Size buckets",
             "One fixed resolution per size bucket (Small/Medium/Large/X-Large)"),
            ('SCALE_DPI', "Drawing scale + DPI",
             "Derive the resolution from the drawing scale and a target print DPI, so the "
             "PNG carries exactly the dots the plate needs and nothing has to be resampled "
             "by hand afterwards"),
        ],
        default='BUCKET'
    )

    bpy.types.Scene.ortho_render_target_dpi = IntProperty(
        name="Target DPI",
        description="Print resolution the views are computed for, in 'Drawing scale + DPI' "
                    "mode. 300 dpi is the print minimum, but note what the size buckets were "
                    "actually delivering: 4000 px across a 1.1 m frame at 1:10 is about "
                    "920 dpi, which is why those renders could be enlarged by hand and still "
                    "hold up. 600 dpi keeps a comparable margin; 300 dpi would be a visible "
                    "step down from the current plates",
        default=600, min=72, max=1200
    )

    bpy.types.Scene.ortho_render_create_lights = BoolProperty(
        name="Create Light Rig",
        description="Create a three-point light rig (Key/Fill/Back) parented to the camera, "
                    "keyframed on every pose for per-view manual fine-tuning",
        default=True
    )

    bpy.types.Scene.ortho_render_rebuild_lights = BoolProperty(
        name="Rebuild Light Rig",
        description="Rebuild the light rig from scratch on the next Setup, resetting "
                    "positions, energy and keyframes. Leave OFF to keep an existing rig "
                    "untouched — turning it ON discards any manual light adjustments",
        default=False
    )

    bpy.types.Scene.ortho_render_frame_margin = FloatProperty(
        name="Frame Margin",
        description="Camera framing padding around the object (1.0 = tight fit, 1.1 = 10%% margin). "
                    "The camera is sized to the real object, so tall/large objects always fit",
        default=1.1, min=1.0, max=3.0
    )

    bpy.types.Scene.ortho_render_engine = EnumProperty(
        name="Engine",
        description="Render engine for the orthogonal views",
        items=[
            ('CYCLES', "Cycles", "Path tracing — best quality for documentation (default)"),
            ('BLENDER_EEVEE', "EEVEE", "Rasterizer — much faster, lower fidelity"),
        ],
        default='CYCLES'
    )

    bpy.types.Scene.ortho_render_samples = IntProperty(
        name="Samples",
        description="Render samples per pixel (Cycles) / TAA render samples (EEVEE). "
                    "Starts low (20) for a fast look; raise it if the views look noisy "
                    "(denoising usually keeps 20 clean enough for documentation)",
        default=20, min=1, max=8192
    )

    bpy.types.Scene.ortho_render_denoise = BoolProperty(
        name="Denoise",
        description="Apply denoising (Cycles) — lets you use fewer samples",
        default=True
    )

    bpy.types.Scene.ortho_render_logo_path = StringProperty(
        name="Logo",
        description="Optional logo image placed in the layout. Leave empty for no logo "
                    "(or drop a 'logo.png' into a template folder). PNG with alpha recommended",
        default="",
        subtype='FILE_PATH',
        options={'PATH_SUPPORTS_BLEND_RELATIVE'} if bpy.app.version >= (4, 5, 0) else set()
    )

    bpy.types.Scene.ortho_render_location = StringProperty(
        name="Location",
        description="Optional location/provenance caption printed bottom-left in the "
                    "title block, under the silhouette (e.g. 'Roma, Basilica Iulia'). "
                    "Leave empty for none",
        default=""
    )

    bpy.types.Scene.ortho_render_device = EnumProperty(
        name="Device",
        description="Compute device for Cycles. GPU requires a device configured in "
                    "Preferences > System; AUTO keeps your current setting",
        items=[
            ('AUTO', "Auto", "Use the device configured in Preferences"),
            ('GPU', "GPU", "Force GPU Compute (falls back to CPU if none configured)"),
            ('CPU', "CPU", "Force CPU"),
        ],
        default='AUTO'
    )

    bpy.types.Scene.ortho_template_family = EnumProperty(
        name="Mode",
        description="How the drawing scale and the paper size relate",
        items=[
            ('FIXED_SHEET', "A3 fixed · scale adapts",
             "The sheet is always A3; the drawing scale adapts (1:10, 1:20, 1:25, 1:50…) "
             "so the piece always fits the same paper. Bigger pieces get more render "
             "resolution, so the A3 stays sharp when zoomed on screen"),
            ('FIXED_SCALE', "Scale fixed · sheet adapts",
             "The drawing scale is fixed (you choose it once); the paper grows "
             "(A2 → A0) to fit the piece. Every plate is at the same scale, paper varies"),
            ('LEGACY', "Legacy", "Original MASTER_*.svg templates"),
        ],
        default='FIXED_SHEET'
    )

    bpy.types.Scene.ortho_render_fixed_scale_denom = EnumProperty(
        name="Fixed Scale",
        description="Drawing scale used in 'Scale fixed · sheet adapts' mode. The paper is "
                    "chosen as the smallest sheet that fits the piece at this scale. The list "
                    "shows the scales that have SCALE_* templates installed",
        items=fixed_scale_denom_items,
    )


def unregister():
    bpy.utils.unregister_class(VIEW3D_PT_ortho_quality)
    bpy.utils.unregister_class(VIEW3D_PT_ortho_resolution)
    bpy.utils.unregister_class(VIEW3D_PT_ortho_framing_sizing)
    bpy.utils.unregister_class(VIEW3D_PT_orthogonal_render)
    bpy.utils.unregister_class(RENDER_OT_create_em_home_folder)
    bpy.utils.unregister_class(RENDER_OT_remove_template_folder)
    bpy.utils.unregister_class(RENDER_OT_add_template_folder)
    bpy.utils.unregister_class(RENDER_UL_template_folders)
    bpy.utils.unregister_class(RENDER_OT_open_templates_folder)
    bpy.utils.unregister_class(RENDER_OT_ortho_benchmark)
    bpy.utils.unregister_class(RENDER_OT_create_orthogonal_svg)
    bpy.utils.unregister_class(RENDER_OT_ortho_key_lights_here)
    bpy.utils.unregister_class(RENDER_OT_ortho_migrate_light_rig)
    bpy.utils.unregister_class(RENDER_OT_orthogonal_views_bw)
    bpy.utils.unregister_class(RENDER_OT_orthogonal_views)
    bpy.utils.unregister_class(OBJECT_OT_setup_orthogonal_render)
    
    # Unregister properties
    del bpy.types.Scene.ortho_render_size_category
    del bpy.types.Scene.ortho_render_small_cutoff
    del bpy.types.Scene.ortho_render_medium_cutoff
    del bpy.types.Scene.ortho_render_large_cutoff
    del bpy.types.Scene.ortho_render_small_resolution
    del bpy.types.Scene.ortho_render_medium_resolution
    del bpy.types.Scene.ortho_render_large_resolution
    del bpy.types.Scene.ortho_render_xlarge_resolution
    del bpy.types.Scene.ortho_render_output_path
    del bpy.types.Scene.ortho_render_skip_existing
    del bpy.types.Scene.ortho_render_versioning
    del bpy.types.Scene.ortho_render_res_mode
    del bpy.types.Scene.ortho_render_target_dpi
    del bpy.types.Scene.ortho_render_create_lights
    del bpy.types.Scene.ortho_render_rebuild_lights
    del bpy.types.Scene.ortho_render_frame_margin
    del bpy.types.Scene.ortho_render_engine
    del bpy.types.Scene.ortho_render_samples
    del bpy.types.Scene.ortho_render_denoise
    del bpy.types.Scene.ortho_render_device
    del bpy.types.Scene.ortho_render_location
    del bpy.types.Scene.ortho_render_logo_path
    del bpy.types.Scene.ortho_template_family
    del bpy.types.Scene.ortho_render_fixed_scale_denom


if __name__ == "__main__":
    register()
