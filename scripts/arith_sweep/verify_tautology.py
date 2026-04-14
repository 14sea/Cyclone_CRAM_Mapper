#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Apply per-width blob to identity_w and verify it matches counter_w exactly
(except header/CRC which we stripped as noise)."""
import json

T = json.load(open("/tmp/arith_sweep/arith_blockband_by_width.json"))
RBF = 368_011
PRE = 32; FS = 210

def load(p):
    with open(p,"rb") as f: return f.read()

def is_crc_byte(off):
    if off < PRE: return False
    rel = off - PRE
    if rel >= 1752 * FS: return False
    return (rel % FS) >= 208

def apply_blob(base, blob):
    buf = bytearray(base)
    for (o, b) in blob["set"]:
        buf[o] |= (1 << b)
    for (o, b) in blob["clear"]:
        buf[o] &= ~(1 << b) & 0xFF
    return bytes(buf)

def diff_non_crc(a, b):
    """Count bit differences, excluding CRC and header (frame<25)."""
    data = 0; hdr = 0; crc = 0; block = 0
    for i in range(len(a)):
        if a[i] == b[i]: continue
        rel = i - PRE if i >= PRE else -1
        frame = rel // FS if rel >= 0 else -1
        xor = a[i] ^ b[i]
        n = bin(xor).count("1")
        if is_crc_byte(i): crc += n
        elif frame >= 0 and frame < 25: hdr += n
        elif 1692 <= frame <= 1738: block += n
        else: data += n
    return {"data": data, "header": hdr, "crc": crc, "block_band": block}

# Test each width
print(f"{'w':>3} {'diff_vs_counter_w':>20}")
for w in range(2, 9):
    ident = load(f"/tmp/arith_sweep/i{w}_lo/output_files/top.rbf")
    target = load(f"/tmp/arith_sweep/c{w}_lo/output_files/top.rbf")
    blob = T["widths"][str(w)]
    got = apply_blob(ident, blob)
    d = diff_non_crc(got, target)
    print(f"{w:>3} {str(d):>20}")

for w in range(9, 16):
    ident = load(f"/tmp/arith_sweep/i{w}_xh/output_files/top.rbf")
    target = load(f"/tmp/arith_sweep/c{w}_xh/output_files/top.rbf")
    blob = T["widths"][str(w)]
    got = apply_blob(ident, blob)
    d = diff_non_crc(got, target)
    print(f"{w:>3} {str(d):>20}")

# w=16 and w=24
ident = load("/tmp/m5_revenge/identity16/output_files/top.rbf")
target = load("/tmp/m5_revenge/counter16/output_files/top.rbf")
blob = T["widths"]["16"]
got = apply_blob(ident, blob)
d = diff_non_crc(got, target)
print(f" 16 {str(d):>20}")

ident = load("/tmp/m5_revenge/identity24/output_files/top.rbf")
target = load("/tmp/m5_revenge/counter24/output_files/top.rbf")
blob = T["multi_lab"]["16+8"]
got = apply_blob(ident, blob)
d = diff_non_crc(got, target)
print(f"24* {str(d):>20}")
