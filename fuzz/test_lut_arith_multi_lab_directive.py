# SPDX-License-Identifier: GPL-3.0-or-later
"""Unit tests for LUT_ARITH_MULTI_LAB FASM directive.

Width-parameterised directive that XOR-applies the multi-LAB carry-
chain activation blob for widths 17..32 from
results/arith_blockband_by_width.json (multi_lab["16+N"] for N=1..16).

Covers:
  1. Parser arity bump (20 → 21), default list is empty
  2. Single parse stores the requested width
  3. Double parse of same width stores [w, w] (XOR parity at apply)
  4. Parse rejects malformed WIDTH= forms
  5. Loader returns n_set+n_clear cells from the JSON for each width
  6. Loader rejects widths outside 17..32
  7. Bitgen single-emit flips exactly (n_set+n_clear) cells
  8. Bitgen double-emit same-width is a no-op
  9. Bitgen two different widths composes (XOR of union)
 10. All mined cells land in the block band (frames 1692-1738) or
     the LAB-col upper region the mining harness touches.  The
     primary invariant we assert is: no cells outside the CRAM
     body (i.e. no cells in the 32B preamble or 59B postamble).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))

import fasm2rbf as f


ARITH_JSON = ROOT / "results" / "arith_blockband_by_width.json"
PRE = 32
POST = 59
# RBF size = 32 (preamble) + 1752*210 (frames) + 59 (postamble) = 368011.


def _zero_base() -> bytes:
    sys.path.insert(0, str(ROOT / "fuzz"))
    from pure_zero_rbf import make_pure_zero_rbf
    return make_pure_zero_rbf()


def test_parse_arity_and_default_empty():
    out = f.parse_fasm("")
    assert len(out) == 25, f"parse_fasm arity {len(out)} != 25"
    assert out[20] == [], (
        f"lut_arith_multi_labs default should be empty list, got {out[20]!r}"
    )
    print("  test_parse_arity_and_default_empty: OK")


def test_parse_single_width():
    out = f.parse_fasm("LUT_ARITH_MULTI_LAB WIDTH=17\n")
    assert out[20] == [17], out[20]
    # Also try the whitespace-tolerant form
    out2 = f.parse_fasm("LUT_ARITH_MULTI_LAB WIDTH = 24\n")
    assert out2[20] == [24], out2[20]
    print("  test_parse_single_width: OK")


def test_parse_double_emit_stores_both():
    out = f.parse_fasm(
        "LUT_ARITH_MULTI_LAB WIDTH=17\n"
        "LUT_ARITH_MULTI_LAB WIDTH=17\n"
    )
    assert out[20] == [17, 17], out[20]
    print("  test_parse_double_emit_stores_both: OK")


def test_parse_rejects_malformed():
    bad_cases = [
        "LUT_ARITH_MULTI_LAB 17\n",       # missing WIDTH=
        "LUT_ARITH_MULTI_LAB WIDTH=\n",   # missing value
        "LUT_ARITH_MULTI_LAB WIDTH=-1\n", # negative
        "LUT_ARITH_MULTI_LAB WIDTH=abc\n",
    ]
    for text in bad_cases:
        try:
            f.parse_fasm(text)
        except f.FasmError:
            continue
        raise AssertionError(f"expected FasmError for {text!r}")
    print("  test_parse_rejects_malformed: OK")


def test_load_cells_matches_json():
    if not ARITH_JSON.exists():
        print("  test_load_cells_matches_json: SKIP (no JSON)")
        return
    f._ARITH_MULTI_LAB_CACHE = None
    data = json.loads(ARITH_JSON.read_text())
    ml = data["multi_lab"]
    for width in (17, 20, 24, 32):
        # Loader returns a (set_cells, clear_cells) 2-tuple since commit
        # b5cbe49 (visible_blink_W23): SET cells apply via XOR, CLEAR cells
        # via AND-clear (force 0), so the two are kept separate.  Assert
        # each list length against its JSON count, plus the combined total.
        set_cells, clear_cells = f._arith_multi_lab_cells(width)
        key = f"16+{width - 16}"
        assert len(set_cells) == ml[key]["n_set"], (
            f"width={width}: loader returned {len(set_cells)} SET cells, "
            f"JSON says n_set={ml[key]['n_set']}"
        )
        assert len(clear_cells) == ml[key]["n_clear"], (
            f"width={width}: loader returned {len(clear_cells)} CLEAR cells, "
            f"JSON says n_clear={ml[key]['n_clear']}"
        )
        expected = ml[key]["n_set"] + ml[key]["n_clear"]
        assert len(set_cells) + len(clear_cells) == expected, (
            f"width={width}: loader returned "
            f"{len(set_cells) + len(clear_cells)} total cells, "
            f"JSON says n_set+n_clear={expected}"
        )
    print("  test_load_cells_matches_json: OK")


def test_load_rejects_out_of_range():
    for width in (0, 1, 16, 33, 64):
        try:
            f._arith_multi_lab_cells(width)
        except f.FasmError:
            continue
        raise AssertionError(
            f"expected FasmError for width={width}"
        )
    print("  test_load_rejects_out_of_range: OK")


def test_bitgen_single_emit_flips_all_cells():
    if not ARITH_JSON.exists():
        print("  test_bitgen_single_emit_flips_all_cells: SKIP")
        return
    base = _zero_base()
    out = f.bitgen(
        "LUT_ARITH_MULTI_LAB WIDTH=17\n", base, patch_crc=False
    )
    # Since commit b5cbe49, SET cells apply via XOR (0->1 on a zero base)
    # and CLEAR cells via AND-clear (force 0).  On a pure-zero base the
    # CLEAR cells are already 0, so AND-clear is a no-op and they do NOT
    # flip.  The flipped count therefore equals len(set_cells).
    set_cells, clear_cells = f._arith_multi_lab_cells(17)
    set_flipped = sum(
        1 for off, bp in set_cells if ((out[off] ^ base[off]) >> bp) & 1
    )
    clear_flipped = sum(
        1 for off, bp in clear_cells if ((out[off] ^ base[off]) >> bp) & 1
    )
    assert set_flipped == len(set_cells), (
        f"expected {len(set_cells)} SET bit flips, got {set_flipped}"
    )
    assert clear_flipped == 0, (
        f"CLEAR cells AND-clear a zero base (no-op); expected 0 flips, "
        f"got {clear_flipped}"
    )
    # SET and CLEAR cells must be disjoint (no cell is both at a single
    # width); otherwise CLEAR's force-0 would silently override SET.
    all_cells = set_cells + clear_cells
    assert len(set(all_cells)) == len(all_cells), (
        "LUT_ARITH_MULTI_LAB SET/CLEAR cells are NOT disjoint at one "
        "width; CLEAR force-0 would silently override SET"
    )
    print(
        f"  test_bitgen_single_emit_flips_all_cells: OK "
        f"({set_flipped} SET flipped)"
    )


def test_bitgen_double_emit_is_noop():
    if not ARITH_JSON.exists():
        print("  test_bitgen_double_emit_is_noop: SKIP")
        return
    base = _zero_base()
    out = f.bitgen(
        "LUT_ARITH_MULTI_LAB WIDTH=17\n"
        "LUT_ARITH_MULTI_LAB WIDTH=17\n",
        base,
        patch_crc=False,
    )
    assert out == base, (
        f"double-emit should cancel; got "
        f"{sum(1 for i in range(len(out)) if out[i] != base[i])} "
        f"byte diffs"
    )
    print("  test_bitgen_double_emit_is_noop: OK")


def test_bitgen_two_widths_compose_as_xor_union():
    if not ARITH_JSON.exists():
        print("  test_bitgen_two_widths_compose_as_xor_union: SKIP")
        return
    base = _zero_base()
    # Reset cache between runs so loads are independent
    f._ARITH_MULTI_LAB_CACHE = None
    # Since commit b5cbe49 the apply path is NOT a pure XOR union: SET
    # cells XOR-toggle (odd-parity wins) while CLEAR cells force 0 and
    # OVERRIDE any SET at the same (off, bp).  Model the two phases:
    #   1. SET symmetric difference (odd XOR parity over SET-only cells)
    #   2. minus every cell that ANY width force-clears.
    # This captures the silicon-validated (365143, 2) case where a cell
    # is SET for W=17 but CLEAR for W=20 — the CLEAR force-0 wins.
    s17, c17 = f._arith_multi_lab_cells(17)
    s20, c20 = f._arith_multi_lab_cells(20)
    set_sym = set(s17) ^ set(s20)
    clear_all = set(c17) | set(c20)
    expected = set_sym - clear_all
    out = f.bitgen(
        "LUT_ARITH_MULTI_LAB WIDTH=17\n"
        "LUT_ARITH_MULTI_LAB WIDTH=20\n",
        base,
        patch_crc=False,
    )
    flipped = set()
    # Scan over the full SET ∪ CLEAR candidate set of both widths
    for off, bp in set(s17) | set(c17) | set(s20) | set(c20):
        if ((out[off] ^ base[off]) >> bp) & 1:
            flipped.add((off, bp))
    assert flipped == expected, (
        f"SET-XOR-minus-CLEAR mismatch: expected {len(expected)} flips, "
        f"got {len(flipped)}; diff="
        f"{len(flipped ^ expected)} cells"
    )
    print(
        f"  test_bitgen_two_widths_compose_as_xor_union: OK "
        f"({len(flipped)} flipped)"
    )


def test_all_cells_in_cram_body():
    """No cell should hit the 32B preamble or 59B postamble."""
    if not ARITH_JSON.exists():
        print("  test_all_cells_in_cram_body: SKIP")
        return
    rbf_len = 368011
    body_lo = PRE
    body_hi = rbf_len - POST  # exclusive
    for width in (17, 24, 32):
        set_cells, clear_cells = f._arith_multi_lab_cells(width)
        for off, bp in set_cells + clear_cells:
            assert body_lo <= off < body_hi, (
                f"width={width}: cell off={off} outside CRAM body "
                f"[{body_lo}, {body_hi})"
            )
            assert 0 <= bp <= 7, f"bp={bp} out of range"
    print("  test_all_cells_in_cram_body: OK")


def main() -> int:
    test_parse_arity_and_default_empty()
    test_parse_single_width()
    test_parse_double_emit_stores_both()
    test_parse_rejects_malformed()
    test_load_cells_matches_json()
    test_load_rejects_out_of_range()
    test_bitgen_single_emit_flips_all_cells()
    test_bitgen_double_emit_is_noop()
    test_bitgen_two_widths_compose_as_xor_union()
    test_all_cells_in_cram_body()
    print("ALL TESTS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
