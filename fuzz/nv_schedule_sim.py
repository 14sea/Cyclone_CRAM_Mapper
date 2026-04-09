# SPDX-License-Identifier: GPL-3.0-or-later
"""Task K — factory scheduling simulator (read-only, no side effects).

Question: the Plan D' factory processes strict_edges_sorted in
lexicographic order. Would sorting the REMAINING edges by per-source
fanout (high-fanout first = "main roads before alleys") reach useful
coverage milestones sooner than the current lex order?

Metrics:
  1. raw edge coverage — trivially identical for both strategies
     (both finish at the same time, both add 1 per compile)
  2. fully-covered sources — the differentiator. Lex order leaves many
     sources partially covered for hours; fanout-first finishes whole
     sources before moving on.
  3. source-fanout-weighted coverage — how much of the total architectural
     "main road" graph is completed.

Uses current factory state as t0 and simulates forward at steady 0.278/s
(measured from last 15 min). Reports clock time to hit 50/70/80/90/95%
milestones under each strategy.
"""
import json, time, os
from pathlib import Path
from collections import Counter, defaultdict

ROOT = Path(__file__).resolve().parent.parent
EDGES = ROOT / 'results' / 'plan_d_prime_edges.json'
STATUS = ROOT / 'results' / 'plan_d_prime_status.json'
RBF = ROOT / 'results' / 'rbf'

# Steady-state rate (from 15-min sliding window earlier measurement)
RATE_PER_SEC = 0.278


def norm(e):
    sx, sy, sn, src_type, dx, dy, dn, port = e
    if sn % 2:
        sn -= 1
    return (sx, sy, sn, dx, dy, dn, port)


def tag_of(e):
    sx, sy, sn, dx, dy, dn, port = e
    return f'nv_pair_X{sx}Y{sy}N{sn}_to_X{dx}Y{dy}N{dn}_{port}'


def simulate(remaining, source_edges_total):
    """Walk through `remaining` in given order. Return list of
    (edge_idx, sources_fully, fanout_covered) snapshots."""
    src_done = defaultdict(int)
    sources_fully = 0
    fanout_covered = 0
    snapshots = []
    for i, e in enumerate(remaining, 1):
        s = (e[0], e[1], e[2])
        src_done[s] += 1
        if src_done[s] == source_edges_total[s]:
            sources_fully += 1
            fanout_covered += source_edges_total[s]
        snapshots.append((i, sources_fully, fanout_covered))
    return snapshots


def main():
    print('=== Task K — factory scheduling simulator ===\n')

    # Load strict edges + dedup with N-norm + drop self-loops (same as Task H)
    data = json.loads(EDGES.read_text())
    raw_edges = [tuple(e) for e in data['strict_edges_sorted']]
    edges_ordered = []   # preserve sorted order post-norm/filter
    seen = set()
    for e in raw_edges:
        ne = norm(e)
        if (ne[0], ne[1], ne[2]) == (ne[3], ne[4], ne[5]):
            continue
        if ne in seen:
            continue
        seen.add(ne)
        edges_ordered.append(ne)
    print(f'edges (N-norm, dedup, no self-loop): {len(edges_ordered):,}')

    # Per-source total edge count (fanout in the strict-edge graph)
    src_total = Counter()
    for e in edges_ordered:
        src_total[(e[0], e[1], e[2])] += 1
    total_src = len(src_total)
    total_fanout = sum(src_total.values())
    print(f'unique sources: {total_src:,}  (total fanout = {total_fanout:,} edges)')

    # Load factory done set — tags in plan_d_prime_status.json
    status = json.loads(STATUS.read_text())
    done_set = set(status['done'])
    print(f'factory done: {len(done_set):,} / {len(edges_ordered):,}')

    # Compute already-completed sources from done_set
    src_done_now = defaultdict(int)
    done_edges = []
    for e in edges_ordered:
        if tag_of(e) in done_set:
            src_done_now[(e[0], e[1], e[2])] += 1
            done_edges.append(e)
    sources_fully_now = sum(1 for s in src_total if src_done_now[s] == src_total[s])
    fanout_covered_now = sum(src_total[s] for s in src_total if src_done_now[s] == src_total[s])
    print(f'  → sources already fully covered: {sources_fully_now:,} ({sources_fully_now/total_src*100:.1f}%)')
    print(f'  → fanout-weighted covered:       {fanout_covered_now:,} ({fanout_covered_now/total_fanout*100:.1f}%)')
    print()

    remaining_set = [e for e in edges_ordered if tag_of(e) not in done_set]
    print(f'remaining edges: {len(remaining_set):,}')

    # Strategy A: lex order (current factory behavior) — remaining_set is already in sorted order
    strat_A = remaining_set[:]

    # Strategy B: sort REMAINING by uncovered-fanout DESC per source,
    # then by source key for tiebreak. Within a source, keep sub-order stable.
    uncov_per_src = Counter()
    for e in remaining_set:
        uncov_per_src[(e[0], e[1], e[2])] += 1
    # Source priority: by current total fanout (not remaining), because a
    # source that's already half-done deserves higher priority to finish
    # than a brand-new one of equal size (it becomes fully-covered faster
    # for each additional edge).
    def src_priority(s):
        return (-src_total[s], uncov_per_src[s], s)
    sorted_srcs = sorted(uncov_per_src, key=src_priority)
    strat_B = []
    src_bucket = defaultdict(list)
    for e in remaining_set:
        src_bucket[(e[0], e[1], e[2])].append(e)
    for s in sorted_srcs:
        strat_B.extend(src_bucket[s])

    # Simulate both
    snaps_A = simulate(strat_A, src_total)
    snaps_B = simulate(strat_B, src_total)

    # Milestones on fully-covered-source fraction (offset by current state)
    milestones = [0.50, 0.60, 0.70, 0.80, 0.90, 0.95]
    now = time.time()

    print('\n=== Milestone ETAs (fully-covered sources) ===')
    print(f'  current: {sources_fully_now}/{total_src} = '
          f'{sources_fully_now/total_src*100:.1f}% @ now')
    print(f'{"":>8} | {"Strategy A (lex)":^22} | {"Strategy B (fanout)":^24} | delta')
    print('-' * 74)
    for m in milestones:
        target = int(m * total_src)
        if target <= sources_fully_now:
            continue

        def find_i(snaps):
            for i, sf, fc in snaps:
                if sf + sources_fully_now >= target:
                    return i
            return None

        ia = find_i(snaps_A)
        ib = find_i(snaps_B)

        def tstr(i):
            if i is None:
                return 'N/A'
            t = i / RATE_PER_SEC
            clock = time.strftime('%H:%M', time.localtime(now + t))
            return f'{t/3600:5.2f}h ({clock})'

        sa = tstr(ia)
        sb = tstr(ib)
        delta = ''
        if ia and ib:
            delta = f'{(ia-ib)/RATE_PER_SEC/3600:+.2f}h'
        print(f'  {int(m*100):>3}%   | {sa:^22} | {sb:^24} | {delta}')

    # Fanout-weighted coverage milestones
    print('\n=== Milestone ETAs (fanout-weighted coverage) ===')
    print(f'  current: {fanout_covered_now:,}/{total_fanout:,} = '
          f'{fanout_covered_now/total_fanout*100:.1f}% @ now')
    print(f'{"":>8} | {"Strategy A (lex)":^22} | {"Strategy B (fanout)":^24} | delta')
    print('-' * 74)
    for m in milestones:
        target = int(m * total_fanout)
        if target <= fanout_covered_now:
            continue

        def find_i(snaps):
            for i, sf, fc in snaps:
                if fc + fanout_covered_now >= target:
                    return i
            return None

        ia = find_i(snaps_A)
        ib = find_i(snaps_B)

        def tstr(i):
            if i is None:
                return 'N/A'
            t = i / RATE_PER_SEC
            clock = time.strftime('%H:%M', time.localtime(now + t))
            return f'{t/3600:5.2f}h ({clock})'

        sa = tstr(ia)
        sb = tstr(ib)
        delta = ''
        if ia and ib:
            delta = f'{(ia-ib)/RATE_PER_SEC/3600:+.2f}h'
        print(f'  {int(m*100):>3}%   | {sa:^22} | {sb:^24} | {delta}')

    # Raw edge milestones (sanity — should be identical)
    print('\n=== Milestone ETAs (raw edge coverage — sanity, should match) ===')
    for m in milestones:
        target_edges = int(m * len(edges_ordered)) - len(done_set)
        if target_edges <= 0:
            continue
        t = target_edges / RATE_PER_SEC
        clock = time.strftime('%H:%M', time.localtime(now + t))
        print(f'  {int(m*100):>3}%  = {int(m*len(edges_ordered)):,} edges @ +{t/3600:.2f}h ({clock})')

    # Top source fanout distribution to understand the delta potential
    print('\n=== Top 15 remaining-fanout sources (Strategy B priority) ===')
    top = uncov_per_src.most_common(15)
    for s, c in top:
        done = src_done_now[s]
        tot = src_total[s]
        mark = '★' if done > 0 else ' '
        print(f'  {mark} X{s[0]:2d}Y{s[1]:2d}N{s[2]:2d}: {c:3d} remaining  '
              f'({done}/{tot} done in this source)')

    # Summary: how concentrated is remaining?
    sorted_fanout = sorted(uncov_per_src.values(), reverse=True)
    cum = 0
    p50 = p80 = None
    total_rem = sum(sorted_fanout)
    for i, v in enumerate(sorted_fanout, 1):
        cum += v
        if p50 is None and cum >= 0.5 * total_rem:
            p50 = i
        if p80 is None and cum >= 0.8 * total_rem:
            p80 = i
            break
    print(f'\nremaining fanout concentration:')
    print(f'  top {p50} sources carry 50% of remaining edges')
    print(f'  top {p80} sources carry 80% of remaining edges')
    print(f'  (out of {len(uncov_per_src):,} sources with remaining work)')

    out = ROOT / 'results' / 'nv_schedule_sim.json'
    out.write_text(json.dumps({
        'rate_per_sec': RATE_PER_SEC,
        'now_sources_full': sources_fully_now,
        'now_fanout_covered': fanout_covered_now,
        'total_sources': total_src,
        'total_fanout': total_fanout,
        'remaining': len(remaining_set),
        'top_15_priority': [
            {'src': f'X{s[0]}Y{s[1]}N{s[2]}', 'remaining': c, 'total': src_total[s]}
            for s, c in top
        ],
        'concentration_p50': p50,
        'concentration_p80': p80,
    }, indent=1))
    print(f'\nwrote {out}')


if __name__ == '__main__':
    main()
