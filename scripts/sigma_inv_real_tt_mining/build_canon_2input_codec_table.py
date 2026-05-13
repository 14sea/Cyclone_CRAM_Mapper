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
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "fuzz"))
from bitstream import LutCodec  # noqa: E402

WORK = REPO / "tmp" / "real_tt_mining"
RES = REPO / "results"
ZERO_RBF_PATH = RES / "rbf" / "nv_zero_global.rbf"

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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("positions", nargs="+", type=int,
                    help="Triples of x y n, e.g. 4 4 0 10 17 0")
    ap.add_argument("--save", action="store_true",
                    help="Write results/canon_2input_codec_table.json")
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

    for (x, y, n) in positions:
        codec = LutCodec.from_cram_model(x, y, n)
        pos_key = f"X{x}Y{y}N{n}"
        print(f"\n=== {pos_key} ===")
        pos_data: dict = {"perm": {}, "neg": {}}
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
                      f"{len(cells):3d} cells {regs}")
                pos_data[layer_name][lbl] = {
                    "mask": mask,
                    "cells": sorted([list(c) for c in cells]),
                    "regions": regs,
                }
        out["per_position"][pos_key] = pos_data

    if args.save:
        out_path = RES / "canon_2input_codec_table.json"
        out_path.write_text(json.dumps(out, indent=2))
        print(f"\nsaved → {out_path}")


if __name__ == "__main__":
    main()
