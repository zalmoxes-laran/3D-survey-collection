"""pytest for the geophysics core embedded from its one source (row G6).

No Blender. What is defended: ``importer/_vendor/geofisica_core`` is the copy
of em-profiles' ``profiles/geofisica/code/geofisica_core`` at the commit of
``scripts/geofisica_core.lock.json`` (its digest is the lock's; when
em-profiles is beside this repository, the lock's digest is the core's at
that commit); no line of reading logic is left in 3DSC; ``import_gpr.py``
reads through the embedded core; the core runs here and stamps naming 3DSC
and the em-profiles commit; the panel's glue (``importer/gpr_scene.py``).
"""
import importlib.util
import json
import re
import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
VENDOR = ROOT / "importer" / "_vendor" / "geofisica_core"
EM_PROFILES = ROOT.parent / "em-profiles"


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


vendor = _load("vendor_geofisica_core", ROOT / "scripts" / "vendor_geofisica_core.py")
glue = _load("gpr_scene", ROOT / "importer" / "gpr_scene.py")


@pytest.fixture(scope="module")
def core():
    pytest.importorskip("numpy")
    pkg = types.ModuleType("dsc_vendor")
    pkg.__path__ = [str(VENDOR.parent)]
    sys.modules["dsc_vendor"] = pkg
    spec = importlib.util.spec_from_file_location(
        "dsc_vendor.geofisica_core", VENDOR / "__init__.py",
        submodule_search_locations=[str(VENDOR)])
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


# ── one source ───────────────────────────────────────────────────────────────

def test_the_embedded_copy_is_the_locks():
    lock = json.loads((ROOT / "scripts" / "geofisica_core.lock.json").read_text(encoding="utf-8"))
    assert lock["repo"] == "em-profiles" and lock["path"] == vendor.CORE_PATH
    assert re.fullmatch(r"[0-9a-f]{40}", lock["commit"])
    assert vendor.tree_digest(VENDOR) == lock["tree_digest"]
    source = json.loads((VENDOR / "SOURCE.json").read_text(encoding="utf-8"))
    assert {k: source[k] for k in lock} == lock
    assert vendor.check(None) == []


def test_the_lock_is_em_profiles_core_at_its_commit():
    if not (EM_PROFILES / ".git").exists():
        pytest.skip("em-profiles is not beside this repository")
    lock = json.loads((ROOT / "scripts" / "geofisica_core.lock.json").read_text(encoding="utf-8"))
    try:
        there = vendor.source_digest(EM_PROFILES, lock["commit"])
    except RuntimeError:
        pytest.skip("em-profiles beside has not the locked commit")
    assert there == lock["tree_digest"]
    assert vendor.check(EM_PROFILES) == []


def test_a_hand_edited_copy_is_refused(tmp_path, monkeypatch):
    import shutil
    copy = tmp_path / "geofisica_core"
    shutil.copytree(VENDOR, copy)
    monkeypatch.setattr(vendor, "VENDOR", copy)
    assert vendor.check(None) == []
    with open(copy / "depth.py", "a", encoding="utf-8") as fh:
        fh.write("\n# a line written in 3DSC\n")
    problems = vendor.check(None)
    assert len(problems) == 1 and "differs from the lock" in problems[0]
    (copy / "depth.py").unlink()
    assert "differs from the lock" in vendor.check(None)[0]


def test_no_reading_logic_left_in_3dsc():
    assert not (ROOT / "importer" / "gpr_core.py").exists()
    defs = re.compile(r"^\s*def (read_csv_slice|repair_chunk|build_cache_steps|build_image_manifest|"
                      r"depth_from_name|to_rgba8|write_png|scan_stack|detect_georeference|"
                      r"propose_shift|load_manifest)\b", re.M)
    found = []
    for p in ROOT.rglob("*.py"):
        parts = p.relative_to(ROOT).parts
        if parts[:2] == ("importer", "_vendor") or {".venv", "build", "__pycache__"} & set(parts):
            continue
        if defs.search(p.read_text(encoding="utf-8", errors="replace")):
            found.append(str(p.relative_to(ROOT)))
    assert found == []


def test_import_gpr_reads_through_the_embedded_core():
    text = (ROOT / "importer" / "import_gpr.py").read_text(encoding="utf-8")
    assert "from ._vendor import geofisica_core as core" in text
    assert "gpr_core" not in text


def test_the_build_checks_the_copy():
    text = (ROOT / "scripts" / "build.py").read_text(encoding="utf-8")
    assert "check_embedded_core(root_dir)" in text


# ── the core here ────────────────────────────────────────────────────────────

def test_the_core_has_the_names_import_gpr_uses(core):
    used = set(re.findall(r"\bcore\.([A-Za-z_]+)",
                          (ROOT / "importer" / "import_gpr.py").read_text(encoding="utf-8")))
    assert used and not [n for n in used if not hasattr(core, n)]


def test_stamps_name_3dsc_and_the_em_profiles_commit(core, tmp_path):
    np = pytest.importorskip("numpy")
    src = tmp_path / "Basilica"
    src.mkdir()
    a = np.zeros((4, 6), dtype=int)
    a[1:3, 1:5] = [[10, 20, 30, 40], [50, 60, 70, 80]]
    np.savetxt(src / "100-150cm.ASC", a, fmt="%d")
    np.savetxt(src / "VERT-1-OK.ASC", a.T, fmt="%d")
    lock = json.loads((ROOT / "scripts" / "geofisica_core.lock.json").read_text(encoding="utf-8"))
    software = [glue.software_line(str(ROOT))]
    m = core.build_stack_cache(
        str(src), kind="ascii_matrix", out_dir=str(tmp_path / "cache"), method="ert",
        value_scale=glue.value_scale(True, (1, 255), (0, 3500), "ohm.m", "figure"),
        declared=glue.declared("ascii_matrix", extent=(92, 50),
                               sections=glue.parse_sections("VERT1=50x8")),
        software=software, at="2026-11-19T12:00:00Z")
    ids = [e["document_id"] for e in m["slices"]]
    assert ids == ["ert:Basilica#d1.000-1.500m", "ert:Basilica#sVERT1"]
    st = json.loads((tmp_path / "cache" / m["slices"][0]["stamp"]).read_text(encoding="utf-8"))
    names = st["how"]["software"]
    assert names[0]["name"] == "3D Survey Collection" and names[0].get("version")
    assert names[-1] == {"name": "geofisica_core", "version": core.__version__,
                         "commit": lock["commit"][:7]}
    sec = m["slices"][1]
    lay = glue.slice_layout(sec, m["grid"], m["georef"])
    assert lay["orientation"] == "vertical" and not lay["shared"] and lay["z"] == 0.0
    assert abs(sec["grid"]["nx"] * sec["grid"]["x_step"] - 50.0) < 1e-6
    assert abs(sec["grid"]["ny"] * sec["grid"]["y_step"] - 8.0) < 1e-6


# ── the panel's glue ─────────────────────────────────────────────────────────

def test_parsing_what_the_person_types():
    assert glue.parse_pair("92 x 50") == (92.0, 50.0)
    assert glue.parse_pair("-50, 25") == (-50.0, 25.0)
    assert glue.parse_pair("") is None
    with pytest.raises(ValueError):
        glue.parse_pair("92")
    assert glue.parse_numbers("610, 170, 1303, 715", 4) == (610.0, 170.0, 1303.0, 715.0)
    assert glue.parse_sections("VERT1=50x8; vert2 = 92 x 9") == {"VERT1": (50.0, 8.0),
                                                                 "VERT2": (92.0, 9.0)}
    with pytest.raises(ValueError):
        glue.parse_sections("VERT1 50x8")


def test_declared_values_and_scale():
    spec_h = types.SimpleNamespace(orientation="horizontal", line=None)
    spec_v = types.SimpleNamespace(orientation="vertical", line="VERT2")
    spec_o = types.SimpleNamespace(orientation="vertical", line="VERT9")
    f = glue.declared("ascii_matrix", extent=(92, 50), sections={"vert2": (92, 9)},
                      section_default=(50, 8))
    assert f(spec_h) == {"extent": (92, 50)}
    assert f(spec_v) == {"length": 92, "depth": 9} and f(spec_o) == {"length": 50, "depth": 8}
    assert glue.declared("screenshot", frame={"px": [1, 2, 3, 4]})(spec_h) == {
        "frame": {"px": [1, 2, 3, 4]}}
    assert glue.declared("geotiff")(spec_h) == {}
    assert glue.value_scale(False, (1, 255), (0, 3500), "ohm.m") is None
    vs = glue.value_scale(True, (1, 255), (0, 3500), "ohm.m", "risultati-fori.pdf p. 5")
    assert vs == {"from": [1.0, 255.0], "to": [0.0, 3500.0], "unit": "ohm.m",
                  "confidence": "low", "source": "risultati-fori.pdf p. 5"}
    assert glue.typed_georef(0, 0) is None
    g = glue.typed_georef(701806.741, 4234824.081, "EPSG:25830")
    assert g["origin_e"] == 701806.741 and g["epsg"] == 25830 and g["source"] == "typed in 3DSC"


def test_where_the_cache_goes():
    assert glue.cache_dir('CSV', "/data/s", "") == "/data/s/_3dsc_gpr_cache"
    assert glue.cache_dir('IMAGES', "/data/s", "/c") == "/c"
    assert glue.cache_dir('GEOTIFF', "/data/s", "", "/pd/geofisica/cache/k") == \
        "/pd/geofisica/cache/k"
    assert glue.cache_dir('ASCII', "/data/s", "") == ""
    assert glue.CORE_KIND['POINTS'] is None
    assert {glue.PANEL_KIND[k] for k in ("xyzv", "xyz_lines")} == {'POINTS'}


def test_where_each_slice_sits():
    head = {"nx": 10, "ny": 5, "x_min": 0.05, "y_min": 0.05, "x_step": 0.1, "y_step": 0.1}
    other = dict(head, nx=12)
    e = {"index": 0, "depth_top": 1.0, "depth_bottom": 1.5, "grid": head}
    assert glue.slice_layout(e, head) == {"orientation": "horizontal", "grid": head, "z": -1.25,
                                          "depth_known": True, "shared": True,
                                          "offset": (0.0, 0.0)}
    assert not glue.slice_layout(dict(e, grid=other), head)["shared"]
    p = {"index": 1, "depth_top": None, "depth_bottom": None, "product": "mean_v2"}
    lay = glue.slice_layout(p, head)
    assert lay["z"] == 0.0 and not lay["depth_known"] and lay["shared"]
    geo = {"origin_e": 701756.963, "origin_n": 4234802.482}
    moved = dict(p, georef={"origin_e": 701757.963, "origin_n": 4234800.482})
    assert glue.slice_layout(moved, head, geo)["offset"] == pytest.approx((1.0, -2.0))
    assert glue.slice_object_name("GPR_S1", e) == "GPR_S1_d01.000"
    assert glue.slice_object_name("GPR_S1", p) == "GPR_S1_mean_v2"
    assert glue.slice_object_name("ERT_B", {"orientation": "vertical", "line": "VERT1"}) == \
        "ERT_B_sVERT1"
    assert glue.quad(head)[2] == pytest.approx((1.0, 0.5, 0.0))
    assert glue.quad(head, "vertical")[2] == pytest.approx((1.0, 0.0, 0.5))
    assert glue.document_kind("gpr", "horizontal") == "gpr_time_slice"
    assert glue.document_kind("ert", "vertical") == "ert_section"
    assert glue.stack_rotation(0.0, {"rotation": 12.5}) == 12.5
    assert glue.stack_rotation(3.0, {"rotation": 12.5}) == 3.0


def test_the_decoder_flips_blender_pixels():
    np = pytest.importorskip("numpy")
    px = np.zeros((2, 3, 4), dtype=np.float32)        # Blender: row 0 at the bottom
    px[0, :, 0] = 1.0                                  # bottom row red
    px[1, :, 2] = 1.0                                  # top row blue
    rgb = glue.rgb_from_pixels(px.ravel(), 3, 2)
    assert rgb.shape == (2, 3, 3) and rgb.dtype == np.uint8
    assert rgb[0, 0].tolist() == [0, 0, 255] and rgb[1, 0].tolist() == [255, 0, 0]


def test_software_line_names_3dsc():
    line = glue.software_line(str(ROOT))
    assert line["name"] == "3D Survey Collection"
    assert re.fullmatch(r"\d+\.\d+\.\d+.*", line["version"])
