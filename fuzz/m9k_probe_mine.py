# SPDX-License-Identifier: GPL-3.0-or-later
"""Phase 3.27 — first M9K CRAM probe.

Compile a minimal single-altsyncram design at a few known M9K positions
under DEVICE=EP4CE10F17C8 (M9K columns are X=15 and X=27, both CE6-illegal
without jailbreak). Diff against a no-M9K baseline to find which CRAM
bytes encode "M9K active at (X, Y)".

Probe positions chosen from the existing CE10 probe_blocks fitter report:
  M9K_X15_Y14_N0 / M9K_X15_Y16_N0 / M9K_X15_Y18_N0 / M9K_X27_Y16_N0
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from compile import compile_and_export
from config import RBF_DIR

CE10_DEVICE = "EP4CE10F17C8"
FAMILY = "Cyclone IV E"

PINS = {
    "clk":  "PIN_E1",
    "we":   "PIN_E15",
    "addr0":"PIN_E16", "addr1":"PIN_M16", "addr2":"PIN_M15",
    "din0": "PIN_N13",
    "dout0":"PIN_G15",
}

PROBES = [(15, 3), (15, 7), (15, 11), (15, 14), (15, 16), (15, 18), (15, 19), (27, 16)]


M9K_VERILOG = """\
module fuzz_top(
    input clk, input we,
    input addr0, input addr1, input addr2,
    input din0,
    output dout0
);
    wire [7:0] addr = {5'b00000, addr2, addr1, addr0};
    wire [3:0] din  = {3'b000, din0};
    wire [3:0] q;
    altsyncram #(
        .operation_mode("SINGLE_PORT"),
        .width_a(4), .widthad_a(8), .numwords_a(256),
        .ram_block_type("M9K"),
        .outdata_reg_a("UNREGISTERED"),
        .init_file("UNUSED")
    ) u (
        .clock0(clk), .address_a(addr), .data_a(din),
        .wren_a(we), .q_a(q)
    );
    assign dout0 = ^q;
endmodule
"""

EMPTY_VERILOG = """\
module fuzz_top(
    input clk, input we,
    input addr0, input addr1, input addr2,
    input din0,
    output dout0
);
    assign dout0 = clk ^ we ^ addr0 ^ addr1 ^ addr2 ^ din0;
endmodule
"""


def gen_qsf(m9k_x=None, m9k_y=None) -> str:
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
    for sig, pin in PINS.items():
        lines.append(f'set_location_assignment {pin} -to {sig}')
    if m9k_x is not None:
        lines.append(f'set_location_assignment M9K_X{m9k_x}_Y{m9k_y}_N0 -to "u"')
    return '\n'.join(lines) + '\n'


def compile_one(tag, verilog, qsf):
    out = os.path.join(RBF_DIR, f"{tag}.rbf")
    if os.path.exists(out):
        print(f"  cached {tag}")
        return out
    print(f"  compiling {tag}...", flush=True)
    rbf, t, err = compile_and_export(tag, verilog, qsf, rbf_output=out)
    if rbf is None:
        print(f"    FAIL ({t:.1f}s) {(err or '')[:120]}")
        return None
    print(f"    OK ({t:.1f}s)")
    return rbf


def main():
    print("=== M9K CRAM probe (Phase 3.27 step 1) ===")
    base = compile_one("m9k_baseline_empty", EMPTY_VERILOG, gen_qsf())
    if base is None:
        return
    z = open(base, "rb").read()
    print()
    for x, y in PROBES:
        tag = f"m9k_probe_X{x}_Y{y}_N0"
        rbf = compile_one(tag, M9K_VERILOG, gen_qsf(x, y))
        if rbf is None:
            continue
        r = open(rbf, "rb").read()
        diffs = [i for i in range(len(z)) if z[i] != r[i]]
        print(f"  X={x} Y={y}: {len(diffs)} diff bytes, "
              f"range 0x{min(diffs):X}..0x{max(diffs):X}" if diffs else f"  X={x} Y={y}: NO DIFF")
        if diffs:
            # Cluster diffs into bands of >=8 contiguous gap
            bands = []
            cur = [diffs[0]]
            for d in diffs[1:]:
                if d - cur[-1] <= 8:
                    cur.append(d)
                else:
                    bands.append(cur)
                    cur = [d]
            bands.append(cur)
            for b in sorted(bands, key=lambda x: -len(x))[:5]:
                print(f"    band 0x{b[0]:X}..0x{b[-1]:X} ({len(b)} cells)")


if __name__ == "__main__":
    main()
