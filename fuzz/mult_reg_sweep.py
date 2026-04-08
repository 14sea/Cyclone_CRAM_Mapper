# SPDX-License-Identifier: GPL-3.0-or-later
"""Phase 5.0-A expansion: sweep mult input/output register options.
Same LOC, same width/rep — only register enable flags vary.
"""
import os, sys, json
from concurrent.futures import ProcessPoolExecutor, as_completed
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from compile import compile_and_export
from config import RBF_DIR

FAMILY = "Cyclone IV E"
DEVICE = "EP4CE10F17C8"
NODE = "lpm_mult:u|mult_qpl:auto_generated|mac_mult1"
LOC = "DSPMULT_X20_Y10_N0"

# Variants: (tag, input_a_pipe, input_b_pipe, output_pipe)
# Using lpm_pipeline parameter — integer 0..2
VARIANTS = [
    ("pipe0",  0),
    ("pipe1",  1),
    ("pipe2",  2),
    ("pipe3",  3),
]

def verilog(pipeline):
    return f"""\
module fuzz_top(input clk, input a0, input a1, input b0, input b1, output p0);
    wire [8:0] a = {{{{7{{1'b0}}}}, a1, a0}};
    wire [8:0] b = {{{{7{{1'b0}}}}, b1, b0}};
    wire [17:0] p;
    lpm_mult #(
        .lpm_widtha(9), .lpm_widthb(9), .lpm_widthp(18),
        .lpm_representation("UNSIGNED"),
        .lpm_pipeline({pipeline}),
        .lpm_type("LPM_MULT")
    ) u (.clock(clk), .dataa(a), .datab(b), .result(p));
    assign p0 = ^p;
endmodule
"""

QSF = f"""\
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
set_location_assignment {LOC} -to "{NODE}"
"""

def build(variant):
    tag, pipe = variant
    tagfull = f"mult_reg_{tag}"
    out = os.path.join(RBF_DIR, f"{tagfull}.rbf")
    rbf, t, err = compile_and_export(tagfull, verilog(pipe), QSF, rbf_output=out)
    return tag, rbf is not None, t, (err or "")[:200]

def main():
    with ProcessPoolExecutor(max_workers=4) as ex:
        futs = {ex.submit(build, v): v for v in VARIANTS}
        for f in as_completed(futs):
            tag, ok, t, err = f.result()
            print(f"  {tag:8s} {'OK' if ok else 'FAIL'} ({t:.1f}s) {err if not ok else ''}")

    base = os.path.join(RBF_DIR, "mult_reg_pipe0.rbf")
    if not os.path.exists(base):
        print("base pipe0 failed")
        return
    base_b = open(base, "rb").read()

    def cells(path):
        d = open(path, "rb").read()
        out = set()
        for i in range(32, min(len(base_b), len(d))):
            x = base_b[i] ^ d[i]
            if x:
                off=(i-32)%210
                if off>=208: continue
                for bp in range(8):
                    if x>>bp&1: out.add((i,bp))
        return out

    results = {}
    for tag, _ in VARIANTS:
        p = os.path.join(RBF_DIR, f"mult_reg_{tag}.rbf")
        if not os.path.exists(p): continue
        c = cells(p)
        results[tag] = sorted(c)
        hdr = sorted(x for x in c if x[0] in (44, 73))
        print(f"{tag:8s} delta={len(c):5}  header44/73={hdr}")

    os.makedirs("results", exist_ok=True)
    with open("results/mult_reg_sweep.json", "w") as f:
        json.dump(results, f, indent=1)
    print("archived results/mult_reg_sweep.json")


if __name__ == "__main__":
    main()
