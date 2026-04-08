# SPDX-License-Identifier: GPL-3.0-or-later
"""Build per-source overhead table against the shared baseline.

For every source LAB with a lits_zero_{sx}_{sy}.rbf, compute the XOR diff
vs results/rbf/baseline.rbf. These are the cells Quartus needs to
instantiate the source-side lut2 driver when the rest of the chip is
empty. Stored to results/source_overhead.json and used by a future
cross-source decomposer (multi-src in the same RBF).
"""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RBF = ROOT / "results" / "rbf"
OUT = ROOT / "results" / "source_overhead.json"

# Reuse the CRC/frame constants
import sys
sys.path.insert(0, str(ROOT / "fuzz"))
from bitstream import (
    CRC_PREAMBLE, CRC_FRAME_SIZE, CRC_DATA_SIZE,
    CRC_FIRST_CRAM_FRAME, CRC_LAST_FRAME,
)


def diff_cells(a, b):
    cells = []
    for n in range(CRC_FIRST_CRAM_FRAME, CRC_LAST_FRAME + 1):
        s = CRC_PREAMBLE + n * CRC_FRAME_SIZE
        for off in range(s, s + CRC_DATA_SIZE):
            x = a[off] ^ b[off]
            if not x:
                continue
            for bp in range(8):
                if (x >> bp) & 1:
                    cells.append([off, bp])
    return cells


def main():
    base = (RBF / "baseline.rbf").read_bytes()
    RE = re.compile(r"lits_zero_(\d+)_(\d+)\.rbf$")
    out = {}
    for p in sorted(RBF.glob("lits_zero_*.rbf")):
        m = RE.match(p.name)
        if not m:
            continue
        sx, sy = int(m[1]), int(m[2])
        cells = diff_cells(p.read_bytes(), base)
        out[f"{sx},{sy}"] = cells
        print(f"  ({sx:2d},{sy:2d}) {len(cells):4d} overhead cells")
    OUT.write_text(json.dumps(out))
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
