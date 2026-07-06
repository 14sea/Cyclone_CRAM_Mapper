#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Directional sparse-compile campaign for the R4 unmapped-I set.

The 'STA-corpus blocked' R4 indices {5,9,24,28-33} (29% of NEORV32 R4
demand) resisted three 2026-05-31 methods.  Root cause found 2026-07-06:
they are the LEFTWARD R4 wires — NEORV32's 40k STA census shows them
driven at dx=+3/+4 (source at the wire's far/right end), while every
green-zone mining route drove rightward wires (dx=0/-1).  Sparse
LEFTWARD routes (dst 3-4 LAB columns left of src) make the router use
them, at ~10s/compile.

Usage:
  # build wave (Quartus; ~15s/build incl. STA; artifacts in tmp/r4_leftward/)
  python3 scripts/routing_model/r4_leftward_campaign.py build \
      "[(13,10),(19,16),(26,23),(31,28)]" "[4,5,6,7,8,9,12,13,14,16,17,18]"
  # analyze all builds on disk
  python3 scripts/routing_model/r4_leftward_campaign.py analyze

Analysis = per-(I, slot, group) cross-column majority voting with
negative discrimination, in the production _r4_addr register:
  off = (COLUMN_BASE[prev_lab_x] - 136) + R + slot_extra + 3*group
  bp  = 7-group (slot0) / 6-group (slot1/2)
Candidate R must hold in EVERY build of >=60% of prev-columns and appear
in <=10% of builds NOT using the wire.  CALIBRATION: documented pairs
recover where the production model itself works (I=17 -> 2802/3223 at
prev=X16/X24; absent exactly at its documented column holes X4/X12).
CONFOUND (do not trust): R values recurring across DIFFERENT I at the
same slot/group (e.g. 4903/5951/6793) are bundle-activity cells — the
homogeneous leftward corpus uses I=17+I=20 together, blinding negatives.
Only I-SPECIFIC candidates count.

Results (2026-07-06 final, 240 builds, PHYSICAL-prev register):
  landed in _R4_BASE_PREV:
    I=24: (2775, 2985)  5/5 cols   I=29: (2746, 2956)  3/3 cols
    I=31: (2738, 2948)  slot0+slot2 cross-derived
  calibration: doc pairs of I=2/17/21/22/25/27 ALL re-derived; I=17
  recovers 4/4 at columns that are holes under the whitelist register
  ('misses near M9K' is partly an anchoring artifact).
  observed lattice: base decreases 8 per +2 I-step within each parity
  family (even 2791/2783/2775..., odd 2762/2754/2746/2738).
  NEORV32 either-pair wire-hit: I=24 32%, I=31 27% == doc-control
  profile (I=17 34%, I=20 38%; random floor 10-15%).
OPEN — direction-alias hypothesis: far-driven I=28/30/33 vote the SAME
byte pairs as I=29/31 under a +3-column (driver-end) anchor.  ADJUDICATED
+ REJECTED 2026-07-06 (commit db0dbd4, r4_direction_adjudicate.py):
rightward vs leftward single-hop differentials are largely DISJOINT
(jaccard 0.04-0.17) -> drive direction changes the CRAM cell, keep the
STA I-label as the write key (do NOT collapse); the "same byte pair" was
lattice coincidence.  Still unmined: {5, 9, 28, 30, 32, 33} -- need an
infra-cancelling design (reach-4 vs reach-8 at a common driver) to
separate the ~2 R4 cells from the ~55 lut-infra cells.
"""
import sys, os, json, glob, re, shutil, subprocess, collections

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(REPO, 'fuzz'))
import bitstream, config  # noqa: E402

CB = config.COLUMN_BASE
CW = bitstream._COL_WIDTH
BASE = bitstream._R4_BASE_PREV
OUTD = os.path.join(REPO, 'tmp', 'r4_leftward')
WORK = os.path.join(OUTD, 'work')
WRE = re.compile(r'\b((?:C4|R24|C16|R4|LOCAL_INTERCONNECT|LE_BUFFER|LOCAL_LINE)'
                 r'_X\d+_Y\d+_N\d+(?:_I\d+)?)\b')
R4RE = re.compile(r'R4_X(\d+)_Y(\d+)_N\d+_I(\d+)$')
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


def r4_geom(y):
    cr = y - 2
    g, s = cr // 3, cr % 3
    bp = 7 - g if s == 0 else 6 - g
    extra = (66 + (1 if g > 0 else 0)) if s == 0 else (-70 if s == 1 else 0)
    return g, s, bp, extra


def build_one(sx, sy, dx, dy, port='dataa'):
    from verilog_gen import gen_two_luts_single_input_clocked
    from plan_d_prime_factory import gen_qsf_ce10
    import compile as qc
    tag = f"lw_X{sx}Y{sy}_to_X{dx}Y{dy}"
    rbf_out = os.path.join(OUTD, tag + '.rbf')
    wires_out = os.path.join(OUTD, tag + '.wires.json')
    if os.path.exists(rbf_out) and os.path.exists(wires_out):
        print(tag, "cached")
        return
    v = gen_two_luts_single_input_clocked(0x8888, 0xAAAA, connect_port=port)
    qsf = gen_qsf_ce10({'lut1': f'LCCOMB_X{sx}_Y{sy}_N0',
                        'lut2': f'LCCOMB_X{dx}_Y{dy}_N0'}, seed=1)
    ws = os.path.join(WORK, tag)
    shutil.rmtree(ws, ignore_errors=True)
    rbf, el, err = qc.compile_and_export(tag, v, qsf, rbf_output=rbf_out, work_dir=WORK)
    if not rbf:
        print(tag, "COMPILE FAIL:", err[:300])
        return
    with open(os.path.join(ws, '_rt.tcl'), 'w') as f:
        f.write(TCL.format(tag=tag))
    subprocess.run([os.path.expanduser('~/intelFPGA_lite/21.1/quartus/bin/quartus_sta'),
                    '-t', '_rt.tcl'], cwd=ws, capture_output=True, timeout=120)
    seq = []
    with open(os.path.join(ws, '_route_out.txt'), errors='replace') as f:
        for line in f:
            for m in WRE.finditer(line):
                if not seq or seq[-1] != m.group(1):
                    seq.append(m.group(1))
    json.dump(seq, open(wires_out, 'w'), indent=1)
    zero = open(os.path.join(REPO, 'results/rbf/nv_zero_global.rbf'), 'rb').read()
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
    r4s = [w for w in seq if w.startswith('R4_')]
    print(f"{tag}: {el:.0f}s R4={sorted(set(r4s))}")
    shutil.rmtree(ws, ignore_errors=True)


def load_builds():
    builds = {}
    for fn in glob.glob(os.path.join(OUTD, '*.wires.json')):
        tag = os.path.basename(fn)[:-11]
        cf = fn.replace('.wires.json', '.cells.json')
        if os.path.exists(cf):
            builds[tag] = (json.load(open(fn)),
                           set(map(tuple, json.load(open(cf)))))
    return builds


def phys_prev(x):
    """Nearest PHYSICAL LAB column left of x with standard 7350 width.

    Differs from RouteCodec._prev_lab_x (CE6-whitelist LAB_X) by counting
    the jailbreak columns X5/X9/X14/X30/X32 as real columns.  2026-07-06
    finding: with this register the documented pairs of I=2/17/21/22/25/27
    re-derive from the campaign corpus, and I=17 recovers 4/4 at columns
    that are HOLES under the whitelist register — the R4 table's 'misses
    near M9K' is at least partly an anchoring artifact, not fabric
    irregularity.  Production read_r4 still uses the whitelist register;
    migrating it needs its own regression campaign.
    """
    phys = sorted(CB)
    cands = [c for c in phys if c < x]
    if not cands:
        return None
    p = max(cands)
    nxt = min((q for q in phys if q > p), default=None)
    return p if nxt and CB[nxt] - CB[p] == 7350 else None


def analyze():
    builds = load_builds()
    print(f"builds: {len(builds)}")
    alltags = set(builds)
    cls = collections.defaultdict(lambda: collections.defaultdict(set))
    for tag, (seq, cells) in builds.items():
        seen = set()
        for w in seq:
            m = R4RE.match(w)
            if not m:
                continue
            x, y, i = int(m.group(1)), int(m.group(2)), int(m.group(3))
            if not (2 <= y <= 21) or (x, y, i) in seen:
                continue
            seen.add((x, y, i))
            px = phys_prev(x)
            if px is None:
                continue
            g, s, bp, extra = r4_geom(y)
            cls[(i, s, g)][(px, CB[px] - 136, bp, extra)].add(tag)

    res = {}
    for (i, s, g), geoms in sorted(cls.items()):
        if len(geoms) < 3:
            continue
        cand = []
        for R in range(-7350, 14700):
            poshits, negbad, negtot = [], 0, 0
            for (px, cs, bp, extra), tags in geoms.items():
                off = cs + R + extra + 3 * g
                if all((off, bp) in builds[t][1] for t in tags):
                    poshits.append(px)
                for t in alltags - tags:
                    negtot += 1
                    negbad += (off, bp) in builds[t][1]
            if len(poshits) / len(geoms) >= 0.6 and negbad / max(1, negtot) <= 0.10:
                cand.append([R, len(poshits), len(geoms),
                             round(negbad / max(1, negtot), 3)])
        if cand:
            doc = BASE.get(i)
            res[f"I={i},slot={s},g={g}"] = {'cand': cand, 'doc': doc}
            mark = " <== DOC" if doc and any(c[0] in doc for c in cand) else ""
            print(f"I={i} slot={s} g={g}: {[(c[0], f'{c[1]}/{c[2]}') for c in cand[:6]]}"
                  f" doc={doc}{mark}")
    out = os.path.join(REPO, 'results/r4_leftward_candidates.json')
    json.dump({'note': 'per-(I,slot,group) discriminated cross-column voting; '
                       'only I-SPECIFIC candidates are trustworthy (see docstring)',
               'classes': res}, open(out, 'w'), indent=1)
    print(f"-> {out}")


if __name__ == '__main__':
    os.makedirs(OUTD, exist_ok=True)
    mode = sys.argv[1] if len(sys.argv) > 1 else 'analyze'
    if mode == 'build':
        import itertools
        pairs = eval(sys.argv[2])
        ys = eval(sys.argv[3])
        for (sx, dxx), y in itertools.product(pairs, ys):
            build_one(sx, y, dxx, y)
    else:
        analyze()
