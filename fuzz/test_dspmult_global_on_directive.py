# SPDX-License-Identifier: GPL-3.0-or-later
"""Unit tests for DSPMULT_GLOBAL_ON FASM directive.

Boolean directive that XOR-applies the silicon-clean 22-cell subset
of the 23-cell intersection across all 42 X=20 mult sites (re-mined
2026-04-16 under specimen factory; bisected on silicon 2026-04-17 —
one cell off=363236 bp=2 frame=1729 is silicon-falsified and masked
out by the loader; see dspmult_bisection_silicon_isolated).

Covers:
  1. Parser registers DSPMULT_GLOBAL_ON as bool
  2. Empty FASM defaults flag to False
  3. Cell loader returns 22 cells, all in block band (frames 1692-1738)
     (= 23 mined - 1 silicon-falsified)
  4. Bitgen single-emit XORs the cells into the working RBF
  5. Double-emit cancels (XOR parity at parse time)
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
BLOCK_LO, BLOCK_HI = 1692, 1738
ANALYZE_JSON = ROOT / "results" / "dspmult_persite_analyze.json"
PURE_ZERO_RBF = ROOT / "fuzz" / "pure_zero_rbf.py"  # for make_pure_zero_rbf


def _zero_base() -> bytes:
    """Get a 368011-byte zero-CRAM RBF for bitgen testing."""
    sys.path.insert(0, str(ROOT / "fuzz"))
    from pure_zero_rbf import make_pure_zero_rbf
    return make_pure_zero_rbf()


def test_parse_arity_and_default_false():
    out = f.parse_fasm("")
    assert len(out) == 23, f"parse_fasm arity {len(out)} != 23"
    assert out[18] is False, "dspmult_global_on default should be False"
    print("  test_parse_arity_and_default_false: OK")


def test_parse_single_emit_true():
    out = f.parse_fasm("DSPMULT_GLOBAL_ON\n")
    assert out[18] is True, "single DSPMULT_GLOBAL_ON should set flag"
    print("  test_parse_single_emit_true: OK")


def test_parse_double_emit_cancels():
    out = f.parse_fasm("DSPMULT_GLOBAL_ON\nDSPMULT_GLOBAL_ON\n")
    assert out[18] is False, "double DSPMULT_GLOBAL_ON should cancel via parity"
    print("  test_parse_double_emit_cancels: OK")


def test_load_cells_in_block_band():
    f._DSPMULT_GLOBAL_ON_CACHE = None  # force reload
    cells = f._load_dspmult_global_on_cells()
    data = json.loads(ANALYZE_JSON.read_text())
    # Loader masks out silicon-falsified cells; JSON count is the raw
    # mined intersection, loader count = mined - |SILICON_FALSIFIED|.
    expected = data["block_band"]["universal_count"] - 1  # 2026-04-17
    assert len(cells) == expected, (
        f"loader returned {len(cells)} cells, expected {expected} "
        f"(mined={data['block_band']['universal_count']}, "
        f"silicon-falsified=1)"
    )
    # Confirm the leaky cell is not in the emitted set.
    assert (363236, 2) not in cells, (
        "silicon-falsified cell (363236, 2) must be masked out"
    )
    for off, bp in cells:
        fr = (off - PRE) // FRAME
        assert BLOCK_LO <= fr <= BLOCK_HI, (
            f"DSPMULT_GLOBAL_ON cell off={off} bp={bp} in frame {fr} — "
            f"expected block band {BLOCK_LO}..{BLOCK_HI}"
        )
    print(f"  test_load_cells_in_block_band: OK ({len(cells)} cells, "
          f"leaky cell masked)")


def test_bitgen_single_emit_flips_cells():
    if not ANALYZE_JSON.exists():
        print("  test_bitgen_single_emit_flips_cells: SKIP (no analyzer JSON)")
        return
    base = _zero_base()
    out = f.bitgen("DSPMULT_GLOBAL_ON\n", base, patch_crc=False)
    cells = f._load_dspmult_global_on_cells()
    diffs = 0
    for off, bp in cells:
        if (out[off] ^ base[off]) & (1 << bp):
            diffs += 1
    assert diffs == len(cells), (
        f"expected {len(cells)} bit flips, got {diffs}"
    )
    print(f"  test_bitgen_single_emit_flips_cells: OK ({diffs} flipped)")


def test_bitgen_double_emit_is_noop():
    if not ANALYZE_JSON.exists():
        print("  test_bitgen_double_emit_is_noop: SKIP (no analyzer JSON)")
        return
    base = _zero_base()
    out = f.bitgen("DSPMULT_GLOBAL_ON\nDSPMULT_GLOBAL_ON\n", base, patch_crc=False)
    assert out == base, (
        f"double emit should be no-op; got "
        f"{sum(1 for i in range(len(out)) if out[i] != base[i])} byte diffs"
    )
    print("  test_bitgen_double_emit_is_noop: OK")


def main() -> int:
    test_parse_arity_and_default_false()
    test_parse_single_emit_true()
    test_parse_double_emit_cancels()
    test_load_cells_in_block_band()
    test_bitgen_single_emit_flips_cells()
    test_bitgen_double_emit_is_noop()
    print("ALL TESTS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
