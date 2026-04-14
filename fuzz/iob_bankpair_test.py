# SPDX-License-Identifier: GPL-3.0-or-later
"""Test the bank-pair model for IOB cross-axis interaction.

Hypothesis: the ~57-byte joint-placement interaction term in cross-axis
IOB combos depends only on (bank(K), bank(LED)), not on the specific pin
identities.  If true, the FASM IOB directive can close the cross-axis
gap with a tiny bank-pair lookup (~64 entries max) instead of a full 2D
pin sweep (~480 entries).

Test: build 2 distinct (K, LED) pairs in each of several bank-pair
groups in parallel, compute the interaction term for each
(I = ΔRBF_actual ⊕ ΔRBF_predicted_by_single_axis_superposition), and
check whether the two samples in the same bank-pair group are byte-
identical.

Confirmed in the same session: bank map for AX301 pins is
  bank 2: P1, R1                bank 6: E15, E16, F15, F16, G15, G16
  bank 3: R5, T2, T8            bank 7: A11, A14
  bank 4: P9, R9, R13, T13      bank 8: A8
  bank 5: K15, K16, L15, L16, M15, M16, P15, R16

K anchor = E15 (bank 6).  LED anchor = G15 (bank 6).
"""
from __future__ import annotations

import os, sys, multiprocessing as mp
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RBF_DIR = ROOT / 'results' / 'rbf'
WORK_ROOT = ROOT / 'tmp' / 'iob_sweep'
XTEST_DIR = ROOT / 'tmp' / 'iob_bankpair'

VERILOG = (
    "module iob_probe(input wire K, output wire LED);\n"
    "  assign LED = K;\n"
    "endmodule\n"
)

QSF_TMPL = (
    'set_global_assignment -name FAMILY "Cyclone IV E"\n'
    'set_global_assignment -name DEVICE EP4CE6F17C8\n'
    'set_global_assignment -name TOP_LEVEL_ENTITY iob_probe\n'
    'set_global_assignment -name VERILOG_FILE fuzz_top.v\n'
    'set_global_assignment -name PROJECT_OUTPUT_DIRECTORY output_files\n'
    'set_global_assignment -name STRATIX_DEVICE_IO_STANDARD "3.3-V LVTTL"\n'
    'set_location_assignment PIN_{kpin} -to K\n'
    'set_location_assignment PIN_{lpin} -to LED\n'
)

# Sample plan: at least 2 distinct (K, LED) pairs per bank-pair, where
# both pins are non-anchor.  Bank-pair (5,6) and (8,5) reuse existing
# tmp/iob_xtest_*.rbf builds from the prior linearity test.
SAMPLES = [
    # bank_pair (5, 5) — both K and LED in bank 5
    ('5_5_a', 'M16', 'K15'),
    ('5_5_b', 'L16', 'K16'),
    # bank_pair (5, 4) — K bank5, LED bank4
    ('5_4_a', 'M16', 'R13'),
    ('5_4_b', 'L15', 'P9'),
    # bank_pair (3, 4) — K bank3 (right-edge near bottom), LED bank4
    ('3_4_a', 'T2',  'R13'),
    ('3_4_b', 'T8',  'P9'),
    # bank_pair (5, 6) — K bank5, LED bank6 (LED anchor's bank, not LED anchor itself)
    ('5_6_a', 'P15', 'F15'),
    ('5_6_b', 'R16', 'G16'),
]

# Pre-existing builds we can reuse (do not rebuild):
PRE_EXISTING = {
    ('M16', 'F15'): ROOT / 'tmp' / 'iob_xtest_M16_F15.rbf',  # bank-pair (5, 6)
    ('A8',  'R16'): ROOT / 'tmp' / 'iob_xtest_A8_R16.rbf',   # bank-pair (8, 5)
}


def build_one(job):
    tag, kpin, lpin = job
    out_path = XTEST_DIR / f'iob_bankpair_{tag}_K{kpin}_L{lpin}.rbf'
    if out_path.exists():
        return tag, kpin, lpin, str(out_path), True, 'cached'
    import sys as _sys
    _sys.path.insert(0, str(ROOT / 'fuzz'))
    from compile import compile_and_export
    qsf = QSF_TMPL.format(kpin=kpin, lpin=lpin)
    rbf, t, err = compile_and_export(
        f'iob_bp_{tag}', VERILOG, qsf,
        rbf_output=str(out_path),
        work_dir=str(WORK_ROOT),
    )
    if rbf:
        return tag, kpin, lpin, str(out_path), True, f'{t:.1f}s'
    return tag, kpin, lpin, str(out_path), False, f'FAIL {err[:120] if err else ""}'


def interaction(in_K_path: Path, out_L_path: Path, xref_path: Path,
                base_path: Path) -> bytes:
    base = base_path.read_bytes()
    in_K = in_K_path.read_bytes()
    out_L = out_L_path.read_bytes()
    xref = xref_path.read_bytes()
    delta_in   = bytes(a ^ b for a, b in zip(in_K,  base))
    delta_out  = bytes(a ^ b for a, b in zip(out_L, base))
    delta_act  = bytes(a ^ b for a, b in zip(xref,  base))
    delta_pred = bytes(a ^ b for a, b in zip(delta_in, delta_out))
    return bytes(a ^ b for a, b in zip(delta_act, delta_pred))


def main():
    XTEST_DIR.mkdir(parents=True, exist_ok=True)
    print(f'building {len(SAMPLES)} cross-axis test RBFs (4-way parallel)...')
    with mp.Pool(processes=4) as pool:
        rbf_paths = {}
        for tag, kpin, lpin, path, ok, msg in pool.imap_unordered(build_one, SAMPLES):
            status = 'OK' if ok else 'FAIL'
            print(f'  [{status:4s}] {tag:6s} K={kpin:4s} L={lpin:4s}  {msg}')
            if ok:
                rbf_paths[tag] = (kpin, lpin, Path(path))

    # Pre-existing builds
    rbf_paths['ext_5_6'] = ('M16', 'F15', PRE_EXISTING[('M16', 'F15')])
    rbf_paths['ext_8_5'] = ('A8',  'R16', PRE_EXISTING[('A8',  'R16')])

    base_path = RBF_DIR / 'iob_in_E15.rbf'
    print()
    print('== interaction term per sample ==')
    interactions = {}
    for tag, (kpin, lpin, xref) in sorted(rbf_paths.items()):
        if not xref.exists():
            print(f'  [SKIP] {tag}: missing {xref}')
            continue
        in_K = RBF_DIR / f'iob_in_{kpin}.rbf'
        out_L = RBF_DIR / f'iob_out_{lpin}.rbf'
        if not (in_K.exists() and out_L.exists()):
            print(f'  [SKIP] {tag}: missing single-axis RBF for K={kpin} or LED={lpin}')
            continue
        I = interaction(in_K, out_L, xref, base_path)
        n_bytes = sum(1 for b in I if b)
        n_bits = sum(bin(b).count('1') for b in I)
        interactions[tag] = (kpin, lpin, I, n_bytes, n_bits)
        print(f'  {tag:8s} K={kpin:4s} L={lpin:4s}  bytes={n_bytes:3d}  bits={n_bits:3d}')

    # Group by bank-pair tag prefix (e.g. '5_5', '5_6', etc.)
    print()
    print('== bank-pair model verification (within-group byte-identity) ==')
    from collections import defaultdict
    groups = defaultdict(list)
    for tag, (k, l, I, nb, nbits) in interactions.items():
        # Strip suffix (_a, _b, ext_) to get the bank-pair label.
        if tag.startswith('ext_'):
            label = tag[4:]
        else:
            label = '_'.join(tag.split('_')[:2])
        groups[label].append((tag, k, l, I, nb))

    for label in sorted(groups):
        members = groups[label]
        if len(members) < 2:
            print(f'  bank-pair {label}: only 1 sample, cannot test')
            continue
        ref_tag, ref_k, ref_l, ref_I, ref_nb = members[0]
        all_match = True
        for tag, k, l, I, nb in members[1:]:
            diff = bytes(a ^ b for a, b in zip(ref_I, I))
            n_diff_bytes = sum(1 for b in diff if b)
            n_diff_bits = sum(bin(b).count('1') for b in diff)
            verdict = 'IDENTICAL' if n_diff_bytes == 0 else f'DIFFER bytes={n_diff_bytes} bits={n_diff_bits}'
            print(f'  bank-pair {label}: {ref_tag}({ref_k},{ref_l}) vs {tag}({k},{l}): {verdict}')
            if n_diff_bytes:
                all_match = False
        if all_match:
            print(f'    → bank-pair {label}: HYPOTHESIS HOLDS for tested samples')
        else:
            print(f'    → bank-pair {label}: HYPOTHESIS FAILS — interaction depends on pin identity')


if __name__ == '__main__':
    main()
