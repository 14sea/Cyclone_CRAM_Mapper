# SPDX-License-Identifier: GPL-3.0-or-later
"""Extract typical LI 9-cell envelopes from the 66-sample column sweep.

Reads every litcol_*.rbf produced by li_mode_column_table.py, groups the
dst-LAB cell sets by classified mode, and prints the frequency histogram
of distinct envelopes per mode. Writes results/li_envelope_typical.json
with the top envelope per mode + traceability metadata.
"""
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "fuzz"))

from bitstream import RouteCodec
from config import LAB_X

RBF_DIR = ROOT / "results" / "rbf"
SRCS = [(3, 5), (17, 8), (25, 15)]
DST_Y = 10
OUT = ROOT / "results" / "li_envelope_typical.json"


def read_dst_cells(codec, design, zero, dx, dy):
    li = codec.read_local_interconnect(design, zero)
    cells = set()
    for e in li:
        lx, ly, p, b = codec._parse_li_name(e[0])
        if (lx, ly) == (dx, dy):
            cells.add((p, b))
    return frozenset(cells)


def classify(cells):
    by_pair = {}
    for p, b in cells:
        by_pair.setdefault(p, set()).add(b)
    if not by_pair:
        return "empty"
    mode, _ = RouteCodec._classify_li_lab(by_pair)
    return mode


def main():
    codec = RouteCodec()

    # Per-src baselines
    zeros = {}
    for sx, sy in SRCS:
        p = RBF_DIR / f"litdec_zero_{sx}_{sy}.rbf"
        if not p.exists():
            print(f"missing baseline: {p}"); return 1
        zeros[(sx, sy)] = p.read_bytes()

    # mode -> Counter[envelope_frozenset]
    by_mode = {"paired": Counter(), "alternating": Counter()}
    n_total = 0
    n_skipped = 0

    for dx in LAB_X:
        srcs_use = [(17, 8), (25, 15)] if dx == 3 else SRCS
        for sx, sy in srcs_use:
            if (sx, sy) == (dx, DST_Y):
                continue
            tag = f"litcol_{sx}_{sy}_to_X{dx}Y{DST_Y}"
            p = RBF_DIR / f"{tag}.rbf"
            if not p.exists():
                continue
            design = p.read_bytes()
            cells = read_dst_cells(codec, design, zeros[(sx, sy)], dx, DST_Y)
            mode = classify(cells)
            if mode in by_mode:
                by_mode[mode][cells] += 1
                n_total += 1
            else:
                n_skipped += 1

    # Histogram + top envelope per mode
    out = {"sample_count": n_total, "skipped": n_skipped, "envelopes": {}}
    for mode, ctr in by_mode.items():
        total = sum(ctr.values())
        print(f"\n=== {mode}  ({total} samples, {len(ctr)} distinct envelopes) ===")
        for env, n in ctr.most_common(8):
            cells_str = " ".join(f"P{p}B{b}" for p, b in sorted(env))
            print(f"  {n:3d}× ({n*100/total:4.1f}%)  {cells_str}")
        top_env, top_n = ctr.most_common(1)[0]
        out["envelopes"][mode] = {
            "cells": sorted([list(c) for c in top_env]),
            "support": top_n,
            "total": total,
            "consensus_pct": round(top_n * 100 / total, 1),
            "n_distinct": len(ctr),
        }

    OUT.write_text(json.dumps(out, indent=2))
    print(f"\nWrote {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
