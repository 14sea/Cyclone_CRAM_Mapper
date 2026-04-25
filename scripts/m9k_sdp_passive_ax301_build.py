# SPDX-License-Identifier: GPL-3.0-or-later
"""SDP 4x2048 passive variant at AX301 pinout for cross-design test.

Same Verilog skeleton as `m9k_sdp_blink_build.py` (4-pin AX301 pinout)
but with M9K output register ENABLED (`outdata_reg_b = "CLOCK0"`) and
non-trivial byteena.  Goal: a same-pinout, same-site, different-feature
fixture so the directive generalization test isolates feature-usage
dependency from pinout dependency.

Output: `tmp/m9k_sdp_passive_ax301_4x2048_X{x}_Y{y}_N{n}.rbf`.
"""
from __future__ import annotations
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "fuzz"))
from compile import setup_project, compile_full, generate_rbf

WORK_ROOT = ROOT / "tmp"
PINS = {"CLK": "PIN_E1", "KEY2": "PIN_E16", "KEY3": "PIN_M16",
        "LED0": "PIN_G15"}

DEFAULT_SITE = (15, 16, 0)
SITE_X, SITE_Y, SITE_N = DEFAULT_SITE


def _verilog() -> str:
    return """\
// Auto-generated m9k_sdp_passive_ax301_4x2048.v.
module m9k_sdp_passive_ax301(
    input  wire CLK,
    input  wire KEY2,
    input  wire KEY3,
    output wire LED0
);
    reg [27:0] counter = 28'd0;
    always @(posedge CLK) counter <= counter + 1'b1;

    wire [10:0] addrr = counter[27 -: 11];
    wire [10:0] addrw = counter[10:0];
    wire [3:0]  din_w = {2{KEY3, KEY2}};
    wire        we_w  = ~KEY2;

    wire [3:0] dout_b;
    reg  [3:0] dout_r;
    always @(posedge CLK) dout_r <= dout_b;
    // Drive LED0 by XOR of all 4 output bits so Quartus must keep them.
    assign LED0 = ^dout_r;

    altsyncram #(
        .operation_mode("DUAL_PORT"),
        .width_a(4), .widthad_a(11), .numwords_a(2048),
        .width_b(4), .widthad_b(11), .numwords_b(2048),
        .lpm_type("altsyncram"),
        .ram_block_type("M9K"),
        .address_reg_b("CLOCK0"),
        .outdata_reg_b("CLOCK0"),
        .read_during_write_mode_mixed_ports("DONT_CARE"),
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
    # Same MIF shape as blink (low half=0, high half=F) so INIT-driven
    # cells overlap maximally; differences come from feature usage only.
    depth = 2048
    width = 4
    lines = [
        f"DEPTH = {depth};",
        f"WIDTH = {width};",
        "ADDRESS_RADIX = HEX;",
        "DATA_RADIX = HEX;",
        "CONTENT BEGIN",
        f"  [0..{(depth // 2) - 1:X}] : 0;",
        f"  [{depth // 2:X}..{depth - 1:X}] : F;",
        "END;",
    ]
    return "\n".join(lines) + "\n"


def _qsf() -> str:
    lines = [
        'set_global_assignment -name FAMILY "Cyclone IV E"',
        "set_global_assignment -name DEVICE EP4CE6F17C8",
        "set_global_assignment -name TOP_LEVEL_ENTITY m9k_sdp_passive_ax301",
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


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--site", default="15,16,0")
    args = ap.parse_args()
    global SITE_X, SITE_Y, SITE_N
    SITE_X, SITE_Y, SITE_N = (int(s) for s in args.site.split(","))

    work = WORK_ROOT / f"m9k_sdp_passive_ax301_X{SITE_X}_Y{SITE_Y}_N{SITE_N}"
    work.mkdir(parents=True, exist_ok=True)
    project = f"m9k_sdp_passive_ax301_X{SITE_X}_Y{SITE_Y}_N{SITE_N}"
    proj_dir = setup_project(project, _verilog(), _qsf(), str(work))
    (Path(proj_dir) / "mem_init.mif").write_text(_mif())
    print(f"=== building {project} @ X{SITE_X}_Y{SITE_Y}_N{SITE_N} ===",
          flush=True)
    ok, el, err = compile_full(project, proj_dir, timeout=300)
    if not ok:
        print(f"build failed after {el:.1f}s: {err}", flush=True)
        return 1
    rbf = generate_rbf(project, proj_dir, str(work / f"{project}.rbf"))
    if rbf is None:
        print("RBF generation failed", flush=True)
        return 1
    print(f"OK -> {rbf} ({el:.1f}s)", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
