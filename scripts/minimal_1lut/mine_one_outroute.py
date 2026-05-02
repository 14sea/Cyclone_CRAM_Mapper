#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Mine OUTROUTE_G15 cells at a single new (X, Y, N) position.

Adapted from sweep_outroute_nv.py for one-shot extension of
results/output_route_sigcache.json.  Supplies a (full, nop) pair at
the target SLICE and computes position_specific = (full_delta_vs_nop)
- g15_invariant_cells.

Usage:
    python3 scripts/minimal_1lut/mine_one_outroute.py X Y our_N

Examples:
    python3 scripts/minimal_1lut/mine_one_outroute.py 4 17 14
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
WORK = REPO / "tmp" / "mine_one_outroute"
QUARTUS = Path.home() / "intelFPGA_lite" / "21.1" / "quartus" / "bin"


def extract_cells(a: bytes, b: bytes) -> list[list[int]]:
    cells = []
    for off in range(32, min(len(a), len(b))):
        if off >= 367952:
            break
        frame = (off - 32) // 210
        pos = (off - 32) % 210
        if frame >= 25 and pos >= 208:
            continue
        xor = a[off] ^ b[off]
        for bp in range(8):
            if xor & (1 << bp):
                cells.append([off, bp])
    return cells


def build(name, verilog, qsf, work_dir):
    bdir = work_dir / name
    bdir.mkdir(parents=True, exist_ok=True)
    (bdir / f"{name}.v").write_text(verilog)
    (bdir / f"{name}.qsf").write_text(qsf)
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
            print(f"FAIL {step} on {name}:")
            if r.stdout:
                print(r.stdout[-2000:])
            if r.stderr:
                print(r.stderr[-2000:])
            return None
    sof = bdir / "output_files" / f"{name}.sof"
    rbf = bdir / f"{name}.rbf"
    r = subprocess.run(
        [str(QUARTUS / "quartus_cpf"), "-c", "-o", "bitstream_compression=off",
         str(sof), str(rbf)],
        cwd=str(bdir), capture_output=True, env=env, timeout=60,
    )
    if r.returncode != 0:
        return None
    return rbf.read_bytes()


def main():
    if len(sys.argv) != 4:
        print("Usage: mine_one_outroute.py X Y our_N")
        sys.exit(1)
    x, y, our_n = int(sys.argv[1]), int(sys.argv[2]), int(sys.argv[3])
    quartus_n = our_n // 2
    loc = f"LCCOMB_X{x}_Y{y}_N{quartus_n}"
    tag = f"X{x}Y{y}N{our_n}"
    print(f"Mining OUTROUTE_G15 at {tag} (Quartus loc: {loc})")

    WORK.mkdir(parents=True, exist_ok=True)

    qsf_common = """\
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
    v_full = f"""\
module full_{tag} (input KEY2, input KEY3, output LED0);
    wire lut_out /* synthesis keep */;
    assign lut_out = KEY2 & KEY3;
    assign LED0 = lut_out;
endmodule
"""
    qsf_full = qsf_common + (
        f'set_global_assignment -name TOP_LEVEL_ENTITY full_{tag}\n'
        f'set_global_assignment -name VERILOG_FILE full_{tag}.v\n'
        f'set_location_assignment {loc} -to "lut_out"\n'
    )
    v_nop = f"""\
module nop_{tag} (input KEY2, input KEY3, output LED0);
    wire lut_out /* synthesis keep */;
    assign lut_out = KEY2 & KEY3;
    assign LED0 = 1'b0;
endmodule
"""
    qsf_nop = qsf_common + (
        f'set_global_assignment -name TOP_LEVEL_ENTITY nop_{tag}\n'
        f'set_global_assignment -name VERILOG_FILE nop_{tag}.v\n'
        f'set_location_assignment {loc} -to "lut_out"\n'
    )

    print("Building full design...")
    rbf_full = build(f"full_{tag}", v_full, qsf_full, WORK)
    if rbf_full is None:
        print("BUILD FAILED — full")
        sys.exit(1)
    print("Building nop design...")
    rbf_nop = build(f"nop_{tag}", v_nop, qsf_nop, WORK)
    if rbf_nop is None:
        print("BUILD FAILED — nop")
        sys.exit(1)

    cells = extract_cells(rbf_full, rbf_nop)
    print(f"\nfull XOR nop: {len(cells)} cells")

    # Load existing sigcache, compute position_specific
    sc_path = REPO / "results" / "output_route_sigcache.json"
    sc = json.loads(sc_path.read_text())
    invariant = set(tuple(c) for c in sc["g15_invariant_cells"])
    cell_set = set(tuple(c) for c in cells)
    specific = cell_set - invariant
    invariant_in_cells = cell_set & invariant
    print(f"  invariant ⊆ cells: {len(invariant_in_cells)}/{len(invariant)}")
    print(f"  position_specific: {len(specific)}")
    if len(invariant_in_cells) != len(invariant):
        print(f"  ⚠ MISSING invariant cells: {invariant - cell_set}")

    new_entry = {
        "total_cells": len(cells),
        "position_specific": sorted(list(specific)),
        "invariant_count": len(invariant),
    }
    sc["routes"][tag] = new_entry
    sc_path.write_text(json.dumps(sc, indent=2))
    print(f"\nAppended {tag} → {sc_path}")

    # Diagnostic: classify cells by frame band
    def band(off):
        if off < 32: return "preamble"
        rel = off - 32
        fr = rel // 210
        if fr < 25: return "header"
        if 1692 <= fr <= 1738: return "block_band"
        return "lab_cram"
    from collections import Counter
    c = Counter()
    for off, bp in specific:
        c[band(off)] += 1
    print(f"position_specific by band: {dict(c)}")


if __name__ == "__main__":
    main()
