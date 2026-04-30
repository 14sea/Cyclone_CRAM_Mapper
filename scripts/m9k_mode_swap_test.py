# SPDX-License-Identifier: GPL-3.0-or-later
"""Non-tautological M9K mode-correctness HW test (ζ-swap variant).

Strips Quartus's M9K mode block-band cells out of a known-good
m9k_blink reference and replaces them with the open-toolchain
inferred_goldintersect codec output.  Hardware behavior tells us
whether the gi codec actually configures the M9K's operation_mode
field correctly.

Strategy:
  R_ref       = Quartus m9k_blink_9x512 (LED blinks at 0.186 Hz, proven)
  R_stripped  = R_ref XOR (R_ref ⊕ nv_zero_global in block-band frames)
                — i.e. forces block-band frames back to nv_zero_global state
                (everything ELSE in the design — counter, IOBs, clock,
                M9K INIT, M9K I/O routing — stays Quartus-built)
  R_swap      = R_stripped XOR (gi cells from m9k_mode_bits.json)
                — applies the open-toolchain gi codec to those frames

If R_swap blinks LED0 at the same 0.186 Hz on AX301 → gi codec is
mode-correct.  If LED is stuck or doesn't blink → gi codec is mode-
incorrect (its 38 cells set a different / wrong M9K mode when
applied on top of nv_zero_global state).

Run from repo root:
    python3 scripts/m9k_mode_swap_test.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "fuzz"))

from bitstream import patch_rbf_crc  # noqa: E402

R_REF = ROOT / "tmp/m9k_blink_9x512_full/m9k_blink_9x512_full.rbf"
NV    = ROOT / "results/rbf/nv_zero_global.rbf"
MODE_BITS = ROOT / "results/m9k_mode_bits.json"
OUT   = ROOT / "tmp/m9k_blink_9x512_full/m9k_blink_9x512_gi_swap.rbf"

BLOCK_FRAME_LO = 1692
BLOCK_FRAME_HI = 1738
PRE = 32
FRAME = 210


def block_band_diff_cells(a: bytes, b: bytes) -> list[tuple[int, int]]:
    cells = []
    for i in range(len(a)):
        if a[i] != b[i]:
            frame = (i - PRE) // FRAME
            if BLOCK_FRAME_LO <= frame <= BLOCK_FRAME_HI:
                x = a[i] ^ b[i]
                for bp in range(8):
                    if x & (1 << bp):
                        cells.append((i, bp))
    return cells


def xor_flip(buf: bytearray, cells) -> None:
    for off, bp in cells:
        buf[off] ^= 1 << bp


def main() -> int:
    r_ref = R_REF.read_bytes()
    nv = NV.read_bytes()
    assert len(r_ref) == len(nv) == 368011

    # Step 1: identify block-band cells where Quartus m9k_blink differs
    # from nv_zero_global at the M9K X=15 site.  We DON'T filter to a
    # specific column because all block-band differences in this design
    # come from the single M9K placed at X15_Y10 (the only memory
    # block in this fit) — confirmed by `Fitter RAM Summary`.
    quartus_block_band = block_band_diff_cells(r_ref, nv)
    print(f"Quartus m9k_blink ⊕ nv_zero_global in block-band: "
          f"{len(quartus_block_band)} cells")

    # Step 2: load gi codec cells for X15_Y10_N0 9x512
    d = json.loads(MODE_BITS.read_text())
    entry = d["X15_Y10_N0_9x512"]
    gi = [tuple(c) for c in entry["cells_by_template"]["inferred_goldintersect"]]
    inf = [tuple(c) for c in entry["cells_by_template"]["inferred"]]
    print(f"gi codec footprint: {len(gi)} cells")
    print(f"inferred (mining truth) footprint: {len(inf)} cells")

    # Step 3: build R_swap
    buf = bytearray(r_ref)
    # 3a. Strip Quartus's M9K mode cells (force block-band back to nv state).
    xor_flip(buf, quartus_block_band)
    # 3b. Apply gi codec (XOR delta).
    xor_flip(buf, gi)
    # Verify block-band state in buf vs nv:
    swapped = block_band_diff_cells(bytes(buf), nv)
    print(f"After swap: block-band cells differing from nv: {len(swapped)} "
          f"(expected ≈ {len(gi)})")
    extras = set(swapped) - set(gi)
    missing = set(gi) - set(swapped)
    if extras or missing:
        print(f"  extras (not in gi): {len(extras)}; missing (gi cells not "
              f"applied): {len(missing)}")

    # Step 4: re-CRC and write
    out = patch_rbf_crc(bytes(buf))
    OUT.write_bytes(out)
    print(f"\n[wrote] {OUT.relative_to(ROOT)}  ({len(out)} bytes)")
    print("Flash with:")
    print(f"  $HOME/see_neorv32_run_linux/tools/openFPGALoader/build/openFPGALoader "
          f"-c usb-blaster {OUT.relative_to(ROOT)}")
    print("\nExpected behavior: same as Quartus m9k_blink_9x512 — LED0 "
          "blinks at ~0.186 Hz (~2.7 s on / 2.7 s off).")
    print("If LED is stuck on/off or blinks at a different rate, gi codec "
          "does not configure the M9K mode correctly when applied on top "
          "of nv_zero_global state.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
