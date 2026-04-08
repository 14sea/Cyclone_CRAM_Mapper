# SPDX-License-Identifier: GPL-3.0-or-later
"""M9K LOC legal-site sweep (parallel to mult_loc_test)."""
import os, sys, re
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from compile import compile_and_export
from config import RBF_DIR

FAMILY = "Cyclone IV E"
DEVICE = "EP4CE10F17C8"

VERILOG = """\
module fuzz_top(
    input clk, input addr, input din, input we, output dout
);
    // Minimal 2x1 M9K so all ports fit on real AX301 pins
    altsyncram #(
        .operation_mode("SINGLE_PORT"),
        .width_a(1), .widthad_a(1), .numwords_a(2),
        .lpm_type("altsyncram"), .ram_block_type("M9K"),
        .outdata_reg_a("UNREGISTERED")
    ) u (
        .clock0(clk), .address_a(addr), .data_a(din), .wren_a(we), .q_a(dout),
        .aclr0(1'b0), .aclr1(1'b0), .addressstall_a(1'b0), .addressstall_b(1'b0),
        .byteena_a(1'b1), .byteena_b(1'b1),
        .address_b({8{1'b0}}), .data_b({8{1'b0}}),
        .clock1(1'b1), .clocken0(1'b1), .clocken1(1'b1),
        .clocken2(1'b1), .clocken3(1'b1), .eccstatus(),
        .q_b(), .rden_a(1'b1), .rden_b(1'b1), .wren_b(1'b0)
    );
endmodule
"""

NODE = "altsyncram:u|altsyncram_3ov:auto_generated|ALTSYNCRAM"

QSF_TMPL = f"""\
set_global_assignment -name FAMILY "{FAMILY}"
set_global_assignment -name DEVICE {DEVICE}
set_global_assignment -name TOP_LEVEL_ENTITY fuzz_top
set_global_assignment -name VERILOG_FILE fuzz_top.v
set_global_assignment -name PROJECT_OUTPUT_DIRECTORY output_files
# REAL pins only — VIRTUAL_PIN mining contaminates CRAM diffs with
# router-to-fake-pin artifacts (Phase 5.0 retraction 2026-04-08).
set_location_assignment PIN_E1  -to clk
set_location_assignment PIN_E16 -to addr
set_location_assignment PIN_M16 -to din
set_location_assignment PIN_M15 -to we
set_location_assignment PIN_G15 -to dout
set_location_assignment {{LOC}} -to "{NODE}"
"""


def try_loc(loc):
    tag = f"m9k_loc_{loc}"
    qsf = QSF_TMPL.replace("{LOC}", loc)
    out = os.path.join(RBF_DIR, f"{tag}.rbf")
    rbf, t, err = compile_and_export(tag, VERILOG, qsf, rbf_output=out)
    if rbf is None:
        return False, (err or "")[:150]
    fit = f"work/{tag}/output_files/{tag}.fit.rpt"
    placed = None
    try:
        for line in open(fit, errors="replace"):
            if "ALTSYNCRAM" in line and "M9K_X" in line:
                m = re.search(r"M9K_X\d+_Y\d+_N\d+", line)
                if m:
                    placed = m.group(0); break
    except FileNotFoundError:
        pass
    return True, f"placed={placed}"


def main():
    # X=15 and X=27 are the two M9K columns; auto-placer chose X15 first
    if len(sys.argv) > 1:
        locs = sys.argv[1:]
    else:
        locs = [f"M9K_X{x}_Y{y}_N{n}"
                for x in (15, 27) for y in range(1, 22) for n in range(3)]
    for loc in locs:
        ok, msg = try_loc(loc)
        print(f"{loc:22s} {'OK' if ok else 'FAIL'}  {msg}")


if __name__ == "__main__":
    main()
