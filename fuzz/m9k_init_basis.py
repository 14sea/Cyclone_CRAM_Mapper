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
M9K_INIT_ANCHORS: dict[tuple[str, int, int], int] = {
    ("X15_Y2_N0", 9, 512): 261142,
}

FRAME_SIZE = 210
CRC_SLOTS = (208, 209)   # per-frame CRC bytes — never touch directly
PRIMARY_BP = 6


def init_cell(anchor: int, word: int, bit: int) -> tuple[int, int]:
    """Return the (byte_offset, bit_position) for M9K init cell
    (word, bit) given the calibrated anchor byte.

    byte = anchor + (word // 2) * 210 - (word % 2) - 2 * bit
    bp   = 6
    """
    byte = anchor + (word // 2) * FRAME_SIZE - (word % 2) - 2 * bit
    return (byte, PRIMARY_BP)


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
                byte, bp = init_cell(anchor, w, bit)
                _assert_cell_safe(byte)
                _bit_flip(out, byte, bp)
                flips += 1
    return bytes(out)


def read_init(
    rbf_bytes: bytes,
    anchor: int,
    width: int = 9,
    depth: int = 512,
) -> list[int]:
    """Decode M9K init words from a raw RBF using the 2D formula.

    Returns depth words, each a `width`-bit int. Absolute decode
    (not delta-vs-base) — reads the primary cell for each (word, bit).
    """
    words = []
    for w in range(depth):
        v = 0
        for bit in range(width):
            byte, bp = init_cell(anchor, w, bit)
            _assert_cell_safe(byte)
            if rbf_bytes[byte] & (1 << bp):
                v |= (1 << bit)
        words.append(v)
    return words


if __name__ == "__main__":
    # Sanity: evaluate the anchor cell and print the formula's round-trip
    # coverage for the 9x512 site.
    anchor = M9K_INIT_ANCHORS[("X15_Y2_N0", 9, 512)]
    print(f"anchor(X15_Y2_N0, 9x512) = {anchor}")
    print(f"w=0 b=0 -> {init_cell(anchor, 0, 0)}")
    print(f"w=0 b=8 -> {init_cell(anchor, 0, 8)}")
    print(f"w=1 b=0 -> {init_cell(anchor, 1, 0)}")
    print(f"w=2 b=0 -> {init_cell(anchor, 2, 0)}")
    print(f"w=511 b=8 -> {init_cell(anchor, 511, 8)}")
    # Full 9x512 = 4608 cells; verify none collide with CRC
    cells = set()
    for w in range(512):
        for b in range(9):
            byte, bp = init_cell(anchor, w, b)
            _assert_cell_safe(byte)
            key = (byte, bp)
            if key in cells:
                raise RuntimeError(f"collision at w={w} b={b}: {key}")
            cells.add(key)
    print(f"4608 cells all unique, all outside CRC slots. Formula OK.")
