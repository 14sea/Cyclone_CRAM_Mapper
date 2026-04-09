# SPDX-License-Identifier: GPL-3.0-or-later
"""Phase 5.2 Stage A null test — compile the SAME zero-init M9K twice
and measure the CRAM-only noise floor.

Mandatory for any non-LAB mining (per
memory/feedback_header_band_noise_floor.md). If the null delta is
larger than the per-bit signal we expect from m9k_init_sweep.py (one
SRAM bit per init bit), the Stage A premise is dead and we must
switch to structured-pattern mining.

Analyzes both:
  - full CRAM band (off >= 5282, excluding CRC bytes at frame pos
    208/209) — the legitimate mining window
  - Phase 5.0 non-LAB block band (frames 1692-1738) — where M9K
    config cells are known to live

Success criterion: null delta should be <= a handful of cells in
the block band. If the LAB-routing harness (addr/data going through
fabric) creates large null delta outside the block band, we'll still
be fine as long as frames 1692-1738 are quiet.
"""
import os, sys, json, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from m9k_init_harness import build
from config import RBF_DIR

FRAME_SIZE = 210
HEADER_END = 5282     # bytes 32..5281 are the 25-frame header
BLOCK_FRAMES = range(1692, 1739)   # Phase 5.0 DSPMULT/M9K band


def cram_cells(base: bytes, other: bytes) -> list[tuple[int, int]]:
    """XOR-diff, return (byte_off, bit_pos) only for CRAM bytes,
    excluding per-frame CRC slots (offsets 208/209 within a frame)."""
    out = []
    n = min(len(base), len(other))
    for i in range(HEADER_END, n):
        x = base[i] ^ other[i]
        if not x:
            continue
        off_in_frame = (i - 32) % FRAME_SIZE
        if off_in_frame >= 208:
            continue
        for bp in range(8):
            if x >> bp & 1:
                out.append((i, bp))
    return out


def frames_of(cells: list[tuple[int, int]]) -> set[int]:
    return {(c[0] - 32) // FRAME_SIZE for c in cells}


def block_band_cells(cells: list[tuple[int, int]]) -> list[tuple[int, int]]:
    return [c for c in cells
            if ((c[0] - 32) // FRAME_SIZE) in BLOCK_FRAMES]


def main():
    runs = []
    for i in (1, 2):
        tag = f"m9k_null_{i}"
        out = os.path.join(RBF_DIR, f"{tag}.rbf")
        t0 = time.time()
        rbf, t, err = build(tag, overrides=None, rbf_output=out)
        if rbf is None:
            print(f"[{i}] compile FAIL ({t:.1f}s): {err[:400]}")
            return
        print(f"[{i}] compile OK ({t:.1f}s) -> {out}")
        runs.append(open(out, "rb").read())

    cells = cram_cells(runs[0], runs[1])
    block = block_band_cells(cells)
    touched_frames = sorted(frames_of(cells))
    print()
    print(f"null delta (full CRAM band):  {len(cells)} cells")
    print(f"null delta (1692-1738 band):  {len(block)} cells")
    print(f"frames touched: {len(touched_frames)}  "
          f"(block-band frames: "
          f"{sorted(set(touched_frames) & set(BLOCK_FRAMES))})")

    if len(block) == 0:
        print("\n>>> CLEAN in block band. Stage A proceed.")
    elif len(block) <= 4:
        print("\n>>> NEARLY CLEAN (<=4 cells). Stage A proceed but watch "
              "per-bit signal closely.")
    else:
        print(f"\n>>> NOISY: {len(block)} cells in block band. Investigate "
              "before trusting Stage A per-bit results.")

    os.makedirs("results", exist_ok=True)
    with open("results/m9k_init_null.json", "w") as f:
        json.dump({
            "null_cram_all": len(cells),
            "null_block_band": len(block),
            "block_band_cells": [list(c) for c in block],
            "touched_frames": touched_frames,
        }, f, indent=1)
    print("\narchived results/m9k_init_null.json")


if __name__ == "__main__":
    main()
