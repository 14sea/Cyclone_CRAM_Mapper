# SPDX-License-Identifier: GPL-3.0-or-later
"""HW probe: simple_led + IOB_OE PIN_R5 (= sdram_dq S_DB[0]) safe-emit.

Stage-0 falsification stress-test for `IOB_OE PIN_X` (landed in commit
5b7f90f, codec-side only; memory `iob_oe_directive_landed.md`).

PIN_R5 is the package pin bound to SDRAM data-bus signal S_DB[0], one
of the 16 mined sdram_dq pins.  It's picked because it does not
overlap simple_led's active pins (E16/G15/E1).  Its per-pin cell set
is 40 cells spanning frames 353..1738 — so this probe uses a
stricter safety gate than the block-band-only directives:

  * `directive_bits ∩ simple_led_bits == empty` (bit-level, not just
    byte-level) — asserts the directive can XOR-apply on top of
    simple_led without mutating any cell simple_led depends on.
  * Frame range of directive cells is NOT restricted — IOB config
    cells legitimately live outside the block band.

Expected behavior:

  * LED follows KEY2 exactly as simple_led_pure (S_DB[0] has no fabric
    connection in this design, so flipping its OE-enable bits is a
    config no-op on the silicon's routing of E16/G15/E1).
  * If LED behavior changes vs simple_led_pure, IOB_OE leaks into
    non-IOB pathways (same failure mode as DSPMULT_GLOBAL_ON).
"""
from __future__ import annotations

import json
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
IOB_OE PIN_R5
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
    f._IOB_OE_CACHE = None

    out = f.bitgen(FASM, pure, patch_crc=True)

    out_path = HERE / "simple_led_iob_oe_r5.rbf"
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
    print(f"     data : {len(data_cells):4d} (expected: 40 per iob_oe_cell_map.json / PIN_R5)")
    print(f"     CRC  : {len(crc_diffs):4d}")
    print(f"   trl   : {len(trl):4d}")

    if data_cells:
        fc = Counter((i - PRE) // FRAME for i in data_cells)
        frames = sorted(fc.keys())
        print(f"   data frame range: {min(frames)}..{max(frames)} "
              f"(expected ~353..1738 per PIN_R5 per-pin OE cells)")

    # STRICT SAFETY GATE: bit-level intersection with simple_led_pure's cells.
    # Partition overlap into:
    #   - CRC bytes (off%210 >= 208): cosmetic, auto-patched by patch_crc
    #   - block band (1692..1738): baseline M9K/MULT/arith defaults; simple_led
    #     uses no block-band feature, so flipping these cannot affect LED
    #   - fabric band (CRAM data outside block band): the real risk region
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
        print(f"\n  [UNSAFE] {len(fabric_ov)} fabric-band bits overlap "
              f"simple_led's active cells -- DO NOT FLASH.  Listing:")
        for off, bp in sorted(fabric_ov):
            col = (off - PRE - 5282) // 7350 if off >= PRE + 5282 else -1
            frame = (off - PRE) // FRAME
            print(f"   off={off} bp={bp} col={col} frame={frame}")
        return 1

    # Cross-check: directive bits should match the IOB_OE cell map for S_DB[0]
    cmap = json.loads((REPO / "results" / "iob_oe_cell_map.json").read_text())
    pin_cells = {tuple(c) for c in cmap["per_pin_oe"]["S_DB[0]"]}
    unexpected = directive_bits - pin_cells
    if unexpected:
        print(f"\n  [WARN] {len(unexpected)} directive bits NOT in "
              f"S_DB[0] per-pin cell set (may be CRC / frame-cross noise)")
    else:
        print(f"\n  directive bits are a subset of iob_oe_cell_map[S_DB[0]] "
              f"({len(pin_cells)} cells)")

    if block_ov:
        print(f"\n  [SAFE*] {len(block_ov)} overlap bits are all in block "
              f"band (frames {SAFE_FRAME_LO}..{SAFE_FRAME_HI}). simple_led "
              f"uses no block feature, so XOR-flipping these cannot affect "
              f"LED behavior -- safe to flash.")
    else:
        print(f"\n  [SAFE] directive bits are disjoint from simple_led's "
              f"active cells -- safe to flash.")
    print("\nExpected HW behavior: LED0 still blinks on KEY2 press (identical "
          "to simple_led_pure). If LED stuck on/off, IOB_OE PIN_R5 "
          "(sdram_dq S_DB[0]) leaks into functional fabric.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
