# SPDX-License-Identifier: GPL-3.0-or-later
"""Batch runner for clk_lab_sel_probe across a representative LAB set.

Goals:
  1. Expand LAB_CLK_SEL coverage beyond the 3 mined LABs.
  2. Test the clock-sector hypothesis from clk_lab_sel_audit:
     Y=4 and Y=10 share 17 cells, Y=16 shares 0 with Y=10.
     Are there Y-band clusters that behave uniformly?

Strategy: cover the X=10 column at a range of Y values (constant-X
sweep), plus a couple of cross-LAB anchors for cross-X confirmation.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
RESULTS = REPO / "results"

# Constant-X sweep at X=10 to probe Y-clustering
# + a few cross-X anchors.  Skip already-mined LABs.
TARGETS = [
    # X=10 column sweep (CE6 whitelist Y ∈ {2..14, 16..19, 21})
    (10, 2), (10, 6), (10, 8), (10, 12), (10, 14),
    (10, 18), (10, 21),
    # cross-X anchors for cluster tests
    (16, 4),   # same-Y as LAB(10,4); different-X
    (22, 4),   # same-Y as LAB(10,4); far-X
    (16, 10),  # same-Y as LAB(22,10); different-X
]


def main():
    REPO_SCRIPT = REPO / "fuzz" / "clk_lab_sel_probe.py"
    for i, (x, y) in enumerate(TARGETS, 1):
        out_json = RESULTS / f"clk_lab_sel_probe_X{x}Y{y}.json"
        if out_json.exists():
            print(f"[{i}/{len(TARGETS)}] LAB({x},{y}) cached — skip", flush=True)
            continue
        print(f"[{i}/{len(TARGETS)}] LAB({x},{y}) — running probe", flush=True)
        p = subprocess.run(
            [sys.executable, str(REPO_SCRIPT), "--lab", f"{x},{y}"],
            cwd=str(REPO),
            capture_output=True,
            text=True,
        )
        # Extract just the summary line from stdout
        for line in p.stdout.splitlines():
            if "LAB CLK_SEL" in line or "shared" in line:
                print(f"    {line.strip()}", flush=True)
        if p.returncode != 0:
            print(f"    FAIL rc={p.returncode}: {p.stderr[:200]}", flush=True)


if __name__ == "__main__":
    main()
