#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Extended sweep: widths 9-15 (cross half-LAB boundary) in single LAB."""
import sys
sys.path.insert(0, "/tmp/arith_sweep")
from gen_designs import gen_pair

# Widths 9..15 at LAB(4,18) starting N=1 (forces cross-half)
CONFIGS = []
for w in range(9, 16):
    CONFIGS.append((f"c{w}_xh", "counter", 4, 18, 1, w))
    CONFIGS.append((f"i{w}_xh", "identity", 4, 18, 1, w))

for tag, kind, lx, ly, nst, w in CONFIGS:
    gen_pair("/tmp/arith_sweep", tag, lx, ly, nst, w, identity=(kind == "identity"))
print(f"generated {len(CONFIGS)} extended design dirs")
