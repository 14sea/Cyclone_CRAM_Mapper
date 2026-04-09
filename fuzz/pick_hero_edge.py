# SPDX-License-Identifier: GPL-3.0-or-later
"""Task I — pick a hero edge for silicon validation.

Selection priorities:
  1. sx == 32 (jailbreak column, CE10-only — maximum symbolic payload)
  2. sn > 0  (non-zero source N, distinguishes "code correct" from "lucky sn=0")
  3. entry present in `route_cells_full.json` (signature cache covers it)
  4. nv_pair RBF exists on disk (factory ground truth for byte-diff check)
  5. dst side preferably LAB_X > 20 (avoids wraparound edge effects)

Falls back through: sx in {32,33} → sx in JAIL_X → sx==32 with sn==0 if nothing else.
"""
import json, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
import route_signatures

RBF_DIR = ROOT / 'results' / 'rbf'
JAIL_X = {5, 9, 14, 30, 32, 33}


def main():
    cache = route_signatures.load_cells_full()
    print(f'cache entries: {len(cache):,}')

    candidates = []
    for key, cells in cache.items():
        head, tail = key.split('->')
        try:
            sx, sy, sn = [int(v) for v in head.split(',')]
            dx, dy, dn, port = tail.split(',')
            dx, dy, dn = int(dx), int(dy), int(dn)
        except ValueError:
            continue
        tag = f'nv_pair_X{sx}Y{sy}N{sn}_to_X{dx}Y{dy}N{dn}_{port}'
        rbf_path = RBF_DIR / f'{tag}.rbf'
        if not rbf_path.exists():
            continue
        priority = 0
        if sx == 32: priority += 100
        elif sx == 33: priority += 80
        elif sx in JAIL_X: priority += 40
        if sn > 0: priority += 20
        if dx == 32: priority += 10
        if dx > 20: priority += 5
        candidates.append((priority, sx, sy, sn, dx, dy, dn, port, len(cells), rbf_path))

    if not candidates:
        print('NO candidates with nv_pair RBF on disk')
        return 1

    candidates.sort(key=lambda c: -c[0])
    print(f'\ntop 10 candidates:')
    for c in candidates[:10]:
        pr, sx, sy, sn, dx, dy, dn, port, nc, _ = c
        print(f'  pri={pr:3d}  X{sx:2d}Y{sy:2d}N{sn:2d} -> X{dx:2d}Y{dy:2d}N{dn:2d}.{port}  ({nc} cells)')

    # Best jailbreak + sn>0 candidate
    best = next((c for c in candidates if c[1] == 32 and c[3] > 0), None)
    if best is None:
        best = next((c for c in candidates if c[1] in JAIL_X and c[3] > 0), None)
    if best is None:
        best = candidates[0]

    pr, sx, sy, sn, dx, dy, dn, port, nc, rbf = best
    print(f'\n=== HERO EDGE ===')
    print(f'  SRC: X{sx}Y{sy}N{sn}  (jailbreak={sx in JAIL_X}, sn>0={sn>0})')
    print(f'  DST: X{dx}Y{dy}N{dn}.{port}')
    print(f'  cells in sig: {nc}')
    print(f'  factory RBF:  {rbf.name}')

    out = ROOT / 'results' / 'hero_edge.json'
    out.write_text(json.dumps({
        'sx': sx, 'sy': sy, 'sn': sn,
        'dx': dx, 'dy': dy, 'dn': dn, 'port': port,
        'n_cells': nc,
        'factory_rbf': str(rbf),
    }, indent=1))
    print(f'\nwrote {out}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
