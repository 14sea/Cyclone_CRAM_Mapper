#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Batch-calibrate 18x512 M9K INIT anchors at multiple sites.

Same probe pattern as scripts/m9k_calib/calibrate_18x512.py (base /
w0_b0 / w1_b0 / w0_b17), but runs N sites in parallel. Used to mine
anchors for the 5-cell width=18 split that Yosys's `memory_libmap`
chooses for a 9x512 user design (see m9k_techmap_libmap_portnames
memory entry).

Output:
  results/m9k_18x512_anchor_batch.json  — derived (anchor, bp) per site
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
LOG_DIR = ROOT / "tmp" / "m9k_18x512_calib_batch"
LOG_DIR.mkdir(parents=True, exist_ok=True)

EXTRA_PINS = [
    "PIN_R5","PIN_T4","PIN_T3","PIN_R3","PIN_T2","PIN_R1","PIN_P2","PIN_P1",
    "PIN_R13","PIN_T13","PIN_R12","PIN_T12","PIN_T10","PIN_R10","PIN_T11","PIN_R11",
    "PIN_T8","PIN_P9","PIN_T9","PIN_R9","PIN_L16","PIN_L15","PIN_N16","PIN_N15",
    "PIN_P16","PIN_P15","PIN_R8","PIN_R16","PIN_T15",
    "PIN_C15","PIN_B16","PIN_A15","PIN_B14","PIN_A14","PIN_B13","PIN_A13","PIN_B12",
    "PIN_A12","PIN_B11","PIN_A11","PIN_B10","PIN_A10","PIN_B9","PIN_A9","PIN_B8",
    "PIN_A8",
    "PIN_M16","PIN_F15","PIN_G15","PIN_F16","PIN_G16",
]


def _compile(site, width, depth, tag_suffix, override):
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
    tag = f"m9k_calib18b_{site}_{tag_suffix}"
    rbf, elapsed, err = h.build(tag, overrides=ov,
                                rbf_output=str(RBF_DIR / f"{tag}.rbf"))
    loc_ok = None
    if rbf is not None:
        from m9k_loc_helper import verify_loc_honored
        proj_dir = os.path.join("work", tag)
        loc_ok, _, _ = verify_loc_honored(proj_dir, tag, site)
    return (site, tag_suffix, rbf, elapsed, err, loc_ok)


def _is_crc_byte(byte_offset: int) -> bool:
    return (byte_offset - 32) % 210 in (208, 209)


def diff_one_cell(a, b):
    diffs = [(d.byte_offset, d.bit_position) for d in diff_rbf_files(a, b)]
    return [
        (off, bp) for (off, bp) in diffs
        if off >= 32 + 5282 and not _is_crc_byte(off)
    ]


def derive_anchor(rbfs):
    """rbfs: dict suffix -> rbf path. Returns (anchor, bp) or None."""
    base = rbfs.get("base")
    if base is None:
        return None
    diffs_w0_b0  = set(diff_one_cell(base, rbfs["w0_b0"]))
    diffs_w1_b0  = set(diff_one_cell(base, rbfs["w1_b0"]))
    diffs_w0_b17 = set(diff_one_cell(base, rbfs["w0_b17"]))
    only_w0_b0 = diffs_w0_b0 - diffs_w1_b0 - diffs_w0_b17
    if len(only_w0_b0) != 1:
        return None
    (anchor, bp), = only_w0_b0
    pred_w1 = anchor - 1
    pred_b17 = anchor - 34
    if (pred_w1, bp) not in diffs_w1_b0:
        return None
    if (pred_b17, bp) not in diffs_w0_b17:
        return None
    return (anchor, bp)


def main():
    sites = sys.argv[1:] or [
        "X15_Y11_N0", "X15_Y12_N0", "X15_Y13_N0", "X15_Y14_N0",
    ]
    width, depth = 18, 512
    probe_overrides = [
        ("base",   None),
        ("w0_b0",  (0, 0)),
        ("w1_b0",  (1, 0)),
        ("w0_b17", (0, 17)),
    ]
    print(f"[calib18b] dispatching {len(sites)} sites × 4 probes = "
          f"{len(sites)*4} compiles, 4 workers")
    t0 = time.time()
    rbfs_per_site: dict[str, dict] = {s: {} for s in sites}

    with ProcessPoolExecutor(max_workers=4) as ex:
        futs = []
        for site in sites:
            for suf, ov in probe_overrides:
                futs.append(ex.submit(
                    _compile, site, width, depth, suf, ov))
        for fut in as_completed(futs):
            site, suf, rbf, elapsed, err, loc_ok = fut.result()
            tag = " " if loc_ok else "!LOC"
            status = "OK  " if rbf else "FAIL"
            print(f"  {site:14s} {suf:8s} {status} ({elapsed:.1f}s) {tag} "
                  f"{(err or '')[:120]}")
            rbfs_per_site[site][suf] = rbf

    print(f"\n[calib18b] total wall: {time.time()-t0:.1f}s\n")

    derived = {}
    for site, rbfs in rbfs_per_site.items():
        ab = derive_anchor(rbfs)
        if ab is None:
            print(f"  {site}: FAILED to derive (probes incomplete or shape mismatch)")
        else:
            anchor, bp = ab
            print(f"  {site}: anchor={anchor}, bp={bp}")
            derived[site] = {"anchor": anchor, "bp": bp,
                             "width": width, "depth": depth}

    out = ROOT / "results" / "m9k_18x512_anchor_batch.json"
    out.write_text(json.dumps(derived, indent=2) + "\n")
    print(f"\nwrote {out}")


if __name__ == "__main__":
    main()
