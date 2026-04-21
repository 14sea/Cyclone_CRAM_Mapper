#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Mine SLICE->IOB output routing by LOC-constraining a LUT at X6Y21N16
(matching the open toolchain's placement) and diffing against a no-output baseline.

Builds two Quartus designs:
  loc_led:  KEY2 & KEY3 -> LUT at LCCOMB_X6_Y21_N8 -> LED0 (G15)
  loc_nop:  KEY2 & KEY3 -> LUT at LCCOMB_X6_Y21_N8 -> constant 0 (G15)

The pair delta = output routing from X6Y21N16 to G15 + IOB_OUT delta.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
WORK = REPO / "tmp" / "mine_outroute_loc"
QUARTUS = Path.home() / "intelFPGA_lite" / "21.1" / "quartus" / "bin"

sys.path.insert(0, str(REPO / "fuzz"))


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

    # Check fit report for actual placement
    rpt = bdir / "output_files" / f"{name}.fit.rpt"
    if rpt.exists():
        text = rpt.read_text(errors="replace")
        for line in text.splitlines():
            ll = line.lower()
            if "total logic elements" in ll and "/" in line:
                print(f"  fit: {line.strip()}")

    # Generate post-fit netlist
    run([str(QUARTUS / "quartus_eda"), "--simulation=on",
         "--format=verilog", "--tool=modelsim", name], cwd=bdir)
    vo = bdir / "simulation" / "modelsim" / f"{name}.vo"
    if vo.exists():
        text = vo.read_text(errors="replace")
        for line in text.splitlines():
            if "LCCOMB" in line or "lut_mask" in line:
                print(f"  vo: {line.strip()}")

    run([str(QUARTUS / "quartus_asm"), "--read_settings_files=on",
         "--write_settings_files=off", name], cwd=bdir)
    sof = bdir / "output_files" / f"{name}.sof"
    rbf = bdir / f"{name}.rbf"
    run([str(QUARTUS / "quartus_cpf"), "-c", "-o", "bitstream_compression=off",
         str(sof), str(rbf)], cwd=bdir)
    print(f"  -> {rbf} ({rbf.stat().st_size} bytes)")
    return rbf


def extract_cells(a: bytes, b: bytes) -> list[list[int]]:
    cells = []
    for off in range(32, min(len(a), len(b))):
        if off >= 367952:
            break
        if (off - 32) % 210 >= 208:
            continue
        xor = a[off] ^ b[off]
        for bp in range(8):
            if xor & (1 << bp):
                cells.append([off, bp])
    return cells


def main():
    WORK.mkdir(parents=True, exist_ok=True)

    # --- Design: LOC-constrained LUT -> LED0 (G15) ---
    v_led = """\
module loc_led (input KEY2, input KEY3, output LED0);
    wire lut_out /* synthesis keep */;
    assign lut_out = KEY2 & KEY3;
    assign LED0 = lut_out;
endmodule
"""
    qsf_led = """\
set_location_assignment PIN_E16 -to KEY2
set_location_assignment PIN_M16 -to KEY3
set_location_assignment PIN_G15 -to LED0
set_location_assignment LCCOMB_X6_Y21_N8 -to "lut_out"
"""
    rbf_led = build("loc_led", v_led, qsf_led).read_bytes()

    # --- Baseline: same LUT, output driven constant ---
    # The LUT is still instantiated at the same LOC but its output
    # is disconnected from LED0. We use synthesis keep to prevent
    # Quartus from removing the LUT.
    v_nop = """\
module loc_nop (input KEY2, input KEY3, output LED0);
    wire lut_out /* synthesis keep */;
    assign lut_out = KEY2 & KEY3;
    assign LED0 = 1'b0;
endmodule
"""
    qsf_nop = """\
set_location_assignment PIN_E16 -to KEY2
set_location_assignment PIN_M16 -to KEY3
set_location_assignment PIN_G15 -to LED0
set_location_assignment LCCOMB_X6_Y21_N8 -to "lut_out"
"""
    rbf_nop = build("loc_nop", v_nop, qsf_nop).read_bytes()

    # --- Also build a baseline with NO LUT at all ---
    v_bare = """\
module loc_bare (input KEY2, input KEY3, output LED0);
    assign LED0 = 1'b0;
endmodule
"""
    qsf_bare = """\
set_location_assignment PIN_E16 -to KEY2
set_location_assignment PIN_M16 -to KEY3
set_location_assignment PIN_G15 -to LED0
"""
    rbf_bare = build("loc_bare", v_bare, qsf_bare).read_bytes()

    nv = (REPO / "results" / "rbf" / "nv_zero_global.rbf").read_bytes()

    # --- Analysis ---
    print("\n=== Cell extraction ===")

    cells_led_nop = extract_cells(rbf_led, rbf_nop)
    cells_led_bare = extract_cells(rbf_led, rbf_bare)
    cells_nop_bare = extract_cells(rbf_nop, rbf_bare)
    cells_led_nv = extract_cells(rbf_led, nv)
    cells_nop_nv = extract_cells(rbf_nop, nv)

    print(f"loc_led vs loc_nop:  {len(cells_led_nop)} cells (output route + IOB delta)")
    print(f"loc_led vs loc_bare: {len(cells_led_bare)} cells (LUT + input + output route)")
    print(f"loc_nop vs loc_bare: {len(cells_nop_bare)} cells (LUT + input route)")
    print(f"loc_led vs nv_zero:  {len(cells_led_nv)} cells")
    print(f"loc_nop vs nv_zero:  {len(cells_nop_nv)} cells")

    def classify(cells):
        hdr = [c for c in cells if c[0] < 32 + 25 * 210]
        data = [c for c in cells if 32 + 25 * 210 <= c[0] < 32 + 1692 * 210]
        block = [c for c in cells if 32 + 1692 * 210 <= c[0]]
        return hdr, data, block

    for name, cells in [("led_vs_nop", cells_led_nop),
                         ("led_vs_bare", cells_led_bare),
                         ("nop_vs_bare", cells_nop_bare)]:
        hdr, data, block = classify(cells)
        print(f"\n  {name}: hdr={len(hdr)}, data={len(data)}, block={len(block)}")
        if cells:
            print(f"    first 10: {cells[:10]}")

    # The pair delta led_vs_nop = output routing cells
    # Save for use in fasm2rbf
    result = {
        "src": "X6Y21N16",
        "pin": "G15",
        "method": "LOC_LCCOMB_X6_Y21_N8 pair delta (led-nop)",
        "cells": cells_led_nop,
        "led_vs_bare_cells": cells_led_bare,
        "nop_vs_bare_cells": cells_nop_bare,
    }
    out_json = WORK / "outroute_x6y21n16_g15.json"
    with open(out_json, "w") as f:
        json.dump(result, f, indent=2)
    print(f"\nSaved to {out_json}")

    # Flash candidate: the gold RBF
    print(f"\nFlash gold with:")
    print(f"  openFPGALoader -c usb-blaster {WORK / 'loc_led' / 'loc_led.rbf'}")


if __name__ == "__main__":
    main()
