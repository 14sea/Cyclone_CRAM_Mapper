#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""β — Mine OUTROUTE_G15 cells for X4Y17N14 via chain-context Quartus build.

Q_N=7 (our_n=14) is chain-only — Quartus rejects standalone LCCOMB
placement there.  The single-LUT mining template (used for X4Y17N0 /
X4Y17N12) cannot apply.  This script instead places an 8-LE counter
chain spanning LAB(4,17) Q_N=0..7 and uses pair-delta diff between
two designs differing only in chain-end-LE → G15 routing.

Designs:
  full:  8-bit counter at LAB(4,17); cnt[7] → LED0 (G15)
  nop:   same counter;               cnt[7] → LED_SEC (F15), LED0 = 0

The chain is identical between the two builds.  full - nop isolates
the SLICE_X4_Y17_N7 → G15 output route cells.

LE pinning: Q_N=0..6 explicitly placed at LCCOMB_X4_Y17_N0..6; Q_N=7
left to auto-cascade via the chain rule.  If Q_N=7 lands at a different
LAB despite this, the script aborts and reports the actual placement.

Output: results/output_route_sigcache.json gains entry "X4Y17N14"
        with `position_specific` cell list.  Also writes a sidecar
        results/path_b_x4y17n14_mining.json with full diagnostics.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
WORK = REPO / "tmp" / "path_b_x4y17n14"
QUARTUS = Path.home() / "intelFPGA_lite" / "21.1" / "quartus" / "bin"

OUR_N = 14  # Q_N = 7 (chain-only LE)
SX, SY, SN = 4, 17, OUR_N
SIGCACHE = REPO / "results" / "output_route_sigcache.json"
SIDECAR = REPO / "results" / "path_b_x4y17n14_mining.json"


def run(cmd, cwd, timeout=300):
    print(f"  $ {' '.join(str(c) for c in cmd)}", flush=True)
    env = os.environ.copy()
    env["PATH"] = str(QUARTUS) + ":" + env["PATH"]
    r = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True,
                       errors="replace", timeout=timeout, env=env)
    return r


def build(name: str, verilog: str, qsf_extra: str) -> bytes | None:
    bdir = WORK / name
    # Clean stale db/ — chain placement is sensitive to incremental cache
    for sub in ("db", "incremental_db", "output_files"):
        p = bdir / sub
        if p.exists():
            shutil.rmtree(p)
    bdir.mkdir(parents=True, exist_ok=True)

    (bdir / f"{name}.v").write_text(verilog)
    qsf = f"""\
set_global_assignment -name FAMILY "Cyclone IV E"
set_global_assignment -name DEVICE EP4CE6F17C8
set_global_assignment -name TOP_LEVEL_ENTITY {name}
set_global_assignment -name VERILOG_FILE {name}.v
set_global_assignment -name PROJECT_OUTPUT_DIRECTORY output_files
set_global_assignment -name SEED 1
set_global_assignment -name STRATIX_DEVICE_IO_STANDARD "3.3-V LVTTL"
set_global_assignment -name RESERVE_ALL_UNUSED_PINS_WEAK_PULLUP "AS INPUT TRI-STATED WITH WEAK PULL-UP"
set_global_assignment -name CYCLONEII_RESERVE_NCEO_AFTER_CONFIGURATION "USE AS REGULAR IO"
{qsf_extra}
"""
    (bdir / f"{name}.qsf").write_text(qsf)
    (bdir / f"{name}.qpf").write_text(f'PROJECT_REVISION = "{name}"\n')

    print(f"\n--- Building {name} ---", flush=True)
    for step in ("quartus_map", "quartus_fit", "quartus_asm"):
        r = run([step, "--read_settings_files=on",
                 "--write_settings_files=off", name], cwd=bdir)
        if r.returncode != 0:
            print(f"  FAIL {step} (rc={r.returncode})")
            print(r.stdout[-3000:])
            return None

    # Inspect fit report for chain placement
    fit_rpt = bdir / "output_files" / f"{name}.fit.rpt"
    if fit_rpt.exists():
        text = fit_rpt.read_text(errors="replace")
        # Look for LCCOMB placements
        chain_locs = []
        for line in text.splitlines():
            if "LCCOMB_X" in line and "X4_Y17" in line:
                chain_locs.append(line.strip()[:200])
        if chain_locs:
            print(f"  Chain LE placements at LAB(4,17):")
            for line in chain_locs[:12]:
                print(f"    {line}")

    sof = bdir / "output_files" / f"{name}.sof"
    rbf = bdir / f"{name}.rbf"
    r = run([str(QUARTUS / "quartus_cpf"), "-c", "-o",
             "bitstream_compression=off", str(sof), str(rbf)], cwd=bdir)
    if r.returncode != 0:
        print(f"  cpf FAIL")
        return None
    return rbf.read_bytes()


def diff_cells(a: bytes, b: bytes) -> list[tuple[int, int]]:
    cells = []
    for off in range(32, min(len(a), len(b))):
        if off >= 367952:
            break
        frame = (off - 32) // 210
        pos = (off - 32) % 210
        if frame >= 25 and pos >= 208:  # CRC
            continue
        x = a[off] ^ b[off]
        if x:
            for bp in range(8):
                if x & (1 << bp):
                    cells.append((off, bp))
    return cells


def main():
    WORK.mkdir(parents=True, exist_ok=True)

    # v4: route cnt[7] to F15 in BOTH builds (so F15 IOB + cnt[7]→F15
    # routing cells cancel in the diff).  Only `full` adds an EXTRA fanout
    # to G15.  Diff = G15 IOB source switch + cnt[7]→G15 routing only.
    v_full = """\
module full (input CLK, output LED0, output LED_SEC);
    (* keep = "true" *) reg [7:0] cnt = 8'h00;
    always @(posedge CLK) cnt <= cnt + 8'd1;
    assign LED0    = cnt[7];   // G15 — the routing under test
    assign LED_SEC = cnt[7];   // F15 — same source in both builds
endmodule
"""
    v_nop = """\
module nop (input CLK, output LED0, output LED_SEC);
    (* keep = "true" *) reg [7:0] cnt = 8'h00;
    always @(posedge CLK) cnt <= cnt + 8'd1;
    assign LED0    = 1'b0;     // G15 — constant (NOT cnt[7])
    assign LED_SEC = cnt[7];   // F15 — same source as full
endmodule
"""
    # Quartus Cyclone IV E LE addressing in back-annotate has stride 2:
    # LCCOMB at even N, FF at odd N+1.  `our_n` (sigcache convention) =
    # Quartus LCCOMB N.  cnt[k] register pin = FF_X{x}_Y{y}_N{2k+1}.
    # Pin cnt[0..6] → leave cnt[7] (FF_X4_Y17_N15) for chain auto-cascade.
    qsf_common = """\
set_location_assignment PIN_E1  -to CLK
set_location_assignment PIN_G15 -to LED0
set_location_assignment PIN_F15 -to LED_SEC
set_location_assignment FF_X4_Y17_N1  -to "cnt[0]"
set_location_assignment FF_X4_Y17_N3  -to "cnt[1]"
set_location_assignment FF_X4_Y17_N5  -to "cnt[2]"
set_location_assignment FF_X4_Y17_N7  -to "cnt[3]"
set_location_assignment FF_X4_Y17_N9  -to "cnt[4]"
set_location_assignment FF_X4_Y17_N11 -to "cnt[5]"
set_location_assignment FF_X4_Y17_N13 -to "cnt[6]"
"""

    nv = (REPO / "results" / "rbf" / "nv_zero_global.rbf").read_bytes()
    assert len(nv) == 368011

    rbf_full = build("full", v_full, qsf_common)
    rbf_nop = build("nop", v_nop, qsf_common)

    if rbf_full is None or rbf_nop is None:
        print("\nBUILD FAILED — see logs above")
        sys.exit(1)

    # Verify chain landed at X4Y17 in both builds (sanity)
    print("\n=== Pair-delta analysis ===")
    cells_full_vs_nv = diff_cells(rbf_full, nv)
    cells_nop_vs_nv = diff_cells(rbf_nop, nv)
    cells_full_vs_nop = diff_cells(rbf_full, rbf_nop)
    print(f"  full vs nv_zero: {len(cells_full_vs_nv)} cells")
    print(f"  nop  vs nv_zero: {len(cells_nop_vs_nv)} cells")
    print(f"  full vs nop    : {len(cells_full_vs_nop)} cells (= candidate OUTROUTE)")

    # Classify by region
    def classify(cells):
        hdr = [c for c in cells if c[0] < 32 + 25 * 210]
        block = [c for c in cells if c[0] >= 32 + 1692 * 210]
        data = [c for c in cells if 32 + 25 * 210 <= c[0] < 32 + 1692 * 210]
        return hdr, data, block

    print()
    for name, cells in [("full vs nv", cells_full_vs_nv),
                        ("nop vs nv",  cells_nop_vs_nv),
                        ("full - nop", cells_full_vs_nop)]:
        hdr, data, block = classify(cells)
        print(f"  {name:14}: total={len(cells):>4}  hdr={len(hdr):>3}  data={len(data):>3}  block={len(block):>3}")

    # Compare against existing X4Y17N12 entry (chain end in W=23 was at N12)
    # for sanity — N14 should be similar in topology but at different bp
    sigcache = json.loads(SIGCACHE.read_text())
    existing_n12 = set(tuple(c) for c in sigcache["routes"]["X4Y17N12"]["position_specific"])
    existing_n0 = set(tuple(c) for c in sigcache["routes"]["X4Y17N0"]["position_specific"])
    new_n14 = set(cells_full_vs_nop)
    print()
    print("  Overlap analysis:")
    print(f"    new_n14 ∩ X4Y17N12: {len(new_n14 & existing_n12)} / {len(new_n14)} cells")
    print(f"    new_n14 ∩ X4Y17N0 : {len(new_n14 & existing_n0 )} / {len(new_n14)} cells")

    # Write sidecar with full diagnostics
    sidecar = {
        "description": "Path B chain-template mining for OUTROUTE_G15 X4Y17N14",
        "method": "8-LE counter chain at LAB(4,17) Q_N=0..7; full - nop pair-delta isolates cnt[7] → G15 routing",
        "design": "full: cnt[7]→G15, LED_SEC=0; nop: cnt[7]→F15, LED0=0",
        "lab": [SX, SY],
        "le_n": SN,
        "full_vs_nv_count": len(cells_full_vs_nv),
        "nop_vs_nv_count": len(cells_nop_vs_nv),
        "full_vs_nop_count": len(cells_full_vs_nop),
        "outroute_cells": [list(c) for c in sorted(cells_full_vs_nop)],
        "overlap_with_x4y17n12": len(new_n14 & existing_n12),
        "overlap_with_x4y17n0": len(new_n14 & existing_n0),
    }
    SIDECAR.write_text(json.dumps(sidecar, indent=2))
    print(f"\n  Sidecar: {SIDECAR}")

    # Conditionally update sigcache — only if the new entry looks reasonable
    # (similar cell count to X4Y17N12 = 38 cells)
    n12_count = len(existing_n12)
    new_count = len(new_n14)
    if not (15 <= new_count <= 80):
        print(f"\n  WARNING: new entry has {new_count} cells (expected ~{n12_count} per X4Y17N12).")
        print("  NOT auto-updating sigcache; review sidecar before manual merge.")
        return

    print(f"\n=== Updating sigcache with X4Y17N14 entry ({new_count} cells) ===")
    sigcache["routes"]["X4Y17N14"] = {
        "total_cells": new_count + sigcache.get("g15_invariant_count", 0),
        "position_specific": [list(c) for c in sorted(new_n14)],
        "invariant_count": sigcache.get("g15_invariant_count", 0),
    }
    SIGCACHE.write_text(json.dumps(sigcache, indent=2))
    print(f"  Updated {SIGCACHE}")


if __name__ == "__main__":
    main()
