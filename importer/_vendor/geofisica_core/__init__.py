# -*- coding: utf-8 -*-
"""geofisica_core — the reading core of the geophysics package: THE one source (G-1).

Geophysical stacks (GPR, ERT, magnetometry: the method is a word in the
stack, not a different program) read into slices, rasterised into a cache of
PNGs, described by a manifest. Pure Python + numpy: **no bpy, no s3dgraphy
required**, so it runs in Blender (3D Survey Collection embeds this folder at
build time, row G6), in EMStudio's bridge and in a test.

It is the old 3D-survey-collection ``importer/gpr_core.py`` (886 lines, moved
here in row G2 of the geophysics plan, MICRO-GEO03) divided into modules:

* :mod:`.grid` — ``GridSpec``, ``SliceSpec``/``Slice`` (with ``orientation``,
  ``line``, ``product``), ``SliceData``, ``Stack`` (``method``, ``quantity``,
  ``unit``, ``value_scale``);
* :mod:`.depth` — depth from a name, the CSV header;
* :mod:`.identity` — ``gpr:<stack>#d<top>-<bottom>m`` unchanged, ``ert:``,
  ``mag:``, ``#s<line>``, ``#<product>``;
* :mod:`.readers` — ``csv_grid``, ``image_stack``, ``geotiff``, ``ascii_matrix``
  (row G3), ``xyzv``, ``xyz_lines``, ``screenshot`` (row G4), ``scan_stack``,
  ``guess_kind``, ``read_slice``, ``same_values``;
* :mod:`.georef` — world files, ``.prj``, shift;
* :mod:`.color`, :mod:`.png` — colour maps (the old ones and the package's
  ``.emc`` ramps), the declared ``value_scale``, the zlib PNG writer;
* :mod:`.manifest` — 3DSC's CSV cache and ``gpr_stack.json`` v2 (reads v1);
* :mod:`.cache` — the cache of ANY stack in ``plugins-data/geofisica/cache/``
  (row G5): PNGs + manifest, deterministic, every file stamped;
* :mod:`.stamp` — ``<file>.stamp.json`` on everything written (G-5).

The names below are a STABLE API: they are what 3DSC's ``import_gpr.py``
uses (``build_cache_steps``, ``build_image_manifest``, ``load_manifest``,
``detect_georeference``, ``is_absolute``, ``propose_shift``, ``scan_stack``,
``MANIFEST_NAME``) and what the old module exported.
"""

from __future__ import annotations

__version__ = "0.1.0"

from .cache import (CacheError, build_stack_cache, cache_key, cache_root, check_cache_dir,
                    plugins_data_dir)
from .color import (COLORMAPS, DEFAULT_RAMP, RAMPS, ColorError, _viridis_lut, apply_value_scale,
                    check_value_scale, load_emc, percentile_range, ramp_lut, ramp_mapping,
                    robust_range, to_rgba8)
from .depth import depth_from_name, parse_csv_header, read_csv_header
from .georef import (ABSOLUTE_COORD_THRESHOLD, detect_georeference, epsg_from_prj,
                     extent_from_world_file, is_absolute, prj_file_for, propose_shift,
                     read_world_file, world_file_for)
from .grid import (DEFAULT_QUANTITY, METHODS, ORIENTATIONS, GridSpec, Slice, SliceData,
                   SliceSpec, Stack)
from .identity import document_id, geo_id, stack_name
from .manifest import (MANIFEST_NAME, MANIFEST_VERSION, as_v1, build_cache, build_cache_steps,
                       build_image_manifest, build_screenshot_manifest, load_manifest, open_stack,
                       upgrade_manifest)
from .png import write_png
from .readers import (ASCII_EXT, CSV_EXT, GEOTIFF_EXT, IMG_EXT, KINDS, NODATA, SATURATION,
                      RepairedReader, geotiff_info, guess_kind, image_size, is_value_raster,
                      line_from_name, read_ascii_matrix, read_ascii_section, read_csv_slice,
                      read_geotiff_slice, read_slice, repair_chunk, same_values, scan_stack,
                      values_digest)
from .readers import (XYZ_EXT, XYZV_COLUMNS, compare_extent, crop_rgba, declare_frame,
                      frame_extent, frame_grid, is_points_file, measure_frame,
                      read_screenshot_slice, read_xyz_lines, read_xyzv, same_frame, xyzv_planes)
from .stamp import STAMP_SUFFIX, file_digest, resource_id_for, stamp_artifact, stamp_path

__all__ = [
    "CacheError", "ColorError", "DEFAULT_RAMP", "RAMPS", "apply_value_scale", "build_stack_cache",
    "cache_key", "cache_root", "check_cache_dir", "check_value_scale", "load_emc",
    "plugins_data_dir", "ramp_lut", "ramp_mapping", "robust_range",
    "XYZ_EXT", "XYZV_COLUMNS", "build_screenshot_manifest", "compare_extent", "crop_rgba",
    "declare_frame", "frame_extent", "frame_grid", "is_points_file", "measure_frame",
    "read_screenshot_slice", "read_xyz_lines", "read_xyzv", "same_frame", "xyzv_planes",
    "ASCII_EXT", "GEOTIFF_EXT", "KINDS", "SATURATION", "geotiff_info", "guess_kind",
    "is_value_raster", "line_from_name", "read_ascii_matrix", "read_ascii_section",
    "read_geotiff_slice", "read_slice", "same_values", "values_digest",
    "ABSOLUTE_COORD_THRESHOLD", "COLORMAPS", "CSV_EXT", "DEFAULT_QUANTITY", "GridSpec", "IMG_EXT",
    "MANIFEST_NAME", "MANIFEST_VERSION", "METHODS", "NODATA", "ORIENTATIONS", "RepairedReader",
    "STAMP_SUFFIX", "Slice", "SliceData", "SliceSpec", "Stack", "as_v1", "build_cache",
    "build_cache_steps", "build_image_manifest", "depth_from_name", "detect_georeference",
    "document_id", "epsg_from_prj", "extent_from_world_file", "file_digest", "geo_id",
    "image_size", "is_absolute", "load_manifest", "open_stack", "parse_csv_header",
    "percentile_range", "prj_file_for", "propose_shift", "read_csv_header", "read_csv_slice",
    "read_world_file", "repair_chunk", "resource_id_for", "scan_stack", "stack_name",
    "stamp_artifact", "stamp_path", "to_rgba8", "upgrade_manifest", "world_file_for",
    "write_png",
]
