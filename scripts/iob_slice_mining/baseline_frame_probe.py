# SPDX-License-Identifier: GPL-3.0-or-later
"""Baseline-integration frame-diff probe.

Measures byte-level diffs between the three reference RBFs that the
IOB FASM directive family currently uses as baselines:

  nv_zero_global.rbf  — virtual-pin zero build (IOB_ROUTE baseline)
  iob_in_E15.rbf      — test design with K=E15, LED=G15 (IOB_IN/OUT
                        baseline — byte-identical to iob_out_G15.rbf)
  iob_zero_{PIN}.rbf  — paired-mining zero variant (IOB_ROUTE bridge
                        midpoint)
  iob_pair_E16_10_4_0_dataa.rbf — HW-verified golden

Goal: characterize where iob_in_E15 and nv_zero_global differ so we can
pick the right baseline-integration strategy for end-to-end FASM synth.

Classification:
  header band   (bytes 0..5281)       — frames 0..24, pin/bank/config
  CRAM band     (bytes 5282..368191)  — frames 25..1751
  trailer band  (bytes 368192..)      — frames 1752+, postamble
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent

PRE = 32
FRAME = 210
FIRST = 25
LAST = 1751
CRAM_START = PRE + FIRST * FRAME           # 5282
CRAM_END = PRE + (LAST + 1) * FRAME        # 368192


def byte_diff(a: bytes, b: bytes) -> list[int]:
    assert len(a) == len(b), f"size mismatch {len(a)} vs {len(b)}"
    return [i for i in range(len(a)) if a[i] != b[i]]


def bucket(offsets: list[int]) -> tuple[int, int, int]:
    hdr = sum(1 for o in offsets if o < CRAM_START)
    cram = sum(1 for o in offsets if CRAM_START <= o < CRAM_END)
    trl = sum(1 for o in offsets if o >= CRAM_END)
    return hdr, cram, trl


def frame_of(off: int) -> int:
    if off < PRE:
        return -1
    f = (off - PRE) // FRAME
    return f


def main() -> int:
    rbfs = REPO / "results" / "rbf"
    work = HERE / "work"

    nv = (rbfs / "nv_zero_global.rbf").read_bytes()
    iob_in_E15 = (rbfs / "iob_in_E15.rbf").read_bytes()
    iob_out_G15 = (rbfs / "iob_out_G15.rbf").read_bytes()
    iob_zero_E15 = (work / "iob_zero_E15.rbf").read_bytes()
    iob_zero_E16 = (work / "iob_zero_E16.rbf").read_bytes()
    pair = (work / "iob_pair_E16_10_4_0_dataa.rbf").read_bytes()

    print(f"[sizes] nv={len(nv)}  iob_in_E15={len(iob_in_E15)}  "
          f"iob_out_G15={len(iob_out_G15)}  "
          f"iob_zero_E15={len(iob_zero_E15)}  "
          f"iob_zero_E16={len(iob_zero_E16)}  "
          f"pair={len(pair)}")

    print()
    print("=== Pairwise diffs (bucketed hdr/CRAM/trl) ===")
    pairs = [
        ("iob_in_E15 vs iob_out_G15", iob_in_E15, iob_out_G15),
        ("nv vs iob_in_E15",          nv,         iob_in_E15),
        ("nv vs iob_zero_E15",        nv,         iob_zero_E15),
        ("nv vs iob_zero_E16",        nv,         iob_zero_E16),
        ("iob_zero_E15 vs iob_zero_E16", iob_zero_E15, iob_zero_E16),
        ("iob_zero_E16 vs pair",      iob_zero_E16, pair),
        ("nv vs pair",                nv,         pair),
        ("iob_in_E15 vs pair",        iob_in_E15, pair),
    ]
    for label, a, b in pairs:
        d = byte_diff(a, b)
        h, c, t = bucket(d)
        print(f"  {label:38s}: {len(d):6d} diffs   "
              f"(hdr={h}, CRAM={c}, trl={t})")

    # Detailed: nv vs iob_in_E15 — this is the "baseline bridge" delta
    # we'd need to carry if we stay on nv_zero_global baseline and want
    # IOB pin config.
    print()
    print("=== nv_zero_global ^ iob_in_E15 — the IOB baseline bridge ===")
    d = byte_diff(nv, iob_in_E15)
    print(f"  total: {len(d)} bytes differ")
    h, c, t = bucket(d)
    print(f"  hdr={h}  CRAM={c}  trl={t}")

    # CRAM diffs = iob_in_E15's fabric (its test design)
    # Show CRAM diff distribution across frames
    cram_diffs = [o for o in d if CRAM_START <= o < CRAM_END]
    if cram_diffs:
        frames = Counter(frame_of(o) for o in cram_diffs)
        top = frames.most_common(10)
        print(f"  CRAM diff frame distribution (top 10): {top}")
        # Frame ranges — contiguous ranges of frames
        fs = sorted(set(frames))
        print(f"  CRAM frames touched: {len(fs)} distinct, "
              f"range {fs[0]}..{fs[-1]}")

    # Header diffs = IOB bank config
    hdr_diffs = [o for o in d if o < CRAM_START]
    if hdr_diffs:
        print(f"  header diffs offsets[:20]: {hdr_diffs[:20]}")

    # Is iob_in_E15 == iob_out_G15?
    print()
    same = iob_in_E15 == iob_out_G15
    print(f"=== iob_in_E15 == iob_out_G15 byte-identical? {same} ===")

    # Now check: can we use iob_pair_* RBFs directly as baseline for
    # their matching FASM design? The logical bet:
    # pair = nv_zero ^ (IOB_ROUTE cells) ^ (pair-fabric-extras) ^
    #        (iob bank config for its pins)
    # We proved CRAM = nv_zero ^ IOB_ROUTE reproduces pair CRAM.  The
    # header band is what's left.
    print()
    print("=== Where does pair differ from nv after IOB_ROUTE in hdr? ===")
    # Can't call bitgen here (circular), but we can bound it: the hdr
    # diff nv vs pair should equal the IOB-pin-config diff.  That's the
    # thing we need to carry.
    pair_hdr_d = [o for o in byte_diff(nv, pair) if o < CRAM_START]
    print(f"  pair hdr diff from nv = {len(pair_hdr_d)} bytes")

    # Cross-reference: is pair's header band a strict subset of
    # iob_in_E15 ^ iob_in_(pin)-configuration bytes?
    # We have iob_in_E15 loaded; if iob_in_E16 config == pair's K_PRIM
    # config, they should share header-band deltas.
    if (rbfs / "iob_in_E16.rbf").exists():
        iob_in_E16 = (rbfs / "iob_in_E16.rbf").read_bytes()
        in_E16_hdr_d = [o for o in byte_diff(nv, iob_in_E16)
                        if o < CRAM_START]
        shared = set(pair_hdr_d) & set(in_E16_hdr_d)
        pair_only = set(pair_hdr_d) - set(in_E16_hdr_d)
        in_E16_only = set(in_E16_hdr_d) - set(pair_hdr_d)
        print(f"  iob_in_E16 hdr diff from nv = {len(in_E16_hdr_d)}")
        print(f"    shared with pair hdr: {len(shared)}")
        print(f"    pair hdr only:        {len(pair_only)}")
        print(f"    iob_in_E16 hdr only:  {len(in_E16_only)}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
