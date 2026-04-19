# SPDX-License-Identifier: GPL-3.0-or-later
"""Build the pipeline-test design with Quartus and export RBF."""
from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
SCRIPT_DIR = Path(__file__).resolve().parent
WORK = REPO / "tmp" / "pipeline_test_quartus"
OUT_RBF = REPO / "tmp" / "pipeline_test_gold.rbf"

QSF = """\
set_global_assignment -name FAMILY "Cyclone IV E"
set_global_assignment -name DEVICE EP4CE6F17C8
set_global_assignment -name TOP_LEVEL_ENTITY test_top
set_global_assignment -name VERILOG_FILE test_top.v
set_global_assignment -name PROJECT_OUTPUT_DIRECTORY output_files
set_global_assignment -name STRATIX_DEVICE_IO_STANDARD "3.3-V LVTTL"
set_global_assignment -name SEED 1
set_global_assignment -name NUM_PARALLEL_PROCESSORS 4
set_global_assignment -name CYCLONEII_RESERVE_NCEO_AFTER_CONFIGURATION "USE AS REGULAR IO"

set_location_assignment PIN_E1  -to CLOCK
set_location_assignment PIN_E16 -to KEY2
set_location_assignment PIN_M16 -to KEY3
set_location_assignment PIN_M15 -to KEY4
set_location_assignment PIN_G1  -to TXD
set_location_assignment PIN_G15 -to LED[0]
set_location_assignment PIN_F16 -to LED[1]
set_location_assignment PIN_F15 -to LED[2]
set_location_assignment PIN_D16 -to LED[3]
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

    # Write source files
    import shutil
    shutil.copy(SCRIPT_DIR / "test_top.v", WORK / "test_top.v")
    (WORK / "test_top.qsf").write_text(QSF)
    (WORK / "test_top.qpf").write_text(
        'PROJECT_REVISION = "test_top"\n')

    t0 = time.time()
    print("Quartus build:", flush=True)
    run(["quartus_map", "--read_settings_files=on", "test_top"], WORK)
    run(["quartus_fit", "--read_settings_files=on", "test_top"], WORK)
    run(["quartus_asm", "test_top"], WORK)

    sof = WORK / "output_files" / "test_top.sof"
    if not sof.exists():
        print(f"ERROR: {sof} not found")
        sys.exit(1)

    run(["quartus_cpf", "-c", "-o", "bitstream_compression=off",
         str(sof), str(OUT_RBF)], WORK)

    elapsed = time.time() - t0
    print(f"\nDone in {elapsed:.0f}s → {OUT_RBF}")
    print(f"RBF size: {OUT_RBF.stat().st_size} bytes")

    # Print fit summary
    fit_sum = WORK / "output_files" / "test_top.fit.summary"
    if fit_sum.exists():
        print("\n" + fit_sum.read_text(errors="replace"))


if __name__ == "__main__":
    main()
