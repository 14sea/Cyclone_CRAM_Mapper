#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Mine σ⁻¹ permutation for uncalibrated (foff//2, fb8) positions.

For each target position (x, y, n), compiles 3 Quartus designs:
  - mask=0x0000 (baseline)
  - mask=0xAAAA (bit 0 selector: minterms where input A=1)
  - mask=0xCCCC (bit 1 selector: minterms where input B=1)

From the CRAM diffs, determines which of the 16 TT cell addresses
correspond to which minterm bits, yielding σ⁻¹.

Output: results/sigma_inv_mined.json
"""
import json
import os
import sys
import time
from itertools import permutations

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'fuzz'))

from compile import compile_and_export
from config import (COLUMN_BASE, LAB_X, LAB_Y, PAIR_SPACING, SLOT_BASE,
                    cram_ctrl_addr, cram_ctrl_bit, cram_n_delta)
from qsf_gen import gen_qsf, make_lccomb
from verilog_gen import gen_lut4_primitive

RESULTS_PATH = os.path.join(os.path.dirname(__file__), '..', 'results',
                            'sigma_inv_mined.json')
WORK_DIR = os.path.join(os.path.dirname(__file__), '..', 'tmp',
                        'sigma_inv_mine_work')


def compute_key(x, y, n):
    slot = (y - 2) % 3
    group = (y - 2) // 3
    nd = cram_n_delta(n)
    offset = SLOT_BASE[slot] + group * 3 + (1 if slot == 0 and group > 0 else 0)
    val = COLUMN_BASE[x] - 168 + offset + nd
    foff = val % 210
    fb8 = (val // 210) % 8
    return foff, fb8


def get_uncovered_keys():
    from bitstream import _SIGMA_INV_CACHE
    calibrated = set((foff // 2, fb8) for (foff, fb8) in _SIGMA_INV_CACHE)

    needed = set()
    for x in LAB_X:
        for y in LAB_Y:
            for n in range(0, 32, 2):
                foff, fb8 = compute_key(x, y, n)
                needed.add((foff // 2, fb8))
    return needed - calibrated


def pick_positions(uncovered):
    """For each uncovered (foff//2, fb8), pick one (x,y,n) position."""
    targets = {}
    for x in LAB_X:
        for y in LAB_Y:
            for n in range(0, 32, 2):
                foff, fb8 = compute_key(x, y, n)
                k = (foff // 2, fb8)
                if k in uncovered and k not in targets:
                    targets[k] = (x, y, n, foff, fb8)
    return targets


def diff_rbf_bytes(rbf_a, rbf_b):
    """Return set of (byte_offset, bit_position) cells that differ."""
    cells = set()
    for i in range(min(len(rbf_a), len(rbf_b))):
        xor = rbf_a[i] ^ rbf_b[i]
        if xor:
            for bp in range(8):
                if xor & (1 << bp):
                    cells.add((i, bp))
    return cells


def extract_sigma_inv(x, y, n, cells_aaaa, cells_cccc):
    """Determine σ⁻¹ from the CRAM diffs of masks 0xAAAA and 0xCCCC vs 0x0000."""
    slot = (y - 2) % 3
    group = (y - 2) // 3
    nd = cram_n_delta(n)
    k = n // 2

    wrapped = slot == 1 and (24 + group * 3 + nd <= 0)
    if wrapped:
        bp_actual = 7 - group
        addr_adj = 207
    else:
        bp_actual = cram_ctrl_bit(y)
        addr_adj = 0

    cell_to_pd = {}
    for pair in range(8):
        for delta in [0, 1]:
            addr = cram_ctrl_addr(x, y, pair, n) + delta + addr_adj
            cell_to_pd[(addr, bp_actual)] = (pair, delta)

    for si in permutations(range(4)):
        sigma = [0] * 4
        for i, j in enumerate(si):
            sigma[j] = i
        ok = True
        for cell, (pair, delta) in cell_to_pd.items():
            b0 = 1 if cell in cells_aaaa else 0
            b1 = 1 if cell in cells_cccc else 0
            p2, p1, p0 = (pair >> 2) & 1, (pair >> 1) & 1, pair & 1
            f = [1 - p2, 1 - p1, 1 - p0,
                 (delta if k % 2 == 0 else 1 - delta) ^ p0]
            if f[sigma[0]] != b0 or f[sigma[1]] != b1:
                ok = False
                break
        if ok:
            return tuple(si)
    return None


def mine_one(x, y, n, work_subdir):
    """Mine σ⁻¹ at one position. Returns (sigma_inv_tuple, foff, fb8) or None."""
    node = "lut_inst"
    placement = {node: make_lccomb(x, y, n)}
    qsf = gen_qsf(placement=placement)

    masks = [0x0000, 0xAAAA, 0xCCCC]
    rbfs = {}

    for mask in masks:
        name = f"si_{x}_{y}_{n}_m{mask:04X}"
        verilog = gen_lut4_primitive(mask)
        rbf_path, elapsed, err = compile_and_export(
            name, verilog, qsf, work_dir=work_subdir)
        if not rbf_path:
            return None, f"compile failed mask=0x{mask:04X}: {err}"
        with open(rbf_path, 'rb') as f:
            rbfs[mask] = f.read()
        os.remove(rbf_path)

    cells_aaaa = diff_rbf_bytes(rbfs[0x0000], rbfs[0xAAAA])
    cells_cccc = diff_rbf_bytes(rbfs[0x0000], rbfs[0xCCCC])

    sigma_inv = extract_sigma_inv(x, y, n, cells_aaaa, cells_cccc)
    if sigma_inv is None:
        return None, "could not determine σ⁻¹"

    foff, fb8 = compute_key(x, y, n)
    return (list(sigma_inv), foff, fb8), ""


def main():
    os.makedirs(WORK_DIR, exist_ok=True)

    if os.path.exists(RESULTS_PATH):
        with open(RESULTS_PATH) as f:
            results = json.load(f)
    else:
        results = {}

    uncovered = get_uncovered_keys()
    already_mined = set()
    for entry in results.values():
        already_mined.add((entry['foff'] // 2, entry['fb8']))
    uncovered -= already_mined

    targets = pick_positions(uncovered)
    total = len(targets)
    print(f"σ⁻¹ mining: {total} positions to mine")
    print(f"Estimated time: ~{total * 90 / 60:.0f} min ({total * 3} compiles)")

    done = 0
    errors = 0
    t0 = time.time()

    for key, (x, y, n, foff, fb8) in sorted(targets.items()):
        done += 1
        tag = f"[{done}/{total}]"
        print(f"{tag} X{x}Y{y}N{n} (foff={foff}, fb8={fb8}) ... ", end="",
              flush=True)

        result, err = mine_one(x, y, n, WORK_DIR)
        if result is None:
            print(f"FAIL: {err}")
            errors += 1
            continue

        si, foff_out, fb8_out = result
        rkey = f"{foff_out},{fb8_out}"
        results[rkey] = {"foff": foff_out, "fb8": fb8_out, "sigma_inv": si,
                         "source": f"X{x}Y{y}N{n}"}
        print(f"σ⁻¹={si}")

        if done % 10 == 0:
            with open(RESULTS_PATH, 'w') as f:
                json.dump(results, f, indent=1)
            elapsed = time.time() - t0
            rate = done / elapsed * 60
            remaining = (total - done) / rate if rate > 0 else 0
            print(f"  --- saved ({done}/{total}, {rate:.1f}/min, "
                  f"~{remaining:.0f} min left) ---")

    with open(RESULTS_PATH, 'w') as f:
        json.dump(results, f, indent=1)

    elapsed = time.time() - t0
    print(f"\nDone: {done - errors}/{total} OK, {errors} errors, "
          f"{elapsed / 60:.1f} min")


if __name__ == "__main__":
    main()
