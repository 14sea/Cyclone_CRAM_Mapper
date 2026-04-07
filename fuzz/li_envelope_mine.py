# SPDX-License-Identifier: GPL-3.0-or-later
"""Mine source AND destination LI envelopes from lits_pair_* corpus.

For each lits_pair_X{sx}Y{sy}_to_X{dx}Y{dy}N{dn}_{port}.rbf, read its LI
cells against the matching zero baseline, then group cells by (lab_x, lab_y).
Classify each LAB as src / dst / transit and dump the (pair, base_idx)
shapes per role.

Goal: discover the canonical source LI shape (currently we wrongly emit
{P8B0, P8B1}) and validate the dst shape against the typical envelope.
"""
import sys, os, re
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from collections import Counter, defaultdict
from pathlib import Path

from bitstream import RouteCodec

ROOT = Path(__file__).resolve().parent.parent
RBF = ROOT / "results" / "rbf"
ZERO = RBF / "lits_zero_10_10.rbf"

NAME = re.compile(r"lits_pair_X(\d+)Y(\d+)_to_X(\d+)Y(\d+)N(\d+)_(\w+)\.rbf")


def main():
    codec = RouteCodec()
    zero = ZERO.read_bytes()

    src_shapes = Counter()  # frozenset((p,b),...)
    dst_shapes = Counter()
    src_with_meta = []
    dst_with_meta = []

    for path in sorted(RBF.glob("lits_pair_*.rbf")):
        m = NAME.match(path.name)
        if not m:
            continue
        sx, sy = int(m.group(1)), int(m.group(2))
        dx, dy = int(m.group(3)), int(m.group(4))
        dn = int(m.group(5))
        port = m.group(6)

        try:
            data = path.read_bytes()
            li = codec.read_local_interconnect(data, zero)
        except Exception:
            continue

        # group by (lx, ly)
        by_lab = defaultdict(set)
        for entry in li:
            name, off, bp = entry[0], entry[1], entry[2]
            lx, ly, p, b = codec._parse_li_name(name)
            by_lab[(lx, ly)].add((p, b))

        src_cells = frozenset(by_lab.get((sx, sy), set()))
        dst_cells = frozenset(by_lab.get((dx, dy), set()))

        if src_cells:
            src_shapes[src_cells] += 1
            src_with_meta.append((src_cells, sx, sy, dx, dy, port))
        if dst_cells:
            dst_shapes[dst_cells] += 1
            dst_with_meta.append((dst_cells, sx, sy, dx, dy, port))

    print(f"=== source-side LI shapes ({sum(src_shapes.values())} samples) ===")
    for shape, n in src_shapes.most_common(10):
        cells = " ".join(f"P{p}B{b}" for p, b in sorted(shape))
        print(f"  {n:3d}×  ({len(shape)} cells)  {cells}")

    print(f"\n=== destination-side LI shapes ({sum(dst_shapes.values())} samples) ===")
    for shape, n in dst_shapes.most_common(10):
        cells = " ".join(f"P{p}B{b}" for p, b in sorted(shape))
        print(f"  {n:3d}×  ({len(shape)} cells)  {cells}")

    # Look at a few samples with (src,dst) labels
    print(f"\n=== first 8 src samples (with route info) ===")
    for shape, sx, sy, dx, dy, port in src_with_meta[:8]:
        cells = " ".join(f"P{p}B{b}" for p, b in sorted(shape))
        print(f"  ({sx},{sy})→({dx},{dy}) {port}: {cells}")

    print(f"\n=== first 8 dst samples ===")
    for shape, sx, sy, dx, dy, port in dst_with_meta[:8]:
        cells = " ".join(f"P{p}B{b}" for p, b in sorted(shape))
        print(f"  ({sx},{sy})→({dx},{dy}) {port}: {cells}")


if __name__ == "__main__":
    main()
