# SPDX-License-Identifier: GPL-3.0-or-later
"""Phase 3.27 follow-up: discover real LOC name for embedded multiplier.

mult_probe_clean.py hit "illegal location" on MULT_X20_Y*_N0. Strategy:
compile an lpm_mult with NO location constraint, let Quartus auto-place,
then grep the fit report for whatever placement name it chose. Plug
that back into mult_probe_clean.py.

One compile, VIRTUAL_PIN so no real pins needed.
"""
import os, re, sys, glob
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

QSF = f"""\
set_global_assignment -name FAMILY "{FAMILY}"
set_global_assignment -name DEVICE {CE10_DEVICE}
set_global_assignment -name TOP_LEVEL_ENTITY fuzz_top
set_global_assignment -name VERILOG_FILE fuzz_top.v
set_global_assignment -name PROJECT_OUTPUT_DIRECTORY output_files
set_instance_assignment -name VIRTUAL_PIN ON -to clk
set_instance_assignment -name VIRTUAL_PIN ON -to a0
set_instance_assignment -name VIRTUAL_PIN ON -to a1
set_instance_assignment -name VIRTUAL_PIN ON -to b0
set_instance_assignment -name VIRTUAL_PIN ON -to b1
set_instance_assignment -name VIRTUAL_PIN ON -to p0
"""


def main():
    print("=== MULT LOC discovery (Phase 3.27 follow-up) ===")
    tag = "mult_loc_discover"
    out = os.path.join(RBF_DIR, f"{tag}.rbf")
    rbf, t, err = compile_and_export(tag, VERILOG, QSF, rbf_output=out)
    if rbf is None:
        print(f"compile FAIL ({t:.1f}s): {(err or '')[:400]}")
        return
    print(f"compile OK ({t:.1f}s)")

    # Scan work/ fit report + placement files for multiplier references
    patterns = [
        r"MULT[A-Z0-9_]*_X\d+_Y\d+_N\d+",
        r"DSPMULT[A-Z0-9_]*_X\d+_Y\d+_N\d+",
        r"MAC[A-Z0-9_]*_X\d+_Y\d+_N\d+",
        r"X\d+_Y\d+_N\d+.*\bmult\b",
    ]
    found = set()
    for fn in glob.glob("work/**/*.fit.rpt", recursive=True) + \
              glob.glob("work/**/*.map.rpt", recursive=True) + \
              glob.glob("work/**/*.place.rpt", recursive=True) + \
              glob.glob("work/**/*.pin", recursive=True):
        try:
            with open(fn, errors="replace") as f:
                txt = f.read()
        except Exception:
            continue
        for pat in patterns:
            for m in re.findall(pat, txt):
                found.add((fn, m))

    print(f"\nMultiplier placement names found: {len(found)}")
    for fn, m in sorted(found)[:40]:
        print(f"  {os.path.basename(fn)}: {m}")

    # Also grep for "u" (the lpm_mult instance) in fit report
    print("\nInstance 'u' references:")
    for fn in glob.glob("work/**/*.fit.rpt", recursive=True):
        with open(fn, errors="replace") as f:
            for line in f:
                if "|u|" in line and ("X" in line and "Y" in line):
                    print(f"  {line.strip()[:200]}")
                    break


if __name__ == "__main__":
    main()
