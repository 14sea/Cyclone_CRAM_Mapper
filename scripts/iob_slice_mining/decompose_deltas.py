# SPDX-License-Identifier: GPL-3.0-or-later
"""Decompose pair-vs-zero mining deltas into:
  - universal_infra : pin-invariant AND target-invariant cells
  - pin_footprint   : pin-specific, target-invariant cells (R(pin->zero_lab)
                      + pin-mux)
  - pure_common     : per-target, pin-invariant residual cells
                      (approx. R(*->target) + R(sec_src->target) + port-mux)

Given a pair-mining template with fixed secondary source (A11) and fixed
zero_lab, each mining delta decomposes as:

  delta(pin, target) = universal_infra
                    ⊕ pin_footprint(pin)
                    ⊕ pure_common(target)
                    ⊕ small residual  (a few cells per pair)

`pure_common` serves as an approximate absolute IOB→target cell set,
valid for any pin that enters the same near-pad fabric column. To fully
isolate R(IOB→target), one more sweep with a different secondary source
(to eliminate R(sec_src→target)) is needed.

Usage:
    python3 decompose_deltas.py
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent


def tup(cells):
    return {tuple(c) for c in cells}


def main() -> int:
    raw = json.loads((REPO / "results" / "iob_route_cells.json").read_text())
    routes = raw["routes"]

    by_target = defaultdict(dict)
    pins_seen = set()
    for key, cells in routes.items():
        pin = key.split("->")[0][4:]
        tgt = tuple(key.split("->")[1].split(","))
        by_target[tgt][pin] = tup(cells)
        pins_seen.add(pin)
    pins = sorted(pins_seen)

    # Universal infra = cells in EVERY delta
    per_tgt_all_pins = [
        set.intersection(*(by_target[t][p] for p in pins if p in by_target[t]))
        for t in by_target
        if all(p in by_target[t] for p in pins)
    ]
    universal = set.intersection(*per_tgt_all_pins)

    # pin_always = cells in every delta for a given pin (across all targets)
    pin_always = {}
    for p in pins:
        sets = [by_target[t][p] for t in by_target if p in by_target[t]]
        pin_always[p] = set.intersection(*sets)
    pin_footprint = {p: pin_always[p] - universal for p in pins}

    print(f"pins seen    : {pins}")
    print(f"targets seen : {len(by_target)}")
    print(f"universal_infra : {len(universal)} cells (pin- AND target-invariant)")
    for p in pins:
        print(f"pin_footprint[{p}] : {len(pin_footprint[p])} cells "
              f"(pin-specific, target-invariant)")

    print("\n=== per-target pure_common (pin-invariant, target-dependent) ===")
    pure_commons = {}
    for tgt, per_pin in by_target.items():
        pure = set.intersection(*per_pin.values()) - universal
        pure_commons[tgt] = pure
        # Residual diagnostics
        pure_per_pin = {p: d - universal - pin_footprint[p]
                        for p, d in per_pin.items()}
        residuals = {}
        for p in per_pin:
            residuals[p] = pure_per_pin[p] - pure
        max_resid = max(len(r) for r in residuals.values())
        print(f"  {tgt}: pure={len(pure)}, max residual across pins={max_resid}")

    # Write decomposition
    out = {
        "meta": raw["meta"],
        "universal_infra": sorted(list(c) for c in universal),
        "pin_footprint": {p: sorted(list(c) for c in f)
                          for p, f in pin_footprint.items()},
        "pure_common": {
            f"{','.join(t)}": sorted(list(c) for c in v)
            for t, v in pure_commons.items()
        },
    }
    out_path = REPO / "results" / "iob_route_decomposed.json"
    out_path.write_text(json.dumps(out, indent=2))
    print(f"\n[ok] wrote {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
