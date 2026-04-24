# SPDX-License-Identifier: GPL-3.0-or-later
"""Universal M9K blink-gold builder.

For a given (width, depth), generates a minimal Quartus project at
M9K_X15_Y10_N0 that drives a counter into the top addr bits and
reads back a pre-loaded INIT pattern. LED0 toggles whenever the
top addr bit flips — at 50 MHz with a 28-bit free-running counter
that's ~0.186 Hz (2.68 s on / 2.68 s off), independent of the
width/depth.

Output: `tmp/m9k_blink_{w}x{d}/m9k_blink_{w}x{d}.rbf` — a flashable
RBF that should blink LED0 at 0.186 Hz on AX301 silicon, validating
that Quartus's (w, d) M9K mode works in a data-path context.

A successful blink for a width is the "functional HW PASS" that
ungates that width into `np2fasm._M9K_MODE_FUNCTIONAL_VALIDATED`
(emission switches from `_inferred_goldintersect` to
`_quartus_gold`).
"""
from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "fuzz"))

from compile import setup_project, compile_full, generate_rbf

WORK_ROOT = ROOT / "tmp"
COMBOS = [(4, 2048), (9, 512), (18, 512), (9, 1024), (36, 256)]

# AX301 pins.  CLK=E1 (dedicated); KEY2=E16 drives WE internally so
# Quartus doesn't fold the RAM into combinational logic; KEY3=M16
# supplies a varying DIN bit for the same reason.  LED0=G15.
PINS = {
    "CLK":  "PIN_E1",
    "KEY2": "PIN_E16",
    "KEY3": "PIN_M16",
    "LED0": "PIN_G15",
}


def _addr_bits(depth: int) -> int:
    return max(1, int(math.ceil(math.log2(depth))))


def _verilog(width: int, depth: int) -> str:
    a = _addr_bits(depth)
    # Drive the top a counter bits as addr; the top bit flips every
    # 2^(27) cycles = 2.68 s @ 50 MHz.
    # Each word splits low vs high half: mem[i][0] = i[a-1].
    # Wider widths get wider DIN replication to dodge LUT folding.
    din_bits = width
    din_tile = ", ".join(["KEY3" if b & 1 else "KEY2"
                          for b in range(din_bits - 1, -1, -1)])
    return f"""\
// Auto-generated m9k_blink_{width}x{depth}.v — M9K data-path smoke.
module m9k_blink(
    input  wire CLK,
    input  wire KEY2,
    input  wire KEY3,
    output wire LED0
);
    reg [27:0] counter = 28'd0;
    always @(posedge CLK) counter <= counter + 1'b1;

    wire [{a-1}:0] addr = counter[27 -: {a}];
    wire           we   = ~KEY2;
    wire [{width-1}:0] din  = {{{din_tile}}};

    (* ramstyle = "M9K" *) reg [{width-1}:0] mem [0:{depth-1}];
    integer i;
    initial begin
        for (i = 0; i < {depth // 2}; i = i + 1)
            mem[i] = {width}'d0;
        for (i = {depth // 2}; i < {depth}; i = i + 1)
            mem[i] = {{{width}{{1'b1}}}};
    end

    reg [{width-1}:0] dout_r;
    always @(posedge CLK) begin
        if (we) mem[addr] <= din;
        dout_r <= mem[addr];
    end

    assign LED0 = dout_r[0];
endmodule
"""


def _qsf(width: int, depth: int) -> str:
    lines = [
        'set_global_assignment -name FAMILY "Cyclone IV E"',
        "set_global_assignment -name DEVICE EP4CE6F17C8",
        "set_global_assignment -name TOP_LEVEL_ENTITY m9k_blink",
        "set_global_assignment -name VERILOG_FILE fuzz_top.v",
        "set_global_assignment -name PROJECT_OUTPUT_DIRECTORY output_files",
        'set_global_assignment -name STRATIX_DEVICE_IO_STANDARD "3.3-V LVTTL"',
        "set_global_assignment -name SEED 1",
    ]
    for sig, pin in PINS.items():
        lines.append(f"set_location_assignment {pin} -to {sig}")
    # Pin the inferred M9K at X15_Y10_N0.
    lines.append(
        'set_instance_assignment -name LOCATION M9K_X15_Y10_N0 '
        '-to "altsyncram:mem_rtl_0|altsyncram_*:auto_generated|ram_block1a*"'
    )
    return "\n".join(lines) + "\n"


def build_one(width: int, depth: int) -> Path:
    combo = f"{width}x{depth}"
    work = WORK_ROOT / f"m9k_blink_{combo}"
    work.mkdir(parents=True, exist_ok=True)
    project = f"m9k_blink_{combo}"
    proj_dir = setup_project(project, _verilog(width, depth),
                             _qsf(width, depth), str(work))
    # fuzz_top.v is Quartus's default file — our top entity is m9k_blink
    # so rename the source file to match.
    (Path(proj_dir) / "m9k_blink.v").write_text(_verilog(width, depth))
    # Overwrite fuzz_top.v to reference the actual module
    (Path(proj_dir) / "fuzz_top.v").write_text(_verilog(width, depth))
    ok, el, err = compile_full(project, proj_dir, timeout=300)
    if not ok:
        raise RuntimeError(f"({width},{depth}) build failed after "
                           f"{el:.1f}s: {err}")
    rbf = generate_rbf(project, proj_dir, str(work / f"{project}.rbf"))
    if rbf is None:
        raise RuntimeError(f"({width},{depth}) RBF generation failed")
    return Path(rbf)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--width", type=int)
    ap.add_argument("--depth", type=int)
    args = ap.parse_args()
    if args.all:
        combos = COMBOS
    elif args.width and args.depth:
        combos = [(args.width, args.depth)]
    else:
        ap.error("specify --all or --width W --depth D")
        return 1
    for w, d in combos:
        print(f"\n=== building m9k_blink_{w}x{d} ===", flush=True)
        try:
            rbf = build_one(w, d)
            print(f"  OK -> {rbf}")
        except Exception as exc:
            print(f"  FAIL: {exc}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
