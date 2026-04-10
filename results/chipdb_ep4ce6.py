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

_delay1 = ctx.getDelayFromNS(0.5)   # direct pips
_delay10 = ctx.getDelayFromNS(5.0)  # hop pips (10× cost, steers pathfinder)

for w in _DATA["wires"]:
    ctx.addWire(name=w["name"], type=w["type"], x=w["x"], y=w["y"])

for b in _DATA["bels"]:
    ctx.addBel(name=b["name"], type=b["type"],
               loc=Loc(b["x"], b["y"], b["z"]),
               gb=False, hidden=False)

for bp in _DATA["belpins"]:
    if bp["output"]:
        ctx.addBelOutput(bel=bp["bel"], name=bp["pin"], wire=bp["wire"])
    else:
        ctx.addBelInput(bel=bp["bel"], name=bp["pin"], wire=bp["wire"])

for p in _DATA["pips"]:
    d = _delay10 if p["delay"] > 1 else _delay1
    ctx.addPip(name=p["name"], type=p["type"],
               srcWire=p["src"], dstWire=p["dst"],
               delay=d, loc=Loc(p["x"], p["y"], 0))

print("[chipdb_ep4ce6] loaded:",
      _DATA["stats"]["n_bels"], "bels,",
      _DATA["stats"]["n_wires"], "wires,",
      _DATA["stats"]["n_pips_total"], "pips")
