# SPDX-License-Identifier: GPL-3.0-or-later
"""Validate FASM IOB_IN / IOB_OUT directives against ground-truth RBFs.

For each pin P in the input sweep, synthesize via:

    IOB_IN  PIN_P
    IOB_OUT PIN_G15

starting from results/rbf/iob_in_E15.rbf (K=E15, LED=G15 baseline), and
diff against results/rbf/iob_in_P.rbf.

For each pin P in the output sweep, synthesize via:

    IOB_IN  PIN_E15
    IOB_OUT PIN_P

and diff against results/rbf/iob_out_P.rbf.

Reports byte/bit deltas per case. Target: 0 diffs across all 44 pins.
"""
from __future__ import annotations

import os, sys, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from pathlib import Path

from fasm2rbf import bitgen


ROOT = Path(__file__).resolve().parent.parent
RBF_DIR = ROOT / 'results' / 'rbf'
BASELINE = RBF_DIR / 'iob_in_E15.rbf'


def diff_bits(a: bytes, b: bytes) -> tuple[int, int]:
    """Return (n_byte_diffs, n_bit_diffs)."""
    nb = nbits = 0
    for x, y in zip(a, b):
        if x != y:
            nb += 1
            nbits += bin(x ^ y).count('1')
    return nb, nbits


def main():
    iob_map = json.loads((ROOT / 'results' / 'iob_cell_map.json').read_text())
    base = BASELINE.read_bytes()

    cases = []  # list[(label, fasm, expected_path)]
    for pin in iob_map['per_pin_input']:
        cases.append((
            f'INPUT  K=PIN_{pin:4s}  LED=PIN_G15',
            f'IOB_IN PIN_{pin}\nIOB_OUT PIN_G15\n',
            RBF_DIR / f'iob_in_{pin}.rbf',
        ))
    for pin in iob_map['per_pin_output']:
        cases.append((
            f'OUTPUT K=PIN_E15  LED=PIN_{pin:4s}',
            f'IOB_IN PIN_E15\nIOB_OUT PIN_{pin}\n',
            RBF_DIR / f'iob_out_{pin}.rbf',
        ))

    # Optional cross-axis case: requires a fresh Quartus build at
    # tmp/iob_xtest_M16_F15.rbf.  Documented as a known partial — the
    # single-axis sweep doesn't capture joint placement state.  Reported
    # but not counted toward pass/fail.
    xref = ROOT / 'tmp' / 'iob_xtest_M16_F15.rbf'
    cross_case = (
        'XAXIS  K=PIN_M16  LED=PIN_F15 (advisory)',
        'IOB_IN PIN_M16\nIOB_OUT PIN_F15\n',
        xref,
    ) if xref.exists() else None

    n_pass = n_fail = 0
    for label, fasm, expected_path in cases:
        if not expected_path.exists():
            print(f'[SKIP] {label}  (missing {expected_path.name})')
            continue
        out = bitgen(fasm, base)
        expected = expected_path.read_bytes()
        nb, nbits = diff_bits(out, expected)
        if nb == 0:
            print(f'[ OK ] {label}')
            n_pass += 1
        else:
            print(f'[FAIL] {label}  bytes={nb}  bits={nbits}')
            n_fail += 1

    print()
    print(f'== {n_pass} pass / {n_fail} fail / {len(cases)} total ==')

    if cross_case is not None:
        label, fasm, expected_path = cross_case
        out = bitgen(fasm, base)
        expected = expected_path.read_bytes()
        nb, nbits = diff_bits(out, expected)
        if nb == 0:
            print(f'[ OK ] {label}')
        else:
            # Expected miss until 2D K×LED sweep is mined.
            print(f'[NOTE] {label}  bytes={nb}  bits={nbits}  '
                  f'(joint-placement gap, see fasm2rbf.py IOB docstring)')

    return 0 if n_fail == 0 else 1


if __name__ == '__main__':
    sys.exit(main())
