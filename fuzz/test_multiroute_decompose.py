# SPDX-License-Identifier: GPL-3.0-or-later
"""Synthetic multi-route decomposer test.

Take N independent single-route RBFs that share the same source LAB,
OR their CRAM cells onto the zero baseline, feed through rbf2fasm
--semantic, verify the decomposer recovers exactly N ROUTE directives
with 0 residue, then feed back through fasm2rbf and confirm the
reconstructed CRAM matches the synthetic target byte-for-byte.
"""
import os
import sys
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from bitstream import (
    CRC_PREAMBLE,
    CRC_FRAME_SIZE,
    CRC_DATA_SIZE,
    CRC_FIRST_CRAM_FRAME,
    CRC_LAST_FRAME,
)
from rbf2fasm import diff_cells, emit
from fasm2rbf import bitgen

ROOT = Path(HERE).parent
RBF = ROOT / "results" / "rbf"


def cram(rbf):
    out = bytearray()
    for n in range(CRC_FIRST_CRAM_FRAME, CRC_LAST_FRAME + 1):
        s = CRC_PREAMBLE + n * CRC_FRAME_SIZE
        out += rbf[s:s + CRC_DATA_SIZE]
    return bytes(out)


def merge_routes(zero, route_rbfs):
    """Union cell sets of every route_rbf onto zero (XOR accumulates)."""
    all_cells = set()
    for r in route_rbfs:
        all_cells |= set(diff_cells(r, zero))
    buf = bytearray(zero)
    for off, bp in all_cells:
        buf[off] ^= (1 << bp)
    return bytes(buf), all_cells


def run_case(label, sx, sy, route_names):
    zpath = RBF / f"lits_zero_{sx}_{sy}.rbf"
    zero = zpath.read_bytes()
    rbfs = [(RBF / n).read_bytes() for n in route_names]
    merged, all_cells = merge_routes(zero, rbfs)

    fasm = emit(merged, zero, semantic=True)
    route_lines = [
        l for l in fasm.splitlines()
        if l.strip() and l.strip().startswith("ROUTE")
    ]
    bit_lines = [
        l for l in fasm.splitlines()
        if l.strip() and l.strip().startswith("BIT")
    ]
    ok_decode = len(route_lines) == len(route_names) and len(bit_lines) == 0

    rec = bitgen(fasm, zero, patch_crc=False)
    ok_replay = cram(rec) == cram(merged)

    status = "OK  " if (ok_decode and ok_replay) else "FAIL"
    print(
        f"  [{status}] {label}: N={len(route_names)} merged={len(all_cells)}  "
        f"decoded_routes={len(route_lines)} residue_bits={len(bit_lines)}  "
        f"replay={'bit-perfect' if ok_replay else 'MISMATCH'}"
    )
    return ok_decode and ok_replay


def main():
    import random
    import re
    random.seed(0xC4C4)

    # Discover per-source route RBFs on disk.
    PAIR_RE = re.compile(r"lits_pair_X(\d+)Y(\d+)_to_X\d+Y\d+N\d+_\w+\.rbf$")
    per_src = {}
    for p in RBF.glob("lits_pair_*.rbf"):
        m = PAIR_RE.match(p.name)
        if not m:
            continue
        sx, sy = int(m[1]), int(m[2])
        if not (RBF / f"lits_zero_{sx}_{sy}.rbf").exists():
            continue
        per_src.setdefault((sx, sy), []).append(p.name)

    ok = fail = 0
    for (sx, sy), names in sorted(per_src.items()):
        if len(names) < 2:
            continue
        # Random 2-route and 3-route samples per source.
        for k in (2, 3):
            if len(names) < k:
                continue
            sample = random.sample(names, k)
            label = f"({sx:2d},{sy:2d}) x{k}"
            if run_case(label, sx, sy, sample):
                ok += 1
            else:
                fail += 1

    print(f"\n{ok} ok / {fail} fail")
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
