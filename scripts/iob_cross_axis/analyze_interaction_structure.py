# SPDX-License-Identifier: GPL-3.0-or-later
"""Offline structural analysis of the IOB cross-axis interaction term.

Uses existing tmp/iob_xtest_*.rbf + tmp/iob_bankpair/*.rbf samples to
characterize the joint-placement overhead that linear superposition
can't predict.

Previously falsified models (see memory):
  - linear superposition  (delta_actual == delta_in XOR delta_out)
  - bank-pair lookup      (I depends only on (bank(K), bank(LED)))

This script doesn't build anything new — it re-digests prior builds to
answer finer-grained questions:

  Q1. Is there a universal cross-axis overhead?  (cells flipped in
      EVERY interaction term I(K, LED) ≠ 0 regardless of pins)
  Q2. Does I decompose as I(K, LED) = f(K) ⊕ g(LED)?  (separable)
  Q3. If not separable, are the cells clustered — a small shared
      infra set plus tiny pair-specific tails?

Output: results/iob_cross_axis_interaction.json — per-sample cells,
intersection/union summaries, and the separability verdict.
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(ROOT / "fuzz"))

RBF_DIR = ROOT / "results" / "rbf"
TMP = ROOT / "tmp"
OUT = ROOT / "results" / "iob_cross_axis_interaction.json"

BASE_PATH = RBF_DIR / "iob_in_E15.rbf"        # K=E15, LED=G15 anchor

SAMPLES = [
    # (label, K, LED, xref_path)
    ("xtest_5_6",   "M16", "F15", TMP / "iob_xtest_M16_F15.rbf"),
    ("xtest_8_5",   "A8",  "R16", TMP / "iob_xtest_A8_R16.rbf"),
    ("bp_5_5_a",    "M16", "K15", TMP / "iob_bankpair" / "iob_bankpair_5_5_a_KM16_LK15.rbf"),
    ("bp_5_5_b",    "L16", "K16", TMP / "iob_bankpair" / "iob_bankpair_5_5_b_KL16_LK16.rbf"),
    ("bp_5_4_a",    "M16", "R13", TMP / "iob_bankpair" / "iob_bankpair_5_4_a_KM16_LR13.rbf"),
    ("bp_5_4_b",    "L15", "P9",  TMP / "iob_bankpair" / "iob_bankpair_5_4_b_KL15_LP9.rbf"),
    ("bp_3_4_a",    "T2",  "R13", TMP / "iob_bankpair" / "iob_bankpair_3_4_a_KT2_LR13.rbf"),
    ("bp_3_4_b",    "T8",  "P9",  TMP / "iob_bankpair" / "iob_bankpair_3_4_b_KT8_LP9.rbf"),
    ("bp_5_6_a",    "P15", "F15", TMP / "iob_bankpair" / "iob_bankpair_5_6_a_KP15_LF15.rbf"),
    ("bp_5_6_b",    "R16", "G16", TMP / "iob_bankpair" / "iob_bankpair_5_6_b_KR16_LG16.rbf"),
]


def read_cells(path: Path) -> bytes:
    return path.read_bytes()


def xor(a: bytes, b: bytes) -> bytes:
    return bytes(x ^ y for x, y in zip(a, b))


def popcount_cells(data: bytes) -> list[tuple[int, int]]:
    """Return list of (offset, bp) for every 1-bit in data."""
    cells = []
    for off, v in enumerate(data):
        if v == 0:
            continue
        for bp in range(8):
            if (v >> bp) & 1:
                cells.append((off, bp))
    return cells


def main():
    base = read_cells(BASE_PATH)

    # Pre-compute single-axis deltas from RBFs
    def single_in(pin: str) -> bytes:
        return xor(read_cells(RBF_DIR / f"iob_in_{pin}.rbf"), base)

    def single_out(pin: str) -> bytes:
        p = RBF_DIR / f"iob_out_{pin}.rbf"
        if not p.exists():
            return None
        return xor(read_cells(p), base)

    interactions = {}
    sample_cells = {}
    all_cells = Counter()
    per_K = {}   # cells appearing only in samples with this K
    per_L = {}

    for tag, kpin, lpin, xref in SAMPLES:
        if not xref.exists():
            print(f"[SKIP] {tag}: missing xref {xref}")
            continue
        din = single_in(kpin)
        dout = single_out(lpin)
        if dout is None:
            print(f"[SKIP] {tag}: missing iob_out_{lpin}.rbf")
            continue
        dact = xor(read_cells(xref), base)
        dpred = xor(din, dout)
        I = xor(dact, dpred)
        cells = set(popcount_cells(I))
        interactions[tag] = {
            "K": kpin, "LED": lpin,
            "bytes_nonzero": sum(1 for b in I if b),
            "bits_set": sum(bin(b).count("1") for b in I),
            "cells": sorted(cells),
        }
        sample_cells[tag] = cells
        for c in cells:
            all_cells[c] += 1
        per_K.setdefault(kpin, []).append(tag)
        per_L.setdefault(lpin, []).append(tag)
        print(f"  {tag:12s} K={kpin:4s} L={lpin:4s}  cells={len(cells):4d}  "
              f"bits={interactions[tag]['bits_set']:4d}")

    n = len(sample_cells)
    if n == 0:
        print("no samples")
        return 1

    # Q1: universal overhead — cells in ALL samples
    universal = set.intersection(*sample_cells.values()) if n else set()
    # cells in >= 50% of samples = "widespread" infra
    widespread = {c for c, cnt in all_cells.items() if cnt >= (n + 1) // 2}
    # cells unique to one sample
    unique = {c for c, cnt in all_cells.items() if cnt == 1}
    union = set(all_cells.keys())

    print()
    print(f"  union     : {len(union):4d} cells across {n} samples")
    print(f"  universal : {len(universal):4d} cells in ALL samples")
    print(f"  widespread: {len(widespread):4d} cells in ≥{(n + 1) // 2} samples")
    print(f"  unique    : {len(unique):4d} cells in exactly 1 sample")

    # Q2: separability — test I(K, LED) == f(K) XOR g(LED) for any 2×2
    # subsquare.  Need two samples sharing a K and two sharing a LED.
    # If separable: I(Ka,La) XOR I(Kb,La) = f(Ka) XOR f(Kb) = I(Ka,Lb)
    # XOR I(Kb,Lb), so the 2x2 product is symmetric.
    print()
    print("  separability probes (2x2 sub-squares):")
    # Find pairs of samples (s1, s2) differing in one axis, check joint
    # residue equivalence.
    samp_by_kl = {(d["K"], d["LED"]): set(d["cells"]) for tag, d in interactions.items()}
    pairs = list(samp_by_kl.keys())
    for i in range(len(pairs)):
        for j in range(i + 1, len(pairs)):
            for k in range(len(pairs)):
                if k in (i, j):
                    continue
                for l in range(k + 1, len(pairs)):
                    if l in (i, j):
                        continue
                    (ka, la), (kb, lb) = pairs[i], pairs[j]
                    (kc, lc), (kd, ld) = pairs[k], pairs[l]
                    # Check for a 2×2 sub-square: {Ka,Kb} × {La,Lb}
                    if {ka, kb} == {kc, kd} and {la, lb} == {lc, ld}:
                        I1 = samp_by_kl[pairs[i]]
                        I2 = samp_by_kl[pairs[j]]
                        I3 = samp_by_kl[pairs[k]]
                        I4 = samp_by_kl[pairs[l]]
                        # XOR of all four: if separable = empty set.
                        xor4 = (I1 ^ I2) ^ (I3 ^ I4)
                        print(f"    {{({ka},{la}), ({kb},{lb})}} x "
                              f"{{({kc},{lc}), ({kd},{ld})}}: |xor4|={len(xor4)}")

    # Per-K and per-L partial signatures: do samples sharing a K have
    # a core of common cells?
    print()
    print("  per-K shared cores (K appearing in ≥2 samples):")
    for k, tags in per_K.items():
        if len(tags) >= 2:
            core = set.intersection(*(sample_cells[t] for t in tags))
            tail = set.union(*(sample_cells[t] for t in tags)) - core
            print(f"    K={k:4s} ({len(tags)} samples): core={len(core):3d}  tail={len(tail):3d}")

    print()
    print("  per-L shared cores (L appearing in ≥2 samples):")
    for lpin, tags in per_L.items():
        if len(tags) >= 2:
            core = set.intersection(*(sample_cells[t] for t in tags))
            tail = set.union(*(sample_cells[t] for t in tags)) - core
            print(f"    L={lpin:4s} ({len(tags)} samples): core={len(core):3d}  tail={len(tail):3d}")

    # Write output
    out = {
        "meta": {
            "base": str(BASE_PATH.relative_to(ROOT)),
            "samples": n,
            "union_cells": len(union),
            "universal_cells": len(universal),
            "widespread_cells": len(widespread),
            "unique_cells": len(unique),
        },
        "universal": sorted(universal),
        "widespread": sorted(widespread),
        "per_sample": interactions,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, indent=2))
    print(f"\n  wrote {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
