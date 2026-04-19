# SPDX-License-Identifier: GPL-3.0-or-later
"""Batch CLK_SEL_LE mining for all LABs referenced in a FASM file.

Identifies LABs from LAB_CLK_SEL / LAB_CLK_SEL_LE directives, runs
clk_lab_sel_probe.py for each unmined LAB, then regenerates
clk_lab_sel_per_le.json.

Usage:
    python3 scripts/clk_sel_batch_mine.py \
        --fasm tmp/ax301_new.fasm \
        --parallel 6
"""
from __future__ import annotations

import argparse
import json
import multiprocessing as mp
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
RESULTS = REPO / "results"
PROBE = REPO / "fuzz" / "clk_lab_sel_probe.py"
WORK_ROOT = REPO / "tmp" / "clk_sel_batch"


def parse_needed_labs(fasm_path: str) -> set[tuple[int, int]]:
    """Extract unique LAB positions from LAB_CLK_SEL* directives."""
    pat_le = re.compile(r"^LAB_CLK_SEL_LE\s+X(\d+)Y(\d+)N(\d+)$")
    pat_lab = re.compile(r"^LAB_CLK_SEL\s+X(\d+)Y(\d+)$")
    labs = set()
    with open(fasm_path) as f:
        for line in f:
            line = line.strip()
            m = pat_le.match(line) or pat_lab.match(line)
            if m:
                labs.add((int(m.group(1)), int(m.group(2))))
    return labs


def find_mined_labs() -> set[tuple[int, int]]:
    """Return LABs that already have probe JSONs with all 16 N slots."""
    mined = set()
    for p in RESULTS.glob("clk_lab_sel_probe_X*Y*.json"):
        try:
            d = json.loads(p.read_text())
        except Exception:
            continue
        pn = d.get("per_n_forced_vs_auto", {})
        all_n = all(str(n) in pn for n in range(0, 31, 2))
        if all_n:
            lab = tuple(d.get("target_lab", []))
            if len(lab) == 2:
                mined.add(lab)
    return mined


def run_one(job: tuple[int, int]) -> tuple[tuple[int, int], int, str]:
    x, y = job
    work = WORK_ROOT / f"X{x}Y{y}"
    work.mkdir(parents=True, exist_ok=True)
    cmd = [
        sys.executable, str(PROBE),
        "--lab", f"{x},{y}",
        "--work", str(work),
    ]
    p = subprocess.run(cmd, cwd=str(REPO), capture_output=True, text=True)
    n_cells = ""
    for line in p.stdout.splitlines():
        if "LAB CLK_SEL" in line:
            n_cells = line.strip()
            break
    return (x, y), p.returncode, n_cells


def main():
    ap = argparse.ArgumentParser(description="Batch CLK_SEL_LE mining")
    ap.add_argument("--fasm", required=True, help="FASM file")
    ap.add_argument("--parallel", type=int, default=6)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    needed = parse_needed_labs(args.fasm)
    print(f"LABs in FASM: {len(needed)}")

    mined = find_mined_labs()
    print(f"Already fully mined (16 N slots): {len(mined)}")

    pending = sorted(needed - mined)
    print(f"Need mining: {len(pending)}")

    if args.dry_run:
        for x, y in pending[:20]:
            print(f"  would mine: LAB({x},{y})")
        if len(pending) > 20:
            print(f"  ... and {len(pending) - 20} more")
        return

    if not pending:
        print("Nothing to mine.")
        return

    WORK_ROOT.mkdir(parents=True, exist_ok=True)
    workers = min(args.parallel, len(pending))
    print(f"\nMining {len(pending)} LABs with {workers} workers...\n",
          flush=True)

    ok = 0
    fail = 0
    with mp.Pool(processes=workers) as pool:
        for i, ((x, y), rc, summary) in enumerate(
            pool.imap_unordered(run_one, pending)
        ):
            if rc == 0:
                ok += 1
                tag = "OK"
            else:
                fail += 1
                tag = "FAIL"
            if (i + 1) % 10 == 0 or rc != 0:
                print(f"  [{i+1}/{len(pending)}] [{tag}] LAB({x},{y}) "
                      f"{summary}  (ok={ok} fail={fail})", flush=True)

    print(f"\nDone: {ok} OK, {fail} FAIL")

    print("\nRegenerating clk_lab_sel_per_le.json...")
    subprocess.run(
        [sys.executable, str(REPO / "fuzz" / "clk_lab_sel_per_le.py")],
        cwd=str(REPO),
    )
    print("Done.")


if __name__ == "__main__":
    main()
