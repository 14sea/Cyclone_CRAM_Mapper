#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Historical negative test: reach-4 vs reach-8 did NOT isolate R4 cells.

Goal (2026-07-06): crack the still-unmined R4 indices {5,9,28,30,32,33}.
They only appear as chain-internal hops in the leftward campaign, where
their wire x is scattered and a single-hop differential mixes the ~2 R4
config cells into ~55 lut-infra cells that column-relative voting cannot
separate (lut1-output infra aligns to the same driver column as the R4).

Design: keep lut1 at a COMMON driver column D and route to two distances,
isolating each route by the connected-vs-disconnected differential (the
shared input-pin->lut1 feed cancels):
  diff4(D) = XOR(D->D-4 connected, disconnected)
           = lut1@D-out  +  route(D->D-4)  +  lut2@(D-4)-in
  diff8(D) = XOR(D->D-8 connected, disconnected)
           = lut1@D-out  +  route(D->D-8)  +  lut2@(D-8)-in
Because lut1 is at the SAME D in both, lut1@D-out is IDENTICAL and lives
in diff4 & diff8.  The symmetric difference diff4 ^ diff8 cancels it,
leaving only the route + lut2-input deltas.

STEP 1 (this run, `prove` mode): measure |diff4|, |diff8|, the cancelled
common part |diff4 & diff8|, and the residual |diff4 ^ diff8|.  If the
common part is the dominant chunk (~lut1 infra) and the residual is small
+ column-localized, the cancellation works and mining is viable.  Records
the STA R4 labels each reach produced so we know which I-indices this
geometry exercises before trusting any base.

Result: DISPROVEN as an isolation mechanism.  Simple 2-LUT reach changes
produce only mapped I=17/20/21, not the target set, and changing the reach
relocates endpoint LUTs enough to swamp the ~2 R4 cells.  Do not use this
script as the next mining path; the follow-up is dense-design per-net
differencing in docs/r4_dense_mining_campaign_spec.md.

Usage: python3 scripts/routing_model/r4_reach_isolate.py prove
Artifacts in tmp/r4_reach/ (gitignored).
"""
import sys, os, json, shutil, subprocess, collections

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(REPO, 'fuzz'))
from verilog_gen import gen_two_luts_single_input_clocked  # noqa: E402
from plan_d_prime_factory import gen_qsf_ce10  # noqa: E402
import compile as qc  # noqa: E402
import config  # noqa: E402

CB = config.COLUMN_BASE
OUTD = os.path.join(REPO, 'tmp', 'r4_reach')
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
report_timing -setup -npaths 12 -detail full_path -show_routing -file _r.txt
project_close
"""
# (D, D-4, D-8) triples with all three valid & standard-width columns
TRIPLES = [(12, 8, 4), (16, 12, 8), (21, 17, 13), (25, 21, 17), (29, 25, 21)]


def diff_cells(rbf_path):
    g = open(rbf_path, 'rb').read()
    cells = set()
    for off in range(5282, 367952):
        if (off - 32) % 210 >= 208:
            continue
        d = g[off] ^ ZERO[off]
        for bp in range(8):
            if d >> bp & 1:
                cells.add((off, bp))
    return cells


def build(tag, l1, l2, connected, want_labels=False):
    ws = os.path.join(WORK, tag)
    shutil.rmtree(ws, ignore_errors=True)
    v = gen_two_luts_single_input_clocked(
        0x8888, 0xAAAA, connect_port='dataa' if connected else 'none')
    qsf = gen_qsf_ce10({'lut1': l1, 'lut2': l2}, seed=1)
    rbf, _, err = qc.compile_and_export(
        tag, v, qsf, rbf_output=os.path.join(OUTD, tag + '.rbf'), work_dir=WORK)
    if not rbf:
        print(tag, "FAIL", err[:100])
        return None, []
    labels = []
    if want_labels:
        with open(os.path.join(ws, '_r.tcl'), 'w') as f:
            f.write(TCL.format(tag=tag))
        subprocess.run([STA, '-t', '_r.tcl'], cwd=ws, capture_output=True, timeout=120)
        rp = os.path.join(ws, '_r.txt')
        if os.path.exists(rp):
            for s in qc._parse_route_file(rp):
                if s['location'].startswith('R4'):
                    labels.append(s['location'])
    cells = diff_cells(os.path.join(OUTD, tag + '.rbf'))
    shutil.rmtree(ws, ignore_errors=True)
    return cells, labels


def col_of(off):
    best = None
    for x in sorted(CB):
        if CB[x] - 200 <= off:
            best = x
    return best


def prove():
    os.makedirs(OUTD, exist_ok=True)
    for D, m4, m8 in TRIPLES:
        Y = 11
        r4_on, lab4 = build(f"re_D{D}_r4_on", f"LCCOMB_X{D}_Y{Y}_N0", f"LCCOMB_X{m4}_Y{Y}_N0", True, True)
        r4_off, _ = build(f"re_D{D}_r4_off", f"LCCOMB_X{D}_Y{Y}_N0", f"LCCOMB_X{m4}_Y{Y}_N0", False)
        r8_on, lab8 = build(f"re_D{D}_r8_on", f"LCCOMB_X{D}_Y{Y}_N0", f"LCCOMB_X{m8}_Y{Y}_N0", True, True)
        r8_off, _ = build(f"re_D{D}_r8_off", f"LCCOMB_X{D}_Y{Y}_N0", f"LCCOMB_X{m8}_Y{Y}_N0", False)
        if None in (r4_on, r4_off, r8_on, r8_off):
            continue
        d4, d8 = r4_on ^ r4_off, r8_on ^ r8_off
        common = d4 & d8
        resid = d4 ^ d8
        rescols = collections.Counter(col_of(o) for o, _ in resid)
        print(f"\n=== D={D} (reach4->X{m4}, reach8->X{m8}) Y{Y} ===")
        print(f"  |diff4|={len(d4)} |diff8|={len(d8)} common(cancelled)={len(common)} residual={len(resid)}")
        print(f"  reach4 R4 labels: {sorted(set(lab4))}")
        print(f"  reach8 R4 labels: {sorted(set(lab8))}")
        print(f"  residual cols: {dict(sorted(rescols.items()))}")
        json.dump({'D': D, 'm4': m4, 'm8': m8, 'lab4': lab4, 'lab8': lab8,
                   'diff4': sorted(d4), 'diff8': sorted(d8)},
                  open(os.path.join(OUTD, f're_D{D}.json'), 'w'))


if __name__ == '__main__':
    mode = sys.argv[1] if len(sys.argv) > 1 else 'prove'
    if mode == 'prove':
        prove()
    else:
        sys.exit("only 'prove' mode implemented; mining follows once cancellation is shown")
