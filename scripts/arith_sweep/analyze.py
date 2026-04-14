#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Diff counter vs identity RBFs, extract per-width arith cell set.

Output: /tmp/arith_sweep/cells_by_width.json
        /tmp/arith_sweep/summary.json
"""
import os, json, sys

RBF_SIZE = 368_011
PREAMBLE = 32
FRAME_SIZE = 210
N_FRAMES = 1752
POSTAMBLE = PREAMBLE + N_FRAMES * FRAME_SIZE  # = 368_012 ... off by one?

def load(path):
    with open(path, "rb") as f:
        data = f.read()
    assert len(data) == RBF_SIZE, f"{path}: size {len(data)} != {RBF_SIZE}"
    return data

def is_crc_byte(off):
    """Return True if offset lies on a CRC byte (offset 208 or 209 within a frame)."""
    if off < PREAMBLE:
        return False
    rel = off - PREAMBLE
    if rel >= N_FRAMES * FRAME_SIZE:
        return False
    byte_in_frame = rel % FRAME_SIZE
    return byte_in_frame >= 208

def diff_bits(a: bytes, b: bytes, skip_crc=True):
    """Return list of (offset, bp, direction) for bit differences.
    direction: +1 = set in b not in a ("SET"), -1 = set in a not in b ("CLEAR")."""
    result = []
    for i in range(len(a)):
        if a[i] == b[i]:
            continue
        if skip_crc and is_crc_byte(i):
            continue
        xor = a[i] ^ b[i]
        for bp in range(8):
            if not (xor >> bp) & 1:
                continue
            a_bit = (a[i] >> bp) & 1
            b_bit = (b[i] >> bp) & 1
            direction = 1 if (b_bit and not a_bit) else -1
            result.append((i, bp, direction))
    return result

def classify_region(off):
    """Rough CRAM region label by frame index."""
    if off < PREAMBLE:
        return "preamble"
    rel = off - PREAMBLE
    if rel >= N_FRAMES * FRAME_SIZE:
        return "postamble"
    frame = rel // FRAME_SIZE
    if frame < 25:
        return "header"
    if 1692 <= frame <= 1738:
        return "block_band"
    return "lab_cram"

def build_config(tag):
    """tag = 'c{w}_{lo|up}' or already-built legacy dirs."""
    return os.path.join("/tmp/arith_sweep", tag)

LEGACY = {
    # (counter_rbf_path, identity_rbf_path, width, half)
    "c16":    ("/tmp/m5_revenge/counter16/output_files/top.rbf",
               "/tmp/m5_revenge/identity16/output_files/top.rbf", 16, "full"),
    "c24":    ("/tmp/m5_revenge/counter24/output_files/top.rbf",
               "/tmp/m5_revenge/identity24/output_files/top.rbf", 24, "crossLAB"),
}

def sweep_items():
    """Yield (key, counter_rbf, identity_rbf, width, half) tuples."""
    for w in range(2, 9):
        for half in ["lo", "up"]:
            c = f"c{w}_{half}"
            i = f"i{w}_{half}"
            yield (c, os.path.join("/tmp/arith_sweep", c, "output_files/top.rbf"),
                      os.path.join("/tmp/arith_sweep", i, "output_files/top.rbf"),
                      w, half)
    for w in range(9, 16):
        c = f"c{w}_xh"
        i = f"i{w}_xh"
        yield (c, os.path.join("/tmp/arith_sweep", c, "output_files/top.rbf"),
                  os.path.join("/tmp/arith_sweep", i, "output_files/top.rbf"),
                  w, "xh")
    for k, (c, i, w, half) in LEGACY.items():
        yield (k, c, i, w, half)

def n_slots_for(width, half):
    """Return N-slot tuple (FF slot numbers) for this config."""
    if half == "lo_y17":
        # counter8_y17 used Y=18 with N=1,3,...,15 (from earlier session memory)
        return tuple(range(1, 1 + 2*width, 2))
    if half == "lo":
        return tuple(range(1, 1 + 2*width, 2))
    if half == "up":
        return tuple(range(17, 17 + 2*width, 2))
    if half == "full":
        return tuple(range(1, 32, 2))  # all 16 FFs N=1..31
    if half == "crossLAB":
        # LAB(4,18) all + LAB(4,17) N=1..15
        return tuple(list(range(1, 32, 2)) + [("y17", n) for n in range(1, 17, 2)])
    return tuple()

def main():
    results = {}
    summary_rows = []
    for key, c_path, i_path, width, half in sweep_items():
        if not (os.path.exists(c_path) and os.path.exists(i_path)):
            summary_rows.append({"key": key, "status": "MISSING", "c": c_path, "i": i_path})
            continue
        try:
            c = load(c_path); i = load(i_path)
        except Exception as e:
            summary_rows.append({"key": key, "status": f"ERR {e}"})
            continue
        diffs = diff_bits(i, c, skip_crc=True)
        sets = [(o, b) for (o, b, d) in diffs if d > 0]
        clears = [(o, b) for (o, b, d) in diffs if d < 0]
        region_counts = {}
        for (o, b, d) in diffs:
            r = classify_region(o)
            region_counts[r] = region_counts.get(r, 0) + 1
        results[key] = {
            "width": width,
            "half": half,
            "n_slots": list(n_slots_for(width, half)),
            "set": sets,
            "clear": clears,
            "total": len(diffs),
            "regions": region_counts,
        }
        summary_rows.append({"key": key, "width": width, "half": half,
                             "set": len(sets), "clear": len(clears),
                             "total": len(diffs), "regions": region_counts})
    with open("/tmp/arith_sweep/cells_by_width.json", "w") as f:
        # compact: convert tuples
        json.dump({k: v for k, v in results.items()}, f)
    with open("/tmp/arith_sweep/summary.json", "w") as f:
        json.dump(summary_rows, f, indent=2)
    print(json.dumps(summary_rows, indent=2))

if __name__ == "__main__":
    main()
