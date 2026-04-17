# SPDX-License-Identifier: GPL-3.0-or-later
"""nextpnr-generic --pre-route hook: dump placement + netlist to JSON.

Extracts cell placements and net connectivity after placement, before
routing starts. Writes to tmp/ax301_placement.json for the external
router that bypasses nextpnr's router2.

Usage:
    nextpnr-generic --pre-pack results/chipdb_ep4ce6.py \
                    --pre-place synth/preplace_ax301.py \
                    --pre-route synth/dump_placement.py \
                    --json tmp/ax301_synth/ax301.json --router router2
"""
import json
import os
import traceback

OUT = "/home/test/EP4CE6/tmp/ax301_placement.json"

try:
    cells = {}
    for kv in ctx.cells:
        name = kv.first
        cell = kv.second
        bel = cell.bel
        if bel is None:
            continue
        bel_str = str(bel)
        cell_type = str(cell.type)
        params = {}
        for pk in cell.params:
            params[pk.first] = str(pk.second)
        cells[name] = {
            "type": cell_type,
            "bel": bel_str,
            "params": params,
        }

    nets = {}
    for kv in ctx.nets:
        net_name = kv.first
        net = kv.second
        driver = None
        if net.driver.cell is not None:
            driver = {
                "cell": str(net.driver.cell.name),
                "port": str(net.driver.port),
            }
        sinks = []
        for user in net.users:
            if user.cell is not None:
                sinks.append({
                    "cell": str(user.cell.name),
                    "port": str(user.port),
                })
        if driver or sinks:
            nets[net_name] = {"driver": driver, "sinks": sinks}

    data = {"cells": cells, "nets": nets}
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w") as f:
        json.dump(data, f, indent=1)

    print(f"[dump_placement] wrote {OUT}: {len(cells)} cells, {len(nets)} nets")
except Exception:
    traceback.print_exc()
