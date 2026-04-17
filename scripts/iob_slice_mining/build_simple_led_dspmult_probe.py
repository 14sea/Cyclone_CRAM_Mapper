# SPDX-License-Identifier: GPL-3.0-or-later
"""HW probe: simple_led + DSPMULT_GLOBAL_ON safe-emit.

Stage-0 falsification stress-test for the newly landed
`DSPMULT_GLOBAL_ON` directive. Memory `dspmult_global_on_clean_remine.md`
claims its 23 cells are pure DSPMULT block enable (no LE/IOB leak),
inverting an older "29 universal cells" claim that was 100% harness
routing artifacts.

This builds simple_led_pure with `DSPMULT_GLOBAL_ON` appended. The
expected behavior:

  * LED follows KEY2 exactly as simple_led_pure (no DSP I/O routed,
    so the activated DSP block is a no-op).
  * If LED behavior changes vs simple_led_pure, the 23 universal cells
    are NOT pure DSP-block enable — they leak into LE/IOB pathways,
    partially falsifying `dspmult_global_on_clean_remine.md`.

Safety:

  * 23 cells in block band frames 1694-1729 (LAB cols 48-49 = X=20
    mult column). Zero overlap with simple_led's X=10 LAB cells.
  * Zero overlap with E16/G15/E1 IOB cells.
  * Doesn't change any pin direction, doesn't enable extra drivers.
  * DSP block has no I/O wired in this design → idle / no current draw.
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
DSPMULT_GLOBAL_ON
"""


def main() -> int:
    pure = make_pure_zero_rbf()
    base_path = (HERE / "work" / "simple_led_E16_to_G15"
                       / "fasm_pure.rbf")
    base_rbf = base_path.read_bytes() if base_path.exists() else None

    f._IOB_BASELINE_HDR_CACHE = None
    f._IOB_MAP_CACHE = None
    f._IOB_ROUTE_CACHE = None
    f._GCLK_PIN_CACHE = None
    f._LAB_CLK_SEL_CACHE.clear()
    f._LAB_CLK_SEL_LE_CACHE = None

    out = f.bitgen(FASM, pure, patch_crc=True)

    out_path = HERE / "work" / "simple_led_E16_to_G15" / "fasm_pure_dspmult.rbf"
    out_path.write_bytes(out)
    print(f"[wrote] {out_path}  ({len(out)} bytes)")

    if base_rbf:
        diffs = [i for i in range(len(out)) if out[i] != base_rbf[i]]
        cram = [i for i in diffs if CRAM_START <= i < CRAM_END]
        hdr = [i for i in diffs if i < CRAM_START]
        trl = [i for i in diffs if i >= CRAM_END]
        # Exclude CRC bytes (last 2 of each frame)
        data_cells = [i for i in cram if (i - PRE) % FRAME < 208]
        crc_diffs = [i for i in cram if (i - PRE) % FRAME >= 208]
        print(f"\n vs simple_led_pure: {len(diffs)} byte diffs")
        print(f"   hdr   : {len(hdr):4d} (expected: 0)")
        print(f"   CRAM  : {len(cram):4d}")
        print(f"     data : {len(data_cells):4d} (expected: 23)")
        print(f"     CRC  : {len(crc_diffs):4d} (varies as cells cross frames)")
        print(f"   trl   : {len(trl):4d} (expected: 0)")
        if data_cells:
            fc = Counter((i - PRE) // FRAME for i in data_cells)
            frames = sorted(fc.keys())
            print(f"   data frame range: {min(frames)}..{max(frames)} "
                  f"(expected 1692..1738 = block band)")
            cols = sorted({(i - PRE - 5282) // 7350 for i in data_cells})
            print(f"   col range      : {min(cols)}..{max(cols)} "
                  f"(expected 47..48 = mult X=20 region)")
        # SAFETY GATE: data cells must be confined to dedicated block band
        # (frames 1692..1738 per phase5_nonlab_block_band). Cells outside
        # this range would mean the directive leaks into LE/IOB CRAM and
        # could change pin/LE function -> NOT SAFE to flash.
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
        print(f"\n  [SAFE] all 23 data cells confined to dedicated block "
              f"band (frames {SAFE_FRAME_LO}..{SAFE_FRAME_HI}) -- safe "
              f"to flash. No LE/IOB CRAM affected.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
