#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Aggregate Phase 1 ownership tables across multiple positions and test
position-invariance of the σ⁻¹ canonicalization-cell layer.

For each pair-diff label (e.g. "a_c", "a_b", "neg_a", ...) the analyzer:

  1. Loads the cell set at every available position
  2. Splits by region (header / lab_cram / block_band)
  3. Tests three invariance hypotheses per region:
        H_abs   — same absolute (off, bp) at every position
        H_col   — offsets shift by ΔX*7350 between positions in the
                  same Y row (column-stride translation; LAB_X cells only)
        H_frac  — fraction of cells matching the strongest hypothesis
  4. Computes pairwise jaccard between positions (sanity floor)

Output: results/canon_cells_phase2_summary.json + readable stdout.

Usage:
    python3 scripts/sigma_inv_real_tt_mining/analyze_canon_phase2.py [--save]

Expected positions on disk: any combination of results/canon_cells_X*Y*N*.json.
"""
from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
RES = REPO / "results"
COLUMN_STRIDE = 7350  # CLAUDE.md: "LAB column step = 7,350 bytes"


def classify_region(off: int) -> str:
    if off < 5282:
        return "header"
    elif off >= 355530:
        return "block_band"
    return "lab_cram"


def load_position(path: Path) -> dict:
    d = json.loads(path.read_text())
    x, y, n = d["position"]
    out = {"x": x, "y": y, "n": n, "diffs": {}}
    for k, cells in d["axis_diffs"].items():
        out["diffs"][f"axis_{k}"] = {tuple(c) for c in cells}
    for k, cells in d["negation_diffs"].items():
        out["diffs"][f"neg_{k}"] = {tuple(c) for c in cells}
    return out


def split_by_region(cells: set) -> dict:
    out = defaultdict(set)
    for off, bp in cells:
        out[classify_region(off)].add((off, bp))
    return dict(out)


def jaccard(a: set, b: set) -> float:
    if not a and not b:
        return 1.0
    inter = len(a & b)
    union = len(a | b)
    return inter / union if union else 0.0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--save", action="store_true",
                    help="Write summary JSON to results/")
    args = ap.parse_args()

    pat = re.compile(r"canon_cells_X(\d+)Y(\d+)N(\d+)\.json")
    positions = []
    for p in sorted(RES.glob("canon_cells_X*Y*N*.json")):
        m = pat.match(p.name)
        if not m:
            continue
        positions.append(load_position(p))

    if not positions:
        print("No canon_cells_*.json found. Run probe Phase 1/2 first.")
        return

    print(f"Loaded {len(positions)} positions:")
    for p in positions:
        print(f"  X{p['x']}Y{p['y']}N{p['n']}: " +
              ", ".join(f"{k}={len(v)}" for k, v in sorted(p['diffs'].items())))
    print()

    # All unique pair-diff labels
    labels = sorted({k for p in positions for k in p["diffs"]})

    summary = {
        "n_positions": len(positions),
        "positions": [(p["x"], p["y"], p["n"]) for p in positions],
        "labels": labels,
        "per_label": {},
    }

    # Per-label cross-position analysis
    for label in labels:
        print(f"=== {label} ===")
        # Region-split cells per position
        per_pos: dict[tuple, dict] = {}
        for p in positions:
            cells = p["diffs"].get(label, set())
            per_pos[(p["x"], p["y"], p["n"])] = split_by_region(cells)

        # Per-region count table
        region_summary = {}
        for region in ("header", "lab_cram", "block_band"):
            counts = {f"X{x}Y{y}N{n}": len(per_pos[(x, y, n)].get(region, set()))
                      for (x, y, n) in per_pos}
            region_summary[region] = counts
            uniq_counts = set(counts.values())
            tag = "uniform" if len(uniq_counts) == 1 else "varies"
            print(f"  {region:11}: {tag} {sorted(counts.values())}")

        # H_abs: same absolute (off,bp) across positions, region-by-region
        h_abs_per_region = {}
        for region in ("header", "lab_cram", "block_band"):
            # intersection of cell sets (cells present at every position)
            cell_sets = [v.get(region, set()) for v in per_pos.values()]
            if any(c for c in cell_sets):
                inter = set.intersection(*cell_sets) if cell_sets else set()
                union = set().union(*cell_sets)
                frac = len(inter) / len(union) if union else 1.0
                h_abs_per_region[region] = {
                    "inter": len(inter),
                    "union": len(union),
                    "frac": round(frac, 3),
                }
                tag = "ALL-POS-INVARIANT" if frac == 1.0 else "partial"
                print(f"  H_abs {region:10}: {len(inter)}/{len(union)} ({frac:.2%}) {tag}")
            else:
                h_abs_per_region[region] = None

        # H_col (LAB_X column-stride translation for lab_cram only)
        # Group positions by Y to control row variance, then check ΔX-stride
        h_col_per_y = {}
        by_y: dict[int, list] = defaultdict(list)
        for (x, y, n) in per_pos:
            by_y[y].append((x, n))
        for y, xn_list in by_y.items():
            if len(xn_list) < 2:
                continue
            xn_list.sort()
            x0, n0 = xn_list[0]
            ref_lab = per_pos[(x0, y, n0)].get("lab_cram", set())
            mismatches = []
            for (x, n) in xn_list[1:]:
                # Translate ref by ΔX * column_stride. (Note: signed; CRAM order
                # may not match LAB_X order — this gives a coarse-grained check.)
                # We test: does the lab_cram cell set at (x,y,n) match a
                # translation of ref_lab by some integer multiple of 7350?
                target = per_pos[(x, y, n)].get("lab_cram", set())
                if not ref_lab and not target:
                    continue
                # Find best Δ in {(x - x0) * k} for k near 1
                best = None
                for k in range(-1, 5):  # small candidate range
                    delta = (x - x0) * k * COLUMN_STRIDE
                    translated = {(off + delta, bp) for (off, bp) in ref_lab}
                    inter = translated & target
                    if best is None or len(inter) > best[1]:
                        best = (delta, len(inter), len(ref_lab), len(target))
                if best:
                    mismatches.append({
                        "from": f"X{x0}Y{y}N{n0}",
                        "to":   f"X{x}Y{y}N{n}",
                        "best_delta_bytes": best[0],
                        "match": best[1],
                        "ref_count": best[2],
                        "target_count": best[3],
                    })
            if mismatches:
                h_col_per_y[y] = mismatches
                for m in mismatches:
                    print(f"  H_col {m['from']}->{m['to']}: best Δ={m['best_delta_bytes']:6d} " +
                          f"match={m['match']}/{m['ref_count']}|{m['target_count']}")

        # Pairwise jaccard floor
        j_pairs = []
        items = sorted(per_pos.items())
        for i in range(len(items)):
            for j in range(i + 1, len(items)):
                ki = items[i][0]
                kj = items[j][0]
                a = set().union(*items[i][1].values())
                b = set().union(*items[j][1].values())
                j_pairs.append({
                    "a": f"X{ki[0]}Y{ki[1]}N{ki[2]}",
                    "b": f"X{kj[0]}Y{kj[1]}N{kj[2]}",
                    "jaccard": round(jaccard(a, b), 3),
                })

        summary["per_label"][label] = {
            "region_counts": region_summary,
            "h_abs_per_region": h_abs_per_region,
            "h_col_per_y": h_col_per_y,
            "jaccard_pairs": j_pairs,
        }
        print()

    # Global invariance verdict
    print("=" * 60)
    print("GLOBAL INVARIANCE VERDICT (per label, all regions union)")
    print("=" * 60)
    n_pos = len(positions)
    verdicts = {}
    for label in labels:
        # Pull union sets per position
        full_sets = []
        for p in positions:
            cells = p["diffs"].get(label, set())
            full_sets.append(cells)
        if not any(full_sets):
            verdicts[label] = "EMPTY"
            print(f"  {label:14}: EMPTY (all positions: 0 cells)")
            continue
        inter = set.intersection(*full_sets) if full_sets else set()
        union = set().union(*full_sets)
        sizes = sorted({len(s) for s in full_sets})
        if len(sizes) == 1 and inter == union:
            verdicts[label] = "GLOBAL_INVARIANT"
            print(f"  {label:14}: GLOBAL_INVARIANT  ({len(union)} cells, "
                  f"{n_pos} positions byte-identical)")
        else:
            frac = len(inter) / len(union) if union else 1.0
            verdicts[label] = f"VARIES ({frac:.0%} core)"
            print(f"  {label:14}: VARIES  size_range={sizes}  "
                  f"core_frac={frac:.2%} (inter {len(inter)}/{len(union)})")

    summary["verdicts"] = verdicts

    # If every label is GLOBAL_INVARIANT, emit the canonical cell table
    all_global = all(v == "GLOBAL_INVARIANT" or v == "EMPTY" for v in verdicts.values())
    if all_global and n_pos >= 3:
        print()
        print("✅ All labels position-invariant across", n_pos, "positions.")
        print("   → Single global canonicalization table is sufficient.")
        # Emit the canonical table from any position (they're all identical)
        ref = positions[0]
        canon_table = {
            "n_positions_validated": n_pos,
            "positions": [(p["x"], p["y"], p["n"]) for p in positions],
            "axis_pair_diffs": {
                k.replace("axis_", ""): sorted([list(c) for c in v])
                for k, v in ref["diffs"].items() if k.startswith("axis_")
            },
            "negation_per_axis": {
                k.replace("neg_", ""): sorted([list(c) for c in v])
                for k, v in ref["diffs"].items() if k.startswith("neg_")
            },
        }
        summary["canon_table"] = canon_table

    if args.save:
        out = RES / "canon_cells_phase2_summary.json"
        # JSON-friendly serialization (no sets, no tuples-as-keys)
        out.write_text(json.dumps(summary, indent=2, default=str))
        print(f"saved → {out}")


if __name__ == "__main__":
    main()
