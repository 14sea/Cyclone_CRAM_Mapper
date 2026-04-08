# SPDX-License-Identifier: GPL-3.0-or-later
"""Cross-source synthetic round-trip.

Merge two lits_pair RBFs from DIFFERENT source LABs onto the shared
baseline.rbf: apply source_overhead[A] ∪ source_overhead[B] ∪ route_A
∪ route_B cells as XOR onto baseline. Feed through rbf2fasm --semantic
and fasm2rbf, confirm CRAM round-trip.

The semantic decomposer finds the two routes via set-cover; overhead
cells fall through as BIT residue lines, which fasm2rbf's BIT directive
flips onto the same baseline. Net effect: identical CRAM.
"""
import json
import os
import sys
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from bitstream import (
    CRC_PREAMBLE, CRC_FRAME_SIZE, CRC_DATA_SIZE,
    CRC_FIRST_CRAM_FRAME, CRC_LAST_FRAME,
)
from rbf2fasm import emit, diff_cells
from fasm2rbf import bitgen
import route_signatures

ROOT = Path(HERE).parent
RBF = ROOT / "results" / "rbf"


def cram(rbf):
    out = bytearray()
    for n in range(CRC_FIRST_CRAM_FRAME, CRC_LAST_FRAME + 1):
        s = CRC_PREAMBLE + n * CRC_FRAME_SIZE
        out += rbf[s:s + CRC_DATA_SIZE]
    return bytes(out)


def synthesize(base, src_overheads, route_cells_lists):
    """XOR union of overhead + route cells onto base."""
    all_cells = set()
    for cells in src_overheads:
        for o, b in cells:
            all_cells.add((o, b))
    for cells in route_cells_lists:
        for o, b in cells:
            all_cells.add((o, b))
    buf = bytearray(base)
    for off, bp in all_cells:
        buf[off] ^= (1 << bp)
    return bytes(buf), all_cells


def run_case(label, base, overhead_tab, cells_tab, cases):
    """`cases` is list of (sx, sy, dx, dy, dn, port)."""
    src_overheads = [overhead_tab[f"{sx},{sy}"] for sx,sy,*_ in cases]
    route_cells = [
        cells_tab[route_signatures._route_key(sx,sy,dx,dy,dn,port)]
        for sx,sy,dx,dy,dn,port in cases
    ]
    merged, all_cells = synthesize(base, src_overheads, route_cells)

    fasm = emit(merged, base, semantic=True)
    routes = [l for l in fasm.splitlines() if l.startswith("ROUTE")]
    bits = [l for l in fasm.splitlines() if l.startswith("BIT")]
    rec = bitgen(fasm, base, patch_crc=False)
    ok = cram(rec) == cram(merged)

    print(
        f"  [{'OK  ' if ok else 'FAIL'}] {label}: "
        f"merged_cells={len(all_cells)} routes={len(routes)}/{len(cases)} "
        f"residue_bits={len(bits)} replay={'bit-perfect' if ok else 'MISMATCH'}"
    )
    return ok


def main():
    base = (RBF / "baseline.rbf").read_bytes()
    overhead_tab = json.loads(
        (ROOT / "results" / "source_overhead.json").read_text()
    )
    cells_tab = route_signatures.load_cells()

    cases = [
        ("2-src (10,10)+(28,12)", [
            (10,10,10,11,0,"datab"),
            (28,12,26,10,0,"datab"),
        ]),
        ("2-src (4,4)+(25,15) jailbreak", [
            (4,4,10,10,0,"datab"),
            (25,15,28,15,0,"datab"),
        ]),
        ("3-src (10,10)+(16,8)+(25,6)", [
            (10,10,10,11,0,"datab"),
            (16,8,11,12,0,"datab"),
            (25,6,11,12,0,"datab"),
        ]),
    ]

    ok = fail = 0
    for label, cs in cases:
        try:
            if run_case(label, base, overhead_tab, cells_tab, cs):
                ok += 1
            else:
                fail += 1
        except KeyError as e:
            print(f"  [SKIP] {label}: missing key {e}")
    print(f"\n{ok} ok / {fail} fail")
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
