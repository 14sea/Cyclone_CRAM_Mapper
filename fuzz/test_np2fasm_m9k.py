# SPDX-License-Identifier: GPL-3.0-or-later
"""np2fasm M9K emission — CONTRACT + XFAIL stubs.

The M9K path through the open-source toolchain is not yet wired end
to end.  This file pins down:

  1. What the `_emit_m9k_init` helper in `synth/np2fasm.py` is
     expected to produce given a synthetic (mock) placed M9K cell
     (unit test — no synthesis required, passes today).
  2. That the full Yosys → nextpnr → np2fasm flow cannot yet place a
     tiny RAM on an M9K bel (xfail stub — will flip to a real test
     once the pipeline closes).

Run standalone: `python3 fuzz/test_np2fasm_m9k.py`.
"""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
SYNTH = ROOT / "synth"
sys.path.insert(0, str(SYNTH))
sys.path.insert(0, str(HERE))

import np2fasm as nf
from m9k_init_basis import M9K_INIT_ANCHORS


def test_parse_yosys_init_round_trip():
    """LSB-first word pack / unpack round-trip.  Uses a small config
    (width=4, depth=8) so the binary string is readable."""
    width, depth = 4, 8
    words = [0xA, 0x5, 0x1, 0xF, 0x0, 0x3, 0xC, 0x7]
    # Build a Yosys-style INIT string: MSB-first, word 0 at the end
    bits = ""
    for w in reversed(words):
        bits += f"{w:0{width}b}"
    parsed = nf._parse_yosys_init(bits, width, depth)
    assert parsed == words, f"round-trip: got {parsed}, want {words}"
    print("  test_parse_yosys_init_round_trip: OK")


def test_emit_m9k_init_synthetic_cell():
    """`_emit_m9k_init` on a hand-built mock cell emits a FASM line
    that matches the known INIT format and targets a calibrated bel."""
    # Pick a known-calibrated anchor so the emitted line could also be
    # consumed by fasm2rbf if a real synth path delivered this cell.
    site = ("X15_Y10_N0", 9, 512)
    assert site in M9K_INIT_ANCHORS, f"calibration gap: {site}"

    width, depth = 9, 512
    words = [i & ((1 << width) - 1) for i in range(depth)]
    # Yosys INIT: MSB-first, word 0 at the end.
    bits = "".join(f"{w:0{width}b}" for w in reversed(words))
    mock_cell = {
        "type": "EP4CE6_M9K",
        "attributes": {"NEXTPNR_BEL": "M9K_X15_Y10_N0"},
        "parameters": {
            "INIT": bits,
            "WIDTH_A": width,
            "DEPTH": depth,
        },
    }
    fasm_line, warning = nf._emit_m9k_init("u_ram", mock_cell)
    assert warning is None, f"unexpected warning: {warning!r}"
    assert fasm_line is not None, "no FASM line emitted"
    assert fasm_line.startswith(f"X15Y10N0.INIT_{width}x{depth} = 0x"), (
        f"unexpected prefix: {fasm_line[:60]!r}"
    )
    # The blob length must match the bit-count / 4 rounding.
    _, _, blob = fasm_line.partition("0x")
    expected_chars = (width * depth + 3) // 4
    assert len(blob) == expected_chars, (
        f"blob length {len(blob)} != expected {expected_chars}"
    )
    print("  test_emit_m9k_init_synthetic_cell: OK")


def test_emit_m9k_init_rejects_non_m9k_bel():
    """A cell placed on a non-M9K bel should not silently emit a line."""
    mock_cell = {
        "type": "EP4CE6_M9K",
        "attributes": {"NEXTPNR_BEL": "SLICE_X3_Y4_N0"},
        "parameters": {"INIT": "", "WIDTH_A": 9, "DEPTH": 512},
    }
    fasm_line, warning = nf._emit_m9k_init("u_ram", mock_cell)
    assert fasm_line is None, f"expected no FASM, got {fasm_line!r}"
    assert warning is not None and "not an M9K" in warning, warning
    print("  test_emit_m9k_init_rejects_non_m9k_bel: OK")


def test_emit_m9k_init_convert_integration_xfail():
    """End-to-end: a routed JSON containing a placed EP4CE6_M9K cell
    should result in `np2fasm.convert()` emitting an INIT line.

    XFAIL today because:
      - `synth/m9k.lib` is the only M9K-aware piece that reaches Yosys
      - techmap rule for `$__M9K_SP_` → `EP4CE6_M9K` exists but is
        gated behind `M9K_TECHMAP` ifdef
      - nextpnr-generic chipdb has M9K bels but no M9K wire pips, so
        even if the techmap fired the placer could not route the RAM

    When the pipeline closes, flip the `xfail` guard below to assert
    the INIT line is present in `fasm`.
    """
    # Synthetic routed-JSON fragment with a single placed M9K cell.
    fake_json = {
        "modules": {
            "top": {
                "cells": {
                    "u_ram": {
                        "type": "EP4CE6_M9K",
                        "attributes": {"NEXTPNR_BEL": "M9K_X15_Y10_N0"},
                        "parameters": {
                            "INIT": "0" * (9 * 512),
                            "WIDTH_A": 9, "DEPTH": 512,
                        },
                        "connections": {},
                    },
                },
                "netnames": {},
            }
        }
    }
    fasm, warnings = nf.convert(fake_json)
    # Today: convert() ignores EP4CE6_M9K cells entirely.  This
    # assertion documents the current gap.  Flip to `assert any(...)`
    # once convert() calls _emit_m9k_init.
    emits_m9k = any(".INIT_" in line for line in fasm)
    if emits_m9k:
        raise AssertionError(
            "XFAIL EXPECTED TO FAIL, but convert() now emits M9K INIT — "
            "flip this test to a positive assertion and remove the "
            "xfail comment."
        )
    print("  test_emit_m9k_init_convert_integration_xfail: "
          "XFAIL OK (convert() does not yet emit M9K INIT)")


def main():
    tests = [
        test_parse_yosys_init_round_trip,
        test_emit_m9k_init_synthetic_cell,
        test_emit_m9k_init_rejects_non_m9k_bel,
        test_emit_m9k_init_convert_integration_xfail,
    ]
    for t in tests:
        t()
    print(f"\n{len(tests)}/{len(tests)} tests OK")


if __name__ == "__main__":
    main()
