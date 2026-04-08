# SPDX-License-Identifier: GPL-3.0-or-later
"""Phase 3.27 follow-up #2: sweep DSPMULT_X20_Y*_N* to find all legal
mult positions. Discovery run showed Quartus auto-places at
DSPMULT_X20_Y1_N0 — probe nearby Y/N coords to map the full column.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from compile import compile_and_export
from config import RBF_DIR

CE10_DEVICE = "EP4CE10F17C8"
FAMILY = "Cyclone IV E"

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


def gen_qsf(loc=None):
    lines = [
        f'set_global_assignment -name FAMILY "{FAMILY}"',
        f'set_global_assignment -name DEVICE {CE10_DEVICE}',
        'set_global_assignment -name TOP_LEVEL_ENTITY fuzz_top',
        'set_global_assignment -name VERILOG_FILE fuzz_top.v',
        'set_global_assignment -name PROJECT_OUTPUT_DIRECTORY output_files',
    ]
    for p in ("clk", "a0", "a1", "b0", "b1", "p0"):
        lines.append(f'set_instance_assignment -name VIRTUAL_PIN ON -to {p}')
    if loc:
        lines.append(f'set_location_assignment {loc} -to "u"')
    return "\n".join(lines) + "\n"


def try_loc(loc):
    tag = f"mult_{loc}"
    rbf, t, err = compile_and_export(tag, VERILOG, gen_qsf(loc),
                                     rbf_output=os.path.join(RBF_DIR, f"{tag}.rbf"))
    ok = rbf is not None
    return ok, (err or "")[:120]


def main():
    # Coords to probe: CE6/CE10 die has X=20 mult column, LAB_Y ∈ [2..21].
    # Discovery showed Y=1 exists; try Y=1..21 and N=0/1/2 to enumerate.
    candidates = []
    for y in range(1, 22):
        for n in (0, 1, 2):
            candidates.append(f"DSPMULT_X20_Y{y}_N{n}")
    legal = []
    illegal = []
    for loc in candidates:
        ok, err = try_loc(loc)
        if ok:
            print(f"  [OK ] {loc}")
            legal.append(loc)
        else:
            if "illegal" in err.lower():
                illegal.append(loc)
            else:
                print(f"  [FAIL] {loc}: {err}")
    print(f"\nlegal: {len(legal)}, illegal: {len(illegal)}")
    print("legal positions:")
    for loc in legal:
        print(f"  {loc}")


if __name__ == "__main__":
    main()
