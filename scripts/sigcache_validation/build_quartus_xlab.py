#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Build a Quartus Lite 21.1 cross-LAB gold for the build_test design.

Mirrors `build_test.py`'s wiring (test_2lut_clocked.v):
  LE_A @ LCCOMB_X4_Y4_N0  with INIT = --le-a-mask
  LE_B @ LCCOMB_X4_Y21_N0 with INIT = 0xAAAA (datac passthrough)
  KEY2 (E16) → LE_A.dataa
  KEY3 (M16) → LE_A.datab
  LE_A.combout → LE_B.datac  (LE_A → LE_B same-column R4-class hop)
  LE_B.combout → DFF → PIN_G15
  CLK = PIN_E1

Used as the byte-identity reference for `build_test.py --canon-2input absolute`
output (Track B1 audit gate, 2026-05-21).

Output: tmp/quartus_xlab/output_files/xlab_X4Y4_to_X4Y21.rbf
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
QUARTUS = Path.home() / "intelFPGA_lite" / "21.1" / "quartus" / "bin"
WORK = REPO / "tmp" / "quartus_xlab"


VERILOG_TEMPLATE = """\
// SPDX-License-Identifier: GPL-3.0-or-later
// Quartus gold reference for build_test cross-LAB X4Y4N0 → X4Y21N0.
// LE_A primitive INIT comes from the command-line --le-a-mask.

module fuzz_top(
    input  wire CLK,
    input  wire A,
    input  wire B,
    output reg  Q
);
    wire le_a_out;
    wire le_b_out;

    cycloneive_lcell_comb #(
        .lut_mask(16'h{LE_A_MASK}),
        .sum_lutc_input("datac"),
        .dont_touch("on")
    ) le_a (
        .dataa(A),
        .datab(B),
        .datac(1'b0),
        .datad(1'b0),
        .combout(le_a_out)
    );

    cycloneive_lcell_comb #(
        .lut_mask(16'hAAAA),
        .sum_lutc_input("datac"),
        .dont_touch("on")
    ) le_b (
        .dataa(le_a_out),
        .datab(1'b0),
        .datac(1'b0),
        .datad(1'b0),
        .combout(le_b_out)
    );

    always @(posedge CLK)
        Q <= le_b_out;
endmodule
"""


def gen_qsf(name: str) -> str:
    lines = [
        'set_global_assignment -name FAMILY "Cyclone IV E"',
        'set_global_assignment -name DEVICE EP4CE6F17C8',
        'set_global_assignment -name TOP_LEVEL_ENTITY fuzz_top',
        'set_global_assignment -name VERILOG_FILE fuzz_top.v',
        'set_global_assignment -name PROJECT_OUTPUT_DIRECTORY output_files',
        'set_global_assignment -name STRATIX_DEVICE_IO_STANDARD "3.3-V LVTTL"',
        'set_global_assignment -name SEED 1',
        'set_global_assignment -name RESERVE_ALL_UNUSED_PINS_WEAK_PULLUP '
        '"AS INPUT TRI-STATED WITH WEAK PULL-UP"',
        'set_global_assignment -name CYCLONEII_RESERVE_NCEO_AFTER_CONFIGURATION '
        '"USE AS REGULAR IO"',
        # Pin assignments
        'set_location_assignment PIN_E1 -to CLK',
        'set_location_assignment PIN_E16 -to A',
        'set_location_assignment PIN_M16 -to B',
        'set_location_assignment PIN_G15 -to Q',
        # LCCOMB locations
        'set_location_assignment LCCOMB_X4_Y4_N0 -to "le_a"',
        'set_location_assignment LCCOMB_X4_Y21_N0 -to "le_b"',
        # Globals
        'set_instance_assignment -name GLOBAL_SIGNAL "GLOBAL CLOCK" -to CLK',
    ]
    return "\n".join(lines) + "\n"


def build(name: str, le_a_mask: int) -> Path | None:
    WORK.mkdir(parents=True, exist_ok=True)
    (WORK / "fuzz_top.v").write_text(
        VERILOG_TEMPLATE.replace("{LE_A_MASK}", f"{le_a_mask:04X}")
    )
    (WORK / f"{name}.qsf").write_text(gen_qsf(name))
    (WORK / f"{name}.qpf").write_text(
        f'QUARTUS_VERSION = "21.1"\nPROJECT_REVISION = "{name}"\n'
    )

    env = os.environ.copy()
    env["PATH"] = str(QUARTUS) + ":" + env.get("PATH", "")

    for step in ("quartus_map", "quartus_fit", "quartus_asm"):
        r = subprocess.run(
            [step, name], cwd=str(WORK), env=env,
            capture_output=True, text=True, errors="replace", timeout=300,
        )
        if r.returncode != 0:
            print(f"  [{step}] FAIL rc={r.returncode}")
            print(r.stderr[-2000:])
            return None
        print(f"  [{step}] OK")

    sof = WORK / "output_files" / f"{name}.sof"
    rbf = WORK / "output_files" / f"{name}.rbf"
    r = subprocess.run(
        [str(QUARTUS / "quartus_cpf"), "-c",
         "-o", "bitstream_compression=off",
         str(sof), str(rbf)],
        cwd=str(WORK), env=env,
        capture_output=True, text=True, errors="replace", timeout=60,
    )
    if r.returncode != 0 or not rbf.exists():
        print("  [cpf] FAIL")
        print(r.stderr[-1000:])
        return None
    return rbf


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--le-a-mask", type=lambda s: int(s, 16),
                    default=0x4444,
                    help="LE_A LUT INIT mask, hex (default 0x4444)")
    args = ap.parse_args()

    name = f"xlab_X4Y4_to_X4Y21_mask{args.le_a_mask:04X}"
    print(f"=== Quartus cross-LAB build: {name} ===")
    rbf = build(name, args.le_a_mask)
    if rbf is None:
        return 1

    import hashlib
    md5 = hashlib.md5(rbf.read_bytes()).hexdigest()
    print(f"\nQuartus RBF: {rbf.relative_to(REPO)}")
    print(f"  md5: {md5}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
