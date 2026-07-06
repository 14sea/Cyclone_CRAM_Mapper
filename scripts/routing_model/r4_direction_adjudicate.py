#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Adjudicate the R4 direction-alias hypothesis by differential isolation.

QUESTION (raised 2026-07-06): are the unmapped far-driven R4 indices
{28,30,32,33} the SAME physical resource as mapped indices {29,31,...}
driven the other way (=> collapse the STA I-label and key the write path
on the physical track), or genuinely direction-dependent cells (=> keep
the I-label as the write key and mine each index separately)?  This
matters because collapsing a shared bidirectional resource under one
direction's rule is exactly the P5d / Track-D class of silent write-path
error.

METHOD: for a physical column pair (A,B) at a fixed Y, build 4 designs
and isolate the lut1->lut2 route by XOR(connected, disconnected).  The
input-pin->lut1 feed is byte-identical in the connected and disconnected
builds (dont_touch keeps lut1 placed either way) and cancels; the
differential is the clean A->B (or B->A) route + the lut2 input mux.
Compare rightward (cR) vs leftward (cL) differentials, and test the
mirror hypothesis  cL == column-shift(cR, |CB[A]-CB[B]|).

RESULT (2026-07-06, X8<->X12 / X10<->X14 / X12<->X16 @ Y11):
  mirror shift-match 8-11 / ~50 cells; direct jaccard(cR,cL) 0.04-0.17.
  Rightward and leftward routes occupy LARGELY DISJOINT cells: Quartus
  picks physically different resources for A->B vs B->A, and drive
  direction changes the CRAM cell.
  **VERDICT: direction is NOT a free alias.  Keep the STA I-label as the
  write key; mine each index separately (as r4_leftward_campaign.py
  does).**

CAVEAT: cR/cL differ partly because Quartus chose different overall
routes (not only the R4 direction cell); the differential mixes
lut1-output + R4 + lut2-input infra, so this is a route-LEVEL, not
single-cell, disjointness — sufficient for the write-key decision, not a
per-cell proof.  A per-cell far-anchor formula for the still-unmined
{5,9,28,30,32,33} needs a design that cancels the lut infra (e.g.
reach-4 vs reach-8 at a common driver column) so the ~2 R4 config cells
separate from the ~55 infra cells; column-relative voting alone cannot,
because lut1-output infra aligns to the same driver column as the R4.

Usage: python3 scripts/routing_model/r4_direction_adjudicate.py
Artifacts land in tmp/r4_dir/ (gitignored).
"""
import sys, os, json, shutil, subprocess

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(REPO, 'fuzz'))
from verilog_gen import gen_two_luts_single_input_clocked  # noqa: E402
from plan_d_prime_factory import gen_qsf_ce10  # noqa: E402
import compile as qc  # noqa: E402
import config  # noqa: E402

OUTD = os.path.join(REPO, 'tmp', 'r4_dir')
WORK = os.path.join(OUTD, 'work')
ZERO = open(os.path.join(REPO, 'results/rbf/nv_zero_global.rbf'), 'rb').read()
STA = os.path.expanduser('~/intelFPGA_lite/21.1/quartus/bin/quartus_sta')
TCL = """project_open {tag}
load_package sta
create_timing_netlist
create_clock -name vclk -period 100 [get_ports CLK]
set_input_delay -clock vclk 0 [get_ports {{A B C D}}]
set_output_delay -clock vclk 0 [get_ports Q]
update_timing_netlist
report_timing -setup -npaths 8 -detail full_path -show_routing -file _dp.txt
delete_timing_netlist
project_close
"""


def build(tag, l1, l2, connected):
    ws = os.path.join(WORK, tag)
    shutil.rmtree(ws, ignore_errors=True)
    v = gen_two_luts_single_input_clocked(
        0x8888, 0xAAAA, connect_port='dataa' if connected else 'none')
    qsf = gen_qsf_ce10({'lut1': l1, 'lut2': l2}, seed=1)
    rbf, _, err = qc.compile_and_export(
        tag, v, qsf, rbf_output=os.path.join(OUTD, tag + '.rbf'), work_dir=WORK)
    if not rbf:
        print(tag, "FAIL", err[:100])
        return None
    g = open(os.path.join(OUTD, tag + '.rbf'), 'rb').read()
    cells = set()
    for off in range(5282, 367952):
        if (off - 32) % 210 >= 208:
            continue
        d = g[off] ^ ZERO[off]
        for bp in range(8):
            if d >> bp & 1:
                cells.add((off, bp))
    shutil.rmtree(ws, ignore_errors=True)
    return cells


def adjudicate(A, B, Y):
    r_on = build(f"dir_R_on_X{A}X{B}Y{Y}", f"LCCOMB_X{A}_Y{Y}_N0", f"LCCOMB_X{B}_Y{Y}_N0", True)
    r_off = build(f"dir_R_off_X{A}X{B}Y{Y}", f"LCCOMB_X{A}_Y{Y}_N0", f"LCCOMB_X{B}_Y{Y}_N0", False)
    l_on = build(f"dir_L_on_X{B}X{A}Y{Y}", f"LCCOMB_X{B}_Y{Y}_N0", f"LCCOMB_X{A}_Y{Y}_N0", True)
    l_off = build(f"dir_L_off_X{B}X{A}Y{Y}", f"LCCOMB_X{B}_Y{Y}_N0", f"LCCOMB_X{A}_Y{Y}_N0", False)
    if None in (r_on, r_off, l_on, l_off):
        return
    cR, cL = r_on ^ r_off, l_on ^ l_off
    shift = config.COLUMN_BASE[B] - config.COLUMN_BASE[A]
    cRsh = {(o + shift, bp) for o, bp in cR}
    inter = cR & cL
    print(f"=== X{A}<->X{B} Y{Y} ===")
    print(f"  |cR|={len(cR)} |cL|={len(cL)} jaccard={len(inter)/max(1,len(cR | cL)):.2f}"
          f"  mirror-shift-match={len(cRsh & cL)}/{len(cL)}")


if __name__ == '__main__':
    os.makedirs(OUTD, exist_ok=True)
    for A, B in [(8, 12), (10, 14), (12, 16)]:
        adjudicate(A, B, 11)
