# SPDX-License-Identifier: GPL-3.0-or-later
"""Task H — NEORV32 edge coverage report.

Cross-reference the 12,976 strict-deduped NEORV32 edges (Plan D' dryrun
output) against the merged sig-cache (`route_cells_full.json`) and report:

  - total edges vs covered edges (7-tuple exact match)
  - covered-by-legacy (sn=0 lift, green-zone 15 islands)
  - covered-by-nv (factory-grown Plan D')
  - uncovered — these need either more factory compiles or fallback
  - breakdown by port (dataa/datab/datac/datad)
  - breakdown by jailbreak zone (X∈{5,9,14,30,32,33}, Y=15)
  - top-N uncovered sources (where factory should focus next)

Reads edge list from results/plan_d_prime_edges.json (the strict set that
was fed to the factory).
"""
import json, sys
from pathlib import Path
from collections import Counter, defaultdict

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
import route_signatures

EDGES = ROOT / 'results' / 'plan_d_prime_edges.json'
JAIL_X = {5, 9, 14, 30, 32, 33}
JAIL_Y = {15}


def load_edges():
    raw = json.loads(EDGES.read_text())
    # Stored as {"strict_edges_sorted": [[sx,sy,sn,src_type,dx,dy,dn,port], ...]}
    return [tuple(e) for e in raw['strict_edges_sorted']]


def norm_n(e):
    """Map odd source N → N-1 (FF in same LE), drop src_type."""
    sx, sy, sn, src_type, dx, dy, dn, port = e
    if sn % 2:
        sn -= 1
    return (sx, sy, sn, dx, dy, dn, port)


def main():
    print('=== NEORV32 edge coverage report ===\n')

    cache = route_signatures.load_cells_full()
    legacy = route_signatures.load_cells() or {}
    print(f'sig-cache (merged 7-tuple): {len(cache):,} entries')
    print(f'legacy (6-tuple, lifted to sn=0): {len(legacy):,} entries\n')

    edges_raw = load_edges()
    edges = [norm_n(e) for e in edges_raw]
    # Dedup again post-norm
    edges_unique = list({e for e in edges
                         if (e[0], e[1], e[2]) != (e[3], e[4], e[5])})
    print(f'edges loaded: {len(edges_raw):,} raw, '
          f'{len(edges_unique):,} after N-norm + self-loop filter\n')

    covered = 0
    covered_legacy = 0
    covered_nv = 0
    uncovered_edges = []
    per_port = Counter()
    per_port_hit = Counter()
    jail_total = 0
    jail_hit = 0
    uncov_src = Counter()
    uncov_dst = Counter()

    for e in edges_unique:
        sx, sy, sn, dx, dy, dn, port = e
        per_port[port] += 1
        jail = (sx in JAIL_X or dx in JAIL_X
                or sy in JAIL_Y or dy in JAIL_Y)
        if jail:
            jail_total += 1

        rk_full = route_signatures._route_key_full(sx, sy, sn, dx, dy, dn, port)
        rk_legacy = route_signatures._route_key(sx, sy, dx, dy, dn, port)

        hit = None
        if rk_full in cache:
            hit = 'full'
            if sn == 0 and rk_legacy in legacy:
                covered_legacy += 1
            else:
                covered_nv += 1
        elif rk_legacy in cache:
            hit = 'legacy-lift'
            covered_legacy += 1

        if hit:
            covered += 1
            per_port_hit[port] += 1
            if jail:
                jail_hit += 1
        else:
            uncovered_edges.append(e)
            uncov_src[(sx, sy, sn)] += 1
            uncov_dst[(dx, dy, dn)] += 1

    total = len(edges_unique)
    print(f'COVERAGE: {covered:,} / {total:,} '
          f'= {covered/total*100:.1f}%')
    print(f'  via legacy green-zone:  {covered_legacy:,}')
    print(f'  via factory (Plan D\'): {covered_nv:,}')
    print(f'  uncovered:              {len(uncovered_edges):,}\n')

    print('per-port coverage:')
    for p in sorted(per_port):
        tot = per_port[p]
        hit = per_port_hit[p]
        print(f'  {p}: {hit:>5} / {tot:>5} = {hit/tot*100:5.1f}%')

    print(f'\njailbreak zone (X∈{{5,9,14,30,32,33}} or Y=15):')
    print(f'  {jail_hit:,} / {jail_total:,} = '
          f'{jail_hit/max(jail_total,1)*100:.1f}% covered')

    print('\ntop 15 uncovered sources (where factory should focus):')
    for (sx, sy, sn), c in uncov_src.most_common(15):
        print(f'  X{sx:2d}Y{sy:2d}N{sn:2d}: {c} uncovered edges')

    print('\ntop 15 uncovered destinations:')
    for (dx, dy, dn), c in uncov_dst.most_common(15):
        print(f'  X{dx:2d}Y{dy:2d}N{dn:2d}: {c} uncovered edges')

    # Distribution: how many sources have partial coverage vs none
    src_total = Counter()
    src_hit = Counter()
    for e in edges_unique:
        key = (e[0], e[1], e[2])
        src_total[key] += 1
    for e in edges_unique:
        if e not in uncovered_edges:  # O(n^2) ok for 13k
            pass
    # Recompute src_hit properly
    uncov_set = set(uncovered_edges)
    src_hit = Counter()
    for e in edges_unique:
        if e not in uncov_set:
            src_hit[(e[0], e[1], e[2])] += 1

    fully_covered = sum(1 for s in src_total if src_hit[s] == src_total[s])
    partial = sum(1 for s in src_total if 0 < src_hit[s] < src_total[s])
    none = sum(1 for s in src_total if src_hit[s] == 0)
    print(f'\nsource-level breakdown ({len(src_total)} unique sources):')
    print(f'  fully covered: {fully_covered}')
    print(f'  partially:     {partial}')
    print(f'  none:          {none}')

    out = ROOT / 'results' / 'nv_edge_coverage.json'
    report = {
        'total_edges': total,
        'covered': covered,
        'covered_legacy': covered_legacy,
        'covered_nv': covered_nv,
        'uncovered_count': len(uncovered_edges),
        'per_port': dict(per_port),
        'per_port_hit': dict(per_port_hit),
        'jail_total': jail_total,
        'jail_hit': jail_hit,
        'uncovered_top_src': uncov_src.most_common(50),
        'uncovered_top_dst': uncov_dst.most_common(50),
        'source_fully_covered': fully_covered,
        'source_partial': partial,
        'source_none': none,
        'unique_sources': len(src_total),
    }
    out.write_text(json.dumps(report, indent=1, default=str))
    print(f'\nwrote {out}')


if __name__ == '__main__':
    main()
