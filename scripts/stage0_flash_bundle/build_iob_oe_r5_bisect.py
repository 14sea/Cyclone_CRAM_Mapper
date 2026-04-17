# SPDX-License-Identifier: GPL-3.0-or-later
"""IOB_OE PIN_R5 silicon bisection — layer 1 with DSPMULT prior.

Full IOB_OE PIN_R5 (40 cells) FAILed silicon on 2026-04-17 (stuck-on).
Removing just the DSPMULT-bisected leaky cell (363236, 2) didn't help
— additional leaky cells are in the R5 set.

Smart layer-1 partition using DSPMULT_GLOBAL_ON 22-cell CLEAN22 result
as a prior:

  * A = R5 cells that appear in DSPMULT_GLOBAL_ON 22-cell cleaned set
    (= silicon-safe proven 2026-04-17; not the leak source)
  * B = R5 cells NOT in the cleaned DSPMULT set
    (= the unexplored candidates)

Then B is the search space for further bisection.  Skips (363236, 2)
entirely since it's the DSPMULT-isolated leaky cell.

A typically holds ~8-9 cells, B ~30-31.  If B FAILs, next layer
splits B in half.  Standard bisection from there.
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
LEAKY_DSPMULT = (363236, 2)  # isolated 2026-04-17


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
    f._IOB_OE_CACHE = None
    f._DSPMULT_GLOBAL_ON_CACHE = None


def _build_half(label: str, cells: list[tuple[int, int]],
                pure: bytes, base_rbf: bytes) -> int:
    bit_lines = "\n".join(f"BIT {off} {bp}" for off, bp in cells) + "\n"
    fasm = SIMPLE_LED_PREFIX + bit_lines

    _reset_caches()
    out = f.bitgen(fasm, pure, patch_crc=True)
    out_path = HERE / f"simple_led_iob_oe_r5_{label}.rbf"
    out_path.write_bytes(out)
    print(f"\n[wrote] {out_path}  ({len(out)} bytes)  — {len(cells)} cells")

    diffs = [i for i in range(len(out)) if out[i] != base_rbf[i]]
    data_cells = [i for i in diffs
                  if CRAM_START <= i < CRAM_END
                  and (i - PRE) % FRAME < 208]
    if data_cells:
        fc = Counter((i - PRE) // FRAME for i in data_cells)
        print(f"  frame range: {min(fc)}..{max(fc)}  "
              f"data cells: {len(data_cells)}")

    sl_bits = _bit_diff_set(pure, base_rbf)
    di_bits = _bit_diff_set(base_rbf, out)
    overlap = sl_bits & di_bits
    fabric_ov = [(o,bp) for o,bp in overlap
                 if (o-PRE)%FRAME < 208
                 and not (SAFE_FRAME_LO <= (o-PRE)//FRAME <= SAFE_FRAME_HI)]
    print(f"  fabric overlap: {len(fabric_ov)}")
    return 0


def main() -> int:
    pure = make_pure_zero_rbf()
    base_path = (REPO / "scripts" / "iob_slice_mining" / "work"
                 / "simple_led_E16_to_G15" / "fasm_pure.rbf")
    base_rbf = base_path.read_bytes()

    _reset_caches()
    r5_cells = set(tuple(c) for c in f._load_iob_oe_cells("R5"))
    print(f"IOB_OE PIN_R5: {len(r5_cells)} cells "
          f"(loader already masks DSPMULT leaky? "
          f"{LEAKY_DSPMULT not in r5_cells})")

    _reset_caches()
    dspmult_clean = set(tuple(c) for c in f._load_dspmult_global_on_cells())
    print(f"DSPMULT_GLOBAL_ON silicon-clean: {len(dspmult_clean)} cells "
          f"(2026-04-17 CLEAN22 PASS)")

    # Partition R5 cells:
    #   A = R5 ∩ dspmult_clean (silicon-safe in combination per CLEAN22)
    #   B = R5 - dspmult_clean - {LEAKY} (the unexplored candidates)
    A = sorted(r5_cells & dspmult_clean)
    B = sorted((r5_cells - dspmult_clean) - {LEAKY_DSPMULT})
    print(f"\nR5 partition against DSPMULT CLEAN22 prior:")
    print(f"  A (proven-safe overlap): {len(A)} cells")
    print(f"  B (unexplored):          {len(B)} cells")
    print(f"  leaky-excluded:          {{{LEAKY_DSPMULT}}}")
    assert len(A) + len(B) + 1 == len(r5_cells), "partition leak"

    _build_half("A_shared_dspmult", A, pure, base_rbf)
    _build_half("B_r5_unique", B, pure, base_rbf)

    # Layer 2: split B 50/50 (HW 2026-04-17: A PASS, B FAIL -> leak in B).
    mid = len(B) // 2
    B0 = B[:mid]
    B1 = B[mid:]
    print(f"\nLayer 2: B({len(B)}) -> B0({len(B0)}) + B1({len(B1)})")
    _build_half("B0", B0, pure, base_rbf)
    _build_half("B1", B1, pure, base_rbf)

    # Layer 3: B0 PASS, B1 FAIL -> leak in B1 (frames 1706..1732).
    m1 = len(B1) // 2
    B10 = B1[:m1]
    B11 = B1[m1:]
    print(f"\nLayer 3: B1({len(B1)}) -> B10({len(B10)}) + B11({len(B11)})")
    _build_half("B10", B10, pure, base_rbf)
    _build_half("B11", B11, pure, base_rbf)

    # Layer 4: B10 PASS, B11 FAIL -> leak in B11 (frames 1719..1732, 8 cells).
    m11 = len(B11) // 2
    B110 = B11[:m11]
    B111 = B11[m11:]
    print(f"\nLayer 4: B11({len(B11)}) -> B110({len(B110)}) + B111({len(B111)})")
    _build_half("B110", B110, pure, base_rbf)
    _build_half("B111", B111, pure, base_rbf)

    # Layer 5: B110 PASS, B111 FAIL -> leak in B111 (frames 1726..1732, 4 cells).
    m111 = len(B111) // 2
    B1110 = B111[:m111]
    B1111 = B111[m111:]
    print(f"\nLayer 5: B111({len(B111)}) -> B1110({len(B1110)}) + B1111({len(B1111)})")
    _build_half("B1110", B1110, pure, base_rbf)
    _build_half("B1111", B1111, pure, base_rbf)

    # Layer 6: B1110 PASS, B1111 FAIL -> leak in B1111 (2 cells).
    S0 = [B1111[0]]
    S1 = [B1111[1]]
    print(f"\nLayer 6: B1111{B1111} -> S0{S0} + S1{S1}")
    _build_half("B1111_S0", S0, pure, base_rbf)
    _build_half("B1111_S1", S1, pure, base_rbf)

    # Verifier: R5 minus both isolated leaky cells (2026-04-17 HW):
    #   (363236, 2) frame=1729  (DSPMULT-shared, isolated 2026-04-17 Stage 0)
    #   (363672, 2) frame=1731  (R5-unique,     isolated 2026-04-17 Stage 1)
    R5_LEAKY = {LEAKY_DSPMULT, (363672, 2)}
    cleaned = sorted(r5_cells - R5_LEAKY)
    print(f"\nCLEAN38 verifier: R5({len(r5_cells)}) - {R5_LEAKY} = {len(cleaned)} cells")
    _build_half("CLEAN38", cleaned, pure, base_rbf)
    return 0


if __name__ == "__main__":
    sys.exit(main())
