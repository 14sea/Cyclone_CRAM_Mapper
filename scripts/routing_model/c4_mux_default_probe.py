#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Read-side falsification probe: C4 MUX default-input semantics.

Follow-up to the NEGATIVE write-loop verdict (memo
c4_pip_write_loop_closed_2026_07_07): the (I, src_type, dx, slot) pip key
failed the fresh-gold gate, and forensics suggested some pips need ZERO
config cells (MUX default input).  This probe tests that hypothesis
directly on (same target C4 wire, different driver) samples — READ-side
only, no emitter.

Method (primary = bitdb corpus ONLY; tmp/c4_fresh golds deliberately
untouched so they stay clean for a future default-aware gate):

  For each C4 I!=0 wire W driven by >=2 distinct drivers across routes:
    win(W)   = cells at bp == Y-address bp of W, |off-CB[x]-3g| < 8000
    mw(r)    = route r's CRAM cells ∩ win(W)
    ctx(W)   = union of mw(r') over routes NOT containing W
               (recurring column activity that is not W-specific)
    per driver D over routes r with pip D->W (need n>=2):
      resid(r) = mw(r) - ctx(W)
      iso(W,D) = ∩ resid(r)
    classification:
      CONFIG   iso != {}           consistent W-specific cells (MUX bits)
      DEFAULT  all resid(r) == {}  no W-specific cell whenever D drives
                                   -> zero-cell (default input) evidence
      VARIANT  iso == {} but some resid != {}
                                   -> cells exist but are inconsistent:
                                   context beyond (W, D) — the H2 red flag
      LOW_SUPPORT  n < 2

Hypothesis H1 (default-input) predicts: each multi-driver wire splits
into >=1 CONFIG driver + at most one DEFAULT driver, with few/no VARIANT.
Many VARIANT pips would instead indicate per-(W,D) NON-determinism —
worse than a missing key dimension, and a stop signal for any C4 write
path.

Also reported:
  - class-level translation invariance RE-CHECK restricted to CONFIG
    pips: same (I,src,dx,slot) at different wires -> same R set?
  - replication leg on tmp/r4_leftward builds (independent dataset):
    presence rate of each corpus-CONFIG iso cell when the same exact
    pip occurs there.

Output: results/c4_mux_default_probe.json
"""
import sys, os, json, glob, re, sqlite3, collections

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(REPO, 'fuzz'))
import config  # noqa: E402

CB = config.COLUMN_BASE
OUT = os.path.join(REPO, 'results/c4_mux_default_probe.json')
WIN = 8000
WIRE = re.compile(r'^(R24|R4|C16|C4|LOCAL_INTERCONNECT|LOCAL_LINE|LE_BUFFER)'
                  r'_X(\d+)_Y(\d+)_N(\d+)(?:_I(\d+))?$')


def yaddr(y):
    cr = y - 2
    g, s = cr // 3, cr % 3
    return g, s, (6 - g) if s == 2 else (7 - g)


def wire_geom(w):
    m = WIRE.match(w)
    if not m or m.group(1) != 'C4' or not m.group(5):
        return None
    x, y, i = int(m.group(2)), int(m.group(3)), int(m.group(5))
    if i == 0 or x not in CB or not 2 <= y <= 21:
        return None
    g, s, bp = yaddr(y)
    return x, y, i, g, s, bp


def pip_class(prev, w):
    x, y, i, g, s, bp = wire_geom(w)
    ma = WIRE.match(prev)
    return (i, ma.group(1), int(ma.group(2)) - x, s) if ma else None


def load_corpus():
    db = sqlite3.connect(os.path.join(REPO, 'results/ep4ce6_bitdb.sqlite'))
    cur = db.cursor()
    cells = collections.defaultdict(set)
    for eid, off, bp in cur.execute(
            "SELECT experiment_id,byte_offset,bit_position FROM bit_mapping "
            "WHERE experiment_id IN (SELECT experiment_id FROM routing_paths)"):
        if off >= 5282 and (off - 32) % 210 < 208:
            cells[eid].add((off, bp))
    routes = {}
    for eid, pj in cur.execute("SELECT experiment_id,path_json FROM routing_paths"):
        if eid not in cells:
            continue
        seq = []
        for e in json.loads(pj):
            loc = e.get('location', '')
            if WIRE.match(loc) and (not seq or seq[-1] != loc):
                seq.append(loc)
        routes[eid] = (seq, cells[eid])
    return routes


def load_leftward():
    routes = {}
    for fn in glob.glob(os.path.join(REPO, 'tmp/r4_leftward/*.wires.json')):
        tag = os.path.basename(fn)[:-11]
        cf = fn.replace('.wires.json', '.cells.json')
        if os.path.exists(cf):
            routes[tag] = (json.load(open(fn)),
                           set(map(tuple, json.load(open(cf)))))
    return routes


def mux_window(cells, x, g, bp):
    base = CB[x] + 3 * g
    return {(off, b) for off, b in cells if b == bp and abs(off - base) < WIN}


def probe(routes):
    # W -> driver -> set(route_id); W -> set(route_id containing W anywhere)
    drv = collections.defaultdict(lambda: collections.defaultdict(set))
    has_w = collections.defaultdict(set)
    for rid, (seq, _) in routes.items():
        for w in seq:
            if wire_geom(w):
                has_w[w].add(rid)
        for a, b in zip(seq, seq[1:]):
            if wire_geom(b):
                drv[b][a].add(rid)

    all_rids = set(routes)
    wires = {}
    for w, dmap in sorted(drv.items()):
        if len(dmap) < 2:
            continue
        x, y, i, g, s, bp = wire_geom(w)
        ctx = set()
        for rid in all_rids - has_w[w]:
            ctx |= mux_window(routes[rid][1], x, g, bp)
        dtab = {}
        for d, rids in sorted(dmap.items()):
            resids = [mux_window(routes[rid][1], x, g, bp) - ctx
                      for rid in sorted(rids)]
            iso = set.intersection(*resids) if resids else set()
            if len(rids) < 2:
                cls = 'LOW_SUPPORT'
            elif iso:
                cls = 'CONFIG'
            elif all(not r for r in resids):
                cls = 'DEFAULT'
            else:
                cls = 'VARIANT'
            dtab[d] = {
                'n_routes': len(rids), 'class': cls,
                'iso_R': sorted(off - CB[x] - 3 * g for off, _ in iso),
                'resid_sizes': [len(r) for r in resids],
                'pip_class': str(pip_class(d, w))}
        wires[w] = {'geom': {'x': x, 'y': y, 'I': i, 'group': g,
                             'slot': s, 'bp': bp},
                    'ctx_size': len(ctx), 'drivers': dtab}
    return wires


def summarize(wires):
    cnt = collections.Counter()
    verdict_rows = []
    for w, ent in wires.items():
        classes = [d['class'] for d in ent['drivers'].values()
                   if d['class'] != 'LOW_SUPPORT']
        if len(classes) < 2:
            continue
        c = collections.Counter(classes)
        cnt['wires_scored'] += 1
        cnt['drv_CONFIG'] += c['CONFIG']
        cnt['drv_DEFAULT'] += c['DEFAULT']
        cnt['drv_VARIANT'] += c['VARIANT']
        if c['VARIANT']:
            shape = 'HAS_VARIANT'
        elif c['DEFAULT'] == 0:
            shape = 'ALL_CONFIG'
        elif c['DEFAULT'] == 1:
            shape = 'ONE_DEFAULT'   # H1-consistent
        else:
            shape = 'MULTI_DEFAULT'  # H1-violating
        cnt[f'wire_{shape}'] += 1
        verdict_rows.append((w, shape, dict(c)))
    return cnt, verdict_rows


def class_invariance(wires):
    """CONFIG pips: same class at different wires -> same R set?"""
    bykey = collections.defaultdict(list)
    for w, ent in wires.items():
        for d, rec in ent['drivers'].items():
            if rec['class'] == 'CONFIG':
                bykey[rec['pip_class']].append((w, tuple(rec['iso_R'])))
    out = {}
    for key, lst in sorted(bykey.items()):
        if len(lst) < 2:
            continue
        rsets = collections.Counter(r for _, r in lst)
        out[key] = {'n_wires': len(lst),
                    'distinct_R_sets': len(rsets),
                    'R_sets': {str(list(r)): n for r, n in
                               rsets.most_common()}}
    return out


def replicate_leftward(wires):
    """Check corpus CONFIG iso cells on the independent leftward builds."""
    routes = load_leftward()
    pips = collections.defaultdict(set)   # (prev, w) -> route ids
    for rid, (seq, _) in routes.items():
        for a, b in zip(seq, seq[1:]):
            pips[(a, b)].add(rid)
    rows = []
    for w, ent in wires.items():
        x, g = ent['geom']['x'], ent['geom']['group']
        bp = ent['geom']['bp']
        for d, rec in ent['drivers'].items():
            if rec['class'] != 'CONFIG' or (d, w) not in pips:
                continue
            cells = [(CB[x] + R + 3 * g, bp) for R in rec['iso_R']]
            hit = tot = 0
            for rid in pips[(d, w)]:
                for c in cells:
                    tot += 1
                    hit += c in routes[rid][1]
            rows.append({'pip': f"{d} -> {w}", 'n_builds': len(pips[(d, w)]),
                         'cells_hit': hit, 'cells_tot': tot})
    return rows


def main():
    routes = load_corpus()
    print(f"corpus routes: {len(routes)}")
    wires = probe(routes)
    print(f"multi-driver C4 I!=0 wires probed: {len(wires)}\n")

    cnt, rows = summarize(wires)
    print("=== per-wire shapes (drivers with n>=2 only) ===")
    for w, shape, c in rows:
        print(f"  {w}: {shape} {c}")
    print(f"\n=== summary ===")
    for k in ('wires_scored', 'wire_ONE_DEFAULT', 'wire_ALL_CONFIG',
              'wire_MULTI_DEFAULT', 'wire_HAS_VARIANT',
              'drv_CONFIG', 'drv_DEFAULT', 'drv_VARIANT'):
        print(f"  {k}: {cnt[k]}")

    inv = class_invariance(wires)
    print("\n=== class-level R-set invariance (CONFIG pips) ===")
    for key, rec in inv.items():
        mark = "INVARIANT" if rec['distinct_R_sets'] == 1 else "VARIES"
        print(f"  {key}: {rec['n_wires']} wires, "
              f"{rec['distinct_R_sets']} distinct R-sets -> {mark}")

    rep = replicate_leftward(wires)
    print("\n=== leftward replication of CONFIG iso cells ===")
    th = tt = 0
    for r in rep:
        print(f"  {r['pip']}: {r['cells_hit']}/{r['cells_tot']} "
              f"over {r['n_builds']} builds")
        th += r['cells_hit']; tt += r['cells_tot']
    print(f"  TOTAL {th}/{tt}" + (f" = {th/tt*100:.0f}%" if tt else ""))

    json.dump({'window': WIN,
               'summary': dict(cnt),
               'wires': wires,
               'class_invariance': inv,
               'leftward_replication': rep},
              open(OUT, 'w'), indent=1)
    print(f"\n-> {OUT}")


if __name__ == '__main__':
    main()
