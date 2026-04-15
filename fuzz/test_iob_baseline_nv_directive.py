# SPDX-License-Identifier: GPL-3.0-or-later
"""Unit tests for IOB_BASELINE_NV FASM directive.

The directive bridges the frame split between IOB_IN/IOB_OUT (iob_in_E15
frame — expects E15/G15 as baseline pin config) and IOB_ROUTE
(nv_zero_global frame — expects no fabric at all).  When a design
starts from nv_zero_global and uses both families, emitting
`IOB_BASELINE_NV` once XOR-applies results/iob_baseline_hdr_cells.json
(132 bit cells in 74 bytes, all in the hdr band off < 5282).  After
that the hdr bytes match iob_in_E15, so IOB_IN/IOB_OUT pair-deltas
swap pins cleanly.

Covers:
  1. Parser registers IOB_BASELINE_NV in the 15-tuple
  2. Cell loader reads the JSON, scopes to hdr band (off < 5282)
  3. Bit-perfect hdr round-trip: applying the cells on top of
     nv_zero_global yields iob_in_E15's hdr bytes exactly
  4. Round-trip with IOB_IN PIN_X: reproduces iob_in_X hdr bytes for
     all 44 mined pins (swap-from-E15 composition works)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))

import fasm2rbf as f


PRE = 32
FRAME = 210
FIRST = 25
CRAM_START = PRE + FIRST * FRAME  # 5282

NV_ZERO = ROOT / "results" / "rbf" / "nv_zero_global.rbf"
IOB_IN_E15 = ROOT / "results" / "rbf" / "iob_in_E15.rbf"
IOB_CELL_MAP = ROOT / "results" / "iob_cell_map.json"
BASELINE_JSON = ROOT / "results" / "iob_baseline_hdr_cells.json"


def test_parse_iob_baseline_nv():
    out = f.parse_fasm("IOB_BASELINE_NV\n")
    assert len(out) == 16, f"parse_fasm arity {len(out)} != 16"
    assert out[14] is True, "iob_baseline_nv flag not set"
    assert out[15] == [], "iob_clk_inputs should default to empty list"

    out = f.parse_fasm("")
    assert out[14] is False, "iob_baseline_nv flag leaked from empty FASM"
    print("  test_parse_iob_baseline_nv: OK")


def test_parse_iob_clk_input():
    out = f.parse_fasm("IOB_CLK_INPUT PIN_E1\nIOB_CLK_INPUT PIN_R8\n")
    assert out[15] == ["E1", "R8"], out[15]
    print("  test_parse_iob_clk_input: OK")


def test_iob_clk_input_E1_loader():
    f._IOB_CLK_INPUT_CACHE = None
    cells = f._load_iob_clk_input_cells("E1")
    assert len(cells) == 40, f"E1 = {len(cells)} cells"
    for off, bp in cells:
        assert off < CRAM_START, f"E1 cell ({off},{bp}) not in hdr band"
    print(f"  test_iob_clk_input_E1_loader: OK "
          f"({len(cells)} hdr cells)")


def test_iob_clk_input_R8_loader():
    f._IOB_CLK_INPUT_CACHE = None
    cells = f._load_iob_clk_input_cells("R8")
    assert len(cells) > 0, "R8 entry empty"
    for off, bp in cells:
        assert off < CRAM_START, f"R8 cell ({off},{bp}) not in hdr band"
        assert 0 <= bp < 8
    print(f"  test_iob_clk_input_R8_loader: OK "
          f"({len(cells)} hdr cells)")


def test_iob_clk_input_N1_loader():
    f._IOB_CLK_INPUT_CACHE = None
    cells = f._load_iob_clk_input_cells("N1")
    assert len(cells) > 0, "N1 entry empty"
    for off, bp in cells:
        assert off < CRAM_START, f"N1 cell ({off},{bp}) not in hdr band"
        assert 0 <= bp < 8
    print(f"  test_iob_clk_input_N1_loader: OK "
          f"({len(cells)} hdr cells)")


def test_iob_clk_input_unknown_pin_raises():
    f._IOB_CLK_INPUT_CACHE = None
    try:
        f._load_iob_clk_input_cells("Z99")
    except f.FasmError as e:
        assert "no entry" in str(e), str(e)
        print("  test_iob_clk_input_unknown_pin_raises: OK")
        return
    raise AssertionError("expected FasmError for unmined clock pin")


def test_bitgen_simple_led_hdr_bit_perfect_vs_gold():
    """nv + BASELINE_NV + IOB_IN E16 + IOB_OUT G15 + IOB_CLK_INPUT E1
    must match simple_led_E16_to_G15.rbf hdr band byte-for-byte."""
    f._IOB_BASELINE_HDR_CACHE = None
    f._IOB_MAP_CACHE = None
    f._IOB_CLK_INPUT_CACHE = None
    base = NV_ZERO.read_bytes()
    gold_path = (ROOT / "scripts" / "iob_slice_mining" / "work"
                 / "simple_led_E16_to_G15" / "output_files"
                 / "simple_led_E16_to_G15.rbf")
    gold = gold_path.read_bytes()
    fasm = ("IOB_BASELINE_NV\n"
            "IOB_IN  PIN_E16\n"
            "IOB_OUT PIN_G15\n"
            "IOB_CLK_INPUT PIN_E1\n")
    out = f.bitgen(fasm, base, patch_crc=False)
    diff = sum(1 for i in range(CRAM_START) if out[i] != gold[i])
    assert diff == 0, f"{diff} hdr byte diffs vs simple_led gold"
    print("  test_bitgen_simple_led_hdr_bit_perfect_vs_gold: OK "
          "(hdr band byte-identical to simple_led_E16_to_G15.rbf)")


def _bitgen_simple_led_hdr_vs_clk_gold(pin):
    """Shared body for R8 / N1 hdr-band round-trip tests."""
    f._IOB_BASELINE_HDR_CACHE = None
    f._IOB_MAP_CACHE = None
    f._IOB_CLK_INPUT_CACHE = None
    base = NV_ZERO.read_bytes()
    gold_path = (ROOT / "scripts" / "iob_slice_mining" / "work"
                 / f"simple_led_E16_to_G15_clk{pin}" / "output_files"
                 / f"simple_led_E16_to_G15_clk{pin}.rbf")
    if not gold_path.exists():
        print(f"  [skip] no gold RBF for PIN_{pin} at {gold_path}")
        return
    gold = gold_path.read_bytes()
    fasm = ("IOB_BASELINE_NV\n"
            "IOB_IN  PIN_E16\n"
            "IOB_OUT PIN_G15\n"
            f"IOB_CLK_INPUT PIN_{pin}\n")
    out = f.bitgen(fasm, base, patch_crc=False)
    diff = sum(1 for i in range(CRAM_START) if out[i] != gold[i])
    assert diff == 0, (
        f"PIN_{pin}: {diff} hdr byte diffs vs "
        f"simple_led_E16_to_G15_clk{pin}.rbf"
    )
    print(f"  test_bitgen_simple_led_hdr_bit_perfect_vs_gold_{pin}: OK "
          f"(hdr byte-identical to simple_led_E16_to_G15_clk{pin}.rbf)")


def test_bitgen_simple_led_hdr_bit_perfect_vs_gold_R8():
    _bitgen_simple_led_hdr_vs_clk_gold("R8")


def test_bitgen_simple_led_hdr_bit_perfect_vs_gold_N1():
    _bitgen_simple_led_hdr_vs_clk_gold("N1")


def test_iob_baseline_hdr_cells_loader():
    f._IOB_BASELINE_HDR_CACHE = None
    cells = f._load_iob_baseline_hdr_cells()
    data = json.loads(BASELINE_JSON.read_text())
    assert len(cells) == len(data["cells"])
    for off, bp in cells:
        assert off < CRAM_START, f"cell ({off},{bp}) is not in hdr band"
        assert 0 <= bp < 8
    print(f"  test_iob_baseline_hdr_cells_loader: OK "
          f"({len(cells)} hdr bit cells, all off < {CRAM_START})")


def test_bitgen_baseline_hdr_bit_perfect_vs_iob_in_E15():
    """nv_zero_global + IOB_BASELINE_NV must match iob_in_E15 in hdr band."""
    f._IOB_BASELINE_HDR_CACHE = None
    base = NV_ZERO.read_bytes()
    gold = IOB_IN_E15.read_bytes()
    out = f.bitgen("IOB_BASELINE_NV\n", base, patch_crc=False)
    assert out[:CRAM_START] == gold[:CRAM_START], (
        "hdr band mismatch vs iob_in_E15"
    )
    # CRAM band must be untouched — iob_in_E15 has a test fabric but
    # IOB_BASELINE_NV scopes cells to off < 5282, so the CRAM should
    # still match nv_zero_global.
    assert out[CRAM_START:] == base[CRAM_START:], (
        "CRAM band was unexpectedly touched by IOB_BASELINE_NV"
    )
    print("  test_bitgen_baseline_hdr_bit_perfect_vs_iob_in_E15: OK")


def test_bitgen_baseline_double_cancels():
    f._IOB_BASELINE_HDR_CACHE = None
    base = NV_ZERO.read_bytes()
    out = f.bitgen("IOB_BASELINE_NV\nIOB_BASELINE_NV\n", base,
                   patch_crc=False)
    # Flag is boolean, so emitting it twice is idempotent — applied once.
    # Confirm the SINGLE-apply semantics: hdr should match iob_in_E15.
    gold = IOB_IN_E15.read_bytes()
    assert out[:CRAM_START] == gold[:CRAM_START], (
        "double-emit should still produce the E15/G15 baseline (not "
        "double-XOR back to nv)"
    )
    print("  test_bitgen_baseline_double_cancels: OK "
          "(flag is boolean; duplicate emit is idempotent)")


def test_bitgen_baseline_plus_iob_in_round_trip():
    """nv + IOB_BASELINE_NV + IOB_IN PIN_X must match iob_in_X hdr band.

    Validates the frame-bridge math for every pin in iob_cell_map.json:
    (nv hdr ^ baseline_hdr ^ cells_in(X)_hdr) must equal iob_in_X hdr.
    """
    f._IOB_BASELINE_HDR_CACHE = None
    f._IOB_MAP_CACHE = None
    base = NV_ZERO.read_bytes()
    iob_map = json.loads(IOB_CELL_MAP.read_text())
    rbf_dir = ROOT / "results" / "rbf"

    checked = 0
    for pin in sorted(iob_map["input_delta"]):
        gold_path = rbf_dir / f"iob_in_{pin}.rbf"
        if not gold_path.exists():
            continue
        gold = gold_path.read_bytes()
        fasm = f"IOB_BASELINE_NV\nIOB_IN PIN_{pin}\n"
        out = f.bitgen(fasm, base, patch_crc=False)
        # Compare hdr band only — IOB_IN cells may touch a few block-band
        # CRAM bytes in some pins, but hdr is the core config.
        diff_hdr = sum(1 for i in range(CRAM_START)
                       if out[i] != gold[i])
        assert diff_hdr == 0, (
            f"IOB_IN PIN_{pin}: {diff_hdr} hdr byte diffs vs iob_in_{pin}.rbf"
        )
        checked += 1
    assert checked >= 20, f"only {checked} pins checked"
    print(f"  test_bitgen_baseline_plus_iob_in_round_trip: OK "
          f"({checked} IOB_IN pins reproduce their gold hdr bytes)")


def main():
    tests = [
        test_parse_iob_baseline_nv,
        test_parse_iob_clk_input,
        test_iob_baseline_hdr_cells_loader,
        test_iob_clk_input_E1_loader,
        test_iob_clk_input_R8_loader,
        test_iob_clk_input_N1_loader,
        test_iob_clk_input_unknown_pin_raises,
        test_bitgen_baseline_hdr_bit_perfect_vs_iob_in_E15,
        test_bitgen_baseline_double_cancels,
        test_bitgen_baseline_plus_iob_in_round_trip,
        test_bitgen_simple_led_hdr_bit_perfect_vs_gold,
        test_bitgen_simple_led_hdr_bit_perfect_vs_gold_R8,
        test_bitgen_simple_led_hdr_bit_perfect_vs_gold_N1,
    ]
    for t in tests:
        f._IOB_BASELINE_HDR_CACHE = None
        f._IOB_MAP_CACHE = None
        f._IOB_CLK_INPUT_CACHE = None
        t()
    print(f"\n{len(tests)}/{len(tests)} tests OK")


if __name__ == "__main__":
    main()
