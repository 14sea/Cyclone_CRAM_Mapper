# SPDX-License-Identifier: GPL-3.0-or-later
"""Per-feature M9K_MODE corpus miner.

For each parameter-only altsyncram axis (no port topology change),
build base + variant in parallel, compute block_band-restricted delta,
record bucket cells.  Then run pairwise triangle composability checks
across all non-empty deltas.

Output: results/m9k_feature_deltas.json with per-feature bb-cell sets
        + pairwise triangle residual matrix.

Pinout: AX301 + 45-pin PIN_POOL fragment, fixed across all fixtures.
Site: X15_Y10_N0 SP (9, 1024) — 9216-bit M9K (single block).

Builds run in parallel via ProcessPoolExecutor (workers = min(N, cpu_count)).
"""
from __future__ import annotations
import argparse
import json
import sys
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, as_completed
from itertools import combinations
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "fuzz"))
sys.path.insert(0, str(ROOT / "scripts"))

from compile import setup_project, compile_full, generate_rbf  # noqa: E402
from m9k_feature_delta_smoke import (  # noqa: E402
    PRE, FRAME, DPF, _verilog, _qsf, _mif, diff_cells,
    SITE_X, SITE_Y, SITE_N, WIDTH, DEPTH,
)

BLOCK_BAND = (1692, 1738)


def bb_only(cells):
    lo, hi = BLOCK_BAND
    return {(off, bp) for off, bp in cells
            if lo <= (off - PRE) // FRAME <= hi}


# Parameter-only feature axes — do NOT change port topology.  Each
# variant builds the SAME Verilog/QSF as `base` except for the
# altsyncram param overrides listed.  Variants whose param values
# Quartus rejects on this geometry are filtered post-hoc.
REGIONS = [
    (0, 24, "header"),
    (25, 1006, "lab_low"),
    (1007, 1013, "clk_net"),
    (1014, 1691, "lab_high"),
    (1692, 1738, "block_band"),
    (1739, 1751, "block_band_post"),
]


def region_of(frame: int) -> str:
    for lo, hi, name in REGIONS:
        if lo <= frame <= hi:
            return name
    return "?"


# Two-tier corpus.  Tier 1 explores parameter-only axes from a
# minimal base.  Tier 2 stacks features onto outreg=CLOCK0 so
# prerequisites are met (e.g. outdata_aclr only matters when the
# outreg exists).  All ports/pins identical to base — only the
# altsyncram parameter overrides differ.
FEATURE_AXES = {
    "base": {},

    # Tier 1: parameter-only deltas vs minimal base.
    "outdata_reg_a__CLOCK0":             {"outdata_reg_a": "CLOCK0"},
    "rdw_a__NEW_DATA_NO_NBE_READ":       {"read_during_write_mode_port_a": "NEW_DATA_NO_NBE_READ"},
    "rdw_a__NEW_DATA_WITH_NBE_READ":     {"read_during_write_mode_port_a": "NEW_DATA_WITH_NBE_READ"},
    "rdw_mixed__OLD_DATA":               {"read_during_write_mode_mixed_ports": "OLD_DATA"},
    "power_up__TRUE":                    {"power_up_uninitialized": "TRUE"},
    "byte_size__9":                      {"byte_size": "9"},

    # Tier 2: stacked on top of outreg=CLOCK0 so prereq is satisfied.
    "stack_outreg_aclr":                 {"outdata_reg_a": "CLOCK0",
                                          "outdata_aclr_a": "CLEAR0"},
    "stack_outreg_clken_in_BYPASS":      {"outdata_reg_a": "CLOCK0",
                                          "clock_enable_input_a": "BYPASS"},
    "stack_outreg_clken_out_BYPASS":     {"outdata_reg_a": "CLOCK0",
                                          "clock_enable_output_a": "BYPASS"},
    "stack_outreg_byteena_byte9":        {"outdata_reg_a": "CLOCK0",
                                          "byte_size": "9"},
}


def build_one(name: str, overrides: dict[str, str], work_root: str):
    proj = f"corpus_{name}"
    proj_dir = setup_project(proj, _verilog(overrides), _qsf(proj), work_dir=work_root)
    (Path(proj_dir) / "mem_init.mif").write_text(_mif())
    ok, elapsed, err = compile_full(proj, proj_dir, timeout=300)
    if not ok:
        return name, None, elapsed, err
    rbf = generate_rbf(proj, proj_dir)
    return name, rbf, elapsed, ""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=4)
    args = ap.parse_args()

    work_root = ROOT / "tmp" / "m9k_feature_corpus"
    work_root.mkdir(parents=True, exist_ok=True)

    print(f"Building {len(FEATURE_AXES)} fixtures in parallel "
          f"(max_workers={args.workers}) at "
          f"X{SITE_X}_Y{SITE_Y}_N{SITE_N} SP ({WIDTH},{DEPTH})...")

    rbfs: dict[str, Path] = {}
    failed: dict[str, str] = {}
    with ProcessPoolExecutor(max_workers=args.workers) as ex:
        futures = {
            ex.submit(build_one, name, ov, str(work_root)): name
            for name, ov in FEATURE_AXES.items()
        }
        for fut in as_completed(futures):
            name, rbf, elapsed, err = fut.result()
            if rbf is None:
                print(f"  [{name}] FAIL ({elapsed:.1f}s): {err[:200]}")
                failed[name] = err
                continue
            rbfs[name] = Path(rbf)
            print(f"  [{name}] ok ({elapsed:.1f}s)")

    if "base" not in rbfs:
        print("\n✗ base fixture failed — aborting.")
        return 1

    base = rbfs["base"].read_bytes()
    deltas: dict[str, set[tuple[int, int]]] = {}
    full_deltas: dict[str, set[tuple[int, int]]] = {}
    region_breakdowns: dict[str, dict[str, int]] = {}
    print(f"\nDeltas vs base (block_band + region breakdown):")
    print(f"  {'feature':40s} {'bb':>4} {'hdr':>4} {'lab_lo':>6} "
          f"{'lab_hi':>6} {'clk':>4} {'bb_p':>5} {'total':>6}")
    for name, path in rbfs.items():
        if name == "base":
            continue
        feat = path.read_bytes()
        full = diff_cells(feat, base)
        bb = bb_only(full)
        full_deltas[name] = full
        deltas[name] = bb
        rb = Counter(region_of((off - PRE) // FRAME) for off, _ in full)
        region_breakdowns[name] = dict(rb)
        print(f"  {name:40s} {len(bb):>4} {rb.get('header', 0):>4} "
              f"{rb.get('lab_low', 0):>6} {rb.get('lab_high', 0):>6} "
              f"{rb.get('clk_net', 0):>4} {rb.get('block_band_post', 0):>5} "
              f"{len(full):>6}")

    # Pairwise triangle composability.  Only check pairs where BOTH
    # deltas are non-empty (otherwise the test is trivially zero).
    non_empty = {n: d for n, d in deltas.items() if d}
    pairs = list(combinations(sorted(non_empty), 2))
    print(f"\nNon-empty features: {len(non_empty)}")
    print(f"Pairwise triangle pre-checks (XOR-disjoint): {len(pairs)} pairs")
    triangle_pass = 0
    triangle_pre_residuals = []
    for fname, gname in pairs:
        f, g = non_empty[fname], non_empty[gname]
        composed = f.symmetric_difference(g)
        # Pre-check: |F ⊕ G| should equal |F| + |G| if disjoint.
        # We can't test full triangle without building base+F+G, but
        # the disjointness pre-check filters obvious feature collisions.
        if len(composed) == len(f) + len(g):
            triangle_pre_residuals.append((fname, gname, "DISJOINT"))
            triangle_pass += 1
        else:
            overlap = len(f & g)
            triangle_pre_residuals.append(
                (fname, gname, f"OVERLAP {overlap}")
            )

    print(f"  Disjoint pairs: {triangle_pass}/{len(pairs)}")
    print(f"  Overlapping pairs (need joint bucket): "
          f"{len(pairs) - triangle_pass}")
    print()
    for fname, gname, status in triangle_pre_residuals:
        marker = "✓" if status == "DISJOINT" else "⚠"
        print(f"  {marker} {fname:36s} ⊕ {gname:36s}  {status}")

    out = {
        "site": f"X{SITE_X}_Y{SITE_Y}_N{SITE_N}",
        "geometry": f"SP {WIDTH}x{DEPTH}",
        "deltas_block_band": {n: sorted(d) for n, d in deltas.items()},
        "deltas_full": {n: sorted(d) for n, d in full_deltas.items()},
        "delta_bb_counts": {n: len(d) for n, d in deltas.items()},
        "region_breakdowns": region_breakdowns,
        "non_empty_features": sorted(non_empty),
        "pairwise_disjoint_pairs": [
            [f, g] for f, g, s in triangle_pre_residuals if s == "DISJOINT"
        ],
        "pairwise_overlap_pairs": [
            [f, g, s] for f, g, s in triangle_pre_residuals if s != "DISJOINT"
        ],
        "failed_fixtures": list(failed),
    }
    out_path = ROOT / "results" / "m9k_feature_deltas.json"
    out_path.write_text(json.dumps(out, indent=2))
    print(f"\nWrote {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
