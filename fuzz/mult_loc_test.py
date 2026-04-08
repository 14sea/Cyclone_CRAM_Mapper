# SPDX-License-Identifier: GPL-3.0-or-later
"""Mult LOC test: force placement of lpm_mult at specific DSPMULT_X20_Y*_N* location.

Previous mult_loc_sweep.py had `-to` backwards (assigned to LOC name instead of
node). Correct form uses the hierarchical MegaFunction node name:
    set_location_assignment DSPMULT_X20_Y1_N0 -to "lpm_mult:u|mult_qpl:auto_generated|mac_mult1"
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from compile import compile_and_export
from config import RBF_DIR

FAMILY = "Cyclone IV E"
DEVICE = "EP4CE10F17C8"

VERILOG = """\
module fuzz_top(
    input clk, input a0, input a1, input b0, input b1,
    output p0
);
    wire [8:0] a = {7'b0, a1, a0};
    wire [8:0] b = {7'b0, b1, b0};
    wire [17:0] p;
    lpm_mult #(
        .lpm_widtha(9), .lpm_widthb(9), .lpm_widthp(18),
        .lpm_representation("UNSIGNED"),
        .lpm_type("LPM_MULT")
    ) u (.dataa(a), .datab(b), .result(p));
    assign p0 = ^p;
endmodule
"""

NODE = "lpm_mult:u|mult_qpl:auto_generated|mac_mult1"

QSF_TMPL = f"""\
set_global_assignment -name FAMILY "{FAMILY}"
set_global_assignment -name DEVICE {DEVICE}
set_global_assignment -name TOP_LEVEL_ENTITY fuzz_top
set_global_assignment -name VERILOG_FILE fuzz_top.v
set_global_assignment -name PROJECT_OUTPUT_DIRECTORY output_files
set_instance_assignment -name VIRTUAL_PIN ON -to clk
set_instance_assignment -name VIRTUAL_PIN ON -to a0
set_instance_assignment -name VIRTUAL_PIN ON -to a1
set_instance_assignment -name VIRTUAL_PIN ON -to b0
set_instance_assignment -name VIRTUAL_PIN ON -to b1
set_instance_assignment -name VIRTUAL_PIN ON -to p0
set_location_assignment {{LOC}} -to "{NODE}"
"""


def try_loc(loc):
    tag = f"mult_loc_{loc}"
    qsf = QSF_TMPL.replace("{LOC}", loc)
    out = os.path.join(RBF_DIR, f"{tag}.rbf")
    rbf, t, err = compile_and_export(tag, VERILOG, qsf, rbf_output=out)
    if rbf is None:
        return False, (err or "")[:200]
    # Verify placement actually landed where requested
    fit = f"work/{tag}/output_files/{tag}.fit.rpt"
    placed = None
    try:
        with open(fit, errors="replace") as f:
            for line in f:
                if "mac_mult1" in line and "DSPMULT_X" in line:
                    import re
                    m = re.search(r"DSPMULT_X\d+_Y\d+_N\d+", line)
                    if m:
                        placed = m.group(0)
                        break
    except FileNotFoundError:
        pass
    return True, f"placed={placed}"


def main():
    locs = sys.argv[1:] or ["DSPMULT_X20_Y1_N0", "DSPMULT_X20_Y5_N1", "DSPMULT_X20_Y10_N2", "DSPMULT_X20_Y21_N0"]
    for loc in locs:
        ok, msg = try_loc(loc)
        print(f"{loc:30s} {'OK' if ok else 'FAIL'}  {msg}")


if __name__ == "__main__":
    main()
