# SPDX-License-Identifier: GPL-3.0-or-later
"""Parallel driver: run `clk_pin_autoforce_probe.py --pin X` for many pins.

The probe does 6 serial Quartus builds per pin, so we parallelize across
pins with a 4-way worker pool.  Each worker writes its own spine JSON
slice; after all workers finish, we merge back into the single
results/clk_cross_pin_spine_check.json file.
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor, as_completed

REPO = Path(__file__).resolve().parent.parent.parent
PROBE = REPO / "fuzz" / "clk_pin_autoforce_probe.py"
LOGDIR = REPO / "tmp" / "gclk_probe_logs"
LOGDIR.mkdir(parents=True, exist_ok=True)

PRIVATE_DIR = REPO / "tmp" / "gclk_spine_slices"
PRIVATE_DIR.mkdir(parents=True, exist_ok=True)
SPINE_JSON = REPO / "results" / "clk_cross_pin_spine_check.json"


def run_one(pin: str) -> tuple[str, int, float]:
    """Invoke the probe for one pin, writing to a per-pin private JSON.

    We copy the master spine JSON into a sentinel file, redirect the
    probe's output to the sentinel, then read the new per-pin entry
    back into our own slice file.  This avoids races between parallel
    workers writing to the master JSON simultaneously.
    """
    t0 = time.time()
    log = LOGDIR / f"autoforce_{pin}.log"

    # Make a private copy of the spine JSON for this worker to scribble
    # into (the probe does a read→update→write on that file).
    priv = PRIVATE_DIR / f"spine_{pin}.json"
    if SPINE_JSON.exists():
        priv.write_text(SPINE_JSON.read_text())
    env_patch = {"CLK_SPINE_JSON_OVERRIDE": str(priv)}

    with log.open("w") as fh:
        r = subprocess.run(
            ["python3", str(PROBE), "--pin", pin],
            stdout=fh, stderr=subprocess.STDOUT, cwd=str(REPO),
            env={**__import__("os").environ, **env_patch},
        )
    dt = time.time() - t0
    return pin, r.returncode, dt


def merge_slices(pins: list[str]) -> None:
    """Copy each worker's PIN_X entry from its private slice into the
    master JSON, then refresh cross-pin overlap / count metadata."""
    if not SPINE_JSON.exists():
        print(f"[warn] master spine JSON missing at {SPINE_JSON}")
        return
    master = json.loads(SPINE_JSON.read_text())
    sect = master.setdefault("per_pin_forced_vs_auto_intersection", {})

    updated = []
    for pin in pins:
        priv = PRIVATE_DIR / f"spine_{pin}.json"
        if not priv.exists():
            continue
        pdata = json.loads(priv.read_text())
        p_sect = pdata.get("per_pin_forced_vs_auto_intersection", {})
        if f"PIN_{pin}" in p_sect:
            sect[f"PIN_{pin}"] = p_sect[f"PIN_{pin}"]
            updated.append(pin)

    # Refresh overlap / counts
    all_sets = {k: set(tuple(c) for c in v) for k, v in sect.items()}
    legacy_keys = {
        "E1_vs_R8": len(all_sets.get("PIN_E1", set())
                        & all_sets.get("PIN_R8", set())),
        "E1_vs_N1": len(all_sets.get("PIN_E1", set())
                        & all_sets.get("PIN_N1", set())),
        "R8_vs_N1": len(all_sets.get("PIN_R8", set())
                        & all_sets.get("PIN_N1", set())),
        "all_three": len(all_sets.get("PIN_E1", set())
                         & all_sets.get("PIN_R8", set())
                         & all_sets.get("PIN_N1", set())),
    }
    pairs = {}
    keys = sorted(all_sets)
    for i, a in enumerate(keys):
        for b in keys[i + 1:]:
            inter = all_sets[a] & all_sets[b]
            if inter:
                pairs[f"{a}_vs_{b}"] = len(inter)
    master["cross_pin_overlap"] = {**legacy_keys, **pairs}
    master["per_pin_cell_counts"] = {
        k: len(v) for k, v in sorted(all_sets.items())
    }
    SPINE_JSON.write_text(json.dumps(master, indent=2))
    print(f"[merge] updated {len(updated)} pins in master: {updated}")


def main():
    pins = sys.argv[1:]
    if not pins:
        print("usage: mine_gclk_pins_batch.py PIN1 PIN2 ...")
        return 2
    print(f"[start] {len(pins)} pins, 4-way parallel: {pins}")
    results = {}
    with ProcessPoolExecutor(max_workers=4) as ex:
        futs = {ex.submit(run_one, p): p for p in pins}
        for f in as_completed(futs):
            pin, rc, dt = f.result()
            status = "OK" if rc == 0 else f"FAIL(rc={rc})"
            print(f"  [{status}] {pin:4s}  {dt:6.1f}s")
            results[pin] = rc
    print(f"[done] {sum(1 for v in results.values() if v==0)}/{len(results)} OK")
    merge_slices(pins)
    return 0 if all(v == 0 for v in results.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
