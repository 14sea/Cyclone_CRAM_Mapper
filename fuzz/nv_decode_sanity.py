# SPDX-License-Identifier: GPL-3.0-or-later
"""Task D — decode-sanity check on factory output.

Sample N completed nv_pair_*.rbf, XOR-diff vs a neutral baseline, classify
bytes into:
  - LAB column band (known LAB_X)
  - Non-LAB band (X=15,20,27 M9K/mult)
  - Header / edge-clock band (off < 5282 or outside any known band)
  - CRC frame-slots (pos 208/209 — expected zero after CRC filter)
Flag any sample with > 10% of cells outside LAB bands.
"""
import sys, os, random
from pathlib import Path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import COLUMN_BASE

ROOT = Path(__file__).resolve().parent.parent
RBF = ROOT / 'results' / 'rbf'
BASE = RBF / 'lits_zero_10_10.rbf'
HDR_END = 32 + 25 * 210  # 5282

# LAB band = [col_base-136, col_base-136+7350)
LAB_BANDS = sorted((COLUMN_BASE[x] - 136, COLUMN_BASE[x] - 136 + 7350)
                   for x in COLUMN_BASE)
NONLAB_X = {15, 20, 27}


def classify(off):
    if off < HDR_END:
        return 'header'
    if (off - 32) % 210 >= 208:
        return 'crc_slot'
    for x, (lo, hi) in zip(sorted(COLUMN_BASE), LAB_BANDS):
        if lo <= off < hi:
            return f'lab_x={x}' if x not in NONLAB_X else f'nonlab_x={x}'
    return 'outside'


def diff_cells(a, b):
    cells = []
    for n in range(25, 1752):
        s = 32 + n * 210
        for off in range(s, s + 208):
            x = a[off] ^ b[off]
            if x:
                for bp in range(8):
                    if (x >> bp) & 1:
                        cells.append(off)
    return cells


def main():
    if not BASE.exists():
        print(f'baseline missing: {BASE}')
        return
    zero = BASE.read_bytes()
    samples = sorted(RBF.glob('nv_pair_*.rbf'))
    random.seed(42)
    pick = random.sample(samples, min(20, len(samples)))
    print(f'== decoding {len(pick)} nv_pair samples vs {BASE.name} ==\n')
    warn = 0
    for p in pick:
        cells = diff_cells(p.read_bytes(), zero)
        counts = {}
        for off in cells:
            k = classify(off)
            counts[k] = counts.get(k, 0) + 1
        total = len(cells)
        lab_hits = sum(v for k, v in counts.items() if k.startswith('lab_x'))
        nonlab = sum(v for k, v in counts.items() if k.startswith('nonlab'))
        out = counts.get('outside', 0) + counts.get('header', 0)
        crc = counts.get('crc_slot', 0)
        pct_lab = 100 * lab_hits / total if total else 0
        flag = '!' if pct_lab < 90 else ' '
        if pct_lab < 90:
            warn += 1
        top = sorted(counts.items(), key=lambda x: -x[1])[:4]
        top_s = ' '.join(f'{k}={v}' for k, v in top)
        print(f' {flag} {p.name[:60]:60s} n={total:5d} lab={pct_lab:5.1f}% '
              f'nonlab={nonlab} outside={out} crc={crc}  top: {top_s}')
    print(f'\n=> {warn}/{len(pick)} samples flagged (>10% outside LAB bands)')


if __name__ == '__main__':
    main()
