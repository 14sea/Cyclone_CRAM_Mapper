# SPDX-License-Identifier: GPL-3.0-or-later
"""Phase 5.0 noise-reduction: recompile mult at Y1_N0 and Y10_N0 with
REAL pin LOCs (no VIRTUAL_PIN) to see if fixing the I/O stabilizes the
auto-router noise around the DSP block.

If per-site cells drop from ~290 toward 62 universal, fitter-noise wall
is breakable and per-(Y,N) mult config mining becomes feasible.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from compile import compile_and_export
from config import RBF_DIR

FAMILY = "Cyclone IV E"
DEVICE = "EP4CE10F17C8"

# Scalar 2x2 mult — 4 input pins, 1 output pin fits AX301
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
set_location_assignment PIN_E1  -to clk
set_location_assignment PIN_E16 -to a0
set_location_assignment PIN_M16 -to a1
set_location_assignment PIN_M15 -to b0
set_location_assignment PIN_E15 -to b1
set_location_assignment PIN_G15 -to p0
set_location_assignment {{LOC}} -to "{NODE}"
"""

BASE_QSF = f"""\
set_global_assignment -name FAMILY "{FAMILY}"
set_global_assignment -name DEVICE {DEVICE}
set_global_assignment -name TOP_LEVEL_ENTITY fuzz_top
set_global_assignment -name VERILOG_FILE fuzz_top.v
set_global_assignment -name PROJECT_OUTPUT_DIRECTORY output_files
set_location_assignment PIN_E1  -to clk
set_location_assignment PIN_E16 -to a0
set_location_assignment PIN_M16 -to a1
set_location_assignment PIN_M15 -to b0
set_location_assignment PIN_E15 -to b1
set_location_assignment PIN_G15 -to p0
"""

BASE_VERILOG = """\
module fuzz_top(
    input clk, input a0, input a1, input b0, input b1, output p0
);
    assign p0 = (a0 & b0) ^ (a1 & b1);
endmodule
"""


def build(tag, vlg, qsf):
    out = os.path.join(RBF_DIR, f"{tag}.rbf")
    rbf, t, err = compile_and_export(tag, vlg, qsf, rbf_output=out)
    return rbf, t, err


def main():
    # 1) baseline with real pins
    print("Compiling mult_noise_base (real pins, no mult)...")
    r, t, e = build("mult_noise_base", BASE_VERILOG, BASE_QSF)
    print(f"  {'OK' if r else 'FAIL'} ({t:.1f}s) {e[:100] if e else ''}")

    # 2) Y1_N0 with real pins
    for y, n in [(1, 0), (10, 0)]:
        loc = f"DSPMULT_X20_Y{y}_N{n}"
        print(f"Compiling mult_noise_{loc}...")
        qsf = QSF_TMPL.replace("{LOC}", loc)
        r, t, e = build(f"mult_noise_{loc}", VERILOG, qsf)
        print(f"  {'OK' if r else 'FAIL'} ({t:.1f}s) {e[:100] if e else ''}")


if __name__ == "__main__":
    main()
