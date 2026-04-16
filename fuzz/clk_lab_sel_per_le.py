# SPDX-License-Identifier: GPL-3.0-or-later
"""Derive per-(LAB, N) N-specific cell sets from existing probe JSONs.

The current `LAB_CLK_SEL` directive uses only the N-invariant intersection
(N=0 ∩ N=4 of the forced-vs-auto diff). HW flash of the N-invariant
subset at LAB(10,4).N=0 produced LED-always-off, which suggests the
per-LE cells (N=0-specific routing) are functionally required, not
noise.

This script:
  1. Loads every `results/clk_lab_sel_probe_X*Y*.json`
  2. For each, computes N0_specific = diff_N0 − diff_N4
                 N4_specific = diff_N4 − diff_N0
  3. Cross-LAB: does N0-specific have a universal shape (per-N-slot
     offset), or is it per-LAB unique?
  4. Saves `results/clk_lab_sel_per_le.json`

If N=0-specific has a clean pattern (e.g. same offset set per LAB, or
fixed-offset w.r.t. LAB's column base), we can emit
  `LAB_CLK_SEL_LE X{x}Y{y}N{n}`
as a small addition to the existing `LAB_CLK_SEL` directive.
"""
from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def main():
    files = sorted((REPO / "results").glob("clk_lab_sel_probe_X*Y*.json"))
    out: dict[str, dict] = {}
    per_n_sets: dict[str, list[set]] = {}   # n_key -> list of per-LAB cell sets
    labs_loaded = []

    print(f"Loading {len(files)} probe JSONs...")
    for p in files:
        m = re.match(r"clk_lab_sel_probe_X(\d+)Y(\d+)\.json", p.name)
        if not m:
            continue
        x, y = int(m.group(1)), int(m.group(2))
        data = json.loads(p.read_text())
        per_n = data.get("per_n_forced_vs_auto", {})
        # N-specific bucket for any slot S = diff_S − intersection(all N).
        # Require at least 2 N slots so the intersection is meaningful.
        present = {k: set(tuple(c) for c in v) for k, v in per_n.items()}
        if len(present) < 2:
            continue
        inter = set.intersection(*present.values())
        entry: dict = {"n_invariant_count": len(inter)}
        for k, s in present.items():
            only = s - inter
            entry[f"n{k}_specific"] = sorted([list(c) for c in only])
            entry[f"n{k}_count"] = len(only)
            per_n_sets.setdefault(k, []).append(only)
        out[f"X{x}Y{y}"] = entry
        labs_loaded.append((x, y))
        bucket_str = "  ".join(
            f"N{k}-only={len(present[k] - inter):3d}"
            for k in sorted(present, key=int)
        )
        print(f"  LAB({x:2d},{y:2d}): {bucket_str}  "
              f"invariant={len(inter):3d}")

    # Cross-LAB histogram for each per-N-specific bucket.
    for k in sorted(per_n_sets, key=int):
        sets = per_n_sets[k]
        print(f"\n=== N{k}-specific cross-LAB occurrence histogram ===")
        c: Counter = Counter()
        for s in sets:
            for cell in s:
                c[cell] += 1
        h = Counter(c.values())
        for hk in sorted(h):
            print(f"  cells appearing in {hk:2d}/{len(sets):2d} LABs: "
                  f"{h[hk]:4d}")

    # Offset-within-column sketch for the lowest mined N (always present).
    # CRAM column step = 7350 bytes (per CLAUDE.md).  Stable
    # offset%7350 across LABs would suggest a per-N-slot formula.
    if per_n_sets:
        anchor_k = min(per_n_sets, key=int)
        print(f"\n=== N{anchor_k}-specific offset-within-column analysis ===")
        COL_STEP = 7350
        for (x, y), s in zip(labs_loaded, per_n_sets[anchor_k]):
            mods = sorted(set((off % COL_STEP, bp) for off, bp in s))
            print(f"  LAB({x:2d},{y:2d}): {len(s):3d} cells, "
                  f"{len(mods):3d} unique (off%7350, bp) tuples")

    out_path = REPO / "results" / "clk_lab_sel_per_le.json"
    out_path.write_text(json.dumps(out, indent=2))
    print(f"\nwrote {out_path}")


if __name__ == "__main__":
    main()
