# SPDX-License-Identifier: GPL-3.0-or-later
# --pre-route hook: snapshot placed state (cell XY, nets, fanout) and
# abort before route() so we can analyse congestion drivers without
# waiting for the stuck router.
#
# Usage:
#   source $HOME/opt/oss-cad-suite/environment
#   PYTHONUNBUFFERED=1 nextpnr-generic \
#       --run results/chipdb_ep4ce6.py \
#       --pre-place synth/preplace_ax301.py \
#       --pre-route scripts/chipdb_probe/preroute_snapshot.py \
#       --json tmp/ax301_synth/ax301.json --router router2
#
# Writes tmp/trackb_probe/placed_snapshot.json with cell coords,
# per-column SLICE utilisation, and high-fanout nets (≥ 50 users).
import json
import sys
from collections import Counter, defaultdict

try:
    from nextpnrpy_generic import Loc  # type: ignore
except ImportError:
    pass

def _loc_of(cell):
    bel = cell.bel
    if bel is None:
        return None, None, None
    try:
        loc = ctx.getBelLocation(bel)
        return loc.x, loc.y, loc.z
    except Exception:
        return None, None, None

cells_by_type = Counter()
cell_xy = defaultdict(Counter)       # type -> Counter[(x,y)]
cell_items = [(kv.first, kv.second) for kv in ctx.cells]
print(f"[snapshot] total cells after place: {len(cell_items)}",
      file=sys.stderr, flush=True)

dense_cells = []
for name, c in cell_items:
    t = c.type
    cells_by_type[t] += 1
    x, y, z = _loc_of(c)
    if x is not None:
        cell_xy[t][(x, y)] += 1
        dense_cells.append({"name": name, "type": t, "x": x, "y": y, "z": z})

print(f"[snapshot] cells by type: {dict(cells_by_type.most_common())}",
      file=sys.stderr, flush=True)

# Top 10 LAB-positions by SLICE crowding
slice_xy = cell_xy.get("GENERIC_SLICE", Counter())
print("[snapshot] top 10 SLICE-crowded LAB positions:",
      file=sys.stderr, flush=True)
for (x, y), n in slice_xy.most_common(10):
    print(f"   ({x:2d},{y:2d}) = {n} slices", file=sys.stderr, flush=True)

# Per-X column utilisation
col_util = Counter()
for (x, y), n in slice_xy.items():
    col_util[x] += n
print("[snapshot] SLICE per LAB-column X (high → low):",
      file=sys.stderr, flush=True)
for x, n in sorted(col_util.items(), key=lambda kv: -kv[1])[:15]:
    print(f"   X={x:2d}: {n} slices", file=sys.stderr, flush=True)

# Net fanout distribution
fanouts = Counter()
high_fanout_nets = []
for kv in ctx.nets:
    netname = kv.first
    net = kv.second
    n_users = len(net.users) if hasattr(net, "users") else 0
    fanouts[n_users] += 1
    if n_users >= 50:
        high_fanout_nets.append((netname, n_users))
print(f"[snapshot] fanout histogram (top 12): "
      f"{dict(Counter({k:v for k,v in fanouts.items()}).most_common(12))}",
      file=sys.stderr, flush=True)
print(f"[snapshot] high-fanout nets (≥50 users): {len(high_fanout_nets)}",
      file=sys.stderr, flush=True)
for netname, n in sorted(high_fanout_nets, key=lambda kv: -kv[1])[:12]:
    print(f"   {n:4d} users : {netname}", file=sys.stderr, flush=True)

# dump to JSON for offline analysis
snap = {
    "cells_by_type": dict(cells_by_type),
    "slice_crowded": [{"x": x, "y": y, "n": n}
                      for (x, y), n in slice_xy.most_common(50)],
    "col_util": dict(col_util),
    "fanout_histogram": dict(fanouts),
    "high_fanout_nets": [{"name": n, "users": u}
                         for n, u in high_fanout_nets],
    "all_cells": dense_cells,
}
import os
_out_dir = os.environ.get("TRACKB_PROBE_DIR", "tmp/trackb_probe")
os.makedirs(_out_dir, exist_ok=True)
_out_path = os.path.join(_out_dir, "placed_snapshot.json")
with open(_out_path, "w") as f:
    json.dump(snap, f, indent=1, default=str)
print(f"[snapshot] wrote {_out_path}",
      file=sys.stderr, flush=True)

# Abort before route — we only want the placement picture.
print("[snapshot] aborting before route() (diagnostic mode)",
      file=sys.stderr, flush=True)
sys.exit(0)
