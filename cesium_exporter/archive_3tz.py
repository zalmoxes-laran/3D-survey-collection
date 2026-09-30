"""3D Tiles Archive (.3tz) — deterministic writer, reader and verifier.

Pure Python, no ``bpy``: importable by the tests and by other tools.

Spec: 3D Tiles Archive Format v1.3 (github.com/erikdahlstrom/3tz-specification),
media type ``application/vnd.maxar.archive.3tz+zip``.

- a plain zip with ``tileset.json`` at the root;
- the LAST entry is ``@3dtilesIndex1@``, stored uncompressed: N records of
  24 bytes, MD5 (16 bytes) of the normalized path + little-endian uint64
  offset of the entry's Local File Header, sorted ascending by the MD5 read
  as two uint64 LE (bytes 0-7, then 8-15);
- entries preferably STORED; zip64; at most 4 GB per entry; relative
  references; no ``.3tz`` paths inside a 3tz.

Determinism is part of the contract — same folder in, same bytes out:
entries in path order, fixed date 1980-01-01, fixed attributes and
``create_system``, no compression by default, ``.DS_Store``/``Thumbs.db``
skipped, names in Unicode NFC. The sha256 of the archive therefore
identifies its content and can be stamped and cited like the digest of a glb.

This is THE canonical profile, written down in ``dtcstamp/profiles/3tz.md``:
general-purpose flag 0 on an ASCII name, ``0x800`` (the name is UTF-8) on a
non-ASCII one — which is what ``zipfile`` writes, deterministically — and
every name NFC. macOS hands names over in NFD: without normalising, the same
folder would give one sha256 on a Mac and another on Linux or Windows.

Alongside the file digest, :func:`content_digest` names what is INSIDE, in
dtcstamp's form (one line ``role NUL path NUL sha256:<hex> LF`` per file,
lines in the order of the UTF-8 bytes of the NFC path, ``tileset.json`` the
``entry_point``): a folder and its archive give the same one, whatever the
packing. :func:`write_3tz` computes it from the bytes it copies, with no
second pass.

Files are copied in blocks, never read whole into memory.
"""
from __future__ import annotations

import hashlib
import os
import struct
import time
import unicodedata
import zipfile

MEDIA_TYPE = "application/vnd.maxar.archive.3tz+zip"
INDEX_NAME = "@3dtilesIndex1@"
FIXED_DATE = (1980, 1, 1, 0, 0, 0)
SKIP_NAMES = frozenset((".DS_Store", "Thumbs.db"))
MAX_ENTRY_BYTES = 4 * 1024 ** 3          # spec: 4 GB per file
ZIP64_LIMIT = 0xFFFFFFFF
_BLOCK = 1 << 20
_RECORD = 24
ENTRY_POINT = "tileset.json"
UTF8_FLAG = 0x800                        # zip general-purpose bit 11


def normalize(path: str) -> str:
    """Archive path of an entry: Unicode NFC, forward slashes, no leading
    slash."""
    return unicodedata.normalize("NFC", path).replace("\\", "/").lstrip("/")


def _md5(name: str) -> bytes:
    return hashlib.md5(normalize(name).encode("utf-8")).digest()


def _sort_key(md5: bytes):
    return struct.unpack("<QQ", md5)


def _zinfo(name: str, size: int, compress: bool) -> zipfile.ZipInfo:
    zi = zipfile.ZipInfo(name, date_time=FIXED_DATE)
    zi.compress_type = zipfile.ZIP_DEFLATED if compress else zipfile.ZIP_STORED
    zi.create_system = 3                          # unix, whatever the host
    zi.external_attr = (0o100644 & 0xFFFF) << 16
    zi.file_size = size
    return zi


def _path_key(name: str) -> bytes:
    return name.encode("utf-8")


def _entries(src_dir: str) -> list:
    """``[(archive path, path on disk relative to src_dir)]`` sorted by the
    UTF-8 bytes of the archive path. The two differ when the disk holds a
    name in NFD (macOS) or with backslashes."""
    by_name = {}
    for root, dirs, files in os.walk(src_dir):
        dirs.sort()
        for f in files:
            if f in SKIP_NAMES:
                continue
            disk = os.path.relpath(os.path.join(root, f), src_dir)
            rel = normalize(disk)
            if ".3tz" in rel.lower():
                raise ValueError(f"a 3tz must not contain '.3tz' paths: {rel}")
            if rel in by_name:
                raise ValueError(
                    f"two files have the same name in NFC, {rel!r}: "
                    f"{by_name[rel]!r} and {disk!r}")
            by_name[rel] = disk
    if ENTRY_POINT not in by_name:
        raise ValueError(f"tileset.json must be at the root of {src_dir}")
    return sorted(by_name.items(), key=lambda kv: _path_key(kv[0]))


def list_entries(src_dir: str) -> list:
    """Sorted archive paths (NFC) of the files under ``src_dir`` (the skip
    list applied). Raises ``ValueError`` on a ``.3tz`` path, on two files
    whose names are the same in NFC, or on a missing root ``tileset.json``."""
    return [name for name, _disk in _entries(src_dir)]


def members_canonical(rows) -> bytes:
    """dtcstamp's canonical list of members of a tree, byte for byte:
    ``role NUL path NUL sha256:<hex> LF`` per ``(path, sha256 hex)`` in
    ``rows``, in the order of the UTF-8 bytes of the NFC path; ``tileset.json``
    is the ``entry_point``, every other file a ``member``."""
    lines = []
    for path, hexdigest in sorted(((normalize(p), h.lower()) for p, h in rows),
                                  key=lambda r: _path_key(r[0])):
        role = "entry_point" if path == ENTRY_POINT else "member"
        lines.append(f"{role}\0{path}\0sha256:{hexdigest}\n")
    return "".join(lines).encode("utf-8")


def _content_digest_of(rows) -> str:
    return "sha256:" + hashlib.sha256(members_canonical(rows)).hexdigest()


def content_digest(path: str) -> dict:
    """The digest of the CONTENT of a tileset — a folder or a ``.3tz`` — in
    dtcstamp's form (``profiles/3tz.md``): ``{"digest": "sha256:<hex>",
    "files": n}``. ``.DS_Store``, ``Thumbs.db`` and the index are not
    members. A folder and its archive give the same value, whatever the
    archive's dates, attributes or compression."""
    rows = []
    if os.path.isdir(path):
        for name, disk in _entries(path):
            rows.append((name, sha256_file(os.path.join(path, disk))))
    else:
        with zipfile.ZipFile(path) as zf:
            for zi in zf.infolist():
                name = normalize(zi.filename)
                if name == INDEX_NAME or name.rsplit("/", 1)[-1] in SKIP_NAMES \
                        or zi.is_dir():
                    continue
                h = hashlib.sha256()
                with zf.open(zi) as fh:
                    for chunk in iter(lambda: fh.read(_BLOCK), b""):
                        h.update(chunk)
                rows.append((name, h.hexdigest()))
    return {"digest": _content_digest_of(rows), "files": len(rows)}


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(_BLOCK), b""):
            h.update(chunk)
    return h.hexdigest()


def write_3tz(src_dir: str, out_path: str, *, compress: bool = False,
              progress=None) -> dict:
    """Pack ``src_dir`` (with ``tileset.json`` at its root) into ``out_path``.

    ``progress(done, total)`` is called after each entry, if given.
    Returns ``{"entries", "bytes", "sha256", "content_digest", "seconds",
    "path"}``; the entry count excludes the index. ``content_digest`` is
    ``{"digest", "files", "computed_by": "producer"}``, hashed from the
    bytes as they are copied. The archive is written to a sibling
    ``.part`` file and renamed at the end, so a failed write never leaves
    a half archive under the final name.
    """
    t0 = time.time()
    src_dir = os.path.abspath(src_dir)
    out_path = os.path.abspath(out_path)
    if out_path.startswith(src_dir.rstrip(os.sep) + os.sep):
        raise ValueError("the archive must not be written inside the folder it packs")
    entries = _entries(src_dir)
    total = len(entries)

    part = out_path + ".part"
    records = []
    hashed = []
    try:
        with zipfile.ZipFile(part, "w", zipfile.ZIP_STORED, allowZip64=True) as zf:
            for i, (rel, disk) in enumerate(entries, start=1):
                src = os.path.join(src_dir, disk)
                size = os.path.getsize(src)
                if size > MAX_ENTRY_BYTES:
                    raise ValueError(f"{rel}: {size} bytes, over the 4 GB per-file limit")
                zi = _zinfo(rel, size, compress)
                h = hashlib.sha256()
                with open(src, "rb") as fh, \
                        zf.open(zi, "w", force_zip64=size >= ZIP64_LIMIT) as dst:
                    for chunk in iter(lambda: fh.read(_BLOCK), b""):
                        h.update(chunk)
                        dst.write(chunk)
                hashed.append((rel, h.hexdigest()))
                records.append((_md5(rel), zi.header_offset))
                if progress is not None:
                    progress(i, total)
            records.sort(key=lambda r: _sort_key(r[0]))
            index = b"".join(md5 + struct.pack("<Q", off) for md5, off in records)
            zf.writestr(_zinfo(INDEX_NAME, len(index), False), index)
        os.replace(part, out_path)
    except BaseException:
        try:
            os.remove(part)
        except OSError:
            pass
        raise

    return {
        "path": out_path,
        "entries": total,
        "bytes": os.path.getsize(out_path),
        "sha256": sha256_file(out_path),
        "content_digest": {"digest": _content_digest_of(hashed),
                           "files": len(hashed), "computed_by": "producer"},
        "seconds": round(time.time() - t0, 3),
    }


def read_index(path: str) -> dict:
    """``md5 -> local header offset`` from the index entry.

    Checks that the index is the last entry, stored, a multiple of 24
    bytes and sorted by MD5."""
    with zipfile.ZipFile(path) as zf:
        infos = zf.infolist()
        if not infos or infos[-1].filename != INDEX_NAME:
            raise ValueError("the index must be the last entry")
        if infos[-1].compress_type != zipfile.ZIP_STORED:
            raise ValueError("the index must be stored uncompressed")
        raw = zf.read(INDEX_NAME)
    if len(raw) % _RECORD:
        raise ValueError("index length is not a multiple of 24")
    out, prev = {}, None
    for i in range(0, len(raw), _RECORD):
        md5, (off,) = raw[i:i + 16], struct.unpack("<Q", raw[i + 16:i + _RECORD])
        if prev is not None and _sort_key(prev) > _sort_key(md5):
            raise ValueError("index not sorted by md5")
        prev = md5
        out[md5] = off
    return out


def _local_entry(fh, off: int):
    """(name, method, compressed size) of the Local File Header at ``off``;
    leaves ``fh`` at the start of the entry data."""
    fh.seek(off)
    hdr = fh.read(30)
    if len(hdr) < 30:
        raise ValueError(f"offset {off} is past the end of the archive")
    sig, _, _, method, _, _, _, csize, _, nlen, xlen = struct.unpack("<IHHHHHIIIHH", hdr)
    if sig != 0x04034B50:
        raise ValueError(f"offset {off} does not point to a local file header")
    name = fh.read(nlen).decode("utf-8")
    extra = fh.read(xlen)
    if csize == ZIP64_LIMIT:                       # zip64: sizes in the extra field
        pos = 0
        while pos + 4 <= len(extra):
            tag, ln = struct.unpack("<HH", extra[pos:pos + 4])
            if tag == 1:
                _usize, csize = struct.unpack("<QQ", extra[pos + 4:pos + 20])
                break
            pos += 4 + ln
    return name, method, csize


def read_entry(path: str, name: str, index: dict | None = None) -> bytes:
    """Random access to one entry through the index, as a viewer would do
    with an HTTP Range request or ``File.slice``: local header, then data."""
    index = index if index is not None else read_index(path)
    key = _md5(name)
    if key not in index:
        raise KeyError(name)
    with open(path, "rb") as fh:
        fname, method, csize = _local_entry(fh, index[key])
        if fname != normalize(name):
            raise ValueError(f"index points to {fname}, not {name}")
        data = fh.read(csize)
    if method == zipfile.ZIP_STORED:
        return data
    if method == zipfile.ZIP_DEFLATED:
        import zlib
        return zlib.decompress(data, -15)
    raise ValueError(f"{name}: unsupported compression method {method}")


def verify_3tz(path: str, src_dir: str | None = None) -> dict:
    """Check an archive against the spec and, optionally, against a folder.

    - the index is the last entry, stored, sorted (``read_index``);
    - every entry but the index has one record, and its offset points to
      a local header carrying that very name;
    - ``tileset.json`` is at the root and no path contains ``.3tz``;
    - with ``src_dir``: the same set of files, each byte-identical (CRC of
      the zip checked too, by reading through ``zipfile``).

    Returns ``{"ok", "entries", "errors", "seconds"}``; ``errors`` lists
    every problem found (empty when ``ok``)."""
    t0 = time.time()
    errors = []
    try:
        index = read_index(path)
    except Exception as exc:
        return {"ok": False, "entries": 0, "errors": [f"index: {exc}"],
                "seconds": round(time.time() - t0, 3)}

    with zipfile.ZipFile(path) as zf:
        infos = [zi for zi in zf.infolist() if zi.filename != INDEX_NAME]
        names = [zi.filename for zi in infos]
        if "tileset.json" not in names:
            errors.append("tileset.json is not at the root")
        if len(index) != len(infos):
            errors.append(f"index has {len(index)} records for {len(infos)} entries")
        with open(path, "rb") as fh:
            for zi in infos:
                if ".3tz" in zi.filename.lower():
                    errors.append(f"'.3tz' path inside the archive: {zi.filename}")
                off = index.get(_md5(zi.filename))
                if off is None:
                    errors.append(f"no index record for {zi.filename}")
                    continue
                try:
                    fname, _, _ = _local_entry(fh, off)
                except ValueError as exc:
                    errors.append(f"{zi.filename}: {exc}")
                    continue
                if fname != zi.filename:
                    errors.append(f"record of {zi.filename} points to {fname}")

        if src_dir is not None:
            try:
                on_disk = dict(_entries(src_dir))
            except ValueError as exc:
                errors.append(f"source folder: {exc}")
                on_disk = {}
            expected = list(on_disk)
            missing = sorted(set(expected) - set(names))
            extra = sorted(set(names) - set(expected))
            errors += [f"missing from archive: {n}" for n in missing]
            errors += [f"not in source folder: {n}" for n in extra]
            for rel in sorted(set(expected) & set(names)):
                if not _same_bytes(zf, rel, os.path.join(src_dir, on_disk[rel])):
                    errors.append(f"differs from source: {rel}")

    return {"ok": not errors, "entries": len(infos), "errors": errors,
            "seconds": round(time.time() - t0, 3)}


def _same_bytes(zf: zipfile.ZipFile, name: str, disk_path: str) -> bool:
    try:
        if zf.getinfo(name).file_size != os.path.getsize(disk_path):
            return False
        with zf.open(name) as a, open(disk_path, "rb") as b:
            while True:
                ca, cb = a.read(_BLOCK), b.read(_BLOCK)
                if ca != cb:
                    return False
                if not ca:
                    return True
    except (zipfile.BadZipFile, OSError):           # CRC mismatch lands here
        return False


if __name__ == "__main__":
    import json
    import sys
    src, out = sys.argv[1], sys.argv[2]
    r = write_3tz(src, out)
    r["verify"] = verify_3tz(out, src)
    print(json.dumps(r, indent=2))
