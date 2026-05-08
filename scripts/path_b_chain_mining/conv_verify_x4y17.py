#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""γ' convention verification probe — does sigcache key OUTROUTE_G15
"X4Y17N{n}" match a Quartus LCCOMB placement at LCCOMB_X4_Y17_N{n}
(true convention, runtime), or LCCOMB_X4_Y17_N{n//2} (sweep_outroute_nv.py
mining convention)?

Builds two minimal 1-LE designs at LAB(4,17):
  LE_6 candidate:  LCCOMB_X4_Y17_N12   (== nextpnr SLICE_X4_Y17_N12)
  LE_8 candidate:  LCCOMB_X4_Y17_N16   (== nextpnr SLICE_X4_Y17_N16)

For each, builds a (full=KEY2→LUT→G15, nop=LED0=0) pair, diffs RBFs.
Compares the resulting cell sets against sigcache "X4Y17N12" (38 cells)
and "X4Y17N16" (50 cells) entries.

Verdict:
  - If true_N12_cells overlap sigcache_N12 strongly → conv was OK for N12.
  - If true_N12_cells overlap sigcache_N16 strongly → sigcache N16 was
    actually mined at LE_6 (conv buggy: n//2 means "X4Y17N16"="LE_4" but
    our true_N16 build at LE_8 differs from sigcache).

Pure software: no flash, no sigcache mutation.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
WORK = REPO / "tmp" / "conv_verify_x4y17"
QUARTUS = Path.home() / "intelFPGA_lite" / "21.1" / "quartus" / "bin"
SIDECAR = REPO / "results" / "conv_verify_x4y17.json"


def extract_cells(a: bytes, b: bytes):
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
                cells.append((off, bp))
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
            [step, "--read_settings_files=on",
             "--write_settings_files=off", name],
            cwd=str(bdir), capture_output=True, env=env,
            timeout=180, text=True, errors="replace",
        )
        if r.returncode != 0:
            print(f"  FAIL {step} on {name}")
            print(r.stdout[-1500:] if r.stdout else r.stderr[-1500:])
            return None
    sof = bdir / "output_files" / f"{name}.sof"
    rbf = bdir / f"{name}.rbf"
    r = subprocess.run(
        [str(QUARTUS / "quartus_cpf"), "-c", "-o",
         "bitstream_compression=off", str(sof), str(rbf)],
        cwd=str(bdir), capture_output=True, env=env, timeout=60,
    )
    if r.returncode != 0:
        return None
    return rbf.read_bytes()


def grep_placement(work_dir, name, qn):
    """Inspect fit.summary or rpt for actual LCCOMB placement."""
    bdir = work_dir / name
    expect = f"LCCOMB_X4_Y17_N{qn}"
    for fn in ["fit.summary", f"{name}.fit.rpt", f"{name}.fit.summary"]:
        p = bdir / fn
        if p.exists():
            txt = p.read_text(errors="replace")
            if expect in txt:
                return True, expect
    # Fallback: scan all .rpt
    for p in bdir.glob("*.rpt"):
        txt = p.read_text(errors="replace")
        if expect in txt:
            return True, expect
    # Also scan output_files
    out = bdir / "output_files"
    if out.exists():
        for p in out.glob("*.rpt"):
            txt = p.read_text(errors="replace")
            if expect in txt:
                return True, expect
    return False, None


def probe_qn(qn: int):
    """Build full+nop pair at LCCOMB_X4_Y17_N{qn}, return (cells, ok)."""
    tag = f"qn{qn}"
    loc = f"LCCOMB_X4_Y17_N{qn}"

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

    print(f"  build full @ {loc} ...", flush=True)
    rbf_full = build(f"full_{tag}", v_full, qsf_full, WORK)
    if rbf_full is None:
        return None, False
    placed_full, _ = grep_placement(WORK, f"full_{tag}", qn)

    print(f"  build nop @ {loc} ...", flush=True)
    rbf_nop = build(f"nop_{tag}", v_nop, qsf_nop, WORK)
    if rbf_nop is None:
        return None, False
    placed_nop, _ = grep_placement(WORK, f"nop_{tag}", qn)

    cells = extract_cells(rbf_full, rbf_nop)
    return cells, (placed_full and placed_nop)


def main():
    WORK.mkdir(parents=True, exist_ok=True)
    sc = json.loads((REPO / "results" / "output_route_sigcache.json").read_text())

    sigcache_n12 = set(tuple(c) for c in sc["routes"]["X4Y17N12"]["position_specific"])
    sigcache_n16 = set(tuple(c) for c in sc["routes"]["X4Y17N16"]["position_specific"])
    sigcache_n0 = set(tuple(c) for c in sc["routes"]["X4Y17N0"]["position_specific"])
    print(f"sigcache N0={len(sigcache_n0)} N12={len(sigcache_n12)} N16={len(sigcache_n16)}")

    print("\n=== probe Q_N=12 (=== nextpnr SLICE_N12 = LE_6) ===")
    cells_n12, ok_n12 = probe_qn(12)
    if cells_n12 is None:
        print("BUILD FAIL Q_N=12"); sys.exit(1)
    cells_n12_set = set(cells_n12)
    print(f"  cells_n12: {len(cells_n12_set)}, placement_verified={ok_n12}")

    print("\n=== probe Q_N=16 (=== nextpnr SLICE_N16 = LE_8) ===")
    cells_n16, ok_n16 = probe_qn(16)
    if cells_n16 is None:
        print("BUILD FAIL Q_N=16"); sys.exit(1)
    cells_n16_set = set(cells_n16)
    print(f"  cells_n16: {len(cells_n16_set)}, placement_verified={ok_n16}")

    def rel(a, b):
        if not b: return 0.0
        return len(a & b) / len(b)

    print("\n=== overlap analysis ===")
    print(f"true_N12 (LCCOMB_N12=LE_6) vs sigcache N12 ({len(sigcache_n12)}): "
          f"{len(cells_n12_set & sigcache_n12)}/{len(sigcache_n12)} = "
          f"{rel(cells_n12_set, sigcache_n12)*100:.0f}%")
    print(f"true_N12 (LCCOMB_N12=LE_6) vs sigcache N16 ({len(sigcache_n16)}): "
          f"{len(cells_n12_set & sigcache_n16)}/{len(sigcache_n16)} = "
          f"{rel(cells_n12_set, sigcache_n16)*100:.0f}%")
    print(f"true_N12 (LCCOMB_N12=LE_6) vs sigcache N0 ({len(sigcache_n0)}): "
          f"{len(cells_n12_set & sigcache_n0)}/{len(sigcache_n0)} = "
          f"{rel(cells_n12_set, sigcache_n0)*100:.0f}%")
    print()
    print(f"true_N16 (LCCOMB_N16=LE_8) vs sigcache N16 ({len(sigcache_n16)}): "
          f"{len(cells_n16_set & sigcache_n16)}/{len(sigcache_n16)} = "
          f"{rel(cells_n16_set, sigcache_n16)*100:.0f}%")
    print(f"true_N16 (LCCOMB_N16=LE_8) vs sigcache N12 ({len(sigcache_n12)}): "
          f"{len(cells_n16_set & sigcache_n12)}/{len(sigcache_n12)} = "
          f"{rel(cells_n16_set, sigcache_n12)*100:.0f}%")
    print(f"true_N16 (LCCOMB_N16=LE_8) vs sigcache N0 ({len(sigcache_n0)}): "
          f"{len(cells_n16_set & sigcache_n0)}/{len(sigcache_n0)} = "
          f"{rel(cells_n16_set, sigcache_n0)*100:.0f}%")
    print()
    print(f"true_N12 vs true_N16 overlap: {len(cells_n12_set & cells_n16_set)}")

    out = {
        "tag": "X4Y17 OUTROUTE_G15 conv verify",
        "true_N12_cells": sorted([list(c) for c in cells_n12_set]),
        "true_N16_cells": sorted([list(c) for c in cells_n16_set]),
        "true_N12_count": len(cells_n12_set),
        "true_N16_count": len(cells_n16_set),
        "sigcache_N0_count": len(sigcache_n0),
        "sigcache_N12_count": len(sigcache_n12),
        "sigcache_N16_count": len(sigcache_n16),
        "overlap_true12_sc12": len(cells_n12_set & sigcache_n12),
        "overlap_true12_sc16": len(cells_n12_set & sigcache_n16),
        "overlap_true16_sc16": len(cells_n16_set & sigcache_n16),
        "overlap_true16_sc12": len(cells_n16_set & sigcache_n12),
        "overlap_true12_true16": len(cells_n12_set & cells_n16_set),
        "placement_n12_verified": ok_n12,
        "placement_n16_verified": ok_n16,
    }
    SIDECAR.write_text(json.dumps(out, indent=2))
    print(f"\nSidecar: {SIDECAR}")


if __name__ == "__main__":
    main()
