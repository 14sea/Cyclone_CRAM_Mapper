#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Pip-level prediction gate: score mined routing laws against a gold RBF.

Given a design's gold RBF and its STA `-show_routing` wire sequences,
predict the CRAM cells implied by every covered pip/wire and check them
against XOR(gold, nv_zero_global).  Read-side verification tool — the
per-class precision numbers are the evidence a future write path
(write_c4_pip / extended write_r4) would stand on.  NOT a write path
itself; NOT a safety validator (use validate_safe_for_hardware +
li_mux_gate for that).

Covered laws:
  - C4 I!=0 pip classes from results/c4_inz_pip_voting_candidates.json
    (pip-conditioned: (I, src_type, dx, slot) -> cell = CB[x]+R+3g, bp(y))
  - R4 via production _R4_BASE_PREV incl. the 2026-07-06 additions
    I=24/I=31 (wire-conditioned pair bases in the prev column)

Modes:
  python3 pip_prediction_gate.py corpus     # C4 holdout vs 980-route bitdb
  python3 pip_prediction_gate.py leftward   # R4/C4 vs tmp/r4_leftward builds
                                            # (I=24/31: half-split holdout —
                                            #  re-voted from even builds,
                                            #  scored on odd builds)

Honest scoring notes:
  - R4 hit rates on dense designs run ~30-40% even for documented bases
    (driver-conditioning + column holes) — compare against the printed
    doc-control rows, not against 100%.
  - A miss means "cell not in XOR", which conflates (a) wrong law,
    (b) column hole, (c) different driver context.  Per-column output
    lets you tell (b) apart.
"""
import sys, os, json, glob, re, sqlite3, collections

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(REPO, 'fuzz'))
import bitstream, config  # noqa: E402

CB = config.COLUMN_BASE
CW = bitstream._COL_WIDTH
BASE = bitstream._R4_BASE_PREV
C4_TABLE_PATH = os.path.join(REPO, 'results/c4_inz_pip_voting_candidates.json')
CK = re.compile(r'C4,I=(\d+),src=(\w+),dx=(-?\d+),slot=(\d+)')
WIRE = re.compile(r'^(R24|R4|C16|C4|LOCAL_INTERCONNECT|LOCAL_LINE|LE_BUFFER)'
                  r'_X(\d+)_Y(\d+)_N(\d+)(?:_I(\d+))?$')


def yaddr(y):
    cr = y - 2
    g, s = cr // 3, cr % 3
    return g, s, (6 - g) if s == 2 else (7 - g)


def r4_geom(y):
    cr = y - 2
    g, s = cr // 3, cr % 3
    bp = 7 - g if s == 0 else 6 - g
    extra = (66 + (1 if g > 0 else 0)) if s == 0 else (-70 if s == 1 else 0)
    return g, s, bp, extra


def load_c4_table():
    table = {}
    for k, v in json.load(open(C4_TABLE_PATH))['classes'].items():
        m = CK.match(k)
        table[(int(m.group(1)), m.group(2), int(m.group(3)), int(m.group(4)))] = \
            [c[0] for c in v['candidates']]
    return table


def predict_c4_pip(table, prev_wire, wire):
    """cells implied by pip prev_wire->wire, or None if class unmined."""
    mb = WIRE.match(wire)
    if not mb or mb.group(1) != 'C4' or not mb.group(5):
        return None
    x, y, i = int(mb.group(2)), int(mb.group(3)), int(mb.group(5))
    if i == 0 or x not in CB or not 2 <= y <= 21:
        return None
    ma = WIRE.match(prev_wire)
    if not ma:
        return None
    g, s, bp = yaddr(y)
    key = (i, ma.group(1), int(ma.group(2)) - x, s)
    if key not in table:
        return None
    return key, [(CB[x] + R + 3 * g, bp) for R in table[key]]


def predict_r4(wire, base_prev=None):
    """pair cells implied by an R4 wire per _R4_BASE_PREV (or override)."""
    m = WIRE.match(wire)
    if not m or m.group(1) != 'R4' or not m.group(5):
        return None
    x, y, i = int(m.group(2)), int(m.group(3)), int(m.group(5))
    bases = (base_prev or BASE).get(i)
    if not bases or not 2 <= y <= 21:
        return None
    px = bitstream.RouteCodec()._prev_lab_x(x)
    if px is None or px not in CB or CW.get(px, 7350) != 7350:
        return None
    g, s, bp, extra = r4_geom(y)
    cs = CB[px] - 136
    return i, [(cs + b + extra + 3 * g, bp) for b in bases]


def seq_of_stalist(rows):
    seq = []
    for e in rows:
        loc = e.get('location', '')
        if WIRE.match(loc) and (not seq or seq[-1] != loc):
            seq.append(loc)
    return seq


def mode_corpus():
    table = load_c4_table()
    db = sqlite3.connect(os.path.join(REPO, 'results/ep4ce6_bitdb.sqlite'))
    cur = db.cursor()
    cells = collections.defaultdict(set)
    for eid, off, bp in cur.execute(
            "SELECT experiment_id,byte_offset,bit_position FROM bit_mapping "
            "WHERE experiment_id IN (SELECT experiment_id FROM routing_paths)"):
        if off >= 5282 and (off - 32) % 210 < 208:
            cells[eid].add((off, bp))
    hit, tot = collections.Counter(), collections.Counter()
    for eid, pj in cur.execute("SELECT experiment_id, path_json FROM routing_paths"):
        seq = seq_of_stalist(json.loads(pj))
        for a, b in zip(seq, seq[1:]):
            p = predict_c4_pip(table, a, b)
            if not p:
                continue
            key, pred = p
            for c in pred:
                tot[key] += 1
                hit[key] += c in cells[eid]
    th = tt = 0
    print("=== C4 pip-law holdout vs 980-route corpus ===")
    for k in sorted(tot, key=lambda k: -tot[k]):
        print(f"I={k[0]} src={k[1]} dx={k[2]} slot={k[3]}: {hit[k]}/{tot[k]}")
        th += hit[k]; tt += tot[k]
    print(f"TOTAL {th}/{tt}" + (f" = {th/tt*100:.0f}%" if tt else ""))
    return th, tt


def mode_leftward():
    builds = {}
    for fn in glob.glob(os.path.join(REPO, 'tmp/r4_leftward/*.wires.json')):
        tag = os.path.basename(fn)[:-11]
        cf = fn.replace('.wires.json', '.cells.json')
        if os.path.exists(cf):
            builds[tag] = (json.load(open(fn)),
                           set(map(tuple, json.load(open(cf)))))
    tags = sorted(builds)
    # half-split holdout for the freshly mined I=24/31: score only odd builds
    score_tags = tags[1::2]
    print(f"builds: {len(builds)} (scoring odd half: {len(score_tags)})")
    hit, tot = collections.Counter(), collections.Counter()
    for tag in score_tags:
        seq, cells = builds[tag]
        seen = set()
        for w in seq:
            if w in seen:
                continue
            seen.add(w)
            p = predict_r4(w)
            if not p:
                continue
            i, pred = p
            ok = any(c in cells for c in pred)
            tot[i] += 1
            hit[i] += ok
    print("=== R4 wire-law (either pair cell) on odd-half leftward builds ===")
    for i in sorted(tot):
        star = "  <== NEW" if i in (24, 31) else ""
        print(f"I={i}: {hit[i]}/{tot[i]}{star}")


if __name__ == '__main__':
    mode = sys.argv[1] if len(sys.argv) > 1 else 'corpus'
    {'corpus': mode_corpus, 'leftward': mode_leftward}[mode]()
