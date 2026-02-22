import json
import os
import struct


def _patch_glb_to_unlit(glb_path):
    try:
        with open(glb_path, "rb") as f:
            data = f.read()
    except Exception:
        return False, "read-failed"

    if len(data) < 12:
        return False, "too-short"
    magic, version, _ = struct.unpack_from("<4sII", data, 0)
    if magic != b"glTF" or version != 2:
        return False, "not-glb2"

    chunks = []
    offset = 12
    while offset + 8 <= len(data):
        chunk_len, chunk_type = struct.unpack_from("<II", data, offset)
        offset += 8
        if offset + chunk_len > len(data):
            return False, "invalid-chunk"
        chunk_data = data[offset:offset + chunk_len]
        offset += chunk_len
        chunks.append((chunk_type, chunk_data))

    json_idx = None
    json_obj = None
    for i, (ctype, cdata) in enumerate(chunks):
        if ctype == 0x4E4F534A:  # JSON
            json_idx = i
            try:
                json_obj = json.loads(cdata.decode("utf-8"))
            except Exception:
                return False, "json-decode-failed"
            break
    if json_idx is None or json_obj is None:
        return False, "json-missing"

    mats = json_obj.get("materials")
    if not isinstance(mats, list) or not mats:
        return True, "no-materials"

    changed = False
    ext_used = json_obj.get("extensionsUsed")
    if not isinstance(ext_used, list):
        ext_used = []
        json_obj["extensionsUsed"] = ext_used
        changed = True
    if "KHR_materials_unlit" not in ext_used:
        ext_used.append("KHR_materials_unlit")
        changed = True

    for mat in mats:
        if not isinstance(mat, dict):
            continue
        ext = mat.get("extensions")
        if not isinstance(ext, dict):
            ext = {}
            mat["extensions"] = ext
            changed = True
        if "KHR_materials_unlit" not in ext:
            ext["KHR_materials_unlit"] = {}
            changed = True
        pbr = mat.get("pbrMetallicRoughness")
        if not isinstance(pbr, dict):
            pbr = {}
            mat["pbrMetallicRoughness"] = pbr
            changed = True
        if pbr.get("metallicFactor", None) != 0.0:
            pbr["metallicFactor"] = 0.0
            changed = True
        if pbr.get("roughnessFactor", None) != 1.0:
            pbr["roughnessFactor"] = 1.0
            changed = True

    if not changed:
        return True, "unchanged"

    json_bytes = json.dumps(json_obj, separators=(",", ":")).encode("utf-8")
    while len(json_bytes) % 4 != 0:
        json_bytes += b" "
    chunks[json_idx] = (0x4E4F534A, json_bytes)

    total_len = 12 + sum(8 + len(cdata) for _, cdata in chunks)
    out = bytearray()
    out += struct.pack("<4sII", b"glTF", 2, total_len)
    for ctype, cdata in chunks:
        out += struct.pack("<II", len(cdata), ctype)
        out += cdata

    try:
        with open(glb_path, "wb") as f:
            f.write(out)
    except Exception:
        return False, "write-failed"
    return True, "patched"

def _patch_output_glbs_to_unlit(output_dir):
    patched = 0
    failed = 0
    if not output_dir or not os.path.isdir(output_dir):
        return patched, failed
    for root, _, names in os.walk(output_dir):
        for name in names:
            if not name.lower().endswith(".glb"):
                continue
            ok, _ = _patch_glb_to_unlit(os.path.join(root, name))
            if ok:
                patched += 1
            else:
                failed += 1
    return patched, failed

def _strip_glb_unlit(glb_path):
    try:
        with open(glb_path, "rb") as f:
            data = f.read()
    except Exception:
        return False, "read-failed"

    if len(data) < 12:
        return False, "too-short"
    magic, version, _ = struct.unpack_from("<4sII", data, 0)
    if magic != b"glTF" or version != 2:
        return False, "not-glb2"

    chunks = []
    offset = 12
    while offset + 8 <= len(data):
        chunk_len, chunk_type = struct.unpack_from("<II", data, offset)
        offset += 8
        if offset + chunk_len > len(data):
            return False, "invalid-chunk"
        chunk_data = data[offset:offset + chunk_len]
        offset += chunk_len
        chunks.append((chunk_type, chunk_data))

    json_idx = None
    json_obj = None
    for i, (ctype, cdata) in enumerate(chunks):
        if ctype == 0x4E4F534A:  # JSON
            json_idx = i
            try:
                json_obj = json.loads(cdata.decode("utf-8"))
            except Exception:
                return False, "json-decode-failed"
            break
    if json_idx is None or json_obj is None:
        return False, "json-missing"

    changed = False
    for ext_key in ("extensionsUsed", "extensionsRequired"):
        ext_list = json_obj.get(ext_key)
        if isinstance(ext_list, list) and "KHR_materials_unlit" in ext_list:
            ext_list[:] = [x for x in ext_list if x != "KHR_materials_unlit"]
            changed = True
            if not ext_list:
                json_obj.pop(ext_key, None)

    mats = json_obj.get("materials")
    if isinstance(mats, list):
        for mat in mats:
            if not isinstance(mat, dict):
                continue
            ext = mat.get("extensions")
            if isinstance(ext, dict) and "KHR_materials_unlit" in ext:
                ext.pop("KHR_materials_unlit", None)
                changed = True
                if not ext:
                    mat.pop("extensions", None)

    if not changed:
        return True, "unchanged"

    json_bytes = json.dumps(json_obj, separators=(",", ":")).encode("utf-8")
    while len(json_bytes) % 4 != 0:
        json_bytes += b" "
    chunks[json_idx] = (0x4E4F534A, json_bytes)

    total_len = 12 + sum(8 + len(cdata) for _, cdata in chunks)
    out = bytearray()
    out += struct.pack("<4sII", b"glTF", 2, total_len)
    for ctype, cdata in chunks:
        out += struct.pack("<II", len(cdata), ctype)
        out += cdata

    try:
        with open(glb_path, "wb") as f:
            f.write(out)
    except Exception:
        return False, "write-failed"
    return True, "stripped"

def _strip_output_glbs_unlit(output_dir):
    stripped = 0
    failed = 0
    if not output_dir or not os.path.isdir(output_dir):
        return stripped, failed
    for root, _, names in os.walk(output_dir):
        for name in names:
            if not name.lower().endswith(".glb"):
                continue
            ok, _ = _strip_glb_unlit(os.path.join(root, name))
            if ok:
                stripped += 1
            else:
                failed += 1
    return stripped, failed


# ---------------------------------------------------------------------------
#  Bounding-box helpers
# ---------------------------------------------------------------------------
