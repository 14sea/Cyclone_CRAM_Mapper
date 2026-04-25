# SPDX-License-Identifier: GPL-3.0-or-later
"""TDP (BIDIR_DUAL_PORT) M9K blink-gold builder.

Quartus-gold exerciser for altsyncram `operation_mode = "BIDIR_DUAL_PORT"`
at a specified M9K site (default X15_Y10_N0).  Writes a live `BIDIR_DUAL_PORT`
M9K into the RBF whose port-A read of a MIF-pre-loaded memory makes LED0
toggle at counter[27] rate (~2.68 s on / 2.68 s off at 50 MHz).

Design (TDP 16x32):
  * port A — `addra = counter[27 -: 5]` (read addr; MSB = counter[27]
    toggles at ~0.186 Hz).
  * port B — `addrb = {counter[27], counter[5:2]}` (different bit
    window so the Fitter can't see addra/addrb as the same wire, but
    MSB still tracks counter[27] — both ports' outputs blink in sync).
  * `wren_a = ~KEY2`, `wren_b = ~KEY3` (active-low keys idle → wren=0
    → MIF intact).  Live wren / din keep Quartus from folding the M9K.
  * MIF: addresses 0..15 = 0x0000; addresses 16..31 = 0xFFFF — so both
    `q_a[0]` and `q_b[0]` flip with their address MSB (= counter[27]).
  * `LED0 = dout_a_r[0] | dout_b_r[0]` — OR of both registered ports.
    Since both MSBs equal counter[27], OR = counter[27] = visible blink.
    Both ports' q outputs are referenced, so neither port can be
    eliminated by the Fitter.

A successful blink at (16, 32) is the "functional HW PASS" that promotes
`_M9K_MODE_FUNCTIONAL_VALIDATED_TDP` at the flashed site from
codec-verified-only to silicon-validated.
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
// Auto-generated m9k_tdp_blink_16x32.v — M9K BIDIR_DUAL_PORT data-path smoke.
module m9k_tdp_blink(
    input  wire CLK,
    input  wire KEY2,
    input  wire KEY3,
    output wire LED0
);
    reg [27:0] counter = 28'd0;
    always @(posedge CLK) counter <= counter + 1'b1;

    // Port A read address — top 5 counter bits, MSB = counter[27]
    // flips at ~0.186 Hz.
    wire [4:0] addra = counter[27 -: 5];
    // Port B address — distinct bit window, but MSB also tracks
    // counter[27] so both ports' MIF reads blink in sync.
    wire [4:0] addrb = {counter[27], counter[5:2]};

    wire        wren_a = ~KEY2;   // idle 0; press KEY2 to inject writes
    wire        wren_b = ~KEY3;   // idle 0; press KEY3 to inject writes
    wire [15:0] din_a  = {16{KEY3}};
    wire [15:0] din_b  = {16{KEY2}};

    wire [15:0] q_a, q_b;
    reg  [15:0] dout_a_r, dout_b_r;
    always @(posedge CLK) begin
        dout_a_r <= q_a;
        dout_b_r <= q_b;
    end
    // OR keeps both ports' outputs observable.  Both MSBs equal
    // counter[27] (MIF is split low/high half all-0 / all-F), so
    // OR = counter[27] = visible 0.186 Hz blink.
    assign LED0 = dout_a_r[0] | dout_b_r[0];

    altsyncram #(
        .operation_mode("BIDIR_DUAL_PORT"),
        .width_a(16), .widthad_a(5), .numwords_a(32),
        .width_b(16), .widthad_b(5), .numwords_b(32),
        .lpm_type("altsyncram"),
        .ram_block_type("M9K"),
        .outdata_reg_a("UNREGISTERED"),
        .outdata_reg_b("UNREGISTERED"),
        .address_reg_b("CLOCK0"),
        .indata_reg_b("CLOCK0"),
        .wrcontrol_wraddress_reg_b("CLOCK0"),
        .read_during_write_mode_port_a("OLD_DATA"),
        .read_during_write_mode_port_b("OLD_DATA"),
        .read_during_write_mode_mixed_ports("OLD_DATA"),
        .clock_enable_input_a("NORMAL"),
        .clock_enable_input_b("NORMAL"),
        .clock_enable_output_a("NORMAL"),
        .clock_enable_output_b("NORMAL"),
        .init_file("mem_init.mif"),
        .intended_device_family("Cyclone IV E")
    ) u (
        .clock0(CLK), .clock1(1'b1),
        .address_a(addra), .data_a(din_a), .wren_a(wren_a), .q_a(q_a),
        .address_b(addrb), .data_b(din_b), .wren_b(wren_b), .q_b(q_b),
        .aclr0(1'b0), .aclr1(1'b0),
        .addressstall_a(1'b0), .addressstall_b(1'b0),
        .byteena_a(1'b1), .byteena_b(1'b1),
        .clocken0(1'b1), .clocken1(1'b1),
        .clocken2(1'b1), .clocken3(1'b1), .eccstatus(),
        .rden_a(1'b1), .rden_b(1'b1)
    );
endmodule
"""


def _mif() -> str:
    depth = 32
    width = 16
    lines = [
        f"DEPTH = {depth};",
        f"WIDTH = {width};",
        "ADDRESS_RADIX = HEX;",
        "DATA_RADIX = HEX;",
        "CONTENT BEGIN",
    ]
    for i in range(depth):
        v = 0x0000 if i < depth // 2 else 0xFFFF
        lines.append(f"  {i:02X} : {v:04X};")
    lines.append("END;")
    return "\n".join(lines) + "\n"


def _qsf() -> str:
    lines = [
        'set_global_assignment -name FAMILY "Cyclone IV E"',
        "set_global_assignment -name DEVICE EP4CE6F17C8",
        "set_global_assignment -name TOP_LEVEL_ENTITY m9k_tdp_blink",
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
    work = WORK_ROOT / f"m9k_tdp_blink_16x32{site_suffix}"
    work.mkdir(parents=True, exist_ok=True)
    project = f"m9k_tdp_blink_16x32{site_suffix}"
    proj_dir = setup_project(project, _verilog(), _qsf(), str(work))
    (Path(proj_dir) / "mem_init.mif").write_text(_mif())
    ok, el, err = compile_full(project, proj_dir, timeout=300)
    if not ok:
        raise RuntimeError(f"TDP 16x32 build failed after {el:.1f}s: {err}")
    rbf = generate_rbf(project, proj_dir, str(work / f"{project}.rbf"))
    if rbf is None:
        raise RuntimeError("TDP 16x32 RBF generation failed")
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

    print(f"=== building m9k_tdp_blink_16x32 @ X{SITE_X}_Y{SITE_Y}_N{SITE_N} ===",
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
