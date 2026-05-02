# SPDX-License-Identifier: GPL-3.0-or-later
"""Build the led_blink design with Quartus and export RBF (gold reference)."""
from __future__ import annotations

import subprocess
import sys
import time
import shutil
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
SCRIPT_DIR = Path(__file__).resolve().parent
WORK = REPO / "tmp" / "led_blink_quartus"
OUT_RBF = REPO / "tmp" / "led_blink_gold.rbf"

QSF = """\
set_global_assignment -name FAMILY "Cyclone IV E"
set_global_assignment -name DEVICE EP4CE6F17C8
set_global_assignment -name TOP_LEVEL_ENTITY led_blink
set_global_assignment -name VERILOG_FILE led_blink.v
set_global_assignment -name PROJECT_OUTPUT_DIRECTORY output_files
set_global_assignment -name STRATIX_DEVICE_IO_STANDARD "3.3-V LVTTL"
set_global_assignment -name SEED 1
set_global_assignment -name NUM_PARALLEL_PROCESSORS 4
set_global_assignment -name CYCLONEII_RESERVE_NCEO_AFTER_CONFIGURATION "USE AS REGULAR IO"

set_location_assignment PIN_E1  -to CLOCK
set_location_assignment PIN_G15 -to LED
"""


def run(cmd, cwd):
    print(f"  $ {' '.join(cmd)}", flush=True)
    r = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True,
                       errors="replace", timeout=300)
    if r.returncode != 0:
        print(f"FAIL (rc={r.returncode})")
        print(r.stdout[-2000:] if r.stdout else "")
        print(r.stderr[-2000:] if r.stderr else "")
        sys.exit(1)
    return r


def main():
    WORK.mkdir(parents=True, exist_ok=True)

    shutil.copy(SCRIPT_DIR / "led_blink.v", WORK / "led_blink.v")
    (WORK / "led_blink.qsf").write_text(QSF)
    (WORK / "led_blink.qpf").write_text('PROJECT_REVISION = "led_blink"\n')

    t0 = time.time()
    print("Quartus build:", flush=True)
    run(["quartus_map", "--read_settings_files=on", "led_blink"], WORK)
    run(["quartus_fit", "--read_settings_files=on", "led_blink"], WORK)
    run(["quartus_asm", "led_blink"], WORK)

    sof = WORK / "output_files" / "led_blink.sof"
    if not sof.exists():
        print(f"ERROR: {sof} not found")
        sys.exit(1)

    run(["quartus_cpf", "-c", "-o", "bitstream_compression=off",
         str(sof), str(OUT_RBF)], WORK)

    elapsed = time.time() - t0
    print(f"\nDone in {elapsed:.0f}s → {OUT_RBF}")
    print(f"RBF size: {OUT_RBF.stat().st_size} bytes")


if __name__ == "__main__":
    main()
