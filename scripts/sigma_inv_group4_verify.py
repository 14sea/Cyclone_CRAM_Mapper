#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Verify Group-4 σ⁻¹ closure end-to-end via LutCodec.from_cram_model.

For each of the 128 newly-mined positions (fb8∈{0,1,3,4} × Y∈{14,16} ×
N∈{0..30 step 2}), predict_sram(0xFACE) must match the FACE-probe CRAM
diff on all emitted cells. fb8=7 group=4 is skipped — X=8 has no LAB at
Y≥12 (structural, not a mining failure).
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "fuzz"))
from bitstream import LutCodec  # noqa: E402

MASK = 0xFACE
TARGETS = [(0, 11), (1, 16), (3, 12), (4, 17)]
Y_VALUES = [14, 16]
N_VALS = list(range(0, 32, 2))


def main():
    nv = (REPO / "results" / "rbf" / "nv_zero_global.rbf").read_bytes()
    ok = bad = 0
    for fb8, x in TARGETS:
        for y in Y_VALUES:
            probe = (REPO / "tmp" / "sigma_group4" / f"face_X{x}_Y{y}"
                     / "output_files" / "probe.rbf").read_bytes()
            for n in N_VALS:
                codec = LutCodec.from_cram_model(x, y, n)
                predicted = codec.predict_sram(MASK)
                miss = 0
                for (off, bp) in predicted:
                    nv_bit = (nv[off] >> bp) & 1
                    p_bit = (probe[off] >> bp) & 1
                    if (nv_bit ^ p_bit) != 1:
                        miss += 1
                if miss:
                    bad += 1
                    print(f"FAIL X{x}Y{y}N{n} fb8={fb8}: {miss}/16 cells wrong")
                else:
                    ok += 1
    print(f"\n{ok}/{ok+bad} OK, {bad} failed")
    sys.exit(0 if bad == 0 else 1)


if __name__ == "__main__":
    main()
