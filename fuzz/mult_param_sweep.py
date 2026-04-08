# SPDX-License-Identifier: GPL-3.0-or-later
"""Phase 5.0-A: decode the 29-cell MULT_GLOBAL_ON_REAL by sweeping
lpm_mult parameters instead of position.

Same LOC (Y=10,N=0), same real pins — only mult parameters vary. Any
bit that flips between two variants is a label for that parameter.

Parallel compile via ProcessPoolExecutor; diff in-memory after.
"""
import os, sys, json, glob
from concurrent.futures import ProcessPoolExecutor, as_completed
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from compile import compile_and_export
from config import RBF_DIR

FAMILY = "Cyclone IV E"
DEVICE = "EP4CE10F17C8"
NODE = "lpm_mult:u|mult_qpl:auto_generated|mac_mult1"
LOC = "DSPMULT_X20_Y10_N0"

# Variants: (tag, widtha, widthb, rep, extra_reg)
# widthp = widtha+widthb
VARIANTS = [
    ("base_9x9u",   9, 9, "UNSIGNED",  False),
    ("wa4_9u",      4, 9, "UNSIGNED",  False),
    ("wa9_4u",      9, 4, "UNSIGNED",  False),
    ("wa4_4u",      4, 4, "UNSIGNED",  False),
    ("wa8_8u",      8, 8, "UNSIGNED",  False),
    ("wa9_9s",      9, 9, "SIGNED",    False),
    ("wa4_4s",      4, 4, "SIGNED",    False),
    ("wa8_8s",      8, 8, "SIGNED",    False),
    ("wa6_6u",      6, 6, "UNSIGNED",  False),
    ("wa6_6s",      6, 6, "SIGNED",    False),
]

QSF_HEAD = f"""\
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

def gen(wa, wb, rep):
    wp = wa + wb
    return f"""\
module fuzz_top(input clk, input a0, input a1, input b0, input b1, output p0);
    wire [{wa-1}:0] a = {{{{{wa-1}{{{{1'b0}}}}}}, a1, a0}} >> (({wa}<2)?0:0);
    wire [{wb-1}:0] b = {{{{{wb-1}{{{{1'b0}}}}}}, b1, b0}} >> (({wb}<2)?0:0);
    wire [{wp-1}:0] p;
    lpm_mult #(.lpm_widtha({wa}), .lpm_widthb({wb}), .lpm_widthp({wp}),
               .lpm_representation("{rep}"), .lpm_type("LPM_MULT")) u
              (.dataa(a), .datab(b), .result(p));
    assign p0 = ^p;
endmodule
"""

# Simpler: always-pad a/b to width by zero-extending the 2 real input bits
def gen_safe(wa, wb, rep):
    wp = wa + wb
    return f"""\
module fuzz_top(input clk, input a0, input a1, input b0, input b1, output p0);
    wire [{wa-1}:0] a = {{ {{{wa-2}{{1'b0}}}}, a1, a0 }};
    wire [{wb-1}:0] b = {{ {{{wb-2}{{1'b0}}}}, b1, b0 }};
    wire [{wp-1}:0] p;
    lpm_mult #(.lpm_widtha({wa}), .lpm_widthb({wb}), .lpm_widthp({wp}),
               .lpm_representation("{rep}"), .lpm_type("LPM_MULT")) u
              (.dataa(a), .datab(b), .result(p));
    assign p0 = ^p;
endmodule
"""


def build(variant):
    tag, wa, wb, rep, _reg = variant
    tagfull = f"mult_param_{tag}"
    verilog = gen_safe(wa, wb, rep)
    out = os.path.join(RBF_DIR, f"{tagfull}.rbf")
    rbf, t, err = compile_and_export(tagfull, verilog, QSF_HEAD, rbf_output=out)
    return tag, rbf is not None, t, (err or "")[:200]


def main():
    print(f"=== Phase 5.0-A: mult param sweep, {len(VARIANTS)} variants ===")
    with ProcessPoolExecutor(max_workers=min(6, os.cpu_count() or 4)) as ex:
        futs = {ex.submit(build, v): v for v in VARIANTS}
        for f in as_completed(futs):
            tag, ok, t, err = f.result()
            print(f"  {tag:12s} {'OK' if ok else 'FAIL':4s} ({t:5.1f}s) {err if not ok else ''}")

    # Diff analysis
    base_path = os.path.join(RBF_DIR, "mult_param_base_9x9u.rbf")
    if not os.path.exists(base_path):
        print("base failed — abort analysis")
        return
    base = open(base_path, "rb").read()

    def cells(path):
        data = open(path, "rb").read()
        out = set()
        for i in range(32, min(len(base), len(data))):
            x = base[i] ^ data[i]
            if x:
                off = (i - 32) % 210
                if off >= 208:  # CRC strip
                    continue
                for bp in range(8):
                    if x >> bp & 1:
                        out.add((i, bp))
        return out

    results = {}
    for tag, *_ in VARIANTS:
        p = os.path.join(RBF_DIR, f"mult_param_{tag}.rbf")
        if not os.path.exists(p): continue
        results[tag] = sorted(cells(p))
        print(f"{tag:12s} delta_vs_base = {len(results[tag])} cells")

    outjson = "results/mult_param_sweep.json"
    os.makedirs("results", exist_ok=True)
    with open(outjson, "w") as f:
        json.dump(results, f, indent=1)
    print(f"\nArchived {outjson}")


if __name__ == "__main__":
    main()
