# SPDX-License-Identifier: GPL-3.0-or-later
"""Structural analysis of IOB per-pin cells from results/iob_cell_map.json.

Groups each pin's unique cells into frame/byte bands and looks for
regularity across pins in the same bank/edge. Output goes to stdout as
a readable report; JSON summary written to results/iob_structure.json.
"""
import json
from collections import defaultdict, Counter
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
MAP = json.loads((REPO / 'results' / 'iob_cell_map.json').read_text())


def frame_of(off):
    # Config region starts at byte 32; 210-byte frames.
    if off < 32:
        return -1
    return (off - 32) // 210


def classify(off):
    f = frame_of(off)
    if f < 0:     return 'preamble'
    if f < 25:    return 'frame_hdr'
    if f < 200:   return 'data_early'
    if f < 1000:  return 'data_mid'
    if f < 1692:  return 'data_late'
    if f < 1739:  return 'block_band'  # IOB/M9K/DSPMULT mode band
    if f < 1752:  return 'data_tail'
    return 'postamble'


def report(group_name, per_pin):
    print(f'\n=== {group_name} ===')
    for pin, cells in sorted(per_pin.items()):
        bands = Counter(classify(off) for off, _ in cells)
        print(f'  {pin:4s} ({len(cells):2d}): {dict(bands)}')

    # Frame-level regularity across pins
    all_cells = set()
    for cells in per_pin.values():
        all_cells |= {tuple(c) for c in cells}
    frames = Counter(frame_of(off) for off, _ in all_cells)
    top_frames = frames.most_common(20)
    print(f'  top 20 frames by cell count: {top_frames}')


def edge_of(pin_name):
    """Return the edge (T/B/L/R) from the pin name's column letter."""
    c = pin_name[0]
    if c == 'A':           return 'LEFT'   # col A = left column
    if c == 'B':           return 'LEFT'
    if c in ('R', 'T', 'P'): return 'RIGHT'
    if c == 'E' and pin_name in ('E1',): return 'TOP'
    if c in ('E', 'F', 'G', 'H', 'J', 'K', 'L', 'M', 'N'):
        row = int(pin_name[1:])
        return 'TOP' if row <= 2 else ('BOT' if row >= 15 else 'MID')
    return 'OTHER'


def shared_by_edge(per_pin):
    by_edge = defaultdict(list)
    for pin, cells in per_pin.items():
        by_edge[edge_of(pin)].append(pin)
    for edge, pins in by_edge.items():
        if len(pins) < 2:
            continue
        sets = [{tuple(c) for c in per_pin[p]} for p in pins]
        shared = sets[0]
        for s in sets[1:]:
            shared &= s
        print(f'  {edge:6s} ({len(pins)} pins): shared-in-edge = {len(shared)}')


def main():
    in_per = {k: [tuple(c) for c in v] for k, v in MAP['per_pin_input'].items()}
    out_per = {k: [tuple(c) for c in v] for k, v in MAP['per_pin_output'].items()}

    report('INPUT per-pin (K varies, LED=G15 fixed)', in_per)
    report('OUTPUT per-pin (K=E15 fixed, LED varies)', out_per)

    print('\n=== INPUT edge-shared ===')
    shared_by_edge(in_per)
    print('\n=== OUTPUT edge-shared ===')
    shared_by_edge(out_per)

    print('\n=== LED=G15 output cells (shared across input sweep) ===')
    cells = [tuple(c) for c in MAP['led_g15_output_cells']]
    print(f'  count = {len(cells)}')
    bands = Counter(classify(off) for off, _ in cells)
    print(f'  bands = {dict(bands)}')
    frames = Counter(frame_of(off) for off, _ in cells)
    print(f'  top frames = {frames.most_common(10)}')

    print('\n=== K=E15 input cells (shared across output sweep) ===')
    cells = [tuple(c) for c in MAP['k_e15_input_cells']]
    print(f'  count = {len(cells)}')
    bands = Counter(classify(off) for off, _ in cells)
    print(f'  bands = {dict(bands)}')
    frames = Counter(frame_of(off) for off, _ in cells)
    print(f'  top frames = {frames.most_common(10)}')

    # Do INPUT and OUTPUT cells for the same pin overlap?
    # Example: pin A8 appears in both sweeps with different roles.
    both = set(in_per) & set(out_per)
    print('\n=== INPUT vs OUTPUT per-pin overlap (same pin, different role) ===')
    for p in sorted(both):
        a = {tuple(c) for c in in_per[p]}
        b = {tuple(c) for c in out_per[p]}
        print(f'  {p:4s}: in={len(a):2d}  out={len(b):2d}  shared={len(a & b):2d}  in-only={len(a-b):2d}  out-only={len(b-a):2d}')


if __name__ == '__main__':
    main()
