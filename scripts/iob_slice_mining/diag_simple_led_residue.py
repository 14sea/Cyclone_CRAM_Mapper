# SPDX-License-Identifier: GPL-3.0-or-later
"""Diagnose where simple_led FASM build differs from Quartus gold.

Isolates the ~140-byte CRAM data residue remaining after the
IOB_BASELINE_NV + IOB_IN + IOB_OUT + IOB_CLK_INPUT + IOB_ROUTE +
GCLK_PIN + LAB_CLK_SEL + LAB_CLK_SEL_LE stack:

  - Enumerate bit-level cells that differ between fasm.rbf and gold.rbf
  - Classify by frame (CRAM frame number, 25..1751)
  - Check whether each residue cell is present in iob_to_slice_sigcache's
    absolute_cells for (E16, 10_4_0, dataa) — that pinpoints pair-template
    secondary-LE decoration.
"""
from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent

PRE = 32
FRAME = 210
FIRST = 25
LAST = 1751
CRAM_START = PRE + FIRST * FRAME          # 5282
CRAM_END = PRE + (LAST + 1) * FRAME       # 368192


def bit_cells_between(a: bytes, b: bytes) -> set[tuple[int, int]]:
    """Return set of (off, bp) where a and b differ."""
    assert len(a) == len(b)
    out = set()
    for i in range(len(a)):
        if a[i] != b[i]:
            x = a[i] ^ b[i]
            for bp in range(8):
                if x & (1 << bp):
                    out.add((i, bp))
    return out


def frame_of(off: int) -> int:
    if off < PRE:
        return -1
    return (off - PRE) // FRAME


def is_crc_byte(off: int) -> bool:
    if off < PRE or off >= CRAM_END:
        return False
    rel = off - PRE
    within = rel % FRAME
    return within >= 208


def main() -> int:
    fasm = (HERE / "work" / "simple_led_E16_to_G15" / "fasm.rbf").read_bytes()
    gold = (HERE / "work" / "simple_led_E16_to_G15"
            / "output_files" / "simple_led_E16_to_G15.rbf").read_bytes()

    residue = bit_cells_between(fasm, gold)
    print(f"Total bit-cell residue: {len(residue)} cells "
          f"in {len({o for o, _ in residue})} bytes")

    # CRC vs data split
    crc = {(o, bp) for (o, bp) in residue if is_crc_byte(o)}
    data = residue - crc
    print(f"  CRC-byte cells : {len(crc)} (in {len({o for o, _ in crc})} bytes)")
    print(f"  data cells     : {len(data)} (in {len({o for o, _ in data})} bytes)")

    # Classify data cells by frame
    frame_bin = Counter(frame_of(o) for o, _ in data)
    print(f"\nData cells by frame (top 15):")
    for f, n in frame_bin.most_common(15):
        print(f"  frame {f:4d}: {n}")

    # Check overlap with IOB_ROUTE absolute cells
    sig_path = REPO / "results" / "iob_to_slice_sigcache.json"
    sig = json.loads(sig_path.read_text())["absolute_cells"]
    route_key = "IOB_E16->10,4,0,dataa"
    route_cells = {tuple(c) for c in sig[route_key]}
    data_in_route = data & route_cells
    data_not_in_route = data - route_cells
    print(f"\nData residue vs IOB_ROUTE absolute_cells (key={route_key}):")
    print(f"  residue cells IN route_cells    : {len(data_in_route)}")
    print(f"  residue cells NOT in route_cells: {len(data_not_in_route)}")

    # For residue-in-route: these are cells that IOB_ROUTE applies but
    # simple_led gold DOES NOT have — i.e., secondary-LE decoration
    # that shouldn't be in a single-LE design.
    # For residue-not-in-route: cells that are OTHERWISE introduced (e.g.,
    # by GCLK_PIN / LAB_CLK_SEL / IOB_IN/OUT cell maps that disagree with
    # simple_led's Quartus gold).

    # Check overlap against pin_footprint(E16) and pure_common((10,4,0))
    # from iob_route_decomposed.json — these are DELTA-frame cells, not
    # absolute, so we have to lift into absolute.  Simpler: check against
    # iob_route_cells.json entries.

    # Frame classification
    print(f"\nResidue cells IN route_cells, top 10 frames:")
    bin_in = Counter(frame_of(o) for (o, _) in data_in_route)
    for f, n in bin_in.most_common(10):
        print(f"  frame {f:4d}: {n}")
    print(f"\nResidue cells NOT in route_cells, top 10 frames:")
    bin_out = Counter(frame_of(o) for (o, _) in data_not_in_route)
    for f, n in bin_out.most_common(10):
        print(f"  frame {f:4d}: {n}")

    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
