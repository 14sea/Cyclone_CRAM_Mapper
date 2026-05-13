#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Aggregate the 2-input canonicalization-cell probe across multiple
positions and decide whether the layer is globally position-invariant
(single table sufficient), column-stride invariant, or per-position.

Companion to analyze_canon_phase2.py — same structure, different
input file set. Phase 2 covered 1-input passthrough (`canon_cells_X*Y*N*.json`),
this script covers `canon_cells_X*Y*N*_2input{,_neg}.json` mined via
`probe_canonicalization_cells.py --2input` and `--2input-negation`.

The 2-input data is two disjoint layers:

  * **permutation** (`*_2input.json`) — within-class diffs across AND/OR/XOR
    input-permutation variants (e.g. `a&b` vs `a&c`). 45 labels per
    position (15 within AND + 15 within OR + 15 within XOR).
  * **negation** (`*_2input_neg.json`) — within-class diffs across
    AND_NEG/OR_NEG input-negation variants (e.g. `a&b` vs `!a&b`). 12
    labels per position (6 within AND_NEG + 6 within OR_NEG).

For each label the analyzer:
  1. Loads cell sets at every available position
  2. Splits by region (header / lab_cram / block_band)
  3. Tests H_abs (same absolute (off, bp) across all positions)
  4. Tests H_col (LAB column-stride translation for lab_cram, per Y row)
  5. Computes pairwise jaccard floor

Output: results/canon_cells_2input{,_neg}_summary.json + readable stdout.

If every label is GLOBAL_INVARIANT across ≥3 positions, the script also
emits a candidate canonical table at `canon_table` keyed by frozenset of
label endpoints — that table is the direct input for the codec extension
in P2.2 (`fuzz/bitstream.py` `CANON_2INPUT_PERMUTATION_DIFFS`).

Usage:
    python3 scripts/sigma_inv_real_tt_mining/analyze_canon_2input.py [--save]
    python3 scripts/sigma_inv_real_tt_mining/analyze_canon_2input.py --layer neg [--save]
    python3 scripts/sigma_inv_real_tt_mining/analyze_canon_2input.py --layer both [--save]
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


def load_position(path: Path, shared_config_only: bool = False) -> dict:
    """Load a probe JSON.  When `shared_config_only`, strip lab_cram
    cells from each diff — those are predict_sram-delta cells (position-
    dependent functional minterms) and contaminate the canon-layer
    invariance verdict.  Shared-config-only (header + block_band) is the
    pure canon layer we want to characterise."""
    d = json.loads(path.read_text())
    x, y, n = d["position"]
    out = {"x": x, "y": y, "n": n, "diffs": {}, "path": path}

    def _filter(cells):
        s = {tuple(c) for c in cells}
        if shared_config_only:
            s = {c for c in s if classify_region(c[0]) != "lab_cram"}
        return s

    for k, cells in d.get("axis_diffs", {}).items():
        out["diffs"][f"axis_{k}"] = _filter(cells)
    for k, cells in d.get("negation_diffs", {}).items():
        out["diffs"][f"neg_{k}"] = _filter(cells)
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


def analyze_layer(positions: list[dict], layer_tag: str) -> dict:
    """Run the full position-invariance analysis on one layer of probe
    data. Returns a JSON-friendly summary dict."""
    print(f"\n{'=' * 70}")
    print(f"LAYER: {layer_tag}   ({len(positions)} positions)")
    print(f"{'=' * 70}")

    for p in positions:
        print(f"  X{p['x']}Y{p['y']}N{p['n']}: "
              + ", ".join(f"{k}={len(v)}"
                          for k, v in sorted(p['diffs'].items()))[:120]
              + ("…" if sum(len(v) for v in p['diffs'].values()) > 0 else ""))
    print()

    labels = sorted({k for p in positions for k in p["diffs"]})
    summary = {
        "layer": layer_tag,
        "n_positions": len(positions),
        "positions": [(p["x"], p["y"], p["n"]) for p in positions],
        "labels": labels,
        "per_label": {},
    }

    for label in labels:
        # Region-split cells per position
        per_pos: dict[tuple, dict] = {}
        for p in positions:
            cells = p["diffs"].get(label, set())
            per_pos[(p["x"], p["y"], p["n"])] = split_by_region(cells)

        # Per-region counts
        region_summary = {}
        for region in ("header", "lab_cram", "block_band"):
            counts = {f"X{x}Y{y}N{n}": len(per_pos[(x, y, n)].get(region, set()))
                      for (x, y, n) in per_pos}
            region_summary[region] = counts

        # H_abs per region
        h_abs_per_region = {}
        for region in ("header", "lab_cram", "block_band"):
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
            else:
                h_abs_per_region[region] = None

        # H_col per Y row (LAB column-stride translation, lab_cram only)
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
                target = per_pos[(x, y, n)].get("lab_cram", set())
                if not ref_lab and not target:
                    continue
                best = None
                for k in range(-1, 5):
                    delta = (x - x0) * k * COLUMN_STRIDE
                    translated = {(off + delta, bp) for (off, bp) in ref_lab}
                    inter = translated & target
                    if best is None or len(inter) > best[1]:
                        best = (delta, len(inter), len(ref_lab), len(target))
                if best:
                    mismatches.append({
                        "from": f"X{x0}Y{y}N{n0}",
                        "to": f"X{x}Y{y}N{n}",
                        "best_delta_bytes": best[0],
                        "match": best[1],
                        "ref_count": best[2],
                        "target_count": best[3],
                    })
            if mismatches:
                h_col_per_y[y] = mismatches

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

    # Global invariance verdicts
    print(f"GLOBAL INVARIANCE VERDICT — {layer_tag} ({len(positions)} positions)")
    print("-" * 70)
    n_pos = len(positions)
    verdicts = {}
    for label in labels:
        full_sets = []
        for p in positions:
            cells = p["diffs"].get(label, set())
            full_sets.append(cells)
        if not any(full_sets):
            verdicts[label] = "EMPTY"
            print(f"  {label:32}: EMPTY")
            continue
        inter = set.intersection(*full_sets) if full_sets else set()
        union = set().union(*full_sets)
        sizes = sorted({len(s) for s in full_sets})
        if len(sizes) == 1 and inter == union:
            verdicts[label] = "GLOBAL_INVARIANT"
            print(f"  {label:32}: GLOBAL_INVARIANT  ({len(union)} cells, "
                  f"{n_pos} positions byte-identical)")
        else:
            frac = len(inter) / len(union) if union else 1.0
            verdicts[label] = f"VARIES_{int(frac * 100)}pct_core"
            print(f"  {label:32}: VARIES  sizes={sizes}  "
                  f"core_frac={frac:.2%} ({len(inter)}/{len(union)})")
    summary["verdicts"] = verdicts

    # Canonical table if globally invariant
    all_global = all(v == "GLOBAL_INVARIANT" or v == "EMPTY"
                     for v in verdicts.values())
    if all_global and n_pos >= 3:
        print(f"\n  ✅ All {layer_tag} labels position-invariant across "
              f"{n_pos} positions — single global table sufficient.")
        ref = positions[0]
        canon_table = {
            "n_positions_validated": n_pos,
            "positions": [(p["x"], p["y"], p["n"]) for p in positions],
            "axis_pair_diffs": {
                k.replace("axis_", ""): sorted([list(c) for c in v])
                for k, v in ref["diffs"].items() if k.startswith("axis_")
            },
            "negation_per_class": {
                k.replace("neg_", ""): sorted([list(c) for c in v])
                for k, v in ref["diffs"].items() if k.startswith("neg_")
            },
        }
        summary["canon_table"] = canon_table
    elif n_pos < 3:
        print(f"\n  ⚠️  Only {n_pos} position(s) — need ≥3 for invariance "
              f"verdict. Re-run after mining additional positions.")

    return summary


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--save", action="store_true",
                    help="Write summary JSON to results/")
    ap.add_argument("--layer", choices=("perm", "neg", "both"),
                    default="both",
                    help="Which layer(s) to analyze (default: both).")
    ap.add_argument("--shared-config-only", action="store_true",
                    help="Strip lab_cram cells from each diff before "
                         "running invariance.  lab_cram cells are "
                         "position-dependent (predict_sram delta) and "
                         "contaminate the canon-layer verdict; the "
                         "shared-config part (header + block_band) is "
                         "the pure canon layer.")
    args = ap.parse_args()

    pat_perm = re.compile(r"canon_cells_X(\d+)Y(\d+)N(\d+)_2input\.json$")
    pat_neg = re.compile(r"canon_cells_X(\d+)Y(\d+)N(\d+)_2input_neg\.json$")

    perm_positions = []
    neg_positions = []
    for p in sorted(RES.glob("canon_cells_X*Y*N*_2input*.json")):
        if pat_perm.search(p.name):
            perm_positions.append(load_position(p, args.shared_config_only))
        elif pat_neg.search(p.name):
            neg_positions.append(load_position(p, args.shared_config_only))

    if not perm_positions and not neg_positions:
        print("No canon_cells_X*Y*N*_2input{,_neg}.json found.")
        print("Run probe_canonicalization_cells.py --2input / --2input-negation "
              "to mine positions first.")
        return

    summaries = {}
    if args.layer in ("perm", "both") and perm_positions:
        summaries["permutation"] = analyze_layer(perm_positions,
                                                 "permutation (--2input)")
    if args.layer in ("neg", "both") and neg_positions:
        summaries["negation"] = analyze_layer(neg_positions,
                                              "negation (--2input-negation)")

    if args.save:
        for tag, summary in summaries.items():
            suffix = "_2input" if tag == "permutation" else "_2input_neg"
            out = RES / f"canon_cells{suffix}_summary.json"
            out.write_text(json.dumps(summary, indent=2, default=str))
            print(f"\nsaved → {out}")


if __name__ == "__main__":
    main()
