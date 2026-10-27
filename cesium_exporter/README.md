# cesium_exporter — 3D Tiles from Blender meshes

Panel: *3DSC → Cesium 3D Tiles*. Output: a 3D Tiles 1.1 tileset (folder,
`.3tz`, or both). Three source modes.

## Which source mode

| you have | use | what happens |
|---|---|---|
| **LODs already** (`*_LOD0`, `*_LOD1`, … — LODgenerator, or a survey's `RB/LOD0..LOD2`) | **Multi-LOD set** | each LOD is clipped into octree cells keeping its own material/atlas: **no rebake**. Valid tileset (0 validator errors), and the fastest way: 22.7 s against 92.5 s for the native split of the same 450k-triangle model. Use this whenever the LODs exist. |
| one mesh in the scene | **Export active mesh** | native split: octree/quadtree, every tile re-baked (below). |
| one OBJ on disk, not in the scene | **Use existing OBJ file** | the OBJ (with its MTL and textures) is imported as one mesh, goes through the same native split as *Export active mesh*, and is removed from the scene afterwards (object, mesh, materials, images). |

## Native split: where the tile textures come from

* **Leaves** (finest tiles) — *Leaf texture source*:
  * **Original textures** (default): each leaf is cut from a pristine copy of
    the source mesh, keeps only the materials it uses, and is baked directly
    (no ray casting) from the original images through their own UV map onto a
    fresh per-tile atlas. Its side follows the original texel density of the
    leaf's faces (UV area × image pixels, ×1.3 for packing, nearest power of
    two), capped by *Leaf max texture* (4096). A leaf is as sharp as the
    photographs.
  * **Global atlas** (legacy): every tile is rebaked from the single global
    atlas of *Bake atlas size*. On a mesh with 44 × 4096² textures and a
    2048² atlas that is 176× fewer pixels than the source — no leaf can be
    sharper than that.
* **Coarse tiles** (root and every non-leaf level, LOD mode) are rebaked from
  the global atlas, which is enough for distant views and cheaper than
  loading every original image for each coarse bake. When nothing needs it
  (no LOD, no Single-JSON root content) and leaves come from the originals,
  the global atlas is not baked at all.

## Native split: a light root

*Coarse tile max triangles* (default 50 000) is a budget for every non-leaf
tile — the root, the LOD levels above the leaves, and the root content of a
*Single JSON* tileset (which used to be the whole mesh). The level's
decimation ratio is lowered when it leaves more; if the protected borders keep
the tile above the budget, a second pass without the protection brings it in.
*Coarse tile max texture* (default 2048) caps their atlas side. 0 disables
either. (On the 8.4M-triangle Templu Mare survey the root was 524k triangles,
29 MB: the LOD ratio of the root, 1/16, is a fraction, not a budget.) A Single JSON tileset can also have no root
content at all (*Add root content tile* off).

## tileset.json

Schema id `cesium_tiling_pipeline` (the 3D Tiles pattern
`[a-zA-Z_][a-zA-Z0-9_]*`; until 1.7.0-dev.16 it was `cesium-tiling-pipeline`).
The tight bounding box of the content is tileset-level `metadata` (class
`tileset`): a tile with `implicitTiling` may not carry `metadata`.

## Tests

`dev_utils/tests/test_cesium_native.py` and `test_cesium_3tz.py` (headless
Blender, see `dev_utils/tests/README.md`).
