# SPDX-License-Identifier: GPL-3.0-or-later
"""Build 3 paired Quartus reference RBFs for differential IOB<->SLICE
route mining. All designs are identical to build_golden_dff's golden.rbf
except for the input (K) or output (Q) pin assignment:

  golden_E15_G15.rbf   K=E15, LED=G15  (input pin differs, same bank)
  golden_M16_G15.rbf   K=M16, LED=G15  (input pin differs, other bank)
  golden_E16_F15.rbf   K=E16, LED=F15  (output pin differs)

diff(golden, golden_E15_G15) isolates E16 -> LAB(10,4).dataa routing
  vs E15 -> LAB(10,4).dataa routing (plus IOB E15/E16 pad-buffer delta).
diff(golden, golden_E16_F15) isolates LAB(10,4).Q -> G15 routing
  vs LAB(10,4).Q -> F15 routing (plus IOB G15/F15 delta).

Companion analyzer: analyze_iob_slice_diffs.py.

Launched in parallel via ProcessPoolExecutor.
"""
from __future__ import annotations

import argparse
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
sys.path.insert(0, str(REPO / "fuzz"))

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


def make_qsf(k_pin: str, q_pin: str) -> str:
    from runner import make_lccomb
    return "\n".join([
        'set_global_assignment -name FAMILY "Cyclone IV E"',
        'set_global_assignment -name DEVICE EP4CE6F17C8',
        'set_global_assignment -name TOP_LEVEL_ENTITY fuzz_top',
        'set_global_assignment -name VERILOG_FILE fuzz_top.v',
        'set_global_assignment -name PROJECT_OUTPUT_DIRECTORY output_files',
        'set_global_assignment -name STRATIX_DEVICE_IO_STANDARD "3.3-V LVTTL"',
        'set_global_assignment -name SEED 1',
        'set_location_assignment PIN_E1  -to CLK',
        f'set_location_assignment PIN_{k_pin} -to A',
        f'set_location_assignment PIN_{q_pin} -to Q',
        f'set_location_assignment {make_lccomb(*DFF_LE)} -to "lut"',
        'set_instance_assignment -name GLOBAL_SIGNAL "GLOBAL CLOCK" -to CLK',
    ]) + "\n"


def build_one(job):
    tag, k_pin, q_pin, out_path, work_dir = job
    sys.path.insert(0, str(REPO / "fuzz"))
    from compile import compile_and_export
    if Path(out_path).exists():
        return tag, True, "cached"
    qsf = make_qsf(k_pin, q_pin)
    rbf, elapsed, err = compile_and_export(
        tag, VERILOG, qsf,
        rbf_output=str(out_path),
        work_dir=str(work_dir),
    )
    if rbf:
        return tag, True, f"{elapsed:.1f}s"
    return tag, False, f"FAIL: {err[:200]}"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--outdir", default=str(HERE / "work"),
                    help="output directory for paired RBFs")
    args = ap.parse_args()
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    jobs = [
        ("golden_E15_G15", "E15", "G15", outdir / "golden_E15_G15.rbf", outdir),
        ("golden_M16_G15", "M16", "G15", outdir / "golden_M16_G15.rbf", outdir),
        ("golden_E16_F15", "E16", "F15", outdir / "golden_E16_F15.rbf", outdir),
    ]
    n_fail = 0
    with ProcessPoolExecutor(max_workers=3) as ex:
        futures = {ex.submit(build_one, j): j[0] for j in jobs}
        for f in as_completed(futures):
            tag = futures[f]
            try:
                t, ok, msg = f.result()
                status = "OK  " if ok else "FAIL"
                print(f"[{status}] {t:20s} {msg}", flush=True)
                if not ok:
                    n_fail += 1
            except Exception as e:
                print(f"[ERR ] {tag:20s} {e}", flush=True)
                n_fail += 1
    return n_fail


if __name__ == "__main__":
    sys.exit(main())
