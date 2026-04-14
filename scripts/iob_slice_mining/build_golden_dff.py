# SPDX-License-Identifier: GPL-3.0-or-later
"""Build a Quartus golden RBF for the minimal 1-LE DFF design:

    Q = latch(KEY2) at posedge CLK

placed at LAB(10,4).N=0 with GCLK forced on CLK. This is the
ground-truth RBF we reproduce via the open toolchain (Yosys ->
prepack -> np2fasm -> fasm2rbf) to isolate the IOB<->SLICE routing
cells missing from the sig-cache.

Structure:
  * 1 cycloneive_lcell_comb at LCCOMB_X10_Y4_N0 with lut_mask=0xAAAA
    (dataa passthrough -- D input = A)
  * 1 register on combout (silicon DFF, same LE)
  * IOBs: CLK=PIN_E1, A=PIN_E16 (KEY2), Q=PIN_G15 (LED)
  * GLOBAL_SIGNAL "GLOBAL CLOCK" on CLK

Default output: <HERE>/work/golden.rbf (scratch). Override with --out.

Companion: build_diff_refs.py builds 3 paired RBFs that differ only
in the K or Q pin assignment, used by analyze_iob_slice_diffs.py to
decompose IOB<->SLICE routing from the pad/LE cell sets.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
sys.path.insert(0, str(REPO / "fuzz"))

from compile import compile_and_export  # noqa: E402
from runner import make_lccomb  # noqa: E402


DFF_LE = (10, 4, 0)


VERILOG = """module fuzz_top(
    input  wire CLK,
    input  wire A,
    output reg  Q
);
    wire lut_out;

    cycloneive_lcell_comb #(
        .lut_mask(16'hAAAA),
        .sum_lutc_input("datac"),
        .dont_touch("on")
    ) lut (
        .dataa(A),
        .datab(1'b0),
        .datac(1'b0),
        .datad(1'b0),
        .combout(lut_out)
    );

    always @(posedge CLK)
        Q <= lut_out;
endmodule
"""


def gen_qsf() -> str:
    lines = [
        'set_global_assignment -name FAMILY "Cyclone IV E"',
        'set_global_assignment -name DEVICE EP4CE6F17C8',
        'set_global_assignment -name TOP_LEVEL_ENTITY fuzz_top',
        'set_global_assignment -name VERILOG_FILE fuzz_top.v',
        'set_global_assignment -name PROJECT_OUTPUT_DIRECTORY output_files',
        'set_global_assignment -name STRATIX_DEVICE_IO_STANDARD "3.3-V LVTTL"',
        'set_global_assignment -name SEED 1',
        'set_location_assignment PIN_E1  -to CLK',
        'set_location_assignment PIN_E16 -to A',
        'set_location_assignment PIN_G15 -to Q',
        f'set_location_assignment {make_lccomb(*DFF_LE)} -to "lut"',
        'set_instance_assignment -name GLOBAL_SIGNAL "GLOBAL CLOCK" -to CLK',
    ]
    return "\n".join(lines) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(HERE / "work" / "golden.rbf"),
                    help="output RBF path")
    ap.add_argument("--work", default=str(HERE / "work"),
                    help="Quartus work directory")
    args = ap.parse_args()

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.exists():
        print(f"[cache] {out} already exists", flush=True)
        return 0

    qsf = gen_qsf()
    print(f"[build] golden.rbf (1-LE DFF @ LAB{DFF_LE}) -> {out}", flush=True)
    rbf, elapsed, err = compile_and_export(
        "iob_slice_golden",
        VERILOG,
        qsf,
        rbf_output=str(out),
        work_dir=args.work,
    )
    if not rbf:
        print(f"FAILED: {err[:500]}", flush=True)
        return 1
    print(f"         -> {out} ({elapsed:.1f}s)", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
