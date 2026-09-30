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


def test_compress_option_still_valid(tmp_path):
    src = _fake_tileset(tmp_path / "ts")
    out = tmp_path / "c.3tz"
    tz.write_3tz(src, out, compress=True)
    with zipfile.ZipFile(out) as zf:
        infos = zf.infolist()
    assert infos[-1].compress_type == zipfile.ZIP_STORED     # index never compressed
    assert infos[0].compress_type == zipfile.ZIP_DEFLATED
    assert tz.read_entry(out, "tiles/0/0.glb") == (src / "tiles/0/0.glb").read_bytes()
    assert tz.verify_3tz(out, src)["ok"]


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
