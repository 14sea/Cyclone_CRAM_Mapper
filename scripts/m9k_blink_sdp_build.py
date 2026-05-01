# SPDX-License-Identifier: GPL-3.0-or-later
"""SDP M9K full-width blink builder, parameterized by (width, depth).

Simple dual-port: separate write/read addresses, single clock — the
mode NEORV32 uses for its main memory.

Usage:
    python3 scripts/m9k_blink_sdp_build.py --width 8 --depth 1024 \\
        --sites "15,10"
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from m9k_blink_modes import build_one  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--width", type=int, required=True)
    ap.add_argument("--depth", type=int, required=True)
    ap.add_argument("--sites", required=True,
                    help="semicolon-separated X,Y pairs")
    args = ap.parse_args()
    sites = [tuple(int(s) for s in p.split(",")) for p in args.sites.split(";")]
    for x, y in sites:
        print(f"=== SDP {args.width}x{args.depth} X={x} Y={y} ===", flush=True)
        rbf = build_one("sdp", args.width, args.depth, x, y, 0)
        if rbf:
            print(f"  OK -> {rbf}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
