#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Build a Quartus gold reference for cross-LAB canon-2input asymmetric mask.

P5 silicon-validation gate: codec's `canon_2input_aware=True` post-loop
applies a ~240-cell absolute table at X4Y4N0 that was mined in a 1-LE
wire4 (combinational, 4 inputs, no CLK) design context.  This script
builds the cross-LAB analog (LE_A=mask@X4Y4N0 + LE_B=passthrough@X4Y21N0
+ DFF + CLK) in Quartus so we can RBF-byte-diff codec output against a
matching Quartus reference *before* flashing.  Byte-identity (0 diff)
means the canon_2input absolute generalizes across design contexts.
Non-zero diff localizes which cells are context-baked.

Pin map matches scripts/sigcache_validation/build_test.py:
    A=PIN_E16, B=PIN_M16, CLK=PIN_E1, Q=PIN_G15
    LE_A: LCCOMB_X4_Y4_N0  (LUT mask=arg)
    LE_B: LCCOMB_X4_Y21_N0 (LUT mask=0xAAAA, passthrough of dataa)
    DFF:  FF_X4_Y21_N0     (paired with LE_B)

Usage:
    python3 scripts/sigma_inv_real_tt_mining/build_xlab_canon_2input_ref.py 0x4444
"""
from __future__ import annotations
import argparse, hashlib, os, subprocess, sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
QUARTUS = Path.home() / "intelFPGA_lite" / "21.1" / "quartus" / "bin"
WORK = REPO / "tmp" / "canon_2input_xlab_quartus"


VERILOG_TMPL = """\
module {name}(
    input  wire CLK,
    input  wire A,
    input  wire B,
    output reg  Q
);
    (* keep = "true" *) wire le_a_out;
    (* keep = "true" *) wire le_b_out;
    cycloneive_lcell_comb #(
        .lut_mask(16'h{mask:04X}),
        .sum_lutc_input("datac"),
        .lpm_type("cycloneive_lcell_comb")
    ) le_a (
        .dataa(A),
        .datab(B),
        .datac(1'b0),
        .datad(1'b0),
        .cin(1'b0),
        .combout(le_a_out),
        .cout()
    );
    cycloneive_lcell_comb #(
        .lut_mask(16'hAAAA),
        .sum_lutc_input("datac"),
        .lpm_type("cycloneive_lcell_comb")
    ) le_b (
        .dataa(le_a_out),
        .datab(1'b0),
        .datac(1'b0),
        .datad(1'b0),
        .cin(1'b0),
        .combout(le_b_out),
        .cout()
    );
    always @(posedge CLK)
        Q <= le_b_out;
endmodule
"""

QSF_TMPL = """\
set_global_assignment -name FAMILY "Cyclone IV E"
set_global_assignment -name DEVICE EP4CE6F17C8
set_global_assignment -name TOP_LEVEL_ENTITY {name}
set_global_assignment -name VERILOG_FILE {name}.v
set_global_assignment -name PROJECT_OUTPUT_DIRECTORY output_files
set_global_assignment -name SEED 1
set_global_assignment -name STRATIX_DEVICE_IO_STANDARD "3.3-V LVTTL"
set_global_assignment -name RESERVE_ALL_UNUSED_PINS_WEAK_PULLUP "AS INPUT TRI-STATED WITH WEAK PULL-UP"
set_global_assignment -name CYCLONEII_RESERVE_NCEO_AFTER_CONFIGURATION "USE AS REGULAR IO"
set_location_assignment PIN_E1  -to CLK
set_location_assignment PIN_E16 -to A
set_location_assignment PIN_M16 -to B
set_location_assignment PIN_G15 -to Q
set_location_assignment LCCOMB_X4_Y4_N0  -to "le_a"
set_location_assignment LCCOMB_X4_Y21_N0 -to "le_b"
# Q (output reg) intentionally unpinned — Quartus packs it with LE_B by
# default (direct LUT→DFF path, lowest routing cost).  Adding an explicit
# FF_X*/LCFF_X* assignment was rejected as "illegal location" in 21.1.
"""


def build(mask: int) -> Path:
    name = f"xlab_canon_X4Y4N0_{mask:04X}"
    bdir = WORK / name
    bdir.mkdir(parents=True, exist_ok=True)
    (bdir / f"{name}.v").write_text(VERILOG_TMPL.format(name=name, mask=mask))
    (bdir / f"{name}.qsf").write_text(QSF_TMPL.format(name=name))
    (bdir / f"{name}.qpf").write_text(f'PROJECT_REVISION = "{name}"\n')

    rbf = bdir / f"{name}.rbf"
    if rbf.exists() and rbf.stat().st_size == 368011:
        print(f"  cache hit: {rbf}", flush=True)
        return rbf

    env = os.environ.copy()
    env["PATH"] = str(QUARTUS) + ":" + env["PATH"]
    for step in ("quartus_map", "quartus_fit", "quartus_asm"):
        print(f"  $ {step} {name}", flush=True)
        r = subprocess.run(
            [step, "--read_settings_files=on", "--write_settings_files=off", name],
            cwd=str(bdir), capture_output=True, env=env, timeout=240,
            text=True, errors="replace",
        )
        if r.returncode != 0:
            print(f"FAIL {step}:\n  stdout: {r.stdout[-1200:]}\n  stderr: {r.stderr[-1200:]}",
                  file=sys.stderr)
            raise SystemExit(2)

    sof = bdir / "output_files" / f"{name}.sof"
    r = subprocess.run(
        [str(QUARTUS / "quartus_cpf"), "-c", "-o", "bitstream_compression=off",
         str(sof), str(rbf)],
        cwd=str(bdir), capture_output=True, env=env, timeout=60,
    )
    if r.returncode != 0:
        print(f"FAIL quartus_cpf: {r.stderr.decode(errors='replace')[-800:]}",
              file=sys.stderr)
        raise SystemExit(2)
    return rbf


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("mask", help="LUT mask hex e.g. 0x4444 (canon_naandb = !A & B)")
    args = ap.parse_args()
    m = int(args.mask, 16)
    rbf = build(m)
    md5 = hashlib.md5(rbf.read_bytes()).hexdigest()
    print(f"\n  reference RBF: {rbf}")
    print(f"  size: {rbf.stat().st_size}")
    print(f"  md5 : {md5}")


if __name__ == "__main__":
    main()
