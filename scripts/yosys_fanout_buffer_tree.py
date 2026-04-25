# SPDX-License-Identifier: GPL-3.0-or-later
"""Insert balanced buffer trees on high-fanout Yosys nets.

⚠️ EMPIRICALLY FALSIFIED 2026-04-25 (no placement constraints variant):
Inserting buffer LUTs ALONE — without per-leaf placement constraints
— makes routing WORSE, not better.  The nextpnr analytical placer
puts each leaf buffer near its sinks' centroid; for a globally-
scattered NEORV32 broadcast, every centroid lands near the chip
center, so all 130 leaf buffers cluster in already-congested LABs.
At iter 28 of router2 vs iter 2 of baseline, the buffered run had:
  total overuse: 12 439 → 13 788 (43% worse)
  top-1 hotspot: 106 @ (17, 26)  (vs baseline 98 @ (16, 26))
  hotspot CLUSTER stayed at Y=26 IOB row + Y=14 mid-grid
The "hotspot migrated 1 LAB sideways" outcome is "原地踏步" —
buffers got placed in the same congested region.  See
`memory/trackb_v2_diagnostic_2026_04_25.md`.

This script is RETAINED as a baseline for future v2 work that adds
placement spreading (centroid-aware LOC constraints OR banked
partitioning).  Do NOT use as-is for production routing.


After Yosys synth, structural broadcasts (e.g. NEORV32's
MuxGate$40482 with 2075 sinks) overwhelm the chipdb's per-bank LOCAL
gateway capacity — Track B Phase 5 v9 showed 14% of total congestion
sourced from a single LAB cell because all 2075 sinks have to escape
through one gateway.

Fix: insert pass-through LUT4 buffers in a balanced tree.  Each
high-fanout net with N > THRESHOLD sinks is split into a tree of
LUT buffers with fanout F per node.  This converts one (N >> F)
broadcast into log_F(N) layers each with manageable per-LAB fanout.

Pre-place placement constraints can then spread the buffers across
multiple LABs / banks so the LOCAL gateway never sees more than ~F
sinks routed through it.

Usage:
    python3 scripts/yosys_fanout_buffer_tree.py \
        --in   tmp/ax301_synth/ax301.json \
        --out  tmp/ax301_synth/ax301.bufd.json \
        --threshold 200 --fanout 16

Output JSON is drop-in compatible with `nextpnr-generic --json`.
The buffer LUTs use cell type `LUT` with `INIT="1010101010101010"`
(passthrough I[0] → Q) and `K="...0100"` (K=4).  These pack into
GENERIC_SLICE just like normal LUTs.
"""
from __future__ import annotations
import argparse
import json
import math
from collections import defaultdict
from pathlib import Path


PASSTHROUGH_INIT_LUT4 = "1010101010101010"   # Q = I[0]
K4_BIN = "00000000000000000000000000000100"  # 32-bit binary, value=4


def find_top(j):
    """Pick the module with the most cells."""
    best, best_n = None, -1
    for name, mod in j.get("modules", {}).items():
        n = len(mod.get("cells", {}))
        if n > best_n:
            best, best_n = name, n
    return best


def collect_sinks(top):
    """Map bit -> list of (cell_name, port_name, index_in_port).

    Only INPUT ports of cells, plus top-level OUTPUT ports.
    """
    sinks = defaultdict(list)
    cells = top.get("cells", {})
    for cn, c in cells.items():
        for port, conn in c.get("connections", {}).items():
            direction = c.get("port_directions", {}).get(port, "")
            if direction != "input":
                continue
            for idx, bit in enumerate(conn):
                if isinstance(bit, int):
                    sinks[bit].append((cn, port, idx))

    # Top-level output ports: their bits are sinks (driven by some
    # internal source).  Don't rewire these — keep IO connectivity.
    return sinks


def max_bit_id(top):
    mx = 1
    def update(x, mx):
        return max(mx, x) if isinstance(x, int) else mx
    for nn, nd in top.get("netnames", {}).items():
        for bit in nd.get("bits", []):
            mx = update(bit, mx)
    for cn, c in top.get("cells", {}).items():
        for port, conn in c.get("connections", {}).items():
            for bit in conn:
                mx = update(bit, mx)
    for pn, pd in top.get("ports", {}).items():
        for bit in pd.get("bits", []):
            mx = update(bit, mx)
    return mx


def insert_buffer_lut(cells, name, src_bit, dst_bit):
    """Insert a LUT4 passthrough cell: dst_bit = src_bit."""
    cells[name] = {
        "hide_name": 1,
        "type": "LUT",
        "parameters": {
            "INIT": PASSTHROUGH_INIT_LUT4,
            "K":    K4_BIN,
        },
        "attributes": {
            "fanout_buffer": "1",
        },
        "port_directions": {
            "I": "input",
            "Q": "output",
        },
        "connections": {
            "I": [src_bit, "0", "0", "0"],
            "Q": [dst_bit],
        },
    }


def chunked(seq, n):
    for i in range(0, len(seq), n):
        yield seq[i : i + n]


CLK_PORT_NAMES = {"CLK", "CLK_EN", "C", "clock0", "clock1", "clk_i", "clk"}


def is_clock_net(sink_list):
    """Heuristic: a net is a clock if >=50% of its sinks land on
    well-known clock-input ports of DFF / EP4CE6_M9K cells.
    Clocks are routed via the chipdb's dedicated GCLK_BUS tree, so
    buffer-treeing them would break the dedicated path."""
    if not sink_list:
        return False
    n_clk = sum(1 for (_, port, _) in sink_list if port in CLK_PORT_NAMES)
    return n_clk >= len(sink_list) // 2


def split_high_fanout(top, threshold, fanout):
    """Insert buffer trees on all bits with > threshold sinks.

    Tree shape: bottom-up.  Sinks grouped into chunks of `fanout`,
    one buffer per chunk fed by `src_bit`.  If the resulting buffer
    count itself exceeds `fanout`, recurse upward — those buffers'
    `I[0]` then point at a freshly-inserted higher-level buffer
    instead of `src_bit` directly, until the top layer has ≤ fanout
    buffers all reading `src_bit`.

    Result: `src_bit` drives ≤ `fanout` direct sinks (the top layer);
    every buffer drives ≤ `fanout` next-level loads; the original
    consumer cells' input ports are rewired to leaf buffer outputs.
    """
    cells = top.setdefault("cells", {})
    sinks = collect_sinks(top)
    next_bit = max_bit_id(top) + 1

    def fresh_bit():
        nonlocal next_bit
        b = next_bit
        next_bit += 1
        return b

    n_buffers = 0
    n_nets_split = 0
    report = []

    candidates = sorted(
        ((bit, len(s)) for bit, s in sinks.items() if len(s) > threshold),
        key=lambda x: -x[1],
    )

    n_clock_skipped = 0
    for src_bit, total_n in candidates:
        sink_list = sinks[src_bit]
        if is_clock_net(sink_list):
            n_clock_skipped += 1
            continue
        added_for_net = 0

        # Layer 0: leaf buffers.  Each drives a chunk of original sinks.
        # Cache buf_bit -> buf_name so upper layers can rewire I[0] in O(1).
        leaf_bits: list[int] = []
        bit_to_buf_name: dict[int, str] = {}
        for chunk_idx, chunk in enumerate(chunked(sink_list, fanout)):
            buf_bit = fresh_bit()
            buf_name = f"$bufx_b{src_bit}_L0_{chunk_idx}"
            insert_buffer_lut(cells, buf_name, src_bit, buf_bit)
            leaf_bits.append(buf_bit)
            bit_to_buf_name[buf_bit] = buf_name
            n_buffers += 1
            added_for_net += 1
            for (sink_cell, sink_port, sink_idx) in chunk:
                conn = cells[sink_cell]["connections"][sink_port]
                conn[sink_idx] = buf_bit

        # Climb up: insert intermediate-layer buffers until top layer
        # size is ≤ fanout.  Each upper-layer buffer drives `fanout`
        # lower-layer buffers (rewriting their I[0] from src_bit).
        layer = leaf_bits
        layer_idx = 1
        while len(layer) > fanout:
            new_layer = []
            for chunk_idx, chunk in enumerate(chunked(layer, fanout)):
                buf_bit = fresh_bit()
                buf_name = f"$bufx_b{src_bit}_L{layer_idx}_{chunk_idx}"
                insert_buffer_lut(cells, buf_name, src_bit, buf_bit)
                new_layer.append(buf_bit)
                bit_to_buf_name[buf_bit] = buf_name
                n_buffers += 1
                added_for_net += 1
                for low_bit in chunk:
                    low_name = bit_to_buf_name[low_bit]
                    cells[low_name]["connections"]["I"][0] = buf_bit
            layer = new_layer
            layer_idx += 1

        n_nets_split += 1
        report.append({
            "src_bit": src_bit,
            "original_sinks": total_n,
            "layers": layer_idx,
            "buffers_added": added_for_net,
            "final_top_layer_size": len(layer),
        })

    return n_nets_split, n_buffers, report, n_clock_skipped


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", required=True)
    ap.add_argument("--out", dest="out", required=True)
    ap.add_argument("--threshold", type=int, default=200,
                    help="split nets with > threshold sinks (default 200)")
    ap.add_argument("--fanout", type=int, default=16,
                    help="max sinks per buffer (default 16)")
    args = ap.parse_args()

    j = json.loads(Path(args.inp).read_text())
    top_name = find_top(j)
    print(f"Top module: {top_name!r}  cells={len(j['modules'][top_name]['cells'])}")

    n_nets, n_bufs, rpt, n_clk_skip = split_high_fanout(
        j["modules"][top_name],
        threshold=args.threshold,
        fanout=args.fanout,
    )
    print(f"\nSplit {n_nets} high-fanout nets, added {n_bufs} buffer LUTs.")
    print(f"Skipped {n_clk_skip} clock-net candidates (kept on GCLK_BUS).")
    for r in rpt[:10]:
        print(f"  bit={r['src_bit']:>5} sinks={r['original_sinks']:>5} "
              f"layers={r['layers']} top_layer_size={r['final_top_layer_size']}")

    new_cells = len(j["modules"][top_name]["cells"])
    print(f"\nFinal cell count: {new_cells}")

    Path(args.out).write_text(json.dumps(j, indent=1))
    print(f"Wrote {args.out}")


if __name__ == "__main__":
    main()
