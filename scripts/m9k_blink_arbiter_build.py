# SPDX-License-Identifier: GPL-3.0-or-later
r"""Medium-complexity 2-M9K reference: 2 SDP RAMs + simple bus arbiter
+ pipeline registers + cross-RAM dependency.

Hypothesis (Tactic 2 from review): minimal m9k_blink emits ~16 block-
band cells per 2-M9K config, NEORV32 emits ~106 in M9K range.  The
gap might come from design context: pipeline registers, multi-clock-
domain fanout, datapath complexity.  This builder forces:

- A 2-stage pipeline between RAMs (RAM_A read → reg → RAM_B address)
- Bus arbiter selecting which RAM gets written each cycle
- Cross-RAM dependency (RAM_B's data depends on RAM_A's previous read)
- Both ports of each RAM exercised (input AND output regs declared)

If cell count grows from ~16 to ~50, design context is captured by
structural complexity, and Option 3-residual works with a sufficiently
complex clone.  If it stays ~16, the gap is NEORV32-specific.

Usage:
    python3 scripts/m9k_blink_arbiter_build.py --site-a 15,4 --site-b 15,10
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
module m9k_arbiter(
    input  wire CLK,
    input  wire KEY2,
    input  wire KEY3,
    output wire LED0
);
    reg [27:0] counter = 28'd0;
    always @(posedge CLK) counter <= counter + 1'b1;

    // Bus arbiter: alternate write target each cycle
    reg arb_state = 1'b0;
    always @(posedge CLK) arb_state <= ~arb_state;

    wire we_a = ~KEY2 &  arb_state;
    wire we_b = ~KEY2 & ~arb_state;

    // RAM A: 8-bit × 1024
    wire [9:0] waddr_a = counter[27 -: 10];
    wire [9:0] raddr_a = counter[26 -: 10];
    wire [7:0] din_a   = {KEY3, KEY2, KEY3, KEY2, KEY3, KEY2, KEY3, KEY2};
    (* ramstyle = "M9K" *) reg [7:0] mem_a [0:1023];
    integer i;
    initial begin
        for (i = 0; i < 1024; i = i + 1)
            mem_a[i] = (i < 512) ? 8'h00 : 8'hFF;
    end
    reg [7:0] dout_a_r;
    always @(posedge CLK) begin
        if (we_a) mem_a[waddr_a] <= din_a;
        dout_a_r <= mem_a[raddr_a];
    end

    // Pipeline stage between RAM_A read and RAM_B address
    reg [9:0] addr_b_pipe;
    always @(posedge CLK) addr_b_pipe <= {2'b0, dout_a_r};

    // RAM B: 8-bit × 1024, address derived from RAM_A's data
    wire [9:0] waddr_b = counter[25 -: 10];
    wire [9:0] raddr_b = addr_b_pipe;
    // din_b feeds back from arbiter state and dout_a (cross-RAM dep)
    wire [7:0] din_b   = dout_a_r ^ {KEY3, KEY2, KEY3, KEY2, KEY3, KEY2, KEY3, KEY2};
    (* ramstyle = "M9K" *) reg [7:0] mem_b [0:1023];
    integer j;
    initial begin
        for (j = 0; j < 1024; j = j + 1)
            mem_b[j] = (j < 512) ? 8'h00 : 8'hFF;
    end
    reg [7:0] dout_b_r;
    always @(posedge CLK) begin
        if (we_b) mem_b[waddr_b] <= din_b;
        dout_b_r <= mem_b[raddr_b];
    end

    // Final pipeline reg combining both RAM outputs
    reg [7:0] result_r;
    always @(posedge CLK) result_r <= dout_a_r + dout_b_r;

    assign LED0 = ^result_r;
endmodule
"""


def render_qsf(x_a: int, y_a: int, x_b: int, y_b: int) -> str:
    return f"""\
set_global_assignment -name FAMILY "Cyclone IV E"
set_global_assignment -name DEVICE EP4CE6F17C8
set_global_assignment -name TOP_LEVEL_ENTITY m9k_arbiter
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
    work = WORK_ROOT / f"m9k_arbiter_{tag}"
    work.mkdir(parents=True, exist_ok=True)
    (work / "fuzz_top.v").write_text(render_verilog())
    (work / "fuzz_top.qsf").write_text(render_qsf(x_a, y_a, x_b, y_b))
    rbf = work / f"m9k_arbiter_{tag}.rbf"
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
    ap.add_argument("--site-a", required=True, help="X,Y for RAM A")
    ap.add_argument("--site-b", required=True, help="X,Y for RAM B")
    ap.add_argument("--tag", default=None,
                    help="build dir tag (default derived from sites)")
    args = ap.parse_args()
    x_a, y_a = (int(s) for s in args.site_a.split(","))
    x_b, y_b = (int(s) for s in args.site_b.split(","))
    tag = args.tag or f"X{x_a}Y{y_a}_X{x_b}Y{y_b}"
    print(f"=== building 2-RAM SDP arbiter at X{x_a}_Y{y_a} + X{x_b}_Y{y_b} ===")
    rbf = build(x_a, y_a, x_b, y_b, tag)
    if rbf:
        print(f"  OK -> {rbf.relative_to(ROOT)}")
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
