#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Probe the LutCodec "canonicalization layer" at a target (X, Y, N).

Companion to probe_sigma_inv_perm.py. Where probe_sigma_inv_perm fits a 4-perm
σ⁻¹ to baseline-diffed cells, this script directly diffs *P-equivalent* LUT
masks against each other to isolate the cells that encode Quartus's input-
axis-canonicalization choice — cells the current LutCodec does NOT model
(Pitfall #16, memo `sigma_inv_x4y4n0_not_a_4perm_2026_05_12.md`).

Two P-equivalent classes are probed:

  1-input passthrough  (4 masks; all functionally equivalent to LED = pin_x)
    0xAAAA = "a"     (alternating every 1 bit)
    0xCCCC = "b"     (alternating every 2 bits)
    0xF0F0 = "c"     (alternating every 4 bits)
    0xFF00 = "d"     (alternating every 8 bits)

  1-input negation     (4 masks; LED = !pin_x)
    0x5555 = !a
    0x3333 = !b
    0x0F0F = !c
    0x00FF = !d

Pairwise diffs inside the passthrough class isolate the "physical input → LUT
axis" cells (silicon: 16 cells per swap per memo). Diffs across passthrough↔
negation pairs (e.g., 0xAAAA vs 0x5555) isolate the "axis negation" cells.

All diffs are RBF-only — no silicon flash needed.

Output: per-(off,bp) cell ownership table classifying each canonicalization
cell as "input axis a/b/c/d" or "negation_axis_X". This table is the
candidate codec extension input.

Usage:
    python3 scripts/sigma_inv_real_tt_mining/probe_canonicalization_cells.py 4 4 0
    python3 scripts/sigma_inv_real_tt_mining/probe_canonicalization_cells.py 4 4 0 --skip-build
        (uses cached RBFs from tmp/real_tt_mining/; will fail if not built yet)
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
WORK = REPO / "tmp" / "real_tt_mining"
OUT_DIR = REPO / "results"
QUARTUS = Path.home() / "intelFPGA_lite" / "21.1" / "quartus" / "bin"

# 1-input passthrough masks (canonical name → LUT mask)
PASSTHROUGH = {
    "a": 0xAAAA,
    "b": 0xCCCC,
    "c": 0xF0F0,
    "d": 0xFF00,
}

# 1-input negation masks
NEGATION = {
    "!a": 0x5555,
    "!b": 0x3333,
    "!c": 0x0F0F,
    "!d": 0x00FF,
}


def build_one(name: str, x: int, y: int, n: int, lut_mask: int) -> bytes | None:
    """Build a 1-LE Quartus design with `lut_mask` at (x, y, n). Cached."""
    if n in (14, 30):
        print(f"  SKIP chain-only LE: N={n}", file=sys.stderr)
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
        return rbf.read_bytes()

    env = os.environ.copy()
    env["PATH"] = str(QUARTUS) + ":" + env["PATH"]
    for step in ("quartus_map", "quartus_fit", "quartus_asm"):
        r = subprocess.run(
            [step, "--read_settings_files=on", "--write_settings_files=off", name],
            cwd=str(bdir), capture_output=True, env=env, timeout=180,
            text=True, errors="replace",
        )
        if r.returncode != 0:
            print(f"  FAIL {step}: {r.stdout[-800:]}", file=sys.stderr)
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
    """Diff two RBFs → set of (off, bp). Skips preamble/postamble/CRC."""
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


def classify_region(off: int) -> str:
    if off < 5282:
        return "header"
    elif off >= 355530:
        return "block_band"
    else:
        return "lab_cram"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("x", type=int)
    ap.add_argument("y", type=int)
    ap.add_argument("n", type=int)
    ap.add_argument("--skip-build", action="store_true",
                    help="Reuse cached RBFs only; fail if any missing")
    ap.add_argument("--save", action="store_true",
                    help="Save per-(off,bp) ownership table to results/")
    args = ap.parse_args()
    x, y, n = args.x, args.y, args.n

    print(f"=== Canonicalization-Cell Probe @ X{x}Y{y}N{n} ===")
    print()

    # Build / load all 8 designs
    rbfs: dict[str, bytes] = {}
    all_masks = {**PASSTHROUGH, **NEGATION}
    for label, mask in all_masks.items():
        name = f"canon_{label.replace('!','n')}_X{x}Y{y}N{n}"
        cached_path = WORK / name / f"{name}.rbf"
        if args.skip_build:
            if not cached_path.exists():
                print(f"FAIL: --skip-build but {cached_path} missing", file=sys.stderr)
                sys.exit(1)
            rbfs[label] = cached_path.read_bytes()
            print(f"  loaded {label:>3}  (0x{mask:04X})  cached")
            continue
        print(f"  building {label:>3}  (0x{mask:04X})...")
        rbf = build_one(name, x, y, n, mask)
        if rbf is None:
            print(f"FAIL: build for {label} (0x{mask:04X}) failed", file=sys.stderr)
            sys.exit(1)
        rbfs[label] = rbf
    print()

    # Pairwise diffs within the passthrough class — these isolate the "input axis"
    # canonicalization cells.
    print("--- Passthrough × Passthrough diffs (axis-canonicalization cells) ---")
    pt_keys = list(PASSTHROUGH.keys())
    axis_cells: dict[frozenset, set[tuple[int, int]]] = {}
    for i in range(len(pt_keys)):
        for j in range(i + 1, len(pt_keys)):
            a, b = pt_keys[i], pt_keys[j]
            d = diff_cells(rbfs[a], rbfs[b])
            regs: dict[str, int] = {}
            for off, bp in d:
                r = classify_region(off)
                regs[r] = regs.get(r, 0) + 1
            print(f"  {a} vs {b}: {len(d):3d} cells  {regs}")
            axis_cells[frozenset([a, b])] = d
    print()

    # Negation pairs — same physical input, output inverted
    print("--- Passthrough × Negation diffs (axis-negation cells) ---")
    neg_cells: dict[str, set[tuple[int, int]]] = {}
    for ax in pt_keys:
        pos_label = ax
        neg_label = "!" + ax
        d = diff_cells(rbfs[pos_label], rbfs[neg_label])
        regs: dict[str, int] = {}
        for off, bp in d:
            r = classify_region(off)
            regs[r] = regs.get(r, 0) + 1
        print(f"  {pos_label} vs {neg_label}: {len(d):3d} cells  {regs}")
        neg_cells[ax] = d
    print()

    # Identify the union of all "canonicalization cells" — cells that flip
    # under any choice swap. This is the candidate set the codec must learn.
    canon_union = set()
    for d in axis_cells.values():
        canon_union |= d
    for d in neg_cells.values():
        canon_union |= d

    by_region: dict[str, list[tuple[int, int]]] = {}
    for cell in canon_union:
        by_region.setdefault(classify_region(cell[0]), []).append(cell)
    print(f"--- Canonicalization-cell union: {len(canon_union)} cells ---")
    for r in sorted(by_region):
        cells = sorted(by_region[r])
        print(f"  {r:11}: {len(cells)} cells")
        for c in cells[:8]:
            print(f"      {c}")
        if len(cells) > 8:
            print(f"      ... ({len(cells) - 8} more)")
    print()

    # Per-cell ownership: which choice does each cell discriminate?
    ownership: dict[tuple[int, int], list[str]] = {}
    for pair, d in axis_cells.items():
        tag = f"axis_{'_'.join(sorted(pair))}"
        for cell in d:
            ownership.setdefault(cell, []).append(tag)
    for ax, d in neg_cells.items():
        tag = f"neg_{ax}"
        for cell in d:
            ownership.setdefault(cell, []).append(tag)

    # Cells that appear in only 1 discriminator are "clean signal";
    # cells appearing in many are shared (the high-fanout core).
    unique_count = sum(1 for tags in ownership.values() if len(tags) == 1)
    print(f"  Cells unique to 1 discriminator (clean signal): {unique_count}/{len(ownership)}")
    print()

    if args.save:
        OUT_DIR.mkdir(exist_ok=True)
        out = OUT_DIR / f"canon_cells_X{x}Y{y}N{n}.json"
        # JSON-friendly serialization
        out_data = {
            "position": [x, y, n],
            "axis_diffs": {
                f"{sorted(pair)[0]}_{sorted(pair)[1]}": sorted([list(c) for c in d])
                for pair, d in axis_cells.items()
            },
            "negation_diffs": {
                ax: sorted([list(c) for c in d]) for ax, d in neg_cells.items()
            },
            "union_count": len(canon_union),
            "union_by_region": {r: len(by_region.get(r, [])) for r in by_region},
            "ownership": {
                f"{off},{bp}": tags for (off, bp), tags in ownership.items()
            },
        }
        out.write_text(json.dumps(out_data, indent=2))
        print(f"  saved → {out}")


if __name__ == "__main__":
    main()
