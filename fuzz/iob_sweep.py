# SPDX-License-Identifier: GPL-3.0-or-later
"""IOB CRAM mining — parallel pin sweep.

Two sweeps:
  - INPUT  sweep: K pin varies, LED pin fixed at G15.  `assign LED = K`.
                  Diff between K=P1 and K=P2 isolates input-IOB cells for P1/P2.
  - OUTPUT sweep: K pin fixed at E15, LED pin varies.  Diff isolates output-IOB.

Builds run in parallel across processes (each gets its own work_dir so
Quartus doesn't collide). All RBFs land in results/rbf/iob_in_{PIN}.rbf
or results/rbf/iob_out_{PIN}.rbf.

Pin pool picked from AX301.tcl covering multiple banks / edges so we can
catch both linear per-pin cells and any bank-shared control bits.
"""
from __future__ import annotations

import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import multiprocessing as mp
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
RBF_DIR = REPO / 'results' / 'rbf'
WORK_ROOT = REPO / 'tmp' / 'iob_sweep'

# Pins known-safe on AX301 (verified via AX301.tcl reference), chosen to
# span banks 1-8, all four edges, and both near/far from the G15 LED.
INPUT_PINS = [
    # KEYs (existing pinprobe_* RBFs are for these, still mine fresh for
    # consistency with current Quartus version).
    "E15", "E16", "M15", "M16",
    # Near-G15 column
    "F15", "F16", "K15", "K16", "L15", "L16",
    # Left edge (top bank)
    "A8", "A11", "A14",
    # Right edge, various rows
    "T2", "T8", "T13",
    "R1", "R5", "R9", "R13", "R16",
    # Top-adjacent
    "P1", "P9", "P15",
]

# For output sweep, pick pins that are:
#   - safe to wire LED=K (output-driving pin)
#   - spread across banks
# Skip pins that collide with K=E15 input location.
OUTPUT_PINS = [
    "G15", "F15", "F16", "G16",     # near-G15 baseline cluster
    "K15", "K16", "L15", "L16",     # mid-right column
    "M15", "M16",                   # KEYs, now as OUTPUT
    "A8", "A11", "A14",
    "T2", "T8", "T13",
    "R1", "R5", "R9", "R13", "R16",
    "P1", "P9", "P15",
]

VERILOG = """module iob_probe(input wire K, output wire LED);
  assign LED = K;
endmodule
"""

QSF_TMPL = """set_global_assignment -name FAMILY "Cyclone IV E"
set_global_assignment -name DEVICE EP4CE6F17C8
set_global_assignment -name TOP_LEVEL_ENTITY iob_probe
set_global_assignment -name VERILOG_FILE fuzz_top.v
set_global_assignment -name PROJECT_OUTPUT_DIRECTORY output_files
set_global_assignment -name STRATIX_DEVICE_IO_STANDARD "3.3-V LVTTL"
set_location_assignment PIN_{kpin} -to K
set_location_assignment PIN_{lpin} -to LED
"""


def build_one(job):
    """Worker: compile one IOB probe design and export the RBF."""
    tag, kpin, lpin, rbf_out = job
    # Import inside worker so each process has its own Quartus state.
    import sys as _sys
    _sys.path.insert(0, str(REPO / 'fuzz'))
    from compile import compile_and_export

    work = WORK_ROOT / tag
    work.mkdir(parents=True, exist_ok=True)
    qsf = QSF_TMPL.format(kpin=kpin, lpin=lpin)
    rbf, t, err = compile_and_export(
        tag, VERILOG, qsf,
        rbf_output=str(rbf_out),
        work_dir=str(WORK_ROOT),
    )
    if rbf:
        return tag, True, f'{t:.1f}s  -> {rbf_out.name}'
    return tag, False, f'FAIL ({t:.1f}s): {err[:200]}'


def plan_jobs():
    jobs = []
    # INPUT sweep: LED = G15 fixed.
    for pin in INPUT_PINS:
        out = RBF_DIR / f'iob_in_{pin}.rbf'
        jobs.append((f'iob_in_{pin}', pin, 'G15', out))
    # OUTPUT sweep: K = E15 fixed.
    for pin in OUTPUT_PINS:
        if pin == 'E15':
            continue  # would collide with K input pin
        out = RBF_DIR / f'iob_out_{pin}.rbf'
        jobs.append((f'iob_out_{pin}', 'E15', pin, out))
    return jobs


def main():
    WORK_ROOT.mkdir(parents=True, exist_ok=True)
    jobs = plan_jobs()
    # Skip jobs whose RBF already exists — lets you resume cleanly.
    pending = [j for j in jobs if not j[3].exists()]
    print(f'{len(pending)}/{len(jobs)} builds pending ({len(jobs) - len(pending)} cached)')

    # Parallelism: cap at 4 to keep the box responsive; Quartus is
    # already multi-threaded internally so pushing past 4 workers
    # rarely helps and thrashes the disk.
    workers = min(4, len(pending) or 1)
    if pending:
        with mp.Pool(processes=workers) as pool:
            for tag, ok, msg in pool.imap_unordered(build_one, pending):
                status = 'OK  ' if ok else 'FAIL'
                print(f'[{status}] {tag:20s}  {msg}', flush=True)


if __name__ == '__main__':
    main()
