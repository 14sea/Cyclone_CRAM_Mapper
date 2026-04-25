# SPDX-License-Identifier: GPL-3.0-or-later
"""Anatomize the ~187-cell lab_low/high residual after all 4 directives.

Per-bp distribution + frame distribution + check if residual is shared
across sites (could become another shared bucket)."""
from __future__ import annotations
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "fuzz"))
PRE, FRAME, DPF = 32, 210, 208


def diff_cells(a, b):
    cells = set()
    for off in range(PRE, len(a)):
        if (off - PRE) % FRAME >= DPF:
            continue
        x = a[off] ^ b[off]
        if x:
            for bp in range(8):
                if x & (1 << bp):
                    cells.add((off, bp))
    return cells


def main():
    from m9k_init_basis import M9K_INIT_ANCHORS, init_cell
    from bitstream import patch_rbf_crc

    nv = (ROOT / "results/rbf/nv_zero_global.rbf").read_bytes()
    d3 = json.loads((ROOT / "results/m9k_mode_d3.json").read_text())
    infra = json.loads((ROOT / "results/m9k_column_infra.json").read_text())
    iob = json.loads((ROOT / "results/iob_pin_bank_infra.json").read_text())
    base = ROOT / "tmp/m9k_mode_quartus_gold/4x2048/sdp"

    # Compute residual per site
    sites = sorted(p.name for p in base.iterdir() if p.is_dir() and p.name.startswith("X"))
    residuals = {}
    for site in sites:
        v0 = (base / site / "m9k_mode_gold_4x2048_sdp_v0.rbf").read_bytes()
        target = diff_cells(v0, nv)

        anchor_info = M9K_INIT_ANCHORS.get((site, 4, 2048))
        init_cells = set()
        if anchor_info:
            anchor = anchor_info[0]
            init_bp = anchor_info[1] if len(anchor_info) > 1 else 6
            footprint = set()
            for w in range(2048):
                for b in range(4):
                    try:
                        footprint.add(init_cell(anchor, w, b, init_bp))
                    except Exception:
                        pass
            init_cells = target & footprint

        d3_cells = set(tuple(c) for c in d3.get(site, {}).get("mode_d3_cells", []))
        infra_cells = set(tuple(c) for c in infra.get(site, {}).get("infra_cells", []))
        iob_cells = set(tuple(c) for c in iob.get("per_site", {}).get(site, []))
        union = init_cells | d3_cells | infra_cells | iob_cells

        rebuilt = bytearray(nv)
        for off, bp in union:
            rebuilt[off] ^= 1 << bp
        final = patch_rbf_crc(bytes(rebuilt))
        residuals[site] = diff_cells(final, v0)

    # Cross-site invariance: which residual cells are shared?
    sets = {s: set(residuals[s]) for s in sites}
    intersection = set.intersection(*sets.values())
    union_all = set.union(*sets.values())
    print(f"Residual size per site: min={min(len(s) for s in sets.values())} "
          f"max={max(len(s) for s in sets.values())} "
          f"mean={sum(len(s) for s in sets.values()) / len(sets):.1f}")
    print(f"Cross-site intersection (cells in EVERY site's residual): {len(intersection)}")
    print(f"Cross-site union (cells in ANY site's residual): {len(union_all)}")

    # Per-site uniqueness
    print(f"\nPer-site unique residual counts:")
    deltas = []
    for s in sites:
        unique = sets[s] - intersection
        deltas.append(len(unique))
    print(f"  unique min={min(deltas)} max={max(deltas)} mean={sum(deltas)/len(deltas):.1f}")

    # X15-only and X27-only intersections
    x15 = [s for s in sites if s.startswith("X15_")]
    x27 = [s for s in sites if s.startswith("X27_")]
    if x15:
        i15 = set.intersection(*[sets[s] for s in x15])
        print(f"X15 ({len(x15)}): intersection={len(i15)}, "
              f"X15-only (not in X27 union)={len(i15 - set.union(*[sets[s] for s in x27]))}")
    if x27:
        i27 = set.intersection(*[sets[s] for s in x27])
        print(f"X27 ({len(x27)}): intersection={len(i27)}, "
              f"X27-only (not in X15 union)={len(i27 - set.union(*[sets[s] for s in x15]))}")

    # Region/bp breakdown of intersection
    print(f"\nIntersection cells region/bp:")
    REGIONS = [(0,24,"hdr"),(25,1006,"ll"),(1007,1013,"clk"),
               (1014,1691,"lh"),(1692,1738,"bb"),(1739,1751,"bb_p")]
    def reg(f):
        for lo,hi,n in REGIONS:
            if lo<=f<=hi: return n
        return "?"
    rb = Counter()
    for off, bp in intersection:
        rb[(reg((off-PRE)//FRAME), bp)] += 1
    for k, v in sorted(rb.items()):
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
