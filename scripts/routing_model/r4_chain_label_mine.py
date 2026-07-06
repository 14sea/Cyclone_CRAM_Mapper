#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Mine unmapped R4 indices {5,9,28,30,32,33} from LABELED long chains.

Pivot from r4_reach_isolate.py (2026-07-06): reach-4-vs-reach-8
cancellation was DISPROVEN as the isolation mechanism — simple 2-LUT
leftward hops produce only the ALREADY-MAPPED indices I=17/20/21, never
the targets.  But confirmed that LONG leftward chains (reach 22-28) DO
produce the unmapped set at specific, STA-labelled (wire_x, I):
  D28->X4 : ... R4_X12_I33, R4_X8_I29, R4_X4_I30
  D31->X3 : R4_X30_I28 ...
So the targets are DEEP-chain hops (driver 3-4 cols to the wire's right).

Method: build many long leftward chains, each isolated by the
connected-vs-disconnected differential (cancels the pin->lut1 feed and
Q-register infra).  STA (-from A -to registers) gives the ordered R4
(wire_x, I) list per build.  Because wire_x is KNOWN, anchor precisely at
prev_col(wire_x) and VOTE the base R over all builds that contain a given
(I, wire_x, slot): R passes if r4_addr(prev_col(wire_x), R, y) is present
in EVERY such build and in <=NEG_MAX of builds without it.  wire_x is
fixed per class, so no scattered-x problem; different surrounding chains
provide the negative diversity.

Pass bar for landing into _R4_BASE_PREV: the same I votes a consistent
(pair) at >=3 physical-column anchors, negatives under threshold.

Usage:
  python3 scripts/routing_model/r4_chain_label_mine.py build   # ~compiles
  python3 scripts/routing_model/r4_chain_label_mine.py vote
Artifacts in tmp/r4_chain/ (gitignored).
"""
import sys, os, json, glob, re, shutil, subprocess, collections

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(REPO, 'fuzz'))
from verilog_gen import gen_two_luts_single_input_clocked  # noqa: E402
from plan_d_prime_factory import gen_qsf_ce10  # noqa: E402
import compile as qc  # noqa: E402
import bitstream, config  # noqa: E402

CB = config.COLUMN_BASE
PHYS = sorted(CB)
OUTD = os.path.join(REPO, 'tmp', 'r4_chain')
WORK = os.path.join(OUTD, 'work')
ZERO = open(os.path.join(REPO, 'results/rbf/nv_zero_global.rbf'), 'rb').read()
STA = os.path.expanduser('~/intelFPGA_lite/21.1/quartus/bin/quartus_sta')
R4RE = re.compile(r'R4_X(\d+)_Y(\d+)_N\d+_I(\d+)$')
TCL = """project_open {tag}
load_package sta
create_timing_netlist
create_clock -name vclk -period 100 [get_ports CLK]
set_input_delay -clock vclk 0 [get_ports {{A B C D}}]
set_output_delay -clock vclk 0 [get_ports Q]
update_timing_netlist
report_timing -from [get_ports A] -to [get_registers *] -npaths 8 -detail full_path -show_routing -file _a.txt
project_close
"""
# long leftward chains: (src_x, dst_x) across the fabric width, several rows
SRC_DST = [(31, 3), (31, 7), (29, 3), (28, 4), (26, 4), (25, 3), (31, 4),
           (29, 4), (28, 3), (26, 3), (25, 4), (24, 4), (23, 3), (22, 4),
           (31, 8), (29, 7), (28, 8), (26, 6), (25, 7), (24, 6)]
ROWS = [11, 5, 17]


def diff_cells(path):
    g = open(path, 'rb').read()
    cells = set()
    for off in range(5282, 367952):
        if (off - 32) % 210 >= 208:
            continue
        d = g[off] ^ ZERO[off]
        for bp in range(8):
            if d >> bp & 1:
                cells.add((off, bp))
    return cells


def one(src, dst, Y):
    tag = f"ch_X{src}to{dst}_Y{Y}"
    if os.path.exists(os.path.join(OUTD, tag + '.json')):
        return
    on = None
    for conn, suf in ((True, 'on'), (False, 'off')):
        t = f"{tag}_{suf}"
        ws = os.path.join(WORK, t)
        shutil.rmtree(ws, ignore_errors=True)
        v = gen_two_luts_single_input_clocked(0x8888, 0xAAAA,
            connect_port='dataa' if conn else 'none')
        qsf = gen_qsf_ce10({'lut1': f'LCCOMB_X{src}_Y{Y}_N0',
                            'lut2': f'LCCOMB_X{dst}_Y{Y}_N0'}, seed=1)
        rbf, _, err = qc.compile_and_export(t, v, qsf,
            rbf_output=os.path.join(OUTD, t + '.rbf'), work_dir=WORK)
        if not rbf:
            print(tag, "FAIL", err[:60]); return
        if conn:
            with open(os.path.join(ws, '_a.tcl'), 'w') as f:
                f.write(TCL.format(tag=t))
            subprocess.run([STA, '-t', '_a.tcl'], cwd=ws, capture_output=True, timeout=120)
            labels = []
            ap = os.path.join(ws, '_a.txt')
            if os.path.exists(ap):
                for s in qc._parse_route_file(ap):
                    m = R4RE.match(s['location'])
                    if m:
                        x, yy, i = int(m.group(1)), int(m.group(2)), int(m.group(3))
                        if yy == Y and min(src, dst) - 1 <= x <= max(src, dst) + 1:
                            labels.append([x, i])
            on = diff_cells(os.path.join(OUTD, t + '.rbf'))
        else:
            off = diff_cells(os.path.join(OUTD, t + '.rbf'))
        shutil.rmtree(ws, ignore_errors=True)
    d = on ^ off
    json.dump({'src': src, 'dst': dst, 'Y': Y, 'labels': labels, 'cells': sorted(d)},
              open(os.path.join(OUTD, tag + '.json'), 'w'))
    for t in (f"{tag}_on", f"{tag}_off"):
        p = os.path.join(OUTD, t + '.rbf')
        if os.path.exists(p): os.remove(p)
    uniq = sorted(set(i for _, i in labels))
    print(f"{tag}: {len(d)} cells, I={uniq}")


def phys_prev(x):
    c = [p for p in PHYS if p < x]
    if not c:
        return None
    p = max(c)
    nxt = min((q for q in PHYS if q > p), default=None)
    return p if nxt and CB[nxt] - CB[p] == 7350 else None


def r4_geom(y):
    cr = y - 2
    g, s = cr // 3, cr % 3
    bp = 7 - g if s == 0 else 6 - g
    extra = (66 + (1 if g > 0 else 0)) if s == 0 else (-70 if s == 1 else 0)
    return g, s, bp, extra


def vote():
    builds = [json.load(open(f)) for f in glob.glob(os.path.join(OUTD, 'ch_*.json'))]
    print(f"builds: {len(builds)}")
    # class (I, wire_x, slot) -> set(build idx that has it); plus cell sets
    cls = collections.defaultdict(set)
    cellsets = [set(map(tuple, b['cells'])) for b in builds]
    for bi, b in enumerate(builds):
        Y = b['Y']
        for x, i in b['labels']:
            g, s, bp, ex = r4_geom(Y)
            cls[(i, x, s, Y)].add(bi)
    TARGET = {5, 9, 28, 30, 32, 33, 27}
    landed = {}
    # group by (I, slot): need >=3 distinct wire_x anchors agreeing on base
    byI = collections.defaultdict(list)
    for (i, x, s, Y), have in cls.items():
        if len(have) < 2:
            continue
        g, _, bp, ex = r4_geom(Y)
        px = phys_prev(x)
        if px is None:
            continue
        cs = CB[px] - 136
        # bases present in ALL builds having this (i,x,s), few without
        without = set(range(len(builds))) - have
        cand = []
        for R in range(2500, 3400):
            off = cs + R + ex + 3 * g
            if all((off, bp) in cellsets[bi] for bi in have):
                nb = sum(1 for bi in without if (off, bp) in cellsets[bi])
                if nb / max(1, len(without)) <= 0.08:
                    cand.append(R)
        if cand:
            byI[(i, s)].append((x, len(have), cand))
    print("=== per-(I,slot) anchors with discriminated base candidates ===")
    for (i, s), rows in sorted(byI.items()):
        tag = " [TARGET]" if i in TARGET else ""
        # bases common across >=3 distinct wire_x
        from collections import Counter
        basecount = Counter()
        for x, n, cand in rows:
            for R in set(cand):
                basecount[R] += 1
        consistent = [R for R, c in basecount.items() if c >= 3]
        print(f"I={i} slot={s}{tag}: {len(rows)} anchors; bases@>=3cols={sorted(consistent)}")
        if consistent and i in TARGET:
            landed[(i, s)] = sorted(consistent)
    json.dump({str(k): v for k, v in landed.items()},
              open(os.path.join(REPO, 'results/r4_chain_landed.json'), 'w'), indent=1)
    print("LANDED (target, >=3 cols):", landed)


if __name__ == '__main__':
    os.makedirs(OUTD, exist_ok=True)
    mode = sys.argv[1] if len(sys.argv) > 1 else 'vote'
    if mode == 'build':
        for Y in ROWS:
            for src, dst in SRC_DST:
                one(src, dst, Y)
    else:
        vote()
