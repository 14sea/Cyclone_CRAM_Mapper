# SPDX-License-Identifier: GPL-3.0-or-later
"""Phase 5.2 T3 — per-site M9K signature analyzer (zero-compile).

The Phase 3.27 real-pin probe left 8 archived RBFs on disk:
  m9k_probe_X{15,27}_Y{3,7,11,14,16,18,19}_N0.rbf
plus m9k_baseline_empty.rbf (same harness, no altsyncram).

Phase 5.0 extracted the *shared* 58-cell signature M9K_GLOBAL_ON
from these. This script asks the question that was never asked:
**what are the per-site cells that distinguish one M9K from
another?** If those cells follow a slot/group formula (like LAB
CRAM), we can codec-ify M9K site addressing without running any
new 126-site sweep. If they look random, we fall back to the
planned T3 compile sweep.

Pure analysis, zero compiles. Safe to run right now alongside
the Plan D' factory.

Method:
  per_site_cells(x,y) = cram_cells(baseline, probe_xy) ∩ block_band
  truly_global = intersection over all 8 sites
  per_site_unique(x,y) = per_site_cells(x,y) \\ truly_global
  look for X/Y regularity in per_site_unique

Block band = Phase 5.0 non-LAB config band (frames 1692-1738).
"""
import os, sys, json
from collections import defaultdict
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from m9k_init_null import cram_cells, block_band_cells, BLOCK_FRAMES, FRAME_SIZE
from config import RBF_DIR

PROBES = [
    (15,  3), (15,  7), (15, 11), (15, 14),
    (15, 16), (15, 18), (15, 19), (27, 16),
]
BASELINE = os.path.join(RBF_DIR, "m9k_baseline_empty.rbf")


def frame_of(cell):
    return (cell[0] - 32) // FRAME_SIZE


def rel_in_frame(cell):
    return ((cell[0] - 32) % FRAME_SIZE, cell[1])


def load_site_cells():
    if not os.path.exists(BASELINE):
        print(f"baseline missing: {BASELINE}")
        sys.exit(1)
    base = open(BASELINE, "rb").read()
    out = {}
    for x, y in PROBES:
        p = os.path.join(RBF_DIR, f"m9k_probe_X{x}_Y{y}_N0.rbf")
        if not os.path.exists(p):
            print(f"  MISSING: {p}")
            continue
        other = open(p, "rb").read()
        all_cram = set(cram_cells(base, other))
        blk = set(block_band_cells(sorted(all_cram)))
        out[(x, y)] = {
            "all_cram": all_cram,
            "block_band": blk,
        }
    return out


def main():
    print("=== Phase 5.2 T3 — per-site M9K analyzer (zero-compile) ===\n")
    sites = load_site_cells()
    if len(sites) < 2:
        print("need at least 2 sites")
        return

    print(f"loaded {len(sites)} sites from archive:\n")
    print(f"{'site':>10} | {'all_CRAM':>8} | {'block_band':>10}")
    print("-" * 40)
    for (x, y), d in sorted(sites.items()):
        print(f"  X={x:>2} Y={y:>2} | {len(d['all_cram']):>8} | {len(d['block_band']):>10}")

    # Intersection over block-band across all sites = "truly shared"
    block_sets = [d["block_band"] for d in sites.values()]
    truly_global = set.intersection(*block_sets)
    union_block  = set.union(*block_sets)
    print(f"\nblock-band intersection (truly shared): {len(truly_global)} cells")
    print(f"block-band union:                         {len(union_block)} cells")
    print(f"expected GLOBAL_ON (sqlite tag):          58 cells")

    # Per-site uniques (within block band)
    per_site_unique = {}
    for key, d in sites.items():
        per_site_unique[key] = d["block_band"] - truly_global

    print("\n=== per-site unique cells (block band) ===")
    print(f"{'site':>10} | {'unique':>6} | sample")
    print("-" * 60)
    for key in sorted(per_site_unique):
        u = sorted(per_site_unique[key])
        preview = ", ".join(f"({c[0]},{c[1]})" for c in u[:3])
        if len(u) > 3:
            preview += f" ... +{len(u)-3}"
        print(f"  X={key[0]:>2} Y={key[1]:>2} | {len(u):>6} | {preview}")

    if not any(per_site_unique.values()):
        print("\n>>> ALL BLOCK-BAND CELLS ARE GLOBAL. T3 per-site needs")
        print("    a different band (or a different diff strategy).")
        print("    Recommendation: widen search to full CRAM + remove")
        print("    global set, look for per-site signal in LAB-column")
        print("    CRAM adjacent to X=15/27.")
        # Do the full-CRAM analysis as a fallback
        print("\n=== FALLBACK: full-CRAM per-site unique ===")
        all_sets = [d["all_cram"] for d in sites.values()]
        truly_global_all = set.intersection(*all_sets)
        print(f"full-CRAM intersection: {len(truly_global_all)} cells")
        for key, d in sorted(sites.items()):
            uniq = d["all_cram"] - truly_global_all
            frames = sorted({frame_of(c) for c in uniq})
            fbands = []
            if frames:
                cur = [frames[0]]
                for f in frames[1:]:
                    if f - cur[-1] <= 3:
                        cur.append(f)
                    else:
                        fbands.append((cur[0], cur[-1], len(cur)))
                        cur = [f]
                fbands.append((cur[0], cur[-1], len(cur)))
            top = sorted(fbands, key=lambda b: -b[2])[:3]
            print(f"  X={key[0]:>2} Y={key[1]:>2}: {len(uniq):>4} unique, "
                  f"top frame bands: {top}")
        # Still save the block-band result as empty for audit trail
        _archive(sites, truly_global, per_site_unique, "global-only")
        return

    # ---- geometric regularity hunt ----
    print("\n=== geometry hunt ===")

    # X=15 Y-progression: do unique cells shift by a fixed delta per Y step?
    x15 = sorted([(y, per_site_unique[(15, y)])
                  for y in sorted({y for (x, y) in per_site_unique if x == 15})],
                 key=lambda t: t[0])
    if len(x15) >= 2:
        print(f"\nX=15 Y-progression ({len(x15)} sites):")
        # For each cell in Y=first, look whether it shifts linearly across Y
        # Simpler: emit frame/bp of each unique cell sorted by Y.
        for y, cells in x15:
            cells_sorted = sorted(cells)
            fr = [(frame_of(c), (c[0]-32) % FRAME_SIZE, c[1]) for c in cells_sorted]
            fr_compact = [f"f{f[0]}.{f[1]}.{f[2]}" for f in fr[:6]]
            if len(fr) > 6:
                fr_compact.append(f"... +{len(fr)-6}")
            print(f"  Y={y:>2}: {' '.join(fr_compact)}")

        # Slot/group formula probe: LAB-style encoding uses
        #   group = (y - Y0) // 3, slot = (y - Y0) % 3
        # M9K rows are much taller (one M9K spans many LAB Y rows),
        # so try (y - Y0) // K for K ∈ {1..6} and see if a clean
        # group/slot pattern emerges on frame index or bit position.
        # How much does the X=15 per-site-unique SET actually change with Y?
        # If most cells are invariant, block band is not the Y-discrim band.
        all_x15 = [set(c) for _, c in x15]
        x15_shared = set.intersection(*all_x15)
        x15_union  = set.union(*all_x15)
        print(f"\n  X=15 across {len(x15)} Y values:")
        print(f"    intersection: {len(x15_shared)} cells (Y-invariant)")
        print(f"    union:        {len(x15_union)} cells")
        print(f"    Y-varying:    {len(x15_union) - len(x15_shared)} cells")
        jaccard = len(x15_shared) / len(x15_union) if x15_union else 0
        print(f"    Jaccard (shared/union): {jaccard:.3f}")
        if jaccard > 0.8:
            print("    >>> block band is MOSTLY Y-INVARIANT at X=15.")
            print("    >>> Y signal must live in another band or LAB CRAM.")

        # Byte-offset linearity: does the minimum byte offset of
        # per_site_unique shift linearly with Y?
        min_offs = [(y, min((c[0] for c in cells), default=None))
                    for y, cells in x15]
        min_offs = [(y, o) for y, o in min_offs if o is not None]
        if len(min_offs) >= 3:
            # linear regression slope
            n = len(min_offs)
            sy = sum(y for y, _ in min_offs)
            so = sum(o for _, o in min_offs)
            sxy = sum(y * o for y, o in min_offs)
            sxx = sum(y * y for y, _ in min_offs)
            denom = n * sxx - sy * sy
            if denom:
                slope = (n * sxy - sy * so) / denom
                intercept = (so - slope * sy) / n
                # R^2
                mean_o = so / n
                ss_tot = sum((o - mean_o) ** 2 for _, o in min_offs)
                ss_res = sum((o - (slope * y + intercept)) ** 2
                             for y, o in min_offs)
                r2 = 1 - ss_res / ss_tot if ss_tot else 0
                print(f"\n  byte-offset vs Y (X=15): slope={slope:.2f} "
                      f"bytes/row, intercept={intercept:.1f}, R²={r2:.3f}")
                if r2 > 0.95:
                    print(f"    >>> LINEAR! per-site byte offset ≈ "
                          f"{slope:.1f}*Y + {intercept:.1f}")

        # Full-CRAM Y-discrimination hunt at X=15: where ARE the
        # per-Y cells, if not in the block band?
        print("\n  full-CRAM Y-discrimination hunt at X=15:")
        x15_all = [(y, sites[(15, y)]["all_cram"]) for y, _ in x15]
        x15_all_shared = set.intersection(*(s for _, s in x15_all))
        per_y_unique_all = {}
        for y, s in x15_all:
            per_y_unique_all[y] = s - x15_all_shared
        print(f"    full-CRAM intersection at X=15: {len(x15_all_shared)} cells")
        for y, uniq in sorted(per_y_unique_all.items()):
            frames = sorted({frame_of(c) for c in uniq})
            # Cluster adjacent frames
            bands = []
            if frames:
                cur = [frames[0]]
                for f in frames[1:]:
                    if f - cur[-1] <= 5:
                        cur.append(f)
                    else:
                        bands.append((cur[0], cur[-1], len(cur)))
                        cur = [f]
                bands.append((cur[0], cur[-1], len(cur)))
            top3 = sorted(bands, key=lambda b: -b[2])[:3]
            print(f"    Y={y:>2}: {len(uniq):>4} Y-varying cells, "
                  f"top frame bands: {top3}")

    # X=15 vs X=27 column offset at same Y
    common_y = sorted({y for (x, y) in per_site_unique if x == 15}
                      & {y for (x, y) in per_site_unique if x == 27})
    if common_y:
        print(f"\nX=15 vs X=27 column offset at common Y={common_y}:")
        for y in common_y:
            c15 = sorted(per_site_unique[(15, y)])
            c27 = sorted(per_site_unique[(27, y)])
            print(f"  Y={y}: X=15 → {len(c15)} cells, X=27 → {len(c27)} cells")
            if c15 and c27:
                d = c27[0][0] - c15[0][0]
                print(f"    first-byte delta (X=27 − X=15): {d}")

    _archive(sites, truly_global, per_site_unique, "analyzed")


def _archive(sites, truly_global, per_site_unique, status):
    os.makedirs("results", exist_ok=True)
    out = {
        "status": status,
        "probes": [[x, y] for (x, y) in sorted(sites)],
        "truly_global_block": sorted([list(c) for c in truly_global]),
        "per_site_unique": {
            f"X{x}Y{y}N0": sorted([list(c) for c in per_site_unique[(x, y)]])
            for (x, y) in sorted(per_site_unique)
        },
    }
    path = "results/m9k_persite_analyze.json"
    with open(path, "w") as f:
        json.dump(out, f, indent=1)
    print(f"\narchived {path}")


if __name__ == "__main__":
    main()
