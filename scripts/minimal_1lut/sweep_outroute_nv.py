#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Output routing sweep: mine SLICE→G15 route cells at many positions.

For each target (x, y, n), builds two Quartus designs:
  full: E16+M16 → LUT(AND) @ LOC → G15
  nop:  E16+M16 → LUT(AND) @ LOC → LED=0 (no output route)

The pair delta (full ^ nop) isolates output routing + G15 activation cells.
Position-invariant cells (G15 activation) are extracted by intersection.

Uses the same extract_cells as mine_outroute_nv.py but corrected to include
header frame positions 208-209 (data, not CRC, for frames 0-24).

Output: results/output_route_sigcache.json
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
WORK = REPO / "tmp" / "sweep_outroute"
QUARTUS = Path.home() / "intelFPGA_lite" / "21.1" / "quartus" / "bin"

sys.path.insert(0, str(REPO / "fuzz"))

POSITIONS = [
    # Green-zone islands, well-covered fb8 groups
    (4, 4, 0), (4, 4, 8), (4, 4, 16),
    (10, 4, 0), (10, 4, 8), (10, 4, 16),
    (10, 10, 0), (10, 10, 8), (10, 10, 16),
    (10, 14, 0), (10, 14, 8),
    (13, 10, 0), (13, 10, 8),
    (16, 4, 0), (16, 4, 8), (16, 4, 16),
    (16, 8, 0), (16, 14, 0),
    (19, 14, 0), (19, 14, 8),
    (22, 12, 0), (22, 12, 8),
    (25, 6, 0), (25, 6, 8),
    (28, 10, 0), (28, 10, 8),
    (28, 18, 0),
    (31, 12, 0), (31, 12, 8),
    # Boundary Y values
    (4, 2, 0), (4, 21, 0),
    (16, 2, 0), (16, 21, 0),
]


def extract_cells(a: bytes, b: bytes) -> list[list[int]]:
    """Extract differing CRAM cells, including header pos 208-209."""
    cells = []
    for off in range(32, min(len(a), len(b))):
        if off >= 367952:
            break
        frame = (off - 32) // 210
        pos = (off - 32) % 210
        # Only skip CRC positions for data frames (25+)
        if frame >= 25 and pos >= 208:
            continue
        xor = a[off] ^ b[off]
        for bp in range(8):
            if xor & (1 << bp):
                cells.append([off, bp])
    return cells


def build_design(name, verilog, qsf_text, work_dir):
    bdir = work_dir / name
    bdir.mkdir(parents=True, exist_ok=True)

    (bdir / f"{name}.v").write_text(verilog)
    (bdir / f"{name}.qsf").write_text(qsf_text)
    (bdir / f"{name}.qpf").write_text(f'PROJECT_REVISION = "{name}"\n')

    env = os.environ.copy()
    env["PATH"] = str(QUARTUS) + ":" + env["PATH"]

    for step in ["quartus_map", "quartus_fit", "quartus_asm"]:
        r = subprocess.run(
            [step, "--read_settings_files=on", "--write_settings_files=off", name],
            cwd=str(bdir), capture_output=True, env=env, timeout=180, text=True,
            errors="replace",
        )
        if r.returncode != 0:
            return None, f"{step} failed"

    sof = bdir / "output_files" / f"{name}.sof"
    rbf = bdir / f"{name}.rbf"
    r = subprocess.run(
        [str(QUARTUS / "quartus_cpf"), "-c", "-o", "bitstream_compression=off",
         str(sof), str(rbf)],
        cwd=str(bdir), capture_output=True, env=env, timeout=60,
    )
    if r.returncode != 0:
        return None, "cpf failed"
    return rbf.read_bytes(), "OK"


def mine_position(x, y, n):
    """Mine output route cells at one position. Returns (cells, error_msg).

    Convention (FIXED 2026-05-08; see scripts/path_b_chain_mining/conv_verify_x4y17.py
    + memo conv_bug_discovery_2026_05_08): tag `n` = chipdb SLICE_N =
    Quartus LCCOMB N = 2 × LE_index, all in {0,2,...,30}.  Place LCCOMB
    at LCCOMB_X{x}_Y{y}_N{n} directly — no //2.  Old version used `n // 2`
    which placed at the wrong LE (e.g., tag X4Y17N16 at LCCOMB_N8 = LE_4
    instead of LE_8).  Existing X4Y17N0 entry happens to be correct (tag
    n=0 → //2 = 0), but X4Y17N16 was wrong and was re-mined at LE_8.
    """
    loc = f"LCCOMB_X{x}_Y{y}_N{n}"
    our_n = n

    qsf_common = f"""\
set_global_assignment -name FAMILY "Cyclone IV E"
set_global_assignment -name DEVICE EP4CE6F17C8
set_global_assignment -name PROJECT_OUTPUT_DIRECTORY output_files
set_global_assignment -name SEED 1
set_global_assignment -name STRATIX_DEVICE_IO_STANDARD "3.3-V LVTTL"
set_global_assignment -name RESERVE_ALL_UNUSED_PINS_WEAK_PULLUP "AS INPUT TRI-STATED WITH WEAK PULL-UP"
set_global_assignment -name CYCLONEII_RESERVE_NCEO_AFTER_CONFIGURATION "USE AS REGULAR IO"
set_location_assignment PIN_E16 -to KEY2
set_location_assignment PIN_M16 -to KEY3
set_location_assignment PIN_G15 -to LED0
"""

    tag = f"X{x}Y{y}N{our_n}"
    sub = WORK / tag

    # Full design: inputs → LUT → output
    v_full = f"""\
module full_{tag} (input KEY2, input KEY3, output LED0);
    wire lut_out /* synthesis keep */;
    assign lut_out = KEY2 & KEY3;
    assign LED0 = lut_out;
endmodule
"""
    qsf_full = qsf_common + f"""\
set_global_assignment -name TOP_LEVEL_ENTITY full_{tag}
set_global_assignment -name VERILOG_FILE full_{tag}.v
set_location_assignment {loc} -to "lut_out"
"""

    # Nop design: inputs → LUT, output=0 (no output route)
    v_nop = f"""\
module nop_{tag} (input KEY2, input KEY3, output LED0);
    wire lut_out /* synthesis keep */;
    assign lut_out = KEY2 & KEY3;
    assign LED0 = 1'b0;
endmodule
"""
    qsf_nop = qsf_common + f"""\
set_global_assignment -name TOP_LEVEL_ENTITY nop_{tag}
set_global_assignment -name VERILOG_FILE nop_{tag}.v
set_location_assignment {loc} -to "lut_out"
"""

    rbf_full, msg = build_design(f"full_{tag}", v_full, qsf_full, sub)
    if rbf_full is None:
        return x, y, our_n, None, msg

    rbf_nop, msg = build_design(f"nop_{tag}", v_nop, qsf_nop, sub)
    if rbf_nop is None:
        return x, y, our_n, None, msg

    cells = extract_cells(rbf_full, rbf_nop)
    return x, y, our_n, cells, "OK"


def main():
    WORK.mkdir(parents=True, exist_ok=True)

    nv = (REPO / "results" / "rbf" / "nv_zero_global.rbf").read_bytes()
    assert len(nv) == 368011

    total = len(POSITIONS)
    print(f"Output routing sweep: {total} positions, 2 compiles each")
    print(f"Estimated: ~{total * 2 * 30 / 60:.0f} min (sequential) or "
          f"~{total * 2 * 30 / 60 / 4:.0f} min (4-way parallel)")

    # Mine all positions
    results = {}
    t0 = time.time()
    done = 0
    errors = 0

    with ProcessPoolExecutor(max_workers=4) as pool:
        futures = {pool.submit(mine_position, x, y, n): (x, y, n)
                   for x, y, n in POSITIONS}
        for fut in as_completed(futures):
            x, y, n, cells, msg = fut.result()
            done += 1
            if cells is None:
                print(f"  [{done}/{total}] X{x}Y{y}N{n}: FAIL ({msg})")
                errors += 1
            else:
                results[(x, y, n)] = cells
                elapsed = time.time() - t0
                print(f"  [{done}/{total}] X{x}Y{y}N{n}: {len(cells)} cells "
                      f"({elapsed:.0f}s)")

    elapsed = time.time() - t0
    print(f"\nMining done: {done - errors}/{total} OK in {elapsed:.0f}s")

    if len(results) < 2:
        print("Too few results to analyze")
        return

    # Find position-invariant cells (intersection of ALL position deltas)
    all_sets = [set(tuple(c) for c in cells) for cells in results.values()]
    invariant = all_sets[0]
    for s in all_sets[1:]:
        invariant &= s

    print(f"\n--- Analysis ---")
    print(f"Position-invariant cells (G15 activation): {len(invariant)}")

    # Position-specific cells
    sigcache = {}
    for (x, y, n), cells in sorted(results.items()):
        cell_set = set(tuple(c) for c in cells)
        specific = cell_set - invariant
        sigcache[f"X{x}Y{y}N{n}"] = {
            "total_cells": len(cells),
            "position_specific": sorted(list(specific)),
            "invariant_count": len(invariant),
        }
        print(f"  X{x}Y{y}N{n}: {len(cells)} total, "
              f"{len(specific)} specific, {len(invariant)} invariant")

    # Save
    output = {
        "description": "SLICE→G15 output route sig-cache",
        "mining_date": "2026-04-21",
        "pins": {"in": ["E16", "M16"], "out": "G15"},
        "g15_invariant_cells": sorted(list(invariant)),
        "g15_invariant_count": len(invariant),
        "routes": sigcache,
    }
    out_path = REPO / "results" / "output_route_sigcache.json"
    out_path.write_text(json.dumps(output, indent=2))
    print(f"\nSaved to {out_path}")

    # Verify consistency with prior mining
    prior = REPO / "results" / "output_route_nv_mining.json"
    if prior.exists():
        p = json.loads(prior.read_text())
        prior_g15 = set(tuple(c) for c in p["g15_output_activate"])
        if prior_g15 == invariant:
            print("G15 invariant cells: MATCH prior mining (11 cells)")
        else:
            print(f"G15 invariant cells: MISMATCH! prior={len(prior_g15)} "
                  f"new={len(invariant)}")
            print(f"  Missing from new: {prior_g15 - invariant}")
            print(f"  Extra in new: {invariant - prior_g15}")


if __name__ == "__main__":
    main()
