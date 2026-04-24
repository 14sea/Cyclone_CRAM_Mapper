# SPDX-License-Identifier: GPL-3.0-or-later
"""Batch-driver around `scripts/m9k_mode_quartus_gold_mine.py`.

Iterates over every (X, Y, N=0) M9K site that has an existing
`9x512` INIT anchor in `fuzz/m9k_init_basis.M9K_INIT_ANCHORS`, and
for each site runs the 5-width mining sweep.  Sites without a
calibrated INIT anchor are skipped (the MODE bucket would mine
cleanly, but np2fasm cannot emit `INIT_*` for them anyway, so
mining MODE at those sites is wasted I/O).

Skip rules:
  * (width, depth) = (18, 512) is only calibrated at X15_Y10..14 —
    mined only at those sites.
  * Sites where the bucket is already present with the current
    `quartus_gold_source.date` are skipped unless `--force` is set
    (idempotent re-runs).

Usage::

    # default: mine every eligible site for all 5 widths
    python3 scripts/m9k_mode_quartus_gold_batch.py --workers 4

    # restrict to NEORV32's M9K site list (extracted from
    # see_neorv32_run_linux/quartus/neorv32_demo.fit.rpt):
    python3 scripts/m9k_mode_quartus_gold_batch.py --neorv32

    # single width, for quick sweeps
    python3 scripts/m9k_mode_quartus_gold_batch.py --width 9 --depth 512
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "fuzz"))

from m9k_init_basis import M9K_INIT_ANCHORS  # noqa: E402

RESULTS_PATH = ROOT / "results" / "m9k_mode_bits.json"

# (w, d) combos the mining script handles per mode. Must stay in sync with
# TARGET_COMBOS_BY_MODE in m9k_mode_quartus_gold_mine.py.
ALL_COMBOS = [(4, 2048), (9, 512), (18, 512), (9, 1024), (36, 256), (8, 64)]
ALL_COMBOS_BY_MODE = {
    "sp":  ALL_COMBOS,
    # Per-M9K split geometry — NEORV32 dmem / imem 2048x8 primitives
    # get decomposed into 2x (2048x4) per primitive by Quartus.
    "sdp": [(4, 2048)],
    # M9K TDP per-port width caps at 18 (Cyclone IV datasheet) so the
    # logical 32x32 cpu_regfile splits into 2x (16x32) TDP M9Ks.
    "tdp": [(16, 32)],
}
_BUCKET_FOR_MODE = {
    "sp":  "quartus_gold",
    "sdp": "quartus_gold_sdp",
    "tdp": "quartus_gold_tdp",
}

# (18, 512) INIT anchors are only calibrated for X15_Y10..14 per
# `fuzz/m9k_init_basis.py`. Mining at other Y values would produce
# a bucket, but np2fasm cannot emit INIT_18x512 for the result —
# skip to save Quartus time.
W18_SITES = {(15, y, 0) for y in range(10, 15)}

# (8, 64) is the NEORV32 cache RAM per-M9K geometry.  The Fitter
# places dcache (4 M9Ks) at X15 Y11..Y14 and the 4 icache logical
# instances share X15 Y10 — 5 unique physical M9Ks.  Mining at any
# other site is wasted Quartus time since np2fasm will never emit
# an (8, 64) cell outside this set.
W8_64_SITES = {(15, y, 0) for y in range(10, 15)}

# NEORV32 M9K physical sites (from neorv32_demo.fit.rpt RAM Summary).
NEORV32_SITES = [
    (15, 2, 0), (15, 3, 0), (15, 4, 0), (15, 5, 0), (15, 6, 0),
    (15, 7, 0), (15, 8, 0), (15, 9, 0), (15, 10, 0), (15, 11, 0),
    (15, 12, 0), (15, 13, 0), (15, 14, 0), (15, 15, 0), (15, 16, 0),
    (27, 2, 0), (27, 3, 0), (27, 4, 0), (27, 5, 0), (27, 6, 0),
    (27, 7, 0), (27, 8, 0), (27, 9, 0), (27, 10, 0), (27, 11, 0),
    (27, 12, 0), (27, 13, 0),
]


def _anchor_sites() -> set[tuple[int, int, int]]:
    """Every (X, Y, N=0) with a 9x512 INIT anchor."""
    out: set[tuple[int, int, int]] = set()
    for (site, w, d), _ in M9K_INIT_ANCHORS.items():
        if w != 9 or d != 512:
            continue
        if not site.startswith("X"):
            continue
        # Parse "X15_Y10_N0"
        parts = site.split("_")
        try:
            x = int(parts[0][1:])
            y = int(parts[1][1:])
            n = int(parts[2][1:])
        except Exception:
            continue
        out.add((x, y, n))
    return out


def _already_mined(site_key: str, today: str, mode: str) -> bool:
    if not RESULTS_PATH.exists():
        return False
    data = json.loads(RESULTS_PATH.read_text())
    entry = data.get(site_key)
    if not entry:
        return False
    bucket = _BUCKET_FOR_MODE[mode]
    qg = entry.get("cells_by_template", {}).get(bucket)
    if not qg:
        return False
    src = entry.get(f"{bucket}_source", {})
    return src.get("date") == today


def _mine_one_site_width(x: int, y: int, n: int, w: int, d: int, mode: str,
                          workers: int, dry_run: bool) -> tuple[str, float]:
    site_tag = f"X{x}_Y{y}_N{n}"
    combo_tag = f"{w}x{d}"
    key = f"{site_tag}_{combo_tag}"

    cmd = [
        sys.executable,
        str(ROOT / "scripts/m9k_mode_quartus_gold_mine.py"),
        "--site", f"{x},{y},{n}",
        "--width", str(w), "--depth", str(d),
        "--mode", mode,
        "--workers", str(workers),
    ]
    if dry_run:
        return key, 0.0

    t0 = time.time()
    r = subprocess.run(cmd, capture_output=True, text=True)
    el = time.time() - t0
    tail = "\n".join(r.stdout.splitlines()[-6:])
    if r.returncode != 0:
        print(f"  FAIL  {key}: rc={r.returncode}", flush=True)
        print(f"    stderr tail: {r.stderr.splitlines()[-3:]}", flush=True)
    else:
        # Extract "gold=NN" from summary
        gold = "?"
        for ln in r.stdout.splitlines()[::-1]:
            if "gold=" in ln:
                gold = ln.strip()
                break
        print(f"  OK    {key} in {el:5.1f}s  {gold}", flush=True)
    return key, el


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=4,
                    help="Quartus parallelism per mining call (default 4).")
    ap.add_argument("--width", type=int)
    ap.add_argument("--depth", type=int)
    ap.add_argument("--neorv32", action="store_true",
                    help="Restrict to NEORV32 M9K site list.")
    ap.add_argument("--force", action="store_true",
                    help="Re-mine even if quartus_gold already present today.")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--mode", choices=("sp", "sdp", "tdp"), default="sp",
                    help="altsyncram operation_mode to mine (default sp). "
                         "sdp sweeps (8,2048) for NEORV32 dmem/imem; tdp "
                         "sweeps (32,32) for the regfile. Each mode lands "
                         "in its own cells_by_template bucket — `quartus_gold` "
                         "(SP), `_sdp`, `_tdp` — so re-running does not "
                         "overwrite sibling buckets.")
    args = ap.parse_args()

    if (args.width and not args.depth) or (args.depth and not args.width):
        ap.error("--width and --depth must be supplied together")

    combos = ALL_COMBOS_BY_MODE[args.mode]
    if args.width:
        combos = [(args.width, args.depth)]

    anchor_sites = _anchor_sites()
    target_sites = sorted(anchor_sites)
    if args.neorv32:
        target_sites = [s for s in NEORV32_SITES if s in anchor_sites]
        skipped = [s for s in NEORV32_SITES if s not in anchor_sites]
        if skipped:
            print(f"[batch] NEORV32 sites without INIT anchor "
                  f"(skipped): {skipped}", flush=True)

    today = time.strftime("%Y-%m-%d")
    plan: list[tuple[int, int, int, int, int]] = []
    for (x, y, n) in target_sites:
        for (w, d) in combos:
            if (w, d) == (18, 512) and (x, y, n) not in W18_SITES:
                continue
            if (w, d) == (8, 64) and (x, y, n) not in W8_64_SITES:
                continue
            key = f"X{x}_Y{y}_N{n}_{w}x{d}"
            if _already_mined(key, today, args.mode) and not args.force:
                continue
            plan.append((x, y, n, w, d))

    total_est = len(plan) * 25.0  # ~25s per (site, width) run at 4 workers
    print(f"[batch] mode={args.mode} plan: {len(plan)} mining calls "
          f"(estimated ~{total_est/60:.1f} min @ {args.workers} workers)",
          flush=True)

    if args.dry_run:
        for (x, y, n, w, d) in plan:
            print(f"  would mine X{x}_Y{y}_N{n} {w}x{d} mode={args.mode}")
        return 0

    t_start = time.time()
    results: list[tuple[str, float]] = []
    for i, (x, y, n, w, d) in enumerate(plan, 1):
        print(f"[{i}/{len(plan)}] mining X{x}_Y{y}_N{n} {w}x{d} "
              f"mode={args.mode} ...", flush=True)
        r = _mine_one_site_width(x, y, n, w, d, args.mode,
                                  args.workers, False)
        results.append(r)

    el_total = time.time() - t_start
    print(f"\n[batch] done: {len(results)} runs in {el_total/60:.1f} min",
          flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
