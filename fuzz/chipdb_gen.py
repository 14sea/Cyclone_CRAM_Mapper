#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Phase 5.3 M2 — nextpnr-generic chipdb generator for EP4CE6.

Emits two artifacts in ``results/``:

* ``chipdb_ep4ce6_data.json`` — compact data blob describing every bel,
  wire, and pip that nextpnr needs.  Produced from ``fuzz/config.py``
  geometry, ``results/route_cells_full.json`` (13,487 Plan D' sig-cache
  entries covering 95.9% of the NEORV32 edge set), and the
  ``M9K_INIT_ANCHORS`` table from ``fuzz/m9k_init_basis.py``.

* ``chipdb_ep4ce6.py`` — tiny ``nextpnr-generic --run`` entry point that
  loads the JSON blob and populates ``ctx`` via the generic Python API.
  Kept intentionally small so nextpnr's Python startup is cheap.

Usage
-----
::

    python3 fuzz/chipdb_gen.py
    nextpnr-generic --uarch generic --run results/chipdb_ep4ce6.py \\
        --json /tmp/nv32_synth/neorv32.json --top neorv32_top \\
        --write /tmp/nv32_synth/neorv32_routed.json

Scope / limits
--------------
* Bels: one ``EP4CE6_SLICE`` per (X, Y, N) LAB slot (``GENERIC_SLICE``
  in nextpnr terms — the packer folds LUT4+DFF into it); ``EP4CE6_IOB``
  for the AX301 pin map from ``config.ROUTE_FUZZ_PINS``; one
  ``EP4CE6_M9K`` per (X, Y, N=0) site at X in {15, 27}, Y 2..21.
* Wires: one output wire per slice (``Q``), four input wires per slice
  (``dataa..datad``), plus every unique endpoint mentioned in the
  route sig-cache (lazily created).
* Pips: exactly one per sig-cache key
  ``"sx,sy,sn->dx,dy,dn,port"``; delay is a placeholder (non-timing-
  driven P&R at this stage — NEORV32 is 46% utilised so slack should
  be ample even without STA).
* M9K bels carry an ``anchor`` attribute so np2fasm (M4) can look up
  the per-site byte anchor for ``write_init``.

This is a functional-first first pass.  Things deliberately *not* in
M2 scope: per-pip delay annotations, IO standard assignments,
carry-chain bels, PLL bels, timing-driven placement hints.  All are
follow-ups once M5/M6 prove the chain.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import config  # noqa: E402
from m9k_init_basis import M9K_INIT_ANCHORS  # noqa: E402

ROOT = HERE.parent
RESULTS = ROOT / "results"

DATA_PATH = RESULTS / "chipdb_ep4ce6_data.json"
SCRIPT_PATH = RESULTS / "chipdb_ep4ce6.py"

# Full LAB grid including the jailbreak columns/rows. The chipdb lives
# on true silicon, not the CE6 fitter whitelist — nextpnr should be
# free to place anywhere the silicon supports.
LAB_X_FULL = sorted(set(config.LAB_X) | set(config.JAILBREAK_LAB_X))
LAB_Y_FULL = sorted(set(config.LAB_Y) | set(config.JAILBREAK_LAB_Y))
LE_N = config.LE_N
M9K_X = [15, 27]
M9K_Y = list(range(2, 22))

PLACEHOLDER_DELAY = 1  # nextpnr generic delay_t units

SLICE_INPUTS = ("dataa", "datab", "datac", "datad")


def _wire_slice_out(x: int, y: int, n: int) -> str:
    return f"slice_X{x}_Y{y}_N{n}_Q"


def _wire_slice_in(x: int, y: int, n: int, port: str) -> str:
    return f"slice_X{x}_Y{y}_N{n}_{port}"


def _wire_m9k_port(x: int, y: int, port: str) -> str:
    return f"m9k_X{x}_Y{y}_N0_{port}"


def _wire_iob(name: str, kind: str) -> str:
    return f"iob_{name}_{kind}"


def build_chipdb() -> dict:
    bels: list[dict] = []
    wires: list[dict] = []
    belpins: list[dict] = []
    pips: list[dict] = []

    # Grid extents for nextpnr. Use inclusive max and add a 1-tile
    # margin for the IO ring so IOB bels can sit at (0, y) / (x, 0).
    grid_w = max(LAB_X_FULL + M9K_X) + 2
    grid_h = max(LAB_Y_FULL + M9K_Y) + 2

    # ---------- LAB slices ----------
    for x in LAB_X_FULL:
        for y in LAB_Y_FULL:
            if (x, y) in config.INVALID_LABS:
                continue
            for n in LE_N:
                name = f"SLICE_X{x}_Y{y}_N{n}"
                bels.append({
                    "name": name,
                    "type": "EP4CE6_SLICE",
                    "x": x, "y": y, "z": n,
                })
                qw = _wire_slice_out(x, y, n)
                wires.append({"name": qw, "type": "SLICE_Q", "x": x, "y": y})
                belpins.append({
                    "bel": name, "pin": "Q", "wire": qw, "output": True,
                })
                for port in SLICE_INPUTS:
                    iw = _wire_slice_in(x, y, n, port)
                    wires.append({"name": iw, "type": "SLICE_IN",
                                  "x": x, "y": y})
                    belpins.append({"bel": name, "pin": port.upper(),
                                    "wire": iw, "output": False})

    # ---------- M9K bels ----------
    for x in M9K_X:
        for y in M9K_Y:
            site = f"X{x}_Y{y}_N0"
            name = f"M9K_{site}"
            # anchor/bp if we've calibrated this site at 9x512 — M4 uses
            # it to emit FASM M9K.INIT directives.
            anchor = M9K_INIT_ANCHORS.get((site, 9, 512))
            bels.append({
                "name": name,
                "type": "EP4CE6_M9K",
                "x": x, "y": y, "z": 0,
                "anchor": anchor,  # [byte, bp] or None
            })
            for port in ("CLK", "ADDR", "DIN", "DOUT", "WE"):
                wn = _wire_m9k_port(x, y, port)
                wires.append({"name": wn, "type": "M9K_" + port,
                              "x": x, "y": y})
                belpins.append({
                    "bel": name, "pin": port, "wire": wn,
                    "output": (port == "DOUT"),
                })

    # ---------- IOBs (AX301 pin map) ----------
    # Put IOBs on the border row Y=grid_h-1 and spread along X so
    # nextpnr has distinct (x,y,z) locations. They don't carry routing
    # at M2 — np2fasm will emit BIT lines for them later.
    for i, (pin_name, pin_loc) in enumerate(config.ROUTE_FUZZ_PINS.items()):
        name = f"IOB_{pin_name}_{pin_loc}"
        bels.append({
            "name": name, "type": "EP4CE6_IOB",
            "x": i, "y": grid_h - 1, "z": 0,
            "pin": pin_loc,
        })
        wi = _wire_iob(pin_name, "I")
        wo = _wire_iob(pin_name, "O")
        wires.extend([
            {"name": wi, "type": "IOB_I", "x": i, "y": grid_h - 1},
            {"name": wo, "type": "IOB_O", "x": i, "y": grid_h - 1},
        ])
        belpins.extend([
            {"bel": name, "pin": "I", "wire": wi, "output": False},
            {"bel": name, "pin": "O", "wire": wo, "output": True},
        ])

    # ---------- Pips from Plan D' sig-cache ----------
    cache_path = RESULTS / "route_cells_full.json"
    cache = json.loads(cache_path.read_text())
    known_wires = {w["name"] for w in wires}
    pip_count = 0
    skipped_unknown_src = 0
    skipped_unknown_dst = 0
    for key in cache.keys():
        try:
            left, right = key.split("->")
            sx, sy, sn = (int(v) for v in left.split(","))
            dx_s, dy_s, dn_s, port = right.split(",")
            dx, dy, dn = int(dx_s), int(dy_s), int(dn_s)
        except ValueError:
            continue
        src_wire = _wire_slice_out(sx, sy, sn)
        dst_wire = _wire_slice_in(dx, dy, dn, port)
        if src_wire not in known_wires:
            skipped_unknown_src += 1
            continue
        if dst_wire not in known_wires:
            skipped_unknown_dst += 1
            continue
        pips.append({
            "name": f"pip_{sx}_{sy}_{sn}__{dx}_{dy}_{dn}_{port}",
            "type": "SIG",
            "src": src_wire,
            "dst": dst_wire,
            "delay": PLACEHOLDER_DELAY,
            "x": dx, "y": dy,
        })
        pip_count += 1

    return {
        "grid_w": grid_w,
        "grid_h": grid_h,
        "bels": bels,
        "wires": wires,
        "belpins": belpins,
        "pips": pips,
        "stats": {
            "n_bels": len(bels),
            "n_wires": len(wires),
            "n_belpins": len(belpins),
            "n_pips": pip_count,
            "pips_skipped_unknown_src": skipped_unknown_src,
            "pips_skipped_unknown_dst": skipped_unknown_dst,
        },
    }


_RUNNER_TEMPLATE = '''\
# SPDX-License-Identifier: GPL-3.0-or-later
"""nextpnr-generic --run entry point for EP4CE6 (auto-generated).

Do not edit by hand; regenerate with ``python3 fuzz/chipdb_gen.py``.
"""
import json, os
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_DATA = json.loads((_HERE / "chipdb_ep4ce6_data.json").read_text())

# ctx is injected by nextpnr-generic when invoked with --run.
# Loc is exposed under the generic Python API.
try:
    from nextpnrpy_generic import Loc  # type: ignore
except ImportError:
    Loc = globals().get("Loc")  # provided by --run environment

_delay = ctx.getDelayFromNS(0.5)  # placeholder

for w in _DATA["wires"]:
    ctx.addWire(w["name"], w["type"], w["x"], w["y"])

for b in _DATA["bels"]:
    ctx.addBel(b["name"], b["type"], Loc(b["x"], b["y"], b["z"]),
               False, False)

for bp in _DATA["belpins"]:
    ctx.addBelInput(bp["bel"], bp["pin"], bp["wire"]) \\
        if not bp["output"] else \\
        ctx.addBelOutput(bp["bel"], bp["pin"], bp["wire"])

for p in _DATA["pips"]:
    ctx.addPip(p["name"], p["type"], p["src"], p["dst"],
               _delay, Loc(p["x"], p["y"], 0))

print("[chipdb_ep4ce6] loaded:",
      _DATA["stats"]["n_bels"], "bels,",
      _DATA["stats"]["n_wires"], "wires,",
      _DATA["stats"]["n_pips"], "pips")
'''


def main() -> None:
    data = build_chipdb()
    DATA_PATH.write_text(json.dumps(data, indent=1))
    SCRIPT_PATH.write_text(_RUNNER_TEMPLATE)

    s = data["stats"]
    print(f"wrote {DATA_PATH.name}")
    print(f"wrote {SCRIPT_PATH.name}")
    print(f"grid: {data['grid_w']} x {data['grid_h']}")
    print(f"bels:    {s['n_bels']:>7d}")
    print(f"wires:   {s['n_wires']:>7d}")
    print(f"belpins: {s['n_belpins']:>7d}")
    print(f"pips:    {s['n_pips']:>7d}")
    print(f"pips skipped (unknown src slice): "
          f"{s['pips_skipped_unknown_src']}")
    print(f"pips skipped (unknown dst slice): "
          f"{s['pips_skipped_unknown_dst']}")


if __name__ == "__main__":
    main()
