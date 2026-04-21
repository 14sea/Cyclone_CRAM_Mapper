#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Build the minimal 1-LUT design in Quartus for gold reference.

Produces: tmp/minimal_1lut_quartus/passthrough.rbf
Also extracts placement/routing for comparison.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
SCRIPT_DIR = Path(__file__).resolve().parent
WORK = REPO / "tmp" / "minimal_1lut_quartus"
OUT_RBF = WORK / "passthrough.rbf"

QUARTUS = Path.home() / "intelFPGA_lite" / "21.1" / "quartus" / "bin"


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


def main():
    WORK.mkdir(parents=True, exist_ok=True)

    verilog = SCRIPT_DIR / "passthrough.v"

    # --- QSF ---
    qsf = WORK / "passthrough.qsf"
    qsf.write_text(f"""
set_global_assignment -name FAMILY "Cyclone IV E"
set_global_assignment -name DEVICE EP4CE6F17C8
set_global_assignment -name TOP_LEVEL_ENTITY passthrough
set_global_assignment -name VERILOG_FILE {verilog}
set_global_assignment -name PROJECT_OUTPUT_DIRECTORY output_files
set_global_assignment -name SEED 1

set_location_assignment PIN_E16 -to KEY2
set_location_assignment PIN_G15 -to LED0

set_global_assignment -name STRATIX_DEVICE_IO_STANDARD "3.3-V LVTTL"
set_global_assignment -name RESERVE_ALL_UNUSED_PINS_WEAK_PULLUP "AS INPUT TRI-STATED WITH WEAK PULL-UP"
set_global_assignment -name CYCLONEII_RESERVE_NCEO_AFTER_CONFIGURATION "USE AS REGULAR IO"
""")

    qpf = WORK / "passthrough.qpf"
    qpf.write_text('PROJECT_REVISION = "passthrough"\n')

    # --- Quartus flow ---
    print("\n=== Quartus: map ===")
    run([str(QUARTUS / "quartus_map"), "--read_settings_files=on",
         "--write_settings_files=off", "passthrough"], cwd=WORK)

    print("\n=== Quartus: fit ===")
    run([str(QUARTUS / "quartus_fit"), "--read_settings_files=on",
         "--write_settings_files=off", "passthrough"], cwd=WORK)

    print("\n=== Quartus: asm ===")
    run([str(QUARTUS / "quartus_asm"), "--read_settings_files=on",
         "--write_settings_files=off", "passthrough"], cwd=WORK)

    print("\n=== Quartus: cpf (RBF) ===")
    sof = WORK / "output_files" / "passthrough.sof"
    run([str(QUARTUS / "quartus_cpf"), "-c",
         "-o", "bitstream_compression=off",
         str(sof), str(OUT_RBF)], cwd=WORK)

    if OUT_RBF.exists():
        print(f"\n  Gold RBF: {OUT_RBF} ({OUT_RBF.stat().st_size} bytes)")
    else:
        print("ERROR: RBF not generated")
        sys.exit(1)

    # --- Extract fit report for placement info ---
    fit_rpt = WORK / "output_files" / "passthrough.fit.rpt"
    if fit_rpt.exists():
        print("\n=== Fit report excerpts ===")
        text = fit_rpt.read_text(errors="replace")
        for line in text.splitlines():
            ll = line.lower()
            if any(k in ll for k in ["key2", "led0", "lccomb",
                                      "total logic elements",
                                      "total registers"]):
                print(f"  {line.strip()}")

    # --- Diff with open-toolchain RBF if available ---
    open_rbf = REPO / "tmp" / "minimal_1lut_open" / "passthrough.rbf"
    if open_rbf.exists():
        gold = OUT_RBF.read_bytes()
        oopen = open_rbf.read_bytes()
        if gold == oopen:
            print("\n  BYTE-IDENTICAL to open toolchain!")
        else:
            diffs = sum(1 for a, b in zip(gold, oopen) if a != b)
            print(f"\n  Differs from open toolchain: {diffs} bytes")

    print(f"\nDone. Flash with:")
    print(f"  openFPGALoader -c usb-blaster {OUT_RBF}")


if __name__ == "__main__":
    main()
