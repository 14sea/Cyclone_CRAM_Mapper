#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Mine SLICE->IOB output routing cells for the 1-LUT design.

Strategy:
  1. Build 'design_led' : KEY2 & KEY3 -> LED0 (G15) [forces 1 LUT]
  2. Build 'design_nop' : KEY2 & KEY3 -> nowhere    [same logic, output disconnected]
  3. Diff CRAM cells: design_led - design_nop = output routing + IOB_OUT pad cells

Also builds a 'design_f16' variant routing to F16 instead of G15, to
separate routing cells from IOB pad-configuration cells via:
  design_led - design_f16 = output routing delta + IOB pad delta

The Quartus fit report is parsed to discover where the LUT was placed.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
SCRIPT_DIR = Path(__file__).resolve().parent
WORK = REPO / "tmp" / "mine_outroute"
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


def build_quartus(name: str, verilog_text: str, qsf_extra: str = "") -> Path:
    """Build a single Quartus design, return RBF path."""
    bdir = WORK / name
    bdir.mkdir(parents=True, exist_ok=True)

    vfile = bdir / f"{name}.v"
    vfile.write_text(verilog_text)

    qsf = bdir / f"{name}.qsf"
    qsf.write_text(f"""
set_global_assignment -name FAMILY "Cyclone IV E"
set_global_assignment -name DEVICE EP4CE6F17C8
set_global_assignment -name TOP_LEVEL_ENTITY {name}
set_global_assignment -name VERILOG_FILE {vfile}
set_global_assignment -name PROJECT_OUTPUT_DIRECTORY output_files
set_global_assignment -name SEED 1
set_global_assignment -name STRATIX_DEVICE_IO_STANDARD "3.3-V LVTTL"
set_global_assignment -name RESERVE_ALL_UNUSED_PINS_WEAK_PULLUP "AS INPUT TRI-STATED WITH WEAK PULL-UP"
set_global_assignment -name CYCLONEII_RESERVE_NCEO_AFTER_CONFIGURATION "USE AS REGULAR IO"
{qsf_extra}
""")

    qpf = bdir / f"{name}.qpf"
    qpf.write_text(f'PROJECT_REVISION = "{name}"\n')

    print(f"\n--- Building {name} ---")
    run([str(QUARTUS / "quartus_map"), "--read_settings_files=on",
         "--write_settings_files=off", name], cwd=bdir)
    run([str(QUARTUS / "quartus_fit"), "--read_settings_files=on",
         "--write_settings_files=off", name], cwd=bdir)
    run([str(QUARTUS / "quartus_asm"), "--read_settings_files=on",
         "--write_settings_files=off", name], cwd=bdir)

    sof = bdir / "output_files" / f"{name}.sof"
    rbf = bdir / f"{name}.rbf"
    run([str(QUARTUS / "quartus_cpf"), "-c",
         "-o", "bitstream_compression=off", str(sof), str(rbf)], cwd=bdir)
    print(f"  -> {rbf} ({rbf.stat().st_size} bytes)")

    # Parse fit report for placement
    fit_rpt = bdir / "output_files" / f"{name}.fit.rpt"
    if fit_rpt.exists():
        text = fit_rpt.read_text(errors="replace")
        for line in text.splitlines():
            ll = line.lower()
            if "lccomb" in ll or "total logic elements" in ll:
                print(f"  fit: {line.strip()}")

    return rbf


def extract_cram_cells(rbf_a: bytes, rbf_b: bytes) -> list[tuple[int, int]]:
    """Return list of (offset, bitpos) CRAM cells that differ."""
    cells = []
    for off in range(32, min(len(rbf_a), len(rbf_b))):
        if off >= 367952:
            break
        frame_off = off - 32
        pos_in_frame = frame_off % 210
        if pos_in_frame >= 208:
            continue  # CRC
        xor = rbf_a[off] ^ rbf_b[off]
        for bp in range(8):
            if xor & (1 << bp):
                cells.append((off, bp))
    return cells


def main():
    WORK.mkdir(parents=True, exist_ok=True)

    nv_rbf = (REPO / "results" / "rbf" / "nv_zero_global.rbf").read_bytes()

    # --- Design A: KEY2 & KEY3 -> LED0 (G15) ---
    v_led = """\
module design_led (input KEY2, input KEY3, output LED0);
    assign LED0 = KEY2 & KEY3;
endmodule
"""
    qsf_led = """\
set_location_assignment PIN_E16 -to KEY2
set_location_assignment PIN_M16 -to KEY3
set_location_assignment PIN_G15 -to LED0
"""
    rbf_led_path = build_quartus("design_led", v_led, qsf_led)
    rbf_led = rbf_led_path.read_bytes()

    # --- Design B: KEY2 & KEY3 -> unused (no output) ---
    v_nop = """\
module design_nop (input KEY2, input KEY3, output LED0);
    wire lut_out = KEY2 & KEY3;
    // LED0 tied to constant to prevent Quartus from removing LUT
    assign LED0 = 1'b0;
endmodule
"""
    qsf_nop = """\
set_location_assignment PIN_E16 -to KEY2
set_location_assignment PIN_M16 -to KEY3
set_location_assignment PIN_G15 -to LED0
"""
    rbf_nop_path = build_quartus("design_nop", v_nop, qsf_nop)
    rbf_nop = rbf_nop_path.read_bytes()

    # --- Design C: KEY2 & KEY3 -> F16 (different output pin) ---
    v_f16 = """\
module design_f16 (input KEY2, input KEY3, output LED1);
    assign LED1 = KEY2 & KEY3;
endmodule
"""
    qsf_f16 = """\
set_location_assignment PIN_E16 -to KEY2
set_location_assignment PIN_M16 -to KEY3
set_location_assignment PIN_F16 -to LED1
"""
    rbf_f16_path = build_quartus("design_f16", v_f16, qsf_f16)
    rbf_f16 = rbf_f16_path.read_bytes()

    # --- Analysis ---
    print("\n=== Cell extraction ===")

    # Delta: design_led vs nv_zero_global
    cells_led_nv = extract_cram_cells(rbf_led, nv_rbf)
    print(f"design_led vs nv_zero: {len(cells_led_nv)} cells")

    cells_nop_nv = extract_cram_cells(rbf_nop, nv_rbf)
    print(f"design_nop vs nv_zero: {len(cells_nop_nv)} cells")

    cells_f16_nv = extract_cram_cells(rbf_f16, nv_rbf)
    print(f"design_f16 vs nv_zero: {len(cells_f16_nv)} cells")

    # Pair deltas
    cells_led_nop = extract_cram_cells(rbf_led, rbf_nop)
    print(f"\ndesign_led vs design_nop: {len(cells_led_nop)} cells")
    print(f"  (= output routing to G15 + IOB_OUT delta for G15)")

    cells_led_f16 = extract_cram_cells(rbf_led, rbf_f16)
    print(f"design_led vs design_f16: {len(cells_led_f16)} cells")
    print(f"  (= G15-specific vs F16-specific output routing + IOB delta)")

    # Classify cells by band
    def classify(cells):
        hdr = [(o, b) for o, b in cells if o < 32 + 25 * 210]
        data = [(o, b) for o, b in cells if 32 + 25 * 210 <= o < 32 + 1692 * 210]
        block = [(o, b) for o, b in cells if 32 + 1692 * 210 <= o]
        return hdr, data, block

    for name, cells in [("led_vs_nv", cells_led_nv),
                         ("nop_vs_nv", cells_nop_nv),
                         ("led_vs_nop", cells_led_nop),
                         ("led_vs_f16", cells_led_f16)]:
        hdr, data, block = classify(cells)
        print(f"\n  {name}: hdr={len(hdr)}, data={len(data)}, block={len(block)}")

    # Save the key delta: led_vs_nop = output routing cells
    result = {
        "description": "SLICE->IOB output routing cells for G15 via pair delta",
        "method": "design_led (KEY2&KEY3->G15) minus design_nop (KEY2&KEY3->nowhere)",
        "pin": "G15",
        "cells": cells_led_nop,
        "led_vs_nv_cells": cells_led_nv,
        "nop_vs_nv_cells": cells_nop_nv,
        "led_vs_f16_cells": cells_led_f16,
    }
    out_json = WORK / "outroute_mining_result.json"
    with open(out_json, "w") as f:
        json.dump(result, f, indent=2)
    print(f"\nSaved to {out_json}")

    # Also extract LUT placement from fit report
    print("\n=== LUT Placement ===")
    for design in ["design_led", "design_nop", "design_f16"]:
        rpt = WORK / design / "output_files" / f"{design}.fit.rpt"
        if not rpt.exists():
            continue
        text = rpt.read_text(errors="replace")
        for line in text.splitlines():
            if "LCCOMB" in line:
                print(f"  {design}: {line.strip()}")


if __name__ == "__main__":
    main()
