# SPDX-License-Identifier: GPL-3.0-or-later
"""Decompose LAB_CLK_SEL N-invariant cells into direction-typed buckets.

The XOR diff `forced ^ auto` collapses two opposite-direction effects:
  1. cells SET in auto, CLEARED in forced  → local-clock distribution
     that gets *disabled* by GCLK promotion (auto-only).
  2. cells CLEARED in auto, SET in forced  → GCLK-enable infrastructure
     (forced-only).

Both buckets show up identically in the XOR diff used by
`clk_lab_sel_probe.py`, but they have very different meaning:
  * auto-only = baseline state (would need a `LAB_LOCAL_CLK_PATH`
    directive if we wanted to retire `nv_zero_global.rbf`)
  * forced-only = activation set (the actual "switch to GCLK" cells)

Reads cached forced/auto pair RBFs from `fuzz/clk_lab_sel_probe.py` for
each --lab arg (or all 13 mined LABs by default) and prints the
N-invariant intersection per direction.
"""
from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
RBF = REPO / "results" / "rbf"
HDR = 32 + 25 * 210  # skip header band
CRC_SLOT = 208


def diff_dir(forced: bytes, auto: bytes, *, want_set_in: str) -> set:
    """Cells where bit_state matches the requested asymmetric pattern.

    want_set_in='auto'   → auto=1 forced=0 (local-clock cells)
    want_set_in='forced' → forced=1 auto=0 (GCLK-enable cells)
    """
    out = set()
    for i in range(HDR, min(len(forced), len(auto))):
        if (i - 32) % 210 >= CRC_SLOT:
            continue
        for bp in range(8):
            f = (forced[i] >> bp) & 1
            a = (auto[i] >> bp) & 1
            if want_set_in == "auto" and a == 1 and f == 0:
                out.add((i, bp))
            elif want_set_in == "forced" and f == 1 and a == 0:
                out.add((i, bp))
    return out


def decompose(x: int, y: int, src=(10, 10, 0)) -> dict:
    sx, sy, sn = src
    auto_only = []
    forced_only = []
    for n in (0, 4):
        f_path = RBF / f"fgclk_FORCE_X{sx}Y{sy}N{sn}_to_X{x}Y{y}N{n}.rbf"
        a_path = RBF / f"fgclk_AUTO_X{sx}Y{sy}N{sn}_to_X{x}Y{y}N{n}.rbf"
        if not f_path.exists() or not a_path.exists():
            return {"error": f"missing rbf for N={n}"}
        fb = f_path.read_bytes()
        ab = a_path.read_bytes()
        auto_only.append(diff_dir(fb, ab, want_set_in="auto"))
        forced_only.append(diff_dir(fb, ab, want_set_in="forced"))
    return {
        "auto_only_n_invariant":   sorted(auto_only[0] & auto_only[1]),
        "forced_only_n_invariant": sorted(forced_only[0] & forced_only[1]),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--lab", action="append", default=None,
                    help='target LAB "X,Y" (repeatable); default = all mined')
    args = ap.parse_args()

    if args.lab:
        labs = [tuple(int(v) for v in s.split(",")) for s in args.lab]
    else:
        labs = []
        for p in sorted((REPO / "results").glob("clk_lab_sel_probe_X*Y*.json")):
            m = re.match(r"clk_lab_sel_probe_X(\d+)Y(\d+)\.json", p.name)
            if m:
                labs.append((int(m.group(1)), int(m.group(2))))

    out = {}
    for x, y in labs:
        r = decompose(x, y)
        out[f"X{x}Y{y}"] = r
        if "error" in r:
            print(f"LAB({x:2d},{y:2d}): {r['error']}")
            continue
        ao = r["auto_only_n_invariant"]
        fo = r["forced_only_n_invariant"]
        print(f"LAB({x:2d},{y:2d}): auto-only={len(ao):3d}  "
              f"forced-only={len(fo):3d}  total={len(ao)+len(fo):3d}")

    # Cross-LAB occurrence histogram for each bucket
    for bucket in ("auto_only_n_invariant", "forced_only_n_invariant"):
        print(f"\n=== {bucket} cross-LAB histogram ===")
        c: Counter = Counter()
        for r in out.values():
            if "error" in r:
                continue
            for cell in r[bucket]:
                c[tuple(cell)] += 1
        h: Counter = Counter(c.values())
        for k in sorted(h):
            print(f"  cells appearing in {k:2d}/{len(out):2d} LABs: {h[k]:3d}")

    # Save
    out_path = REPO / "results" / "clk_lab_sel_decomposed.json"
    out_path.write_text(json.dumps(out, indent=2))
    print(f"\nwrote {out_path}")


if __name__ == "__main__":
    main()
