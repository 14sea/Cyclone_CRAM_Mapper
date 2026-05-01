# SPDX-License-Identifier: GPL-3.0-or-later
"""Build Quartus references at every M9K site NEORV32 places, for the
mode/shape that NEORV32 uses at that site.

Reference: ~/see_neorv32_run_linux/quartus/neorv32_demo.fit.rpt
(captured 2026-04-30; commit current at that snapshot).

Each (mode, w, d, X, Y, N=0) is built once via the per-mode CLI.
Subsequent runs are no-ops if the RBF already exists.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from m9k_blink_modes import build_one  # noqa: E402


# (mode, width, depth, [(X, Y), ...])
NEORV32_PLACEMENTS = [
    # boot ROM (1024×32 split into 4 M9Ks of 32×256 each)
    ("rom", 32, 256, [(15, 10), (15, 11), (15, 12), (15, 13)]),
    # icache cache_ram — 4 logical 8×64 SP packed into 1 physical M9K
    ("sp", 8, 64, [(15, 7)]),
    # cpu_regfile — TDP 32×32 split into 2 M9Ks of 16×32 each
    ("tdp", 16, 32, [(27, 10), (27, 11)]),
    # DMEM + IMEM — 8 SDP 8×2048 instances each split into 2 M9Ks of 8×1024
    ("sdp", 8, 1024,
     [(15, 1), (15, 2), (15, 3), (15, 4), (15, 5), (15, 6), (15, 8), (15, 9),
      (27, 1), (27, 2), (27, 3), (27, 4), (27, 5), (27, 6), (27, 7), (27, 8)]),
]


def main() -> int:
    total = sum(len(sites) for _, _, _, sites in NEORV32_PLACEMENTS)
    print(f"Building {total} Quartus references for NEORV32 M9K sites")
    built = 0
    failed: list[str] = []
    for mode, w, d, sites in NEORV32_PLACEMENTS:
        for x, y in sites:
            print(f"\n=== {mode.upper()} {w}x{d} X={x} Y={y} ===", flush=True)
            rbf = build_one(mode, w, d, x, y, 0)
            if rbf:
                built += 1
                print(f"  OK -> {rbf.relative_to(ROOT)}")
            else:
                tag = f"{mode}_{w}x{d}_X{x}_Y{y}"
                print(f"  FAIL")
                failed.append(tag)
    print(f"\nResults: {built}/{total} built")
    if failed:
        print("Failed:")
        for f in failed:
            print(f"  {f}")
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
