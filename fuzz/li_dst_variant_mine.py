# SPDX-License-Identifier: GPL-3.0-or-later
"""Mine per-(src_dx, dst_x, dst_y) dst LI envelope variants.

The 'typical' envelope ({P0,P2,P4,P6}+P8B0) is the most common variant
globally but not for every dst LAB. This script aggregates each dst LAB's
exact envelope keyed by routing direction so the planner can pick the
right variant per case.

Reads from lits_pair_* AND litcol_* corpora.
"""
import sys, os, re
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from collections import Counter, defaultdict
from pathlib import Path

from bitstream import RouteCodec

ROOT = Path(__file__).resolve().parent.parent
RBF = ROOT / "results" / "rbf"

PATTERNS = [
    (re.compile(r"lits_pair_X(\d+)Y(\d+)_to_X(\d+)Y(\d+)N(\d+)_(\w+)\.rbf"),
     "lits_zero_10_10.rbf"),
    (re.compile(r"litcol_(\d+)_(\d+)_to_X(\d+)Y(\d+)\.rbf"),
     None),  # uses litdec_zero_{sx}_{sy}.rbf
]


def main():
    codec = RouteCodec()
    zeros = {}

    # (dst_x, dst_y) → Counter[envelope]
    by_dst = defaultdict(Counter)
    # (dst_x, dx_sign) → Counter — keyed by route direction
    by_dst_dir = defaultdict(Counter)

    for path in sorted(RBF.glob("lits_pair_*.rbf")):
        m = PATTERNS[0][0].match(path.name)
        if not m:
            continue
        sx, sy, dx, dy, dn = (int(m.group(i)) for i in range(1, 6))
        zname = "lits_zero_10_10.rbf"
        if zname not in zeros:
            zeros[zname] = (RBF / zname).read_bytes()
        try:
            data = path.read_bytes()
            li = codec.read_local_interconnect(data, zeros[zname])
        except Exception:
            continue
        by_lab = defaultdict(set)
        for e in li:
            lx, ly, p, b = codec._parse_li_name(e[0])
            by_lab[(lx, ly)].add((p, b))
        cells = frozenset(by_lab.get((dx, dy), set()))
        if not cells:
            continue
        by_dst[(dx, dy)][cells] += 1
        # Direction key
        if dx == sx:
            direction = "vertical"
        elif dy == sy:
            direction = "horizontal"
        else:
            direction = "diagonal"
        by_dst_dir[(dx, dy, direction)][cells] += 1

    # Per-LAB analysis
    print("=== per-LAB dst envelope (lits_pair corpus) ===")
    print(f"{'dst':>10} {'n_var':>6} {'top%':>6}  top envelope")
    for (dx, dy) in sorted(by_dst):
        ctr = by_dst[(dx, dy)]
        tot = sum(ctr.values())
        top, n = ctr.most_common(1)[0]
        cells = " ".join(f"P{p}B{b}" for p, b in sorted(top))
        print(f"  ({dx:>2},{dy:>2}) {len(ctr):>6} {n*100/tot:>5.0f}%  {cells}")

    # Direction-keyed: does the variant depend on src→dst direction?
    print(f"\n=== direction-keyed per-LAB ===")
    by_lab = defaultdict(dict)
    for (dx, dy, dr), ctr in by_dst_dir.items():
        top = ctr.most_common(1)[0][0]
        by_lab[(dx, dy)][dr] = top
    for (dx, dy), drmap in sorted(by_lab.items()):
        if len(drmap) > 1:
            print(f"  ({dx},{dy}) — multi-direction:")
            for dr, top in drmap.items():
                cells = " ".join(f"P{p}B{b}" for p, b in sorted(top))
                print(f"     {dr:10s}: {cells}")

    # Identify which paired sub-variant each LAB uses
    print(f"\n=== paired-mode middle-pair signature per LAB ===")
    KNOWN = {
        frozenset({2, 4, 6}): "P246",
        frozenset({1, 4, 5}): "P145",
        frozenset({1, 2, 3}): "P123",
        frozenset({1, 2, 4, 5}): "P1245",
    }
    sig_per_lab = {}
    for (dx, dy), ctr in by_dst.items():
        top = ctr.most_common(1)[0][0]
        # Find paired pairs (both B0 and B1)
        by_pair = defaultdict(set)
        for p, b in top:
            by_pair[p].add(b)
        paired = frozenset(p for p, bs in by_pair.items() if bs == {0, 1} and p != 0)
        # P0 is universal, exclude from middle signature
        sig_per_lab[(dx, dy)] = paired
    sig_count = Counter(sig_per_lab.values())
    for sig, n in sig_count.most_common():
        labs = [k for k, v in sig_per_lab.items() if v == sig]
        sig_str = "{" + ",".join(str(p) for p in sorted(sig)) + "}"
        print(f"  {sig_str:>14}  {n:>3} LABs: {sorted(labs)[:6]}{'...' if len(labs) > 6 else ''}")


def dump_lookup_table():
    """Build a (src_x, src_y, dst_x, dst_y) → envelope JSON for the synthesizer."""
    import json
    codec = RouteCodec()
    zero = (RBF / "lits_zero_10_10.rbf").read_bytes()
    pat = re.compile(r"lits_pair_X(\d+)Y(\d+)_to_X(\d+)Y(\d+)N(\d+)_(\w+)\.rbf")
    table = {}
    for path in sorted(RBF.glob("lits_pair_*.rbf")):
        m = pat.match(path.name)
        if not m:
            continue
        sx, sy, dx, dy, dn = (int(m.group(i)) for i in range(1, 6))
        port = m.group(6)
        try:
            data = path.read_bytes()
            li = codec.read_local_interconnect(data, zero)
        except Exception:
            continue
        by_lab = defaultdict(set)
        for e in li:
            lx, ly, p, b = codec._parse_li_name(e[0])
            by_lab[(lx, ly)].add((p, b))
        cells = sorted(by_lab.get((dx, dy), set()))
        if not cells:
            continue
        key = f"{sx},{sy},{dx},{dy},{port}"
        table[key] = [list(c) for c in cells]
    out = ROOT / "results" / "li_dst_variant_table.json"
    out.write_text(__import__("json").dumps(table, indent=2))
    print(f"\nwrote {out}  ({len(table)} entries)")


if __name__ == "__main__":
    main()
    dump_lookup_table()
