# SPDX-License-Identifier: GPL-3.0-or-later
"""Build simple_led on top of PURE_ZERO via NV_BASELINE_PACK.

Stage-0 HW-flash candidate: proves NV_BASELINE_PACK is silicon-equivalent
to the legacy nv_zero_global.rbf (Phase 7 retirement gate). Same FASM body
as `build_simple_led_fasm.py`, but the baseline is the directive-synthesised
PURE_ZERO + NV_BASELINE_PACK pair instead of the opaque Quartus-built
nv_zero_global.

Diffs vs Quartus gold (simple_led_E16_to_G15.rbf) and vs the nv-baseline
build (build_simple_led_fasm.py output) are reported. If both are 0,
the resulting RBF is a hot-swap drop-in for the nv-baseline path.
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
"""


def main() -> int:
    pure = make_pure_zero_rbf()
    gold_path = (HERE / "work" / "simple_led_E16_to_G15"
                 / "output_files" / "simple_led_E16_to_G15.rbf")
    gold = gold_path.read_bytes()
    nv_fasm_path = (HERE / "work" / "simple_led_E16_to_G15" / "fasm.rbf")
    assert len(pure) == len(gold) == 368011

    f._IOB_BASELINE_HDR_CACHE = None
    f._IOB_MAP_CACHE = None
    f._IOB_ROUTE_CACHE = None
    f._GCLK_PIN_CACHE = None
    f._LAB_CLK_SEL_CACHE.clear()
    f._LAB_CLK_SEL_LE_CACHE = None

    out = f.bitgen(FASM, pure, patch_crc=True)

    out_path = HERE / "work" / "simple_led_E16_to_G15" / "fasm_pure.rbf"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(out)
    print(f"[wrote] {out_path}  ({len(out)} bytes)")

    # 1. vs Quartus gold
    diffs = [i for i in range(len(out)) if out[i] != gold[i]]
    hdr = [i for i in diffs if i < CRAM_START]
    cram = [i for i in diffs if CRAM_START <= i < CRAM_END]
    trl = [i for i in diffs if i >= CRAM_END]
    print(f"\nFASM(pure) vs Quartus gold: {len(diffs)} byte diffs")
    print(f"  hdr   : {len(hdr):4d}")
    print(f"  CRAM  : {len(cram):4d}")
    print(f"  trl   : {len(trl):4d}")
    if cram:
        fc = Counter((i - PRE) // FRAME for i in cram)
        print(f"  CRAM frame histogram (top 12): {fc.most_common(12)}")

    # 2. vs the nv-baseline FASM build (same design, different baseline)
    if nv_fasm_path.exists():
        nv_fasm = nv_fasm_path.read_bytes()
        diffs2 = [i for i in range(len(out)) if out[i] != nv_fasm[i]]
        print(f"\nFASM(pure) vs FASM(nv): {len(diffs2)} byte diffs")
        if not diffs2:
            print("  [PERFECT] pure-baseline path is byte-identical to nv-baseline path.")
    else:
        print(f"\n[skip] nv-baseline reference not present at {nv_fasm_path}")
        print("       run build_simple_led_fasm.py first if you want the cross-check")

    return 0


if __name__ == "__main__":
    sys.exit(main())
