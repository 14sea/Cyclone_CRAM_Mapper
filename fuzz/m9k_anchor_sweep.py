#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Phase 5.2 Stage B follow-up — anchor calibration sweep.

For each candidate (site, width, depth) configuration, compile:
  base             — all-zero init
  probe_w0_b0      — word=0 bit=0 set
  probe_w1_b0      — word=1 bit=0 set
  probe_w0_b8      — word=0 bit=8 set (highest bit of 9-bit word)

Then derive the anchor from probe_w0_b0 and verify it predicts the
other two probes using the locked 2D formula
    byte(w, bit) = anchor + (w//2)*210 - (w%2) - 2*bit,  bp=6.

Writes results/m9k_anchor_sweep.json with verified anchors.
"""
import json, os, sys, time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from rbf_diff import diff_rbf_files

ROOT = HERE.parent
RBF_DIR = ROOT / "results" / "rbf"

# Sites to probe. Keep 9x512 so we isolate the *site* axis first; once
# that generalizes, a second pass can vary WIDTH/DEPTH.
SITES = [
    # Gap sites — the 12 NEORV32 M9K positions still missing a 9x512
    # INIT anchor after the 2026-04-24f session.  Restricted list so
    # this sweep is ~10 min instead of ~40.  The 31 sites mined in
    # earlier sessions are preserved in fuzz/m9k_init_basis.py; this
    # run only appends the gap.
    *[(f"X15_Y{y}_N0", 9, 512) for y in (2, 3, 4, 7)],
    *[(f"X27_Y{y}_N0", 9, 512) for y in (2, 3, 5, 6, 7, 8, 9, 10)],
]

PROBES = [
    ("base",    None),
    ("w0_b0",   (0, 0)),
    ("w1_b0",   (1, 0)),
    ("w0_b8",   (0, 8)),
]


def _compile(site, width, depth, tag_suffix, override):
    """Worker: patch harness globals then build one RBF."""
    import m9k_init_harness as h
    h.M9K_LOC = f"M9K_{site}"
    # Use the harness default M9K_NODE ("u" — Verilog instance name).
    # Earlier attempts with `altsyncram:u|*|ALTSYNCRAM` or the exact
    # hierarchical wrapper path both triggered Fitter warning 15706
    # ("does not exist in design") and silently auto-placed the M9K.
    h.M9K_NODE = "u"
    h.WIDTH = width
    h.DEPTH = depth
    h.ADDR_BITS = (depth - 1).bit_length()
    # Rebuild pin map for the requested width/depth
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
    tag = f"m9k_as_{site}_{width}x{depth}_{tag_suffix}"
    rbf, elapsed, err = h.build(tag, overrides=ov,
                                rbf_output=str(RBF_DIR / f"{tag}.rbf"))
    # Post-compile sanity: confirm Quartus actually placed the M9K at
    # the requested site. If not, the RBF is from an auto-placed
    # block and its anchor is NOT the one the caller asked for.
    loc_ok = None
    loc_actual = None
    loc_reason = ""
    if rbf is not None:
        from m9k_loc_helper import verify_loc_honored
        import os
        proj_dir = os.path.join("work", tag)
        loc_ok, loc_actual, loc_reason = verify_loc_honored(
            proj_dir, tag, site
        )
    return (site, width, depth, tag_suffix, rbf, elapsed, err,
            loc_ok, loc_actual, loc_reason)


def _is_crc_byte(byte_offset: int) -> bool:
    """Per-frame CRC slot (210-byte frames, offsets 208/209)."""
    return (byte_offset - 32) % 210 in (208, 209)


def diff_one_cell(a, b):
    """Return CRAM-only, non-CRC diff cells between two RBFs.

    Filters header band (off<32+5282) and per-frame CRC byte slots
    (offsets 208/209 within each 210-byte frame). No bp filter —
    ``bp`` is per-site (X27_Y4_N0 = 6, X27_Y16_N0 LED harness = 2),
    so fixing bp would drop valid singletons on any site whose
    primary row isn't bp=6.
    """
    diffs = [(d.byte_offset, d.bit_position) for d in diff_rbf_files(a, b)]
    return [
        (off, bp) for (off, bp) in diffs
        if off >= 32 + 5282 and not _is_crc_byte(off)
    ]


def main():
    tasks = []
    for site, w, d in SITES:
        for tag_suf, ov in PROBES:
            tasks.append((site, w, d, tag_suf, ov))

    print(f"dispatching {len(tasks)} compiles across 4 workers "
          f"({len(SITES)} sites)")
    t0 = time.time()
    out = {}
    loc_status = {}  # key -> (honored, actual_site, reason)
    with ProcessPoolExecutor(max_workers=4) as ex:
        futs = [ex.submit(_compile, *t) for t in tasks]
        for fut in as_completed(futs):
            (site, w, d, suf, rbf, elapsed, err,
             loc_ok, loc_actual, loc_reason) = fut.result()
            key = f"{site}_{w}x{d}"
            if rbf is None:
                print(f"  {key:28s} {suf:8s} FAIL ({elapsed:.1f}s): "
                      f"{err[:160]}")
                out.setdefault(key, {})[suf] = None
            else:
                tag = " " if loc_ok else "!LOC"
                print(f"  {key:28s} {suf:8s} OK   ({elapsed:.1f}s) "
                      f"{tag} {loc_reason}")
                out.setdefault(key, {})[suf] = rbf
                # Track per-(key) LOC honor — if ANY probe within a
                # key is auto-placed, the whole key's anchor is
                # compromised and we must not emit an anchor for it.
                prev = loc_status.get(key)
                if prev is None or not prev[0]:
                    loc_status[key] = (loc_ok, loc_actual, loc_reason)
    print(f"\ntotal wall: {time.time()-t0:.1f}s\n")

    anchors = {}
    for key, results in out.items():
        if any(v is None for v in results.values()):
            print(f"{key}: SKIP (compile failure)")
            continue
        status = loc_status.get(key)
        if status is not None and not status[0]:
            print(f"{key}: SKIP (LOC ignored by Quartus — "
                  f"actual site {status[1]}; {status[2]})")
            continue
        base = results["base"]
        c_w0b0 = diff_one_cell(base, results["w0_b0"])
        c_w1b0 = diff_one_cell(base, results["w1_b0"])
        c_w0b8 = diff_one_cell(base, results["w0_b8"])
        if len(c_w0b0) != 1:
            print(f"{key}: w0_b0 diff not singleton ({len(c_w0b0)} cells) "
                  f"— noise or routing echo, skipping")
            continue
        anchor, bp = c_w0b0[0]
        # bp is per-site; do NOT hardcode 6 here. Stage B formula
        # structure expected to hold with whichever bp the anchor
        # probe lands on.
        # Predict w1_b0: byte = anchor + 0 - 1 - 0 = anchor - 1
        # Predict w0_b8: byte = anchor + 0 - 0 - 16 = anchor - 16
        pred_w1 = (anchor - 1, bp)
        pred_b8 = (anchor - 16, bp)
        ok_w1 = pred_w1 in c_w1b0
        ok_b8 = pred_b8 in c_w0b8
        status = "OK" if (ok_w1 and ok_b8) else "FORMULA MISMATCH"
        print(f"{key}: anchor={anchor} bp={bp}  "
              f"w1_b0:{'+' if ok_w1 else '-'} "
              f"w0_b8:{'+' if ok_b8 else '-'}  {status}")
        anchors[key] = {
            "site": key.rsplit("_", 1)[0],
            "anchor": anchor,
            "bp": bp,
            "verified_w1_b0": ok_w1,
            "verified_w0_b8": ok_b8,
            "w1_b0_cells": c_w1b0,
            "w0_b8_cells": c_w0b8,
        }

    out_path = ROOT / "results" / "m9k_anchor_sweep.json"
    out_path.write_text(json.dumps(anchors, indent=1))
    print(f"\narchived {out_path}")


if __name__ == "__main__":
    main()
