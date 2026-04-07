# SPDX-License-Identifier: GPL-3.0-or-later
"""T9 part 2: tiny in-house decision tree (no sklearn).

Greedy depth-N tree on the li_mode_dataset.json features. Target: derive a
pickable rule for paired vs alternating.
"""
import json
from collections import Counter
from pathlib import Path

ROWS = json.loads(Path("/home/test/EP4CE6/results/li_mode_dataset.json").read_text())
NON_LAB_X = {5, 9, 14, 15, 20, 27, 30}

# Restrict to mappable
ROWS = [r for r in ROWS if r["mode"] in ("paired", "alternating", "edge_even_b0")]

FEATURES = ["sx", "sy", "dx", "dy", "dxs", "dys", "adx", "ady", "manhattan",
            "dst_dist_nonlab"]
BOOL_FEATURES = ["row_only", "col_only", "diag", "dst_near_nonlab",
                 "dst_y_edge", "src_y_edge"]


def majority(rows):
    if not rows:
        return None, 0, 0
    c = Counter(r["mode"] for r in rows)
    label, n = c.most_common(1)[0]
    return label, n, len(rows)


def gini(rows):
    if not rows:
        return 0
    c = Counter(r["mode"] for r in rows)
    n = len(rows)
    return 1 - sum((v / n) ** 2 for v in c.values())


def best_split(rows, depth=0):
    if not rows:
        return None
    base = gini(rows) * len(rows)
    best = None
    for feat in FEATURES:
        vals = sorted(set(r[feat] for r in rows))
        for i in range(len(vals) - 1):
            thr = (vals[i] + vals[i + 1]) / 2
            L = [r for r in rows if r[feat] <= thr]
            R = [r for r in rows if r[feat] > thr]
            score = gini(L) * len(L) + gini(R) * len(R)
            if score < base - 1e-9:
                gain = base - score
                if best is None or gain > best[0]:
                    best = (gain, feat, thr, "num", L, R)
    for feat in BOOL_FEATURES:
        L = [r for r in rows if not r[feat]]
        R = [r for r in rows if r[feat]]
        if not L or not R:
            continue
        score = gini(L) * len(L) + gini(R) * len(R)
        if score < base - 1e-9:
            gain = base - score
            if best is None or gain > best[0]:
                best = (gain, feat, None, "bool", L, R)
    return best


def grow(rows, depth=0, max_depth=4, min_leaf=5, prefix=""):
    label, nlab, ntot = majority(rows)
    purity = nlab / ntot if ntot else 0
    if depth >= max_depth or ntot < 2 * min_leaf or purity >= 0.95:
        c = Counter(r["mode"] for r in rows)
        print(f"{prefix}└─ leaf  n={ntot}  → {label} ({nlab}/{ntot}, {100*purity:.0f}%)  {dict(c)}")
        return
    sp = best_split(rows)
    if sp is None:
        c = Counter(r["mode"] for r in rows)
        print(f"{prefix}└─ leaf  n={ntot}  → {label}  {dict(c)}")
        return
    gain, feat, thr, kind, L, R = sp
    if kind == "num":
        cond_L = f"{feat} <= {thr:g}"
        cond_R = f"{feat} >  {thr:g}"
    else:
        cond_L = f"NOT {feat}"
        cond_R = f"{feat}"
    print(f"{prefix}├─ split [{cond_L}]  n={len(L)}  gain={gain:.3f}")
    grow(L, depth + 1, max_depth, min_leaf, prefix + "│  ")
    print(f"{prefix}├─ split [{cond_R}]  n={len(R)}")
    grow(R, depth + 1, max_depth, min_leaf, prefix + "│  ")


def main():
    print(f"=== T9 decision tree on {len(ROWS)} mappable rows ===")
    print(f"  modes: {Counter(r['mode'] for r in ROWS)}")
    print()
    grow(ROWS, max_depth=4, min_leaf=5)

    # Per-(sx,sy) breakdown
    print("\n=== Per-source mode bias ===")
    by_src = {}
    for r in ROWS:
        by_src.setdefault((r["sx"], r["sy"]), []).append(r)
    for src in sorted(by_src):
        c = Counter(r["mode"] for r in by_src[src])
        n = len(by_src[src])
        print(f"  src={src}  n={n:3d}  paired={c['paired']:3d}  alt={c['alternating']:3d}  edge={c['edge_even_b0']:3d}")


if __name__ == "__main__":
    main()
