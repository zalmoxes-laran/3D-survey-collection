import json
import os
import struct


def _implicit_level_offset(level, tree_type):
    if level <= 0:
        return 0
    if tree_type == 'OCTREE':
        return ((8 ** level) - 1) // 7
    return ((4 ** level) - 1) // 3

def _implicit_total_nodes(level_count, tree_type):
    return _implicit_level_offset(level_count, tree_type)

def _implicit_morton_index(node, tree_type):
    depth = int(node.get("depth", 0))
    x = int(node.get("grid_x", 0))
    y = int(node.get("grid_y", 0))
    z = int(node.get("grid_z", 0))

    morton = 0
    if tree_type == 'OCTREE':
        for bit in range(depth - 1, -1, -1):
            slot = ((x >> bit) & 1) + (((y >> bit) & 1) << 1) + (((z >> bit) & 1) << 2)
            morton = (morton << 3) + slot
    else:
        for bit in range(depth - 1, -1, -1):
            slot = ((x >> bit) & 1) + (((y >> bit) & 1) << 1)
            morton = (morton << 2) + slot
    return morton

def _bitarray_set_once(bitarr, bit_idx):
    byte_idx = bit_idx // 8
    mask = 1 << (bit_idx % 8)
    old = bitarr[byte_idx]
    if old & mask:
        return False
    bitarr[byte_idx] = old | mask
    return True

def _write_subtree_file(subtree_path, tile_bits, tile_count, content_bits, content_count):
    streams = []
    stream_map = {}
    stream_offsets = []
    cursor = 0

    for bits in (tile_bits, content_bits):
        key = bytes(bits)
        idx = stream_map.get(key)
        if idx is None:
            idx = len(streams)
            stream_map[key] = idx
            streams.append(key)
            stream_offsets.append(cursor)
            cursor += len(key)

    buffer_views = []
    for i, blob in enumerate(streams):
        buffer_views.append({
            "buffer": 0,
            "byteOffset": stream_offsets[i],
            "byteLength": len(blob),
        })

    tile_view_idx = stream_map[bytes(tile_bits)]
    content_view_idx = stream_map[bytes(content_bits)]
    bin_blob = b"".join(streams)

    subtree_json = {
        "buffers": [{"byteLength": len(bin_blob)}],
        "bufferViews": buffer_views,
        "tileAvailability": {
            "bitstream": tile_view_idx,
            "availableCount": int(tile_count),
        },
        "contentAvailability": [{
            "bitstream": content_view_idx,
            "availableCount": int(content_count),
        }],
        "childSubtreeAvailability": {
            "constant": 0,
            "availableCount": 0,
        },
    }

    json_blob = json.dumps(subtree_json, separators=(",", ":")).encode("utf-8")
    while len(json_blob) % 8 != 0:
        json_blob += b" "
    while len(bin_blob) % 8 != 0:
        bin_blob += b"\x00"

    os.makedirs(os.path.dirname(subtree_path), exist_ok=True)
    with open(subtree_path, "wb") as f:
        f.write(struct.pack("<4sIQQ", b"subt", 1, len(json_blob), len(bin_blob)))
        f.write(json_blob)
        f.write(bin_blob)


# ---------------------------------------------------------------------------
#  GLB export for a single node (leaf or internal with LOD)
# ---------------------------------------------------------------------------
