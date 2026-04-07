# SPDX-License-Identifier: GPL-3.0-or-later
"""L2: cell-set diff between synthesized RBF and real Quartus RBF.

For each test case, synthesize an RBF via synth_route() and compare its
active CRAM cells against a Quartus-compiled RBF for the same (src, dst).
Report intersection / synth-only / quartus-only.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from pathlib import Path
from collections import defaultdict
from route_synth import synth_route
from bitstream import RouteCodec

ROOT = Path(__file__).resolve().parent.parent
RBF_DIR = ROOT / "results" / "rbf"
ZERO = RBF_DIR / "lits_zero_10_10.rbf"


def cells_of(codec, rbf, zero):
    """Return {(type, name, off, bp)} set."""
    sw = codec.read_switches(rbf, zero)
    out = set()
    for t, lst in sw.items():
        for e in lst:
            # entries vary in shape; first 3 fields are name, off, bp
            name, off, bp = e[0], e[1], e[2]
            out.add((t, name, off, bp))
    return out


def summarize_by_type(cells):
    by_type = defaultdict(list)
    for t, name, off, bp in cells:
        by_type[t].append((name, off, bp))
    return {t: len(v) for t, v in by_type.items()}, by_type


CASES = [
    ((10, 10), (11, 10), "lits_pair_X10Y10_to_X11Y10N0_datab.rbf"),
    ((10, 10), (12, 10), "lits_pair_X10Y10_to_X12Y10N0_datab.rbf"),
    ((10, 10), (10, 11), "lits_pair_X10Y10_to_X10Y11N0_datab.rbf"),
    ((10, 10), (16,  8), "lits_pair_X10Y10_to_X16Y8N0_datab.rbf"),
    ((10, 10), (28, 21), None),  # may not exist
]


def main():
    codec = RouteCodec()
    base = ZERO.read_bytes()

    for src, dst, qfile in CASES:
        print(f"=== {src} -> {dst} ===")
        synth_rbf, _ = synth_route(base, src, dst)
        synth_cells = cells_of(codec, synth_rbf, base)
        s_summary, s_by = summarize_by_type(synth_cells)
        print(f"  synth: {dict(s_summary)}  total={len(synth_cells)}")

        if qfile is None:
            print("  (no quartus reference) skipping diff\n")
            continue
        qpath = RBF_DIR / qfile
        if not qpath.exists():
            print(f"  ✗ missing quartus reference {qfile}\n")
            continue
        q = qpath.read_bytes()
        q_cells = cells_of(codec, q, base)
        q_summary, q_by = summarize_by_type(q_cells)
        print(f"  quartus: {dict(q_summary)}  total={len(q_cells)}")

        inter = synth_cells & q_cells
        synth_only = synth_cells - q_cells
        quartus_only = q_cells - synth_cells
        print(f"  intersection: {len(inter)}")
        print(f"  synth_only:   {len(synth_only)}")
        print(f"  quartus_only: {len(quartus_only)}")

        # Top breakdown by type
        def by_type_count(s):
            d = defaultdict(int)
            for t, _, _, _ in s:
                d[t] += 1
            return dict(d)
        print(f"    inter   by type: {by_type_count(inter)}")
        print(f"    s_only  by type: {by_type_count(synth_only)}")
        print(f"    q_only  by type: {by_type_count(quartus_only)}")

        # Show 5 quartus_only LI cells (likely src-driver / packer cells we missed)
        q_only_li = [(t, n, o, b) for t, n, o, b in quartus_only if t == "li"]
        if q_only_li:
            print(f"  quartus_only LI samples (first 8):")
            for t, n, o, b in sorted(q_only_li)[:8]:
                lx, ly, p, bi = codec._parse_li_name(n)
                print(f"    {n}  → LAB({lx},{ly}) P{p}B{bi}")

        # Show 5 quartus_only C4/R4 wires
        q_only_wire = [(t, n) for t, n, _, _ in quartus_only if t in ("c4", "r4", "r24")]
        if q_only_wire:
            print(f"  quartus_only wires (first 8):")
            for t, n in sorted(set(q_only_wire))[:8]:
                print(f"    {n}")
        print()


if __name__ == "__main__":
    main()
