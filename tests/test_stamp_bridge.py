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
    # the gesture goes to EM Tools; with no resolve_kind (an old EM Tools) the
    # bridge writes the dev27 equivalent itself
    assert seen["objects"] == ["obj"] and seen["dtc_kind"] == "decimation"
    assert sb.report_line([res]) == "Stamps: 1 stamped"


def test_a_failing_emtools_never_stops_the_export(monkeypatch):
    fake = types.SimpleNamespace(
        stamp_blender_export=lambda path, **kw: (_ for _ in ()).throw(RuntimeError("boom")),
        software_entry=lambda name, folder: {"name": name})
    monkeypatch.setattr(sb, "emtools_birth_stamp", lambda: fake)
    res = sb.stamp("/nowhere.glb")
    assert res["state"] == "failed" and "boom" in res["line"]


def test_the_kinds_are_the_gestures_of_dev28():
    assert (sb.KIND_EXPORT, sb.KIND_LOD, sb.KIND_TILING, sb.KIND_PACKING) == (
        "export", "lod_generation", "tiling", "packing")


def test_em_tools_says_which_word_the_stamp_carries():
    new = types.SimpleNamespace(resolve_kind=lambda k: k)
    assert sb.kind_for(new, sb.KIND_PACKING) == "packing"
    old = types.SimpleNamespace()                    # an EM Tools before dev28
    assert [sb.kind_for(old, k) for k in (sb.KIND_EXPORT, sb.KIND_LOD, sb.KIND_TILING,
                                          sb.KIND_PACKING)] == [
        "format_conversion", "decimation", "transformation", "format_conversion"]
    assert sb.kind_for(None, "georeferencing") == "georeferencing"


def test_the_bridge_asks_em_tools_to_resolve(tmp_path, monkeypatch):
    seen = {}
    fake = types.SimpleNamespace(
        stamp_blender_export=lambda path, **kw: seen.update(kw) or {"state": "stamped"},
        software_entry=lambda name, folder: {"name": name},
        resolve_kind=lambda k: {"lod_generation": "lod_generation"}.get(k, "x"))
    monkeypatch.setattr(sb, "emtools_birth_stamp", lambda: fake)
    sb.stamp(str(tmp_path / "a.obj"), dtc_kind=sb.KIND_LOD)
    assert seen["dtc_kind"] == "lod_generation"


# --- EM Tools found by its manifest id, whatever folder it is installed under

def _fake_addon(tmp_path, monkeypatch, key, manifest_id, with_birth_stamp=True):
    """An enabled add-on ``key`` whose folder holds a blender_manifest.toml
    with ``id = manifest_id`` (and a birth_stamp.py), loaded in sys.modules
    as Blender loads an extension."""
    folder = tmp_path / key.rsplit(".", 1)[-1]
    folder.mkdir()
    (folder / "__init__.py").write_text("", encoding="utf-8")
    (folder / "blender_manifest.toml").write_text(
        'schema_version = "1.0.0"\n\n'
        f'id = "{manifest_id}"   # the add-on\n'
        'name = "Some add-on"\n\n[build]\nid = "not_this"\n', encoding="utf-8")
    if with_birth_stamp:
        (folder / "birth_stamp.py").write_text(
            "def stamp_blender_export(path, **kw):\n"
            "    return {'state': 'stamped', 'line': 'ok', 'stamp_path': path, 'stamp': {}}\n",
            encoding="utf-8")
    pkg = types.ModuleType(key)
    pkg.__file__ = str(folder / "__init__.py")
    pkg.__path__ = [str(folder)]
    monkeypatch.setitem(sys.modules, key, pkg)
    return folder


def _fake_bpy(monkeypatch, keys):
    addons = types.SimpleNamespace(keys=lambda: list(keys))
    bpy = types.SimpleNamespace(context=types.SimpleNamespace(
        preferences=types.SimpleNamespace(addons=addons)))
    monkeypatch.setitem(sys.modules, "bpy", bpy)


def _no_birth_stamp_loaded(monkeypatch):
    for name in [n for n in sys.modules if n.endswith(".birth_stamp")]:
        monkeypatch.delitem(sys.modules, name)


def test_manifest_id_reads_the_top_level_id_only(tmp_path):
    (tmp_path / "blender_manifest.toml").write_text(
        'schema_version = "1.0.0"\nidentity = "x"\nid = \'em_tools\'\n[build]\nid = "y"\n',
        encoding="utf-8")
    assert sb.manifest_id(str(tmp_path)) == "em_tools"
    (tmp_path / "blender_manifest.toml").write_text('name = "a"\n[x]\nid = "em_tools"\n',
                                                    encoding="utf-8")
    assert sb.manifest_id(str(tmp_path)) is None
    assert sb.manifest_id(str(tmp_path / "missing")) is None
    assert sb.manifest_id(None) is None


def test_the_development_link_is_em_tools_by_its_manifest(tmp_path, monkeypatch):
    key = "bl_ext.vscode_development.EM-blender-tools"
    _fake_addon(tmp_path, monkeypatch, key, "em_tools")
    other = "bl_ext.vscode_development.OpenShelf"
    _fake_addon(tmp_path, monkeypatch, other, "openshelf")
    keys = ["bl_ext.blender_org.something", other, key]
    assert sb.addon_key_for("em_tools", keys) == key
    _no_birth_stamp_loaded(monkeypatch)
    _fake_bpy(monkeypatch, keys)
    try:
        module = sb.emtools_birth_stamp()
        assert module is not None and module.__name__ == key + ".birth_stamp"
        assert sb.stamp(str(tmp_path / "a.glb"))["state"] == "stamped"
    finally:
        sys.modules.pop(key + ".birth_stamp", None)


def test_the_installed_names_still_match_without_reading_a_manifest():
    assert sb.addon_key_for("em_tools", ["x", "em_tools"]) == "em_tools"
    assert sb.addon_key_for("em_tools", ["bl_ext.user_default.em_tools"]) == \
        "bl_ext.user_default.em_tools"


def test_unrelated_addons_are_not_em_tools(tmp_path, monkeypatch):
    # an add-on with "em_tools" in its name but another id, one with no
    # manifest, one that is not loaded and cannot be found
    _fake_addon(tmp_path, monkeypatch, "bl_ext.dev.my_em_tools_fork", "my_fork")
    bare = tmp_path / "bare"
    bare.mkdir()
    mod = types.ModuleType("bare_addon")
    mod.__file__ = str(bare / "__init__.py")
    monkeypatch.setitem(sys.modules, "bare_addon", mod)
    keys = ["bl_ext.dev.my_em_tools_fork", "bare_addon", "not_loaded_anywhere_xyz"]
    assert sb.addon_key_for("em_tools", keys) is None
    _no_birth_stamp_loaded(monkeypatch)
    _fake_bpy(monkeypatch, keys)
    assert sb.emtools_birth_stamp() is None
    assert sb.stamp("/nowhere.glb")["state"] == "no_emtools"


def test_em_tools_without_birth_stamp_is_too_old(tmp_path, monkeypatch):
    key = "bl_ext.vscode_development.EM-blender-tools"
    _fake_addon(tmp_path, monkeypatch, key, "em_tools", with_birth_stamp=False)
    _no_birth_stamp_loaded(monkeypatch)
    _fake_bpy(monkeypatch, [key])
    assert sb.emtools_birth_stamp() is None
