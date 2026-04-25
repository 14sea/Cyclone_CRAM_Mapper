# SPDX-License-Identifier: GPL-3.0-or-later
"""D2 fix probe — single-variant bucket on zero baseline.

Per `m9k_mode_codec_silicon_broken_2026_04_25.md`, D2 is:
    bucket_d2 = (v0 ⊕ nv_zero_global)   restricted to block band
i.e., no v0/v1/v2 intersection — keep every block-band cell that
v0 differs from zero on, INIT-correlated metadata included.

Layer-1 (polarity vs nv_zero_global) is fixed by mining-base-relative
construction. Layer-2 (over-filtering) is fixed by NOT intersecting.

Probe site = X15_Y16_N0 SDP (4, 2048) — same site where the 21-cell
intersection silicon-reset, so a non-reset here is the cleanest
"D2 unblocks the codec" signal.

Two outputs:
  * `tmp/d2_probe_pure_zero_sdp_X15_Y16.rbf` — `nv_zero_global ⊕ d2`,
    CRC repatched. Pure codec-emission probe: PASS = silicon does not
    reset (M9K mode safely loaded onto zero baseline). No blink test
    possible — no counter / IO / wires.
  * Diagnostic stdout: bucket size + breakdown vs baseline-shared
    cells.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "fuzz"))

from bitstream import patch_rbf_crc

PRE, FRAME, DPF = 32, 210, 208
BLOCK_LO, BLOCK_HI = 1692, 1738

ZERO = ROOT / "results/rbf/nv_zero_global.rbf"
SITE_DIR = ROOT / "tmp/m9k_mode_quartus_gold/4x2048/sdp/X15_Y16_N0"
V0 = SITE_DIR / "m9k_mode_gold_4x2048_sdp_v0.rbf"
V1 = SITE_DIR / "m9k_mode_gold_4x2048_sdp_v1.rbf"
V2 = SITE_DIR / "m9k_mode_gold_4x2048_sdp_v2.rbf"
BASE = SITE_DIR / "m9k_mode_gold_4x2048_sdp_baseline.rbf"

OUT = ROOT / "tmp/d2_probe_pure_zero_sdp_X15_Y16.rbf"


def block_band_cells(a: bytes, b: bytes) -> list[tuple[int, int]]:
    cells: list[tuple[int, int]] = []
    for off in range(PRE, len(a)):
        frame = (off - PRE) // FRAME
        if frame < BLOCK_LO or frame > BLOCK_HI:
            continue
        if (off - PRE) % FRAME >= DPF:
            continue
        x = a[off] ^ b[off]
        if not x:
            continue
        for bp in range(8):
            if x & (1 << bp):
                cells.append((off, bp))
    return cells


def main() -> int:
    zero = ZERO.read_bytes()
    v0 = V0.read_bytes()
    v1 = V1.read_bytes()
    v2 = V2.read_bytes()
    base = BASE.read_bytes()

    d2 = block_band_cells(v0, zero)
    inter21 = list(set(block_band_cells(v0, zero))
                   & set(block_band_cells(v1, zero))
                   & set(block_band_cells(v2, zero)))
    base_cells = set(block_band_cells(base, zero))
    d2_set = set(d2)
    print(f"D2 bucket = {len(d2)} cells (v0 ⊕ zero, block band)")
    print(f"  vs current intersection bucket = {len(inter21)} cells "
          f"(silicon-reset reference)")
    print(f"  D2 cells unique to M9K (not in no-M9K baseline) = "
          f"{len(d2_set - base_cells)}")
    print(f"  D2 cells shared with baseline (design infra) = "
          f"{len(d2_set & base_cells)}")
    print(f"  D2 ⊃ intersection? {set(inter21) <= d2_set}")

    emit = bytearray(zero)
    for off, bp in d2:
        emit[off] ^= (1 << bp)
    patch_rbf_crc(emit)
    OUT.write_bytes(bytes(emit))
    print(f"\nWrote {OUT}  (size={len(emit)})")
    print(f"Flash with: openFPGALoader -c usb-blaster {OUT}")
    print("Expected on PASS: board stays alive (LED0 default off, "
          "no power-cycle reset, JTAG responsive). LED will NOT "
          "blink — there is no counter / IO / wiring in this RBF.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
