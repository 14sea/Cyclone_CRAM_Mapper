# SPDX-License-Identifier: GPL-3.0-or-later
"""D2-extended probe — explore what cells outside block-band M9K needs.

D2 (block-band only, 35 cells) silicon-reset. Mining methodology
assumes M9K mode bits live entirely in frames 1692..1738, but the
reset implies otherwise. This probe builds a series of expansion
buckets to bisect what region(s) silicon actually requires.

Each variant: (v0 ⊕ nv_zero_global) ∩ {region}, applied as XOR onto
nv_zero_global. PASS = no reset (LEDs idle, board responsive). FAIL =
silicon reset.

Variant chosen via --variant {a,b,c,d}:
  a: block_band + block_band_post   (1692..1751, ~60 cells)
  b: a + lab_high                   (+1014..1691,  ~110 cells)
  c: b + header                     (+0..24,       ~822 cells)
  d: full v0 ⊕ zero                 (= byte-identical to v0, ~5222 cells)
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "fuzz"))

from bitstream import patch_rbf_crc

PRE, FRAME, DPF = 32, 210, 208

ZERO = ROOT / "results/rbf/nv_zero_global.rbf"
V0 = ROOT / "tmp/m9k_mode_quartus_gold/4x2048/sdp/X15_Y16_N0/m9k_mode_gold_4x2048_sdp_v0.rbf"

REGIONS = {
    "a": [(1692, 1751)],
    "b": [(1014, 1751)],
    "c": [(0, 24), (1014, 1751)],
    "d": [(0, 1751)],
}


def cells_in_regions(a: bytes, b: bytes, regions: list[tuple[int, int]]):
    out = []
    for off in range(PRE, len(a)):
        frame = (off - PRE) // FRAME
        if (off - PRE) % FRAME >= DPF:
            continue
        in_region = any(lo <= frame <= hi for lo, hi in regions)
        if not in_region:
            continue
        x = a[off] ^ b[off]
        if not x:
            continue
        for bp in range(8):
            if x & (1 << bp):
                out.append((off, bp))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--variant", choices=list(REGIONS), required=True)
    args = ap.parse_args()

    zero = ZERO.read_bytes()
    v0 = V0.read_bytes()
    cells = cells_in_regions(v0, zero, REGIONS[args.variant])
    emit = bytearray(zero)
    for off, bp in cells:
        emit[off] ^= (1 << bp)
    patch_rbf_crc(emit)

    out = ROOT / f"tmp/d2_ext_{args.variant}_sdp_X15_Y16.rbf"
    out.write_bytes(bytes(emit))
    print(f"variant {args.variant}: {len(cells)} cells, frames "
          f"{REGIONS[args.variant]}")
    print(f"-> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
