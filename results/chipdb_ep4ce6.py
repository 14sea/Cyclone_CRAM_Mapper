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
    ctx.addBelInput(bp["bel"], bp["pin"], bp["wire"]) \
        if not bp["output"] else \
        ctx.addBelOutput(bp["bel"], bp["pin"], bp["wire"])

for p in _DATA["pips"]:
    ctx.addPip(p["name"], p["type"], p["src"], p["dst"],
               _delay, Loc(p["x"], p["y"], 0))

print("[chipdb_ep4ce6] loaded:",
      _DATA["stats"]["n_bels"], "bels,",
      _DATA["stats"]["n_wires"], "wires,",
      _DATA["stats"]["n_pips"], "pips")
