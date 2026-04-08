# SPDX-License-Identifier: GPL-3.0-or-later
"""M9K LOC syntax discovery (Phase 5.0 parallel).

Same trick that cracked DSPMULT: compile one altsyncram with no LOC,
grep fit.rpt for the hierarchical node path + M9K container name.
"""
import os, re, sys, glob
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from compile import compile_and_export
from config import RBF_DIR

FAMILY = "Cyclone IV E"
DEVICE = "EP4CE10F17C8"

VERILOG = """\
module fuzz_top(
    input clk,
    input [7:0] addr,
    input [7:0] din,
    input we,
    output [7:0] dout
);
    altsyncram #(
        .operation_mode("SINGLE_PORT"),
        .width_a(8), .widthad_a(8), .numwords_a(256),
        .lpm_type("altsyncram"),
        .ram_block_type("M9K"),
        .outdata_reg_a("UNREGISTERED")
    ) u (
        .clock0(clk), .address_a(addr), .data_a(din),
        .wren_a(we), .q_a(dout),
        .aclr0(1'b0), .aclr1(1'b0),
        .addressstall_a(1'b0), .addressstall_b(1'b0),
        .byteena_a(1'b1), .byteena_b(1'b1),
        .address_b({8{1'b0}}), .data_b({8{1'b0}}),
        .clock1(1'b1), .clocken0(1'b1), .clocken1(1'b1),
        .clocken2(1'b1), .clocken3(1'b1), .eccstatus(),
        .q_b(), .rden_a(1'b1), .rden_b(1'b1), .wren_b(1'b0)
    );
endmodule
"""

QSF = f"""\
set_global_assignment -name FAMILY "{FAMILY}"
set_global_assignment -name DEVICE {DEVICE}
set_global_assignment -name TOP_LEVEL_ENTITY fuzz_top
set_global_assignment -name VERILOG_FILE fuzz_top.v
set_global_assignment -name PROJECT_OUTPUT_DIRECTORY output_files
set_instance_assignment -name VIRTUAL_PIN ON -to clk
set_instance_assignment -name VIRTUAL_PIN ON -to addr
set_instance_assignment -name VIRTUAL_PIN ON -to din
set_instance_assignment -name VIRTUAL_PIN ON -to we
set_instance_assignment -name VIRTUAL_PIN ON -to dout
"""


def main():
    tag = "m9k_loc_discover"
    out = os.path.join(RBF_DIR, f"{tag}.rbf")
    rbf, t, err = compile_and_export(tag, VERILOG, QSF, rbf_output=out)
    if rbf is None:
        print(f"compile FAIL ({t:.1f}s): {(err or '')[:400]}")
        return
    print(f"compile OK ({t:.1f}s)")

    patterns = [
        r"M9K_X\d+_Y\d+_N\d+",
        r"RAMBLOCK_X\d+_Y\d+_N\d+",
        r"MEMBLOCK_X\d+_Y\d+_N\d+",
        r"RAM_X\d+_Y\d+_N\d+",
        r"altsyncram[^;\s]*",
    ]
    found = set()
    rpts = glob.glob(f"work/{tag}/output_files/*.fit.rpt") + \
           glob.glob(f"work/{tag}/output_files/*.map.rpt")
    for fn in rpts:
        try:
            txt = open(fn, errors="replace").read()
        except Exception:
            continue
        for pat in patterns:
            for m in re.findall(pat, txt):
                found.add(m)
    print(f"\nCandidates ({len(found)}):")
    for m in sorted(found)[:50]:
        print(f"  {m}")

    print("\nRAM summary section:")
    for fn in rpts:
        txt = open(fn, errors="replace").read()
        # find "RAM Summary" or "M9K" tables
        for m in re.finditer(r"(M9K|RAM_BLOCK|Memory Block)[^\n]*\n[^\n]*\n[^\n]*", txt):
            s = m.group(0).strip()
            if len(s) < 400:
                print(f"  {s[:200]}")


if __name__ == "__main__":
    main()
