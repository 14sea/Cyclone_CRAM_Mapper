#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Pip-level prediction gate: score mined routing laws against gold RBFs.

Given a design's gold RBF and its STA `-show_routing` wire sequences,
predict the CRAM cells implied by every covered pip/wire and check them
against XOR(gold, nv_zero_global).  Read-side verification tool — the
per-class precision numbers are the evidence the write path prototype
(write_c4_pip_proto.py) stands on.  NOT a production write path; NOT a
safety validator (use validate_safe_for_hardware + li_mux_gate for that).

Covered laws:
  - C4 I!=0 FULL pip patterns from results/c4_pip_pattern_table.json
    (families A/B/C; key includes dy since 2026-07-07 — dy-less tables
    are refused).  Classes carry a 'mined_from' tag (neorv32 | corpus);
    the gate NEVER scores a class on the dataset it was mined from —
    every number printed is held out.
  - R4 via production _R4_BASE_PREV incl. the 2026-07-06 additions
    I=24/29/31 (wire-conditioned pair bases in the prev column).

Modes:
  python3 pip_prediction_gate.py corpus     # C4 vs 980-route bitdb
  python3 pip_prediction_gate.py neorv32    # C4 vs NEORV32 gold + 40k census
  python3 pip_prediction_gate.py leftward   # C4 + R4 vs tmp/r4_leftward builds
                                            # (R4 I=24/31: odd-half holdout)
  python3 pip_prediction_gate.py scores     # all three; writes
                                            # results/c4_pip_gate_scores.json
                                            # (consumed by write_c4_pip_proto)

Metric vocabulary (per class, full-pattern):
  cell TP    predicted cell present in gold XOR
  cell MISS  predicted cell ABSENT — this is the write-side FALSE-POSITIVE
             risk: a write path would set a bit Quartus does not set
  inst FULL  instance where EVERY pattern cell hit (what byte-identity needs)
  coverage   C4 I!=0 pips whose class key is in the table / all such pips

Honest scoring notes:
  - R4 hit rates on dense designs run ~30-40% even for documented bases
    (driver-conditioning + column holes) — compare against the printed
    doc-control rows, not against 100%.
  - A miss conflates (a) wrong law, (b) column hole, (c) driver context.
  - 'ambiguous_geom' classes (instances span <2 groups) cannot tell
    families A/B/C apart; they are scored but flagged, and the write
    prototype refuses them.
"""
import sys, os, json, glob, re, sqlite3, collections

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(REPO, 'fuzz'))
import bitstream, config  # noqa: E402

CB = config.COLUMN_BASE
CW = bitstream._COL_WIDTH
BASE = bitstream._R4_BASE_PREV
PATTERN_PATH = os.path.join(REPO, 'results/c4_pip_pattern_table.json')
LEGACY_PATH = os.path.join(REPO, 'results/c4_inz_pip_voting_candidates.json')
SCORES_PATH = os.path.join(REPO, 'results/c4_pip_gate_scores.json')
CK = re.compile(r'C4,I=(\d+),src=(\w+),dx=(-?\d+),dy=(-?\d+),slot=(\d+)')
WIRE = re.compile(r'^(R24|R4|C16|C4|LOCAL_INTERCONNECT|LOCAL_LINE|LE_BUFFER)'
                  r'_X(\d+)_Y(\d+)_N(\d+)(?:_I(\d+))?$')


def yaddr(y):
    cr = y - 2
    g, s = cr // 3, cr % 3
    return g, s, (6 - g) if s == 2 else (7 - g)


def reg_geom(y, dy):
    """MUX-cell Y-address geometry -> (group, slot, bp).  MUST stay
    identical to c4_pip_pattern_mine.reg_geom: attach end (y+dy) for
    downward wires (dy>0), name-Y otherwise."""
    if dy > 0 and 2 <= y + dy <= 21:
        return yaddr(y + dy)
    return yaddr(y)


def r4_geom(y):
    cr = y - 2
    g, s = cr // 3, cr % 3
    bp = 7 - g if s == 0 else 6 - g
    extra = (66 + (1 if g > 0 else 0)) if s == 0 else (-70 if s == 1 else 0)
    return g, s, bp, extra


def load_c4_table():
    """(I, src, dx, dy, slot) -> {'pattern': {'A': [R..], 'B': [R..],
    'C': [(R, bp)..]}, 'ambiguous': bool, 'mined_from': str}

    The dy-less legacy candidates file (results/
    c4_inz_pip_voting_candidates.json) is NOT loadable any more — the
    2026-07-07 probe showed dy-less classes mix attach points and
    default pips; scoring them would repeat the closed negative."""
    table = {}
    for k, v in json.load(open(PATTERN_PATH))['classes'].items():
        m = CK.match(k)
        if not m:
            sys.exit(f"pattern table has dy-less key '{k}' — re-run "
                     "c4_pip_pattern_mine.py (post-2026-07-07, dy in key)")
        key = (int(m.group(1)), m.group(2), int(m.group(3)),
               int(m.group(4)), int(m.group(5)))
        table[key] = {
            'A': [r['R'] for r in v['pattern']['A']],
            'B': [r['R'] for r in v['pattern']['B']],
            'C': [(r['R'], r['bp']) for r in v['pattern']['C']],
            'ambiguous': v.get('ambiguous_geom', False),
            'mined_from': v.get('mined_from', 'neorv32')}
    return table, 'pattern'


def class_name(key):
    return (f"C4,I={key[0]},src={key[1]},dx={key[2]},dy={key[3]},"
            f"slot={key[4]}")


def predict_c4_pip(table, prev_wire, wire):
    """(key, cells) implied by pip prev_wire->wire; None if not a C4 I!=0
    pip; (key, None) if the pip is C4 I!=0 but its class is unmined."""
    mb = WIRE.match(wire)
    if not mb or mb.group(1) != 'C4' or not mb.group(5):
        return None
    x, y, i = int(mb.group(2)), int(mb.group(3)), int(mb.group(5))
    if i == 0 or x not in CB or not 2 <= y <= 21:
        return None
    ma = WIRE.match(prev_wire)
    if not ma:
        return None
    dy = int(ma.group(3)) - y
    _, s, _ = yaddr(y)                       # key slot = target-Y slot
    g, _, bp = reg_geom(y, dy)               # cell geometry = attach-end
    key = (i, ma.group(1), int(ma.group(2)) - x, dy, s)
    ent = table.get(key)
    if ent is None:
        return key, None
    cells = [(CB[x] + R + 3 * g, bp) for R in ent['A']]
    cells += [(CB[x] + R, bp) for R in ent['B']]
    cells += [(CB[x] + R + 3 * g, b) for R, b in ent['C']]
    return key, cells


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


class C4Acc:
    """Full-pattern accumulator over one held-out dataset.

    dataset: name matched against each class's 'mined_from' — a class is
    never scored on its own mining data (counted as 'skipped_self' so
    coverage stays honest).
    """

    def __init__(self, dataset):
        self.dataset = dataset
        self.cell_hit = collections.Counter()
        self.cell_tot = collections.Counter()
        self.inst_full = collections.Counter()
        self.inst_tot = collections.Counter()
        self.uncovered = collections.Counter()   # unmined class keys
        self.skipped_self = 0
        self.pips_total = 0

    def score_seq(self, table, seq, cells):
        self.score_pips(table, zip(seq, seq[1:]), cells)

    def score_pips(self, table, pips, cells):
        seen = set()
        for a, b in pips:
            p = predict_c4_pip(table, a, b)
            if not p:
                continue
            key, pred = p
            if (key, b) in seen:
                continue
            seen.add((key, b))
            self.pips_total += 1
            if pred is None:
                self.uncovered[key] += 1
                continue
            if table[key]['mined_from'] == self.dataset:
                self.skipped_self += 1
                continue
            ok = True
            for c in pred:
                self.cell_tot[key] += 1
                hit = c in cells
                self.cell_hit[key] += hit
                ok &= hit
            self.inst_tot[key] += 1
            self.inst_full[key] += ok

    def report(self, table, title):
        print(f"=== {title} ===")
        th = tt = fi = ft = 0
        for k in sorted(self.inst_tot, key=lambda k: -self.inst_tot[k]):
            amb = " [ambiguous_geom]" if table[k]['ambiguous'] else ""
            print(f"{class_name(k)}: cells {self.cell_hit[k]}/{self.cell_tot[k]}"
                  f"  inst-full {self.inst_full[k]}/{self.inst_tot[k]}{amb}")
            th += self.cell_hit[k]; tt += self.cell_tot[k]
            fi += self.inst_full[k]; ft += self.inst_tot[k]
        cov = sum(self.inst_tot.values())
        print(f"TOTAL cells TP {th}/{tt}" +
              (f" = {th/tt*100:.0f}%  (MISS = write-side FP risk: {tt-th})"
               if tt else ""))
        print(f"TOTAL inst-full {fi}/{ft}" + (f" = {fi/ft*100:.0f}%" if ft else ""))
        print(f"coverage: {cov + self.skipped_self}/{self.pips_total} "
              f"C4 I!=0 pip instances covered"
              + (f" = {(cov+self.skipped_self)/self.pips_total*100:.0f}%"
                 if self.pips_total else "")
              + f"  (scored held-out: {cov}, mined-here so unscored: "
                f"{self.skipped_self})")
        if self.uncovered:
            top = ", ".join(f"{class_name(k)}({n})" for k, n in
                            self.uncovered.most_common(6))
            print(f"top unmined classes: {top}")
        print()

    def as_dict(self, table):
        return {class_name(k): {
                    'cell_hit': self.cell_hit[k], 'cell_tot': self.cell_tot[k],
                    'inst_full': self.inst_full[k], 'inst_tot': self.inst_tot[k],
                    'ambiguous_geom': table[k]['ambiguous']}
                for k in self.inst_tot}


def corpus_designs():
    db = sqlite3.connect(os.path.join(REPO, 'results/ep4ce6_bitdb.sqlite'))
    cur = db.cursor()
    cells = collections.defaultdict(set)
    for eid, off, bp in cur.execute(
            "SELECT experiment_id,byte_offset,bit_position FROM bit_mapping "
            "WHERE experiment_id IN (SELECT experiment_id FROM routing_paths)"):
        if off >= 5282 and (off - 32) % 210 < 208:
            cells[eid].add((off, bp))
    for eid, pj in cur.execute("SELECT experiment_id, path_json FROM routing_paths"):
        yield seq_of_stalist(json.loads(pj)), cells[eid]


def leftward_builds():
    builds = {}
    for fn in glob.glob(os.path.join(REPO, 'tmp/r4_leftward/*.wires.json')):
        tag = os.path.basename(fn)[:-11]
        cf = fn.replace('.wires.json', '.cells.json')
        if os.path.exists(cf):
            builds[tag] = (json.load(open(fn)),
                           set(map(tuple, json.load(open(cf)))))
    return builds


def mode_corpus(table=None):
    if table is None:
        table, src = load_c4_table()
        print(f"C4 table: {src}")
    acc = C4Acc('corpus')
    for seq, cells in corpus_designs():
        acc.score_seq(table, seq, cells)
    acc.report(table, "C4 full-pattern holdout vs 980-route bitdb corpus")
    return acc


def mode_neorv32(table=None):
    if table is None:
        table, src = load_c4_table()
        print(f"C4 table: {src}")
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import pip_voting_neorv32 as pv
    acc = C4Acc('neorv32')
    acc.score_pips(table, pv.parse_pips(), pv.xor_cells())
    acc.report(table, "C4 full-pattern holdout vs NEORV32 gold (40k census)")
    return acc


def mode_leftward(table=None):
    if table is None:
        table, src = load_c4_table()
        print(f"C4 table: {src}")
    builds = leftward_builds()
    tags = sorted(builds)
    # --- C4 full-pattern on ALL builds (no class was mined from them) ---
    acc = C4Acc('leftward')
    for tag in tags:
        seq, cells = builds[tag]
        acc.score_seq(table, seq, cells)
    print(f"builds: {len(builds)}")
    acc.report(table, "C4 full-pattern holdout vs leftward builds")
    # --- R4 wire-law, half-split holdout for freshly mined I=24/31 ---
    score_tags = tags[1::2]
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
            tot[i] += 1
            hit[i] += any(c in cells for c in pred)
    print(f"=== R4 wire-law (either pair cell) on odd-half leftward builds "
          f"({len(score_tags)}) ===")
    for i in sorted(tot):
        star = "  <== NEW" if i in (24, 29, 31) else ""
        print(f"I={i}: {hit[i]}/{tot[i]}{star}")
    return acc


def mode_scores():
    table, src = load_c4_table()
    print(f"C4 table: {src}")
    accs = [mode_corpus(table), mode_neorv32(table), mode_leftward(table)]
    # merged per-class holdout confidence for the write prototype
    merged = {}
    for k in set().union(*(a.inst_tot for a in accs)):
        ch = sum(a.cell_hit[k] for a in accs)
        ct = sum(a.cell_tot[k] for a in accs)
        fi = sum(a.inst_full[k] for a in accs)
        ft = sum(a.inst_tot[k] for a in accs)
        merged[class_name(k)] = {
            'cell_hit': ch, 'cell_tot': ct, 'cell_rate': round(ch / ct, 3),
            'inst_full': fi, 'inst_tot': ft,
            'inst_full_rate': round(fi / ft, 3) if ft else 0.0,
            'ambiguous_geom': table[k]['ambiguous'],
            'mined_from': table[k]['mined_from']}
    with open(SCORES_PATH, 'w') as f:
        json.dump({'table_source': src,
                   'holdout_policy': 'a class is never scored on its own '
                                     'mining dataset (mined_from)',
                   'per_set': {a.dataset: a.as_dict(table) for a in accs},
                   'merged': merged}, f, indent=1)
    print(f"-> {SCORES_PATH}")


if __name__ == '__main__':
    mode = sys.argv[1] if len(sys.argv) > 1 else 'corpus'
    {'corpus': mode_corpus, 'neorv32': mode_neorv32, 'leftward': mode_leftward,
     'scores': mode_scores}[mode]()
