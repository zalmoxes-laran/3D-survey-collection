import math

import bpy


def _pow2_round(x):
    """Round x up to the nearest power of 2, clamped to [64, 8192]."""
    if x <= 64:
        return 64
    p = 64
    while p < x and p < 8192:
        p *= 2
    return p

def _compute_lod_parameters(total_faces, area_m2, max_tex_res, tree_type, scene):
    """Compute LOD depth and per-level decimation/atlas parameters.

    Args:
        total_faces: total polygon count of the mesh
        area_m2: surface area in square metres
        max_tex_res: maximum texture resolution of source images (pixels, e.g. 4096)
        tree_type: 'OCTREE' or 'QUADTREE'
        scene: Blender scene (for user overrides)

    Returns:
        dict with 'max_depth', 'features_per_tile', 'lod_levels' list
    """
    auto_params = bool(getattr(scene, "cesium_lod_auto_params", True))
    leaf_atlas = int(getattr(scene, "cesium_lod_leaf_atlas_size", 1024))
    root_atlas = int(getattr(scene, "cesium_lod_root_atlas_size", 256))

    if auto_params:
        # Auto depth: balance texture resolution with atlas size
        # mean_res_tex_m is in mm/pixel from qualitycheck; convert to m/pixel
        if area_m2 > 0 and max_tex_res > 0:
            bbox_side_estimate = math.sqrt(area_m2)
            # How many leaf_atlas-sized tiles we need per axis?
            tiles_per_axis = max(bbox_side_estimate * 1000.0 / (leaf_atlas * 1.0), 1.0)  # rough
            if tree_type == 'OCTREE':
                max_depth = max(1, min(int(math.ceil(math.log2(tiles_per_axis))), 8))
            else:
                max_depth = max(1, min(int(math.ceil(math.log2(tiles_per_axis))), 10))
        else:
            max_depth = 4

        # Features per tile: target ~8000 faces per leaf
        branching = 8 if tree_type == 'OCTREE' else 4
        features_per_tile = max(2000, int(total_faces / max(branching ** max_depth, 1)))
        features_per_tile = min(features_per_tile, 25000)
    else:
        max_depth = int(getattr(scene, "cesium_native_max_depth", 6))
        features_per_tile = int(scene.cesium_features_per_tile)

    # Build per-level config
    levels = []
    for d in range(max_depth + 1):
        t = d / max(max_depth, 1)  # 0.0 = root, 1.0 = leaf
        # Exponential interpolation for atlas size
        atlas_size = _pow2_round(root_atlas * ((leaf_atlas / max(root_atlas, 1)) ** t))
        atlas_size = max(root_atlas, min(atlas_size, leaf_atlas))
        # Decimation ratio: leaf=1.0, root=small fraction
        if d == max_depth:
            decimation_ratio = 1.0
        else:
            # Ratio decreases as we go up the tree
            decimation_ratio = max(0.01, (atlas_size / leaf_atlas) ** 2)
        levels.append({
            "depth": d,
            "decimation_ratio": round(decimation_ratio, 4),
            "atlas_size": int(atlas_size),
        })

    return {
        "max_depth": max_depth,
        "features_per_tile": features_per_tile,
        "lod_levels": levels,
    }

def _prepare_lod_image_cache(source_image, lod_config):
    """Create downsampled copies of the baked atlas for each LOD level.

    Returns dict {atlas_size_px: bpy.types.Image}.
    """
    cache = {}
    if source_image is None:
        return cache

    source_w = source_image.size[0]
    source_h = source_image.size[1]
    if source_w == 0 or source_h == 0:
        return cache

    # The source image is the leaf atlas (largest)
    cache[source_w] = source_image

    needed_sizes = set()
    for level in lod_config.get("lod_levels", []):
        sz = int(level["atlas_size"])
        if sz != source_w and sz > 0:
            needed_sizes.add(sz)

    for sz in sorted(needed_sizes, reverse=True):
        img_name = f"__CesiumLOD_{sz}px"
        existing = bpy.data.images.get(img_name)
        if existing is not None:
            try:
                bpy.data.images.remove(existing, do_unlink=True)
            except Exception:
                pass

        # Copy the source image pixels and scale down
        lod_img = source_image.copy()
        lod_img.name = img_name
        lod_img.scale(sz, sz)
        try:
            lod_img.pack()
        except Exception:
            pass
        cache[sz] = lod_img

    return cache

def _cleanup_lod_image_cache(cache, keep_source=True):
    """Remove LOD images from bpy.data.images."""
    if not cache:
        return
    for sz, img in list(cache.items()):
        try:
            if keep_source and not img.name.startswith("__CesiumLOD_"):
                continue
            if img is not None and img.users == 0:
                bpy.data.images.remove(img, do_unlink=True)
        except Exception:
            pass


# ===========================================================================
#  BLOCK C: Implicit Tiling, Export, Main Pipeline
# ===========================================================================

# ---------------------------------------------------------------------------
#  Implicit tiling helpers (Morton codes, subtree files)
# ---------------------------------------------------------------------------
