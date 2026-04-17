# SPDX-License-Identifier: GPL-3.0-or-later
"""Unit test for np2fasm.py IOB directive emission.

Builds synthetic nextpnr-generic routed JSON fragments with GENERIC_IOB
cells in several direction configurations and checks the FASM output
against expected `IOB_IN PIN_X` / `IOB_OUT PIN_X` lines.

Verifies the direction convention from chipdb_gen.py:
  - BEL pin "O" is output from BEL to fabric  → pad is INPUT
  - BEL pin "I" is input to BEL from fabric   → pad is OUTPUT
So a cell with connections={"O": [netid]} should emit IOB_IN, and
connections={"I": [netid]} should emit IOB_OUT.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "synth"))

from np2fasm import convert  # type: ignore


def _mk_iob_cell(bel_name: str, *, O_net: int | None = None,
                 I_net: int | None = None,
                 EN_net: int | None = None) -> dict:
    conns: dict[str, list] = {}
    dirs: dict[str, str] = {}
    if O_net is not None:
        conns["O"] = [O_net]
        dirs["O"] = "output"
    if I_net is not None:
        conns["I"] = [I_net]
        dirs["I"] = "input"
    if EN_net is not None:
        conns["EN"] = [EN_net]
        dirs["EN"] = "input"
    return {
        "type": "GENERIC_IOB",
        "attributes": {"NEXTPNR_BEL": bel_name},
        "connections": conns,
        "port_directions": dirs,
        "parameters": {},
    }


def _wrap(cells: dict) -> dict:
    return {
        "modules": {
            "top": {
                "cells": cells,
                "netnames": {},
            }
        }
    }


def test_iob_in_emission():
    # IOB acting as INPUT: BEL drives its "O" port into the fabric.
    cells = {"pad_K": _mk_iob_cell("IOB_B_PIN_M16", O_net=100)}
    fasm, warns = convert(_wrap(cells))
    assert "IOB_IN PIN_M16" in fasm, fasm
    assert "IOB_OUT PIN_M16" not in fasm, fasm


def test_iob_out_emission():
    # IOB acting as OUTPUT: fabric drives BEL's "I" port.
    cells = {"pad_LED": _mk_iob_cell("IOB_Q_PIN_G15", I_net=200)}
    fasm, warns = convert(_wrap(cells))
    assert "IOB_OUT PIN_G15" in fasm, fasm
    assert "IOB_IN PIN_G15" not in fasm, fasm


def test_iob_both_dirs_same_design():
    # Realistic `assign LED = K` shape: one input pad + one output pad.
    cells = {
        "pad_K":   _mk_iob_cell("IOB_B_PIN_M16", O_net=100),
        "pad_LED": _mk_iob_cell("IOB_Q_PIN_F15", I_net=100),
    }
    fasm, warns = convert(_wrap(cells))
    assert "IOB_IN PIN_M16" in fasm, fasm
    assert "IOB_OUT PIN_F15" in fasm, fasm


def test_iob_bidir_emits_both_with_warning():
    # Bidir IOB pads must emit the _BIDIR suffix variants so fasm2rbf
    # dispatches to per_pin_input/per_pin_output (cells UNIQUE to the
    # pin across the sweep) instead of input_delta/output_delta (XOR
    # diff vs E15/G15 anchor).  See iob_in_out_r5_composition_falsified.
    cells = {"bidir": _mk_iob_cell("IOB_X_PIN_R13", O_net=1, I_net=2)}
    fasm, warns = convert(_wrap(cells))
    assert "IOB_IN_BIDIR PIN_R13" in fasm, fasm
    assert "IOB_OUT_BIDIR PIN_R13" in fasm, fasm
    # Non-BIDIR variants must NOT be emitted (would double-flip anchor).
    assert "IOB_IN PIN_R13" not in fasm, fasm
    assert "IOB_OUT PIN_R13" not in fasm, fasm
    assert any("bidirectional" in w for w in warns), warns


def test_iob_bidir_with_en_emits_iob_oe():
    # Tristate bidir pad: O+I+EN all connected → IOB_IN_BIDIR + IOB_OUT_BIDIR + IOB_OE.
    cells = {"tristate": _mk_iob_cell("IOB_X_PIN_R5", O_net=1, I_net=2, EN_net=3)}
    fasm, warns = convert(_wrap(cells))
    assert "IOB_IN_BIDIR PIN_R5" in fasm, fasm
    assert "IOB_OUT_BIDIR PIN_R5" in fasm, fasm
    assert "IOB_OE PIN_R5" in fasm, fasm
    assert any("bidirectional" in w for w in warns), warns


def test_iob_bidir_without_en_no_iob_oe():
    # Bidir pad without EN → IOB_IN_BIDIR + IOB_OUT_BIDIR but NO IOB_OE.
    cells = {"bidir_no_en": _mk_iob_cell("IOB_X_PIN_T4", O_net=1, I_net=2)}
    fasm, warns = convert(_wrap(cells))
    assert "IOB_IN_BIDIR PIN_T4" in fasm, fasm
    assert "IOB_OUT_BIDIR PIN_T4" in fasm, fasm
    assert "IOB_OE PIN_T4" not in fasm, fasm


def test_iob_unused_warns_no_emit():
    cells = {"unused": _mk_iob_cell("IOB_U_PIN_A14")}
    fasm, warns = convert(_wrap(cells))
    assert not any(line.startswith("IOB_") for line in fasm), fasm
    assert any("no I/O connections" in w for w in warns), warns


def test_iob_malformed_bel_warns():
    # BEL name that doesn't match IOB_<name>_PIN_<loc> — skip with warning.
    cell = _mk_iob_cell("IOB_WEIRD_NAME", O_net=5)
    cells = {"weird": cell}
    fasm, warns = convert(_wrap(cells))
    assert not any(line.startswith("IOB_IN") or line.startswith("IOB_OUT")
                   for line in fasm), fasm
    assert any("doesn't match" in w for w in warns), warns


def main():
    tests = [
        test_iob_in_emission,
        test_iob_out_emission,
        test_iob_both_dirs_same_design,
        test_iob_bidir_emits_both_with_warning,
        test_iob_bidir_with_en_emits_iob_oe,
        test_iob_bidir_without_en_no_iob_oe,
        test_iob_unused_warns_no_emit,
        test_iob_malformed_bel_warns,
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
