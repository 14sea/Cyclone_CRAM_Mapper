# SPDX-License-Identifier: GPL-3.0-or-later
"""Phase A unit tests for np2fasm audit-gap emission.

Covers the four directives added after the NV_BASELINE_PACK landing
(2026-04-15) to close out missing emission paths in np2fasm.convert():

  A1. IOB_BASELINE_NV emitted exactly once whenever any IOB_IN /
      IOB_OUT is present (bridges nv_zero_global hdr into iob_in_E15
      frame so pair-deltas apply correctly).

  A2. IOB_CLK_INPUT PIN_X paired with each GCLK_PIN PIN_X for the 12
      F17 pins mined in iob_clk_pin_hdr_cells.json.

  A3. IOB_ROUTE PIN_X -> X{dx}Y{dy}N{dn}.{port} for direct
      IOB→SLICE drives when the key is present in
      iob_to_slice_sigcache.json (15 HW-verified entries covering
      E16/E15/M16 × five LAB targets).

  A4. SRC X{sx}Y{sy} once per unique LAB that sources a SLICE→SLICE
      ROUTE — unions with route cells before XOR-flip.
"""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "synth"))

from np2fasm import convert  # type: ignore


def _iob(bel: str, O_net: int | None = None, I_net: int | None = None):
    conns: dict = {}
    dirs: dict = {}
    if O_net is not None:
        conns["O"] = [O_net]
        dirs["O"] = "output"
    if I_net is not None:
        conns["I"] = [I_net]
        dirs["I"] = "input"
    return {
        "type": "GENERIC_IOB",
        "attributes": {"NEXTPNR_BEL": bel},
        "connections": conns,
        "port_directions": dirs,
        "parameters": {},
    }


def _dff(x: int, y: int, n: int, clk_net: int, d_net: int, q_net: int):
    return {
        "type": "DFF",
        "attributes": {"NEXTPNR_BEL": f"SLICE_X{x}_Y{y}_N{n}"},
        "connections": {
            "CLK": [clk_net], "D": [d_net], "Q": [q_net],
        },
        "port_directions": {"CLK": "input", "D": "input", "Q": "output"},
        "parameters": {},
    }


def _lut(x: int, y: int, n: int, init_hex: int,
         i_nets: list, q_net: int):
    return {
        "type": "GENERIC_SLICE",
        "attributes": {"NEXTPNR_BEL": f"SLICE_X{x}_Y{y}_N{n}"},
        "connections": {"I": i_nets, "Q": [q_net]},
        "port_directions": {"I": "input", "Q": "output"},
        "parameters": {
            "INIT": bin(init_hex)[2:].zfill(16),
            "FF_USED": "0",
        },
    }


def _wrap(cells: dict) -> dict:
    return {"modules": {"top": {"cells": cells, "netnames": {}}}}


# ---------------------------------------------------------------- A1

def test_iob_baseline_nv_emitted_once_when_iob_in():
    cells = {"pad_K": _iob("IOB_B_PIN_M16", O_net=100)}
    fasm, _ = convert(_wrap(cells))
    assert fasm.count("IOB_BASELINE_NV") == 1, fasm
    # IOB_BASELINE_NV should be at the top (position 0 with no
    # NV_BASELINE_PACK prefix).
    assert fasm[0] == "IOB_BASELINE_NV", fasm
    print("  test_iob_baseline_nv_emitted_once_when_iob_in: OK")


def test_iob_baseline_nv_emitted_once_when_iob_out():
    cells = {"pad_LED": _iob("IOB_Q_PIN_G15", I_net=200)}
    fasm, _ = convert(_wrap(cells))
    assert fasm.count("IOB_BASELINE_NV") == 1, fasm
    print("  test_iob_baseline_nv_emitted_once_when_iob_out: OK")


def test_iob_baseline_nv_dedup_both_dirs():
    cells = {
        "pad_K":   _iob("IOB_B_PIN_M16", O_net=100),
        "pad_LED": _iob("IOB_Q_PIN_G15", I_net=200),
    }
    fasm, _ = convert(_wrap(cells))
    assert fasm.count("IOB_BASELINE_NV") == 1, fasm
    print("  test_iob_baseline_nv_dedup_both_dirs: OK")


def test_iob_baseline_nv_absent_when_no_iob():
    fasm, _ = convert(_wrap({}))
    assert "IOB_BASELINE_NV" not in fasm, fasm
    print("  test_iob_baseline_nv_absent_when_no_iob: OK")


def test_iob_baseline_nv_goes_after_pure_header():
    cells = {"pad_K": _iob("IOB_B_PIN_M16", O_net=100)}
    fasm, _ = convert(_wrap(cells), baseline="pure")
    assert fasm[0] == "NV_BASELINE_PACK", fasm
    assert fasm[1] == "IOB_BASELINE_NV", fasm
    print("  test_iob_baseline_nv_goes_after_pure_header: OK")


def test_iob_baseline_nv_skipped_for_clock_only_dedicated_pin():
    # PIN_E1 is a dedicated clock pad with no IOB_IN entry → IOB
    # emission suppressed → no IOB_BASELINE_NV needed either.
    cells = {
        "clkpad": _iob("IOB_B_PIN_E1", O_net=1),
        "ff":     _dff(10, 4, 0, clk_net=1, d_net=2, q_net=3),
    }
    fasm, _ = convert(_wrap(cells))
    assert "IOB_IN PIN_E1" not in fasm, fasm
    assert "IOB_BASELINE_NV" not in fasm, fasm
    print("  test_iob_baseline_nv_skipped_for_clock_only_dedicated_pin: OK")


# ---------------------------------------------------------------- A2

def test_iob_clk_input_pairs_with_gclk_pin_e1():
    cells = {
        "clkpad": _iob("IOB_B_PIN_E1", O_net=1),
        "ff":     _dff(10, 4, 0, clk_net=1, d_net=2, q_net=3),
    }
    fasm, _ = convert(_wrap(cells))
    assert "GCLK_PIN PIN_E1" in fasm, fasm
    assert "IOB_CLK_INPUT PIN_E1" in fasm, fasm
    # Ordering: IOB_CLK_INPUT immediately follows its GCLK_PIN.
    idx = fasm.index("GCLK_PIN PIN_E1")
    assert fasm[idx + 1] == "IOB_CLK_INPUT PIN_E1", fasm
    print("  test_iob_clk_input_pairs_with_gclk_pin_e1: OK")


def test_iob_clk_input_emitted_for_mined_pins():
    for pin in ("E1", "R8", "N1", "M1", "M2", "T4", "R4",
                "M16", "M15", "E15", "A14", "B14"):
        cells = {
            "clkpad": _iob(f"IOB_B_PIN_{pin}", O_net=1),
            "ff":     _dff(10, 4, 0, clk_net=1, d_net=2, q_net=3),
        }
        fasm, _ = convert(_wrap(cells))
        assert f"IOB_CLK_INPUT PIN_{pin}" in fasm, (pin, fasm)
    print("  test_iob_clk_input_emitted_for_mined_pins: OK "
          "(12 F17 pins covered)")


def test_iob_clk_input_missing_warns():
    # PIN_Z99 isn't a real F17 clock pin, so IOB_CLK_INPUT is skipped
    # and a warning fires.  Hack via a synthetic BEL name — the GCLK
    # emission only needs the regex to parse.
    cells = {
        "clkpad": _iob("IOB_B_PIN_Z99", O_net=1),
        "ff":     _dff(10, 4, 0, clk_net=1, d_net=2, q_net=3),
    }
    fasm, warns = convert(_wrap(cells))
    assert "GCLK_PIN PIN_Z99" in fasm, fasm
    assert "IOB_CLK_INPUT PIN_Z99" not in fasm, fasm
    assert any("IOB_CLK_INPUT" in w and "Z99" in w for w in warns), warns
    print("  test_iob_clk_input_missing_warns: OK")


# ---------------------------------------------------------------- A3

def test_iob_route_emitted_when_sigcache_hit():
    # IOB_E16 driving a LUT at SLICE_X10_Y4_N0 on dataa (sink_idx=0)
    # — one of the 15 HW-verified entries in iob_to_slice_sigcache.json.
    cells = {
        "pad_K": _iob("IOB_B_PIN_E16", O_net=100),
        "lut":   _lut(10, 4, 0, init_hex=0xAAAA,
                      i_nets=[100, "x", "x", "x"], q_net=200),
    }
    fasm, warns = convert(_wrap(cells))
    assert "IOB_ROUTE PIN_E16 -> X10Y4N0.dataa" in fasm, fasm
    # Not emitted as a SLICE→SLICE ROUTE.
    assert not any(line.startswith("ROUTE ") for line in fasm), fasm
    print("  test_iob_route_emitted_when_sigcache_hit: OK")


def test_iob_route_dedups_across_multiple_sinks():
    # Two LUTs, both reading the same IOB on dataa.  Expect ONE
    # IOB_ROUTE line per (pin, sink) tuple — no duplicates across
    # identical keys.
    cells = {
        "pad_K":  _iob("IOB_B_PIN_E16", O_net=100),
        "lut_a":  _lut(10, 4, 0, init_hex=0xAAAA,
                       i_nets=[100, "x", "x", "x"], q_net=201),
        "lut_b":  _lut(16, 4, 0, init_hex=0xAAAA,
                       i_nets=[100, "x", "x", "x"], q_net=202),
    }
    fasm, _ = convert(_wrap(cells))
    routes = [l for l in fasm if l.startswith("IOB_ROUTE")]
    assert sorted(routes) == [
        "IOB_ROUTE PIN_E16 -> X10Y4N0.dataa",
        "IOB_ROUTE PIN_E16 -> X16Y4N0.dataa",
    ], routes
    print("  test_iob_route_dedups_across_multiple_sinks: OK")


def test_iob_route_miss_warns():
    # Valid pin but a LAB not in the sig-cache → no IOB_ROUTE line,
    # warning fires.
    cells = {
        "pad_K": _iob("IOB_B_PIN_E16", O_net=100),
        "lut":   _lut(22, 12, 0, init_hex=0xAAAA,
                      i_nets=[100, "x", "x", "x"], q_net=200),
    }
    fasm, warns = convert(_wrap(cells))
    assert "IOB_ROUTE PIN_E16 -> X22Y12N0.dataa" not in fasm, fasm
    assert any("iob_to_slice" in w and "22,12,0" in w for w in warns), warns
    print("  test_iob_route_miss_warns: OK")


def test_iob_route_skipped_for_clock_only_iob():
    # E1 drives only DFF.CLK — no IOB_ROUTE should fire (that's
    # GCLK_PIN / IOB_CLK_INPUT territory).
    cells = {
        "clkpad": _iob("IOB_B_PIN_E1", O_net=1),
        "ff":     _dff(10, 4, 0, clk_net=1, d_net=2, q_net=3),
    }
    fasm, _ = convert(_wrap(cells))
    assert not any(l.startswith("IOB_ROUTE") for l in fasm), fasm
    print("  test_iob_route_skipped_for_clock_only_iob: OK")


# ---------------------------------------------------------------- A4

def test_src_emitted_for_slice_source_of_route():
    # LUT A drives LUT B — a SLICE→SLICE ROUTE.  Expect SRC X{sx}Y{sy}
    # emitted once for the driver LAB.
    cells = {
        "lut_a": _lut(10, 4, 0, init_hex=0xAAAA,
                      i_nets=["x", "x", "x", "x"], q_net=50),
        "lut_b": _lut(16, 4, 0, init_hex=0xAAAA,
                      i_nets=[50, "x", "x", "x"], q_net=51),
    }
    fasm, _ = convert(_wrap(cells))
    assert any(l.startswith("ROUTE X10Y4N0") for l in fasm), fasm
    assert "SRC X10Y4" in fasm, fasm
    # Exactly one SRC for this LAB.
    assert fasm.count("SRC X10Y4") == 1, fasm
    print("  test_src_emitted_for_slice_source_of_route: OK")


def test_src_dedup_across_multi_sink_route():
    # Same source drives two sinks → still one SRC line.
    cells = {
        "lut_a": _lut(10, 4, 0, init_hex=0xAAAA,
                      i_nets=["x", "x", "x", "x"], q_net=50),
        "lut_b": _lut(16, 4, 0, init_hex=0xAAAA,
                      i_nets=[50, "x", "x", "x"], q_net=51),
        "lut_c": _lut(10, 10, 0, init_hex=0xAAAA,
                      i_nets=[50, "x", "x", "x"], q_net=52),
    }
    fasm, _ = convert(_wrap(cells))
    assert fasm.count("SRC X10Y4") == 1, fasm
    print("  test_src_dedup_across_multi_sink_route: OK")


def test_src_absent_without_slice_routes():
    # Pure IOB→SLICE drive produces IOB_ROUTE, not ROUTE, and no SRC.
    cells = {
        "pad_K": _iob("IOB_B_PIN_E16", O_net=100),
        "lut":   _lut(10, 4, 0, init_hex=0xAAAA,
                      i_nets=[100, "x", "x", "x"], q_net=200),
    }
    fasm, _ = convert(_wrap(cells))
    assert not any(l.startswith("SRC ") for l in fasm), fasm
    print("  test_src_absent_without_slice_routes: OK")


def _main():
    import traceback
    passed = failed = 0
    for name, fn in sorted(globals().items()):
        if not name.startswith("test_") or not callable(fn):
            continue
        try:
            fn()
        except Exception:
            traceback.print_exc()
            print(f"FAIL {name}")
            failed += 1
        else:
            passed += 1
    print(f"\n{passed} passed, {failed} failed")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    _main()
