# SPDX-License-Identifier: GPL-3.0-or-later
"""Unit test for np2fasm.py GCLK_PIN + LAB_CLK_SEL emission.

The refactored GCLK pipeline replaces the legacy one-line `GCLK`
directive with two XOR-delta directives:
  * `GCLK_PIN PIN_X`   — per-pin one-hot activate set
  * `LAB_CLK_SEL X{x}Y{y}` — per-LAB clock-select cell set

These are emitted when a DFF's CLK net traces back to an IOB driver.
Fallback to the legacy `GCLK` is kept for the (expected rare) case
where no CLK net resolves to an IOB (e.g. pre-IOB test harnesses).
"""
from __future__ import annotations

import json
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
        conns["O"] = [O_net]; dirs["O"] = "output"
    if I_net is not None:
        conns["I"] = [I_net]; dirs["I"] = "input"
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


def _lut(x: int, y: int, n: int, init_hex: int, i_nets: list, q_net: int):
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


def test_gclk_pin_single_dff_to_iob_clk():
    """DFF.CLK ← IOB.O (pad M16 acting as CLK input)."""
    cells = {
        "clkpad": _iob("IOB_B_PIN_M16", O_net=1),
        "ff":     _dff(10, 4, 0, clk_net=1, d_net=2, q_net=3),
    }
    fasm, warns = convert(_wrap(cells))
    assert "GCLK_PIN PIN_M16" in fasm, fasm
    assert "LAB_CLK_SEL X10Y4" in fasm, fasm
    assert "LAB_CLK_SEL_LE X10Y4N0" in fasm, fasm
    assert "GCLK" not in fasm, fasm  # no legacy fallback
    assert "IOB_IN PIN_M16" in fasm, fasm


def test_gclk_pin_multiple_dffs_same_clk_same_lab():
    """Two DFFs sharing one CLK in one LAB → 1 GCLK_PIN, 1 LAB_CLK_SEL."""
    cells = {
        "clkpad": _iob("IOB_B_PIN_E1", O_net=1),
        "ff0":    _dff(10, 4, 0, clk_net=1, d_net=2, q_net=3),
        "ff1":    _dff(10, 4, 2, clk_net=1, d_net=4, q_net=5),
    }
    fasm, warns = convert(_wrap(cells))
    assert fasm.count("GCLK_PIN PIN_E1") == 1, fasm
    assert fasm.count("LAB_CLK_SEL X10Y4") == 1, fasm
    # Per-LE layer: N=0 and N=2 each get their own directive
    assert "LAB_CLK_SEL_LE X10Y4N0" in fasm, fasm
    assert "LAB_CLK_SEL_LE X10Y4N2" in fasm, fasm


def test_gclk_pin_multiple_dffs_different_labs():
    """Two DFFs in different LABs sharing one CLK → 1 pin, 2 LAB_CLK_SELs."""
    cells = {
        "clkpad": _iob("IOB_B_PIN_R8", O_net=1),
        "ff_a":   _dff(10, 4,  0, clk_net=1, d_net=2, q_net=3),
        "ff_b":   _dff(22, 10, 0, clk_net=1, d_net=4, q_net=5),
    }
    fasm, warns = convert(_wrap(cells))
    assert fasm.count("GCLK_PIN PIN_R8") == 1, fasm
    assert "LAB_CLK_SEL X10Y4" in fasm, fasm
    assert "LAB_CLK_SEL X22Y10" in fasm, fasm
    assert "LAB_CLK_SEL_LE X10Y4N0" in fasm, fasm
    assert "LAB_CLK_SEL_LE X22Y10N0" in fasm, fasm


def test_gclk_fallback_when_no_iob_driver():
    """DFF whose CLK net has no IOB driver → legacy GCLK + warning."""
    cells = {
        # DFF CLK net 99 has no driver at all
        "ff": _dff(10, 4, 0, clk_net=99, d_net=2, q_net=3),
    }
    fasm, warns = convert(_wrap(cells))
    assert "GCLK" in fasm, fasm
    assert not any(line.startswith("GCLK_PIN") for line in fasm), fasm
    assert not any(line.startswith("LAB_CLK_SEL") for line in fasm), fasm
    assert any("no IOB driver" in w for w in warns), warns


def test_no_dff_no_gclk_anything():
    """Combinational design — no clock at all."""
    cells = {
        "inpad":  _iob("IOB_B_PIN_M16", O_net=1),
        "lut":    _lut(10, 4, 0, 0x8888, [1, 0, 0, 0], 2),
        "outpad": _iob("IOB_Q_PIN_G15", I_net=2),
    }
    fasm, warns = convert(_wrap(cells))
    assert not any(line.startswith("GCLK") for line in fasm), fasm
    assert not any(line.startswith("LAB_CLK_SEL") for line in fasm), fasm


def test_partial_resolution_warns():
    """Two DFFs; only one has IOB driver on CLK. Emit for the resolved
    one, warn for the unresolved."""
    cells = {
        "clkpad": _iob("IOB_B_PIN_M16", O_net=1),
        "ff_ok":  _dff(10, 4, 0, clk_net=1,  d_net=2, q_net=3),
        "ff_bad": _dff(22, 10, 0, clk_net=99, d_net=4, q_net=5),
    }
    fasm, warns = convert(_wrap(cells))
    assert "GCLK_PIN PIN_M16" in fasm, fasm
    assert "LAB_CLK_SEL X10Y4" in fasm, fasm
    assert "LAB_CLK_SEL_LE X10Y4N0" in fasm, fasm
    assert "LAB_CLK_SEL X22Y10" not in fasm, fasm
    assert "LAB_CLK_SEL_LE X22Y10N0" not in fasm, fasm
    assert any("did not resolve" in w for w in warns), warns


def main():
    tests = [
        test_gclk_pin_single_dff_to_iob_clk,
        test_gclk_pin_multiple_dffs_same_clk_same_lab,
        test_gclk_pin_multiple_dffs_different_labs,
        test_gclk_fallback_when_no_iob_driver,
        test_no_dff_no_gclk_anything,
        test_partial_resolution_warns,
    ]
    n_pass = n_fail = 0
    for t in tests:
        try:
            t()
            print(f"[ OK ] {t.__name__}")
            n_pass += 1
        except AssertionError as e:
            print(f"[FAIL] {t.__name__}: {e}")
            n_fail += 1
        except Exception as e:
            print(f"[ERR ] {t.__name__}: {type(e).__name__}: {e}")
            n_fail += 1
    print()
    print(f"== {n_pass} pass / {n_fail} fail / {len(tests)} total ==")
    return 0 if n_fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
