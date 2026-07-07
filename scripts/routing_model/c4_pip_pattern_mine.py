#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Full MUX-pattern miner for C4 I!=0 pip classes (Step 1 of write-path loop).

Extends pip_voting_neorv32.py from "top 1-2 candidate cells" to the
COMPLETE per-class cell pattern, which is what a write path must emit.
Class key: (I, src_type, dx, DY, slot) — pip-conditioned (Pitfall: MUX
config is per-DRIVER, not per-wire; dead_class_pip_conditioned_remine).

DY = prev_y - y (the driver's attach offset along the wire) was added
2026-07-07 after the c4_mux_default_probe.py multi-driver analysis showed
R sets are dy-conditioned: e.g. class (1,C4,dx=0,slot0) dy=-4 ->
{3919,4550} invariant across 5 columns while dy=-3 -> {4549}; slot2 shows
the same shape shifted by 67.  Without dy the classes mix attach points
(and mix default-input pips that need ZERO cells), which poisoned pos
coverage and produced the fresh-gate failure (memo
c4_pip_write_loop_closed_2026_07_07).  Default pips are expected to
surface as dy-classes with NO candidates — that is correct write-side
behaviour (emit nothing), not a mining failure.

Three geometric families are scanned per class (all column-relative,
candidate byte = COLUMN_BASE[x] + ...):

  A: off = CB[x] + R + 3*group, bp = universal Y-address bp of target Y
     (the known C4 I=0 shape; companions at R+420/R+630 land here too)
  B: off = CB[x] + R (flat, no group slope), bp = Y-address bp
  C: off = CB[x] + R + 3*group, bp = FIXED (independent of Y)

HOLDOUT VERDICT 2026-07-07 (pip_prediction_gate.py): family A survives
held-out scoring (~86% cell TP); family B is empty; family C entries FAIL
holdout across the board (e.g. I=1<-C4 slot1: 0/123) — they are mining-set
confounds.  They are still emitted here for the record, but the write
prototype must use family A only.

Two independent mining datasets, two independent holdouts:

  --data neorv32   NEORV32 gold XOR + 40k STA census (default).  Covers
                   the sparse-design classes (mostly src=LE_BUFFER dx=0).
  --data corpus    bitdb 980-route green-zone corpus (routing_paths +
                   bit_mapping).  Covers the chained-driver classes
                   (src=C4 / src=R24) that dominate real routing but never
                   pass discrimination in the single NEORV32 gold.
  --data both      mine both, merge (neorv32 wins on key conflict), tag
                   every class with 'mined_from' so the gate can score
                   each class ONLY on data it was not mined from.

Discriminated voting per cell: positive coverage over class instances
>= POS_MIN and hit rate over same-slot other-I wire instances <= NEG_MAX
(negatives kill LAB-activity confounds).  Classes whose instances span
<2 distinct groups cannot distinguish A/B/C — flagged 'ambiguous_geom'
and refused by the write prototype.

Calibration gates (hard-fail, per dataset): C4 I=0 <- LE_BUFFER dx=0 must
recover R = 1519 + _C4_SLOT_BASE in family A on >=2 slots.

Output: results/c4_pip_pattern_table.json
"""
import os
import sys
import json
import sqlite3
import argparse
import collections

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(REPO, 'fuzz'))
sys.path.insert(0, HERE)
import bitstream  # noqa: E402
import config  # noqa: E402
import pip_voting_neorv32 as pv  # noqa: E402

CB = config.COLUMN_BASE
SB = bitstream._C4_SLOT_BASE
DB = os.path.join(REPO, 'results/ep4ce6_bitdb.sqlite')
OUT = os.path.join(REPO, 'results/c4_pip_pattern_table.json')
POS_MIN, NEG_MAX, MIN_N = 0.84, 0.08, 7
R_LO, R_HI = -7350, 14700


class Dataset:
    """Uniform view over either mining dataset.

    Instances are (ctx, x, group, bp_y); ctx selects the cell universe a
    hit is tested against (None = the single NEORV32 gold XOR set,
    route-id = that route's diff cells in the corpus).
    """

    def __init__(self, name, inst, winst, cbp_of_ctx):
        self.name = name
        self.inst = inst          # key -> set((ctx, x, g, bp))
        self.winst = winst        # (t, I, slot) -> set((ctx, x, g, bp))
        self.cbp = cbp_of_ctx     # ctx -> {bp: set(off)}

    def negatives(self, key):
        t, i, pt, dx, dy, s = key
        neg = set()
        for (tt, ii, ss), ws in self.winst.items():
            if tt == t and ss == s and ii != i:
                neg |= ws
        return neg - self.inst.get(key, set())


def cells_by_bp(cells):
    d = collections.defaultdict(set)
    for off, bp in cells:
        d[bp].add(off)
    return d


def reg_geom(yb, dy):
    """Y-address geometry of the MUX config cell -> (group, slot, bp).

    Anchor-hunt (c4_downward_anchor_hunt.py, 2026-07-07): DOWNWARD C4
    wires (driver attaches at the high end, dy>0) place the MUX cell at
    the Y-address of the ATTACH end (yb+dy), not the wire-name end.
    Upward/level pips keep the name-Y register — that is what produced
    the first fresh-gold write PASS.  Falls back to name-Y if the attach
    end leaves the 2..21 fabric.  The KEY still records the target-Y
    slot (bijective with attach slot at fixed dy), so class partitions
    are unchanged; only the stored (group, bp) that families A/C predict
    on move to the attach end.
    """
    if dy > 0 and 2 <= yb + dy <= 21:
        return pv.yaddr(yb + dy)
    return pv.yaddr(yb)


def instances_dy(pips, ctx):
    """(t, I, src_t, dx, dy, slot) -> {(ctx, x, g, bp)}; plus per-(t,I,slot)
    wire sets (negatives stay dy-agnostic: any same-slot other-I wire).

    (group, bp) follow reg_geom (attach-end for downward wires); the key
    slot is the target-Y slot."""
    inst = collections.defaultdict(set)
    winst = collections.defaultdict(set)
    for a, b in pips:
        ma, mb = pv.WPARSE.match(a), pv.WPARSE.match(b)
        if not ma or not mb:
            continue
        tb, xb, yb = mb.group(1), int(mb.group(2)), int(mb.group(3))
        ib = int(mb.group(5)) if mb.group(5) else None
        if tb != 'C4' or xb not in CB or not 2 <= yb <= 21:
            continue
        _, s, _ = pv.yaddr(yb)                 # key slot = target-Y slot
        dx = int(ma.group(2)) - xb
        dy = int(ma.group(3)) - yb
        g, _, bp = reg_geom(yb, dy)            # cell geometry = attach-end
        inst[(tb, ib, ma.group(1), dx, dy, s)].add((ctx, xb, g, bp))
        winst[(tb, ib, s)].add((ctx, xb, g, bp))
    return inst, winst


def load_neorv32():
    cells = pv.xor_cells()
    print(f"neorv32: XOR CRAM cells {len(cells)}")
    inst, winst = instances_dy(pv.parse_pips(), None)
    return Dataset('neorv32', dict(inst), dict(winst),
                   {None: cells_by_bp(cells)})


def load_corpus():
    db = sqlite3.connect(DB)
    cur = db.cursor()
    cells = collections.defaultdict(set)
    for eid, off, bp in cur.execute(
            "SELECT experiment_id,byte_offset,bit_position FROM bit_mapping "
            "WHERE experiment_id IN (SELECT experiment_id FROM routing_paths)"):
        if off >= 5282 and (off - 32) % 210 < 208:
            cells[eid].add((off, bp))
    inst = collections.defaultdict(set)
    winst = collections.defaultdict(set)
    nroutes = 0
    for eid, pj in cur.execute("SELECT experiment_id, path_json FROM routing_paths"):
        if eid not in cells:
            continue
        nroutes += 1
        seq = []
        for e in json.loads(pj):
            loc = e.get('location', '')
            if pv.WPARSE.match(loc) and (not seq or seq[-1] != loc):
                seq.append(loc)
        i2, w2 = instances_dy(zip(seq, seq[1:]), eid)
        for k, v in i2.items():
            inst[k] |= v
        for k, v in w2.items():
            winst[k] |= v
    print(f"corpus: {nroutes} routes with cells")
    return Dataset('corpus', dict(inst), dict(winst),
                   {eid: cells_by_bp(cs) for eid, cs in cells.items()})


def scan(ds, pos, neg, family, pos_min=POS_MIN, neg_max=NEG_MAX):
    """All (R[, bp]) passing discrimination for one family."""
    def addr(x, g, bpy, R, bp_fix):
        slope = 0 if family == 'B' else 3 * g
        return CB[x] + R + slope, (bp_fix if bp_fix is not None else bpy)

    def cand_counter(insts, bp_fix):
        # each instance is unique in the set, so counter == positive hits
        cnt = collections.Counter()
        for ctx, x, g, bpy in insts:
            slope = 0 if family == 'B' else 3 * g
            bp = bp_fix if bp_fix is not None else bpy
            base = CB[x] + slope
            for off in ds.cbp[ctx].get(bp, ()):
                r = off - base
                if R_LO <= r < R_HI:
                    cnt[r] += 1
        return cnt

    def hits(insts, R, bp_fix):
        n = 0
        for ctx, x, g, bpy in insts:
            off, bp = addr(x, g, bpy, R, bp_fix)
            n += off in ds.cbp[ctx].get(bp, ())
        return n

    out = []
    for bp_fix in (range(8) if family == 'C' else [None]):
        for R, ph in cand_counter(pos, bp_fix).items():
            if ph / len(pos) < pos_min:
                continue
            nh = hits(neg, R, bp_fix)
            if nh / max(1, len(neg)) <= neg_max:
                rec = {'R': R, 'pos': round(ph / len(pos), 3),
                       'neg': round(nh / max(1, len(neg)), 3)}
                if bp_fix is not None:
                    rec['bp'] = bp_fix
                out.append(rec)
    return sorted(out, key=lambda r: (-r['pos'], r['neg'], r['R']))


def dedupe_c(a_cells, c_cells, pos):
    """Drop family-C entries that predict the identical cell set as some
    family-A entry over these instances (single-group shadows)."""
    a_sets = [frozenset((CB[x] + rec['R'] + 3 * g, bpy)
                        for _, x, g, bpy in pos) for rec in a_cells]
    return [rec for rec in c_cells
            if frozenset((CB[x] + rec['R'] + 3 * g, rec['bp'])
                         for _, x, g, bpy in pos) not in a_sets]


def calibrate(ds):
    ok = 0
    for s in (1, 2):
        # dy-pooled: merge all dy variants of C4 I=0 <- LE_BUFFER dx=0
        # (the known law is dy-independent for I=0 self-column drivers)
        pos, neg = set(), set()
        for k in ds.inst:
            if k[:4] == ('C4', 0, 'LE_BUFFER', 0) and k[5] == s:
                pos |= ds.inst[k]
                neg |= ds.negatives(k)
        neg -= pos
        if len(pos) < 6:
            continue
        # relaxed thresholds for the KNOWN law (NEORV32 slot1 sits at
        # pos .83 / neg .125 — same values pip_voting_neorv32 gates on)
        found = scan(ds, pos, neg, 'A', pos_min=0.80, neg_max=0.15)
        true_r = 1519 + SB[s]
        if any(abs(r['R'] - true_r) <= 1 for r in found):
            ok += 1
            print(f"{ds.name} calibration slot {s}: true R={true_r} recovered OK")
    if ok < 2:
        sys.exit(f"CALIBRATION FAILED on {ds.name} — do not trust output")


def mine(ds):
    calibrate(ds)
    results = {}
    keys = sorted((k for k in ds.inst if k[0] == 'C4' and k[1] != 0
                   and len(ds.inst[k]) >= MIN_N),
                  key=lambda k: -len(ds.inst[k]))
    for key in keys:
        t, i, pt, dx, dy, s = key
        pos, neg = ds.inst[key], ds.negatives(key)
        groups = len({g for _, _, g, _ in pos})
        a = scan(ds, pos, neg, 'A')
        b = scan(ds, pos, neg, 'B')
        c = dedupe_c(a, scan(ds, pos, neg, 'C'), pos)
        if not (a or b or c):
            continue
        name = f"C4,I={i},src={pt},dx={dx},dy={dy},slot={s}"
        results[name] = {
            'pos_n': len(pos), 'neg_n': len(neg), 'groups': groups,
            'ambiguous_geom': groups < 2, 'mined_from': ds.name,
            'pattern': {'A': a, 'B': b, 'C': c}}
        print(f"[{ds.name}] {name}: n={len(pos)} groups={groups} "
              f"A={[(r['R'], r['pos']) for r in a]} "
              f"B={[(r['R'], r['pos']) for r in b]} "
              f"C={[(r['R'], r['bp'], r['pos']) for r in c]}")
    return results


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--data', choices=['neorv32', 'corpus', 'both'],
                    default='both')
    args = ap.parse_args()

    merged = {}
    if args.data in ('corpus', 'both'):
        merged.update(mine(load_corpus()))
    if args.data in ('neorv32', 'both'):
        # neorv32 wins on conflict: its negatives saw far more wire diversity
        merged.update(mine(load_neorv32()))

    with open(OUT, 'w') as f:
        json.dump({
            'method': 'pip-conditioned discriminated voting, full-pattern scan',
            'families': {
                'A': 'off=CB[x]+R+3*group, bp=Y-address bp of target Y',
                'B': 'off=CB[x]+R (flat), bp=Y-address bp',
                'C': 'off=CB[x]+R+3*group, bp=fixed '
                     '(HOLDOUT-FALSIFIED — do not write)'},
            'thresholds': {'pos_min': POS_MIN, 'neg_max': NEG_MAX,
                           'min_n': MIN_N},
            'mining_data': args.data,
            'classes': merged}, f, indent=1)
    print(f"\n{len(merged)} classes -> {OUT}")


if __name__ == '__main__':
    main()
