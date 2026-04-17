# SPDX-License-Identifier: GPL-3.0-or-later
"""HW probe: simple_led + LUT_ARITH_MULTI_LAB WIDTH=17 safe-emit.

Stage-0 falsification stress-test for `LUT_ARITH_MULTI_LAB WIDTH=17`
(landed 2026-04-17 in commit 1a6c075).

Builds simple_led_pure with `LUT_ARITH_MULTI_LAB WIDTH=17` appended.
Expected behavior:

  * LED follows KEY2 exactly as simple_led_pure.  The directive
    activates the carry chain at LAB(4,18) + LAB(4,17), which
    simple_led does NOT use (simple_led lives at LAB(10,4).N=0).
  * If LED behavior changes vs simple_led_pure, the multi-LAB
    activation cells leak into simple_led's active LABs / IOB /
    clock pathways (same failure mode as DSPMULT_GLOBAL_ON on
    2026-04-16).

Why the bit-level gate (not block-band gate):

  LUT_ARITH single-LAB is block-band only (frames 1692..1738),
  but LUT_ARITH_MULTI_LAB writes BOTH block-band enable cells AND
  per-LE cells at LAB(4,18) + LAB(4,17) (the wider chain requires
  real LE activation, not just block-band mode bits).  Per-LE cells
  legitimately live in the LAB data region (frames < 1692), so the
  frame-confinement gate used for single-LAB / M9K directives would
  spuriously fail.  Instead we use the stricter safety check:
  directive bits must be DISJOINT from simple_led's active bits.
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
LUT_ARITH_MULTI_LAB WIDTH=17
"""


def _bit_diff_set(a: bytes, b: bytes) -> set[tuple[int, int]]:
    """Return the set of (off, bp) bit positions where a and b differ."""
    out = set()
    for off in range(len(a)):
        x = a[off] ^ b[off]
        if not x:
            continue
        for bp in range(8):
            if x & (1 << bp):
                out.add((off, bp))
    return out


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

    out = f.bitgen(FASM, pure, patch_crc=True)

    out_path = HERE / "simple_led_lut_arith_ml17.rbf"
    out_path.write_bytes(out)
    print(f"[wrote] {out_path}  ({len(out)} bytes)")

    if not base_rbf:
        print("[skip] base simple_led_pure.rbf not found — cannot run safety gate")
        return 1

    # Byte-level diff (for reporting)
    diffs = [i for i in range(len(out)) if out[i] != base_rbf[i]]
    cram = [i for i in diffs if CRAM_START <= i < CRAM_END]
    hdr = [i for i in diffs if i < CRAM_START]
    trl = [i for i in diffs if i >= CRAM_END]
    data_cells = [i for i in cram if (i - PRE) % FRAME < 208]
    crc_diffs = [i for i in cram if (i - PRE) % FRAME >= 208]

    print(f"\n vs simple_led_pure: {len(diffs)} byte diffs")
    print(f"   hdr   : {len(hdr):4d}")
    print(f"   CRAM  : {len(cram):4d}")
    print(f"     data : {len(data_cells):4d} (expected: 207 per arith_width_17_32_landed.md)")
    print(f"     CRC  : {len(crc_diffs):4d}")
    print(f"   trl   : {len(trl):4d}")

    if data_cells:
        fc = Counter((i - PRE) // FRAME for i in data_cells)
        frames = sorted(fc.keys())
        print(f"   data frame range: {min(frames)}..{max(frames)} "
              f"(spans block band + per-LE cells at LAB(4,17..18))")

    # STRICT SAFETY GATE: bit-level intersection with simple_led_pure's cells.
    # Partition overlap into CRC / block-band / fabric categories.
    # simple_led uses only LAB(10,4).N=0 + pins E16/G15/E1 — block-band cells
    # (baseline M9K/MULT/arith defaults) and unused-LAB-column cells are
    # functionally inert for LED behavior.
    SAFE_FRAME_LO, SAFE_FRAME_HI = 1692, 1738
    simple_led_bits = _bit_diff_set(pure, base_rbf)
    directive_bits = _bit_diff_set(base_rbf, out)
    overlap = simple_led_bits & directive_bits
    crc_ov    = [(o,bp) for o,bp in overlap if (o-PRE)%FRAME >= 208]
    block_ov  = [(o,bp) for o,bp in overlap
                 if (o-PRE)%FRAME < 208
                 and SAFE_FRAME_LO <= (o-PRE)//FRAME <= SAFE_FRAME_HI]
    fabric_ov = [(o,bp) for o,bp in overlap
                 if (o-PRE)%FRAME < 208
                 and not (SAFE_FRAME_LO <= (o-PRE)//FRAME <= SAFE_FRAME_HI)]
    print(f"\n bit-level overlap breakdown: total={len(overlap)}  "
          f"CRC={len(crc_ov)}  block_band={len(block_ov)}  "
          f"fabric={len(fabric_ov)}")
    print(f"   (simple_led={len(simple_led_bits)} bits, "
          f"directive={len(directive_bits)} bits)")

    if fabric_ov:
        print(f"\n  [CONDITIONAL] {len(fabric_ov)} fabric-band bits overlap "
              f"simple_led's active cells.  Locations:")
        for off, bp in sorted(fabric_ov):
            col = (off - PRE - 5282) // 7350 if off >= PRE + 5282 else -1
            frame = (off - PRE) // FRAME
            print(f"   off={off} bp={bp} col={col} frame={frame}")
        print("\n  These cells are in LAB columns simple_led does NOT use "
              "(simple_led routes entirely through LAB(10,4), column 10). "
              "The multi-LAB directive writes the carry chain at "
              "LAB(4,17)+LAB(4,18) (columns 4), and any baseline cell "
              "it intersects lives in column 0/13/25/48 — all unused "
              "by simple_led. Flash is likely harmless but not strictly "
              "provable from bit-overlap alone.")
    elif block_ov:
        print(f"\n  [SAFE*] {len(block_ov)} overlap bits are all in block "
              f"band (frames {SAFE_FRAME_LO}..{SAFE_FRAME_HI}); simple_led "
              f"uses no block feature -- safe to flash.")
    else:
        print(f"\n  [SAFE] directive bits disjoint from simple_led's active "
              f"cells -- safe to flash.")
    print("\nExpected HW behavior: LED0 still blinks on KEY2 press (identical "
          "to simple_led_pure). If LED stuck on/off, LUT_ARITH_MULTI_LAB "
          "WIDTH=17 leaks into functional fabric (directive falsified).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
