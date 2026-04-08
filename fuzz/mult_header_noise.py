# SPDX-License-Identifier: GPL-3.0-or-later
"""Phase 5.0-A verification: null hypothesis test for byte 44/73 mult
'signed bit' finding. Compile same 9x9u mult design twice with
different QSF seeds. Diff byte 44/73 — if non-zero, the 4-cell
SIGNED_CORE is Quartus header-rewrite noise, not a real signed field.
"""
import os, sys
from concurrent.futures import ProcessPoolExecutor, as_completed
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from compile import compile_and_export
from config import RBF_DIR

FAMILY = "Cyclone IV E"
DEVICE = "EP4CE10F17C8"
NODE = "lpm_mult:u|mult_qpl:auto_generated|mac_mult1"
LOC = "DSPMULT_X20_Y10_N0"

VERILOG = """\
module fuzz_top(input clk, input a0, input a1, input b0, input b1, output p0);
    wire [8:0] a = {{7{1'b0}}, a1, a0};
    wire [8:0] b = {{7{1'b0}}, b1, b0};
    wire [17:0] p;
    lpm_mult #(.lpm_widtha(9), .lpm_widthb(9), .lpm_widthp(18),
               .lpm_representation("UNSIGNED"), .lpm_type("LPM_MULT")) u
              (.dataa(a), .datab(b), .result(p));
    assign p0 = ^p;
endmodule
"""

def qsf(seed):
    return f"""\
set_global_assignment -name FAMILY "{FAMILY}"
set_global_assignment -name DEVICE {DEVICE}
set_global_assignment -name TOP_LEVEL_ENTITY fuzz_top
set_global_assignment -name VERILOG_FILE fuzz_top.v
set_global_assignment -name PROJECT_OUTPUT_DIRECTORY output_files
set_global_assignment -name SEED {seed}
set_location_assignment PIN_E1  -to clk
set_location_assignment PIN_E16 -to a0
set_location_assignment PIN_M16 -to a1
set_location_assignment PIN_M15 -to b0
set_location_assignment PIN_E15 -to b1
set_location_assignment PIN_G15 -to p0
set_location_assignment {LOC} -to "{NODE}"
"""

def build(seed):
    tag = f"mult_noise_seed{seed}"
    out = os.path.join(RBF_DIR, f"{tag}.rbf")
    rbf, t, err = compile_and_export(tag, VERILOG, qsf(seed), rbf_output=out)
    return seed, rbf is not None, t, (err or "")[:200]

def main():
    seeds = [1, 2, 3, 4, 5]
    with ProcessPoolExecutor(max_workers=5) as ex:
        futs = {ex.submit(build, s): s for s in seeds}
        for f in as_completed(futs):
            s, ok, t, err = f.result()
            print(f"  seed {s} {'OK' if ok else 'FAIL'} ({t:.1f}s) {err if not ok else ''}")

    # Diff against seed1; report byte 44/73 flip counts
    base = open(os.path.join(RBF_DIR, "mult_noise_seed1.rbf"), "rb").read()
    print("\nNoise check vs seed1 (full diff + byte 44/73 specifically):")
    for s in seeds[1:]:
        path = os.path.join(RBF_DIR, f"mult_noise_seed{s}.rbf")
        if not os.path.exists(path): continue
        data = open(path, "rb").read()
        total = 0
        hdr = []
        for i in range(32, min(len(base), len(data))):
            x = base[i] ^ data[i]
            if x:
                off=(i-32)%210
                if off>=208: continue
                total += bin(x).count("1")
                if i in (44, 73):
                    for bp in range(8):
                        if x>>bp&1: hdr.append((i,bp))
        print(f"  seed{s}: total={total} bits, byte44/73 hits={hdr}")


if __name__ == "__main__":
    main()
