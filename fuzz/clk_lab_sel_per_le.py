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
    all_n0_specific: list[set] = []
    all_n4_specific: list[set] = []
    labs_loaded = []

    print(f"Loading {len(files)} probe JSONs...")
    for p in files:
        m = re.match(r"clk_lab_sel_probe_X(\d+)Y(\d+)\.json", p.name)
        if not m:
            continue
        x, y = int(m.group(1)), int(m.group(2))
        data = json.loads(p.read_text())
        per_n = data.get("per_n_forced_vs_auto", {})
        if "0" not in per_n or "4" not in per_n:
            continue
        d0 = set(tuple(c) for c in per_n["0"])
        d4 = set(tuple(c) for c in per_n["4"])
        inter = d0 & d4
        n0_only = d0 - d4
        n4_only = d4 - d0
        out[f"X{x}Y{y}"] = {
            "n0_specific": sorted([list(c) for c in n0_only]),
            "n4_specific": sorted([list(c) for c in n4_only]),
            "n0_count": len(n0_only),
            "n4_count": len(n4_only),
            "n_invariant_count": len(inter),
        }
        all_n0_specific.append(n0_only)
        all_n4_specific.append(n4_only)
        labs_loaded.append((x, y))
        print(f"  LAB({x:2d},{y:2d}): N0-only={len(n0_only):3d}  "
              f"N4-only={len(n4_only):3d}  invariant={len(inter):3d}")

    # Cross-LAB histogram for N0-specific
    for label, sets in (("N0-specific", all_n0_specific),
                       ("N4-specific", all_n4_specific)):
        print(f"\n=== {label} cross-LAB occurrence histogram ===")
        c: Counter = Counter()
        for s in sets:
            for cell in s:
                c[cell] += 1
        h = Counter(c.values())
        for k in sorted(h):
            print(f"  cells appearing in {k:2d}/{len(sets):2d} LABs: {h[k]:4d}")

    # Look for offset-from-LAB-column pattern.
    # CRAM column step = 7350 bytes (per CLAUDE.md). If N0-specific cells
    # always sit at fixed offset-within-column for every LAB, they're
    # encodable as LAB_CLK_SEL_LE.
    #
    # Approximate LAB-column base: offset rounds down to multiple of 7350.
    print(f"\n=== N0-specific offset-within-column analysis ===")
    COL_STEP = 7350
    for (x, y), s in zip(labs_loaded, all_n0_specific):
        # quick sketch: dump (offset mod 7350, bp) per cell, see if pattern
        mods = sorted(set((off % COL_STEP, bp) for off, bp in s))
        print(f"  LAB({x:2d},{y:2d}): {len(s):3d} cells, "
              f"{len(mods):3d} unique (off%7350, bp) tuples")

    out_path = REPO / "results" / "clk_lab_sel_per_le.json"
    out_path.write_text(json.dumps(out, indent=2))
    print(f"\nwrote {out_path}")


if __name__ == "__main__":
    main()
