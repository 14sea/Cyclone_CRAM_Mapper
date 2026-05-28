#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Regression tests for the LI-MUX composition-conflict gate (Track D).

Self-contained: inlines the cross-LAB FASM and builds `composed` via bitgen
on the committed nv_zero_global baseline.  Does not depend on the (gitignored)
tmp/ Quartus gold — the precise gold-mismatch assertion is covered separately
when the gold is present on disk.
"""
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "fuzz"))

from fasm2rbf import bitgen, parse_pragmas  # noqa: E402
from li_mux_conflict_gate import (  # noqa: E402
    li_mux_gate, codetermined_li_cells, LiMuxConflictError,
)

BASE_RBF = REPO / "results" / "rbf" / "nv_zero_global.rbf"

# The Track D cross-LAB design (LE_A@X4Y4N0 canon 0x4444 -> LE_B@X4Y21N0 -> G15).
XLAB_FASM = """# fasm2rbf: canon_2input_aware=1
IOB_PAD_NV
X4Y4N0.LUT = 0x4444
X4Y21N0.LUT = 0xaaaa
X4Y21N0.DFF
GCLK_PIN PIN_E1
IOB_CLK_INPUT PIN_E1
LAB_CLK_SEL X4Y21
LAB_CLK_SEL_LE X4Y21N0
ROUTE X4Y4N0 -> X4Y21N0.dataa
IOB_ROUTE PIN_M16 -> X4Y4N0.datab
IOB_ROUTE PIN_E16 -> X4Y4N0.dataa
OUTROUTE_G15 X4Y21N0
SRC X4Y4
"""

# A pure-routing FASM with no LUT directive -> gate must be a no-op.
NO_LUT_FASM = """IOB_PAD_NV
ROUTE X10Y10N0 -> X10Y12N4.datab
"""


def _results(passed, failed):
    print(f"\n{'PASS' if not failed else 'FAIL'}: "
          f"{passed}/{passed + failed} li-mux-gate tests")
    return failed == 0


def main():
    if not BASE_RBF.exists():
        print(f"SKIP: baseline {BASE_RBF} not present")
        return 0
    base = BASE_RBF.read_bytes()
    passed = failed = 0

    def check(name, cond):
        nonlocal passed, failed
        if cond:
            passed += 1
            print(f"  PASS  {name}")
        else:
            failed += 1
            print(f"  FAIL  {name}")

    pragmas = parse_pragmas(XLAB_FASM)
    composed = bitgen(XLAB_FASM, base, **pragmas)

    # 1. co-determined LI cells detected at LAB(4,4) (LUT + routing overlap).
    codet = codetermined_li_cells(XLAB_FASM, base, pragmas=pragmas)
    check("codetermined cells found at LAB(4,4)", (4, 4) in codet and codet[(4, 4)])

    # 2. no gold -> UNVERIFIED -> not ok, and raise_on_fail raises.
    rep = li_mux_gate(XLAB_FASM, base, composed_rbf=composed, gold_rbf=None)
    check("no-gold -> not ok", rep["ok"] is False)
    check("no-gold -> unverified lists LAB(4,4)", (4, 4) in rep["unverified"])
    try:
        li_mux_gate(XLAB_FASM, base, composed_rbf=composed, gold_rbf=None,
                    raise_on_fail=True)
        check("no-gold raise_on_fail raises", False)
    except LiMuxConflictError:
        check("no-gold raise_on_fail raises", True)

    # 3. self-gold (composed IS the gold) -> byte-identical -> PASS.
    rep_self = li_mux_gate(XLAB_FASM, base, composed_rbf=composed,
                           gold_rbf=composed)
    check("self-gold -> ok (0 mismatches)",
          rep_self["ok"] and not rep_self["mismatches"])

    # 4. mismatching gold -> FAIL with mismatches (flip one co-determined cell).
    off, bp = codet[(4, 4)][0]
    fake_gold = bytearray(composed)
    fake_gold[off] ^= (1 << bp)
    rep_mis = li_mux_gate(XLAB_FASM, base, composed_rbf=composed,
                          gold_rbf=bytes(fake_gold))
    check("flipped-gold -> >=1 mismatch",
          not rep_mis["ok"] and len(rep_mis["mismatches"]) >= 1)

    # 5. no-LUT build -> gate is a no-op (ok, even without gold).
    rep_nolut = li_mux_gate(NO_LUT_FASM, base, gold_rbf=None)
    check("no-LUT build -> ok (no co-determined cells)",
          rep_nolut["ok"] and not rep_nolut["codetermined"])

    # 6. (optional) precise gold-mismatch vs the real Quartus gold if present.
    gold_path = (REPO / "tmp" / "quartus_xlab" / "output_files"
                 / "xlab_X4Y4_to_X4Y21_mask4444.rbf")
    if gold_path.exists():
        gold = gold_path.read_bytes()
        rep_g = li_mux_gate(XLAB_FASM, base, composed_rbf=composed, gold_rbf=gold)
        under = [m for m in rep_g["mismatches"]
                 if m["off_hex"] == "0x9354" and m["direction"] == "under_drive"]
        check("real-gold -> detects 0x9354 under_drive (P5d cell)", bool(under))
        check("real-gold -> >=6 mismatches", len(rep_g["mismatches"]) >= 6)
    else:
        print("  (skip real-gold checks — gold not on disk)")

    return 0 if _results(passed, failed) else 1


if __name__ == "__main__":
    sys.exit(main())
