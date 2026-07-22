# SPDX-License-Identifier: GPL-3.0-or-later
"""Dense-fill route-forcing payload: saturate one LAB column with a snake chain.

The two-LUT pair (plan_d_prime_factory.compile_edge) forces ONE wire per
Quartus compile → only ~3-5 new bits, because a single wire's cells are mostly
shared infra already explained. This module instead packs a whole LAB column
with a chain of pinned LUT cells, each fed by the previous one, so a SINGLE
compile forces dozens-to-hundreds of distinct wires — every cell's inbound
LOCAL_INTERCONNECT mux + the routing feeding it lands in the target column,
exactly where the hard-to-reach "dark" routing bits live.

Why a chain (not independent pairs): each cell drives the next (real fanout)
and the last drives a registered output, so `dont_touch` can't fold anything
away and we need only ONE input pin + one clock for the whole column. Snake
ordering (row by row, N alternating direction) keeps consecutive cells
physically adjacent so the forced hops are short, well-defined C4/LOCAL routes.

Cells cycle through all four input ports so different LI-mux inputs get
exercised across the column in one shot.
"""
from __future__ import annotations

from config import LAB_Y

PORTS = ("dataa", "datab", "datac", "datad")


def snake_placements(x: int, ns=(0, 8, 16, 24), rows=None, pattern="row"):
    """Return an ordered [(x, y, n), ...] visiting every cell of column x.

    The chain wires consecutive entries together, so the VISITATION ORDER
    determines which physical routing wires get forced. This is the ONE
    diversity knob that matters — validated 2026-07-20: port rotation and LUT
    mask add ~0 new bits (routing cells don't depend on LUT pin or truth
    table), but a different traversal order adds ~75 new routing bits/compile
    because it forces a different set of C4/LOCAL hops.

    Patterns (all cover the same cell set, different consecutive-pair profile):
      row      — Y outer, N inner (short N-steps then row jumps)
      col      — N outer, Y inner (row-steps then N jumps; longer C4)
      rowstr2  — rows in stride-2 order (0,2,4,.. then 1,3,..) → 2-row C4 hops
      colstr2  — cols/N traversal, rows stride-2 inner
      diag     — diagonal walk (both Y and N advance each step)
    """
    rows = list(rows) if rows is not None else list(LAB_Y)
    ns = list(ns)

    def boustro(seq, i):
        return seq if (i % 2 == 0) else list(reversed(seq))

    out = []
    if pattern == "row":
        for i, y in enumerate(rows):
            for n in boustro(ns, i):
                out.append((x, y, n))
    elif pattern == "col":
        for i, n in enumerate(ns):
            for y in boustro(rows, i):
                out.append((x, y, n))
    elif pattern == "rowstr2":
        order = rows[0::2] + rows[1::2]
        for i, y in enumerate(order):
            for n in boustro(ns, i):
                out.append((x, y, n))
    elif pattern == "colstr2":
        order = rows[0::2] + rows[1::2]
        for i, n in enumerate(ns):
            for y in boustro(order, i):
                out.append((x, y, n))
    elif pattern == "diag":
        cells = [(y, n) for y in rows for n in ns]
        cells.sort(key=lambda yn: (rows.index(yn[0]) + ns.index(yn[1]),
                                   ns.index(yn[1])))
        out = [(x, y, n) for (y, n) in cells]
    elif pattern.startswith("perm"):
        # Deterministic pseudo-random traversal: chains physically DISTANT
        # cells, so the forced hops span long distances -> exercises long
        # lines (C16/R24) and multi-span C4/R4 that adjacency patterns never
        # touch. Seed from the suffix (perm1, perm2, ...); no RNG needed.
        seed = int(pattern[4:] or "1")
        cells = [(x, y, n) for y in rows for n in ns]
        k = len(cells)
        # LCG-style index permutation with a seed-dependent odd stride
        stride = (2 * ((seed * 2654435761) % (k // 2)) + 1)
        order = sorted(range(k), key=lambda i: ((i * stride + seed * 40503) % k))
        out = [cells[i] for i in order]
    else:
        raise ValueError(f"unknown pattern {pattern!r}")
    return out


def gen_column_fill(placements, name: str = "fuzz_top", mask: int = 0x8888,
                    port_offset: int = 0):
    """Build a chained-LUT Verilog module + placement dict for one column.

    placements: ordered [(x, y, n), ...]; consecutive entries are chained.
    mask: LUT truth-table — different masks set different LUT SRAM cells, so
        sweeping it covers the LUT-SRAM dark bits a single mask misses.
    port_offset: rotates which input port each cell uses. Cell i drives
        PORTS[(i+port_offset)%4]; sweeping offset 0..3 makes every LE receive
        its signal on every port across passes → covers all four inbound
        LOCAL_INTERCONNECT mux groups per LE (a big share of routing dark bits).
    Returns (verilog_str, placement_map) mapping cell name -> LCCOMB_X_Y_N.
    """
    k = len(placements)
    if k < 2:
        raise ValueError("need >=2 placements for a chain")

    lines = []
    placement = {}
    for i, (x, y, n) in enumerate(placements):
        inst = f"cell_{i}"
        placement[inst] = f"LCCOMB_X{x}_Y{y}_N{n}"
        port = PORTS[(i + port_offset) % 4]
        # cell 0 is driven by top-level pin A; cell i>0 by the previous combout
        src = "A" if i == 0 else f"w{i-1}"
        pin_ports = []
        for p in PORTS:
            sig = src if p == port else "1'b0"
            pin_ports.append(f"        .{p}({sig})")
        pin_ports_str = ",\n".join(pin_ports)
        lines.append(f"""    wire w{i};
    cycloneive_lcell_comb #(
        .lut_mask(16'h{mask:04X}),
        .sum_lutc_input("datac"),
        .dont_touch("on")
    ) {inst} (
{pin_ports_str},
        .combout(w{i})
    );""")

    body = "\n".join(lines)
    verilog = f"""module {name}(
    input  wire CLK,
    input  wire A,
    output reg  Q
);
{body}

    always @(posedge CLK)
        Q <= w{k-1};
endmodule
"""
    return verilog, placement
