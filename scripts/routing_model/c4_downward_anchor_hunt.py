#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Anchor/window hunt for the DOWNWARD C4 family (dy=+3/+4).

After the dy-key breakthrough (memo c4_dy_key_first_write_pass_2026_07_07)
the downward classes (I=12/14/15/21-23, driver attaches at the wire's
high end) remained 0-for-all under the standard register
(target-column, target-Y bp, base+3*group).  Two prior artifacts point
at a wrong ANCHOR rather than true zero-cell defaults: the X33
MULTI_DEFAULT wires, and I=12 iso cells at weird negative R.

This hunt drops every register assumption:
  1. collect ALL corpus pips onto C4 I!=0 wires with dy>0, n>=2 routes
     (not just multi-driver wires);
  2. isolate per-(wire,driver) cells with a WIDE window: any bp,
     |off - CB[target_x]| < 15000 (covers prev and next LAB columns),
     intersection across the pip's routes minus union over routes not
     containing the wire;
  3. let four candidate registers COMPETE to explain cross-wire
     invariance of the isolated cells within each (I, src, dx, dy)
     class:
       tgtY   : bp == bp(y),        normR = off - CB[x]     - 3*g(y)
       attY   : bp == bp(y+dy),     normR = off - CB[x]     - 3*g(y+dy)
       prev+tgtY: bp == bp(y),      normR = off - CB[prev_x] - 3*g(y)
       prev+attY: bp == bp(y+dy),   normR = off - CB[prev_x] - 3*g(y+dy)
     plus 'other' (isolated cells matching no register's bp).
     Register score per class = best normR support / pips-with-iso.
  4. replication leg: best (class, register, normR) laws re-checked on
     the tmp/r4_leftward builds' downward pips (independent dataset).

Also answers: are the downward DEFAULT verdicts real?  A pip whose WIDE
window has no isolated cells at all is a much stronger zero-cell claim
than the earlier bp-filtered one.

READ-side only.  Fresh golds (tmp/c4_fresh) remain untouched.
Output: results/c4_downward_anchor_hunt.json
"""
import sys, os, json, glob, collections

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(REPO, 'fuzz'))
sys.path.insert(0, HERE)
import config  # noqa: E402
from c4_mux_default_probe import (load_corpus, load_leftward, wire_geom,
                                  yaddr, WIRE)  # noqa: E402

CB = config.COLUMN_BASE
OUT = os.path.join(REPO, 'results/c4_downward_anchor_hunt.json')
WIN = 15000
PHYS = sorted(CB)


def prev_col(x):
    c = [p for p in PHYS if p < x]
    return c[-1] if c else None


def registers(x, y, dy):
    """register name -> (expected bp, normalization base) or None.

    top4Y tests the UNIFIED rule suggested by the first hunt run: the
    MUX Y-address is the wire's TOP (north) end = y+4 for downward
    wires regardless of whether the driver attaches at +3 or +4 (the
    upward family's working register, name-Y, is already its top end).
    """
    g1, s1, bp1 = yaddr(y)
    out = {'tgtY': (bp1, CB[x] + 3 * g1)}
    ya = y + dy
    if 2 <= ya <= 21:
        g2, s2, bp2 = yaddr(ya)
        out['attY'] = (bp2, CB[x] + 3 * g2)
    if dy > 0 and 2 <= y + 4 <= 21:
        g4, s4, bp4 = yaddr(y + 4)
        out['top4Y'] = (bp4, CB[x] + 3 * g4)
    px = prev_col(x)
    if px is not None:
        out['prev+tgtY'] = (bp1, CB[px] + 3 * g1)
        if 2 <= ya <= 21:
            g2, s2, bp2 = yaddr(ya)
            out['prev+attY'] = (bp2, CB[px] + 3 * g2)
    return out


def collect_downward_pips(routes):
    """(W, D) -> set(route_id), restricted to dy>0, n>=2."""
    drv = collections.defaultdict(set)
    has_w = collections.defaultdict(set)
    for rid, (seq, _) in routes.items():
        for w in seq:
            if wire_geom(w):
                has_w[w].add(rid)
        for a, b in zip(seq, seq[1:]):
            gb = wire_geom(b)
            ma = WIRE.match(a)
            if gb and ma and int(ma.group(3)) - gb[1] > 0:
                drv[(a, b)].add(rid)
    return {k: v for k, v in drv.items() if len(v) >= 2}, has_w


def isolate(routes, pips, has_w):
    """(D, W) -> sorted iso cells [(off, bp)] in the WIDE window."""
    all_rids = set(routes)
    ctx_cache = {}
    iso = {}
    for (d, w), rids in sorted(pips.items()):
        x = wire_geom(w)[0]

        def win(cells):
            return {(o, b) for o, b in cells if abs(o - CB[x]) < WIN}
        if w not in ctx_cache:
            c = set()
            for rid in all_rids - has_w[w]:
                c |= win(routes[rid][1])
            ctx_cache[w] = c
        resids = [win(routes[rid][1]) - ctx_cache[w] for rid in sorted(rids)]
        iso[(d, w)] = sorted(set.intersection(*resids))
    return iso


def class_of(d, w):
    x, y, i, g, s, bp = wire_geom(w)
    ma = WIRE.match(d)
    return (i, ma.group(1), int(ma.group(2)) - x, int(ma.group(3)) - y)


def fit_registers(iso):
    """per class: per register, normR support counts over pips."""
    classes = collections.defaultdict(list)
    for (d, w), cells in iso.items():
        classes[class_of(d, w)].append((d, w, cells))
    report = {}
    for key, pips in sorted(classes.items(), key=lambda kv: -len(kv[1])):
        n_iso = sum(1 for _, _, c in pips if c)
        if n_iso < 2:
            continue
        reg_support = {}
        for reg in ('tgtY', 'attY', 'top4Y', 'prev+tgtY', 'prev+attY'):
            cnt = collections.Counter()
            for d, w, cells in pips:
                x, y, i, g, s, bp = wire_geom(w)
                dy = int(WIRE.match(d).group(3)) - y
                regs = registers(x, y, dy)
                if reg not in regs:
                    continue
                ebp, base = regs[reg]
                for off, b in cells:
                    if b == ebp:
                        cnt[off - base] += 1
            if cnt:
                best = cnt.most_common(4)
                reg_support[reg] = {'best': best,
                                    'score': round(best[0][1] / n_iso, 3)}
        name = f"C4,I={key[0]},src={key[1]},dx={key[2]},dy={key[3]}"
        report[name] = {
            'key': list(key),
            'n_pips': len(pips), 'n_with_iso': n_iso,
            'zero_iso_pips': [f"{d} -> {w}" for d, w, c in pips if not c],
            'registers': reg_support}
    return report


def replicate(report):
    """check each class's best (register, normR) on leftward downward pips."""
    routes = load_leftward()
    pips, has_w = collect_downward_pips(routes)
    rows = []
    for name, rec in report.items():
        best_reg = None
        for reg, s in rec['registers'].items():
            if best_reg is None or s['score'] > rec['registers'][best_reg]['score']:
                best_reg = reg
        if not best_reg or rec['registers'][best_reg]['score'] < 0.6:
            continue
        i, src, dx, dy = rec['key']
        normR = rec['registers'][best_reg]['best'][0][0]
        hit = tot = 0
        for (d, w), rids in pips.items():
            if class_of(d, w) != (i, src, dx, dy):
                continue
            x, y, _, g, s, bp = wire_geom(w)
            regs = registers(x, y, dy)
            if best_reg not in regs:
                continue
            ebp, base = regs[best_reg]
            for rid in rids:
                tot += 1
                hit += (base + normR, ebp) in routes[rid][1]
        if tot:
            rows.append({'class': name, 'register': best_reg, 'normR': normR,
                         'leftward': f"{hit}/{tot}"})
    return rows


def main():
    routes = load_corpus()
    print(f"corpus routes: {len(routes)}")
    pips, has_w = collect_downward_pips(routes)
    print(f"downward (dy>0) pips with n>=2: {len(pips)}")
    iso = isolate(routes, pips, has_w)
    n_zero = sum(1 for c in iso.values() if not c)
    print(f"pips with EMPTY wide-window iso (strong zero-cell): "
          f"{n_zero}/{len(iso)}\n")

    report = fit_registers(iso)
    print("=== register competition per class ===")
    for name, rec in report.items():
        print(f"{name}: pips={rec['n_pips']} with_iso={rec['n_with_iso']}")
        for reg, s in sorted(rec['registers'].items(),
                             key=lambda kv: -kv[1]['score']):
            print(f"    {reg:10s} score={s['score']} best={s['best']}")

    rows = replicate(report)
    print("\n=== leftward replication of best laws (score>=0.6) ===")
    for r in rows:
        print(f"  {r['class']} [{r['register']} R={r['normR']}]: "
              f"{r['leftward']}")

    json.dump({'window': WIN, 'n_pips': len(pips), 'n_zero_iso': n_zero,
               'classes': report, 'leftward_replication': rows},
              open(OUT, 'w'), indent=1)
    print(f"\n-> {OUT}")


if __name__ == '__main__':
    main()
