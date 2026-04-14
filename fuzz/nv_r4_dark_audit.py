# SPDX-License-Identifier: GPL-3.0-or-later
"""Task E — predict which dark R4 I-indices Plan D' will illuminate.

Walks tmp/neorv32_timing_big.txt (under the repo-local scratch dir) and
counts occurrences of R4 wires for each unmapped I-index. If Plan D'
edges route through them with decent coverage, the dark indices can
finally be mined from the factory output.
"""
import re, sys, os, mmap
from pathlib import Path
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, as_completed

_ROOT = Path(__file__).resolve().parent.parent
TIMING = _ROOT / 'tmp' / 'neorv32_timing_big.txt'
DARK = {5, 6, 9, 24, 28, 29, 30, 31, 32, 33, 104, 116, 125}
RE = re.compile(rb'R4_X(\d+)_Y(\d+)_N(\d+)_I(\d+)')


def scan_chunk(path, start, end):
    wires = Counter()
    I_counts = Counter()
    with open(path, 'rb') as f:
        f.seek(start)
        data = f.read(end - start)
    for m in RE.finditer(data):
        x, y, n, i = int(m[1]), int(m[2]), int(m[3]), int(m[4])
        I_counts[i] += 1
        if i in DARK:
            wires[(x, y, n, i)] += 1
    return wires, I_counts


def main():
    size = TIMING.stat().st_size
    n = 8
    with open(TIMING, 'rb') as f:
        mm = mmap.mmap(f.fileno(), 0, prot=mmap.PROT_READ)
        offs = [i * size // n for i in range(n + 1)]
        aligned = [0]
        for a in offs[1:-1]:
            idx = mm.find(b'\nPath #', a)
            aligned.append(idx + 1 if idx != -1 else size)
        aligned.append(size)
        mm.close()
    chunks = list(zip(aligned[:-1], aligned[1:]))

    dark_wires = Counter()
    I_counts = Counter()
    with ProcessPoolExecutor(max_workers=n) as ex:
        futs = [ex.submit(scan_chunk, str(TIMING), s, e) for s, e in chunks]
        for f in as_completed(futs):
            w, ic = f.result()
            dark_wires.update(w)
            I_counts.update(ic)

    print('== R4 I-index frequency in NEORV32 STA ==')
    total = sum(I_counts.values())
    for i in sorted(I_counts):
        c = I_counts[i]
        tag = 'DARK' if i in DARK else '    '
        print(f'  {tag} I={i:3d}  {c:7d}  ({100*c/total:5.2f}%)')

    print(f'\n== DARK I-indices: unique wires encountered ==')
    by_i = {}
    for (x, y, n, i), c in dark_wires.items():
        by_i.setdefault(i, []).append((x, y, n, c))
    for i in sorted(by_i):
        wires = by_i[i]
        print(f'  I={i:3d}: {len(wires):4d} unique wires, '
              f'{sum(c for *_, c in wires):6d} total refs')
        for x, y, n, c in sorted(wires, key=lambda t: -t[3])[:3]:
            print(f'       X{x}_Y{y}_N{n}  refs={c}')

    dark_found = sum(1 for i in DARK if i in by_i)
    print(f'\n=> {dark_found}/{len(DARK)} dark I-indices have wire evidence in STA')


if __name__ == '__main__':
    main()
