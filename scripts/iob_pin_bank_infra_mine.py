# SPDX-License-Identifier: GPL-3.0-or-later
"""IOB_PIN_BANK_INFRA bucket miner.

Hypothesis: every M9K v0 fixture uses the same Quartus pinout
(CLK=E1, KEY2=E16, KEY3=M16, KEY4=M15, LED0=G15 — AX301), so the
header cells in `(v0 ⊕ nv_zero_global) ∩ header` should be identical
across all 26 sites.  If verified, a single shared bucket suffices.

If sites disagree, the bucket is per-site (or per-pinout-combination)
and we need fixture diversity.

Output: results/iob_pin_bank_infra.json with the shared bucket (if
identical) or per-site buckets (if not).
"""
from __future__ import annotations
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PRE, FRAME, DPF = 32, 210, 208
HEADER = (0, 24)


def diff_cells(a: bytes, b: bytes) -> set[tuple[int, int]]:
    cells = set()
    for off in range(PRE, len(a)):
        if (off - PRE) % FRAME >= DPF:
            continue
        x = a[off] ^ b[off]
        if not x:
            continue
        for bp in range(8):
            if x & (1 << bp):
                cells.add((off, bp))
    return cells


def header_cells(diff: set[tuple[int, int]]) -> set[tuple[int, int]]:
    lo, hi = HEADER
    return {(off, bp) for off, bp in diff
            if lo <= (off - PRE) // FRAME <= hi}


def parse_site(name: str) -> tuple[int, int, int]:
    p = name.split("_")
    return int(p[0][1:]), int(p[1][1:]), int(p[2][1:])


def main() -> int:
    base = ROOT / "tmp/m9k_mode_quartus_gold/4x2048/sdp"
    nv = (ROOT / "results/rbf/nv_zero_global.rbf").read_bytes()
    sites = sorted(p.name for p in base.iterdir()
                   if p.is_dir() and p.name.startswith("X")
                   and "_Y" in p.name and "_N" in p.name)

    per_site: dict[str, set[tuple[int, int]]] = {}
    for site in sites:
        v0 = (base / site / "m9k_mode_gold_4x2048_sdp_v0.rbf").read_bytes()
        per_site[site] = header_cells(diff_cells(v0, nv))
        print(f"  {site:14}  header={len(per_site[site]):4}")

    # Site-invariance check
    intersection = set.intersection(*per_site.values())
    union = set.union(*per_site.values())
    print(f"\nIntersection: {len(intersection)}")
    print(f"Union:        {len(union)}")
    print(f"Per-site delta vs intersection (should be ~0 if invariant):")
    deltas = []
    for site in sites:
        delta = len(per_site[site] - intersection)
        deltas.append(delta)
    print(f"  min={min(deltas)} max={max(deltas)} mean={sum(deltas)/len(deltas):.1f}")

    if len(union) == len(intersection):
        print("\n✓ All sites have IDENTICAL header bucket — shared bucket sufficient.")
        out = {"shared": sorted(intersection),
               "shared_count": len(intersection),
               "pinout": "CLK=E1, KEY2=E16, KEY3=M16, KEY4=M15, LED0=G15 (AX301)"}
    else:
        print(f"\n✗ Sites disagree by up to {max(deltas)} cells — per-site bucket.")
        out = {"per_site": {s: sorted(per_site[s]) for s in sites},
               "shared_core": sorted(intersection),
               "shared_core_count": len(intersection)}

    out_path = ROOT / "results/iob_pin_bank_infra.json"
    out_path.write_text(json.dumps(out, indent=2))
    print(f"\nWrote {out_path}")
    return 0


if __name__ == "__main__":
    main()
