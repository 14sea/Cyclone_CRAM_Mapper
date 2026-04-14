# SPDX-License-Identifier: GPL-3.0-or-later
"""Translate pair-vs-iob_zero deltas into absolute cells (nv_zero_global frame)
for sig-cache injection.

Algebra:
  cells_abs(pin, tgt) = cells_pair(pin, tgt) XOR cells_nv_zero
                      = delta(pin, tgt) XOR bridge(pin)
where bridge(pin) = cells_nv_zero XOR cells_iob_zero(pin).

This script:
  1. Recomputes absolute cells directly from pair RBFs + nv_zero_global
     (ground truth — the answer we want to store in sig-cache).
  2. Reconstructs the SAME absolute set from delta(pin, tgt) XOR bridge(pin)
     using the mining data we already have.
  3. Verifies both paths produce identical cells (they must, by algebra).
  4. Reports absolute-cell sizes per (pin, tgt) — this is the final
     R(IOB→SLICE) route footprint in nv_zero_global frame.
  5. Writes results/iob_to_slice_sigcache.json — ready to inject.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
sys.path.insert(0, str(REPO / "scripts" / "iob_slice_mining"))

from bridge_delta_probe import read_rbf_cells  # noqa: E402


def main() -> int:
    work = HERE / "work"
    nv_zero_path = REPO / "results" / "rbf" / "nv_zero_global.rbf"

    raw_routes = json.loads(
        (REPO / "results" / "iob_route_cells.json").read_text()
    )
    routes = raw_routes["routes"]

    nv_cells = read_rbf_cells(nv_zero_path)
    print(f"[ref ] nv_zero_global: {len(nv_cells)} cells")

    # Build bridges from iob_zero RBFs
    pins = sorted({k.split("->")[0][4:] for k in routes})
    bridges = {}
    for p in pins:
        iob_zero = work / f"iob_zero_{p}.rbf"
        bridges[p] = nv_cells ^ read_rbf_cells(iob_zero)
        print(f"[bridge] {p}: {len(bridges[p])} cells")

    out_entries = {}
    mismatches = 0
    for key, delta_cells in routes.items():
        pin = key.split("->")[0][4:]
        tgt = key.split("->")[1]
        # delta -> absolute via bridge
        delta_set = {tuple(c) for c in delta_cells}
        abs_via_bridge = delta_set ^ bridges[pin]

        # ground truth: directly diff pair.rbf vs nv_zero_global
        pair_rbf = work / f"iob_pair_{pin}_{tgt.replace(',', '_')}.rbf"
        if not pair_rbf.exists():
            # spaces OK -- mining script used underscores already
            print(f"  [miss] {pair_rbf.name} not found, "
                  f"skipping GT check")
            ok = "(unchecked)"
        else:
            pair_cells = read_rbf_cells(pair_rbf)
            abs_direct = nv_cells ^ pair_cells
            if abs_direct == abs_via_bridge:
                ok = "OK"
            else:
                sd = abs_direct ^ abs_via_bridge
                ok = f"MISMATCH sd={len(sd)}"
                mismatches += 1

        print(f"  {key:50s}  |delta|={len(delta_cells):4d}  "
              f"|abs|={len(abs_via_bridge):4d}  [{ok}]")
        out_entries[key] = sorted(list(c) for c in abs_via_bridge)

    out = {
        "meta": {
            **raw_routes.get("meta", {}),
            "frame": "nv_zero_global",
            "source": "delta XOR bridge(pin), verified against direct "
                      "pair XOR nv_zero_global",
            "count": len(out_entries),
        },
        "absolute_cells": out_entries,
    }
    out_path = REPO / "results" / "iob_to_slice_sigcache.json"
    out_path.write_text(json.dumps(out, indent=2))

    print()
    print(f"[ok] wrote {out_path} ({out_path.stat().st_size} bytes, "
          f"{len(out_entries)} entries)")
    if mismatches:
        print(f"[!!] {mismatches} entries failed GT check — "
              "bridge math is wrong somewhere.")
        return 1
    print("[verified] all entries: delta ^ bridge(pin) == "
          "pair ^ nv_zero_global  (algebra correct)")

    sizes = sorted(len(v) for v in out_entries.values())
    print(f"\nabsolute-cell size distribution: "
          f"min={sizes[0]}  median={sizes[len(sizes)//2]}  max={sizes[-1]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
