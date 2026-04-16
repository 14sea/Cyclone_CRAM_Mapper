#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Calibrate the 18x512 M9K INIT anchor at site X15_Y10_N0.

Mirrors fuzz/m9k_anchor_sweep.py but for width=18 (the geometry that
Yosys's `memory_libmap` picks for our open-flow smoke test). Builds 4
Quartus RBFs in parallel:

  base    — all-zero INIT
  w0_b0   — INIT[word=0, bit=0]   = 1
  w1_b0   — INIT[word=1, bit=0]   = 1
  w0_b17  — INIT[word=0, bit=17]  = 1  (top of the 18-bit word)

Diffs each probe against base in the CRAM-only / non-CRC band, then
prints the candidate `(anchor, bp)` for site X15_Y10_N0 width=18.

The 9x512 calibration formula
  byte(w, bit) = anchor + (w//2)*210 - (w%2) - 2*bit, bp=6
is *width-agnostic* in form: word stride = 210, bit stride = 2. We
expect the same shape with width=18 — just a different anchor and
possibly a different bp slot.

Output:
  results/m9k_18x512_anchor.json    — derived (anchor, bp) per site
  tmp/m9k_18x512_calib/build.log    — per-build elapsed + LOC honor
"""
from __future__ import annotations
import json, os, sys, time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(ROOT / "fuzz"))

from rbf_diff import diff_rbf_files

RBF_DIR = ROOT / "results" / "rbf"
LOG_DIR = ROOT / "tmp" / "m9k_18x512_calib"
LOG_DIR.mkdir(parents=True, exist_ok=True)

# Extra legal pins on EP4CE6F17C8 (AX301 board, headless mining — the
# pin LOC just needs to be legal; the design isn't driven on hardware).
# 47 pins needed: 1 clk + 1 wren + 9 addr + 18 din + 18 dout.
EXTRA_PINS = [
    # SDRAM data bus (16)
    "PIN_R5","PIN_T4","PIN_T3","PIN_R3","PIN_T2","PIN_R1","PIN_P2","PIN_P1",
    "PIN_R13","PIN_T13","PIN_R12","PIN_T12","PIN_T10","PIN_R10","PIN_T11","PIN_R11",
    # SDRAM addr bus (13)
    "PIN_T8","PIN_P9","PIN_T9","PIN_R9","PIN_L16","PIN_L15","PIN_N16","PIN_N15",
    "PIN_P16","PIN_P15","PIN_R8","PIN_R16","PIN_T15",
    # VGAD column (17)
    "PIN_C15","PIN_B16","PIN_A15","PIN_B14","PIN_A14","PIN_B13","PIN_A13","PIN_B12",
    "PIN_A12","PIN_B11","PIN_A11","PIN_B10","PIN_A10","PIN_B9","PIN_A9","PIN_B8",
    "PIN_A8",
    # Spillover from KEY/LED area (5+)
    "PIN_M16","PIN_F15","PIN_G15","PIN_F16","PIN_G16",
]


def _compile(site, width, depth, tag_suffix, override):
    """Worker: patch harness globals then build one RBF."""
    import m9k_init_harness as h
    h.M9K_LOC = f"M9K_{site}"
    h.M9K_NODE = "u"
    h.WIDTH = width
    h.DEPTH = depth
    h.ADDR_BITS = (depth - 1).bit_length()
    h._FREE_PINS = EXTRA_PINS
    pins = {"clk": "PIN_E1", "wren": "PIN_E15"}
    for i in range(h.ADDR_BITS):
        pins[f"addr{i}"] = h._FREE_PINS[i]
    for i in range(width):
        pins[f"din{i}"] = h._FREE_PINS[h.ADDR_BITS + i]
    for i in range(width):
        pins[f"dout{i}"] = h._FREE_PINS[h.ADDR_BITS + width + i]
    h.PINS = pins

    if override is None:
        ov = None
    else:
        w, b = override
        ov = {w: 1 << b}
    tag = f"m9k_calib18_{site}_{tag_suffix}"
    rbf, elapsed, err = h.build(tag, overrides=ov,
                                rbf_output=str(RBF_DIR / f"{tag}.rbf"))
    loc_ok, loc_actual, loc_reason = (None, None, "")
    if rbf is not None:
        from m9k_loc_helper import verify_loc_honored
        proj_dir = os.path.join("work", tag)
        loc_ok, loc_actual, loc_reason = verify_loc_honored(
            proj_dir, tag, site
        )
    return (site, tag_suffix, rbf, elapsed, err,
            loc_ok, loc_actual, loc_reason)


def _is_crc_byte(byte_offset: int) -> bool:
    return (byte_offset - 32) % 210 in (208, 209)


def diff_one_cell(a, b):
    diffs = [(d.byte_offset, d.bit_position) for d in diff_rbf_files(a, b)]
    return [
        (off, bp) for (off, bp) in diffs
        if off >= 32 + 5282 and not _is_crc_byte(off)
    ]


def main():
    site = "X15_Y10_N0"
    width, depth = 18, 512
    probes = [
        ("base",   None),
        ("w0_b0",  (0, 0)),
        ("w1_b0",  (1, 0)),
        ("w0_b17", (0, 17)),
    ]
    print(f"[calib18] dispatching {len(probes)} compiles for {site} "
          f"({width}x{depth}) across 4 workers")
    t0 = time.time()
    results = {}
    with ProcessPoolExecutor(max_workers=4) as ex:
        futs = [ex.submit(_compile, site, width, depth, suf, ov)
                for suf, ov in probes]
        for fut in as_completed(futs):
            (site, suf, rbf, elapsed, err,
             loc_ok, loc_actual, loc_reason) = fut.result()
            tag = " " if loc_ok else "!LOC"
            status = "OK  " if rbf else "FAIL"
            print(f"  {suf:8s} {status} ({elapsed:.1f}s) {tag} "
                  f"{loc_reason or err[:160]}")
            results[suf] = (rbf, loc_ok, loc_reason)
    print(f"\n[calib18] total wall: {time.time()-t0:.1f}s\n")

    # --- Derive (anchor, bp) ---
    base = results["base"][0]
    if base is None:
        sys.exit("base build failed; cannot derive anchor")

    diffs_w0_b0  = diff_one_cell(base, results["w0_b0"][0])
    diffs_w1_b0  = diff_one_cell(base, results["w1_b0"][0])
    diffs_w0_b17 = diff_one_cell(base, results["w0_b17"][0])

    print(f"diffs[w0_b0]  = {diffs_w0_b0}")
    print(f"diffs[w1_b0]  = {diffs_w1_b0}")
    print(f"diffs[w0_b17] = {diffs_w0_b17}")

    # Pick the anchor candidate as a cell that appears ONLY in w0_b0.
    # The 9x512 calibration uses bp=fixed-per-site; we expect the same.
    s_w0b0  = set(diffs_w0_b0)
    s_w1b0  = set(diffs_w1_b0)
    s_w0b17 = set(diffs_w0_b17)
    only_w0_b0 = s_w0b0 - s_w1b0 - s_w0b17

    print(f"\ncells only in w0_b0: {sorted(only_w0_b0)}")

    if len(only_w0_b0) == 1:
        (anchor, bp), = only_w0_b0
        # Verify shape with formula
        # w1_b0 should be at byte = anchor + (1//2)*210 - 1 = anchor - 1
        # w0_b17 should be at byte = anchor - 2*17 = anchor - 34
        pred_w1 = anchor - 1
        pred_b17 = anchor - 34
        ok_w1 = (pred_w1, bp) in s_w1b0
        ok_b17 = (pred_b17, bp) in s_w0b17
        print(f"\nanchor candidate: byte={anchor} bp={bp}")
        print(f"  predicts w1_b0 at byte={pred_w1} : "
              f"{'OK' if ok_w1 else 'MISS'}")
        print(f"  predicts w0_b17 at byte={pred_b17} : "
              f"{'OK' if ok_b17 else 'MISS'}")
        out = {
            "site": site, "width": width, "depth": depth,
            "anchor": anchor, "bp": bp,
            "verified_w1_b0": ok_w1,
            "verified_w0_b17": ok_b17,
        }
        out_path = ROOT / "results" / "m9k_18x512_anchor.json"
        out_path.write_text(json.dumps(out, indent=2) + "\n")
        print(f"\nwrote {out_path}")
    else:
        print("WARN: anchor candidate is ambiguous, manual review needed")
        print(f"  w0_b0 ∩ ¬w1_b0 ∩ ¬w0_b17 = {sorted(only_w0_b0)}")


if __name__ == "__main__":
    main()
