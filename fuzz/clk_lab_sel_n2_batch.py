# SPDX-License-Identifier: GPL-3.0-or-later
"""Parallel N-slot extension for clk_lab_sel_probe across all mined LABs.

Originally written as the N=2 backfill driver after CLAUDE.md flagged
12 of 14 mined LABs as N ∈ {0, 4} only.  Now generalised: pass the
target N values via --n (default reads N_SLOTS from clk_lab_sel_probe)
and the driver re-runs the probe on any LAB whose JSON is missing
any of those N entries.  The probe caches RBFs under results/rbf/
keyed by tag, so re-running a LAB only triggers the missing slots.

Each LAB gets a unique work_dir so parallel Quartus runs don't
collide; cap at 4 workers per iob_sweep.py precedent.

Usage:
    # extend to N=6, N=8 across every mined LAB
    python3 fuzz/clk_lab_sel_n2_batch.py --n 6,8

    # default: whatever N_SLOTS clk_lab_sel_probe.py declares
    python3 fuzz/clk_lab_sel_n2_batch.py
"""
from __future__ import annotations

import argparse
import json
import multiprocessing as mp
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
RESULTS = REPO / "results"
PROBE = REPO / "fuzz" / "clk_lab_sel_probe.py"
WORK_ROOT = REPO / "tmp" / "clk_lab_sel_n2"


def _default_target_ns() -> tuple[int, ...]:
    """Read N_SLOTS from the probe module so the driver tracks it."""
    sys.path.insert(0, str(REPO / "fuzz"))
    import clk_lab_sel_probe as p
    return tuple(p.N_SLOTS)


def labs_needing_ns(target_ns: tuple[int, ...]) -> list[tuple[int, int]]:
    """Return LABs whose probe JSON is missing any N in target_ns."""
    out = []
    for p in sorted(RESULTS.glob("clk_lab_sel_probe_X*Y*.json")):
        d = json.loads(p.read_text())
        pn = d.get("per_n_forced_vs_auto", {})
        if all(str(n) in pn for n in target_ns):
            continue
        name = p.stem
        # clk_lab_sel_probe_X{x}Y{y}
        xy = name.removeprefix("clk_lab_sel_probe_X")
        xs, ys = xy.split("Y")
        out.append((int(xs), int(ys)))
    return out


def run_one(job):
    x, y = job
    work = WORK_ROOT / f"X{x}Y{y}"
    work.mkdir(parents=True, exist_ok=True)
    cmd = [sys.executable, str(PROBE),
           "--lab", f"{x},{y}",
           "--work", str(work)]
    p = subprocess.run(cmd, cwd=str(REPO),
                       capture_output=True, text=True)
    summary = []
    for line in p.stdout.splitlines():
        if ("LAB CLK_SEL" in line or "shared" in line or
                "[N=" in line or "forced-vs-auto" in line):
            summary.append(line.strip())
    return (x, y), p.returncode, "\n    ".join(summary), p.stderr[:300]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", default=None,
                    help='comma-separated target N slots (default: '
                         'clk_lab_sel_probe.N_SLOTS)')
    args = ap.parse_args()
    if args.n:
        target_ns = tuple(int(x) for x in args.n.split(","))
    else:
        target_ns = _default_target_ns()
    print(f"target N slots: {target_ns}")

    WORK_ROOT.mkdir(parents=True, exist_ok=True)
    pending = labs_needing_ns(target_ns)
    print(f"LABs needing extension: {len(pending)}")
    for x, y in pending:
        print(f"  LAB({x:2d},{y:2d})")
    if not pending:
        print("nothing to do — all mined LABs already cover target N slots")
        return

    workers = min(4, len(pending))
    print(f"\nrunning with {workers} workers...\n", flush=True)
    with mp.Pool(processes=workers) as pool:
        for lab, rc, summary, err in pool.imap_unordered(run_one, pending):
            x, y = lab
            tag = "OK  " if rc == 0 else "FAIL"
            print(f"[{tag}] LAB({x:2d},{y:2d})", flush=True)
            if summary:
                print(f"    {summary}", flush=True)
            if rc != 0 and err:
                print(f"    stderr: {err}", flush=True)

    # Regenerate per_le.json now that more N data is available.
    print("\nRegenerating clk_lab_sel_per_le.json...")
    subprocess.run([sys.executable,
                    str(REPO / "fuzz" / "clk_lab_sel_per_le.py")],
                   cwd=str(REPO))


if __name__ == "__main__":
    main()
