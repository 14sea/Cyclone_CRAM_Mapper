#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Mine dead-class (R24 / C16 / C4 I!=0) pip cells from the EXISTING bitdb.

No Quartus, no flash: the 980-route green-zone corpus (bitdb
`routing_paths` STA sequences + `bit_mapping` per-experiment diff cells)
already exercised the "dead" route classes — long-span sparse routes go
R24/C16/C4, not R4 (the 2026-05-31 Method-3 pilot observation, inverted
into an asset).  The legacy `_R24_FIXED_OFFSETS` / `_C4_FIXED_OFFSETS`
tables were CRC-byte junk; the REAL cells were in this corpus all along.

Pipeline:
  1. Per-route ordered wire sequence from `routing_paths.path_json`
     (STA rows; `location` column carries the wire name).
  2. Per-route CRAM cell set from `bit_mapping` (off>=5282, CRC excluded).
  3. Pips grouped by identical route-support (co-occurrence classes);
     iso(class) = intersection(cells of routes containing it) minus
     union(cells of all other routes).
  4. Within a co-occurrence chain, split cells to pips by the universal
     Y-address bp of each pip's target wire Y (unique-bp assignment).
  5. Per (type, x, I, slot): candidate bases B with off == B + 3*group
     consistent across >=2 DISTINCT groups.

Key structural findings this encodes (2026-07-06):
  - MUX config is PIP-conditioned (per-driver), not per-wire: per-wire
    intersection is EMPTY at high support (e.g. R24_X19_Y12_N0_I0,
    support 420) while per-pip attribution isolates cells.
  - Dead-class cells follow the universal Y-address bp AND the
    base + 3*group byte law (same shape as C4 I=0 / R4).
  - Cross-validates pip_voting_neorv32.py: C4 I=1 slot=2 bases
    184224/249114 == COLUMN_BASE[16|25] + 4062 (NEORV32 scan: R=4062).

Calibration figure: on C4 I=0 the true base (LAB_CRAM_END + slot_base)
is recovered in the candidate set for 13/25 (x,slot) groups with >=2
distinct Y — recall-limited by corpus Y-diversity, precision is high.

Output: results/bitdb_pip_base_candidates.json
"""
import sys, os, json, re, sqlite3, collections

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(REPO, 'fuzz'))
import config  # noqa: E402

DB = os.path.join(REPO, 'results/ep4ce6_bitdb.sqlite')
OUT = os.path.join(REPO, 'results/bitdb_pip_base_candidates.json')
WIRE = re.compile(r'^(R24|R4|C16|C4|LOCAL_INTERCONNECT|LOCAL_LINE|LE_BUFFER)'
                  r'_X(\d+)_Y(\d+)_N(\d+)(?:_I(\d+))?$')


def yaddr(y):
    cr = y - 2
    g, s = cr // 3, cr % 3
    return g, s, (6 - g) if s == 2 else (7 - g)


def main():
    db = sqlite3.connect(DB)
    cur = db.cursor()

    seq = {}
    for eid, pj in cur.execute(
            "SELECT experiment_id, path_json FROM routing_paths"):
        wires = []
        for e in json.loads(pj):
            loc = e.get('location', '')
            if WIRE.match(loc) and (not wires or wires[-1] != loc):
                wires.append(loc)
        seq[eid] = wires

    cells = collections.defaultdict(set)
    for eid, off, bp in cur.execute(
            "SELECT experiment_id, byte_offset, bit_position FROM bit_mapping "
            "WHERE experiment_id IN (SELECT experiment_id FROM routing_paths)"):
        if off >= 5282 and (off - 32) % 210 < 208:
            cells[eid].add((off, bp))

    pip_support = collections.defaultdict(set)
    for eid, ws in seq.items():
        for a, b in zip(ws, ws[1:]):
            pip_support[(a, b)].add(eid)
    classes = collections.defaultdict(list)   # frozenset(eids) -> [pips]
    for pip, eids in pip_support.items():
        if len(eids) >= 2:
            classes[frozenset(eids)].append(pip)

    all_eids = set(cells)
    samples = collections.defaultdict(list)   # (t,x,I,slot) -> [(group, off)]
    for sig, pips in classes.items():
        withs = [cells[e] for e in sig if e in cells]
        if len(withs) < 2:
            continue
        core = set.intersection(*withs)
        if not core:
            continue
        outside = set()
        for e in all_eids - set(sig):
            outside |= cells[e]
        iso = core - outside
        if not iso:
            continue
        bp_map = collections.defaultdict(set)
        for a, b in pips:
            m = WIRE.match(b)
            t, x, y = m.group(1), int(m.group(2)), int(m.group(3))
            i = int(m.group(5)) if m.group(5) else None
            g, s, bp = yaddr(y)
            bp_map[bp].add((t, x, i, g, s))
        for off, bp in iso:
            cands = bp_map.get(bp, set())
            if len(cands) == 1:      # unique bp -> unambiguous pip in chain
                t, x, i, g, s = next(iter(cands))
                samples[(t, x, i, s)].append((g, off))

    out = {}
    for (t, x, i, s), lst in sorted(samples.items()):
        bygroup = collections.defaultdict(set)
        for g, off in lst:
            bygroup[g].add(off - 3 * g)
        if len(bygroup) < 2:
            continue
        cnt = collections.Counter()
        for bs in bygroup.values():
            for b in bs:
                cnt[b] += 1
        cands = sorted(((b, c) for b, c in cnt.items() if c >= 2),
                       key=lambda kv: -kv[1])
        if cands:
            key = f"{t},x={x},I={i},slot={s}"
            out[key] = {'n': len(lst), 'groups': len(bygroup),
                        'bases': cands[:6]}
            if t in ('R24', 'C16') or (t == 'C4' and i != 0):
                print(f"{key}: n={len(lst)} groups={len(bygroup)} "
                      f"bases={cands[:4]}")
    with open(OUT, 'w') as f:
        json.dump({'model': 'off = base + 3*group, bp = universal Y-address of target wire Y',
                   'note': 'pip-conditioned; bases valid only for the same driver geometry',
                   'classes': out}, f, indent=1)
    print(f"\n{len(out)} (type,x,I,slot) classes -> {OUT}")


if __name__ == '__main__':
    main()
