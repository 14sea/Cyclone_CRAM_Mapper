# SPDX-License-Identifier: GPL-3.0-or-later
"""IOB_PIN_BANK_INFRA bucket miner.

Mines per-site cells in the two pinout-driven CRAM regions:
  * HEADER          (frames 0..24)
  * BLOCK_BAND_POST (frames 1739..1751)

Both regions encode IO-bank / pin-state side effects, NOT M9K activation.
Generalization v2 (`m9k_directives_design_dependent_2026_04_26.md`)
showed that BLOCK_BAND_POST cells track pin count, not M9K presence:
both AX301-pinout SDP fixtures yield 0 cells there, and only the
45-pin PIN_POOL fixture lights up ~25 cells per site.  The historical
`M9K_BLOCK_TAIL` directive captured exactly those cells and is folded
in here as the BLOCK_BAND_POST half of one unified pinout bucket.

Output: results/iob_pin_bank_infra.json
  per_site:
    "<X>_<Y>_<N>": [[off, bp], ...]   # union of header + block_band_post
  per_site_header:
    "<X>_<Y>_<N>": [...]              # header-only slice
  per_site_block_band_post:
    "<X>_<Y>_<N>": [...]              # block_band_post-only slice
  shared_core:        cells in EVERY site (union region)
  shared_core_count:  len(shared_core)
  pinout:             "CLK=E1, KEY2=E16, KEY3=M16, KEY4=M15, LED0=G15
                       (AX301 + 45-pin PIN_POOL — see fixture builder)"
"""
from __future__ import annotations
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PRE, FRAME, DPF = 32, 210, 208
HEADER = (0, 24)
BLOCK_BAND_POST = (1739, 1751)


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


def filter_region(diff, region):
    lo, hi = region
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

    per_hdr: dict[str, set[tuple[int, int]]] = {}
    per_bbp: dict[str, set[tuple[int, int]]] = {}
    per_union: dict[str, set[tuple[int, int]]] = {}
    for site in sites:
        v0 = (base / site / "m9k_mode_gold_4x2048_sdp_v0.rbf").read_bytes()
        diff = diff_cells(v0, nv)
        hdr = filter_region(diff, HEADER)
        bbp = filter_region(diff, BLOCK_BAND_POST)
        per_hdr[site] = hdr
        per_bbp[site] = bbp
        per_union[site] = hdr | bbp
        print(f"  {site:14}  hdr={len(hdr):4}  bb_post={len(bbp):3}  "
              f"total={len(per_union[site]):4}")

    # Site-invariance check (union region)
    intersection = set.intersection(*per_union.values())
    union_all = set.union(*per_union.values())
    print(f"\nUnion-region intersection: {len(intersection)}")
    print(f"Union-region union:        {len(union_all)}")
    deltas = [len(per_union[s] - intersection) for s in sites]
    print(f"Per-site delta vs intersection: "
          f"min={min(deltas)} max={max(deltas)} "
          f"mean={sum(deltas)/len(deltas):.1f}")

    if len(union_all) == len(intersection):
        print("\n✓ All sites have IDENTICAL bucket — shared.")
    else:
        print(f"\n✗ Sites disagree by up to {max(deltas)} cells — per-site.")

    out = {
        "per_site": {s: sorted(per_union[s]) for s in sites},
        "per_site_header": {s: sorted(per_hdr[s]) for s in sites},
        "per_site_block_band_post": {s: sorted(per_bbp[s]) for s in sites},
        "shared_core": sorted(intersection),
        "shared_core_count": len(intersection),
        "pinout": "CLK=E1, KEY2=E16, KEY3=M16, KEY4=M15, LED0=G15 "
                  "(AX301) + 45-pin PIN_POOL (M9K mining corpus)",
    }
    out_path = ROOT / "results/iob_pin_bank_infra.json"
    out_path.write_text(json.dumps(out, indent=2))
    print(f"\nWrote {out_path}")
    return 0


if __name__ == "__main__":
    main()
