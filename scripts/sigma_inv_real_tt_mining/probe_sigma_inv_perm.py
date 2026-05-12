#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Probe the σ⁻¹ permutation at a specific (X, Y, N) via asymmetric LUT masks.

Pitfall #16 (2026-05-11): σ⁻¹ at X4Y4N0 LE_0 is broken for asymmetric masks
(0x8888 reads as 0xC0C0, 0xAAAA reads as 0xF0F0). Symmetric masks (XOR4 / XNOR4)
flip all 16 cells uniformly so they can't distinguish σ⁻¹ permutations. This
script fits the σ⁻¹ permutation empirically by:

  1. Building zero baseline (mask=0x0000) and probe builds (mask=0x8888, 0xAAAA)
     at the target (X, Y, N) using cycloneive_lcell_comb (bypass Yosys optimization).
  2. Diffing probe builds vs zero baseline → observed CRAM cells for each mask.
  3. For each candidate σ⁻¹ ∈ Perms(4) (24 total), computing the predicted cell
     set via the from_cram_model formula with that permutation. The σ⁻¹ that
     reproduces ALL observed masks simultaneously is the silicon-correct one.

If the fit succeeds with a single unique σ⁻¹, that permutation is the column-
specific override for (x, y, n). Compare to the current table-stored σ⁻¹ at the
(foff, fb8, group) key; if different, this is a position-specific patch.

Usage:
    python3 scripts/sigma_inv_real_tt_mining/probe_sigma_inv_perm.py 4 4 0
    python3 scripts/sigma_inv_real_tt_mining/probe_sigma_inv_perm.py 4 4 0 --masks 0x8888 0xAAAA 0xCCCC

The script reuses tmp/real_tt_mining/ as Quartus work directory.
"""
from __future__ import annotations

import argparse
import itertools
import json
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
WORK = REPO / "tmp" / "real_tt_mining"
QUARTUS = Path.home() / "intelFPGA_lite" / "21.1" / "quartus" / "bin"

sys.path.insert(0, str(REPO / "fuzz"))
from bitstream import (  # noqa: E402
    SLOT_BASE, COLUMN_BASE, cram_n_delta, cram_ctrl_bit, cram_ctrl_addr,
    _sigma_inv_lookup,
)


def build_one(name: str, x: int, y: int, n: int, lut_mask: int) -> bytes | None:
    """Build a 1-LE Quartus design with `lut_mask` at (x, y, n)."""
    if n in (14, 30):
        print(f"  SKIP chain-only LE: N={n}")
        return None
    bdir = WORK / name
    bdir.mkdir(parents=True, exist_ok=True)

    verilog = f"""\
module {name} (input KEY2, input KEY3, output LED0);
    wire combout;
    cycloneive_lcell_comb #(
        .lut_mask(16'h{lut_mask:04X}),
        .sum_lutc_input("datac"),
        .lpm_type("cycloneive_lcell_comb")
    ) le_inst (
        .dataa(KEY2),
        .datab(KEY3),
        .datac(1'b0),
        .datad(1'b0),
        .cin(1'b0),
        .combout(combout),
        .cout()
    );
    assign LED0 = combout;
endmodule
"""
    qsf = f"""\
set_global_assignment -name FAMILY "Cyclone IV E"
set_global_assignment -name DEVICE EP4CE6F17C8
set_global_assignment -name TOP_LEVEL_ENTITY {name}
set_global_assignment -name VERILOG_FILE {name}.v
set_global_assignment -name PROJECT_OUTPUT_DIRECTORY output_files
set_global_assignment -name SEED 1
set_global_assignment -name STRATIX_DEVICE_IO_STANDARD "3.3-V LVTTL"
set_global_assignment -name RESERVE_ALL_UNUSED_PINS_WEAK_PULLUP "AS INPUT TRI-STATED WITH WEAK PULL-UP"
set_global_assignment -name CYCLONEII_RESERVE_NCEO_AFTER_CONFIGURATION "USE AS REGULAR IO"
set_location_assignment PIN_E16 -to KEY2
set_location_assignment PIN_M16 -to KEY3
set_location_assignment PIN_G15 -to LED0
set_location_assignment LCCOMB_X{x}_Y{y}_N{n} -to "le_inst"
"""
    (bdir / f"{name}.v").write_text(verilog)
    (bdir / f"{name}.qsf").write_text(qsf)
    (bdir / f"{name}.qpf").write_text(f'PROJECT_REVISION = "{name}"\n')

    rbf = bdir / f"{name}.rbf"
    if rbf.exists() and rbf.stat().st_size == 368011:
        return rbf.read_bytes()  # cached

    env = os.environ.copy()
    env["PATH"] = str(QUARTUS) + ":" + env["PATH"]

    for step in ("quartus_map", "quartus_fit", "quartus_asm"):
        r = subprocess.run(
            [step, "--read_settings_files=on", "--write_settings_files=off", name],
            cwd=str(bdir), capture_output=True, env=env, timeout=180,
            text=True, errors="replace",
        )
        if r.returncode != 0:
            print(f"  FAIL {step}: {r.stdout[-800:]}")
            return None

    sof = bdir / "output_files" / f"{name}.sof"
    r = subprocess.run(
        [str(QUARTUS / "quartus_cpf"), "-c", "-o", "bitstream_compression=off",
         str(sof), str(rbf)],
        cwd=str(bdir), capture_output=True, env=env, timeout=60,
    )
    if r.returncode != 0:
        return None
    return rbf.read_bytes()


def diff_cells(a: bytes, b: bytes) -> set[tuple[int, int]]:
    """Diff two RBFs → set of (off, bp) cells excluding preamble/postamble/CRC."""
    cells = set()
    for off in range(32, min(len(a), len(b))):
        if off >= 367952:
            break
        frame = (off - 32) // 210
        pos = (off - 32) % 210
        if frame >= 25 and pos >= 208:
            continue
        x = a[off] ^ b[off]
        if x:
            for bp in range(8):
                if x & (1 << bp):
                    cells.add((off, bp))
    return cells


def cells_for_mask(x: int, y: int, n: int, sigma_inv: tuple[int, int, int, int],
                   mask: int) -> set[tuple[int, int]]:
    """Compute predict_sram(mask) using a candidate σ⁻¹ permutation.

    Replicates from_cram_model + predict_sram with σ⁻¹ as a parameter.
    """
    slot = (y - 2) % 3
    group = (y - 2) // 3
    nd = cram_n_delta(n)
    if slot == 1 and group == 0:
        wrapped = (24 + nd <= 0)
        addr_adj = 206 if wrapped else 0
        bp = (7 - group) if wrapped else cram_ctrl_bit(y)
    else:
        wrapped = slot == 1 and (24 + group * 3 + nd < 0)
        addr_adj = 207 if wrapped else 0
        bp = (7 - group) if wrapped else cram_ctrl_bit(y)

    sigma = [0] * 4
    for i, j in enumerate(sigma_inv):
        sigma[j] = i
    k = n // 2

    cells = set()
    for b in range(16):
        if not (mask & (1 << b)):
            continue
        f0_tgt = (b >> sigma[0]) & 1
        f1_tgt = (b >> sigma[1]) & 1
        f2_tgt = (b >> sigma[2]) & 1
        f3_tgt = (b >> sigma[3]) & 1
        pair = ((1 - f0_tgt) << 2) | ((1 - f1_tgt) << 1) | (1 - f2_tgt)
        da = f3_tgt ^ (1 - f2_tgt)
        delta = da if k % 2 == 0 else 1 - da
        addr = cram_ctrl_addr(x, y, pair, n) + delta + addr_adj
        # Toggle cell (predict_sram is XOR over per-bit pattern sets)
        cell = (addr, bp)
        if cell in cells:
            cells.discard(cell)
        else:
            cells.add(cell)
    return cells


def fit_sigma_inv(x: int, y: int, n: int,
                  observed: dict[int, set[tuple[int, int]]]
                  ) -> list[tuple[int, ...]]:
    """Find all σ⁻¹ permutations whose predict_sram matches observed for ALL probe masks."""
    matches = []
    for perm in itertools.permutations(range(4)):
        ok = True
        for mask, obs in observed.items():
            predicted = cells_for_mask(x, y, n, perm, mask)
            if predicted != obs:
                ok = False
                break
        if ok:
            matches.append(perm)
    return matches


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("x", type=int)
    ap.add_argument("y", type=int)
    ap.add_argument("n", type=int)
    # Default {0x8888, 0xAAAA, 0xF0F0} combo is empirically proven to uniquely
    # disambiguate all 24 σ⁻¹ permutations (vs 0x6996 baseline). 2-mask combos
    # like {0x8888, 0xAAAA} leave 2 ambiguous candidates for some truths.
    ap.add_argument("--masks", nargs="*", default=["0x8888", "0xAAAA", "0xF0F0"],
                    help="Asymmetric masks to probe (default: 0x8888 0xAAAA 0xF0F0)")
    args = ap.parse_args()

    masks = [int(m, 0) for m in args.masks]
    x, y, n = args.x, args.y, args.n

    print(f"=== σ⁻¹ Permutation Probe @ X{x}Y{y}N{n} ===")
    # Compute key
    slot = (y - 2) % 3
    group = (y - 2) // 3
    nd = cram_n_delta(n)
    if slot == 1 and group == 0:
        wrapped = (24 + nd <= 0)
        addr_adj = 206 if wrapped else 0
    else:
        wrapped = slot == 1 and (24 + group * 3 + nd < 0)
        addr_adj = 207 if wrapped else 0
    offset = SLOT_BASE[slot] + group * 3 + (1 if slot == 0 and group > 0 else 0)
    val = COLUMN_BASE[x] - 168 + offset + nd + addr_adj
    foff = val % 210
    fb8 = (val // 210) % 8
    current = _sigma_inv_lookup(foff, fb8, group)
    print(f"  3-key (foff,fb8,group) = ({foff},{fb8},{group})")
    print(f"  Current σ⁻¹ from lookup = {list(current)}")
    print()

    WORK.mkdir(parents=True, exist_ok=True)

    # Baseline = 0x6996 (XOR4). Quartus reliably places this; avoids the risk
    # of mask=0x0000 being optimized to a tied constant with no LE allocation.
    # Reuses the existing `xor_X{X}Y{Y}N{N}` cached RBF from real_tt_mining if
    # available (build_one returns cached bytes when rbf already exists).
    BASELINE_MASK = 0x6996
    baseline_name = f"xor_X{x}Y{y}N{n}"
    print(f"Building baseline ({baseline_name}, mask=0x{BASELINE_MASK:04X})...")
    baseline_rbf = build_one(baseline_name, x, y, n, BASELINE_MASK)
    if baseline_rbf is None:
        print("FAIL: baseline build failed", file=sys.stderr)
        sys.exit(1)

    # observed[mask] = predict_sram(mask) XOR predict_sram(BASELINE_MASK)
    #                = predict_sram(mask XOR BASELINE_MASK)
    # We store under the EFFECTIVE mask (mask ^ baseline) so the fitter matches
    # cells_for_mask(perm, effective_mask) directly.
    observed = {}
    for mask in masks:
        name = f"m{mask:04X}_X{x}Y{y}N{n}"
        print(f"Building probe ({name}, mask=0x{mask:04X})...")
        rbf = build_one(name, x, y, n, mask)
        if rbf is None:
            print(f"FAIL: build for mask 0x{mask:04X} failed", file=sys.stderr)
            sys.exit(1)
        cells = diff_cells(rbf, baseline_rbf)
        effective = mask ^ BASELINE_MASK
        observed[effective] = cells
        print(f"  diff(0x{mask:04X}, 0x{BASELINE_MASK:04X}) = predict_sram(0x{effective:04X}): "
              f"{len(cells)} cells → {sorted(cells)}")

    print()
    print("Fitting σ⁻¹ across all 24 permutations...")
    matches = fit_sigma_inv(x, y, n, observed)
    print(f"  found {len(matches)} permutation(s) matching ALL probe masks: {matches}")

    if len(matches) == 0:
        print("\nNO σ⁻¹ fits — the break is not a pure permutation. Either:")
        print("  (a) cram_ctrl_addr / addr_adj formula is wrong for this position")
        print("  (b) σ⁻¹ space is wider than 4-perm (e.g., per-bit offsets)")
        print("  Dump observed cells for forensic inspection above.")
    elif len(matches) == 1:
        new_si = list(matches[0])
        print(f"\n✓ Unique fit: σ⁻¹ = {new_si}")
        print(f"  Current (lookup): {list(current)}")
        if list(current) == new_si:
            print(f"  ⚠️  Same as current — the codec ALREADY uses this σ⁻¹. Bug is elsewhere.")
        else:
            print(f"  ⚠️  DIFFERENT from current — patch needed.")
            print(f"  Suggested override: position_overrides['{x},{y},{n}'] = {new_si}")
    else:
        print(f"\n⚠️  Probe ambiguous — add more masks to disambiguate. Candidates: {matches}")


if __name__ == "__main__":
    main()
