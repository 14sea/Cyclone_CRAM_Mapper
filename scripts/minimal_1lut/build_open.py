#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Build the minimal 1-LUT design (KEY2 -> LED0) through the open toolchain.

Yosys -> nextpnr-generic -> np2fasm -> fasm2rbf -> RBF

Produces: tmp/minimal_1lut_open/passthrough.rbf
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
SCRIPT_DIR = Path(__file__).resolve().parent
WORK = REPO / "tmp" / "minimal_1lut_open"
OUT_RBF = WORK / "passthrough.rbf"

sys.path.insert(0, str(REPO / "fuzz"))
sys.path.insert(0, str(REPO / "synth"))


def run(cmd, cwd=None, env=None):
    print(f"  $ {' '.join(str(c) for c in cmd)}", flush=True)
    r = subprocess.run(cmd, cwd=str(cwd) if cwd else None,
                       capture_output=True, text=True, errors="replace",
                       timeout=300, env=env)
    if r.returncode != 0:
        print(f"FAIL (rc={r.returncode})")
        if r.stdout:
            print(r.stdout[-3000:])
        if r.stderr:
            print(r.stderr[-3000:])
        sys.exit(1)
    return r


def get_oss_env():
    import os
    env = os.environ.copy()
    oss_env = Path.home() / "opt" / "oss-cad-suite" / "environment"
    if oss_env.exists():
        r = subprocess.run(
            ["bash", "-c", f"source {oss_env} && env"],
            capture_output=True, text=True)
        for line in r.stdout.splitlines():
            if "=" in line:
                k, _, v = line.partition("=")
                env[k] = v
    return env


def main():
    env = get_oss_env()
    WORK.mkdir(parents=True, exist_ok=True)

    verilog = SCRIPT_DIR / "passthrough.v"
    techmap = REPO / "synth" / "ep4ce6_map.v"
    prims   = REPO / "synth" / "prims.v"
    chipdb_py   = REPO / "results" / "chipdb_ep4ce6.py"
    chipdb_json = REPO / "results" / "chipdb_ep4ce6_data.json"

    # --- Step 1: Yosys synthesis ---
    print("\n=== Step 1: Yosys synthesis ===", flush=True)
    yosys_json = WORK / "passthrough.json"
    yosys_script = f"""
read_verilog -lib {prims}
read_verilog {verilog}
hierarchy -check -top passthrough
proc
opt -full
flatten
opt -full
techmap -map {techmap}
techmap
opt -fast
simplemap
abc -lut 4
clean
techmap -map {techmap}
opt_clean
simplemap t:$and t:$or t:$xor t:$xnor t:$not
techmap -map +/gate2lut.v -D LUT_WIDTH=4
clean
techmap -map {techmap}
opt_clean
delete t:$scopeinfo
clean
stat
write_json {yosys_json}
"""
    yosys_ys = WORK / "synth.ys"
    yosys_ys.write_text(yosys_script)
    r = run(["yosys", "-s", str(yosys_ys)], cwd=WORK, env=env)
    print(r.stdout[-1500:])

    # Inspect synthesized design
    synth_data = json.loads(yosys_json.read_text())
    for mod_name, mod in synth_data.get("modules", {}).items():
        cells = mod.get("cells", {})
        if cells:
            print(f"  Module {mod_name}: {len(cells)} cells")
            for cn, cc in cells.items():
                print(f"    {cn}: type={cc.get('type')}")

    # --- Step 1b: Pin constraints ---
    PIN_MAP = {
        "KEY2$iob": "IOB_A_PIN_E16",
        "LED0$iob": "IOB_Q_PIN_G15",
    }
    pin_script = WORK / "pin_constraints.py"
    pin_script.write_text(
        "import nextpnrpy_generic as npnr\n"
        "PIN_MAP = " + repr(PIN_MAP) + "\n"
        "bound = 0\n"
        "for kv in ctx.cells:\n"
        "    name = str(kv.first)\n"
        "    if name in PIN_MAP:\n"
        "        ctx.bindBel(PIN_MAP[name], kv.second, npnr.STRENGTH_LOCKED)\n"
        "        bound += 1\n"
        "        print(f'  pin {name} -> {PIN_MAP[name]}')\n"
        "print(f'[pin_constraints] bound {bound}/{len(PIN_MAP)} IO cells')\n"
    )

    # --- Step 2: nextpnr-generic ---
    print("\n=== Step 2: nextpnr placement + routing ===", flush=True)
    if not chipdb_json.exists():
        print("ERROR: chipdb not found. Run: python3 fuzz/chipdb_gen.py")
        sys.exit(1)

    placed_json = WORK / "passthrough_placed.json"
    nextpnr_cmd = [
        "nextpnr-generic",
        "--json", str(yosys_json),
        "--pre-pack", str(chipdb_py),
        "--pre-place", str(pin_script),
        "--router", "router2",
        "--write", str(placed_json),
    ]
    r = run(nextpnr_cmd, cwd=WORK, env=env)
    for line in (r.stdout + r.stderr).splitlines():
        ll = line.lower()
        if any(k in ll for k in ["error", "warning", "utilisation",
                                   "cells", "bels", "placed",
                                   "routed", "slack", "info: program"]):
            print(f"  {line}")

    # --- Step 3: np2fasm ---
    print("\n=== Step 3: np2fasm ===", flush=True)
    fasm_path = WORK / "passthrough.fasm"
    from np2fasm import convert
    routed_data = json.loads(placed_json.read_text())
    fasm_lines, warnings = convert(routed_data, baseline="pure")
    fasm_text = "\n".join(fasm_lines) + "\n"
    fasm_path.write_text(fasm_text)

    print(f"  FASM: {len(fasm_lines)} lines")
    print("  --- FASM content ---")
    for line in fasm_lines:
        print(f"    {line}")
    print("  --- end FASM ---")

    if warnings:
        print(f"\n  Warnings ({len(warnings)}):")
        for w in warnings:
            print(f"    {w}")

    # Show placed cell positions
    print("\n  --- Placed cells ---")
    mods = routed_data.get("modules", {})
    for mod_name, mod in mods.items():
        for cn, cc in mod.get("cells", {}).items():
            bel = cc.get("attributes", {}).get("NEXTPNR_BEL", "")
            ctype = cc.get("type", "")
            if bel:
                print(f"    {cn}: type={ctype}, bel={bel}")

    # --- Step 4: fasm2rbf ---
    print("\n=== Step 4: fasm2rbf ===", flush=True)
    from pure_zero_rbf import make_pure_zero_rbf
    from fasm2rbf import bitgen

    base_rbf = make_pure_zero_rbf()
    result_rbf = bitgen(fasm_text, base_rbf, lenient=False)
    OUT_RBF.write_bytes(result_rbf)
    print(f"  RBF: {len(result_rbf)} bytes -> {OUT_RBF}")

    # --- Analysis: what's missing? ---
    print("\n=== Analysis ===")
    has_iob_in = any("IOB_IN" in l for l in fasm_lines)
    has_iob_out = any("IOB_OUT" in l for l in fasm_lines)
    has_lut = any(".LUT " in l for l in fasm_lines)
    has_route = any(l.startswith("ROUTE ") for l in fasm_lines)
    has_iob_route = any("IOB_ROUTE" in l for l in fasm_lines)
    has_src = any(l.startswith("SRC ") for l in fasm_lines)
    has_gclk = any("GCLK" in l for l in fasm_lines)
    has_out_route = False  # SLICE->IOB output routing

    print(f"  IOB_IN:       {'YES' if has_iob_in else 'MISSING'}")
    print(f"  IOB_OUT:      {'YES' if has_iob_out else 'MISSING'}")
    print(f"  LUT:          {'YES' if has_lut else 'MISSING'}")
    print(f"  IOB_ROUTE:    {'YES' if has_iob_route else 'MISSING'}")
    print(f"  ROUTE:        {'YES' if has_route else 'N/A (1-LUT, no inter-SLICE)'}")
    print(f"  SRC:          {'YES' if has_src else 'N/A'}")
    print(f"  GCLK:         {'YES' if has_gclk else 'N/A (combinational)'}")
    print(f"  OUTPUT_ROUTE: {'YES' if has_out_route else 'MISSING (SLICE->IOB gap)'}")

    if not has_out_route:
        print("\n  ** SLICE->IOB output routing is NOT emitted by np2fasm. **")
        print("  ** The LED pad is configured but won't receive logic output. **")
        print("  ** This is likely the root cause of 'LEDs constant-on'. **")

    print(f"\nDone. Flash with:")
    print(f"  openFPGALoader -c usb-blaster {OUT_RBF}")


if __name__ == "__main__":
    main()
