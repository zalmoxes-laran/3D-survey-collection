"""pytest for master_mark.py — the sign «master not stamped» in 3DSC
(MICRO-TIMBRA-MASTER, 6 Nov 2026). No Blender, no dtcstamp, no s3dgraphy:
the rule is s3Dgraphy's (``resources.master_stamp``) and, when its sources
are on this machine, the answers are compared with it."""
import importlib.util
import json
import sys
import types
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("master_mark", _ROOT / "master_mark.py")
mm = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mm)
_sb_spec = importlib.util.spec_from_file_location("stamp_bridge", _ROOT / "stamp_bridge.py")
sb = importlib.util.module_from_spec(_sb_spec)
_sb_spec.loader.exec_module(sb)

S3D = _ROOT.parent / "s3Dgraphy" / "src" / "s3dgraphy" / "resources" / "master_stamp.py"

PATHS = ["/p/SB/Tempio/master/Tempio.obj", "/p/RB/_master/T/T.ply", "/p/RB/Templu_VHR.ply",
         "/p/RB/Templu_master.glb", "/p/RB/versions/Templu@lod1-web.glb",
         "/p/RB/LOD0/OB_PODIO_LOD0.obj", "/p/SB/master/notes.txt", "/p/x/scan_highres.e57"]


def _obj(folder, name, texture):
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{name}.obj").write_text(f"mtllib {name}.mtl\nv 0 0 0\n")
    (folder / f"{name}.mtl").write_text("newmtl m\n" + (f"map_Kd {name}.jpg\n" if texture else "Kd 1 1 1\n"))
    return folder / f"{name}.obj"


def test_which_files_are_masters():
    want = [True, True, True, True, False, False, False, True]
    assert [mm.looks_like_master(p) for p in PATHS] == want


def test_the_mark_and_its_gesture(tmp_path):
    vhr = tmp_path / "RB" / "master" / "Templu_VHR.ply"
    vhr.parent.mkdir(parents=True)
    vhr.write_bytes(b"ply\nformat ascii 1.0\nelement vertex 0\nproperty uchar red\nend_header\n")
    m = mm.mark(str(vhr))
    assert m == {"state": "unstamped", "kind": "very_high_resolution",
                 "label": "⚠ master not stamped · very high resolution", "gesture": "stamp_master"}
    tex = _obj(tmp_path / "SB" / "master", "Tempio", True)
    assert mm.mark(str(tex))["kind"] == "complete"
    Path(str(tex) + ".stamp.json").write_text(json.dumps({"stamp": 1, "self": {"resource_id": "r"}}))
    m = mm.mark(str(tex))
    assert m["state"] == "stamped" and m["gesture"] is None and m["label"] == "master stamped · complete"
    assert mm.mark(str(tmp_path / "a.txt")) is None


def test_the_same_answers_as_s3dgraphy(tmp_path):
    if not S3D.is_file():
        pytest.skip("s3Dgraphy's sources are not beside this repository")
    if "dtcstamp" not in sys.modules:
        sys.modules["dtcstamp"] = types.ModuleType("dtcstamp")     # the pure questions do not use it
    spec = importlib.util.spec_from_file_location("s3d_master_stamp", S3D)
    ms = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ms)
    assert [mm.looks_like_master(p) for p in PATHS] == [ms.looks_like_master(p) for p in PATHS]
    assert mm.KIND_LABELS == ms.KIND_LABELS
    for name, tex in (("a", True), ("b", False)):
        f = _obj(tmp_path, name, tex)
        assert mm.kind(str(f)) == ms.master_kind(None, textured=ms.is_textured(str(f)))


def test_stamp_master_goes_through_emtools(tmp_path, monkeypatch):
    f = tmp_path / "master" / "T.ply"
    f.parent.mkdir()
    f.write_bytes(b"ply")
    monkeypatch.setattr(sb, "emtools_birth_stamp", lambda: None)
    assert sb.stamp_master(str(f))["state"] == "no_emtools"
    calls = {}

    def stamp_export(path, **kw):
        calls.update(kw, path=path)
        return {"state": "stamped", "line": "stamped"}
    fake = types.SimpleNamespace(stamp_export=stamp_export, current_operator=lambda: None)
    monkeypatch.setattr(sb, "emtools_birth_stamp", lambda: fake)
    assert sb.stamp_master(str(f), kind="very_high_resolution")["state"] == "stamped"
    assert calls["tier"] == "master" and calls["master_kind"] == "very_high_resolution"
    assert calls["how"]["dtc_kind"] == "local_import"

    def old(path, how=None, operator=None, label=None):     # an EM Tools before the master's stamp
        return {"state": "stamped"}
    monkeypatch.setattr(sb, "emtools_birth_stamp", lambda: types.SimpleNamespace(stamp_export=old))
    assert sb.stamp_master(str(f))["state"] == "old_emtools"
