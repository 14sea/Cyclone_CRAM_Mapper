# SPDX-License-Identifier: GPL-3.0-or-later
"""Parallel N=2 extension for clk_lab_sel_probe across all mined LABs.

Context: 12 of 14 mined LABs currently have only N ∈ {0, 4}. CLAUDE.md
calls out the remaining gap — extend probe to cover N ∉ {0, 4}.

The probe caches RBFs under results/rbf/ keyed by tag, so re-running a
LAB that already has N=0/N=4 only triggers the missing N=2 Quartus
build. Each LAB gets a unique work_dir so parallel Quartus runs don't
collide; cap at 4 workers per iob_sweep.py precedent.

Usage:
    python3 fuzz/clk_lab_sel_n2_batch.py
"""
from __future__ import annotations

import json
import multiprocessing as mp
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
RESULTS = REPO / "results"
PROBE = REPO / "fuzz" / "clk_lab_sel_probe.py"
WORK_ROOT = REPO / "tmp" / "clk_lab_sel_n2"


def labs_needing_n2() -> list[tuple[int, int]]:
    """Return LABs whose probe JSON is missing N=2."""
    out = []
    for p in sorted(RESULTS.glob("clk_lab_sel_probe_X*Y*.json")):
        d = json.loads(p.read_text())
        pn = d.get("per_n_forced_vs_auto", {})
        if "2" in pn:
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
    WORK_ROOT.mkdir(parents=True, exist_ok=True)
    pending = labs_needing_n2()
    print(f"LABs needing N=2 extension: {len(pending)}")
    for x, y in pending:
        print(f"  LAB({x:2d},{y:2d})")
    if not pending:
        print("nothing to do — all mined LABs already have N=2")
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

    # Regenerate per_le.json now that more N=2 data is available.
    print("\nRegenerating clk_lab_sel_per_le.json...")
    subprocess.run([sys.executable,
                    str(REPO / "fuzz" / "clk_lab_sel_per_le.py")],
                   cwd=str(REPO))


if __name__ == "__main__":
    main()
