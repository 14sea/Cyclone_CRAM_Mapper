# SPDX-License-Identifier: GPL-3.0-or-later
"""Y=10 companion sweep (row invariance check for ff_y4_sweep).

Runs fewer workers (3) so it coexists with an active Y=4 sweep.
"""
import os, sys
from pathlib import Path
HERE = Path(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, str(HERE))
import ff_per_le_placed as base  # noqa: E402
import ff_y4_sweep as y4  # reuse custom_analyze, LAB_X, NS  # noqa: E402

TARGETS = [(x, 10, n) for x in y4.LAB_X for n in y4.NS]

base.TARGETS = TARGETS
base.RBF_DIR = base.REPO / "results" / "rbf" / "ff_y10_sweep"
base.WORK_ROOT = base.REPO / "work_ff_y10_sweep"
base.OUT_JSON = base.REPO / "results" / "ff_y10_sweep.json"
y4.TARGETS = TARGETS
y4.base = base  # rebind for custom_analyze

if __name__ == "__main__":
    base.RBF_DIR.mkdir(parents=True, exist_ok=True)
    base.WORK_ROOT.mkdir(parents=True, exist_ok=True)
    if len(sys.argv) > 1 and sys.argv[1] == "analyze":
        y4.custom_analyze(); sys.exit(0)
    from concurrent.futures import ProcessPoolExecutor, as_completed
    jobs = [(x, y, n, False) for (x, y, n) in TARGETS] + \
           [(x, y, n, True) for (x, y, n) in TARGETS]
    print(f"queueing {len(jobs)} compiles (max_workers=3)")
    with ProcessPoolExecutor(max_workers=3) as ex:
        futs = {ex.submit(base.build_one, j): j for j in jobs}
        done = 0
        for f in as_completed(futs):
            tag, status = f.result(); done += 1
            if done % 20 == 0 or status != "ok":
                print(f"  [{done}/{len(jobs)}] {tag:30s} {status}", flush=True)
    y4.custom_analyze()
