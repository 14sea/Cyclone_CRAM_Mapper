# SPDX-License-Identifier: GPL-3.0-or-later
"""Full-width m9k_blink builder — 9-bit DOUT XOR-reduced so Quartus
must instantiate full 9x512 SP M9K (avoids the collapse-to-1x512
optimization in scripts/m9k_blink_build.py when only DOUT[0] is used).

Used for mining M9K column infrastructure cells across X=15 / X=27
column sites — see memory m9k_mode_gi_swap_silicon_test_2026_04_30.md.
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WORK_ROOT = ROOT / "tmp"


def render_verilog() -> str:
    return """\
module m9k_blink(
    input  wire CLK,
    input  wire KEY2,
    input  wire KEY3,
    output wire LED0
);
    reg [27:0] counter = 28'd0;
    always @(posedge CLK) counter <= counter + 1'b1;

    wire [8:0] addr = counter[27 -: 9];
    wire       we   = ~KEY2;
    wire [8:0] din  = {KEY3, KEY2, KEY3, KEY2, KEY3, KEY2, KEY3, KEY2, KEY3};

    (* ramstyle = "M9K" *) reg [8:0] mem [0:511];
    integer i;
    initial begin
        for (i = 0; i < 256; i = i + 1)
            mem[i] = 9'b000000000;
        for (i = 256; i < 512; i = i + 1)
            mem[i] = 9'b111111111;
    end

    reg [8:0] dout_r;
    always @(posedge CLK) begin
        if (we) mem[addr] <= din;
        dout_r <= mem[addr];
    end

    assign LED0 = ^dout_r;
endmodule
"""


def render_qsf(x: int, y: int, n: int) -> str:
    return f"""\
set_global_assignment -name FAMILY "Cyclone IV E"
set_global_assignment -name DEVICE EP4CE6F17C8
set_global_assignment -name TOP_LEVEL_ENTITY m9k_blink
set_global_assignment -name VERILOG_FILE fuzz_top.v
set_global_assignment -name PROJECT_OUTPUT_DIRECTORY output_files
set_global_assignment -name STRATIX_DEVICE_IO_STANDARD "3.3-V LVTTL"
set_global_assignment -name SEED 1
set_location_assignment PIN_E1  -to CLK
set_location_assignment PIN_E16 -to KEY2
set_location_assignment PIN_M16 -to KEY3
set_location_assignment PIN_G15 -to LED0
set_location_assignment M9K_X{x}_Y{y}_N{n} -to "altsyncram:mem_rtl_0"
"""


def build_one(x: int, y: int, n: int = 0) -> Path:
    work = WORK_ROOT / f"m9k_blink_full_X{x}_Y{y}_N{n}"
    work.mkdir(parents=True, exist_ok=True)
    (work / "fuzz_top.v").write_text(render_verilog())
    (work / "fuzz_top.qsf").write_text(render_qsf(x, y, n))

    rbf = work / f"m9k_blink_full_X{x}_Y{y}_N{n}.rbf"
    if rbf.exists():
        print(f"  exists: {rbf}")
        return rbf

    qbin = Path.home() / "intelFPGA_lite/21.1/quartus/bin"
    env = {"PATH": f"{qbin}:" + subprocess.os.environ.get("PATH", "")}
    for tool in ("quartus_map", "quartus_fit", "quartus_asm"):
        r = subprocess.run([str(qbin / tool), "fuzz_top",
                            "--read_settings_files=on",
                            "--write_settings_files=off"],
                           cwd=work, env={**subprocess.os.environ, **env},
                           capture_output=True, text=True)
        if r.returncode != 0:
            print(f"FAIL {tool}: {r.stderr[-200:]}")
            return None
    r = subprocess.run([str(qbin / "quartus_cpf"), "-c",
                        "-o", "bitstream_compression=off",
                        "output_files/fuzz_top.sof", str(rbf)],
                       cwd=work, env={**subprocess.os.environ, **env},
                       capture_output=True, text=True)
    if r.returncode != 0 or not rbf.exists():
        print(f"FAIL cpf")
        return None
    return rbf


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sites", required=True,
                    help="comma-separated X,Y pairs e.g. 15,4;15,5;15,6")
    args = ap.parse_args()
    sites = [tuple(int(s) for s in p.split(",")) for p in args.sites.split(";")]
    for x, y in sites:
        print(f"=== X={x} Y={y} ===", flush=True)
        rbf = build_one(x, y, 0)
        if rbf:
            print(f"  OK -> {rbf}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
