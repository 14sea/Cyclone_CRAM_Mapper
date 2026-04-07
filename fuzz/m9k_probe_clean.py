# SPDX-License-Identifier: GPL-3.0-or-later
"""Phase 3.27 step 2 — clean M9K CRAM probe with VIRTUAL_PIN.

The original m9k_probe_mine.py had ~530 position cells per Y, dominated
by routing churn (auto-placed I/O paths to the M9K). This version marks
all top-level ports as VIRTUAL_PIN so Quartus skips I/O buffer/routing
to chip pins and the only thing varying between probes is the M9K
placement itself, hopefully exposing a clean (Y, stride) linear model.

We sweep many Y values at X=15 to make the stride visible.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from compile import compile_and_export
from config import RBF_DIR

CE10_DEVICE = "EP4CE10F17C8"
FAMILY = "Cyclone IV E"

PORTS = ["clk", "we", "addr0", "addr1", "addr2", "din0", "dout0"]

# X=15 column at every Y position the fitter accepts (M9Ks span Y bands)
PROBES_X15 = [(15, y) for y in (3, 7, 11, 14, 16, 18, 19)]
PROBES_X27 = [(27, 16), (27, 18)]
PROBES = PROBES_X15 + PROBES_X27

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
    # virtual pins: skip all I/O routing/buffer placement
    for p in PORTS:
        lines.append(f'set_instance_assignment -name VIRTUAL_PIN ON -to {p}')
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
        print(f"    FAIL ({t:.1f}s) {(err or '')[:160]}")
        return None
    print(f"    OK ({t:.1f}s)")
    return rbf


def main():
    print("=== M9K CRAM probe v2 (VIRTUAL_PIN, Phase 3.27 step 2) ===")
    base = compile_one("m9k_clean_baseline", EMPTY_VERILOG, gen_qsf())
    if base is None:
        return
    z = open(base, "rb").read()
    print()
    HEADER_END = 32 + 25 * 210
    diffs = {}
    for x, y in PROBES:
        tag = f"m9k_clean_X{x}_Y{y}_N0"
        rbf = compile_one(tag, M9K_VERILOG, gen_qsf(x, y))
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
        print(f"  X={x} Y={y}: {len(cells)} cells (post-header)")

    if len(diffs) < 2:
        return
    inter = set.intersection(*diffs.values())
    print(f"\n=== Intersection (universal M9K-on): {len(inter)} cells ===")
    x15 = [c for k, c in diffs.items() if k[0] == 15]
    if len(x15) >= 2:
        inter15 = set.intersection(*x15)
        print(f"=== X=15 column intersection: {len(inter15)} cells "
              f"(+{len(inter15 - inter)} unique to X=15) ===")
    print("\n=== Per-probe position cells (probe \\ universal) ===")
    for k, cells in diffs.items():
        print(f"  {k}: {len(cells - inter)} cells")


if __name__ == "__main__":
    main()
