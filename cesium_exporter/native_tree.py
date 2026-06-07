
from mathutils import Vector

from .tileset_stitcher import _bbox_union_from_face_ids


def _build_face_spatial_data(mesh, to_gltf_yup=False):
    """Build per-face centroids and bounding boxes.

    to_gltf_yup=False: bounding volumes stay in Blender Z-up frame
    (required by 3D Tiles spec). GLB Y-up conversion is handled by
    Blender's glTF exporter (export_yup=True) at export time.
    """
    verts = []
    for v in mesh.vertices:
        co = v.co.copy()
        if to_gltf_yup:
            co = Vector((co.x, co.z, -co.y))
        verts.append(co)
    centroids = {}
    face_mins = {}
    face_maxs = {}
    face_ids = []

    for poly in mesh.polygons:
        vidx = poly.vertices
        xs = [verts[i].x for i in vidx]
        ys = [verts[i].y for i in vidx]
        zs = [verts[i].z for i in vidx]
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)
        min_z, max_z = min(zs), max(zs)
        centroids[poly.index] = (
            sum(xs) / len(xs),
            sum(ys) / len(ys),
            sum(zs) / len(zs),
        )
        face_mins[poly.index] = (min_x, min_y, min_z)
        face_maxs[poly.index] = (max_x, max_y, max_z)
        face_ids.append(poly.index)

    return face_ids, centroids, face_mins, face_maxs

def _split_face_ids(face_ids, centroids, bbox, tree_type, face_mins=None, face_maxs=None):
    # Face overlap split: a face whose bbox crosses a bin boundary enters every
    # bin it touches (not only the bin of its centroid). Eliminates faces that
    # protrude outside their tile's bounding volume.
    # Falls back to centroid-only assignment if face_mins/face_maxs are not
    # provided (legacy callers).
    (min_x, min_y, min_z), (max_x, max_y, max_z) = bbox
    mid_x = (min_x + max_x) * 0.5
    mid_y = (min_y + max_y) * 0.5
    mid_z = (min_z + max_z) * 0.5

    overlap = face_mins is not None and face_maxs is not None
    bins = {}
    groups = []
    if tree_type == 'OCTREE':
        if overlap:
            for fid in face_ids:
                fmin = face_mins[fid]
                fmax = face_maxs[fid]
                ix_lo = 0 if fmin[0] <  mid_x else 1
                ix_hi = 1 if fmax[0] >= mid_x else 0
                iy_lo = 0 if fmin[1] <  mid_y else 1
                iy_hi = 1 if fmax[1] >= mid_y else 0
                iz_lo = 0 if fmin[2] <  mid_z else 1
                iz_hi = 1 if fmax[2] >= mid_z else 0
                for ix in range(ix_lo, ix_hi + 1):
                    for iy in range(iy_lo, iy_hi + 1):
                        for iz in range(iz_lo, iz_hi + 1):
                            slot = ix + (iy * 2) + (iz * 4)
                            bins.setdefault(slot, []).append(fid)
        else:
            for fid in face_ids:
                cx, cy, cz = centroids[fid]
                ix = 1 if cx >= mid_x else 0
                iy = 1 if cy >= mid_y else 0
                iz = 1 if cz >= mid_z else 0
                slot = ix + (iy * 2) + (iz * 4)
                bins.setdefault(slot, []).append(fid)
        for slot in range(8):
            vals = bins.get(slot)
            if vals:
                groups.append((slot, vals))
    else:
        if overlap:
            for fid in face_ids:
                fmin = face_mins[fid]
                fmax = face_maxs[fid]
                ix_lo = 0 if fmin[0] <  mid_x else 1
                ix_hi = 1 if fmax[0] >= mid_x else 0
                iy_lo = 0 if fmin[1] <  mid_y else 1
                iy_hi = 1 if fmax[1] >= mid_y else 0
                for ix in range(ix_lo, ix_hi + 1):
                    for iy in range(iy_lo, iy_hi + 1):
                        slot = ix + (iy * 2)
                        bins.setdefault(slot, []).append(fid)
        else:
            for fid in face_ids:
                cx, cy, _ = centroids[fid]
                ix = 1 if cx >= mid_x else 0
                iy = 1 if cy >= mid_y else 0
                slot = ix + (iy * 2)
                bins.setdefault(slot, []).append(fid)
        for slot in range(4):
            vals = bins.get(slot)
            if vals:
                groups.append((slot, vals))

    return groups

def _child_split_bbox(parent_bbox, slot, tree_type):
    (min_x, min_y, min_z), (max_x, max_y, max_z) = parent_bbox
    mid_x = (min_x + max_x) * 0.5
    mid_y = (min_y + max_y) * 0.5
    mid_z = (min_z + max_z) * 0.5

    ix = slot & 1
    iy = (slot >> 1) & 1
    iz = (slot >> 2) & 1

    cmin_x = mid_x if ix else min_x
    cmax_x = max_x if ix else mid_x
    cmin_y = mid_y if iy else min_y
    cmax_y = max_y if iy else mid_y

    if tree_type == 'OCTREE':
        cmin_z = mid_z if iz else min_z
        cmax_z = max_z if iz else mid_z
    else:
        cmin_z = min_z
        cmax_z = max_z

    return (cmin_x, cmin_y, cmin_z), (cmax_x, cmax_y, cmax_z)

def _build_native_tree(
    face_ids, depth, tree_type, max_faces, min_depth, max_depth,
    centroids, face_mins, face_maxs,
    path_code="", grid_x=0, grid_y=0, grid_z=0, split_bbox=None,
):
    bbox = _bbox_union_from_face_ids(face_ids, face_mins, face_maxs)
    # cell_bbox is the IDEALIZED octree cell bbox (uniform subdivision of root).
    # When the caller provides split_bbox (IMPLICIT_TILING layout) it propagates
    # down the tree via _child_split_bbox. The real geometric clipping at
    # export time uses cell_bbox; bbox stays as the face-union extent for
    # 3D Tiles boundingVolume reporting (it's the tight bbox of the content).
    cell_bbox = split_bbox if split_bbox is not None else bbox
    node = {
        "depth": depth,
        "path_code": path_code,
        "grid_x": int(grid_x),
        "grid_y": int(grid_y),
        "grid_z": int(grid_z),
        "bbox": bbox,
        "cell_bbox": cell_bbox,
        "face_ids": face_ids,
        "children": [],
    }

    should_split = (depth < max_depth) and (depth < min_depth or len(face_ids) > max_faces)
    if not should_split:
        return node

    split_basis_bbox = split_bbox if split_bbox is not None else bbox
    split_groups = _split_face_ids(
        face_ids, centroids, split_basis_bbox, tree_type,
        face_mins=face_mins, face_maxs=face_maxs,
    )
    if len(split_groups) <= 1:
        return node

    for slot, group in split_groups:
        child_x = (grid_x * 2) + (slot & 1)
        child_y = (grid_y * 2) + ((slot >> 1) & 1)
        if tree_type == 'OCTREE':
            child_z = (grid_z * 2) + ((slot >> 2) & 1)
        else:
            child_z = grid_z
        child_split_bbox = _child_split_bbox(split_basis_bbox, slot, tree_type) if split_bbox is not None else None
        child = _build_native_tree(
            face_ids=group,
            depth=depth + 1,
            tree_type=tree_type,
            max_faces=max_faces,
            min_depth=min_depth,
            max_depth=max_depth,
            centroids=centroids,
            face_mins=face_mins,
            face_maxs=face_maxs,
            path_code=f"{path_code}{slot}",
            grid_x=child_x,
            grid_y=child_y,
            grid_z=child_z,
            split_bbox=child_split_bbox,
        )
        node["children"].append(child)

    return node

def _collect_native_leaves(node, out):
    if not node["children"]:
        out.append(node)
        return
    for child in node["children"]:
        _collect_native_leaves(child, out)

def _collect_native_nodes(node, out):
    out.append(node)
    for child in node.get("children", []):
        _collect_native_nodes(child, out)

def _collect_nodes_at_depth(node, depth, out):
    if node["depth"] == depth:
        out.append(node)
        return
    for child in node.get("children", []):
        _collect_nodes_at_depth(child, depth, out)


# ---------------------------------------------------------------------------
#  LOD auto-parametrization
# ---------------------------------------------------------------------------
