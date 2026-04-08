# SPDX-License-Identifier: GPL-3.0-or-later
"""Step A — purify the (10,14) and (10,10) fingerprints by removing
GND-tie noise. Use compile_route_pair (multi-input lut2) with
connect_port='datad' so all 4 lut2 inputs receive real routed signals.

Compile 5 pure routes per source, intersect for the clean fingerprint,
then compare:
  - clean fingerprint size vs raw fingerprint size
  - physical location of clean bits (do they return to source column?)
  - cross-source intersection (the holy grail)
"""
import sys, os, re
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from collections import Counter
from pathlib import Path
from runner import compile_route_pair, compile_route_baseline_abcd
from bitstream import RouteCodec

ROOT = Path(__file__).resolve().parent.parent
RBF = ROOT / 'results' / 'rbf'

# 5 short routes per source — keep simple to avoid fitter failures
SOURCES = {
    (10, 10): [(11, 10), (12, 10), (10, 11), (10, 12), (13, 10)],
    (10, 14): [(11, 14), (12, 14), (10, 16), (13, 14), (10, 11)],
}


def compile_pure(sx, sy, dx, dy):
    """Multi-input pair, datad-connect (no GND ties)."""
    tag = f"litpur_X{sx}Y{sy}_to_X{dx}Y{dy}_d"
    path = RBF / f"{tag}.rbf"
    if path.exists():
        return path, "exists"
    rbf, t, err = compile_route_pair(
        tag, sx, sy, 0, dx, dy, 0,
        mask1=0x8888, mask2=0xAAAA,  # mask doesn't matter for routing topology
    )
    return (path if rbf else None), (err or f"OK {t:.1f}s")


def compile_zero(sx, sy):
    """Pure baseline matching the 4-input shape (need a separate zero)."""
    tag = f"litpur_zero_X{sx}Y{sy}"
    path = RBF / f"{tag}.rbf"
    if path.exists():
        return path
    # Use compile_route_baseline_abcd — single LUT with abcd inputs.
    rbf, t, err = compile_route_baseline_abcd(tag, sx, sy, 0)
    return path if rbf else None


def cells_set(codec, rbf, zero):
    sw = codec.read_switches(rbf, zero)
    return {(t, e[1], e[2]) for t, lst in sw.items() for e in lst}


def main():
    codec = RouteCodec()
    fingerprints = {}

    for (sx, sy), dsts in SOURCES.items():
        print(f"\n=== ({sx},{sy}) — purifying ===")
        zpath = compile_zero(sx, sy)
        if not zpath:
            print(f"  baseline FAIL"); continue
        zero = zpath.read_bytes()

        all_cells = []
        for dx, dy in dsts:
            p, msg = compile_pure(sx, sy, dx, dy)
            if not p:
                print(f"  ({dx},{dy}) FAIL: {msg[:80]}")
                continue
            print(f"  ({dx},{dy}) {msg}")
            try:
                all_cells.append(cells_set(codec, p.read_bytes(), zero))
            except Exception as e:
                print(f"    read err: {e}")

        if len(all_cells) < 2:
            print(f"  insufficient samples ({len(all_cells)})")
            continue

        fp = set(all_cells[0])
        for s in all_cells[1:]:
            fp &= s
        fingerprints[(sx, sy)] = fp
        bt = Counter(t for t, _, _ in fp)
        print(f"  PURIFIED fingerprint: {len(fp)} cells  by_type={dict(bt)}")
        for t, off, bp in sorted(fp):
            print(f"    {t:6s} off={off:#08x} bp={bp}")

    # Cross-source intersection
    if len(fingerprints) >= 2:
        keys = list(fingerprints)
        common = set(fingerprints[keys[0]])
        for k in keys[1:]:
            common &= fingerprints[k]
        print(f"\n=== cross-source intersection ===")
        print(f"  shared bits across {keys}: {len(common)}")
        for c in sorted(common):
            print(f"    {c}")


if __name__ == "__main__":
    main()
