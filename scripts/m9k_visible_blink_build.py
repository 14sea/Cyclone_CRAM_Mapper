# SPDX-License-Identifier: GPL-3.0-or-later
r"""Visible-blink 2-M9K reference for Step F silicon validation.

Builds a 2-M9K Quartus reference where LED0 visibly blinks at ~1.5 Hz
when M9K is correctly configured, and freezes (stuck or random) when
M9K mode bits are missing.  Used to silicon-validate the
DESIGN_BLOCK_BAND_PACK directive end-to-end.

Verilog: 2 SDP RAMs at LOC'd sites; counter[27:18] sweeps the read
address; LED0 = bit-0 of dout_a XOR bit-0 of dout_b.  RAM contents are
init'd so that bit-0 alternates with address bit-5 / bit-6 — gives a
visible blink rate visible to the eye.

Usage:
    python3 scripts/m9k_visible_blink_build.py --site-a 15,4 --site-b 15,10
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WORK_ROOT = ROOT / "tmp"


def render_verilog() -> str:
    return r"""
module m9k_visible(
    input  wire CLK,
    input  wire KEY2,
    input  wire KEY3,
    output wire LED0
);
    reg [27:0] counter = 28'd0;
    always @(posedge CLK) counter <= counter + 1'b1;

    wire [9:0] raddr_a = counter[27 -: 10];
    wire [9:0] raddr_b = raddr_a ^ {10{KEY2}};  // KEY2 inverts B's addr

    (* ramstyle = "M9K" *) reg [7:0] mem_a [0:1023];
    (* ramstyle = "M9K" *) reg [7:0] mem_b [0:1023];
    integer i;
    initial begin
        for (i = 0; i < 1024; i = i + 1) begin
            mem_a[i] = {7'd0, i[5]};  // bit 0 alternates with addr bit 5
            mem_b[i] = {7'd0, i[6]};  // bit 0 alternates with addr bit 6
        end
    end

    reg [7:0] dout_a_r, dout_b_r;
    always @(posedge CLK) begin
        dout_a_r <= mem_a[raddr_a];
        dout_b_r <= mem_b[raddr_b];
    end

    assign LED0 = dout_a_r[0] ^ dout_b_r[0];
endmodule
"""


def render_qsf(x_a: int, y_a: int, x_b: int, y_b: int) -> str:
    return f"""\
set_global_assignment -name FAMILY "Cyclone IV E"
set_global_assignment -name DEVICE EP4CE6F17C8
set_global_assignment -name TOP_LEVEL_ENTITY m9k_visible
set_global_assignment -name VERILOG_FILE fuzz_top.v
set_global_assignment -name PROJECT_OUTPUT_DIRECTORY output_files
set_global_assignment -name STRATIX_DEVICE_IO_STANDARD "3.3-V LVTTL"
set_global_assignment -name SEED 1
set_location_assignment PIN_E1  -to CLK
set_location_assignment PIN_E16 -to KEY2
set_location_assignment PIN_M16 -to KEY3
set_location_assignment PIN_G15 -to LED0
set_location_assignment M9K_X{x_a}_Y{y_a}_N0 -to "altsyncram:mem_a_rtl_0"
set_location_assignment M9K_X{x_b}_Y{y_b}_N0 -to "altsyncram:mem_b_rtl_0"
"""


def build(x_a: int, y_a: int, x_b: int, y_b: int, tag: str) -> Path | None:
    work = WORK_ROOT / f"m9k_visible_{tag}"
    work.mkdir(parents=True, exist_ok=True)
    (work / "fuzz_top.v").write_text(render_verilog())
    (work / "fuzz_top.qsf").write_text(render_qsf(x_a, y_a, x_b, y_b))
    rbf = work / f"m9k_visible_{tag}.rbf"
    if rbf.exists():
        print(f"  exists: {rbf.relative_to(ROOT)}")
        return rbf
    qbin = Path.home() / "intelFPGA_lite/21.1/quartus/bin"
    env = {**os.environ, "PATH": f"{qbin}:" + os.environ.get("PATH", "")}
    for tool in ("quartus_map", "quartus_fit", "quartus_asm"):
        r = subprocess.run([str(qbin / tool), "fuzz_top",
                            "--read_settings_files=on",
                            "--write_settings_files=off"],
                           cwd=work, env=env, capture_output=True, text=True)
        if r.returncode != 0:
            print(f"  FAIL {tool}: {r.stderr[-300:]}")
            return None
    r = subprocess.run([str(qbin / "quartus_cpf"), "-c",
                        "-o", "bitstream_compression=off",
                        "output_files/fuzz_top.sof", str(rbf)],
                       cwd=work, env=env, capture_output=True, text=True)
    if r.returncode != 0 or not rbf.exists():
        print(f"  FAIL cpf: {r.stderr[-300:]}")
        return None
    return rbf


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--site-a", required=True)
    ap.add_argument("--site-b", required=True)
    ap.add_argument("--tag", default=None)
    args = ap.parse_args()
    x_a, y_a = (int(s) for s in args.site_a.split(","))
    x_b, y_b = (int(s) for s in args.site_b.split(","))
    tag = args.tag or f"X{x_a}Y{y_a}_X{x_b}Y{y_b}"
    print(f"=== Visible 2-M9K blink at X{x_a}_Y{y_a} + X{x_b}_Y{y_b} ===")
    rbf = build(x_a, y_a, x_b, y_b, tag)
    if rbf:
        print(f"  OK -> {rbf.relative_to(ROOT)}")
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
