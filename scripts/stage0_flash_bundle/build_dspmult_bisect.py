# SPDX-License-Identifier: GPL-3.0-or-later
"""DSPMULT_GLOBAL_ON bisection layer 1 — silicon fault localization.

Stage 0 flash session 2026-04-16 falsified DSPMULT_GLOBAL_ON: all
23 cells applied atomically stuck LED0 constant-on on top of
simple_led_pure.  This script builds TWO bisection probes, each
flipping roughly half the 23 cells via raw `BIT` directives:

  * `simple_led_dspmult_half_A.rbf` — cells 0..11 (low frames
    1694..1710, block-band row A, 12 cells)
  * `simple_led_dspmult_half_B.rbf` — cells 12..22 (frames
    1712..1729, block-band row B, 11 cells)

HW flash outcome:

  * Both PASS → the 23 cells are individually safe but compose
    into a bad directive state (XOR parity / interaction bug).
  * A FAIL, B PASS → leaky cell is in {0..11}.  Next layer
    splits A into A0/A1.
  * A PASS, B FAIL → leaky cell is in {12..22}.  Next layer
    splits B into B0/B1.
  * Both FAIL → either 23-cell set has a leaky cell in each
    half, or XOR cancellation masks when applied separately.

log2(23) ≈ 5 bisection rounds to isolate a single cell.  This
script is layer 1.  Subsequent layers are built from the FAIL
half: split its cells 50/50 and re-run.

Cells list is loaded live from `fuzz/fasm2rbf._load_dspmult_global_on_cells()`
so it stays in sync with the directive.

Runs the same bit-level safety gate as the Stage 0 round-2 bundle.
"""
from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
sys.path.insert(0, str(REPO / "fuzz"))

import fasm2rbf as f
from pure_zero_rbf import make_pure_zero_rbf


PRE = 32
FRAME = 210
FIRST = 25
LAST = 1751
CRAM_START = PRE + FIRST * FRAME
CRAM_END = PRE + (LAST + 1) * FRAME
SAFE_FRAME_LO, SAFE_FRAME_HI = 1692, 1738


SIMPLE_LED_PREFIX = """\
NV_BASELINE_PACK
IOB_BASELINE_NV
IOB_IN  PIN_E16
IOB_OUT PIN_G15
IOB_CLK_INPUT PIN_E1
IOB_ROUTE PIN_E16 -> X10Y4N0.dataa
GCLK_PIN PIN_E1
LAB_CLK_SEL X10Y4
LAB_CLK_SEL_LE X10Y4N0
"""


def _bit_diff_set(a: bytes, b: bytes) -> set[tuple[int, int]]:
    out = set()
    for off in range(len(a)):
        x = a[off] ^ b[off]
        if not x:
            continue
        for bp in range(8):
            if x & (1 << bp):
                out.add((off, bp))
    return out


def _reset_caches():
    f._IOB_BASELINE_HDR_CACHE = None
    f._IOB_MAP_CACHE = None
    f._IOB_ROUTE_CACHE = None
    f._GCLK_PIN_CACHE = None
    f._LAB_CLK_SEL_CACHE.clear()
    f._LAB_CLK_SEL_LE_CACHE = None


def _build_half(label: str, cells: list[tuple[int, int]],
                pure: bytes, base_rbf: bytes) -> int:
    bit_lines = "\n".join(f"BIT {off} {bp}" for off, bp in cells) + "\n"
    fasm = SIMPLE_LED_PREFIX + bit_lines

    _reset_caches()
    out = f.bitgen(fasm, pure, patch_crc=True)
    out_path = HERE / f"simple_led_dspmult_half_{label}.rbf"
    out_path.write_bytes(out)
    print(f"\n[wrote] {out_path}  ({len(out)} bytes)  — {len(cells)} cells")

    diffs = [i for i in range(len(out)) if out[i] != base_rbf[i]]
    cram = [i for i in diffs if CRAM_START <= i < CRAM_END]
    data_cells = [i for i in cram if (i - PRE) % FRAME < 208]
    crc_diffs  = [i for i in cram if (i - PRE) % FRAME >= 208]
    print(f"  vs simple_led_pure: {len(diffs)} byte diffs  "
          f"(data={len(data_cells)} crc={len(crc_diffs)})")
    if data_cells:
        fc = Counter((i - PRE) // FRAME for i in data_cells)
        print(f"  frame range: {min(fc)}..{max(fc)}")

    sl_bits = _bit_diff_set(pure, base_rbf)
    di_bits = _bit_diff_set(base_rbf, out)
    overlap = sl_bits & di_bits
    crc_ov    = [(o,bp) for o,bp in overlap if (o-PRE)%FRAME >= 208]
    block_ov  = [(o,bp) for o,bp in overlap
                 if (o-PRE)%FRAME < 208
                 and SAFE_FRAME_LO <= (o-PRE)//FRAME <= SAFE_FRAME_HI]
    fabric_ov = [(o,bp) for o,bp in overlap
                 if (o-PRE)%FRAME < 208
                 and not (SAFE_FRAME_LO <= (o-PRE)//FRAME <= SAFE_FRAME_HI)]
    print(f"  overlap: total={len(overlap)}  CRC={len(crc_ov)}  "
          f"block={len(block_ov)}  fabric={len(fabric_ov)}")
    if fabric_ov:
        print(f"  [UNSAFE] half_{label} has fabric-band overlap:")
        for off, bp in sorted(fabric_ov):
            col = (off - PRE - 5282) // 7350 if off >= PRE + 5282 else -1
            frame = (off - PRE) // FRAME
            print(f"    off={off} bp={bp} col={col} frame={frame}")
        return 1
    print(f"  [SAFE*] half_{label} overlap is block-band only "
          f"-- safe to flash.")
    return 0


def main() -> int:
    pure = make_pure_zero_rbf()
    base_path = (REPO / "scripts" / "iob_slice_mining" / "work"
                 / "simple_led_E16_to_G15" / "fasm_pure.rbf")
    if not base_path.exists():
        print(f"[error] simple_led_pure.rbf not found at {base_path}")
        return 1
    base_rbf = base_path.read_bytes()

    _reset_caches()
    cells = sorted(f._load_dspmult_global_on_cells())
    n = len(cells)
    print(f"DSPMULT_GLOBAL_ON: {n} cells (expected 23)")
    assert n == 23, f"expected 23 cells, got {n}"

    half_a = cells[: n // 2]       # 11 cells (indices 0..10)
    half_b = cells[n // 2 :]       # 12 cells (indices 11..22)
    print(f"\nLayer-1 bisection:")
    print(f"  half_A: {len(half_a)} cells, frames "
          f"{(half_a[0][0]-PRE)//FRAME}..{(half_a[-1][0]-PRE)//FRAME}")
    print(f"  half_B: {len(half_b)} cells, frames "
          f"{(half_b[0][0]-PRE)//FRAME}..{(half_b[-1][0]-PRE)//FRAME}")

    rc_a = _build_half("A", half_a, pure, base_rbf)
    rc_b = _build_half("B", half_b, pure, base_rbf)
    return rc_a | rc_b


if __name__ == "__main__":
    sys.exit(main())
