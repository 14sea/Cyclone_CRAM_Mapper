# SPDX-License-Identifier: GPL-3.0-or-later
"""Analyze IOB sweep RBFs — extract per-pin CRAM cell sets.

Input sweep (LED=G15 fixed, K=P varies):
  per_pin_input[P] = cells unique to iob_in_P.rbf (not in any other input RBF)
  shared_input     = cells common to ALL input RBFs (LED-G15 output + universal)

Output sweep (K=E15 fixed, LED=P varies):
  per_pin_output[P] = cells unique to iob_out_P.rbf
  shared_output     = cells common to ALL output RBFs (K-E15 input + universal)

Sanity cross-checks:
  - shared_input ∩ shared_output = universal IOB infrastructure
  - shared_input - shared_output = LED G15 output cells (since LED varies
    in output sweep but is fixed in input sweep)
  - shared_output - shared_input = K E15 input cells

Emits results/iob_cell_map.json with per-pin sets + shared bands.
"""
from __future__ import annotations

import os, sys, re, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
RBF_DIR = REPO / 'results' / 'rbf'


def cells_from_rbf(rbf: bytes, zero: bytes | None) -> set[tuple[int, int]]:
    """Bit-level delta against `zero`. If zero is None, treat every set bit
    in `rbf` as a cell (absolute).

    Per-frame CRC bytes (rel=208/209) are skipped ONLY for config frames
    (frame >= 25) where patch_rbf_crc() will recompute them.  Header
    frames (0..24) carry IOB pin-assignment metadata at every byte
    position including 208/209 — those bytes are NOT CRC.
    """
    def is_data_crc(off: int) -> bool:
        if off < 32:
            return False
        frame = (off - 32) // 210
        if frame < 25:
            return False  # header frame — every byte is data
        rel = (off - 32) % 210
        return rel in (208, 209)

    out = set()
    if zero is not None:
        for off, (x, y) in enumerate(zip(rbf, zero)):
            d = x ^ y
            if not d:
                continue
            if is_data_crc(off):
                continue
            for bp in range(8):
                if d & (1 << bp):
                    out.add((off, bp))
    else:
        for off, b in enumerate(rbf):
            if not b:
                continue
            if is_data_crc(off):
                continue
            for bp in range(8):
                if b & (1 << bp):
                    out.add((off, bp))
    return out


def load_group(prefix: str):
    """Return {pin: cells_set} for all RBFs matching prefix."""
    pat = re.compile(rf'{re.escape(prefix)}_(\w+)\.rbf')
    groups = {}
    for path in sorted(RBF_DIR.glob(f'{prefix}_*.rbf')):
        m = pat.match(path.name)
        if not m:
            continue
        pin = m.group(1)
        raw = path.read_bytes()
        groups[pin] = cells_from_rbf(raw, None)  # absolute bits
    return groups


def main():
    input_g = load_group('iob_in')
    output_g = load_group('iob_out')
    print(f'loaded input sweep: {len(input_g)} RBFs, pins={sorted(input_g)}')
    print(f'loaded output sweep: {len(output_g)} RBFs, pins={sorted(output_g)}')

    if not input_g or not output_g:
        print('insufficient RBFs; run iob_sweep.py first')
        return

    # Per-pin unique cells = cells in THIS pin's RBF but no other sibling.
    def per_pin_unique(group):
        out = {}
        all_pins = list(group)
        for p in all_pins:
            others = set()
            for q in all_pins:
                if q == p:
                    continue
                others |= group[q]
            out[p] = sorted(group[p] - others)
        return out

    # Shared = intersection across all RBFs in the group.
    def shared(group):
        sets = list(group.values())
        if not sets:
            return set()
        s = set(sets[0])
        for g in sets[1:]:
            s &= g
        return s

    in_unique = per_pin_unique(input_g)
    out_unique = per_pin_unique(output_g)
    in_shared = shared(input_g)
    out_shared = shared(output_g)

    led_g15_cells = in_shared - out_shared     # LED=G15 output (fixed in input sweep)
    k_e15_cells   = out_shared - in_shared     # K=E15 input (fixed in output sweep)
    universal     = in_shared & out_shared     # universal IOB infra

    print()
    print(f'== per-pin unique counts ==')
    print('INPUT  sweep (K varies, LED=G15):')
    for p in sorted(in_unique):
        print(f'  K={p:4s}  unique cells = {len(in_unique[p])}')
    print()
    print('OUTPUT sweep (K=E15, LED varies):')
    for p in sorted(out_unique):
        print(f'  LED={p:4s}  unique cells = {len(out_unique[p])}')

    print()
    print(f'== shared bands ==')
    print(f'  LED=G15 output cells:    {len(led_g15_cells)}')
    print(f'  K=E15 input cells:       {len(k_e15_cells)}')
    print(f'  universal IOB infra:     {len(universal)}')

    # Pair-wise deltas vs anchor baselines (E15 for input sweep, G15 for
    # output sweep).  These are EXACT XOR deltas and capture every cell
    # that changes between baseline and target — including "semi-shared"
    # cells (set in two-or-more sibling pins but not all), which the
    # per_pin_unique decomposition above misses.  CRC bytes are filtered
    # because patch_rbf_crc() recomputes them post-application.
    K_REF = 'E15'
    LED_REF = 'G15'

    def pair_delta(group, ref_pin):
        if ref_pin not in group:
            return None
        ref = group[ref_pin]
        out = {}
        for p in group:
            # Symmetric diff = cells that flip going from ref → p.
            # Both sets are absolute, so XOR = symmetric diff.
            out[p] = sorted(group[p] ^ ref)
        return out

    in_delta = pair_delta(input_g, K_REF)
    out_delta = pair_delta(output_g, LED_REF)
    if in_delta is None or out_delta is None:
        raise RuntimeError(
            f'baseline missing: K_REF={K_REF} in input_g? {K_REF in input_g}; '
            f'LED_REF={LED_REF} in output_g? {LED_REF in output_g}'
        )

    print()
    print('== pair-delta vs baseline (used by FASM IOB directive) ==')
    print(f'INPUT  delta vs K={K_REF}:')
    for p in sorted(in_delta):
        print(f'  K={p:4s}  delta = {len(in_delta[p]):4d} cells')
    print(f'OUTPUT delta vs LED={LED_REF}:')
    for p in sorted(out_delta):
        print(f'  LED={p:4s}  delta = {len(out_delta[p]):4d} cells')

    out = {
        'input_pins': sorted(input_g),
        'output_pins': sorted(output_g),
        'k_ref': K_REF,
        'led_ref': LED_REF,
        # Legacy unique-only sets (per_pin_unique) — kept for backward
        # compat / structural analysis; do NOT use for synthesis.
        'per_pin_input': {p: [list(c) for c in cs] for p, cs in in_unique.items()},
        'per_pin_output': {p: [list(c) for c in cs] for p, cs in out_unique.items()},
        # Pair-delta vs baseline — USE THESE for synthesis.
        'input_delta': {p: [list(c) for c in cs] for p, cs in in_delta.items()},
        'output_delta': {p: [list(c) for c in cs] for p, cs in out_delta.items()},
        'led_g15_output_cells': sorted([list(c) for c in led_g15_cells]),
        'k_e15_input_cells':   sorted([list(c) for c in k_e15_cells]),
        'universal_cells':     sorted([list(c) for c in universal]),
    }
    p = REPO / 'results' / 'iob_cell_map.json'
    p.write_text(json.dumps(out, indent=1))
    print(f'\nwrote {p}')


if __name__ == '__main__':
    main()
