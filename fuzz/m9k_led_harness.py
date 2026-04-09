#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Phase 5.2 observable silicon harness — M9K readout → AX301 LEDs.

A 9-bit address counter (divided from 50 MHz clock) walks through the
M9K addresses; dout[3:0] drives the 4 AX301 LEDs (G15/F16/F15/D16).
With the Stage B codec writing an address-echo init pattern into this
bitstream, the LEDs will visibly count upward ~1 Hz.

The altsyncram instance is shape-identical to m9k_init_harness.py
(9b×512, SINGLE_PORT, UNREGISTERED, init_file=m9k_init.mif) so Quartus
should auto-place at the same physical site and the existing
M9K_INIT_ANCHORS entry for (X27_Y4_N0, 9, 512) at anchor 261142 should
still apply. If not, we'll see LEDs that don't count.
"""
import os, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from compile import setup_project, compile_full, generate_rbf
from config import RBF_DIR

FAMILY = "Cyclone IV E"
DEVICE = "EP4CE10F17C8"

WIDTH = 9
DEPTH = 512
ADDR_BITS = 9

PINS = {
    "clk":    "PIN_E1",
    "led0":   "PIN_G15",
    "led1":   "PIN_F16",
    "led2":   "PIN_F15",
    "led3":   "PIN_D16",
}


def gen_mif():
    lines = [f"WIDTH = {WIDTH};", f"DEPTH = {DEPTH};",
             "ADDRESS_RADIX = HEX;", "DATA_RADIX = HEX;",
             "CONTENT BEGIN"]
    for w in range(DEPTH):
        lines.append(f"  {w:03X} : 000;")
    lines.append("END;")
    return "\n".join(lines) + "\n"


def gen_verilog():
    return f"""\
module fuzz_top(
    input  clk,
    output led0, output led1, output led2, output led3
);
    // ~0.75 Hz address stepping: 50 MHz / 2^26 ≈ 0.75 Hz
    reg [25:0] slow;
    always @(posedge clk) slow <= slow + 1'b1;

    reg [{ADDR_BITS-1}:0] addr;
    always @(posedge clk)
        if (slow == {{26{{1'b1}}}}) addr <= addr + 1'b1;

    wire [{WIDTH-1}:0] dout;
    assign led0 = dout[0];
    assign led1 = dout[1];
    assign led2 = dout[2];
    assign led3 = dout[3];

    altsyncram #(
        .operation_mode("SINGLE_PORT"),
        .width_a({WIDTH}), .widthad_a({ADDR_BITS}), .numwords_a({DEPTH}),
        .lpm_type("altsyncram"),
        .ram_block_type("M9K"),
        .outdata_reg_a("UNREGISTERED"),
        .init_file("m9k_init.mif"),
        .intended_device_family("{FAMILY}")
    ) u (
        .clock0(clk), .address_a(addr), .data_a({{{WIDTH}{{1'b0}}}}),
        .wren_a(1'b0), .q_a(dout),
        .aclr0(1'b0), .aclr1(1'b0),
        .addressstall_a(1'b0), .addressstall_b(1'b0),
        .byteena_a(1'b1), .byteena_b(1'b1),
        .address_b({{{ADDR_BITS}{{1'b0}}}}), .data_b({{{WIDTH}{{1'b0}}}}),
        .clock1(1'b1), .clocken0(1'b1), .clocken1(1'b1),
        .clocken2(1'b1), .clocken3(1'b1), .eccstatus(),
        .q_b(), .rden_a(1'b1), .rden_b(1'b1), .wren_b(1'b0)
    );
endmodule
"""


def gen_qsf():
    lines = [
        f'set_global_assignment -name FAMILY "{FAMILY}"',
        f'set_global_assignment -name DEVICE {DEVICE}',
        'set_global_assignment -name TOP_LEVEL_ENTITY fuzz_top',
        'set_global_assignment -name VERILOG_FILE fuzz_top.v',
        'set_global_assignment -name MIF_FILE m9k_init.mif',
        'set_global_assignment -name PROJECT_OUTPUT_DIRECTORY output_files',
        # F16 is nCEO by default; AX301 wires it to LED[1]. Release it.
        'set_global_assignment -name CYCLONEII_RESERVE_NCEO_AFTER_CONFIGURATION "USE AS REGULAR IO"',
    ]
    for sig, pin in PINS.items():
        lines.append(f'set_location_assignment {pin} -to {sig}')
    return "\n".join(lines) + "\n"


def build(tag):
    proj_dir = setup_project(tag, gen_verilog(), gen_qsf())
    with open(os.path.join(proj_dir, "m9k_init.mif"), "w") as f:
        f.write(gen_mif())
    with open(os.path.join(proj_dir, f"{tag}.qpf"), "w") as f:
        f.write(f'PROJECT_REVISION = "{tag}"\n')
    t0 = time.time()
    ok, elapsed, err = compile_full(tag, proj_dir)
    if not ok:
        return None, elapsed, err
    out = os.path.join(RBF_DIR, f"{tag}.rbf")
    rbf = generate_rbf(tag, proj_dir, out)
    return rbf, elapsed, ""


if __name__ == "__main__":
    rbf, t, err = build("m9k_led_zero")
    if rbf is None:
        print(f"FAIL ({t:.1f}s): {err[:400]}")
        sys.exit(1)
    print(f"OK ({t:.1f}s) -> {rbf}")
    # Report the physical M9K site so we know if anchor 261142 still applies
    import glob
    rpt = glob.glob("work/m9k_led_zero/output_files/*.fit.rpt")
    if rpt:
        with open(rpt[0], errors="replace") as f:
            for line in f:
                if "ALTSYNCRAM" in line and "M9K_X" in line:
                    # pull the M9K_X.._Y.._N.. token
                    for tok in line.split(";"):
                        tok = tok.strip()
                        if tok.startswith("M9K_X"):
                            print(f"physical site: {tok}")
                            break
                    break
