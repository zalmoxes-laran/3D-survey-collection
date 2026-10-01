"""pytest for stamp_bridge.py — 3DSC stamps only through EM Tools.

No Blender: without EM Tools (here: no bpy, no add-on) the file is written
without a stamp and the report says so; with an EM Tools ``birth_stamp`` in
``sys.modules`` the call goes to it with 3DSC as the producer. The stamps
themselves are EM Tools' and dtcstamp's, tested there and in the headless
smoke (EM-blender-tools/tests/blender_smoke_birth_stamp.py).
"""
import importlib.util
import sys
import types
from pathlib import Path

_MOD = Path(__file__).resolve().parents[1] / "stamp_bridge.py"
_spec = importlib.util.spec_from_file_location("stamp_bridge", _MOD)
sb = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sb)


def test_no_copy_of_dtcstamp_in_3dsc():
    root = Path(__file__).resolve().parents[1]
    copies = [p for p in root.rglob("dtcstamp*.py") if ".venv" not in p.parts]
    assert copies == []
    assert "import dtcstamp" not in _MOD.read_text(encoding="utf-8")


def test_without_emtools_the_file_is_not_stamped_and_it_is_said(tmp_path, monkeypatch):
    monkeypatch.setattr(sb, "emtools_birth_stamp", lambda: None)
    f = tmp_path / "a.glb"
    f.write_bytes(b"glTF")
    res = sb.stamp(str(f), objects=[None])
    assert res["state"] == "no_emtools"
    assert not (tmp_path / "a.glb.stamp.json").exists()
    line = sb.report_line([res, res])
    assert line.startswith("2 file(s) not stamped: EM Tools is not installed")

    class Op:
        said = None

        def report(self, level, text):
            Op.said = (level, text)
    sb.report(Op(), [res])
    assert Op.said[0] == {'INFO'} and "EM Tools is not installed" in Op.said[1]


def test_with_emtools_the_call_goes_there_with_3dsc_as_producer(tmp_path, monkeypatch):
    seen = {}
    fake = types.ModuleType("bl_ext.user_default.em_tools.birth_stamp")

    def stamp_blender_export(path, **kw):
        seen.update(kw, path=path)
        return {"state": "stamped", "line": "ok", "stamp_path": path + ".stamp.json",
                "stamp": {}}
    fake.stamp_blender_export = stamp_blender_export
    fake.software_entry = lambda name, folder: {"name": name, "version": "1.7.0-dev.15"}
    fake.report_line = lambda rows: f"Stamps: {len(rows)} stamped"
    monkeypatch.setitem(sys.modules, fake.__name__, fake)
    assert sb.emtools_birth_stamp() is fake
    res = sb.stamp(str(tmp_path / "x.glb"), objects=[None, "obj"], dtc_kind=sb.KIND_LOD,
                   technique="LOD", parameters={"operator": "lod.creation"})
    assert res["state"] == "stamped"
    assert seen["producer"] == {"name": "3D Survey Collection", "version": "1.7.0-dev.15"}
    assert seen["objects"] == ["obj"] and seen["dtc_kind"] == "decimation"
    assert sb.report_line([res]) == "Stamps: 1 stamped"


def test_a_failing_emtools_never_stops_the_export(monkeypatch):
    fake = types.SimpleNamespace(
        stamp_blender_export=lambda path, **kw: (_ for _ in ()).throw(RuntimeError("boom")),
        software_entry=lambda name, folder: {"name": name})
    monkeypatch.setattr(sb, "emtools_birth_stamp", lambda: fake)
    res = sb.stamp("/nowhere.glb")
    assert res["state"] == "failed" and "boom" in res["line"]


def test_kinds_are_of_the_dev26_vocabulary():
    assert {sb.KIND_EXPORT, sb.KIND_LOD, sb.KIND_TILING} == {
        "format_conversion", "decimation", "transformation"}
