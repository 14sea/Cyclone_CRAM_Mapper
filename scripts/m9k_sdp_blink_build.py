# SPDX-License-Identifier: GPL-3.0-or-later
"""SDP (DUAL_PORT) M9K blink-gold builder.

Quartus-gold exerciser for altsyncram `operation_mode = "DUAL_PORT"` at a
specified M9K site (default X15_Y10_N0).  Writes a live `DUAL_PORT` M9K
into the RBF whose port-B read of a MIF-pre-loaded memory makes LED0
toggle at counter[27] rate (~2.68 s on / 2.68 s off at 50 MHz).

Design:
  * port A (write side): wraddr = counter[10:0], din = {4{KEY3}},
    wren = ~KEY2 — keeps Quartus from folding the RAM.  With KEY2 idle
    (active-low, so wren=0) the MIF contents stay intact.
  * port B (read side):  rdaddr = counter[27 -: 11], q_b → dout_r → LED0[0].
  * MIF: low half (addr 0..1023) = 0x0; high half (1024..2047) = 0xF.
    LED0 = dout_r[0] → toggles when rdaddr MSB = counter[27] flips.

A successful blink at (4, 2048) is the "functional HW PASS" that
promotes `_M9K_MODE_FUNCTIONAL_VALIDATED_SDP` at the flashed site from
fabric-safety-only to silicon-validated.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "fuzz"))

from compile import setup_project, compile_full, generate_rbf

WORK_ROOT = ROOT / "tmp"

DEFAULT_SITE = (15, 10, 0)
SITE_X, SITE_Y, SITE_N = DEFAULT_SITE

PINS = {
    "CLK":  "PIN_E1",
    "KEY2": "PIN_E16",
    "KEY3": "PIN_M16",
    "LED0": "PIN_G15",
}


def _verilog() -> str:
    return """\
// Auto-generated m9k_sdp_blink_4x2048.v — M9K DUAL_PORT data-path smoke.
module m9k_sdp_blink(
    input  wire CLK,
    input  wire KEY2,
    input  wire KEY3,
    output wire LED0
);
    reg [27:0] counter = 28'd0;
    always @(posedge CLK) counter <= counter + 1'b1;

    // Port B read address walks through all 2048 words, MSB toggling
    // at ~0.186 Hz.  MIF splits low/high halves so dout[0] flips cleanly.
    wire [10:0] addrr = counter[27 -: 11];
    // Port A write address walks low 11 counter bits so the write
    // traffic is "live" and Quartus can't fold the RAM away.
    wire [10:0] addrw = counter[10:0];
    wire [3:0]  din_w = {4{KEY3}};
    wire        we_w  = ~KEY2;

    wire [3:0] dout_b;
    reg  [3:0] dout_r;
    always @(posedge CLK) dout_r <= dout_b;
    assign LED0 = dout_r[0];

    altsyncram #(
        .operation_mode("DUAL_PORT"),
        .width_a(4), .widthad_a(11), .numwords_a(2048),
        .width_b(4), .widthad_b(11), .numwords_b(2048),
        .lpm_type("altsyncram"),
        .ram_block_type("M9K"),
        .address_reg_b("CLOCK0"),
        .outdata_reg_b("UNREGISTERED"),
        .read_during_write_mode_mixed_ports("OLD_DATA"),
        .clock_enable_input_a("NORMAL"),
        .clock_enable_input_b("NORMAL"),
        .clock_enable_output_a("NORMAL"),
        .clock_enable_output_b("NORMAL"),
        .init_file("mem_init.mif"),
        .intended_device_family("Cyclone IV E")
    ) u (
        .clock0(CLK),
        .address_a(addrw), .data_a(din_w), .wren_a(we_w),
        .address_b(addrr), .q_b(dout_b),
        .aclr0(1'b0), .aclr1(1'b0),
        .addressstall_a(1'b0), .addressstall_b(1'b0),
        .byteena_a(1'b1), .byteena_b(1'b1),
        .clock1(1'b1), .clocken0(1'b1), .clocken1(1'b1),
        .clocken2(1'b1), .clocken3(1'b1), .eccstatus(),
        .data_b(4'b0), .q_a(),
        .rden_a(1'b1), .rden_b(1'b1), .wren_b(1'b0)
    );
endmodule
"""


def _mif() -> str:
    depth = 2048
    width = 4
    lines = [
        f"DEPTH = {depth};",
        f"WIDTH = {width};",
        "ADDRESS_RADIX = HEX;",
        "DATA_RADIX = HEX;",
        "CONTENT BEGIN",
    ]
    for i in range(depth):
        v = 0x0 if i < depth // 2 else 0xF
        lines.append(f"  {i:03X} : {v:X};")
    lines.append("END;")
    return "\n".join(lines) + "\n"


def _qsf() -> str:
    lines = [
        'set_global_assignment -name FAMILY "Cyclone IV E"',
        "set_global_assignment -name DEVICE EP4CE6F17C8",
        "set_global_assignment -name TOP_LEVEL_ENTITY m9k_sdp_blink",
        "set_global_assignment -name VERILOG_FILE fuzz_top.v",
        "set_global_assignment -name MIF_FILE mem_init.mif",
        "set_global_assignment -name PROJECT_OUTPUT_DIRECTORY output_files",
        'set_global_assignment -name STRATIX_DEVICE_IO_STANDARD "3.3-V LVTTL"',
        "set_global_assignment -name SEED 1",
    ]
    for sig, pin in PINS.items():
        lines.append(f"set_location_assignment {pin} -to {sig}")
    lines.append(
        f'set_location_assignment M9K_X{SITE_X}_Y{SITE_Y}_N{SITE_N} -to "u"'
    )
    return "\n".join(lines) + "\n"


def build() -> Path:
    site_suffix = ""
    if (SITE_X, SITE_Y, SITE_N) != DEFAULT_SITE:
        site_suffix = f"_X{SITE_X}_Y{SITE_Y}_N{SITE_N}"
    work = WORK_ROOT / f"m9k_sdp_blink_4x2048{site_suffix}"
    work.mkdir(parents=True, exist_ok=True)
    project = f"m9k_sdp_blink_4x2048{site_suffix}"
    proj_dir = setup_project(project, _verilog(), _qsf(), str(work))
    (Path(proj_dir) / "mem_init.mif").write_text(_mif())
    ok, el, err = compile_full(project, proj_dir, timeout=300)
    if not ok:
        raise RuntimeError(f"SDP 4x2048 build failed after {el:.1f}s: {err}")
    rbf = generate_rbf(project, proj_dir, str(work / f"{project}.rbf"))
    if rbf is None:
        raise RuntimeError("SDP 4x2048 RBF generation failed")
    return Path(rbf)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--site", default="15,10,0",
                    help="M9K site X,Y,N (default 15,10,0).")
    args = ap.parse_args()

    global SITE_X, SITE_Y, SITE_N
    try:
        SITE_X, SITE_Y, SITE_N = (int(s) for s in args.site.split(","))
    except ValueError:
        ap.error(f"--site must be X,Y,N; got {args.site!r}")
        return 1

    print(f"=== building m9k_sdp_blink_4x2048 @ X{SITE_X}_Y{SITE_Y}_N{SITE_N} ===",
          flush=True)
    try:
        rbf = build()
        print(f"  OK -> {rbf}")
    except Exception as exc:
        print(f"  FAIL: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
