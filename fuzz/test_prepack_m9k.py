# SPDX-License-Identifier: GPL-3.0-or-later
"""prepack_m9k.py — assigns NEXTPNR_BEL to EP4CE6_M9K cells.

The smoke test path is:
  Yosys (memory_libmap → techmap)
    → prepack_m9k (this module)
    → np2fasm
    → fasm2rbf

prepack_m9k draws sites from the calibrated `M9K_INIT_ANCHORS` table
in m9k_init_basis. We pin down:

1. Single-cell pre-pack reaches the first calibrated site at the
   target (W, D).
2. Multi-cell pre-pack consumes consecutive calibrated sites,
   matching the libmap-split behaviour for a 9×512 RAM that becomes
   5 width=18 cells.
3. --sites override is honoured in order.
4. Yosys-style binary-string params (WIDTH_A / DEPTH) are accepted.
5. Insufficient anchors → an ERROR-prefixed warning, no BEL stamped.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import prepack_m9k as pm
from m9k_init_basis import M9K_INIT_ANCHORS


def _mock_design(n_cells: int, width: int, depth: int) -> dict:
    cells = {}
    for i in range(n_cells):
        cells[f"mem.0.{i}"] = {
            "type": "EP4CE6_M9K",
            "parameters": {
                "INIT": "0" * (width * depth),
                "WIDTH_A": width, "DEPTH": depth,
            },
            "connections": {},
        }
    return {"modules": {"top": {"cells": cells, "netnames": {}}}}


def test_single_cell_picks_first_anchor():
    d = _mock_design(1, 9, 512)
    out, warns = pm.prepack(d, sites_override=None)
    assert not any(w.startswith("ERROR") for w in warns), warns
    cell = out["modules"]["top"]["cells"]["mem.0.0"]
    bel = cell["attributes"]["NEXTPNR_BEL"]
    expect_first = sorted(s for (s, w, dp) in M9K_INIT_ANCHORS
                          if w == 9 and dp == 512)[0]
    assert bel == f"M9K_{expect_first}", bel
    print("  test_single_cell_picks_first_anchor: OK")


def test_multi_cell_consumes_consecutive_sites():
    d = _mock_design(5, 18, 512)
    out, warns = pm.prepack(d, sites_override=None)
    assert not any(w.startswith("ERROR") for w in warns), warns
    bels = [out["modules"]["top"]["cells"][f"mem.0.{i}"]
            ["attributes"]["NEXTPNR_BEL"] for i in range(5)]
    # All distinct
    assert len(set(bels)) == 5, bels
    # All M9K sites
    assert all(b.startswith("M9K_X") for b in bels), bels
    # All match calibrated entries at (18, 512)
    cal = {f"M9K_{s}" for (s, w, d) in M9K_INIT_ANCHORS
           if w == 18 and d == 512}
    assert set(bels).issubset(cal), set(bels) - cal
    print("  test_multi_cell_consumes_consecutive_sites: OK")


def test_sites_override_is_honoured_in_order():
    d = _mock_design(3, 18, 512)
    override = ["X15_Y14_N0", "X15_Y10_N0", "X15_Y12_N0"]
    out, warns = pm.prepack(d, sites_override=override)
    assert not any(w.startswith("ERROR") for w in warns), warns
    bels = [out["modules"]["top"]["cells"][f"mem.0.{i}"]
            ["attributes"]["NEXTPNR_BEL"] for i in range(3)]
    assert bels == [f"M9K_{s}" for s in override], bels
    print("  test_sites_override_is_honoured_in_order: OK")


def test_yosys_binary_params_accepted():
    """post-techmap JSON serializes WIDTH_A / DEPTH as binary strings."""
    width, depth = 18, 512
    d = {
        "modules": {
            "top": {
                "cells": {
                    "mem.0.0": {
                        "type": "EP4CE6_M9K",
                        "parameters": {
                            "INIT": "0" * (width * depth),
                            "WIDTH_A": f"{width:032b}",
                            "DEPTH": f"{depth:032b}",
                        },
                        "connections": {},
                    },
                },
                "netnames": {},
            }
        }
    }
    out, warns = pm.prepack(d, sites_override=None)
    assert not any(w.startswith("ERROR") for w in warns), warns
    bel = out["modules"]["top"]["cells"]["mem.0.0"]["attributes"]["NEXTPNR_BEL"]
    cal_18 = {f"M9K_{s}" for (s, w, dp) in M9K_INIT_ANCHORS
              if w == 18 and dp == 512}
    assert bel in cal_18, bel
    print("  test_yosys_binary_params_accepted: OK")


def test_too_many_cells_yields_error_warning():
    """When more cells share (W, D) than calibrated sites exist, prepack
    should emit an ERROR warning rather than silently leaving cells
    unplaced — the downstream np2fasm path would otherwise produce
    incomplete FASM with no clear cause."""
    n_cal = sum(1 for (s, w, d) in M9K_INIT_ANCHORS if w == 18 and d == 512)
    d = _mock_design(n_cal + 1, 18, 512)
    out, warns = pm.prepack(d, sites_override=None)
    assert any(w.startswith("ERROR") for w in warns), warns
    # No bels stamped (group bailed)
    cells = out["modules"]["top"]["cells"]
    assert all(
        "NEXTPNR_BEL" not in c.get("attributes", {})
        for c in cells.values()
    )
    print("  test_too_many_cells_yields_error_warning: OK")


def test_no_m9k_cells_is_a_warn_not_error():
    """A design with zero EP4CE6_M9K cells should pass through with a
    descriptive non-error warning (so prepack can be safely chained
    even when the design has no M9K)."""
    d = {"modules": {"top": {"cells": {}, "netnames": {}}}}
    _, warns = pm.prepack(d, sites_override=None)
    assert not any(w.startswith("ERROR") for w in warns), warns
    assert any("no EP4CE6_M9K" in w for w in warns), warns
    print("  test_no_m9k_cells_is_a_warn_not_error: OK")


def main():
    tests = [
        test_single_cell_picks_first_anchor,
        test_multi_cell_consumes_consecutive_sites,
        test_sites_override_is_honoured_in_order,
        test_yosys_binary_params_accepted,
        test_too_many_cells_yields_error_warning,
        test_no_m9k_cells_is_a_warn_not_error,
    ]
    for t in tests:
        t()
    print(f"\n{len(tests)}/{len(tests)} tests OK")


if __name__ == "__main__":
    main()
