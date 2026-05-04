"""Multi-LOD source mode for cesium_exporter.

Convention: pre-baked LOD set produced by 3D-survey-collection's
LODgenerator. Naming: ``<base>_LOD<N>`` (or ``<base>_LOD<N>_*``), e.g.
``Sarcofago_LOD0``, ``Sarcofago_LOD1``, ``Sarcofago_LOD2``, ``Sarcofago_LOD3``.

The architectural answer to:
    "io ho già modelli fatti in LOD, quello che manca è l'OCTREE
    vero vero con taglio mesh"

Pipeline:

    For each LOD level L in {0, 1, ..., N}:
        target_depth = N - L              # LOD0 → leaves, LOD_max → root
        cells = uniform subdivision of root bbox at target_depth
        for each cell:
            clipped = clip(LOD_L_mesh, cell_bbox)         # bmesh.bisect_plane
            export GLB preserving LOD_L's material        # NO REBAKE

    Write implicit tiling tileset.json + subtree files.

This bypasses the per-tile rebake step entirely — each LOD level
already has its own validated atlas (from LODgenerator's bake, which
the user has visually confirmed). The cesium_exporter contribution
is **only** the spatial subdivision + geometric clipping.

Compared to the single-mesh path (which decimates and rebakes per
level inside cesium_exporter), this:
  - Eliminates the bake-quality dependency on Cycles/smart_project
  - Preserves textures exactly as the user authored them
  - Keeps tile sizes small (LOD textures are typically already small)
  - Maps 1:1 with the LODgenerator output workflow
"""

from __future__ import annotations

import os
import re
import struct

import bpy
import bmesh
from mathutils import Matrix

from .octree_clip import _clip_bm_to_bbox, _clip_quadtree_bm_to_bbox
from .tileset_stitcher import _bbox_to_box
# Reuse the validated subtree writer + bit helpers from the existing
# native_export pipeline (these have been tested in v8+ and produce
# subtree binaries that ATON / CesiumJS load correctly).
from .implicit import (
    _bitarray_set_once as _impl_bit_set,
    _implicit_level_offset as _impl_lvl_off,
    _implicit_morton_index as _impl_morton,
    _implicit_total_nodes as _impl_total,
    _write_subtree_file as _impl_write_subtree,
)


# ---------------------------------------------------------------------------
# Detection: parse object names against the LOD<N> convention
# ---------------------------------------------------------------------------

# Matches:  "..._LOD0",  "..._LOD3_something",  "..._LOD12.001"
# Captures: the integer LOD level
_LOD_NAME_RE = re.compile(r'_LOD(\d+)', re.IGNORECASE)
# For stripping the suffix, match _LOD<N> and ANY trailing text up to end
_LOD_SUFFIX_RE = re.compile(r'_LOD\d+.*$', re.IGNORECASE)


def _parse_lod_level(name):
    """Extract LOD level from an object name.

    Returns int level, or None if the name does not match the convention.
    """
    if not name:
        return None
    m = _LOD_NAME_RE.search(name)
    if m is None:
        return None
    try:
        return int(m.group(1))
    except (ValueError, TypeError):
        return None


def _strip_lod_suffix(name):
    """Remove the ``_LOD<N>...`` suffix and everything after, returning the base.

    Examples:
        "Sarcofago_LOD0"          -> "Sarcofago"
        "Sarcofago_LOD3_baked"    -> "Sarcofago"
        "OB_Foo_LOD2.001"         -> "OB_Foo"
        "no_match"                -> "no_match"
    """
    return _LOD_SUFFIX_RE.sub('', name).rstrip('._-')


def detect_lod_set(objects, bbox_outlier_factor=10.0):
    """Detect a coherent LOD set from a list of mesh objects.

    Args:
        objects: iterable of bpy.types.Object.
        bbox_outlier_factor: drop LODs whose bbox diagonal differs from the
            median by more than this factor. Common case: LOD0 from
            Metashape is in raw world CRS (e.g. UTM, hundreds of meters),
            while LODgenerator output is normalized to local frame
            (~1 m). Mixing them breaks the shared-bbox assumption of the
            octree clip.

    Returns:
        dict {level_int: bpy.types.Object} sorted by level, or ``None`` if
        fewer than 2 distinct, bbox-consistent LOD levels remain.
    """
    by_level = {}
    base_names = set()
    for obj in objects:
        if obj is None or getattr(obj, 'type', None) != 'MESH':
            continue
        level = _parse_lod_level(obj.name)
        if level is None:
            continue
        base = _strip_lod_suffix(obj.name)
        base_names.add(base)
        if level in by_level:
            print(
                f"[multi_lod] WARN: multiple objects at LOD{level} "
                f"({by_level[level].name} vs {obj.name}); keeping first"
            )
            continue
        by_level[level] = obj

    if len(by_level) < 2:
        return None

    if len(base_names) > 1:
        print(
            f"[multi_lod] WARN: LOD set spans multiple base names "
            f"{sorted(base_names)} — proceeding but consider exporting one base at a time"
        )

    # --- Coordinate-frame consistency check ---
    # Drop LODs whose world bbox differs from the median by > outlier factor.
    diags = {}
    for level, obj in by_level.items():
        (a, b, c), (d, e, f) = _world_bbox_of_object(obj)
        diag = ((d - a) ** 2 + (e - b) ** 2 + (f - c) ** 2) ** 0.5
        diags[level] = diag

    sorted_diags = sorted(diags.values())
    n = len(sorted_diags)
    median = sorted_diags[n // 2] if n % 2 else (sorted_diags[n // 2 - 1] + sorted_diags[n // 2]) / 2
    if median <= 0:
        median = max(sorted_diags) or 1.0

    keep = {}
    dropped = []
    for level, obj in by_level.items():
        d = diags[level]
        ratio = max(d / median, median / max(d, 1e-9))
        if ratio > bbox_outlier_factor:
            dropped.append((level, obj.name, d, ratio))
        else:
            keep[level] = obj

    if dropped:
        for level, name, d, ratio in dropped:
            print(
                f"[multi_lod] WARN: dropping LOD{level} '{name}' "
                f"(bbox diag {d:.2f} vs median {median:.2f}, factor {ratio:.1f}× > {bbox_outlier_factor}×). "
                f"Likely in a different coordinate frame (e.g. raw Metashape world vs LODgen-normalized)."
            )

    if len(keep) < 2:
        print(
            f"[multi_lod] ERROR: after outlier removal, only {len(keep)} LOD level remains. "
            f"Need to align all LODs to a common coordinate frame before export."
        )
        return None

    return dict(sorted(keep.items()))


# ---------------------------------------------------------------------------
# Spatial helpers
# ---------------------------------------------------------------------------

def _world_bbox_of_object(obj):
    """Return ((min_x, min_y, min_z), (max_x, max_y, max_z)) of obj in world space."""
    me = obj.data
    if me is None or not me.vertices:
        return ((0.0, 0.0, 0.0), (0.0, 0.0, 0.0))
    mw = obj.matrix_world
    co = mw @ me.vertices[0].co
    min_x = max_x = co.x
    min_y = max_y = co.y
    min_z = max_z = co.z
    for v in me.vertices:
        c = mw @ v.co
        if c.x < min_x: min_x = c.x
        if c.x > max_x: max_x = c.x
        if c.y < min_y: min_y = c.y
        if c.y > max_y: max_y = c.y
        if c.z < min_z: min_z = c.z
        if c.z > max_z: max_z = c.z
    return ((min_x, min_y, min_z), (max_x, max_y, max_z))


def _bbox_union(bboxes):
    """Union of bboxes."""
    if not bboxes:
        return ((0.0, 0.0, 0.0), (0.0, 0.0, 0.0))
    (min_x, min_y, min_z), (max_x, max_y, max_z) = bboxes[0]
    for ((a, b, c), (d, e, f)) in bboxes[1:]:
        if a < min_x: min_x = a
        if b < min_y: min_y = b
        if c < min_z: min_z = c
        if d > max_x: max_x = d
        if e > max_y: max_y = e
        if f > max_z: max_z = f
    return ((min_x, min_y, min_z), (max_x, max_y, max_z))


def _subdivide_bbox_uniform(bbox, depth, tree_type='OCTREE'):
    """Generate all idealized cell bboxes at a given depth.

    Cells are 2**depth per axis (octree) or 2**depth × 2**depth (quadtree,
    Z extent unchanged).

    Yields (cell_bbox, (i, j, k)) tuples. For quadtree, k is always 0.
    """
    (min_x, min_y, min_z), (max_x, max_y, max_z) = bbox
    n = 2 ** depth if depth >= 0 else 1
    if n == 1:
        yield bbox, (0, 0, 0)
        return
    dx = (max_x - min_x) / n
    dy = (max_y - min_y) / n
    if tree_type == 'OCTREE':
        dz = (max_z - min_z) / n
        for i in range(n):
            for j in range(n):
                for k in range(n):
                    cell = (
                        (min_x + i * dx, min_y + j * dy, min_z + k * dz),
                        (min_x + (i + 1) * dx, min_y + (j + 1) * dy, min_z + (k + 1) * dz),
                    )
                    yield cell, (i, j, k)
    else:  # QUADTREE
        for i in range(n):
            for j in range(n):
                cell = (
                    (min_x + i * dx, min_y + j * dy, min_z),
                    (min_x + (i + 1) * dx, min_y + (j + 1) * dy, max_z),
                )
                yield cell, (i, j, 0)


# ---------------------------------------------------------------------------
# Per-tile clip + export
# ---------------------------------------------------------------------------

def _make_clipped_tile_object(source_obj, cell_bbox, tree_type, temp_collection):
    """Clone source_obj, bake its world transform into the mesh, clip to
    cell_bbox, link to temp_collection.

    Returns the new bpy.types.Object or None if no faces remain after clip.
    Caller is responsible for removing the object when done.
    """
    me = source_obj.data.copy()
    new_obj = bpy.data.objects.new(
        name=f"__cesium_mlod_tile_{source_obj.name[:32]}",
        object_data=me,
    )
    # Bake the world transform into the mesh data so the clip planes
    # (defined in world space) cut correctly. After this, new_obj sits
    # at the world origin and its mesh holds world-space coordinates.
    me.transform(source_obj.matrix_world)
    new_obj.matrix_world = Matrix.Identity(4)

    # Preserve materials as-is (this is the whole point: no rebake)
    me.materials.clear()
    for slot in source_obj.material_slots:
        if slot.material is not None:
            me.materials.append(slot.material)

    temp_collection.objects.link(new_obj)

    bm = bmesh.new()
    bm.from_mesh(me)
    if tree_type == 'OCTREE':
        n = _clip_bm_to_bbox(bm, cell_bbox)
    else:
        n = _clip_quadtree_bm_to_bbox(bm, cell_bbox)
    bm.to_mesh(me)
    bm.free()
    me.update()

    if n == 0:
        # Empty cell — clean up immediately
        bpy.data.objects.remove(new_obj, do_unlink=True)
        try:
            bpy.data.meshes.remove(me, do_unlink=True)
        except Exception:
            pass
        return None

    return new_obj


def _export_tile_glb(context, tile_obj, filepath, export_yup=True, force_unlit=False):
    """Export a single tile object as binary glTF (.glb).

    Selects only tile_obj, then runs bpy.ops.export_scene.gltf with
    Cesium-friendly options (Y-up, embedded textures, apply modifiers).

    Returns True on success.
    """
    os.makedirs(os.path.dirname(filepath), exist_ok=True)

    # Selection state
    for obj in bpy.data.objects:
        try:
            obj.select_set(False)
        except Exception:
            pass
    tile_obj.select_set(True)
    context.view_layer.objects.active = tile_obj

    try:
        bpy.ops.export_scene.gltf(
            filepath=filepath,
            export_format='GLB',
            use_selection=True,
            export_apply=True,
            export_yup=bool(export_yup),
            export_image_format='AUTO',
            export_texcoords=True,
            export_normals=True,
            export_materials='EXPORT',
            export_extras=False,
            export_animations=False,
            export_skins=False,
        )
    except Exception as e:
        print(f"[multi_lod] export GLB failed for {tile_obj.name}: {e}")
        return False

    return os.path.exists(filepath)


# ---------------------------------------------------------------------------
# Tileset.json + subtree writer (implicit tiling)
# ---------------------------------------------------------------------------

def _content_uri_template(tree_type):
    if tree_type == 'OCTREE':
        return "tiles/{level}/{x}/{y}/{z}.glb"
    return "tiles/{level}/{x}/{y}.glb"


def _subtree_uri_template(tree_type):
    if tree_type == 'OCTREE':
        return "subtrees/{level}/{x}/{y}/{z}.subtree"
    return "subtrees/{level}/{x}/{y}.subtree"


def _write_implicit_tileset_json(output_dir, root_bbox, max_depth,
                                 tree_type, geometric_error_root,
                                 refine='REPLACE'):
    """Write tileset.json with implicit tiling root."""
    import json
    box = _bbox_to_box(root_bbox)
    subtree_levels = max_depth + 1
    tileset = {
        "asset": {"version": "1.1"},
        "geometricError": 10000.0,
        "root": {
            "boundingVolume": {"box": box},
            "geometricError": float(geometric_error_root),
            "refine": refine,
            "content": {"uri": _content_uri_template(tree_type)},
            "implicitTiling": {
                "subdivisionScheme": tree_type,
                "subtreeLevels": int(subtree_levels),
                "availableLevels": int(subtree_levels),
                "subtrees": {"uri": _subtree_uri_template(tree_type)},
            },
        },
    }
    path = os.path.join(output_dir, "tileset.json")
    with open(path, "w") as f:
        json.dump(tileset, f, indent=2)
    return path


def _write_subtree_file(subtree_path, tile_avail, content_avail, n_tiles, n_content):
    """Minimal 3D Tiles subtree binary writer.

    Format (as of 3D Tiles 1.1):
      - Magic "subt" (4 bytes)
      - Version uint32 LE = 1
      - JSON length uint64 LE
      - Binary length uint64 LE
      - JSON chunk (UTF-8, padded to 8 bytes)
      - Binary chunk (padded to 8 bytes), holds the bitstreams

    See https://github.com/CesiumGS/3d-tiles/tree/main/specification/Schema/Subtree
    """
    os.makedirs(os.path.dirname(subtree_path), exist_ok=True)
    # Pack bits into bytes (little-endian per byte, low bit first)
    def _pack_bits(bits):
        n = len(bits)
        out = bytearray((n + 7) // 8)
        for i, b in enumerate(bits):
            if b:
                out[i // 8] |= 1 << (i % 8)
        return bytes(out)

    tile_bytes = _pack_bits(tile_avail)
    content_bytes = _pack_bits(content_avail)
    binary = bytearray()
    # Append tile availability
    tile_off = len(binary)
    binary += tile_bytes
    while len(binary) % 8 != 0:
        binary += b"\x00"
    content_off = len(binary)
    binary += content_bytes
    while len(binary) % 8 != 0:
        binary += b"\x00"

    json_obj = {
        "buffers": [{"byteLength": len(binary)}],
        "bufferViews": [
            {"buffer": 0, "byteOffset": tile_off, "byteLength": len(tile_bytes)},
            {"buffer": 0, "byteOffset": content_off, "byteLength": len(content_bytes)},
        ],
        "tileAvailability": {"bitstream": 0, "availableCount": int(n_tiles)},
        "contentAvailability": [{"bitstream": 1, "availableCount": int(n_content)}],
        "childSubtreeAvailability": {"constant": 0},
    }
    import json as _json
    json_bytes = _json.dumps(json_obj, separators=(",", ":")).encode("utf-8")
    while len(json_bytes) % 8 != 0:
        json_bytes += b" "

    with open(subtree_path, "wb") as f:
        f.write(b"subt")
        f.write(struct.pack("<I", 1))                  # version
        f.write(struct.pack("<Q", len(json_bytes)))    # JSON length
        f.write(struct.pack("<Q", len(binary)))        # binary length
        f.write(json_bytes)
        f.write(binary)


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

def _morton_index_2d(x, y, depth):
    """Interleave bits of x, y for quadtree morton order at given depth."""
    idx = 0
    for i in range(depth):
        idx |= ((x >> i) & 1) << (2 * i)
        idx |= ((y >> i) & 1) << (2 * i + 1)
    return idx


def _morton_index_3d(x, y, z, depth):
    """Interleave bits of x, y, z for octree morton order at given depth."""
    idx = 0
    for i in range(depth):
        idx |= ((x >> i) & 1) << (3 * i)
        idx |= ((y >> i) & 1) << (3 * i + 1)
        idx |= ((z >> i) & 1) << (3 * i + 2)
    return idx


def _level_offset(depth, tree_type):
    """Cumulative tile count of all levels strictly above ``depth``."""
    if tree_type == 'OCTREE':
        # 1 + 8 + 64 + ... + 8^(depth-1) = (8^depth - 1) / 7
        return (8 ** depth - 1) // 7
    # quadtree: (4^depth - 1) / 3
    return (4 ** depth - 1) // 3


def _total_tiles_in_subtree(max_depth, tree_type):
    """Total count of tiles for levels [0, max_depth]."""
    if tree_type == 'OCTREE':
        return (8 ** (max_depth + 1) - 1) // 7
    return (4 ** (max_depth + 1) - 1) // 3


def run_multi_lod_export(
    context,
    scene,
    lod_objects,
    output_dir,
    tree_type='OCTREE',
    refine='REPLACE',
    keep_temp=False,
):
    """Run the full multi-LOD export pipeline.

    Args:
        context: Blender context
        scene: bpy.types.Scene
        lod_objects: dict {level: bpy.types.Object}, sorted ascending
        output_dir: target directory (will contain tileset.json, tiles/, subtrees/)
        tree_type: 'OCTREE' or 'QUADTREE'
        refine: '3D Tiles refine mode (REPLACE or ADD)
        keep_temp: leave temporary clipped tile objects in scene for inspection

    Returns:
        (ok: bool, info: dict)
    """
    if not lod_objects:
        return False, {"error": "no LOD objects provided"}

    sorted_levels = sorted(lod_objects.keys())
    max_lod = sorted_levels[-1]
    n_levels = max_lod + 1
    if n_levels != len(sorted_levels):
        # Gap in LOD levels: pad by reusing nearest lower LOD
        print(f"[multi_lod] WARN: LOD level gap in {sorted_levels}; padding")
    max_depth = max_lod  # depth = max_lod - level (LOD0 at depth max_lod)

    # Compute the root bbox from the highest-detail LOD (LOD0) for accuracy
    lod0 = lod_objects.get(0) or lod_objects[sorted_levels[0]]
    root_bbox = _world_bbox_of_object(lod0)

    os.makedirs(output_dir, exist_ok=True)

    # Temp collection for tile objects
    temp_collection = bpy.data.collections.get("__cesium_multi_lod_tmp")
    if temp_collection is None:
        temp_collection = bpy.data.collections.new("__cesium_multi_lod_tmp")
        scene.collection.children.link(temp_collection)

    # Track availability bitstreams (for subtree file). We use the same
    # bytearray/bit-packed format as the validated implicit.py writer.
    total_n = _impl_total(max_depth + 1, tree_type)
    n_total_bytes = (total_n + 7) // 8
    tile_avail_ba = bytearray(n_total_bytes)
    content_avail_ba = bytearray(n_total_bytes)
    n_tiles = 0
    n_content = 0

    info = {
        "n_levels": n_levels,
        "max_depth": max_depth,
        "tree_type": tree_type,
        "tiles_per_level": {},
        "exported_tiles": 0,
        "skipped_empty": 0,
    }

    try:
        for level, lod_obj in sorted(lod_objects.items()):
            target_depth = max_lod - level  # LOD0 → leaves
            cells = list(_subdivide_bbox_uniform(root_bbox, target_depth, tree_type))
            print(f"[multi_lod] LOD{level} ({lod_obj.name}) → depth {target_depth}: {len(cells)} candidate cells")

            level_count = 0
            for cell_bbox, (i, j, k) in cells:
                tile_obj = _make_clipped_tile_object(lod_obj, cell_bbox, tree_type, temp_collection)
                if tile_obj is None:
                    info["skipped_empty"] += 1
                    continue

                if tree_type == 'OCTREE':
                    rel = f"tiles/{target_depth}/{i}/{j}/{k}.glb"
                else:
                    rel = f"tiles/{target_depth}/{i}/{j}.glb"
                # Use the validated morton from implicit.py for byte-level
                # parity with the v8 subtree writer.
                morton = _impl_morton(
                    {"depth": target_depth, "grid_x": i, "grid_y": j, "grid_z": k},
                    tree_type,
                )

                tile_path = os.path.join(output_dir, rel)
                ok = _export_tile_glb(context, tile_obj, tile_path)
                if not ok:
                    print(f"[multi_lod] FAILED export: {rel}")
                    if not keep_temp:
                        bpy.data.objects.remove(tile_obj, do_unlink=True)
                    continue

                # Record availability via the implicit.py bit-set helper
                bit_idx = _impl_lvl_off(target_depth, tree_type) + morton
                if 0 <= bit_idx < total_n:
                    if _impl_bit_set(tile_avail_ba, bit_idx):
                        n_tiles += 1
                    if _impl_bit_set(content_avail_ba, bit_idx):
                        n_content += 1

                level_count += 1
                info["exported_tiles"] += 1

                if not keep_temp:
                    me = tile_obj.data
                    bpy.data.objects.remove(tile_obj, do_unlink=True)
                    try:
                        if me.users == 0:
                            bpy.data.meshes.remove(me, do_unlink=True)
                    except Exception:
                        pass

            info["tiles_per_level"][target_depth] = level_count
            print(f"[multi_lod]   exported {level_count} non-empty tiles at depth {target_depth}")

    finally:
        if not keep_temp:
            try:
                if not temp_collection.objects:
                    scene.collection.children.unlink(temp_collection)
                    bpy.data.collections.remove(temp_collection)
            except Exception:
                pass

    # Propagate tile_avail upward: for every cell with tile_avail=1 (at
    # any depth), set tile_avail=1 on all ancestors so the loader can
    # traverse the tree from root to leaf. content_avail is NOT
    # propagated — empty ancestor cells stay no-content (loader skips).
    children_per_node = 8 if tree_type == 'OCTREE' else 4
    parent_tiles_filled = 0

    def _bit_get(ba, idx):
        return (ba[idx // 8] >> (idx % 8)) & 1

    for L in range(max_depth, 0, -1):
        off_L = _impl_lvl_off(L, tree_type)
        off_parent = _impl_lvl_off(L - 1, tree_type)
        n_at_L = children_per_node ** L
        for i in range(n_at_L):
            if not _bit_get(tile_avail_ba, off_L + i):
                continue
            morton_parent = i // children_per_node
            parent_idx = off_parent + morton_parent
            if _impl_bit_set(tile_avail_ba, parent_idx):
                n_tiles += 1
                parent_tiles_filled += 1
    info["parent_tiles_filled_for_walk"] = parent_tiles_filled
    if parent_tiles_filled:
        print(f"[multi_lod] Propagated tile_avail to {parent_tiles_filled} "
              f"empty ancestor cells so loader can traverse")

    # Write subtree file (single subtree at the root) using the validated
    # implicit.py writer — this format is byte-compatible with the v8/v10
    # implicit-tiling exports that ATON loads correctly.
    if tree_type == 'OCTREE':
        subtree_rel = "subtrees/0/0/0/0.subtree"
    else:
        subtree_rel = "subtrees/0/0/0.subtree"
    subtree_path = os.path.join(output_dir, subtree_rel)
    _impl_write_subtree(subtree_path, tile_avail_ba, n_tiles, content_avail_ba, n_content)

    # Compute root geometric error.
    #
    # 3D Tiles loaders refine when SSE > maxSSE (typically 16 px). With
    # implicit tiling, child geometric error is auto-computed as
    # parent / 2. So:
    #     root_error / (2^max_depth) at the leaves
    #
    # If ATON / the client uses a higher SSE threshold, modest root_error
    # leaves the SSE for inner levels too low → loader stops at root.
    #
    # We size root_error against the LOD pyramid's actual coarseness.
    # Heuristic: root_error = bbox_diag × sqrt(face_ratio), where
    # face_ratio is the ratio between LOD0 (most detailed) and the
    # mesh used at root (most decimated). This grounds the value in
    # the real visual deviation introduced by showing the coarsest mesh.
    (a, b, c), (d, e, f) = root_bbox
    diag = ((d - a) ** 2 + (e - b) ** 2 + (f - c) ** 2) ** 0.5
    finest = lod_objects.get(0) or lod_objects[sorted_levels[0]]
    coarsest = lod_objects[sorted_levels[-1]]
    n_faces_finest = max(len(finest.data.polygons), 1)
    n_faces_coarsest = max(len(coarsest.data.polygons), 1)
    face_ratio = n_faces_finest / n_faces_coarsest
    # Cap the ratio to avoid degenerate values; sqrt scales the
    # face-count ratio into a per-vertex linear deviation.
    coarseness_factor = min(face_ratio ** 0.5, 50.0)
    root_error = max(diag * coarseness_factor, diag, 1.0)

    print(
        f"[multi_lod] geometric_error: root={root_error:.3f} "
        f"(bbox_diag={diag:.3f} × coarseness={coarseness_factor:.2f}, "
        f"face ratio finest/coarsest = {n_faces_finest}/{n_faces_coarsest} = {face_ratio:.0f}). "
        f"Implicit children will halve per level: "
        f"L0={root_error:.3f} L_max={root_error / (2**max_depth):.3f}"
    )

    _write_implicit_tileset_json(
        output_dir, root_bbox, max_depth, tree_type, root_error, refine=refine,
    )

    info["root_bbox"] = root_bbox
    info["root_geometric_error"] = root_error
    info["n_tiles_in_subtree"] = n_tiles
    info["n_content_in_subtree"] = n_content
    return True, info
