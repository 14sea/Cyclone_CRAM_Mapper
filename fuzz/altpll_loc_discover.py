# SPDX-License-Identifier: GPL-3.0-or-later
"""Phase 5.0-C: discover altpll LOC name and locate PLL config bits.

Same trick as mult_loc_discover / m9k_loc_discover: compile altpll
with no LOC, grep fit.rpt for PLL_* placement name. VIRTUAL_PIN is
SAFE here — no CRAM diffing, only node-path extraction.
"""
import os, re, sys, glob
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from compile import compile_and_export
from config import RBF_DIR

FAMILY = "Cyclone IV E"
DEVICE = "EP4CE10F17C8"

VERILOG = """\
module fuzz_top(input inclk0, output c0, output locked);
    altpll #(
        .intended_device_family("Cyclone IV E"),
        .operation_mode("NORMAL"),
        .inclk0_input_frequency(20000),
        .clk0_divide_by(1),
        .clk0_multiply_by(2),
        .compensate_clock("CLK0"),
        .lpm_type("altpll")
    ) u (
        .inclk({{1'b0, inclk0}}),
        .clk({c0_wire, 4'b0}),
        .locked(locked),
        .areset(1'b0), .clkena(6'b111111), .extclkena(4'b1111),
        .fbin(1'b1), .pfdena(1'b1),
        .activeclock(), .clkbad(), .clkloss(), .clkswitch(1'b0),
        .configupdate(1'b0), .extclk(), .fbmimicbidir(), .fbout(),
        .phasecounterselect(4'b0), .phasedone(), .phasestep(1'b0),
        .phaseupdown(1'b0), .pllena(1'b1), .scanaclr(1'b0),
        .scanclk(1'b0), .scanclkena(1'b1), .scandata(1'b0),
        .scandataout(), .scandone(), .scanread(1'b0), .scanwrite(1'b0),
        .sclkout0(), .sclkout1(), .vcooverrange(), .vcounderrange()
    );
    wire c0_wire;
    assign c0 = c0_wire;
endmodule
"""

# Simpler version — just instantiate altpll_lite-ish
VERILOG_SIMPLE = """\
module fuzz_top(input inclk0, output c0);
    wire [4:0] clk;
    altpll #(
        .intended_device_family("Cyclone IV E"),
        .operation_mode("NORMAL"),
        .inclk0_input_frequency(20000),
        .clk0_divide_by(1),
        .clk0_multiply_by(2),
        .compensate_clock("CLK0"),
        .lpm_type("altpll")
    ) u (
        .inclk({1'b0, inclk0}),
        .clk(clk),
        .areset(1'b0), .clkena(6'b111111), .extclkena(4'b1111),
        .fbin(1'b1), .pfdena(1'b1), .pllena(1'b1),
        .clkswitch(1'b0), .configupdate(1'b0),
        .phasecounterselect(4'b0), .phasestep(1'b0), .phaseupdown(1'b0),
        .scanaclr(1'b0), .scanclk(1'b0), .scanclkena(1'b1),
        .scandata(1'b0), .scanread(1'b0), .scanwrite(1'b0)
    );
    assign c0 = clk[0];
endmodule
"""

QSF = f"""\
set_global_assignment -name FAMILY "{FAMILY}"
set_global_assignment -name DEVICE {DEVICE}
set_global_assignment -name TOP_LEVEL_ENTITY fuzz_top
set_global_assignment -name VERILOG_FILE fuzz_top.v
set_global_assignment -name PROJECT_OUTPUT_DIRECTORY output_files
set_instance_assignment -name VIRTUAL_PIN ON -to inclk0
set_instance_assignment -name VIRTUAL_PIN ON -to c0
"""


def main():
    tag = "altpll_loc_discover"
    out = os.path.join(RBF_DIR, f"{tag}.rbf")
    rbf, t, err = compile_and_export(tag, VERILOG_SIMPLE, QSF, rbf_output=out)
    if rbf is None:
        print(f"compile FAIL ({t:.1f}s): {(err or '')[:400]}")
        return
    print(f"compile OK ({t:.1f}s)")

    patterns = [
        r"PLL_\d+", r"PLL[A-Z0-9_]*_X\d+_Y\d+_N\d+",
        r"ALTPLL[A-Z0-9_]*_X\d+_Y\d+_N\d+",
        r"altpll[^;\s]{0,40}",
    ]
    found = set()
    for fn in glob.glob(f"work/{tag}/output_files/*.fit.rpt") + \
              glob.glob(f"work/{tag}/output_files/*.map.rpt"):
        try:
            txt = open(fn, errors="replace").read()
        except Exception:
            continue
        for pat in patterns:
            for m in re.findall(pat, txt):
                found.add(m)
    print(f"\nCandidates ({len(found)}):")
    for m in sorted(found)[:60]:
        print(f"  {m}")


if __name__ == "__main__":
    main()
