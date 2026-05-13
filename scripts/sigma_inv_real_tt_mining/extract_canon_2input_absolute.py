#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""⚠️ EXPLORATORY — superseded by build_canon_2input_codec_table.py.

This script (P2 session 2026-05-13) was an early attempt at the position-
invariance verdict for the 2-input absolute canon-layer cells.  It
filters to shared-config-only (header + block_band), strips lab_cram,
and reports per-label H_abs across mined positions.

Verdict at the 5 mined positions (X4Y4, X10Y17, X16Y2, X22Y17, X28Y2,
N=0): NOT globally position-invariant (10-22 shared-config cells per
label, near-zero cross-position intersection).  The 2-input canon layer
is genuinely per-position; a single global table does NOT close the
gap.

What this script doesn't do: it filters the pair-diff data (which has
already cancelled position-overhead) by region, but the resulting cell
sets are still per-position-specific in their absolute (off, bp) coords.
For the production codec we mine ABSOLUTE per-(label, position) deltas
via build_canon_2input_codec_table.py — which is what
results/canon_2input_codec_table.json + CANON_2INPUT_ABSOLUTE consume.

Kept in-tree as documentation of the dead-end exploration that informed
the per-position absolute-table design.

Original docstring follows.
----

Extract per-label ABSOLUTE 2-input canonicalization cells across mined
positions and decide position-invariance per label.

Rationale (P2.2 design refinement):
    Codec's `predict_sram(M)` writes only `lab_cram` cells; `nv_zero_global`
    has neither lab_cram TT bits nor canon-layer cells.  Therefore for any
    Quartus build of mask M:

        delta = Quartus_rbf XOR nv_zero_global
            = (lab_cram TT)           — matches codec.predict_sram(M)
            + (header + block_band)   — pure canon-layer for label(M)

    Filtering `delta` to header+block_band regions gives the pure canon
    layer per label, independent of position.  If position-invariant
    (likely by analogy to 1-input Phase 2), a single global table indexed
    by P-equivalent 2-input label is sufficient — codec just XOR-applies
    `CANON_2INPUT_ABSOLUTE[label]` on top of `predict_sram(M)`.

Inputs:
    tmp/real_tt_mining/canon_{label_safe}_X{x}Y{y}N{n}/canon_*.rbf
    results/rbf/nv_zero_global.rbf

Outputs:
    results/canon_2input_absolute_summary.json — per-label position-wise
        absolute cells (shared-config-only) + invariance verdict.
    results/canon_2input_absolute_table.json — final codec table when
        every label is GLOBAL_INVARIANT; otherwise omitted.

Usage:
    python3 scripts/sigma_inv_real_tt_mining/extract_canon_2input_absolute.py [--save]
    python3 scripts/sigma_inv_real_tt_mining/extract_canon_2input_absolute.py --layer neg --save
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
WORK = REPO / "tmp" / "real_tt_mining"
RES = REPO / "results"
ZERO_RBF_PATH = RES / "rbf" / "nv_zero_global.rbf"

# Mask tables mirrored from probe_canonicalization_cells.py
AND2 = {"a&b": 0x8888, "a&c": 0xA0A0, "a&d": 0xAA00,
        "b&c": 0xC0C0, "b&d": 0xCC00, "c&d": 0xF000}
OR2 = {"a|b": 0xEEEE, "a|c": 0xFAFA, "a|d": 0xAAFF,
       "b|c": 0xFCFC, "b|d": 0xCCFF, "c|d": 0xFFF0}
XOR2 = {"a^b": 0x6666, "a^c": 0x5A5A, "a^d": 0x55AA,
        "b^c": 0x3C3C, "b^d": 0x33CC, "c^d": 0x0FF0}
AND_NEG = {"a&b": 0x8888, "!a&b": 0x4444, "a&!b": 0x2222, "!a&!b": 0x1111}
OR_NEG = {"a|b": 0xEEEE, "!a|b": 0xDDDD, "a|!b": 0xBBBB, "!a|!b": 0x7777}


def _safe(lbl: str) -> str:
    return (lbl.replace("!", "n")
               .replace("&", "and")
               .replace("|", "or")
               .replace("^", "xor"))


def classify_region(off: int) -> str:
    if off < 5282:
        return "header"
    elif off >= 355530:
        return "block_band"
    return "lab_cram"


def diff_cells(a: bytes, b: bytes) -> set[tuple[int, int]]:
    """Diff two RBFs → set of (off, bp). Skips preamble/postamble/CRC."""
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


def find_positions(layer: str) -> list[tuple[int, int, int]]:
    """Discover mined positions for the requested layer.  Returns sorted
    list of (x, y, n) tuples; only positions where EVERY label of the
    layer has a built RBF are accepted (partial coverage is filtered)."""
    if layer == "perm":
        labels = list(AND2) + list(OR2) + list(XOR2)
    else:
        labels = list(AND_NEG) + list(OR_NEG)
    pat = re.compile(r"canon_.+_X(\d+)Y(\d+)N(\d+)$")
    positions: dict[tuple[int, int, int], set[str]] = defaultdict(set)
    for d in WORK.iterdir():
        if not d.is_dir():
            continue
        m = pat.match(d.name)
        if not m:
            continue
        x, y, n = (int(m.group(1)), int(m.group(2)), int(m.group(3)))
        # Try to recover the label from the safe-encoded prefix.
        rest = d.name[len("canon_"):-len(f"_X{x}Y{y}N{n}")]
        for L in labels:
            if _safe(L) == rest:
                rbf_path = d / f"{d.name}.rbf"
                if rbf_path.exists() and rbf_path.stat().st_size == 368011:
                    positions[(x, y, n)].add(L)
                break
    expected = set(labels)
    return sorted([pos for pos, found in positions.items()
                   if found == expected])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--save", action="store_true")
    ap.add_argument("--layer", choices=("perm", "neg", "both"),
                    default="both")
    ap.add_argument("--include-incomplete", action="store_true",
                    help="Include positions that have only a subset of "
                         "the expected labels (default: skip).")
    args = ap.parse_args()

    if not ZERO_RBF_PATH.exists():
        print(f"FAIL: zero baseline missing: {ZERO_RBF_PATH}", file=sys.stderr)
        sys.exit(1)
    zero = ZERO_RBF_PATH.read_bytes()

    summary: dict = {}
    for layer_tag in ("perm", "neg"):
        if args.layer != "both" and args.layer != layer_tag:
            continue
        labels = ((list(AND2) + list(OR2) + list(XOR2)) if layer_tag == "perm"
                  else (list(AND_NEG) + list(OR_NEG)))

        # Discover positions
        if args.include_incomplete:
            pat = re.compile(r"canon_.+_X(\d+)Y(\d+)N(\d+)$")
            all_positions: set[tuple[int, int, int]] = set()
            for d in WORK.iterdir():
                m = pat.match(d.name) if d.is_dir() else None
                if not m:
                    continue
                x, y, n = (int(m.group(1)), int(m.group(2)),
                           int(m.group(3)))
                rest = d.name[len("canon_"):-len(f"_X{x}Y{y}N{n}")]
                if rest in (_safe(L) for L in labels):
                    rbf_path = d / f"{d.name}.rbf"
                    if rbf_path.exists() and rbf_path.stat().st_size == 368011:
                        all_positions.add((x, y, n))
            positions = sorted(all_positions)
        else:
            positions = find_positions(layer_tag)

        if not positions:
            print(f"[{layer_tag}] no complete positions discovered")
            continue
        print(f"\n{'=' * 70}")
        print(f"LAYER: {layer_tag}  ({len(positions)} positions discovered)")
        print(f"  positions: {positions}")
        print(f"{'=' * 70}")

        # Per (label, position) → shared-config cell set
        per_label_per_pos: dict[str, dict[tuple, set]] = {}
        for L in labels:
            for (x, y, n) in positions:
                rbf_path = (WORK / f"canon_{_safe(L)}_X{x}Y{y}N{n}"
                            / f"canon_{_safe(L)}_X{x}Y{y}N{n}.rbf")
                if not rbf_path.exists():
                    continue
                rbf = rbf_path.read_bytes()
                delta = diff_cells(rbf, zero)
                # Shared config only (header + block_band, NOT lab_cram).
                shared = {c for c in delta
                          if classify_region(c[0]) != "lab_cram"}
                per_label_per_pos.setdefault(L, {})[(x, y, n)] = shared

        # Verdict per label
        layer_summary = {
            "positions": positions,
            "labels": labels,
            "per_label": {},
            "verdicts": {},
        }
        for L in labels:
            per_pos = per_label_per_pos.get(L, {})
            sizes = sorted({len(s) for s in per_pos.values()})
            cell_sets = list(per_pos.values())
            if not cell_sets:
                continue
            inter = set.intersection(*cell_sets) if cell_sets else set()
            union = set().union(*cell_sets)
            verdict_label: str
            if len(sizes) == 1 and inter == union:
                verdict = "GLOBAL_INVARIANT"
                verdict_label = f"GLOBAL_INVARIANT ({len(union)} cells)"
            else:
                frac = len(inter) / len(union) if union else 1.0
                verdict = f"VARIES_{int(frac * 100)}pct_core"
                verdict_label = (f"VARIES sizes={sizes} "
                                 f"core_frac={frac:.2%} "
                                 f"({len(inter)}/{len(union)})")
            print(f"  {L:>8}: {verdict_label}")
            layer_summary["per_label"][L] = {
                "by_position": {f"X{x}Y{y}N{n}": sorted([list(c) for c in s])
                                for (x, y, n), s in per_pos.items()},
                "size_range": sizes,
                "intersection_count": len(inter),
                "union_count": len(union),
            }
            layer_summary["verdicts"][L] = verdict

        # Final table if all labels are GLOBAL_INVARIANT
        all_global = all(v == "GLOBAL_INVARIANT"
                         for v in layer_summary["verdicts"].values())
        if all_global and len(positions) >= 3:
            print(f"  ✅ ALL labels GLOBAL_INVARIANT — codec table ready")
            ref_pos = positions[0]
            layer_summary["canon_absolute_table"] = {
                L: sorted([list(c) for c in
                           per_label_per_pos[L][ref_pos]])
                for L in labels
            }
        elif len(positions) < 3:
            print(f"  ⚠️  {len(positions)} positions — need ≥3 for verdict")

        summary[layer_tag] = layer_summary

    if args.save:
        out = RES / "canon_2input_absolute_summary.json"
        out.write_text(json.dumps(summary, indent=2, default=str))
        print(f"\nsaved → {out}")


if __name__ == "__main__":
    main()
