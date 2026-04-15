# SPDX-License-Identifier: GPL-3.0-or-later
"""For each residue cell, identify WHICH directive contributed it.

Model: fasm_out = nv ^ (XOR of directive cell sets with parity).
gold = nv ^ gold_delta (the cells simple_led actually needs).
residue = fasm_out ^ gold = (directive_cells XOR gold_delta).

So residue splits into:
  - over-applied : cells in directive XOR sum but NOT in gold_delta
                   -> some directive is adding a cell gold doesn't have
  - under-applied: cells in gold_delta but NOT in directive XOR sum
                   -> some directive is missing a cell gold has

Per over-applied cell we identify which directive(s) contributed it
(with parity).  Per under-applied cell we verify it's not covered by
any directive.
"""
from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
sys.path.insert(0, str(REPO / "fuzz"))

import fasm2rbf as f  # noqa: E402


PRE = 32
FRAME = 210
FIRST = 25
LAST = 1751
CRAM_START = PRE + FIRST * FRAME
CRAM_END = PRE + (LAST + 1) * FRAME


def bit_cells_in(rbf_xor: bytes) -> set[tuple[int, int]]:
    out = set()
    for i, b in enumerate(rbf_xor):
        if not b:
            continue
        for bp in range(8):
            if b & (1 << bp):
                out.add((i, bp))
    return out


def is_crc_byte(off: int) -> bool:
    if off < PRE or off >= CRAM_END:
        return False
    return (off - PRE) % FRAME >= 208


def main() -> int:
    nv = (REPO / "results" / "rbf" / "nv_zero_global.rbf").read_bytes()
    gold = ((HERE / "work" / "simple_led_E16_to_G15"
             / "output_files" / "simple_led_E16_to_G15.rbf")
            .read_bytes())

    gold_xor = bytes(a ^ b for a, b in zip(gold, nv))
    gold_delta = bit_cells_in(gold_xor)
    # drop CRC and trailer
    gold_delta = {c for c in gold_delta
                  if not is_crc_byte(c[0]) and c[0] < CRAM_END}
    print(f"gold_delta (non-CRC, in-band): {len(gold_delta)} cells")

    # Reset caches
    f._IOB_BASELINE_HDR_CACHE = None
    f._IOB_MAP_CACHE = None
    f._IOB_ROUTE_CACHE = None
    f._GCLK_PIN_CACHE = None
    f._LAB_CLK_SEL_CACHE.clear()
    f._LAB_CLK_SEL_LE_CACHE = None
    f._IOB_CLK_INPUT_CACHE = None

    iob_map = f._load_iob_map()
    contributions = {
        "IOB_BASELINE_NV":
            {tuple(c) for c in f._load_iob_baseline_hdr_cells()},
        "IOB_IN E16":
            {tuple(c) for c in f._iob_delta_cells("IN", "E16", iob_map)},
        "IOB_OUT G15":
            {tuple(c) for c in f._iob_delta_cells("OUT", "G15", iob_map)},
        "IOB_CLK_INPUT E1":
            {tuple(c) for c in f._load_iob_clk_input_cells("E1")},
        "IOB_ROUTE E16->10,4,0,dataa":
            set(f._load_iob_route_cells("E16", 10, 4, 0, "dataa")),
        "GCLK_PIN E1":
            set(f._load_gclk_pin_cells("E1")),
        "LAB_CLK_SEL 10,4":
            set(f._load_lab_clk_sel_cells(10, 4)),
        "LAB_CLK_SEL_LE 10,4,0":
            set(f._load_lab_clk_sel_le_cells(10, 4, 0)),
    }

    # Drop empties (missing loaders)
    contributions = {k: v for k, v in contributions.items() if v}
    for name, cells in contributions.items():
        print(f"  {name:34s}: {len(cells)} cells")

    # XOR parity across all directives
    parity = Counter()
    for cells in contributions.values():
        for c in cells:
            parity[c] ^= 1
    applied = {c for c, v in parity.items() if v}
    # restrict to non-CRC, in-band
    applied = {c for c in applied
               if not is_crc_byte(c[0]) and c[0] < CRAM_END}
    print(f"Applied XOR parity (non-CRC, in-band): {len(applied)} cells")

    over = applied - gold_delta
    under = gold_delta - applied
    print(f"Over-applied : {len(over)} cells (in directives, not in gold)")
    print(f"Under-applied: {len(under)} cells (in gold, not in directives)")

    # Which directive contributed each over cell?
    attr = defaultdict(list)
    for c in sorted(over):
        sources = [k for k, v in contributions.items() if c in v]
        attr[tuple(sources)].append(c)
    print(f"\nOver-applied cell attribution (top 10 source sets):")
    for srcs, cs in sorted(attr.items(), key=lambda kv: -len(kv[1]))[:10]:
        print(f"  {srcs}: {len(cs)} cells")

    # Under-applied cells: no directive has them
    print(f"\nUnder-applied cells — distribution by frame (top 10):")
    bin_under = Counter((c[0] - PRE) // FRAME for c in under if c[0] >= PRE)
    for fr, n in bin_under.most_common(10):
        print(f"  frame {fr:4d}: {n}")
    # Show first 10
    for c in sorted(under)[:10]:
        fr = (c[0] - PRE) // FRAME
        print(f"    {c} frame={fr}")

    # Save breakdown for later use
    out = {
        "over_applied": {
            " + ".join(k) if isinstance(k, tuple) else k:
                [list(c) for c in v]
            for k, v in attr.items()
        },
        "under_applied": [list(c) for c in sorted(under)],
        "counts": {
            "gold_delta": len(gold_delta),
            "applied": len(applied),
            "over": len(over),
            "under": len(under),
        },
    }
    out_path = HERE / "work" / "residue_attribution.json"
    out_path.write_text(json.dumps(out, indent=2))
    print(f"\n[wrote] {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
