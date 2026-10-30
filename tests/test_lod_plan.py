"""pytest for lod_plan.py — how many textures, how large, per level (no Blender).

The rules are the Cesium exporter's: texel density of the original textures
rounded to the nearest power of two (native_bake._original_texel_atlas_size),
16 px per face rounded up when there is no texture
(native_export._auto_atlas_size_for_tile), ratio = (side / leaf side)²
(lod._compute_lod_parameters). New: a level that does not fit one
max_texture_size atlas gets several.
"""
import importlib.util
from pathlib import Path

import pytest

_MOD = Path(__file__).resolve().parents[1] / "lod_plan.py"
_spec = importlib.util.spec_from_file_location("lod_plan", _MOD)
lp = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(lp)


def test_lod_plan_does_not_import_bpy():
    assert "import bpy" not in _MOD.read_text(encoding="utf-8")


def test_default_chain_halves_the_texture_side_per_level():
    assert lp.level_ratios(3) == [1.0, 0.25, 0.0625]
    assert lp.level_ratios([1, 0.5, 0.1]) == [1.0, 0.5, 0.1]
    for bad in (0, [], [1.0, 0.0], [1.5], True):
        with pytest.raises(ValueError):
            lp.level_ratios(bad)


def test_one_texture_while_it_fits_rounded_as_native_bake():
    # sqrt(3.8e6) = 1949 -> 2048 (nearest), 1.0e6 -> 1000 -> 1024
    assert lp.textures_for_pixels(3.8e6) == (1, 2048)
    assert lp.textures_for_pixels(1.0e6) == (1, 1024)
    assert lp.textures_for_pixels(10) == (1, 256)            # min_size
    assert lp.textures_for_pixels(0) == (1, 256)
    # nearest rounding keeps one 4096 up to 2 x 4096² ...
    assert lp.textures_for_pixels(1.9 * 4096 ** 2) == (1, 4096)
    # ... beyond, several 4096 atlases instead of one clamped
    assert lp.textures_for_pixels(2.2 * 4096 ** 2) == (2, 4096)
    assert lp.textures_for_pixels(5.4 * 4096 ** 2) == (5, 4096)
    assert lp.textures_for_pixels(100 * 4096 ** 2) == (16, 4096)   # max_textures
    assert lp.textures_for_pixels(5.4 * 4096 ** 2, max_textures=1) == (1, 4096)
    assert lp.textures_for_pixels(5.4 * 2048 ** 2, max_size=2048) == (5, 2048)


def test_face_count_fallback_is_auto_atlas_size_for_tile():
    # the examples of native_export._auto_atlas_size_for_tile (16 px/face, up)
    for faces, side in ((5_000, 512), (10_000, 512), (30_000, 1024), (100_000, 2048),
                        (486_000, 4096)):
        assert lp.textures_for_pixels(faces * 16, rounding="up") == (1, side)


def test_plan_of_a_podio_like_source():
    # 449k triangles, one 2048 texture almost fully used: 0.7 x 2048² x 1.3
    px = 0.7 * 2048 ** 2 * 1.3
    plan = lp.plan_lod_set(449_000, px, 3)
    assert [(p["level"], p["triangles"], p["textures"], p["texture_px"], p["rule"])
            for p in plan] == [(0, 449_000, 1, 2048, "texel_density"),
                               (1, 112_250, 1, 1024, "texel_density"),
                               (2, 28_062, 1, 512, "texel_density")]


def test_plan_splits_a_dense_level_into_several_atlases():
    # a mesh with 44 x 8192² textures (Templu Mare scale) under an Unreal cap
    px = 44 * 8192 ** 2 * 0.6 * 1.3
    plan = lp.plan_lod_set(12_000_000, px, [1.0, 0.25, 0.0625, 0.015625],
                           max_texture_size=8192)
    assert [(p["textures"], p["texture_px"]) for p in plan] == [
        (16, 8192), (9, 8192), (2, 8192), (1, 8192)]
    # pixels shrink with the triangle ratio
    assert plan[1]["pixels"] == pytest.approx(plan[0]["pixels"] * 0.25, rel=1e-6)


def test_plan_without_textures_uses_the_face_count():
    plan = lp.plan_lod_set(100_000, None, 2)
    assert [(p["texture_px"], p["rule"]) for p in plan] == [(2048, "face_count"),
                                                            (1024, "face_count")]


def test_fixed_sizes_are_lodgenerator_one_texture_per_level():
    plan = lp.plan_lod_set(1000, 1e9, 3, texture_px=[2048, 512, 128])
    assert [(p["textures"], p["texture_px"], p["rule"]) for p in plan] == [
        (1, 2048, "fixed"), (1, 512, "fixed"), (1, 128, "fixed")]
    assert [p["texture_px"] for p in lp.plan_lod_set(10, None, 2, texture_px=1024)] == [1024, 1024]
    with pytest.raises(ValueError):
        lp.plan_lod_set(10, None, 3, texture_px=[1, 2])


def test_base_name_strips_the_lod_suffix():
    assert lp.base_name("OB_PODIO_LOD1") == "OB_PODIO"
    assert lp.base_name("Sarcofago_LOD3_baked.001") == "Sarcofago"
    assert lp.base_name("Rock") == "Rock"


def test_split_by_weight_gives_slabs_of_equal_surface():
    keys = list(range(10))
    assert lp.split_by_weight(keys, [1] * 10, 2) == [0] * 5 + [1] * 5
    assert lp.split_by_weight(keys, [1] * 10, 1) == [0] * 10
    # one heavy element at the end takes a slab of its own
    assert lp.split_by_weight(keys, [1] * 9 + [9], 2) == [0] * 9 + [1]
    groups = lp.split_by_weight([5, 1, 3], [0, 0, 0], 3)       # no weight: by count
    assert sorted(groups) == [0, 1, 2] and groups[1] == 0 and groups[0] == 2
