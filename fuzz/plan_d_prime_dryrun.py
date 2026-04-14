# SPDX-License-Identifier: GPL-3.0-or-later
"""Plan D' dry-run: parse NEORV32 timing dump, extract routing edges,
report strict vs loose dedup counts. Compiles nothing.

Edge definition: (src_lccomb, dst_lccomb, port). Source = most-recent
LCCOMB/FF before the routing hops; dst = the LCCOMB/FF at an IC-type
line whose Element field carries `...|<port>`.

Multi-threaded: split the 3.6 GB file into chunks at 'Path #' boundaries
and parse each chunk in a worker.
"""
import os, re, sys, json, mmap
from pathlib import Path
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, as_completed

_ROOT  = Path(__file__).resolve().parent.parent
TIMING = _ROOT / 'tmp' / 'neorv32_timing_big.txt'
HOLD   = _ROOT / 'tmp' / 'neorv32_timing_hold.txt'
OUT    = _ROOT / 'results' / 'plan_d_prime_edges.json'

# Line patterns inside a path block
RE_LCCOMB = re.compile(r'LCCOMB_X(\d+)_Y(\d+)_N(\d+)')
RE_FF     = re.compile(r'\bFF_X(\d+)_Y(\d+)_N(\d+)')
# IC row: ";   23.277 ;   0.000 ; FF ; IC   ; 1      ; LCCOMB_X4_Y2_N4  ; ...|datac "
RE_IC     = re.compile(
    r';\s*[-\d.]+\s*;\s*[-\d.]+\s*;[^;]*;\s*IC\s*;[^;]*;\s*'
    r'(LCCOMB|FF)_X(\d+)_Y(\d+)_N(\d+)\s*;\s*([^;]+?)\s*;'
)
# Cell row: marks a source LCCOMB/FF producing its output
RE_CELL_SRC = re.compile(
    r';\s*[-\d.]+\s*;\s*[-\d.]+\s*;[^;]*;\s*CELL\s*;[^;]*;\s*'
    r'(LCCOMB|FF)_X(\d+)_Y(\d+)_N(\d+)\s*;'
)
RE_PATH = re.compile(rb'^Path #', re.M)
PORT_RE = re.compile(r'\|([a-z]+)(?:\s|$)')


def parse_chunk(path, start, end):
    """Parse bytes [start:end) of timing file; return list of edges."""
    edges = []
    with open(path, 'rb') as f:
        f.seek(start)
        data = f.read(end - start).decode('latin-1', errors='replace')
    cur_src = None  # (x,y,n) of last-seen CELL source (LCCOMB or FF)
    in_data_path = False
    for line in data.split('\n'):
        if 'Data Arrival Path' in line or 'data path' in line:
            in_data_path = True
            cur_src = None
            continue
        if 'Data Required Path' in line or 'Extra Fitter' in line:
            in_data_path = False
            cur_src = None
            continue
        if not in_data_path:
            continue
        m = RE_IC.search(line)
        if m:
            kind, x, y, n, elem = m.group(1), int(m.group(2)), int(m.group(3)), int(m.group(4)), m.group(5)
            pm = PORT_RE.search(elem)
            port = pm.group(1) if pm else '?'
            # Only datac/datad/dataa/datab are real LE inputs we can target
            if port in ('dataa', 'datab', 'datac', 'datad') and cur_src is not None:
                sx, sy, sn = cur_src
                edges.append((sx, sy, sn, kind, x, y, n, port))
            continue
        m = RE_CELL_SRC.search(line)
        if m:
            cur_src = (int(m.group(2)), int(m.group(3)), int(m.group(4)))
    return edges


def split_offsets(path, n_chunks):
    """Return list of (start, end) byte offsets aligned to 'Path #' markers."""
    size = path.stat().st_size
    with open(path, 'rb') as f:
        mm = mmap.mmap(f.fileno(), 0, prot=mmap.PROT_READ)
        approx = [i * size // n_chunks for i in range(n_chunks + 1)]
        aligned = [0]
        for a in approx[1:-1]:
            # scan forward to next Path # marker
            idx = mm.find(b'\nPath #', a)
            aligned.append(idx + 1 if idx != -1 else size)
        aligned.append(size)
        mm.close()
    return list(zip(aligned[:-1], aligned[1:]))


def run_file(path, workers):
    print(f'== {path} ({path.stat().st_size / 1e9:.2f} GB) ==')
    chunks = split_offsets(path, workers)
    all_edges = []
    with ProcessPoolExecutor(max_workers=workers) as ex:
        futs = [ex.submit(parse_chunk, str(path), s, e) for s, e in chunks]
        for i, f in enumerate(as_completed(futs)):
            es = f.result()
            all_edges.extend(es)
            print(f'  chunk {i+1}/{len(chunks)}: {len(es):,} edges (total {len(all_edges):,})')
    return all_edges


def main():
    workers = int(os.environ.get('WORKERS', '8'))
    edges = run_file(TIMING, workers)
    if HOLD.exists():
        edges += run_file(HOLD, workers)

    print(f'\nTotal raw edges (with dup from multi-path): {len(edges):,}')

    # Strict dedup: full 8-tuple
    strict = set(edges)
    print(f'Strict dedup (sx,sy,sn,kind,dx,dy,dn,port): {len(strict):,}')

    # Loose dedup: (dst_x, dst_y, dst_n, port) — sig-cache lookup key
    loose = {(e[4], e[5], e[6], e[7]) for e in edges}
    print(f'Loose dedup (dx,dy,dn,port) — sig-cache key:  {len(loose):,}')

    # Extra: per-dst LE count (how many unique dst LEs)
    dst_les = {(e[4], e[5], e[6]) for e in edges}
    dst_labs = {(e[4], e[5]) for e in edges}
    print(f'Unique dst LEs (dx,dy,dn):                    {len(dst_les):,}')
    print(f'Unique dst LABs (dx,dy):                      {len(dst_labs):,}')

    # Port mix
    port_counts = Counter(e[7] for e in strict)
    print(f'\nPort distribution (strict):')
    for p, c in sorted(port_counts.items()):
        print(f'  {p}: {c:,}')

    # Sample 20
    import random
    random.seed(0)
    sample = random.sample(sorted(strict), min(20, len(strict)))
    print(f'\nSample 20 strict edges:')
    for e in sample:
        sx, sy, sn, kind, dx, dy, dn, port = e
        print(f'  ({sx:2},{sy:2},{sn:2}) -> {kind}({dx:2},{dy:2},{dn:2}).{port}')

    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps({
        'raw': len(edges),
        'strict': len(strict),
        'loose': len(loose),
        'dst_les': len(dst_les),
        'dst_labs': len(dst_labs),
        'port_counts': dict(port_counts),
        'strict_edges_sorted': sorted(list(strict)),
    }, indent=1))
    print(f'\nWrote {OUT}')


if __name__ == '__main__':
    main()
