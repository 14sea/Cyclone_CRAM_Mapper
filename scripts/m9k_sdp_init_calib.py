# SPDX-License-Identifier: GPL-3.0-or-later
"""Calibrate M9K INIT CRAM positions for SDP 4×2048 mode.

Builds an SDP 4×2048 blink with all-zero INIT and diffs against the
existing half-half blink (words 1024..2047 = 0xF). The XOR cells are
the CRAM bit positions that encode those INIT words.

Usage:
  python3 scripts/m9k_sdp_init_calib.py [--site 15,10,0] [--build]

With --build: runs Quartus to produce the zero-INIT variant.
Without --build: prints info using any existing zero-INIT RBF at tmp/.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "fuzz"))

from m9k_init_basis import M9K_INIT_ANCHORS, init_cell, read_init

FRAME_SIZE = 210


def _find_rbf(site_str: str) -> Path:
    suffix = "" if site_str == "15,10,0" else f"_X{site_str.replace(',','_Y').replace(',','_N')}"
    p = ROOT / "tmp" / f"m9k_sdp_blink_4x2048{suffix}" / f"m9k_sdp_blink_4x2048{suffix}.rbf"
    return p


def _build_zero_init(site_x: int, site_y: int, site_n: int) -> Path:
    """Build SDP blink with ALL_ZERO INIT, return RBF path."""
    import importlib.util, types, os
    spec = importlib.util.spec_from_file_location(
        "m9k_sdp_blink_build",
        ROOT / "scripts" / "m9k_sdp_blink_build.py",
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    # Patch globals before calling build()
    mod.SITE_X = site_x
    mod.SITE_Y = site_y
    mod.SITE_N = site_n

    # Override MIF to all-zero
    _orig_mif = mod._mif
    def _all_zero_mif():
        depth, width = 2048, 4
        lines = [
            f"DEPTH = {depth};", f"WIDTH = {width};",
            "ADDRESS_RADIX = HEX;", "DATA_RADIX = HEX;",
            "CONTENT BEGIN",
        ]
        for i in range(depth):
            lines.append(f"  {i:03X} : 0;")
        lines.append("END;")
        return "\n".join(lines) + "\n"
    mod._mif = _all_zero_mif

    # Override project name to avoid clobbering the existing blink
    site_sfx = f"_X{site_x}_Y{site_y}_N{site_n}"
    work = ROOT / "tmp" / f"m9k_sdp_blink_4x2048_allzero{site_sfx}"
    from compile import setup_project, compile_full, generate_rbf
    work.mkdir(parents=True, exist_ok=True)
    project = f"m9k_sdp_blink_4x2048_allzero{site_sfx}"
    v = mod._verilog()
    q = mod._qsf()
    proj_dir = setup_project(project, v, q, str(work))
    (Path(proj_dir) / "mem_init.mif").write_text(mod._mif())
    ok, el, err = compile_full(project, proj_dir, timeout=300)
    if not ok:
        sys.exit(f"all-zero build FAIL ({el:.1f}s): {err}")
    rbf = generate_rbf(project, proj_dir, str(work / f"{project}.rbf"))
    if rbf is None:
        sys.exit("all-zero RBF generation failed")
    return Path(rbf)


def calibrate(gold_rbf: Path, zero_rbf: Path, site_str: str, width=4, depth=2048) -> None:
    """Diff gold vs zero-init, characterise INIT bit positions."""
    gold = bytearray(gold_rbf.read_bytes())
    zero = bytearray(zero_rbf.read_bytes())

    if len(gold) != len(zero):
        sys.exit(f"length mismatch: {len(gold)} vs {len(zero)}")

    # XOR delta = cells that differ (= INIT cells for non-zero words + potential MODE diff)
    diffs: list[tuple[int, int]] = []  # (byte_offset, bit_pos)
    for i, (a, b) in enumerate(zip(gold, zero)):
        x = a ^ b
        for bp in range(8):
            if x & (1 << bp):
                diffs.append((i, bp))

    print(f"Total XOR cells: {len(diffs)}")

    # Expected INIT cells from formula: words 1024..2047 (high half = 0xF in gold)
    key = (f"X{site_str.replace(',', '_Y').replace(',', '_N')}", width, depth)
    # Reconstruct site key
    sx, sy, sn = site_str.split(",")
    site_key = (f"X{sx}_Y{sy}_N{sn}", width, depth)
    if site_key not in M9K_INIT_ANCHORS:
        print(f"WARNING: {site_key} not in M9K_INIT_ANCHORS — using formula with sp anchor")
        anchor, bp_anchor = M9K_INIT_ANCHORS[(f"X{sx}_Y{sy}_N{sn}", 9, 512)]
    else:
        anchor, bp_anchor = M9K_INIT_ANCHORS[site_key]
    print(f"Anchor for {site_key}: byte={anchor} bp={bp_anchor}")

    # Predicted cells from formula
    predicted: set[tuple[int, int]] = set()
    for w in range(1024, 2048):  # high half (= 0xF in gold)
        for bit in range(width):
            byte, bp = init_cell(anchor, w, bit, bp=bp_anchor)
            predicted.add((byte, bp))
    print(f"Predicted INIT cells (high half, formula): {len(predicted)}")

    diff_set = set(diffs)
    tp = len(diff_set & predicted)
    fp = len(diff_set - predicted)
    fn = len(predicted - diff_set)
    print(f"Formula TP={tp}, FP={fp} (extra in diff), FN={fn} (predicted but missing)")

    if tp == 0:
        print("\nFormula has ZERO overlap — different storage region for SDP INIT")
        # Let's understand the actual XOR pattern
        print("\nSample of actual XOR cells (first 20):")
        for off, bp in sorted(diffs)[:20]:
            frame_off = (off - 32) % FRAME_SIZE
            frame_idx = (off - 32) // FRAME_SIZE
            print(f"  off={off} byte_in_frame={frame_off} frame={frame_idx} bp={bp}")
        print(f"\nSample of predicted cells (first 10):")
        for off, bp in sorted(predicted)[:10]:
            frame_off = (off - 32) % FRAME_SIZE
            frame_idx = (off - 32) // FRAME_SIZE
            print(f"  off={off} byte_in_frame={frame_off} frame={frame_idx} bp={bp}")
    else:
        print(f"\nFormula recall = {tp}/{tp+fn} = {tp/(tp+fn)*100:.1f}%")
        if fp:
            print(f"Extra cells (not predicted — may be MODE diffs):")
            for off, bp in sorted(diff_set - predicted)[:10]:
                frame_off = (off - 32) % FRAME_SIZE
                frame_idx = (off - 32) // FRAME_SIZE
                print(f"  off={off} bif={frame_off} frame={frame_idx} bp={bp}")

    # Frame distribution of actual diffs
    frame_counts: dict[int, int] = {}
    for off, _bp in diffs:
        fidx = (off - 32) // FRAME_SIZE
        frame_counts[fidx] = frame_counts.get(fidx, 0) + 1
    if frame_counts:
        print(f"\nFrame distribution (top 10 frames by cell count):")
        for f, cnt in sorted(frame_counts.items(), key=lambda x: -x[1])[:10]:
            print(f"  frame {f:4d}: {cnt} cells")

    # Within-frame byte distribution (bp=anchor check)
    byte_in_frame_set = set((off - 32) % FRAME_SIZE for off, _ in diffs)
    print(f"\nDistinct byte-in-frame positions: {sorted(byte_in_frame_set)[:20]}")
    bp_set = set(bp for _, bp in diffs)
    print(f"Distinct bp values: {sorted(bp_set)}")

    # Check if diffs align to a simple read_init formula with different bp
    print(f"\nTrying all 8 bp values for anchor {anchor}:")
    for try_bp in range(8):
        pred = set()
        for w in range(1024, 2048):
            for bit in range(width):
                byte, bp = init_cell(anchor, w, bit, bp=try_bp)
                pred.add((byte, bp))
        tp2 = len(diff_set & pred)
        fn2 = len(pred - diff_set)
        if tp2 > 0:
            print(f"  bp={try_bp}: TP={tp2}/{len(pred)}, FN={fn2}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--site", default="15,10,0")
    ap.add_argument("--build", action="store_true",
                    help="run Quartus to build all-zero INIT variant")
    args = ap.parse_args()

    sx, sy, sn = (int(v) for v in args.site.split(","))
    sfx = "" if args.site == "15,10,0" else f"_X{sx}_Y{sy}_N{sn}"
    gold_rbf = ROOT / "tmp" / f"m9k_sdp_blink_4x2048{sfx}" / f"m9k_sdp_blink_4x2048{sfx}.rbf"
    zero_rbf = ROOT / "tmp" / f"m9k_sdp_blink_4x2048_allzero_X{sx}_Y{sy}_N{sn}" / \
               f"m9k_sdp_blink_4x2048_allzero_X{sx}_Y{sy}_N{sn}.rbf"

    if not gold_rbf.exists():
        sys.exit(f"Gold blink not found: {gold_rbf}\nRun: python3 scripts/m9k_sdp_blink_build.py --site {args.site}")

    if not zero_rbf.exists():
        if not args.build:
            sys.exit(f"Zero-INIT build not found: {zero_rbf}\nRe-run with --build to generate it")
        print("Building all-zero INIT SDP blink ...")
        zero_rbf = _build_zero_init(sx, sy, sn)
        print(f"Built: {zero_rbf}")

    print(f"Gold : {gold_rbf}")
    print(f"Zero : {zero_rbf}")
    calibrate(gold_rbf, zero_rbf, args.site)


if __name__ == "__main__":
    main()
