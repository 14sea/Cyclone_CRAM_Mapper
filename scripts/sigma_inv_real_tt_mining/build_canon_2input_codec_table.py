#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Build the LutCodec 2-input canonicalization-cell table for one position.

Strategy (P2.2):

For every 2-input mask label L the codec must reach `Quartus(L)` from
`nv_zero_global + codec.predict_sram(M_L)`.  The delta between those two
RBFs is the **absolute canon-2input cell set** for L at this position.

  abs[L] = (Quartus(L)_rbf XOR nv_zero_global) XOR codec.predict_sram(M_L)
         = canon-layer-cells the codec must XOR-apply to land on Quartus

This is the same trick used by Phase 4 bypass byte-identity: take the
Quartus reference as ground truth, isolate the layer the codec doesn't
model yet, store it as a cell set, XOR-apply at write time.

Coverage at one position:
  * 18 permutation labels: 6×AND + 6×OR + 6×XOR
  * 6 negation labels (the 6 non-`X&Y/X|Y` 2-input AND/OR negation variants;
    8 total AND_NEG+OR_NEG minus 2 duplicates with the perm table)

Per-label absolute size at X4Y4N0 ≈ 240 cells (~110 lab_cram + ~120 hdr +
~12 block_band).  The lab_cram portion is the σ⁻¹-permutation gap
(Pitfall #16) — codec.predict_sram() only models 16 functional TT bits,
Quartus emits ~110 lab_cram cells for any 2-input mask.  Pre-mining the
full absolute delta sidesteps the σ⁻¹ codec rework.

Position invariance is NOT assumed: the data at multiple positions has
size-varying deltas, so this script writes a position-keyed table.  Run
with extra `(x, y, n)` arguments to mine additional positions.

Usage:
    python3 scripts/sigma_inv_real_tt_mining/build_canon_2input_codec_table.py \
        4 4 0 [10 17 0] [16 2 0] ... --save
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "fuzz"))
from bitstream import LutCodec  # noqa: E402

WORK = REPO / "tmp" / "real_tt_mining"
RES = REPO / "results"
ZERO_RBF_PATH = RES / "rbf" / "nv_zero_global.rbf"
P5B_WORK = REPO / "tmp" / "p5b_canon_unique"

# Per-label (mask, safe-name) tables.  Safe names match
# probe_canonicalization_cells.py's _safe(label).
PERM_LABELS = [
    ("a&b", 0x8888, "aandb"), ("a&c", 0xA0A0, "aandc"),
    ("a&d", 0xAA00, "aandd"), ("b&c", 0xC0C0, "bandc"),
    ("b&d", 0xCC00, "bandd"), ("c&d", 0xF000, "candd"),
    ("a|b", 0xEEEE, "aorb"),  ("a|c", 0xFAFA, "aorc"),
    ("a|d", 0xAAFF, "aord"),  ("b|c", 0xFCFC, "borc"),
    ("b|d", 0xCCFF, "bord"),  ("c|d", 0xFFF0, "cord"),
    ("a^b", 0x6666, "axorb"), ("a^c", 0x5A5A, "axorc"),
    ("a^d", 0x55AA, "axord"), ("b^c", 0x3C3C, "bxorc"),
    ("b^d", 0x33CC, "bxord"), ("c^d", 0x0FF0, "cxord"),
]
# 6 unique negation labels (a&b and a|b dup with perm).
NEG_LABELS = [
    ("!a&b", 0x4444, "naandb"), ("a&!b", 0x2222, "aandnb"),
    ("!a&!b", 0x1111, "naandnb"),
    ("!a|b", 0xDDDD, "naorb"),  ("a|!b", 0xBBBB, "aornb"),
    ("!a|!b", 0x7777, "naornb"),
]


def diff_cells(a: bytes, b: bytes) -> set[tuple[int, int]]:
    cells: set[tuple[int, int]] = set()
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


def classify_region(off: int) -> str:
    if off < 5282:
        return "header"
    elif off >= 355530:
        return "block_band"
    return "lab_cram"


def compute_abs(zero: bytes, codec: LutCodec, mask: int, rbf_path: Path) -> set:
    """abs[label] = Quartus_rbf XOR (zero + codec.predict_sram(mask))."""
    quartus = rbf_path.read_bytes()
    codec_out = bytearray(zero)
    for addr, bp in codec.predict_sram(mask):
        codec_out[addr] ^= 1 << bp
    return diff_cells(quartus, bytes(codec_out))


def compute_codec_full_emit(x: int, y: int, n: int, mask: int) -> bytes:
    """Run fasm2rbf on a synthetic FASM that approximates what np2fasm
    would emit for the wire4 single-LE Quartus mining design at (x, y, n)
    WITHOUT canon_2input_aware.  The codec lacks IOB_ROUTE entries for
    PIN_E15/E16/M16/M15 -> X{x}Y{y}N{n}.dataa/b/c/d (single_le_cells
    bucket is quarantined as of 2026-04-24 — see fasm2rbf.py L1185), so
    the achievable codec emit for the canon mining design is:

        IOB_PAD_NV             # E16+M16 input pad infra + G15 output pad infra
        OUTROUTE_G15 X{x}Y{y}N{n}  # SLICE -> G15 routing
        X{x}Y{y}N{n}.LUT = M_L     # LUT predict_sram

    Cells that Quartus's wire4 build emits but the codec cannot reproduce
    here (the per-pin IOB_ROUTE infra) will land in canon_unique[L] as
    residual — that is fine, codec_emit XOR canon_unique = Quartus by
    construction.  When canon_unique is later applied in a DIFFERENT
    design (e.g. cross-LAB at runtime) the codec's IOB_PAD_NV/ROUTE/
    OUTROUTE emissions cover the design-specific cells separately, and
    canon_unique contributes only the residual.

    Returns the rebuilt RBF bytes (368011 bytes).
    """
    P5B_WORK.mkdir(parents=True, exist_ok=True)
    fasm_path = P5B_WORK / f"codec_emit_X{x}Y{y}N{n}_0x{mask:04x}.fasm"
    rbf_path = P5B_WORK / f"codec_emit_X{x}Y{y}N{n}_0x{mask:04x}.rbf"
    fasm_path.write_text(
        f"IOB_PAD_NV\n"
        f"OUTROUTE_G15 X{x}Y{y}N{n}\n"
        f"X{x}Y{y}N{n}.LUT = 0x{mask:04x}\n"
    )
    r = subprocess.run(
        ["python3", str(REPO / "fuzz" / "fasm2rbf.py"), str(fasm_path),
         str(ZERO_RBF_PATH), str(rbf_path)],
        capture_output=True, text=True,
    )
    if r.returncode != 0:
        raise RuntimeError(
            f"fasm2rbf failed for codec_full_emit X{x}Y{y}N{n} 0x{mask:04x}:\n"
            f"STDOUT: {r.stdout[-600:]}\nSTDERR: {r.stderr[-600:]}"
        )
    data = rbf_path.read_bytes()
    if len(data) != 368011:
        raise RuntimeError(f"bad RBF size {len(data)}")
    return data


def compute_canon_unique(codec_rbf: bytes, quartus_rbf_path: Path) -> set:
    """canon_unique[label] = codec_full_emit_rbf XOR Quartus_singleLE_rbf.

    By symmetric-difference algebra, applying canon_unique on top of the
    codec's emission (IOB_PAD_NV + OUTROUTE_G15 + LUT.predict_sram) yields
    the Quartus single-LE wire4 build byte-identical.  Cross-LAB use is
    the next-session validation: in dense designs the codec emits
    additional design directives (IOB_CLK_INPUT, ROUTE, LAB_CLK_SEL_LE,
    cross-LAB OUTROUTE) and canon_unique should overlap minimally — that
    is the property that the P5 analytical gate (2026-05-15) showed was
    violated by the absolute table."""
    quartus = quartus_rbf_path.read_bytes()
    return diff_cells(codec_rbf, quartus)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("positions", nargs="+", type=int,
                    help="Triples of x y n, e.g. 4 4 0 10 17 0")
    ap.add_argument("--save", action="store_true",
                    help="Write results/canon_2input_codec_table.json")
    ap.add_argument("--canon-unique", action="store_true",
                    help="P5b refactor (2026-05-15): for each label also "
                         "compute canon_unique[L] = codec_full_emit_rbf XOR "
                         "Quartus_rbf, where codec_full_emit is fasm2rbf's "
                         "output for `IOB_PAD_NV + OUTROUTE_G15 + LUT=M_L` on "
                         "nv_zero_global.  Writes the parallel sidecar "
                         "results/canon_2input_codec_table_unique.json. "
                         "Subtracting codec-elsewhere directive emissions "
                         "shrinks the per-label cell count in regions the "
                         "codec already covers (lab_cram at LE_A's own LAB "
                         "column, plus hdr cells inside IOB_PAD_NV).  Does "
                         "NOT mutate the absolute table — bitstream.py still "
                         "loads canon_2input_codec_table.json for the codec "
                         "live path until single-LE silicon validation "
                         "confirms canon_unique is sound.")
    args = ap.parse_args()

    if len(args.positions) % 3 != 0:
        print("FAIL: positions must be in (x, y, n) triples", file=sys.stderr)
        sys.exit(2)
    positions = [tuple(args.positions[i:i + 3])
                 for i in range(0, len(args.positions), 3)]

    if not ZERO_RBF_PATH.exists():
        print(f"FAIL: zero baseline missing: {ZERO_RBF_PATH}", file=sys.stderr)
        sys.exit(1)
    zero = ZERO_RBF_PATH.read_bytes()

    out: dict = {
        "positions": positions,
        "per_position": {},
    }
    out_unique: dict = {
        "positions": positions,
        "per_position": {},
        "mining_model": (
            "canon_unique[L] = codec_full_emit_rbf XOR Quartus_singleLE_wire4_rbf. "
            "codec_full_emit = fasm2rbf( 'IOB_PAD_NV; OUTROUTE_G15 X{x}Y{y}N{n}; "
            "X{x}Y{y}N{n}.LUT = M_L' ).  Subtracts the codec's known design-"
            "context emissions (IOB_PAD_NV pad infra, OUTROUTE_G15, LUT "
            "predict_sram) from the absolute mining delta.  Cells the codec "
            "cannot reproduce for the wire4 design (PIN_E15/E16/M16/M15 -> "
            "X{x}Y{y}N{n}.dataa/b/c/d IOB_ROUTE, single_le_cells bucket "
            "quarantined per fasm2rbf.py L1185) remain in canon_unique."
        ),
        "purpose": (
            "P5b refactor (2026-05-15): isolate the canonicalization layer "
            "from design-context infra so it can be applied on top of any "
            "codec build, not only the wire4 mining design.  Validation: "
            "applying canon_unique on top of the same wire4 codec_emit yields "
            "Quartus_singleLE_wire4 byte-identical by construction.  Cross-"
            "LAB validation deferred to next session (flash budget 1/3)."
        ),
    } if args.canon_unique else None

    for (x, y, n) in positions:
        codec = LutCodec.from_cram_model(x, y, n)
        pos_key = f"X{x}Y{y}N{n}"
        print(f"\n=== {pos_key} ===")
        pos_data: dict = {"perm": {}, "neg": {}}
        pos_unique: dict = {"perm": {}, "neg": {}} if args.canon_unique else None
        all_labels = (("perm", PERM_LABELS), ("neg", NEG_LABELS))
        for layer_name, labels in all_labels:
            for lbl, mask, safe in labels:
                rbf_path = WORK / f"canon_{safe}_{pos_key}" / \
                           f"canon_{safe}_{pos_key}.rbf"
                if not rbf_path.exists():
                    print(f"  [{layer_name}] {lbl:>6} (0x{mask:04X}): "
                          f"MISSING cache")
                    continue
                cells = compute_abs(zero, codec, mask, rbf_path)
                regs = {"header": 0, "lab_cram": 0, "block_band": 0}
                for off, bp in cells:
                    regs[classify_region(off)] += 1
                print(f"  [{layer_name}] {lbl:>6} (0x{mask:04X}): "
                      f"abs={len(cells):3d} {regs}", end="")
                pos_data[layer_name][lbl] = {
                    "mask": mask,
                    "cells": sorted([list(c) for c in cells]),
                    "regions": regs,
                }
                if args.canon_unique:
                    codec_rbf = compute_codec_full_emit(x, y, n, mask)
                    uniq_cells = compute_canon_unique(codec_rbf, rbf_path)
                    uniq_regs = {"header": 0, "lab_cram": 0, "block_band": 0}
                    for off, bp in uniq_cells:
                        uniq_regs[classify_region(off)] += 1
                    print(f"  unique={len(uniq_cells):3d} {uniq_regs}")
                    pos_unique[layer_name][lbl] = {
                        "mask": mask,
                        "cells": sorted([list(c) for c in uniq_cells]),
                        "regions": uniq_regs,
                        "abs_minus_unique": (
                            len(cells) - len(uniq_cells)
                        ),
                    }
                else:
                    print()
        out["per_position"][pos_key] = pos_data
        if args.canon_unique:
            out_unique["per_position"][pos_key] = pos_unique

    if args.save:
        out_path = RES / "canon_2input_codec_table.json"
        out_path.write_text(json.dumps(out, indent=2))
        print(f"\nsaved → {out_path}")
        if args.canon_unique:
            out_unique_path = RES / "canon_2input_codec_table_unique.json"
            out_unique_path.write_text(json.dumps(out_unique, indent=2))
            print(f"saved → {out_unique_path}")


if __name__ == "__main__":
    main()
