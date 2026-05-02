#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Extract the per-bit gap cell set between two RBFs of the same logical
design (open-toolchain output vs Quartus gold), categorize by region.

Used to debug cross-LAB cascade silicon failure (memory:
cross_lab_cascade_silicon_failed_2026_05_04.md).  Output JSON +
human-readable summary to drive codec mining for next session.

Usage:
  python3 scripts/cross_lab/extract_gap.py <open_rbf> <quartus_gold_rbf> [<out.json>]
"""
import json
import sys
from collections import defaultdict
from pathlib import Path


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)
    open_rbf = Path(sys.argv[1]).read_bytes()
    gold_rbf = Path(sys.argv[2]).read_bytes()
    out_path = Path(sys.argv[3]) if len(sys.argv) >= 4 else None

    if len(open_rbf) != len(gold_rbf):
        print(f"length mismatch: open={len(open_rbf)} gold={len(gold_rbf)}")
        sys.exit(1)

    diff_cells = []
    for off in range(len(open_rbf)):
        d = open_rbf[off] ^ gold_rbf[off]
        if d:
            for bp in range(8):
                if d & (1 << bp):
                    diff_cells.append((off, bp))

    def region(off):
        if off < 32:
            return "preamble"
        if (off - 32) < 5200:
            return "header"
        if off > len(open_rbf) - 59:
            return "postamble"
        pos = off - 32
        if (pos % 210) >= 208:
            return "crc"
        return "fabric"

    def info(off):
        pos = off - 32
        return pos // 210, pos % 210

    def cell_dir(off, bp):
        gbit = (gold_rbf[off] >> bp) & 1
        obit = (open_rbf[off] >> bp) & 1
        if gbit == 1 and obit == 0:
            return "MISSING"
        if gbit == 0 and obit == 1:
            return "OVEREMIT"
        return "?"

    by_region = defaultdict(lambda: defaultdict(int))
    block_band = []
    fabric_other = []
    header_cells = []
    for off, bp in diff_cells:
        r = region(off)
        d = cell_dir(off, bp)
        by_region[r][d] += 1
        if r == "fabric":
            fr, _ = info(off)
            if 1692 <= fr <= 1738:
                block_band.append({"off": off, "bp": bp, "dir": d, "frame": fr,
                                    "bif": (off - 32) % 210})
            else:
                fabric_other.append({"off": off, "bp": bp, "dir": d, "frame": fr,
                                      "bif": (off - 32) % 210})
        elif r == "header":
            header_cells.append({"off": off, "bp": bp, "dir": d,
                                  "frame": info(off)[0], "bif": (off - 32) % 210})

    print(f"Total diff cells: {len(diff_cells)}")
    print("By region/direction:")
    for r in by_region:
        print(f"  {r}: {dict(by_region[r])}")
    print(f"\nBlock-band cells (frames 1692..1738): {len(block_band)}")
    print(f"Header cells: {len(header_cells)}")
    print(f"Other fabric cells: {len(fabric_other)}")

    result = {
        "totals": {r: dict(by_region[r]) for r in by_region},
        "block_band": block_band,
        "header": header_cells,
        "fabric_other": fabric_other,
    }
    if out_path:
        out_path.write_text(json.dumps(result, indent=2))
        print(f"\nwrote {out_path}")


if __name__ == "__main__":
    main()
