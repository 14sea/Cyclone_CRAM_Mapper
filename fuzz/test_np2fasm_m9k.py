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


def test_emit_m9k_init_convert_integration():
    """End-to-end: a routed JSON containing a placed EP4CE6_M9K cell
    is consumed by `np2fasm.convert()` and produces an INIT FASM line.

    Upstream Yosys / nextpnr pipeline for M9K is still blocked (chipdb
    has no M9K wire pips), but convert() now wires _emit_m9k_init into
    the cell dispatch so hand-built or patched JSON can round-trip.
    """
    # Synthetic routed-JSON fragment with a single placed M9K cell
    # (non-zero INIT so the emitted blob is distinguishable).
    width, depth = 9, 512
    words = [(i * 3 + 1) & ((1 << width) - 1) for i in range(depth)]
    bits = "".join(f"{w:0{width}b}" for w in reversed(words))
    fake_json = {
        "modules": {
            "top": {
                "cells": {
                    "u_ram": {
                        "type": "EP4CE6_M9K",
                        "attributes": {"NEXTPNR_BEL": "M9K_X15_Y10_N0"},
                        "parameters": {
                            "INIT": bits,
                            "WIDTH_A": width, "DEPTH": depth,
                        },
                        "connections": {},
                    },
                },
                "netnames": {},
            }
        }
    }
    fasm, warnings = nf.convert(fake_json)
    init_lines = [l for l in fasm if ".INIT_" in l]
    assert len(init_lines) == 1, (
        f"expected exactly 1 INIT line, got {len(init_lines)}: {init_lines}"
    )
    assert init_lines[0].startswith(f"X15Y10N0.INIT_{width}x{depth} = 0x"), (
        f"unexpected prefix: {init_lines[0][:60]!r}"
    )
    print("  test_emit_m9k_init_convert_integration: OK")


def test_emit_m9k_init_yosys_binary_params():
    """WIDTH_A and DEPTH from Yosys come as little-endian binary strings
    (e.g. '00000000000000000000000000010010' for 18). _emit_m9k_init
    must parse them — regressed once when convert() saw post-techmap
    JSON and silently dropped INITs because int('...10010') = 10010.
    """
    width, depth = 18, 512
    words = [(i & 1) for i in range(depth)]  # alternating 0/1
    bits = "".join(f"{w:0{width}b}" for w in reversed(words))
    width_bin = f"{width:032b}"
    depth_bin = f"{depth:032b}"
    mock_cell = {
        "type": "EP4CE6_M9K",
        "attributes": {"NEXTPNR_BEL": "M9K_X15_Y10_N0"},
        "parameters": {
            "INIT": bits,
            "WIDTH_A": width_bin,
            "DEPTH": depth_bin,
        },
    }
    fasm_line, warning = nf._emit_m9k_init("u_ram", mock_cell)
    assert warning is None, f"unexpected warning: {warning!r}"
    assert fasm_line is not None, "no FASM line emitted"
    assert fasm_line.startswith(f"X15Y10N0.INIT_{width}x{depth} = 0x"), (
        f"binary params should parse as ints; got {fasm_line[:60]!r}"
    )
    print("  test_emit_m9k_init_yosys_binary_params: OK")


def test_parse_yosys_init_handles_x_dontcares():
    """libmap-split cells leave unused bit slots as 'x' in the INIT
    string. _parse_yosys_init must treat them as 0 (functionally safe)
    rather than raising ValueError on int(s, 2)."""
    width, depth = 18, 4
    # Yosys INIT is MSB-first within each word: char 0 = bit (width-1),
    # char (width-1) = bit 0. Set bit 9 = '1' (char index width-1-9 = 8)
    # and bit 0 = '0' (char index width-1 = 17). All other slots = 'x'.
    one_word = "x" * 8 + "1" + "x" * 8 + "0"
    assert len(one_word) == width
    # Words are concatenated MSB-first across `depth`, with word 0 last.
    bits = one_word * depth
    parsed = nf._parse_yosys_init(bits, width, depth)
    assert len(parsed) == depth
    for i, w in enumerate(parsed):
        assert (w & 1) == 0, f"word {i}: bit 0 = {w & 1}"
        assert (w >> 9) & 1 == 1, f"word {i}: bit 9 = {(w >> 9) & 1}"
        assert w == (1 << 9), f"word {i}: stray bits in {w:#020b}"
    print("  test_parse_yosys_init_handles_x_dontcares: OK")


def test_convert_skips_ep4ce6_m9k_blackbox_module():
    """When the post-techmap JSON contains both the design top and the
    EP4CE6_M9K blackbox module declaration, convert() must skip the
    blackbox and pick the top — otherwise it iterates an empty cell
    dict and silently emits zero INIT lines (regressed once when the
    BLACKBOX_MODULES set lacked EP4CE6_M9K)."""
    width, depth = 9, 512
    words = [(i + 1) & ((1 << width) - 1) for i in range(depth)]
    bits = "".join(f"{w:0{width}b}" for w in reversed(words))
    fake_json = {
        "modules": {
            # Blackbox first — it must NOT be selected as design top.
            "EP4CE6_M9K": {"cells": {}, "netnames": {}},
            "top": {
                "cells": {
                    "u_ram": {
                        "type": "EP4CE6_M9K",
                        "attributes": {"NEXTPNR_BEL": "M9K_X15_Y10_N0"},
                        "parameters": {
                            "INIT": bits,
                            "WIDTH_A": width, "DEPTH": depth,
                        },
                        "connections": {},
                    },
                },
                "netnames": {},
            },
        }
    }
    fasm, warnings = nf.convert(fake_json)
    init_lines = [l for l in fasm if ".INIT_" in l]
    assert len(init_lines) == 1, (
        f"EP4CE6_M9K module should be skipped; got {len(init_lines)} "
        f"INIT lines (warnings: {warnings})"
    )
    print("  test_convert_skips_ep4ce6_m9k_blackbox_module: OK")


def test_emit_m9k_mode_synthetic_cell():
    """`_emit_m9k_mode` produces the per-site enable directive that
    accompanies INIT.  Without this line the silicon block stays in
    its idle configuration and never reads back the user pattern.

    HW flash 2026-04-17: the helper emits the explicit
    `_inferred_goldintersect` suffix — the Stage C.1 intersection of
    the inferred-RAM mining template with the Quartus smoke gold
    (38 cells at w=9, site-invariant) PASSed silicon.  convert()
    now emits the line whenever a w=9 M9K cell is placed.
    """
    width, depth = 9, 512
    mock_cell = {
        "type": "EP4CE6_M9K",
        "attributes": {"NEXTPNR_BEL": "M9K_X15_Y10_N0"},
        "parameters": {"INIT": "0", "WIDTH_A": width, "DEPTH": depth},
    }
    line, warn = nf._emit_m9k_mode("u_ram", mock_cell)
    assert warn is None, f"unexpected warning: {warn!r}"
    assert line == (
        f"X15Y10N0.M9K_MODE_{width}x{depth}_inferred_goldintersect"
    ), line
    print("  test_emit_m9k_mode_synthetic_cell: OK")


def test_emit_m9k_mode_w18_emits_goldintersect():
    """w=18 sites ungated 2026-04-24 after re-mining under a collision-
    free WIDE_PIN_MAP (F16 → P2 for DOUT14).  Helper now emits the
    `inferred_goldintersect` suffix identically to w=9."""
    mock_cell = {
        "type": "EP4CE6_M9K",
        "attributes": {"NEXTPNR_BEL": "M9K_X15_Y10_N0"},
        "parameters": {"INIT": "0", "WIDTH_A": 18, "DEPTH": 512},
    }
    line, warn = nf._emit_m9k_mode("u_ram", mock_cell)
    assert warn is None, f"unexpected warning: {warn!r}"
    assert line == "X15Y10N0.M9K_MODE_18x512_inferred_goldintersect", line
    print("  test_emit_m9k_mode_w18_emits_goldintersect: OK")


def test_emit_m9k_mode_rejects_non_m9k_bel():
    mock_cell = {
        "type": "EP4CE6_M9K",
        "attributes": {"NEXTPNR_BEL": "SLICE_X3_Y4_N0"},
        "parameters": {"WIDTH_A": 9, "DEPTH": 512},
    }
    line, warn = nf._emit_m9k_mode("u_ram", mock_cell)
    assert line is None, f"expected no FASM, got {line!r}"
    print("  test_emit_m9k_mode_rejects_non_m9k_bel: OK")


def test_convert_emits_m9k_mode_goldintersect():
    """convert() now emits one M9K_MODE_{w}x{d}_inferred_goldintersect
    line per placed w=9 EP4CE6_M9K cell (HW-validated 2026-04-17).
    w=18 sites warn instead — they lack a goldintersect bucket until
    the mining harness covers them."""
    width, depth = 9, 512
    words = [(i + 1) & ((1 << width) - 1) for i in range(depth)]
    bits = "".join(f"{w:0{width}b}" for w in reversed(words))
    fake_json = {
        "modules": {
            "top": {
                "cells": {
                    "u_ram": {
                        "type": "EP4CE6_M9K",
                        "attributes": {"NEXTPNR_BEL": "M9K_X15_Y10_N0"},
                        "parameters": {
                            "INIT": bits,
                            "WIDTH_A": width, "DEPTH": depth,
                        },
                        "connections": {},
                    },
                },
                "netnames": {},
            }
        }
    }
    fasm, warnings = nf.convert(fake_json)
    mode_lines = [l for l in fasm if ".M9K_MODE_" in l]
    init_lines = [l for l in fasm if ".INIT_" in l]
    assert mode_lines == [
        f"X15Y10N0.M9K_MODE_{width}x{depth}_inferred_goldintersect"
    ], f"expected one goldintersect MODE line; got: {mode_lines}"
    assert len(init_lines) == 1, f"expected 1 INIT line, got {init_lines}"
    print("  test_convert_emits_m9k_mode_goldintersect: OK")


def test_emit_m9k_init_convert_skips_unplaced():
    """An EP4CE6_M9K cell without a valid M9K_* bel should warn, not emit."""
    fake_json = {
        "modules": {
            "top": {
                "cells": {
                    "u_ram": {
                        "type": "EP4CE6_M9K",
                        # SLICE bel — not an M9K site.
                        "attributes": {"NEXTPNR_BEL": "SLICE_X3_Y4_N0"},
                        "parameters": {
                            "INIT": "", "WIDTH_A": 9, "DEPTH": 512,
                            "INIT": "0" * (9 * 512),
                        },
                        "connections": {},
                    },
                },
                "netnames": {},
            }
        }
    }
    fasm, warnings = nf.convert(fake_json)
    init_lines = [l for l in fasm if ".INIT_" in l]
    # Cell placed on SLICE bel — parse_bel returns ('SLICE', 3, 4, 0), so
    # the dispatch hits the SLICE branch rather than M9K.  That branch
    # treats a param-less cell as a pure LUT with 0-init and emits
    # nothing (no INIT key present in a SLICE-shaped cell).  Main
    # assertion: no INIT line makes it through.
    assert init_lines == [], f"unexpected INIT emitted: {init_lines}"
    print("  test_emit_m9k_init_convert_skips_unplaced: OK")


def main():
    tests = [
        test_parse_yosys_init_round_trip,
        test_emit_m9k_init_synthetic_cell,
        test_emit_m9k_init_rejects_non_m9k_bel,
        test_emit_m9k_init_convert_integration,
        test_emit_m9k_init_yosys_binary_params,
        test_parse_yosys_init_handles_x_dontcares,
        test_convert_skips_ep4ce6_m9k_blackbox_module,
        test_emit_m9k_init_convert_skips_unplaced,
        test_emit_m9k_mode_synthetic_cell,
        test_emit_m9k_mode_w18_emits_goldintersect,
        test_emit_m9k_mode_rejects_non_m9k_bel,
        test_convert_emits_m9k_mode_goldintersect,
    ]
    for t in tests:
        t()
    print(f"\n{len(tests)}/{len(tests)} tests OK")


if __name__ == "__main__":
    main()
