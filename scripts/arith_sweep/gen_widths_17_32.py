#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Widths 17..32 arith sweep generator — multi-LAB carry chains.

A single Cyclone IV LAB holds 16 LEs (N = 0, 2, ..., 30), so the carry
chain saturates at 16 bits per LAB.  For widths 17..32 we spill the
upper bits into the adjacent LAB (4, 17) along the chain's N30 -> N0
Y-decreasing link.

Canonical placement (mirrors ``gen_designs.py``'s ``_lo`` convention):

    bits 0 .. 15         -> LAB(4, 18) FF slots N=1,3,...,31
    bits 16 .. (w-1)     -> LAB(4, 17) FF slots N=1,3,...,2*(w-16)-1

Tag scheme: ``c{w}_ml`` / ``i{w}_ml`` ("ml" = multi_lab).  Widths 17..32
are always cross-LAB; no single-LAB variant exists at those widths.

Invoke from the repo root: ``python3 scripts/arith_sweep/gen_widths_17_32.py``.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from gen_designs import gen_pair, QSF_HEADER, TEMPLATE_V_COUNTER, TEMPLATE_V_IDENTITY

BASE = "tmp/arith_sweep"  # repo-root-relative (gitignored)
LX = 4
LY_HI = 18  # primary LAB (bits 0..15)
LY_LO = 17  # secondary LAB (bits 16..)


def gen_multilab_pair(base_dir, name, w, *, identity=False):
    """Emit a w-bit counter or identity spanning LAB(LX,LY_HI) -> LAB(LX,LY_LO).

    bits [0, 16)   pinned to LAB(LX, LY_HI) FF slots N=1,3,...,31
    bits [16, w)   pinned to LAB(LX, LY_LO) FF slots N=1,3,...,2*(w-16)-1
    """
    assert 17 <= w <= 32, f"width {w} out of range for multi-LAB gen"
    d = os.path.join(base_dir, name)
    os.makedirs(d, exist_ok=True)

    # Slot lists for the two LABs
    slots_hi = list(range(1, 32, 2))           # N = 1,3,...,31 (16 slots)
    slots_lo = list(range(1, 2 * (w - 16), 2)) # N = 1,3,...,2*(w-16)-1
    all_slots = [(LY_HI, n) for n in slots_hi] + [(LY_LO, n) for n in slots_lo]
    assert len(all_slots) == w

    n_list_str = ",".join(f"Y{ly}N{n}" for (ly, n) in all_slots)
    ctx = dict(name=name, w=w, w_1=w - 1, lx=LX, ly=LY_HI, n_list=n_list_str)
    vtxt = (TEMPLATE_V_IDENTITY if identity else TEMPLATE_V_COUNTER).format(**ctx)
    with open(os.path.join(d, "top.v"), "w") as f:
        f.write(vtxt)

    qsf = QSF_HEADER
    for i, (ly, n) in enumerate(all_slots):
        qsf += f'set_location_assignment FF_X{LX}_Y{ly}_N{n}  -to "Q[{i}]"\n'
    with open(os.path.join(d, "top.qsf"), "w") as f:
        f.write(qsf)
    with open(os.path.join(d, "top.qpf"), "w") as f:
        f.write('PROJECT_REVISION = "top"\n')
    return d


CONFIGS = []  # list of (tag, kind, w)
for w in range(17, 33):
    CONFIGS.append((f"c{w}_ml", "counter", w))
    CONFIGS.append((f"i{w}_ml", "identity", w))


def main():
    os.makedirs(BASE, exist_ok=True)
    for tag, kind, w in CONFIGS:
        gen_multilab_pair(BASE, tag, w, identity=(kind == "identity"))
    print(f"generated {len(CONFIGS)} multi-LAB design dirs under {BASE}")
    for tag, kind, w in CONFIGS:
        extra_lo = w - 16
        print(
            f"  {tag}: {kind} w={w} "
            f"LAB({LX},{LY_HI}) N=[1..31] + LAB({LX},{LY_LO}) N=[1..{2*extra_lo - 1}]"
        )


if __name__ == "__main__":
    main()
