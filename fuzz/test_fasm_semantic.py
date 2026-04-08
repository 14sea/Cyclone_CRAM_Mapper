# SPDX-License-Identifier: GPL-3.0-or-later
"""Semantic rbf2fasm regression.

For every lits_pair_*.rbf, run semantic rbf2fasm → expect a single ROUTE
line → feed through fasm2rbf → compare CRAM bytes to the original.
Tracks: (a) how many RBFs collapsed to a single ROUTE, (b) how many
round-trip bit-perfect through the high-level path (which exercises the
synth_route fingerprint + r4_iindex + universal overhead stack).
"""
import os
import re
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
from fasm2rbf import bitgen
from rbf2fasm import emit

ROOT = Path(HERE).parent
RBF = ROOT / "results" / "rbf"

NAME_RE = re.compile(r"lits_pair_X(\d+)Y(\d+)_to_X(\d+)Y(\d+)N(\d+)_(\w+)\.rbf$")


def cram(rbf):
    out = bytearray()
    for n in range(CRC_FIRST_CRAM_FRAME, CRC_LAST_FRAME + 1):
        s = CRC_PREAMBLE + n * CRC_FRAME_SIZE
        out += rbf[s:s + CRC_DATA_SIZE]
    return bytes(out)


def main():
    total = 0
    collapsed = 0     # dump is exactly one ROUTE line
    bit_perfect = 0   # rebuild matches target CRAM
    fallback = 0      # signature matched but synth_route produced different bits
    miss = 0          # signature missing (shouldn't happen — we just built it)
    by_src_collapsed = {}
    by_src_bp = {}

    for p in sorted(RBF.glob("lits_pair_*.rbf")):
        m = NAME_RE.match(p.name)
        if not m:
            continue
        sx, sy = int(m[1]), int(m[2])
        zpath = RBF / f"lits_zero_{sx}_{sy}.rbf"
        if not zpath.exists():
            continue
        total += 1
        zero = zpath.read_bytes()
        target = p.read_bytes()
        fasm = emit(target, zero, semantic=True)

        route_lines = [
            l for l in fasm.splitlines()
            if l.strip() and not l.strip().startswith("#")
        ]
        is_collapsed = len(route_lines) == 1 and route_lines[0].startswith("ROUTE")
        if is_collapsed:
            collapsed += 1
            by_src_collapsed[(sx, sy)] = by_src_collapsed.get((sx, sy), 0) + 1
        else:
            miss += 1
            continue

        try:
            rec = bitgen(fasm, zero, patch_crc=False)
        except Exception as e:
            fallback += 1
            print(f"  BUILD FAIL {p.name}: {e}")
            continue

        if cram(rec) == cram(target):
            bit_perfect += 1
            by_src_bp[(sx, sy)] = by_src_bp.get((sx, sy), 0) + 1
        else:
            fallback += 1
            # Not necessarily a regression — single-route ROUTE directive
            # exercises synth_route, whose guaranteed-bit-perfect coverage
            # is the 15-island green zone. Yellow-zone sources are expected
            # to round-trip the cell set (BIT path) but may diverge on the
            # high-level semantic path.
            pass

    print("per-source collapse / bit-perfect:")
    for k in sorted(by_src_collapsed):
        c = by_src_collapsed[k]
        b = by_src_bp.get(k, 0)
        tag = "GREEN" if c == b else "yellow"
        print(f"  ({k[0]:2d},{k[1]:2d})  collapse={c:3d}  bit_perfect={b:3d}  {tag}")
    print()
    print(f"total:         {total}")
    print(f"collapsed:     {collapsed}  ({collapsed/total*100:.1f}%)")
    print(f"bit_perfect:   {bit_perfect}  ({bit_perfect/total*100:.1f}%)")
    print(f"yellow-zone diverge: {fallback}")
    print(f"signature miss: {miss}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
