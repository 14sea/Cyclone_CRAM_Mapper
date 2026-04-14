# SPDX-License-Identifier: GPL-3.0-or-later
"""Unit tests for GCLK_PIN and LAB_CLK_SEL FASM directives.

Covers:
  1. Regex parsing of new directives
  2. Cell loaders read the expected JSON files and return tuple lists
  3. XOR-delta semantics: single application flips, double cancels
  4. Parity composition across overlapping LAB_CLK_SEL sets
  5. Error on missing pin / missing LAB JSON
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))

import fasm2rbf as f


def _flat_zero_rbf() -> bytes:
    """Synthetic 368,011-byte buffer: header FF, body 00, trailer FF."""
    HDR, BODY, TRL = 32, 210 * 1752, 59
    return b"\xff" * HDR + b"\x00" * BODY + b"\xff" * TRL


def test_parse_new_directives():
    text = "GCLK_PIN PIN_E1\nGCLK_PIN PIN_R8\nLAB_CLK_SEL X10Y4\nLAB_CLK_SEL X22Y10\n"
    out = f.parse_fasm(text)
    assert len(out) == 12, f"parse_fasm arity {len(out)} != 12"
    gclk_pins = out[10]
    lab_clk_sels = out[11]
    assert gclk_pins == ["E1", "R8"], gclk_pins
    assert lab_clk_sels == [(10, 4), (22, 10)], lab_clk_sels
    print("  test_parse_new_directives: OK")


def test_gclk_pin_loader():
    cells_e1 = f._load_gclk_pin_cells("E1")
    cells_r8 = f._load_gclk_pin_cells("R8")
    assert len(cells_e1) == 3, f"E1 = {len(cells_e1)} cells"
    assert len(cells_r8) == 5, f"R8 = {len(cells_r8)} cells"
    # Cross-pin overlap must be zero (per-pin one-hot model)
    assert not (set(cells_e1) & set(cells_r8)), "E1 ∩ R8 should be empty"
    print("  test_gclk_pin_loader: OK (E1=3, R8=5, ∩=0)")


def test_lab_clk_sel_loader():
    c104 = f._load_lab_clk_sel_cells(10, 4)
    c1016 = f._load_lab_clk_sel_cells(10, 16)
    c2210 = f._load_lab_clk_sel_cells(22, 10)
    assert len(c104) == 26, len(c104)
    assert len(c1016) == 53, len(c1016)
    assert len(c2210) == 45, len(c2210)
    # LAB(10,4) and LAB(22,10) share row-GCLK-tree cells (frame 55-95)
    shared = set(c104) & set(c2210)
    assert len(shared) > 0, "expected row-tree overlap between (10,4) and (22,10)"
    print(f"  test_lab_clk_sel_loader: OK "
          f"((10,4)=26, (10,16)=53, (22,10)=45, (10,4)∩(22,10)={len(shared)})")


def test_bitgen_gclk_pin_xor_single():
    base = _flat_zero_rbf()
    fasm = "GCLK_PIN PIN_E1\n"
    out = f.bitgen(fasm, base, patch_crc=False)
    cells = f._load_gclk_pin_cells("E1")
    for off, bp in cells:
        assert (out[off] >> bp) & 1 == 1, f"cell ({off},{bp}) not flipped"
    # outside the 3 cells, everything should still match base
    cells_set = set(cells)
    flipped_bytes = {off for off, _ in cells_set}
    for i, (a, b) in enumerate(zip(base, out)):
        if a != b:
            assert i in flipped_bytes, f"unexpected diff at {i}"
    print("  test_bitgen_gclk_pin_xor_single: OK")


def test_bitgen_gclk_pin_xor_double_cancels():
    base = _flat_zero_rbf()
    fasm = "GCLK_PIN PIN_E1\nGCLK_PIN PIN_E1\n"
    out = f.bitgen(fasm, base, patch_crc=False)
    assert out == base, "double GCLK_PIN PIN_E1 should cancel (XOR parity)"
    print("  test_bitgen_gclk_pin_xor_double_cancels: OK")


def test_bitgen_lab_clk_sel_overlap_cancels():
    """(10,4) and (22,10) share row-tree cells; XOR them → shared cells cancel."""
    base = _flat_zero_rbf()
    c104 = set(f._load_lab_clk_sel_cells(10, 4))
    c2210 = set(f._load_lab_clk_sel_cells(22, 10))
    shared = c104 & c2210
    xor_expected = c104 ^ c2210
    fasm = "LAB_CLK_SEL X10Y4\nLAB_CLK_SEL X22Y10\n"
    out = f.bitgen(fasm, base, patch_crc=False)
    for off, bp in shared:
        assert (out[off] >> bp) & 1 == 0, f"shared cell ({off},{bp}) should cancel"
    for off, bp in xor_expected:
        assert (out[off] >> bp) & 1 == 1, f"unique cell ({off},{bp}) should flip"
    print(f"  test_bitgen_lab_clk_sel_overlap_cancels: OK "
          f"({len(shared)} cancelled, {len(xor_expected)} flipped)")


def test_unknown_pin_raises():
    try:
        f._load_gclk_pin_cells("Z99")
    except f.FasmError as e:
        assert "no entry" in str(e)
        print("  test_unknown_pin_raises: OK")
        return
    raise AssertionError("expected FasmError for unknown pin")


def test_unmined_lab_raises():
    try:
        f._load_lab_clk_sel_cells(99, 99)
    except f.FasmError as e:
        assert "no mined data" in str(e)
        print("  test_unmined_lab_raises: OK")
        return
    raise AssertionError("expected FasmError for unmined LAB")


def main():
    tests = [
        test_parse_new_directives,
        test_gclk_pin_loader,
        test_lab_clk_sel_loader,
        test_bitgen_gclk_pin_xor_single,
        test_bitgen_gclk_pin_xor_double_cancels,
        test_bitgen_lab_clk_sel_overlap_cancels,
        test_unknown_pin_raises,
        test_unmined_lab_raises,
    ]
    for t in tests:
        # clear caches so each test sees a cold load
        f._GCLK_PIN_CACHE = None
        f._LAB_CLK_SEL_CACHE.clear()
        t()
    print(f"\n{len(tests)}/{len(tests)} tests OK")


if __name__ == "__main__":
    main()
