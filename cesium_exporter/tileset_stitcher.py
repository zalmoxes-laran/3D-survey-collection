import json
import math
import os


def _bbox_union_from_face_ids(face_ids, face_mins, face_maxs):
    first = face_ids[0]
    min_x, min_y, min_z = face_mins[first]
    max_x, max_y, max_z = face_maxs[first]
    for face_id in face_ids[1:]:
        fmin = face_mins[face_id]
        fmax = face_maxs[face_id]
        min_x = min(min_x, fmin[0])
        min_y = min(min_y, fmin[1])
        min_z = min(min_z, fmin[2])
        max_x = max(max_x, fmax[0])
        max_y = max(max_y, fmax[1])
        max_z = max(max_z, fmax[2])
    return (min_x, min_y, min_z), (max_x, max_y, max_z)

def _bbox_to_box(bbox):
    (min_x, min_y, min_z), (max_x, max_y, max_z) = bbox
    cx = (min_x + max_x) * 0.5
    cy = (min_y + max_y) * 0.5
    cz = (min_z + max_z) * 0.5
    hx = max((max_x - min_x) * 0.5, 1e-6)
    hy = max((max_y - min_y) * 0.5, 1e-6)
    hz = max((max_z - min_z) * 0.5, 1e-6)
    return [cx, cy, cz, hx, 0.0, 0.0, 0.0, hy, 0.0, 0.0, 0.0, hz]

def _bbox_diag_len(bbox):
    (min_x, min_y, min_z), (max_x, max_y, max_z) = bbox
    return math.sqrt((max_x - min_x) ** 2 + (max_y - min_y) ** 2 + (max_z - min_z) ** 2)

def _normalize_parent_tileset_name(name):
    value = os.path.basename((name or "").strip())
    if not value:
        value = "tileset.json"
    if not value.lower().endswith(".json"):
        value += ".json"
    return value

def _aabb_from_3dtiles_box(box_vals):
    if not isinstance(box_vals, (list, tuple)) or len(box_vals) != 12:
        return None
    try:
        vals = [float(v) for v in box_vals]
    except Exception:
        return None
    cx, cy, cz = vals[0], vals[1], vals[2]
    x_axis = vals[3:6]
    y_axis = vals[6:9]
    z_axis = vals[9:12]
    ex = abs(x_axis[0]) + abs(y_axis[0]) + abs(z_axis[0])
    ey = abs(x_axis[1]) + abs(y_axis[1]) + abs(z_axis[1])
    ez = abs(x_axis[2]) + abs(y_axis[2]) + abs(z_axis[2])
    return ((cx - ex, cy - ey, cz - ez), (cx + ex, cy + ey, cz + ez))

def _bbox_union_many(bboxes):
    if not bboxes:
        return None
    min_x, min_y, min_z = bboxes[0][0]
    max_x, max_y, max_z = bboxes[0][1]
    for bbox in bboxes[1:]:
        (bx0, by0, bz0), (bx1, by1, bz1) = bbox
        min_x = min(min_x, bx0)
        min_y = min(min_y, by0)
        min_z = min(min_z, bz0)
        max_x = max(max_x, bx1)
        max_y = max(max_y, by1)
        max_z = max(max_z, bz1)
    return ((min_x, min_y, min_z), (max_x, max_y, max_z))


# ---------------------------------------------------------------------------
#  Parent tileset stitcher
# ---------------------------------------------------------------------------

def _scan_child_tilesets(output_root, parent_name):
    parent_abs = os.path.abspath(os.path.join(output_root, parent_name))
    entries = []
    for entry in sorted(os.listdir(output_root)):
        child_dir = os.path.join(output_root, entry)
        if not os.path.isdir(child_dir):
            continue
        child_tileset = os.path.join(child_dir, "tileset.json")
        if not os.path.isfile(child_tileset):
            continue
        if os.path.abspath(child_tileset) == parent_abs:
            continue
        entries.append((entry, child_tileset, f"{entry}/tileset.json"))
    return entries

def _build_parent_tileset(output_root, parent_name):
    parent_name = _normalize_parent_tileset_name(parent_name)
    if not output_root or not os.path.isdir(output_root):
        return False, "Output folder does not exist.", "", 0, 0

    child_entries = _scan_child_tilesets(output_root, parent_name)
    if not child_entries:
        return False, "No child tilesets found in output subfolders.", "", 0, 0

    children = []
    bboxes = []
    child_errors = []
    skipped = 0

    for _, child_tileset_path, child_uri in child_entries:
        try:
            with open(child_tileset_path, "r", encoding="utf-8") as f:
                child_data = json.load(f)
        except Exception:
            skipped += 1
            continue

        root = child_data.get("root")
        if not isinstance(root, dict):
            skipped += 1
            continue
        bounding_volume = root.get("boundingVolume", {})
        box_vals = bounding_volume.get("box")
        bbox = _aabb_from_3dtiles_box(box_vals)
        if bbox is None:
            skipped += 1
            continue

        child_error = float(child_data.get("geometricError", root.get("geometricError", 0.0)) or 0.0)
        children.append(
            {
                "boundingVolume": {"box": box_vals},
                "geometricError": max(child_error, 0.0),
                "refine": "REPLACE",
                "content": {"uri": child_uri},
            }
        )
        bboxes.append(bbox)
        child_errors.append(max(child_error, 0.0))

    if not children:
        return False, "Child tilesets found, but none had a valid root boundingVolume.box.", "", 0, skipped

    union_bbox = _bbox_union_many(bboxes)
    if union_bbox is None:
        return False, "Unable to compute parent bounding volume.", "", 0, skipped

    max_child_error = max(child_errors) if child_errors else 0.0
    root_error = max(max_child_error, max(_bbox_diag_len(union_bbox), 1.0))
    parent_tileset = {
        "asset": {"version": "1.1"},
        "geometricError": root_error,
        "root": {
            "boundingVolume": {"box": _bbox_to_box(union_bbox)},
            "geometricError": root_error,
            "refine": "REPLACE",
            "children": children,
        },
    }

    parent_path = os.path.join(output_root, parent_name)
    with open(parent_path, "w", encoding="utf-8") as f:
        json.dump(parent_tileset, f, indent=2)

    return True, f"Parent tileset rebuilt with {len(children)} child tileset(s).", parent_path, len(children), skipped


# ---------------------------------------------------------------------------
#  Mesh preparation / cleanup helpers
# ---------------------------------------------------------------------------
