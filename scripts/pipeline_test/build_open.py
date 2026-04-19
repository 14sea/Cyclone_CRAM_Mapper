# SPDX-License-Identifier: GPL-3.0-or-later
"""Build the pipeline-test design with the open toolchain.

Yosys → nextpnr-generic → np2fasm → fasm2rbf → RBF
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
SCRIPT_DIR = Path(__file__).resolve().parent
WORK = REPO / "tmp" / "pipeline_test_open"
OUT_RBF = REPO / "tmp" / "pipeline_test_open.rbf"

sys.path.insert(0, str(REPO / "fuzz"))
sys.path.insert(0, str(REPO / "synth"))


def run(cmd, cwd=None, env=None):
    print(f"  $ {' '.join(str(c) for c in cmd)}", flush=True)
    r = subprocess.run(cmd, cwd=str(cwd) if cwd else None,
                       capture_output=True, text=True, errors="replace",
                       timeout=1800, env=env)
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

    verilog = SCRIPT_DIR / "test_top.v"
    techmap = REPO / "synth" / "ep4ce6_map.v"
    prims   = REPO / "synth" / "prims.v"
    chipdb_py   = REPO / "results" / "chipdb_ep4ce6.py"
    chipdb_json = REPO / "results" / "chipdb_ep4ce6_data.json"

    # --- Step 1: Yosys synthesis ---
    print("\n=== Step 1: Yosys synthesis ===", flush=True)
    yosys_json = WORK / "test_top.json"
    yosys_script = f"""
read_verilog -lib {prims}
read_verilog {verilog}
hierarchy -check -top test_top
proc
async2sync
opt -full
flatten
opt -full
techmap -map {techmap}
techmap
opt -fast
dffunmap -ce-only
dffunmap -srst-only
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

    # --- Step 1b: Generate pin constraint script for --pre-place ---
    PIN_MAP = {
        "CLOCK$iob": "IOB_CLK_PIN_E1",
        "KEY2$iob":  "IOB_A_PIN_E16",
        "KEY3$iob":  "IOB_B_PIN_M16",
        "KEY4$iob":  "IOB_C_PIN_M15",
        "TXD$iob":   "IOB_TXD_PIN_G1",
        "LED[0]$iob": "IOB_Q_PIN_G15",
        "LED[1]$iob": "IOB_LED_1_PIN_F16",
        "LED[2]$iob": "IOB_LED_2_PIN_F15",
        "LED[3]$iob": "IOB_LED_3_PIN_D16",
    }
    pin_script = WORK / "pin_constraints.py"
    pin_script.write_text(
        "# Auto-generated pin constraints for AX301\n"
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
    print(f"  Generated pin constraint script ({len(PIN_MAP)} pins)")

    # --- Step 2: nextpnr-generic ---
    print("\n=== Step 2: nextpnr placement + routing ===", flush=True)
    if not chipdb_json.exists():
        print("ERROR: chipdb not found. Run: python3 fuzz/chipdb_gen.py")
        sys.exit(1)

    placed_json = WORK / "test_top_placed.json"

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
                                   "routed", "slack", "info: program",
                                   "info: device"]):
            print(f"  {line}")

    # --- Step 3: np2fasm ---
    print("\n=== Step 3: np2fasm ===", flush=True)
    fasm_path = WORK / "test_top.fasm"
    from np2fasm import convert
    routed_data = json.loads(placed_json.read_text())
    fasm_lines, warnings = convert(routed_data, baseline="pure")
    fasm_text = "\n".join(fasm_lines) + "\n"
    fasm_path.write_text(fasm_text)
    print(f"  FASM: {len(fasm_lines)} lines")

    if warnings:
        print(f"  Warnings: {len(warnings)}")
        for w in warnings[:20]:
            print(f"    {w}")

    # --- Step 4: fasm2rbf ---
    print("\n=== Step 4: fasm2rbf ===", flush=True)
    from pure_zero_rbf import make_pure_zero_rbf
    from fasm2rbf import bitgen

    base_rbf = make_pure_zero_rbf()
    result_rbf = bitgen(fasm_text, base_rbf, lenient=True)
    OUT_RBF.write_bytes(result_rbf)
    print(f"  RBF: {len(result_rbf)} bytes → {OUT_RBF}")

    # --- Step 5: Compare with Quartus gold ---
    gold_rbf_path = REPO / "tmp" / "pipeline_test_gold.rbf"
    if gold_rbf_path.exists():
        gold = gold_rbf_path.read_bytes()
        if gold == result_rbf:
            print("\n  BYTE-IDENTICAL to Quartus gold!")
        else:
            diffs = sum(1 for a, b in zip(gold, result_rbf) if a != b)
            print(f"\n  Differs from Quartus gold: {diffs} bytes")

    print("\nDone. Flash with:")
    print(f"  openFPGALoader -c usb-blaster {OUT_RBF}")


if __name__ == "__main__":
    main()
