# SPDX-License-Identifier: GPL-3.0-or-later
"""Classify the 53-cell residual between directive-applied synth and Quartus
FORCE-mode reference at LAB(10,4).N0, PIN_E1.

Buckets:
  header   : off < 5282 (should be 0 — we already filter)
  iob_band : frames 25..29 (adjacent to header, I/O ring cells)
  lab_X    : within [col_base[X], col_base[X] + 7350)
  non_lab  : the remainder (gaps between LAB cols / high-addr frames)

Target LAB is X=10 → col_base 0x13F9E.  The sink LE is N=0.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))

import fasm2rbf as f

HDR = 32
FRAME = 210
CRC_SLOT = 208
HEADER_BAND_END = 5282  # off < this = header

# From analyze.py known_bases (CE6 whitelist)
COL_BASES = {
    3: 0x076A4, 4: 0x0935A, 6: 0x0CCC6, 7: 0x0E97C,
    8: 0x10632, 10: 0x13F9E, 11: 0x15C54, 12: 0x1790A,
    13: 0x195C0, 16: 0x2BF86, 17: 0x2DC3C, 18: 0x2FC3A,
    19: 0x318F0, 21: 0x34A28, 22: 0x366DE, 23: 0x38394,
    24: 0x3A04A, 25: 0x3BD00, 26: 0x3D9B6, 28: 0x4E6C6,
    29: 0x5037C, 31: 0x53CE8,
}
LAB_STEP = 7350


def cell_diff(a: bytes, b: bytes):
    out = set()
    for i in range(HDR, min(len(a), len(b))):
        if (i - 32) % FRAME >= CRC_SLOT:
            continue
        x = a[i] ^ b[i]
        if x:
            for bp in range(8):
                if (x >> bp) & 1:
                    out.add((i, bp))
    return out


def classify(off: int) -> tuple[str, object]:
    frame = (off - 32) // FRAME
    if off < HEADER_BAND_END:
        return ("header", frame)
    if frame < 30:
        return ("iob_band", frame)
    for x, base in COL_BASES.items():
        if base <= off < base + LAB_STEP:
            rel = off - base
            return (f"lab_X{x}", (frame, rel))
    return ("non_lab", frame)


def main():
    RBF = ROOT / "results" / "rbf"
    auto = (RBF / "fgclk_AUTO_X10Y10N0_to_X10Y4N0.rbf").read_bytes()
    force = (RBF / "fgclk_FORCE_X10Y10N0_to_X10Y4N0.rbf").read_bytes()

    ground = cell_diff(auto, force)
    e1 = set(f._load_gclk_pin_cells("E1"))
    labsel = set(f._load_lab_clk_sel_cells(10, 4))
    ours = e1 | labsel
    residual = ground - ours

    print(f"ground truth:  {len(ground)} cells")
    print(f"our directive: {len(ours)} cells")
    print(f"residual:      {len(residual)} cells\n")

    # Classify each cell
    buckets: dict[str, list] = {}
    for off, bp in sorted(residual):
        cat, meta = classify(off)
        buckets.setdefault(cat, []).append((off, bp, meta))

    for cat in sorted(buckets):
        cells = buckets[cat]
        print(f"=== {cat}: {len(cells)} cells ===")
        for off, bp, meta in cells:
            frame = (off - 32) // FRAME
            print(f"    off={off:6d} bp={bp}  frame={frame:4d}  meta={meta}")
        print()

    # Cross-check against known IOB / target LAB
    print("=== summary ===")
    for cat, cells in sorted(buckets.items()):
        print(f"  {cat:14s}: {len(cells):3d} cells")

    # Is target-LAB cell set at X=10? Should be the interesting "per-(LAB,N)" layer
    target = buckets.get("lab_X10", [])
    if target:
        # Summarize sub-frames within X=10 col
        frames = sorted(set((c[0] - 32) // FRAME for c in target))
        print(f"\n  lab_X10 frame range: {min(frames)}..{max(frames)}  "
              f"distinct frames: {len(frames)}")

    # Cross-check: how many residual cells are in results/iob_cell_map.json
    iob_path = ROOT / "results" / "iob_cell_map.json"
    if iob_path.exists():
        iob_data = json.loads(iob_path.read_text())
        iob_all = set()
        for pin_map in iob_data.values():
            if isinstance(pin_map, dict):
                for cells in pin_map.values():
                    if isinstance(cells, list):
                        iob_all.update(tuple(c) for c in cells)
        iob_hits = residual & iob_all
        print(f"\n  residual ∩ iob_cell_map: {len(iob_hits)} / {len(residual)} cells")
        if iob_hits:
            for off, bp in sorted(iob_hits):
                print(f"    off={off:6d} bp={bp}")

    out_path = ROOT / "results" / "clk_residual_classify.json"
    out_path.write_text(json.dumps({
        "ground_truth_count": len(ground),
        "directive_count": len(ours),
        "residual_count": len(residual),
        "buckets": {k: [[c[0], c[1]] for c in v] for k, v in buckets.items()},
    }, indent=2))
    print(f"\nwrote {out_path}")


if __name__ == "__main__":
    main()
