#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Single-edge sig-cache mining: X=4 cross-LAB R4 routes.

Background — memory `d_i_silicon_failed_2026_05_04`: led_blink_open W=24
flash REJECTED on AX301 because the cross-LAB ROUTE
`X4Y17N14 -> X4Y4N16.dataa` had no sig-cache entry, fell through to the
parse_need formula path, which emitted cells at structurally wrong CRAM
offsets → bitstream rejected by FPGA config controller.

This tool reproduces the Plan D' factory pattern (plan_d_prime_factory.py
+ nv_global_baseline_extract.py + nv_sig_cache_merge.py) for a single
edge, sized for one-off mining of routes that are needed but unmined.

Pipeline:
  1. Compile a single-input clocked pair via Quartus CE10:
       lut1 at src LCCOMB, lut2 at dst LCCOMB, single input from lut1
       to lut2's specified port (dataa/datab/datac/datad).
  2. Diff resulting `nv_pair_X<sx>Y<sy>N<sn>_to_X<dx>Y<dy>N<dn>_<port>.rbf`
     against `nv_zero_global.rbf` (the existing baseline, lut1 and lut2
     parked at LCCOMB_X10_Y10_N0 + LCCOMB_X10_Y11_N0 with TT=0x0000).
  3. Result cells = src LUT TT + dst LUT TT + routing + LE infra delta.
     fasm2rbf handles LUT-bit dedup via the existing _iob_route_dedup
     mechanism (verified by the 34 existing X=4 cross-LAB sig-cache
     entries that work correctly today).
  4. Inject into `results/route_cells_full.json` as a new entry
     keyed `<sx>,<sy>,<sn>-><dx>,<dy>,<dn>,<port>`.

Usage:
  python3 scripts/sigcache_remine/mine_x4_cross_lab_route.py \\
      --src 4,17,14 --dst 4,4,16 --port dataa
  python3 scripts/sigcache_remine/mine_x4_cross_lab_route.py \\
      --src 4,17,14 --dst 4,4,16 --port dataa --dry-run

The script is RESUMABLE: if the nv_pair RBF already exists, it skips
Quartus and goes straight to diff + inject.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "fuzz"))

from plan_d_prime_factory import compile_edge  # noqa: E402

NV_ZERO_GLOBAL = REPO / "results" / "rbf" / "nv_zero_global.rbf"
ROUTE_CELLS_FULL = REPO / "results" / "route_cells_full.json"
NV_ROUTE_CELLS = REPO / "results" / "nv_route_cells.json"
RBF_DIR = REPO / "results" / "rbf"


def parse_xyn(arg: str) -> tuple[int, int, int]:
    parts = arg.split(",")
    if len(parts) != 3:
        raise SystemExit(f"--src/--dst expects X,Y,N — got {arg!r}")
    return tuple(int(p) for p in parts)


def diff_cells(pair_rbf: bytes, base_rbf: bytes) -> list[tuple[int, int]]:
    """Cell-level XOR diff in the CRAM data region (frames 25..1751,
    bytes 0..207, skipping the 32-byte preamble + 2-byte CRC suffix
    per frame).  Same selector used by nv_global_baseline_extract.py
    for consistency with the factory."""
    cells = []
    for f in range(25, 1752):
        s = 32 + f * 210
        for off in range(s, s + 208):
            x = pair_rbf[off] ^ base_rbf[off]
            if not x:
                continue
            for bp in range(8):
                if (x >> bp) & 1:
                    cells.append((off, bp))
    return cells


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--src", required=True,
                    help="source X,Y,N (e.g. 4,17,14)")
    ap.add_argument("--dst", required=True,
                    help="destination X,Y,N (e.g. 4,4,16)")
    ap.add_argument("--port", required=True,
                    choices=["dataa", "datab", "datac", "datad"],
                    help="destination LUT input port")
    ap.add_argument("--dry-run", action="store_true",
                    help="don't write to route_cells_full.json")
    args = ap.parse_args()

    sx, sy, sn = parse_xyn(args.src)
    dx, dy, dn = parse_xyn(args.dst)
    port = args.port

    # Normalize: factory maps odd N → N-1 (FF in same LE → LCCOMB).
    if sn % 2:
        print(f"  src N={sn} odd → normalizing to {sn-1}")
        sn -= 1
    if dn % 2:
        print(f"  dst N={dn} odd → normalizing to {dn-1}")
        dn -= 1

    edge = (sx, sy, sn, "LCCOMB", dx, dy, dn, port)
    tag = f"nv_pair_X{sx}Y{sy}N{sn}_to_X{dx}Y{dy}N{dn}_{port}"
    pair_rbf_path = RBF_DIR / f"{tag}.rbf"
    key = f"{sx},{sy},{sn}->{dx},{dy},{dn},{port}"

    print(f"\n=== single-edge sig-cache mining ===")
    print(f"  edge: {edge}")
    print(f"  tag: {tag}")
    print(f"  key: {key!r}")

    # Step 1: compile if pair RBF doesn't exist
    if pair_rbf_path.exists() and pair_rbf_path.stat().st_size == 368011:
        print(f"  [skip Quartus] pair RBF already on disk: "
              f"{pair_rbf_path.relative_to(REPO)}")
    else:
        print(f"  [compile via Quartus CE10]")
        os.environ.setdefault("PATH",
                              f"{os.environ.get('PATH', '')}:"
                              f"{os.path.expanduser('~/intelFPGA_lite/21.1/quartus/bin')}")
        result = compile_edge(edge)
        if not result.get("ok"):
            print(f"  COMPILE FAILED:\n  {result.get('err', 'unknown')}")
            sys.exit(1)
        print(f"  compiled in {result.get('elapsed', 0):.1f}s")

    if not pair_rbf_path.exists():
        print(f"  ERROR: expected RBF missing: {pair_rbf_path}")
        sys.exit(1)
    if pair_rbf_path.stat().st_size != 368011:
        print(f"  ERROR: RBF wrong size: {pair_rbf_path.stat().st_size}")
        sys.exit(1)

    # Step 2: diff vs nv_zero_global
    pair_b = pair_rbf_path.read_bytes()
    base_b = NV_ZERO_GLOBAL.read_bytes()
    cells = diff_cells(pair_b, base_b)
    print(f"  diff vs nv_zero_global: {len(cells)} cells")
    if not cells:
        print(f"  WARN: 0 cells in diff — Quartus may have placed "
              f"differently than requested.  Check {pair_rbf_path.name}.")
        sys.exit(2)

    # Step 3: inject into route_cells_full.json
    if args.dry_run:
        print(f"  [dry-run] would write key {key!r} with {len(cells)} cells")
        # Still print a sample
        print(f"  sample cells: {cells[:5]}")
        return

    cells_sorted = sorted(set((o, b) for o, b in cells))

    # Write to nv_route_cells.json (the canonical source for the
    # nv_sig_cache_merge.py pipeline).  This is the entry that survives
    # future re-runs of the merger.
    if NV_ROUTE_CELLS.exists():
        nv_sigs = json.loads(NV_ROUTE_CELLS.read_text())
    else:
        nv_sigs = {}
    if key in nv_sigs:
        print(f"  WARN: nv_route_cells.json already has key {key!r} "
              f"({len(nv_sigs[key])} cells) — overwriting.")
    nv_sigs[key] = [list(c) for c in cells_sorted]
    tmp = NV_ROUTE_CELLS.with_suffix(NV_ROUTE_CELLS.suffix + ".tmp")
    tmp.write_text(json.dumps(nv_sigs))
    os.replace(tmp, NV_ROUTE_CELLS)
    print(f"  wrote → {NV_ROUTE_CELLS.relative_to(REPO)} "
          f"(now {len(nv_sigs)} entries)")

    # Also patch route_cells_full.json directly so the entry takes effect
    # immediately without requiring a full nv_sig_cache_merge.py run.
    # The merger, when next invoked, will reproduce this same entry from
    # nv_route_cells.json above.
    sigcache = json.loads(ROUTE_CELLS_FULL.read_text())
    if key in sigcache:
        existing = sigcache[key]
        print(f"  WARN: route_cells_full.json already has key {key!r} "
              f"({len(existing)} cells) — overwriting.")
    sigcache[key] = cells_sorted
    tmp = ROUTE_CELLS_FULL.with_suffix(ROUTE_CELLS_FULL.suffix + ".tmp")
    tmp.write_text(json.dumps(sigcache))
    os.replace(tmp, ROUTE_CELLS_FULL)
    print(f"  wrote → {ROUTE_CELLS_FULL.relative_to(REPO)} "
          f"(now {len(sigcache)} entries)")


if __name__ == "__main__":
    main()
