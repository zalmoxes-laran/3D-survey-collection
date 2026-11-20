"""pytest for cesium_exporter/archive_3tz.py — no Blender needed.

The module is loaded from its file, not through the package: the
package ``__init__`` imports ``bpy``.
"""
import importlib.util
import json
import os
import struct
import zipfile
from pathlib import Path

import pytest

# the writer is dtcstamp's (MICRO-COR08): from the venv, or the checkout beside
# this one when the venv has not been set up again since
try:
    import dtcstamp  # noqa: F401
except ImportError:
    import sys
    _SIBLING = Path(__file__).resolve().parents[2] / "dtcstamp"
    if not (_SIBLING / "dtcstamp.py").is_file():
        pytest.skip("dtcstamp is neither installed nor checked out beside 3DSC",
                    allow_module_level=True)
    sys.path.insert(0, str(_SIBLING))
    import dtcstamp  # noqa: F401

_MOD = Path(__file__).resolve().parents[1] / "cesium_exporter" / "archive_3tz.py"
_spec = importlib.util.spec_from_file_location("archive_3tz", _MOD)
tz = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(tz)


def _fake_tileset(root: Path, n_tiles: int = 12) -> Path:
    """A small tileset: root tileset.json, tiles in nested folders, an
    external subtileset, a .DS_Store that must be skipped."""
    root.mkdir(parents=True, exist_ok=True)
    children = []
    for i in range(n_tiles):
        rel = f"tiles/{i % 3}/{i}.glb"
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"glTF" + bytes([i]) * (1000 + 37 * i))
        children.append({"geometricError": 0, "content": {"uri": rel}})
    sub = root / "sub" / "tileset.json"
    sub.parent.mkdir(parents=True, exist_ok=True)
    sub.write_text(json.dumps({"asset": {"version": "1.1"}, "geometricError": 1,
                               "root": {"geometricError": 0, "boundingVolume": {"sphere": [0, 0, 0, 1]}}}))
    children.append({"geometricError": 1, "content": {"uri": "sub/tileset.json"}})
    (root / "tileset.json").write_text(json.dumps({
        "asset": {"version": "1.1"}, "geometricError": 10,
        "root": {"geometricError": 10, "refine": "ADD",
                 "boundingVolume": {"sphere": [0, 0, 0, 10]}, "children": children},
    }))
    (root / ".DS_Store").write_bytes(b"finder junk")
    (root / "tiles" / "Thumbs.db").write_bytes(b"windows junk")
    return root


def _touch_all(root: Path, mtime: float):
    for p in root.rglob("*"):
        if p.is_file():
            os.utime(p, (mtime, mtime))


def test_two_writes_same_sha_even_after_touching_dates(tmp_path):
    src = _fake_tileset(tmp_path / "ts")
    a = tz.write_3tz(src, tmp_path / "a.3tz")
    _touch_all(src, 1_900_000_000)            # 2030: dates must not leak in
    b = tz.write_3tz(src, tmp_path / "b.3tz")
    assert a["sha256"] == b["sha256"]
    assert a["bytes"] == b["bytes"]
    assert a["entries"] == b["entries"] == 12 + 2      # tiles + 2 tileset.json
    assert (tmp_path / "a.3tz").read_bytes() == (tmp_path / "b.3tz").read_bytes()


def test_changed_file_changes_sha(tmp_path):
    src = _fake_tileset(tmp_path / "ts")
    a = tz.write_3tz(src, tmp_path / "a.3tz")
    (src / "tiles" / "1" / "4.glb").write_bytes(b"glTF-changed")
    b = tz.write_3tz(src, tmp_path / "b.3tz")
    assert a["sha256"] != b["sha256"]


def test_archive_layout_follows_spec(tmp_path):
    src = _fake_tileset(tmp_path / "ts")
    out = tmp_path / "x.3tz"
    tz.write_3tz(src, out)
    with zipfile.ZipFile(out) as zf:
        infos = zf.infolist()
    names = [zi.filename for zi in infos]
    assert names[-1] == tz.INDEX_NAME
    assert names[:-1] == sorted(names[:-1])                  # path order
    assert ".DS_Store" not in names and "tiles/Thumbs.db" not in names
    for zi in infos:
        assert zi.compress_type == zipfile.ZIP_STORED
        assert zi.date_time == tz.FIXED_DATE
        assert zi.create_system == 3
    idx = tz.read_index(out)
    assert len(idx) == len(names) - 1
    keys = [struct.unpack("<QQ", k) for k in idx]            # dict keeps order
    assert keys == sorted(keys)
    assert tz.read_entry(out, "tileset.json", idx) == (src / "tileset.json").read_bytes()
    assert tz.read_entry(out, "tiles/2/5.glb", idx) == (src / "tiles/2/5.glb").read_bytes()
    v = tz.verify_3tz(out, src)
    assert v["ok"], v["errors"]


def test_one_writer_dtcstamp_s(tmp_path, monkeypatch):
    """MICRO-COR08: write_3tz is dtcstamp.write_canonical_3tz — the same bytes,
    and the call goes there (no second writer, no compress option)."""
    src = _fake_tileset(tmp_path / "ts")
    ours = tz.write_3tz(src, tmp_path / "a.3tz")
    theirs = dtcstamp.write_canonical_3tz(str(src), str(tmp_path / "b.3tz"))
    assert theirs["sha256"] == "sha256:" + ours["sha256"]
    assert theirs["content_digest"] == ours["content_digest"]
    called = []
    monkeypatch.setattr(dtcstamp, "write_canonical_3tz",
                        lambda s, o, progress=None: called.append((s, o)) or
                        {"sha256": "sha256:ab", "path": o})
    assert tz.write_3tz(src, tmp_path / "c.3tz")["sha256"] == "ab"
    assert called == [(str(src), str(tmp_path / "c.3tz"))]
    with pytest.raises(TypeError):
        tz.write_3tz(src, tmp_path / "d.3tz", compress=True)


def test_verify_finds_altered_tile(tmp_path):
    src = _fake_tileset(tmp_path / "ts")
    out = tmp_path / "x.3tz"
    tz.write_3tz(src, out)
    # alter the source: the archive no longer matches the folder
    (src / "tiles" / "0" / "3.glb").write_bytes(b"glTF-other")
    v = tz.verify_3tz(out, src)
    assert not v["ok"]
    assert any("tiles/0/3.glb" in e for e in v["errors"])


def test_verify_finds_tile_altered_inside_archive(tmp_path):
    src = _fake_tileset(tmp_path / "ts")
    out = tmp_path / "x.3tz"
    tz.write_3tz(src, out)
    target = (src / "tiles" / "2" / "8.glb").read_bytes()
    raw = bytearray(out.read_bytes())
    pos = raw.find(target)
    assert pos > 0
    raw[pos + 10] ^= 0xFF                                    # flip one byte in place
    out.write_bytes(bytes(raw))
    v = tz.verify_3tz(out, src)
    assert not v["ok"]
    assert any("tiles/2/8.glb" in e for e in v["errors"])


def test_verify_finds_broken_index(tmp_path):
    src = _fake_tileset(tmp_path / "ts")
    out = tmp_path / "x.3tz"
    tz.write_3tz(src, out)
    idx = tz.read_index(out)
    # rewrite the archive with an index pointing every record to offset 0
    bad = tmp_path / "bad.3tz"
    with zipfile.ZipFile(out) as zin, zipfile.ZipFile(bad, "w") as zout:
        for zi in zin.infolist()[:-1]:
            zout.writestr(zi, zin.read(zi))
        recs = sorted(idx, key=lambda k: struct.unpack("<QQ", k))
        zout.writestr(tz.INDEX_NAME, b"".join(k + struct.pack("<Q", 0) for k in recs))
    v = tz.verify_3tz(bad)
    assert not v["ok"]
    assert any("points to" in e for e in v["errors"])


def test_missing_root_tileset_stops(tmp_path):
    src = _fake_tileset(tmp_path / "ts")
    (src / "tileset.json").unlink()
    with pytest.raises(ValueError, match="tileset.json"):
        tz.write_3tz(src, tmp_path / "x.3tz")
    assert not (tmp_path / "x.3tz").exists()


def test_3tz_path_is_refused(tmp_path):
    src = _fake_tileset(tmp_path / "ts")
    (src / "nested.3tz").write_bytes(b"PK")
    with pytest.raises(ValueError, match=r"\.3tz"):
        tz.write_3tz(src, tmp_path / "x.3tz")


def test_archive_inside_source_is_refused(tmp_path):
    src = _fake_tileset(tmp_path / "ts")
    with pytest.raises(ValueError, match="inside"):
        tz.write_3tz(src, src / "self.zip")


# ── the one profile: NFC names, 0x800, content_digest (dtcstamp/profiles/3tz.md)

_TILESET_20 = (b'{"asset": {"version": "1.0"}, "geometricError": 10, "root": '
               b'{"content": {"uri": "Data/c01/e0001.b3dm"}, "geometricError": 1, '
               b'"refine": "REPLACE", "boundingVolume": {"sphere": [0, 0, 0, 10]}}}')


def _write_tree(root: Path, files: dict) -> Path:
    for rel, data in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
    return root


def test_dtcstamp_conformance_case_20(tmp_path):
    """dtcstamp conformance/20-tileset-folder-and-3tz.json, byte for byte."""
    src = _write_tree(tmp_path / "small", {
        "tileset.json": _TILESET_20,
        "Data/c01/e0001.b3dm": b"b3dm" + b"\x01" * 100,
        "Data/c02/e0002.b3dm": b"b3dm" + b"\x02" * 200,
    })
    out = tmp_path / "small.3tz"
    r = tz.write_3tz(src, out)
    assert r["sha256"] == "75b111b73bbd230e5083091304a53e19d1ad4495763b16f318c803bdec86f0bf"
    want = "sha256:fefca8bcbc5a4f20573a8134d9c7c631dddb84c6dd40d664c7a25f9bc33373a8"
    assert r["content_digest"] == {"digest": want, "files": 3, "computed_by": "producer"}
    assert tz.content_digest(src) == {"digest": want, "files": 3}
    assert tz.content_digest(out) == {"digest": want, "files": 3}


_TILESET_23 = ('{"asset": {"version": "1.0"}, "geometricError": 10, "root": '
               '{"content": {"uri": "Data/città.b3dm"}, "geometricError": 1, '
               '"refine": "REPLACE", "boundingVolume": {"sphere": [0, 0, 0, 10]}}}'
               ).encode("utf-8")


def _tree_23(root: Path, form: str) -> Path:
    import unicodedata
    return _write_tree(root, {
        "tileset.json": _TILESET_23,
        unicodedata.normalize(form, "Data/città.b3dm"): b"b3dm" + b"\x03" * 100,
        "Data/c02/e0002.b3dm": b"b3dm" + b"\x02" * 200,
    })


_CASE_23_SHA256 = "29b06145656c39cd3dcbf82b35245cd73614248fde71dc89b57aa55fa0d69d19"
_CASE_23_CONTENT = "sha256:c03e9083db54a0f680a6ec9f485b9de40e52391b78cf03d23716b69a88d89422"


def test_dtcstamp_conformance_case_23_non_ascii_name(tmp_path):
    """dtcstamp conformance/23-tileset-non-ascii-name.json: written by this
    module, then checked there and in s3Dgraphy."""
    src = _tree_23(tmp_path / "small", "NFC")
    out = tmp_path / "small.3tz"
    r = tz.write_3tz(src, out)
    assert r["sha256"] == _CASE_23_SHA256
    assert r["content_digest"]["digest"] == _CASE_23_CONTENT
    assert tz.content_digest(out)["digest"] == _CASE_23_CONTENT


def test_nfd_on_disk_gives_the_nfc_archive(tmp_path):
    """macOS hands names over in NFD: the archive must not care."""
    import unicodedata
    nfc = tz.write_3tz(_tree_23(tmp_path / "nfc", "NFC"), tmp_path / "nfc.3tz")
    nfd_src = _tree_23(tmp_path / "nfd", "NFD")
    nfd = tz.write_3tz(nfd_src, tmp_path / "nfd.3tz")
    assert nfd["sha256"] == nfc["sha256"]
    assert nfd["content_digest"] == nfc["content_digest"]
    assert tz.content_digest(nfd_src)["digest"] == nfc["content_digest"]["digest"]
    with zipfile.ZipFile(tmp_path / "nfd.3tz") as zf:
        for zi in zf.infolist():
            assert zi.filename == unicodedata.normalize("NFC", zi.filename)
    assert tz.read_entry(tmp_path / "nfd.3tz", "Data/città.b3dm") \
        == b"b3dm" + b"\x03" * 100
    assert tz.verify_3tz(tmp_path / "nfd.3tz", nfd_src)["ok"]


def test_utf8_flag_exactly_on_non_ascii_names(tmp_path):
    src = _tree_23(tmp_path / "small", "NFC")
    _write_tree(src, {"tiles/plain.glb": b"glTF"})
    out = tmp_path / "x.3tz"
    tz.write_3tz(src, out)
    with zipfile.ZipFile(out) as zf:
        flags = {zi.filename: zi.flag_bits for zi in zf.infolist()}
    assert flags["Data/città.b3dm"] == tz.UTF8_FLAG
    for name, bits in flags.items():
        if name.isascii():
            assert bits == 0, (name, hex(bits))


def test_two_names_equal_in_nfc_stop_the_write(tmp_path, monkeypatch):
    # APFS will not hold both on one disk: the listing is what Linux gives.
    src = tmp_path / "ts"
    src.mkdir()
    nfc, nfd = "città.b3dm", "città.b3dm"
    monkeypatch.setattr(tz.os, "walk",
                        lambda _d: iter([(str(src), [], ["tileset.json", nfc, nfd])]))
    with pytest.raises(ValueError) as caught:
        tz.write_3tz(src, tmp_path / "x.3tz")
    assert nfc in str(caught.value) and nfd in str(caught.value)
    assert not (tmp_path / "x.3tz").exists()


_TEMPLU_MARE = (Path.home() / "Library/CloudStorage/OneDrive-CNR/Extended Matrix/"
                "EM_CaseStudies/01_EM_Tempio Grande/_base_EMStudio/RM/TempluMare_cesium")


@pytest.mark.skipif(not _TEMPLU_MARE.is_dir(), reason="TempluMare base not on this machine")
def test_templu_mare_keeps_its_sha256(tmp_path):
    r = tz.write_3tz(_TEMPLU_MARE, tmp_path / "TempluMare_cesium.3tz")
    assert r["sha256"] == "232dfcbc148f30e52098fef9c83606a3e1638a106fc0678563e909cde1db0c17"
    assert r["content_digest"]["digest"] == \
        "sha256:8aa6fbd3e5847e9f8c2e219fb4305d9a3ad52e41135120e79bb8c3d18b67caed"
    assert r["content_digest"]["files"] == 7302


# ── the RealityScan form: X.json beside the folder X ─────────────────────────

def _realityscan_pair(parent: Path, name: str = "tileset_Basilica") -> Path:
    """RealityScan writes the root X.json BESIDE the folder X/, whose tiles the
    root references as ``X/...``."""
    folder = parent / name
    for i in range(5):
        p = folder / "Geometry" / f"{i}.b3dm"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"b3dm" + bytes([i]) * 500)
    (folder / ".DS_Store").write_bytes(b"x")
    (parent / f"{name}.json").write_text(json.dumps({
        "asset": {"version": "1.0", "generator": "RealityScan"}, "geometricError": 10,
        "root": {"geometricError": 0, "boundingVolume": {"sphere": [0, 0, 0, 1]},
                 "children": [{"geometricError": 0, "content": {"uri": f"{name}/Geometry/{i}.b3dm"}}
                              for i in range(5)]}}))
    return folder


def test_find_source_understands_the_four_shapes(tmp_path):
    plain = _fake_tileset(tmp_path / "plain")
    assert tz.find_tileset_source(plain) == (str(plain), None, str(plain) + ".3tz")
    pair_dir = tmp_path / "rs"
    folder = _realityscan_pair(pair_dir)
    want = (str(folder), str(folder) + ".json", str(folder) + ".3tz")
    assert tz.find_tileset_source(folder) == want                    # the folder X
    assert tz.find_tileset_source(str(folder) + ".json") == want     # the X.json
    assert tz.find_tileset_source(pair_dir) == want                  # the folder holding the pair


def test_find_source_refuses_what_is_not_a_tileset(tmp_path):
    (tmp_path / "empty").mkdir()
    with pytest.raises(ValueError, match="RealityScan form"):
        tz.find_tileset_source(tmp_path / "empty")
    two = tmp_path / "two"
    _realityscan_pair(two, "a")
    _realityscan_pair(two, "b")
    with pytest.raises(ValueError, match="choose one"):
        tz.find_tileset_source(two)


def test_realityscan_pair_packs_with_root_tileset_json(tmp_path):
    folder = _realityscan_pair(tmp_path)
    fol, root, out = tz.find_tileset_source(folder)
    stage = tz.stage_tileset_pair(root, fol)
    try:
        info = tz.write_3tz(stage, out)
        v = tz.verify_3tz(out, stage)
    finally:
        import shutil
        shutil.rmtree(stage)
    assert v["ok"], v["errors"]
    assert info["entries"] == 6                     # tileset.json + 5 tiles, no .DS_Store
    with zipfile.ZipFile(out) as zf:
        names = zf.namelist()
    assert "tileset.json" in names and "tileset_Basilica/Geometry/0.b3dm" in names
    assert json.loads(tz.read_entry(out, "tileset.json"))["asset"]["generator"] == "RealityScan"
    # the originals are untouched and nothing is left beside them
    assert sorted(p.name for p in tmp_path.iterdir()) == [
        "tileset_Basilica", "tileset_Basilica.3tz", "tileset_Basilica.json"]
    assert (folder / ".DS_Store").exists()
