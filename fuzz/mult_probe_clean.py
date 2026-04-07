# SPDX-License-Identifier: GPL-3.0-or-later
"""Phase 3.27 — embedded-multiplier (X=20) CRAM probe.

Parallel to m9k_probe_clean.py: same VIRTUAL_PIN trick, instances an
lpm_mult at MULT_X20_Yy positions to find the multiplier-column
universal + position bits.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from compile import compile_and_export
from config import RBF_DIR

CE10_DEVICE = "EP4CE10F17C8"
FAMILY = "Cyclone IV E"

PORTS = ["clk", "a0", "a1", "b0", "b1", "p0"]

# X=20 mult column probes — try several Y rows
PROBES = [(20, y) for y in (4, 8, 12, 16, 20)]

MULT_VERILOG = """\
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

EMPTY_VERILOG = """\
module fuzz_top(
    input clk, input a0, input a1, input b0, input b1,
    output p0
);
    assign p0 = clk ^ a0 ^ a1 ^ b0 ^ b1;
endmodule
"""


def gen_qsf(mx=None, my=None) -> str:
    lines = [
        f'set_global_assignment -name FAMILY "{FAMILY}"',
        f'set_global_assignment -name DEVICE {CE10_DEVICE}',
        'set_global_assignment -name TOP_LEVEL_ENTITY fuzz_top',
        'set_global_assignment -name VERILOG_FILE fuzz_top.v',
        'set_global_assignment -name PROJECT_OUTPUT_DIRECTORY output_files',
        'set_global_assignment -name MIN_CORE_JUNCTION_TEMP 0',
        'set_global_assignment -name MAX_CORE_JUNCTION_TEMP 85',
        'set_global_assignment -name ERROR_CHECK_FREQUENCY_DIVISOR 1',
        'set_global_assignment -name STRATIX_DEVICE_IO_STANDARD "3.3-V LVTTL"',
        'set_global_assignment -name SEED 1',
    ]
    for p in PORTS:
        lines.append(f'set_instance_assignment -name VIRTUAL_PIN ON -to {p}')
    if mx is not None:
        lines.append(f'set_location_assignment MULT_X{mx}_Y{my}_N0 -to "u"')
    return '\n'.join(lines) + '\n'


def compile_one(tag, verilog, qsf):
    out = os.path.join(RBF_DIR, f"{tag}.rbf")
    if os.path.exists(out):
        print(f"  cached {tag}")
        return out
    print(f"  compiling {tag}...", flush=True)
    rbf, t, err = compile_and_export(tag, verilog, qsf, rbf_output=out)
    if rbf is None:
        print(f"    FAIL ({t:.1f}s) {(err or '')[:160]}")
        return None
    print(f"    OK ({t:.1f}s)")
    return rbf


def main():
    print("=== MULT X=20 CRAM probe (Phase 3.27) ===")
    base = compile_one("mult_clean_baseline", EMPTY_VERILOG, gen_qsf())
    if base is None:
        return
    z = open(base, "rb").read()
    HEADER_END = 32 + 25 * 210
    diffs = {}
    for x, y in PROBES:
        tag = f"mult_clean_X{x}_Y{y}_N0"
        rbf = compile_one(tag, MULT_VERILOG, gen_qsf(x, y))
        if rbf is None:
            continue
        r = open(rbf, "rb").read()
        cells = set()
        for i in range(HEADER_END, len(z)):
            xb = z[i] ^ r[i]
            if xb:
                for bp in range(8):
                    if xb >> bp & 1:
                        cells.add((i, bp))
        diffs[(x, y)] = cells
        print(f"  X={x} Y={y}: {len(cells)} cells")
    if len(diffs) >= 2:
        inter = set.intersection(*diffs.values())
        print(f"\n  intersection: {len(inter)} universal MULT cells")


if __name__ == "__main__":
    main()
