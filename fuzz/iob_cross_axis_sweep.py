# SPDX-License-Identifier: GPL-3.0-or-later
"""IOB cross-axis full K×LED 2D pair sweep — builder only.

Context (2026-04-14 memories `iob_cross_axis_not_decomposable` +
`iob_cross_axis_interaction_structure`): linear superposition and
bank-pair lookup both failed to model the joint-placement interaction
term I(K, LED). Closing the gap requires the full 2D sweep. ~480
Quartus builds.

This script is BUILD-ONLY. It compiles every (K, LED) pair into
`tmp/iob_cross_axis/iob_xy_K{K}_L{L}.rbf`, skipping any that already
exist so it resumes cleanly. Analysis (interaction decomposition,
shared-infra extraction) is a follow-up once the data lands — see
`scripts/iob_cross_axis/analyze_interaction_structure.py` for the
existing 10-sample analyzer which will be generalized.

Same worker-pool pattern as `fuzz/iob_sweep.py` and
`fuzz/clk_lab_sel_n2_batch.py`: 4 concurrent Quartus processes, each
with its own work dir (WORK_ROOT/<tag>), per CLAUDE.md pitfall #3
("don't share work/ across parallel campaigns").

Cost estimate: ~506 pairs (23 K × 22 LED, excluding the single-axis
anchors). Each Quartus fit ~40–90 s. 4-wide: ~2 hours wall clock.

Resumable: the RBF existence check in `build_one` makes this safe to
Ctrl-C and restart. The script returns exit 0 if all pairs land RBFs
on disk. Partial runs do not invalidate analysis later — the analyzer
reads RBFs lazily.

USAGE (do not run during the workday on a shared box):
    export PATH=$PATH:$HOME/intelFPGA_lite/21.1/quartus/bin
    python3 fuzz/iob_cross_axis_sweep.py

To cap runtime, pass `--limit N` to build only the first N missing
pairs — useful for sanity-checking the driver with 4 builds before
committing to the full sweep.
"""
from __future__ import annotations

import argparse
import multiprocessing as mp
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

REPO = Path(__file__).resolve().parent.parent
RBF_DIR = REPO / 'tmp' / 'iob_cross_axis'
WORK_ROOT = REPO / 'tmp' / 'iob_cross_axis_work'

# Reuse the exact pin pools that iob_sweep.py used for single-axis
# mining — guarantees single-axis RBFs (base + delta_in + delta_out)
# exist for every cross-axis pair when the analyzer runs.
K_PINS = [
    "E15", "E16", "M15", "M16",
    "F15", "F16", "K15", "K16", "L15", "L16",
    "A8", "A11", "A14",
    "T2", "T8", "T13",
    "R1", "R5", "R9", "R13", "R16",
    "P1", "P9", "P15",
]
L_PINS = [
    "G15", "F15", "F16", "G16",
    "K15", "K16", "L15", "L16",
    "M15", "M16",
    "A8", "A11", "A14",
    "T2", "T8", "T13",
    "R1", "R5", "R9", "R13", "R16",
    "P1", "P9", "P15",
]

VERILOG = "module iob_probe(input wire K, output wire LED);\n  assign LED = K;\nendmodule\n"

QSF_TMPL = (
    'set_global_assignment -name FAMILY "Cyclone IV E"\n'
    'set_global_assignment -name DEVICE EP4CE6F17C8\n'
    'set_global_assignment -name TOP_LEVEL_ENTITY iob_probe\n'
    'set_global_assignment -name VERILOG_FILE fuzz_top.v\n'
    'set_global_assignment -name PROJECT_OUTPUT_DIRECTORY output_files\n'
    'set_global_assignment -name STRATIX_DEVICE_IO_STANDARD "3.3-V LVTTL"\n'
    'set_location_assignment PIN_{kpin} -to K\n'
    'set_location_assignment PIN_{lpin} -to LED\n'
)


def rbf_path(kpin: str, lpin: str) -> Path:
    return RBF_DIR / f'iob_xy_K{kpin}_L{lpin}.rbf'


def is_single_axis(kpin: str, lpin: str) -> bool:
    """Skip single-axis anchors — already built by iob_sweep.py."""
    return kpin == 'E15' or lpin == 'G15'


def plan_jobs() -> list[tuple[str, str, str]]:
    jobs = []
    for k in K_PINS:
        for l in L_PINS:
            if is_single_axis(k, l):
                continue
            if k == l:  # can't assign two signals to one pin
                continue
            tag = f'iobxy_K{k}_L{l}'
            jobs.append((tag, k, l))
    return jobs


def build_one(job):
    tag, kpin, lpin = job
    out = rbf_path(kpin, lpin)
    if out.exists():
        return tag, True, f'cached -> {out.name}'
    work_dir = WORK_ROOT / tag
    work_dir.mkdir(parents=True, exist_ok=True)
    sys.path.insert(0, str(REPO / 'fuzz'))
    from compile import compile_and_export
    qsf = QSF_TMPL.format(kpin=kpin, lpin=lpin)
    rbf, t, err = compile_and_export(
        tag, VERILOG, qsf,
        rbf_output=str(out),
        work_dir=str(WORK_ROOT),
    )
    if rbf:
        return tag, True, f'{t:.1f}s -> {out.name}'
    return tag, False, f'FAIL ({t:.1f}s): {(err or "")[:160]}'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--limit', type=int, default=0,
                    help='build only the first N missing pairs (0 = all)')
    ap.add_argument('--workers', type=int, default=4,
                    help='parallel Quartus processes (default 4)')
    args = ap.parse_args()

    RBF_DIR.mkdir(parents=True, exist_ok=True)
    WORK_ROOT.mkdir(parents=True, exist_ok=True)

    jobs = plan_jobs()
    pending = [j for j in jobs if not rbf_path(j[1], j[2]).exists()]
    total = len(jobs)
    done = total - len(pending)
    print(f'plan: {total} pairs total, {done} cached, {len(pending)} pending',
          flush=True)
    if args.limit and len(pending) > args.limit:
        pending = pending[:args.limit]
        print(f'--limit {args.limit} active: building {len(pending)} pairs',
              flush=True)
    if not pending:
        print('nothing to do')
        return

    workers = min(args.workers, len(pending))
    print(f'building with {workers} workers...\n', flush=True)
    n_ok = n_fail = 0
    with mp.Pool(processes=workers) as pool:
        for tag, ok, msg in pool.imap_unordered(build_one, pending):
            status = 'OK  ' if ok else 'FAIL'
            print(f'[{status}] {tag:28s} {msg}', flush=True)
            if ok:
                n_ok += 1
            else:
                n_fail += 1

    print(f'\nsweep done: {n_ok} ok, {n_fail} fail, {done + n_ok}/{total} cached on disk',
          flush=True)
    if n_fail:
        sys.exit(1)


if __name__ == '__main__':
    main()
