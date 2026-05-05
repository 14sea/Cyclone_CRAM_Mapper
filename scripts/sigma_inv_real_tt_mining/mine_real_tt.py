#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Mine the actual silicon-correct TT cells for std_lut LEs by diffing
LUT=0xFFFF vs LUT=0x0000 Quartus builds at the same LE position.

For each (x, y, n) std_lut LE, the silicon LUT TT lives in 16 distinct
CRAM bits (one per minterm). σ⁻¹'s `LutCodec.from_cram_model(x,y,n)`
*claims* 16 cells but at colliding Y values may misclassify some/all
of them as LI MUX bytes that overlap at the same bp.

Method:
  full design : 1 LCCOMB at (x, y, n) with `lut_mask = 16'hFFFF`
  zero design : 1 LCCOMB at same position with `lut_mask = 16'h0000`
  diff = the 16 silicon-correct TT cells (one per minterm bit)

Both designs use cycloneive_lcell_comb primitive directly to bypass
Yosys/Quartus optimization (a constant-output LUT might otherwise be
optimized to a tied 0/1 with no LE allocation).

Output: results/real_tt_classification.json
  per (x, y, n):
    real_tt              : 16 cells silicon actually uses
    sigma_inv_claimed    : 16 cells σ⁻¹ predict_sram(0xFFFF) claims
    correctly_identified : real_tt ∩ sigma_inv_claimed
    misclassified        : sigma_inv_claimed - real_tt (σ⁻¹ wrong, Phase 3 owns)
    sigma_inv_missed     : real_tt - sigma_inv_claimed (σ⁻¹ wrong, currently unwritten)

Usage:
    python3 scripts/sigma_inv_real_tt_mining/mine_real_tt.py X Y N [X Y N ...]
    python3 scripts/sigma_inv_real_tt_mining/mine_real_tt.py --batch
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
WORK = REPO / "tmp" / "real_tt_mining"
QUARTUS = Path.home() / "intelFPGA_lite" / "21.1" / "quartus" / "bin"

sys.path.insert(0, str(REPO / "fuzz"))
from bitstream import LutCodec  # noqa: E402

OUT_JSON = REPO / "results" / "real_tt_classification.json"

# Default batch: cross_lab_open's two stages + W=24 buffer + sanity-check
# safe-Y positions.
DEFAULT_BATCH = [
    (16, 4, 0),    # cross_lab_open Stage A — Y=4 collision
    (16, 14, 0),   # cross_lab_open Stage B — Y=14 collision
    (4, 4, 0),     # W=24 buffer LE — Y=4 collision
    (10, 4, 0),    # used in regression test — Y=4 collision
    (10, 10, 0),   # common silicon position — Y=10 collision
    (4, 17, 0),    # arith chain end - actually arith. test as std_lut
    (10, 6, 0),    # safe Y=6 — sanity check
    (10, 3, 0),    # safe Y=3 — sanity check
]


def build_one(name: str, x: int, y: int, n: int, lut_mask: int) -> bytes | None:
    """Build a single Quartus design with a 1-LE LUT at (x, y, n).

    Returns the RBF bytes or None on build failure.

    Note: our_n // 2 maps to Quartus's LCCOMB N.  Quartus rejects
    standalone LCCOMB placement at N=7 and N=15 (chain-terminator
    LE positions) — see CLAUDE.md / memory note on Path B blocker.
    Our_n values 14 and 30 will hit those rejection cases; those
    positions can only be populated via a chain primitive cascading
    from N=0.  This script's 1-LE template doesn't apply there.
    """
    quartus_n = n // 2
    if quartus_n in (7, 15):
        print(
            f"  SKIP (chain-only LE): our_n={n} → LCCOMB_X{x}_Y{y}_N{quartus_n} "
            f"is rejected by Quartus fitter for standalone placement. "
            f"Use a chain-based mining template instead."
        )
        return None
    bdir = WORK / name
    bdir.mkdir(parents=True, exist_ok=True)

    # Use cycloneive_lcell_comb primitive directly to keep the LE alive
    # even when lut_mask=0 (which would otherwise constant-fold to gnd).
    verilog = f"""\
module {name} (input KEY2, input KEY3, output LED0);
    wire combout;
    cycloneive_lcell_comb #(
        .lut_mask(16'h{lut_mask:04X}),
        .sum_lutc_input("datac"),
        .lpm_type("cycloneive_lcell_comb")
    ) le_inst (
        .dataa(KEY2),
        .datab(KEY3),
        .datac(1'b0),
        .datad(1'b0),
        .cin(1'b0),
        .combout(combout),
        .cout()
    );
    assign LED0 = combout;
endmodule
"""
    qsf = f"""\
set_global_assignment -name FAMILY "Cyclone IV E"
set_global_assignment -name DEVICE EP4CE6F17C8
set_global_assignment -name TOP_LEVEL_ENTITY {name}
set_global_assignment -name VERILOG_FILE {name}.v
set_global_assignment -name PROJECT_OUTPUT_DIRECTORY output_files
set_global_assignment -name SEED 1
set_global_assignment -name STRATIX_DEVICE_IO_STANDARD "3.3-V LVTTL"
set_global_assignment -name RESERVE_ALL_UNUSED_PINS_WEAK_PULLUP "AS INPUT TRI-STATED WITH WEAK PULL-UP"
set_global_assignment -name CYCLONEII_RESERVE_NCEO_AFTER_CONFIGURATION "USE AS REGULAR IO"
set_location_assignment PIN_E16 -to KEY2
set_location_assignment PIN_M16 -to KEY3
set_location_assignment PIN_G15 -to LED0
set_location_assignment LCCOMB_X{x}_Y{y}_N{quartus_n} -to "le_inst"
"""
    (bdir / f"{name}.v").write_text(verilog)
    (bdir / f"{name}.qsf").write_text(qsf)
    (bdir / f"{name}.qpf").write_text(f'PROJECT_REVISION = "{name}"\n')

    env = os.environ.copy()
    env["PATH"] = str(QUARTUS) + ":" + env["PATH"]

    for step in ("quartus_map", "quartus_fit", "quartus_asm"):
        r = subprocess.run(
            [step, "--read_settings_files=on", "--write_settings_files=off", name],
            cwd=str(bdir), capture_output=True, env=env, timeout=180,
            text=True, errors="replace",
        )
        if r.returncode != 0:
            print(f"  FAIL {step}: {r.stdout[-1200:]}")
            return None

    sof = bdir / "output_files" / f"{name}.sof"
    rbf = bdir / f"{name}.rbf"
    r = subprocess.run(
        [str(QUARTUS / "quartus_cpf"), "-c", "-o", "bitstream_compression=off",
         str(sof), str(rbf)],
        cwd=str(bdir), capture_output=True, env=env, timeout=60,
    )
    if r.returncode != 0:
        return None
    return rbf.read_bytes()


def diff_cells(a: bytes, b: bytes) -> set[tuple[int, int]]:
    """Diff two RBFs, return set of (off, bp) cells (excluding CRC + preamble + postamble)."""
    cells = set()
    for off in range(32, min(len(a), len(b))):
        if off >= 367952:
            break
        frame = (off - 32) // 210
        pos = (off - 32) % 210
        if frame >= 25 and pos >= 208:
            continue
        x = a[off] ^ b[off]
        if x:
            for bp in range(8):
                if x & (1 << bp):
                    cells.add((off, bp))
    return cells


def mine_le(x: int, y: int, n: int) -> dict:
    """Mine real TT cells for std_lut at (x, y, n)."""
    print(f"\n=== Mining X{x}Y{y}N{n} (LCCOMB_X{x}_Y{y}_N{n//2}) ===", flush=True)

    full_name = f"xor_X{x}Y{y}N{n}"
    zero_name = f"xnor_X{x}Y{y}N{n}"

    # 0x6996 = 4-input XOR  (output=1 iff odd # of {a,b,c,d}=1)
    # 0x9669 = 4-input XNOR (output=1 iff even # of {a,b,c,d}=1)
    # XOR = 0xFFFF — every minterm cell flips between the two builds.
    # Both are "real" 4-input LUTs (Quartus can't optimize to passthrough).
    print(f"  Building {full_name} (lut_mask=0x6996 XOR4)...", flush=True)
    full_rbf = build_one(full_name, x, y, n, 0x6996)
    if full_rbf is None:
        return {"error": "full build failed"}

    print(f"  Building {zero_name} (lut_mask=0x9669 XNOR4)...", flush=True)
    zero_rbf = build_one(zero_name, x, y, n, 0x9669)
    if zero_rbf is None:
        return {"error": "zero build failed"}

    real_tt = diff_cells(full_rbf, zero_rbf)
    sigma_inv = LutCodec.from_cram_model(x, y, n).predict_sram(0xFFFF)

    correct = real_tt & sigma_inv
    misclassified = sigma_inv - real_tt
    missed = real_tt - sigma_inv

    print(f"  real_tt              : {len(real_tt)} cells")
    print(f"  sigma_inv_claimed    : {len(sigma_inv)} cells")
    print(f"  correctly_identified : {len(correct)}")
    print(f"  misclassified        : {len(misclassified)} (Phase 3 owns)")
    print(f"  sigma_inv_missed     : {len(missed)} (currently unwritten)")

    # Bit-position distribution
    from collections import Counter
    real_bp = Counter(bp for _, bp in real_tt)
    sigma_bp = Counter(bp for _, bp in sigma_inv)
    print(f"  real_tt by bp        : {dict(real_bp)}")
    print(f"  sigma_inv by bp      : {dict(sigma_bp)}")

    return {
        "real_tt": sorted([list(c) for c in real_tt]),
        "sigma_inv_claimed": sorted([list(c) for c in sigma_inv]),
        "correctly_identified": sorted([list(c) for c in correct]),
        "misclassified": sorted([list(c) for c in misclassified]),
        "sigma_inv_missed": sorted([list(c) for c in missed]),
        "real_tt_count": len(real_tt),
        "correct_count": len(correct),
        "misclassified_count": len(misclassified),
        "missed_count": len(missed),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--batch", action="store_true", help="Mine the default 8-position batch")
    ap.add_argument("triples", nargs="*", help="X Y N triples (space-separated)")
    args = ap.parse_args()

    targets = []
    if args.batch:
        targets = list(DEFAULT_BATCH)
    if args.triples:
        if len(args.triples) % 3 != 0:
            print("Need triples of (X Y N)", file=sys.stderr)
            sys.exit(1)
        for i in range(0, len(args.triples), 3):
            targets.append(tuple(int(t) for t in args.triples[i:i+3]))
    if not targets:
        print("Specify --batch or X Y N triples", file=sys.stderr)
        sys.exit(1)

    WORK.mkdir(parents=True, exist_ok=True)

    # Load existing classification, merge new results
    if OUT_JSON.exists():
        existing = json.loads(OUT_JSON.read_text())
    else:
        existing = {"description": "Per-(x,y,n) std_lut TT classification: σ⁻¹ vs silicon ground-truth", "entries": {}}

    for x, y, n in targets:
        key = f"X{x}Y{y}N{n}"
        result = mine_le(x, y, n)
        existing["entries"][key] = result
        # Persist after each LE in case of interruption
        OUT_JSON.write_text(json.dumps(existing, indent=2))

    print(f"\nWrote {OUT_JSON}")


if __name__ == "__main__":
    main()
