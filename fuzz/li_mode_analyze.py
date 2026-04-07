# SPDX-License-Identifier: GPL-3.0-or-later
"""T9: LI mode-selection analysis.

For every lits_pair_X{sx}Y{sy}_to_X{dx}Y{dy}N0_datab.rbf, read LI cells at the
destination LAB, classify the mode, and look for a decision rule that maps
(src, dst) features → mode.

Output: a feature table + decision tree.
"""
import os, sys, re, json
from pathlib import Path
from collections import Counter, defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bitstream import RouteCodec

ROOT = Path('/home/test/EP4CE6')
RBF_DIR = ROOT / 'results' / 'rbf'
NON_LAB_X = {5, 9, 14, 15, 20, 27, 30}
LAB_X = [3, 4, 6, 7, 8, 10, 11, 12, 13, 16, 17, 18, 19, 21, 22, 23, 24, 25, 26, 28, 29, 31]
LAB_Y = [2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 16, 17, 18, 19, 21]

PAIR_RE = re.compile(r'lits_pair_X(\d+)Y(\d+)_to_X(\d+)Y(\d+)N0_datab\.rbf$')


def read_dst_mode(codec, rbf, zero, dx, dy):
    li = codec.read_local_interconnect(rbf, zero)
    pair_map = {}
    for e in li:
        lx, ly, p, b = codec._parse_li_name(e[0])
        if (lx, ly) == (dx, dy):
            pair_map.setdefault(p, set()).add(b)
    if not pair_map:
        return "empty", 0, pair_map
    mode, _ = RouteCodec._classify_li_lab(pair_map)
    n_cells = sum(len(v) for v in pair_map.values())
    return mode, n_cells, pair_map


def features(sx, sy, dx, dy):
    dxs, dys = dx - sx, dy - sy
    return {
        "sx": sx, "sy": sy, "dx": dx, "dy": dy,
        "dxs": dxs, "dys": dys,
        "adx": abs(dxs), "ady": abs(dys),
        "manhattan": abs(dxs) + abs(dys),
        "row_only": dys == 0,
        "col_only": dxs == 0,
        "diag": dxs != 0 and dys != 0,
        "dst_x_in_lab": dx in LAB_X,
        "dst_near_nonlab": min((abs(dx - n) for n in NON_LAB_X), default=99) <= 1,
        "dst_dist_nonlab": min((abs(dx - n) for n in NON_LAB_X), default=99),
        "dst_y_edge": dy in (2, 21),
        "src_y_edge": sy in (2, 21),
    }


def main():
    codec = RouteCodec()
    by_src_zero = {}
    rows = []
    skipped = 0
    for f in RBF_DIR.glob('lits_pair_X*_to_X*_datab.rbf'):
        m = PAIR_RE.search(f.name)
        if not m:
            continue
        sx, sy, dx, dy = map(int, m.groups())
        zpath = RBF_DIR / f"lits_zero_{sx}_{sy}.rbf"
        if not zpath.exists():
            skipped += 1
            continue
        if (sx, sy) not in by_src_zero:
            by_src_zero[(sx, sy)] = zpath.read_bytes()
        zero = by_src_zero[(sx, sy)]
        try:
            rbf = f.read_bytes()
            mode, n_cells, pm = read_dst_mode(codec, rbf, zero, dx, dy)
        except Exception as e:
            skipped += 1
            continue
        feat = features(sx, sy, dx, dy)
        feat["mode"] = mode
        feat["n_cells"] = n_cells
        feat["pairs"] = sorted(pm.keys())
        rows.append(feat)

    print(f"=== T9 LI mode-selection analysis ===")
    print(f"  total samples: {len(rows)}  (skipped {skipped})")
    print()

    # Mode distribution
    mode_count = Counter(r["mode"] for r in rows)
    print(f"  mode distribution:")
    for m, c in mode_count.most_common():
        print(f"    {m:14s} {c:4d}  ({100*c/len(rows):4.1f}%)")
    print()

    # Filter to mappable modes
    mappable = [r for r in rows if r["mode"] in ("paired", "alternating", "edge_even_b0")]
    print(f"  mappable rows (paired/alt/edge): {len(mappable)}")
    print()

    # Univariate splits — for each feature, mode distribution
    print(f"  === Univariate feature → mode tendencies ===")
    interesting = ["row_only", "col_only", "diag", "dst_x_in_lab",
                   "dst_near_nonlab", "dst_y_edge", "src_y_edge"]
    for feat in interesting:
        groups = defaultdict(Counter)
        for r in mappable:
            groups[r[feat]][r["mode"]] += 1
        print(f"  {feat}:")
        for v, ctr in sorted(groups.items()):
            total = sum(ctr.values())
            parts = ", ".join(f"{m}={c}({100*c/total:.0f}%)" for m, c in ctr.most_common())
            print(f"    {feat}={str(v):5s} n={total:3d}  {parts}")
        print()

    # dst_x → mode (per-column tendency)
    print(f"  === dst_x → mode (per-column) ===")
    by_dx = defaultdict(Counter)
    for r in mappable:
        by_dx[r["dx"]][r["mode"]] += 1
    print(f"  {'dx':>3}  {'n':>4}  paired  alt    edge")
    for dx in sorted(by_dx):
        c = by_dx[dx]
        n = sum(c.values())
        print(f"  {dx:3d}  {n:4d}  {c['paired']:3d}    {c['alternating']:3d}    {c['edge_even_b0']:3d}    "
              f"({'in_lab' if dx in LAB_X else 'NON_LAB'}, dist_nonLAB={min(abs(dx-n) for n in NON_LAB_X)})")
    print()

    # dst_y → mode
    print(f"  === dst_y → mode ===")
    by_dy = defaultdict(Counter)
    for r in mappable:
        by_dy[r["dy"]][r["mode"]] += 1
    for dy in sorted(by_dy):
        c = by_dy[dy]
        n = sum(c.values())
        print(f"    dy={dy:2d}  n={n:3d}  paired={c['paired']:3d}  alt={c['alternating']:3d}  edge={c['edge_even_b0']:3d}")
    print()

    # Try a small decision tree
    try:
        from sklearn.tree import DecisionTreeClassifier, export_text
        feat_names = ["dxs", "dys", "adx", "ady", "manhattan",
                      "dst_x_in_lab", "dst_near_nonlab", "dst_dist_nonlab",
                      "dst_y_edge", "src_y_edge"]
        X = [[int(r[f]) if isinstance(r[f], bool) else r[f] for f in feat_names] for r in mappable]
        y = [r["mode"] for r in mappable]
        clf = DecisionTreeClassifier(max_depth=4, min_samples_leaf=5)
        clf.fit(X, y)
        acc = clf.score(X, y)
        print(f"  === Decision tree (depth=4, min_leaf=5), train acc = {acc:.3f} ===")
        print(export_text(clf, feature_names=feat_names))
    except ImportError:
        print("  (sklearn not installed — skipping decision tree)")

    # Save raw rows
    out_path = ROOT / "results" / "li_mode_dataset.json"
    out_path.write_text(json.dumps([{k: (list(v) if isinstance(v, list) else v)
                                      for k, v in r.items()} for r in rows], indent=1))
    print(f"\n  raw dataset → {out_path}")


if __name__ == "__main__":
    main()
