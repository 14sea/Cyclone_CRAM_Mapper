# SPDX-License-Identifier: GPL-3.0-or-later
"""Re-mine the 14 originally-mined LABs with additional N-slots needed
by the NEORV32 design.

The old probes were mined with N={0,2,4,6,8}. The NEORV32 design uses
N values up to N=30 at these LABs.  This script extends each probe
by mining the missing N-slots and rewriting the probe JSON.

Usage:
    python3 scripts/stage_a_audit/remine_old_labs.py --workers 4
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO / "fuzz"))

from mass_clk_sel_mine import (
    process_lab, RESULTS, RBF_DIR, ALL_N_SLOTS, pick_src
)


def get_design_n_slots(fasm_path):
    """Get per-LAB N-slot requirements from FASM."""
    lab_n_slots = defaultdict(set)
    with open(fasm_path) as f:
        for line in f:
            m = re.match(r'LAB_CLK_SEL_LE\s+X(\d+)Y(\d+)N(\d+)', line)
            if m:
                lab_n_slots[(int(m.group(1)), int(m.group(2)))].add(int(m.group(3)))
    return lab_n_slots


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--fasm", default="tmp/ax301_v2.fasm")
    ap.add_argument("--work-base", default="tmp/mass_clk_sel")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    lab_n_slots = get_design_n_slots(args.fasm)

    # Find LABs whose probes exist but are missing needed N-slots
    todo = []
    for p in sorted(RESULTS.glob("clk_lab_sel_probe_X*Y*.json")):
        m = re.search(r'X(\d+)Y(\d+)', p.name)
        x, y = int(m.group(1)), int(m.group(2))
        needed = lab_n_slots.get((x, y), set())
        if not needed:
            continue
        data = json.loads(p.read_text())
        mined = set(int(k) for k in data.get("per_n_forced_vs_auto", {}))
        gap = needed - mined
        if gap:
            # Need to re-mine with the union of mined + needed
            slots = sorted(mined | needed)
            # Ensure at least 3 for intersection
            if len(slots) < 3:
                extras = sorted(set(ALL_N_SLOTS) - set(slots))
                slots.extend(extras[:3 - len(slots)])
                slots = sorted(set(slots))
            todo.append((x, y, sorted(gap), slots))

    print(f"LABs needing N-slot extension: {len(todo)}")
    total_new = sum(len(gap) * 2 for _, _, gap, _ in todo)
    cached = 0
    for x, y, gap, _ in todo:
        sx, sy, sn = pick_src((x, y))
        for n in gap:
            for v in ("FORCE", "AUTO"):
                tag = f"fgclk_{v}_X{sx}Y{sy}N{sn}_to_X{x}Y{y}N{n}"
                if (RBF_DIR / f"{tag}.rbf").exists():
                    cached += 1
    print(f"  New builds: {total_new - cached} (of {total_new}, {cached} cached)")
    for x, y, gap, slots in todo:
        print(f"  LAB({x:2d},{y:2d}): add N={gap}, total slots={len(slots)}")

    if args.dry_run:
        return

    if not todo:
        print("Nothing to do.")
        return

    # Delete existing probes so process_lab rewrites them
    for x, y, _, _ in todo:
        probe = RESULTS / f"clk_lab_sel_probe_X{x}Y{y}.json"
        if probe.exists():
            probe.unlink()

    t0 = time.time()
    work_base = Path(args.work_base)
    done = 0

    with ProcessPoolExecutor(max_workers=args.workers) as ex:
        futures = {
            ex.submit(process_lab, x, y, str(work_base), slots): (x, y)
            for x, y, _, slots in todo
        }
        for fut in as_completed(futures):
            x, y = futures[fut]
            done += 1
            try:
                _, _, _, msg = fut.result()
                print(f"[{done}/{len(todo)}] LAB({x:2d},{y:2d}): {msg}", flush=True)
            except Exception as e:
                print(f"[{done}/{len(todo)}] LAB({x},{y}): EXCEPTION {e}", flush=True)

    print(f"Done in {time.time() - t0:.0f}s")


if __name__ == "__main__":
    # Add parent dir to path for mass_clk_sel_mine import
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    main()
