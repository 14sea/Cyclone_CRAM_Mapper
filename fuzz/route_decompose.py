# SPDX-License-Identifier: GPL-3.0-or-later
"""Decompose a CRAM cell set into a union of known single-route signatures.

Set-cover is NP-hard in general, but our universe (~1050 routes) is tiny
and the cell sets are highly structured, so a greedy pass with a strict
containment constraint (a route's cells must all lie inside the target
set — we can never flip a cell outside the target) converges quickly.

Inputs:
    cells: iterable of (off, bp)
    cells_table: {route_key: [(off, bp), ...]}   from route_signatures

Returns:
    (routes, residue)
      routes  — list of route_key strings, order chosen, each guaranteed
                to be a subset of the input cell set.
      residue — frozenset of (off, bp) not covered by any route — should
                be empty for pure multi-route RBFs; any leftover goes out
                as BIT directives in the FASM dump.
"""
import os
import sys
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import route_signatures


def decompose(cells, cells_table, overhead_table=None):
    """Greedy set-cover over route chunks + optional source-overhead chunks.

    Routes are tagged `route:<rk>` in the returned list; source overheads
    are tagged `src:<sx>,<sy>`. Callers peel the prefix to decide which
    FASM directive to emit.
    """
    target = frozenset((o, b) for o, b in cells)
    candidates = []
    for rk, rcells in cells_table.items():
        rset = frozenset((o, b) for o, b in rcells)
        if rset and rset <= target:
            candidates.append((f"route:{rk}", rset))
    if overhead_table is not None:
        for sk, ocells in overhead_table.items():
            oset = frozenset((o, b) for o, b in ocells)
            if oset and oset <= target:
                candidates.append((f"src:{sk}", oset))

    remaining = set(target)
    picked = []
    covered = set()
    while remaining and candidates:
        best_tag = None
        best_gain = 0
        best_set = None
        for tag, cset in candidates:
            gain = len(cset & remaining)
            if gain > best_gain:
                best_gain = gain
                best_tag = tag
                best_set = cset
        if best_gain == 0:
            break
        picked.append(best_tag)
        covered |= best_set
        remaining -= best_set
    residue = target - covered
    return picked, residue


def rk_to_fasm(rk):
    """route_key 'sx,sy->dx,dy,dn,port' → FASM ROUTE line."""
    lhs, rhs = rk.split("->")
    sx, sy = lhs.split(",")
    dx, dy, dn, port = rhs.split(",")
    return f"ROUTE X{sx}Y{sy} -> X{dx}Y{dy}N{dn}.{port}"
