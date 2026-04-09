# SPDX-License-Identifier: GPL-3.0-or-later
"""Task G — Dark R4 I-index miner (passive observation mode).

Strategy:
  1. XOR-diff the full NEORV32 RBF vs nv_zero_global.rbf → cell set D
     (CRAM only, frames 25..1751, CRC slots excluded).
  2. Parse STA dump for every R4_X{wx}_Y{wy}_N{n}_I{i} wire appearing on
     any routing path. Collect unique (wx, wy, i).
  3. For each dark I-index and each wire of that I:
       - locate prev_lab_x + col_start
       - for every candidate BASE b in [0..7350]:
           predict (byte, bp) = _r4_addr(b, wy); cell = (col_start+byte, bp)
           if cell ∈ D → wire votes for b
  4. Aggregate votes per I-index across all its wires.
  5. Report top BASE candidates per dark I. A real BASE should collect
     votes ≥ N_wires_used * 0.5 with a clear winner delta.
  6. Also aggregate per (I, prev_x) to detect X-dependent BASE.

The beauty: this is purely passive — we never ask Quartus to do anything,
we just read what it already wrote into the RBF under real routing pressure.
"""
import os, re, sys, mmap, json
from pathlib import Path
from collections import defaultdict, Counter

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))

from bitstream import (
    _R4_BASE_PREV, _r4_addr, COLUMN_BASE, LAB_X, LAB_Y,
    CRC_PREAMBLE, CRC_FRAME_SIZE, CRC_DATA_SIZE,
    CRC_FIRST_CRAM_FRAME, CRC_LAST_FRAME,
)

NEORV32_RBF = Path('/home/test/see_neorv32_run_linux/output/neorv32_demo.rbf')
BASE_RBF = ROOT / 'results' / 'rbf' / 'nv_zero_global.rbf'
STA_DUMP = Path('/tmp/neorv32_timing_big.txt')
OUT = ROOT / 'results' / 'r4_dark_mine.json'

DARK = [5, 6, 9, 24, 28, 29, 30, 31, 32, 33, 104, 116, 125]
BASE_MAX = 7350   # sweep range within a LAB column

R4_WIRE_RE = re.compile(rb'R4_X(\d+)_Y(\d+)_N(\d+)_I(\d+)')


def build_diff_cells():
    """XOR NEORV32 vs nv_zero_global, return dict[off]=bitmask of changed bits.
    Skip header frames and per-frame CRC byte positions."""
    a = NEORV32_RBF.read_bytes()
    b = BASE_RBF.read_bytes()
    assert len(a) == len(b) == 368011
    cells = {}
    for n in range(CRC_FIRST_CRAM_FRAME, CRC_LAST_FRAME + 1):
        s = CRC_PREAMBLE + n * CRC_FRAME_SIZE
        for off in range(s, s + CRC_DATA_SIZE):
            x = a[off] ^ b[off]
            if x:
                cells[off] = x
    return cells


def has_cell(cells, off, bp):
    return off in cells and ((cells[off] >> bp) & 1) == 1


def parse_r4_wires():
    """Stream-scan the 3.6GB STA dump for unique (wx, wy, I) triples."""
    wires = set()
    with open(STA_DUMP, 'rb') as f:
        mm = mmap.mmap(f.fileno(), 0, prot=mmap.PROT_READ)
        for m in R4_WIRE_RE.finditer(mm):
            wx, wy, _, ii = m.groups()
            wires.add((int(wx), int(wy), int(ii)))
        mm.close()
    return wires


def prev_lab_x(wx):
    for j in range(len(LAB_X) - 1, -1, -1):
        if LAB_X[j] < wx:
            return LAB_X[j]
    return None


def mine_base_for_wire(cells, prev_x, wy):
    """Return set of candidate BASE values (within [0..BASE_MAX]) that predict
    a cell in the diff set for this (prev_x, wy) wire."""
    if prev_x not in COLUMN_BASE:
        return set()
    col_start = COLUMN_BASE[prev_x] - 136
    hits = set()
    for base in range(BASE_MAX + 1):
        byte_off, bp = _r4_addr(base, wy)
        off = col_start + byte_off
        if off < 0:
            continue
        if has_cell(cells, off, bp):
            hits.add(base)
    return hits


def main():
    print('=== R4 Dark I-index miner (passive NEORV32 scan) ===\n')

    print(f'[1] Building diff cell set vs {BASE_RBF.name}...')
    cells = build_diff_cells()
    total_bits = sum(bin(v).count('1') for v in cells.values())
    print(f'    {len(cells):,} dirty bytes, {total_bits:,} set cells\n')

    print(f'[2] Parsing R4 wires from STA ({STA_DUMP.stat().st_size/1e9:.1f} GB)...')
    wires = parse_r4_wires()
    print(f'    {len(wires):,} unique (wx,wy,I) triples')
    per_i = defaultdict(list)
    for wx, wy, ii in wires:
        per_i[ii].append((wx, wy))
    print(f'    {len(per_i)} distinct I-indices in STA\n')

    print('[3] Per-wire BASE candidate sweep for each dark I-index...')
    report = {}
    for ii in DARK:
        wl = per_i.get(ii, [])
        print(f'\n  I={ii:3d}: {len(wl)} wires')
        if not wl:
            report[ii] = {'n_wires': 0, 'note': 'no wires in STA'}
            continue

        global_votes = Counter()
        per_prev_votes = defaultdict(Counter)
        wires_counted = 0
        wires_counted_per_prev = defaultdict(int)

        for wx, wy in wl:
            px = prev_lab_x(wx)
            if px is None or px not in COLUMN_BASE:
                continue
            hits = mine_base_for_wire(cells, px, wy)
            if not hits:
                continue
            wires_counted += 1
            wires_counted_per_prev[px] += 1
            for b in hits:
                global_votes[b] += 1
                per_prev_votes[px][b] += 1

        top_global = global_votes.most_common(10)
        per_prev_top = {
            px: (wires_counted_per_prev[px], per_prev_votes[px].most_common(3))
            for px in per_prev_votes
        }

        if top_global:
            win_b, win_v = top_global[0]
            frac = win_v / max(wires_counted, 1)
            status = 'STRONG' if frac >= 0.6 else ('WEAK' if frac >= 0.3 else 'NOISE')
        else:
            win_b, win_v, frac, status = None, 0, 0.0, 'DEAD'

        print(f'    wires with ≥1 hit: {wires_counted}/{len(wl)}')
        print(f'    top global: {top_global[:5]}  [{status}]')
        if win_b is not None:
            print(f'    best BASE={win_b} hits={win_v}/{wires_counted} ({frac*100:.0f}%)')

        # X-dependent detection
        x_dep = False
        if len(per_prev_top) >= 3:
            per_col_winners = [c.most_common(1)[0][0]
                               for c in per_prev_votes.values()
                               if c]
            if len(set(per_col_winners)) > 1:
                x_dep = True
                print(f'    ⚠ X-DEPENDENT: per-col winners vary: {Counter(per_col_winners).most_common(5)}')

        report[ii] = {
            'n_wires_sta': len(wl),
            'n_wires_with_hit': wires_counted,
            'top_global': top_global[:10],
            'best_base': win_b,
            'best_hits': win_v,
            'best_fraction': frac,
            'status': status,
            'x_dependent': x_dep,
            'per_prev_col': {
                str(px): {'n_wires': n, 'top': t}
                for px, (n, t) in per_prev_top.items()
            },
        }

    OUT.write_text(json.dumps(report, indent=1))
    print(f'\n[4] Report written: {OUT}')

    print('\n=== SUMMARY ===')
    strong = [i for i in DARK if report[i].get('status') == 'STRONG']
    weak = [i for i in DARK if report[i].get('status') == 'WEAK']
    noise = [i for i in DARK if report[i].get('status') == 'NOISE']
    dead = [i for i in DARK if report[i].get('status') in ('DEAD', None)]
    print(f'  STRONG (≥60% hit, ready to add): {strong}')
    print(f'  WEAK   (30-60%, needs review)  : {weak}')
    print(f'  NOISE  (<30%, ambiguous)        : {noise}')
    print(f'  DEAD   (no wire or no hit)      : {dead}')
    xd = [i for i in DARK if report[i].get('x_dependent')]
    if xd:
        print(f'  ⚠ X-dependent BASE suspected: {xd}')


if __name__ == '__main__':
    main()
