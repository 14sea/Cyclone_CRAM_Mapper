#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Track B1 regression: IOB_ROUTE at X4Y4N0 must reproduce Quartus golds
byte-identically when combined with bypass LUT + OUTROUTE_G15.

This pins the 2026-05-21 bitgen reorder (iob_routes moved from pre-all_luts
to post-all_luts) so that:

  * OUTROUTE_G15 X4Y4N0 emits at LI-MUX-aliased cells (0x9354 etc., the
    predict_sram(0xFFFF) coords at X4Y4N0 per `p5d_per_lab_li_filter_2026
    _05_21` audit footnote)
  * LUT Phase 1 unconditionally clears those TT-coord cells
  * IOB_ROUTE then XOR-flips them to the gold value

If anyone moves iob_routes back to pre-all_luts (or breaks the XOR
composition), this regression fails loudly.

The golds are Quartus Lite 21.1 builds under
``scripts/iob_slice_mining/work/`` (cached by ``mine_padnv_x4y4n0.py``).

Run: ``python3 fuzz/test_iob_route_x4y4_reorder.py``
"""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))

import fasm2rbf as f  # noqa: E402


NV_ZERO = ROOT / "results" / "rbf" / "nv_zero_global.rbf"
GOLD_E16_SINGLE = (
    ROOT / "scripts" / "iob_slice_mining" / "work"
    / "padnv_single_E16_X4Y4N0" / "output_files" / "single_E16_X4Y4N0.rbf"
)
GOLD_AND_TWO_PIN = (
    ROOT / "scripts" / "iob_slice_mining" / "work"
    / "padnv_two_pin_X4Y4N0" / "output_files" / "two_pin_X4Y4N0.rbf"
)


def _reset():
    f._IOB_BASELINE_HDR_CACHE = None
    f._IOB_MAP_CACHE = None
    f._IOB_ROUTE_CACHE = None
    f._IOB_ROUTE_NODEDUP_KEYS = None
    f._IOB_ROUTE_LEGACY_CACHE = None
    f._GCLK_PIN_CACHE = None
    f._LAB_CLK_SEL_CACHE.clear()
    f._LAB_CLK_SEL_LE_CACHE = None
    f._IOB_CLK_INPUT_CACHE = None
    f._IOB_PAD_NV_CACHE = None
    f._OUTROUTE_SIGCACHE = None


def _bitgen_with_pragmas(fasm_text: str, base: bytes) -> bytes:
    """Mirror the canonical direct-bitgen calling convention: parse pragmas
    from the FASM text and forward as kwargs.  See
    `gamma_iob_x4y4_padnv_mining_2026_05_21` memo for the latent-bug context.
    """
    pragmas = f.parse_pragmas(fasm_text)
    return f.bitgen(fasm_text, base, patch_crc=True, **pragmas)


def t_single_pin_bypass_byte_identical():
    """Single-pin E16→X4Y4N0.dataa passthrough (mask=0xAAAA = canon_a
    bypass) must rebuild byte-identical to the Quartus gold via the new
    padnv-bucket sigcache entry."""
    if not GOLD_E16_SINGLE.exists():
        print(f"  [skip] gold missing: {GOLD_E16_SINGLE}")
        return
    base = NV_ZERO.read_bytes()
    gold = GOLD_E16_SINGLE.read_bytes()
    fasm = (
        "# fasm2rbf: bypass_aware=1\n"
        "IOB_ROUTE PIN_E16 -> X4Y4N0.dataa\n"
        "IOB_PAD_NV\n"
        "IOB_CLK_INPUT PIN_E1\n"
        "OUTROUTE_G15 X4Y4N0\n"
        "X4Y4N0.LUT = 0xAAAA\n"
        "GCLK_PIN PIN_E1\n"
        "LAB_CLK_SEL X4Y4\n"
        "LAB_CLK_SEL_LE X4Y4N0\n"
    )
    _reset()
    out = _bitgen_with_pragmas(fasm, base)
    bydiff = sum(1 for i in range(len(out)) if out[i] != gold[i])
    assert bydiff == 0, (
        f"single-pin E16->X4Y4N0.dataa bypass: {bydiff} byte diffs vs Quartus "
        f"gold {GOLD_E16_SINGLE.name}.  Likely a regression in the bitgen "
        f"iob_routes reorder (Track B1, 2026-05-21) — verify "
        f"`if iob_routes:` block still sits AFTER `if all_luts:` and the "
        f"post-loop canon-2input apply."
    )
    print(f"  t_single_pin_bypass_byte_identical: OK (0 diffs vs "
          f"{GOLD_E16_SINGLE.name})")


def t_two_pin_canon_2input_byte_identical():
    """Two-pin AND (E16→dataa + M16→datab, mask=0x8888 = canon_2input 'a&b')
    must rebuild byte-identical via the new padnv-bucket sigcache entries +
    canon_2input_aware path."""
    if not GOLD_AND_TWO_PIN.exists():
        print(f"  [skip] gold missing: {GOLD_AND_TWO_PIN}")
        return
    base = NV_ZERO.read_bytes()
    gold = GOLD_AND_TWO_PIN.read_bytes()
    fasm = (
        "# fasm2rbf: canon_2input_aware=1\n"
        "IOB_ROUTE PIN_E16 -> X4Y4N0.dataa\n"
        "IOB_ROUTE PIN_M16 -> X4Y4N0.datab\n"
        "IOB_PAD_NV\n"
        "IOB_CLK_INPUT PIN_E1\n"
        "OUTROUTE_G15 X4Y4N0\n"
        "X4Y4N0.LUT = 0x8888\n"
        "GCLK_PIN PIN_E1\n"
        "LAB_CLK_SEL X4Y4\n"
        "LAB_CLK_SEL_LE X4Y4N0\n"
    )
    _reset()
    out = _bitgen_with_pragmas(fasm, base)
    bydiff = sum(1 for i in range(len(out)) if out[i] != gold[i])
    assert bydiff == 0, (
        f"two-pin E16+M16 AND canon_2input: {bydiff} byte diffs vs Quartus "
        f"gold {GOLD_AND_TWO_PIN.name}."
    )
    print(f"  t_two_pin_canon_2input_byte_identical: OK (0 diffs vs "
          f"{GOLD_AND_TWO_PIN.name})")


def t_iob_route_position_in_bitgen():
    """Structural test: `if iob_routes:` must appear AFTER `if all_luts:` in
    bitgen — encodes the Track B1 reorder so a future blind rearrange that
    moves iob_routes back to pre-all_luts will fail loudly.

    Reads fasm2rbf.py source and verifies the relative line order.
    """
    src = (ROOT / "fuzz" / "fasm2rbf.py").read_text().splitlines()
    in_bitgen = False
    line_all_luts = None
    line_iob_routes = None
    for i, line in enumerate(src, 1):
        if line.startswith("def bitgen("):
            in_bitgen = True
            continue
        if in_bitgen and line.startswith("def ") and not line.lstrip().startswith("def "):
            # next top-level def — end of bitgen
            break
        if in_bitgen and "    if all_luts:" in line and line_all_luts is None:
            line_all_luts = i
        if in_bitgen and "    if iob_routes:" in line and line_iob_routes is None:
            line_iob_routes = i
    assert line_all_luts is not None, "couldn't find `if all_luts:` in bitgen"
    assert line_iob_routes is not None, "couldn't find `if iob_routes:` in bitgen"
    assert line_iob_routes > line_all_luts, (
        f"`if iob_routes:` (line {line_iob_routes}) must come AFTER "
        f"`if all_luts:` (line {line_all_luts}) per Track B1 reorder "
        f"(2026-05-21).  Moving iob_routes back to pre-all_luts re-introduces "
        f"the OUTROUTE_G15 × IOB_ROUTE XOR-cancel bug at LI-aliased cells."
    )
    print(f"  t_iob_route_position_in_bitgen: OK (iob_routes at line "
          f"{line_iob_routes}, after all_luts at line {line_all_luts})")


def main():
    tests = [
        t_single_pin_bypass_byte_identical,
        t_two_pin_canon_2input_byte_identical,
        t_iob_route_position_in_bitgen,
    ]
    n_pass = 0
    for tt in tests:
        try:
            tt()
            n_pass += 1
        except AssertionError as e:
            print(f"  FAIL {tt.__name__}: {e}")
    print(f"\n{n_pass}/{len(tests)} Track B1 reorder regression tests OK")
    return 0 if n_pass == len(tests) else 1


if __name__ == "__main__":
    sys.exit(main())
