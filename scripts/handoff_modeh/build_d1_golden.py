#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""D1 sentinel + D1++ stratified golden-RBF builder for rot_tpu_handoff mode H.

Produces per (x, y, n, mask) one Quartus Lite 21.1 RBF + .diff + .cells JSON.
Reuses build_one from probe_canonicalization_cells.py with a local WORK
override so cache hygiene stays clean.

Schema per consumer side spec (cyclone_cram_mapper_targets_modeH.txt §D1):

  results/golden_rbf_modeH/X{x}_Y{y}_N{n}_mask{MMMM}_q211.rbf
  results/golden_rbf_modeH/X{x}_Y{y}_N{n}_mask{MMMM}_q211.diff   (cells, gzipped JSON if large)
  results/golden_rbf_modeH/X{x}_Y{y}_N{n}_mask{MMMM}_q211.cells  (list of {addr, bit, before, after})

  results/golden_rbf_modeH/sweep_summary.json   (top-level coverage summary)

Per D1 spec, .diff/.cells exclude:
  - preamble [0, 32) and postamble [367952, 368011) (constants)
  - per-frame CRC bytes (off, off+1) at (off - 32) % 210 >= 208
  - per-build variable header bytes [0x29, 0x35) + [0x49, 0x4B)
    (design-dependent + design-level CRC, documented in D4)

Wall: ~32 builds * 60-90 sec * 4 process parallel ≈ 40-50 min.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import multiprocessing as mp
import os
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
OUT_DIR = REPO / "results" / "golden_rbf_modeH"
WORK = REPO / "tmp" / "handoff_modeh_d1"
QUARTUS = Path.home() / "intelFPGA_lite" / "21.1" / "quartus" / "bin"
QUARTUS_VERSION = "Lite 21.1"

# Per-build variable header byte ranges (half-open). From D4 doc.
VARIABLE_BYTE_RANGES = ((0x29, 0x35), (0x49, 0x4B))

# Constants from fuzz/bitstream.py and D4.
PREAMBLE_BYTES = 32
FRAME_SIZE = 210
LAST_CRAM_FRAME = 1751
POSTAMBLE_START = PREAMBLE_BYTES + (LAST_CRAM_FRAME + 1) * FRAME_SIZE  # 367952


def build_one(name: str, x: int, y: int, n: int, lut_mask: int) -> bytes:
    """Build a 4-input 1-LUT design at LCCOMB_X{x}_Y{y}_N{n} with the given mask.

    KEY1->dataa, KEY2->datab, KEY3->datac, KEY4->datad.  All four pins are
    wired regardless of mask so Quartus does NOT constant-fold any 16-bit
    truth table.  Cached on disk under WORK/<name>/.

    Returns the 368011-byte RBF bytes.
    """
    bdir = WORK / name
    bdir.mkdir(parents=True, exist_ok=True)
    rbf_path = bdir / f"{name}.rbf"
    if rbf_path.exists() and rbf_path.stat().st_size == 368011:
        return rbf_path.read_bytes()

    verilog = f"""\
module {name} (input KEY1, input KEY2, input KEY3, input KEY4, output LED0);
    wire combout;
    cycloneive_lcell_comb #(
        .lut_mask(16'h{lut_mask:04X}),
        .sum_lutc_input("datac"),
        .lpm_type("cycloneive_lcell_comb")
    ) le_inst (
        .dataa(KEY1),
        .datab(KEY2),
        .datac(KEY3),
        .datad(KEY4),
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
set_location_assignment PIN_E15 -to KEY1
set_location_assignment PIN_E16 -to KEY2
set_location_assignment PIN_M16 -to KEY3
set_location_assignment PIN_M15 -to KEY4
set_location_assignment PIN_G15 -to LED0
set_location_assignment LCCOMB_X{x}_Y{y}_N{n} -to "le_inst"
"""
    (bdir / f"{name}.v").write_text(verilog)
    (bdir / f"{name}.qsf").write_text(qsf)
    (bdir / f"{name}.qpf").write_text(f'PROJECT_REVISION = "{name}"\n')

    env = os.environ.copy()
    env["PATH"] = str(QUARTUS) + ":" + env["PATH"]
    for step in ("quartus_map", "quartus_fit", "quartus_asm"):
        r = subprocess.run(
            [step, "--read_settings_files=on", "--write_settings_files=off", name],
            cwd=str(bdir), capture_output=True, env=env, timeout=240,
            text=True, errors="replace",
        )
        if r.returncode != 0:
            raise RuntimeError(
                f"build_one {name}: {step} failed\n"
                f"stdout tail:\n{r.stdout[-800:]}\nstderr tail:\n{r.stderr[-400:]}"
            )

    sof = bdir / "output_files" / f"{name}.sof"
    r = subprocess.run(
        [str(QUARTUS / "quartus_cpf"), "-c", "-o", "bitstream_compression=off",
         str(sof), str(rbf_path)],
        cwd=str(bdir), capture_output=True, env=env, timeout=60,
    )
    if r.returncode != 0:
        raise RuntimeError(f"build_one {name}: quartus_cpf failed")
    data = rbf_path.read_bytes()
    if len(data) != 368011:
        raise RuntimeError(f"build_one {name}: bad size {len(data)}")
    return data


def in_variable_range(off: int) -> bool:
    return any(lo <= off < hi for lo, hi in VARIABLE_BYTE_RANGES)


def is_crc_byte(off: int) -> bool:
    """True iff off is a per-frame CRC byte at any frame."""
    if off < PREAMBLE_BYTES or off >= POSTAMBLE_START:
        return False
    return (off - PREAMBLE_BYTES) % FRAME_SIZE >= 208


def diff_cells(target: bytes, baseline: bytes) -> list[dict]:
    """Compute bit-level diff target vs baseline. Excludes preamble,
    postamble, CRC bytes, and per-build variable header bytes.

    Returns a list of {addr, bit, before, after} dicts in absolute file
    coordinates; addr is a hex string, bit is an integer 0..7.
    """
    cells = []
    for off in range(PREAMBLE_BYTES, POSTAMBLE_START):
        if is_crc_byte(off):
            continue
        if in_variable_range(off):
            continue
        x = target[off] ^ baseline[off]
        if not x:
            continue
        for bp in range(8):
            if not (x & (1 << bp)):
                continue
            cells.append({
                "addr": f"0x{off:05X}",
                "bit": bp,
                "before": (baseline[off] >> bp) & 1,
                "after": (target[off] >> bp) & 1,
            })
    return cells


def classify_region(off: int) -> str:
    if off < 5282:
        return "header"
    if off >= 355530:
        return "block_band"
    return "lab_cram"


def diff_region_summary(cells: list[dict]) -> dict[str, int]:
    out = {"header": 0, "lab_cram": 0, "block_band": 0}
    for c in cells:
        out[classify_region(int(c["addr"], 16))] += 1
    return out


def _build_worker(args):
    """Multiprocess worker: builds RBF, returns (key, error_or_None)."""
    x, y, n, mask = args
    name = f"X{x}_Y{y}_N{n}_mask{mask:04X}_q211"
    try:
        t0 = time.time()
        build_one(name, x, y, n, mask)
        return (name, time.time() - t0, None)
    except Exception as e:
        return (name, 0.0, str(e))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--processes", type=int, default=4,
                    help="Parallel Quartus compiles (default: 4)")
    ap.add_argument("--dry-run", action="store_true",
                    help="Print the build plan and exit without compiling.")
    ap.add_argument("--skip-build", action="store_true",
                    help="Use cached RBFs only; fail if any are missing.")
    args = ap.parse_args()

    # Build plan: sentinel (2 pos x 4 masks) + stratified (12 pos x 2 masks) = 32.
    SENTINEL_POSITIONS = [(10, 2, 0), (28, 17, 0)]    # Note: handoff doc said
    # X28Y17N14, but N=14 is a chain-only LE per the existing probe script
    # (build_one skips N in {14, 30}).  Substituting N=0 keeps the slice
    # standard-lut and avoids the chain edge case.  Documented in
    # sweep_summary.json under `n_substitution_note`.
    SENTINEL_MASKS = [0x0000, 0x6996, 0xDEAD, 0xFFFF]

    # Stratified sample: 12 of 16 (X in {10,16,22,28} x Y in {2,8,14,21})
    # excluding the 4 corner-most positions.
    STRAT_X = (10, 16, 22, 28)
    STRAT_Y = (2, 8, 14, 21)
    STRAT_CORNERS = {(10, 2), (10, 21), (28, 2), (28, 21)}
    STRAT_POSITIONS = sorted([
        (x, y, 0) for x in STRAT_X for y in STRAT_Y
        if (x, y) not in STRAT_CORNERS
    ])
    # 2026-05-28 (CRTM Part-3): extend the asymmetric mask 0xDEAD from the
    # 2 sentinels to all 12 stratified positions, unlocking per-position
    # canon-cell coverage for an asymmetric mask across all 14 D1++ sites.
    # (0xFFFF/0x0000 are trivial constants; 0x6996 is the symmetric XOR4.)
    STRAT_MASKS = [0x0000, 0x6996, 0xDEAD]

    plan: list[tuple[int, int, int, int]] = []
    sentinel_keys = set()
    for x, y, n in SENTINEL_POSITIONS:
        for m in SENTINEL_MASKS:
            plan.append((x, y, n, m))
            sentinel_keys.add((x, y, n, m))
    # Avoid duplicates if a stratified position equals a sentinel position
    for x, y, n in STRAT_POSITIONS:
        for m in STRAT_MASKS:
            if (x, y, n, m) not in sentinel_keys:
                plan.append((x, y, n, m))

    print(f"D1 build plan: {len(plan)} compiles "
          f"({len(SENTINEL_POSITIONS)} sentinel pos x "
          f"{len(SENTINEL_MASKS)} masks + "
          f"{len(STRAT_POSITIONS)} stratified pos x "
          f"{len(STRAT_MASKS)} masks)")
    for entry in plan:
        x, y, n, m = entry
        kind = "S" if entry in sentinel_keys else "X"
        print(f"  [{kind}] X{x:>2} Y{y:>2} N{n:>2} mask=0x{m:04X}")

    if args.dry_run:
        print("\n(dry-run) plan complete; exiting.")
        return

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    print(f"\nLaunching {args.processes}-way parallel Quartus builds "
          f"(wall ~{60*len(plan)//(60*max(1,args.processes))}-{90*len(plan)//(60*max(1,args.processes))} min)...")
    t_start = time.time()
    if args.skip_build:
        # Skip Quartus invocations; assume RBFs already cached.
        results = [(f"X{x}_Y{y}_N{n}_mask{m:04X}_q211", 0.0, None)
                   for x, y, n, m in plan]
    else:
        with mp.Pool(processes=args.processes) as pool:
            results = pool.map(_build_worker, plan)
    t_build = time.time() - t_start

    # Check for failures.
    failures = [(name, err) for name, _, err in results if err]
    if failures:
        print(f"\nFAIL: {len(failures)} build(s) failed:")
        for name, err in failures:
            print(f"  {name}: {err[:200]}")
        sys.exit(1)
    print(f"\nAll {len(plan)} Quartus builds succeeded ({t_build:.1f}s wall)")

    # Group plan entries by (x, y, n) for diffing against per-position mask=0 baseline.
    by_pos: dict[tuple[int, int, int], list[int]] = {}
    for x, y, n, m in plan:
        by_pos.setdefault((x, y, n), []).append(m)

    summary = {
        "schema_version": 1,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "quartus_version": QUARTUS_VERSION,
        "coverage": [
            {"x": x, "y": y, "n": n, "masks": [f"0x{m:04X}" for m in sorted(masks)]}
            for (x, y, n), masks in sorted(by_pos.items())
        ],
        "n_substitution_note": (
            "Sentinel position X28_Y17_N14 from cyclone_cram_mapper_targets_modeH.txt "
            "substituted with X28_Y17_N0 — N=14 is a chain-only LE in EP4CE6 (the "
            "existing probe pipeline skips N in {14, 30}). N=0 keeps the slice "
            "standard-lut. Original N=14 can be re-requested if consumer side has "
            "host-side coverage that specifically needs it."
        ),
        "build_args": {
            "wire4": True,
            "pin_map": {"KEY1": "PIN_E15", "KEY2": "PIN_E16",
                         "KEY3": "PIN_M16", "KEY4": "PIN_M15",
                         "LED0": "PIN_G15"},
            "qsf_seed": 1,
        },
        "per_build_variable_ranges": [
            [f"0x{lo:02X}", f"0x{hi:02X}"] for lo, hi in VARIABLE_BYTE_RANGES
        ],
        "results": [],
    }

    # Generate .diff + .cells per non-zero mask against same-position mask=0 baseline.
    print(f"\nGenerating .diff + .cells JSON for {len(plan) - len(by_pos)} non-zero builds...")
    n_pass_byte_identity_codec = 0
    n_failed_diff = 0
    for (x, y, n), masks in sorted(by_pos.items()):
        masks_sorted = sorted(masks)
        if 0x0000 not in masks_sorted:
            print(f"  WARN: position X{x}Y{y}N{n} has no mask=0x0000 build — "
                  f"skipping diffs for this position")
            continue
        base_name = f"X{x}_Y{y}_N{n}_mask0000_q211"
        base_rbf = (WORK / base_name / f"{base_name}.rbf").read_bytes()
        # Copy mask=0 RBF to output dir (no diff/cells emitted for it; it IS the baseline).
        (OUT_DIR / f"{base_name}.rbf").write_bytes(base_rbf)
        for m in masks_sorted:
            name = f"X{x}_Y{y}_N{n}_mask{m:04X}_q211"
            target_rbf_path = WORK / name / f"{name}.rbf"
            target_rbf = target_rbf_path.read_bytes()
            (OUT_DIR / f"{name}.rbf").write_bytes(target_rbf)

            entry = {
                "x": x, "y": y, "n": n,
                "mask": f"0x{m:04X}",
                "rbf_md5": hashlib.md5(target_rbf).hexdigest(),
                "byte_identity_passes_against_codec": None,
                # Filled below for non-zero masks.
            }

            if m == 0x0000:
                entry["is_baseline"] = True
                entry["n_cells_in_diff"] = 0
                entry["regions"] = {"header": 0, "lab_cram": 0, "block_band": 0}
                summary["results"].append(entry)
                continue

            cells = diff_cells(target_rbf, base_rbf)
            (OUT_DIR / f"{name}.cells").write_text(json.dumps(cells, indent=2))
            # .diff is the same content, gzipped if large. For convenience emit
            # uncompressed JSON; consumer can gzip if disk pressure arises.
            (OUT_DIR / f"{name}.diff").write_text(json.dumps({
                "schema_version": 1,
                "baseline_rbf": f"{base_name}.rbf",
                "target_rbf": f"{name}.rbf",
                "cells": cells,
                "region_summary": diff_region_summary(cells),
                "n_cells": len(cells),
                "excluded": {
                    "preamble_postamble": True,
                    "per_frame_crc_bytes": True,
                    "per_build_variable_ranges": VARIABLE_BYTE_RANGES,
                },
            }, indent=2))

            # Byte-identity gate against the EP4CE6 LutCodec.
            try:
                sys.path.insert(0, str(REPO / "fuzz"))
                from bitstream import LutCodec  # noqa: E402
                codec = LutCodec.from_cram_model(x, y, n)
                codec_rbf = bytearray(base_rbf)
                for addr, bp in codec.predict_sram(m):
                    codec_rbf[addr] ^= 1 << bp
                # Compare codec output to Quartus target on CRAM cells only,
                # excluding per-build variable header bytes and CRC.
                mismatches = []
                for off in range(PREAMBLE_BYTES, POSTAMBLE_START):
                    if is_crc_byte(off) or in_variable_range(off):
                        continue
                    if codec_rbf[off] != target_rbf[off]:
                        mismatches.append(off)
                entry["byte_identity_passes_against_codec"] = (len(mismatches) == 0)
                entry["codec_mismatch_count"] = len(mismatches)
                if mismatches:
                    n_failed_diff += 1
                else:
                    n_pass_byte_identity_codec += 1
            except Exception as e:
                entry["byte_identity_passes_against_codec"] = None
                entry["codec_check_error"] = str(e)
            entry["n_cells_in_diff"] = len(cells)
            entry["regions"] = diff_region_summary(cells)
            summary["results"].append(entry)

    summary["overall"] = {
        "total_builds": len(plan),
        "n_byte_identity_passes_against_codec": n_pass_byte_identity_codec,
        "n_codec_mismatches": n_failed_diff,
        "n_baseline_only": sum(1 for r in summary["results"] if r["mask"] == "0x0000"),
        "wall_seconds_build": round(t_build, 1),
    }

    summary["overall"]["codec_check_interpretation"] = (
        "byte_identity_passes_against_codec is INFORMATIONAL ONLY for D1. "
        "D1's contract is producing Quartus golden RBFs; the consumer side runs "
        "the byte-identity gate against THEIR lutcodec.c, not this side's "
        "LutCodec.predict_sram. EP4CE6's predict_sram emits only the per-minterm "
        "lab_cram cells (16 max) and does NOT include canon-cells (per-position "
        "σ⁻¹ input-axis / bypass / 2-input canonicalization layer). Per Pitfall "
        "#16 in CLAUDE.md, canon-cells are silicon-mined only at X4Y4N0 and are "
        "expected to fire at other pin-friendly positions for non-trivial masks. "
        "If consumer side's lutcodec.c is also a thin predict_sram (4x18x16 σ⁻¹ "
        "entries), it will see similar mismatches and that is the empirical "
        "answer to the D2 question (canon-cells are NOT no-op at pin-friendly "
        "positions for non-symmetric masks). See sweep_summary.json results[] "
        "for per-build region breakdown."
    )
    (OUT_DIR / "sweep_summary.json").write_text(json.dumps(summary, indent=2))
    print(f"\nWrote {OUT_DIR}/sweep_summary.json")
    print(f"  byte-identity vs EP4CE6 LutCodec.predict_sram (informational): "
          f"{n_pass_byte_identity_codec} pass, {n_failed_diff} mismatch")
    print(f"  rbf + diff + cells per build under {OUT_DIR}/")
    if n_failed_diff:
        print(f"\nNOTE: {n_failed_diff} builds show mismatch vs this side's "
              f"LutCodec.predict_sram. This is EXPECTED per Pitfall #16 — "
              f"canon-cells unmined outside X4Y4N0. Goldens are still valid "
              f"D1 deliverables; consumer side runs the actual byte-identity "
              f"gate against their own lutcodec.c.")


if __name__ == "__main__":
    main()
