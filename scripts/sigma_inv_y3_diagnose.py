#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Y=3 σ⁻¹ gap diagnostic — probe the address scheme that actually carries
the TT cells at Y=3 × N∈{12..30} (the 80 wrapped-address positions).

Reads the 8 cached FACE (mask=0xFACE) probe RBFs for Y=3 — one per fb8.
For each (x, y=3, n) position, brute-forces over candidate (bp, addr_adj)
schemes and checks whether *any* permutation σ⁻¹ of the 16 TT cells
perfectly reproduces 0xFACE at every minterm. Prints a schema table so
we know which (bp, addr_adj) tuple is correct for each wrapped N.

Outputs nothing to disk — this is a purely read-only diagnostic to pick
the right formulas before running the full mining.
"""
from __future__ import annotations

import sys
from collections import defaultdict
from itertools import permutations
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "fuzz"))
from config import cram_ctrl_addr, cram_ctrl_bit, cram_n_delta  # noqa: E402

MASK = 0xFACE
N_VALS_WRAPPED = list(range(12, 32, 2))  # N ∈ {12,14,16,...,30}

# fb8 → (X, probe_dir)
TARGETS = [
    (0, 3,  "sigma_existing_groups"),
    (1, 6,  "sigma_existing_groups"),
    (2, 21, "sigma_fb8_mine"),
    (3, 4,  "sigma_existing_groups"),
    (4, 7,  "sigma_existing_groups"),
    (5, 10, "sigma_fb8_mine"),
    (6, 13, "sigma_fb8_mine"),
    (7, 8,  "sigma_existing_groups"),
]


def best_sigma_inv(x, y, n, bp, addr_adj, probe, nv):
    """Return (best_perm, best_err) for given (bp, addr_adj) scheme."""
    k = n // 2
    best_err = 17
    best_si = None
    for si in permutations(range(4)):
        sigma = [0] * 4
        for i, j in enumerate(si):
            sigma[j] = i
        err = 0
        for b in range(16):
            f0 = (b >> sigma[0]) & 1
            f1 = (b >> sigma[1]) & 1
            f2 = (b >> sigma[2]) & 1
            f3 = (b >> sigma[3]) & 1
            pair = ((1 - f0) << 2) | ((1 - f1) << 1) | (1 - f2)
            da = f3 ^ (1 - f2)
            delta = da if k % 2 == 0 else 1 - da
            addr = cram_ctrl_addr(x, y, pair, n) + delta + addr_adj
            if not 0 <= addr < len(probe):
                err = 99
                break
            nv_bit = (nv[addr] >> bp) & 1
            p_bit = (probe[addr] >> bp) & 1
            d = nv_bit ^ p_bit
            m = (MASK >> b) & 1
            if d != m:
                err += 1
        if err < best_err:
            best_err = err
            best_si = si
    return best_si, best_err


def main():
    nv = (REPO / "results" / "rbf" / "nv_zero_global.rbf").read_bytes()
    assert len(nv) == 368011

    # Candidate schemes to explore
    # (bp, addr_adj) — extrapolating from the known wrapped convention
    schemes = [
        ("wrapped-strict", 7, 207),
        ("wrapped-bp6",    6, 207),
        ("nonwrapped",     6, 0),
        ("wrapped-208",    7, 208),
        ("wrapped-206",    7, 206),
        ("wrapped-210",    7, 210),
    ]
    # Also sweep: (bp ∈ 0..7, addr_adj ∈ small set)
    sweep_bps = list(range(8))
    sweep_adjs = [-2, -1, 0, 1, 2, 205, 206, 207, 208, 209, 210]

    print(f"{'fb8':>3}  {'X':>2}  {'N':>2}   scheme                 best_err  best_σ⁻¹")
    print("-" * 80)
    fixed = defaultdict(list)  # scheme -> list of (fb8, X, N, si)
    sweep_wins = defaultdict(int)  # (bp, adj) -> count

    for fb8, x, sub in TARGETS:
        probe_path = REPO / "tmp" / sub / f"face_X{x}_Y3" / "output_files" / "probe.rbf"
        probe = probe_path.read_bytes()
        for n in N_VALS_WRAPPED:
            # Try named schemes first
            best_per_scheme = {}
            for name, bp, adj in schemes:
                si, err = best_sigma_inv(x, 3, n, bp, adj, probe, nv)
                best_per_scheme[name] = (si, err)
            # Pick the best-named scheme
            best_name = min(best_per_scheme, key=lambda k: best_per_scheme[k][1])
            best_si, best_err = best_per_scheme[best_name]
            if best_err > 0:
                # Fall back to exhaustive (bp, adj) sweep
                sweep_best = (None, None, 17, None)
                for bp in sweep_bps:
                    for adj in sweep_adjs:
                        si, err = best_sigma_inv(x, 3, n, bp, adj, probe, nv)
                        if err < sweep_best[2]:
                            sweep_best = (bp, adj, err, si)
                bp, adj, err, si = sweep_best
                sweep_wins[(bp, adj)] += 1
                note = f"SWEEP bp={bp} adj={adj}"
                print(f"{fb8:>3}  {x:>2}  {n:>2}   {note:<22}  {err:>8}  {si}")
                fixed[note].append((fb8, x, n, si))
            else:
                print(f"{fb8:>3}  {x:>2}  {n:>2}   {best_name:<22}  {best_err:>8}  {best_si}")
                fixed[best_name].append((fb8, x, n, best_si))

    print()
    print("=== scheme usage summary ===")
    for name, rows in sorted(fixed.items(), key=lambda kv: -len(kv[1])):
        print(f"  {name:<30} : {len(rows)} positions")
    if sweep_wins:
        print()
        print("=== sweep winners (bp, adj) ===")
        for (bp, adj), cnt in sorted(sweep_wins.items(), key=lambda kv: -kv[1]):
            print(f"  bp={bp} adj={adj:>4} : {cnt}")


if __name__ == "__main__":
    main()
