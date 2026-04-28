#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Phase 5.2 Stage B — M9K init content codec.

2D linear CRAM formula (validated 10/10 points 2026-04-09 at
M9K_X15_Y2_N0 under 9b×512 altsyncram):

    byte(anchor, w, bit) = anchor + (w // 2) * 210 - (w % 2) - 2 * bit
    bp                   = 6

Where `anchor` is the M9K block's (word=0, bit=0) CRAM byte offset for
the given (X, Y, N, width, depth) configuration. Currently locked for
one site/mode; future calibration sweeps will populate a table keyed
by (X, Y, N, WIDTH, DEPTH).

The codec flips ONLY primary data cells (bp=6). Frame CRC bytes at
frame offsets 208/209 update automatically via
`bitstream.patch_rbf_crc()` and must be left alone here — flipping
them manually would corrupt the CRC.

Usage:
    from fuzz.m9k_init_basis import M9K_INIT_ANCHORS, write_init, read_init
    from fuzz.bitstream import patch_rbf_crc

    anchor = M9K_INIT_ANCHORS[('X15_Y2_N0', 9, 512)]
    rbf_bytes = open('zero.rbf', 'rb').read()
    new = write_init(rbf_bytes, anchor, [0]*512, [0x155, 0x0AA, ...],
                     width=9, depth=512)
    new = patch_rbf_crc(new)
    open('out.rbf', 'wb').write(new)
"""
from __future__ import annotations

# Calibrated anchors: (site, WIDTH, DEPTH) -> (word=0, bit=0) CRAM byte.
# Extend via calibration sweeps similar to LUT TT n_sweep.
# Per-site calibration: (site, width, depth) -> (anchor_byte, bp).
# bp is the constant bit position of the primary row for this site.
M9K_INIT_ANCHORS: dict[tuple[str, int, int], tuple[int, int]] = {
    # Stage A/B legacy (aliased site, kept for backward-compat RBFs)
    ("X27_Y4_N0",  9, 512): (261142, 6),
    ("X27_Y16_N0", 4, 512): (261154, 2),  # LED harness 4b×512
    # NEORV32 Linux demo M9K sites — 31 anchors calibrated 2026-04-09
    # via m9k_anchor_sweep.py post-LOC-fix. All 9×512 uniform probe;
    # w1_b0 + w0_b8 formula validated 31/31. Pattern: bp decrements
    # every 3 Y rows, anchor cycles (+70, +70, -137) per Y.
    ("X15_Y10_N0",  9, 512): (120028, 4),
    ("X15_Y11_N0",  9, 512): (120098, 4),
    ("X15_Y12_N0",  9, 512): (119961, 3),
    ("X15_Y13_N0",  9, 512): (120031, 3),
    ("X15_Y14_N0",  9, 512): (120101, 3),
    ("X15_Y15_N0",  9, 512): (119964, 2),
    ("X15_Y16_N0",  9, 512): (120034, 2),
    ("X15_Y17_N0",  9, 512): (120104, 2),
    ("X15_Y18_N0",  9, 512): (119967, 1),
    ("X15_Y19_N0",  9, 512): (120037, 1),
    ("X15_Y20_N0",  9, 512): (120107, 1),
    ("X15_Y21_N0",  9, 512): (119970, 0),
    ("X15_Y22_N0",  9, 512): (120040, 0),
    ("X15_Y23_N0",  9, 512): (120110, 0),
    ("X15_Y5_N0",  9, 512): (120092, 6),
    ("X15_Y6_N0",  9, 512): (119955, 5),
    ("X15_Y8_N0",  9, 512): (120095, 5),
    ("X15_Y9_N0",  9, 512): (119958, 4),
    ("X27_Y11_N0",  9, 512): (261218, 4),
    ("X27_Y12_N0",  9, 512): (261081, 3),
    ("X27_Y13_N0",  9, 512): (261151, 3),
    ("X27_Y14_N0",  9, 512): (261221, 3),
    ("X27_Y15_N0",  9, 512): (261084, 2),
    ("X27_Y16_N0",  9, 512): (261154, 2),
    ("X27_Y17_N0",  9, 512): (261224, 2),
    ("X27_Y18_N0",  9, 512): (261087, 1),
    ("X27_Y19_N0",  9, 512): (261157, 1),
    ("X27_Y20_N0",  9, 512): (261227, 1),
    ("X27_Y21_N0",  9, 512): (261090, 0),
    ("X27_Y22_N0",  9, 512): (261160, 0),
    ("X27_Y23_N0",  9, 512): (261230, 0),
    # Gap-fill sites — calibrated 2026-04-25 via m9k_anchor_sweep.py.
    # Completes NEORV32's 27-site inventory (X15 Y=2..16, X27 Y=2..13).
    # 8/12 validated w1_b0 + w0_b8; 4 sites flagged "FORMULA MISMATCH"
    # on w0_b8 (bp+1, byte+~206) — same parity-row anomaly that X15_Y6
    # and X15_Y9 exhibit in the earlier batch (accepted precedent).
    # Data bits 0..7 are correct at all 12 sites.
    ("X15_Y2_N0",  9, 512): (120088, 7),
    ("X15_Y3_N0",  9, 512): (119952, 6),
    ("X15_Y4_N0",  9, 512): (120022, 6),
    ("X15_Y7_N0",  9, 512): (120025, 5),
    ("X27_Y2_N0",  9, 512): (261208, 7),
    ("X27_Y3_N0",  9, 512): (261072, 6),
    ("X27_Y5_N0",  9, 512): (261212, 6),
    ("X27_Y6_N0",  9, 512): (261075, 5),
    ("X27_Y7_N0",  9, 512): (261145, 5),
    ("X27_Y8_N0",  9, 512): (261215, 5),
    ("X27_Y9_N0",  9, 512): (261078, 4),
    ("X27_Y10_N0", 9, 512): (261148, 4),
    # Width=18 anchors — calibrated 2026-04-16 via
    # scripts/m9k_calib/calibrate_18x512{,_batch}.py.  The anchor + bp
    # are byte-identical to the 9×512 case at the same site (the M9K's
    # primary INIT cell is shared physical CRAM; only the per-word
    # stride width differs).  Formula
    #   byte(w, bit) = anchor + (w//2)*210 - (w%2) - 2*bit
    # verified for w1_b0 (anchor−1) and w0_b17 (anchor−34) at Y10/11/
    # 13/14.  At Y12 the bit-17 cell lands in a different bp than the
    # data-bit anchor (parity-row anomaly at bp transitions); the
    # recorded anchor is exact for bits 0..16, which is all the
    # libmap-split smoke test exercises (≤2 user bits per cell).
    # Unblocks the 5×width=18 split that Yosys's libmap picks for the
    # 9×512 smoke test (see m9k_techmap_libmap_portnames memory entry).
    ("X15_Y10_N0", 18, 512): (120028, 4),
    ("X15_Y11_N0", 18, 512): (120098, 4),
    ("X15_Y12_N0", 18, 512): (119961, 3),  # bits 0..16 only (see note)
    ("X15_Y13_N0", 18, 512): (120031, 3),
    ("X15_Y14_N0", 18, 512): (120101, 3),
    # Width=9 depth=1024, width=4 depth=2048, width=36 depth=256:
    # Anchors are shared with 9×512 at the same physical site (same CRAM
    # cell for word=0,bit=0; only the depth/width stride differs).
    # Extrapolated from the 18×512 confirmation; NOT yet calibrated
    # independently. All-zero INIT is correct regardless; non-zero INIT
    # needs per-site calibration sweep before trusting.
    # --- 9×1024 (same anchor as 9×512) ---
    # ⚠️  THESE ENTRIES USE THE WRONG FORMULA FOR NON-ZERO INIT at depth=1024.
    # 9×1024 stores 4 words per frame (vs 2 for 9×512); the linear formula
    # `byte = anchor + (w//2)*210 - (w%2) - 2*bit` gives wrong cells.
    # Calibrated 2026-04-27 — use `write_init_sp9x1024` / `read_init_sp9x1024`
    # and `SP_9X1024_BASE_FRAMES` instead.  Anchors retained for backward-
    # compat with allzero use (zero delta = no flips).
    ("X15_Y5_N0",   9, 1024): (120092, 6),
    ("X15_Y6_N0",   9, 1024): (119955, 5),
    ("X15_Y8_N0",   9, 1024): (120095, 5),
    ("X15_Y9_N0",   9, 1024): (119958, 4),
    ("X15_Y10_N0",  9, 1024): (120028, 4),
    ("X15_Y11_N0",  9, 1024): (120098, 4),
    ("X15_Y12_N0",  9, 1024): (119961, 3),
    ("X15_Y13_N0",  9, 1024): (120031, 3),
    ("X15_Y14_N0",  9, 1024): (120101, 3),
    ("X15_Y15_N0",  9, 1024): (119964, 2),
    ("X15_Y16_N0",  9, 1024): (120034, 2),
    ("X15_Y17_N0",  9, 1024): (120104, 2),
    ("X15_Y18_N0",  9, 1024): (119967, 1),
    ("X15_Y19_N0",  9, 1024): (120037, 1),
    ("X15_Y20_N0",  9, 1024): (120107, 1),
    ("X15_Y21_N0",  9, 1024): (119970, 0),
    ("X15_Y22_N0",  9, 1024): (120040, 0),
    ("X15_Y23_N0",  9, 1024): (120110, 0),
    ("X27_Y4_N0",   9, 1024): (261142, 6),
    ("X27_Y11_N0",  9, 1024): (261218, 4),
    ("X27_Y12_N0",  9, 1024): (261081, 3),
    ("X27_Y13_N0",  9, 1024): (261151, 3),
    ("X27_Y14_N0",  9, 1024): (261221, 3),
    ("X27_Y15_N0",  9, 1024): (261084, 2),
    ("X27_Y16_N0",  9, 1024): (261154, 2),
    ("X27_Y17_N0",  9, 1024): (261224, 2),
    ("X27_Y18_N0",  9, 1024): (261087, 1),
    ("X27_Y19_N0",  9, 1024): (261157, 1),
    ("X27_Y20_N0",  9, 1024): (261227, 1),
    ("X27_Y21_N0",  9, 1024): (261090, 0),
    ("X27_Y22_N0",  9, 1024): (261160, 0),
    ("X27_Y23_N0",  9, 1024): (261230, 0),
    # Gap-fill sites (2026-04-25), anchors shared with 9×512 at same site.
    ("X15_Y2_N0",   9, 1024): (120088, 7),
    ("X15_Y3_N0",   9, 1024): (119952, 6),
    ("X15_Y4_N0",   9, 1024): (120022, 6),
    ("X15_Y7_N0",   9, 1024): (120025, 5),
    ("X27_Y2_N0",   9, 1024): (261208, 7),
    ("X27_Y3_N0",   9, 1024): (261072, 6),
    ("X27_Y5_N0",   9, 1024): (261212, 6),
    ("X27_Y6_N0",   9, 1024): (261075, 5),
    ("X27_Y7_N0",   9, 1024): (261145, 5),
    ("X27_Y8_N0",   9, 1024): (261215, 5),
    ("X27_Y9_N0",   9, 1024): (261078, 4),
    ("X27_Y10_N0",  9, 1024): (261148, 4),
    # --- 4×2048 (same anchor as 9×512) ---
    # ⚠️  THESE ENTRIES ARE WRONG FOR NON-ZERO INIT.
    # The linear formula byte=anchor+(w//2)*210-(w%2)-2*bit has zero overlap
    # with the actual SDP CRAM layout (calibrated 2026-04-27).  Use
    # write_init_sdp4x2048 / read_init_sdp4x2048 instead for SDP 4×2048.
    # All-zero INIT still works (zero delta = no flips), but non-zero
    # content will flip completely wrong cells and silicon-reset.
    ("X15_Y5_N0",   4, 2048): (120092, 6),
    ("X15_Y6_N0",   4, 2048): (119955, 5),
    ("X15_Y8_N0",   4, 2048): (120095, 5),
    ("X15_Y9_N0",   4, 2048): (119958, 4),
    ("X15_Y10_N0",  4, 2048): (120028, 4),
    ("X15_Y11_N0",  4, 2048): (120098, 4),
    ("X15_Y12_N0",  4, 2048): (119961, 3),
    ("X15_Y13_N0",  4, 2048): (120031, 3),
    ("X15_Y14_N0",  4, 2048): (120101, 3),
    ("X15_Y15_N0",  4, 2048): (119964, 2),
    ("X15_Y16_N0",  4, 2048): (120034, 2),
    ("X15_Y17_N0",  4, 2048): (120104, 2),
    ("X15_Y18_N0",  4, 2048): (119967, 1),
    ("X15_Y19_N0",  4, 2048): (120037, 1),
    ("X15_Y20_N0",  4, 2048): (120107, 1),
    ("X15_Y21_N0",  4, 2048): (119970, 0),
    ("X15_Y22_N0",  4, 2048): (120040, 0),
    ("X15_Y23_N0",  4, 2048): (120110, 0),
    ("X27_Y4_N0",   4, 2048): (261142, 6),
    ("X27_Y11_N0",  4, 2048): (261218, 4),
    ("X27_Y12_N0",  4, 2048): (261081, 3),
    ("X27_Y13_N0",  4, 2048): (261151, 3),
    ("X27_Y14_N0",  4, 2048): (261221, 3),
    ("X27_Y15_N0",  4, 2048): (261084, 2),
    ("X27_Y16_N0",  4, 2048): (261154, 2),
    ("X27_Y17_N0",  4, 2048): (261224, 2),
    ("X27_Y18_N0",  4, 2048): (261087, 1),
    ("X27_Y19_N0",  4, 2048): (261157, 1),
    ("X27_Y20_N0",  4, 2048): (261227, 1),
    ("X27_Y21_N0",  4, 2048): (261090, 0),
    ("X27_Y22_N0",  4, 2048): (261160, 0),
    ("X27_Y23_N0",  4, 2048): (261230, 0),
    # Gap-fill sites (2026-04-25), anchors shared with 9×512 at same site.
    ("X15_Y2_N0",   4, 2048): (120088, 7),
    ("X15_Y3_N0",   4, 2048): (119952, 6),
    ("X15_Y4_N0",   4, 2048): (120022, 6),
    ("X15_Y7_N0",   4, 2048): (120025, 5),
    ("X27_Y2_N0",   4, 2048): (261208, 7),
    ("X27_Y3_N0",   4, 2048): (261072, 6),
    ("X27_Y5_N0",   4, 2048): (261212, 6),
    ("X27_Y6_N0",   4, 2048): (261075, 5),
    ("X27_Y7_N0",   4, 2048): (261145, 5),
    ("X27_Y8_N0",   4, 2048): (261215, 5),
    ("X27_Y9_N0",   4, 2048): (261078, 4),
    ("X27_Y10_N0",  4, 2048): (261148, 4),
    # --- 36×256 (same anchor as 9×512) ---
    # ⚠️  THESE ENTRIES USE THE WRONG FORMULA FOR NON-ZERO INIT at width=36.
    # 36×256 splits each word across two frame regions (lower base+0 for bits
    # 0..15+32..33; upper base+128 for bits 16..31+34..35); the simple linear
    # formula gives wrong cells.  Calibrated 2026-04-27 — use
    # `write_init_sp36x256` / `read_init_sp36x256` and `SP_36X256_BASE_FRAMES`
    # instead.  Anchors retained for backward-compat with allzero use.
    ("X15_Y5_N0",  36, 256): (120092, 6),
    ("X15_Y6_N0",  36, 256): (119955, 5),
    ("X15_Y8_N0",  36, 256): (120095, 5),
    ("X15_Y9_N0",  36, 256): (119958, 4),
    ("X15_Y10_N0", 36, 256): (120028, 4),
    ("X15_Y11_N0", 36, 256): (120098, 4),
    ("X15_Y12_N0", 36, 256): (119961, 3),
    ("X15_Y13_N0", 36, 256): (120031, 3),
    ("X15_Y14_N0", 36, 256): (120101, 3),
    ("X15_Y15_N0", 36, 256): (119964, 2),
    ("X15_Y16_N0", 36, 256): (120034, 2),
    ("X15_Y17_N0", 36, 256): (120104, 2),
    ("X15_Y18_N0", 36, 256): (119967, 1),
    ("X15_Y19_N0", 36, 256): (120037, 1),
    ("X15_Y20_N0", 36, 256): (120107, 1),
    ("X15_Y21_N0", 36, 256): (119970, 0),
    ("X15_Y22_N0", 36, 256): (120040, 0),
    ("X15_Y23_N0", 36, 256): (120110, 0),
    ("X27_Y4_N0",  36, 256): (261142, 6),
    ("X27_Y11_N0", 36, 256): (261218, 4),
    ("X27_Y12_N0", 36, 256): (261081, 3),
    ("X27_Y13_N0", 36, 256): (261151, 3),
    ("X27_Y14_N0", 36, 256): (261221, 3),
    ("X27_Y15_N0", 36, 256): (261084, 2),
    ("X27_Y16_N0", 36, 256): (261154, 2),
    ("X27_Y17_N0", 36, 256): (261224, 2),
    ("X27_Y18_N0", 36, 256): (261087, 1),
    ("X27_Y19_N0", 36, 256): (261157, 1),
    ("X27_Y20_N0", 36, 256): (261227, 1),
    ("X27_Y21_N0", 36, 256): (261090, 0),
    ("X27_Y22_N0", 36, 256): (261160, 0),
    ("X27_Y23_N0", 36, 256): (261230, 0),
    # Gap-fill sites (2026-04-25), anchors shared with 9×512 at same site.
    ("X15_Y2_N0",  36, 256): (120088, 7),
    ("X15_Y3_N0",  36, 256): (119952, 6),
    ("X15_Y4_N0",  36, 256): (120022, 6),
    ("X15_Y7_N0",  36, 256): (120025, 5),
    ("X27_Y2_N0",  36, 256): (261208, 7),
    ("X27_Y3_N0",  36, 256): (261072, 6),
    ("X27_Y5_N0",  36, 256): (261212, 6),
    ("X27_Y6_N0",  36, 256): (261075, 5),
    ("X27_Y7_N0",  36, 256): (261145, 5),
    ("X27_Y8_N0",  36, 256): (261215, 5),
    ("X27_Y9_N0",  36, 256): (261078, 4),
    ("X27_Y10_N0", 36, 256): (261148, 4),
}

FRAME_SIZE = 210
CRC_SLOTS = (208, 209)   # per-frame CRC bytes — never touch directly
PREAMBLE   = 32

# ── SDP 4×2048 4-bit codec ───────────────────────────────────────────────────
# Calibrated 2026-04-27 via single-word Quartus probes at X15_Y10_N0.
# Layout: 8 words per CRAM frame; byte positions indexed by (word % 8);
#         all cells at bp=4. base_frame = (sp_9x512_anchor - PREAMBLE - 86) // 210.
# Bit-stride: bif(w,bit) = _SDP_4X2048_BIF[w%8] - 2*bit (bits 0..3 covered).
# Validated: bit 0 silicon (stripe64), bits 1-3 Quartus-probe (XOR-design).
#
# Word→frame: frame = base_frame + word // 8
# Word→byte:  SDP_4X2048_BIF[word % 8]
_SDP_4X2048_BIF = [86, 78, 68, 60, 85, 77, 67, 59]   # indexed by word % 8
_SDP_4X2048_BP  = 4

# SDP 4×2048 base_frame is silicon-validated ONLY at X15_Y10_N0.
#
# 2026-04-28 calibration finding: the `(sp_9x512_anchor - 118) // 210`
# extrapolation formula does NOT hold at other sites. Diff of Quartus
# gold blink vs allzero base at X15_Y16_N0 and X27_Y7_N0 produced TP=0
# against the formula:
#
#   site         | extrapolated frame | actual SDP frame | bp
#   X15_Y10_N0   | 571                | 571 ✓            | 4
#   X15_Y16_N0   | 571 (codec wrote)  | 699 (real)       | 2 (not 4)
#   X27_Y7_N0    | 1243 (codec wrote) | 1371 (real)      | 5 (not 4)
#
# Real SDP cell counts at non-Y10 sites are also ~2300 (vs predicted
# 4096) — physical layout differs in non-trivial ways. Cross-site SDP
# requires per-site mining (8 single-word probes per site to remap
# word→bif, plus characterization of the cell-count gap).
#
# The dict below is therefore restricted to silicon-validated sites.
# Callers will get a KeyError on non-Y10 sites — that's intentional.
SDP_4X2048_BASE_FRAMES: dict[str, int] = {
    "X15_Y10_N0": 571,  # = (120028 - PREAMBLE - 86) // FRAME_SIZE
}

# Historical record of the broken extrapolations (do NOT use for codec
# writes — kept for reproducibility of the 2026-04-28 finding and as a
# starting point for future per-site mining).
_SDP_4X2048_BROKEN_EXTRAPOLATIONS: dict[str, int] = {
    "X15_Y5_N0":  120092, "X15_Y6_N0":  119955, "X15_Y8_N0":  120095,
    "X15_Y9_N0":  119958,                       "X15_Y11_N0": 120098,
    "X15_Y12_N0": 119961, "X15_Y13_N0": 120031, "X15_Y14_N0": 120101,
    "X15_Y15_N0": 119964, "X15_Y16_N0": 120034, "X15_Y17_N0": 120104,
    "X15_Y18_N0": 119967, "X15_Y19_N0": 120037, "X15_Y20_N0": 120107,
    "X15_Y21_N0": 119970, "X15_Y22_N0": 120040, "X15_Y23_N0": 120110,
    "X27_Y4_N0":  261142, "X27_Y11_N0": 261218, "X27_Y12_N0": 261081,
    "X27_Y13_N0": 261151, "X27_Y14_N0": 261221, "X27_Y15_N0": 261084,
    "X27_Y16_N0": 261154, "X27_Y17_N0": 261224, "X27_Y18_N0": 261087,
    "X27_Y19_N0": 261157, "X27_Y20_N0": 261227, "X27_Y21_N0": 261090,
    "X27_Y22_N0": 261160, "X27_Y23_N0": 261230,
}


def sdp_4x2048_cell(base_frame: int, word: int, bit: int = 0) -> tuple[int, int]:
    """Return (byte_offset, bp) for the SDP 4×2048 INIT cell of (word, bit).

    Calibrated 2026-04-27 at X15_Y10_N0:
      bif(w, bit) = _SDP_4X2048_BIF[w % 8] - 2 * bit
      frame(w)   = base_frame + w // 8
      bp         = 4 (constant for all bits at this site)

    bit ∈ {0, 1, 2, 3}.
    """
    if not 0 <= bit < 4:
        raise ValueError(f"SDP 4×2048 has 4 bits per word; got bit={bit}")
    frame  = base_frame + word // 8
    bif    = _SDP_4X2048_BIF[word % 8] - 2 * bit
    offset = PREAMBLE + frame * FRAME_SIZE + bif
    return offset, _SDP_4X2048_BP


def read_init_sdp4x2048(rbf_bytes: bytes, base_frame: int,
                         depth: int = 2048) -> list[int]:
    """Read INIT words (full 4-bit) from a SDP 4×2048 RBF.

    Returns a list of `depth` values in [0, 0xF] — bits 0..3 per word.
    """
    words = []
    for w in range(depth):
        v = 0
        for bit in range(4):
            offset, bp = sdp_4x2048_cell(base_frame, w, bit)
            if rbf_bytes[offset] & (1 << bp):
                v |= (1 << bit)
        words.append(v)
    return words


def write_init_sdp4x2048(
    rbf_bytes: bytes,
    base_frame: int,
    base_words: list[int],
    target_words: list[int],
    depth: int = 2048,
) -> bytes:
    """XOR-delta writer for SDP 4×2048 INIT cells (full 4-bit).

    base_words / target_words: each entry is in [0, 0xF].
    Caller must run patch_rbf_crc() afterwards.
    """
    if len(base_words) != depth or len(target_words) != depth:
        raise ValueError(f"expected {depth} words")
    out = bytearray(rbf_bytes)
    for w in range(depth):
        delta = (base_words[w] ^ target_words[w]) & 0xF
        if delta == 0:
            continue
        for bit in range(4):
            if not (delta & (1 << bit)):
                continue
            offset, bp = sdp_4x2048_cell(base_frame, w, bit)
            off_in_frame = (offset - PREAMBLE) % FRAME_SIZE
            if off_in_frame in CRC_SLOTS:
                raise ValueError(
                    f"sdp cell w={w} bit={bit} lands on CRC slot offset {offset}"
                )
            out[offset] ^= (1 << bp)
    return bytes(out)


# ── end SDP 4×2048 codec ──────────────────────────────────────────────────────


# ── SP 9×1024 codec ──────────────────────────────────────────────────────────
# Calibrated 2026-04-27 at X15_Y10_N0 via single-word/single-bit Quartus probes
# (XOR-fold design forces all 9 bits into CRAM).
# Layout: 4 words per CRAM frame (vs 2 for 9×512); -2 byte stride per bit.
#   frame(w)     = base_frame + w // 4
#   bif(w, bit)  = _SP_9X1024_BIF[w % 4] - 2*bit
#   bp           = 4 (constant at this site)
# base_frame is shared with 9×512 (same physical M9K block at X15_Y10_N0).

_SP_9X1024_BIF = [86, 68, 85, 67]  # indexed by word % 4
_SP_9X1024_BP  = 4

SP_9X1024_BASE_FRAMES: dict[str, int] = {
    "X15_Y10_N0": 571,  # = (120028 - PREAMBLE - 86) // FRAME_SIZE
    # Other sites: extrapolate via (sp_9x512_anchor - PREAMBLE - 86) // 210.
    # Only X15_Y10_N0 is silicon-validated.
}


def sp_9x1024_cell(base_frame: int, word: int, bit: int) -> tuple[int, int]:
    if not 0 <= bit < 9:
        raise ValueError(f"SP 9×1024 has 9 bits per word; got bit={bit}")
    frame  = base_frame + word // 4
    bif    = _SP_9X1024_BIF[word % 4] - 2 * bit
    offset = PREAMBLE + frame * FRAME_SIZE + bif
    return offset, _SP_9X1024_BP


def read_init_sp9x1024(rbf_bytes: bytes, base_frame: int,
                        depth: int = 1024) -> list[int]:
    words = []
    for w in range(depth):
        v = 0
        for bit in range(9):
            offset, bp = sp_9x1024_cell(base_frame, w, bit)
            if rbf_bytes[offset] & (1 << bp):
                v |= (1 << bit)
        words.append(v)
    return words


def write_init_sp9x1024(rbf_bytes: bytes, base_frame: int,
                         base_words: list[int], target_words: list[int],
                         depth: int = 1024) -> bytes:
    if len(base_words) != depth or len(target_words) != depth:
        raise ValueError(f"expected {depth} words")
    out = bytearray(rbf_bytes)
    for w in range(depth):
        delta = (base_words[w] ^ target_words[w]) & 0x1FF
        if delta == 0:
            continue
        for bit in range(9):
            if not (delta & (1 << bit)):
                continue
            offset, bp = sp_9x1024_cell(base_frame, w, bit)
            off_in_frame = (offset - PREAMBLE) % FRAME_SIZE
            if off_in_frame in CRC_SLOTS:
                raise ValueError(
                    f"sp9x1024 cell w={w} bit={bit} lands on CRC slot {offset}"
                )
            out[offset] ^= (1 << bp)
    return bytes(out)


# ── SP 36×256 codec ──────────────────────────────────────────────────────────
# Calibrated 2026-04-27 at X15_Y10_N0 via 36-bit single-bit probes.
# Layout: 36 bits split across two frames (lower base+0, upper base+128).
#   bit 0..15  → lower half, position = bit
#   bit 16..31 → upper half, position = bit - 16
#   bit 32, 33 → lower half, position = 16, 17
#   bit 34, 35 → upper half, position = 16, 17
# Within a half: 2 words/frame, frame = base + word//2,
# bif = 86 - 2*pos - (word%2), bp = 4.

_SP_36X256_BP = 4
_SP_36X256_UPPER_OFFSET = 128

SP_36X256_BASE_FRAMES: dict[str, int] = {
    "X15_Y10_N0": 571,
    # Other sites extrapolated via (sp_9x512_anchor - PREAMBLE - 86) // 210.
}


def _sp_36x256_bit_to_half_pos(bit: int) -> tuple[int, int]:
    if not 0 <= bit < 36:
        raise ValueError(f"SP 36×256 has 36 bits per word; got bit={bit}")
    if bit < 32:
        half = (bit // 16) % 2
        pos  = bit % 16
    else:
        half = (bit - 32) // 2  # 32,33→0; 34,35→1
        pos  = 16 + (bit - 32) % 2  # 32,34→16; 33,35→17
    return half, pos


def sp_36x256_cell(base_frame: int, word: int, bit: int) -> tuple[int, int]:
    half, pos = _sp_36x256_bit_to_half_pos(bit)
    frame  = base_frame + word // 2 + half * _SP_36X256_UPPER_OFFSET
    bif    = 86 - 2 * pos - (word % 2)
    offset = PREAMBLE + frame * FRAME_SIZE + bif
    return offset, _SP_36X256_BP


def read_init_sp36x256(rbf_bytes: bytes, base_frame: int,
                        depth: int = 256) -> list[int]:
    words = []
    for w in range(depth):
        v = 0
        for bit in range(36):
            offset, bp = sp_36x256_cell(base_frame, w, bit)
            if rbf_bytes[offset] & (1 << bp):
                v |= (1 << bit)
        words.append(v)
    return words


def write_init_sp36x256(rbf_bytes: bytes, base_frame: int,
                         base_words: list[int], target_words: list[int],
                         depth: int = 256) -> bytes:
    if len(base_words) != depth or len(target_words) != depth:
        raise ValueError(f"expected {depth} words")
    out = bytearray(rbf_bytes)
    mask = (1 << 36) - 1
    for w in range(depth):
        delta = (base_words[w] ^ target_words[w]) & mask
        if delta == 0:
            continue
        for bit in range(36):
            if not (delta & (1 << bit)):
                continue
            offset, bp = sp_36x256_cell(base_frame, w, bit)
            off_in_frame = (offset - PREAMBLE) % FRAME_SIZE
            if off_in_frame in CRC_SLOTS:
                raise ValueError(
                    f"sp36x256 cell w={w} bit={bit} lands on CRC slot {offset}"
                )
            out[offset] ^= (1 << bp)
    return bytes(out)


# ── end SP 9×1024 / 36×256 codecs ─────────────────────────────────────────────


def init_cell(anchor: int, word: int, bit: int, bp: int = 6) -> tuple[int, int]:
    """Return the (byte_offset, bit_position) for M9K init cell
    (word, bit) given the calibrated (anchor, bp) pair.

    byte = anchor + (word // 2) * 210 - (word % 2) - 2 * bit
    """
    byte = anchor + (word // 2) * FRAME_SIZE - (word % 2) - 2 * bit
    return (byte, bp)


def _assert_cell_safe(byte: int) -> None:
    """Guard: the 2D formula must never land on a CRC slot. If it does,
    the calibration is wrong — the formula is bit-exact for the
    validated site."""
    off_in_frame = (byte - 32) % FRAME_SIZE
    if off_in_frame in CRC_SLOTS:
        raise ValueError(
            f"init_cell byte {byte} lands in frame CRC slot "
            f"(offset {off_in_frame}); formula/anchor is wrong"
        )


def _bit_flip(rbf: bytearray, byte: int, bp: int) -> None:
    rbf[byte] ^= (1 << bp)


def write_init(
    rbf_bytes: bytes,
    anchor: int,
    base_words: list[int],
    target_words: list[int],
    width: int = 9,
    depth: int = 512,
    bp: int = 6,
) -> bytes:
    """XOR-delta writer.

    base_words: what the block currently holds (all-zero if fresh)
    target_words: desired contents

    Returns a new RBF byte string with primary data cells updated.
    Caller must run patch_rbf_crc() afterwards before flashing.
    """
    if len(base_words) != depth or len(target_words) != depth:
        raise ValueError(f"expected {depth} words, got "
                         f"{len(base_words)}/{len(target_words)}")
    mask_full = (1 << width) - 1
    out = bytearray(rbf_bytes)
    flips = 0
    for w in range(depth):
        delta = (base_words[w] ^ target_words[w]) & mask_full
        if not delta:
            continue
        for bit in range(width):
            if delta & (1 << bit):
                byte, _bp = init_cell(anchor, w, bit, bp=bp)
                _assert_cell_safe(byte)
                _bit_flip(out, byte, _bp)
                flips += 1
    return bytes(out)


def read_init(
    rbf_bytes: bytes,
    anchor: int,
    width: int = 9,
    depth: int = 512,
    bp: int = 6,
) -> list[int]:
    """Decode M9K init words from a raw RBF using the 2D formula.

    Returns depth words, each a `width`-bit int. Absolute decode
    (not delta-vs-base) — reads the primary cell for each (word, bit).
    """
    words = []
    for w in range(depth):
        v = 0
        for bit in range(width):
            byte, _bp = init_cell(anchor, w, bit, bp=bp)
            off_in_frame = (byte - 32) % FRAME_SIZE
            if off_in_frame in CRC_SLOTS:
                # Formula points at a CRC byte for this (anchor, bit).
                # Real silicon stores this bit elsewhere; the simple
                # 2-D model isn't valid here.  Treat as 0 — INIT bits
                # can't physically live in CRC bytes.
                continue
            if rbf_bytes[byte] & (1 << _bp):
                v |= (1 << bit)
        words.append(v)
    return words


if __name__ == "__main__":
    # Sanity: evaluate the anchor cell and print the formula's round-trip
    # coverage for the 9x512 site.
    anchor, bp = M9K_INIT_ANCHORS[("X15_Y2_N0", 9, 512)]
    print(f"anchor(X15_Y2_N0, 9x512) = ({anchor}, bp={bp})")
    print(f"w=0 b=0 -> {init_cell(anchor, 0, 0, bp=bp)}")
    print(f"w=0 b=8 -> {init_cell(anchor, 0, 8, bp=bp)}")
    print(f"w=1 b=0 -> {init_cell(anchor, 1, 0, bp=bp)}")
    print(f"w=2 b=0 -> {init_cell(anchor, 2, 0, bp=bp)}")
    print(f"w=511 b=8 -> {init_cell(anchor, 511, 8, bp=bp)}")
    # Full 9x512 = 4608 cells; verify none collide with CRC
    cells = set()
    for w in range(512):
        for b in range(9):
            byte, _bp = init_cell(anchor, w, b, bp=bp)
            _assert_cell_safe(byte)
            key = (byte, _bp)
            if key in cells:
                raise RuntimeError(f"collision at w={w} b={b}: {key}")
            cells.add(key)
    print(f"4608 cells all unique, all outside CRC slots. Formula OK.")
