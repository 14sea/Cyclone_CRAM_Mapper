#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Targeted Y-group diversity campaign for ambiguous DOWNWARD C4 classes.

The attach-end register (c4_dy_key_first_write_pass memo) cracked the
LE_BUFFER downward family, but single-group classes stayed
ambiguous_geom: their corpus support came from ONE (x,y) each
(I=15<-R24 @ (16,8), I=12<-C4 slot2 @ (11,4), ...), so families A/B/C
can't be told apart.  Relaxing MIN_N onto the thin NEORV32 multi-group
data was a NET NEGATIVE (n=4 overfits — see MIN_N_MG note in
c4_pip_pattern_mine).  The fix is REAL Y-group diversity from new
compiles.

Method: LONG downward vertical two-LUT routes (source LUT high, dest LUT
low, same column) across several X columns.  A long span (e.g. Y21->Y2 =
~5 C4 hops) makes the router chain C4 wires through every Y-group, so
one route yields C4 pips at groups 0..6; pooling across X columns
(column-relative) gives each (I,src,dx,dy,slot) class multiple instances
in multiple groups.

Artifacts -> tmp/c4_ygroup/ (own dir; NOT a holdout set — the miner reads
it as a third leg, gate treats it as mined).  ~10-15 s/compile.

Usage:
  python3 c4_ygroup_diversity_campaign.py build     # run the grid
  python3 c4_ygroup_diversity_campaign.py analyze    # group-diversity report
"""
import sys, os, json, glob, re, shutil, subprocess, collections

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(REPO, 'fuzz'))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config  # noqa: E402

CB = config.COLUMN_BASE
OUTD = os.path.join(REPO, 'tmp', 'c4_ygroup')
WORK = os.path.join(OUTD, 'work')
ZERO = os.path.join(REPO, 'results/rbf/nv_zero_global.rbf')
WRE = re.compile(r'\b((?:C4|R24|C16|R4|LOCAL_INTERCONNECT|LE_BUFFER|LOCAL_LINE)'
                 r'_X\d+_Y\d+_N\d+(?:_I\d+)?)\b')
TCL = """project_open {tag}
load_package sta
create_timing_netlist
create_clock -name vclk -period 100 [get_ports CLK]
set_input_delay -clock vclk 0 [get_ports {{A B C D}}]
set_output_delay -clock vclk 0 [get_ports Q]
update_timing_netlist
report_timing -setup -npaths 8 -detail full_path -show_routing -file _route_out.txt
delete_timing_netlist
project_close
"""

# LONG downward vertical routes at spread X columns (avoid X4 Pitfall
# #16 country and non-LAB X15/20/27); plus medium spans for group
# coverage.  (sx, sy, dx, dy) with sy > dy = downward.
COLS = [10, 13, 16, 19, 22, 25, 28, 31]
SPANS = [(21, 2), (19, 4), (18, 5), (21, 8), (14, 2), (17, 6)]


def build_one(sx, sy, dxx, dy, port='dataa'):
    from verilog_gen import gen_two_luts_single_input_clocked
    from plan_d_prime_factory import gen_qsf_ce10
    import compile as qc
    tag = f"yg_X{sx}Y{sy}_to_X{dxx}Y{dy}"
    rbf_out = os.path.join(OUTD, tag + '.rbf')
    wires_out = os.path.join(OUTD, tag + '.wires.json')
    if os.path.exists(rbf_out) and os.path.exists(wires_out):
        print(tag, "cached")
        return
    v = gen_two_luts_single_input_clocked(0x8888, 0xAAAA, connect_port=port)
    qsf = gen_qsf_ce10({'lut1': f'LCCOMB_X{sx}_Y{sy}_N0',
                        'lut2': f'LCCOMB_X{dxx}_Y{dy}_N0'}, seed=1)
    ws = os.path.join(WORK, tag)
    shutil.rmtree(ws, ignore_errors=True)
    rbf, el, err = qc.compile_and_export(tag, v, qsf, rbf_output=rbf_out,
                                         work_dir=WORK)
    if not rbf:
        print(tag, "COMPILE FAIL:", err[:200])
        return
    with open(os.path.join(ws, '_rt.tcl'), 'w') as f:
        f.write(TCL.format(tag=tag))
    subprocess.run([os.path.expanduser(
        '~/intelFPGA_lite/21.1/quartus/bin/quartus_sta'),
        '-t', '_rt.tcl'], cwd=ws, capture_output=True, timeout=120)
    seq = []
    with open(os.path.join(ws, '_route_out.txt'), errors='replace') as f:
        for line in f:
            for m in WRE.finditer(line):
                if not seq or seq[-1] != m.group(1):
                    seq.append(m.group(1))
    json.dump(seq, open(wires_out, 'w'), indent=1)
    zero = open(ZERO, 'rb').read()
    g = open(rbf_out, 'rb').read()
    cells = []
    for off in range(5282, 367952):
        if (off - 32) % 210 >= 208:
            continue
        d = g[off] ^ zero[off]
        for bp in range(8):
            if d >> bp & 1:
                cells.append([off, bp])
    json.dump(cells, open(os.path.join(OUTD, tag + '.cells.json'), 'w'))
    c4 = sorted({w for w in seq if w.startswith('C4_')})
    print(f"{tag}: {el:.0f}s  #C4={len(c4)}")
    shutil.rmtree(ws, ignore_errors=True)


def mode_build():
    os.makedirs(OUTD, exist_ok=True)
    for x in COLS:
        for sy, dy in SPANS:
            build_one(x, sy, x, dy)


def mode_analyze():
    import c4_mux_default_probe as probe

    def yaddr(y):
        cr = y - 2
        g, s = cr // 3, cr % 3
        return g, s
    builds = {}
    for fn in glob.glob(os.path.join(OUTD, '*.wires.json')):
        builds[os.path.basename(fn)[:-11]] = json.load(open(fn))
    print(f"builds: {len(builds)}")
    # downward class (I,src,dx,dy,slot) -> attach-groups seen
    cls = collections.defaultdict(lambda: collections.defaultdict(int))
    for tag, seq in builds.items():
        seen = set()
        for a, b in zip(seq, seq[1:]):
            gb = probe.wire_geom(b)
            ma = probe.WIRE.match(a)
            if not gb or not ma:
                continue
            x, y, i, g, s, bp = gb
            dy = int(ma.group(3)) - y
            if dy <= 0:
                continue
            key = (i, ma.group(1), int(ma.group(2)) - x, dy, (y - 2) % 3)
            if (key, b) in seen:
                continue
            seen.add((key, b))
            ag, _ = yaddr(y + dy)
            cls[key][ag] += 1
    # report classes now spanning >=2 groups (the ones diversity unlocks)
    print("=== downward classes with >=2 attach-groups (n>=7) ===")
    hits = 0
    for key, gmap in sorted(cls.items(), key=lambda kv: -sum(kv[1].values())):
        n, ng = sum(gmap.values()), len(gmap)
        if n >= 7 and ng >= 2:
            hits += 1
            print(f"  I={key[0]} src={key[1]} dx={key[2]} dy={key[3]} "
                  f"slot={key[4]}: n={n} groups={sorted(gmap)}")
    print(f"{hits} multi-group downward classes reach n>=7 from this campaign")


if __name__ == '__main__':
    mode = sys.argv[1] if len(sys.argv) > 1 else 'analyze'
    {'build': mode_build, 'analyze': mode_analyze}[mode]()
