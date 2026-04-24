#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Verify Y=3 σ⁻¹ closure end-to-end: for every (fb8 × N∈{12..30}) position,
LutCodec.from_cram_model(x, 3, n).predict_sram(0xFACE) must match the
actual CRAM-byte diff of the mining probe RBF vs the zero baseline on the
cells returned by predict_sram.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "fuzz"))
from bitstream import LutCodec  # noqa: E402

MASK = 0xFACE
N_VALS = list(range(12, 32, 2))
TARGETS = [
    (0, 3,  "sigma_existing_groups"),
    (1, 6,  "sigma_existing_groups"),
    (2, 21, "sigma_fb8_mine"),
    (3, 4,  "sigma_existing_groups"),
    (4, 7,  "sigma_existing_groups"),
    (5, 10, "sigma_fb8_mine"),
    (6, 13, "sigma_fb8_mine"),
    (7, 8,  "sigma_existing_groups"),
]


def main():
    nv = (REPO / "results" / "rbf" / "nv_zero_global.rbf").read_bytes()
    assert len(nv) == 368011
    ok = 0
    bad = 0
    for fb8, x, sub in TARGETS:
        probe_path = REPO / "tmp" / sub / f"face_X{x}_Y3" / "output_files" / "probe.rbf"
        probe = probe_path.read_bytes()
        for n in N_VALS:
            codec = LutCodec.from_cram_model(x, 3, n)
            predicted = codec.predict_sram(MASK)
            mismatches = 0
            for (off, bp) in predicted:
                nv_bit = (nv[off] >> bp) & 1
                p_bit = (probe[off] >> bp) & 1
                if (nv_bit ^ p_bit) != 1:
                    mismatches += 1
            # Also ensure we flipped every bit the probe actually flips
            # in this (foff, fb8, wrap-bp) slice; the 16 predicted cells
            # should be exactly the cells in bp=7 that changed at these
            # foff positions. Not re-summing that here — the main harness
            # (test_green_zone_harden.py) exercises the full round-trip.
            if mismatches:
                bad += 1
                print(f"FAIL X{x}Y3N{n} fb8={fb8}: {mismatches}/16 predicted cells do NOT flip 0→1 in probe")
            else:
                ok += 1
    print(f"\n{ok}/80 OK, {bad} failed")
    sys.exit(0 if bad == 0 else 1)


if __name__ == "__main__":
    main()
