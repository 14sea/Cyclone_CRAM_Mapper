# SPDX-License-Identifier: GPL-3.0-or-later
"""Parallel driver: build + mine clock-input pins.

Spawns up to 4 concurrent `compute_clk_pin_hdr.py --build --pin X`
jobs using subprocess, captures stdout/stderr per pin, and prints a
compact summary.  Designed to run from any cwd within the repo.
"""
from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor, as_completed

REPO = Path(__file__).resolve().parent.parent.parent
SCRIPT = REPO / "scripts" / "iob_slice_mining" / "compute_clk_pin_hdr.py"
LOGDIR = REPO / "tmp" / "clk_build_logs"
LOGDIR.mkdir(parents=True, exist_ok=True)


def build_one(pin: str) -> tuple[str, int, float, str]:
    t0 = time.time()
    log = LOGDIR / f"build_{pin}.log"
    with log.open("w") as fh:
        r = subprocess.run(
            ["python3", str(SCRIPT), "--build", "--pin", pin],
            stdout=fh, stderr=subprocess.STDOUT, cwd=str(REPO),
        )
    dt = time.time() - t0
    tail = log.read_text().splitlines()[-4:]
    return pin, r.returncode, dt, "\n".join(tail)


def main():
    pins = sys.argv[1:]
    if not pins:
        print("usage: mine_clk_pins_batch.py PIN1 PIN2 ...")
        return 2
    print(f"[start] {len(pins)} pins, 4-way parallel: {pins}")
    results = {}
    with ProcessPoolExecutor(max_workers=4) as ex:
        futs = {ex.submit(build_one, p): p for p in pins}
        for f in as_completed(futs):
            pin, rc, dt, tail = f.result()
            status = "OK" if rc == 0 else f"FAIL(rc={rc})"
            print(f"  [{status}] {pin:4s}  {dt:6.1f}s")
            if rc != 0:
                print("    tail:")
                for line in tail.splitlines():
                    print(f"      {line}")
            results[pin] = rc
    print(f"[done] {sum(1 for v in results.values() if v==0)}/{len(results)} OK")
    return 0 if all(v == 0 for v in results.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
