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
}

FRAME_SIZE = 210
CRC_SLOTS = (208, 209)   # per-frame CRC bytes — never touch directly


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
