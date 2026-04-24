#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Close the σ⁻¹ Y=3 gap — 80 wrapped-address positions (slot=1, group=0,
N=12..30). Diagnosis (2026-04-24): these need **addr_adj=206** (not 207 as
the other slot-1 wrap groups use), and the wrap boundary must **include**
N=12 (`24+group*3+nd <= 0` rather than `< 0`). Re-uses the 8 cached
FACE (mask=0xFACE) Y=3 probe RBFs under tmp/sigma_{existing_groups,fb8_mine}/.

Emits `results/sigma_inv_y3_wrapped_patch.json` — 80 new (foff, fb8,
group=0) → σ⁻¹ entries that can be merged into
`results/sigma_inv_fb8_groups.json`. A follow-up integration step adds
them into the 3-key table and patches `bitstream.py::from_cram_model`.
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from itertools import permutations
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "fuzz"))
from config import cram_ctrl_addr, cram_n_delta  # noqa: E402

MASK = 0xFACE
N_VALS = list(range(12, 32, 2))

# fb8 → (X, probe subdir)
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

Y = 3
GROUP = 0
BP = 7                # slot-1 wrapped bit-position
ADDR_ADJ = 206        # Y=3 wrap offset (differs from group≥1's 207)


def best_sigma_inv(x, n, probe, nv):
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
            addr = cram_ctrl_addr(x, Y, pair, n) + delta + ADDR_ADJ
            nv_bit = (nv[addr] >> BP) & 1
            p_bit = (probe[addr] >> BP) & 1
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

    entries = {}
    per_fb8_sig = defaultdict(set)
    errors = 0

    for fb8, x, sub in TARGETS:
        probe_path = REPO / "tmp" / sub / f"face_X{x}_Y{Y}" / "output_files" / "probe.rbf"
        if not probe_path.exists():
            print(f"WARN: missing probe {probe_path}")
            continue
        probe = probe_path.read_bytes()
        for n in N_VALS:
            si, err = best_sigma_inv(x, n, probe, nv)
            nd = cram_n_delta(n)
            # same foff formula as bitstream.from_cram_model
            from config import COLUMN_BASE, SLOT_BASE
            val = COLUMN_BASE[x] - 168 + SLOT_BASE[1] + nd + ADDR_ADJ
            foff = val % 210
            fb8_c = (val // 210) % 8
            if fb8_c != fb8:
                print(f"WARN: fb8 mismatch X{x}N{n}: expected {fb8}, got {fb8_c}")
            if err != 0:
                print(f"ERR: X{x} Y{Y} N{n} fb8={fb8} err={err}")
                errors += 1
                continue
            key = f"{foff},{fb8},{GROUP}"
            entries[key] = {
                "foff": foff, "fb8": fb8, "group": GROUP, "sigma_inv": list(si),
                "source": f"X{x}Y{Y}N{n} (wrapped, addr_adj={ADDR_ADJ})",
            }
            per_fb8_sig[fb8].add(si)

    print(f"\n{len(entries)}/80 entries mined, {errors} errors")
    for fb8 in sorted(per_fb8_sig):
        sigs = per_fb8_sig[fb8]
        print(f"  fb8={fb8}: {len(sigs)} distinct σ⁻¹: {sorted(sigs)}")

    out_path = REPO / "results" / "sigma_inv_y3_wrapped_patch.json"
    out = {
        "description": "Y=3 (slot=1 group=0) wrapped-address σ⁻¹ closure — "
                       "80 entries covering N∈{12..30} × fb8∈{0..7}. "
                       "addr_adj=206 (not 207 as group≥1 wraps use); N=12 "
                       "(nd=-24) is inside the wrap region.",
        "mining_date": "2026-04-24",
        "mask": f"0x{MASK:04X}",
        "addr_adj": ADDR_ADJ,
        "bp": BP,
        "entries": entries,
    }
    out_path.write_text(json.dumps(out, indent=2) + "\n")
    print(f"\nWrote patch to {out_path}")


if __name__ == "__main__":
    main()
