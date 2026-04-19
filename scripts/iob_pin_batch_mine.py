# SPDX-License-Identifier: GPL-3.0-or-later
"""Batch IOB pin mining for pins missing from iob_cell_map.json.

Identifies pins referenced in a FASM file that lack per_pin_input or
per_pin_output entries, runs iob_sweep.py-style Quartus builds for each,
then regenerates iob_cell_map.json via iob_analyze.py.

Usage:
    python3 scripts/iob_pin_batch_mine.py \
        --fasm tmp/ax301_new.fasm \
        --parallel 6
"""
from __future__ import annotations

import argparse
import json
import multiprocessing as mp
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
RBF_DIR = REPO / "results" / "rbf"
WORK_ROOT = REPO / "tmp" / "iob_pin_mine"

K_REF = "E15"
LED_REF = "G15"

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


def find_missing_pins(fasm_path: str) -> tuple[list[str], list[str]]:
    """Return (missing_in, missing_out) pins from FASM vs iob_cell_map."""
    iob_path = REPO / "results" / "iob_cell_map.json"
    iob_map = json.loads(iob_path.read_text())
    per_pin_in = set(iob_map.get("per_pin_input", {}).keys())
    per_pin_out = set(iob_map.get("per_pin_output", {}).keys())

    needed_in: set[str] = set()
    needed_out: set[str] = set()
    with open(fasm_path) as f:
        for line in f:
            line = line.strip()
            m = re.match(r"IOB_IN\s+PIN_(\w+)$", line)
            if m:
                needed_in.add(m.group(1))
            m = re.match(r"IOB_OUT\s+PIN_(\w+)$", line)
            if m:
                needed_out.add(m.group(1))
    return sorted(needed_in - per_pin_in), sorted(needed_out - per_pin_out)


def build_one(job):
    tag, kpin, lpin, rbf_out = job
    sys.path.insert(0, str(REPO / "fuzz"))
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
        return tag, True, f"{t:.1f}s -> {rbf_out.name}"
    return tag, False, f"FAIL: {(err or '')[:120]}"


def main():
    ap = argparse.ArgumentParser(description="Batch IOB pin mining")
    ap.add_argument("--fasm", required=True, help="FASM file")
    ap.add_argument("--parallel", type=int, default=6)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    missing_in, missing_out = find_missing_pins(args.fasm)
    print(f"Missing IOB_IN pins:  {len(missing_in)}  {missing_in}")
    print(f"Missing IOB_OUT pins: {len(missing_out)}  {missing_out}")

    jobs = []
    for pin in missing_in:
        rbf_out = RBF_DIR / f"iob_in_{pin}.rbf"
        if not rbf_out.exists():
            jobs.append((f"iob_in_{pin}", pin, LED_REF, rbf_out))
    for pin in missing_out:
        rbf_out = RBF_DIR / f"iob_out_{pin}.rbf"
        if not rbf_out.exists():
            jobs.append((f"iob_out_{pin}", K_REF, pin, rbf_out))

    print(f"Jobs to run: {len(jobs)}")
    if args.dry_run:
        for tag, _, _, rbf_out in jobs[:10]:
            print(f"  would build: {tag}")
        return

    if not jobs:
        print("Nothing to mine.")
        return

    WORK_ROOT.mkdir(parents=True, exist_ok=True)
    workers = min(args.parallel, len(jobs))
    print(f"\nMining {len(jobs)} IOB pins with {workers} workers...\n",
          flush=True)

    ok = 0
    fail = 0
    with mp.Pool(processes=workers) as pool:
        for tag, success, msg in pool.imap_unordered(build_one, jobs):
            if success:
                ok += 1
            else:
                fail += 1
            print(f"  [{ok+fail}/{len(jobs)}] {tag}: {msg}", flush=True)

    print(f"\nDone: {ok} OK, {fail} FAIL")

    if ok > 0:
        print("\nRegenerating iob_cell_map.json...")
        import subprocess
        subprocess.run(
            [sys.executable, str(REPO / "fuzz" / "iob_analyze.py")],
            cwd=str(REPO),
        )
        print("Done.")


if __name__ == "__main__":
    main()
