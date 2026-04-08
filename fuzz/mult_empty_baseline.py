# SPDX-License-Identifier: GPL-3.0-or-later
"""True empty baseline for Phase 5.0 mult mining: same scaffold as
mult_loc_test but no lpm_mult instance. Diffs reveal always-mult infra."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from compile import compile_and_export
from config import RBF_DIR

FAMILY = "Cyclone IV E"
DEVICE = "EP4CE10F17C8"

VERILOG = """\
module fuzz_top(
    input clk, input a0, input a1, input b0, input b1, output p0
);
    assign p0 = (a0 & b0) ^ (a1 & b1);
endmodule
"""

QSF = f"""\
set_global_assignment -name FAMILY "{FAMILY}"
set_global_assignment -name DEVICE {DEVICE}
set_global_assignment -name TOP_LEVEL_ENTITY fuzz_top
set_global_assignment -name VERILOG_FILE fuzz_top.v
set_global_assignment -name PROJECT_OUTPUT_DIRECTORY output_files
# REAL pins only — see memory/feedback_virtual_pin_mining_is_fiction.md
set_location_assignment PIN_E1  -to clk
set_location_assignment PIN_E16 -to a0
set_location_assignment PIN_M16 -to a1
set_location_assignment PIN_M15 -to b0
set_location_assignment PIN_E15 -to b1
set_location_assignment PIN_G15 -to p0
"""


def main():
    tag = "mult_empty_baseline"
    out = os.path.join(RBF_DIR, f"{tag}.rbf")
    rbf, t, err = compile_and_export(tag, VERILOG, QSF, rbf_output=out)
    print(f"{'OK' if rbf else 'FAIL'} ({t:.1f}s) {out}")
    if err: print(err[:200])


if __name__ == "__main__":
    main()
