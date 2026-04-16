# SPDX-License-Identifier: GPL-3.0-or-later
"""Full-grid structural analysis of the IOB cross-axis interaction term.

Generalizes ``analyze_interaction_structure.py`` from the 10-sample
bankpair corpus to the 421-sample 2D grid under
``tmp/iob_cross_axis/iob_xy_K{K}_L{L}.rbf`` (Quartus-built, full
23 K x 22 LED matrix minus single-axis anchors and same-bank
IOPAD conflicts).

Baseline: ``results/rbf/iob_in_E15.rbf`` (K=E15, LED=G15).

Per-sample interaction term:

    I(K, L) = (pair ^ base) ^ (single_in(K) ^ base) ^ (single_out(L) ^ base)
            = pair ^ base ^ single_in(K) ^ base ^ single_out(L) ^ base
            = pair ^ single_in(K) ^ single_out(L) ^ base

Three-way decomposition we try:

    I(K, L) = per_K_core[K]  ^  per_L_core[L]  ^  joint_residue[K, L]

where per_K_core[K] = intersection over L of I(K, L), etc.  The
question the memory files want answered: with all 421 samples, does
``joint_residue`` collapse to something small (<20 cells / pair)?

Outputs:
  results/iob_cross_axis_interaction_full.json  -- verbose summary
  results/iob_cross_axis_cells.json             -- three-way tables
                                                   (only if residue is tractable)
"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent

RBF_DIR = ROOT / "results" / "rbf"
GRID_DIR = ROOT / "tmp" / "iob_cross_axis"
OUT_JSON = ROOT / "results" / "iob_cross_axis_interaction_full.json"
TABLES_JSON = ROOT / "results" / "iob_cross_axis_cells.json"

BASE_PATH = RBF_DIR / "iob_in_E15.rbf"     # K=E15, LED=G15

FNAME_RE = re.compile(r"^iob_xy_K([^_]+)_L([^.]+)\.rbf$")


def read_bytes(path: Path) -> bytes:
    return path.read_bytes()


def xor(a: bytes, b: bytes) -> bytes:
    return bytes(x ^ y for x, y in zip(a, b))


def xor_many(*chunks: bytes) -> bytes:
    it = iter(chunks)
    acc = next(it)
    for c in it:
        acc = xor(acc, c)
    return acc


def cells_of(data: bytes) -> set[tuple[int, int]]:
    s = set()
    for off, v in enumerate(data):
        if v == 0:
            continue
        for bp in range(8):
            if (v >> bp) & 1:
                s.add((off, bp))
    return s


def main() -> int:
    base = read_bytes(BASE_PATH)
    print(f"baseline: {BASE_PATH.relative_to(ROOT)} ({len(base)} B)")

    # Cache single-axis deltas (cells)
    in_delta: dict[str, set] = {}
    out_delta: dict[str, set] = {}

    for p in sorted(RBF_DIR.glob("iob_in_*.rbf")):
        pin = p.stem[len("iob_in_"):]
        in_delta[pin] = cells_of(xor(read_bytes(p), base))
    for p in sorted(RBF_DIR.glob("iob_out_*.rbf")):
        pin = p.stem[len("iob_out_"):]
        out_delta[pin] = cells_of(xor(read_bytes(p), base))

    print(f"single-axis inputs: {len(in_delta)} pins   "
          f"outputs: {len(out_delta)} pins")

    # Iterate grid
    samples = sorted(GRID_DIR.glob("iob_xy_K*.rbf"))
    print(f"grid samples: {len(samples)}")

    interactions: dict[tuple[str, str], set] = {}
    missing_axis = []
    for path in samples:
        m = FNAME_RE.match(path.name)
        if not m:
            continue
        kpin, lpin = m.group(1), m.group(2)
        if kpin not in in_delta or lpin not in out_delta:
            missing_axis.append((kpin, lpin))
            continue
        pair = read_bytes(path)
        dpair = cells_of(xor(pair, base))
        I = dpair.symmetric_difference(in_delta[kpin])
        I = I.symmetric_difference(out_delta[lpin])
        interactions[(kpin, lpin)] = I

    if missing_axis:
        print(f"  WARN: skipped {len(missing_axis)} samples with missing single-axis RBF")
        for (k, l) in missing_axis[:5]:
            print(f"    K={k} L={l}")

    N = len(interactions)
    print(f"usable interactions: {N}")

    # Size distribution
    sizes = sorted(len(v) for v in interactions.values())
    print(f"  I size min/median/max = {sizes[0]}/{sizes[N//2]}/{sizes[-1]}  "
          f"mean={sum(sizes)/N:.1f}")

    # Per-cell occurrence
    cell_count: Counter = Counter()
    for cells in interactions.values():
        for c in cells:
            cell_count[c] += 1
    union = set(cell_count.keys())
    universal = {c for c, n in cell_count.items() if n == N}
    widespread = {c for c, n in cell_count.items() if n >= (N + 1) // 2}
    unique = {c for c, n in cell_count.items() if n == 1}
    print(f"  union={len(union)}  universal={len(universal)}  "
          f"widespread(>=N/2)={len(widespread)}  unique={len(unique)}")

    # Group samples by K and by L
    by_K: dict[str, list[tuple[str, str]]] = defaultdict(list)
    by_L: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for (k, l) in interactions:
        by_K[k].append((k, l))
        by_L[l].append((k, l))

    # Per-K core: intersection over all L for that K
    per_K_core: dict[str, set] = {}
    for k, keys in by_K.items():
        sets = [interactions[kk] for kk in keys]
        per_K_core[k] = set.intersection(*sets) if sets else set()

    # Per-L core: intersection over all K for that L
    per_L_core: dict[str, set] = {}
    for l, keys in by_L.items():
        sets = [interactions[kk] for kk in keys]
        per_L_core[l] = set.intersection(*sets) if sets else set()

    pk_sizes = sorted(len(v) for v in per_K_core.values())
    pl_sizes = sorted(len(v) for v in per_L_core.values())
    print(f"  per-K core sizes: min={pk_sizes[0]} median={pk_sizes[len(pk_sizes)//2]} "
          f"max={pk_sizes[-1]} ({len(per_K_core)} K pins)")
    print(f"  per-L core sizes: min={pl_sizes[0]} median={pl_sizes[len(pl_sizes)//2]} "
          f"max={pl_sizes[-1]} ({len(per_L_core)} L pins)")

    # Cross-pin consistency of per-K/per-L cores: universal shared by
    # all per-K cores should equal universal of full grid (it does by
    # definition; sanity check)
    if per_K_core:
        pkc_common = set.intersection(*per_K_core.values())
        print(f"  per-K-core intersection (global infra estimate): {len(pkc_common)}")
    if per_L_core:
        plc_common = set.intersection(*per_L_core.values())
        print(f"  per-L-core intersection (global infra estimate): {len(plc_common)}")

    # Three-way decomposition: define
    #   per_K_only[K]  = per_K_core[K] - universal
    #   per_L_only[L]  = per_L_core[L] - universal
    #   joint[K,L]     = I(K,L) ^ universal ^ per_K_only[K] ^ per_L_only[L]
    #
    # If the interaction cleanly factors into per-axis terms, |joint|
    # will be ~0 for every (K, L).  If it's genuinely pair-specific,
    # |joint| ~ 60-70% of |I|.
    per_K_only = {k: v - universal for k, v in per_K_core.items()}
    per_L_only = {l: v - universal for l, v in per_L_core.items()}

    joint_sizes: list[int] = []
    joint_residue: dict[tuple[str, str], set] = {}
    for (k, l), cells in interactions.items():
        pk = per_K_only[k]
        pl = per_L_only[l]
        residue = cells ^ universal ^ pk ^ pl
        joint_residue[(k, l)] = residue
        joint_sizes.append(len(residue))

    joint_sizes.sort()
    print()
    print("  three-way decomposition:")
    print(f"    universal term       : {len(universal)} cells (constant)")
    print(f"    per-K-only sizes     : min={min(len(v) for v in per_K_only.values())} "
          f"median={sorted(len(v) for v in per_K_only.values())[len(per_K_only)//2]} "
          f"max={max(len(v) for v in per_K_only.values())}")
    print(f"    per-L-only sizes     : min={min(len(v) for v in per_L_only.values())} "
          f"median={sorted(len(v) for v in per_L_only.values())[len(per_L_only)//2]} "
          f"max={max(len(v) for v in per_L_only.values())}")
    print(f"    joint residue sizes  : min={joint_sizes[0]} "
          f"median={joint_sizes[N//2]} max={joint_sizes[-1]} "
          f"mean={sum(joint_sizes)/N:.1f}")

    ratio = sum(joint_sizes) / max(1, sum(sizes))
    print(f"    joint/raw ratio      : {ratio:.3f} "
          f"(sum |joint| / sum |I|)")

    # Union of joint residues: does the joint term itself have
    # amortizable structure, or is every pair unique?
    joint_cell_count: Counter = Counter()
    for cells in joint_residue.values():
        for c in cells:
            joint_cell_count[c] += 1
    joint_union = set(joint_cell_count)
    joint_unique = {c for c, n in joint_cell_count.items() if n == 1}
    print(f"    joint union cells    : {len(joint_union)}  "
          f"unique-to-one-pair={len(joint_unique)} "
          f"({100.0*len(joint_unique)/max(1,len(joint_union)):.1f}%)")

    # 2x2 separability probe on a random sample of sub-squares
    print()
    print("  separability probe (2x2 sub-squares, XOR of four I's):")
    subsquare_stats = {"tested": 0, "zero": 0, "small": 0, "large": 0,
                       "max_residue": 0, "sum_residue": 0}
    ks = list(by_K)
    ls = list(by_L)
    # Iterate a bounded number of sub-squares for speed
    import itertools
    tested = 0
    for (k1, k2) in itertools.combinations(ks, 2):
        for (l1, l2) in itertools.combinations(ls, 2):
            if all((k, l) in interactions
                   for k in (k1, k2) for l in (l1, l2)):
                I11 = interactions[(k1, l1)]
                I12 = interactions[(k1, l2)]
                I21 = interactions[(k2, l1)]
                I22 = interactions[(k2, l2)]
                xor4 = (I11 ^ I12) ^ (I21 ^ I22)
                subsquare_stats["tested"] += 1
                subsquare_stats["sum_residue"] += len(xor4)
                if len(xor4) == 0:
                    subsquare_stats["zero"] += 1
                elif len(xor4) <= 4:
                    subsquare_stats["small"] += 1
                else:
                    subsquare_stats["large"] += 1
                subsquare_stats["max_residue"] = max(
                    subsquare_stats["max_residue"], len(xor4))
                tested += 1
                if tested >= 5000:
                    break
        if tested >= 5000:
            break
    t = subsquare_stats["tested"]
    if t:
        print(f"    sub-squares tested   : {t}")
        print(f"    |XOR4| == 0          : {subsquare_stats['zero']} "
              f"({100.0*subsquare_stats['zero']/t:.1f}%)")
        print(f"    |XOR4| <= 4          : {subsquare_stats['small']}")
        print(f"    |XOR4|  > 4          : {subsquare_stats['large']}")
        print(f"    max |XOR4|           : {subsquare_stats['max_residue']}")
        print(f"    mean |XOR4|          : {subsquare_stats['sum_residue']/t:.1f}")

    # Write verbose summary
    meta = {
        "base": str(BASE_PATH.relative_to(ROOT)),
        "grid_dir": str(GRID_DIR.relative_to(ROOT)),
        "samples_total": len(samples),
        "samples_usable": N,
        "universal_cells": len(universal),
        "widespread_cells": len(widespread),
        "unique_cells": len(unique),
        "union_cells": len(union),
        "I_size_min": sizes[0],
        "I_size_median": sizes[N // 2],
        "I_size_max": sizes[-1],
        "I_size_mean": sum(sizes) / N,
        "joint_residue_min": joint_sizes[0],
        "joint_residue_median": joint_sizes[N // 2],
        "joint_residue_max": joint_sizes[-1],
        "joint_residue_mean": sum(joint_sizes) / N,
        "joint_union_cells": len(joint_union),
        "joint_unique_cells": len(joint_unique),
        "joint_over_raw_ratio": ratio,
        "subsquare_stats": subsquare_stats,
    }
    verbose = {
        "meta": meta,
        "universal": sorted(universal),
        "per_K_only_sizes": {k: len(v) for k, v in per_K_only.items()},
        "per_L_only_sizes": {l: len(v) for l, v in per_L_only.items()},
        "joint_size_hist": dict(sorted(Counter(joint_sizes).items())),
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(verbose, indent=2))
    print(f"\n  wrote {OUT_JSON.relative_to(ROOT)}")

    # Tables artefact: only write the joint residue table if the
    # decomposition is actually tractable (median residue < 20 cells).
    tractable = joint_sizes[N // 2] < 20
    tables = {
        "meta": meta,
        "tractable": tractable,
        "universal": sorted(universal),
        "per_K_only": {k: sorted(v) for k, v in per_K_only.items()},
        "per_L_only": {l: sorted(v) for l, v in per_L_only.items()},
    }
    if tractable:
        tables["joint_residue"] = {
            f"{k}|{l}": sorted(v) for (k, l), v in joint_residue.items() if v
        }
        print(f"  decomposition tractable (median residue {joint_sizes[N//2]}) — "
              f"writing full tables")
    else:
        print(f"  decomposition NOT tractable (median residue {joint_sizes[N//2]}) — "
              f"tables artefact omits per-pair joints")
    TABLES_JSON.write_text(json.dumps(tables, indent=2))
    print(f"  wrote {TABLES_JSON.relative_to(ROOT)}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
