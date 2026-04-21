#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Mine second position (X10Y10N0) for cross-position decomposition.

Same pin combo (E16+M16→G15) but different LUT placement.
Compare with X16Y4N0 to separate:
  - Position-invariant cells (IOB pad config)
  - Position-specific cells (routing from LUT to pin)
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
WORK = REPO / "tmp" / "mine_outroute_nv_x10y10"
QUARTUS = Path.home() / "intelFPGA_lite" / "21.1" / "quartus" / "bin"

sys.path.insert(0, str(REPO / "fuzz"))

LOC_X, LOC_Y, LOC_N = 10, 10, 0
QUARTUS_LOC = f"LCCOMB_X{LOC_X}_Y{LOC_Y}_N{LOC_N}"
OUR_N = LOC_N * 2


def run(cmd, cwd=None):
    print(f"  $ {' '.join(str(c) for c in cmd)}", flush=True)
    r = subprocess.run(cmd, cwd=str(cwd) if cwd else None,
                       capture_output=True, text=True, errors="replace",
                       timeout=300)
    if r.returncode != 0:
        print(f"FAIL (rc={r.returncode})")
        if r.stdout:
            print(r.stdout[-3000:])
        if r.stderr:
            print(r.stderr[-3000:])
        sys.exit(1)
    return r


def build(name, verilog, qsf_extra):
    bdir = WORK / name
    bdir.mkdir(parents=True, exist_ok=True)
    vf = bdir / f"{name}.v"
    vf.write_text(verilog)
    qsf = bdir / f"{name}.qsf"
    qsf.write_text(f"""
set_global_assignment -name FAMILY "Cyclone IV E"
set_global_assignment -name DEVICE EP4CE6F17C8
set_global_assignment -name TOP_LEVEL_ENTITY {name}
set_global_assignment -name VERILOG_FILE {vf}
set_global_assignment -name PROJECT_OUTPUT_DIRECTORY output_files
set_global_assignment -name SEED 1
set_global_assignment -name STRATIX_DEVICE_IO_STANDARD "3.3-V LVTTL"
set_global_assignment -name RESERVE_ALL_UNUSED_PINS_WEAK_PULLUP "AS INPUT TRI-STATED WITH WEAK PULL-UP"
set_global_assignment -name CYCLONEII_RESERVE_NCEO_AFTER_CONFIGURATION "USE AS REGULAR IO"
{qsf_extra}
""")
    (bdir / f"{name}.qpf").write_text(f'PROJECT_REVISION = "{name}"\n')
    print(f"\n--- Building {name} ---")
    run([str(QUARTUS / "quartus_map"), "--read_settings_files=on",
         "--write_settings_files=off", name], cwd=bdir)
    run([str(QUARTUS / "quartus_fit"), "--read_settings_files=on",
         "--write_settings_files=off", name], cwd=bdir)
    fit_rpt = bdir / "output_files" / f"{name}.fit.rpt"
    if fit_rpt.exists():
        text = fit_rpt.read_text(errors="replace")
        for line in text.splitlines():
            ll = line.lower()
            if "lccomb" in ll or "total logic elements" in ll:
                print(f"  fit: {line.strip()}")
    run([str(QUARTUS / "quartus_asm"), "--read_settings_files=on",
         "--write_settings_files=off", name], cwd=bdir)
    sof = bdir / "output_files" / f"{name}.sof"
    rbf = bdir / f"{name}.rbf"
    run([str(QUARTUS / "quartus_cpf"), "-c", "-o", "bitstream_compression=off",
         str(sof), str(rbf)], cwd=bdir)
    print(f"  -> {rbf} ({rbf.stat().st_size} bytes)")
    return rbf


def extract_cells_full(a: bytes, b: bytes) -> list[list[int]]:
    """Extract cells including header pos 208-209."""
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


def main():
    WORK.mkdir(parents=True, exist_ok=True)
    nv = (REPO / "results" / "rbf" / "nv_zero_global.rbf").read_bytes()

    v_full = f"""\
module x10y10_full (input KEY2, input KEY3, output LED0);
    wire lut_out /* synthesis keep */;
    assign lut_out = KEY2 & KEY3;
    assign LED0 = lut_out;
endmodule
"""
    qsf_full = f"""\
set_location_assignment PIN_E16 -to KEY2
set_location_assignment PIN_M16 -to KEY3
set_location_assignment PIN_G15 -to LED0
set_location_assignment {QUARTUS_LOC} -to "lut_out"
"""
    rbf_full = build("x10y10_full", v_full, qsf_full).read_bytes()

    v_nop = f"""\
module x10y10_nop (input KEY2, input KEY3, output LED0);
    wire lut_out /* synthesis keep */;
    assign lut_out = KEY2 & KEY3;
    assign LED0 = 1'b0;
endmodule
"""
    qsf_nop = f"""\
set_location_assignment PIN_E16 -to KEY2
set_location_assignment PIN_M16 -to KEY3
set_location_assignment PIN_G15 -to LED0
set_location_assignment {QUARTUS_LOC} -to "lut_out"
"""
    rbf_nop = build("x10y10_nop", v_nop, qsf_nop).read_bytes()

    # --- Analysis ---
    c_full_nv = extract_cells_full(rbf_full, nv)
    c_nop_nv = extract_cells_full(rbf_nop, nv)
    c_full_nop = extract_cells_full(rbf_full, rbf_nop)

    print(f"\n{'='*60}")
    print(f"X10Y10N0 RESULTS")
    print(f"{'='*60}")
    print(f"  full - nv_zero: {len(c_full_nv)} cells")
    print(f"  nop - nv_zero:  {len(c_nop_nv)} cells")
    print(f"  full - nop:     {len(c_full_nop)} cells (output route + LUT)")

    # --- Cross-position comparison with X16Y4N0 ---
    r16 = json.load(open(REPO / "tmp" / "mine_outroute_nv" / "outroute_nv_result.json"))

    # Add header cells to X16Y4 data
    hdr_extra_16 = [
        [1080, 0], [1080, 5], [1081, 0], [1081, 5],
        [1920, 0], [1920, 2], [1921, 0], [1921, 2],
        [3600, 0], [3600, 2], [3600, 4], [3600, 5], [3600, 7],
        [3601, 0], [3601, 2], [3601, 4], [3601, 5], [3601, 7],
    ]
    full16 = set(tuple(c) for c in r16['full_vs_nv'] + hdr_extra_16)
    nop16 = set(tuple(c) for c in r16['nop_vs_nv'] + hdr_extra_16)
    route16 = set(tuple(c) for c in r16['output_route_cells'])

    full10 = set(tuple(c) for c in c_full_nv)
    nop10 = set(tuple(c) for c in c_nop_nv)
    route10 = set(tuple(c) for c in c_full_nop)

    print(f"\n{'='*60}")
    print(f"CROSS-POSITION COMPARISON (X16Y4 vs X10Y10)")
    print(f"{'='*60}")

    # Full design intersection
    full_shared = full16 & full10
    full_16only = full16 - full10
    full_10only = full10 - full16
    print(f"\n  Full designs:")
    print(f"    X16Y4: {len(full16)}, X10Y10: {len(full10)}")
    print(f"    Shared: {len(full_shared)}")
    print(f"    X16Y4 only: {len(full_16only)}")
    print(f"    X10Y10 only: {len(full_10only)}")

    # Nop (IOB-only) intersection — should be very high
    nop_shared = nop16 & nop10
    nop_16only = nop16 - nop10
    nop_10only = nop10 - nop16
    print(f"\n  Nop designs (IOB pads only, no LUT):")
    print(f"    X16Y4: {len(nop16)}, X10Y10: {len(nop10)}")
    print(f"    Shared: {len(nop_shared)}")
    print(f"    X16Y4 only: {len(nop_16only)}")
    print(f"    X10Y10 only: {len(nop_10only)}")

    # Output route intersection — should be low (different paths)
    route_shared = route16 & route10
    route_16only = route16 - route10
    route_10only = route10 - route16
    print(f"\n  Output route (full-nop):")
    print(f"    X16Y4: {len(route16)}, X10Y10: {len(route10)}")
    print(f"    Shared: {len(route_shared)} (position-invariant G15 activation)")
    print(f"    X16Y4 only: {len(route_16only)} (X16Y4-specific routing)")
    print(f"    X10Y10 only: {len(route_10only)} (X10Y10-specific routing)")

    if route_shared:
        print(f"\n  Position-invariant output route cells:")
        for off, bp in sorted(route_shared):
            frame = (off - 32) // 210
            pos = (off - 32) % 210
            band = "hdr" if frame < 25 else ("data" if frame < 1692 else "block")
            print(f"    ({off}, {bp})  frame={frame} pos={pos} band={band}")

    # Save
    result = {
        "loc": f"X{LOC_X}Y{LOC_Y}N{OUR_N}",
        "full_vs_nv": c_full_nv,
        "nop_vs_nv": c_nop_nv,
        "output_route_cells": c_full_nop,
        "cross_position": {
            "nop_shared": len(nop_shared),
            "nop_16only": len(nop_16only),
            "nop_10only": len(nop_10only),
            "route_shared": sorted(list(route_shared)),
            "route_16only": sorted(list(route_16only)),
            "route_10only": sorted(list(route_10only)),
        }
    }
    out = WORK / "outroute_nv_x10y10_result.json"
    out.write_text(json.dumps(result, indent=2))
    print(f"\nSaved to {out}")


if __name__ == "__main__":
    main()
