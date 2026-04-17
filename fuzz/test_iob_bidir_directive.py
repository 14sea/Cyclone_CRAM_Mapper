# SPDX-License-Identifier: GPL-3.0-or-later
"""IOB_IN_BIDIR / IOB_OUT_BIDIR directive tests.

These directives emit `per_pin_input` / `per_pin_output` cells from
`results/iob_cell_map.json` — cells UNIQUE to that pin across the 23/24
pin sweep.  Unlike the legacy `IOB_IN` / `IOB_OUT` (which are XOR deltas
vs the iob_in_E15 / iob_out_G15 anchors), the BIDIR variants compose
safely atop a design that already has other IOBs active.  They are
intended for the Stage B-narrow `$tribuf` use case on NEORV32 sdram_dq
bidir pins, where a single pin needs IOB_IN + IOB_OUT + IOB_OE in one
build.  See `iob_in_out_r5_composition_falsified.md` for why.
"""
from __future__ import annotations

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import fasm2rbf as f
from pure_zero_rbf import make_pure_zero_rbf

REPO = os.path.dirname(HERE)


def _reset_caches():
    f._IOB_MAP_CACHE = None


def test_parse_accepts_bidir_suffix():
    """`IOB_IN_BIDIR PIN_R5` parses as role='IN_BIDIR' and the legacy
    `IOB_IN PIN_E16` still parses as role='IN'."""
    fasm = "IOB_IN_BIDIR PIN_R5\nIOB_OUT_BIDIR PIN_R5\nIOB_IN PIN_E16\nIOB_OUT PIN_G15\n"
    result = f.parse_fasm(fasm)
    iobs = result[8]  # 9th element is the `iobs` list
    assert iobs == [
        ("IN_BIDIR", "R5"),
        ("OUT_BIDIR", "R5"),
        ("IN", "E16"),
        ("OUT", "G15"),
    ], iobs
    print("  test_parse_accepts_bidir_suffix: OK")


def test_bidir_dispatches_to_per_pin_tables():
    """BIDIR roles read per_pin_input/per_pin_output, not input_delta/output_delta."""
    _reset_caches()
    iob_map = f._load_iob_map()
    # Non-BIDIR: input_delta[R5]
    legacy_in = f._iob_delta_cells("IN", "R5", iob_map)
    # BIDIR: per_pin_input[R5]
    bidir_in = f._iob_delta_cells("IN_BIDIR", "R5", iob_map)
    assert len(legacy_in) == len(iob_map["input_delta"]["R5"])
    assert len(bidir_in) == len(iob_map["per_pin_input"]["R5"])
    # BIDIR set should be strictly smaller (unique ⊂ delta for R5)
    assert len(bidir_in) < len(legacy_in), (len(bidir_in), len(legacy_in))
    print(f"  test_bidir_dispatches_to_per_pin_tables: OK "
          f"(legacy IN={len(legacy_in)}, bidir IN={len(bidir_in)})")


def test_bidir_falsified_mask_applied():
    """The OUT_R5 known-leak mask removes 2 fabric-band cells.

    Expected size: per_pin_output[R5] - 2 mask cells."""
    _reset_caches()
    iob_map = f._load_iob_map()
    raw = {tuple(c) for c in iob_map["per_pin_output"]["R5"]}
    masked = set(f._iob_delta_cells("OUT_BIDIR", "R5", iob_map))
    removed = raw - masked
    assert removed == {(84275, 3), (84868, 4)}, removed
    assert len(masked) == len(raw) - 2
    print(f"  test_bidir_falsified_mask_applied: OK "
          f"(raw={len(raw)}, masked={len(masked)}, removed=2)")


def test_bitgen_bidir_double_emit_cancels():
    """Emitting IOB_IN_BIDIR twice on the same pin should be a no-op (parity)."""
    pure = make_pure_zero_rbf()
    _reset_caches()
    once = f.bitgen("IOB_IN_BIDIR PIN_R5\n", pure, patch_crc=False)
    _reset_caches()
    twice = f.bitgen("IOB_IN_BIDIR PIN_R5\nIOB_IN_BIDIR PIN_R5\n",
                     pure, patch_crc=False)
    assert twice == pure, "double-emit should cancel under XOR parity"
    assert once != pure, "single-emit should flip cells"
    print("  test_bitgen_bidir_double_emit_cancels: OK")


def test_bitgen_bidir_r5_no_fabric_overlap_simple_led():
    """The bidir probe atop simple_led_pure has zero fabric/hdr/block overlap
    with simple_led_pure's active cells.

    This is the regression lock for the Stage B-narrow `$tribuf` path —
    if any bidir cell set starts to overlap the simple_led bridge or
    fabric, this test will trip before an HW flash attempt.
    """
    import pathlib
    PRE = 32
    FRAME = 210
    SAFE_LO, SAFE_HI = 1692, 1738
    pure = make_pure_zero_rbf()
    base_path = (pathlib.Path(REPO) / "scripts" / "iob_slice_mining"
                 / "work" / "simple_led_E16_to_G15" / "fasm_pure.rbf")
    if not base_path.exists():
        print("  test_bitgen_bidir_r5_no_fabric_overlap_simple_led: "
              "SKIP (simple_led baseline not built)")
        return
    base = base_path.read_bytes()
    fasm = (
        "NV_BASELINE_PACK\n"
        "IOB_BASELINE_NV\n"
        "IOB_IN  PIN_E16\n"
        "IOB_OUT PIN_G15\n"
        "IOB_CLK_INPUT PIN_E1\n"
        "IOB_ROUTE PIN_E16 -> X10Y4N0.dataa\n"
        "GCLK_PIN PIN_E1\n"
        "LAB_CLK_SEL X10Y4\n"
        "LAB_CLK_SEL_LE X10Y4N0\n"
        "IOB_IN_BIDIR  PIN_R5\n"
        "IOB_OUT_BIDIR PIN_R5\n"
        "IOB_OE        PIN_R5\n"
    )
    _reset_caches()
    f._IOB_BASELINE_HDR_CACHE = None
    f._IOB_ROUTE_CACHE = None
    f._GCLK_PIN_CACHE = None
    f._LAB_CLK_SEL_CACHE.clear()
    f._LAB_CLK_SEL_LE_CACHE = None
    f._IOB_OE_CACHE = None
    out = f.bitgen(fasm, pure, patch_crc=True)

    def bits(a, b):
        s = set()
        for o in range(len(a)):
            x = a[o] ^ b[o]
            if not x:
                continue
            for bp in range(8):
                if x & (1 << bp):
                    s.add((o, bp))
        return s

    sl = bits(pure, base)
    di = bits(base, out)
    ov = sl & di
    hdr = [x for x in ov if (x[0]-PRE) % FRAME < 208
           and (x[0]-PRE) // FRAME < 25]
    data = [x for x in ov if (x[0]-PRE) % FRAME < 208
            and 25 <= (x[0]-PRE) // FRAME < SAFE_LO]
    block = [x for x in ov if (x[0]-PRE) % FRAME < 208
             and SAFE_LO <= (x[0]-PRE) // FRAME <= SAFE_HI]
    assert len(hdr) == 0, f"hdr overlap should be 0, got {len(hdr)}"
    assert len(data) == 0, f"fabric overlap should be 0, got {len(data)}"
    assert len(block) == 0, f"block overlap should be 0, got {len(block)}"
    print(f"  test_bitgen_bidir_r5_no_fabric_overlap_simple_led: OK "
          f"(total overlap = {len(ov)}, all CRC)")


def main() -> int:
    tests = [
        test_parse_accepts_bidir_suffix,
        test_bidir_dispatches_to_per_pin_tables,
        test_bidir_falsified_mask_applied,
        test_bitgen_bidir_double_emit_cancels,
        test_bitgen_bidir_r5_no_fabric_overlap_simple_led,
    ]
    fails = 0
    for t in tests:
        try:
            t()
        except AssertionError as e:
            print(f"  {t.__name__}: FAIL  {e}")
            fails += 1
    total = len(tests)
    print(f"\n{total - fails}/{total} tests OK")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
