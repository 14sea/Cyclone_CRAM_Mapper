# SPDX-License-Identifier: GPL-3.0-or-later
"""Tests for the programmatic pure-zero RBF baseline.

Phase 1 of nv_zero_global retirement.  Verifies PURE_ZERO satisfies the
RBF shape + CRC invariants, and records the NV ^ PURE_ZERO cell-count
that Phase 2 mining will have to decompose.
"""
from __future__ import annotations

import os
import sys
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from bitstream import (
    CRC_DATA_SIZE,
    CRC_FIRST_CRAM_FRAME,
    CRC_FRAME_SIZE,
    CRC_LAST_FRAME,
    CRC_PREAMBLE,
    crc16_rbf_frame,
    patch_rbf_crc,
)
from pure_zero_rbf import POSTAMBLE, RBF_SIZE, make_pure_zero_rbf

ROOT = Path(__file__).resolve().parent.parent
NV_ZERO = ROOT / "results" / "rbf" / "nv_zero_global.rbf"


def test_pure_zero_size():
    rbf = make_pure_zero_rbf()
    assert len(rbf) == RBF_SIZE == 368011


def test_pure_zero_preamble_postamble():
    rbf = make_pure_zero_rbf()
    assert rbf[:CRC_PREAMBLE] == b"\xFF" * CRC_PREAMBLE
    assert rbf[-POSTAMBLE:] == b"\xFF" * POSTAMBLE


def test_pure_zero_all_frame_data_zero():
    """Every frame's 208 data bytes must be zero (hdr 0..24 + CRAM 25..1751)."""
    rbf = make_pure_zero_rbf()
    for n in range(CRC_LAST_FRAME + 1):
        s = CRC_PREAMBLE + n * CRC_FRAME_SIZE
        assert rbf[s:s + CRC_DATA_SIZE] == bytes(CRC_DATA_SIZE), (
            f"frame {n} data not zero")


def test_pure_zero_header_frames_crc_zero():
    """Frames 0..24 are header — patch_rbf_crc skips them, so their
    CRC slots stay at whatever we initialised them to (zero)."""
    rbf = make_pure_zero_rbf()
    for n in range(CRC_FIRST_CRAM_FRAME):  # 0..24
        s = CRC_PREAMBLE + n * CRC_FRAME_SIZE
        assert rbf[s + CRC_DATA_SIZE] == 0
        assert rbf[s + CRC_DATA_SIZE + 1] == 0


def test_pure_zero_cram_frames_crc_deterministic():
    """All 1727 CRAM frames are all-zero data → identical CRC."""
    rbf = make_pure_zero_rbf()
    zero_frame_crc = crc16_rbf_frame(bytes(CRC_DATA_SIZE))
    for n in range(CRC_FIRST_CRAM_FRAME, CRC_LAST_FRAME + 1):
        s = CRC_PREAMBLE + n * CRC_FRAME_SIZE
        lo = rbf[s + CRC_DATA_SIZE]
        hi = rbf[s + CRC_DATA_SIZE + 1]
        got = lo | (hi << 8)
        assert got == zero_frame_crc, (
            f"frame {n} CRC {got:#06x} != {zero_frame_crc:#06x}")


def test_patch_rbf_crc_idempotent_on_pure_zero():
    rbf = make_pure_zero_rbf()
    assert patch_rbf_crc(rbf) == rbf


def test_pure_zero_stable_across_calls():
    """Factory is deterministic — two calls return identical bytes."""
    assert make_pure_zero_rbf() == make_pure_zero_rbf()


def test_pure_zero_vs_nv_zero_global_gap_recorded():
    """Phase 2 mining target — record the byte-level delta NV ^ PURE_ZERO.

    This test does not assert a specific count; it records the gap that
    NV_BASELINE_PACK (Phase 3) must close and fails only if the gap is
    zero (which would mean nv_zero_global is already pure-zero — not the
    case in the current tree).
    """
    if not NV_ZERO.exists():
        # Skip gracefully if nv_zero_global is not present locally
        return
    nv = NV_ZERO.read_bytes()
    pz = make_pure_zero_rbf()
    assert len(nv) == len(pz)
    # Byte-level diff count (non-CRC positions — CRC bytes will also
    # differ since nv's CRAM is non-zero and has its own CRCs)
    hdr_diff_bytes = sum(
        1 for i in range(CRC_PREAMBLE, CRC_PREAMBLE + CRC_FIRST_CRAM_FRAME * CRC_FRAME_SIZE)
        if nv[i] != pz[i])
    cram_diff_bytes = 0
    cram_crc_diff_bytes = 0
    for n in range(CRC_FIRST_CRAM_FRAME, CRC_LAST_FRAME + 1):
        s = CRC_PREAMBLE + n * CRC_FRAME_SIZE
        for i in range(CRC_DATA_SIZE):
            if nv[s + i] != pz[s + i]:
                cram_diff_bytes += 1
        if nv[s + CRC_DATA_SIZE] != pz[s + CRC_DATA_SIZE]:
            cram_crc_diff_bytes += 1
        if nv[s + CRC_DATA_SIZE + 1] != pz[s + CRC_DATA_SIZE + 1]:
            cram_crc_diff_bytes += 1
    # Bit-level cell count for non-CRC bytes
    hdr_bit_cells = 0
    for i in range(CRC_PREAMBLE, CRC_PREAMBLE + CRC_FIRST_CRAM_FRAME * CRC_FRAME_SIZE):
        hdr_bit_cells += bin(nv[i] ^ pz[i]).count("1")
    cram_bit_cells = 0
    for n in range(CRC_FIRST_CRAM_FRAME, CRC_LAST_FRAME + 1):
        s = CRC_PREAMBLE + n * CRC_FRAME_SIZE
        for i in range(CRC_DATA_SIZE):
            cram_bit_cells += bin(nv[s + i] ^ pz[s + i]).count("1")
    print(f"\n  NV ^ PURE_ZERO gap:")
    print(f"    hdr-band (off < 5282): {hdr_diff_bytes} bytes, {hdr_bit_cells} bit-cells")
    print(f"    CRAM data:             {cram_diff_bytes} bytes, {cram_bit_cells} bit-cells")
    print(f"    CRAM CRC bytes:        {cram_crc_diff_bytes} bytes (auto-patched)")
    total_cells = hdr_bit_cells + cram_bit_cells
    print(f"    TOTAL non-CRC bit cells: {total_cells}")
    assert total_cells > 0, "NV and PURE_ZERO identical — impossible"


def _main():
    passed = failed = 0
    for name, fn in sorted(globals().items()):
        if not name.startswith("test_") or not callable(fn):
            continue
        try:
            fn()
        except Exception:
            traceback.print_exc()
            print(f"FAIL {name}")
            failed += 1
        else:
            print(f"PASS {name}")
            passed += 1
    print(f"\n{passed} passed, {failed} failed")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    _main()
