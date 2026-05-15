#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Intersect canon-2input absolute cells between wire2 + wire4 mining contexts.

Hypothesis (P5 refactor, 2026-05-15): the existing canon_2input absolute
table built from wire4 mining (KEY1+KEY2+KEY3+KEY4 pinned) embeds
IOB-routing artifacts for KEY1/KEY4 — cells that aren't LE-internal
canonicalization at all.  Cross-LAB designs that don't pin KEY1/KEY4
end up with 92% of the hdr canon cells double-flipping with their own
IOB directives, breaking the canonicalization.

Test: for canon labels expressible with only dataa+datab (so Quartus
doesn't const-fold them under wire2), mine in BOTH wire2 and wire4
contexts at X4Y4N0 and intersect:
    true_canon[L]    = abs_wire4[L] ∩ abs_wire2[L]   # LE-internal only
    context_wire4[L] = abs_wire4[L] \\ abs_wire2[L]   # KEY1+KEY4 baggage
    context_wire2[L] = abs_wire2[L] \\ abs_wire4[L]   # wire2-only baggage

If hypothesis holds, true_canon ≈ pure lab_cram cells; the wire4-only
slice ≈ the ~120 hdr cells that double-flip in cross-LAB.

Wire2-viable labels at AB axis only (9 of 24 canon labels):
    perm AB: a&b 0x8888, a^b 0x6666, a|b 0xEEEE
    neg    : !a&b 0x4444, a&!b 0x2222, !a&!b 0x1111,
             !a|b 0xDDDD, a|!b 0xBBBB, !a|!b 0x7777

Usage:
    python3 scripts/sigma_inv_real_tt_mining/intersect_canon_2input_wire24.py [--save]
"""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "fuzz"))
sys.path.insert(0, str(REPO / "scripts" / "sigma_inv_real_tt_mining"))
from bitstream import LutCodec  # noqa: E402
from probe_canonicalization_cells import build_one, diff_cells  # noqa: E402

WORK = REPO / "tmp" / "real_tt_mining"
RES  = REPO / "results"
ZERO_RBF = RES / "rbf" / "nv_zero_global.rbf"

X, Y, N = 4, 4, 0

# 9 canon labels expressible over {dataa, datab} only.
WIRE2_VIABLE = [
    ("a&b",   0x8888, "aandb",   "perm"),
    ("a^b",   0x6666, "axorb",   "perm"),
    ("a|b",   0xEEEE, "aorb",    "perm"),
    ("!a&b",  0x4444, "naandb",  "neg"),
    ("a&!b",  0x2222, "aandnb",  "neg"),
    ("!a&!b", 0x1111, "naandnb", "neg"),
    ("!a|b",  0xDDDD, "naorb",   "neg"),
    ("a|!b",  0xBBBB, "aornb",   "neg"),
    ("!a|!b", 0x7777, "naornb",  "neg"),
]


def classify_region(off: int) -> str:
    if off < 5282:    return "hdr"
    if off >= 355530: return "block_band"
    return "lab_cram"


def split_by_region(cells) -> dict:
    r = {"hdr": 0, "lab_cram": 0, "block_band": 0}
    for off, _ in cells:
        r[classify_region(off)] += 1
    return r


def compute_abs(zero: bytes, codec: LutCodec, mask: int, rbf: bytes) -> set:
    codec_out = bytearray(zero)
    for addr, bp in codec.predict_sram(mask):
        codec_out[addr] ^= 1 << bp
    return diff_cells(rbf, bytes(codec_out))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--save", action="store_true",
                    help="Write results/canon_2input_intersect_X4Y4N0.json")
    ap.add_argument("--skip-build", action="store_true",
                    help="Use cached wire2/wire4 RBFs only; fail if missing")
    args = ap.parse_args()

    zero = ZERO_RBF.read_bytes()
    codec = LutCodec.from_cram_model(X, Y, N)
    pos_key = f"X{X}Y{Y}N{N}"

    summary = {
        "position": [X, Y, N],
        "labels": {},
    }

    print(f"=== Intersect mining @ {pos_key} ===\n")
    print(f"  {'label':>7} {'mask':>6}  "
          f"{'w4':>4} {'w2':>4} {'∩':>4} {'w4only':>6} {'w2only':>6}   regions(∩)")
    print("  " + "-"*82)

    for lbl, mask, safe, layer in WIRE2_VIABLE:
        # wire4 cached build (mined earlier by build_canon_2input_codec_table.py)
        w4_name = f"canon_{safe}_{pos_key}"
        w4_path = WORK / w4_name / f"{w4_name}.rbf"
        # wire2 build (new) — name suffix to avoid collision with wire4 cache
        w2_name = f"canon_{safe}_{pos_key}_wire2"
        w2_path = WORK / w2_name / f"{w2_name}.rbf"

        if args.skip_build:
            if not w4_path.exists() or not w2_path.exists():
                print(f"  {lbl:>7} SKIP — missing cache")
                continue
            w4_rbf = w4_path.read_bytes()
            w2_rbf = w2_path.read_bytes()
        else:
            if not w4_path.exists():
                print(f"  {lbl:>7} SKIP — wire4 not cached (run "
                      f"build_canon_2input_codec_table.py first)")
                continue
            w4_rbf = w4_path.read_bytes()
            # Build wire2 if not cached
            w2_rbf = build_one(w2_name, X, Y, N, mask, wire4=False)
            if w2_rbf is None:
                print(f"  {lbl:>7} FAIL wire2 build")
                continue

        abs_w4 = compute_abs(zero, codec, mask, w4_rbf)
        abs_w2 = compute_abs(zero, codec, mask, w2_rbf)
        inter   = abs_w4 & abs_w2
        w4_only = abs_w4 - abs_w2
        w2_only = abs_w2 - abs_w4
        reg_inter = split_by_region(inter)
        print(f"  {lbl:>7} 0x{mask:04X}  "
              f"{len(abs_w4):>4} {len(abs_w2):>4} {len(inter):>4} "
              f"{len(w4_only):>6} {len(w2_only):>6}   {reg_inter}")

        summary["labels"][lbl] = {
            "mask": mask,
            "layer": layer,
            "abs_wire4_count": len(abs_w4),
            "abs_wire2_count": len(abs_w2),
            "intersect_count": len(inter),
            "wire4_only_count": len(w4_only),
            "wire2_only_count": len(w2_only),
            "intersect_regions": reg_inter,
            "wire4_only_regions": split_by_region(w4_only),
            "wire2_only_regions": split_by_region(w2_only),
            "intersect_cells": sorted([list(c) for c in inter]),
        }

    if args.save:
        out = RES / f"canon_2input_intersect_{pos_key}.json"
        out.write_text(json.dumps(summary, indent=2))
        print(f"\nsaved → {out}")


if __name__ == "__main__":
    main()
