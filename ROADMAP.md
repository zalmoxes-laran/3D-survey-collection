# 3D Survey Collection - Roadmap

## About

3D Survey Collection (3DSC) is an open-source Blender add-on (GPL-3.0) for managing and optimizing archaeological and architectural 3D survey data. It transforms photogrammetric surveys into real-time assets for game engines (Unreal, Unity, Godot).

Developed by Emanuel Demetrescu at CNR-ISPC (Italian National Council for Research, Institute of Heritage Science).

## Current version

**1.7.0 dev01** (development branch: `3DSC-dev-1.7.0`) -- requires Blender 4.2+

## Recently completed (v1.7.0 dev cycle)

- **Cesium exporter rewrite** -- new `cesium_exporter` package replacing the previous VTK-based backend; added Cesium VTK export option with pip helper utilities
- **LOD system improvements** -- LOD 4 support, LOD clustering, alpha source handling with enforced PNG for alpha, presets/menu/operators, progress tracking with UI feedback, shortkeys for LOD management
- **FBX export enhancements** -- metre-to-centimetre export toggle with dedicated UI
- **Native export improvements** -- TILE side-length parameter, export directory management, coordinate shift fixes
- **UI overhaul** -- revamped panel ordering, help popups, import UI enhancements, collapsible panels at startup
- **Image format conversion** utility
- **Internal baking** fixes and selection fixing mechanism
- **Legacy Base preset migration** to new format

## Recently completed (v1.6.x cycle)

- **DXF importer** -- georeferenced DXF file import with hatch support
- **SVG template management** and PDF export options
- **Orthogonal render** improvements
- **METS XML exporter** (`mets_exporter` module)
- **Alignment/orientation tool**
- **Blender-to-Unreal camera converter**
- **Color correction and statistics** improvements
- **Mesh patcher** and non-manifold filler fixes
- **Texture/cutter system** improvements
- **Reality Capture CLI integration** (Windows, alpha)
- **BlenderGIS integration**

## Active development areas

The following areas show ongoing activity based on recent commits and branch state:

- **Cesium/3D Tiles pipeline** -- export workflow stabilization and cleanup (removal of deprecated `vtk_cesium` modules)
- **LOD generation** -- continued refinement of the multi-level LOD pipeline and preset system
- **Photogrammetry toolset** -- improvements to survey-oriented tools
- **Export pipeline** -- native, FBX, and Cesium exporters under active iteration

## Project links

- Repository: https://github.com/zalmoxes-laran/3D-survey-collection
- Documentation: https://docs.extendedmatrix.org/projects/3DSC/en/latest/index.html
- Telegram user group: https://t.me/UserGroup3DSC
