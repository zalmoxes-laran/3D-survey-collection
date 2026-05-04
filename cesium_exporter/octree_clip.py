"""Geometric clipping primitives for the cesium_exporter octree.

The classic octree-with-3D-Tiles pipeline (Cesium Ion, 3DTilesIndex, etc.)
produces tiles whose **geometry is fully contained** in their cell bounding
volume. Faces that cross a cell boundary are *split* at the boundary so each
fragment lives in exactly one cell. This is the missing ingredient for a
"real real" octree as opposed to the centroid- or bbox-overlap sort that this
package historically used.

Implementation: `bmesh.ops.bisect_plane` against the 6 axis-aligned planes
of the cell bounding box. Per-face data (UVs, vertex colors) is interpolated
linearly across cuts by the bmesh op.

This module is intentionally bmesh-only and does not import the rest of the
package, so it can be unit-tested in headless Blender with no addon
registration.
"""

from __future__ import annotations

import bmesh


def _clip_bm_to_bbox(bm, bbox, epsilon=1e-6):
    """Clip a bmesh in-place to an axis-aligned bbox.

    Faces that straddle a face of the bbox are split along the boundary and
    the outside portion is discarded. After this call the bmesh's geometry
    is fully contained in `bbox` (modulo the snap epsilon).

    Args:
        bm: bmesh.types.BMesh, modified in place.
        bbox: ((min_x, min_y, min_z), (max_x, max_y, max_z)) world-space.
        epsilon: snap tolerance — vertices within this distance from a
            cutting plane are snapped onto it (also avoids creating
            sub-epsilon slivers).

    Returns:
        Number of faces remaining after clipping.
    """
    (min_x, min_y, min_z), (max_x, max_y, max_z) = bbox

    # Six clipping planes. Plane normal points OUTWARD from the bbox interior;
    # `clear_outer=True` drops everything on the outward side of the plane.
    planes = (
        ((min_x, 0.0, 0.0), (-1.0, 0.0,  0.0)),  # X-min
        ((max_x, 0.0, 0.0), ( 1.0, 0.0,  0.0)),  # X-max
        ((0.0, min_y, 0.0), ( 0.0,-1.0,  0.0)),  # Y-min
        ((0.0, max_y, 0.0), ( 0.0, 1.0,  0.0)),  # Y-max
        ((0.0, 0.0, min_z), ( 0.0, 0.0, -1.0)),  # Z-min
        ((0.0, 0.0, max_z), ( 0.0, 0.0,  1.0)),  # Z-max
    )

    for plane_co, plane_no in planes:
        if not bm.faces:
            break
        geom = list(bm.verts) + list(bm.edges) + list(bm.faces)
        bmesh.ops.bisect_plane(
            bm,
            geom=geom,
            dist=epsilon,
            plane_co=plane_co,
            plane_no=plane_no,
            use_snap_center=False,
            clear_outer=True,
            clear_inner=False,
        )
        # bisect_plane can leave dangling verts/edges; clean them
        bmesh.ops.delete(
            bm,
            geom=[v for v in bm.verts if not v.link_faces],
            context='VERTS',
        )

    return len(bm.faces)


def _clip_quadtree_bm_to_bbox(bm, bbox, epsilon=1e-6):
    """Same as `_clip_bm_to_bbox` but only clips X and Y planes.

    Use this for QUADTREE cells where the Z extent is the full mesh extent
    (cells are infinite columns along Z, not boxes).
    """
    (min_x, min_y, _), (max_x, max_y, _) = bbox
    planes = (
        ((min_x, 0.0, 0.0), (-1.0, 0.0, 0.0)),
        ((max_x, 0.0, 0.0), ( 1.0, 0.0, 0.0)),
        ((0.0, min_y, 0.0), ( 0.0,-1.0, 0.0)),
        ((0.0, max_y, 0.0), ( 0.0, 1.0, 0.0)),
    )
    for plane_co, plane_no in planes:
        if not bm.faces:
            break
        geom = list(bm.verts) + list(bm.edges) + list(bm.faces)
        bmesh.ops.bisect_plane(
            bm,
            geom=geom,
            dist=epsilon,
            plane_co=plane_co,
            plane_no=plane_no,
            use_snap_center=False,
            clear_outer=True,
            clear_inner=False,
        )
        bmesh.ops.delete(
            bm,
            geom=[v for v in bm.verts if not v.link_faces],
            context='VERTS',
        )
    return len(bm.faces)


def clip_mesh_to_cell(mesh_data, cell_bbox, tree_type='OCTREE', epsilon=1e-6):
    """Clip a Blender mesh datablock to a cell bbox in-place.

    Convenience wrapper that opens a bmesh on `mesh_data`, clips it, writes
    back, and returns the resulting face count.

    Args:
        mesh_data: bpy.types.Mesh.
        cell_bbox: ((min_x, min_y, min_z), (max_x, max_y, max_z)).
        tree_type: 'OCTREE' (clip 6 planes) or 'QUADTREE' (clip 4 planes,
            preserve Z extent).
        epsilon: snap tolerance.

    Returns:
        Face count after clipping.
    """
    bm = bmesh.new()
    bm.from_mesh(mesh_data)
    if tree_type == 'OCTREE':
        n = _clip_bm_to_bbox(bm, cell_bbox, epsilon=epsilon)
    else:
        n = _clip_quadtree_bm_to_bbox(bm, cell_bbox, epsilon=epsilon)
    bm.to_mesh(mesh_data)
    bm.free()
    mesh_data.update()
    return n
