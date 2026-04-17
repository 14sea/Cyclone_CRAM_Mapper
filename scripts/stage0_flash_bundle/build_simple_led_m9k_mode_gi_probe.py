# SPDX-License-Identifier: GPL-3.0-or-later
"""HW probe: simple_led + M9K_MODE_9x512_inferred_goldintersect safe-emit.

Stage-0 falsification stress-test for the
`X15Y10N0.M9K_MODE_9x512_inferred_goldintersect` codec suffix (landed
2026-04-17 in commit d4a26aa).

The goldintersect bucket is 38 cells = inferred (77) ∩ smoke_gold (76).
HW outcome decides which bucket np2fasm should emit for M9K MODE:

  * LED still follows KEY2 → goldintersect is a clean subset; np2fasm
    can ungate with `_inferred_goldintersect` as the preferred suffix.
  * LED broken → even the 38-cell safe subset leaks into fabric
    pathways; M9K_MODE emission stays permanently gated pending a
    different mining strategy.

Safety gate: 38 cells confined to block band (frames 1692..1738).
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


FASM = """\
NV_BASELINE_PACK
IOB_BASELINE_NV
IOB_IN  PIN_E16
IOB_OUT PIN_G15
IOB_CLK_INPUT PIN_E1
IOB_ROUTE PIN_E16 -> X10Y4N0.dataa
GCLK_PIN PIN_E1
LAB_CLK_SEL X10Y4
LAB_CLK_SEL_LE X10Y4N0
X15Y10N0.M9K_MODE_9x512_inferred_goldintersect
"""


def main() -> int:
    pure = make_pure_zero_rbf()
    base_path = (REPO / "scripts" / "iob_slice_mining" / "work"
                 / "simple_led_E16_to_G15" / "fasm_pure.rbf")
    base_rbf = base_path.read_bytes() if base_path.exists() else None

    f._IOB_BASELINE_HDR_CACHE = None
    f._IOB_MAP_CACHE = None
    f._IOB_ROUTE_CACHE = None
    f._GCLK_PIN_CACHE = None
    f._LAB_CLK_SEL_CACHE.clear()
    f._LAB_CLK_SEL_LE_CACHE = None
    f._M9K_MODE_CACHE = None

    out = f.bitgen(FASM, pure, patch_crc=True)

    out_path = HERE / "simple_led_m9k_mode_goldintersect.rbf"
    out_path.write_bytes(out)
    print(f"[wrote] {out_path}  ({len(out)} bytes)")

    if not base_rbf:
        print("[skip] base simple_led_pure.rbf not found — cannot run safety gate")
        return 1

    diffs = [i for i in range(len(out)) if out[i] != base_rbf[i]]
    cram = [i for i in diffs if CRAM_START <= i < CRAM_END]
    hdr = [i for i in diffs if i < CRAM_START]
    trl = [i for i in diffs if i >= CRAM_END]
    data_cells = [i for i in cram if (i - PRE) % FRAME < 208]
    crc_diffs = [i for i in cram if (i - PRE) % FRAME >= 208]

    print(f"\n vs simple_led_pure: {len(diffs)} byte diffs")
    print(f"   hdr   : {len(hdr):4d} (expected: 0)")
    print(f"   CRAM  : {len(cram):4d}")
    print(f"     data : {len(data_cells):4d} (expected: 38)")
    print(f"     CRC  : {len(crc_diffs):4d} (varies as cells cross frames)")
    print(f"   trl   : {len(trl):4d} (expected: 0)")

    if data_cells:
        fc = Counter((i - PRE) // FRAME for i in data_cells)
        frames = sorted(fc.keys())
        print(f"   data frame range: {min(frames)}..{max(frames)} "
              f"(expected 1692..1738 = block band)")

    SAFE_FRAME_LO, SAFE_FRAME_HI = 1692, 1738
    unsafe = [i for i in data_cells
              if not (SAFE_FRAME_LO <= (i - PRE) // FRAME <= SAFE_FRAME_HI)]
    if unsafe:
        print(f"\n  [UNSAFE] {len(unsafe)} cells outside block band "
              f"frames {SAFE_FRAME_LO}..{SAFE_FRAME_HI} -- DO NOT FLASH.")
        for off in unsafe[:10]:
            col = (off - PRE - 5282) // 7350
            frame = (off - PRE) // FRAME
            print(f"   off={off} col={col} frame={frame}")
        return 1

    print(f"\n  [SAFE] all {len(data_cells)} data cells confined to block "
          f"band (frames {SAFE_FRAME_LO}..{SAFE_FRAME_HI}) -- safe to flash.")
    print("\nExpected HW behavior: LED0 still blinks on KEY2 press (identical "
          "to simple_led_pure). If LED stuck on/off, M9K_MODE goldintersect "
          "bucket leaks into functional fabric.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
